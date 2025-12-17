"""
OpenAI GPT LLM provider implementation.

TERTIARY provider for VAUCDA with API-based GPT access.
Supports GPT-4o, GPT-4 Turbo, GPT-3.5 Turbo.
"""

import openai
import logging
from typing import AsyncIterator, Dict, Optional
from datetime import datetime

from llm.base import (
    LLMProvider,
    LLMResponse,
    StreamChunk,
    ModelInfo,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider implementation."""

    SUPPORTED_MODELS = {
        "gpt-4o": {
            "context_window": 128000,
            "max_tokens": 16384,
            "capabilities": ["completion", "chat", "streaming", "vision", "function_calling"],
            "pricing": {"input": 0.0025, "output": 0.01},  # per 1K tokens
        },
        "gpt-4o-mini": {
            "context_window": 128000,
            "max_tokens": 16384,
            "capabilities": ["completion", "chat", "streaming", "vision", "function_calling"],
            "pricing": {"input": 0.00015, "output": 0.0006},
        },
        "gpt-4-turbo": {
            "context_window": 128000,
            "max_tokens": 4096,
            "capabilities": ["completion", "chat", "streaming", "vision", "function_calling"],
            "pricing": {"input": 0.01, "output": 0.03},
        },
        "gpt-4": {
            "context_window": 8192,
            "max_tokens": 4096,
            "capabilities": ["completion", "chat", "streaming", "function_calling"],
            "pricing": {"input": 0.03, "output": 0.06},
        },
        "gpt-3.5-turbo": {
            "context_window": 16385,
            "max_tokens": 4096,
            "capabilities": ["completion", "chat", "streaming", "function_calling"],
            "pricing": {"input": 0.0005, "output": 0.0015},
        },
    }

    def __init__(self, config: Dict):
        """
        Initialize OpenAI provider.

        Args:
            config: Configuration dict with:
                - api_key: OpenAI API key (required)
                - model: Model name (default: gpt-4o)
                - timeout: Request timeout in seconds (default: 120)
                - organization: OpenAI organization ID (optional)
        """
        super().__init__(config)

        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("OpenAI API key is required")

        self.client = openai.AsyncOpenAI(
            api_key=api_key,
            organization=config.get("organization"),
            timeout=config.get("timeout", 120),
        )
        self.model = config.get("model", "gpt-4o")
        self.timeout = config.get("timeout", 120)

        if self.model not in self.SUPPORTED_MODELS:
            logger.warning(
                f"Model {self.model} not in supported list. "
                f"Supported: {list(self.SUPPORTED_MODELS.keys())}"
            )

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate completion using OpenAI API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional OpenAI parameters

        Returns:
            LLMResponse with generated content
        """
        start_time = datetime.now()

        try:
            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Call OpenAI API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            # Extract content
            content = response.choices[0].message.content or ""

            # Calculate tokens used
            tokens_used = response.usage.total_tokens

            duration = (datetime.now() - start_time).total_seconds()

            return LLMResponse(
                content=content,
                model=response.model,
                provider="openai",
                tokens_used=tokens_used,
                finish_reason=response.choices[0].finish_reason,
                metadata={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "duration_seconds": duration,
                    "response_id": response.id,
                },
            )

        except openai.RateLimitError as e:
            raise LLMRateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
        except openai.APITimeoutError as e:
            raise LLMTimeoutError(f"OpenAI request timed out: {str(e)}")
        except openai.APIError as e:
            raise LLMProviderError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            logger.error(f"OpenAI generation error: {str(e)}")
            raise LLMProviderError(f"OpenAI generation failed: {str(e)}")

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Generate completion with streaming using OpenAI API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional OpenAI parameters

        Yields:
            StreamChunk objects as they are generated
        """
        try:
            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Stream from OpenAI API
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs
            )

            async for chunk in stream:
                if chunk.choices:
                    choice = chunk.choices[0]

                    # Check if this is the final chunk
                    is_final = choice.finish_reason is not None

                    # Extract content delta
                    content = ""
                    if choice.delta and choice.delta.content:
                        content = choice.delta.content

                    metadata = {}
                    if is_final:
                        metadata["finish_reason"] = choice.finish_reason

                    yield StreamChunk(
                        content=content,
                        is_final=is_final,
                        metadata=metadata,
                    )

                    if is_final:
                        break

        except openai.RateLimitError as e:
            raise LLMRateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
        except openai.APITimeoutError as e:
            raise LLMTimeoutError(f"OpenAI streaming request timed out: {str(e)}")
        except openai.APIError as e:
            raise LLMProviderError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            logger.error(f"OpenAI streaming error: {str(e)}")
            raise LLMProviderError(f"OpenAI streaming failed: {str(e)}")

    def get_model_info(self) -> ModelInfo:
        """
        Get information about the current GPT model.

        Returns:
            ModelInfo object with model capabilities
        """
        model_config = self.SUPPORTED_MODELS.get(
            self.model,
            {
                "context_window": 8192,
                "max_tokens": 4096,
                "capabilities": ["completion", "chat", "streaming"],
                "pricing": {"input": 0.0025, "output": 0.01},
            }
        )

        return ModelInfo(
            name=self.model,
            provider="openai",
            context_window=model_config["context_window"],
            supports_streaming=True,
            max_tokens=model_config.get("max_tokens"),
            pricing=model_config.get("pricing"),
            capabilities=model_config["capabilities"],
        )

    async def health_check(self) -> bool:
        """
        Check if OpenAI API is accessible.

        Returns:
            True if API is accessible
        """
        try:
            # Try a minimal API call
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5,
                timeout=5,
            )
            return True
        except Exception as e:
            logger.error(f"OpenAI health check error: {str(e)}")
            return False

    def count_tokens(self, text: str) -> int:
        """
        Estimate token count using tiktoken.

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count
        """
        try:
            import tiktoken

            # Get encoding for model
            if self.model.startswith("gpt-4"):
                encoding = tiktoken.encoding_for_model("gpt-4")
            elif self.model.startswith("gpt-3.5"):
                encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
            else:
                encoding = tiktoken.get_encoding("cl100k_base")

            return len(encoding.encode(text))
        except Exception:
            # Fallback to approximation (~4 chars per token)
            return len(text) // 4
