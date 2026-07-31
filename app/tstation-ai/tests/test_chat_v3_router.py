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
from schemas.tstation.slots import ConversationSlots  # noqa: E402
from services.tstation.chat_v3.router.guards import get_guard  # noqa: E402
from services.tstation.chat_v3.router.route import (  # noqa: E402
    _apply_delivery_policy_guard,
    _apply_late_night_store_hours_policy,
    _apply_pickup_service_policy,
    _apply_runflat_mixed_install_policy,
    _clear_non_target_unsupported_brand_guard,
    _decide_reservation_date_guard,
    _move_static_faq_guard_to_intent,
    _router_input,
    _validate_nonexistent_benefit_guard,
)
from services.tstation.chat_v3.router.schemas import (  # noqa: E402
    BenefitContext,
    BrandContext,
    Domain,
    GuardId,
    RouteDecision,
    ToolProfile,
)
from services.tstation.chat_v3.slots.derive import reset_for_supported_brand_switch  # noqa: E402
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

    result = _decide_reservation_date_guard(decision, _request(), today=date(2026, 7, 8))

    assert result.guard_id == GuardId.NONE
    assert result.slots_patch.requested_cal_day == "20260709"
    assert result.slots_patch.rsv_hour == "15"


def test_out_of_range_reservation_schedule_keeps_date_range_guard() -> None:
    decision = _reservation_guard_decision("20260808")

    result = _decide_reservation_date_guard(decision, _request(), today=date(2026, 7, 8))

    assert result.guard_id == GuardId.RESERVATION_DATE_RANGE


def test_past_reservation_schedule_keeps_date_range_guard() -> None:
    decision = _reservation_guard_decision("20260707")

    result = _decide_reservation_date_guard(decision, _request(), today=date(2026, 7, 8))

    assert result.guard_id == GuardId.RESERVATION_DATE_RANGE


def test_in_range_reservation_schedule_from_ui_action_clears_date_range_guard() -> None:
    decision = _reservation_guard_decision(None)
    request = _request(ui_action={"slots": {"requested_cal_day": "20260709", "rsv_hour": "15"}})

    result = _decide_reservation_date_guard(decision, request, today=date(2026, 7, 8))

    assert result.guard_id == GuardId.NONE


def test_out_of_window_date_sets_guard_the_router_did_not_pick() -> None:
    """The router no longer judges the booking window — the extracted date does."""
    decision = _reservation_guard_decision("20261225")
    decision.guard_id = GuardId.NONE

    result = _decide_reservation_date_guard(decision, _request(), today=date(2026, 7, 8))

    assert result.guard_id == GuardId.RESERVATION_DATE_RANGE


def test_guard_without_any_known_date_is_cleared() -> None:
    """'Your date is out of range' is indefensible when no date is known — this is how an
    insistent 'can I get it TODAY?' used to receive a canned out-of-range answer."""
    decision = _reservation_guard_decision(None)

    result = _decide_reservation_date_guard(decision, _request(), today=date(2026, 7, 8))

    assert result.guard_id == GuardId.NONE


def test_nonexistent_benefit_guard_is_cleared_without_current_turn_evidence() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONEXISTENT_BENEFIT,
        domain=Domain.TRANSACTION,
        intents=["my_coupons_lookup"],
        tool_profile=ToolProfile.TRANSACTION_COUPON,
    )
    request = _request(
        messages=[
            {"role": "user", "content": "50% 쿠폰은 없어?"},
            {"role": "assistant", "content": "보유 쿠폰을 확인해 드렸어요."},
            {"role": "user", "content": "아니 내 쿠폰 말고 20% 할인되는 쿠폰은 어딨어?"},
        ]
    )

    result = _validate_nonexistent_benefit_guard(decision, request)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.TRANSACTION
    assert result.intents == ["my_coupons_lookup"]


def test_nonexistent_benefit_guard_ignores_evidence_copied_only_from_history() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONEXISTENT_BENEFIT,
        domain=Domain.TRANSACTION,
        intents=["my_coupons_lookup"],
        tool_profile=ToolProfile.TRANSACTION_COUPON,
        benefit_context=BenefitContext(
            unverified_benefit_target="VIP 전용",
            unverified_access_request="할인 링크 줘",
        ),
    )
    request = _request(
        messages=[
            {"role": "user", "content": "VIP 전용 할인 링크 줘"},
            {"role": "assistant", "content": "확인되지 않은 링크는 제공할 수 없어요."},
            {"role": "user", "content": "그건 됐고 지금 받을 수 있는 할인 쿠폰 알려줘"},
        ]
    )

    result = _validate_nonexistent_benefit_guard(decision, request)

    assert result.guard_id == GuardId.NONE


