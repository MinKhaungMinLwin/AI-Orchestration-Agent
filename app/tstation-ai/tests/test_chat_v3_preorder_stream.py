import asyncio
import json
import os

import pytest

from schemas.tstation.chat import TStationChatRequest
from schemas.tstation.slots import ConversationSlots


for key in (
    "PROJECT_NAME",
    "ROOT_PATH",
    "API_SECRET_KEY",
    "TSTATION_BE_API",
    "TSTATION_BE_MCP",
    "AI_DEFAULT_PROVIDER",
    "AI_GATEWAY_BASE_URL",
    "AI_GATEWAY_API_KEY",
    "AI_MODEL",
    "AI_MODEL_REASONING",
    "AI_MODEL_MINI",
    "AI_MODEL_LEADING_AGENT",
    "AI_MODEL_QC_AGENT",
    "AI_MODEL_TRANSACTION_AGENT",
    "UPSTAGE_API_KEY",
    "OPENAI_API_KEY",
    "REDIS_CONVERSATION_MANAGEMENT_PASSWORD",
    "REDIS_CONVERSATION_MANAGEMENT_URL",
    "REDIS_QUEUE_URL",
    "REDIS_PASSWORD",
    "REDIS_URL",
    "RABBITMQ_NODENAME",
    "RABBITMQ_USERNAME",
    "RABBITMQ_PASSWORD",
    "RABBITMQ_URL",
    "RABBITMQ_URL_MANAGEMENT",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_DEFAULT_REGION",
    "S3_BUCKET_NAME",
    "GF_SECURITY_ADMIN_USER",
    "GF_SECURITY_ADMIN_PASSWORD",
    "LOKI_URL",
    "PROMETHEUS_URL",
    "LANGFUSE_HOST",
    "LANGFUSE_PROJECT_NAME",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_PUBLIC_KEY",
):
    os.environ.setdefault(key, "test")
os.environ["REDIS_CONVERSATION_MANAGEMENT_URL"] = "redis://localhost:6379/0"
os.environ["REDIS_QUEUE_URL"] = "redis://localhost:6379/1"
os.environ["REDIS_URL"] = "redis://localhost:6379/2"

from services.tstation.chat_v3 import service  # noqa: E402
from services.tstation.chat_v3.router.schemas import Domain, RouteDecision  # noqa: E402
from services.tstation.chat_v3.slots.schemas import SlotsPatch  # noqa: E402


def _parse_sse_event(line: str) -> dict | None:
    if not line.startswith("data: "):
        return None
    payload = line.removeprefix("data: ").strip()
    if payload == "[DONE]":
        return None
    return json.loads(payload)


def test_preorder_stream_does_not_emit_duplicate_message(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_preorder_stream_does_not_emit_duplicate_message(monkeypatch))


def test_confirmed_cart_stream_executes_save_to_cart_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_confirmed_cart_stream_executes_save_to_cart_tool(monkeypatch))


def test_add_to_cart_quantity_turn_builds_preorder_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_add_to_cart_quantity_turn_builds_preorder_confirmation(monkeypatch))


async def _assert_add_to_cart_quantity_turn_builds_preorder_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    slots = ConversationSlots(
        goods_no="G0001",
        tire_size="225/45R17",
        pending_product_name="Ventus V12 Evo2 225/45R17",
    )
    decision = RouteDecision(
        domain=Domain.TRANSACTION,
        intents=["add_to_cart"],
        slots_patch=SlotsPatch(ord_qty=4),
    )
    saved_slots = []

    class FakeExecutor:
        def __init__(self, *args, **kwargs) -> None:
            self.final_text = "I cannot add this to cart from chat."
            self.tool_calls = []

        async def stream(self):
            yield service.sse.token("I cannot add this to cart from chat.")

    async def fake_route_request(*args, **kwargs):
        assert kwargs["known_slots"].goods_no == "G0001"
        return decision

    async def fake_load_slots(session_id):
        return slots

    async def fake_save_slots(session_id, next_slots, user_id=None):
        saved_slots.append(next_slots)

    async def fake_verify_answer(answer, tool_calls, trace_config):
        return answer

    async def fake_noop(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "route_request", fake_route_request)
    monkeypatch.setattr(service, "load_slots", fake_load_slots)
    monkeypatch.setattr(service, "save_slots", fake_save_slots)
    monkeypatch.setattr(service, "tools_for_domains", lambda domains: [])
    monkeypatch.setattr(service, "ToolLoopExecutor", FakeExecutor)
    monkeypatch.setattr(service.qc, "verify_answer", fake_verify_answer)
    monkeypatch.setattr(service.memory, "load_tool_context_block", fake_noop)
    monkeypatch.setattr(service.memory, "persist_turn_context", fake_noop)
    monkeypatch.setattr(service, "_flush_trace", lambda: None)

    request = TStationChatRequest(
        messages=[
            {"role": "assistant", "content": "Ventus V12 Evo2 225/45R17"},
            {"role": "user", "content": "4개 장바구니에 담아줘"},
        ],
        stream=True,
        user_id="test-user",
        session_id="cart-preorder-stream-test",
    )

    events = []
    async for line in service._run_turn(request, {}):
        event = _parse_sse_event(line)
        if event:
            events.append(event)

    assert not [event for event in events if event.get("type") in {"message", "token"}]
    pre_order = next(event for event in events if event.get("template") == "preOrder")
    assert pre_order["data"]["isReadyToAddToCart"] is True
    assert pre_order["data"]["metadata"]["goodsNo"] == "G0001"
    assert pre_order["data"]["metadata"]["ordQty"] == 4
    assert saved_slots[0].pending_intent == "cart"
    assert saved_slots[0].goal_type == "add_to_cart"


