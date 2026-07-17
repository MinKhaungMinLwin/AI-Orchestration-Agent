import asyncio
import json
import os
from types import SimpleNamespace

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

from api.tstation import chat_message as chat_message_module  # noqa: E402
from services.tstation.chat_v3 import service  # noqa: E402
from services.tstation.chat_v3.router.schemas import Domain, RouteDecision  # noqa: E402
from services.tstation.chat_v3.slots.derive import (  # noqa: E402
    apply_fe_slots,
    apply_text_vehicle_selection,
    clamp_staggered_ord_qty,
    derive_slots_from_tool_calls,
    promote_selected_vehicle,
)
from services.tstation.chat_v3.slots.schemas import SlotsPatch  # noqa: E402
from services.tstation.chat_v3.slots.store import slots_context_block  # noqa: E402
from services.tstation.common.cta_urls import CTAUrls  # noqa: E402


def _parse_sse_event(line: str) -> dict | None:
    if not line.startswith("data: "):
        return None
    payload = line.removeprefix("data: ").strip()
    if payload == "[DONE]":
        return None
    return json.loads(payload)


async def _noop_async(*args, **kwargs):
    return None


class _FakeRedis:
    async def exists(self, key: str) -> bool:
        return False

    async def delete(self, key: str) -> None:
        return None


class _FakeStreamResponse:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    @property
    def body_iterator(self):
        async def _iterate():
            for chunk in self._chunks:
                yield chunk

        return _iterate()


def test_preorder_stream_does_not_emit_duplicate_message(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_preorder_stream_does_not_emit_duplicate_message(monkeypatch))


def test_stream_chat_response_saves_preorder_template_without_text(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_stream_chat_response_saves_preorder_template_without_text(monkeypatch))


def test_static_faq_policy_route_uses_registered_ctas(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_static_faq_policy_route_uses_registered_ctas(monkeypatch))


def test_store_visit_schedule_selection_uses_store_detail_cta(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_store_visit_schedule_selection_uses_store_detail_cta(monkeypatch))


def test_cart_confirmation_turn_does_not_write_cart_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_cart_turn_goes_through_executor(monkeypatch, intent="cart_confirmation"))


def test_add_to_cart_intent_goes_through_executor_not_direct_cart(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_cart_turn_goes_through_executor(monkeypatch, intent="add_to_cart"))


def test_place_order_intent_promotes_purchase_flow_state() -> None:
    decision = RouteDecision(domain=Domain.TRANSACTION, intents=["place_order"])

    slots = service._normalize_transaction_goal_slots(decision, ConversationSlots())

    assert slots.goal_type == "place_order"
    assert slots.pending_intent == "order"


def test_place_order_intent_replaces_stale_cart_flow_state() -> None:
    decision = RouteDecision(domain=Domain.TRANSACTION, intents=["place_order"])
    stale_slots = ConversationSlots(goal_type="add_to_cart", pending_intent="cart")

    slots = service._normalize_transaction_goal_slots(decision, stale_slots)

    assert slots.goal_type == "place_order"
    assert slots.pending_intent == "order"


def test_quick_order_attempt_context_keeps_confirmed_order_snapshot() -> None:
    context = chat_message_module._quick_order_attempt_context(
        {
            "goods_no": "G0001",
            "ord_qty": 3,
            "shop_id": "S001",
            "rsv_date": "20260716",
            "rsv_hour": "16",
        },
        {
            "product_name": "Ventus S1 Evo Z AS X 235/55R19",
            "store_name": "T-Station Seocho Branch",
            "booking_datetime": "July 16, 2026 16:00",
            "payment_amount": 768000,
        },
        {"status": "error", "message": "temporary failure"},
    )

    attempt = context["last_order_attempt"]

    assert attempt["tool"] == "quick_order_tool"
    assert attempt["status"] == "error"
    assert attempt["message"] == "temporary failure"
    assert attempt["order"]["ord_qty"] == 3
    assert attempt["order"]["requested_cal_day"] == "20260716"
    assert attempt["order"]["rsv_hour"] == "16"


