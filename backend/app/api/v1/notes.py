"""
Note Generation API endpoints
Handles clinical note generation with LLM and RAG
"""

import logging
import os
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_active_user
from app.database.sqlite_models import User
from app.database.sqlite_session import get_db
from app.schemas.notes import (
    NoteGenerateRequest,
    NoteResponse,
    InitialNoteRequest,
    InitialNoteResponse,
    FinalNoteRequest,
    FinalNoteResponse
)
from app.services.note_generator import NoteGenerator
from llm.llm_manager import LLMManager, TaskType
from database.neo4j_client import Neo4jClient, Neo4jConfig
from rag.embeddings import EmbeddingGenerator

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


# Dependency injection
def get_note_generator() -> NoteGenerator:
    """Get note generator instance with dependencies."""
    try:
        # Get shared LLM manager instance
        llm_manager = get_llm_manager()

        # Initialize Neo4j client (optional - may not be running)
        try:
            neo4j_config = Neo4jConfig()
            neo4j_client = Neo4jClient(neo4j_config)
        except Exception as e:
            logger.warning(f"Neo4j not available: {e}")
            neo4j_client = None

        # Initialize embedding generator (optional)
        try:
            embedding_generator = EmbeddingGenerator() if neo4j_client else None
        except Exception as e:
            logger.warning(f"Embedding generator not available: {e}")
            embedding_generator = None

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


@router.get("/{note_id}")
async def get_note(
    note_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve a previously generated note.

    **Note:** Currently notes are not persisted (HIPAA compliance).
    This endpoint is reserved for future session-based retrieval.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Note persistence not implemented (notes are session-only for HIPAA compliance)"
    )


# ============================================================================
# TWO-STAGE WORKFLOW ENDPOINTS (Improved Clinical Workflow)
# ============================================================================

@router.post("/generate-initial", response_model=InitialNoteResponse)
async def generate_initial_note(
    request: InitialNoteRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    STAGE 1: Generate preliminary note with calculator suggestions.

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
            f"(type: {request.note_type}, provider: {request.llm_provider})"
        )

        # Step 1: Retrieve context via Vector RAG (for structured note generation)
        rag_context = ""
        rag_sources = []

        if request.use_rag:
            try:
                from rag.rag_pipeline import RAGPipeline
                from rag.retriever import RAGRetriever
                from rag.embeddings import get_embedding_generator
                from database.neo4j_client import Neo4jClient, Neo4jConfig

                # Initialize RAG pipeline
                try:
                    neo4j_config = Neo4jConfig()
                    neo4j_client = Neo4jClient(neo4j_config)
                    embedding_generator = get_embedding_generator()
                    retriever = RAGRetriever(neo4j_client, embedding_generator)

                    rag_pipeline = RAGPipeline(
                        retriever=retriever,
                        neo4j_client=neo4j_client,
                        embedding_generator=embedding_generator
                    )

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
                except Exception as e:
                    logger.warning(f"RAG pipeline initialization failed: {e}")
            except Exception as e:
                logger.warning(f"RAG retrieval failed: {e}")

        # Step 3: Generate preliminary note using section extraction + template builder (Stage 1)
        note_generator = get_note_generator()

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
        preliminary_note = build_urology_note(request.clinical_input)

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
                'llm_provider': request.llm_provider
            }
        )

    except Exception as e:
        logger.error(f"Initial note generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Initial note generation failed: {str(e)}"
        )


