"""
Note Generation API endpoints
Handles clinical note generation with LLM and RAG

Supports task-specific LLM configuration:
- OCR: Uses ocr_llm config from user settings
- Stage 1: Uses stage1_llm config from user settings
- Stage 2: Uses stage2_llm config from user settings (with RAG/GraphRAG)
"""

import asyncio
import logging
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Request, File, Form, UploadFile, Header
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_active_user
from app.config import settings
from app.database.sqlite_models import User, UserPreferences
from app.database.sqlite_session import get_db
from app.schemas.notes import (
    NoteGenerateRequest,
    NoteResponse,
    InitialNoteRequest,
    InitialNoteResponse,
    FinalNoteRequest,
    FinalNoteResponse,
    DocumentUploadResponse,
    BatchProcessingRequest,
    BatchProcessingResponse,
    BatchFileResult,
    BatchFileStatus,
    BatchFolderListResponse,
    BatchFolderFile,
)
from app.services.document_processor import DocumentProcessor
from app.services.temp_file_manager import TempFileManager
from app.services.note_generator import NoteGenerator
from app.services.llm_config_manager import LLMConfigManager, LLMTaskType
from llm.llm_manager import LLMManager, TaskType

logger = logging.getLogger(__name__)

router = APIRouter()


# Global shared LLM manager instance (singleton)
# Initialize once at module level to avoid reloading models for each request
_global_llm_manager: LLMManager = None

def get_llm_manager() -> LLMManager:
    """Get or create the global LLM manager instance."""
    global _global_llm_manager
    if _global_llm_manager is None:
        _global_llm_manager = LLMManager()
    return _global_llm_manager


async def _get_user_source_format(user_id: str, db) -> str:
    """Look up the user's preferred source EHR format ('cprs' | 'vista').

    Returns 'cprs' on any error / missing pref so existing single-tenant
    deployments behave exactly as before.
    """
    try:
        stmt = select(UserPreferences).where(UserPreferences.user_id == user_id)
        result = await db.execute(stmt)
        prefs = result.scalars().first()
        sf = (prefs.source_format if prefs and prefs.source_format else "cprs").lower()
        return "vista" if sf == "vista" else "cprs"
    except Exception:
        return "cprs"


# Dependency injection - get note generator using app.state resources
def get_note_generator(request: Request) -> NoteGenerator:
    """Get note generator instance with dependencies from app.state."""
    try:
        # Get shared LLM manager instance
        llm_manager = get_llm_manager()

        # Use Neo4j client from app.state (initialized at startup)
        neo4j_client = getattr(request.app.state, 'neo4j', None)
        if neo4j_client is None:
            logger.warning("Neo4j not available from app.state")

        # Get embedding generator from RAG pipeline if available
        rag_pipeline = getattr(request.app.state, 'rag_pipeline', None)
        embedding_generator = None
        if rag_pipeline is not None:
            embedding_generator = getattr(rag_pipeline, 'embedding_generator', None)

        # Create note generator
        note_gen = NoteGenerator(
            llm_manager=llm_manager,
            neo4j_client=neo4j_client,
            embedding_generator=embedding_generator
        )

        return note_gen

    except Exception as e:
        logger.error(f"Failed to initialize note generator: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Note generation service temporarily unavailable"
        )


# ============================================================================
# DOCUMENT UPLOAD ENDPOINT (OCR Support)
# ============================================================================

@router.post("/upload-document", response_model=DocumentUploadResponse)
async def upload_document_for_stage1(
    file: UploadFile = File(..., description="PDF or TXT file to process"),
    session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a clinical document (PDF or TXT) for Stage 1 note generation.

    For image-based PDFs (scanned documents), automatically uses OCR
    with user-configured OCR LLM settings from Settings page.

    Extracted text is saved to a session-linked temp file for HIPAA compliance.
    Temp files are automatically deleted after Stage 2 completion.

    **Supported file types:** PDF, TXT
    **Max file size:** 10MB

    Returns:
        - extracted_text: The text content from the document
        - temp_file_id: ID for temp file (deleted after Stage 2)
        - extraction_method: "text" or "ocr"
        - page_count: Number of pages processed (PDFs)
    """
    try:
        # Validate file type
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File name is required"
            )

        lower_name = file.filename.lower()
        if not (lower_name.endswith('.pdf') or lower_name.endswith('.txt')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type. Only PDF and TXT files are allowed."
            )

        # Check file size (read to validate)
        content = await file.read()
        max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

        if len(content) > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE_MB}MB."
            )

        # Reset file position for processor
        await file.seek(0)

        logger.info(
            f"User {current_user.id} uploading document: {file.filename} "
            f"({len(content)} bytes)"
        )

        # Load task-specific LLM config for OCR from user settings
        llm_config_manager = LLMConfigManager(user_id=current_user.user_id)
        await llm_config_manager.load_from_database(db)
        ocr_config = llm_config_manager.get_config(LLMTaskType.OCR)

        logger.info(f"Using OCR config: provider={ocr_config.provider}, model={ocr_config.model}")

        # Process document with user's OCR LLM config
        processor = DocumentProcessor(task_config=ocr_config)
        result = await processor.process_document(file)

        # Generate session ID if not provided
        effective_session_id = session_id or f"user_{current_user.id}"

        # Save to temp file
        temp_manager = TempFileManager()
        temp_file_id = temp_manager.save_temp_file(
            content=result.text,
            session_id=effective_session_id
        )

        logger.info(
            f"Document processed: {result.extraction_method} extraction, "
            f"{result.page_count} pages, {len(result.text)} chars. "
            f"Temp file: {temp_file_id}"
        )

        return DocumentUploadResponse(
            extracted_text=result.text,
            temp_file_id=temp_file_id,
            extraction_method=result.extraction_method,
            page_count=result.page_count,
            file_name=result.file_name,
            file_size_bytes=result.file_size_bytes
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {str(e)}"
        )


@router.post("/generate", response_model=NoteResponse)
async def generate_note(
    request: NoteGenerateRequest,
    current_user: User = Depends(get_current_active_user),
    note_generator: NoteGenerator = Depends(get_note_generator)
):
    """
    Generate clinical note from unstructured input.

    This endpoint:
    1. Runs specified clinical calculators
    2. Retrieves relevant knowledge via RAG (if enabled)
    3. Generates structured note using LLM
    4. Returns note with calculator results and sources

    **Note:** No PHI is logged or stored permanently.
    """
    try:
        logger.info(
            f"User {current_user.id} requesting note generation "
            f"(type: {request.note_type}, provider: {request.llm_provider})"
        )

        # Generate note
        result = await note_generator.generate_note(
            clinical_input=request.input_text,
            note_type=request.note_type,
            llm_provider=request.llm_provider,
            calculator_ids=request.calculator_ids,
            use_rag=request.use_rag,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )

        logger.info(
            f"Note generated successfully for user {current_user.id} "
            f"(time: {result.metadata.get('generation_time_seconds', 0):.2f}s)"
        )

        return NoteResponse(**result.dict())

    except Exception as e:
        logger.error(f"Note generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Note generation failed: {str(e)}"
        )


@router.websocket("/generate-stream")
async def generate_note_stream(websocket: WebSocket):
    """
    Generate note with streaming (WebSocket).

    Streams generated text in real-time for better UX.

    **Protocol:**
    1. Client sends JSON with NoteGenerateRequest fields
    2. Server streams text chunks
    3. Server sends final metadata as JSON with type="metadata"
    """
    await websocket.accept()

    try:
        # Receive request data
        data = await websocket.receive_json()

        logger.info(f"WebSocket note generation started (type: {data.get('note_type', 'clinic')})")

        # Validate request (basic validation)
        if not data.get('input_text'):
            await websocket.send_json({
                "type": "error",
                "message": "Missing required field: input_text"
            })
            await websocket.close()
            return

        # Initialize note generator
        note_generator = get_note_generator()

        # Stream note generation
        async for chunk in note_generator.generate_note_stream(
            clinical_input=data.get('input_text'),
            note_type=data.get('note_type', 'clinic'),
            llm_provider=data.get('llm_provider', 'ollama'),
            calculator_ids=data.get('calculator_ids', []),
            use_rag=data.get('use_rag', True),
            temperature=data.get('temperature', 0.3),
            max_tokens=data.get('max_tokens')
        ):
            await websocket.send_json({
                "type": "chunk",
                "content": chunk
            })

        # Send completion signal
        await websocket.send_json({
            "type": "complete"
        })

        logger.info("WebSocket note generation completed")

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")

    except Exception as e:
        logger.error(f"WebSocket note generation failed: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass

    finally:
        try:
            await websocket.close()
        except:
            pass


# ============================================================================
# TWO-STAGE WORKFLOW ENDPOINTS (Improved Clinical Workflow)
# ============================================================================

@router.post("/generate-initial", response_model=InitialNoteResponse)
async def generate_initial_note(
    request: InitialNoteRequest,
    http_request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    STAGE 1: Generate preliminary note with calculator suggestions.

    Uses user-configured Stage 1 LLM settings from Settings page.

    This endpoint:
    1. Organizes clinical data into structured note format
    2. Extracts clinical entities using NLP
    3. Suggests relevant calculators based on available data
    4. Returns note WITHOUT Assessment & Plan

    The preliminary note allows clinicians to review organized data
    before selecting which calculators to run.
    """
    from app.schemas.notes import InitialNoteResponse, ExtractedEntity, CalculatorSuggestion
    from app.services.entity_extractor import ClinicalEntityExtractor
    from app.services.calculator_suggester import get_calculator_suggester
    from pathlib import Path
    import time

    try:
        start_time = time.time()

        # Load task-specific LLM config for Stage 1 from user settings
        llm_config_manager = LLMConfigManager(user_id=current_user.user_id)
        await llm_config_manager.load_from_database(db)
        stage1_config = llm_config_manager.get_config(LLMTaskType.STAGE1)

        logger.info(f"Using Stage 1 LLM config: provider={stage1_config.provider}, model={stage1_config.model}")

        # Load urology system prompt
        urology_prompt_file = Path(__file__).parent.parent.parent.parent / "urology_prompt.txt"
        urology_system_prompt = ""
        try:
            with open(urology_prompt_file, 'r') as f:
                urology_system_prompt = f.read()
            logger.info(f"Loaded urology system prompt ({len(urology_system_prompt)} chars)")
        except Exception as e:
            logger.warning(f"Could not load urology_prompt.txt: {e}")

        logger.info(
            f"User {current_user.id} requesting initial note generation "
            f"(type: {request.note_type}, provider: {stage1_config.provider}, model: {stage1_config.model})"
        )

        # Step 1: Retrieve context via Vector RAG (for structured note generation)
        rag_context = ""
        rag_sources = []

        if request.use_rag:
            try:
                # Use RAG pipeline from app.state (initialized at startup)
                rag_pipeline = getattr(http_request.app.state, 'rag_pipeline', None)
                if rag_pipeline is not None:
                    # Use VECTOR RAG for structured note component extraction
                    # Vector search is best for finding similar documentation patterns
                    rag_result = await rag_pipeline.retrieve_and_augment(
                        query=request.clinical_input,
                        k=3,  # Fewer results for preliminary note
                        search_strategy="vector",  # Vector RAG for note structure
                        category=None
                    )

                    rag_context = rag_result.context
                    rag_sources = rag_result.sources

                    logger.info(
                        f"Retrieved {len(rag_sources)} RAG sources via vector search "
                        f"({len(rag_context)} chars context)"
                    )
                else:
                    logger.warning("RAG pipeline not available in app.state")
            except Exception as e:
                logger.warning(f"RAG retrieval failed: {e}")

        # Step 3: Generate preliminary note using section extraction + template builder (Stage 1)
        note_generator = get_note_generator(http_request)

        logger.info("Stage 1: Extracting and organizing clinical data using regex-based section extraction...")

        # Check input size to determine processing strategy
        input_size_chars = len(request.clinical_input)
        input_size_tokens = input_size_chars // 4  # Rough estimate: 4 chars/token

        # CRITICAL FIX: Always use agentic extraction pipeline with section extraction + template builder
        # This ensures template builder is ALWAYS invoked for ALL extraction workflows
        # The agentic pipeline automatically handles both small and large inputs efficiently
        # NO FILE SIZE THRESHOLD - use agentic extraction for everything (per rules.txt)
        use_agentic_extraction = True  # ALWAYS TRUE for compliance

        logger.info(f"Input size: {input_size_chars} chars / ~{input_size_tokens} tokens")
        logger.info("Using section extraction + template builder (Ollama-based)")

        # Production extraction workflow: Agent-based note processing system
        # Uses the fixed extractors and agents from note_processing
        logger.info("Using agent-based note processing system for structured extraction")

        # Import the fixed note processing system
        from app.services.note_processing.note_builder import build_urology_note

        # Use the agent-based system with all the extraction fixes
        # Pass task_config for Stage 1 LLM settings
        # CRITICAL: Run in thread pool to avoid blocking async event loop
        # build_urology_note contains blocking LLM calls via requests.post()
        # Prepend visit date so extractors (IPSS, age calculation) can use it
        clinical_input_with_date = request.clinical_input
        if request.visit_date:
            clinical_input_with_date = f"VISIT DATE: {request.visit_date}\n\n{request.clinical_input}"

        _src_fmt = await _get_user_source_format(current_user.user_id, db)
        # Compute the authoritative PatientStatusFacts ONCE (multi-cancer ground
        # truth + optional L1 enrichment) and feed it to Stage 1 so the CC/HPI
        # agents anchor on the correct primary. Stage 2 (generate-final) derives
        # the same facts from the same clinical input.
        from app.services.note_processing.note_builder import (
            build_authoritative_patient_facts,
        )
        _shared_facts = await asyncio.to_thread(
            build_authoritative_patient_facts, clinical_input_with_date, _src_fmt,
        )
        preliminary_note = await asyncio.to_thread(
            build_urology_note,
            clinical_text=clinical_input_with_date,
            task_config=stage1_config,
            source_format=_src_fmt,
            patient_facts=_shared_facts,
        )

        logger.info(f"Agent-based note builder complete: {len(preliminary_note)} chars generated")

        # Step 4: Extract clinical entities from the organized preliminary note (not raw input)
        # CRITICAL: Extract from preliminary_note to get most recent/relevant values,
        # not from raw clinical_input which contains years of historical data
        extractor = ClinicalEntityExtractor()
        entities = await extractor.extract_entities(preliminary_note)

        logger.info(f"Extracted {len(entities)} clinical entities from preliminary note")

        # Step 5: Suggest calculators based on extracted entities
        suggester = get_calculator_suggester()
        suggestions = suggester.suggest_calculators(entities)

        logger.info(f"Suggested {len(suggestions)} calculators")

        # Format response
        generation_time = time.time() - start_time

        return InitialNoteResponse(
            preliminary_note=preliminary_note,
            extracted_entities=[ExtractedEntity(**e) for e in entities],
            suggested_calculators=[CalculatorSuggestion(**s) for s in suggestions],
            metadata={
                'generation_time_seconds': round(generation_time, 2),
                'entities_extracted': len(entities),
                'calculators_suggested': len(suggestions),
                'note_type': request.note_type,
                'llm_provider': stage1_config.provider,
                'llm_model': stage1_config.model
            }
        )

    except Exception as e:
        from app.services.note_processing.llm_helper import LLMProviderError
        logger.error(f"Initial note generation failed: {e}", exc_info=True)
        if isinstance(e, LLMProviderError):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Initial note generation failed: {str(e)}"
        )


