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
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    ChangeAliasesOperation,
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
    Distance,
    PointStruct,
    VectorParams,
)

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
            for idx, (doc, vector) in enumerate(zip(documents, vectors)):
                print(f"Upserting document {idx}: id={doc.get('id', 'N/A')}, vector_length={len(vector)}")
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

    def ensure_collection_multi_vector(
        self,
        collection_name: str,
        vector_size: int,
        distance: Distance = Distance.COSINE,
    ) -> bool:
        """
        Create the multi-vector collection only if it does not already exist.

        Safe to call on every ingestion run — idempotent by design.

        Race condition handling: if two workers start simultaneously and both
        see the collection as absent, one create() will win and the other will
        receive a 'collection already exists' error from Qdrant. We catch that
        specific case and verify the collection is now present, then proceed.

        Returns True if collection already existed, False if it was just created.
        """
        try:
            existing = {c.name for c in self.client.get_collections().collections}
            if collection_name in existing:
                logger.debug("Collection %s already exists — skipping create", collection_name)
                return True

            self.client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "question": VectorParams(size=vector_size, distance=distance),
                    "answer": VectorParams(size=vector_size, distance=distance),
                },
            )
            logger.info("Created multi-vector collection: %s (vector_size=%d)", collection_name, vector_size)
            return False

        except Exception:
            # Another worker may have won the race and created the collection.
            # Verify it now exists before re-raising.
            try:
                existing = {c.name for c in self.client.get_collections().collections}
                if collection_name in existing:
                    logger.warning(
                        "Collection %s create conflict (race) — collection now exists, proceeding",
                        collection_name,
                    )
                    return True
            except Exception:
                pass  # original exception is more informative
            logger.exception("Failed to ensure collection %s", collection_name)
            raise

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

    def create_versioned_collection_name(self, alias_name: str) -> str:
        """Build a physical collection name for blue/green FAQ indexing."""
        safe_alias = alias_name.replace("-", "_").replace(".", "_")
        return f"{safe_alias}__{int(time.time())}__{uuid.uuid4().hex[:8]}"

    def create_collection_multi_vector_if_absent(
        self,
        collection_name: str,
        vector_size: int = 1536,
        distance: Distance = Distance.COSINE,
    ) -> bool:
        """Create a multi-vector collection without deleting any existing collection."""
        existing = {c.name for c in self.client.get_collections().collections}
        if collection_name in existing:
            logger.info("Collection %s already exists; keeping it", collection_name)
            return False

        self.client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "question": VectorParams(size=vector_size, distance=distance),
                "answer": VectorParams(size=vector_size, distance=distance),
            },
        )
        logger.info("Created multi-vector collection: %s (size=%d)", collection_name, vector_size)
        return True

    def get_alias_target(self, alias_name: str) -> str | None:
        """Return physical collection currently attached to alias, if any."""
        aliases = self.client.get_aliases().aliases
        for alias in aliases:
            if alias.alias_name == alias_name:
                return alias.collection_name
        return None

    def swap_alias(self, alias_name: str, new_collection_name: str) -> str | None:
        """Move alias to a new collection. Returns previous collection name."""
        old_collection = self.get_alias_target(alias_name)
        existing_collections = {c.name for c in self.client.get_collections().collections}

        # First migration: the configured name may still be a real collection.
        # Qdrant cannot create an alias with the same name as an existing collection,
        # so delete the legacy collection only after the green collection is ready.
        if old_collection is None and alias_name in existing_collections:
            old_collection = alias_name
            self.client.delete_collection(collection_name=alias_name)
            logger.warning(
                "Deleted legacy collection %s before creating alias with the same name",
                alias_name,
            )

        operations: list[ChangeAliasesOperation] = []
        if old_collection and old_collection != alias_name:
            operations.append(
                DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias_name))
            )
        operations.append(
            CreateAliasOperation(
                create_alias=CreateAlias(
                    collection_name=new_collection_name,
                    alias_name=alias_name,
                )
            )
        )
        self.client.update_collection_aliases(change_aliases_operations=operations)
        logger.info("Swapped Qdrant alias %s: %s -> %s", alias_name, old_collection, new_collection_name)
        return old_collection

    def upsert_multi_vector(
        self,
        collection_name: str,
        documents: list[dict],
        question_vectors: list[list[float]],
        answer_vectors: list[list[float]],
        point_ids: Optional[list[str]] = None,
        batch_size: int = 50,
    ) -> dict:
        """
        Upsert documents with named 'question' and 'answer' vectors in batches.

        Qdrant has a 32 MB HTTP body limit. JSON-encoded float arrays are verbose
        (~15 chars/float), so 290 docs × 2 × 3072 floats ≈ 35 MB in one shot.
        Batching keeps each request well under the limit.

        Args:
            point_ids: Optional list of deterministic UUIDs (same length as documents).
                       When provided, Qdrant will update an existing point with the same
                       ID instead of inserting a duplicate (idempotent upsert).
                       When None, random UUIDs are generated (default for bulk re-index).
            batch_size: Points per upsert request (default 50 ≈ ~5 MB/batch).
        """
        if not (len(documents) == len(question_vectors) == len(answer_vectors)):
            raise ValueError("documents, question_vectors, answer_vectors must have equal length")
        if point_ids is not None and len(point_ids) != len(documents):
            raise ValueError("point_ids must have the same length as documents")

        total_upserted = 0
        n_batches = (len(documents) + batch_size - 1) // batch_size

        for batch_idx in range(n_batches):
            start = batch_idx * batch_size
            end = start + batch_size
            ids_slice = point_ids[start:end] if point_ids is not None else [None] * (end - start)
            batch_points = [
                PointStruct(
                    id=pid if pid is not None else uuid.uuid4(),
                    vector={"question": q_vec, "answer": a_vec},
                    payload=doc,
                )
                for doc, q_vec, a_vec, pid in zip(
                    documents[start:end],
                    question_vectors[start:end],
                    answer_vectors[start:end],
                    ids_slice,
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

        Retrieves top_k*3 from each vector then fuses with Reciprocal Rank Fusion.
        The fused score is normalized to [0,1] and filtered by score_threshold.
        """
        fetch_k = max(top_k * 3, 15)
        try:
            q_results = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                using="question",
                limit=fetch_k,
                with_payload=True,
            )
            a_results = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                using="answer",
                limit=fetch_k,
                with_payload=True,
            )
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

    def get_all_content_hashes(self, collection_name: str) -> dict[str, str]:
        """Scroll all points and return {point_id: content_hash} for incremental sync."""
        hashes: dict[str, str] = {}
        offset = None
        while True:
            result, next_offset = self.client.scroll(
                collection_name=collection_name,
                offset=offset,
                limit=256,
                with_vectors=False,
                with_payload=["metadata"],
            )
            for point in result:
                h = ((point.payload or {}).get("metadata") or {}).get("content_hash", "")
                hashes[str(point.id)] = h
            if next_offset is None:
                break
            offset = next_offset
        return hashes

    def delete_points(self, collection_name: str, point_ids: list[str]) -> None:
        """Delete specific points by ID."""
        from qdrant_client.models import PointIdsList
        self.client.delete(
            collection_name=collection_name,
            points_selector=PointIdsList(points=point_ids),
        )
        logger.info("Deleted %d points from %s", len(point_ids), collection_name)

    def get_collection_stats(self, collection_name: str) -> dict:
        """Get collection statistics."""
        try:
            count_result = self.client.count(collection_name, exact=True)
            return {
                "collection_name": collection_name,
                "points_count": count_result.count,
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
