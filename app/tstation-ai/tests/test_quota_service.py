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


def test_monthly_quota_uses_korea_standard_time():
    assert quota_service._KST.total_seconds() == 9 * 60 * 60


def test_quota_exempt_user_is_read_from_redis_set():
    fake_redis = MagicMock()
    fake_redis.sismember.side_effect = lambda key, user_id: (
        key == quota_service._QUOTA_EXEMPT_USERS_KEY and user_id == "M200012931"
    )

    with patch("services.tstation.chat_history_service.get_redis_client", return_value=fake_redis):
        assert quota_service.is_quota_exempt("M200012931") is True
        assert quota_service.is_quota_exempt("M200012932") is False


def test_quota_exemption_check_fails_closed_when_redis_is_unavailable():
    with patch(
        "services.tstation.chat_history_service.get_redis_client",
        side_effect=RuntimeError("redis unavailable"),
    ):
        assert quota_service.is_quota_exempt("M200012931") is False


def test_empty_user_id_never_checks_quota_exemption():
    with patch("services.tstation.chat_history_service.get_redis_client") as mock_redis:
        assert quota_service.is_quota_exempt("") is False

    mock_redis.assert_not_called()


def test_exempt_user_bypasses_monthly_quota_blocking():
    with patch.object(quota_service, "is_quota_exempt", return_value=True), patch.object(
        quota_service, "is_quota_exceeded", return_value=True
    ) as mock_exceeded:
        blocked = quota_service.should_block_monthly_quota("M200012931", 2_000_000)

    assert blocked is False
    mock_exceeded.assert_not_called()


def test_non_exempt_over_limit_user_is_still_blocked():
    with patch.object(quota_service, "is_quota_exempt", return_value=False), patch.object(
        quota_service, "is_quota_exceeded", return_value=True
    ):
        assert quota_service.should_block_monthly_quota("M200012932", 2_000_000) is True


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
    # The SDK's own request paths already start with "api/public/..." relative to
    # base_url — appending it here too would double the path and 404 every call.
    assert "/api/public" not in mock_client_cls.call_args.kwargs["base_url"]
    fake_redis.set.assert_called_once()
    (key, value), kwargs = fake_redis.set.call_args
    assert key.startswith("quota:tokens:M200012890:")
    assert value == 5_820_000
    assert kwargs["ex"] > 0

    query = json.loads(fake_metrics_client.metrics.metrics.call_args.kwargs["query"])
    assert query["view"] == "observations"
    assert query["metrics"] == [{"measure": "totalTokens", "aggregation": "sum"}]
    assert query["filters"] == [{"column": "userId", "operator": "=", "value": "M200012890", "type": "string"}]


def test_reconcile_posts_corrected_monthly_score_under_the_user():
    fake_redis = MagicMock()
    fake_response = MagicMock()
    fake_response.data = [{"sum_totalTokens": 30_406_846}]
    fake_metrics_client = MagicMock()
    fake_metrics_client.metrics.metrics.return_value = fake_response

    fake_span = MagicMock()
    fake_tracer = MagicMock()
    fake_tracer.start_span.return_value = fake_span

    with patch("langfuse.api.client.FernLangfuse", return_value=fake_metrics_client), \
            patch("services.tstation.chat_history_service.get_redis_client", return_value=fake_redis), \
            patch("config.tracing.tracer", fake_tracer), \
            patch("config.tracing._tracing_enabled", True), \
            patch.object(quota_service, "post_langfuse_score") as mock_post:
        real_total = quota_service.reconcile_user_from_langfuse("M200012931")

    assert real_total == 30_406_846
    # The corrected score must be attached to a trace carrying this user_id, or it
    # won't show under the user in the Scores tab.
    fake_span.update_trace.assert_called_once()
    assert fake_span.update_trace.call_args.kwargs["user_id"] == "M200012931"
    # Reuses the proven post_langfuse_score with the reconciled total.
    mock_post.assert_called_once()
    post_args = mock_post.call_args[0]
    assert post_args[1] == "monthly_tokens_used"
    assert post_args[2] == float(30_406_846)
    assert "reconciled" in post_args[3]
    # One-off invocation exits immediately — the score must be flushed or it's lost.
    fake_tracer.flush.assert_called_once()


def test_reconcile_still_returns_total_when_score_post_fails():
    fake_redis = MagicMock()
    fake_response = MagicMock()
    fake_response.data = [{"sum_totalTokens": 7_000_000}]
    fake_metrics_client = MagicMock()
    fake_metrics_client.metrics.metrics.return_value = fake_response

    fake_tracer = MagicMock()
    fake_tracer.start_span.side_effect = RuntimeError("langfuse write down")

    with patch("langfuse.api.client.FernLangfuse", return_value=fake_metrics_client), \
            patch("services.tstation.chat_history_service.get_redis_client", return_value=fake_redis), \
            patch("config.tracing.tracer", fake_tracer), \
            patch("config.tracing._tracing_enabled", True):
        real_total = quota_service.reconcile_user_from_langfuse("M200012931")

    # Redis correction (the part that matters for enforcement) must stick even if
    # the cosmetic score post throws.
    assert real_total == 7_000_000
    fake_redis.set.assert_called_once()


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