@router.post("/generate-final", response_model=FinalNoteResponse)
async def generate_final_note(
    request: FinalNoteRequest,
    http_request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    STAGE 2: Generate final note with Assessment & Plan using agent-based architecture.

    This endpoint uses specialized agents:
    - assessment_agent: Synthesizes clinical assessment/impression
    - plan_agent: Synthesizes treatment plan

    Both agents leverage:
    1. Stage 1 preliminary note (historical data organized)
    2. Prior assessments/plans from GU notes
    3. Calculator results (44 specialized calculators)
    4. RAG content (evidence-based guidelines from Neo4j)
    5. User-selected model from Settings

    CRITICAL: Uses session isolation to prevent cross-patient contamination.
    """
    from app.schemas.notes import FinalNoteResponse, CalculatorResultSchema
    from app.services.note_processing.note_identifier import identify_notes
    from app.services.note_processing.stage2_builder import build_stage2_note
    from app.services.note_processing.session_manager import start_patient_session, end_patient_session
    from calculators.registry import CalculatorRegistry
    from app.services.entity_extractor import ClinicalEntityExtractor
    from sqlalchemy import select
    from app.database.sqlite_models import UserPreferences
    import time

    # CRITICAL: Start isolated patient session to prevent cross-contamination
    session = start_patient_session(patient_identifier=f"user_{current_user.id}")
    logger.info(f"Started patient session {session.session_id} for Stage 2 generation")

    try:
        start_time = time.time()

        logger.info(
            f"User {current_user.id} requesting Stage 2 agent-based note generation "
            f"with {len(request.selected_calculators)} calculators"
        )

        # Step 0: Load task-specific LLM config for Stage 2 from user settings
        llm_config_manager = LLMConfigManager(user_id=current_user.user_id)
        await llm_config_manager.load_from_database(db)
        stage2_config = llm_config_manager.get_config(LLMTaskType.STAGE2)

        logger.info(
            f"Using Stage 2 LLM config: provider={stage2_config.provider}, "
            f"model={stage2_config.model}, use_rag={stage2_config.use_rag}, "
            f"use_graphrag={stage2_config.use_graphrag}, rag_top_k={stage2_config.rag_top_k}"
        )

        # Step 1: Identify notes from clinical input (to get GU and non-GU notes)
        logger.info("Step 1: Identifying historical notes...")
        notes_dict = identify_notes(request.clinical_input)
        gu_notes = notes_dict.get("gu_notes", [])
        non_gu_notes = notes_dict.get("non_gu_notes", [])
        logger.info(f"Found {len(gu_notes)} GU notes and {len(non_gu_notes)} non-GU notes for cross-specialty analysis")

        # Step 2: Extract entities for calculator execution from Stage 1 preliminary note
        logger.info("Step 2: Extracting clinical entities...")
        extractor = ClinicalEntityExtractor()
        # CRITICAL: Extract from preliminary_note, NOT clinical_input (raw data)
        entities = await extractor.extract_entities(request.preliminary_note)
        entity_dict = {e['field']: e['value'] for e in entities}

        logger.info(f"Extracted {len(entities)} entities from Stage 1 preliminary note")
        logger.info(f"Entity extraction details:")
        for entity in entities:
            logger.info(f"  - {entity['field']}: {entity['value']} (confidence: {entity['confidence']}, method: {entity['extraction_method']})")
        logger.info(f"Entity dictionary: {entity_dict}")

        # Merge with user-provided additional inputs
        entity_dict.update(request.additional_inputs)
        logger.info(f"Merged with {len(request.additional_inputs)} user-provided inputs")

        # Step 3: Execute selected calculators
        logger.info("Step 3: Executing calculators...")
        registry = CalculatorRegistry()
        calculator_results = []
        calculator_results_dict = {}

        for calc_id in request.selected_calculators:
            try:
                calculator = registry.get(calc_id)
                if calculator is None:
                    logger.warning(f"Calculator not found: {calc_id}")
                    continue

                # Extract required inputs for this calculator
                required_inputs = calculator.required_inputs
                calc_inputs = {k: entity_dict.get(k) for k in required_inputs if k in entity_dict}

                # Run calculator
                result = calculator.calculate(calc_inputs)

                # Format inputs for display
                inputs_display = ", ".join([f"{k}={v}" for k, v in calc_inputs.items()])

                calc_result = {
                    'calculator_id': calc_id,
                    'calculator_name': calculator.name,
                    'result': result.result,
                    'interpretation': result.interpretation,
                    'recommendations': result.recommendations if hasattr(result, 'recommendations') else [],
                    'inputs': calc_inputs,
                    'formatted_output': f"{calculator.name}\nInputs: {inputs_display}\nResult: {result.interpretation}"
                }

                calculator_results.append(calc_result)
                calculator_results_dict[calc_id] = calc_result

                logger.info(f"Calculator {calc_id} executed successfully")

            except Exception as e:
                logger.error(f"Calculator {calc_id} failed: {e}")
                continue

        # Step 4: Retrieve evidence via RAG (if enabled based on stage2_config settings)
        # ROOT CAUSE #1 FIX: Use TARGETED queries based on Chief Complaint, not entire document
        logger.info("Step 4: Retrieving RAG content with targeted queries...")
        rag_sources = []
        rag_content = ""

        # Use RAG settings from stage2_config (user's Settings page preferences)
        effective_use_rag = stage2_config.use_rag
        effective_use_graphrag = stage2_config.use_graphrag
        effective_rag_top_k = stage2_config.rag_top_k

        if effective_use_rag:
            try:
                # Use RAG pipeline from app.state (initialized at startup)
                rag_pipeline = getattr(http_request.app.state, 'rag_pipeline', None)
                if rag_pipeline is not None:
                    # ARCHITECTURAL FIX: Build targeted queries from Chief Complaint
                    # instead of passing entire clinical document
                    from app.services.note_processing.rag_query_builder import build_targeted_rag_queries

                    targeted_queries = build_targeted_rag_queries(
                        preliminary_note=request.preliminary_note,
                        clinical_input=request.clinical_input,
                        max_queries=1
                    )

                    all_sources = []
                    all_contexts = []

                    # Determine search strategy based on user settings
                    search_strategy = "graphrag" if effective_use_graphrag else "vector"
                    logger.info(f"Using search strategy: {search_strategy}, top_k: {effective_rag_top_k}")

                    for query in targeted_queries:
                        logger.info(f"RAG query ({search_strategy}): {query}")
                        try:
                            # Use configured search strategy and top_k from user settings
                            rag_result = await rag_pipeline.retrieve_and_augment(
                                query=query,
                                k=effective_rag_top_k,
                                search_strategy=search_strategy,
                                category=None
                            )

                            if rag_result.context:
                                all_contexts.append(f"[{query}]\n{rag_result.context}")
                            all_sources.extend(rag_result.sources)
                        except Exception as query_error:
                            logger.warning(f"RAG query '{query}' failed: {query_error}")

                    # Combine results
                    rag_content = "\n\n".join(all_contexts)
                    # Deduplicate sources
                    seen_sources = set()
                    for src in all_sources:
                        src_key = str(src) if isinstance(src, dict) else src
                        if src_key not in seen_sources:
                            seen_sources.add(src_key)
                            rag_sources.append(src)

                    logger.info(
                        f"Retrieved {len(rag_sources)} RAG sources from {len(targeted_queries)} targeted queries "
                        f"({len(rag_content)} chars context)"
                    )
                else:
                    logger.warning("RAG pipeline not available in app.state")
            except Exception as e:
                logger.warning(f"RAG retrieval failed: {e}")

        # Step 5: Generate Stage 2 note using agent-based architecture
        logger.info("Step 5: Generating Stage 2 Assessment & Plan using specialized agents...")

        # Ambient transcript placeholder for future ambient listening integration
        # When implemented, this will contain real-time provider-patient conversation
        ambient_transcript = None

        # Compute the authoritative PatientStatusFacts from the SAME raw clinical
        # input Stage 1 used (multi-cancer ground truth + optional L1), so the
        # Assessment/Plan ground on those facts instead of re-deriving a divergent
        # picture from the rendered Stage 1 note.
        from app.services.note_processing.note_builder import (
            build_authoritative_patient_facts,
        )
        _src_fmt = await _get_user_source_format(current_user.user_id, db)
        _final_input = request.clinical_input
        if request.visit_date:
            _final_input = f"VISIT DATE: {request.visit_date}\n\n{request.clinical_input}"
        _shared_facts = await asyncio.to_thread(
            build_authoritative_patient_facts, _final_input, _src_fmt,
        )

        # Build Stage 2 note with task-specific LLM config
        # Pass non_gu_notes for cross-specialty urologic content extraction
        complete_note = build_stage2_note(
            stage1_note=request.preliminary_note,
            gu_notes=gu_notes,
            non_gu_notes=non_gu_notes,
            ambient_transcript=ambient_transcript,
            calculator_results=calculator_results_dict,
            rag_content=rag_content,
            task_config=stage2_config,
            note_type=request.note_type,
            patient_name=request.patient_name,
            ssn_last4=request.ssn_last4,
            patient_facts=_shared_facts,
        )

        logger.info("Stage 2 agent-based note generation complete")

        # Format response
        generation_time = time.time() - start_time

        return FinalNoteResponse(
            final_note=complete_note,
            calculator_results=[CalculatorResultSchema(**r) for r in calculator_results],
            rag_sources=rag_sources,
            metadata={
                'generation_time_seconds': round(generation_time, 2),
                'calculators_executed': len(calculator_results),
                'rag_enabled': effective_use_rag,
                'rag_sources_count': len(rag_sources),
                'gu_notes_found': len(gu_notes),
                'workflow': 'stage2_agent_based',
                'llm_provider': stage2_config.provider,
                'llm_model': stage2_config.model
            }
        )

    except Exception as e:
        from app.services.note_processing.llm_helper import LLMProviderError
        logger.error(f"Stage 2 agent-based note generation failed: {e}", exc_info=True)
        if isinstance(e, LLMProviderError):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stage 2 agent-based note generation failed: {str(e)}"
        )
    finally:
        # CRITICAL: Always purge patient data when session ends
        end_patient_session()
        logger.info("Patient session ended and data purged")

        # Clean up temp files for this user's session (HIPAA compliance)
        try:
            temp_manager = TempFileManager()
            session_id = f"user_{current_user.id}"
            deleted_count = temp_manager.cleanup_session(session_id)
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} temp files for session {session_id}")
        except Exception as cleanup_error:
            logger.warning(f"Temp file cleanup failed: {cleanup_error}")


@router.post("/generate-express", response_model=FinalNoteResponse)
async def generate_express_note(
    request: InitialNoteRequest,
    http_request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    EXPRESS: Run Stage 1 + Stage 2 back-to-back without calculator selection.

    Skips entity extraction, calculator suggestion, and the user-facing
    calculator-selection step. Produces the final note (with A&P) directly
    in a single request. RAG is honored according to user's Stage 2
    settings; ``selected_calculators`` is forced to empty.

    Useful for: quick clinic-note generation when the provider does not
    need calculator-based risk stratification, or for batch workflows.
    """
    from app.schemas.notes import (
        FinalNoteResponse,
        CalculatorResultSchema,
    )
    from app.services.note_processing.note_builder import build_urology_note
    from app.services.note_processing.note_identifier import identify_notes
    from app.services.note_processing.stage2_builder import build_stage2_note
    from app.services.note_processing.session_manager import (
        start_patient_session,
        end_patient_session,
    )
    from pathlib import Path
    import time

    session = start_patient_session(patient_identifier=f"user_{current_user.id}")
    logger.info(f"Started patient session {session.session_id} for Express generation")

    try:
        start_time = time.time()

        # Load Stage 1 + Stage 2 LLM configs
        llm_config_manager = LLMConfigManager(user_id=current_user.user_id)
        await llm_config_manager.load_from_database(db)
        stage1_config = llm_config_manager.get_config(LLMTaskType.STAGE1)
        stage2_config = llm_config_manager.get_config(LLMTaskType.STAGE2)

        logger.info(
            f"Express: Stage 1 LLM={stage1_config.provider}/{stage1_config.model}, "
            f"Stage 2 LLM={stage2_config.provider}/{stage2_config.model}"
        )

        # Step 1: Stage 1 — preliminary note (no entity extraction, no
        # calculator suggestions)
        clinical_input_with_date = request.clinical_input
        if request.visit_date:
            clinical_input_with_date = (
                f"VISIT DATE: {request.visit_date}\n\n{request.clinical_input}"
            )

        logger.info("Express Step 1: Building Stage 1 preliminary note...")
        _src_fmt = await _get_user_source_format(current_user.user_id, db)
        # Phase 1: compute the authoritative PatientStatusFacts ONCE and feed
        # the same object to Stage 1 and Stage 2, so the Assessment grounds on
        # the same facts as the HPI instead of re-deriving (and inventing) a
        # divergent timeline/status from the rendered note.
        from app.services.note_processing.note_builder import (
            build_authoritative_patient_facts,
        )
        _shared_facts = await asyncio.to_thread(
            build_authoritative_patient_facts,
            clinical_input_with_date,
            _src_fmt,
        )
        preliminary_note = await asyncio.to_thread(
            build_urology_note,
            clinical_text=clinical_input_with_date,
            task_config=stage1_config,
            source_format=_src_fmt,
            patient_facts=_shared_facts,
        )
        logger.info(
            f"Express: preliminary note ready ({len(preliminary_note)} chars)"
        )

        # Step 2: Identify GU/non-GU notes for Stage 2
        notes_dict = identify_notes(request.clinical_input)
        gu_notes = notes_dict.get("gu_notes", [])
        non_gu_notes = notes_dict.get("non_gu_notes", [])

        # Step 3: RAG (optional, mirrors generate-final).
        # Low-complexity heuristic: skip RAG entirely for short clinical
        # inputs whose chief complaint matches a routine-followup
        # pattern. Saves ~5-15s on those notes; the LLM can synthesize
        # them adequately from the structured Stage 1 preliminary note
        # alone, since these patients aren't undergoing complex
        # decision-making that benefits from guideline retrieval.
        rag_sources = []
        rag_content = ""
        effective_use_rag = stage2_config.use_rag and request.use_rag
        effective_use_graphrag = stage2_config.use_graphrag
        effective_rag_top_k = stage2_config.rag_top_k

        _input_token_estimate = len(request.clinical_input) // 4
        _routine_cc_patterns = (
            "follow-up", "follow up", "followup", "f/u",
            "post-op", "post op", "postop",
            "routine", "well visit", "annual",
            "med refill", "medication refill", "rx refill",
        )
        _cc_lower = (preliminary_note[:1500] if preliminary_note else "").lower()
        _is_routine_cc = any(p in _cc_lower for p in _routine_cc_patterns)
        if effective_use_rag and _input_token_estimate < 4000 and _is_routine_cc:
            logger.info(
                "Express: skipping RAG for low-complexity routine note "
                "(input ~%d tokens, CC matches routine pattern)",
                _input_token_estimate,
            )
            effective_use_rag = False

        if effective_use_rag:
            try:
                rag_pipeline = getattr(http_request.app.state, 'rag_pipeline', None)
                if rag_pipeline is not None:
                    from app.services.note_processing.rag_query_builder import (
                        build_targeted_rag_queries,
                    )
                    targeted_queries = build_targeted_rag_queries(
                        preliminary_note=preliminary_note,
                        clinical_input=request.clinical_input,
                        max_queries=1,
                    )
                    search_strategy = (
                        "graphrag" if effective_use_graphrag else "vector"
                    )
                    all_sources = []
                    all_contexts = []
                    for query in targeted_queries:
                        try:
                            rag_result = await rag_pipeline.retrieve_and_augment(
                                query=query,
                                k=effective_rag_top_k,
                                search_strategy=search_strategy,
                                category=None,
                            )
                            if rag_result.context:
                                all_contexts.append(
                                    f"[{query}]\n{rag_result.context}"
                                )
                            all_sources.extend(rag_result.sources)
                        except Exception as query_error:
                            logger.warning(
                                f"Express RAG query '{query}' failed: {query_error}"
                            )
                    rag_content = "\n\n".join(all_contexts)
                    seen_sources = set()
                    for src in all_sources:
                        src_key = str(src) if isinstance(src, dict) else src
                        if src_key not in seen_sources:
                            seen_sources.add(src_key)
                            rag_sources.append(src)
            except Exception as e:
                logger.warning(f"Express RAG retrieval failed: {e}")

        # Step 4: Stage 2 — A&P with no calculators
        logger.info("Express Step 2: Building Stage 2 final note (no calculators)...")
        complete_note = build_stage2_note(
            stage1_note=preliminary_note,
            gu_notes=gu_notes,
            non_gu_notes=non_gu_notes,
            ambient_transcript=None,
            calculator_results={},
            rag_content=rag_content,
            task_config=stage2_config,
            note_type=request.note_type,
            patient_name=request.patient_name,
            ssn_last4=request.ssn_last4,
            patient_facts=_shared_facts,  # Phase 1: shared authoritative facts
        )

        generation_time = time.time() - start_time

        return FinalNoteResponse(
            final_note=complete_note,
            preliminary_note=preliminary_note,
            calculator_results=[],
            rag_sources=rag_sources,
            metadata={
                'generation_time_seconds': round(generation_time, 2),
                'calculators_executed': 0,
                'rag_enabled': effective_use_rag,
                'rag_sources_count': len(rag_sources),
                'gu_notes_found': len(gu_notes),
                'workflow': 'express',
                'stage1_provider': stage1_config.provider,
                'stage1_model': stage1_config.model,
                'stage2_provider': stage2_config.provider,
                'stage2_model': stage2_config.model,
            },
        )

    except Exception as e:
        from app.services.note_processing.llm_helper import LLMProviderError
        logger.error(f"Express note generation failed: {e}", exc_info=True)
        if isinstance(e, LLMProviderError):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Express note generation failed: {str(e)}",
        )
    finally:
        end_patient_session()
        logger.info("Express session ended and data purged")
        try:
            temp_manager = TempFileManager()
            session_id = f"user_{current_user.id}"
            deleted_count = temp_manager.cleanup_session(session_id)
            if deleted_count > 0:
                logger.info(
                    f"Cleaned up {deleted_count} temp files for session {session_id}"
                )
        except Exception as cleanup_error:
            logger.warning(f"Express temp file cleanup failed: {cleanup_error}")


