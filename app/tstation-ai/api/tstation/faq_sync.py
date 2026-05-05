"""
FAQ Sync API - Trigger async FAQ ingestion into Qdrant vector store.

Endpoint:
- POST /api/tstation/faq/sync  - Queue FAQ documents for embedding + Qdrant upsert
"""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Security

from celery_app import celery_execute
from config.env import settings
from config.sec import get_api_key
from schemas.queue import QueueRes
from schemas.tstation.faq_sync import FAQItem, FAQSyncResponse

logger = logging.getLogger(__name__)
router = APIRouter()

_FAQ_SYNC_QUEUE = "faq_sync"
_FAQ_SYNC_TASK = "faq_sync_task"
_MAX_ITEMS_PER_REQUEST = 500


@router.post("/sync", dependencies=[Depends(get_api_key)])
async def sync_faq(
    items: Annotated[list[FAQItem], Body(min_length=1)],
    collection_name: Annotated[Optional[str], Query()] = None,
    user: dict = Security(get_api_key),
) -> FAQSyncResponse:
    """
    Queue FAQ documents for async embedding and Qdrant upsert.

    Upsert is idempotent: submitting the same FAQ `id` updates the existing
    vector point rather than creating a duplicate.

    Parameters:
    - Header:
        - Authorization (str): Bearer JWT token

    - Body (JSON array): list of FAQ items to sync (max 500)

    - Query:
        - collection_name (str | None): Override Qdrant collection name

    Returns:
        - task_id (str): Poll status via GET /queue/{task_id}
        - status (str): "PENDING"
        - total_items (int): Number of items queued
    """
    if len(items) > _MAX_ITEMS_PER_REQUEST:
        raise HTTPException(
            status_code=422,
            detail=f"Too many items: {len(items)} > {_MAX_ITEMS_PER_REQUEST}. Split into smaller batches.",
        )

    resolved_collection = collection_name or settings.QDRANT_COLLECTION_FAQ
    logger.info(
        "[REDIS_LOG] Received sync request from user=%s with %d items for collection=%s",
        user.get("user_id"), len(items), resolved_collection,
    )

    # Create queue tracking entry (saves NEW → PENDING in Redis)
    queue_res = QueueRes.new(queue_name=_FAQ_SYNC_QUEUE, task_name=_FAQ_SYNC_TASK)
    logger.info("[REDIS_LOG] Created queue task %s for user %s with %d items (collection: %s)",
                queue_res.task_id, user.get("user_id"), len(items), resolved_collection)
    queue_res.pending()

    # Serialize FAQ items for Celery (pydantic → plain dict)
    documents = [item.model_dump() for item in items]

    logger.info(
        "[REDIS_LOG] user=%s task_id=%s items=%d collection=%s",
        user.get("user_id"), queue_res.task_id, len(documents), resolved_collection,
    )

    # Fire-and-forget: ingestion worker picks this up from RabbitMQ
    celery_execute.send_task(
        _FAQ_SYNC_TASK,
        kwargs={
            "task_id": queue_res.task_id,
            "documents": documents,
            "collection_name": resolved_collection,
        },
        queue=_FAQ_SYNC_QUEUE,
    )

    return FAQSyncResponse(
        task_id=queue_res.task_id,
        status="PENDING",
        total_items=len(documents),
    )