def test_slots_context_block_guides_failed_order_attempt_recovery() -> None:
    slots = ConversationSlots(
        goods_no="G0001",
        tire_size="235/55R19",
        ord_qty=3,
        shop_id="S001",
        requested_cal_day="20260716",
        rsv_hour="16",
        order_context={
            "last_order_attempt": {
                "tool": "quick_order_tool",
                "status": "error",
                "order": {"ord_qty": 3},
            }
        },
    )

    context = slots_context_block(slots)

    assert context is not None
    assert "order_attempt_recovery_guidance" in context
    assert "last_order_attempt" in context
    assert "schedule/date picker" in context


def test_installation_schedule_change_clears_old_schedule_but_keeps_order_core() -> None:
    decision = RouteDecision(domain=Domain.TRANSACTION, installation_schedule_change=True)
    slots = ConversationSlots(
        goods_no="G0001",
        tire_size="225/45R17",
        ord_qty=3,
        shop_id="S001",
        shop_name="T-Station Songpa Samjeon Branch",
        requested_cal_day="20260716",
        rsv_hour="11",
        payment_amount=356400,
        price_basis="payment_amount",
        price_source_tool="get_final_price_tool",
        price_facts={"amount": 356400},
        coupon_facts={"used": True},
        pending_intent="order",
        goal_type="place_order",
    )

    updated = service._apply_installation_schedule_change_intent(decision, slots)

    assert updated.goods_no == "G0001"
    assert updated.ord_qty == 3
    assert updated.shop_id == "S001"
    assert updated.shop_name == "T-Station Songpa Samjeon Branch"
    assert updated.requested_cal_day is None
    assert updated.rsv_hour is None
    assert updated.payment_amount is None
    assert updated.price_basis is None
    assert updated.price_source_tool is None
    assert updated.price_facts is None
    assert updated.coupon_facts is None
    assert updated.pending_intent == "order"
    assert updated.goal_type == "place_order"


def test_store_finder_intent_does_not_infer_purchase_flow_state() -> None:
    decision = RouteDecision(domain=Domain.TRANSACTION, intents=["store_finder"])

    slots = service._normalize_transaction_goal_slots(decision, ConversationSlots())

    assert slots.goal_type is None
    assert slots.pending_intent is None


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


async def _assert_static_faq_policy_route_uses_registered_ctas(monkeypatch: pytest.MonkeyPatch) -> None:
    saved_slots = []
    persisted_context = {}

    async def fake_route_request(*args, **kwargs):
        return RouteDecision(
            domain=Domain.SUPPORT,
            intents=["maintenance_history_access_policy"],
            needs_selection_card=False,
        )

    async def fake_load_slots(session_id):
        return ConversationSlots()

    async def fake_save_slots(session_id, next_slots, user_id=None):
        saved_slots.append(next_slots)

    async def fake_persist_turn_context(session_id, tool_calls, quick_reply_domains, predicted_domains, user_id=None):
        persisted_context["tool_calls"] = tool_calls
        persisted_context["quick_reply_domains"] = quick_reply_domains
        persisted_context["predicted_domains"] = predicted_domains

    async def forbidden_composer(*args, **kwargs):
        raise AssertionError("static FAQ policy must use registered quick replies")

    monkeypatch.setattr(service, "route_request", fake_route_request)
    monkeypatch.setattr(service, "load_slots", fake_load_slots)
    monkeypatch.setattr(service, "save_slots", fake_save_slots)
    monkeypatch.setattr(service.memory, "persist_turn_context", fake_persist_turn_context)
    monkeypatch.setattr(service, "_record_real_usage", _noop_async)
    monkeypatch.setattr(service, "_flush_trace", lambda: None)
    monkeypatch.setattr(service.composer, "suggest_quick_replies", forbidden_composer)

    request = TStationChatRequest(
        messages=[{"role": "user", "content": "정비이력은 어디서 확인해?"}],
        stream=True,
        user_id="test-user",
        session_id="static-faq-policy-cta-test",
    )

    events = []
    async for line in service._run_turn(request, {}):
        event = _parse_sse_event(line)
        if event:
            events.append(event)

    data_events = [event for event in events if event.get("type") == "data"]
    assert data_events
    assert data_events[0]["assistant_response_source"] == "code_static_faq_policy"
    quick_replies = data_events[0]["data"]["quickReplies"]
    assert quick_replies[0]["url"] == CTAUrls.STORE_SERVICE_HISTORY
    assert all(chip.get("url") != CTAUrls.MY_COUPON_LIST_PC for chip in quick_replies)
    assert saved_slots
    assert persisted_context["tool_calls"] == []


