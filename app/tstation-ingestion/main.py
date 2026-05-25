import json
import os
import logging
from pathlib import Path

# Load env
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent.parent
env_file = project_root / ".env"

if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

BASE_DIR = Path(__file__).parent
logger = logging.getLogger("ingestion")

def load_documents():
    """Load and normalise FAQ data from the local data file."""
    from rag.document_processor import DocumentProcessor

    data_path = BASE_DIR / "data" / "faq_data.json"
    with open(data_path, "r", encoding="utf-8") as f:
        raw_docs = json.load(f)

    documents = [DocumentProcessor._normalize_document(doc, idx) for idx, doc in enumerate(raw_docs)]
    logger.info(f"Loaded {len(documents)} documents")
    return documents


def init_services():
    """Initialize Qdrant + Embedding."""
    from rag.qdrant_service import get_qdrant_service
    from rag.embedding_service import get_embedding_service

    from config.env import settings

    qdrant_svc = get_qdrant_service(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
    )

    api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY

    embedding_svc = get_embedding_service(
        model=settings.EMBEDDING_MODEL,
        provider=settings.EMBEDDING_PROVIDER,
        api_key=api_key,
    )

    if not qdrant_svc.health_check():
        raise RuntimeError("Qdrant is not available")

    if not embedding_svc.health_check():
        raise RuntimeError("Embedding service is not available")

    return qdrant_svc, embedding_svc


def build_embeddings(documents, embedding_svc):
    """Convert documents → embeddings."""
    from rag.document_processor import DocumentProcessor

    question_texts = []
    answer_texts = []

    for doc in documents:
        q, a = DocumentProcessor.build_embedding_texts(doc)
        question_texts.append(q)
        answer_texts.append(a)

    # Warn about documents that produced empty embedding texts
    empty_q = [i for i, t in enumerate(question_texts) if not t.strip()]
    empty_a = [i for i, t in enumerate(answer_texts) if not t.strip()]
    if empty_q:
        logger.warning(f"build_embeddings: {len(empty_q)} document(s) have empty question text at indices {empty_q}")
    if empty_a:
        logger.warning(f"build_embeddings: {len(empty_a)} document(s) have empty answer text at indices {empty_a}")

    all_texts = question_texts + answer_texts
    embeddings = embedding_svc.embed_texts(all_texts)

    return (
        embeddings[: len(documents)],       # question
        embeddings[len(documents) :],       # answer
    )


def upsert_to_qdrant(qdrant_svc, documents, q_vecs, a_vecs, embedding_svc):
    """Push data into Qdrant using blue/green alias swap."""
    from config.env import settings
    from rag.document_processor import DocumentProcessor
    from tasks.faq_sync_task import _faq_point_id

    vector_size = embedding_svc.get_embedding_dimension()
    alias_name = settings.QDRANT_COLLECTION_FAQ
    target_collection = qdrant_svc.create_versioned_collection_name(alias_name)

    qdrant_svc.create_collection_multi_vector_if_absent(
        collection_name=target_collection,
        vector_size=vector_size,
    )
    qdrant_svc.ensure_payload_text_index(target_collection, "question")

    slim_docs = []
    point_ids = []

    for doc in documents:
        meta = dict(doc.get("metadata", {}))
        meta["keywords_normalized"] = DocumentProcessor.normalize_keywords(
            meta.get("keywords", [])
        )

        slim_docs.append(
            {
                "id": doc.get("id"),
                "question": doc.get("question", ""),
                "answer": doc.get("answer", ""),
                "metadata": meta,
            }
        )
        point_ids.append(_faq_point_id(doc.get("id")))

    result = qdrant_svc.upsert_multi_vector(
        collection_name=target_collection,
        documents=slim_docs,
        question_vectors=q_vecs,
        answer_vectors=a_vecs,
        point_ids=point_ids,
        batch_size=50,
    )

    old_collection = qdrant_svc.swap_alias(alias_name, target_collection)
    if old_collection and old_collection != target_collection:
        qdrant_svc.delete_collection(old_collection)
    logger.info(
        "Indexed %d documents and moved alias %s: %s -> %s",
        result["upserted_count"],
        alias_name,
        old_collection,
        target_collection,
    )


def collection_has_data(qdrant_svc, collection_name: str) -> bool:
    """Return True if the collection exists and contains at least one point."""
    try:
        stats = qdrant_svc.get_collection_stats(collection_name)
        count = stats.get("points_count") or 0
        return count > 0
    except Exception:
        return False


def main():
    """ENTRYPOINT - ingestion pipeline"""
    logger.info("Starting ingestion bootstrap check")

    from config.env import settings

    # Init services first so we can query Qdrant state
    qdrant_svc, embedding_svc = init_services()

    if collection_has_data(qdrant_svc, settings.QDRANT_COLLECTION_FAQ):
        logger.info(
            "Collection '%s' already has data — skipping bootstrap. "
            "Qdrant state is the source of truth.",
            settings.QDRANT_COLLECTION_FAQ,
        )
        return

    logger.info("Collection is empty — running bootstrap from faq_data.json")

    # 1. Load data
    documents = load_documents()

    # 2. Embed
    q_vecs, a_vecs = build_embeddings(documents, embedding_svc)

    # 3. Upsert
    upsert_to_qdrant(qdrant_svc, documents, q_vecs, a_vecs, embedding_svc)

    logger.info("Bootstrap completed successfully")


if __name__ == "__main__":
    main()