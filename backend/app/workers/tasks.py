"""
Celery background tasks for asynchronous processing
"""
from datetime import datetime, timedelta
import logging
from typing import Dict, Any, Optional
from celery import Task
import json

from app.workers.celery_app import celery_app
from app.config import settings
from app.database.sqlite_session import SessionLocal
from app.database.sqlite_models import AuditLog, SessionLog
from sqlalchemy import delete
import asyncio

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """Base task with database session management."""

    _db = None

    @property
    def db(self):
        """Get database session (lazy initialization)."""
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def on_success(self, retval, task_id, args, kwargs):
        """Close database session on task success."""
        if self._db is not None:
            self._db.close()
            self._db = None

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Close database session on task failure."""
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(name="app.workers.tasks.generate_note_async", bind=True, base=DatabaseTask, max_retries=3)
def generate_note_async(
    self,
    session_id: str,
    clinical_input: str,
    note_type: str,
    selected_modules: list,
    llm_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate clinical note asynchronously.

    Performs complete note generation pipeline:
    1. Load appropriate template based on note_type
    2. Extract and parse clinical data from input
    3. Execute selected clinical calculators
    4. Generate note content using LLM with RAG retrieval
    5. Format and structure final output
    6. Store result in Redis with session_id key

    Args:
        session_id: Session identifier
        clinical_input: Unstructured clinical data
        note_type: Type of note (clinic_note, consult, preop, postop)
        selected_modules: List of calculator IDs to execute
        llm_config: LLM provider configuration including provider, model, temperature

    Returns:
        Generated note data with appendices and metadata

    Raises:
        Exception: On note generation failure (retried up to 3 times)
    """
    start_time = datetime.utcnow()

    try:
        logger.info(f"Starting async note generation for session {session_id}")

        # Update task state
        self.update_state(
            state="PROCESSING",
            meta={"status": "Initializing note generation", "progress": 10}
        )

        # Step 1: Load template
        self.update_state(
            state="PROCESSING",
            meta={"status": "Loading template", "progress": 20}
        )
        from app.services.template_manager import TemplateManager
        template_manager = TemplateManager()
        template_content = template_manager.load_template(note_type)
        logger.info(f"Loaded template for note type: {note_type}")

        # Step 2: Extract clinical data from input
        self.update_state(
            state="PROCESSING",
            meta={"status": "Extracting clinical data", "progress": 30}
        )
        from app.services.note_generator import NoteGenerator
        generator = NoteGenerator()
        extracted_data = generator._extract_clinical_data(clinical_input)
        logger.info(f"Extracted {len(extracted_data)} data points from clinical input")

        # Step 3: Execute selected calculators
        self.update_state(
            state="PROCESSING",
            meta={"status": "Executing calculators", "progress": 50}
        )
        calculator_results = {}
        from calculators.registry import CalculatorRegistry
        registry = CalculatorRegistry()

        for module_id in selected_modules:
            try:
                calculator = registry.get_calculator(module_id)
                if calculator:
                    result = calculator.calculate(extracted_data)
                    calculator_results[module_id] = result
                    logger.info(f"Executed calculator {module_id}")
            except Exception as e:
                logger.warning(f"Error executing calculator {module_id}: {e}")
                calculator_results[module_id] = {"error": str(e)}

        # Step 4: Generate note with LLM + RAG
        self.update_state(
            state="PROCESSING",
            meta={"status": "Generating note content", "progress": 70}
        )
        from rag.retriever import Retriever
        retriever = Retriever()
        rag_context = retriever.retrieve(clinical_input, top_k=5)

        note_content = generator.generate_note(
            clinical_input=clinical_input,
            note_type=note_type,
            template=template_content,
            calculator_results=calculator_results,
            rag_context=rag_context,
            llm_config=llm_config
        )
        logger.info(f"Generated note content ({len(note_content)} characters)")

        # Step 5: Format output
        self.update_state(
            state="PROCESSING",
            meta={"status": "Formatting output", "progress": 90}
        )
        generation_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        result = {
            "session_id": session_id,
            "status": "completed",
            "note_id": session_id,
            "note_content": note_content,
            "note_type": note_type,
            "calculators_executed": len(calculator_results),
            "calculator_results": calculator_results,
            "rag_context_used": len(rag_context) > 0,
            "generation_time_ms": generation_time_ms,
            "generated_at": datetime.utcnow().isoformat()
        }

        # Store in Redis
        try:
            import redis
            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            redis_client.setex(
                f"note_result:{session_id}",
                settings.NOTE_SESSION_TTL_MINUTES * 60,
                json.dumps(result)
            )
            logger.info(f"Stored note result in Redis for session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to store result in Redis: {e}")

        # Log audit entry
        try:
            audit_log = AuditLog(
                session_id=session_id,
                user_id="system",
                action="note_generation",
                module_used="note_generator",
                llm_provider=llm_config.get("provider", "unknown"),
                success=True,
                duration_ms=generation_time_ms
            )
            self.db.add(audit_log)
            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to log audit entry: {e}")

        self.update_state(
            state="PROCESSING",
            meta={"status": "Note generation complete", "progress": 100}
        )

        logger.info(f"Async note generation completed for session {session_id} in {generation_time_ms}ms")
        return result

    except Exception as e:
        logger.error(f"Error in async note generation: {str(e)}", exc_info=True)

        # Retry with exponential backoff
        try:
            raise self.retry(exc=e, countdown=2 ** self.request.retries)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for session {session_id}")
            self.update_state(
                state="FAILURE",
                meta={"error": str(e)}
            )
            raise


