import os

from celery import Celery
from redis import Redis

redis = Redis.from_url(
    os.getenv("REDIS_QUEUE_URL"),
    socket_timeout=0.3,
    socket_connect_timeout=0.3,
    retry_on_timeout=False,
)

celery_app = Celery(
    "ingestion",
    broker=os.getenv("RABBITMQ_URL"),
    backend=os.getenv("REDIS_QUEUE_URL"),
    include=["tasks.faq_sync_task"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Acknowledge task only after it completes (prevents lost tasks on worker crash)
    task_acks_late=True,
    # Process one task at a time per worker to avoid OOM during large embedding batches
    worker_prefetch_multiplier=1,
)
