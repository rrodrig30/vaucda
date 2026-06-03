"""
LLM Configuration Manager

Provides task-specific LLM configuration with multi-provider support.
Loads settings from user preferences database and routes calls to
the correct provider (Ollama, Anthropic, OpenAI).

Task Types:
- OCR: Document OCR processing (vision models)
- STAGE1: Initial note generation and extraction
- STAGE2: Assessment & Plan with RAG/GraphRAG retrieval

Context window (num_ctx) resolution order:
1. If the user has set a per-task num_ctx in the database, that value is used.
2. Else if the model name is in MODEL_CONTEXT_SIZES, the table value is used.
   The table holds each model's TRUE training context window (n_ctx_train),
   not a practical/throttled limit.
3. Else DEFAULT_CONTEXT_SIZE (125000) is used.

This is the single fallback chain in the system; no other code path may
silently override the resolved value before sending to the provider.
"""

import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import httpx
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.sqlite_models import UserPreferences

logger = logging.getLogger(__name__)


# Model context window sizes — TRUE training context (n_ctx_train) per model.
# Each value is the maximum input context the model was trained for, taken from
# the model's published spec / model card. The user is the source of truth at
# runtime: a per-task num_ctx column in user_preferences overrides this table.
# When the user has not set a value AND the model is not in this table, we fall
# back to DEFAULT_CONTEXT_SIZE (125000).
#
# Adding a new model: insert the model's published n_ctx_train (NOT a throttled
# value). The lookup table only documents true maxes; user choice gates runtime.
MODEL_CONTEXT_SIZES = {
    # Local models (Ollama)
    "llama3.1:8b": 131072,
    "llama3.1:70b": 131072,
    "llama3.3:70b": 131072,
    "llama3:8b": 8192,
    "llama3:70b": 8192,
    "llama4:16x17b": 131072,
    "qwen2.5:72b": 131072,
    "qwen2-math:72b": 32768,
    "qwen3-vl:32b": 131072,
    "qwen3-coder:30b": 131072,
    "qwen3-embedding:latest": 8192,
    "deepseek-r1:70b": 131072,
    "phi3:medium": 131072,
    "devstral:24b": 131072,
    "gpt-oss:latest": 131072,
    "gemma2:9b": 8192,
    "gemma2:27b": 8192,
    "medgemma1.5:latest": 131072,
    "medgemma:27b": 131072,
    "glm-ocr:latest": 8192,
    "llava:34b": 4096,
    "llava:13b": 4096,
    "mistral:7b": 32768,
    "mixtral:8x7b": 32768,
    "nomic-embed-text:latest": 8192,
    "embeddinggemma:latest": 2048,

    # Cloud models (per public specs)
    "glm-4.6:cloud": 200000,
    "gpt-oss:120b-cloud": 131072,
    "deepseek-v3.2:cloud": 131072,
    "minimax-m2:cloud": 200000,
    "minimax-m2.5:cloud": 200000,
    "qwen3.5:397b-cloud": 131072,
    "mistral-large-3:675b-cloud": 131072,
    "kimi-k2-thinking:cloud": 200000,
    "gemini-3-flash-preview:cloud": 1000000,
}

# Default context size for unknown models. Per project rules, when a model is
# not in MODEL_CONTEXT_SIZES and the user has not set a per-task num_ctx, this
# is the value used. 125000 chosen as a generous, modern default that fits most
# instruction-tuned LLMs released after 2024.
DEFAULT_CONTEXT_SIZE = 125000


def get_model_context_size(model: str) -> int:
    """
    Look up the model's TRUE training context window (n_ctx_train).

    This is ONLY the lookup-table fallback; the resolved value used at runtime
    is computed by LLMConfigManager.get_config(), which prefers the user-set
    per-task num_ctx when present.

    Args:
        model: Model name (e.g., "llama3.1:8b")

    Returns:
        Context window size in tokens (table value or DEFAULT_CONTEXT_SIZE).
    """
    # Exact match first
    if model in MODEL_CONTEXT_SIZES:
        return MODEL_CONTEXT_SIZES[model]

    # Check for partial matches (e.g., "llama3.1" matches "llama3.1:8b")
    model_lower = model.lower()
    for known_model, ctx_size in MODEL_CONTEXT_SIZES.items():
        if known_model.split(":")[0] in model_lower:
            return ctx_size

    return DEFAULT_CONTEXT_SIZE


