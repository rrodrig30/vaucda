"""
Embedding Generation for RAG Pipeline
Uses sentence-transformers for generating 768-dimensional embeddings
Includes Redis caching for frequently embedded queries
"""

import os
import logging
import hashlib
import json
import pickle
from typing import List, Optional, Union
import numpy as np
from sentence_transformers import SentenceTransformer
import redis
import torch

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """
    Generate embeddings for text using sentence-transformers.

    Features:
    - 768-dimensional embeddings via all-MiniLM-L6-v2
    - Batch processing for efficiency
    - Redis caching for frequent queries
    - GPU support if available
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        cache_enabled: bool = True,
        redis_host: Optional[str] = None,
        redis_port: Optional[int] = None,
        redis_db: int = 1,
        device: Optional[str] = None
    ):
        """
        Initialize embedding generator.

        Args:
            model_name: Name of sentence-transformers model
            cache_enabled: Whether to enable Redis caching
            redis_host: Redis host (defaults to env or localhost)
            redis_port: Redis port (defaults to env or 6379)
            redis_db: Redis database number
            device: Device to use ('cuda', 'cpu', or None for auto)
        """
        self.model_name = model_name
        self.cache_enabled = cache_enabled

        # Determine device
        if device:
            self.device = device
        else:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Load model
        logger.info(f"Loading embedding model: {model_name} on {self.device}")
        self.model = SentenceTransformer(model_name, device=self.device)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        logger.info(f"Model loaded. Embedding dimension: {self.embedding_dim}")

        # Initialize Redis cache
        self.redis_client = None
        if cache_enabled:
            try:
                redis_host = redis_host or os.getenv("REDIS_HOST", "localhost")
                redis_port = redis_port or int(os.getenv("REDIS_PORT", "6379"))

                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=False  # We store binary data (pickled numpy arrays)
                )

                # Test connection
                self.redis_client.ping()
                logger.info(f"Redis cache connected: {redis_host}:{redis_port}")
            except Exception as e:
                logger.warning(f"Redis cache unavailable: {e}. Proceeding without cache.")
                self.redis_client = None

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        return f"embedding:{self.model_name}:{text_hash}"

    def _get_from_cache(self, text: str) -> Optional[np.ndarray]:
        """Retrieve embedding from cache."""
        if not self.redis_client:
            return None

        try:
            key = self._get_cache_key(text)
            cached = self.redis_client.get(key)

            if cached:
                embedding = pickle.loads(cached)
                logger.debug(f"Cache hit for text (length {len(text)})")
                return embedding
        except Exception as e:
            logger.warning(f"Cache retrieval failed: {e}")

        return None

    def _save_to_cache(self, text: str, embedding: np.ndarray, ttl: int = 86400):
        """
        Save embedding to cache.

        Args:
            text: Original text
            embedding: Embedding vector
            ttl: Time to live in seconds (default 24 hours)
        """
        if not self.redis_client:
            return

        try:
            key = self._get_cache_key(text)
            value = pickle.dumps(embedding)
            self.redis_client.setex(key, ttl, value)
            logger.debug(f"Cached embedding for text (length {len(text)})")
        except Exception as e:
            logger.warning(f"Cache storage failed: {e}")

    def generate_embedding(self, text: str, use_cache: bool = True) -> np.ndarray:
        """
        Generate embedding for single text.

        Args:
            text: Input text
            use_cache: Whether to use cache (default True)

        Returns:
            768-dimensional numpy array
        """
        # Check cache first
        if use_cache:
            cached = self._get_from_cache(text)
            if cached is not None:
                return cached

        # Generate embedding
        embedding = self.model.encode(
            text,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True  # L2 normalization for cosine similarity
        )

        # Cache result
        if use_cache:
            self._save_to_cache(text, embedding)

        return embedding

    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress: bool = False,
        use_cache: bool = False  # Batch mode typically doesn't use cache
    ) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of input texts
            batch_size: Batch size for processing
            show_progress: Whether to show progress bar
            use_cache: Whether to use cache (slower for batch)

        Returns:
            List of 768-dimensional numpy arrays
        """
        if not texts:
            return []

        # If using cache, process individually
        if use_cache:
            return [self.generate_embedding(text, use_cache=True) for text in texts]

        # Batch processing
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=show_progress,
            normalize_embeddings=True
        )

        return [embedding for embedding in embeddings]

    def get_cached_or_generate(self, text: str) -> np.ndarray:
        """
        Convenience method: check cache first, generate if miss.

        Args:
            text: Input text

        Returns:
            768-dimensional numpy array
        """
        return self.generate_embedding(text, use_cache=True)

    def compute_similarity(
        self,
        embedding1: Union[np.ndarray, str],
        embedding2: Union[np.ndarray, str]
    ) -> float:
        """
        Compute cosine similarity between two embeddings or texts.

        Args:
            embedding1: Embedding array or text
            embedding2: Embedding array or text

        Returns:
            Cosine similarity score (0-1)
        """
        # Convert texts to embeddings if needed
        if isinstance(embedding1, str):
            embedding1 = self.generate_embedding(embedding1)
        if isinstance(embedding2, str):
            embedding2 = self.generate_embedding(embedding2)

        # Compute cosine similarity
        similarity = np.dot(embedding1, embedding2)
        return float(similarity)

    def clear_cache(self, pattern: str = "*") -> int:
        """
        Clear embeddings from cache.

        Args:
            pattern: Pattern for keys to clear (default all embeddings)

        Returns:
            Number of keys deleted
        """
        if not self.redis_client:
            return 0

        try:
            keys = self.redis_client.keys(f"embedding:{self.model_name}:{pattern}")
            if keys:
                deleted = self.redis_client.delete(*keys)
                logger.info(f"Cleared {deleted} cached embeddings")
                return deleted
        except Exception as e:
            logger.error(f"Cache clear failed: {e}")

        return 0

    def get_model_info(self) -> dict:
        """Get information about the embedding model."""
        return {
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "device": self.device,
            "cache_enabled": self.redis_client is not None,
        }


# Global singleton instance
_embedding_generator = None


def get_embedding_generator() -> EmbeddingGenerator:
    """Get or create global embedding generator instance."""
    global _embedding_generator
    if _embedding_generator is None:
        _embedding_generator = EmbeddingGenerator()
    return _embedding_generator
