"""
Ollama LLM provider implementation.

PRIMARY provider for VAUCDA with local model support.
Supports llama3.1:70b, llama3.1:8b, phi3:medium, and other Ollama models.
"""

import aiohttp
import asyncio
import json
import logging
from typing import AsyncIterator, Dict, Optional
from datetime import datetime

from llm.base import (
    LLMProvider,
    LLMResponse,
    StreamChunk,
    ModelInfo,
    LLMProviderError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama provider implementation for local LLM inference."""

    SUPPORTED_MODELS = {
        "llama3.1:70b": {
            "context_window": 8192,
            "max_tokens": 4096,
            "capabilities": ["completion", "chat", "streaming"],
        },
        "llama3.1:8b": {
            "context_window": 8192,
            "max_tokens": 4096,
            "capabilities": ["completion", "chat", "streaming"],
        },
        "phi3:medium": {
            "context_window": 4096,
            "max_tokens": 2048,
            "capabilities": ["completion", "chat", "streaming"],
        },
        "mistral:7b": {
            "context_window": 8192,
            "max_tokens": 4096,
            "capabilities": ["completion", "chat", "streaming"],
        },
    }

    def __init__(self, config: Dict):
        """
        Initialize Ollama provider.

        Args:
            config: Configuration dict with:
                - base_url: Ollama API endpoint (default: http://localhost:11434)
                - model: Model name (default: llama3.1:8b)
                - timeout: Request timeout in seconds (default: 120)
                - num_ctx: Context window size (optional)
                - num_predict: Max tokens to generate (optional)
        """
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.model = config.get("model", "llama3.1:8b")
        self.timeout = config.get("timeout", 120)
        self.num_ctx = config.get("num_ctx")
        self.num_predict = config.get("num_predict")

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
        Generate completion using Ollama API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional Ollama parameters

        Returns:
            LLMResponse with generated content
        """
        start_time = datetime.now()

        # Build request payload
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }

        # Add system prompt if provided
        if system_prompt:
            payload["system"] = system_prompt

        # Add context window size
        if self.num_ctx:
            payload["options"]["num_ctx"] = self.num_ctx

        # Add max tokens
        if max_tokens or self.num_predict:
            payload["options"]["num_predict"] = max_tokens or self.num_predict

        # Merge additional options
        if kwargs:
            payload["options"].update(kwargs)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise LLMProviderError(
                            f"Ollama API error (status {response.status}): {error_text}"
                        )

                    result = await response.json()

                    # Extract response content
                    content = result.get("response", "")

                    # Calculate tokens used (Ollama provides eval_count)
                    tokens_used = result.get("eval_count")

                    duration = (datetime.now() - start_time).total_seconds()

                    return LLMResponse(
                        content=content,
                        model=self.model,
                        provider="ollama",
                        tokens_used=tokens_used,
                        finish_reason=result.get("done_reason"),
                        metadata={
                            "total_duration_ns": result.get("total_duration"),
                            "load_duration_ns": result.get("load_duration"),
                            "prompt_eval_count": result.get("prompt_eval_count"),
                            "eval_count": result.get("eval_count"),
                            "duration_seconds": duration,
                        },
                    )

        except asyncio.TimeoutError:
            raise LLMTimeoutError(
                f"Ollama request timed out after {self.timeout}s"
            )
        except aiohttp.ClientError as e:
            raise LLMProviderError(f"Ollama connection error: {str(e)}")
        except Exception as e:
            logger.error(f"Ollama generation error: {str(e)}")
            raise LLMProviderError(f"Ollama generation failed: {str(e)}")

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Generate completion with streaming using Ollama API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional Ollama parameters

        Yields:
            StreamChunk objects as they are generated
        """
        # Build request payload
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
            }
        }

        # Add system prompt if provided
        if system_prompt:
            payload["system"] = system_prompt

        # Add context window size
        if self.num_ctx:
            payload["options"]["num_ctx"] = self.num_ctx

        # Add max tokens
        if max_tokens or self.num_predict:
            payload["options"]["num_predict"] = max_tokens or self.num_predict

        # Merge additional options
        if kwargs:
            payload["options"].update(kwargs)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise LLMProviderError(
                            f"Ollama API error (status {response.status}): {error_text}"
                        )

                    # Stream response line by line
                    async for line in response.content:
                        if line:
                            try:
                                chunk_data = json.loads(line.decode('utf-8'))

                                # Extract chunk content
                                chunk_content = chunk_data.get("response", "")
                                is_final = chunk_data.get("done", False)

                                yield StreamChunk(
                                    content=chunk_content,
                                    is_final=is_final,
                                    metadata={
                                        "model": self.model,
                                        "eval_count": chunk_data.get("eval_count"),
                                    } if is_final else {},
                                )

                                if is_final:
                                    break

                            except json.JSONDecodeError:
                                logger.warning(f"Failed to decode chunk: {line}")
                                continue

        except asyncio.TimeoutError:
            raise LLMTimeoutError(
                f"Ollama streaming request timed out after {self.timeout}s"
            )
        except aiohttp.ClientError as e:
            raise LLMProviderError(f"Ollama connection error: {str(e)}")
        except Exception as e:
            logger.error(f"Ollama streaming error: {str(e)}")
            raise LLMProviderError(f"Ollama streaming failed: {str(e)}")

    def get_model_info(self) -> ModelInfo:
        """
        Get information about the current Ollama model.

        Returns:
            ModelInfo object with model capabilities
        """
        model_config = self.SUPPORTED_MODELS.get(
            self.model,
            {
                "context_window": 4096,
                "max_tokens": 2048,
                "capabilities": ["completion", "chat", "streaming"],
            }
        )

        return ModelInfo(
            name=self.model,
            provider="ollama",
            context_window=model_config["context_window"],
            supports_streaming=True,
            max_tokens=model_config.get("max_tokens"),
            pricing=None,  # Ollama is free/local
            capabilities=model_config["capabilities"],
        )

    async def health_check(self) -> bool:
        """
        Check if Ollama server is healthy and model is available.

        Returns:
            True if Ollama is accessible and model is loaded
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Check if Ollama is running
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status != 200:
                        logger.error(f"Ollama health check failed: status {response.status}")
                        return False

                    # Check if model is available
                    result = await response.json()
                    models = [m["name"] for m in result.get("models", [])]

                    if self.model not in models:
                        logger.warning(
                            f"Model {self.model} not found in Ollama. "
                            f"Available models: {models}"
                        )
                        return False

                    return True

        except Exception as e:
            logger.error(f"Ollama health check error: {str(e)}")
            return False

    def count_tokens(self, text: str) -> int:
        """
        Estimate token count using Llama tokenizer approximation.

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count
        """
        # Llama models use ~3.5 characters per token on average
        return int(len(text) / 3.5)
