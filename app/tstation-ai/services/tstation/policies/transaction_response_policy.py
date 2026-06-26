"""Deterministic response policy for Transaction reservation/stock flows."""
from __future__ import annotations

from typing import Any

from services.tstation.policies.response_decision import ResponseDecision, ResponseShape, TemplateName


_PRODUCT_RECONFIRM_FORBIDDEN = (
    "ask_product_again",
    "offer_start_over",
)
_NO_ORDER_NULL_FORBIDDEN = (
    "preorder_with_null_required_fields",
    "order_summary_with_null_required_fields",
)
_PURE_INVENTORY_FLOW_FORBIDDEN = (
    "datepick_for_pure_inventory_flow",
    "preorder_for_pure_inventory_flow",
)
_QUICK_ORDER_EXECUTE_FORBIDDEN = (
    "preorder_again_after_user_confirmed",
    "confirm_text_without_quick_order_tool",
    "order_complete_without_quick_order_tool",
    "quick_order_with_null_required_fields",
)


def decide_transaction_response(
    *,
    intent: str,
    user_text: str = "",
    known_slots: dict[str, Any] | None = None,
    tool_result: dict[str, Any] | None = None,
) -> ResponseDecision:
    """Return the response contract for high-risk Transaction TC paths.

    This policy intentionally stays independent from ``chat.py`` and the template
    mapper in phase 1. Tests pin the contract first; integration can then call
    this function without changing the expected behavior.
    """
    slots = known_slots or {}
    text = user_text or ""

    if intent == "stock_store_search":
        return _decide_stock_store_search(text=text, slots=slots)
    if intent == "store_schedule":
        return _decide_store_schedule(text=text, slots=slots)
    if intent == "open_store_search":
        return _decide_open_store_search()
    if intent == "store_service_search":
        return _decide_store_service_search(slots=slots)
    if intent == "store_service_advisory":
        return _decide_store_service_advisory()
    if intent == "store_visit_advisory":
        return _decide_store_visit_advisory()
    if intent == "service_duration_advisory":
        return _decide_service_duration_advisory()
    if intent == "maintenance_addon_with_tire_service":
        return _decide_maintenance_addon_with_tire_service()
    if intent == "store_attribute_inquiry":
        return _decide_store_attribute_inquiry()
    if intent == "store_service_availability":
        return _decide_store_attribute_inquiry()
    if intent == "favorite_store_lookup":
        return _decide_favorite_store_lookup()
    if intent == "reservation_store_info_lookup":
        return _decide_reservation_store_info_lookup()
    if intent == "reservation_status_lookup":
        return _decide_reservation_status_lookup()
    if intent == "order_arrival_status_lookup":
        return _decide_order_arrival_status_lookup()
    if intent == "order_cancel_status_lookup":
        return _decide_order_cancel_status_lookup()
    if intent == "order_cancel_fee_inquiry":
        return _decide_order_cancel_fee_inquiry()
    if intent == "order_cancel_request":
        return _decide_order_cancel_request()
    if intent == "payment_method_change_request":
        return _decide_payment_method_change_request()
    if intent == "payment_account_info_lookup":
        return _decide_payment_account_info_lookup()
    if intent == "maintenance_history_lookup":
        return _decide_maintenance_history_lookup(slots=slots)
    if intent == "maintenance_history_access_policy":
        return _decide_maintenance_history_access_policy()
    if intent == "order_history_reorder":
        return _decide_order_history_reorder()
    if intent == "plain_store_info_lookup":
        return _decide_plain_store_info_lookup()
    if intent == "store_holiday_lookup":
        return _decide_store_holiday_lookup()
    if intent == "price_or_benefit_alert_request":
        return _decide_price_or_benefit_alert_request(slots=slots)
    if intent == "inventory_availability":
        return _decide_inventory_availability(slots=slots, tool_result=tool_result or {})
    if intent == "quick_order_reservation":
        return _decide_quick_order_reservation(slots=slots)
    if intent == "quick_order_execute":
        return _decide_quick_order_execute(slots=slots)

    return _decision(
        response_shape_key="transaction_fallback",
        response_shape=ResponseShape.CLARIFY,
        template=TemplateName.QUICK_REPLY,
        assistant_guidance="확정된 슬롯과 도구 결과 범위 안에서 다음에 필요한 정보만 요청한다.",
    )


