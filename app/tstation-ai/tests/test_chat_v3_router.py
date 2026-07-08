from __future__ import annotations

import os
from datetime import date

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
from services.tstation.chat_v3.router.guards import get_guard  # noqa: E402
from services.tstation.chat_v3.router.route import (  # noqa: E402
    _apply_delivery_policy_guard,
    _apply_runflat_mixed_install_policy,
    _clear_in_range_reservation_date_guard,
    _move_static_faq_guard_to_intent,
)
from services.tstation.chat_v3.router.schemas import Domain, GuardId, RouteDecision  # noqa: E402
from services.tstation.chat_v3.slots.schemas import SlotsPatch  # noqa: E402


def _request(**kwargs) -> TStationChatRequest:
    messages = kwargs.pop("messages", [{"role": "user", "content": "2026년 07월 09일 15:00"}])
    return TStationChatRequest(
        messages=messages,
        stream=True,
        user_id="M200012931",
        session_id="session",
        **kwargs,
    )


def _reservation_guard_decision(requested_cal_day: str | None) -> RouteDecision:
    return RouteDecision(
        guard_id=GuardId.RESERVATION_DATE_RANGE,
        domain=Domain.TRANSACTION,
        intents=["reservation_schedule_selection"],
        slots_patch=SlotsPatch(requested_cal_day=requested_cal_day, rsv_hour="15"),
        needs_selection_card=False,
    )


def test_in_range_reservation_schedule_slot_clears_date_range_guard() -> None:
    decision = _reservation_guard_decision("20260709")

    result = _clear_in_range_reservation_date_guard(decision, _request(), today=date(2026, 7, 8))

    assert result.guard_id == GuardId.NONE
    assert result.slots_patch.requested_cal_day == "20260709"
    assert result.slots_patch.rsv_hour == "15"


def test_out_of_range_reservation_schedule_keeps_date_range_guard() -> None:
    decision = _reservation_guard_decision("20260808")

    result = _clear_in_range_reservation_date_guard(decision, _request(), today=date(2026, 7, 8))

    assert result.guard_id == GuardId.RESERVATION_DATE_RANGE


def test_past_reservation_schedule_keeps_date_range_guard() -> None:
    decision = _reservation_guard_decision("20260707")

    result = _clear_in_range_reservation_date_guard(decision, _request(), today=date(2026, 7, 8))

    assert result.guard_id == GuardId.RESERVATION_DATE_RANGE


def test_in_range_reservation_schedule_from_ui_action_clears_date_range_guard() -> None:
    decision = _reservation_guard_decision(None)
    request = _request(ui_action={"slots": {"requested_cal_day": "20260709", "rsv_hour": "15"}})

    result = _clear_in_range_reservation_date_guard(decision, request, today=date(2026, 7, 8))

    assert result.guard_id == GuardId.NONE


def test_direct_home_delivery_policy_overrides_v3_router_guard() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.SUPPORT,
        intents=["delivery_policy"],
        needs_selection_card=False,
    )
    request = _request(
        messages=[{"role": "user", "content": "타이어 2짝은 매장 장착하고 2짝은 집으로 택배 받을 수 있어?"}]
    )

    result = _apply_delivery_policy_guard(decision, request)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.SUPPORT
    assert result.intents[0] == "direct_home_delivery"


def test_static_faq_router_guard_is_moved_to_support_intent() -> None:
    decision = RouteDecision(
        guard_id=GuardId.PICKUP_INFO,
        domain=Domain.LEADING,
        intents=[],
        needs_selection_card=True,
    )

    result = _move_static_faq_guard_to_intent(decision)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.SUPPORT
    assert result.extra_domains == []
    assert result.needs_selection_card is False
    assert result.intents == ["pickup_info"]


def test_runflat_mixed_install_policy_overrides_vehicle_type_compatibility() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.SUPPORT,
        intents=["vehicle_type_compatibility"],
        needs_selection_card=True,
    )
    request = _request(messages=[{"role": "user", "content": "원래 런플랫 타이어인데 앞바퀴 2짝만 일반 타이어로 바꿔도 돼?"}])

    result = _apply_runflat_mixed_install_policy(decision, request)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.SUPPORT
    assert result.extra_domains == []
    assert result.needs_selection_card is False
    assert result.intents[0] == "runflat_mixed_install_policy"