@celery_app.task(name="app.workers.tasks.cleanup_expired_sessions", bind=True, base=DatabaseTask)
def cleanup_expired_sessions(self) -> Dict[str, int]:
    """
    Clean up expired sessions from SQLite database.
    Runs every 5 minutes via Celery Beat.

    Deletes all session logs where expires_at timestamp is in the past.
    This prevents the database from accumulating old session metadata.

    Returns:
        Dictionary with cleanup statistics including count of deleted sessions
    """
    try:
        logger.info("Starting session cleanup task")

        # Delete sessions where expires_at < current_time
        now = datetime.utcnow()
        stmt = delete(SessionLog).where(SessionLog.expires_at < now)
        result = self.db.execute(stmt)
        deleted_count = result.rowcount
        self.db.commit()

        logger.info(f"Session cleanup completed. Deleted {deleted_count} expired sessions")

        return {
            "deleted_sessions": deleted_count,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in session cleanup: {str(e)}", exc_info=True)
        raise


@celery_app.task(name="app.workers.tasks.cleanup_old_audit_logs", bind=True, base=DatabaseTask)
def cleanup_old_audit_logs(self) -> Dict[str, int]:
    """
    Clean up audit logs older than retention period.
    Runs daily at 2 AM.

    Deletes all audit log entries where created_at is older than the configured
    retention period. This implements data lifecycle management for audit logs
    while maintaining compliance with log retention requirements.

    Returns:
        Dictionary with cleanup statistics including count of deleted logs and retention date
    """
    try:
        logger.info("Starting audit log cleanup task")

        retention_date = datetime.utcnow() - timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)

        # Delete audit logs older than retention date
        stmt = delete(AuditLog).where(AuditLog.created_at < retention_date)
        result = self.db.execute(stmt)
        deleted_count = result.rowcount
        self.db.commit()

        logger.info(f"Audit log cleanup completed. Deleted {deleted_count} logs older than {retention_date.isoformat()}")

        return {
            "deleted_logs": deleted_count,
            "retention_date": retention_date.isoformat(),
            "retention_days": settings.AUDIT_LOG_RETENTION_DAYS,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in audit log cleanup: {str(e)}", exc_info=True)
        raise


@celery_app.task(name="app.workers.tasks.ingest_document", bind=True, max_retries=3)
def ingest_document(
    self,
    file_path: str,
    document_type: str,
    category: Optional[str] = None,
    source: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ingest document into Neo4j knowledge base for RAG system.

    Performs complete document ingestion pipeline:
    1. Parse document (PDF/DOCX/TXT format)
    2. Extract text content and metadata
    3. Chunk text into manageable segments
    4. Generate embeddings for each chunk
    5. Store chunks and embeddings in Neo4j with metadata

    Args:
        file_path: Path to document file to ingest
        document_type: Type of document (guideline, reference, calculator_doc, literature)
        category: Medical category (prostate, kidney, bladder, fertility, stones, etc.)
        source: Source organization (NCCN, AUA, EAU, etc.)

    Returns:
        Dictionary with ingestion result including document_id and chunks count

    Raises:
        Exception: On ingestion failure (retried up to 3 times with exponential backoff)
    """
    import os
    import PyPDF2
    from docx import Document
    import uuid

    start_time = datetime.utcnow()

    try:
        logger.info(f"Starting document ingestion: {file_path}")

        # Verify file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Document file not found: {file_path}")

        # Step 1: Parse document based on file type
        logger.info(f"Parsing document: {os.path.basename(file_path)}")
        file_ext = os.path.splitext(file_path)[1].lower()

        text_content = ""
        if file_ext == ".pdf":
            with open(file_path, "rb") as pdf_file:
                reader = PyPDF2.PdfReader(pdf_file)
                text_content = "\n".join(
                    page.extract_text() for page in reader.pages if page.extract_text()
                )
        elif file_ext == ".docx":
            doc = Document(file_path)
            text_content = "\n".join(paragraph.text for paragraph in doc.paragraphs)
        elif file_ext == ".txt":
            with open(file_path, "r", encoding="utf-8") as txt_file:
                text_content = txt_file.read()
        else:
            raise ValueError(f"Unsupported document format: {file_ext}")

        if not text_content.strip():
            raise ValueError("Document contains no extractable text")

        logger.info(f"Extracted {len(text_content)} characters from document")

        # Step 2: Chunk text
        logger.info("Chunking document text")
        from rag.chunking import MedicalDocumentChunker
        chunker = MedicalDocumentChunker()

        # Choose chunking strategy based on document type
        if document_type == "guideline":
            chunks = chunker.chunk_guideline(text_content, {
                "source": source,
                "category": category
            })
        elif document_type == "literature":
            chunks = chunker.chunk_literature(text_content, {
                "source": source,
                "category": category
            })
        else:
            chunks = chunker.chunk_generic(text_content, {
                "document_type": document_type,
                "source": source,
                "category": category
            })

        logger.info(f"Created {len(chunks)} chunks from document")

        # Step 3: Generate embeddings
        logger.info("Generating embeddings for chunks")
        from rag.embeddings import EmbeddingGenerator
        embedder = EmbeddingGenerator()

        for chunk in chunks:
            chunk.embedding = embedder.generate_embedding(chunk.content)

        logger.info(f"Generated embeddings for {len(chunks)} chunks")

        # Step 4: Store in Neo4j
        logger.info("Storing chunks in Neo4j knowledge base")

        # Import Neo4j client from app state (if available in context)
        try:
            from app.main import app
            neo4j_client = app.state.neo4j
        except:
            # Fallback: create new Neo4j client
            from database.neo4j_client import Neo4jClient, Neo4jConfig
            neo4j_config = Neo4jConfig()
            neo4j_client = Neo4jClient(neo4j_config)

        # Generate document ID
        document_id = str(uuid.uuid4())

        # Store chunks in Neo4j (batch operation)
        asyncio.run(neo4j_client.batch_ingest_documents(
            chunks,
            metadata={
                "document_id": document_id,
                "document_type": document_type,
                "category": category,
                "source": source,
                "file_path": file_path,
                "ingested_at": datetime.utcnow().isoformat()
            }
        ))

        ingestion_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        result = {
            "status": "completed",
            "document_id": document_id,
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "document_type": document_type,
            "category": category,
            "source": source,
            "chunks_created": len(chunks),
            "total_characters": len(text_content),
            "ingestion_time_ms": ingestion_time_ms,
            "ingested_at": datetime.utcnow().isoformat()
        }

        logger.info(f"Document ingestion completed successfully. Document ID: {document_id}, "
                   f"Chunks: {len(chunks)}, Time: {ingestion_time_ms}ms")

        return result

    except Exception as e:
        logger.error(f"Error in document ingestion: {str(e)}", exc_info=True)

        # Retry with exponential backoff
        try:
            raise self.retry(exc=e, countdown=2 ** self.request.retries)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for document ingestion: {file_path}")
            raise