def _decide_stock_store_search(*, text: str, slots: dict[str, Any]) -> ResponseDecision:
    has_goods = bool(slots.get("goods_no"))
    has_size = bool(slots.get("tire_size"))
    has_product = bool(
        slots.get("product_name")
        or slots.get("pattern_name")
        or slots.get("tire_model")
        or slots.get("pending_product_name")
        or has_goods
    )
    has_location = bool(slots.get("region") or slots.get("place") or slots.get("lat") or slots.get("lng"))
    has_quantity = bool(slots.get("quantity") or slots.get("ord_qty"))
    stock_check_mode = str(slots.get("stock_check_mode") or "inventory_only")

    required_slots: list[str] = []
    if not has_product:
        required_slots.append("product")
    if has_product and not has_size and not has_goods:
        required_slots.append("tire_size")
    if has_product and not has_quantity:
        required_slots.append("quantity")
    if not has_location and _needs_location_for_nearby_stock(text):
        required_slots.append("location")

    if required_slots:
        return _decision(
            response_shape_key="missing_stock_search_slots",
            response_shape=ResponseShape.CLARIFY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("empty_location_card", "ask_unrelated_reset"),
            assistant_guidance="상품은 확정된 것으로 보고 재확인하지 말고, 재고 조회에 필요한 누락 정보만 짧게 요청한다.",
            metadata={"missing_slots": tuple(required_slots), "stock_check_mode": stock_check_mode},
        )

    if stock_check_mode == "inventory_only":
        return _decision(
            response_shape_key="stock_inventory_lookup",
            response_shape=ResponseShape.LOCATION,
            template=TemplateName.LOCATION,
            forbidden_behaviors=_PURE_INVENTORY_FLOW_FORBIDDEN + ("empty_select_only_response",),
            assistant_guidance=(
                "순수 재고 확인 흐름은 매장 ID를 해소한 뒤 매장 오늘 장착 가능 재고를 먼저 확인한다. "
                "매장 재고가 확인되지 않으면 goods_no 기준 물류 재고와 rsv_install_date를 확인할 수 있다. "
                "datepick/preOrder/주문 확정으로 바로 확장하지 말고, 물류 기준 가능 일정은 텍스트 안내와 확인 CTA까지만 제공한다."
            ),
            metadata={
                "stock_check_mode": "inventory_only",
                "logistics_notice_allowed": True,
                "reservation_ui_allowed": False,
            },
        )

    return _decision(
        response_shape_key="stock_store_candidates",
        response_shape=ResponseShape.LOCATION,
        template=TemplateName.LOCATION,
        forbidden_behaviors=("datepick_before_store_selection", "empty_select_only_response"),
        assistant_guidance="재고와 장착 조건을 만족하는 매장 후보를 location 카드로 먼저 제시한다.",
        metadata={"stock_check_mode": "preview"},
    )


def _decide_price_or_benefit_alert_request(*, slots: dict[str, Any]) -> ResponseDecision:
    return _decision(
        response_shape_key="price_or_benefit_alert_guidance",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=("promise_price_alert_registration", "promise_coupon_issue", "invent_discount"),
        assistant_guidance=(
            "가격이 내려가거나 쿠폰·이벤트가 생겼을 때 자동으로 알려주는 기능은 제공되지 않는다. "
            "알림 등록 완료처럼 말하지 말고, 상품 상세와 쿠폰함에서 가격·혜택을 직접 확인하도록 안내한다."
        ),
        metadata={"alert_scope": "price_or_benefit"},
    )


def _decide_store_schedule(*, text: str, slots: dict[str, Any]) -> ResponseDecision:
    if slots.get("store_exact_match") is False:
        return _decision(
            response_shape_key="unverified_store_schedule_lookup",
            response_shape=ResponseShape.CLARIFY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("datepick_for_unverified_store", "pretend_store_exists"),
            assistant_guidance=(
                "입력 매장명이 정확히 확인되지 않으면 매장 확인을 먼저 진행한다. "
                "다만 generic missing-store 가드로 막지 말고 get_store_list_tool 로 후보를 확인한다."
            ),
        )

    if _asks_noon(text):
        return _decision(
            response_shape_key="time_filtered_schedule",
            response_shape=ResponseShape.DATE_PICK,
            template=TemplateName.DATE_PICK,
            forbidden_behaviors=("show_blocked_noon_slot",),
            assistant_guidance="12시는 예약 불가 슬롯이므로 선택 가능한 시간에서 제외한다.",
        )

    if slots.get("booking_type") == "store_visit" and not slots.get("goods_no"):
        return _decision(
            response_shape_key="store_visit_schedule",
            response_shape=ResponseShape.DATE_PICK,
            template=TemplateName.DATE_PICK,
            forbidden_behaviors=("force_tire_order_flow", "ask_current_time"),
            assistant_guidance="타이어 주문예약이 아닌 방문예약으로 보고 매장 방문 가능 시간을 안내한다.",
        )

    return _decision(
        response_shape_key="order_reservation_schedule",
        response_shape=ResponseShape.DATE_PICK,
        template=TemplateName.DATE_PICK,
        forbidden_behaviors=("store_hours_instead_of_slots",),
        assistant_guidance="상품/수량/매장이 확정된 예약 요청은 영업시간 설명이 아니라 예약 슬롯을 제시한다.",
    )