async def _assert_store_visit_schedule_selection_uses_store_detail_cta(monkeypatch: pytest.MonkeyPatch) -> None:
    persisted_context = {}

    async def fake_route_request(*args, **kwargs):
        return RouteDecision(
            domain=Domain.TRANSACTION,
            intents=["store_schedule"],
            needs_selection_card=False,
        )

    async def fake_load_slots(session_id):
        return ConversationSlots(
            shop_id="F203675962",
            shop_name="티스테이션 한남점",
            ord_qty=1,
            pending_intent="reservation",
        )

    async def fake_save_slots(session_id, next_slots, user_id=None):
        assert next_slots.requested_cal_day == "20260715"
        assert next_slots.rsv_hour == "17"

    async def fake_persist_turn_context(session_id, tool_calls, quick_reply_domains, predicted_domains, user_id=None):
        persisted_context["tool_calls"] = tool_calls
        persisted_context["quick_reply_domains"] = quick_reply_domains
        persisted_context["predicted_domains"] = predicted_domains

    async def forbidden_composer(*args, **kwargs):
        raise AssertionError("store visit schedule selection must use the registered store-detail CTA")

    monkeypatch.setattr(service, "route_request", fake_route_request)
    monkeypatch.setattr(service, "load_slots", fake_load_slots)
    monkeypatch.setattr(service, "save_slots", fake_save_slots)
    monkeypatch.setattr(service.memory, "persist_turn_context", fake_persist_turn_context)
    monkeypatch.setattr(service, "_record_real_usage", _noop_async)
    monkeypatch.setattr(service, "_flush_trace", lambda: None)
    monkeypatch.setattr(service.composer, "suggest_quick_replies", forbidden_composer)

    request = TStationChatRequest(
        messages=[{"role": "user", "content": "2026년 07월 15일\n17:00"}],
        stream=True,
        user_id="test-user",
        session_id="store-visit-schedule-cta-test",
        slots={"requested_cal_day": "20260715", "rsv_hour": "17", "ord_qty": 1},
    )

    events = []
    async for line in service._run_turn(request, {}):
        event = _parse_sse_event(line)
        if event:
            events.append(event)

    data_events = [event for event in events if event.get("type") == "data"]
    assert data_events
    assert data_events[0]["assistant_response_source"] == "code_store_visit_schedule_redirect"
    quick_replies = data_events[0]["data"]["quickReplies"]
    assert quick_replies[0]["label"] == "매장 상세 페이지로 이동"
    assert quick_replies[0]["url"] == CTAUrls.STORE_DETAIL.replace("<shop_seq>", "F203675962")
    assert quick_replies[0]["domain"] == "TRANSACTION"
    assert "타이어 추천 받기" not in [chip["label"] for chip in quick_replies]
    assert "1:1 문의하기" not in [chip["label"] for chip in quick_replies]
    assert persisted_context["tool_calls"] == []


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


def test_staggered_size_choice_chips_do_not_carry_cart_state() -> None:
    slots = ConversationSlots(
        car_no="29ì¡°3345",
        car_lnc_cd="W063680",
        car_model="BMW 3 Series M340i A/T",
        tire_size_front="225/40R19",
        tire_size_rear="255/35R19",
        goods_no="G0001",
        ord_qty=2,
        pending_intent="cart",
        goal_type="add_to_cart",
        shop_id="S0001",
        requested_cal_day="20260710",
    )

    event = service._staggered_tire_size_choice_event(slots)

    assert event is not None
    for chip in event["data"]["quickReplies"][:2]:
        chip_slots = chip["metadata"]["slots"]
        assert chip_slots["car_no"] == "29ì¡°3345"
        assert chip_slots["tire_size"] in {"225/40R19", "255/35R19"}
        assert chip_slots["tire_size_front"] == "225/40R19"
        assert chip_slots["tire_size_rear"] == "255/35R19"
        assert "goods_no" not in chip_slots
        assert "ord_qty" not in chip_slots
        assert "pending_intent" not in chip_slots
        assert "goal_type" not in chip_slots
        assert "shop_id" not in chip_slots
        assert "requested_cal_day" not in chip_slots


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


