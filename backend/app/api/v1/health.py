"""
Health check API endpoints
Provides system health status and readiness probes
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import time

from app.config import settings
from app.database.sqlite_session import get_db
from app.core.security import get_current_user
from app.database.sqlite_models import User


router = APIRouter()


# Track application start time
START_TIME = time.time()


@router.get("/health")
async def health_check():
    """
    Basic health check endpoint (no authentication required).
    Returns application status and uptime.
    """
    uptime_seconds = int(time.time() - START_TIME)

    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": uptime_seconds
    }


@router.get("/health/detailed")
async def detailed_health_check(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Detailed health check endpoint (requires authentication).
    Returns status of all services and dependencies.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {}
    }

    # Check SQLite database
    try:
        start_time = time.time()
        result = await db.execute(text("SELECT 1"))
        response_time_ms = int((time.time() - start_time) * 1000)

        health_status["services"]["sqlite"] = {
            "status": "healthy",
            "response_time_ms": response_time_ms
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["services"]["sqlite"] = {
            "status": "unhealthy",
            "error": str(e)
        }

    # Check Ollama connection
    try:
        start_time = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            response_time_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                models = response.json().get("models", [])
                health_status["services"]["ollama"] = {
                    "status": "healthy",
                    "response_time_ms": response_time_ms,
                    "models_available": len(models)
                }
            else:
                health_status["status"] = "degraded"
                health_status["services"]["ollama"] = {
                    "status": "degraded",
                    "response_time_ms": response_time_ms,
                    "error": f"HTTP {response.status_code}"
                }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["services"]["ollama"] = {
            "status": "unhealthy",
            "error": str(e)
        }

    # Check Neo4j connection
    try:
        from app.main import app
        if hasattr(app.state, 'neo4j'):
            start_time = time.time()
            neo4j_client = app.state.neo4j
            is_connected = await neo4j_client.verify_connectivity()
            response_time_ms = int((time.time() - start_time) * 1000)

            if is_connected:
                health_status["services"]["neo4j"] = {
                    "status": "healthy",
                    "response_time_ms": response_time_ms
                }
            else:
                health_status["status"] = "unhealthy"
                health_status["services"]["neo4j"] = {
                    "status": "unhealthy",
                    "error": "Neo4j connectivity verification failed"
                }
        else:
            health_status["status"] = "degraded"
            health_status["services"]["neo4j"] = {
                "status": "unavailable",
                "message": "Neo4j client not initialized"
            }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["services"]["neo4j"] = {
            "status": "unhealthy",
            "error": str(e)
        }

    # Check Redis connection
    try:
        from app.main import app
        if hasattr(app.state, 'redis'):
            start_time = time.time()
            redis_client = app.state.redis
            redis_client.ping()
            response_time_ms = int((time.time() - start_time) * 1000)

            health_status["services"]["redis"] = {
                "status": "healthy",
                "response_time_ms": response_time_ms
            }
        else:
            health_status["status"] = "degraded"
            health_status["services"]["redis"] = {
                "status": "unavailable",
                "message": "Redis client not initialized"
            }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["services"]["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }

    # Add user information to response
    health_status["authenticated_user"] = current_user.email if current_user else "anonymous"

    return health_status


@router.get("/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """
    Kubernetes readiness probe endpoint.
    Returns 200 if application is ready to serve traffic, 503 otherwise.
    """
    try:
        # Check database connectivity
        await db.execute(text("SELECT 1"))

        # Check Ollama connectivity
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Ollama service not ready"
                )

        return {"status": "ready"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service not ready: {str(e)}"
        )


@router.get("/health/live")
async def liveness_check():
    """
    Kubernetes liveness probe endpoint.
    Returns 200 if application is alive (even if not fully ready).
    """
    return {"status": "alive"}