def _decide_store_visit_advisory() -> ResponseDecision:
    return _decision(
        response_shape_key="store_visit_advisory",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "datepick_for_store_visit_advisory",
            "schedule_tool_for_store_visit_advisory",
            "force_store_schedule_for_visit_advisory",
        ),
        assistant_guidance=(
            "혼잡도, 대기시간, 점심시간 작업 가능 여부, 휴무/영업 여부, 그냥 가도 되는지 같은 방문 시간 상담은 "
            "예약 슬롯 조회가 아니므로 datepick을 제시하지 않는다. 실시간 혼잡도 데이터가 없으면 일반적인 방문 권장 시간과 "
            "매장 직접 확인 CTA를 quickReply로 안내한다."
        ),
    )


def _decide_open_store_search() -> ResponseDecision:
    return _decision(
        response_shape_key="open_store_filter",
        response_shape=ResponseShape.LOCATION,
        template=TemplateName.LOCATION,
        forbidden_behaviors=("unfiltered_store_list_for_open_store_filter", "store_visit_advisory_for_open_store_filter"),
        assistant_guidance=(
            "지역 기반 요일/휴일 영업 매장 검색은 방문 혼잡도 상담이 아니다. "
            "지역 후보 매장을 특정 날짜/요일 영업 여부로 필터링하고, 확인된 매장은 location 카드로 안내한다."
        ),
        metadata={"open_only": True},
    )


def _decide_store_service_search(*, slots: dict[str, Any]) -> ResponseDecision:
    if not slots.get("region"):
        return _decision(
            response_shape_key="missing_store_service_search_region",
            response_shape=ResponseShape.CLARIFY,
            template=TemplateName.QUICK_REPLY,
            required_slots=("region",),
            forbidden_behaviors=("random_store_service_search_without_region", "store_service_advisory_for_search"),
            assistant_guidance="서비스 조건 매장 검색은 지역이 필요하므로 지역만 짧게 요청한다.",
            metadata={"service_name": slots.get("service_name")},
        )
    return _decision(
        response_shape_key="store_service_search",
        response_shape=ResponseShape.LOCATION,
        template=TemplateName.LOCATION,
        forbidden_behaviors=(
            "store_service_advisory_for_search",
            "schedule_tool_for_store_service_search",
            "claim_service_without_matching_svc_code",
        ),
        assistant_guidance=(
            "지역+서비스 조건 매장 검색은 조건에 맞는 매장 location 카드로 안내한다. "
            "svc_codes에 해당 서비스 코드가 확인된 경우에만 가능 표현을 쓴다."
        ),
        metadata={
            "service_name": slots.get("service_name"),
            "service_codes": tuple(slots.get("service_codes") or ()),
        },
    )


def _decide_store_service_advisory() -> ResponseDecision:
    return _decision(
        response_shape_key="store_service_advisory",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "random_store_service_search_without_region",
            "claim_service_without_matching_svc_code",
            "schedule_tool_for_store_service_advisory",
        ),
        assistant_guidance=(
            "지역이나 특정 매장이 없는 서비스 가능 여부 질문은 일반 안내로 답하고, "
            "검색하려면 지역 또는 매장명을 요청한다."
        ),
    )


def _decide_favorite_store_lookup() -> ResponseDecision:
    return _decision(
        response_shape_key="favorite_store_lookup",
        response_shape=ResponseShape.LOCATION,
        template=TemplateName.LOCATION,
        forbidden_behaviors=("ask_location_for_favorite_store", "auto_select_single_store", "fallback_to_generic_store_search"),
        assistant_guidance=(
            "단골매장 조회는 위치를 다시 묻지 말고 get_favorite_stores_tool 결과만 사용한다. "
            "결과가 비면 등록된 단골매장이 없다는 quickReply로 안내하고 일반 매장 검색으로 자동 전환하지 않는다."
        ),
    )


def _decide_reservation_store_info_lookup() -> ResponseDecision:
    return _decision(
        response_shape_key="reservation_store_info_lookup",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "reservation_store_claim_without_reservation_source",
            "use_viewed_store_as_reservation_store",
            "generic_store_search_for_reservation_store",
        ),
        assistant_guidance=(
            "예약한 매장/예약 지점 참조는 최근 조회 매장이 아니라 예약 내역 source로 확인한다. "
            "get_my_reservations_tool 또는 주문/예약 내역 결과가 없으면 예약 매장을 단정하지 말고 예약번호/주문번호 또는 예약 내역 확인을 요청한다."
        ),
    )


