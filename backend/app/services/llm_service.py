"""
LLM Service - Ollama Integration
Primary LLM provider for clinical note generation
"""
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator
import httpx
import json

from app.config import settings

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client for interacting with Ollama LLM API."""

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.default_model = settings.OLLAMA_DEFAULT_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT
        self.embedding_model = settings.OLLAMA_EMBEDDING_MODEL

    async def health_check(self) -> bool:
        """Check if Ollama service is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama health check failed: {str(e)}")
            return False

    async def list_models(self) -> List[Dict[str, Any]]:
        """
        List all available models.

        Returns:
            List of model information dictionaries
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()

                data = response.json()
                models = data.get("models", [])

                return [
                    {
                        "name": model.get("name"),
                        "size": model.get("size"),
                        "modified_at": model.get("modified_at"),
                        "digest": model.get("digest")
                    }
                    for model in models
                ]

        except Exception as e:
            logger.error(f"Failed to list models: {str(e)}")
            raise

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stop: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate text completion.

        Args:
            prompt: Input prompt
            model: Model name (defaults to configured default)
            system: System prompt
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            stop: Stop sequences

        Returns:
            Generated response with metadata
        """
        model = model or self.default_model

        try:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                }
            }

            if system:
                payload["system"] = system

            if stop:
                payload["options"]["stop"] = stop

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload
                )
                response.raise_for_status()

                result = response.json()

                return {
                    "response": result.get("response", ""),
                    "model": result.get("model"),
                    "tokens_used": result.get("eval_count", 0),
                    "generation_time_ms": result.get("total_duration", 0) // 1_000_000,
                    "done": result.get("done", False)
                }

        except httpx.TimeoutException:
            logger.error(f"Ollama request timeout after {self.timeout}s")
            raise
        except Exception as e:
            logger.error(f"Ollama generation failed: {str(e)}")
            raise

    async def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> AsyncGenerator[str, None]:
        """
        Generate text completion with streaming.

        Args:
            prompt: Input prompt
            model: Model name
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            Generated text chunks
        """
        model = model or self.default_model

        try:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                }
            }

            if system:
                payload["system"] = system

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json=payload
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                chunk = data.get("response", "")
                                if chunk:
                                    yield chunk

                                if data.get("done", False):
                                    break
                            except json.JSONDecodeError:
                                continue

        except Exception as e:
            logger.error(f"Ollama streaming generation failed: {str(e)}")
            raise

    async def generate_embeddings(
        self,
        text: str,
        model: Optional[str] = None
    ) -> List[float]:
        """
        Generate embeddings for text.

        Args:
            text: Input text
            model: Embedding model name (defaults to configured embedding model)

        Returns:
            List of embedding values (768-dimensional)
        """
        model = model or self.embedding_model

        try:
            payload = {
                "model": model,
                "prompt": text
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json=payload
                )
                response.raise_for_status()

                result = response.json()
                embedding = result.get("embedding", [])

                if len(embedding) != settings.EMBEDDING_DIMENSION:
                    logger.warning(
                        f"Embedding dimension mismatch: expected {settings.EMBEDDING_DIMENSION}, "
                        f"got {len(embedding)}"
                    )

                return embedding

        except Exception as e:
            logger.error(f"Ollama embedding generation failed: {str(e)}")
            raise

    async def pull_model(self, model_name: str) -> Dict[str, str]:
        """
        Pull/download a model.

        Args:
            model_name: Name of model to pull

        Returns:
            Status dictionary
        """
        try:
            payload = {
                "name": model_name,
                "stream": False
            }

            async with httpx.AsyncClient(timeout=3600.0) as client:  # 1 hour timeout for model pull
                response = await client.post(
                    f"{self.base_url}/api/pull",
                    json=payload
                )
                response.raise_for_status()

                return {
                    "status": "success",
                    "model": model_name,
                    "message": f"Model {model_name} pulled successfully"
                }

        except Exception as e:
            logger.error(f"Failed to pull model {model_name}: {str(e)}")
            raise


# Global Ollama client instance
ollama_client = OllamaClient()