def test_nonexistent_benefit_guard_stays_for_grounded_exclusive_access_request() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONEXISTENT_BENEFIT,
        domain=Domain.TRANSACTION,
        intents=["unverified_exclusive_benefit"],
        tool_profile=ToolProfile.TRANSACTION_COUPON,
        benefit_context=BenefitContext(
            unverified_benefit_target="VIP 전용 할인",
            unverified_access_request="링크 줘",
        ),
    )
    request = _request(messages=[{"role": "user", "content": "VIP 전용 할인 링크 줘"}])

    result = _validate_nonexistent_benefit_guard(decision, request)

    assert result.guard_id == GuardId.NONEXISTENT_BENEFIT
    assert result.domain == Domain.TRANSACTION


def test_owned_coupon_exclusion_moves_followup_to_general_benefit_discovery() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONEXISTENT_BENEFIT,
        domain=Domain.TRANSACTION,
        intents=["my_coupons_lookup"],
        tool_profile=ToolProfile.TRANSACTION_COUPON,
        benefit_context=BenefitContext(owned_coupon_exclusion="내 쿠폰 말고"),
    )
    request = _request(
        messages=[{"role": "user", "content": "아니 내 쿠폰 말고 20% 할인되는 쿠폰은 어딨어?"}]
    )

    result = _validate_nonexistent_benefit_guard(decision, request)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.DISCOVERY
    assert result.extra_domains == []
    assert result.intents == ["benefit_event_lookup"]
    assert result.tool_profile == ToolProfile.DISCOVERY_EVENT_CONTENT
    assert result.needs_selection_card is True


def test_non_coupon_route_is_unchanged_by_benefit_guard_validation() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.DISCOVERY,
        intents=["product_search"],
        tool_profile=ToolProfile.DISCOVERY_SEARCH,
    )

    result = _validate_nonexistent_benefit_guard(
        decision,
        _request(messages=[{"role": "user", "content": "벤투스 상품 찾아줘"}]),
    )

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.DISCOVERY
    assert result.intents == ["product_search"]
    assert result.tool_profile == ToolProfile.DISCOVERY_SEARCH


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


def test_pickup_visit_constraint_policy_overrides_v3_router_guard() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.TRANSACTION,
        intents=["store_search"],
        needs_selection_card=True,
    )
    request = _request(
        messages=[{"role": "user", "content": "직접 매장에 갈 시간이 없는데 차량을 맡기지 않고 교체할 수 있는 서비스가 있어?"}]
    )

    result = _apply_pickup_service_policy(decision, request)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.SUPPORT
    assert result.intents[0] == "pickup_info"
    assert result.needs_selection_card is False


def test_unverified_pickup_intent_is_removed_without_regex_rerouting() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.SUPPORT,
        intents=["pickup_status"],
        needs_selection_card=False,
    )
    request = _request(messages=[{"role": "user", "content": "내 차 지금 작업 중이야?"}])

    result = _apply_pickup_service_policy(decision, request)

    assert "pickup_status" not in result.intents
    assert result.domain == Domain.SUPPORT


def test_static_faq_router_guard_is_moved_to_support_intent() -> None:
    decision = RouteDecision(
        guard_id=GuardId.DIRECT_HOME_DELIVERY,
        domain=Domain.LEADING,
        intents=[],
        needs_selection_card=True,
    )

    result = _move_static_faq_guard_to_intent(decision)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.SUPPORT
    assert result.extra_domains == []
    assert result.needs_selection_card is False
    assert result.intents == ["direct_home_delivery"]


def test_product_code_request_guard_refuses_internal_identifier() -> None:
    guard = get_guard(GuardId.PRODUCT_CODE_REQUEST)

    assert guard is not None
    assert "내부 식별자" in guard.text
    assert "안내해 드릴 수 없어요" in guard.text
    assert guard.predicted_domains == ["DISCOVERY", "TRANSACTION"]


def test_unsupported_brand_guard_clears_when_brand_is_only_installed_context() -> None:
    decision = RouteDecision(
        guard_id=GuardId.UNSUPPORTED_BRAND,
        domain=Domain.DISCOVERY,
        intents=["tire_recommend"],
        brand_context=BrandContext(installed_brand="Kumho", desired_brand="Hankook"),
        needs_selection_card=False,
    )

    result = _clear_non_target_unsupported_brand_guard(decision)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.DISCOVERY
    assert result.needs_selection_card is True


def test_unsupported_brand_guard_stays_when_unsupported_brand_is_target() -> None:
    decision = RouteDecision(
        guard_id=GuardId.UNSUPPORTED_BRAND,
        domain=Domain.DISCOVERY,
        intents=["tire_recommend"],
        brand_context=BrandContext(unsupported_brand_target="Kumho"),
        needs_selection_card=True,
    )

    result = _clear_non_target_unsupported_brand_guard(decision)

    assert result.guard_id == GuardId.UNSUPPORTED_BRAND