def _decide_reservation_status_lookup() -> ResponseDecision:
    return _decision(
        response_shape_key="reservation_status_lookup",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "reservation_status_claim_without_reservation_source",
            "discovery_first_for_owned_reservation_lookup",
            "product_search_for_owned_reservation_lookup",
            "store_schedule_for_owned_reservation_lookup",
        ),
        assistant_guidance=(
            "기존 예약 상태/존재 확인은 현재 턴의 owned-record 조회다. "
            "stale 상품/매장 슬롯으로 상품 검색이나 예약 가능 시간 조회로 돌리지 말고, "
            "get_my_reservations_tool 또는 주문/예약 source를 확인한 뒤 확인된 예약만 안내한다."
        ),
    )


def _decide_order_arrival_status_lookup() -> ResponseDecision:
    return _decision(
        response_shape_key="order_arrival_status_lookup",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "route_to_notification_settings",
            "show_reminding_alarm_cta",
            "datepick_for_arrival_notification",
            "generic_store_search_for_arrival_notification",
        ),
        assistant_guidance=(
            "매장 도착/입고 문자를 받은 뒤 방문 가능 여부를 묻는 경우는 알림 설정이 아니라 주문/예약 상태 확인이다. "
            "주문/예약 source를 확인하고, 예약 시간이 있으면 예약 시간 기준 방문을 권장한다. "
            "예약 시간이 없으면 방문 전 매장 또는 주문내역 확인을 안내한다."
        ),
    )


def _decide_maintenance_history_lookup(*, slots: dict[str, Any]) -> ResponseDecision:
    requested_item = str(slots.get("requested_service_item") or "").strip()
    return _decision(
        response_shape_key="maintenance_history_lookup",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "fallback_to_support_without_history_tool",
            "ask_order_for_maintenance_history",
            "use_order_history_for_maintenance_history",
            "recommend_product_for_maintenance_history",
        ),
        assistant_guidance=(
            "정비/서비스 이력 조회는 주문번호나 상품 슬롯 없이 get_maintenance_history_tool(limit=5)를 호출한다. "
            "사용자가 특정 항목을 언급했으면 tool 결과에서 해당 항목을 우선 필터링하고, 결과 응답에는 정비이력보기 CTA를 포함한다."
        ),
        metadata={"requested_service_item": requested_item} if requested_item else None,
    )


def _decide_order_history_reorder() -> ResponseDecision:
    return _decision(
        response_shape_key="order_history_reorder",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "quick_order_without_current_confirmation",
            "product_search_for_owned_order_reorder",
            "arbitrary_order_selection",
        ),
        assistant_guidance=(
            "이전 주문 기반 재구매는 현재 턴의 owned order history 조회다. "
            "get_orders_of_user_tool 결과에서 매칭된 이전 타이어만 요약하고, 바로 주문 완료/예약으로 진행하지 않는다."
        ),
    )


def _decide_plain_store_info_lookup() -> ResponseDecision:
    return _decision(
        response_shape_key="plain_store_info_lookup",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "datepick_for_plain_store_info",
            "booking_cta_for_plain_store_info",
            "store_detail_without_store_tool",
        ),
        assistant_guidance=(
            "특정 매장의 전화/주소/상세/사진 문의는 매장 정보 조회다. "
            "get_store_list_tool/get_store_detail_tool 결과 범위에서만 안내하고 예약/재고/주문 CTA로 확장하지 않는다."
        ),
    )


def _decide_store_holiday_lookup() -> ResponseDecision:
    return _decision(
        response_shape_key="store_holiday_lookup",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "datepick_for_store_holiday",
            "booking_cta_for_store_holiday",
            "assert_open_without_holiday_source",
        ),
        assistant_guidance=(
            "특정 매장의 휴무/영업일 문의는 예약 가능 시간 조회가 아니라 매장 상세의 휴무 정보 확인이다. "
            "get_store_list_tool/get_store_detail_tool 결과로 확인되는 휴무만 안내하고 운영 여부를 임의 단정하지 않는다."
        ),
    )


def _decide_order_cancel_request() -> ResponseDecision:
    return _decision(
        response_shape_key="order_cancel_request_guidance",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "ask_which_order_to_cancel",
            "ask_order_number_for_cancel_request",
            "select_order_for_cancel_request",
            "promise_cancel_availability_check",
            "promise_cancel_progress",
            "promise_cancel_processing",
        ),
        assistant_guidance=(
            "챗봇이 직접 주문을 취소 처리할 수 없음을 안내한다. 취소 가능 여부와 취소 버튼은 주문 상세 화면에서 "
            "사용자가 직접 확인해야 한다. 주문번호가 명확하면 주문 상세 CTA를 제공하고, 없거나 여러 건이면 주문내역 CTA만 제공한다. "
            "어떤 주문을 취소할지 선택하게 하거나 주문번호를 요구하지 않는다."
        ),
    )


