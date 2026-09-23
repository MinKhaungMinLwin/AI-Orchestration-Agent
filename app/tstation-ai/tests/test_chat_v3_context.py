from __future__ import annotations

import os

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
    "LANGFUSE_SECRET_KEY": "test",
    "LANGFUSE_PUBLIC_KEY": "test",
}

for key, value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(key, value)

from schemas.tstation.chat import TStationChatRequest  # noqa: E402
from services.tstation.chat_v3 import context  # noqa: E402


def _request() -> TStationChatRequest:
    return TStationChatRequest(
        messages=[{"role": "user", "content": "이번 달 이벤트 알려줘"}],
        stream=True,
        user_id="M200012931",
        session_id="session",
    )


def test_build_messages_injects_langfuse_client_prompt_into_system_context(monkeypatch) -> None:
    monkeypatch.setattr(context, "load_client_injection", lambda: "7월 한정 이벤트 안내")

    messages = context.build_messages(_request(), system_prompt="BASE SYSTEM", extra_context=["EXTRA CONTEXT"])

    system_content = str(messages[0].content)
    assert "BASE SYSTEM" in system_content
    assert "## CLIENT INSTRUCTIONS\n7월 한정 이벤트 안내" in system_content
    assert "EXTRA CONTEXT" in system_content


def test_build_messages_skips_empty_langfuse_client_prompt(monkeypatch) -> None:
    monkeypatch.setattr(context, "load_client_injection", lambda: "")

    messages = context.build_messages(_request(), system_prompt="BASE SYSTEM")

    system_content = str(messages[0].content)
    assert "BASE SYSTEM" in system_content
    assert "## CLIENT INSTRUCTIONS" not in system_content
