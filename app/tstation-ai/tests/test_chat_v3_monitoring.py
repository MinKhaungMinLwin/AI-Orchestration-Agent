from __future__ import annotations

import os
import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

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

from config import tracing  # noqa: E402
from services.tstation.chat_v3 import monitoring, service  # noqa: E402


def test_active_trace_span_propagates_formal_user_and_session(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class FakeSpan:
        id = "span-1"

    class FakeManager:
        def __init__(self, name: str, value: object) -> None:
            self.name = name
            self.value = value

        def __enter__(self):
            calls.append((f"{self.name}_enter", self.value))
            return self.value

        def __exit__(self, exc_type, exc, traceback):
            calls.append((f"{self.name}_exit", exc_type))

    class FakeTracer:
        def start_as_current_span(self, **kwargs):
            calls.append(("start_as_current_span", kwargs))
            return FakeManager("span", FakeSpan())

    def fake_propagate_attributes(**kwargs):
        calls.append(("propagate_attributes", kwargs))
        return FakeManager("attributes", None)

    monkeypatch.setattr(tracing, "_tracing_enabled", True)
    monkeypatch.setattr(tracing, "tracer", FakeTracer())
    monkeypatch.setattr(tracing, "propagate_attributes", fake_propagate_attributes)

    with tracing.active_trace_span(
        "chat_v3",
        trace_id="trace-1",
        session_id="session-1",
        user_id="user-1",
        trace_name="타이어 추천",
        input="타이어 추천",
        metadata={"runtime": "chat_v3"},
    ) as span:
        assert span.id == "span-1"

    start_kwargs = next(value for name, value in calls if name == "start_as_current_span")
    propagated = next(value for name, value in calls if name == "propagate_attributes")
    assert start_kwargs["trace_context"] == {"trace_id": "trace-1"}
    assert start_kwargs["metadata"] == {"runtime": "chat_v3"}
    assert propagated == {
        "session_id": "session-1",
        "user_id": "user-1",
        "trace_name": "타이어 추천",
    }
    assert [name for name, _ in calls[-2:]] == ["attributes_exit", "span_exit"]


def test_build_trace_config_inherits_matching_active_trace(monkeypatch) -> None:
    handlers: list[dict] = []

    class FakeHandler:
        def __init__(self, **kwargs):
            handlers.append(kwargs)

    class FakeTracer:
        def get_current_trace_id(self):
            return "trace-1"

    monkeypatch.setattr(tracing, "_tracing_enabled", True)
    monkeypatch.setattr(tracing, "tracer", FakeTracer())
    monkeypatch.setattr(tracing, "FilteredCallbackHandler", FakeHandler)

    config = tracing.build_trace_config(
        trace_id="trace-1",
        parent_span_id="span-1",
        inherit_active_trace=True,
    )

    assert config["callbacks"]
    assert handlers == [{"prompt_name": None}]
    assert config["configurable"]["tstation_trace_id"] == "trace-1"
    assert config["configurable"]["tstation_parent_span_id"] == "span-1"


def test_build_trace_config_keeps_explicit_context_without_matching_active_trace(monkeypatch) -> None:
    handlers: list[dict] = []

    class FakeHandler:
        def __init__(self, **kwargs):
            handlers.append(kwargs)

    class FakeTracer:
        def get_current_trace_id(self):
            return "other-trace"

    monkeypatch.setattr(tracing, "_tracing_enabled", True)
    monkeypatch.setattr(tracing, "tracer", FakeTracer())
    monkeypatch.setattr(tracing, "FilteredCallbackHandler", FakeHandler)

    tracing.build_trace_config(
        trace_id="trace-1",
        parent_span_id="span-1",
        inherit_active_trace=True,
    )

    assert handlers == [{
        "prompt_name": None,
        "trace_context": {"trace_id": "trace-1", "parent_span_id": "span-1"},
    }]


def test_trace_span_inherits_matching_active_trace(monkeypatch) -> None:
    starts: list[dict] = []

    class FakeSpan:
        def end(self):
            return None

    class FakeTracer:
        def get_current_trace_id(self):
            return "trace-1"

        def start_span(self, **kwargs):
            starts.append(kwargs)
            return FakeSpan()

    monkeypatch.setattr(tracing, "_tracing_enabled", True)
    monkeypatch.setattr(tracing, "tracer", FakeTracer())

    with tracing.trace_span(
        "tool-summary",
        trace_id="trace-1",
        parent_span_id="span-1",
        input={"goods_no": "G0001"},
    ):
        pass

    assert starts == [{"name": "tool-summary", "input": {"goods_no": "G0001"}}]


def test_trace_span_keeps_explicit_context_without_matching_active_trace(monkeypatch) -> None:
    starts: list[dict] = []

    class FakeSpan:
        def end(self):
            return None

    class FakeTracer:
        def get_current_trace_id(self):
            return "other-trace"

        def start_span(self, **kwargs):
            starts.append(kwargs)
            return FakeSpan()

    monkeypatch.setattr(tracing, "_tracing_enabled", True)
    monkeypatch.setattr(tracing, "tracer", FakeTracer())

    with tracing.trace_span(
        "tool-summary",
        trace_id="trace-1",
        parent_span_id="span-1",
        input={"goods_no": "G0001"},
    ):
        pass

    assert starts == [{
        "name": "tool-summary",
        "trace_context": {"trace_id": "trace-1", "parent_span_id": "span-1"},
        "input": {"goods_no": "G0001"},
    }]


def test_v3_trace_config_requests_active_trace_inheritance(monkeypatch) -> None:
    captured: dict = {}

    def fake_build_trace_config(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(service, "build_trace_config", fake_build_trace_config)
    request = SimpleNamespace(session_id="session-1", user_id="user-1", tracing_id="trace-1")

    service._trace_config(
        request,
        run_name="router",
        prompt_name="router",
        tags=["router"],
        parent_span_id="span-1",
    )

    assert captured["inherit_active_trace"] is True
    assert captured["trace_id"] == "trace-1"
    assert captured["parent_span_id"] == "span-1"


def test_run_turn_keeps_pipeline_inside_active_trace_context(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeSpan:
        id = "span-1"

        def update_trace(self, **kwargs) -> None:
            captured["trace_update"] = kwargs

    @contextmanager
    def fake_active_trace_span(**kwargs):
        captured["active_context"] = kwargs
        yield FakeSpan()

    async def fake_run_turn_impl(request, result, *, parent_span, parent_span_id):
        captured["impl_parent_span"] = parent_span
        captured["impl_parent_span_id"] = parent_span_id
        yield "event"

    flush_calls: list[bool] = []
    monkeypatch.setattr(service.context, "last_user_text", lambda request: "타이어 추천")
    monkeypatch.setattr(service, "active_trace_span", fake_active_trace_span)
    monkeypatch.setattr(service, "_run_turn_impl", fake_run_turn_impl)
    monkeypatch.setattr(service, "_flush_trace", lambda: flush_calls.append(True))

    request = SimpleNamespace(tracing_id="trace-1", session_id="session-1", user_id="user-1")
    async def collect_events() -> list[object]:
        return [event async for event in service._run_turn(request, {})]

    events = asyncio.run(collect_events())

    assert events == ["event"]
    assert captured["active_context"] == {
        "name": "chat_v3",
        "trace_id": "trace-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "trace_name": "타이어 추천",
        "input": "타이어 추천",
        "metadata": {"runtime": "chat_v3"},
    }
    assert captured["impl_parent_span_id"] == "span-1"
    assert captured["trace_update"]["session_id"] == "session-1"
    assert captured["trace_update"]["user_id"] == "user-1"
    assert flush_calls == [True]


def test_customer_monitoring_groups_domain_af_and_tools() -> None:
    payload = monitoring.build_customer_monitoring(
        route_domains=["DISCOVERY", "TRANSACTION"],
        tool_calls=[
            {"name": "search_product_tool", "output": '{"status":"success","data":{"items":[{}]}}'},
            {"name": "get_store_list_tool", "output": '{"status":"success","data":{"stores":[{}]}}'},
            {"name": "get_store_inventory_tool", "output": '{"status":"success","data":{"items":[{}]}}'},
        ],
        final_template="location",
        latency_ms=4200,
    )

    metadata = payload["metadata"]
    assert metadata["route_domains"] == ["DISCOVERY", "TRANSACTION"]
    assert metadata["tool_domains"] == ["DISCOVERY", "TRANSACTION"]
    assert metadata["af_path"] == ["Product Recommendation AF", "Store AF", "Inventory AF"]
    assert metadata["primary_domain"] == "TRANSACTION"
    assert metadata["primary_af"] == "Inventory AF"
    assert metadata["primary_tool"] == "get_store_inventory_tool"
    assert metadata["result_count"] == 1
    assert metadata["final_status"] == "success"
    assert metadata["status_reason"] == "tool_success_with_template"
    assert metadata["error_reason"] == "none"
    assert "af:inventory" in payload["tags"]
    assert "tool:get_store_inventory_tool" in payload["tags"]
    assert "status:success" in payload["tags"]


def test_customer_monitoring_marks_no_results_as_fallback() -> None:
    payload = monitoring.build_customer_monitoring(
        route_domains=["DISCOVERY"],
        tool_calls=[{"name": "search_product_tool", "output": '{"status":"no_results","reason":"empty"}'}],
        final_template="quickReply",
    )

    metadata = payload["metadata"]
    assert metadata["primary_af"] == "Product Recommendation AF"
    assert metadata["final_status"] == "fallback"
    assert metadata["status_reason"] == "tool_no_results"
    assert metadata["error_reason"] == "tool_no_results"
    assert metadata["no_result_tools"] == ["search_product_tool"]
    assert "status:fallback" in payload["tags"]


def test_customer_monitoring_marks_qc_correction_as_partial_success() -> None:
    payload = monitoring.build_customer_monitoring(
        route_domains=["SUPPORT"],
        tool_calls=[{"name": "search_faq_hybrid_tool", "output": '{"status":"success"}'}],
        final_template="quickReply",
        qc_corrected=True,
    )

    metadata = payload["metadata"]
    assert metadata["primary_af"] == "FAQ AF"
    assert metadata["final_status"] == "partial_success"
    assert metadata["status_reason"] == "qc_corrected"
    assert metadata["error_reason"] == "qc_corrected"
    assert "status:partial_success" in payload["tags"]


def test_customer_monitoring_records_qc_failure_without_changing_status() -> None:
    payload = monitoring.build_customer_monitoring(
        route_domains=["DISCOVERY"],
        tool_calls=[{"name": "get_products_recommendations_tool", "output": '{"status":"success"}'}],
        final_template="product",
        qc_failed=True,
        qc_reason="qc_failed_correction_suppressed",
    )

    metadata = payload["metadata"]
    assert metadata["final_status"] == "success"
    assert metadata["status_reason"] == "tool_success_with_template"
    assert metadata["error_reason"] == "none"
    assert metadata["qc_corrected"] is False
    assert metadata["qc_failed"] is True
    assert metadata["qc_reason"] == "qc_failed_correction_suppressed"
    assert "qc:failed" in payload["tags"]


def test_update_trace_monitoring_does_not_call_current_trace(monkeypatch) -> None:
    # The payload is applied to the explicit active parent span so the monitoring
    # update cannot accidentally target one of its child observations.
    current_trace_calls: list[dict] = []
    parent_trace_calls: list[dict] = []

    class FakeParentSpan:
        def update_trace(self, **kwargs):
            parent_trace_calls.append(kwargs)

    class FakeTracer:
        def update_current_trace(self, **kwargs):
            current_trace_calls.append(kwargs)

    monkeypatch.setattr(service, "tracer", FakeTracer())

    service._update_trace_monitoring(
        trace_observation=FakeParentSpan(),
        route_domains=["TRANSACTION"],
        tool_calls=[{"name": "quick_order_tool", "output": '{"status":"success"}'}],
        final_template="orderComplete",
        latency_ms=100,
    )

    assert current_trace_calls == []  # the redundant, active-span-dependent call is gone
    assert parent_trace_calls  # payload applied via the explicit parent span
    assert parent_trace_calls[0]["metadata"]["primary_af"] == "Quick Shopping AF"
    assert parent_trace_calls[0]["metadata"]["final_status"] == "success"
    assert "af:quick_shopping" in parent_trace_calls[0]["tags"]


def test_update_trace_monitoring_applies_payload_to_parent_span(monkeypatch) -> None:
    current_trace_calls: list[dict] = []
    parent_observation_calls: list[dict] = []
    parent_trace_calls: list[dict] = []

    class FakeParentSpan:
        def update(self, **kwargs):
            parent_observation_calls.append(kwargs)

        def update_trace(self, **kwargs):
            parent_trace_calls.append(kwargs)

    class FakeTracer:
        def update_current_trace(self, **kwargs):
            current_trace_calls.append(kwargs)

    monkeypatch.setattr(service, "tracer", FakeTracer())

    service._update_trace_monitoring(
        trace_observation=FakeParentSpan(),
        route_domains=["DISCOVERY"],
        tool_calls=[{"name": "get_products_recommendations_tool", "output": '{"status":"success"}'}],
        final_template="product",
        answer="추천 타이어입니다.",
        user_text="타이어 추천",
        latency_ms=100,
    )

    assert current_trace_calls == []
    assert parent_observation_calls == [{
        "input": "타이어 추천",
        "output": "추천 타이어입니다.",
    }]
    assert parent_trace_calls
    assert parent_trace_calls[0]["metadata"]["primary_af"] == "Product Recommendation AF"
    assert parent_trace_calls[0]["input"] == "타이어 추천"
    assert parent_trace_calls[0]["output"] == "추천 타이어입니다."


def test_update_trace_monitoring_records_customer_event_as_active_trace_child(monkeypatch) -> None:
    events: list[dict] = []
    scores: list[dict] = []

    class FakeEvent:
        def score_trace(self, **kwargs):
            scores.append(kwargs)

    class FakeTracer:
        def create_event(self, **kwargs):
            events.append(kwargs)
            return FakeEvent()

        def update_current_trace(self, **kwargs):
            pass

    monkeypatch.setattr(service, "tracer", FakeTracer())

    service._update_trace_monitoring(
        trace_id="trace-1",
        parent_span_id="span-1",
        session_id="session-1",
        user_id="user-1",
        message_id="message-1",
        route_intents=["place_order", "product_search"],
        route_domains=["TRANSACTION", "DISCOVERY"],
        tool_calls=[{"name": "present_order_preview_tool", "output": '{"status":"success"}'}],
        final_template="preOrder",
        answer="주문 내용을 확인해 주세요.",
        user_text="주문할래",
        latency_ms=100,
    )

    assert events
    metadata = events[0]["metadata"]
    assert "trace_context" not in events[0]
    assert events[0]["input"] == "주문할래"
    assert events[0]["output"] == "주문 내용을 확인해 주세요."
    assert metadata["message_id"] == "message-1"
    assert metadata["route_intents"] == ["place_order", "product_search"]
    assert metadata["error_reason"] == "none"
    assert metadata["final_status"] == "success"
    assert metadata["final_template"] == "preOrder"
    assert "intent:place_order" in metadata["tags"]
    assert scores[0]["name"] == "customer_final_status"
    assert scores[0]["value"] == "success"
