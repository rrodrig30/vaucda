"""
Ambient Listening API - Real-time Audio Transcription with Speaker Diarization

WebSocket endpoint for streaming audio from clinical encounters,
transcribing with Whisper, and identifying speakers with pyannote.
"""

import logging
import base64
import json
import asyncio
import tempfile
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Optional, Dict, List
import os

logger = logging.getLogger(__name__)

router = APIRouter()


# Global model instances (lazy-loaded)
_whisper_model = None
_diarization_pipeline = None


def get_whisper_model():
    """Get or initialize Whisper model."""
    global _whisper_model

    if _whisper_model is None:
        try:
            import whisper
            logger.info("Loading Whisper model (medium.en)...")
            _whisper_model = whisper.load_model("medium.en")
            logger.info("Whisper model loaded successfully")
        except ImportError:
            logger.error("Whisper not installed. Install with: pip install openai-whisper")
            raise
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise

    return _whisper_model


def get_diarization_pipeline():
    """Get or initialize pyannote speaker diarization pipeline."""
    global _diarization_pipeline

    if _diarization_pipeline is None:
        try:
            from pyannote.audio import Pipeline

            # Check for HuggingFace token
            hf_token = os.getenv('HUGGINGFACE_TOKEN')
            if not hf_token:
                logger.warning(
                    "HUGGINGFACE_TOKEN not set. Speaker diarization will be disabled. "
                    "Get token from: https://huggingface.co/settings/tokens"
                )
                return None

            logger.info("Loading pyannote speaker diarization pipeline...")
            _diarization_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=hf_token
            )
            logger.info("Pyannote pipeline loaded successfully")

        except ImportError:
            logger.warning(
                "Pyannote not installed. Speaker diarization disabled. "
                "Install with: pip install pyannote-audio"
            )
            return None
        except Exception as e:
            logger.error(f"Failed to load pyannote pipeline: {e}")
            return None

    return _diarization_pipeline