@router.post("/generate-express-stream")
async def generate_express_note_stream(
    request: InitialNoteRequest,
    http_request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    EXPRESS (streaming): same end-state as /generate-express, but streams
    Server-Sent Events so the frontend can show progress while the
    multi-minute LLM workflow runs.

    Event names emitted (each `data:` line is a JSON object):
      stage1_start          {"message": "..."}
      stage1_complete       {"length": <int>}
      rag_start             {"queries": [...]}
      rag_skipped           {"reason": "..."}
      rag_complete          {"sources_count": <int>}
      stage2_start          {"message": "..."}
      stage2_complete       {"length": <int>}
      complete              {"final_note": "...", "preliminary_note": "...",
                             "metadata": {...}}
      error                 {"detail": "..."}
    """
    from app.services.note_processing.note_builder import build_urology_note
    from app.services.note_processing.note_identifier import identify_notes
    from app.services.note_processing.stage2_builder import build_stage2_note
    from app.services.note_processing.session_manager import (
        start_patient_session,
        end_patient_session,
    )
    import json as _json
    import time as _time

    user_id = current_user.id
    user_uuid = current_user.user_id
    note_type = request.note_type
    patient_name_v = request.patient_name
    ssn_last4_v = request.ssn_last4
    visit_date_v = request.visit_date
    use_rag_req = request.use_rag
    clinical_input = request.clinical_input

    async def event_stream():
        def _sse(event: str, payload: dict) -> bytes:
            return f"event: {event}\ndata: {_json.dumps(payload)}\n\n".encode("utf-8")

        session_started = False
        try:
            session = start_patient_session(patient_identifier=f"user_{user_id}")
            session_started = True
            logger.info(
                f"Started patient session {session.session_id} for Express(stream) generation"
            )

            # Per-task LLM configs
            llm_config_manager = LLMConfigManager(user_id=user_uuid)
            await llm_config_manager.load_from_database(db)
            stage1_config = llm_config_manager.get_config(LLMTaskType.STAGE1)
            stage2_config = llm_config_manager.get_config(LLMTaskType.STAGE2)

            yield _sse("stage1_start", {
                "message": "Building Stage 1 preliminary note...",
                "model": stage1_config.model,
                "provider": stage1_config.provider,
            })
            t0 = _time.time()

            clinical_input_with_date = clinical_input
            if visit_date_v:
                clinical_input_with_date = (
                    f"VISIT DATE: {visit_date_v}\n\n{clinical_input}"
                )

            _src_fmt = await _get_user_source_format(current_user.user_id, db)
            # Authoritative PatientStatusFacts computed ONCE (multi-cancer ground
            # truth + optional L1), shared by Stage 1 and Stage 2 below.
            from app.services.note_processing.note_builder import (
                build_authoritative_patient_facts,
            )
            _shared_facts = await asyncio.to_thread(
                build_authoritative_patient_facts, clinical_input_with_date, _src_fmt,
            )
            preliminary_note = await asyncio.to_thread(
                build_urology_note,
                clinical_text=clinical_input_with_date,
                task_config=stage1_config,
                source_format=_src_fmt,
                patient_facts=_shared_facts,
            )
            t_stage1 = _time.time() - t0

            yield _sse("stage1_complete", {
                "length": len(preliminary_note),
                "elapsed_seconds": round(t_stage1, 2),
            })

            # Identify notes for Stage 2
            notes_dict = identify_notes(clinical_input)
            gu_notes = notes_dict.get("gu_notes", [])
            non_gu_notes = notes_dict.get("non_gu_notes", [])

            # RAG (mirror of generate-express logic + low-complexity skip)
            rag_sources = []
            rag_content = ""
            effective_use_rag = stage2_config.use_rag and use_rag_req
            effective_use_graphrag = stage2_config.use_graphrag
            effective_rag_top_k = stage2_config.rag_top_k

            input_token_estimate = len(clinical_input) // 4
            routine_cc_patterns = (
                "follow-up", "follow up", "followup", "f/u",
                "post-op", "post op", "postop",
                "routine", "well visit", "annual",
                "med refill", "medication refill", "rx refill",
            )
            cc_lower = (preliminary_note[:1500] if preliminary_note else "").lower()
            is_routine_cc = any(p in cc_lower for p in routine_cc_patterns)
            if effective_use_rag and input_token_estimate < 4000 and is_routine_cc:
                yield _sse("rag_skipped", {
                    "reason": "low-complexity routine note",
                    "input_token_estimate": input_token_estimate,
                })
                effective_use_rag = False

            if effective_use_rag:
                try:
                    rag_pipeline = getattr(
                        http_request.app.state, 'rag_pipeline', None
                    )
                    if rag_pipeline is not None:
                        from app.services.note_processing.rag_query_builder import (
                            build_targeted_rag_queries,
                        )
                        targeted_queries = build_targeted_rag_queries(
                            preliminary_note=preliminary_note,
                            clinical_input=clinical_input,
                            max_queries=1,
                        )
                        yield _sse("rag_start", {"queries": targeted_queries})

                        search_strategy = (
                            "graphrag" if effective_use_graphrag else "vector"
                        )
                        all_sources = []
                        all_contexts = []
                        for q in targeted_queries:
                            try:
                                rag_result = await rag_pipeline.retrieve_and_augment(
                                    query=q,
                                    k=effective_rag_top_k,
                                    search_strategy=search_strategy,
                                    category=None,
                                )
                                if rag_result.context:
                                    all_contexts.append(f"[{q}]\n{rag_result.context}")
                                all_sources.extend(rag_result.sources)
                            except Exception as q_err:
                                logger.warning(
                                    f"Express(stream) RAG query '{q}' failed: {q_err}"
                                )

                        rag_content = "\n\n".join(all_contexts)
                        seen = set()
                        for src in all_sources:
                            key = str(src) if isinstance(src, dict) else src
                            if key not in seen:
                                seen.add(key)
                                rag_sources.append(src)
                        yield _sse("rag_complete", {
                            "sources_count": len(rag_sources),
                            "context_chars": len(rag_content),
                        })
                except Exception as e:
                    logger.warning(f"Express(stream) RAG failed: {e}")
                    yield _sse("rag_complete", {
                        "sources_count": 0,
                        "error": str(e),
                    })

            yield _sse("stage2_start", {
                "message": "Building Stage 2 final note...",
                "model": stage2_config.model,
                "provider": stage2_config.provider,
            })
            t1 = _time.time()
            complete_note = await asyncio.to_thread(
                build_stage2_note,
                stage1_note=preliminary_note,
                gu_notes=gu_notes,
                non_gu_notes=non_gu_notes,
                ambient_transcript=None,
                calculator_results={},
                rag_content=rag_content,
                task_config=stage2_config,
                note_type=note_type,
                patient_name=patient_name_v,
                ssn_last4=ssn_last4_v,
                patient_facts=_shared_facts,
            )
            t_stage2 = _time.time() - t1
            yield _sse("stage2_complete", {
                "length": len(complete_note),
                "elapsed_seconds": round(t_stage2, 2),
            })

            yield _sse("complete", {
                "final_note": complete_note,
                "preliminary_note": preliminary_note,
                "calculator_results": [],
                "rag_sources": rag_sources,
                "metadata": {
                    "generation_time_seconds": round(t_stage1 + t_stage2, 2),
                    "stage1_seconds": round(t_stage1, 2),
                    "stage2_seconds": round(t_stage2, 2),
                    "calculators_executed": 0,
                    "rag_enabled": effective_use_rag,
                    "rag_sources_count": len(rag_sources),
                    "gu_notes_found": len(gu_notes),
                    "workflow": "express_stream",
                    "stage1_provider": stage1_config.provider,
                    "stage1_model": stage1_config.model,
                    "stage2_provider": stage2_config.provider,
                    "stage2_model": stage2_config.model,
                },
            })
        except Exception as e:
            from app.services.note_processing.llm_helper import LLMProviderError
            logger.error(f"Express(stream) failed: {e}", exc_info=True)
            detail = str(e) if isinstance(e, LLMProviderError) else f"Express failed: {e}"
            yield _sse("error", {"detail": detail})
        finally:
            if session_started:
                try:
                    end_patient_session()
                except Exception as ee:
                    logger.warning(f"Express(stream) session cleanup failed: {ee}")
            try:
                temp_manager = TempFileManager()
                session_id_ = f"user_{user_id}"
                temp_manager.cleanup_session(session_id_)
            except Exception:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate-two-stage", response_model=NoteResponse)
async def generate_note_two_stage(
    request: NoteGenerateRequest,
    current_user: User = Depends(get_current_active_user),
    note_generator: NoteGenerator = Depends(get_note_generator)
):
    """
    Generate clinical note using improved two-model workflow.

    **Stage 1 (Data Extraction):** model = STAGE1_LLM_MODEL (env / user setting)
    - Extracts and organizes clinical data
    - Lower temperature (0.1) for factual accuracy
    - Structured data output without interpretation

    **Stage 2 (Clinical Reasoning):** model = STAGE2_LLM_MODEL (env / user setting)
    - Generates final note with Assessment & Plan
    - Incorporates calculator results and evidence
    - Clinical reasoning and recommendations

    Both models are selected per task by LLMConfigManager based on the
    user's Settings page preferences and the .env defaults. The note
    response metadata records the actual model + provider used for
    each stage so the audit trail reflects what ran, not a documentation
    assumption.

    This approach:
    - Reduces hallucinations by separating extraction from reasoning
    - Uses specialized models for each task
    - Provides better accuracy and clinical quality

    **Note:** This is the recommended workflow for complex cases.
    """
    try:
        logger.info(
            f"User {current_user.id} requesting two-stage note generation "
            f"(type: {request.note_type})"
        )

        # Generate note using two-stage workflow
        result = await note_generator.generate_note_two_stage(
            clinical_input=request.input_text,
            note_type=request.note_type,
            calculator_ids=request.calculator_ids,
            use_rag=request.use_rag,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )

        logger.info(
            f"Two-stage note generated successfully for user {current_user.id} "
            f"(time: {result.metadata.get('generation_time_seconds', 0):.2f}s, "
            f"workflow: {result.metadata.get('workflow', 'unknown')})"
        )

        return NoteResponse(**result.dict())

    except Exception as e:
        logger.error(f"Two-stage note generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Two-stage note generation failed: {str(e)}"
        )


@router.post("/generate-stage2-agent", response_model=FinalNoteResponse)
async def generate_stage2_agent(
    request: FinalNoteRequest,
    http_request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    STAGE 2 (Agent-Based): Generate Assessment & Plan using specialized agents.

    This endpoint uses the new agent-based architecture for Stage 2:
    - assessment_agent: Synthesizes clinical assessment/impression
    - plan_agent: Synthesizes treatment plan

    Both agents leverage:
    1. Stage 1 preliminary note (historical data organized)
    2. Prior assessments/plans from GU notes
    3. Ambient listening transcript (if available)
    4. Calculator results (44 specialized calculators)
    5. RAG content (evidence-based guidelines from Neo4j)

    This approach provides superior integration of all data sources
    and generates clinically-accurate, context-aware Assessment & Plan sections.

    CRITICAL: Uses session isolation to prevent cross-patient contamination.
    """
    from app.schemas.notes import FinalNoteResponse, CalculatorResultSchema
    from app.services.note_processing.note_identifier import identify_notes
    from app.services.note_processing.stage2_builder import build_stage2_note
    from app.services.note_processing.session_manager import start_patient_session, end_patient_session
    from calculators.registry import CalculatorRegistry
    from app.services.entity_extractor import ClinicalEntityExtractor
    from sqlalchemy import select
    from app.database.sqlite_models import UserPreferences
    import time

    # CRITICAL: Start isolated patient session to prevent cross-contamination
    session = start_patient_session(patient_identifier=f"user_{current_user.id}")
    logger.info(f"Started patient session {session.session_id} for Stage 2 agent generation")

    try:
        start_time = time.time()

        logger.info(
            f"User {current_user.id} requesting Stage 2 agent-based note generation "
            f"with {len(request.selected_calculators)} calculators"
        )

        # Step 0: Load task-specific LLM config for Stage 2 from user settings
        llm_config_manager = LLMConfigManager(user_id=current_user.user_id)
        await llm_config_manager.load_from_database(db)
        stage2_config = llm_config_manager.get_config(LLMTaskType.STAGE2)

        logger.info(
            f"Using Stage 2 LLM config: provider={stage2_config.provider}, "
            f"model={stage2_config.model}, use_rag={stage2_config.use_rag}, "
            f"use_graphrag={stage2_config.use_graphrag}, rag_top_k={stage2_config.rag_top_k}"
        )

        # Step 1: Identify notes from clinical input (to get GU and non-GU notes)
        logger.info("Step 1: Identifying historical notes...")
        notes_dict = identify_notes(request.clinical_input)
        gu_notes = notes_dict.get("gu_notes", [])
        non_gu_notes = notes_dict.get("non_gu_notes", [])
        logger.info(f"Found {len(gu_notes)} GU notes and {len(non_gu_notes)} non-GU notes for cross-specialty analysis")

        # Step 2: Extract entities for calculator execution from Stage 1 preliminary note
        logger.info("Step 2: Extracting clinical entities...")
        extractor = ClinicalEntityExtractor()
        # CRITICAL: Extract from preliminary_note, NOT clinical_input (raw data)
        entities = await extractor.extract_entities(request.preliminary_note)
        entity_dict = {e['field']: e['value'] for e in entities}

        logger.info(f"Extracted {len(entities)} entities from Stage 1 preliminary note")
        logger.info(f"Entity extraction details:")
        for entity in entities:
            logger.info(f"  - {entity['field']}: {entity['value']} (confidence: {entity['confidence']}, method: {entity['extraction_method']})")
        logger.info(f"Entity dictionary: {entity_dict}")

        # Merge with user-provided additional inputs
        entity_dict.update(request.additional_inputs)
        logger.info(f"Merged with {len(request.additional_inputs)} user-provided inputs")

        # Step 3: Execute selected calculators
        logger.info("Step 3: Executing calculators...")
        registry = CalculatorRegistry()
        calculator_results = []
        calculator_results_dict = {}

        for calc_id in request.selected_calculators:
            try:
                calculator = registry.get(calc_id)
                if calculator is None:
                    logger.warning(f"Calculator not found: {calc_id}")
                    continue

                # Extract required inputs for this calculator
                required_inputs = calculator.required_inputs
                calc_inputs = {k: entity_dict.get(k) for k in required_inputs if k in entity_dict}

                # Run calculator
                result = calculator.calculate(calc_inputs)

                # Format inputs for display
                inputs_display = ", ".join([f"{k}={v}" for k, v in calc_inputs.items()])

                calc_result = {
                    'calculator_id': calc_id,
                    'calculator_name': calculator.name,
                    'result': result.result,
                    'interpretation': result.interpretation,
                    'recommendations': result.recommendations if hasattr(result, 'recommendations') else [],
                    'inputs': calc_inputs,
                    'formatted_output': f"{calculator.name}\nInputs: {inputs_display}\nResult: {result.interpretation}"
                }

                calculator_results.append(calc_result)
                calculator_results_dict[calc_id] = calc_result

                logger.info(f"Calculator {calc_id} executed successfully")

            except Exception as e:
                logger.error(f"Calculator {calc_id} failed: {e}")
                continue

        # Step 4: Retrieve evidence via RAG (if enabled based on stage2_config settings)
        # ROOT CAUSE #1 FIX: Use TARGETED queries based on Chief Complaint, not entire document
        logger.info("Step 4: Retrieving RAG content with targeted queries...")
        rag_sources = []
        rag_content = ""

        # Use RAG settings from stage2_config (user's Settings page preferences)
        effective_use_rag = stage2_config.use_rag
        effective_use_graphrag = stage2_config.use_graphrag
        effective_rag_top_k = stage2_config.rag_top_k

        if effective_use_rag:
            try:
                # Use RAG pipeline from app.state (initialized at startup)
                rag_pipeline = getattr(http_request.app.state, 'rag_pipeline', None)
                if rag_pipeline is not None:
                    # ARCHITECTURAL FIX: Build targeted queries from Chief Complaint
                    # instead of passing entire clinical document
                    from app.services.note_processing.rag_query_builder import build_targeted_rag_queries

                    targeted_queries = build_targeted_rag_queries(
                        preliminary_note=request.preliminary_note,
                        clinical_input=request.clinical_input,
                        max_queries=1
                    )

                    all_sources = []
                    all_contexts = []

                    # Determine search strategy based on user settings
                    search_strategy = "graphrag" if effective_use_graphrag else "vector"
                    logger.info(f"Using search strategy: {search_strategy}, top_k: {effective_rag_top_k}")

                    for query in targeted_queries:
                        logger.info(f"RAG query ({search_strategy}): {query}")
                        try:
                            # Use configured search strategy and top_k from user settings
                            rag_result = await rag_pipeline.retrieve_and_augment(
                                query=query,
                                k=effective_rag_top_k,
                                search_strategy=search_strategy,
                                category=None
                            )

                            if rag_result.context:
                                all_contexts.append(f"[{query}]\n{rag_result.context}")
                            all_sources.extend(rag_result.sources)
                        except Exception as query_error:
                            logger.warning(f"RAG query '{query}' failed: {query_error}")

                    # Combine results
                    rag_content = "\n\n".join(all_contexts)
                    # Deduplicate sources
                    seen_sources = set()
                    for src in all_sources:
                        src_key = str(src) if isinstance(src, dict) else src
                        if src_key not in seen_sources:
                            seen_sources.add(src_key)
                            rag_sources.append(src)

                    logger.info(
                        f"Retrieved {len(rag_sources)} RAG sources from {len(targeted_queries)} targeted queries "
                        f"({len(rag_content)} chars context)"
                    )
                else:
                    logger.warning("RAG pipeline not available in app.state")
            except Exception as e:
                logger.warning(f"RAG retrieval failed: {e}")

        # Step 5: Generate Stage 2 note using agent-based architecture
        logger.info("Step 5: Generating Stage 2 Assessment & Plan using specialized agents...")

        # Ambient transcript placeholder for future ambient listening integration
        # When implemented, this will contain real-time provider-patient conversation
        ambient_transcript = None

        # Compute the authoritative PatientStatusFacts from the SAME raw clinical
        # input Stage 1 used (multi-cancer ground truth + optional L1), so the
        # Assessment/Plan ground on those facts instead of re-deriving a divergent
        # picture from the rendered Stage 1 note.
        from app.services.note_processing.note_builder import (
            build_authoritative_patient_facts,
        )
        _src_fmt = await _get_user_source_format(current_user.user_id, db)
        _final_input = request.clinical_input
        if request.visit_date:
            _final_input = f"VISIT DATE: {request.visit_date}\n\n{request.clinical_input}"
        _shared_facts = await asyncio.to_thread(
            build_authoritative_patient_facts, _final_input, _src_fmt,
        )

        # Build Stage 2 note with task-specific LLM config
        # Pass non_gu_notes for cross-specialty urologic content extraction
        complete_note = build_stage2_note(
            stage1_note=request.preliminary_note,
            gu_notes=gu_notes,
            non_gu_notes=non_gu_notes,
            ambient_transcript=ambient_transcript,
            calculator_results=calculator_results_dict,
            rag_content=rag_content,
            task_config=stage2_config,
            note_type=request.note_type,
            patient_name=request.patient_name,
            ssn_last4=request.ssn_last4,
            patient_facts=_shared_facts,
        )

        logger.info("Stage 2 agent-based note generation complete")

        # Format response
        generation_time = time.time() - start_time

        return FinalNoteResponse(
            final_note=complete_note,
            calculator_results=[CalculatorResultSchema(**r) for r in calculator_results],
            rag_sources=rag_sources,
            metadata={
                'generation_time_seconds': round(generation_time, 2),
                'calculators_executed': len(calculator_results),
                'rag_enabled': effective_use_rag,
                'rag_sources_count': len(rag_sources),
                'gu_notes_found': len(gu_notes),
                'workflow': 'stage2_agent_based',
                'llm_provider': stage2_config.provider,
                'llm_model': stage2_config.model
            }
        )

    except Exception as e:
        from app.services.note_processing.llm_helper import LLMProviderError
        logger.error(f"Stage 2 agent-based note generation failed: {e}", exc_info=True)
        if isinstance(e, LLMProviderError):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stage 2 agent-based note generation failed: {str(e)}"
        )
    finally:
        # CRITICAL: Always purge patient data when session ends
        end_patient_session()
        logger.info("Patient session ended and data purged")