@router.post("/generate-final", response_model=FinalNoteResponse)
async def generate_final_note(
    request: FinalNoteRequest,
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
    """
    from app.schemas.notes import FinalNoteResponse, CalculatorResultSchema
    from app.services.note_processing.note_identifier import identify_notes
    from app.services.note_processing.stage2_builder import build_stage2_note
    from calculators.registry import CalculatorRegistry
    from app.services.entity_extractor import ClinicalEntityExtractor
    from sqlalchemy import select
    from app.database.sqlite_models import UserPreferences
    import time

    try:
        start_time = time.time()

        logger.info(
            f"User {current_user.id} requesting Stage 2 agent-based note generation "
            f"with {len(request.selected_calculators)} calculators"
        )

        # Step 0: Load user settings to get selected model
        user_model = None
        try:
            stmt = select(UserPreferences).where(UserPreferences.user_id == current_user.user_id)
            result = await db.execute(stmt)
            prefs = result.scalars().first()
            if prefs and prefs.default_model:
                user_model = prefs.default_model
                logger.info(f"Using user-selected model: {user_model}")
            else:
                logger.info(f"No user model preference found, using .env default")
        except Exception as e:
            logger.warning(f"Failed to load user preferences: {e}, using .env default")

        # Step 1: Identify notes from clinical input (to get GU notes for prior assessments/plans)
        logger.info("Step 1: Identifying historical GU notes...")
        notes_dict = identify_notes(request.clinical_input)
        gu_notes = notes_dict.get("gu_notes", [])
        logger.info(f"Found {len(gu_notes)} GU notes for historical context")

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

        # Step 4: Retrieve evidence via RAG (if enabled)
        logger.info("Step 4: Retrieving RAG content...")
        rag_sources = []
        rag_content = ""

        if request.use_rag:
            try:
                from rag.rag_pipeline import RAGPipeline
                from rag.retriever import RAGRetriever
                from rag.embeddings import get_embedding_generator
                from database.neo4j_client import Neo4jClient, Neo4jConfig

                try:
                    neo4j_config = Neo4jConfig()
                    neo4j_client = Neo4jClient(neo4j_config)
                    embedding_generator = get_embedding_generator()
                    retriever = RAGRetriever(neo4j_client, embedding_generator)

                    rag_pipeline = RAGPipeline(
                        retriever=retriever,
                        neo4j_client=neo4j_client,
                        embedding_generator=embedding_generator
                    )

                    # Use GRAPH RAG for Assessment & Plan
                    rag_result = await rag_pipeline.retrieve_and_augment(
                        query=request.clinical_input,
                        k=5,
                        search_strategy="graph",
                        category=None
                    )

                    rag_content = rag_result.context
                    rag_sources = rag_result.sources

                    logger.info(
                        f"Retrieved {len(rag_sources)} RAG sources "
                        f"({len(rag_content)} chars context)"
                    )
                except Exception as e:
                    logger.warning(f"RAG pipeline initialization failed: {e}")
            except Exception as e:
                logger.warning(f"RAG retrieval failed: {e}")

        # Step 5: Generate Stage 2 note using agent-based architecture
        logger.info("Step 5: Generating Stage 2 Assessment & Plan using specialized agents...")

        # Prepare ambient transcript (if provided in request)
        # In future, this will come from real-time ambient listening
        ambient_transcript = None  # TODO: Add ambient_transcript field to FinalNoteRequest schema

        # Build Stage 2 note with user-selected model
        complete_note = build_stage2_note(
            stage1_note=request.preliminary_note,
            gu_notes=gu_notes,
            ambient_transcript=ambient_transcript,
            calculator_results=calculator_results_dict,
            rag_content=rag_content,
            model=user_model,
            note_type=request.note_type,
            patient_name=request.patient_name,
            ssn_last4=request.ssn_last4
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
                'rag_enabled': request.use_rag,
                'rag_sources_count': len(rag_sources),
                'gu_notes_found': len(gu_notes),
                'workflow': 'stage2_agent_based'
            }
        )

    except Exception as e:
        logger.error(f"Stage 2 agent-based note generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stage 2 agent-based note generation failed: {str(e)}"
        )


@router.post("/generate-two-stage", response_model=NoteResponse)
async def generate_note_two_stage(
    request: NoteGenerateRequest,
    current_user: User = Depends(get_current_active_user),
    note_generator: NoteGenerator = Depends(get_note_generator)
):
    """
    Generate clinical note using improved two-model workflow.

    **Stage 1 (Data Extraction):** qwen3-coder:30b
    - Extracts and organizes clinical data
    - Lower temperature (0.1) for factual accuracy
    - Structured data output without interpretation

    **Stage 2 (Clinical Reasoning):** llama3.1:70b
    - Generates final note with Assessment & Plan
    - Incorporates calculator results and evidence
    - Clinical reasoning and recommendations

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
    current_user: User = Depends(get_current_active_user)
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
    """
    from app.schemas.notes import FinalNoteResponse, CalculatorResultSchema
    from app.services.note_processing.note_identifier import identify_notes
    from app.services.note_processing.stage2_builder import build_stage2_note
    from calculators.registry import CalculatorRegistry
    from app.services.entity_extractor import ClinicalEntityExtractor
    from sqlalchemy import select
    from app.database.sqlite_models import UserPreferences
    import time

    try:
        start_time = time.time()

        logger.info(
            f"User {current_user.id} requesting Stage 2 agent-based note generation "
            f"with {len(request.selected_calculators)} calculators"
        )

        # Step 0: Load user settings to get selected model
        user_model = None
        try:
            stmt = select(UserPreferences).where(UserPreferences.user_id == current_user.user_id)
            result = await db.execute(stmt)
            prefs = result.scalars().first()
            if prefs and prefs.default_model:
                user_model = prefs.default_model
                logger.info(f"Using user-selected model: {user_model}")
            else:
                logger.info(f"No user model preference found, using .env default")
        except Exception as e:
            logger.warning(f"Failed to load user preferences: {e}, using .env default")

        # Step 1: Identify notes from clinical input (to get GU notes for prior assessments/plans)
        logger.info("Step 1: Identifying historical GU notes...")
        notes_dict = identify_notes(request.clinical_input)
        gu_notes = notes_dict.get("gu_notes", [])
        logger.info(f"Found {len(gu_notes)} GU notes for historical context")

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

        # Step 4: Retrieve evidence via RAG (if enabled)
        logger.info("Step 4: Retrieving RAG content...")
        rag_sources = []
        rag_content = ""

        if request.use_rag:
            try:
                from rag.rag_pipeline import RAGPipeline
                from rag.retriever import RAGRetriever
                from rag.embeddings import get_embedding_generator
                from database.neo4j_client import Neo4jClient, Neo4jConfig

                try:
                    neo4j_config = Neo4jConfig()
                    neo4j_client = Neo4jClient(neo4j_config)
                    embedding_generator = get_embedding_generator()
                    retriever = RAGRetriever(neo4j_client, embedding_generator)

                    rag_pipeline = RAGPipeline(
                        retriever=retriever,
                        neo4j_client=neo4j_client,
                        embedding_generator=embedding_generator
                    )

                    # Use GRAPH RAG for Assessment & Plan
                    rag_result = await rag_pipeline.retrieve_and_augment(
                        query=request.clinical_input,
                        k=5,
                        search_strategy="graph",
                        category=None
                    )

                    rag_content = rag_result.context
                    rag_sources = rag_result.sources

                    logger.info(
                        f"Retrieved {len(rag_sources)} RAG sources "
                        f"({len(rag_content)} chars context)"
                    )
                except Exception as e:
                    logger.warning(f"RAG pipeline initialization failed: {e}")
            except Exception as e:
                logger.warning(f"RAG retrieval failed: {e}")

        # Step 5: Generate Stage 2 note using agent-based architecture
        logger.info("Step 5: Generating Stage 2 Assessment & Plan using specialized agents...")

        # Prepare ambient transcript (if provided in request)
        # In future, this will come from real-time ambient listening
        ambient_transcript = None  # TODO: Add ambient_transcript field to FinalNoteRequest schema

        # Build Stage 2 note with user-selected model
        complete_note = build_stage2_note(
            stage1_note=request.preliminary_note,
            gu_notes=gu_notes,
            ambient_transcript=ambient_transcript,
            calculator_results=calculator_results_dict,
            rag_content=rag_content,
            model=user_model,
            note_type=request.note_type,
            patient_name=request.patient_name,
            ssn_last4=request.ssn_last4
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
                'rag_enabled': request.use_rag,
                'rag_sources_count': len(rag_sources),
                'gu_notes_found': len(gu_notes),
                'workflow': 'stage2_agent_based'
            }
        )

    except Exception as e:
        logger.error(f"Stage 2 agent-based note generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stage 2 agent-based note generation failed: {str(e)}"
        )


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
