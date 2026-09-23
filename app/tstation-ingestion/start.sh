#!/bin/sh
set -e

chmod 755 /app/data

echo "[ingestion] Reconciling FAQ files (faq_data.json + local_faq.json) into Qdrant..."
uv run python main.py

echo "[ingestion] Starting Celery beat scheduler..."
uv run python -m celery -A celery_app beat --loglevel=info &

echo "[ingestion] Starting Celery worker..."
exec uv run python -m celery -A celery_app worker --loglevel=info -Q faq_sync
