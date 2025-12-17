"""
Anthropic Claude LLM provider implementation.

SECONDARY provider for VAUCDA with API-based Claude access.
Supports Claude 3.5 Sonnet, Claude 3 Opus, Claude 3 Haiku.
"""

import anthropic
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


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider implementation."""

    SUPPORTED_MODELS = {
        "claude-3-5-sonnet-20241022": {
            "context_window": 200000,
            "max_tokens": 8192,
            "capabilities": ["completion", "chat", "streaming", "vision"],
            "pricing": {"input": 0.003, "output": 0.015},  # per 1K tokens
        },
        "claude-3-opus-20240229": {
            "context_window": 200000,
            "max_tokens": 4096,
            "capabilities": ["completion", "chat", "streaming", "vision"],
            "pricing": {"input": 0.015, "output": 0.075},
        },
        "claude-3-haiku-20240307": {
            "context_window": 200000,
            "max_tokens": 4096,
            "capabilities": ["completion", "chat", "streaming", "vision"],
            "pricing": {"input": 0.00025, "output": 0.00125},
        },
        "claude-3-sonnet-20240229": {
            "context_window": 200000,
            "max_tokens": 4096,
            "capabilities": ["completion", "chat", "streaming", "vision"],
            "pricing": {"input": 0.003, "output": 0.015},
        },
    }

    def __init__(self, config: Dict):
        """
        Initialize Anthropic provider.

        Args:
            config: Configuration dict with:
                - api_key: Anthropic API key (required)
                - model: Model name (default: claude-3-5-sonnet-20241022)
                - timeout: Request timeout in seconds (default: 120)
        """
        super().__init__(config)

        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("Anthropic API key is required")

        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = config.get("model", "claude-3-5-sonnet-20241022")
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
        Generate completion using Anthropic API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate (default: 4096)
            **kwargs: Additional Anthropic parameters

        Returns:
            LLMResponse with generated content
        """
        start_time = datetime.now()

        # Default max_tokens if not specified
        if max_tokens is None:
            max_tokens = 4096

        try:
            # Build message
            messages = [{"role": "user", "content": prompt}]

            # Call Anthropic API
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt if system_prompt else anthropic.NOT_GIVEN,
                messages=messages,
                timeout=self.timeout,
                **kwargs
            )

            # Extract content
            content = ""
            for block in response.content:
                if block.type == "text":
                    content += block.text

            # Calculate tokens used
            tokens_used = response.usage.input_tokens + response.usage.output_tokens

            duration = (datetime.now() - start_time).total_seconds()

            return LLMResponse(
                content=content,
                model=response.model,
                provider="anthropic",
                tokens_used=tokens_used,
                finish_reason=response.stop_reason,
                metadata={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "duration_seconds": duration,
                    "response_id": response.id,
                },
            )

        except anthropic.RateLimitError as e:
            raise LLMRateLimitError(f"Anthropic rate limit exceeded: {str(e)}")
        except anthropic.APITimeoutError as e:
            raise LLMTimeoutError(f"Anthropic request timed out: {str(e)}")
        except anthropic.APIError as e:
            raise LLMProviderError(f"Anthropic API error: {str(e)}")
        except Exception as e:
            logger.error(f"Anthropic generation error: {str(e)}")
            raise LLMProviderError(f"Anthropic generation failed: {str(e)}")

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Generate completion with streaming using Anthropic API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate (default: 4096)
            **kwargs: Additional Anthropic parameters

        Yields:
            StreamChunk objects as they are generated
        """
        # Default max_tokens if not specified
        if max_tokens is None:
            max_tokens = 4096

        try:
            # Build message
            messages = [{"role": "user", "content": prompt}]

            # Stream from Anthropic API
            async with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt if system_prompt else anthropic.NOT_GIVEN,
                messages=messages,
                timeout=self.timeout,
                **kwargs
            ) as stream:
                async for event in stream:
                    # Handle different event types
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            yield StreamChunk(
                                content=event.delta.text,
                                is_final=False,
                            )

                    elif event.type == "message_stop":
                        # Final chunk with metadata
                        message = await stream.get_final_message()
                        yield StreamChunk(
                            content="",
                            is_final=True,
                            metadata={
                                "input_tokens": message.usage.input_tokens,
                                "output_tokens": message.usage.output_tokens,
                                "stop_reason": message.stop_reason,
                            },
                        )

        except anthropic.RateLimitError as e:
            raise LLMRateLimitError(f"Anthropic rate limit exceeded: {str(e)}")
        except anthropic.APITimeoutError as e:
            raise LLMTimeoutError(f"Anthropic streaming request timed out: {str(e)}")
        except anthropic.APIError as e:
            raise LLMProviderError(f"Anthropic API error: {str(e)}")
        except Exception as e:
            logger.error(f"Anthropic streaming error: {str(e)}")
            raise LLMProviderError(f"Anthropic streaming failed: {str(e)}")

    def get_model_info(self) -> ModelInfo:
        """
        Get information about the current Claude model.

        Returns:
            ModelInfo object with model capabilities
        """
        model_config = self.SUPPORTED_MODELS.get(
            self.model,
            {
                "context_window": 200000,
                "max_tokens": 4096,
                "capabilities": ["completion", "chat", "streaming"],
                "pricing": {"input": 0.003, "output": 0.015},
            }
        )

        return ModelInfo(
            name=self.model,
            provider="anthropic",
            context_window=model_config["context_window"],
            supports_streaming=True,
            max_tokens=model_config.get("max_tokens"),
            pricing=model_config.get("pricing"),
            capabilities=model_config["capabilities"],
        )

    async def health_check(self) -> bool:
        """
        Check if Anthropic API is accessible.

        Returns:
            True if API is accessible
        """
        try:
            # Try a minimal API call
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}],
                timeout=5,
            )
            return True
        except Exception as e:
            logger.error(f"Anthropic health check error: {str(e)}")
            return False

    def count_tokens(self, text: str) -> int:
        """
        Estimate token count using Claude tokenizer.

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count
        """
        # Use Anthropic's count_tokens method
        try:
            return self.client.count_tokens(text)
        except Exception:
            # Fallback to approximation (~4 chars per token)
            return len(text) // 4
