import os
import asyncio

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

from services.tstation.chat_v3 import qc  # noqa: E402


def test_qc_failure_keeps_original_answer_and_suppresses_correction(monkeypatch) -> None:
    class FakeLlm:
        def with_structured_output(self, *args, **kwargs):
            return self

        async def ainvoke(self, *args, **kwargs):
            return qc.QCVerdict(passed=False, corrected_response="틀리게 고친 답변")

    monkeypatch.setattr(qc.settings, "AI_QC_ENABLED", True)
    monkeypatch.setattr(qc, "get_router_llm", lambda: FakeLlm())

    result = asyncio.run(
        qc.verify_answer(
            "원래 tool 기반 답변",
            [{"name": "get_store_install_availability_tool", "args": {}, "output": '{"status":"success"}'}],
        )
    )

    assert result.answer == "원래 tool 기반 답변"
    assert result.failed is True
    assert result.corrected_response == "틀리게 고친 답변"
    assert result.reason == "qc_failed_correction_suppressed"


def test_qc_pass_keeps_original_answer(monkeypatch) -> None:
    class FakeLlm:
        def with_structured_output(self, *args, **kwargs):
            return self

        async def ainvoke(self, *args, **kwargs):
            return qc.QCVerdict(passed=True, corrected_response="")

    monkeypatch.setattr(qc.settings, "AI_QC_ENABLED", True)
    monkeypatch.setattr(qc, "get_router_llm", lambda: FakeLlm())

    result = asyncio.run(
        qc.verify_answer(
            "원래 답변",
            [{"name": "get_products_recommendations_tool", "args": {}, "output": '{"status":"success"}'}],
        )
    )

    assert result.answer == "원래 답변"
    assert result.failed is False
    assert result.reason == "qc_passed"