def _decide_order_cancel_fee_inquiry() -> ResponseDecision:
    return _decision(
        response_shape_key="order_cancel_fee_inquiry_summary",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "direct_cancel_unavailable_guidance",
            "normalize_as_cancel_request",
            "arbitrary_past_order_fee_answer",
            "ask_which_order_to_cancel",
            "promise_cancel_processing",
        ),
        assistant_guidance=(
            "취소 실행 요청이 아니라 취소 비용/위약금/수수료 발생 여부 문의다. 특정 주문/예약이 없으면 과거 출고 주문을 "
            "임의 선택해 비용을 단정하지 않는다. 활성 온라인 주문/예약이 정확히 1건이면 해당 상태 기준으로 조건부 안내하고, "
            "온라인 주문 내역이 없거나 매장 방문 예약만 가능한 경우에는 매장 방문 예약은 별도 취소 수수료가 발생하지 않는다고 "
            "안내한 뒤 예약/주문 내역 또는 1:1 문의 CTA를 제공한다. '제가 직접 주문을 취소 처리할 수는 없어요' 같은 "
            "취소 실행 불가 안내로 정규화하지 않는다."
        ),
    )


def _decide_order_cancel_status_lookup() -> ResponseDecision:
    return _decision(
        response_shape_key="order_cancel_status_summary",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "answer_without_order_lookup",
            "direct_cancel_unavailable_guidance",
            "order_cancel_request_normalizer",
            "promise_cancel_progress",
            "promise_cancel_processing",
        ),
        assistant_guidance=(
            "이미 취소됐는지 또는 결제/카드 취소가 승인됐는지 확인하는 상태 조회다. 주문번호가 있으면 "
            "get_order_status_tool(query_no=...)을 우선 호출하고, 없으면 get_orders_of_user_tool로 최근 주문을 확인하거나 "
            "주문내역 CTA를 안내한다. '제가 직접 주문을 취소 처리할 수는 없어요' 같은 취소 실행 불가 안내로 정규화하지 않는다."
        ),
    )


def _decide_payment_method_change_request() -> ResponseDecision:
    return _decision(
        response_shape_key="payment_method_change_request",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "pii_hard_block_for_payment_business_request",
            "promise_payment_method_changed",
            "direct_payment_method_change",
            "pick_arbitrary_order",
        ),
        assistant_guidance=(
            "챗봇이 직접 결제수단을 변경 완료했다고 말하지 않는다. 주문 목록에서 suffix 또는 전체 주문번호로 주문을 확인하고, "
            "주문 상세에서 결제 정보/변경 가능 여부를 확인하도록 안내한다. 필요 시 주문 상세 보기와 1:1 문의 CTA를 제공한다."
        ),
    )


def _decide_payment_account_info_lookup() -> ResponseDecision:
    return _decision(
        response_shape_key="payment_account_info_lookup",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "pii_hard_block_for_payment_business_request",
            "invent_virtual_account",
            "expose_sensitive_payment_secret",
            "pick_arbitrary_order",
        ),
        assistant_guidance=(
            "무통장 입금 기한/가상계좌/결제 정보 확인은 주문 상세 기준으로 안내한다. 주문을 특정할 수 있으면 주문 상세 CTA를 제공하고, "
            "특정할 수 없으면 주문내역 확인 CTA를 제공한다."
        ),
    )


def _decide_maintenance_history_access_policy() -> ResponseDecision:
    return _decision(
        response_shape_key="maintenance_history_access_policy",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "call_maintenance_history_tool_for_access_policy",
            "require_order_for_maintenance_history_access_policy",
            "show_actual_history_rows_for_access_policy",
        ),
        assistant_guidance=(
            "정비/서비스 이력의 조회 가능 여부, 다른 지역/아무 매장에서도 볼 수 있는지, 매장 확인 절차를 묻는 경우는 "
            "사용자의 실제 이력을 조회하지 않는다. 차량번호/예약자 정보로 매장 확인 요청이 가능할 수 있음을 안내하고, "
            "상세 이력 확인 CTA를 제공한다."
        ),
    )


def _decide_service_duration_advisory() -> ResponseDecision:
    return _decision(
        response_shape_key="service_duration_advisory",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=("datepick_for_service_duration_advisory", "require_order_for_general_service_info"),
        assistant_guidance=(
            "이미 예약한 서비스에 현장 부가 서비스를 추가할 때의 일반 소요시간 안내는 주문번호 없이 답변한다. "
            "예약 변경/취소/시간 재조정이 아닌 한 datepick이나 예약 슬롯을 제시하지 않는다."
        ),
    )