def test_direct_home_delivery_policy_handles_short_home_delivery_question() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.SUPPORT,
        intents=["delivery_policy"],
        needs_selection_card=False,
    )
    request = _request(messages=[{"role": "user", "content": "타이어 집으로 배송 받을수 있어?"}])

    result = _apply_delivery_policy_guard(decision, request)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.SUPPORT
    assert result.intents[0] == "direct_home_delivery"


def test_delivery_policy_guard_does_not_hijack_order_delivery_status() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.TRANSACTION,
        intents=["order_delivery_status"],
        needs_selection_card=False,
    )
    request = _request(messages=[{"role": "user", "content": "주문 배송 상태 확인해줘"}])

    result = _apply_delivery_policy_guard(decision, request)

    assert result.guard_id == GuardId.NONE


def test_delivery_policy_guard_handles_jeju_shipping_fee() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.SUPPORT,
        intents=["delivery_policy"],
        needs_selection_card=False,
    )
    request = _request(messages=[{"role": "user", "content": "서귀포시인데 배송비 더 들어?"}])

    result = _apply_delivery_policy_guard(decision, request)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.SUPPORT
    assert result.intents[0] == "shipping_fee_region"


def test_delivery_policy_guard_handles_short_shipping_fee_followup() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.SUPPORT,
        intents=["delivery_policy"],
        needs_selection_card=False,
    )
    request = _request(
        messages=[
            {"role": "user", "content": "강원 산간 지역은 배송비 더 들어?"},
            {"role": "assistant", "content": "지역별 추가 배송비는 결제 단계에서 확인해 주세요."},
            {"role": "user", "content": "제주도는?"},
        ]
    )

    result = _apply_delivery_policy_guard(decision, request)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.SUPPORT
    assert result.intents[0] == "shipping_fee_region"


def test_delivery_policy_guard_handles_online_store_price_policy() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.SUPPORT,
        intents=["delivery_policy"],
        needs_selection_card=False,
    )
    request = _request(messages=[{"role": "user", "content": "제주도 매장에서도 온라인 가격이랑 똑같아?"}])

    result = _apply_delivery_policy_guard(decision, request)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.SUPPORT
    assert result.intents[0] == "online_store_price_policy"


def test_delivery_policy_guard_handles_regional_price_policy() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.SUPPORT,
        intents=["delivery_policy"],
        needs_selection_card=False,
    )
    request = _request(messages=[{"role": "user", "content": "제주도는 서울이랑 같은 상품 가격이 달라?"}])

    result = _apply_delivery_policy_guard(decision, request)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.SUPPORT
    assert result.intents[0] == "regional_price_policy"


def test_direct_home_delivery_guard_response_matches_policy() -> None:
    guard = get_guard(GuardId.DIRECT_HOME_DELIVERY)

    assert guard is not None
    assert "집으로 배송받아 직접 장착하는 방식은 지원하지 않아요" in guard.text
    assert [chip["label"] for chip in guard.chips] == ["장착 매장 찾기", "타이어 추천", "구매하기"]


def test_delivery_policy_guard_responses_match_v2_policy_texts() -> None:
    shipping_guard = get_guard(GuardId.SHIPPING_FEE_REGION)
    online_store_guard = get_guard(GuardId.ONLINE_STORE_PRICE_POLICY)
    regional_price_guard = get_guard(GuardId.REGIONAL_PRICE_POLICY)

    assert shipping_guard is not None
    assert "상품 1개당 배송비 1만 원" in shipping_guard.text
    assert online_store_guard is not None
    assert "온라인 판매가와 매장 현장 판매가" in online_store_guard.text
    assert regional_price_guard is not None
    assert "지역, 장착점, 행사, 쿠폰, 재고, 배송 조건" in regional_price_guard.text
