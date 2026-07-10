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
from services.tstation.chat_v3.slots.derive import apply_fe_slots, apply_text_vehicle_selection, derive_slots_from_tool_calls  # noqa: E402
from services.tstation.chat_v3.slots.schemas import SlotsPatch  # noqa: E402
from services.tstation.chat_v3.slots.store import slots_context_block  # noqa: E402


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


def test_reaffirmed_add_to_cart_stream_executes_save_to_cart_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_confirmed_cart_stream_executes_save_to_cart_tool(monkeypatch, intent="add_to_cart"))


def test_reaffirmed_add_to_cart_with_same_quantity_executes_save_to_cart_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(
        _assert_confirmed_cart_stream_executes_save_to_cart_tool(
            monkeypatch,
            intent="add_to_cart",
            slots_patch=SlotsPatch(ord_qty=4),
        )
    )


def test_add_to_cart_quantity_turn_executes_save_to_cart_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_add_to_cart_quantity_turn_executes_save_to_cart_tool(monkeypatch))


def test_fe_vehicle_patch_preserves_staggered_sizes_without_selecting_one() -> None:
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "select car"}],
        stream=True,
        user_id="test-user",
        session_id="staggered-fe-slot-test",
        slots={"tireSize": "225/50R18", "tireSizeRe": "255/50R18"},
    )

    slots = apply_fe_slots(ConversationSlots(), request)

    assert slots.tire_size is None
    assert slots.tire_size_front == "225/50R18"
    assert slots.tire_size_rear == "255/50R18"


def test_fe_vehicle_ui_action_preserves_staggered_sizes_without_selecting_one() -> None:
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "select car"}],
        stream=True,
        user_id="test-user",
        session_id="staggered-fe-ui-action-test",
        ui_action={
            "action_type": "select_vehicle_candidate",
            "slots": {
                "carNo": "29조3345",
                "carLncCd": "W000003",
                "tireSize": "225/40R19",
                "tireSizeRe": "255/35R19",
            },
        },
    )

    slots = apply_fe_slots(ConversationSlots(), request)

    assert slots.car_no == "29조3345"
    assert slots.car_lnc_cd == "W000003"
    assert slots.tire_size is None
    assert slots.tire_size_front == "225/40R19"
    assert slots.tire_size_rear == "255/35R19"


def test_vehicle_candidate_ui_action_ignores_premature_selected_size_for_staggered_vehicle() -> None:
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "select car"}],
        stream=True,
        user_id="test-user",
        session_id="staggered-fe-ui-action-selected-size-test",
        ui_action={
            "action_type": "select_vehicle_candidate",
            "slots": {
                "carNo": "29조3345",
                "carLncCd": "W000003",
                "tire_size": "225/40R19",
                "tireSize": "225/40R19",
                "tireSizeRe": "255/35R19",
            },
        },
    )

    slots = apply_fe_slots(ConversationSlots(), request)

    assert slots.tire_size is None
    assert slots.tire_size_front == "225/40R19"
    assert slots.tire_size_rear == "255/35R19"


def test_vehicle_card_slots_ignore_premature_selected_size_for_staggered_vehicle() -> None:
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "select car"}],
        stream=True,
        user_id="test-user",
        session_id="staggered-fe-card-selected-size-test",
        slots={
            "carNo": "29ì¡°3345",
            "carLncCd": "W063680",
            "mbr_car_reg_seq": "2000003099",
            "carModelDet": "3-series(G20 F/L2) M340i A/T",
            "tire_size": "225/40R19",
            "tireSize": "225/40R19",
            "tireSizeRe": "255/35R19",
        },
    )

    slots = apply_fe_slots(ConversationSlots(), request)

    assert slots.car_no == "29ì¡°3345"
    assert slots.car_lnc_cd == "W063680"
    assert slots.car_model == "3-series(G20 F/L2) M340i A/T"
    assert slots.mbr_car_reg_seq == "2000003099"
    assert slots.tire_size is None
    assert slots.tire_size_front == "225/40R19"
    assert slots.tire_size_rear == "255/35R19"