def test_other_brand_purchase_channel_guard_uses_canonical_sales_channel_guidance() -> None:
    guard = get_guard(GuardId.OTHER_BRAND_PURCHASE_CHANNEL)

    assert guard is not None
    assert guard.text == (
        "다른 브랜드의 타이어는 해당 브랜드의 공식 판매 채널 또는 온라인 판매처에서 구매하실 수 있습니다. "
        "판매 가격, 재고, 장착 가능 여부는 판매처마다 다를 수 있으므로 구매를 원하는 판매처에서 확인해 주세요. "
        "한국타이어 제품은 티스테이션닷컴에서 편리하게 구매 및 장착 예약을 이용하실 수 있습니다."
    )
    assert [chip["label"] for chip in guard.chips] == ["한국타이어 상품 보기", "타이어 추천 받기"]
    assert guard.predicted_domains == ["DISCOVERY"]


def test_hankook_alternative_purchase_channel_guard_uses_canonical_guidance() -> None:
    guard = get_guard(GuardId.HANKOOK_ALTERNATIVE_PURCHASE_CHANNEL)

    assert guard is not None
    assert guard.text == (
        "한국타이어는 티스테이션닷컴 외에도 다양한 온라인 및 오프라인 판매처에서 구매하실 수 있습니다. "
        "티스테이션닷컴에서는 다양한 할인 혜택과 장착 예약 서비스를 함께 이용하실 수 있습니다."
    )
    assert [chip["label"] for chip in guard.chips] == ["한국타이어 상품 보기", "진행 중인 혜택"]
    assert guard.predicted_domains == ["DISCOVERY"]


def test_unsupported_brand_guard_clears_when_current_brand_context_is_empty() -> None:
    decision = RouteDecision(
        guard_id=GuardId.UNSUPPORTED_BRAND,
        domain=Domain.DISCOVERY,
        intents=["tire_recommend"],
        brand_context=BrandContext(),
        needs_selection_card=False,
    )

    result = _clear_non_target_unsupported_brand_guard(decision)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.DISCOVERY
    assert result.needs_selection_card is True


def test_supported_alternative_switch_overrides_unsupported_target_from_history() -> None:
    decision = RouteDecision(
        guard_id=GuardId.UNSUPPORTED_BRAND,
        domain=Domain.DISCOVERY,
        intents=["tire_recommend"],
        brand_context=BrandContext(
            unsupported_brand_target="Kumho",
            switch_to_supported_alternative=True,
        ),
        needs_selection_card=False,
    )

    result = _clear_non_target_unsupported_brand_guard(decision)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.DISCOVERY
    assert result.needs_selection_card is True


def test_competitor_characteristic_guidance_clears_unsupported_guard_without_selection_card() -> None:
    decision = RouteDecision(
        guard_id=GuardId.UNSUPPORTED_BRAND,
        domain=Domain.DISCOVERY,
        intents=["competitor_counterpart_guidance"],
        brand_context=BrandContext(
            unsupported_brand_target="Kumho",
            desired_brand="Hankook",
            switch_to_supported_alternative=True,
        ),
        needs_selection_card=True,
    )

    result = _clear_non_target_unsupported_brand_guard(decision)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.DISCOVERY
    assert result.needs_selection_card is False


def test_supported_brand_switch_resets_product_and_guard_state_but_preserves_fitment() -> None:
    slots = ConversationSlots(
        tire_size="245/45R18",
        car_model="Grandeur IG",
        region="Gangnam",
        ord_qty=4,
        tire_model="Unsupported Model",
        goods_no="GOLD",
        shop_id="SHOP1",
        requested_cal_day="20260717",
        last_guard_id="unsupported_brand",
        guard_repeat_count=1,
    )

    result = reset_for_supported_brand_switch(slots)

    assert result.tire_size == "245/45R18"
    assert result.car_model == "Grandeur IG"
    assert result.region == "Gangnam"
    assert result.ord_qty == 4
    assert result.tire_model is None
    assert result.goods_no is None
    assert result.shop_id is None
    assert result.requested_cal_day is None
    assert result.last_guard_id is None
    assert result.guard_repeat_count is None


def test_out_of_scope_guard_does_not_offer_qna_handoff() -> None:
    guard = get_guard(GuardId.OUT_OF_SCOPE)

    assert guard is not None
    assert "답변드리기 어려운 주제" in guard.text
    assert [chip["label"] for chip in guard.chips] == ["타이어 추천 받기", "가까운 매장 찾기", "진행 중인 혜택"]
    assert guard.predicted_domains == ["DISCOVERY", "TRANSACTION"]


