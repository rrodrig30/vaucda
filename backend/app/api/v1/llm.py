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
from app.services.llm_config_manager import (
    MODEL_CONTEXT_SIZES,
    DEFAULT_CONTEXT_SIZE,
    get_model_context_size,
)

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


class ModelContextSizeResponse(BaseModel):
    """Response describing a model's known/default input context window."""
    model: str = Field(..., description="Model name as queried")
    context_size: int = Field(..., description="Resolved context window in tokens (table value or DEFAULT_CONTEXT_SIZE)")
    known: bool = Field(..., description="True if the model is in MODEL_CONTEXT_SIZES; False means context_size is DEFAULT_CONTEXT_SIZE")
    default_size: int = Field(..., description="The default fallback used when a model is unknown")


def is_embedding_model(model_name: str) -> bool:
    """
    Check if a model is an embedding-only model (not suitable for any generation).

    These models cannot generate text at all and should be hidden from all dropdowns.
    OCR and vision models ARE kept — they are valid choices for the OCR task dropdown.
    """
    model_lower = model_name.lower()

    exclude_patterns = [
        'embed',         # Embedding models (nomic-embed-text, etc.)
        'embedding',     # Embedding models
        'minilm',        # Embedding models (all-minilm)
        'e5-',           # Embedding models
        'bge-',          # Embedding models
        'gte-',          # Embedding models
        'clip',          # CLIP embedding models
        'whisper',       # Audio transcription models (not text generation)
    ]

    for pattern in exclude_patterns:
        if pattern in model_lower:
            return True

    return False


# ---------------------------------------------------------------------------
# Live provider model discovery — only ACTIVELY AVAILABLE models are surfaced.
# Anthropic and OpenAI each expose a keyed /v1/models endpoint; we query it with
# the configured key rather than showing a hardcoded (and quickly stale) list.
# Results are briefly cached (keyed by the key's fingerprint) to avoid hammering
# the API on the several getProviders() calls the Settings page makes.
# ---------------------------------------------------------------------------
import time

_MODEL_CACHE: Dict[str, tuple] = {}   # provider -> (expires_monotonic, key_fp, [LLMModel])
_MODEL_CACHE_TTL = 120                 # seconds

# OpenAI /models returns everything (embeddings, tts, whisper, image, …). Keep
# only chat/completion-capable families and drop non-chat modalities.
_OPENAI_CHAT_PREFIXES = ("gpt-", "chatgpt", "o1", "o3", "o4")
_OPENAI_EXCLUDE = (
    "embedding", "whisper", "tts", "dall-e", "audio", "realtime", "moderation",
    "image", "transcribe", "search", "instruct", "davinci", "babbage",
)


async def _fetch_anthropic_models(api_key: str) -> List["LLMModel"]:
    """Actively available Claude models from the Anthropic /v1/models API."""
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.anthropic.com/v1/models",
            headers=headers, params={"limit": 1000},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Anthropic /models HTTP {resp.status}")
            data = await resp.json()
    return [
        LLMModel(name=m["id"], parameter_size=m.get("display_name"))
        for m in data.get("data", []) if m.get("id")
    ]