def test_staggered_size_chip_slots_apply_selected_size() -> None:
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "ì•žë°”í€´ì‚¬ì´ì¦ˆ"}],
        stream=True,
        user_id="test-user",
        session_id="staggered-size-chip-selected-size-test",
        chip_context={
            "metadata": {
                "slots": {
                    "carNo": "29ì¡°3345",
                    "carLncCd": "W063680",
                    "tire_size": "225/40R19",
                    "tireSize": "225/40R19",
                    "tireSizeRe": "255/35R19",
                }
            }
        },
    )

    slots = apply_fe_slots(ConversationSlots(), request)

    assert slots.tire_size == "225/40R19"
    assert slots.tire_size_front == "225/40R19"
    assert slots.tire_size_rear == "255/35R19"


def test_staggered_selected_size_context_blocks_simultaneous_purchase_overclaim() -> None:
    slots = ConversationSlots(
        tire_size="225/40R19",
        tire_size_front="225/40R19",
        tire_size_rear="255/35R19",
    )

    context = slots_context_block(slots) or ""

    assert "두 규격을 한 번에 구매 가능하다고" in context
    assert "선택한 규격 하나씩 상품 추천/구매를 진행" in context


def test_vehicle_card_slots_clear_stale_selected_size_for_staggered_vehicle() -> None:
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "select car"}],
        stream=True,
        user_id="test-user",
        session_id="staggered-fe-card-stale-selected-size-test",
        slots={
            "carNo": "TESTCAR",
            "carLncCd": "W063680",
            "tire_size": "225/40R19",
            "tireSize": "225/40R19",
            "tireSizeRe": "255/35R19",
        },
    )
    stale_slots = ConversationSlots(tire_size="225/40R19")

    slots = apply_fe_slots(stale_slots, request)

    assert slots.tire_size is None
    assert slots.tire_size_front == "225/40R19"
    assert slots.tire_size_rear == "255/35R19"


def test_text_vehicle_selection_recovers_staggered_sizes_from_previous_candidates() -> None:
    tool_output = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "29조3345",
                    "car_lnc_cd": "W000003",
                    "car_model_det": "3-series(G20 F/L2) M340i A/T",
                    "tire_size_fr": "225/40R19",
                    "tire_size_re": "255/35R19",
                },
                {
                    "car_no": "29조3344",
                    "car_lnc_cd": "W000004",
                    "car_model_det": "Jetta",
                    "tire_size_fr": "225/45R17",
                    "tire_size_re": "225/45R17",
                },
            ]
        },
    }
    slots = derive_slots_from_tool_calls(
        ConversationSlots(),
        [{"name": "get_my_cars_tool", "args": {}, "output": json.dumps(tool_output, ensure_ascii=False)}],
    )

    slots = apply_text_vehicle_selection(slots, "29조3345")

    assert slots.car_no == "29조3345"
    assert slots.car_lnc_cd == "W000003"
    assert slots.tire_size is None
    assert slots.tire_size_front == "225/40R19"
    assert slots.tire_size_rear == "255/35R19"


def test_staggered_vehicle_size_guard_blocks_purchase_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_staggered_vehicle_size_guard_blocks_purchase_flow(monkeypatch))


def test_staggered_vehicle_size_guard_survives_router_car_no_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(
        _assert_staggered_vehicle_size_guard_blocks_purchase_flow(
            monkeypatch,
            slots=ConversationSlots(
                car_no="29조3345",
                tire_size_front="225/40R19",
                tire_size_rear="255/35R19",
            ),
            decision=RouteDecision(
                domain=Domain.DISCOVERY,
                intents=["tire_recommend"],
                slots_patch=SlotsPatch(car_no="29조3345"),
            ),
            expected_front_size="225/40R19",
            expected_rear_size="255/35R19",
        )
    )


def test_staggered_vehicle_card_click_guard_blocks_recommendation_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_staggered_vehicle_card_click_guard_blocks_recommendation_flow(monkeypatch))


def test_staggered_vehicle_size_guard_does_not_depend_on_router_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(
        _assert_staggered_vehicle_size_guard_blocks_purchase_flow(
            monkeypatch,
            slots=ConversationSlots(
                car_no="29ì¡°3345",
                car_model="BMW 3 Series M340i A/T",
                tire_size_front="225/40R19",
                tire_size_rear="255/35R19",
            ),
            decision=RouteDecision(domain=Domain.LEADING, intents=["vehicle_selection"]),
            expected_front_size="225/40R19",
            expected_rear_size="255/35R19",
        )
    )


