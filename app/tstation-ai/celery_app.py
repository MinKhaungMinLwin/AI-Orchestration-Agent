import os

from celery import Celery
from redis import Redis

redis = Redis.from_url(
    os.getenv("REDIS_URL"),
    socket_timeout=0.3,
    socket_connect_timeout=0.3,
    retry_on_timeout=False,
)

# Celery app
celery_execute = Celery(
    broker=os.getenv("RABBITMQ_URL"),
    backend=os.getenv("REDIS_URL")
)
