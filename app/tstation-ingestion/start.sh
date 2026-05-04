#!/bin/sh
set -e

echo "[ingestion] Running bootstrap from faq_data.json..."
uv run python main.py

echo "[ingestion] Starting Celery worker..."
exec uv run python -m celery -A celery_app worker --loglevel=info -Q faq_sync