def _decide_maintenance_addon_with_tire_service() -> ResponseDecision:
    return _decision(
        response_shape_key="maintenance_addon_with_tire_service",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "fabricate_maintenance_booking_slot",
            "ask_tire_product_for_maintenance_addon",
            "fallback_to_maintenance_dday_faq",
            "generic_required_slot_clarification",
        ),
        assistant_guidance=(
            "타이어 교체와 엔진오일/실내필터/와이퍼 등 경정비 동시 요청은 매장 서비스 가능 여부 안내로 처리한다. "
            "svc_codes 121/122 또는 All My T/경정비 신호가 확인되면 온라인 타이어 주문 시 경정비 함께 주문 가능성을 안내하고, "
            "확인되지 않으면 타이어 장착은 온라인 주문/예약으로 진행하되 경정비는 방문예약 또는 매장 사전 연락으로 확인하도록 안내한다."
        ),
    )


def _decide_store_attribute_inquiry() -> ResponseDecision:
    return _decision(
        response_shape_key="store_attribute_inquiry",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=(
            "datepick_for_store_attribute_inquiry",
            "preorder_for_store_attribute_inquiry",
            "order_complete_for_store_attribute_inquiry",
            "claim_unverified_store_service_available",
            "pick_arbitrary_store",
        ),
        assistant_guidance=(
            "특정 매장의 서비스/장비/운영 조건/주관 품질 가능 여부는 source 없이 단정하지 않는다. "
            "매장명이 있으면 기본 매장정보를 함께 안내해 사용자가 직접 확인하도록 하고, 매장명이 없으면 매장명을 요청한다."
        ),
    )


def _decide_store_service_availability() -> ResponseDecision:
    return _decide_store_attribute_inquiry()


def _decide_inventory_availability(
    *,
    slots: dict[str, Any],
    tool_result: dict[str, Any],
) -> ResponseDecision:
    stock_check_mode = str(
        slots.get("stock_check_mode")
        or ("preview" if slots.get("requested_cal_day") or slots.get("availability_intent") == "today_install" else "inventory_only")
    )
    if stock_check_mode == "inventory_only":
        requested_qty = _int_or_none(slots.get("quantity") or slots.get("ord_qty")) or 1
        available_qty = _available_quantity_or_none(tool_result)
        has_inventory = bool(
            _has_inventory_rows(tool_result, "todayShopArray")
            or _has_inventory_rows(tool_result, "tnaShopArray")
            or (available_qty is not None and available_qty > 0)
        )
        if not has_inventory or (available_qty is not None and available_qty < requested_qty):
            response_shape_key = "logistics_stock_available" if _has_logistics_stock_or_reservation(tool_result) else "stock_unavailable"
            return _decision(
                response_shape_key=response_shape_key,
                response_shape=ResponseShape.NO_RESULT,
                template=TemplateName.QUICK_REPLY,
                forbidden_behaviors=(
                    "say_available_when_stock_zero",
                    "datepick_for_unavailable_stock",
                ) + _PURE_INVENTORY_FLOW_FORBIDDEN,
                assistant_guidance=(
                    "순수 재고 확인 흐름에서는 예약 슬롯이나 주문서로 확장하지 말고, "
                    "매장 오늘 장착 가능 재고가 없으면 불가 사실을 먼저 말한다. "
                    "다만 물류 재고 또는 예약 가능일이 확인되면 datepick/preOrder 없이 물류 기준 가능 일정 안내와 확인 CTA만 제공한다."
                ),
                metadata={"stock_check_mode": "inventory_only"},
            )
        return _decision(
            response_shape_key="stock_available",
            response_shape=ResponseShape.LOCATION,
            template=TemplateName.LOCATION,
            forbidden_behaviors=_PURE_INVENTORY_FLOW_FORBIDDEN,
            assistant_guidance=(
                "순수 재고 확인 흐름에서는 get_store_inventory_tool 결과만 사용해 "
                "매장재고/T바로배송 가능 여부를 안내한다."
            ),
            metadata={"stock_check_mode": "inventory_only"},
        )

    if _is_region_preview_scope(slots) and _has_preview_candidate_rows(tool_result):
        return _decision(
            response_shape_key="stock_store_candidates",
            response_shape=ResponseShape.LOCATION,
            template=TemplateName.LOCATION,
            forbidden_behaviors=("datepick_before_store_selection", "empty_select_only_response"),
            assistant_guidance="지역 단위 조회는 단일 매장을 임의 확정하지 말고 장착 가능 매장 후보를 location 카드로 먼저 제시한다.",
            metadata={"stock_check_mode": "preview"},
        )

    if _has_preview_schedule_slots(tool_result):
        return _decision(
            response_shape_key="reservation_slots",
            response_shape=ResponseShape.DATE_PICK,
            template=TemplateName.DATE_PICK,
            forbidden_behaviors=("hide_available_stock",),
            assistant_guidance="예약 가능한 슬롯이 있으면 재고 없음으로 보지 말고 datepick으로 이어간다.",
            metadata={"stock_check_mode": "preview"},
        )

    requested_qty = _int_or_none(slots.get("quantity") or slots.get("ord_qty")) or 1
    available_qty = _available_quantity(tool_result)
    today_installable = bool(
        _tool_result_value(tool_result, "today_installable")
        or _tool_result_value(tool_result, "today_service_available")
        or _has_inventory_rows(tool_result, "todayShopArray")
    )
    tna_available = bool(
        _tool_result_value(tool_result, "tna_available")
        or _tool_result_value(tool_result, "is_tna_delivery")
        or _has_inventory_rows(tool_result, "tnaShopArray")
    )
    installable_store_available = _has_installable_preview_store(tool_result)

    if available_qty < requested_qty and not today_installable and not tna_available and not installable_store_available:
        return _decision(
            response_shape_key="stock_unavailable",
            response_shape=ResponseShape.NO_RESULT,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("say_available_when_stock_zero", "datepick_for_unavailable_stock", "preorder"),
            assistant_guidance="재고/오늘서비스/T바로배송이 불가하면 가능하다고 안내하지 말고 대체 매장 또는 조건 변경을 제안한다.",
            metadata={"stock_check_mode": "preview"},
        )

    return _decision(
        response_shape_key="stock_available",
        response_shape=ResponseShape.LOCATION,
        template=TemplateName.LOCATION,
        forbidden_behaviors=("hide_available_stock",),
        assistant_guidance="요청 수량을 충족하는 재고 또는 배송 가능 경로를 안내한다.",
        metadata={"stock_check_mode": "preview"},
    )