# ============================================================================
# STAGE 3: AMBIENT-AUGMENTED NOTE (Final with Discussion Integration)
# ============================================================================

@router.post("/ambient-augment", response_model=FinalNoteResponse)
async def generate_ambient_augmented_note(
    request: dict,
    current_user: User = Depends(get_current_active_user)
):
    """
    STAGE 3: Generate ambient-augmented final note.

    Takes a Stage 2 note and ambient transcription, performs intelligent
    section-aware merging to update the note with discussion details.

    **Workflow:**
    1. Parse transcription into section-specific segments
    2. Intelligently merge each segment into appropriate section
    3. Use LLM to polish and integrate updates naturally
    4. Return updated final note

    **Request Body:**
    ```json
    {
        "stage2_note": "Complete Stage 2 note text",
        "transcription": "Ambient listening transcription",
        "speaker_map": {"speaker_0": "Clinician", "speaker_1": "Patient"}
    }
    ```
    """
    from app.schemas.notes import FinalNoteResponse
    from app.services.ambient_merge_service import IntelligentNoteMerger

    try:
        logger.info(f"User {current_user.id if current_user else 'anonymous'} requesting Stage 3 ambient-augmented note")

        stage2_note = request.get('stage2_note', '')
        transcription = request.get('transcription', '')
        speaker_map = request.get('speaker_map', {})

        if not stage2_note:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="stage2_note is required"
            )

        if not transcription:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="transcription is required"
            )

        # Step 1: Perform intelligent merge
        merger = IntelligentNoteMerger()
        merged_note = merger.merge(
            existing_note=stage2_note,
            transcription=transcription,
            speaker_map=speaker_map
        )

        logger.info(f"Stage 3 ambient-augmented note generated: {len(merged_note)} chars")

        return FinalNoteResponse(
            final_note=merged_note,
            calculator_results=[],  # Calculators already in Stage 2
            rag_sources=[],  # RAG already in Stage 2
            metadata={
                'workflow': 'stage3_ambient_augmented',
                'transcription_length': len(transcription),
                'segments_merged': 'see logs'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stage 3 ambient-augmented note generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stage 3 ambient-augmented note generation failed: {str(e)}"
        )


# ============================================================================
# SSE HELPER
# ============================================================================

def _sse_event(event_type: str, data: dict) -> str:
    """Format an SSE event with newline-safe JSON.

    SSE uses \\n\\n as event terminator. json.dumps escapes newlines
    inside string values as the two-character sequence \\n in the JSON
    output. The .replace() is a belt-and-suspenders defense to catch any
    literal newline bytes that could break SSE framing.
    """
    import json as _json
    json_str = _json.dumps(data, ensure_ascii=False)
    json_str = json_str.replace('\n', '\\n').replace('\r', '\\r')
    return f"event: {event_type}\ndata: {json_str}\n\n"


# ============================================================================
# BATCH PROCESSING ENDPOINT
# ============================================================================

@router.post("/batch-upload-process")
async def batch_upload_and_process(
    files: list[UploadFile] = File(..., description="Clinical .txt files to batch process"),
    visit_date: Optional[str] = Form(None, description="Visit date (YYYY-MM-DD) for IPSS and age calculation"),
    http_request: Request = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload and batch process clinical .txt files with SSE streaming.

    Streams each completed note back immediately via Server-Sent Events,
    so the frontend can save files as they finish — no waiting for the
    entire batch, no timeout risk.

    SSE event types:
    - file_complete: Completed note (includes note_content for immediate download)
    - file_failed: Failed file (after all retries)
    - file_start: File processing started
    - total: The total.vaucda concatenation content
    - complete: Final summary with counts and timing
    - error: Fatal error
    """
    from app.services.batch_processor import detect_note_type, process_single_file
    from app.services.note_processing.note_builder import build_urology_note
    from app.services.note_processing.note_identifier import identify_notes
    from app.services.note_processing.stage2_builder import build_stage2_note
    from app.services.note_processing.session_manager import (
        start_patient_session, end_patient_session, purge_all_patient_data
    )
    from app.services.entity_extractor import ClinicalEntityExtractor
    from app.services.note_processing.rag_query_builder import build_targeted_rag_queries
    import tempfile
    import json
    import gc

    # Validate uploads synchronously before streaming
    def _sse_err(detail: str) -> str:
        return _sse_event('error', {'detail': detail})

    if not files:
        async def err():
            yield _sse_err('No files uploaded')
        return StreamingResponse(err(), media_type="text/event-stream")

    txt_files = [f for f in files if f.filename and f.filename.lower().endswith('.txt')]
    if not txt_files:
        async def err():
            yield _sse_err('No .txt files found in upload')
        return StreamingResponse(err(), media_type="text/event-stream")

    max_files = settings.BATCH_MAX_FILES
    if len(txt_files) > max_files:
        async def err():
            yield _sse_err(f'Too many files ({len(txt_files)}). Max is {max_files}.')
        return StreamingResponse(err(), media_type="text/event-stream")

    # Save uploads to temp dir
    batch_temp_dir = tempfile.mkdtemp(prefix="vaucda_batch_")
    saved_files = []
    for upload_file in txt_files:
        base_name = os.path.basename(upload_file.filename)
        file_path = os.path.join(batch_temp_dir, base_name)
        content = await upload_file.read()
        with open(file_path, 'wb') as f:
            f.write(content)
        saved_files.append(base_name)

    # Sort files numerically then alphabetically
    import re as _re
    def _sort_key(name):
        m = _re.match(r'^(\d+)', name)
        return (0, int(m.group(1)), name) if m else (1, 0, name)
    saved_files.sort(key=_sort_key)

    # Load LLM configs before streaming starts
    llm_config_manager = LLMConfigManager(user_id=current_user.user_id)
    await llm_config_manager.load_from_database(db)
    stage1_config = llm_config_manager.get_config(LLMTaskType.STAGE1)
    stage2_config = llm_config_manager.get_config(LLMTaskType.STAGE2)

    logger.info(f"Batch SSE upload: {len(saved_files)} files, temp: {batch_temp_dir}, visit_date: {visit_date}")

    async def event_generator():
        import time
        from pathlib import Path

        max_retries = settings.BATCH_MAX_RETRIES
        file_timeout = settings.BATCH_FILE_TIMEOUT
        separator = settings.BATCH_FILE_SEPARATOR
        start_time = time.time()
        completed_notes = []  # (filename, content) for total.vaucda
        results = []
        _src_fmt = await _get_user_source_format(current_user.user_id, db)

        async def stage1_func(clinical_input, note_type):
            return await asyncio.to_thread(
                build_urology_note,
                clinical_text=clinical_input,
                task_config=stage1_config,
                source_format=_src_fmt,
            )

        async def stage2_func(preliminary_note, clinical_input, note_type):
            session = start_patient_session(patient_identifier=f"batch_{current_user.user_id}")
            try:
                notes_dict = identify_notes(clinical_input)
                gu_notes = notes_dict.get("gu_notes", [])
                non_gu_notes = notes_dict.get("non_gu_notes", [])
                extractor = ClinicalEntityExtractor(
                    provider=stage1_config.provider,
                    model=stage1_config.model,
                )
                entities = await extractor.extract_entities(preliminary_note)
                entity_dict = {e['field']: e['value'] for e in entities}

                calculator_results_dict = {}
                try:
                    from app.services.calculator_suggester import get_calculator_suggester
                    from calculators.registry import CalculatorRegistry
                    suggester = get_calculator_suggester()
                    suggestions = suggester.suggest_calculators(entities)
                    auto_calcs = [s['calculator_id'] for s in suggestions if s.get('auto_selected')]
                    registry = CalculatorRegistry()
                    for calc_id in auto_calcs:
                        try:
                            calculator = registry.get(calc_id)
                            if not calculator:
                                continue
                            req = calculator.required_inputs
                            ci = {k: entity_dict.get(k) for k in req if k in entity_dict}
                            r = calculator.calculate(ci)
                            disp = ", ".join([f"{k}={v}" for k, v in ci.items()])
                            calculator_results_dict[calc_id] = {
                                'calculator_id': calc_id, 'calculator_name': calculator.name,
                                'result': r.result, 'interpretation': r.interpretation,
                                'recommendations': r.recommendations if hasattr(r, 'recommendations') else [],
                                'inputs': ci,
                                'formatted_output': f"{calculator.name}\nInputs: {disp}\nResult: {r.interpretation}",
                            }
                        except Exception:
                            pass
                except Exception:
                    pass

                rag_content = ""
                if stage2_config.use_rag:
                    try:
                        rag_pipeline = getattr(http_request.app.state, 'rag_pipeline', None)
                        if rag_pipeline:
                            tq = build_targeted_rag_queries(preliminary_note=preliminary_note, clinical_input=clinical_input, max_queries=1)
                            ctxs = []
                            strat = "graphrag" if stage2_config.use_graphrag else "vector"
                            for q in tq:
                                try:
                                    rr = await rag_pipeline.retrieve_and_augment(query=q, k=stage2_config.rag_top_k, search_strategy=strat, category=None)
                                    if rr.context:
                                        ctxs.append(f"[{q}]\n{rr.context}")
                                except Exception:
                                    pass
                            rag_content = "\n\n".join(ctxs)
                    except Exception:
                        pass

                return await asyncio.to_thread(
                    build_stage2_note,
                    stage1_note=preliminary_note, gu_notes=gu_notes, non_gu_notes=non_gu_notes,
                    ambient_transcript=None, calculator_results=calculator_results_dict,
                    rag_content=rag_content, task_config=stage2_config,
                    note_type=note_type, patient_name=None, ssn_last4=None,
                )
            finally:
                end_patient_session()

        try:
            for idx, filename in enumerate(saved_files):
                note_type = detect_note_type(filename)
                output_name = Path(filename).stem + ".vaucda"
                file_path = Path(batch_temp_dir) / filename

                # Notify: starting
                yield _sse_event('file_start', {'filename': filename, 'output_filename': output_name, 'note_type': note_type, 'current_index': idx + 1, 'total_files': len(saved_files)})

                success = False
                error_msg = None
                gen_time = None

                for attempt in range(1, max_retries + 1):
                    purge_all_patient_data()
                    gc.collect()

                    try:
                        file_start = time.time()
                        final_note = await asyncio.wait_for(
                            process_single_file(file_path, note_type, stage1_func, stage2_func, visit_date=visit_date),
                            timeout=file_timeout,
                        )
                        gen_time = round(time.time() - file_start, 2)
                        success = True

                        # Stream the completed note immediately
                        completed_notes.append((output_name, final_note))
                        yield _sse_event('file_complete', {'filename': filename, 'output_filename': output_name, 'note_type': note_type, 'current_index': idx + 1, 'total_files': len(saved_files), 'attempts': attempt, 'generation_time_seconds': gen_time, 'note_content': final_note})
                        break

                    except asyncio.TimeoutError:
                        error_msg = f"Timed out after {file_timeout}s"
                        purge_all_patient_data()
                    except Exception as e:
                        error_msg = f"Processing error: {type(e).__name__}"
                        purge_all_patient_data()

                    if attempt < max_retries:
                        await asyncio.sleep(1)

                if not success:
                    results.append({'filename': filename, 'output_filename': output_name, 'note_type': note_type, 'status': 'failed', 'attempts': max_retries, 'error_message': error_msg})
                    yield _sse_event('file_failed', {'filename': filename, 'output_filename': output_name, 'note_type': note_type, 'current_index': idx + 1, 'total_files': len(saved_files), 'attempts': max_retries, 'error_message': error_msg})
                else:
                    results.append({'filename': filename, 'output_filename': output_name, 'note_type': note_type, 'status': 'completed', 'attempts': attempt, 'generation_time_seconds': gen_time})

                purge_all_patient_data()
                gc.collect()

            # Build and stream total.vaucda
            if completed_notes:
                total_content = f"\n{separator}\n".join(content for _, content in completed_notes)
                yield _sse_event('total', {'filename': 'total.vaucda', 'note_content': total_content})

            # Final summary
            total_time = round(time.time() - start_time, 2)
            processed = sum(1 for r in results if r.get('status') == 'completed')
            failed = sum(1 for r in results if r.get('status') == 'failed')
            yield _sse_event('complete', {'total_files': len(saved_files), 'processed': processed, 'failed': failed, 'total_time_seconds': total_time, 'results': results})

        except Exception as e:
            logger.error(f"Batch SSE processing failed: {e}", exc_info=True)
            yield _sse_event('error', {'detail': 'Batch processing failed due to an internal error'})
        finally:
            try:
                purge_all_patient_data()
            except Exception as purge_err:
                logger.critical(f"Final HIPAA purge failed: {purge_err}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/batch-download/{filename}")
async def download_batch_result(
    filename: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    Download a .vaucda result file from batch processing.
    Only allows downloading .vaucda files from temp batch directories.
    """
    import glob
    from fastapi.responses import FileResponse

    if not filename.endswith('.vaucda'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .vaucda files can be downloaded"
        )

    # Search for the file in temp batch directories
    temp_dir = settings.TEMP_FILE_DIR if hasattr(settings, 'TEMP_FILE_DIR') else '/tmp'
    pattern = os.path.join(temp_dir, 'vaucda_batch_*', filename)
    matches = glob.glob(pattern)

    # Also check system temp
    import tempfile
    sys_temp = tempfile.gettempdir()
    pattern2 = os.path.join(sys_temp, 'vaucda_batch_*', filename)
    matches.extend(glob.glob(pattern2))

    if not matches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found. Batch results may have been cleaned up."
        )

    file_path = matches[0]
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='text/plain',
    )


