import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Button } from '@/components/common/Button'
import { Card } from '@/components/common/Card'
import { FiMic, FiMicOff, FiActivity, FiUser, FiUsers } from 'react-icons/fi'
import type {
  ExtractedEntity,
  AmbientWSMessage
} from '@/types/api.types'

interface TranscriptionEntry {
  text: string
  speaker?: string
  speakerLabel?: string
  timestamp: number
  confidence: number
}

interface SpeakerInfo {
  speakerId: string
  label: string | null
  suggestedLabel: string
  firstSeen: number
}

interface AmbientListeningProps {
  onTranscription?: (text: string) => void
  onEntitiesExtracted?: (entities: ExtractedEntity[]) => void
  onClinicalInputUpdate?: (text: string) => void
}

export const AmbientListening: React.FC<AmbientListeningProps> = ({
  onTranscription,
  onEntitiesExtracted,
  onClinicalInputUpdate
}) => {
  const [isRecording, setIsRecording] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [transcriptions, setTranscriptions] = useState<TranscriptionEntry[]>([])
  const [extractedEntities, setExtractedEntities] = useState<ExtractedEntity[]>([])
  const [speakers, setSpeakers] = useState<Map<string, SpeakerInfo>>(new Map())
  const [diarizationEnabled, setDiarizationEnabled] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [audioLevel, setAudioLevel] = useState(0)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const animationFrameRef = useRef<number>()

  // Get WebSocket URL
  const getWebSocketURL = () => {
    const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
    const wsURL = baseURL.replace(/^http/, 'ws')
    return `${wsURL}/api/v1/ambient/stream`
  }

  // Monitor audio level for visual feedback
  const monitorAudioLevel = useCallback(() => {
    if (!analyserRef.current) return

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount)
    analyserRef.current.getByteFrequencyData(dataArray)

    const average = dataArray.reduce((a, b) => a + b) / dataArray.length
    setAudioLevel(Math.min(100, (average / 256) * 100))

    if (isRecording) {
      animationFrameRef.current = requestAnimationFrame(monitorAudioLevel)
    }
  }, [isRecording])

  // Label a speaker
  const labelSpeaker = useCallback((speakerId: string, label: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'label_speaker',
        speaker_id: speakerId,
        label: label
      }))
    }

    setSpeakers(prev => {
      const updated = new Map(prev)
      const speaker = updated.get(speakerId)
      if (speaker) {
        updated.set(speakerId, { ...speaker, label })
      }
      return updated
    })
  }, [])

  // Initialize WebSocket connection
  const connectWebSocket = useCallback(() => {
    return new Promise<WebSocket>((resolve, reject) => {
      const token = localStorage.getItem('access_token')
      const wsURL = `${getWebSocketURL()}?token=${token}`

      const ws = new WebSocket(wsURL)

      ws.onopen = () => {
        console.log('Ambient listening WebSocket connected')
        resolve(ws)
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        reject(new Error('Failed to connect to ambient listening service'))
      }

      ws.onmessage = (event) => {
        try {
          const message: AmbientWSMessage = JSON.parse(event.data)

          switch (message.type) {
            case 'transcription':
              const text = (message as any).text
              const speaker = (message as any).speaker
              const speakerLabel = (message as any).speaker_label
              const timestamp = (message as any).timestamp
              const confidence = (message as any).confidence

              // Add transcription entry
              setTranscriptions(prev => [...prev, {
                text,
                speaker,
                speakerLabel,
                timestamp,
                confidence
              }])

              // Call callbacks
              if (onTranscription) {
                onTranscription(text)
              }
              if (onClinicalInputUpdate) {
                const fullText = [...transcriptions, { text }].map(t => t.text).join(' ')
                onClinicalInputUpdate(fullText)
              }
              break

            case 'entities':
              const entities = (message as any).entities

              // Update entities (merge with existing)
              setExtractedEntities(prev => {
                const merged = [...prev]
                entities.forEach((entity: ExtractedEntity) => {
                  const existingIndex = merged.findIndex(e => e.field === entity.field)
                  if (existingIndex >= 0) {
                    if (entity.confidence > merged[existingIndex].confidence) {
                      merged[existingIndex] = entity
                    }
                  } else {
                    merged.push(entity)
                  }
                })
                return merged
              })

              if (onEntitiesExtracted) {
                onEntitiesExtracted(entities)
              }
              break

            case 'speaker_identified':
              const speakerId = (message as any).speaker_id
              const suggestedLabel = (message as any).suggested_label

              setSpeakers(prev => {
                const updated = new Map(prev)
                if (!updated.has(speakerId)) {
                  updated.set(speakerId, {
                    speakerId,
                    label: null,
                    suggestedLabel,
                    firstSeen: Date.now()
                  })
                }
                return updated
              })

              setDiarizationEnabled(true)
              break

            case 'speaker_labeled':
              // Confirmation that speaker was labeled
              console.log(`Speaker ${(message as any).speaker_id} labeled as ${(message as any).label}`)
              break

            case 'info':
              console.log((message as any).message)
              if ((message as any).message.includes('disabled')) {
                setDiarizationEnabled(false)
              }
              break

            case 'error':
              const errorMsg = (message as any).message
              setError(errorMsg)
              break

            case 'stopped':
              console.log('Ambient listening stopped by server')
              stopRecording()
              break
          }
        } catch (err) {
          console.error('Error parsing WebSocket message:', err)
        }
      }

      ws.onclose = () => {
        console.log('Ambient listening WebSocket closed')
      }
    })
  }, [transcriptions, onTranscription, onEntitiesExtracted, onClinicalInputUpdate])

  // Start recording
  const startRecording = async () => {
    try {
      setIsConnecting(true)
      setError(null)

      // Check if getUserMedia is available (requires HTTPS or localhost)
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error(
          'Microphone access requires HTTPS or localhost. ' +
          'Please access the application via https:// or use localhost instead of the network IP.'
        )
      }

      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000
        }
      })

      // Set up audio context for visualization
      audioContextRef.current = new AudioContext({ sampleRate: 16000 })
      const source = audioContextRef.current.createMediaStreamSource(stream)
      analyserRef.current = audioContextRef.current.createAnalyser()
      analyserRef.current.fftSize = 256
      source.connect(analyserRef.current)

      // Connect WebSocket
      const ws = await connectWebSocket()
      wsRef.current = ws

      // Set up MediaRecorder
      const mimeType = MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : 'audio/ogg'

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType,
        audioBitsPerSecond: 16000
      })

      mediaRecorderRef.current = mediaRecorder

      // Handle audio data
      mediaRecorder.ondataavailable = async (event) => {
        if (event.data.size > 0) {
          // Convert to base64 and send via WebSocket
          const reader = new FileReader()
          reader.onloadend = () => {
            const base64Audio = (reader.result as string).split(',')[1]

            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({
                type: 'audio',
                data: base64Audio,
                format: mimeType.includes('webm') ? 'webm' : 'ogg',
                sample_rate: 16000
              }))
            }
          }
          reader.readAsDataURL(event.data)
        }
      }

      // Start recording with 2-second chunks
      mediaRecorder.start(2000)
      setIsRecording(true)
      setIsConnecting(false)

      // Start audio level monitoring
      monitorAudioLevel()

    } catch (err: any) {
      console.error('Failed to start recording:', err)
      setError(err.message || 'Failed to start recording. Please check microphone permissions.')
      setIsConnecting(false)
    }
  }

  // Stop recording
  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop())
      mediaRecorderRef.current = null
    }

    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }

    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ type: 'stop' }))
      wsRef.current.close()
      wsRef.current = null
    }

    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
    }

    setIsRecording(false)
    setAudioLevel(0)
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopRecording()
    }
  }, [])

  // Get speaker label color
  const getSpeakerColor = (label: string | null) => {
    if (!label) return 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
    const colors: Record<string, string> = {
      'Clinician': 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
      'Patient': 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
      'Family': 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
      'Other': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300'
    }
    return colors[label] || 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
  }

  return (
    <Card className="p-6">
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <FiActivity className="h-5 w-5 text-medical" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Ambient Listening
              {diarizationEnabled && (
                <span className="ml-2 text-xs font-normal text-gray-600 dark:text-gray-400">
                  with Speaker Identification
                </span>
              )}
            </h3>
          </div>

          {/* Recording Indicator */}
          {isRecording && (
            <div className="flex items-center space-x-2">
              <div className="flex space-x-1">
                <div className="w-1 h-4 bg-error rounded animate-pulse" style={{ animationDelay: '0ms' }} />
                <div className="w-1 h-4 bg-error rounded animate-pulse" style={{ animationDelay: '150ms' }} />
                <div className="w-1 h-4 bg-error rounded animate-pulse" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-sm text-error font-medium">Recording</span>
            </div>
          )}
        </div>

        {/* Control Button */}
        <div className="flex justify-center">
          <Button
            variant={isRecording ? 'error' : 'medical'}
            size="lg"
            onClick={isRecording ? stopRecording : startRecording}
            isLoading={isConnecting}
            disabled={isConnecting}
            icon={isRecording ? <FiMicOff /> : <FiMic />}
            className="px-8"
          >
            {isRecording ? 'Stop Listening' : 'Start Listening'}
          </Button>
        </div>

        {/* Audio Level Visualizer */}
        {isRecording && (
          <div className="space-y-2">
            <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400">
              <span>Audio Level</span>
              <span>{Math.round(audioLevel)}%</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div
                className="bg-medical h-2 rounded-full transition-all duration-100"
                style={{ width: `${audioLevel}%` }}
              />
            </div>
          </div>
        )}

        {/* Error Display */}
        {error && (
          <div className="p-3 bg-error/10 border border-error rounded-lg">
            <p className="text-sm text-error">{error}</p>
          </div>
        )}

        {/* Speaker Labeling */}
        {diarizationEnabled && speakers.size > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center">
              <FiUsers className="mr-2" />
              Identified Speakers ({speakers.size})
            </h4>
            <div className="space-y-2">
              {Array.from(speakers.values()).map(speaker => (
                <div key={speaker.speakerId} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                  <div className="flex items-center space-x-2">
                    <FiUser className="text-gray-400" />
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      {speaker.speakerId}
                    </span>
                    {speaker.label && (
                      <span className={`px-2 py-0.5 text-xs font-medium rounded ${getSpeakerColor(speaker.label)}`}>
                        {speaker.label}
                      </span>
                    )}
                  </div>
                  {!speaker.label && (
                    <div className="flex items-center space-x-2">
                      <span className="text-xs text-gray-500 dark:text-gray-400">Label as:</span>
                      {['Clinician', 'Patient', 'Family', 'Other'].map(label => (
                        <button
                          key={label}
                          onClick={() => labelSpeaker(speaker.speakerId, label)}
                          className={`px-2 py-1 text-xs rounded transition-colors ${getSpeakerColor(label)} hover:opacity-80`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Transcription History with Speakers */}
        {transcriptions.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Transcription History:
            </h4>
            <div className="max-h-64 overflow-y-auto space-y-2 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
              {transcriptions.map((entry, idx) => (
                <div key={idx} className="space-y-1">
                  {diarizationEnabled && entry.speakerLabel && (
                    <div className="flex items-center space-x-2">
                      <span className={`px-2 py-0.5 text-xs font-medium rounded ${getSpeakerColor(entry.speakerLabel)}`}>
                        {entry.speakerLabel}
                      </span>
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {Math.round(entry.confidence * 100)}% confidence
                      </span>
                    </div>
                  )}
                  <p className="text-sm text-gray-700 dark:text-gray-300">
                    {entry.text}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Extracted Entities */}
        {extractedEntities.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Extracted Clinical Data: ({extractedEntities.length})
            </h4>
            <div className="grid grid-cols-2 gap-2">
              {extractedEntities.map((entity, idx) => (
                <div
                  key={idx}
                  className="p-2 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded"
                >
                  <div className="text-xs font-medium text-gray-600 dark:text-gray-400">
                    {entity.field.replace(/_/g, ' ').toUpperCase()}
                  </div>
                  <div className="text-sm font-semibold text-gray-900 dark:text-white">
                    {typeof entity.value === 'number'
                      ? entity.value.toFixed(2)
                      : entity.value}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    {Math.round(entity.confidence * 100)}% confidence
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Usage Info */}
        {!isRecording && transcriptions.length === 0 && (
          <div className="text-center p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Click <strong>Start Listening</strong> to begin capturing audio from your clinical encounter.
              <br />
              Transcription and entity extraction will happen in real-time.
              {diarizationEnabled ? (
                <>
                  <br />
                  <strong>Speaker diarization enabled:</strong> Speakers will be automatically identified.
                </>
              ) : (
                <>
                  <br />
                  <em>Note: Speaker diarization requires pyannote-audio and HuggingFace token.</em>
                </>
              )}
            </p>
          </div>
        )}
      </div>
    </Card>
  )
}