def _decide_quick_order_reservation(*, slots: dict[str, Any]) -> ResponseDecision:
    missing: list[str] = []
    if not (slots.get("goods_no") or slots.get("tire_size")):
        missing.append("tire_size")
    if not slots.get("quantity") and not slots.get("ord_qty"):
        missing.append("quantity")
    if not (slots.get("shop_id") or slots.get("store_name")):
        missing.append("store")

    if missing:
        return _decision(
            response_shape_key="missing_order_slots",
            response_shape=ResponseShape.CLARIFY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=_NO_ORDER_NULL_FORBIDDEN,
            assistant_guidance="주문 요약을 만들기 전에 누락된 필수 주문 정보를 먼저 수집한다.",
            metadata={"missing_slots": tuple(missing)},
        )

    if _has_selected_booking_datetime(slots):
        return _decision(
            response_shape_key="reservation_confirmation_ready",
            response_shape=ResponseShape.ACTION_CONFIRM,
            template=TemplateName.PRE_ORDER,
            forbidden_behaviors=_NO_ORDER_NULL_FORBIDDEN + ("store_hours_instead_of_slots",),
            assistant_guidance=(
                "예약 날짜와 시간까지 확정된 주문 흐름에서는 datepick를 다시 요구하지 말고 "
                "preOrder 확인 또는 quick_order_tool 단계로 이어간다."
            ),
        )

    return _decision(
        response_shape_key="reservation_slots",
        response_shape=ResponseShape.DATE_PICK,
        template=TemplateName.DATE_PICK,
        forbidden_behaviors=_NO_ORDER_NULL_FORBIDDEN + ("store_hours_instead_of_slots",),
        assistant_guidance="상품/수량/매장이 확정됐으면 예약 가능한 날짜와 시간을 먼저 선택하게 한다.",
        metadata={"next_step": "booking_datetime"},
    )


def _decide_quick_order_execute(*, slots: dict[str, Any]) -> ResponseDecision:
    missing: list[str] = []
    if not slots.get("goods_no"):
        missing.append("product")
    if not slots.get("ord_qty") and not slots.get("quantity"):
        missing.append("quantity")
    if not slots.get("shop_id"):
        missing.append("store")
    if not (slots.get("requested_cal_day") and slots.get("rsv_hour")):
        missing.append("booking_datetime")

    if missing:
        return _decision(
            response_shape_key="missing_order_execution_slots",
            response_shape=ResponseShape.CLARIFY,
            template=TemplateName.QUICK_REPLY,
            required_slots=tuple(missing),
            forbidden_behaviors=_QUICK_ORDER_EXECUTE_FORBIDDEN,
            assistant_guidance="preOrder 확인 이후 주문 실행에 필요한 상품/수량/매장/예약일시가 비면 quick_order_tool을 호출하지 않는다.",
        )

    return _decision(
        response_shape_key="quick_order_execute",
        response_shape=ResponseShape.ACTION_CONFIRM,
        template=TemplateName.ORDER_COMPLETE,
        forbidden_behaviors=_QUICK_ORDER_EXECUTE_FORBIDDEN,
        assistant_guidance="사용자가 preOrder를 확인한 뒤 확정 의사를 밝히면 quick_order_tool로 실제 주문서 생성을 실행하고 orderComplete 또는 실패 안내로 종료한다.",
    )