@router.post("/batch-process", response_model=BatchProcessingResponse)
async def batch_process_folder(
    request: BatchProcessingRequest,
    http_request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Batch process a folder of clinical documents through Stage 1 → Stage 2.

    - Files with "CON" as a standalone word in the name are processed as urology consults
    - All other files are processed as urology clinic notes
    - Each file outputs a .vaucda file with the same stem name
    - Complete session purge between each patient (HIPAA compliance)
    - Retries up to BATCH_MAX_RETRIES times per file on error
    - Creates total.vaucda concatenation of all outputs at the end
    - Only .txt files are supported (PDFs require individual upload with OCR)
    """
    from app.services.batch_processor import (
        run_batch_processing, validate_folder_path
    )
    from app.services.note_processing.note_builder import build_urology_note
    from app.services.note_processing.note_identifier import identify_notes
    from app.services.note_processing.stage2_builder import build_stage2_note
    from app.services.note_processing.session_manager import (
        start_patient_session, end_patient_session, purge_all_patient_data
    )
    from app.services.entity_extractor import ClinicalEntityExtractor
    from app.services.note_processing.rag_query_builder import build_targeted_rag_queries

    # Validate folder path (security: path traversal protection)
    try:
        validated_path = validate_folder_path(request.folder_path)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    folder_path = str(validated_path)

    try:
        # Load LLM configs for Stage 1 and Stage 2
        llm_config_manager = LLMConfigManager(user_id=current_user.user_id)
        await llm_config_manager.load_from_database(db)
        stage1_config = llm_config_manager.get_config(LLMTaskType.STAGE1)
        stage2_config = llm_config_manager.get_config(LLMTaskType.STAGE2)

        logger.info(
            f"Batch processing: Stage 1 config={stage1_config.provider}/{stage1_config.model}, "
            f"Stage 2 config={stage2_config.provider}/{stage2_config.model}"
        )

        # Define Stage 1 processing function
        _src_fmt = await _get_user_source_format(current_user.user_id, db)
        async def stage1_func(clinical_input: str, note_type: str) -> str:
            return await asyncio.to_thread(
                build_urology_note,
                clinical_text=clinical_input,
                task_config=stage1_config,
                source_format=_src_fmt,
            )

        # Define Stage 2 processing function
        async def stage2_func(
            preliminary_note: str,
            clinical_input: str,
            note_type: str,
        ) -> str:
            # Start isolated patient session
            session = start_patient_session(
                patient_identifier=f"batch_user_{current_user.user_id}"
            )

            try:
                # Identify historical notes
                notes_dict = identify_notes(clinical_input)
                gu_notes = notes_dict.get("gu_notes", [])
                non_gu_notes = notes_dict.get("non_gu_notes", [])

                # Extract entities from preliminary note
                extractor = ClinicalEntityExtractor(
                    provider=stage1_config.provider,
                    model=stage1_config.model,
                )
                entities = await extractor.extract_entities(preliminary_note)
                entity_dict = {e['field']: e['value'] for e in entities}

                # Execute auto-selected calculators
                calculator_results_dict = {}
                try:
                    from app.services.calculator_suggester import get_calculator_suggester
                    from calculators.registry import CalculatorRegistry

                    suggester = get_calculator_suggester()
                    suggestions = suggester.suggest_calculators(entities)
                    auto_calcs = [s['calculator_id'] for s in suggestions if s.get('auto_selected')]

                    registry = CalculatorRegistry()
                    for calc_id in auto_calcs:
                        try:
                            calculator = registry.get(calc_id)
                            if calculator is None:
                                continue
                            required_inputs = calculator.required_inputs
                            calc_inputs = {
                                k: entity_dict.get(k)
                                for k in required_inputs if k in entity_dict
                            }
                            result = calculator.calculate(calc_inputs)
                            inputs_display = ", ".join(
                                [f"{k}={v}" for k, v in calc_inputs.items()]
                            )
                            calculator_results_dict[calc_id] = {
                                'calculator_id': calc_id,
                                'calculator_name': calculator.name,
                                'result': result.result,
                                'interpretation': result.interpretation,
                                'recommendations': (
                                    result.recommendations
                                    if hasattr(result, 'recommendations') else []
                                ),
                                'inputs': calc_inputs,
                                'formatted_output': (
                                    f"{calculator.name}\nInputs: {inputs_display}\n"
                                    f"Result: {result.interpretation}"
                                ),
                            }
                        except Exception as calc_err:
                            logger.warning(f"Batch calc {calc_id} failed: {calc_err}")
                except Exception as calc_setup_err:
                    logger.warning(f"Batch calculator setup failed: {calc_setup_err}")

                # RAG retrieval
                rag_content = ""
                if stage2_config.use_rag:
                    try:
                        rag_pipeline = getattr(
                            http_request.app.state, 'rag_pipeline', None
                        )
                        if rag_pipeline is not None:
                            targeted_queries = build_targeted_rag_queries(
                                preliminary_note=preliminary_note,
                                clinical_input=clinical_input,
                                max_queries=1,
                            )
                            all_contexts = []
                            search_strategy = (
                                "graphrag" if stage2_config.use_graphrag else "vector"
                            )
                            for query in targeted_queries:
                                try:
                                    rag_result = await rag_pipeline.retrieve_and_augment(
                                        query=query,
                                        k=stage2_config.rag_top_k,
                                        search_strategy=search_strategy,
                                        category=None,
                                    )
                                    if rag_result.context:
                                        all_contexts.append(
                                            f"[{query}]\n{rag_result.context}"
                                        )
                                except Exception as query_err:
                                    logger.warning(f"Batch RAG query failed: {query_err}")
                            rag_content = "\n\n".join(all_contexts)
                    except Exception as rag_err:
                        logger.warning(f"Batch RAG failed: {rag_err}")

                # Build Stage 2 note (wrapped in thread to avoid blocking event loop)
                complete_note = await asyncio.to_thread(
                    build_stage2_note,
                    stage1_note=preliminary_note,
                    gu_notes=gu_notes,
                    non_gu_notes=non_gu_notes,
                    ambient_transcript=None,
                    calculator_results=calculator_results_dict,
                    rag_content=rag_content,
                    task_config=stage2_config,
                    note_type=note_type,
                    patient_name=None,
                    ssn_last4=None,
                )

                return complete_note

            finally:
                # CRITICAL: Always purge patient data
                end_patient_session()

        # Define purge function
        def purge_func():
            purge_all_patient_data()

        # Run batch processing. active_model lets the pre-flight Ollama
        # health check use the workload-aware variant — when the user's
        # Stage 2 model is cloud-proxied (``*-cloud``), a separate
        # process's local-model wedge is tolerated as long as the cloud
        # route is verified responsive.
        results, total_path, total_time = await run_batch_processing(
            folder_path=folder_path,
            stage1_func=stage1_func,
            stage2_func=stage2_func,
            purge_func=purge_func,
            visit_date=request.visit_date,
            active_model=stage2_config.model,
        )

        processed = sum(
            1 for r in results if r.status == BatchFileStatus.COMPLETED
        )
        failed = sum(
            1 for r in results if r.status == BatchFileStatus.FAILED
        )

        return BatchProcessingResponse(
            total_files=len(results),
            processed=processed,
            failed=failed,
            results=results,
            total_file=total_path,
            total_time_seconds=total_time,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Batch processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Batch processing failed due to an internal error"
        )
    finally:
        # Final purge after entire batch
        try:
            from app.services.note_processing.session_manager import purge_all_patient_data
            purge_all_patient_data()
        except Exception as purge_err:
            logger.critical(f"Final HIPAA purge failed: {purge_err}")


@router.post("/batch-process-stream")
async def batch_process_folder_stream(
    request: BatchProcessingRequest,
    http_request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Batch process with Server-Sent Events (SSE) for real-time progress.

    Streams progress events as each file starts/completes/fails.
    Final event contains the complete BatchProcessingResponse.

    Event types:
    - progress: Per-file status update
    - complete: Final results with summary
    - error: Fatal error that stops the batch
    """
    from app.services.batch_processor import (
        run_batch_processing, validate_folder_path
    )
    from app.services.note_processing.note_builder import build_urology_note
    from app.services.note_processing.note_identifier import identify_notes
    from app.services.note_processing.stage2_builder import build_stage2_note
    from app.services.note_processing.session_manager import (
        start_patient_session, end_patient_session, purge_all_patient_data
    )
    from app.services.entity_extractor import ClinicalEntityExtractor
    from app.services.note_processing.rag_query_builder import build_targeted_rag_queries
    import json

    # Validate folder path
    try:
        validated_path = validate_folder_path(request.folder_path)
    except ValueError as e:
        async def error_stream():
            yield _sse_event('error', {'detail': str(e)})
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    folder_path = str(validated_path)

    # Load LLM configs
    llm_config_manager = LLMConfigManager(user_id=current_user.user_id)
    await llm_config_manager.load_from_database(db)
    stage1_config = llm_config_manager.get_config(LLMTaskType.STAGE1)
    stage2_config = llm_config_manager.get_config(LLMTaskType.STAGE2)

    # Queue for SSE events from the batch processor
    progress_queue: asyncio.Queue = asyncio.Queue()
    _src_fmt = await _get_user_source_format(current_user.user_id, db)

    async def stage1_func(clinical_input: str, note_type: str) -> str:
        return await asyncio.to_thread(
            build_urology_note,
            clinical_text=clinical_input,
            task_config=stage1_config,
            source_format=_src_fmt,
        )

    async def stage2_func(
        preliminary_note: str,
        clinical_input: str,
        note_type: str,
    ) -> str:
        session = start_patient_session(
            patient_identifier=f"batch_user_{current_user.user_id}"
        )
        try:
            notes_dict = identify_notes(clinical_input)
            gu_notes = notes_dict.get("gu_notes", [])
            non_gu_notes = notes_dict.get("non_gu_notes", [])

            extractor = ClinicalEntityExtractor()
            entities = await extractor.extract_entities(preliminary_note)
            entity_dict = {e['field']: e['value'] for e in entities}

            calculator_results_dict = {}
            try:
                from app.services.calculator_suggester import get_calculator_suggester
                from calculators.registry import CalculatorRegistry
                suggester = get_calculator_suggester()
                suggestions = suggester.suggest_calculators(entities)
                auto_calcs = [s['calculator_id'] for s in suggestions if s.get('auto_selected')]
                registry = CalculatorRegistry()
                for calc_id in auto_calcs:
                    try:
                        calculator = registry.get(calc_id)
                        if calculator is None:
                            continue
                        required_inputs = calculator.required_inputs
                        calc_inputs = {k: entity_dict.get(k) for k in required_inputs if k in entity_dict}
                        result = calculator.calculate(calc_inputs)
                        inputs_display = ", ".join([f"{k}={v}" for k, v in calc_inputs.items()])
                        calculator_results_dict[calc_id] = {
                            'calculator_id': calc_id,
                            'calculator_name': calculator.name,
                            'result': result.result,
                            'interpretation': result.interpretation,
                            'recommendations': result.recommendations if hasattr(result, 'recommendations') else [],
                            'inputs': calc_inputs,
                            'formatted_output': f"{calculator.name}\nInputs: {inputs_display}\nResult: {result.interpretation}",
                        }
                    except Exception as calc_err:
                        logger.warning(f"Batch calc {calc_id} failed: {calc_err}")
            except Exception as calc_setup_err:
                logger.warning(f"Batch calculator setup failed: {calc_setup_err}")

            rag_content = ""
            if stage2_config.use_rag:
                try:
                    rag_pipeline = getattr(http_request.app.state, 'rag_pipeline', None)
                    if rag_pipeline is not None:
                        targeted_queries = build_targeted_rag_queries(
                            preliminary_note=preliminary_note,
                            clinical_input=clinical_input,
                            max_queries=1,
                        )
                        all_contexts = []
                        search_strategy = "graphrag" if stage2_config.use_graphrag else "vector"
                        for query in targeted_queries:
                            try:
                                rag_result = await rag_pipeline.retrieve_and_augment(
                                    query=query, k=stage2_config.rag_top_k,
                                    search_strategy=search_strategy, category=None,
                                )
                                if rag_result.context:
                                    all_contexts.append(f"[{query}]\n{rag_result.context}")
                            except Exception as query_err:
                                logger.warning(f"Batch RAG query failed: {query_err}")
                        rag_content = "\n\n".join(all_contexts)
                except Exception as rag_err:
                    logger.warning(f"Batch RAG failed: {rag_err}")

            complete_note = await asyncio.to_thread(
                build_stage2_note,
                stage1_note=preliminary_note, gu_notes=gu_notes, non_gu_notes=non_gu_notes,
                ambient_transcript=None, calculator_results=calculator_results_dict,
                rag_content=rag_content, task_config=stage2_config,
                note_type=note_type, patient_name=None, ssn_last4=None,
            )
            return complete_note
        finally:
            end_patient_session()

    def purge_func():
        purge_all_patient_data()

    async def event_generator():
        """Run batch processing and yield SSE events."""
        try:
            from app.services.batch_processor import get_processable_files, detect_note_type
            import time
            import gc

            files = get_processable_files(folder_path)
            if not files:
                yield _sse_event('error', {'detail': 'No processable .txt files found'})
                return

            max_files = settings.BATCH_MAX_FILES
            if len(files) > max_files:
                yield _sse_event('error', {'detail': f'Folder contains {len(files)} files, exceeding limit of {max_files}'})
                return

            max_retries = settings.BATCH_MAX_RETRIES
            file_timeout = settings.BATCH_FILE_TIMEOUT
            separator = settings.BATCH_FILE_SEPARATOR

            start_time = time.time()
            results = []
            output_folder = validated_path

            for idx, file_path in enumerate(files):
                note_type = detect_note_type(file_path.name)
                output_filename = file_path.stem + ".vaucda"

                # Send progress: starting file
                yield _sse_event('progress', {'current_file': file_path.name, 'current_index': idx + 1, 'total_files': len(files), 'status': 'starting', 'attempt': 1, 'note_type': note_type})

                result = {
                    'filename': file_path.name,
                    'output_filename': output_filename,
                    'note_type': note_type,
                    'status': 'processing',
                    'attempts': 0,
                    'error_message': None,
                    'generation_time_seconds': None,
                }

                success = False
                for attempt in range(1, max_retries + 1):
                    result['attempts'] = attempt

                    if attempt > 1:
                        yield _sse_event('progress', {'current_file': file_path.name, 'current_index': idx + 1, 'total_files': len(files), 'status': f'retrying (attempt {attempt}/{max_retries})', 'attempt': attempt, 'note_type': note_type})

                    try:
                        purge_func()
                        gc.collect()

                        file_start = time.time()

                        from app.services.batch_processor import process_single_file
                        final_note = await asyncio.wait_for(
                            process_single_file(
                                file_path=file_path, note_type=note_type,
                                stage1_func=stage1_func, stage2_func=stage2_func,
                            ),
                            timeout=file_timeout,
                        )

                        output_path = output_folder / output_filename
                        output_path.write_text(final_note, encoding='utf-8')

                        result['status'] = 'completed'
                        result['generation_time_seconds'] = round(time.time() - file_start, 2)
                        result['error_message'] = None
                        success = True
                        break

                    except asyncio.TimeoutError:
                        result['error_message'] = f"Timed out after {file_timeout}s"
                        purge_func()
                    except Exception as e:
                        result['error_message'] = f"Processing error: {type(e).__name__}"
                        purge_func()

                    if attempt < max_retries:
                        await asyncio.sleep(1)

                if not success:
                    result['status'] = 'failed'

                purge_func()
                gc.collect()
                results.append(result)

                # Send progress: file done
                yield _sse_event('progress', {'current_file': file_path.name, 'current_index': idx + 1, 'total_files': len(files), 'status': result['status'], 'attempt': result['attempts'], 'note_type': note_type, 'generation_time_seconds': result.get('generation_time_seconds'), 'error_message': result.get('error_message')})

            # Create total.vaucda
            from app.services.batch_processor import _create_total_file
            from pathlib import Path
            total_path = output_folder / "total.vaucda"
            # Build BatchFileResult-compatible objects for _create_total_file
            from app.schemas.notes import BatchFileResult as BFR, BatchFileStatus as BFS
            bfr_results = [
                BFR(filename=r['filename'], output_filename=r['output_filename'],
                    note_type=r['note_type'], status=BFS(r['status']),
                    attempts=r['attempts'], error_message=r.get('error_message'),
                    generation_time_seconds=r.get('generation_time_seconds'))
                for r in results
            ]
            _create_total_file(bfr_results, output_folder, total_path, separator)

            total_time = round(time.time() - start_time, 2)
            processed = sum(1 for r in results if r['status'] == 'completed')
            failed = sum(1 for r in results if r['status'] == 'failed')

            final_response = {
                'total_files': len(results),
                'processed': processed,
                'failed': failed,
                'results': results,
                'total_file': str(total_path),
                'total_time_seconds': total_time,
            }

            yield _sse_event('complete', final_response)

        except Exception as e:
            logger.error(f"Batch SSE processing failed: {e}", exc_info=True)
            yield _sse_event('error', {'detail': 'Batch processing failed due to an internal error'})
        finally:
            try:
                purge_all_patient_data()
            except Exception as purge_err:
                logger.critical(f"Final HIPAA purge failed: {purge_err}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/list-folder", response_model=BatchFolderListResponse)
async def list_folder_contents(
    folder_path: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    List processable files in a folder for batch processing preview.

    Returns file list with detected note types.
    Only .txt files are listed (PDFs require individual upload with OCR).
    """
    from app.services.batch_processor import (
        get_processable_files, detect_note_type, validate_folder_path
    )

    if not folder_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="folder_path query parameter is required"
        )

    # Validate folder path (security: path traversal protection)
    try:
        validated_path = validate_folder_path(folder_path)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    try:
        files = get_processable_files(str(validated_path))
        file_list = []
        for f in files:
            file_list.append(BatchFolderFile(
                filename=f.name,
                size_bytes=f.stat().st_size,
                note_type=detect_note_type(f.name),
                output_filename=f.stem + ".vaucda",
            ))

        return BatchFolderListResponse(
            folder_path=str(validated_path),
            total_files=len(file_list),
            files=file_list,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"List folder failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list folder contents"
        )


@router.get("/browse-directory")
async def browse_directory(
    path: Optional[str] = None,
    current_user: User = Depends(get_current_active_user)
):
    """
    Browse server-side directories for batch processing folder selection.

    Returns subdirectories and .txt file count for the given path.
    If no path is provided, returns configured allowed directories as roots,
    or the user's home directory if BATCH_ALLOWED_DIRS is not configured.
    """
    from pathlib import Path as PathLib

    try:
        if not path:
            # Return root directories
            allowed_dirs = settings.batch_allowed_dirs_list
            if allowed_dirs:
                roots = []
                for d in allowed_dirs:
                    p = PathLib(d)
                    if p.is_dir():
                        txt_count = sum(1 for f in p.iterdir() if f.is_file() and f.suffix.lower() == '.txt')
                        roots.append({
                            "name": p.name or str(p),
                            "path": str(p),
                            "txt_file_count": txt_count,
                        })
                return {
                    "current_path": None,
                    "parent_path": None,
                    "directories": roots,
                    "txt_file_count": 0,
                }
            else:
                # Default to home directory
                home = PathLib.home()
                path = str(home)

        # Validate the path
        from app.services.batch_processor import validate_folder_path
        try:
            validated = validate_folder_path(path)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

        # List subdirectories
        subdirs = []
        txt_count = 0
        try:
            for item in sorted(validated.iterdir(), key=lambda x: x.name.lower()):
                if item.name.startswith('.'):
                    continue  # Skip hidden files/dirs
                if item.is_dir():
                    sub_txt = sum(1 for f in item.iterdir() if f.is_file() and f.suffix.lower() == '.txt')
                    subdirs.append({
                        "name": item.name,
                        "path": str(item),
                        "txt_file_count": sub_txt,
                    })
                elif item.is_file() and item.suffix.lower() == '.txt':
                    txt_count += 1
        except PermissionError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied reading directory"
            )

        # Compute parent path
        parent = validated.parent
        parent_path = str(parent) if parent != validated else None

        # If BATCH_ALLOWED_DIRS is set, don't allow navigating above allowed roots
        allowed_dirs = settings.batch_allowed_dirs_list
        if allowed_dirs and parent_path:
            parent_allowed = False
            for ad in allowed_dirs:
                ad_resolved = PathLib(ad).resolve()
                parent_resolved = PathLib(parent_path).resolve()
                if parent_resolved == ad_resolved or ad_resolved in parent_resolved.parents:
                    parent_allowed = True
                    break
            if not parent_allowed:
                parent_path = None

        return {
            "current_path": str(validated),
            "parent_path": parent_path,
            "directories": subdirs,
            "txt_file_count": txt_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Browse directory failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to browse directory"
        )


# ============================================================================
# SESSION MANAGEMENT ENDPOINTS (Cross-Patient Contamination Prevention)
# ============================================================================

@router.post("/new-session")
async def start_new_patient_session(
    current_user: User = Depends(get_current_active_user)
):
    """
    Start a new patient session - PURGES all previous patient data.

    CRITICAL: Call this endpoint when:
    - User clicks "New Patient" button
    - User clicks "Clear Note" button
    - Before starting work on a different patient

    This ensures complete data isolation between patients (HIPAA compliance).
    """
    from app.services.note_processing.session_manager import (
        get_session_manager,
        purge_all_patient_data
    )

    try:
        logger.info(f"User {current_user.id} requesting new patient session (purging previous data)")

        # Purge ALL previous patient data
        purge_all_patient_data()

        # Start fresh session
        session_mgr = get_session_manager()
        new_session = session_mgr.start_session(patient_identifier=f"user_{current_user.id}")

        logger.info(f"New patient session started: {new_session.session_id}")

        return {
            "status": "success",
            "message": "Previous patient data purged. New session started.",
            "session_id": new_session.session_id
        }

    except Exception as e:
        logger.error(f"Failed to start new session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start new session: {str(e)}"
        )


@router.post("/end-session")
async def end_patient_session(
    current_user: User = Depends(get_current_active_user)
):
    """
    End current patient session and PURGE all patient data.

    CRITICAL: Call this endpoint when:
    - User logs out
    - User closes the application
    - Session timeout occurs

    This ensures no patient data persists after the session ends (HIPAA compliance).
    """
    from app.services.note_processing.session_manager import (
        get_session_manager,
        purge_all_patient_data
    )

    try:
        logger.info(f"User {current_user.id} ending patient session (purging all data)")

        # Purge ALL patient data
        purge_all_patient_data()

        logger.info("Patient session ended and all data purged")

        return {
            "status": "success",
            "message": "Patient session ended. All patient data purged."
        }

    except Exception as e:
        logger.error(f"Failed to end session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to end session: {str(e)}"
        )


@router.get("/session-status")
async def get_session_status(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current session status (for debugging/monitoring).

    Returns whether a patient session is active and session metadata.
    """
    from app.services.note_processing.session_manager import get_session_manager

    try:
        session_mgr = get_session_manager()
        current_session = session_mgr.get_current_session()

        if current_session:
            return {
                "session_active": True,
                "session_id": current_session.session_id,
                "created_at": current_session.created_at.isoformat(),
                "has_clinical_input": current_session.clinical_input is not None,
                "has_preliminary_note": current_session.preliminary_note is not None,
                "has_embeddings": current_session.source_embeddings is not None
            }
        else:
            return {
                "session_active": False,
                "session_id": None,
                "message": "No active patient session"
            }

    except Exception as e:
        logger.error(f"Failed to get session status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session status: {str(e)}"
        )


# ============================================================================
# LEGACY ENDPOINTS
# ============================================================================

@router.get("/templates")
async def list_templates(
    current_user: User = Depends(get_current_active_user)
):
    """
    List available note templates.

    Returns available note types and descriptions.
    """
    from app.services.template_manager import get_template_manager

    template_manager = get_template_manager()
    available_types = template_manager.get_available_types()

    return {
        "templates": available_types,
        "total": len(available_types)
    }


# ============================================================================
# CATCH-ALL ROUTE (must be LAST to avoid intercepting specific GET routes)
# ============================================================================

@router.get("/{note_id}")
async def get_note(
    note_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve a previously generated note.

    **Note:** Currently notes are not persisted (HIPAA compliance).
    This endpoint is reserved for future session-based retrieval.

    IMPORTANT: This route MUST remain the last GET route in this file.
    It uses a path parameter that would otherwise intercept routes like
    /list-folder, /session-status, /templates, etc.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Note persistence not implemented (notes are session-only for HIPAA compliance)"
    )