def test_router_model_hint_promotes_staggered_vehicle_without_launch_code() -> None:
    tool_output = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "29조3345",
                    "car_lnc_cd": "W063680",
                    "car_maker": "BMW",
                    "car_model_det": "3-series(G20 F/L2) M340i A/T",
                    "tire_size_fr": "225/40R19",
                    "tire_size_re": "255/35R19",
                },
                {
                    "car_no": "29조3344",
                    "car_lnc_cd": "W036270",
                    "car_maker": "Volkswagen",
                    "car_model_det": "Jetta",
                    "tire_size_fr": "225/45R17",
                    "tire_size_re": "225/45R17",
                },
            ]
        },
    }
    tool_calls = [{"name": "get_my_cars_tool", "args": {}, "output": json.dumps(tool_output, ensure_ascii=False)}]
    slots = derive_slots_from_tool_calls(ConversationSlots(car_model="BMW"), tool_calls)

    promoted = promote_selected_vehicle(slots, tool_calls, car_model_hint="BMW")

    assert promoted.car_no == "29조3345"
    assert promoted.tire_size is None
    assert promoted.tire_size_front == "225/40R19"
    assert promoted.tire_size_rear == "255/35R19"
    assert service._staggered_tire_size_choice_event(promoted) is not None


def test_generic_vehicle_list_does_not_auto_select_staggered_candidate() -> None:
    tool_output = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "29조3345",
                    "car_maker": "BMW",
                    "car_model_det": "M340i",
                    "tire_size_fr": "225/40R19",
                    "tire_size_re": "255/35R19",
                }
            ]
        },
    }
    tool_calls = [{"name": "get_my_cars_tool", "args": {}, "output": json.dumps(tool_output, ensure_ascii=False)}]
    slots = derive_slots_from_tool_calls(ConversationSlots(), tool_calls)

    promoted = promote_selected_vehicle(slots, tool_calls)

    assert promoted.car_no is None
    assert promoted.tire_size_front is None
    assert promoted.vehicle_candidates


def test_plate_lookup_promotes_staggered_vehicle_before_next_flow() -> None:
    tool_output = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "29조3345",
                    "car_maker": "BMW",
                    "car_model_det": "M340i",
                    "tire_size_fr": "225/40R19",
                    "tire_size_re": "255/35R19",
                }
            ]
        },
    }
    tool_calls = [
        {
            "name": "get_user_vehicles_tool",
            "args": {"car_no": "29조3345", "owner_nm": "공태웅"},
            "output": json.dumps(tool_output, ensure_ascii=False),
        }
    ]
    slots = derive_slots_from_tool_calls(ConversationSlots(car_no="29조3345"), tool_calls)

    promoted = promote_selected_vehicle(slots, tool_calls)

    assert promoted.car_no == "29조3345"
    assert promoted.tire_size is None
    assert promoted.tire_size_front == "225/40R19"
    assert promoted.tire_size_rear == "255/35R19"


def test_selected_staggered_size_survives_vehicle_repromotion() -> None:
    slots = ConversationSlots(
        car_no="29조3345",
        car_model="BMW",
        tire_size="255/35R19",
        tire_size_front="225/40R19",
        tire_size_rear="255/35R19",
        vehicle_candidates=[
            {
                "car_no": "29조3345",
                "car_lnc_cd": "W063680",
                "car_maker": "BMW",
                "car_model": "M340i",
                "tire_size_front": "225/40R19",
                "tire_size_rear": "255/35R19",
            }
        ],
    )
    tool_calls = [
        {
            "name": "get_products_recommendations_tool",
            "args": {"tire_size": "255/35R19"},
            "output": '{"status":"success","data":{"items":[]}}',
        }
    ]

    promoted = promote_selected_vehicle(slots, tool_calls, car_model_hint="BMW")

    assert promoted.tire_size == "255/35R19"
    assert service._staggered_tire_size_choice_event(promoted) is None


def test_staggered_ord_qty_is_clamped_to_two_even_when_typed() -> None:
    slots = ConversationSlots(tire_size_front="225/40R19", tire_size_rear="255/35R19", ord_qty=4)

    assert clamp_staggered_ord_qty(slots).ord_qty == 2


