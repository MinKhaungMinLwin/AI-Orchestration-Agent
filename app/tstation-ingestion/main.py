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
    """ENTRYPOINT — reconcile the local_faq.json overlay into Qdrant on startup.

    local_faq.json is the LOCAL OVERLAY: the FAQ base is fetched from Oracle by
    the periodic `faq_fetch_task`; local_faq.json is merged on top by `id`.
    On every container start we upsert only the overlay entries whose content
    changed (content-hash diff inside `_run_incremental_sync`), so the deploy
    flow "edit local_faq.json → rebuild/redeploy" is enough to refresh exactly
    those points — no manual re-embed, no waiting for the beat cycle.

    `delete_missing=False`: never touch Oracle-sourced base points. (Removing an
    entry from local_faq.json therefore does NOT delete it from Qdrant here — a
    full Oracle fetch reconciles deletions.) Unchanged overlay → zero writes.
    """
    logger.info("Starting FAQ overlay reconcile from local_faq.json")

    from config.env import settings
    from faq_dataset import load_local_overlay_documents
    from tasks.faq_sync_task import _run_incremental_sync

    # Fail fast on unhealthy dependencies before doing any work.
    init_services()

    overlay = load_local_overlay_documents()
    if not overlay:
        logger.info("No local_faq.json overlay found — nothing to reconcile")
        return

    result = _run_incremental_sync(
        overlay,
        settings.QDRANT_COLLECTION_FAQ,
        delete_missing=False,
    )
    logger.info(
        "Overlay reconcile complete: upserted=%d collection=%s",
        result.get("upserted_count", 0),
        result.get("collection_name", ""),
    )


if __name__ == "__main__":
    main()
