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

from services.tstation.chat_v3 import monitoring, service  # noqa: E402


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


def test_update_trace_monitoring_uses_langfuse_current_trace(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeTracer:
        def update_current_trace(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(service, "tracer", FakeTracer())

    service._update_trace_monitoring(
        route_domains=["TRANSACTION"],
        tool_calls=[{"name": "quick_order_tool", "output": '{"status":"success"}'}],
        final_template="orderComplete",
        latency_ms=100,
    )

    assert calls
    assert calls[0]["metadata"]["primary_af"] == "Quick Shopping AF"
    assert calls[0]["metadata"]["final_status"] == "success"
    assert "af:quick_shopping" in calls[0]["tags"]


def test_update_trace_monitoring_keeps_current_trace_update_with_parent_span(monkeypatch) -> None:
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
        route_domains=["DISCOVERY"],
        tool_calls=[{"name": "get_products_recommendations_tool", "output": '{"status":"success"}'}],
        final_template="product",
        answer="추천 타이어입니다.",
        user_text="타이어 추천",
        latency_ms=100,
    )

    assert parent_trace_calls
    assert current_trace_calls
    assert current_trace_calls[0]["metadata"]["primary_af"] == "Product Recommendation AF"
    assert current_trace_calls[0]["input"] == "타이어 추천"
    assert current_trace_calls[0]["output"] == "추천 타이어입니다."


def test_update_trace_monitoring_records_customer_event_with_turn_metadata(monkeypatch) -> None:
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
    assert events[0]["trace_context"] == {"trace_id": "trace-1", "parent_span_id": "span-1"}
    assert metadata["message_id"] == "message-1"
    assert metadata["route_intents"] == ["place_order", "product_search"]
    assert metadata["error_reason"] == "none"
    assert "intent:place_order" in metadata["tags"]
    assert scores[0]["name"] == "customer_final_status"
    assert scores[0]["value"] == "success"
