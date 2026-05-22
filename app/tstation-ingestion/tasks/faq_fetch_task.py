"""
Celery Beat task: faq_fetch_task

Periodically fetches all FAQ data from tstation-be (Oracle DB source of truth)
and re-ingests it into Qdrant, keeping vector search in sync automatically.

Schedule is controlled by FAQ_SYNC_INTERVAL_SECONDS (default: 3600).
Requires TSTATION_BE_BASE_URL to be set; skips silently if missing.
"""

import logging
import uuid

import httpx
from celery_app import celery_app
from tasks.faq_sync_task import _persist_faq_data, _run_ingestion

logger = logging.getLogger(__name__)

_FAQ_BE_PATH = "/api/faq"
_FAQ_FETCH_LIMIT = 200
_FAQ_FETCH_TIMEOUT = 30


def _stable_faq_id(question: str) -> str:
    """Deterministic UUID5 from question text — same question maps to the same Qdrant point ID."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, question))


def _fetch_faq_from_be(base_url: str, token: str = "") -> list[dict]:
    """
    Fetch all FAQ items from tstation-be and map to the ingestion schema expected
    by _run_ingestion (same format as faq_data.json documents).

    tstation-be FaqItem fields:
        cust_quest   → question
        pc_ans_cont  → answer
        lrcl_cd      → metadata.category_lv1
        mdcl_cd      → metadata.category_lv2
    """
    url = base_url.rstrip("/") + _FAQ_BE_PATH
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = httpx.get(url, params={"limit": _FAQ_FETCH_LIMIT}, timeout=_FAQ_FETCH_TIMEOUT, headers=headers)
    response.raise_for_status()

    items = response.json().get("items", [])
    documents = []
    for item in items:
        question = (item.get("cust_quest") or "").strip()
        if not question:
            continue
        documents.append(
            {
                "id": _stable_faq_id(question),
                "question": question,
                "answer": (item.get("pc_ans_cont") or "").strip(),
                "metadata": {
                    "category_lv1": item.get("lrcl_cd") or "",
                    "category_lv2": item.get("mdcl_cd") or "",
                    "source": "tstation-be",
                    "lang": "ko",
                    "document_type": "faq_qa",
                },
            }
        )

    logger.info("[faq_fetch_task] Fetched %d FAQ documents from %s", len(documents), url)
    return documents


@celery_app.task(
    name="faq_fetch_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="faq_sync",
)
def faq_fetch_task(self):
    """Periodic task: pull FAQ from tstation-be and sync into Qdrant."""
    from config.env import settings

    base_url = settings.TSTATION_BE_API
    if not base_url:
        logger.warning("[faq_fetch_task] TSTATION_BE_API not configured — skipping sync")
        return

    logger.info("[faq_fetch_task] Starting periodic FAQ sync from %s", base_url)

    try:
        documents = _fetch_faq_from_be(base_url, token=settings.JWT_TOKEN)
    except Exception as exc:
        logger.exception("[faq_fetch_task] Failed to fetch FAQ from tstation-be")
        raise self.retry(exc=exc)

    if not documents:
        logger.warning("[faq_fetch_task] No FAQ documents returned — skipping ingestion")
        return

    try:
        result = _run_ingestion(documents, settings.QDRANT_COLLECTION_FAQ)
    except Exception as exc:
        logger.exception("[faq_fetch_task] Ingestion failed")
        raise self.retry(exc=exc)

    try:
        _persist_faq_data(documents)
    except Exception:
        logger.warning("[faq_fetch_task] Could not persist faq_data.json — skipping file backup")

    logger.info(
        "[faq_fetch_task] Sync complete: upserted=%d collection=%s",
        result.get("upserted_count", 0),
        result.get("collection_name", ""),
    )
