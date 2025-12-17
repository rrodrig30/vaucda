"""
VAUCDA FastAPI Application
Main entry point for the REST API server
"""

# CRITICAL: Detect GPUs FIRST before any other imports
# This MUST be the first code executed to preserve multi-GPU visibility
# The accelerate library restricts GPU visibility after model loading
from llm.gpu_config import get_gpu_config
_GPU_CONFIG = get_gpu_config()

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
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
        else:
            app.state.neo4j = neo4j_client
            logger.info(f"Neo4j connected successfully: {settings.NEO4J_URI}")
    except Exception as e:
        logger.warning(f"Neo4j connection failed: {e} - RAG features will be disabled")
        app.state.neo4j = None

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

    # Verify Ollama availability (optional but recommended)
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    models = data.get("models", [])
                    logger.info(f"Ollama available with {len(models)} models")
                    app.state.ollama_available = True
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


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing."""
    start_time = time.time()

    # Process request
    response = await call_next(request)

    # Calculate duration
    duration = time.time() - start_time

    # Log request (NO PHI - only metadata)
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Duration: {duration:.3f}s"
    )

    # Add custom headers
    response.headers["X-Process-Time"] = str(duration)
    response.headers["X-API-Version"] = settings.APP_VERSION

    return response


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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    # Log validation errors for debugging
    logger.error(f"Validation error on {request.method} {request.url.path}:")
    for error in exc.errors():
        logger.error(f"  Field: {error['loc']}, Error: {error['msg']}, Type: {error['type']}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "details": exc.errors(),
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
