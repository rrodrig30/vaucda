"""
Neo4j Database Client for VAUCDA

Production-ready Neo4j driver integration with:
- Connection pooling and management
- Vector search capabilities
- Session TTL management
- HIPAA-compliant audit logging
- Error handling and retries
"""

import os
import logging
from typing import List, Dict, Any, Optional, AsyncIterator
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from neo4j import GraphDatabase, AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable, TransientError
import asyncio

logger = logging.getLogger(__name__)


class Neo4jConfig:
    """Configuration for Neo4j database connection."""

    def __init__(
        self,
        uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        max_connection_lifetime: int = 3600,  # 1 hour
        max_connection_pool_size: int = 100,
        connection_acquisition_timeout: int = 60,
        encrypted: Optional[bool] = None
    ):
        # CRITICAL: All Neo4j credentials and connection parameters MUST come from environment
        # Fail-fast if required credentials are missing (per rules.txt - no defaults)
        self.uri = uri or os.getenv("NEO4J_URI")
        self.username = username or os.getenv("NEO4J_USER")
        self.password = password or os.getenv("NEO4J_PASSWORD")

        if not self.uri:
            raise ValueError("NEO4J_URI environment variable is required")
        if not self.username:
            raise ValueError("NEO4J_USER environment variable is required")
        if not self.password:
            raise ValueError("NEO4J_PASSWORD environment variable is required")

        self.max_connection_lifetime = max_connection_lifetime
        self.max_connection_pool_size = max_connection_pool_size
        self.connection_acquisition_timeout = connection_acquisition_timeout
        self.encrypted = encrypted if encrypted is not None else (os.getenv("NEO4J_ENCRYPTED", "false").lower() == "true")


