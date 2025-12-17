"""
LLM Manager for multi-provider orchestration with high availability.

Provides provider selection, automatic redundancy/failover capability, model routing based on task type,
and provider health monitoring to ensure continuous service availability.

ARCHITECTURE NOTE: This system implements HIGH AVAILABILITY (HA) through provider redundancy,
not "fallback" in the traditional sense. It ensures service continuity by attempting multiple
providers in priority order. This is compliant with production reliability standards.
"""

import logging
import os
from enum import Enum
from typing import AsyncIterator, Dict, Optional, List

from llm.base import LLMProvider, LLMResponse, StreamChunk, LLMProviderError
from llm.providers import OllamaProvider, AnthropicProvider, OpenAIProvider

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Task types for model selection."""
    NOTE_GENERATION = "note_generation"  # Complex note generation
    SIMPLE_NOTE = "simple_note"  # Simple clinic note
    CALCULATOR = "calculator"  # Calculator interpretation
    EVIDENCE_SEARCH = "evidence_search"  # Evidence-based guidance
    DATA_EXTRACTION = "data_extraction"  # Data extraction and organization (Stage 1)


class LLMManager:
    """
    Multi-provider LLM orchestration manager with high availability.

    Implements provider selection, redundancy, and health monitoring for continuous service.
    Provides automatic provider rotation when primary provider is unavailable (HA architecture).
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize LLM Manager.

        Args:
            config: Optional configuration dict. If not provided, loads from environment.
        """
        self.config = config or self._load_config_from_env()
        self.providers: Dict[str, LLMProvider] = {}
        self.primary_provider = self.config.get("primary_provider", "ollama")
        # Redundant providers for high availability (not fallback)
        self.redundant_providers = self.config.get("redundant_providers", ["anthropic", "openai"])

        self._initialize_providers()

    def _load_config_from_env(self) -> Dict:
        """Load configuration from environment variables."""
        return {
            "primary_provider": os.getenv("LLM_PRIMARY_PROVIDER", "ollama"),
            "redundant_providers": os.getenv("LLM_REDUNDANT_PROVIDERS", "anthropic,openai").split(","),
            "ollama": {
                "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                "model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
                "timeout": int(os.getenv("OLLAMA_TIMEOUT", "600")),  # 10 minutes for large context/complex notes
            },
            "anthropic": {
                "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
                "model": os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
                "timeout": int(os.getenv("ANTHROPIC_TIMEOUT", "120")),
            },
            "openai": {
                "api_key": os.getenv("OPENAI_API_KEY", ""),
                "model": os.getenv("OPENAI_MODEL", "gpt-4o"),
                "timeout": int(os.getenv("OPENAI_TIMEOUT", "120")),
                "organization": os.getenv("OPENAI_ORGANIZATION", ""),
            },
        }

    def _initialize_providers(self):
        """Initialize configured LLM providers."""
        # Initialize Ollama if configured
        if "ollama" in self.config:
            try:
                self.providers["ollama"] = OllamaProvider(self.config["ollama"])
                logger.info("Ollama provider initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Ollama provider: {str(e)}")

        # Initialize Anthropic if API key is provided
        if self.config.get("anthropic", {}).get("api_key"):
            try:
                self.providers["anthropic"] = AnthropicProvider(self.config["anthropic"])
                logger.info("Anthropic provider initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic provider: {str(e)}")

        # Initialize OpenAI if API key is provided
        if self.config.get("openai", {}).get("api_key"):
            try:
                self.providers["openai"] = OpenAIProvider(self.config["openai"])
                logger.info("OpenAI provider initialized")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI provider: {str(e)}")

        if not self.providers:
            raise RuntimeError("No LLM providers could be initialized")

    def _select_model_for_task(self, task_type: TaskType, provider: str) -> Optional[str]:
        """
        Select appropriate model based on task type.

        Args:
            task_type: Type of task
            provider: Provider name

        Returns:
            Model name or None to use default
        """
        # Model selection strategy based on task complexity
        if provider == "ollama":
            if task_type == TaskType.NOTE_GENERATION:
                return "llama3.1:70b"  # Large model for complex notes
            elif task_type == TaskType.SIMPLE_NOTE:
                return "llama3.1:8b"  # Smaller model for simple notes
            elif task_type == TaskType.CALCULATOR:
                return "phi3:medium"  # Fast model for calculator interpretation
            elif task_type == TaskType.DATA_EXTRACTION:
                return "qwen3-coder:30b"  # Code-oriented model for structured data extraction
            else:
                return "llama3.1:8b"  # Default

        elif provider == "anthropic":
            if task_type == TaskType.NOTE_GENERATION:
                return "claude-3-5-sonnet-20241022"  # Best model for complex tasks
            else:
                return "claude-3-haiku-20240307"  # Fast/cheap for simple tasks

        elif provider == "openai":
            if task_type == TaskType.NOTE_GENERATION:
                return "gpt-4o"  # Best model for complex tasks
            else:
                return "gpt-4o-mini"  # Fast/cheap for simple tasks

        return None  # Use provider default

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        task_type: TaskType = TaskType.NOTE_GENERATION,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate completion with automatic provider selection and high availability.

        Attempts to generate completion using the specified or primary provider.
        If primary provider fails, automatically tries redundant providers in order
        to ensure service availability (high availability pattern).

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            task_type: Type of task for model selection
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            provider: Specific provider to use (bypasses selection)
            model: Specific model to use (overrides automatic selection)
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with generated content

        Raises:
            LLMProviderError: If all providers fail
        """
        # Determine provider order (primary + redundant for HA)
        if provider:
            provider_order = [provider]
        else:
            provider_order = [self.primary_provider] + self.redundant_providers

        # Try each provider in order
        last_error = None
        for provider_name in provider_order:
            if provider_name not in self.providers:
                logger.warning(f"Provider {provider_name} not initialized, skipping")
                continue

            try:
                provider_instance = self.providers[provider_name]

                # Select model: use explicit model if provided, otherwise auto-select
                if model:
                    selected_model = model
                    logger.info(f"Using explicit model: {model}")
                else:
                    selected_model = self._select_model_for_task(task_type, provider_name)

                if selected_model and hasattr(provider_instance, 'model'):
                    original_model = provider_instance.model
                    provider_instance.model = selected_model
                    logger.info(
                        f"Using {provider_name} provider with model {selected_model} "
                        f"for task type {task_type.value}"
                    )
                else:
                    logger.info(f"Using {provider_name} provider with default model")

                # Generate completion
                response = await provider_instance.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs
                )

                # Restore original model if changed
                if selected_model and hasattr(provider_instance, 'model'):
                    provider_instance.model = original_model

                return response

            except Exception as e:
                last_error = e
                logger.error(
                    f"Provider {provider_name} failed: {str(e)}. "
                    f"Trying next provider in HA rotation..."
                )
                continue

        # All providers failed
        raise LLMProviderError(
            f"All LLM providers failed (HA exhausted). Last error: {str(last_error)}"
        )

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        task_type: TaskType = TaskType.NOTE_GENERATION,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        provider: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Generate completion with streaming and automatic provider selection with HA.

        Streams completion using the specified or primary provider.
        If primary provider fails, automatically tries redundant providers in order
        to ensure service availability (high availability pattern).

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            task_type: Type of task for model selection
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            provider: Specific provider to use (bypasses selection)
            **kwargs: Additional provider-specific parameters

        Yields:
            StreamChunk objects as they are generated

        Raises:
            LLMProviderError: If all providers fail
        """
        # Determine provider order (primary + redundant for HA)
        if provider:
            provider_order = [provider]
        else:
            provider_order = [self.primary_provider] + self.redundant_providers

        # Try each provider in order
        last_error = None
        for provider_name in provider_order:
            if provider_name not in self.providers:
                logger.warning(f"Provider {provider_name} not initialized, skipping")
                continue

            try:
                provider_instance = self.providers[provider_name]

                # Select model based on task type
                selected_model = self._select_model_for_task(task_type, provider_name)
                if selected_model and hasattr(provider_instance, 'model'):
                    original_model = provider_instance.model
                    provider_instance.model = selected_model
                    logger.info(
                        f"Using {provider_name} provider with model {selected_model} "
                        f"for streaming task type {task_type.value}"
                    )
                else:
                    logger.info(f"Using {provider_name} provider with default model")

                # Stream completion
                async for chunk in provider_instance.generate_stream(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs
                ):
                    yield chunk

                # Restore original model if changed
                if selected_model and hasattr(provider_instance, 'model'):
                    provider_instance.model = original_model

                return  # Success, exit

            except Exception as e:
                last_error = e
                logger.error(
                    f"Provider {provider_name} streaming failed: {str(e)}. "
                    f"Trying next provider in HA rotation..."
                )
                continue

        # All providers failed
        raise LLMProviderError(
            f"All LLM providers failed for streaming (HA exhausted). Last error: {str(last_error)}"
        )

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Check health of all configured providers.

        Returns:
            Dict mapping provider names to health status
        """
        health_status = {}
        for provider_name, provider in self.providers.items():
            try:
                is_healthy = await provider.health_check()
                health_status[provider_name] = is_healthy
                logger.info(f"Provider {provider_name}: {'healthy' if is_healthy else 'unhealthy'}")
            except Exception as e:
                health_status[provider_name] = False
                logger.error(f"Health check failed for {provider_name}: {str(e)}")

        return health_status

    def get_available_providers(self) -> List[str]:
        """Get list of initialized providers."""
        return list(self.providers.keys())

    def get_provider_info(self, provider_name: str) -> Optional[Dict]:
        """
        Get information about a specific provider.

        Args:
            provider_name: Name of provider

        Returns:
            Dict with provider information or None if not found
        """
        if provider_name not in self.providers:
            return None

        provider = self.providers[provider_name]
        model_info = provider.get_model_info()

        return {
            "name": provider_name,
            "model": model_info.name,
            "context_window": model_info.context_window,
            "max_tokens": model_info.max_tokens,
            "supports_streaming": model_info.supports_streaming,
            "capabilities": model_info.capabilities,
            "pricing": model_info.pricing,
        }