class LLMTaskType(Enum):
    """Task types for LLM configuration routing."""
    OCR = "ocr"
    STAGE1 = "stage1"
    STAGE2 = "stage2"


class LLMProvider(Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


@dataclass
class LLMTaskConfig:
    """
    Configuration for a specific LLM task.

    Contains all parameters needed to call the LLM for a specific task type.

    num_ctx: Resolved input context window in tokens. None means "not set by
    user; downstream code should fall back to get_model_context_size(model) or
    DEFAULT_CONTEXT_SIZE." LLMConfigManager populates this from user prefs.
    """
    provider: str
    model: str
    temperature: float
    max_tokens: int

    # Input context window override (Ollama options.num_ctx). When None the
    # llm_helper / OCR layer falls back to the lookup table.
    num_ctx: Optional[int] = None

    # Stage 2 RAG/GraphRAG settings (only used for STAGE2 task)
    use_rag: bool = False
    use_graphrag: bool = False
    rag_top_k: int = 5

    # Additional parameters
    top_p: float = 0.9
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "num_ctx": self.num_ctx,
            "use_rag": self.use_rag,
            "use_graphrag": self.use_graphrag,
            "rag_top_k": self.rag_top_k,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
        }


class LLMConfigManager:
    """
    Manages task-specific LLM configurations.

    Loads user preferences from database and provides appropriate
    LLMTaskConfig for each task type (OCR, Stage 1, Stage 2).
    """

    def __init__(self, user_id: Optional[str] = None):
        """
        Initialize LLMConfigManager.

        Args:
            user_id: Optional user ID to load preferences for
        """
        self.user_id = user_id
        self._configs: Dict[LLMTaskType, LLMTaskConfig] = {}
        self._loaded = False

    async def load_from_database(self, db: AsyncSession) -> None:
        """
        Load LLM configurations from user preferences in database.

        Args:
            db: Async database session
        """
        if not self.user_id:
            logger.debug("No user_id provided, using environment defaults")
            self._load_from_environment()
            self._loaded = True
            return

        try:
            stmt = select(UserPreferences).where(
                UserPreferences.user_id == self.user_id
            )
            result = await db.execute(stmt)
            prefs = result.scalars().first()

            if not prefs:
                logger.info(f"No preferences found for user {self.user_id}, using defaults")
                self._load_from_environment()
            else:
                self._load_from_preferences(prefs)
                logger.info(f"Loaded LLM configs for user {self.user_id}")

            self._loaded = True

        except Exception as e:
            logger.error(f"Failed to load LLM configs from database: {e}")
            self._load_from_environment()
            self._loaded = True

    def _load_from_preferences(self, prefs: UserPreferences) -> None:
        """
        Load configurations from UserPreferences object.

        Args:
            prefs: UserPreferences database object
        """
        # IMPORTANT: Use explicit None checks, NOT 'or' operator
        # The 'or' operator would cause fallback for empty strings or zero values

        # OCR Configuration
        # num_ctx: pass user value through if set; else None so llm_helper /
        # OCR service falls back to get_model_context_size().
        self._configs[LLMTaskType.OCR] = LLMTaskConfig(
            provider=prefs.ocr_llm_provider if prefs.ocr_llm_provider is not None else "ollama",
            model=prefs.ocr_llm_model if prefs.ocr_llm_model is not None else settings.OCR_MODEL,
            temperature=prefs.ocr_llm_temperature if prefs.ocr_llm_temperature is not None else 0.1,
            max_tokens=prefs.ocr_llm_max_tokens if prefs.ocr_llm_max_tokens is not None else 4096,
            num_ctx=prefs.ocr_llm_num_ctx if prefs.ocr_llm_num_ctx is not None else None,
        )

        # Stage 1 Configuration
        self._configs[LLMTaskType.STAGE1] = LLMTaskConfig(
            provider=prefs.stage1_llm_provider if prefs.stage1_llm_provider is not None else "ollama",
            model=prefs.stage1_llm_model if prefs.stage1_llm_model is not None else settings.OLLAMA_DEFAULT_MODEL,
            temperature=prefs.stage1_llm_temperature if prefs.stage1_llm_temperature is not None else 0.1,
            max_tokens=prefs.stage1_llm_max_tokens if prefs.stage1_llm_max_tokens is not None else 8192,
            num_ctx=prefs.stage1_llm_num_ctx if prefs.stage1_llm_num_ctx is not None else None,
        )

        # Stage 2 Configuration (with RAG/GraphRAG settings)
        self._configs[LLMTaskType.STAGE2] = LLMTaskConfig(
            provider=prefs.stage2_llm_provider if prefs.stage2_llm_provider is not None else "ollama",
            model=prefs.stage2_llm_model if prefs.stage2_llm_model is not None else settings.OLLAMA_DEFAULT_MODEL,
            temperature=prefs.stage2_llm_temperature if prefs.stage2_llm_temperature is not None else 0.0,
            max_tokens=prefs.stage2_llm_max_tokens if prefs.stage2_llm_max_tokens is not None else 8192,
            num_ctx=prefs.stage2_llm_num_ctx if prefs.stage2_llm_num_ctx is not None else None,
            use_rag=prefs.stage2_use_rag if prefs.stage2_use_rag is not None else True,
            use_graphrag=prefs.stage2_use_graphrag if prefs.stage2_use_graphrag is not None else True,
            rag_top_k=prefs.stage2_rag_top_k if prefs.stage2_rag_top_k is not None else 5,
        )

    def _load_from_environment(self) -> None:
        """Load default configurations from environment settings."""
        # OCR Configuration (from environment)
        self._configs[LLMTaskType.OCR] = LLMTaskConfig(
            provider="ollama",
            model=settings.OCR_MODEL,
            temperature=0.1,
            max_tokens=4096,
        )

        # Stage 1 Configuration (from environment)
        self._configs[LLMTaskType.STAGE1] = LLMTaskConfig(
            provider="ollama",
            model=settings.OLLAMA_DEFAULT_MODEL,
            temperature=0.1,
            max_tokens=settings.OLLAMA_MAX_TOKENS,
        )

        # Stage 2 Configuration (from environment, with RAG enabled by default)
        self._configs[LLMTaskType.STAGE2] = LLMTaskConfig(
            provider="ollama",
            model=settings.OLLAMA_DEFAULT_MODEL,
            temperature=0.0,  # Zero temperature for deterministic clinical output
            max_tokens=settings.OLLAMA_MAX_TOKENS,
            use_rag=True,
            use_graphrag=True,
            rag_top_k=settings.VECTOR_SEARCH_TOP_K,
        )

    def get_config(self, task_type: LLMTaskType) -> LLMTaskConfig:
        """
        Get configuration for a specific task type.

        Args:
            task_type: The LLM task type (OCR, STAGE1, STAGE2)

        Returns:
            LLMTaskConfig for the specified task

        Raises:
            ValueError: If config not loaded or invalid task type
        """
        if not self._loaded:
            logger.warning("LLMConfigManager not loaded, using environment defaults")
            self._load_from_environment()
            self._loaded = True

        if task_type not in self._configs:
            raise ValueError(f"Unknown task type: {task_type}")

        return self._configs[task_type]

    @property
    def ocr_config(self) -> LLMTaskConfig:
        """Get OCR task configuration."""
        return self.get_config(LLMTaskType.OCR)

    @property
    def stage1_config(self) -> LLMTaskConfig:
        """Get Stage 1 task configuration."""
        return self.get_config(LLMTaskType.STAGE1)

    @property
    def stage2_config(self) -> LLMTaskConfig:
        """Get Stage 2 task configuration."""
        return self.get_config(LLMTaskType.STAGE2)