def test_staggered_ord_qty_within_limit_is_kept() -> None:
    slots = ConversationSlots(tire_size_front="225/40R19", tire_size_rear="255/35R19", ord_qty=1)

    assert clamp_staggered_ord_qty(slots).ord_qty == 1


def test_same_size_vehicle_ord_qty_is_not_clamped() -> None:
    slots = ConversationSlots(tire_size_front="225/45R17", tire_size_rear="225/45R17", ord_qty=4)

    assert clamp_staggered_ord_qty(slots).ord_qty == 4


def test_staggered_qty_tool_normalizer_caps_cart_and_order_args() -> None:
    slots = ConversationSlots(tire_size_front="225/40R19", tire_size_rear="255/35R19")
    normalize = service._staggered_qty_tool_normalizer(slots)

    cart_call = normalize({"name": "save_to_cart_tool", "args": {"goods_no": "G0001", "ord_qty": 4}})
    order_call = normalize({"name": "quick_order_tool", "args": {"goods_no": "G0001", "ord_qty": 3, "shop_id": "C1"}})

    assert cart_call["args"]["ord_qty"] == 2
    assert order_call["args"]["ord_qty"] == 2


def test_staggered_qty_tool_normalizer_ignores_same_size_vehicle() -> None:
    slots = ConversationSlots(tire_size_front="225/45R17", tire_size_rear="225/45R17")
    normalize = service._staggered_qty_tool_normalizer(slots)

    call = normalize({"name": "save_to_cart_tool", "args": {"goods_no": "G0001", "ord_qty": 4}})

    assert call["args"]["ord_qty"] == 4


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


def test_direct_staggered_availability_requests_size_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(
        _assert_staggered_vehicle_size_guard_blocks_purchase_flow(
            monkeypatch,
            slots=ConversationSlots(),
            decision=RouteDecision(
                domain=Domain.TRANSACTION,
                intents=["store_with_stock"],
                slots_patch=SlotsPatch(
                    tire_size_front="245 40 r19",
                    tire_size_rear="275 35 r19",
                    tire_model="Ventus S2 AS",
                    region="Dongtan",
                ),
            ),
            expected_front_size="245/40R19",
            expected_rear_size="275/35R19",
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


def test_staggered_size_chip_selection_requests_quantity_before_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_staggered_size_chip_selection_requests_quantity_before_tools(monkeypatch))


def test_staggered_region_followup_bypasses_simultaneous_purchase_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_assert_staggered_region_followup_bypasses_simultaneous_purchase_guard(monkeypatch))


def test_cart_write_guard_blocks_save_to_cart_without_explicit_request() -> None:
    decision = RouteDecision(domain=Domain.TRANSACTION, intents=["price_check"])
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "네"}], stream=True, user_id="u", session_id="s"
    )
    guard = service._cart_write_guard(decision, request)

    assert guard({"name": "save_to_cart_tool", "args": {"goods_no": "G1", "ord_qty": 2}}) is not None
    assert guard({"name": "get_final_price_tool", "args": {"goods_no": "G1"}}) is None


def test_cart_write_guard_allows_explicit_intent_or_cart_button() -> None:
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "장바구니에 담아줘"}], stream=True, user_id="u", session_id="s"
    )
    decision = RouteDecision(domain=Domain.TRANSACTION, intents=["add_to_cart"])
    assert service._cart_write_guard(decision, request)({"name": "save_to_cart_tool", "args": {}}) is None

    button_request = TStationChatRequest(
        messages=[{"role": "user", "content": "장바구니 담기"}],
        stream=True,
        user_id="u",
        session_id="s",
        chip_context={"metadata": {"cta_action": "add_to_cart"}},
    )
    no_intent = RouteDecision(domain=Domain.TRANSACTION, intents=[])
    assert service._cart_write_guard(no_intent, button_request)({"name": "save_to_cart_tool", "args": {}}) is None


def test_transaction_tool_guard_blocks_order_tools_until_staggered_size_is_selected() -> None:
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "continue"}], stream=True, user_id="u", session_id="s"
    )
    decision = RouteDecision(domain=Domain.TRANSACTION, intents=["place_order"])
    slots = ConversationSlots(tire_size_front="245/40R19", tire_size_rear="275/35R19")
    guard = service._transaction_tool_guard(decision, request, slots)

    for tool_name in ("present_order_preview_tool", "quick_order_tool", "save_to_cart_tool"):
        assert guard({"name": tool_name, "args": {}}) is not None
    assert guard({"name": "get_store_install_availability_tool", "args": {}}) is None


