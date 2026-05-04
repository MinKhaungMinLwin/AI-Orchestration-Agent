"""
Lightweight Reranker Service for Korean FAQ RAG.

Uses keyword-overlap + content-overlap scoring to rerank retrieved documents
without any additional model dependencies (pure Python, zero latency overhead).

Scoring formula:
    final_score = vector_score * 0.5
               + keyword_jaccard * 0.3   (query tokens ∩ FAQ keywords / union)
               + content_overlap * 0.2  (query tokens found in question+content)
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Korean particles stripped before tokenization for overlap comparison
_STRIP_PATTERN = re.compile(r"[^\w가-힣a-zA-Z0-9]")
_SPLIT_PATTERN = re.compile(r"[\s,./\-_>()\[\]「」『』【】]+")

# Minimum token length (filter single-char noise)
_MIN_TOKEN_LEN = 2


class RerankerService:
    """
    Post-retrieval reranker for FAQ results.

    Combines the original vector score with lexical signals (keyword Jaccard
    and content token overlap) to improve precision without LLM overhead.
    """

    def __init__(
        self,
        vector_weight: float = 0.5,
        keyword_weight: float = 0.3,
        content_weight: float = 0.2,
    ):
        if abs(vector_weight + keyword_weight + content_weight - 1.0) > 1e-6:
            raise ValueError("Weights must sum to 1.0")
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.content_weight = content_weight

    def rerank(
        self,
        query: str,
        results: list[dict],
        top_k: int = 5,
        score_threshold: Optional[float] = None,
    ) -> list[dict]:
        """
        Rerank FAQ results for a given query.

        Args:
            query: User's original query string.
            results: List of hit dicts with keys: id, score, payload.
            top_k: Number of results to return after reranking.
            score_threshold: Optional minimum final score to include result.

        Returns:
            Reranked list (up to top_k), with updated 'score' field.
        """
        if not results:
            return []

        query_tokens = self._tokenize(query)

        scored: list[dict] = []
        for result in results:
            payload = result.get("payload", {})
            vector_score = float(result.get("score", 0.0))

            keyword_score = self._keyword_jaccard(query_tokens, payload)
            content_score = self._content_overlap(query_tokens, payload)

            final_score = (
                self.vector_weight * vector_score
                + self.keyword_weight * keyword_score
                + self.content_weight * content_score
            )

            entry = {**result, "score": final_score}
            if score_threshold is None or final_score >= score_threshold:
                scored.append(entry)

        scored.sort(key=lambda x: x["score"], reverse=True)

        logger.info(
            f"[Reranker] query_tokens={len(query_tokens)}, "
            f"input={len(results)}, output={min(len(scored), top_k)}"
        )
        return scored[:top_k]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> set[str]:
        """Whitespace + punctuation split; filter short tokens."""
        raw = _SPLIT_PATTERN.split(text.strip().lower())
        return {t for t in raw if len(t) >= _MIN_TOKEN_LEN}

    def _keyword_jaccard(self, query_tokens: set[str], payload: dict) -> float:
        """Jaccard similarity between query tokens and normalized FAQ keywords."""
        meta = payload.get("metadata", {})
        raw_keywords: list[str] = meta.get("keywords", [])
        if not raw_keywords:
            return 0.0

        kw_tokens: set[str] = set()
        for kw in raw_keywords:
            kw_tokens.update(self._tokenize(kw))

        if not kw_tokens:
            return 0.0

        intersection = len(query_tokens & kw_tokens)
        union = len(query_tokens | kw_tokens)
        return intersection / union if union else 0.0

    def _content_overlap(self, query_tokens: set[str], payload: dict) -> float:
        """Fraction of query tokens found in the FAQ question + answer text."""
        if not query_tokens:
            return 0.0

        # Payload stores 'question' and 'answer'. The 'content' field was removed
        # during slim payload indexing to reduce Qdrant request size.
        text_parts = [
            payload.get("question", ""),
            payload.get("answer", ""),
        ]
        content_tokens = set()
        for part in text_parts:
            content_tokens.update(self._tokenize(part))

        matched = len(query_tokens & content_tokens)
        return min(matched / len(query_tokens), 1.0)


# Singleton
_reranker: Optional[RerankerService] = None


def get_reranker_service(
    vector_weight: float = 0.5,
    keyword_weight: float = 0.3,
    content_weight: float = 0.2,
) -> RerankerService:
    """Get or initialize singleton RerankerService."""
    global _reranker
    if _reranker is None:
        _reranker = RerankerService(
            vector_weight=vector_weight,
            keyword_weight=keyword_weight,
            content_weight=content_weight,
        )
    return _reranker