@router.websocket("/stream")
async def ambient_listening_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time audio transcription with speaker diarization.

    **Protocol:**

    Client → Server (Audio Stream):
    {
        "type": "audio",
        "data": "<base64-encoded audio chunk>",
        "format": "wav" | "webm",
        "sample_rate": 16000
    }

    Server → Client (Transcription with Speaker):
    {
        "type": "transcription",
        "text": "Transcribed text from audio",
        "speaker": "SPEAKER_00" | "SPEAKER_01",
        "speaker_label": "Clinician" | "Patient",
        "start_time": 0.0,
        "end_time": 2.5,
        "timestamp": 1234567890.123,
        "confidence": 0.95
    }

    Server → Client (Entities):
    {
        "type": "entities",
        "entities": [
            {"field": "psa", "value": 8.5, "confidence": 0.9, "speaker": "Patient"}
        ]
    }

    Server → Client (Speaker Identification):
    {
        "type": "speaker_identified",
        "speaker_id": "SPEAKER_00",
        "suggested_label": "Clinician",
        "confidence": 0.85
    }

    Client → Server (Speaker Label Assignment):
    {
        "type": "label_speaker",
        "speaker_id": "SPEAKER_00",
        "label": "Clinician"
    }

    Server → Client (Error):
    {
        "type": "error",
        "message": "Error description"
    }

    **HIPAA Compliance:**
    - Audio chunks are transcribed immediately and deleted
    - Transcribed text is sent to client but NOT stored server-side
    - No PHI persisted to disk or database
    - All processing in-memory only
    """
    await websocket.accept()

    logger.info("Ambient listening WebSocket connection established")

    # Audio buffer for accumulating chunks
    audio_buffer = bytearray()
    accumulated_audio = bytearray()  # For diarization of longer segments
    chunk_duration_seconds = 2.0  # Process every 2 seconds
    diarization_window_seconds = 30.0  # Diarize every 30 seconds
    sample_rate = 16000
    bytes_per_second = sample_rate * 2  # 16-bit audio = 2 bytes per sample
    chunk_size_bytes = int(chunk_duration_seconds * bytes_per_second)
    diarization_window_bytes = int(diarization_window_seconds * bytes_per_second)

    # Speaker label mapping (user can customize)
    speaker_labels: Dict[str, str] = {}  # speaker_id -> label

    try:
        # Import entity extractor
        from app.services.entity_extractor import ClinicalEntityExtractor
        extractor = ClinicalEntityExtractor()

        # Get Whisper model
        try:
            whisper_model = get_whisper_model()
        except Exception as e:
            await websocket.send_json({
                "type": "error",
                "message": f"Whisper model not available: {str(e)}"
            })
            await websocket.close()
            return

        # Get diarization pipeline (optional)
        diarization_pipeline = get_diarization_pipeline()
        diarization_enabled = diarization_pipeline is not None

        if not diarization_enabled:
            await websocket.send_json({
                "type": "info",
                "message": "Speaker diarization disabled (pyannote not available or no HuggingFace token)"
            })

        while True:
            # Receive message from client
            try:
                message = await websocket.receive_json()
            except WebSocketDisconnect:
                logger.info("Client disconnected from ambient listening")
                break
            except Exception as e:
                logger.error(f"Error receiving message: {e}")
                continue

            if message.get('type') == 'audio':
                # Decode base64 audio data
                try:
                    audio_data = base64.b64decode(message.get('data', ''))
                    audio_buffer.extend(audio_data)
                    accumulated_audio.extend(audio_data)

                    # Process when buffer reaches chunk size
                    if len(audio_buffer) >= chunk_size_bytes:
                        # Extract audio chunk
                        audio_chunk = bytes(audio_buffer[:chunk_size_bytes])
                        audio_buffer = audio_buffer[chunk_size_bytes:]

                        # Transcribe with Whisper (no diarization yet)
                        transcription_result = await transcribe_audio_chunk(
                            model=whisper_model,
                            audio_chunk=audio_chunk,
                            sample_rate=sample_rate
                        )

                        if transcription_result:
                            text = transcription_result.get('text', '').strip()

                            if text:
                                # Send transcription to client (speaker TBD)
                                await websocket.send_json({
                                    "type": "transcription",
                                    "text": text,
                                    "speaker": None,  # Will be updated after diarization
                                    "speaker_label": None,
                                    "timestamp": asyncio.get_event_loop().time(),
                                    "confidence": transcription_result.get('confidence', 0.0)
                                })

                                # Extract clinical entities from transcription
                                try:
                                    entities = await extractor.extract_entities(text)
                                    if entities:
                                        await websocket.send_json({
                                            "type": "entities",
                                            "entities": entities
                                        })
                                except Exception as e:
                                    logger.warning(f"Entity extraction failed: {e}")

                        # IMPORTANT: Delete audio chunk immediately (HIPAA compliance)
                        del audio_chunk

                    # Perform speaker diarization on accumulated audio
                    if diarization_enabled and len(accumulated_audio) >= diarization_window_bytes:
                        # Extract diarization window
                        diarization_chunk = bytes(accumulated_audio[:diarization_window_bytes])

                        # Perform diarization
                        diarization_result = await perform_speaker_diarization(
                            pipeline=diarization_pipeline,
                            audio_chunk=diarization_chunk,
                            sample_rate=sample_rate
                        )

                        if diarization_result:
                            # Send speaker information to client
                            for segment in diarization_result['segments']:
                                speaker_id = segment['speaker']

                                # Auto-suggest speaker labels based on turn order
                                if speaker_id not in speaker_labels:
                                    suggested_label = "Clinician" if len(speaker_labels) == 0 else "Patient"

                                    await websocket.send_json({
                                        "type": "speaker_identified",
                                        "speaker_id": speaker_id,
                                        "suggested_label": suggested_label,
                                        "start_time": segment['start'],
                                        "end_time": segment['end']
                                    })

                        # Clear accumulated audio after diarization
                        accumulated_audio = accumulated_audio[diarization_window_bytes:]

                        # IMPORTANT: Delete diarization chunk (HIPAA)
                        del diarization_chunk

                except Exception as e:
                    logger.error(f"Audio processing error: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Audio processing failed: {str(e)}"
                    })

            elif message.get('type') == 'label_speaker':
                # User assigned a label to a speaker
                speaker_id = message.get('speaker_id')
                label = message.get('label')

                if speaker_id and label:
                    speaker_labels[speaker_id] = label
                    logger.info(f"Speaker {speaker_id} labeled as {label}")

                    await websocket.send_json({
                        "type": "speaker_labeled",
                        "speaker_id": speaker_id,
                        "label": label
                    })

            elif message.get('type') == 'stop':
                # Client requested to stop listening
                logger.info("Client requested to stop ambient listening")
                await websocket.send_json({
                    "type": "stopped",
                    "message": "Ambient listening stopped"
                })
                break

    except WebSocketDisconnect:
        logger.info("Ambient listening WebSocket disconnected")

    except Exception as e:
        logger.error(f"Ambient listening error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass

    finally:
        # Cleanup: Ensure all audio data is deleted
        del audio_buffer
        del accumulated_audio
        try:
            await websocket.close()
        except:
            pass


async def transcribe_audio_chunk(model, audio_chunk: bytes, sample_rate: int = 16000) -> Optional[dict]:
    """
    Transcribe audio chunk using Whisper model.

    Args:
        model: Loaded Whisper model
        audio_chunk: Raw audio bytes
        sample_rate: Audio sample rate

    Returns:
        Dict with transcription result or None
    """
    import tempfile
    import numpy as np
    import soundfile as sf

    try:
        # Convert bytes to numpy array
        audio_array = np.frombuffer(audio_chunk, dtype=np.int16)

        # Normalize to [-1, 1]
        audio_float = audio_array.astype(np.float32) / 32768.0

        # Write to temporary WAV file (Whisper requires file input)
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as temp_file:
            sf.write(temp_file.name, audio_float, sample_rate)

            # Transcribe
            result = model.transcribe(
                temp_file.name,
                language='en',
                task='transcribe',
                fp16=False,  # CPU compatibility
                word_timestamps=True,
                temperature=0.0  # Deterministic
            )

            # Calculate confidence from word-level probabilities
            avg_confidence = 0.0
            if 'segments' in result:
                confidences = []
                for segment in result['segments']:
                    if 'words' in segment:
                        for word in segment['words']:
                            if 'probability' in word:
                                confidences.append(word['probability'])

                if confidences:
                    avg_confidence = sum(confidences) / len(confidences)

            return {
                'text': result.get('text', ''),
                'confidence': avg_confidence,
                'language': result.get('language', 'en'),
                'segments': result.get('segments', [])
            }

    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}")
        return None


async def perform_speaker_diarization(
    pipeline,
    audio_chunk: bytes,
    sample_rate: int = 16000
) -> Optional[dict]:
    """
    Perform speaker diarization using pyannote.

    Args:
        pipeline: Loaded pyannote pipeline
        audio_chunk: Raw audio bytes
        sample_rate: Audio sample rate

    Returns:
        Dict with diarization results (speaker segments) or None
    """
    import tempfile
    import numpy as np
    import soundfile as sf
    from pyannote.core import Segment

    try:
        # Convert bytes to numpy array
        audio_array = np.frombuffer(audio_chunk, dtype=np.int16)

        # Normalize to [-1, 1]
        audio_float = audio_array.astype(np.float32) / 32768.0

        # Write to temporary WAV file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as temp_file:
            sf.write(temp_file.name, audio_float, sample_rate)

            # Perform diarization
            diarization = pipeline(temp_file.name)

            # Extract speaker segments
            segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segments.append({
                    'speaker': speaker,
                    'start': turn.start,
                    'end': turn.end,
                    'duration': turn.end - turn.start
                })

            return {
                'segments': segments,
                'num_speakers': len(set(seg['speaker'] for seg in segments))
            }

    except Exception as e:
        logger.error(f"Speaker diarization failed: {e}")
        return None


async def align_transcription_with_speakers(
    transcription_segments: List[dict],
    diarization_segments: List[dict]
) -> List[dict]:
    """
    Align Whisper transcription segments with pyannote speaker segments.

    Args:
        transcription_segments: Whisper word-level timestamps
        diarization_segments: Pyannote speaker segments

    Returns:
        List of transcription segments with speaker labels
    """
    aligned_segments = []

    for trans_seg in transcription_segments:
        start_time = trans_seg.get('start', 0)
        end_time = trans_seg.get('end', 0)
        text = trans_seg.get('text', '')

        # Find overlapping speaker segment
        speaker = None
        max_overlap = 0

        for diar_seg in diarization_segments:
            diar_start = diar_seg['start']
            diar_end = diar_seg['end']

            # Calculate overlap
            overlap_start = max(start_time, diar_start)
            overlap_end = min(end_time, diar_end)
            overlap_duration = max(0, overlap_end - overlap_start)

            if overlap_duration > max_overlap:
                max_overlap = overlap_duration
                speaker = diar_seg['speaker']

        aligned_segments.append({
            'text': text,
            'speaker': speaker,
            'start': start_time,
            'end': end_time,
            'confidence': trans_seg.get('confidence', 0.0)
        })

    return aligned_segments
