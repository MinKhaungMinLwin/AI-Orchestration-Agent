from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

_TEST_ENV_DEFAULTS = {
    "PROJECT_NAME": "test",
    "ROOT_PATH": "",
    "API_SECRET_KEY": "secret",
    "TSTATION_BE_API": "http://localhost",
    "TSTATION_BE_MCP": "http://localhost",
    "AI_DEFAULT_PROVIDER": "openai",
    "AI_GATEWAY_BASE_URL": "http://localhost/v1",
    "AI_GATEWAY_API_KEY": "test",
    "AI_MODEL": "gpt-test",
    "AI_MODEL_REASONING": "gpt-test",
    "AI_MODEL_MINI": "gpt-test",
    "AI_MODEL_LEADING_AGENT": "gpt-test",
    "AI_MODEL_QC_AGENT": "gpt-test",
    "AI_MODEL_TRANSACTION_AGENT": "gpt-test",
    "UPSTAGE_API_KEY": "test",
    "OPENAI_API_KEY": "test",
    "REDIS_CONVERSATION_MANAGEMENT_PASSWORD": "",
    "REDIS_CONVERSATION_MANAGEMENT_URL": "redis://localhost:6379/0",
    "REDIS_QUEUE_URL": "redis://localhost:6379/1",
    "REDIS_PASSWORD": "",
    "REDIS_URL": "redis://localhost:6379/0",
    "RABBITMQ_NODENAME": "rabbit@test",
    "RABBITMQ_USERNAME": "guest",
    "RABBITMQ_PASSWORD": "guest",
    "RABBITMQ_URL": "amqp://guest:guest@localhost:5672/",
    "RABBITMQ_URL_MANAGEMENT": "http://localhost:15672",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
    "AWS_DEFAULT_REGION": "ap-northeast-2",
    "S3_BUCKET_NAME": "test",
    "GF_SECURITY_ADMIN_USER": "admin",
    "GF_SECURITY_ADMIN_PASSWORD": "admin",
    "LOKI_URL": "http://localhost",
    "PROMETHEUS_URL": "http://localhost",
    "LANGFUSE_HOST": "http://localhost",
    "LANGFUSE_PROJECT_NAME": "test",
    "LANGFUSE_SECRET_KEY": "test-secret",
    "LANGFUSE_PUBLIC_KEY": "test-public",
}

for key, value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(key, value)

from services.tstation import quota_service  # noqa: E402


def test_record_monthly_tokens_increments_redis_and_posts_score():
    with patch.object(quota_service, "add_monthly_tokens", return_value=364_790) as mock_add, \
            patch.object(quota_service, "post_langfuse_score") as mock_score:
        new_total = quota_service.record_monthly_tokens("M200012931", 413, "trace-abc", 2_000_000)

    assert new_total == 364_790
    mock_add.assert_called_once_with("M200012931", 413)
    mock_score.assert_called_once()
    args, _ = mock_score.call_args
    assert args[0] == "trace-abc"
    assert args[1] == "monthly_tokens_used"
    assert args[2] == 364_790.0
    assert "364,790" in args[3] and "2,000,000" in args[3]


def test_reconcile_user_from_langfuse_overwrites_redis_with_real_total():
    fake_redis = MagicMock()
    fake_response = MagicMock()
    fake_response.data = [{"sum_totalTokens": 5_820_000}]
    fake_metrics_client = MagicMock()
    fake_metrics_client.metrics.metrics.return_value = fake_response

    with patch("langfuse.api.client.FernLangfuse", return_value=fake_metrics_client) as mock_client_cls, \
            patch("services.tstation.chat_history_service.get_redis_client", return_value=fake_redis):
        real_total = quota_service.reconcile_user_from_langfuse("M200012890")

    assert real_total == 5_820_000
    mock_client_cls.assert_called_once()
    fake_redis.set.assert_called_once()
    (key, value), kwargs = fake_redis.set.call_args
    assert key.startswith("quota:tokens:M200012890:")
    assert value == 5_820_000
    assert kwargs["ex"] > 0

    query = json.loads(fake_metrics_client.metrics.metrics.call_args.kwargs["query"])
    assert query["view"] == "observations"
    assert query["metrics"] == [{"measure": "totalTokens", "aggregation": "sum"}]
    assert query["filters"] == [{"column": "userId", "operator": "=", "value": "M200012890", "type": "string"}]


def test_reconcile_user_from_langfuse_returns_none_on_query_failure():
    with patch("langfuse.api.client.FernLangfuse", side_effect=RuntimeError("langfuse unreachable")), \
            patch("services.tstation.chat_history_service.get_redis_client") as mock_redis:
        result = quota_service.reconcile_user_from_langfuse("M200012931")

    assert result is None
    mock_redis.assert_not_called()


def test_reconcile_user_from_langfuse_treats_empty_rows_as_zero():
    fake_redis = MagicMock()
    fake_response = MagicMock()
    fake_response.data = []
    fake_metrics_client = MagicMock()
    fake_metrics_client.metrics.metrics.return_value = fake_response

    with patch("langfuse.api.client.FernLangfuse", return_value=fake_metrics_client), \
            patch("services.tstation.chat_history_service.get_redis_client", return_value=fake_redis):
        real_total = quota_service.reconcile_user_from_langfuse("codex")

    assert real_total == 0
    fake_redis.set.assert_called_once_with(
        fake_redis.set.call_args[0][0], 0, ex=fake_redis.set.call_args.kwargs["ex"]
    )
