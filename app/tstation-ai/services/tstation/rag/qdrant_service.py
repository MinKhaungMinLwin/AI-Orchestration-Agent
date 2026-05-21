"""
Qdrant Vector Store Service for RAG operations.

Provides interface for:
- Collection management (create, delete, get stats)
- Document indexing (upsert vectors)
- Similarity search
"""

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# ─────────────────────────────────────────────
# Collection size cache  (TTL = 5 min)
# Avoids a Qdrant round-trip on every query
# just to compute a dynamic fetch_k.
# ─────────────────────────────────────────────
_collection_size_cache: dict[str, tuple[int, float]] = {}
_COLLECTION_CACHE_TTL: float = 3600.0

# Reused across all search_multi_vector calls — avoids per-request thread create/destroy overhead
_search_executor = ThreadPoolExecutor(max_workers=2)

logger = logging.getLogger(__name__)


class QdrantService:
    """Manages Qdrant vector store for FAQ documents."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        api_key: Optional[str] = None,
    ):
        """
        Initialize Qdrant client.

        Args:
            host: Qdrant host
            port: Qdrant port
            api_key: Optional API key for secured Qdrant
        """
        self.host = host
        self.port = port
        self.client = QdrantClient(
            host=host,
            port=port,
            api_key=api_key,
        )
        logger.info(f"Initialized Qdrant client: {host}:{port}")

    def create_collection(
        self,
        collection_name: str,
        vector_size: int = 1536,
        distance: Distance = Distance.COSINE,
    ) -> bool:
        """
        Create a new collection in Qdrant.

        Args:
            collection_name: Name of collection
            vector_size: Embedding vector size (default 1536 for OpenAI)
            distance: Distance metric (COSINE, EUCLID, DOT_PRODUCT)

        Returns:
            True if created successfully
        """
        try:
            # Check if collection exists
            collections = self.client.get_collections()
            existing_collections = [c.name for c in collections.collections]

            if collection_name in existing_collections:
                logger.warning(f"Collection {collection_name} already exists")
                return True

            # Create collection
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=distance,
                ),
            )
            logger.info(f"Created collection: {collection_name}")
            return True
        except Exception as e:
            logger.exception(f"Failed to create collection {collection_name}")
            raise

    def upsert_documents(
        self,
        collection_name: str,
        documents: list[dict],
        vectors: list[list[float]],
    ) -> dict:
        """
        Index documents into Qdrant collection.

        Args:
            collection_name: Collection name
            documents: List of documents with metadata
            vectors: List of embedding vectors (same length as documents)

        Returns:
            dict with upsert status

        Example:
            documents = [
                {"id": 1, "content": "...", "metadata": {...}},
                {"id": 2, "content": "...", "metadata": {...}},
            ]
            vectors = [[0.1, 0.2, ...], [0.3, 0.4, ...]]
            result = service.upsert_documents(collection_name, documents, vectors)
        """
        if len(documents) != len(vectors):
            raise ValueError("documents and vectors must have same length")

        try:
            points = []
            for doc, vector in zip(documents, vectors):
                point = PointStruct(
                    # id=doc.get("id", idx),
                    id=uuid.uuid4(),
                    vector=vector,
                    payload=doc,
                )
                points.append(point)

            self.client.upsert(
                collection_name=collection_name,
                points=points,
            )
            logger.info(f"Upserted {len(points)} documents into {collection_name}")
            return {
                "status": "success",
                "collection_name": collection_name,
                "upserted_count": len(points),
            }
        except Exception as e:
            logger.exception(f"Failed to upsert documents to {collection_name}")
            raise

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        using: Optional[str] = None,
    ) -> list[dict]:
        """
        Search for similar documents in collection.

        Args:
            collection_name: Collection name
            query_vector: Query embedding vector
            top_k: Number of results to return
            score_threshold: Minimum similarity score (0-1)
            using: Named vector to query (for multi-vector collections)

        Returns:
            List of results with similarity scores and payloads
        """
        try:
            kwargs: dict = dict(
                collection_name=collection_name,
                query=query_vector,
                limit=top_k,
                with_payload=True,
                score_threshold=score_threshold,
            )
            if using:
                kwargs["using"] = using

            results = self.client.query_points(**kwargs)

            hits = []
            for result in results.points:
                hit = {
                    "id": result.id,
                    "score": result.score,
                    "payload": result.payload,
                }
                hits.append(hit)

            logger.info(
                f"Search in {collection_name}: vector={using or 'default'}, "
                f"top_k={top_k}, score_threshold={score_threshold}, results={len(hits)}"
            )
            return hits
        except Exception as e:
            logger.exception(f"Failed to search in {collection_name}")
            raise

    # ---------------------------------------------------------------------------
    # Multi-vector collection support
    # ---------------------------------------------------------------------------

    def create_collection_multi_vector(
        self,
        collection_name: str,
        vector_size: int = 1536,
        distance: Distance = Distance.COSINE,
    ) -> bool:
        """
        Create a collection with named vectors 'question' and 'answer'.
        Deletes existing collection if present to ensure correct schema.
        """
        try:
            collections = self.client.get_collections()
            existing = [c.name for c in collections.collections]
            if collection_name in existing:
                logger.warning(f"Dropping existing collection {collection_name} for multi-vector recreate")
                self.client.delete_collection(collection_name)

            self.client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "question": VectorParams(size=vector_size, distance=distance),
                    "answer": VectorParams(size=vector_size, distance=distance),
                },
            )
            logger.info(f"Created multi-vector collection: {collection_name} (size={vector_size})")
            return True
        except Exception as e:
            logger.exception(f"Failed to create multi-vector collection {collection_name}")
            raise

    def upsert_multi_vector(
        self,
        collection_name: str,
        documents: list[dict],
        question_vectors: list[list[float]],
        answer_vectors: list[list[float]],
        batch_size: int = 50,
    ) -> dict:
        """
        Upsert documents with named 'question' and 'answer' vectors in batches.

        Qdrant has a 32 MB HTTP body limit. JSON-encoded float arrays are verbose
        (~15 chars/float), so 290 docs × 2 × 3072 floats ≈ 35 MB in one shot.
        Batching keeps each request well under the limit.

        Args:
            batch_size: Points per upsert request (default 50 ≈ ~5 MB/batch).
        """
        if not (len(documents) == len(question_vectors) == len(answer_vectors)):
            raise ValueError("documents, question_vectors, answer_vectors must have equal length")

        total_upserted = 0
        n_batches = (len(documents) + batch_size - 1) // batch_size

        for batch_idx in range(n_batches):
            start = batch_idx * batch_size
            end = start + batch_size
            batch_points = [
                PointStruct(
                    id=uuid.uuid4(),
                    vector={"question": q_vec, "answer": a_vec},
                    payload=doc,
                )
                for doc, q_vec, a_vec in zip(
                    documents[start:end],
                    question_vectors[start:end],
                    answer_vectors[start:end],
                )
            ]
            try:
                self.client.upsert(collection_name=collection_name, points=batch_points)
                total_upserted += len(batch_points)
                logger.info(
                    f"Upserted batch {batch_idx + 1}/{n_batches}: "
                    f"{len(batch_points)} points ({total_upserted}/{len(documents)} total)"
                )
            except Exception:
                logger.exception(f"Failed to upsert batch {batch_idx + 1} to {collection_name}")
                raise

        return {"status": "success", "collection_name": collection_name, "upserted_count": total_upserted}

    def search_multi_vector(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int = 5,
        score_threshold: float = 0.6,
        question_weight: float = 0.7,
        answer_weight: float = 0.3,
    ) -> list[dict]:
        """
        Hybrid search using RRF fusion of 'question' and 'answer' named vectors.

        Retrieves top_k candidates from each vector then fuses with Reciprocal Rank Fusion.
        The fused score is normalized to [0,1] and filtered by score_threshold.
        """
        fetch_k = top_k
        try:
            # Run question/answer vector searches in parallel to halve network latency
            def _query(vector_name: str):
                return self.client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    using=vector_name,
                    limit=fetch_k,
                    with_payload=True,
                )

            q_future = _search_executor.submit(_query, "question")
            a_future = _search_executor.submit(_query, "answer")
            q_results = q_future.result()
            a_results = a_future.result()
        except Exception as e:
            logger.exception(f"Failed multi-vector search in {collection_name}")
            raise

        # RRF fusion (k=60 is standard constant)
        RRF_K = 60
        scores: dict[str, float] = {}
        payloads: dict[str, dict] = {}

        for rank, point in enumerate(q_results.points):
            pid = str(point.id)
            scores[pid] = scores.get(pid, 0.0) + question_weight / (RRF_K + rank + 1)
            payloads[pid] = point.payload or {}

        for rank, point in enumerate(a_results.points):
            pid = str(point.id)
            scores[pid] = scores.get(pid, 0.0) + answer_weight / (RRF_K + rank + 1)
            if pid not in payloads:
                payloads[pid] = point.payload or {}

        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
        max_score = scores[sorted_ids[0]] if sorted_ids else 1.0

        hits = []
        for pid in sorted_ids:
            normalized = scores[pid] / max_score
            if normalized < score_threshold:
                break
            hits.append({"id": pid, "score": normalized, "payload": payloads[pid]})
            if len(hits) >= top_k:
                break

        logger.info(
            f"Multi-vector search in {collection_name}: fetch_k={fetch_k}, "
            f"score_threshold={score_threshold}, returned={len(hits)}"
        )
        return hits

    def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection."""
        try:
            self.client.delete_collection(collection_name=collection_name)
            logger.info(f"Deleted collection: {collection_name}")
            return True
        except Exception as e:
            logger.exception(f"Failed to delete collection {collection_name}")
            raise

    def get_collection_size_cached(self, collection_name: str) -> int:
        """
        Return collection point count with 5-minute in-process cache.

        Avoids a Qdrant HTTP round-trip on every query just to compute fetch_k.
        Falls back to a safe default (300) if Qdrant is unreachable.
        """
        now = time.monotonic()
        entry = _collection_size_cache.get(collection_name)
        if entry is not None:
            size, inserted_at = entry
            if now - inserted_at < _COLLECTION_CACHE_TTL:
                return size

        try:
            info = self.client.get_collection(collection_name)
            size = info.points_count or 0
        except Exception:
            logger.warning("[QdrantService] Could not fetch collection size, defaulting to 300")
            size = 300

        _collection_size_cache[collection_name] = (size, now)
        logger.debug("[QdrantService] collection_size_cached: %s → %d", collection_name, size)
        return size

    def get_collection_stats(self, collection_name: str) -> dict:
        """Get collection statistics."""
        try:
            collection_info = self.client.get_collection(collection_name)
            return {
                "collection_name": collection_name,
                "points_count": collection_info.points_count,
            }
        except Exception:
            logger.exception(f"Failed to get stats for {collection_name}")
            raise

    def health_check(self) -> bool:
        """Check Qdrant server health."""
        try:
            self.client.get_collections()
            logger.info("Qdrant health check passed")
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False


# Singleton instance
_qdrant_service: Optional[QdrantService] = None


def get_qdrant_service(
    host: str = "localhost",
    port: int = 6333,
    api_key: Optional[str] = None,
) -> QdrantService:
    """Get or initialize singleton Qdrant service."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService(host=host, port=port, api_key=api_key)
    return _qdrant_service
