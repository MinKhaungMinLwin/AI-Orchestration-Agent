"""
RAG Dynamic Configuration.

Replaces hardcoded magic numbers (top_k * 4, score_threshold=0.6) with
values computed at runtime from actual collection size and score distribution.

Two public APIs:
    RAGDynamicConfig.compute_fetch_k(collection_size, final_top_k) -> int
    RAGDynamicConfig.adaptive_threshold(scores, base_threshold)     -> float
"""

import logging
import math

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Tunable constants
# ─────────────────────────────────────────────────────────────
_MIN_FETCH_K: int = 10       # never fetch fewer than 10 candidates
_MAX_FETCH_K: int = 100      # cap to avoid oversized Qdrant responses
_SCORE_GAP_RATIO: float = 0.15   # relative drop ≥ 15% = natural boundary
_ABS_FLOOR: float = 0.30     # never accept any doc below this score


class RAGDynamicConfig:
    """
    Utility class for computing dynamic RAG retrieval parameters.

    All methods are static — no instance needed.

    Why logarithmic fetch_k?
    ─────────────────────────
    As data grows, marginal candidates become less useful (more noise).
    log10 growth gives coverage without linearly exploding latency/payload:

        290 docs   → fetch_k ≈ 25
        2 900 docs → fetch_k ≈ 35
        29 000 docs → fetch_k ≈ 45
        290 000 docs → fetch_k = 55  (capped at 100)

    Why adaptive threshold?
    ───────────────────────
    A fixed 0.6 threshold is arbitrary — it may be too strict (cutting good
    docs) or too loose (letting noise through) depending on the query.
    Finding the first natural "score gap" (≥15% relative drop) lets the
    distribution itself tell us where relevant docs end and noise begins.
    """

    @staticmethod
    def compute_fetch_k(collection_size: int, final_top_k: int = 5) -> int:
        """
        Compute how many candidates to retrieve before reranking.

        Formula: max(log10(collection_size) × final_top_k × 2, MIN_FETCH_K, final_top_k × 2)
        Capped at MAX_FETCH_K to prevent oversized payloads.

        Args:
            collection_size: Total number of points in the Qdrant collection.
            final_top_k: Desired number of results after reranking.

        Returns:
            fetch_k as int.
        """
        if collection_size <= 0:
            collection_size = 100

        log_factor = math.log10(max(collection_size, 10))
        raw = int(log_factor * final_top_k * 2)

        fetch_k = max(
            min(raw, _MAX_FETCH_K),
            _MIN_FETCH_K,
            final_top_k * 2,
        )
        logger.debug(
            "[RAGDynamicConfig] collection=%d, final_top_k=%d → fetch_k=%d",
            collection_size, final_top_k, fetch_k,
        )
        return fetch_k

    @staticmethod
    def adaptive_threshold(scores: list[float], base_threshold: float = _ABS_FLOOR) -> float:
        """
        Detect the natural score gap in retrieved results and use it as cutoff.

        Algorithm:
            1. Sort descending.
            2. Walk pairs; find first where relative_drop = (s[i]-s[i+1])/s[i] ≥ GAP_RATIO.
            3. Threshold = max(s[i+1], base_threshold).
            4. If no gap found → fall back to base_threshold.

        Example:
            scores = [0.91, 0.88, 0.85, 0.51, 0.48]
            gap at 0.85→0.51: (0.85-0.51)/0.85 = 40% ≥ 15%
            → threshold = max(0.51, base) = 0.51

        Args:
            scores: Retrieval scores in any order.
            base_threshold: Absolute floor (from tool call, default 0.6).

        Returns:
            Effective threshold as float.
        """
        if len(scores) < 2:
            return base_threshold

        sorted_scores = sorted(scores, reverse=True)
        for i in range(len(sorted_scores) - 1):
            current = sorted_scores[i]
            nxt = sorted_scores[i + 1]
            if current < 1e-9:
                break
            relative_drop = (current - nxt) / current
            if relative_drop >= _SCORE_GAP_RATIO:
                threshold = max(nxt, base_threshold)
                logger.debug(
                    "[RAGDynamicConfig] gap %.0f%% at rank %d (%.3f→%.3f) → threshold=%.3f",
                    relative_drop * 100, i, current, nxt, threshold,
                )
                return threshold

        return base_threshold