def test_staggered_simultaneous_purchase_inquiry_does_not_run_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_staggered_simultaneous_purchase_inquiry_does_not_run_tools(monkeypatch))


def test_staggered_simultaneous_purchase_inquiry_recovers_candidate_sizes(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(
        _assert_staggered_simultaneous_purchase_inquiry_does_not_run_tools(
            monkeypatch,
            slots=ConversationSlots(
                car_no="29조3345",
                tire_size="225/40R19",
                vehicle_candidates=[
                    {
                        "car_no": "29조3345",
                        "tire_size_front": "225/40R19",
                        "tire_size_rear": "255/35R19",
                    }
                ],
            ),
        )
    )


def test_duplicate_cart_preview_tool_call_redirects_to_save_to_cart() -> None:
    slots = ConversationSlots(goods_no="G0001", ord_qty=4, pending_intent="cart")
    normalize = service._add_to_cart_tool_normalizer(slots, enabled=True)

    normalized = normalize(
        {"name": "present_order_preview_tool", "args": {"goods_no": "G0001", "ord_qty": 4}, "id": "call-1"}
    )

    assert normalized["name"] == "save_to_cart_tool"
    assert normalized["args"] == {"goods_no": "G0001", "ord_qty": 4}
    assert normalized["id"] == "call-1"


def test_add_to_cart_preview_tool_call_redirects_with_tool_args() -> None:
    slots = ConversationSlots(goods_no="G0001", ord_qty=4, pending_intent="cart")
    normalize = service._add_to_cart_tool_normalizer(slots, enabled=True)
    call = {"name": "present_order_preview_tool", "args": {"goods_no": "G0001", "ord_qty": 2}}

    normalized = normalize(call)

    assert normalized["name"] == "save_to_cart_tool"
    assert normalized["args"] == {"goods_no": "G0001", "ord_qty": 2}


async def _assert_staggered_vehicle_size_guard_blocks_purchase_flow(
    monkeypatch: pytest.MonkeyPatch,
    *,
    slots: ConversationSlots | None = None,
    decision: RouteDecision | None = None,
    expected_front_size: str = "225/50R18",
    expected_rear_size: str = "255/50R18",
) -> None:
    slots = slots or ConversationSlots(
        tire_size_front=expected_front_size,
        tire_size_rear=expected_rear_size,
        pending_intent="order",
        goal_type="place_order",
    )
    decision = decision or RouteDecision(domain=Domain.TRANSACTION, intents=["quick_order_reservation"])
    saved_slots = []
    persisted_domains = []

    class ForbiddenExecutor:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("staggered vehicle must choose front/rear size before purchase flow")

    async def fake_route_request(*args, **kwargs):
        return decision

    async def fake_load_slots(session_id):
        return slots

    async def fake_save_slots(session_id, next_slots, user_id=None):
        saved_slots.append(next_slots)

    async def fake_persist_turn_context(session_id, tool_calls, quick_reply_domains, predicted_domains, user_id=None):
        persisted_domains.extend(quick_reply_domains)

    monkeypatch.setattr(service, "route_request", fake_route_request)
    monkeypatch.setattr(service, "load_slots", fake_load_slots)
    monkeypatch.setattr(service, "save_slots", fake_save_slots)
    monkeypatch.setattr(service, "ToolLoopExecutor", ForbiddenExecutor)
    monkeypatch.setattr(service.memory, "persist_turn_context", fake_persist_turn_context)
    monkeypatch.setattr(service, "_flush_trace", lambda: None)

    request = TStationChatRequest(
        messages=[{"role": "user", "content": "order tires for my car"}],
        stream=True,
        user_id="test-user",
        session_id="staggered-guard-test",
    )

    events = []
    async for line in service._run_turn(request, {}):
        event = _parse_sse_event(line)
        if event:
            events.append(event)

    data_events = [event for event in events if event.get("type") == "data"]
    assert data_events
    assert data_events[0]["template"] == "quickReply"
    assert expected_front_size in data_events[0]["data"]["assistantResponse"]
    assert expected_rear_size in data_events[0]["data"]["assistantResponse"]
    assert [chip["label"] for chip in data_events[0]["data"]["quickReplies"]] == [
        "앞바퀴사이즈",
        "뒷바퀴사이즈",
        "다른 사이즈 입력",
    ]
    assert data_events[0]["data"]["quickReplies"][0]["metadata"]["slots"]["tire_size"] == expected_front_size
    assert data_events[0]["data"]["quickReplies"][1]["metadata"]["slots"]["tire_size"] == expected_rear_size
    assert saved_slots[0].tire_size is None
    assert persisted_domains == ["DISCOVERY", "DISCOVERY", "DISCOVERY"]


async def _assert_staggered_simultaneous_purchase_inquiry_does_not_run_tools(
    monkeypatch: pytest.MonkeyPatch,
    *,
    slots: ConversationSlots | None = None,
) -> None:
    slots = slots or ConversationSlots(
        car_no="29조3345",
        tire_size="225/40R19",
        tire_size_front="225/40R19",
        tire_size_rear="255/35R19",
    )
    saved_slots = []
    persisted_domains = []

    class ForbiddenExecutor:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("simultaneous staggered purchase inquiry must not run product/order tools")

    async def fake_route_request(*args, **kwargs):
        return RouteDecision(domain=Domain.TRANSACTION, intents=["simultaneous_purchase_inquiry"])

    async def fake_load_slots(session_id):
        return slots

    async def fake_save_slots(session_id, next_slots, user_id=None):
        saved_slots.append(next_slots)

    async def fake_persist_turn_context(session_id, tool_calls, quick_reply_domains, predicted_domains, user_id=None):
        persisted_domains.extend(quick_reply_domains)

    monkeypatch.setattr(service, "route_request", fake_route_request)
    monkeypatch.setattr(service, "load_slots", fake_load_slots)
    monkeypatch.setattr(service, "save_slots", fake_save_slots)
    monkeypatch.setattr(service, "ToolLoopExecutor", ForbiddenExecutor)
    monkeypatch.setattr(service.memory, "persist_turn_context", fake_persist_turn_context)
    monkeypatch.setattr(service, "_flush_trace", lambda: None)

    request = TStationChatRequest(
        messages=[{"role": "user", "content": "둘다 동시에 구매 못해?"}],
        stream=True,
        user_id="test-user",
        session_id="staggered-simultaneous-purchase-test",
    )

    events = []
    async for line in service._run_turn(request, {}):
        event = _parse_sse_event(line)
        if event:
            events.append(event)

    data_events = [event for event in events if event.get("type") == "data"]
    assert data_events
    assert data_events[0]["template"] == "quickReply"
    answer = data_events[0]["data"]["assistantResponse"]
    assert "가능합니다" not in answer
    assert "한 번에 함께 구매 가능한지는" in answer
    assert "선택한 규격 하나씩 추천/구매" in answer
    assert [chip["label"] for chip in data_events[0]["data"]["quickReplies"]] == [
        "앞바퀴사이즈",
        "뒷바퀴사이즈",
        "다른 사이즈 입력",
    ]
    assert saved_slots[0].tire_size == "225/40R19"
    assert persisted_domains == ["DISCOVERY", "DISCOVERY", "DISCOVERY"]


async def _assert_staggered_vehicle_card_click_guard_blocks_recommendation_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved_slots = []

    class ForbiddenExecutor:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("staggered vehicle card click must choose front/rear size before recommendation flow")

    async def fake_route_request(*args, **kwargs):
        known_slots = kwargs["known_slots"]
        assert known_slots.car_no == "29ì¡°3345"
        assert known_slots.tire_size is None
        assert known_slots.tire_size_front == "225/40R19"
        assert known_slots.tire_size_rear == "255/35R19"
        return RouteDecision(domain=Domain.DISCOVERY, intents=["vehicle_resolved_recommendation"])

    async def fake_load_slots(session_id):
        return ConversationSlots()

    async def fake_save_slots(session_id, next_slots, user_id=None):
        saved_slots.append(next_slots)

    async def fake_noop(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "route_request", fake_route_request)
    monkeypatch.setattr(service, "load_slots", fake_load_slots)
    monkeypatch.setattr(service, "save_slots", fake_save_slots)
    monkeypatch.setattr(service, "ToolLoopExecutor", ForbiddenExecutor)
    monkeypatch.setattr(service.memory, "persist_turn_context", fake_noop)
    monkeypatch.setattr(service, "_flush_trace", lambda: None)

    request = TStationChatRequest(
        messages=[{"role": "user", "content": "select car"}],
        stream=True,
        user_id="test-user",
        session_id="staggered-card-click-guard-test",
        slots={
            "carNo": "29ì¡°3345",
            "carLncCd": "W063680",
            "mbr_car_reg_seq": "2000003099",
            "carModelDet": "3-series(G20 F/L2) M340i A/T",
            "tire_size": "225/40R19",
            "tireSize": "225/40R19",
            "tireSizeRe": "255/35R19",
        },
    )

    events = []
    async for line in service._run_turn(request, {}):
        event = _parse_sse_event(line)
        if event:
            events.append(event)

    data_events = [event for event in events if event.get("type") == "data"]
    assert data_events
    assert data_events[0]["template"] == "quickReply"
    assert "225/40R19" in data_events[0]["data"]["assistantResponse"]
    assert "255/35R19" in data_events[0]["data"]["assistantResponse"]
    assert "3-series(G20 F/L2) M340i A/T" in data_events[0]["data"]["assistantResponse"]
    assert "29ì¡°3345" in data_events[0]["data"]["assistantResponse"]
    assert saved_slots[0].tire_size is None


def test_cart_preview_tool_call_is_preserved_when_guard_disabled() -> None:
    slots = ConversationSlots(goods_no="G0001", ord_qty=4, pending_intent="cart")
    normalize = service._add_to_cart_tool_normalizer(slots, enabled=False)
    call = {"name": "present_order_preview_tool", "args": {"goods_no": "G0001", "ord_qty": 4}}

    assert normalize(call) is call


async def _assert_add_to_cart_quantity_turn_executes_save_to_cart_tool(monkeypatch: pytest.MonkeyPatch) -> None:
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
    persisted_tool_calls = []

    class FakeCartTool:
        name = "save_to_cart_tool"

        async def ainvoke(self, args, config=None):
            assert args == {"goods_no": "G0001", "ord_qty": 4}
            return {"status": "success", "http_status": 200, "data": {"result": True}}

    class ForbiddenExecutor:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("add-to-cart request should execute save_to_cart_tool without preOrder")

    async def fake_route_request(*args, **kwargs):
        assert kwargs["known_slots"].goods_no == "G0001"
        return decision

    async def fake_load_slots(session_id):
        return slots

    async def fake_save_slots(session_id, next_slots, user_id=None):
        saved_slots.append(next_slots)

    async def fake_persist_turn_context(session_id, tool_calls, quick_reply_domains, predicted_domains, user_id=None):
        persisted_tool_calls.extend(tool_calls)

    async def fake_noop(*args, **kwargs):
        return None

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

    tool_events = [event for event in events if event.get("type") == "tool"]
    assert tool_events
    assert tool_events[0]["tool"] == "save_to_cart_tool"
    assert "장바구니에 담았어요" in next(
        event["content"] for event in events if event.get("type") == "message"
    )
    assert persisted_tool_calls[0]["name"] == "save_to_cart_tool"
    assert saved_slots[0].pending_intent == "cart"
    assert saved_slots[0].goal_type == "add_to_cart"


async def _assert_confirmed_cart_stream_executes_save_to_cart_tool(
    monkeypatch: pytest.MonkeyPatch,
    *,
    intent: str = "cart_confirmation",
    slots_patch: SlotsPatch | None = None,
) -> None:
    slots = ConversationSlots(
        goods_no="G0001",
        ord_qty=4,
        pending_product_name="Ventus S2 AS 225/45R17",
    )
    decision = RouteDecision(
        domain=Domain.TRANSACTION,
        intents=[intent],
        slots_patch=slots_patch or SlotsPatch(),
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