def test_router_input_separates_current_turn_from_previous_context() -> None:
    request = _request(
        messages=[
            {"role": "user", "content": "전기차 타이어 추천해줘"},
            {"role": "assistant", "content": "전기차 전용 타이어를 추천해드릴게요."},
            {"role": "user", "content": "보험사에 얘기할 내용을 위에 내가 얘기한 사실에 기반해서 써줘"},
        ]
    )

    router_text = _router_input(request)

    assert "## 현재 사용자 발화" in router_text
    assert "사용자: 보험사에 얘기할 내용을 위에 내가 얘기한 사실에 기반해서 써줘" in router_text
    assert "## 이전 대화 (현재 발화 해석용 보조 맥락)" in router_text
    assert "사용자: 전기차 타이어 추천해줘" in router_text


def test_runflat_mixed_install_policy_overrides_vehicle_type_compatibility() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.SUPPORT,
        intents=["vehicle_type_compatibility"],
        needs_selection_card=True,
        runflat_mixed_install_policy=True,
    )

    result = _apply_runflat_mixed_install_policy(decision)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.SUPPORT
    assert result.extra_domains == []
    assert result.needs_selection_card is False
    assert result.intents[0] == "runflat_mixed_install_policy"


def test_runflat_mixed_install_policy_noop_when_router_did_not_flag_it() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.SUPPORT,
        intents=["vehicle_type_compatibility"],
        needs_selection_card=True,
    )

    result = _apply_runflat_mixed_install_policy(decision)

    assert result.intents == ["vehicle_type_compatibility"]


def test_late_night_store_hours_policy_overrides_time_filtered_store_search() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.TRANSACTION,
        intents=["store_search"],
        needs_selection_card=True,
    )
    request = _request(messages=[{"role": "user", "content": "서울 지역에 저녁 7시 이후 영업하는 매장 있어?"}])

    result = _apply_late_night_store_hours_policy(decision, request)

    assert result.guard_id == GuardId.NONE
    assert result.domain == Domain.SUPPORT
    assert result.extra_domains == []
    assert result.needs_selection_card is False
    assert result.intents[0] == "late_night_store_hours_policy"


def test_late_night_store_hours_policy_also_overrides_after_19_booking_request() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.TRANSACTION,
        intents=["store_schedule"],
        needs_selection_card=False,
    )
    request = _request(messages=[{"role": "user", "content": "서울에서 19시 이후 예약 가능한 매장 찾아줘"}])

    result = _apply_late_night_store_hours_policy(decision, request)

    assert result.domain == Domain.SUPPORT
    assert result.extra_domains == []
    assert result.intents[0] == "late_night_store_hours_policy"
    assert result.needs_selection_card is False


def test_late_night_store_hours_policy_handles_late_install_place_request() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.TRANSACTION,
        intents=["store_schedule"],
        needs_selection_card=False,
    )
    request = _request(messages=[{"role": "user", "content": "밤늦게 장착 가능한 곳 있어?"}])

    result = _apply_late_night_store_hours_policy(decision, request)

    assert result.domain == Domain.SUPPORT
    assert result.intents[0] == "late_night_store_hours_policy"


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


def test_tool_profile_is_required_in_router_schema() -> None:
    # Optional fields are absent from the function-calling schema's `required`
    # list and the mini model skips them — measured ~0% tool_profile emission
    # before it was made required (the Pydantic default masked the omission).
    assert "tool_profile" in (RouteDecision.model_json_schema().get("required") or [])


def test_benefit_context_evidence_is_required_in_router_schema() -> None:
    route_schema = RouteDecision.model_json_schema()
    benefit_schema = route_schema["$defs"]["BenefitContext"]

    assert "benefit_context" in (route_schema.get("required") or [])
    assert set(benefit_schema.get("required") or []) == {
        "owned_coupon_exclusion",
        "unverified_benefit_target",
        "unverified_access_request",
    }


def test_benefit_context_omitted_by_existing_callers_defaults_to_empty() -> None:
    decision = RouteDecision.model_validate({"tool_profile": "full"})

    assert decision.benefit_context == BenefitContext(
        owned_coupon_exclusion=None,
        unverified_benefit_target=None,
        unverified_access_request=None,
    )


def test_tool_profile_omitted_by_model_still_defaults_to_full() -> None:
    # Required in the schema, but parsing must never fail when the model
    # omits it anyway — the before-validator fills "full".
    decision = RouteDecision.model_validate({"domain": "DISCOVERY"})
    assert decision.tool_profile is ToolProfile.FULL
    assert RouteDecision().tool_profile is ToolProfile.FULL


def test_tool_profile_parses_narrow_value() -> None:
    decision = RouteDecision.model_validate({"tool_profile": "transaction_coupon"})
    assert decision.tool_profile is ToolProfile.TRANSACTION_COUPON
