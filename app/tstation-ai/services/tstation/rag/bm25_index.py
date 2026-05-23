"""In-memory BM25 index for FAQ hybrid search. Lazy-builds; auto-refreshes hourly."""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_TTL: float = 3600.0  # rebuild every hour; FAQ sync is weekly


class Bm25FaqIndex:
    """
    In-memory BM25 index over FAQ question texts, backed by a Qdrant collection.

    Lazy-initialises on the first call to ensure_built(); refreshes every _TTL seconds.
    Thread-safe: concurrent rebuild calls serialise via _build_lock; readers always see
    a consistent snapshot (Python attribute assignment is atomic for simple types).
    """

    _instance: Optional["Bm25FaqIndex"] = None
    _class_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._bm25 = None
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
        return self._bm25 is None or (time.monotonic() - self._built_at) >= _TTL

    def _build(self, qdrant_client, collection_name: str) -> None:
        from rank_bm25 import BM25Okapi

        point_ids: list[str] = []
        payloads: dict[str, dict] = {}
        corpus: list[list[str]] = []
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
                corpus.append(self._tokenize(payload.get("question", "")))
            if next_offset is None:
                break
            offset = next_offset

        if not corpus:
            logger.warning("[Bm25FaqIndex] No documents found in '%s'; index not built", collection_name)
            return

        bm25 = BM25Okapi(corpus)
        # Atomic field assignment: swap all fields before updating _built_at
        self._bm25 = bm25
        self._point_ids = point_ids
        self._payloads = payloads
        self._built_at = time.monotonic()
        logger.info("[Bm25FaqIndex] Built: %d documents from '%s'", len(corpus), collection_name)

    def search(self, query: str, top_k: int) -> list[dict]:
        """Return [{id, score, payload}] BM25 matches. Empty list if index not ready."""
        if self._bm25 is None:
            return []
        tokens = self._tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [
            {"id": self._point_ids[i], "score": float(scores[i]), "payload": self._payloads[self._point_ids[i]]}
            for i in top_indices
            if scores[i] > 0.0
        ]

    def is_ready(self) -> bool:
        return self._bm25 is not None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Whitespace tokenisation — correctly handles Korean space-separated words."""
        return text.split()


def get_bm25_index() -> Bm25FaqIndex:
    return Bm25FaqIndex.get()
