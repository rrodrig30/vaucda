"""
Base LLM provider interface for VAUCDA.

Defines abstract base class for all LLM providers with synchronous
and streaming generation capabilities.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional
from datetime import datetime


@dataclass
class LLMResponse:
    """Response from LLM generation."""

    content: str
    model: str
    provider: str
    tokens_used: Optional[int] = None
    finish_reason: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class StreamChunk:
    """Single chunk from streaming generation."""

    content: str
    is_final: bool = False
    metadata: Dict = field(default_factory=dict)


@dataclass
class ModelInfo:
    """Information about an LLM model."""

    name: str
    provider: str
    context_window: int
    supports_streaming: bool
    max_tokens: Optional[int] = None
    pricing: Optional[Dict[str, float]] = None
    capabilities: List[str] = field(default_factory=list)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: Dict):
        """
        Initialize LLM provider.

        Args:
            config: Provider-specific configuration
        """
        self.config = config
        self.provider_name = self.__class__.__name__

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate completion synchronously.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse with generated content
        """
        pass

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Generate completion with streaming.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Yields:
            StreamChunk objects as they are generated
        """
        pass

    @abstractmethod
    def get_model_info(self) -> ModelInfo:
        """
        Get information about the current model.

        Returns:
            ModelInfo object with model capabilities
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if provider is healthy and accessible.

        Returns:
            True if provider is available
        """
        pass

    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        Default implementation uses rough approximation.
        Override for provider-specific tokenization.

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count
        """
        # Rough approximation: ~4 characters per token
        return len(text) // 4


class LLMError(Exception):
    """Base exception for LLM errors."""
    pass


class LLMProviderError(LLMError):
    """Exception for provider-specific errors."""
    pass


class LLMRateLimitError(LLMError):
    """Exception for rate limit errors."""
    pass


class LLMTimeoutError(LLMError):
    """Exception for timeout errors."""
    pass
