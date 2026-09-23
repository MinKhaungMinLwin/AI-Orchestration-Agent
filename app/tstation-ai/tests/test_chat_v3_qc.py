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


class _UnusedLlm:
    """Deterministic-layer tests must never reach the LLM fallback."""

    def with_structured_output(self, *args, **kwargs):
        raise AssertionError("LLM QC must not be called when tool outputs are parseable")


# Non-JSON tool output: unparseable by qc_verifier → exercises the LLM fallback branch.
_UNPARSEABLE_TOOL_CALLS = [{"name": "get_store_install_availability_tool", "args": {}, "output": "plain text result"}]


def test_qc_llm_fallback_failure_keeps_original_answer(monkeypatch) -> None:
    class FakeLlm:
        def with_structured_output(self, *args, **kwargs):
            return self

        async def ainvoke(self, *args, **kwargs):
            return qc.QCVerdict(passed=False, reason="가격 불일치")

    monkeypatch.setattr(qc.settings, "AI_QC_ENABLED", True)
    monkeypatch.setattr(qc, "get_router_llm", lambda: FakeLlm())

    result = asyncio.run(qc.verify_answer("원래 tool 기반 답변", _UNPARSEABLE_TOOL_CALLS))

    assert result.answer == "원래 tool 기반 답변"
    assert result.failed is True
    assert result.corrected_response == ""
    assert result.reason == "가격 불일치"


def test_qc_llm_fallback_pass_keeps_original_answer(monkeypatch) -> None:
    class FakeLlm:
        def with_structured_output(self, *args, **kwargs):
            return self

        async def ainvoke(self, *args, **kwargs):
            return qc.QCVerdict(passed=True)

    monkeypatch.setattr(qc.settings, "AI_QC_ENABLED", True)
    monkeypatch.setattr(qc, "get_router_llm", lambda: FakeLlm())

    result = asyncio.run(qc.verify_answer("원래 답변", _UNPARSEABLE_TOOL_CALLS))

    assert result.answer == "원래 답변"
    assert result.failed is False
    assert result.reason == "qc_passed"


def test_qc_deterministic_pass_skips_llm(monkeypatch) -> None:
    monkeypatch.setattr(qc.settings, "AI_QC_ENABLED", True)
    monkeypatch.setattr(qc, "get_router_llm", lambda: _UnusedLlm())

    result = asyncio.run(
        qc.verify_answer(
            "벤투스 S2 가격은 150,000원입니다.",
            [{"name": "get_final_price_tool", "args": {}, "output": '{"data": {"sale_prc": 150000}}'}],
        )
    )

    assert result.failed is False
    assert result.reason == "qc_det_passed"


def test_qc_deterministic_mismatch_flags_without_llm(monkeypatch) -> None:
    monkeypatch.setattr(qc.settings, "AI_QC_ENABLED", True)
    monkeypatch.setattr(qc, "get_router_llm", lambda: _UnusedLlm())

    result = asyncio.run(
        qc.verify_answer(
            "벤투스 S2 가격은 999,000원입니다.",
            [{"name": "get_final_price_tool", "args": {}, "output": '{"data": {"sale_prc": 150000}}'}],
        )
    )

    assert result.answer == "벤투스 S2 가격은 999,000원입니다."
    assert result.failed is True
    assert result.reason.startswith("qc_det_failed:price=")
