import logging
import os
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


def init_services():
    """Fail fast if Qdrant or the embedding backend is unreachable."""
    from config.env import settings
    from rag.embedding_service import get_embedding_service
    from rag.qdrant_service import get_qdrant_service

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


def main():
    """ENTRYPOINT — reconcile the two hand-edited FAQ files into Qdrant on startup.

    faq_data.json and local_faq.json are both human-owned; they are merged by `id`
    (local_faq wins on collision) and layered on top of the Oracle FAQ set that the
    periodic `faq_fetch_task` maintains. On every container start we upsert only the
    entries whose content changed (content-hash diff inside `_run_incremental_sync`),
    so the deploy flow "edit a FAQ file → rebuild/redeploy" refreshes exactly those
    points — no manual re-embed, no waiting for the beat cycle.

    `delete_scope=FILE_FAQ_SOURCES`: this sync owns the file-backed points, so
    removing an entry from a file also removes it from Qdrant. Oracle-sourced
    points are outside the scope and are never touched here.
    """
    logger.info("Starting FAQ reconcile from faq_data.json + local_faq.json")

    from config.env import settings
    from faq_dataset import FILE_FAQ_SOURCES, load_file_faq_documents
    from tasks.faq_sync_task import _run_incremental_sync

    # Fail fast on unhealthy dependencies before doing any work.
    init_services()

    documents = load_file_faq_documents()
    if not documents:
        logger.info("No FAQ files found — nothing to reconcile")
        return

    result = _run_incremental_sync(
        documents,
        settings.QDRANT_COLLECTION_FAQ,
        delete_scope=FILE_FAQ_SOURCES,
    )
    logger.info(
        "FAQ file reconcile complete: upserted=%d deleted=%d collection=%s",
        result.get("upserted_count", 0),
        result.get("deleted_count", 0),
        result.get("collection_name", ""),
    )


if __name__ == "__main__":
    main()
