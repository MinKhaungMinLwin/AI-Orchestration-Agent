"""pytest config — make app/tstation-ai/ importable so tests can do
``from services.tstation.qc_verifier import ...`` without setting PYTHONPATH.
"""
import os
import sys
from pathlib import Path

# Stub the Settings (config/env.py) fields that are NOT in the local .env so
# tests that transitively import `config.env` (e.g. via `services.tstation.
# template_mapper` → `services.tstation.common.cta_urls`) can build the
# BaseSettings instance during collection. Real values are not needed because
# tests do not exercise these code paths — only construction must succeed.
_ENV_STUBS = {
    # Application
    "PROJECT_NAME": "tstation-ai-test",
    "ROOT_PATH": "/api",
    "API_SECRET_KEY": "stub",
    "TSTATION_BE_API": "http://stub",
    "TSTATION_BE_MCP": "http://stub",
    # AI Gateway / Models
    "AI_DEFAULT_PROVIDER": "openai",
    "AI_GATEWAY_BASE_URL": "http://stub",
    "AI_GATEWAY_API_KEY": "stub",
    "AI_MODEL": "stub",
    "AI_MODEL_REASONING": "stub",
    "AI_MODEL_MINI": "stub",
    "AI_MODEL_LEADING_AGENT": "stub",
    "AI_MODEL_QC_AGENT": "stub",
    "AI_MODEL_TRANSACTION_AGENT": "stub",
    "UPSTAGE_API_KEY": "stub",
    "OPENAI_API_KEY": "stub",
    # Redis
    "REDIS_CONVERSATION_MANAGEMENT_PASSWORD": "stub",
    "REDIS_CONVERSATION_MANAGEMENT_URL": "redis://stub",
    "REDIS_QUEUE_URL": "redis://stub",
    "REDIS_PASSWORD": "stub",
    "REDIS_URL": "redis://stub",
    # RabbitMQ
    "RABBITMQ_NODENAME": "stub",
    "RABBITMQ_USERNAME": "stub",
    "RABBITMQ_PASSWORD": "stub",
    "RABBITMQ_URL": "amqp://stub",
    "RABBITMQ_URL_MANAGEMENT": "http://stub",
    # AWS
    "AWS_ACCESS_KEY_ID": "stub",
    "AWS_SECRET_ACCESS_KEY": "stub",
    "AWS_DEFAULT_REGION": "ap-northeast-2",
    "S3_BUCKET_NAME": "stub",
    # Monitoring
    "GF_SECURITY_ADMIN_USER": "stub",
    "GF_SECURITY_ADMIN_PASSWORD": "stub",
    "LOKI_URL": "http://stub",
    "PROMETHEUS_URL": "http://stub",
    "LANGFUSE_HOST": "http://stub",
    "LANGFUSE_PROJECT_NAME": "stub",
    "LANGFUSE_SECRET_KEY": "stub",
    "LANGFUSE_PUBLIC_KEY": "stub",
}
for _k, _v in _ENV_STUBS.items():
    os.environ.setdefault(_k, _v)

_APP_ROOT = Path(__file__).resolve().parent.parent  # app/tstation-ai/
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))