def test_transaction_tool_guard_allows_order_after_staggered_size_selection() -> None:
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "continue"}], stream=True, user_id="u", session_id="s"
    )
    decision = RouteDecision(domain=Domain.TRANSACTION, intents=["place_order"])
    slots = ConversationSlots(
        tire_size="245/40R19",
        tire_size_front="245/40R19",
        tire_size_rear="275/35R19",
    )
    guard = service._transaction_tool_guard(decision, request, slots)

    assert guard({"name": "present_order_preview_tool", "args": {}}) is None
    assert guard({"name": "quick_order_tool", "args": {}}) is None


def test_executor_guard_blocks_tool_invocation() -> None:
    asyncio.run(_assert_executor_guard_blocks_tool_invocation())


async def _assert_executor_guard_blocks_tool_invocation() -> None:
    invoked = []

    class FakeCartTool:
        name = "save_to_cart_tool"

        async def ainvoke(self, args, config=None):
            invoked.append(args)
            return {"status": "success"}

    executor = service.ToolLoopExecutor(
        [],
        [FakeCartTool()],
        {},
        tool_call_guard=lambda call: "blocked" if call.get("name") == "save_to_cart_tool" else None,
    )
    events = []
    async for event in executor._run_tool({"name": "save_to_cart_tool", "args": {"goods_no": "G1", "ord_qty": 1}, "id": "c1"}):
        events.append(event)

    assert not invoked, "guarded tool must not be invoked"
    assert executor.tool_calls[0]["output"].startswith("Tool error: blocked_by_policy")


def test_preview_tool_call_is_never_rewritten_to_cart_write() -> None:
    slots = ConversationSlots(goods_no="G0001", ord_qty=4, pending_intent="cart")
    normalize = service._staggered_qty_tool_normalizer(slots)
    call = {"name": "present_order_preview_tool", "args": {"goods_no": "G0001", "ord_qty": 4}, "id": "call-1"}

    assert normalize(call) is call


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
        f"앞 타이어 {expected_front_size}",
        f"뒤 타이어 {expected_rear_size}",
    ]
    assert data_events[0]["data"]["quickReplies"][0]["metadata"]["slots"]["tire_size"] == expected_front_size
    assert data_events[0]["data"]["quickReplies"][1]["metadata"]["slots"]["tire_size"] == expected_rear_size
    assert saved_slots[0].tire_size is None
    assert persisted_domains == ["DISCOVERY", "DISCOVERY"]


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
        "앞 타이어 225/40R19",
        "뒤 타이어 255/35R19",
    ]
    assert saved_slots[0].tire_size == "225/40R19"
    assert persisted_domains == ["DISCOVERY", "DISCOVERY"]


async def _assert_staggered_size_chip_selection_requests_quantity_before_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = ConversationSlots(
        car_no="29조3345",
        tire_size_front="225/40R19",
        tire_size_rear="255/35R19",
    )

    class ForbiddenExecutor:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("quantity must be selected before product or availability tools run")

    async def fake_route_request(*args, **kwargs):
        return RouteDecision(domain=Domain.DISCOVERY, intents=["staggered_simultaneous_purchase_inquiry"])

    async def fake_load_slots(session_id):
        return slots

    async def fake_noop(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "route_request", fake_route_request)
    monkeypatch.setattr(service, "load_slots", fake_load_slots)
    monkeypatch.setattr(service, "ToolLoopExecutor", ForbiddenExecutor)
    monkeypatch.setattr(service, "tools_for_domains", lambda domains, tool_profile=None: [])
    monkeypatch.setattr(service.qc, "verify_answer", fake_verify_answer)
    monkeypatch.setattr(service, "save_slots", fake_noop)
    monkeypatch.setattr(service.memory, "persist_turn_context", fake_noop)
    monkeypatch.setattr(service, "_flush_trace", lambda: None)

    request = TStationChatRequest(
        messages=[{"role": "user", "content": "앞바퀴사이즈"}],
        stream=True,
        user_id="test-user",
        session_id="staggered-size-chip-guard-bypass-test",
        chip_context={
            "metadata": {
                "slots": {
                    "tire_size": "225/40R19",
                    "tire_size_front": "225/40R19",
                    "tire_size_rear": "255/35R19",
                    "car_no": "29조3345",
                }
            }
        },
    )

    events = []
    async for line in service._run_turn(request, {}):
        event = _parse_sse_event(line)
        if event:
            events.append(event)

    data_events = [event for event in events if event.get("type") == "data"]
    assert data_events
    assert data_events[0]["data"]["assistantResponse"] == (
        "225/40R19 기준으로 확인하겠습니다. 필요한 타이어 수량을 선택해 주세요."
    )
    assert [chip["label"] for chip in data_events[0]["data"]["quickReplies"]] == ["1개", "2개"]
    assert [chip["metadata"]["slots"]["ord_qty"] for chip in data_events[0]["data"]["quickReplies"]] == [1, 2]


