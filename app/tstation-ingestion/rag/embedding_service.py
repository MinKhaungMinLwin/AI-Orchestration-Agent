"""
Embedding Service for generating text embeddings.

Supports multiple embedding models:
- OpenAI (text-embedding-3-small)
- Cohere
"""

import logging
import os
from typing import Optional, Union

logger = logging.getLogger(__name__)


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
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (list of floats)
        """
        return self.embed_texts([text])[0]

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
