"""In-memory BM25 index for FAQ hybrid search. Lazy-builds; auto-refreshes hourly."""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_TTL: float = 3600.0  # rebuild every hour; FAQ sync is weekly
_RRF_K: int = 60


class Bm25FaqIndex:
    """
    In-memory BM25 index over FAQ question and answer texts, backed by a Qdrant collection.

    Lazy-initialises on the first call to ensure_built(); refreshes every _TTL seconds.
    Thread-safe: concurrent rebuild calls serialise via _build_lock; readers always see
    a consistent snapshot (Python attribute assignment is atomic for simple types).

    search() scores against both question and answer corpora independently,
    then fuses via pure RRF (k=60) before returning top_k hits.
    """

    _instance: Optional["Bm25FaqIndex"] = None
    _class_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._bm25_question = None
        self._bm25_answer = None
        self._point_ids: list[str] = []
        self._payloads: dict[str, dict] = {}
        self._built_at: float = 0.0
        self._build_lock = threading.Lock()

    @classmethod
    def get(cls) -> "Bm25FaqIndex":
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = Bm25FaqIndex()
        return cls._instance

    def ensure_built(self, qdrant_client, collection_name: str) -> None:
        """Build or refresh the index if needed. Concurrent callers serialise on _build_lock."""
        if not self._needs_rebuild():
            return
        with self._build_lock:
            if not self._needs_rebuild():
                return
            self._build(qdrant_client, collection_name)

    def _needs_rebuild(self) -> bool:
        return self._bm25_question is None or (time.monotonic() - self._built_at) >= _TTL

    def _build(self, qdrant_client, collection_name: str) -> None:
        from rank_bm25 import BM25Okapi

        point_ids: list[str] = []
        payloads: dict[str, dict] = {}
        question_corpus: list[list[str]] = []
        answer_corpus: list[list[str]] = []
        offset = None

        while True:
            records, next_offset = qdrant_client.scroll(
                collection_name=collection_name,
                limit=200,
                with_payload=True,
                with_vectors=False,
                offset=offset,
            )
            for r in records:
                payload = r.payload or {}
                pid = str(r.id)
                point_ids.append(pid)
                payloads[pid] = payload
                question_corpus.append(self._tokenize(payload.get("question", "")))
                answer_corpus.append(self._tokenize(payload.get("answer", "")))
            if next_offset is None:
                break
            offset = next_offset

        if not question_corpus:
            logger.warning("[Bm25FaqIndex] No documents found in '%s'; index not built", collection_name)
            return

        bm25_question = BM25Okapi(question_corpus)
        bm25_answer = BM25Okapi(answer_corpus)
        # Atomic swap: assign all fields before updating _built_at
        self._bm25_question = bm25_question
        self._bm25_answer = bm25_answer
        self._point_ids = point_ids
        self._payloads = payloads
        self._built_at = time.monotonic()
        logger.info("[Bm25FaqIndex] Built: %d documents from '%s'", len(question_corpus), collection_name)

    def search(self, query: str, top_k: int) -> list[dict]:
        """Return top_k [{id, score, payload}] via internal RRF of question + answer BM25."""
        if self._bm25_question is None:
            return []
        tokens = self._tokenize(query)
        if not tokens:
            return []

        logger.info("[Bm25FaqIndex] tokens=%s", tokens)

        q_scores = self._bm25_question.get_scores(tokens)
        a_scores = self._bm25_answer.get_scores(tokens)

        q_ranked = sorted(range(len(q_scores)), key=lambda i: q_scores[i], reverse=True)
        a_ranked = sorted(range(len(a_scores)), key=lambda i: a_scores[i], reverse=True)

        logger.info(
            "[Bm25FaqIndex] top3 question-BM25: %s",
            [(self._payloads[self._point_ids[i]].get("question", "")[:50], round(float(q_scores[i]), 3)) for i in q_ranked[:3] if q_scores[i] > 0],
        )
        logger.info(
            "[Bm25FaqIndex] top3 answer-BM25:   %s",
            [(self._payloads[self._point_ids[i]].get("question", "")[:50], round(float(a_scores[i]), 3)) for i in a_ranked[:3] if a_scores[i] > 0],
        )

        rrf_scores: dict[int, float] = {}
        for rank, idx in enumerate(q_ranked):
            if q_scores[idx] > 0.0:
                rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1 / (_RRF_K + rank + 1)
        for rank, idx in enumerate(a_ranked):
            if a_scores[idx] > 0.0:
                rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1 / (_RRF_K + rank + 1)

        top_indices = sorted(rrf_scores, key=lambda i: rrf_scores[i], reverse=True)[:top_k]

        results = [
            {"id": self._point_ids[i], "score": rrf_scores[i], "payload": self._payloads[self._point_ids[i]]}
            for i in top_indices
        ]
        logger.info(
            "[Bm25FaqIndex] top3 after RRF: %s",
            [(r["payload"].get("question", "")[:50], round(r["score"], 4)) for r in results[:3]],
        )
        return results

    def is_ready(self) -> bool:
        return self._bm25_question is not None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Whitespace tokenisation — correctly handles Korean space-separated words."""
        return text.split()


def get_bm25_index() -> Bm25FaqIndex:
    return Bm25FaqIndex.get()