async def _assert_staggered_region_followup_bypasses_simultaneous_purchase_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = ConversationSlots(
        car_no="29조3345",
        tire_size="255/35R19",
        tire_size_front="225/40R19",
        tire_size_rear="255/35R19",
        goods_no="G0001",
        ord_qty=2,
        pending_intent="cart",
        goal_type="add_to_cart",
    )
    saved_slots = []

    class FakeExecutor:
        def __init__(self, *args, **kwargs) -> None:
            self.final_text = "Continuing with the selected rear tire in Bundang."
            self.tool_calls = []

        async def stream(self):
            yield service.sse.token("Continuing with the selected rear tire in Bundang.")

    async def fake_route_request(*args, **kwargs):
        return RouteDecision(
            domain=Domain.TRANSACTION,
            intents=["staggered_simultaneous_purchase_inquiry"],
            slots_patch=SlotsPatch(region="분당"),
        )

    async def fake_load_slots(session_id):
        return slots

    async def fake_verify_answer(answer, tool_calls, trace_config):
        return answer

    async def fake_save_slots(session_id, next_slots, user_id=None):
        saved_slots.append(next_slots)

    async def fake_noop(*args, **kwargs):
        return None

    async def fake_chips(*args, **kwargs):
        return []

    monkeypatch.setattr(service, "route_request", fake_route_request)
    monkeypatch.setattr(service, "load_slots", fake_load_slots)
    monkeypatch.setattr(service, "tools_for_domains", lambda domains, tool_profile=None: [])
    monkeypatch.setattr(service, "ToolLoopExecutor", FakeExecutor)
    monkeypatch.setattr(service.qc, "verify_answer", fake_verify_answer)
    monkeypatch.setattr(service, "save_slots", fake_save_slots)
    monkeypatch.setattr(service.memory, "load_tool_context_block", fake_noop)
    monkeypatch.setattr(service.memory, "persist_turn_context", fake_noop)
    monkeypatch.setattr(service.templates, "build_rich_data_event", fake_noop)
    monkeypatch.setattr(service.composer, "suggest_quick_replies", fake_chips)
    monkeypatch.setattr(service, "_flush_trace", lambda: None)

    request = TStationChatRequest(
        messages=[{"role": "user", "content": "분당"}],
        stream=True,
        user_id="test-user",
        session_id="staggered-region-followup-test",
    )

    events = []
    async for line in service._run_turn(request, {}):
        event = _parse_sse_event(line)
        if event:
            events.append(event)

    messages = [event["content"] for event in events if event.get("type") == "message"]
    assert messages == ["Continuing with the selected rear tire in Bundang."]
    data_events = [event for event in events if event.get("type") == "data"]
    assert data_events
    answer = data_events[0]["data"]["assistantResponse"]
    assert "한 번에 함께 구매 가능한지는" not in answer
    assert "225/40R19" not in answer
    assert saved_slots[0].tire_size == "255/35R19"
    assert saved_slots[0].region == "분당"


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
    assert "앞/뒤 타이어 규격이 다른 차량으로 확인되었습니다" in data_events[0]["data"]["assistantResponse"]
    assert saved_slots[0].tire_size is None


