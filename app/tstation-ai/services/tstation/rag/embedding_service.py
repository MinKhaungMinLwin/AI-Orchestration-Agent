"""
Embedding Service for generating text embeddings.

Supports multiple embedding models:
- OpenAI (text-embedding-3-small)
- Cohere
"""

import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from typing import Optional

import redis as _redis

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# L1: In-process embedding cache (per-worker, <1ms hit)
# Key:   "{model}:{text}"   Value: (vector, inserted_monotonic)
# TTL:   1 hour — query embeddings don't change within a session
# Max:   2000 entries — prevents unbounded memory growth
#
# L2: Redis shared cache (cross-worker, ~2ms hit)
# Key:   "embed:{model}:{md5(text)}"   TTL: 1 hour
# ─────────────────────────────────────────────────────────────
_embed_cache: OrderedDict[str, tuple[list[float], float]] = OrderedDict()
_EMBED_CACHE_TTL: float = 3600.0
_EMBED_CACHE_MAX: int = 2000

_redis_embed: Optional[_redis.Redis] = None


def _get_redis_embed() -> Optional[_redis.Redis]:
    global _redis_embed
    if _redis_embed is None:
        from config.env import settings
        url = getattr(settings, "REDIS_CONVERSATION_MANAGEMENT_URL", None)
        if url:
            _redis_embed = _redis.from_url(
                url, socket_timeout=1, socket_connect_timeout=1, decode_responses=True
            )
    return _redis_embed


class EmbeddingService:
    """Generates embeddings for text documents."""

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        provider: str = "openai",
        api_key: Optional[str] = None,
    ):
        """
        Initialize embedding service.

        Args:
            model: Embedding model name (default: text-embedding-3-small)
            provider: Provider ("openai" or "cohere")
            api_key: Optional API key (will try to load from env if not provided)
        """
        self.model = model
        self.provider = provider

        if provider == "openai":
            try:
                from openai import OpenAI

                # Try to get API key from multiple sources
                openai_key = api_key or os.getenv("OPENAI_API_KEY")
                
                if not openai_key:
                    # Try to load from settings
                    try:
                        from config.env import settings
                        openai_key = settings.OPENAI_API_KEY
                    except Exception:
                        pass

                if openai_key:
                    self.client = OpenAI(api_key=openai_key)
                else:
                    raise ValueError(
                        "OPENAI_API_KEY not found. Please set OPENAI_API_KEY in .env "
                        "or pass it as api_key parameter"
                    )
            except ImportError:
                raise ImportError(
                    "openai package required. Install with: pip install openai"
                )
        elif provider == "cohere":
            try:
                import cohere

                cohere_key = api_key or os.getenv("COHERE_API_KEY")
                
                if not cohere_key:
                    try:
                        from config.env import settings
                        cohere_key = getattr(settings, "COHERE_API_KEY", None)
                    except Exception:
                        pass

                if cohere_key:
                    self.client = cohere.ClientV2(api_key=cohere_key)
                else:
                    self.client = cohere.ClientV2()

            except ImportError:
                raise ImportError(
                    "cohere package required. Install with: pip install cohere"
                )
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        logger.info(f"Initialized {provider} embedding service with model {model}")

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text (no cache)."""
        return self.embed_texts([text])[0]

    def embed_text_cached(self, text: str) -> list[float]:
        """
        Generate embedding with two-layer cache.

        L1 (in-process dict) → <1ms, per-worker only.
        L2 (Redis)           → ~2ms, shared across all workers.
        Cache miss           → calls embed_text() (~150ms API call).
        """
        l1_key = f"{self.model}:{text}"
        l2_key = f"embed:{self.model}:{hashlib.md5(text.encode()).hexdigest()}"
        now = time.monotonic()

        # L1: in-process cache
        entry = _embed_cache.get(l1_key)
        if entry is not None:
            vector, inserted_at = entry
            if now - inserted_at < _EMBED_CACHE_TTL:
                logger.debug("[EmbeddingService] L1 HIT (len=%d)", len(text))
                return vector
            del _embed_cache[l1_key]

        # L2: Redis shared cache
        r = _get_redis_embed()
        if r is not None:
            try:
                cached = r.get(l2_key)
                if cached is not None:
                    vector = json.loads(cached)
                    _embed_cache[l1_key] = (vector, now)
                    logger.debug("[EmbeddingService] L2 Redis HIT (len=%d)", len(text))
                    return vector
            except Exception:
                logger.debug("[EmbeddingService] Redis unavailable, falling through to API")

        vector = self.embed_text(text)

        if r is not None:
            try:
                r.setex(l2_key, int(_EMBED_CACHE_TTL), json.dumps(vector))
            except Exception:
                pass

        # Evict oldest half when L1 is full (OrderedDict preserves insert order → O(1) per pop)
        if len(_embed_cache) >= _EMBED_CACHE_MAX:
            for _ in range(_EMBED_CACHE_MAX // 2):
                _embed_cache.popitem(last=False)
            logger.debug("[EmbeddingService] L1 evicted %d entries", _EMBED_CACHE_MAX // 2)

        _embed_cache[l1_key] = (vector, now)
        logger.debug("[EmbeddingService] cache MISS → API (len=%d)", len(text))
        return vector

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        try:
            if self.provider == "openai":
                # Remove newlines for better results
                texts_cleaned = [text.replace("\n", " ") for text in texts]

                response = self.client.embeddings.create(
                    input=texts_cleaned,
                    model=self.model,
                )

                embeddings = [item.embedding for item in response.data]
                logger.info(f"Generated embeddings for {len(texts)} texts via OpenAI")
                return embeddings

            elif self.provider == "cohere":
                response = self.client.embed(
                    texts=texts,
                    model=self.model,
                    input_type="search_document",
                )

                embeddings = response.embeddings
                logger.info(f"Generated embeddings for {len(texts)} texts via Cohere")
                return embeddings

        except Exception as e:
            logger.exception(f"Failed to generate embeddings for {len(texts)} texts")
            raise

    def get_embedding_dimension(self) -> int:
        """Get embedding vector dimension."""
        if self.provider == "openai":
            if "small" in self.model:
                return 1536
            elif "large" in self.model:
                return 3072
        elif self.provider == "cohere":
            if "english" in self.model:
                return 4096
        return 1536  # Default

    def health_check(self) -> bool:
        """Test if embedding service is accessible."""
        try:
            _ = self.embed_text("test")
            logger.info(f"Embedding service health check passed ({self.provider})")
            return True
        except Exception as e:
            logger.error(f"Embedding service health check failed: {e}")
            return False


# Global instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service(
    model: str = "text-embedding-3-small",
    provider: str = "openai",
    api_key: Optional[str] = None,
) -> EmbeddingService:
    """Get or initialize singleton embedding service."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(
            model=model,
            provider=provider,
            api_key=api_key,
        )
    return _embedding_service
