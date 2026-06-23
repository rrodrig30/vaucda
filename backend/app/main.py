"""
VAUCDA FastAPI Application
Main entry point for the REST API server
"""

# CRITICAL: Detect GPUs FIRST before any other imports
# This MUST be the first code executed to preserve multi-GPU visibility
# The accelerate library restricts GPU visibility after model loading
from llm.gpu_config import get_gpu_config
_GPU_CONFIG = get_gpu_config()

# Load .env into os.environ so VAUCDA_* feature flags read via
# os.environ.get() (e.g. VAUCDA_HPI_V2, VAUCDA_CONSISTENCY_CHECK) pick
# up values from the .env file. Pydantic-Settings reads .env only into
# its Settings model — it does NOT populate os.environ, so flags read
# with os.environ.get() would silently miss .env values without this.
from dotenv import load_dotenv as _load_dotenv
_load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import asyncio
import logging
import time

from app.config import settings
from app.database.sqlite_session import init_db, close_db
from app.api.v1 import auth, notes, calculators, settings as settings_api, health, rag, llm, documents
from database.neo4j_client import Neo4jClient, Neo4jConfig
import redis


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # Initialize SQLite database
    try:
        await init_db()
        logger.info("SQLite database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize SQLite database: {e}")
        raise

    # Initialize Neo4j connection (optional - for RAG features)
    neo4j_client = None
    try:
        neo4j_config = Neo4jConfig(
            uri=settings.NEO4J_URI,
            username=settings.NEO4J_USER,
            password=settings.NEO4J_PASSWORD,
            encrypted=settings.NEO4J_ENCRYPTED
        )
        neo4j_client = Neo4jClient(neo4j_config)
        is_connected = await neo4j_client.verify_connectivity()
        if not is_connected:
            logger.warning("Neo4j not available - RAG features will be disabled")
            app.state.neo4j = None
            neo4j_client = None
        else:
            app.state.neo4j = neo4j_client
            logger.info(f"Neo4j connected successfully: {settings.NEO4J_URI}")
    except Exception as e:
        logger.warning(f"Neo4j connection failed: {e} - RAG features will be disabled")
        app.state.neo4j = None
        neo4j_client = None

    # Initialize RAG Pipeline (requires Neo4j)
    app.state.rag_pipeline = None
    if neo4j_client is not None:
        try:
            from rag.embeddings import EmbeddingGenerator
            from rag.retriever import RAGRetriever
            from rag.rag_pipeline import RAGPipeline

            embedding_generator = EmbeddingGenerator()
            retriever = RAGRetriever(neo4j_client, embedding_generator)
            rag_pipeline = RAGPipeline(
                retriever=retriever,
                neo4j_client=neo4j_client,
                embedding_generator=embedding_generator
            )
            app.state.rag_pipeline = rag_pipeline
            logger.info("RAG pipeline initialized successfully")
        except Exception as e:
            logger.warning(f"RAG pipeline initialization failed: {e} - RAG features will be limited")
            app.state.rag_pipeline = None

    # Initialize Redis connection (optional - for caching)
    try:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=settings.REDIS_DECODE_RESPONSES,
            socket_connect_timeout=10,
            socket_keepalive=True,
            health_check_interval=30
        )
        redis_client.ping()
        app.state.redis = redis_client
        logger.info(f"Redis connected successfully: {settings.REDIS_URL}")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e} - Caching will be disabled")
        app.state.redis = None

    # Verify Ollama availability and (optionally) pre-warm the user's
    # configured Stage 1 / Stage 2 / OCR models. Pre-warming sends a tiny
    # /api/generate request to each model so weights are GPU-resident
    # before the first user request arrives. Combined with
    # OLLAMA_KEEP_ALIVE this eliminates the ~30s cold-start that
    # currently dominates the first request after backend idle.
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    models = data.get("models", [])
                    logger.info(f"Ollama available with {len(models)} models")
                    app.state.ollama_available = True

                    if getattr(settings, "ENABLE_MODEL_PREWARM", False):
                        # Determine which models to pre-warm by reading
                        # users' preferences from SQLite. We exclude
                        # system/seed accounts (admin@*) per
                        # MODEL_PREWARM_SKIP_USER_EMAILS so leftover
                        # defaults from initial install don't trigger
                        # pointless pre-warms. Failures non-fatal.
                        prewarm_models = set()
                        skip_emails = {
                            e.strip().lower()
                            for e in (settings.MODEL_PREWARM_SKIP_USER_EMAILS or "").split(",")
                            if e.strip()
                        }
                        try:
                            from sqlalchemy import select
                            from app.database.sqlite_models import (
                                UserPreferences,
                                User,
                            )
                            from app.database.sqlite_session import AsyncSessionLocal
                            async with AsyncSessionLocal() as db:
                                # Join to filter out skip-listed users
                                stmt = (
                                    select(UserPreferences, User.email)
                                    .join(User, User.user_id == UserPreferences.user_id)
                                )
                                rows = await db.execute(stmt)
                                for prefs, email in rows.all():
                                    if email and email.lower() in skip_emails:
                                        logger.info(
                                            f"  Pre-warm: skipping models from "
                                            f"system account '{email}'"
                                        )
                                        continue
                                    for m in (
                                        prefs.stage1_llm_model,
                                        prefs.stage2_llm_model,
                                        prefs.ocr_llm_model,
                                        prefs.default_model,
                                    ):
                                        if m:
                                            prewarm_models.add(m)
                        except Exception as e:
                            logger.warning(f"Could not read user preferences for pre-warm: {e}")
                        if not prewarm_models:
                            for m in (
                                settings.STAGE1_LLM_MODEL,
                                settings.STAGE2_LLM_MODEL,
                                settings.OCR_LLM_MODEL,
                                settings.OLLAMA_DEFAULT_MODEL,
                            ):
                                if m:
                                    prewarm_models.add(m)

                        # Size guard: skip local models larger than the
                        # configured budget. Cloud models (`:cloud`
                        # suffix) are exempt — they don't consume local
                        # VRAM. Local sizes come from `/api/tags`.
                        # Models that fail to fit produce 60s+ load
                        # stalls per backend restart for no benefit.
                        size_by_name = {}
                        for m_info in models:
                            name = m_info.get("name") or m_info.get("model")
                            sz = m_info.get("size") or 0
                            if name:
                                size_by_name[name] = sz
                        max_bytes = int(
                            settings.MODEL_PREWARM_MAX_LOCAL_GB * 1024 * 1024 * 1024
                        )

                        filtered = []
                        for m in sorted(prewarm_models):
                            if ":cloud" in m.lower():
                                filtered.append(m)
                                continue
                            sz = size_by_name.get(m)
                            if sz is None:
                                # Unknown locally (model not pulled).
                                # Try anyway - Ollama may resolve it.
                                filtered.append(m)
                                continue
                            if sz > max_bytes:
                                gb = sz / (1024 ** 3)
                                logger.warning(
                                    f"  Pre-warm: skipping {m} "
                                    f"({gb:.1f} GB > "
                                    f"{settings.MODEL_PREWARM_MAX_LOCAL_GB:.0f} GB "
                                    f"budget — would not fit in VRAM)"
                                )
                                continue
                            filtered.append(m)

                        # Pre-warm in the BACKGROUND. Even after size
                        # filtering, loading a 50GB+ local model can
                        # take 20-30s. start.sh's 30s health-check
                        # window would time out if we awaited it.
                        # Fire-and-forget asyncio task lets
                        # /api/v1/health come up immediately while
                        # pre-warming continues asynchronously.
                        prewarm_list = filtered
                        logger.info(
                            f"Scheduling background pre-warm of {len(prewarm_list)} "
                            f"model(s): {prewarm_list}"
                        )

                        async def _prewarm_models_background(model_names):
                            import aiohttp as _aiohttp
                            async with _aiohttp.ClientSession() as bg:
                                for m in model_names:
                                    try:
                                        async with bg.post(
                                            f"{settings.OLLAMA_BASE_URL}/api/generate",
                                            json={
                                                "model": m,
                                                "prompt": "ok",
                                                "stream": False,
                                                "keep_alive": settings.OLLAMA_KEEP_ALIVE,
                                                "options": {"num_predict": 1},
                                            },
                                            timeout=120,
                                        ) as r:
                                            if r.status == 200:
                                                logger.info(f"  Pre-warmed {m}")
                                            else:
                                                logger.warning(
                                                    f"  Pre-warm of {m} returned status {r.status}"
                                                )
                                    except Exception as e:
                                        logger.warning(f"  Pre-warm of {m} failed: {e}")

                        # Track the background task on app.state so it
                        # is cancelled cleanly during shutdown rather
                        # than emitting "Task was destroyed but is
                        # pending" warnings.
                        app.state.prewarm_task = asyncio.create_task(
                            _prewarm_models_background(prewarm_list),
                            name="model-prewarm",
                        )
                    else:
                        logger.info(
                            "Skipping model preload (ENABLE_MODEL_PREWARM=false)"
                        )
                else:
                    logger.warning(f"Ollama health check returned status {response.status}")
                    app.state.ollama_available = False
    except Exception as e:
        logger.warning(f"Ollama not available (this is optional): {e}")
        app.state.ollama_available = False

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Cancel background pre-warm task if still running
    if hasattr(app.state, 'prewarm_task'):
        task = app.state.prewarm_task
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    # Close Neo4j connection
    if hasattr(app.state, 'neo4j'):
        try:
            await app.state.neo4j.close()
            logger.info("Neo4j connection closed")
        except Exception as e:
            logger.error(f"Error closing Neo4j connection: {e}")

    # Close Redis connection
    if hasattr(app.state, 'redis'):
        try:
            app.state.redis.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")

    # Close SQLite database connections
    try:
        await close_db()
        logger.info("SQLite database connections closed")
    except Exception as e:
        logger.error(f"Error closing SQLite connections: {e}")

    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="VA Urology Clinical Documentation Assistant - LLM-powered clinical note generation with RAG",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan
)


# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.cors_methods_list,
    allow_headers=settings.cors_headers_list,
)


# Pure ASGI Request Logging Middleware
# NOTE: We use pure ASGI middleware instead of @app.middleware("http") because
# the decorator uses BaseHTTPMiddleware internally, which has known issues with
# StreamingResponse (causes CancelledError). Pure ASGI middleware avoids this.
STREAMING_ENDPOINTS = {"/api/v1/rag/upload-documents"}


class RequestLoggingMiddleware:
    """
    Pure ASGI middleware for request logging that doesn't break streaming responses.

    Unlike @app.middleware("http") which uses BaseHTTPMiddleware internally,
    this pure ASGI implementation passes streaming responses through without
    consuming the response body, avoiding CancelledError on long-running streams.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            # Pass through non-HTTP requests (websockets, etc.)
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        # For streaming endpoints, pass through completely without any wrapping
        if path in STREAMING_ENDPOINTS:
            logger.info(f"{method} {path} - Streaming endpoint (pure passthrough)")
            await self.app(scope, receive, send)
            return

        # For non-streaming endpoints, log with timing
        start_time = time.time()
        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                # Add custom headers
                headers = list(message.get("headers", []))
                duration = time.time() - start_time
                headers.append((b"x-process-time", str(duration).encode()))
                headers.append((b"x-api-version", settings.APP_VERSION.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.time() - start_time
            logger.info(
                f"{method} {path} - "
                f"Status: {status_code} - "
                f"Duration: {duration:.3f}s"
            )


# Add the pure ASGI middleware
app.add_middleware(RequestLoggingMiddleware)


# Exception handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
        }
    )


def sanitize_errors(errors):
    """Convert bytes and other non-serializable types in validation errors."""
    sanitized = []
    for error in errors:
        sanitized_error = {}
        for key, value in error.items():
            if isinstance(value, bytes):
                sanitized_error[key] = value.decode('utf-8', errors='replace')
            elif isinstance(value, (list, tuple)):
                sanitized_error[key] = [
                    v.decode('utf-8', errors='replace') if isinstance(v, bytes) else str(v)
                    for v in value
                ]
            else:
                sanitized_error[key] = value
        sanitized.append(sanitized_error)
    return sanitized


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    # Log validation errors for debugging
    logger.error(f"Validation error on {request.method} {request.url.path}:")
    for error in exc.errors():
        logger.error(f"  Field: {error.get('loc')}, Error: {error.get('msg')}, Type: {error.get('type')}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "details": sanitize_errors(exc.errors()),
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "error_code": "VAUCDA-050",
        }
    )


# API Routes
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(notes.router, prefix="/api/v1/notes", tags=["Notes"])
app.include_router(calculators.router, prefix="/api/v1/calculators", tags=["Calculators"])
app.include_router(rag.router, prefix="/api/v1/rag", tags=["RAG"])
app.include_router(llm.router, prefix="/api/v1/llm", tags=["LLM"])
app.include_router(settings_api.router, prefix="/api/v1/settings", tags=["Settings"])
app.include_router(documents.router, prefix="/api/v1", tags=["Documents"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
        "docs": "/api/docs" if settings.DEBUG else "Documentation disabled in production"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        workers=settings.API_WORKERS if not settings.DEBUG else 1,
        log_level=settings.LOG_LEVEL.lower()
    )