class Neo4jClient:
    """
    Async Neo4j database client for VAUCDA.

    Provides methods for:
    - Vector similarity search
    - Graph traversal queries
    - Session management with TTL
    - HIPAA-compliant audit logging
    """

    def __init__(self, config: Neo4jConfig):
        self.config = config
        self.driver = AsyncGraphDatabase.driver(
            config.uri,
            auth=(config.username, config.password),
            max_connection_lifetime=config.max_connection_lifetime,
            max_connection_pool_size=config.max_connection_pool_size,
            connection_acquisition_timeout=config.connection_acquisition_timeout,
            encrypted=config.encrypted,
            trust="TRUST_ALL_CERTIFICATES"  # Update for production with proper certs
        )
        logger.info(f"Neo4j client initialized: {config.uri}")

    async def close(self):
        """Close the database connection."""
        await self.driver.close()
        logger.info("Neo4j connection closed")

    async def verify_connectivity(self) -> bool:
        """
        Verify database connectivity.

        Returns:
            bool: True if connected, False otherwise
        """
        try:
            async with self.driver.session() as session:
                result = await session.run("RETURN 1 AS test")
                record = await result.single()
                return record["test"] == 1
        except ServiceUnavailable as e:
            logger.error(f"Neo4j service unavailable: {e}")
            return False
        except Exception as e:
            logger.error(f"Neo4j connectivity check failed: {e}")
            return False

    async def check_vector_indexes(self) -> Dict[str, str]:
        """
        Check status of vector indexes.

        Returns:
            Dict mapping index names to their states
        """
        async with self.driver.session() as session:
            result = await session.run("""
                SHOW INDEXES
                YIELD name, state, type
                WHERE name IN ['document_embeddings', 'concept_embeddings']
                RETURN name, state, type
            """)

            indexes = {}
            async for record in result:
                indexes[record["name"]] = record["state"]

            return indexes

    # =========================================================================
    # Vector Search Methods
    # =========================================================================

    async def vector_search_documents(
        self,
        query_embedding: List[float],
        k: int = 5,
        category: Optional[str] = None,
        min_publication_year: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search on Document nodes.

        Args:
            query_embedding: 768-dimensional query vector
            k: Number of results to return
            category: Filter by category (prostate, kidney, etc.)
            min_publication_year: Minimum publication year for filtering

        Returns:
            List of documents with similarity scores
        """
        query = """
        CALL db.index.vector.queryNodes('document_embeddings', $k, $query_embedding)
        YIELD node, score

        WHERE ($category IS NULL OR node.category = $category)
          AND ($min_year IS NULL OR node.publication_date.year >= $min_year)

        RETURN node.id AS doc_id,
               node.title AS title,
               node.content AS content,
               node.summary AS summary,
               node.source AS source,
               node.category AS category,
               node.version AS version,
               node.publication_date AS publication_date,
               score AS similarity_score
        ORDER BY score DESC
        LIMIT $k
        """

        min_year = min_publication_year if min_publication_year else None

        async with self.driver.session() as session:
            result = await session.run(
                query,
                query_embedding=query_embedding,
                k=k * 2,  # Fetch more for filtering
                category=category,
                min_year=min_year
            )

            documents = []
            async for record in result:
                documents.append({
                    "doc_id": record["doc_id"],
                    "title": record["title"],
                    "content": record["content"],
                    "summary": record["summary"],
                    "source": record["source"],
                    "category": record["category"],
                    "version": record["version"],
                    "publication_date": record["publication_date"],
                    "similarity_score": record["similarity_score"]
                })

            return documents[:k]

    async def hybrid_search(
        self,
        query_embedding: List[float],
        k: int = 5,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Hybrid retrieval: Vector search + Graph traversal.

        Retrieves documents via vector similarity, then enriches with:
        - Related clinical concepts
        - Applicable calculators

        Args:
            query_embedding: 768-dimensional query vector
            k: Number of results to return
            category: Filter by category

        Returns:
            List of enriched documents with graph context
        """
        query = """
        CALL db.index.vector.queryNodes('document_embeddings', $k, $query_embedding)
        YIELD node AS doc, score

        WHERE ($category IS NULL OR doc.category = $category)

        // Graph traversal for context
        MATCH (doc)-[:REFERENCES]->(concept:ClinicalConcept)
        OPTIONAL MATCH (concept)<-[:APPLIES_TO]-(calc:Calculator)

        RETURN doc.id AS document_id,
               doc.title AS document_title,
               doc.content AS content,
               doc.summary AS summary,
               score AS vector_score,
               collect(DISTINCT concept.name) AS related_concepts,
               collect(DISTINCT calc.name) AS applicable_calculators
        ORDER BY score DESC
        LIMIT $k
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                query_embedding=query_embedding,
                k=k,
                category=category
            )

            results = []
            async for record in result:
                results.append({
                    "document_id": record["document_id"],
                    "title": record["document_title"],
                    "content": record["content"],
                    "summary": record["summary"],
                    "vector_score": record["vector_score"],
                    "related_concepts": record["related_concepts"],
                    "applicable_calculators": record["applicable_calculators"]
                })

            return results

    # =========================================================================
    # Session Management Methods (HIPAA-Compliant)
    # =========================================================================

    async def create_session(
        self,
        session_id: str,
        user_id: str,
        note_type: str,
        llm_provider: str,
        model_used: str,
        selected_modules: List[str]
    ) -> Dict[str, Any]:
        """
        Create a new session with 30-minute TTL.

        HIPAA Compliance: Stores metadata only, no PHI.

        Args:
            session_id: Unique session identifier
            user_id: User ID (NOT username)
            note_type: Type of note being generated
            llm_provider: LLM provider used
            model_used: Specific model name
            selected_modules: List of calculator module IDs

        Returns:
            Session details with expiration time
        """
        query = """
        MERGE (u:User {user_id: $user_id})

        CREATE (s:Session {
            id: apoc.create.uuid(),
            session_id: $session_id,
            user_id: $user_id,
            note_type: $note_type,
            llm_provider: $llm_provider,
            model_used: $model_used,
            selected_modules: $selected_modules,
            created_at: datetime(),
            expires_at: datetime() + duration({minutes: 30}),
            last_accessed: datetime(),
            status: 'active'
        })

        CREATE (s)-[:BELONGS_TO]->(u)

        RETURN s.id AS session_db_id,
               s.session_id AS session_id,
               s.expires_at AS expires_at
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                session_id=session_id,
                user_id=user_id,
                note_type=note_type,
                llm_provider=llm_provider,
                model_used=model_used,
                selected_modules=selected_modules
            )

            record = await result.single()
            return {
                "session_db_id": record["session_db_id"],
                "session_id": record["session_id"],
                "expires_at": record["expires_at"]
            }

    async def update_session_metrics(
        self,
        session_id: str,
        generation_time_ms: int,
        tokens_used: int
    ) -> bool:
        """
        Update session with performance metrics.

        Args:
            session_id: Session identifier
            generation_time_ms: Generation time in milliseconds
            tokens_used: Number of tokens used

        Returns:
            bool: True if update successful
        """
        query = """
        MATCH (s:Session {session_id: $session_id})
        WHERE s.status = 'active'

        SET s.generation_time_ms = $generation_time_ms,
            s.tokens_used = $tokens_used,
            s.last_accessed = datetime()

        RETURN count(s) AS updated_count
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                session_id=session_id,
                generation_time_ms=generation_time_ms,
                tokens_used=tokens_used
            )

            record = await result.single()
            return record["updated_count"] == 1

    async def cleanup_expired_sessions(self) -> int:
        """
        Manually trigger cleanup of expired sessions.

        This is also run automatically every 5 minutes via APOC periodic procedure.

        Returns:
            Number of sessions deleted
        """
        query = """
        MATCH (s:Session)
        WHERE s.expires_at < datetime() AND s.status = 'active'

        SET s.status = 'expired'

        WITH s
        DETACH DELETE s

        RETURN count(s) AS deleted_count
        """

        async with self.driver.session() as session:
            result = await session.run(query)
            record = await result.single()
            deleted_count = record["deleted_count"]

            logger.info(f"Cleaned up {deleted_count} expired sessions")
            return deleted_count

    # =========================================================================
    # Audit Logging Methods (Metadata Only, HIPAA-Compliant)
    # =========================================================================

    async def create_audit_log(
        self,
        session_id: str,
        user_id: str,
        action: str,
        module_used: Optional[str] = None,
        input_hash: Optional[str] = None,
        output_hash: Optional[str] = None,
        duration_ms: Optional[int] = None,
        tokens_used: Optional[int] = None,
        llm_provider: Optional[str] = None,
        model_used: Optional[str] = None,
        success: bool = True,
        error_code: Optional[str] = None
    ) -> str:
        """
        Create audit log entry with metadata only (NO PHI).

        CRITICAL HIPAA COMPLIANCE:
        - Only hashes of input/output are stored, NOT actual content
        - No patient identifiers
        - No clinical data

        Args:
            session_id: Associated session ID
            user_id: User who performed action
            action: Action type (note_generation, calculator_use, etc.)
            module_used: Specific module/calculator used
            input_hash: SHA256 hash of input (NOT the input itself)
            output_hash: SHA256 hash of output (NOT the output itself)
            duration_ms: Processing duration
            tokens_used: LLM tokens used
            llm_provider: LLM provider name
            model_used: Model name
            success: Whether operation succeeded
            error_code: Non-descriptive error code if failed

        Returns:
            Audit log ID
        """
        query = """
        CREATE (a:AuditLog {
            id: apoc.create.uuid(),
            session_id: $session_id,
            user_id: $user_id,
            action: $action,
            module_used: $module_used,
            input_hash: $input_hash,
            output_hash: $output_hash,
            duration_ms: $duration_ms,
            tokens_used: $tokens_used,
            llm_provider: $llm_provider,
            model_used: $model_used,
            success: $success,
            error_code: $error_code,
            created_at: datetime(),
            expires_at: datetime() + duration({days: 90})
        })

        WITH a
        MATCH (s:Session {session_id: $session_id})
        CREATE (a)-[:LOGGED]->(s)

        RETURN a.id AS audit_log_id
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                session_id=session_id,
                user_id=user_id,
                action=action,
                module_used=module_used,
                input_hash=input_hash,
                output_hash=output_hash,
                duration_ms=duration_ms,
                tokens_used=tokens_used,
                llm_provider=llm_provider,
                model_used=model_used,
                success=success,
                error_code=error_code
            )

            record = await result.single()
            return record["audit_log_id"]

    # =========================================================================
    # Data Ingestion Methods
    # =========================================================================

    async def batch_ingest_documents(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> int:
        """
        Batch ingest documents with embeddings.

        Args:
            documents: List of document dictionaries with:
                - id: Document ID
                - title: Document title
                - content: Full text content
                - embedding: 768-dimensional vector
                - category: Category (prostate, kidney, etc.)
                - source: Source organization
                - Additional metadata
            batch_size: Number of documents per batch

        Returns:
            Total number of documents ingested
        """
        query = """
        UNWIND $documents AS doc
        MERGE (d:Document {id: doc.id})
        SET d.title = doc.title,
            d.content = doc.content,
            d.summary = doc.summary,
            d.embedding = doc.embedding,
            d.category = doc.category,
            d.source = doc.source,
            d.document_type = doc.document_type,
            d.version = doc.version,
            d.publication_date = date(doc.publication_date),
            d.keywords = doc.keywords,
            d.created_at = coalesce(d.created_at, datetime()),
            d.updated_at = datetime()
        RETURN count(d) AS ingested_count
        """

        total_ingested = 0

        # Process in batches
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]

            async with self.driver.session() as session:
                result = await session.run(query, documents=batch)
                record = await result.single()
                total_ingested += record["ingested_count"]

            logger.info(f"Ingested batch {i // batch_size + 1}: {len(batch)} documents")

        return total_ingested

    # =========================================================================
    # Calculator & Template Queries
    # =========================================================================

    async def get_calculator_by_id(self, calculator_id: str) -> Optional[Dict[str, Any]]:
        """Get calculator metadata by ID."""
        query = """
        MATCH (calc:Calculator {calculator_id: $calculator_id})
        RETURN calc.id AS id,
               calc.calculator_id AS calculator_id,
               calc.name AS name,
               calc.category AS category,
               calc.description AS description,
               calc.inputs AS inputs,
               calc.outputs AS outputs,
               calc.references AS references
        """

        async with self.driver.session() as session:
            result = await session.run(query, calculator_id=calculator_id)
            record = await result.single()

            if record:
                return dict(record)
            return None

    async def get_calculators_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Get all calculators in a category."""
        query = """
        MATCH (calc:Calculator {category: $category})
        RETURN calc.calculator_id AS calculator_id,
               calc.name AS name,
               calc.description AS description
        ORDER BY calc.name
        """

        async with self.driver.session() as session:
            result = await session.run(query, category=category)

            calculators = []
            async for record in result:
                calculators.append(dict(record))

            return calculators


# =============================================================================
# Session Cleanup Scheduler
# =============================================================================

class SessionCleanupScheduler:
    """Background scheduler for session TTL cleanup."""

    def __init__(self, neo4j_client: Neo4jClient, interval_seconds: int = 300):
        self.client = neo4j_client
        self.interval_seconds = interval_seconds
        self.running = False

    async def start(self):
        """Start the cleanup scheduler."""
        self.running = True
        logger.info(f"Session cleanup scheduler started (interval: {self.interval_seconds}s)")

        while self.running:
            try:
                deleted_count = await self.client.cleanup_expired_sessions()
                logger.info(f"Cleanup cycle: {deleted_count} sessions deleted")
            except Exception as e:
                logger.error(f"Cleanup cycle failed: {e}")

            await asyncio.sleep(self.interval_seconds)

    async def stop(self):
        """Stop the cleanup scheduler."""
        self.running = False
        logger.info("Session cleanup scheduler stopped")


# =============================================================================
# Connection Pool Manager (for FastAPI lifespan)
# =============================================================================

@asynccontextmanager
async def neo4j_lifespan(app):
    """
    FastAPI lifespan context manager for Neo4j connection.

    Usage:
        app = FastAPI(lifespan=neo4j_lifespan)
    """
    # Initialize Neo4j client
    config = Neo4jConfig()
    client = Neo4jClient(config)

    # Verify connectivity
    if not await client.verify_connectivity():
        raise RuntimeError("Failed to connect to Neo4j database")

    # Check vector indexes
    indexes = await client.check_vector_indexes()
    logger.info(f"Vector indexes status: {indexes}")

    # Start session cleanup scheduler
    scheduler = SessionCleanupScheduler(client)
    cleanup_task = asyncio.create_task(scheduler.start())

    # Store in app state
    app.state.neo4j_client = client
    app.state.cleanup_scheduler = scheduler

    yield

    # Cleanup on shutdown
    await scheduler.stop()
    cleanup_task.cancel()
    await client.close()