async def _fetch_openai_models(api_key: str) -> List["LLMModel"]:
    """Actively available chat models from the OpenAI /v1/models API."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"OpenAI /models HTTP {resp.status}")
            data = await resp.json()
    ids = [
        m["id"] for m in data.get("data", []) if m.get("id")
        and any(m["id"].lower().startswith(p) for p in _OPENAI_CHAT_PREFIXES)
        and not any(x in m["id"].lower() for x in _OPENAI_EXCLUDE)
    ]
    return [LLMModel(name=i, parameter_size="N/A") for i in sorted(ids)]


async def _list_provider_models(provider: str, api_key: str) -> tuple:
    """(models, available) for a keyed cloud provider. Live-fetches the actively
    available models with a short per-key cache; returns ([], False) on any error
    (invalid key / network) so only genuinely available models are ever shown."""
    fp = api_key[-6:] if api_key else ""
    now = time.monotonic()
    cached = _MODEL_CACHE.get(provider)
    if cached and cached[0] > now and cached[1] == fp:
        return cached[2], True
    try:
        if provider == "anthropic":
            models = await _fetch_anthropic_models(api_key)
        else:
            models = await _fetch_openai_models(api_key)
        _MODEL_CACHE[provider] = (now + _MODEL_CACHE_TTL, fp, models)
        return models, True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not fetch {provider} models: {e}")
        return [], False


@router.get("/providers", response_model=ProvidersResponse)
async def get_providers(
    current_user: Optional[User] = Depends(get_optional_user)
):
    """
    Get all LLM providers and their status.

    Returns information about available LLM providers (Ollama, Anthropic, OpenAI),
    including which ones are enabled, available, and what models they have.

    Works without authentication (read-only endpoint).

    Note: Filters out non-text-generation models (OCR, embedding, etc.)
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

                            # Filter out embedding models only — keep OCR/vision models
                            # so they appear in the OCR dropdown on the Settings page
                            if is_embedding_model(model_name):
                                logger.debug(f"Filtering out embedding model: {model_name}")
                                continue

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

        # Anthropic Provider — only actively available models (live /v1/models)
        anthropic_enabled = bool(settings.ANTHROPIC_API_KEY)
        anthropic_models = []
        anthropic_available = False
        if anthropic_enabled:
            anthropic_models, anthropic_available = await _list_provider_models(
                "anthropic", settings.ANTHROPIC_API_KEY)
        anthropic_names = [m.name for m in anthropic_models]
        providers.append(LLMProvider(
            name="anthropic",
            display_name="Anthropic Claude",
            enabled=anthropic_enabled,
            available=anthropic_available,
            models=anthropic_models,
            default_model=(settings.ANTHROPIC_DEFAULT_MODEL
                           if settings.ANTHROPIC_DEFAULT_MODEL in anthropic_names
                           else (anthropic_names[0] if anthropic_names else None)),
        ))

        # OpenAI Provider — only actively available chat models (live /v1/models)
        openai_enabled = bool(settings.OPENAI_API_KEY)
        openai_models = []
        openai_available = False
        if openai_enabled:
            openai_models, openai_available = await _list_provider_models(
                "openai", settings.OPENAI_API_KEY)
        openai_names = [m.name for m in openai_models]
        providers.append(LLMProvider(
            name="openai",
            display_name="OpenAI GPT",
            enabled=openai_enabled,
            available=openai_available,
            models=openai_models,
            default_model=(settings.OPENAI_DEFAULT_MODEL
                           if settings.OPENAI_DEFAULT_MODEL in openai_names
                           else (openai_names[0] if openai_names else None)),
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
    Get available Ollama models for text generation.

    Queries the local Ollama server for all installed models and returns
    detailed information about each one.

    Note: Filters out non-text-generation models (OCR, embedding, etc.)
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

                    # Filter out non-text-generation models
                    if not is_text_generation_model(model_name):
                        continue

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

        user_id = current_user.user_id if current_user else "anonymous"
        logger.info(f"Retrieved {len(models)} Ollama models for user {user_id}")

        return OllamaModelsResponse(models=models)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Ollama models: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get Ollama models: {str(e)}"
        )


@router.get("/model-context-size", response_model=ModelContextSizeResponse)
async def get_model_context_size_endpoint(
    model: str,
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Look up the published training context window (n_ctx_train) for a model.

    Used by the Settings UI to populate the per-task num_ctx input when the
    user picks a model. Returns:
      - context_size: lookup-table value if the model is known, else DEFAULT_CONTEXT_SIZE
      - known: True iff the model is in MODEL_CONTEXT_SIZES (exact or family match)
      - default_size: the unknown-model fallback (informational)

    This endpoint does NOT consult user preferences. The frontend uses the
    return value as a default that can be overridden by the user's input.
    """
    if not model or not model.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'model' is required"
        )

    model_name = model.strip()
    # 'known' must reflect whether the lookup succeeded, not just exact match
    resolved = get_model_context_size(model_name)
    is_known = resolved != DEFAULT_CONTEXT_SIZE or model_name in MODEL_CONTEXT_SIZES

    user_info = current_user.user_id if current_user else "anonymous"
    logger.info(
        f"Model context size lookup for '{model_name}' -> "
        f"{resolved} (known={is_known}) by {user_info}"
    )

    return ModelContextSizeResponse(
        model=model_name,
        context_size=resolved,
        known=is_known,
        default_size=DEFAULT_CONTEXT_SIZE,
    )