def _decision(
    *,
    response_shape_key: str,
    response_shape: ResponseShape,
    template: TemplateName,
    required_slots: tuple[str, ...] = (),
    forbidden_behaviors: tuple[str, ...] = (),
    assistant_guidance: str = "",
    metadata: dict[str, Any] | None = None,
) -> ResponseDecision:
    return ResponseDecision(
        response_shape=response_shape,
        template=template,
        required_slots=required_slots,
        forbidden_behaviors=forbidden_behaviors,
        assistant_guidance=assistant_guidance,
        metadata={"response_shape_key": response_shape_key, **(metadata or {})},
    )


def _needs_location_for_nearby_stock(text: str) -> bool:
    return any(token in text for token in ("근처", "주변", "오늘", "당장", "장착"))


def _asks_noon(text: str) -> bool:
    normalized = text.replace(" ", "")
    return "12시" in normalized or "점심시간" in normalized


def _has_selected_booking_datetime(slots: dict[str, Any]) -> bool:
    if slots.get("booking_datetime"):
        return True
    return bool(slots.get("requested_cal_day") and slots.get("rsv_hour"))


def _available_quantity_or_none(tool_result: dict[str, Any]) -> int | None:
    for key in ("available_qty", "stock_qty", "quantity", "qty"):
        value = _int_or_none(_tool_result_value(tool_result, key))
        if value is not None:
            return value
    stores = _tool_result_value(tool_result, "stores")
    if isinstance(stores, list):
        return sum(
            _int_or_none(store.get("available_qty") or store.get("stock_qty")) or 0
            for store in stores
            if isinstance(store, dict)
        )
    return None


def _available_quantity(tool_result: dict[str, Any]) -> int:
    return _available_quantity_or_none(tool_result) or 0


def _has_inventory_rows(tool_result: dict[str, Any], key: str) -> bool:
    rows = _tool_result_value(tool_result, key)
    return isinstance(rows, list) and bool(rows)


def _has_installable_preview_store(tool_result: dict[str, Any]) -> bool:
    for stores in _preview_store_lists(tool_result):
        if any(isinstance(store, dict) and bool(store.get("is_installable")) for store in stores):
            return True
    return False


def _is_region_preview_scope(slots: dict[str, Any]) -> bool:
    return bool((slots.get("region") or slots.get("place")) and not (slots.get("shop_id") or slots.get("shop_name") or slots.get("store_name")))


def _has_preview_candidate_rows(tool_result: dict[str, Any]) -> bool:
    return bool(
        _has_inventory_rows(tool_result, "todayShopArray")
        or _has_inventory_rows(tool_result, "tnaShopArray")
        or any(stores for stores in _preview_store_lists(tool_result))
    )


def _has_logistics_stock_or_reservation(tool_result: dict[str, Any]) -> bool:
    logistics_qty = _int_or_none(_tool_result_value(tool_result, "logistics_qty"))
    if logistics_qty is None:
        logistics_qty = _int_or_none(_tool_result_value(tool_result, "logisticsQty"))
    if logistics_qty is not None and logistics_qty > 0:
        return True
    rsv_sale_yn = str(_tool_result_value(tool_result, "rsv_sale_yn") or _tool_result_value(tool_result, "rsvSaleYn") or "").upper()
    rsv_install_date = str(
        _tool_result_value(tool_result, "rsv_install_date")
        or _tool_result_value(tool_result, "rsvInstallDate")
        or ""
    ).strip()
    return rsv_sale_yn == "Y" or bool(rsv_install_date)


def _has_preview_schedule_slots(tool_result: dict[str, Any]) -> bool:
    for stores in _preview_store_lists(tool_result):
        for store in stores:
            if not isinstance(store, dict):
                continue
            slots = store.get("slots")
            if isinstance(slots, list) and slots:
                return True
    return False


def _tool_result_value(tool_result: dict[str, Any], key: str) -> Any:
    if key in tool_result:
        return tool_result.get(key)
    data = tool_result.get("data")
    if isinstance(data, dict):
        if key in data:
            return data.get(key)
        for nested_key in ("inventory", "schedule", "logistics", "price"):
            nested = data.get(nested_key)
            if isinstance(nested, dict) and key in nested:
                return nested.get(key)
    return None


def _preview_store_lists(tool_result: dict[str, Any]) -> list[list[dict[str, Any]]]:
    lists: list[list[dict[str, Any]]] = []
    data = tool_result.get("data")
    if isinstance(data, dict):
        schedule = data.get("schedule")
        if isinstance(schedule, dict):
            stores = schedule.get("stores")
            if isinstance(stores, list):
                lists.append(stores)
        stores = data.get("stores")
        if isinstance(stores, list):
            lists.append(stores)
    stores = tool_result.get("stores")
    if isinstance(stores, list):
        lists.append(stores)
    return lists


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
