"""
Qdrant Vector Store Service for RAG operations.

Provides interface for:
- Collection management (create, delete, get stats)
- Document indexing (upsert vectors)
- Similarity search
"""

import logging
import uuid
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

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
    ) -> list[dict]:
        """
        Search for similar documents in collection.

        Args:
            collection_name: Collection name
            query_vector: Query embedding vector
            top_k: Number of results to return
            score_threshold: Minimum similarity score (0-1)

        Returns:
            List of results with similarity scores and payloads
        """
        try:
            # results = self.client.search(
            #     collection_name=collection_name,
            #     query_vector=query_vector,
            #     limit=top_k,
            #     score_threshold=score_threshold,
            # )

            results = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=top_k,
                with_payload=True,
                # score_threshold=score_threshold,
            )

            print(f"Raw search results: {results}")
            print(f"Type of results returned: {type(results)}")
            print(f"Number of results returned: {len(results.points)}")

            hits = []
            for result in results.points:
                hit = {
                    "id": result.id,
                    "score": result.score,
                    "payload": result.payload,
                }
                hits.append(hit)

            logger.info(
                f"Search in {collection_name}: query_vector_size={len(query_vector)}, "
                f"top_k={top_k}, results={len(hits)}"
            )
            return hits
        except Exception as e:
            logger.exception(f"Failed to search in {collection_name}")
            raise

    def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection."""
        try:
            self.client.delete_collection(collection_name=collection_name)
            logger.info(f"Deleted collection: {collection_name}")
            return True
        except Exception as e:
            logger.exception(f"Failed to delete collection {collection_name}")
            raise

    def get_collection_stats(self, collection_name: str) -> dict:
        """Get collection statistics."""
        try:
            collection_info = self.client.get_collection(collection_name)
            print(f"Collection info: {collection_info}")
            print(f"Collection points count: {collection_info.model_dump()}")
            return {
                "collection_name": collection_name,
                "points_count": collection_info.points_count,
                # "vectors_count": collection_info.vectors_count,
                # "vectors_count": (
                #     collection_info.config.params.vectors.size
                #     if hasattr(collection_info.config.params, "vectors")
                #     else None
            # ),
            }
        except Exception as e:
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
