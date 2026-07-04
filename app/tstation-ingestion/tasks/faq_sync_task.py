"""
Celery task: faq_sync_task

Consumes FAQ documents pushed by tstation-ai, embeds them, and upserts
into the Qdrant multi-vector collection with deterministic point IDs for
idempotency (same FAQ id → same Qdrant point ID → update, not duplicate).
"""

import hashlib
import json
import logging
import os
import tempfile
import time
import uuid

from celery_app import celery_app, redis as task_redis
from faq_dataset import PRIMARY_FAQ_FILE, apply_local_overlay

_DATA_FILE = PRIMARY_FAQ_FILE

logger = logging.getLogger(__name__)

_TASK_TTL = 8 * 3600  # Redis key TTL: 8 hours


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _faq_point_id(faq_id: str | int) -> str:
    """Deterministic UUID v5 from FAQ id — enables idempotent Qdrant upsert."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, str(faq_id)))


def _content_hash(question: str, answer: str) -> str:
    """MD5 fingerprint of question+answer — detects content changes for incremental sync."""
    return hashlib.md5(f"{question}\n{answer}".encode()).hexdigest()


def _update_redis_status(task_id: str, status: str, result: dict | None = None, error: str | None = None):
    """
    Patch the QueueRes JSON blob in Redis to reflect current task status.
    Writes only valid fields so the tstation-ai queue endpoint can read it.
    """
    raw = task_redis.get(task_id)
    if raw is None:
        logger.warning("[faq_sync_task] task_id %s not found in Redis, skipping status update", task_id)
        return

    try:
        data = json.loads(raw)
        data["status"] = status
        now = int(time.time())

        if data.get("metadata") and data["metadata"].get("time"):
            data["metadata"]["time"]["end"] = now
            start = data["metadata"]["time"].get("start", now)
            data["metadata"]["time"]["total"] = now - start

        if result is not None:
            data["result"] = {"status_code": 200, "data": result, "error": None}
        elif error is not None:
            data["result"] = {"status_code": 500, "data": None, "error": {"message": error}}

        # Append pipeline log entry
        log_entry = {"status": status, "timestamp": now}
        logs = data.setdefault("metadata", {}).setdefault("logs_task", {})
        logs.setdefault("pipeline", []).append(log_entry)

        task_redis.set(task_id, json.dumps(data), ex=_TASK_TTL)
    except Exception:
        logger.exception("[faq_sync_task] Failed to update Redis status for task %s", task_id)


# ---------------------------------------------------------------------------
# Local persistence (keeps bootstrap in sync with API updates)
# ---------------------------------------------------------------------------

def _persist_faq_data(documents: list[dict]) -> None:
    """
    Atomically overwrite the local FAQ data file with the latest documents.

    Uses write-to-temp + os.replace() so the file is never partially written.
    After this call, the next service restart will bootstrap from the updated data.
    """
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=_DATA_FILE.parent, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(documents, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, _DATA_FILE)
        logger.info("[faq_sync_task] Persisted %d documents to %s", len(documents), _DATA_FILE)
    except Exception:
        # Clean up temp file if something went wrong
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Core ingestion logic (separated for testability)
# ---------------------------------------------------------------------------

def _run_ingestion(documents: list[dict], collection_name: str) -> dict:
    """Embed documents and upsert into Qdrant. Returns result dict."""
    from config.env import settings
    from rag.document_processor import DocumentProcessor
    from rag.embedding_service import get_embedding_service
    from rag.qdrant_service import get_qdrant_service

    api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY

    embedding_svc = get_embedding_service(
        model=settings.EMBEDDING_MODEL,
        provider=settings.EMBEDDING_PROVIDER,
        api_key=api_key,
    )
    qdrant_svc = get_qdrant_service(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        api_key=settings.QDRANT_API_KEY or None,
    )

    # Keep the local overlay indexed even when the primary FAQ data is refreshed
    # via API sync or periodic fetch.
    documents = apply_local_overlay(documents)

    # Normalise to unified schema — resolves representative_question/question,
    # representative_answer/answer, and fills in missing metadata fields.
    documents = [DocumentProcessor._normalize_document(doc, idx) for idx, doc in enumerate(documents)]

    # Build embedding input texts
    question_texts, answer_texts = [], []
    for doc in documents:
        q, a = DocumentProcessor.build_embedding_texts(doc)
        question_texts.append(q)
        answer_texts.append(a)

    # Single batched embedding call (question + answer interleaved by concat)
    all_texts = question_texts + answer_texts
    embeddings = embedding_svc.embed_texts(all_texts)
    q_vecs = embeddings[: len(documents)]
    a_vecs = embeddings[len(documents) :]

    # Blue/green indexing: build a fresh physical collection first, then swap
    # the stable alias only after the new collection is fully populated.
    alias_name = collection_name
    target_collection = qdrant_svc.create_versioned_collection_name(alias_name)
    qdrant_svc.create_collection_multi_vector_if_absent(
        collection_name=target_collection,
        vector_size=embedding_svc.get_embedding_dimension(),
    )
    qdrant_svc.ensure_payload_text_index(target_collection, "question")

    # Build slim payloads + deterministic point IDs
    slim_docs: list[dict] = []
    point_ids: list[str] = []
    for doc in documents:
        meta = dict(doc.get("metadata", {}))
        meta["keywords_normalized"] = DocumentProcessor.normalize_keywords(
            meta.get("keywords", [])
        )
        meta["content_hash"] = _content_hash(doc.get("question", ""), doc.get("answer", ""))
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

    stats = qdrant_svc.get_collection_stats(target_collection)
    indexed_count = stats.get("points_count") or 0
    expected_count = len(set(point_ids))
    if indexed_count != expected_count:
        qdrant_svc.delete_collection(target_collection)
        raise RuntimeError(
            f"Indexed count mismatch for {target_collection}: "
            f"expected={expected_count} actual={indexed_count}"
        )

    old_collection = qdrant_svc.swap_alias(alias_name, target_collection)
    if old_collection and old_collection != target_collection:
        qdrant_svc.delete_collection(old_collection)
        logger.info("[_run_ingestion] Deleted old collection: %s", old_collection)
    result.update(
        {
            "alias_name": alias_name,
            "collection_name": target_collection,
            "previous_collection_name": old_collection,
        }
    )
    return result


# ---------------------------------------------------------------------------
# Incremental sync (periodic fetch: only embed/upsert what changed)
# ---------------------------------------------------------------------------

def _run_incremental_sync(
    documents: list[dict],
    collection_name: str,
    delete_missing: bool = True,
) -> dict:
    """
    Incremental FAQ sync: only embed and upsert changed/new docs, delete removed ones when safe.
    Falls back to full _run_ingestion if the target collection does not exist yet.
    """
    from config.env import settings
    from rag.document_processor import DocumentProcessor
    from rag.embedding_service import get_embedding_service
    from rag.qdrant_service import get_qdrant_service

    qdrant_svc = get_qdrant_service(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        api_key=settings.QDRANT_API_KEY or None,
    )

    # Resolve live collection from alias (or direct name)
    live_collection = qdrant_svc.get_alias_target(collection_name)
    if live_collection is None:
        existing = {c.name for c in qdrant_svc.client.get_collections().collections}
        if collection_name not in existing:
            logger.info("[incremental_sync] Collection absent — running full ingestion")
            return _run_ingestion(documents, collection_name)
        live_collection = collection_name

    qdrant_svc.ensure_payload_text_index(live_collection, "question")

    # Keep the local overlay indexed even when the fetched base FAQ set changes.
    documents = apply_local_overlay(documents)
    documents = [DocumentProcessor._normalize_document(doc, idx) for idx, doc in enumerate(documents)]

    # Build incoming map: point_id → entry
    incoming: dict[str, dict] = {}
    for doc in documents:
        meta = dict(doc.get("metadata", {}))
        meta["keywords_normalized"] = DocumentProcessor.normalize_keywords(meta.get("keywords", []))
        c_hash = _content_hash(doc.get("question", ""), doc.get("answer", ""))
        meta["content_hash"] = c_hash
        q_text, a_text = DocumentProcessor.build_embedding_texts(doc)
        point_id = _faq_point_id(doc.get("id"))
        incoming[point_id] = {
            "slim_doc": {
                "id": doc.get("id"),
                "question": doc.get("question", ""),
                "answer": doc.get("answer", ""),
                "metadata": meta,
            },
            "q_text": q_text,
            "a_text": a_text,
            "content_hash": c_hash,
        }

    # Compare with existing hashes in Qdrant
    existing_hashes = qdrant_svc.get_all_content_hashes(live_collection)
    to_upsert = [pid for pid, v in incoming.items() if existing_hashes.get(pid) != v["content_hash"]]
    to_delete = [pid for pid in existing_hashes if pid not in incoming] if delete_missing else []

    logger.info(
        "[incremental_sync] total=%d upsert=%d delete=%d unchanged=%d delete_missing=%s",
        len(incoming),
        len(to_upsert),
        len(to_delete),
        len(incoming) - len(to_upsert),
        delete_missing,
    )

    if not to_upsert and not to_delete:
        logger.info("[incremental_sync] No changes detected — skipping OpenAI + Qdrant writes")
        return {"status": "success", "collection_name": live_collection, "upserted_count": 0, "deleted_count": 0}

    result: dict = {"collection_name": live_collection, "upserted_count": 0, "deleted_count": 0}

    if to_upsert:
        api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY
        embedding_svc = get_embedding_service(
            model=settings.EMBEDDING_MODEL,
            provider=settings.EMBEDDING_PROVIDER,
            api_key=api_key,
        )
        entries = [incoming[pid] for pid in to_upsert]
        all_texts = [e["q_text"] for e in entries] + [e["a_text"] for e in entries]
        embeddings = embedding_svc.embed_texts(all_texts)
        q_vecs = embeddings[: len(to_upsert)]
        a_vecs = embeddings[len(to_upsert) :]

        upsert_result = qdrant_svc.upsert_multi_vector(
            collection_name=live_collection,
            documents=[e["slim_doc"] for e in entries],
            question_vectors=q_vecs,
            answer_vectors=a_vecs,
            point_ids=to_upsert,
            batch_size=50,
        )
        result["upserted_count"] = upsert_result.get("upserted_count", 0)

    if to_delete:
        qdrant_svc.delete_points(live_collection, to_delete)
        result["deleted_count"] = len(to_delete)

    return result


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    name="faq_sync_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="faq_sync",
)
def faq_sync_task(self, task_id: str, documents: list[dict], collection_name: str):
    """
    Async FAQ ingestion task.

    Args:
        task_id: QueueRes task_id (for Redis status updates)
        documents: List of FAQ dicts with id, question, answer, metadata
        collection_name: Target Qdrant collection name
    """
    logger.info(
        "[faq_sync_task] START task_id=%s documents=%d collection=%s",
        task_id, len(documents), collection_name,
    )

    _update_redis_status(task_id, "PROCESSING")

    try:
        result = _run_ingestion(documents, collection_name)
        _persist_faq_data(documents)

        logger.info(
            "[faq_sync_task] SUCCESS task_id=%s upserted=%d",
            task_id, result.get("upserted_count", 0),
        )
        _update_redis_status(task_id, "SUCCESS", result=result)
        return result

    except Exception as exc:
        logger.exception("[faq_sync_task] FAILED task_id=%s", task_id)

        if self.request.retries < self.max_retries:
            logger.info(
                "[faq_sync_task] Retrying task_id=%s (attempt %d/%d)",
                task_id, self.request.retries + 1, self.max_retries,
            )
            raise self.retry(exc=exc)

        _update_redis_status(task_id, "FAILURE", error=str(exc))
        raise