async def _assert_cart_turn_goes_through_executor(
    monkeypatch: pytest.MonkeyPatch,
    *,
    intent: str,
) -> None:
    """고객 요구사항: 어떤 intent 도 장바구니 쓰기를 직접 실행하지 않는다 —
    save_to_cart_tool 은 항상 일반 tool executor 루프를 통해서만 호출된다."""
    slots = ConversationSlots(
        goods_no="G0001",
        ord_qty=4,
        pending_product_name="Ventus S2 AS 225/45R17",
    )
    decision = RouteDecision(domain=Domain.TRANSACTION, intents=[intent])
    executor_created = []

    class FakeExecutor:
        def __init__(self, *args, **kwargs) -> None:
            executor_created.append(True)
            self.final_text = "장바구니에 담아드릴까요?"
            self.tool_calls = []

        async def stream(self):
            yield service.sse.token("장바구니에 담아드릴까요?")

    async def fake_route_request(*args, **kwargs):
        return decision

    async def fake_load_slots(session_id):
        return slots

    async def fake_verify_answer(answer, tool_calls, trace_config):
        return answer

    async def fake_noop(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "route_request", fake_route_request)
    monkeypatch.setattr(service, "load_slots", fake_load_slots)
    monkeypatch.setattr(service, "save_slots", fake_noop)
    monkeypatch.setattr(service, "tools_for_domains", lambda domains, tool_profile=None: [])
    monkeypatch.setattr(service, "ToolLoopExecutor", FakeExecutor)
    monkeypatch.setattr(service.qc, "verify_answer", fake_verify_answer)
    monkeypatch.setattr(service.memory, "load_tool_context_block", fake_noop)
    monkeypatch.setattr(service.memory, "persist_turn_context", fake_noop)
    monkeypatch.setattr(service, "_flush_trace", lambda: None)

    request = TStationChatRequest(
        messages=[
            {"role": "assistant", "content": "맞으면 장바구니에 담아드릴게요."},
            {"role": "user", "content": "네"},
        ],
        stream=True,
        user_id="test-user",
        session_id=f"cart-executor-only-{intent}",
    )

    events = []
    async for line in service._run_turn(request, {}):
        event = _parse_sse_event(line)
        if event:
            events.append(event)

    assert executor_created, "cart turns must run the normal executor loop"
    cart_tool_events = [
        event for event in events if event.get("type") == "tool" and event.get("tool") == "save_to_cart_tool"
    ]
    assert not cart_tool_events, "no deterministic save_to_cart_tool call outside the executor"


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
    monkeypatch.setattr(service, "tools_for_domains", lambda domains, tool_profile=None: [])
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


async def _assert_stream_chat_response_saves_preorder_template_without_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved_messages: list[dict] = []
    preorder_event = {
        "type": "data",
        "template": "preOrder",
        "data": {
            "orderInfo": {"product": "Ventus S2 AS", "quantity": 4},
            "isReadyToOrder": True,
            "isReadyToAddToCart": False,
            "metadata": {"goodsNo": "G0001"},
        },
    }

    class FakeChatService:
        @staticmethod
        async def chat(chat_request):
            return _FakeStreamResponse([
                f"data: {json.dumps(preorder_event, ensure_ascii=False)}\n\n",
                "data: [DONE]\n\n",
            ])

    class FakeHistoryService:
        def save_message(self, session_id, role, content, template_data=None, user_id=None):
            saved_messages.append({
                "session_id": session_id,
                "role": role,
                "content": content,
                "template_data": template_data,
                "user_id": user_id,
            })
            return "saved-message"

    async def fake_refresh_summary(session_id: str) -> None:
        return None

    monkeypatch.setattr(chat_message_module, "TStationChatServiceV2", FakeChatService)
    monkeypatch.setattr("services.tstation.chat.TStationChatServiceV2", FakeChatService)
    monkeypatch.setattr("services.tstation.chat_history_service.get_async_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr("services.tstation.history_summarizer.refresh_summary", fake_refresh_summary)

    chat_request = SimpleNamespace(
        messages=[{"role": "user", "content": "2026년 07월 21일 10:00"}],
        user_id="u1",
    )

    chunks = [
        chunk
        async for chunk in chat_message_module.stream_chat_response(
            chat_request,
            "s1",
            "m1",
            FakeHistoryService(),
        )
    ]

    assert chunks[-1] == "data: [DONE]\n\n"
    assert saved_messages == [
        {
            "session_id": "s1",
            "role": "assistant",
            "content": "",
            "template_data": preorder_event,
            "user_id": "u1",
        }
    ]
