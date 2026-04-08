"""
Document Chunking Service for splitting large texts into manageable chunks.

Supports:
- Fixed-size chunking
- Overlapping chunks
- Semantic-aware chunking
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ChunkingService:
    """Splits documents into chunks with optional overlap."""

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separator: str = " ",
    ):
        """
        Initialize chunking service.

        Args:
            chunk_size: Maximum tokens per chunk (default 512)
            chunk_overlap: Number of overlapping tokens (default 50)
            separator: Text separator for splitting (default " ")
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separator = separator

        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")

        logger.info(
            f"Initialized ChunkingService: size={chunk_size}, "
            f"overlap={chunk_overlap}, separator='{separator}'"
        )

    def chunk_text(self, text: str, metadata: Optional[dict] = None) -> list[dict]:
        """
        Split a single text into chunks.

        Args:
            text: Text to chunk
            metadata: Optional metadata to attach to each chunk

        Returns:
            List of chunks with metadata
        """
        return self.chunk_texts([text], [metadata or {}])[0]

    def chunk_texts(
        self,
        texts: list[str],
        metadatas: list[dict],
    ) -> list[list[dict]]:
        """
        Split multiple texts into chunks.

        Args:
            texts: List of texts to chunk
            metadatas: List of metadata dicts (one per text)

        Returns:
            List of chunk lists (one list per text)

        Example:
            texts = ["Long text 1...", "Long text 2..."]
            metadatas = [{"source": "doc1"}, {"source": "doc2"}]
            chunks = service.chunk_texts(texts, metadatas)
        """
        if len(texts) != len(metadatas):
            raise ValueError("texts and metadatas must have same length")

        all_chunks = []

        for text, metadata in zip(texts, metadatas):
            chunks = self._split_text(text, metadata)
            all_chunks.append(chunks)
            logger.info(
                f"Chunked text: original_length={len(text)}, "
                f"chunk_count={len(chunks)}"
            )

        return all_chunks

    def _split_text(self, text: str, metadata: dict) -> list[dict]:
        """Split single text into overlapping chunks."""
        # Split text into tokens (words)
        tokens = text.split(self.separator)
        chunks = []
        chunk_idx = 0

        for i in range(0, len(tokens), self.chunk_size - self.chunk_overlap):
            chunk_tokens = tokens[i : i + self.chunk_size]
            chunk_text = self.separator.join(chunk_tokens)

            chunk = {
                "id": f"{metadata.get('id', 'chunk')}_{chunk_idx}",
                "content": chunk_text,
                "chunk_index": chunk_idx,
                "token_count": len(chunk_tokens),
                "metadata": metadata,
                "original_text": text,
            }
            chunks.append(chunk)
            chunk_idx += 1

            # Stop if we've covered all tokens
            if i + self.chunk_size >= len(tokens):
                break

        return chunks

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text (simple split-based).

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return len(text.split(self.separator))

    @staticmethod
    def merge_chunks(
        chunks: list[dict],
        merge_threshold: int = 5,
    ) -> list[dict]:
        """
        Merge small consecutive chunks if they're below threshold.

        Args:
            chunks: List of chunks
            merge_threshold: Min tokens to keep chunk separate

        Returns:
            Merged chunks
        """
        if not chunks:
            return []

        merged = []
        current_merged = None

        for chunk in chunks:
            if current_merged is None:
                current_merged = chunk.copy()
            elif chunk["token_count"] < merge_threshold:
                # Merge with previous
                current_merged["content"] += " " + chunk["content"]
                current_merged["token_count"] += chunk["token_count"]
            else:
                merged.append(current_merged)
                current_merged = chunk.copy()

        if current_merged:
            merged.append(current_merged)

        logger.info(f"Merged chunks: {len(chunks)} -> {len(merged)}")
        return merged
