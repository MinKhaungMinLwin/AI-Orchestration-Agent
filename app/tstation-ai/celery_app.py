import os

from celery import Celery
from redis import Redis

redis = Redis.from_url(
    os.getenv("REDIS_QUEUE_URL"),
    socket_timeout=2,
    socket_connect_timeout=1,
    retry_on_timeout=True,
)

# Celery app
celery_execute = Celery(
    broker=os.getenv("RABBITMQ_URL"),
    backend=os.getenv("REDIS_QUEUE_URL")
)
