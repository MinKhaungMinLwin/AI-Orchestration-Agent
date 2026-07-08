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
            if False:
                yield ""

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

    assert not [event for event in events if event.get("type") == "message"]
    assert any(
        event.get("type") == "data" and event.get("template") == "preOrder"
        for event in events
    )