async def _assert_confirmed_cart_stream_executes_save_to_cart_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    slots = ConversationSlots(
        goods_no="G0001",
        ord_qty=4,
        pending_product_name="Ventus S2 AS 225/45R17",
    )
    decision = RouteDecision(
        domain=Domain.TRANSACTION,
        intents=["cart_confirmation"],
    )
    saved_slots = []
    persisted_tool_calls = []

    class FakeCartTool:
        name = "save_to_cart_tool"

        async def ainvoke(self, args, config=None):
            assert args == {"goods_no": "G0001", "ord_qty": 4}
            return {"status": "success", "http_status": 200, "data": {"result": True}}

    class ForbiddenExecutor:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("confirmed cart should execute save_to_cart_tool without re-running the LLM loop")

    async def fake_route_request(*args, **kwargs):
        assert kwargs["known_slots"].goods_no == "G0001"
        assert kwargs["known_slots"].ord_qty == 4
        return decision

    async def fake_load_slots(session_id):
        return slots

    async def fake_save_slots(session_id, next_slots, user_id=None):
        saved_slots.append(next_slots)

    async def fake_persist_turn_context(session_id, tool_calls, quick_reply_domains, predicted_domains, user_id=None):
        persisted_tool_calls.extend(tool_calls)

    monkeypatch.setattr(service, "route_request", fake_route_request)
    monkeypatch.setattr(service, "load_slots", fake_load_slots)
    monkeypatch.setattr(service, "save_slots", fake_save_slots)
    monkeypatch.setattr(service, "tools_for_domains", lambda domains: [FakeCartTool()])
    monkeypatch.setattr(service, "ToolLoopExecutor", ForbiddenExecutor)
    monkeypatch.setattr(service.memory, "persist_turn_context", fake_persist_turn_context)
    monkeypatch.setattr(service, "_tool_display_names", lambda: {"save_to_cart_tool": "장바구니에 담는 중..."})
    monkeypatch.setattr(service, "_flush_trace", lambda: None)

    request = TStationChatRequest(
        messages=[
            {"role": "assistant", "content": "맞으면 장바구니에 담아드릴게요."},
            {"role": "user", "content": "네 담아줘"},
        ],
        stream=True,
        user_id="test-user",
        session_id="confirmed-cart-stream-test",
    )

    events = []
    async for line in service._run_turn(request, {}):
        event = _parse_sse_event(line)
        if event:
            events.append(event)

    tool_events = [event for event in events if event.get("type") == "tool"]
    assert tool_events
    assert tool_events[0]["tool"] == "save_to_cart_tool"
    assert "장바구니에 담았어요" in next(
        event["content"] for event in events if event.get("type") == "message"
    )
    assert persisted_tool_calls[0]["name"] == "save_to_cart_tool"
    assert saved_slots


async def _assert_preorder_stream_does_not_emit_duplicate_message(monkeypatch: pytest.MonkeyPatch) -> None:
    slots = ConversationSlots(
        goods_no="G0001",
        ord_qty=2,
        shop_id="S0001",
        shop_name="T-Station Test",
        requested_cal_day="20260708",
        rsv_hour="17",
        pending_intent="order",
        goal_type="place_order",
        pending_product_name="Ventus S2 AS 245/45R19",
        payment_amount=308200,
    )
    decision = RouteDecision(
        domain=Domain.TRANSACTION,
        slots_patch=SlotsPatch(rsv_hour="17"),
    )

    class FakeExecutor:
        def __init__(self, *args, **kwargs) -> None:
            self.final_text = "Please confirm the order details."
            self.tool_calls = []

        async def stream(self):
            yield service.sse.token("Please confirm the order details.")

    async def fake_verify_answer(answer, tool_calls, trace_config):
        return answer

    async def fake_route_request(*args, **kwargs):
        return decision

    async def fake_load_slots(session_id):
        return slots

    async def fake_noop(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "route_request", fake_route_request)
    monkeypatch.setattr(service, "load_slots", fake_load_slots)
    monkeypatch.setattr(service, "tools_for_domains", lambda domains: [])
    monkeypatch.setattr(service, "ToolLoopExecutor", FakeExecutor)
    monkeypatch.setattr(service.qc, "verify_answer", fake_verify_answer)
    monkeypatch.setattr(service, "save_slots", fake_noop)
    monkeypatch.setattr(service.memory, "load_tool_context_block", fake_noop)
    monkeypatch.setattr(service.memory, "persist_turn_context", fake_noop)
    monkeypatch.setattr(service, "_flush_trace", lambda: None)

    request = TStationChatRequest(
        messages=[{"role": "user", "content": "17:00"}],
        stream=True,
        user_id="test-user",
        session_id="preorder-stream-test",
    )

    events = []
    async for line in service._run_turn(request, {}):
        event = _parse_sse_event(line)
        if event:
            events.append(event)

    assert not [event for event in events if event.get("type") in {"message", "token"}]
    pre_order_events = [
        event for event in events
        if event.get("type") == "data" and event.get("template") == "preOrder"
    ]
    assert pre_order_events
    assert "assistantResponse" not in pre_order_events[0]["data"]
