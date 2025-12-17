"""
LLM Provider API endpoints
Manages LLM providers and models
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging
import aiohttp

from app.core.security import get_optional_user
from app.database.sqlite_models import User
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# Response Models
class LLMModel(BaseModel):
    """LLM model information."""
    name: str = Field(..., description="Model name")
    size: Optional[int] = Field(None, description="Model size in bytes")
    modified_at: Optional[str] = Field(None, description="Last modification timestamp")
    digest: Optional[str] = Field(None, description="Model digest/hash")
    family: Optional[str] = Field(None, description="Model family (e.g., llama, phi)")
    parameter_size: Optional[str] = Field(None, description="Parameter size (e.g., 8B, 70B)")
    quantization: Optional[str] = Field(None, description="Quantization level")


class LLMProvider(BaseModel):
    """LLM provider information."""
    name: str = Field(..., description="Provider name")
    display_name: str = Field(..., description="Display name")
    enabled: bool = Field(..., description="Whether provider is enabled")
    available: bool = Field(..., description="Whether provider is available/reachable")
    models: List[LLMModel] = Field(default_factory=list, description="Available models")
    default_model: Optional[str] = Field(None, description="Default model for this provider")


class ProvidersResponse(BaseModel):
    """Response with all providers."""
    providers: List[LLMProvider]


class OllamaModelsResponse(BaseModel):
    """Response with Ollama models."""
    models: List[LLMModel]


@router.get("/providers", response_model=ProvidersResponse)
async def get_providers(
    current_user: Optional[User] = Depends(get_optional_user)
):
    """
    Get all LLM providers and their status.

    Returns information about available LLM providers (Ollama, Anthropic, OpenAI),
    including which ones are enabled, available, and what models they have.

    Works without authentication (read-only endpoint).
    """
    try:
        providers = []

        # Ollama Provider
        ollama_models = []
        ollama_available = False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{settings.OLLAMA_BASE_URL}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        ollama_available = True

                        for model in data.get("models", []):
                            # Parse model name to extract details
                            model_name = model.get("name", "")
                            size = model.get("size", 0)

                            # Extract parameter size from name (e.g., llama3.1:70b -> 70B)
                            param_size = None
                            if ":" in model_name:
                                tag = model_name.split(":")[-1]
                                if tag.replace("b", "").replace("B", "").isdigit():
                                    param_size = tag.upper() if not tag.upper().endswith("B") else tag.upper()

                            ollama_models.append(LLMModel(
                                name=model_name,
                                size=size,
                                modified_at=model.get("modified_at"),
                                digest=model.get("digest"),
                                family=model.get("details", {}).get("family"),
                                parameter_size=param_size,
                                quantization=model.get("details", {}).get("quantization_level")
                            ))
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")

        providers.append(LLMProvider(
            name="ollama",
            display_name="Ollama (Local)",
            enabled=True,
            available=ollama_available,
            models=ollama_models,
            default_model=settings.OLLAMA_DEFAULT_MODEL
        ))

        # Anthropic Provider
        anthropic_enabled = bool(settings.ANTHROPIC_API_KEY)
        anthropic_models = []
        if anthropic_enabled:
            # List known Anthropic models
            anthropic_models = [
                LLMModel(
                    name="claude-3-5-sonnet-20250101",
                    parameter_size="N/A",
                ),
                LLMModel(
                    name="claude-3-5-haiku-20250101",
                    parameter_size="N/A",
                ),
                LLMModel(
                    name="claude-3-opus-20240229",
                    parameter_size="N/A",
                ),
            ]

        providers.append(LLMProvider(
            name="anthropic",
            display_name="Anthropic Claude",
            enabled=anthropic_enabled,
            available=anthropic_enabled,  # If key is set, assume available
            models=anthropic_models,
            default_model=settings.ANTHROPIC_DEFAULT_MODEL if anthropic_enabled else None
        ))

        # OpenAI Provider
        openai_enabled = bool(settings.OPENAI_API_KEY)
        openai_models = []
        if openai_enabled:
            # List known OpenAI models
            openai_models = [
                LLMModel(
                    name="gpt-4o",
                    parameter_size="N/A",
                ),
                LLMModel(
                    name="gpt-4o-mini",
                    parameter_size="N/A",
                ),
                LLMModel(
                    name="gpt-4-turbo",
                    parameter_size="N/A",
                ),
            ]

        providers.append(LLMProvider(
            name="openai",
            display_name="OpenAI GPT",
            enabled=openai_enabled,
            available=openai_enabled,  # If key is set, assume available
            models=openai_models,
            default_model=settings.OPENAI_DEFAULT_MODEL if openai_enabled else None
        ))

        user_info = f"user {current_user.user_id}" if current_user else "anonymous user"
        logger.info(f"Retrieved {len(providers)} LLM providers for {user_info}")

        return ProvidersResponse(providers=providers)

    except Exception as e:
        logger.error(f"Error getting LLM providers: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get LLM providers: {str(e)}"
        )


@router.get("/ollama/models", response_model=OllamaModelsResponse)
async def get_ollama_models(
    current_user: Optional[User] = Depends(get_optional_user)
):
    """
    Get available Ollama models.

    Queries the local Ollama server for all installed models and returns
    detailed information about each one.
    """
    try:
        models = []

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{settings.OLLAMA_BASE_URL}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status != 200:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Ollama service unavailable"
                    )

                data = await response.json()

                for model in data.get("models", []):
                    model_name = model.get("name", "")
                    size = model.get("size", 0)

                    # Extract parameter size from name
                    param_size = None
                    if ":" in model_name:
                        tag = model_name.split(":")[-1]
                        if tag.replace("b", "").replace("B", "").isdigit():
                            param_size = tag.upper() if not tag.upper().endswith("B") else tag.upper()

                    models.append(LLMModel(
                        name=model_name,
                        size=size,
                        modified_at=model.get("modified_at"),
                        digest=model.get("digest"),
                        family=model.get("details", {}).get("family"),
                        parameter_size=param_size,
                        quantization=model.get("details", {}).get("quantization_level")
                    ))

        logger.info(f"Retrieved {len(models)} Ollama models for user {current_user.user_id}")

        return OllamaModelsResponse(models=models)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Ollama models: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get Ollama models: {str(e)}"
        )