class MultiProviderLLMClient:
    """
    Multi-provider LLM client that routes calls to the configured provider.

    Supports Ollama, Anthropic Claude, and OpenAI GPT.
    """

    def __init__(self):
        """Initialize multi-provider client."""
        self.ollama_base_url = settings.OLLAMA_BASE_URL
        self.ollama_timeout = settings.OLLAMA_TIMEOUT

        # Optional providers
        self.anthropic_api_key = settings.ANTHROPIC_API_KEY
        self.anthropic_timeout = settings.ANTHROPIC_TIMEOUT

        self.openai_api_key = settings.OPENAI_API_KEY
        self.openai_timeout = settings.OPENAI_TIMEOUT

    async def generate(
        self,
        prompt: str,
        config: LLMTaskConfig,
        system_prompt: Optional[str] = None,
        images: Optional[list] = None
    ) -> str:
        """
        Generate text using the configured provider.

        Args:
            prompt: Input prompt
            config: LLMTaskConfig with provider and model settings
            system_prompt: Optional system prompt
            images: Optional list of base64-encoded images (for vision models)

        Returns:
            Generated text response

        Raises:
            RuntimeError: If provider fails or is not configured
        """
        provider = config.provider.lower()

        if provider == LLMProvider.OLLAMA.value:
            return await self._call_ollama(prompt, config, system_prompt, images)
        elif provider == LLMProvider.ANTHROPIC.value:
            return await self._call_anthropic(prompt, config, system_prompt, images)
        elif provider == LLMProvider.OPENAI.value:
            return await self._call_openai(prompt, config, system_prompt, images)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    async def _call_ollama(
        self,
        prompt: str,
        config: LLMTaskConfig,
        system_prompt: Optional[str] = None,
        images: Optional[list] = None
    ) -> str:
        """Call Ollama API."""
        if not self.ollama_base_url:
            raise RuntimeError("OLLAMA_BASE_URL not configured")

        # Resolve context window using the documented order:
        # user-set config.num_ctx -> lookup table -> DEFAULT_CONTEXT_SIZE.
        num_ctx = config.num_ctx if config.num_ctx is not None else get_model_context_size(config.model)
        logger.info(
            f"Setting num_ctx={num_ctx} for model {config.model} "
            f"(source={'user' if config.num_ctx is not None else 'lookup'})"
        )

        payload = {
            "model": config.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature": config.temperature,
                "num_predict": config.max_tokens,
                "num_ctx": num_ctx,  # CRITICAL: Set full context window
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        if images:
            payload["images"] = images

        try:
            async with httpx.AsyncClient(timeout=self.ollama_timeout) as client:
                response = await client.post(
                    f"{self.ollama_base_url}/api/generate",
                    json=payload
                )
                response.raise_for_status()

                result = response.json()
                return result.get("response", "").strip()

        except httpx.TimeoutException:
            logger.error(f"Ollama timeout after {self.ollama_timeout}s for model {config.model}")
            raise RuntimeError(f"Ollama timeout for model {config.model}")
        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            raise RuntimeError(f"Ollama call failed: {e}")

    async def _call_anthropic(
        self,
        prompt: str,
        config: LLMTaskConfig,
        system_prompt: Optional[str] = None,
        images: Optional[list] = None
    ) -> str:
        """Call Anthropic Claude API."""
        if not self.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")

        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Build messages
        messages = []

        # Handle images for vision models
        if images:
            content = []
            for img_b64 in images:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64,
                    }
                })
            content.append({"type": "text", "text": prompt})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": prompt})

        payload = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "messages": messages,
        }

        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self.anthropic_timeout) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()

                result = response.json()
                # Extract text from content blocks
                content = result.get("content", [])
                text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                return "".join(text_parts).strip()

        except httpx.TimeoutException:
            logger.error(f"Anthropic timeout after {self.anthropic_timeout}s")
            raise RuntimeError(f"Anthropic timeout for model {config.model}")
        except Exception as e:
            logger.error(f"Anthropic call failed: {e}")
            raise RuntimeError(f"Anthropic call failed: {e}")

    async def _call_openai(
        self,
        prompt: str,
        config: LLMTaskConfig,
        system_prompt: Optional[str] = None,
        images: Optional[list] = None
    ) -> str:
        """Call OpenAI API."""
        if not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not configured")

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }

        # Build messages
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Handle images for vision models
        if images:
            content = []
            for img_b64 in images:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                })
            content.append({"type": "text", "text": prompt})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": prompt})

        payload = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "messages": messages,
        }

        try:
            async with httpx.AsyncClient(timeout=self.openai_timeout) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()

                result = response.json()
                choices = result.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
                return ""

        except httpx.TimeoutException:
            logger.error(f"OpenAI timeout after {self.openai_timeout}s")
            raise RuntimeError(f"OpenAI timeout for model {config.model}")
        except Exception as e:
            logger.error(f"OpenAI call failed: {e}")
            raise RuntimeError(f"OpenAI call failed: {e}")


# Global multi-provider client instance
multi_provider_client = MultiProviderLLMClient()


async def synthesize_with_config(
    prompt: str,
    config: LLMTaskConfig,
    system_prompt: Optional[str] = None,
    images: Optional[list] = None
) -> str:
    """
    Convenience function to synthesize text using task-specific config.

    Args:
        prompt: Input prompt
        config: LLMTaskConfig with provider and model settings
        system_prompt: Optional system prompt
        images: Optional list of base64-encoded images

    Returns:
        Generated text response
    """
    return await multi_provider_client.generate(
        prompt=prompt,
        config=config,
        system_prompt=system_prompt,
        images=images
    )
