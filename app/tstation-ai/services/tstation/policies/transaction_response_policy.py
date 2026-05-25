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
    if intent == "inventory_availability":
        return _decide_inventory_availability(slots=slots, tool_result=tool_result or {})
    if intent == "quick_order_reservation":
        return _decide_quick_order_reservation(slots=slots)

    return _decision(
        response_shape_key="transaction_fallback",
        response_shape=ResponseShape.CLARIFY,
        template=TemplateName.QUICK_REPLY,
        assistant_guidance="확정된 슬롯과 도구 결과 범위 안에서 다음에 필요한 정보만 요청한다.",
    )


def _decide_stock_store_search(*, text: str, slots: dict[str, Any]) -> ResponseDecision:
    has_goods = bool(slots.get("goods_no"))
    has_size = bool(slots.get("tire_size"))
    has_product = bool(slots.get("product_name") or slots.get("pattern_name") or has_goods)
    has_location = bool(slots.get("region") or slots.get("place") or slots.get("lat") or slots.get("lng"))
    has_quantity = bool(slots.get("quantity") or slots.get("ord_qty"))

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
            required_slots=tuple(required_slots),
            forbidden_behaviors=("empty_location_card", "ask_unrelated_reset"),
            assistant_guidance="상품은 확정된 것으로 보고 재확인하지 말고, 재고 조회에 필요한 누락 정보만 짧게 요청한다.",
        )

    return _decision(
        response_shape_key="stock_store_candidates",
        response_shape=ResponseShape.LOCATION,
        template=TemplateName.LOCATION,
        forbidden_behaviors=("datepick_before_store_selection", "empty_select_only_response"),
        assistant_guidance="재고와 장착 조건을 만족하는 매장 후보를 location 카드로 먼저 제시한다.",
    )


def _decide_store_schedule(*, text: str, slots: dict[str, Any]) -> ResponseDecision:
    if slots.get("store_exact_match") is False:
        return _decision(
            response_shape_key="invalid_store_confirmation",
            response_shape=ResponseShape.CLARIFY,
            template=TemplateName.QUICK_REPLY,
            required_slots=("store",),
            forbidden_behaviors=("datepick_for_unverified_store", "pretend_store_exists"),
            assistant_guidance="입력 매장명이 정확히 확인되지 않으면 예약 슬롯을 보여주지 말고 매장 확인부터 진행한다.",
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


def _decide_inventory_availability(
    *,
    slots: dict[str, Any],
    tool_result: dict[str, Any],
) -> ResponseDecision:
    requested_qty = _int_or_none(slots.get("quantity") or slots.get("ord_qty")) or 1
    available_qty = _available_quantity(tool_result)
    today_installable = bool(
        tool_result.get("today_installable")
        or tool_result.get("today_service_available")
        or _has_inventory_rows(tool_result, "todayShopArray")
    )
    tna_available = bool(
        tool_result.get("tna_available")
        or tool_result.get("is_tna_delivery")
        or _has_inventory_rows(tool_result, "tnaShopArray")
    )

    if available_qty < requested_qty and not today_installable and not tna_available:
        return _decision(
            response_shape_key="stock_unavailable",
            response_shape=ResponseShape.NO_RESULT,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("say_available_when_stock_zero", "datepick_for_unavailable_stock", "preorder"),
            assistant_guidance="재고/오늘서비스/T바로배송이 불가하면 가능하다고 안내하지 말고 대체 매장 또는 조건 변경을 제안한다.",
        )

    return _decision(
        response_shape_key="stock_available",
        response_shape=ResponseShape.LOCATION,
        template=TemplateName.LOCATION,
        forbidden_behaviors=("hide_available_stock",),
        assistant_guidance="요청 수량을 충족하는 재고 또는 배송 가능 경로를 안내한다.",
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
            required_slots=tuple(missing),
            forbidden_behaviors=_NO_ORDER_NULL_FORBIDDEN,
            assistant_guidance="주문 요약을 만들기 전에 누락된 필수 주문 정보를 먼저 수집한다.",
        )

    return _decision(
        response_shape_key="reservation_slots",
        response_shape=ResponseShape.DATE_PICK,
        template=TemplateName.DATE_PICK,
        required_slots=("booking_datetime",),
        forbidden_behaviors=_NO_ORDER_NULL_FORBIDDEN + ("store_hours_instead_of_slots",),
        assistant_guidance="상품/수량/매장이 확정됐으면 예약 가능한 날짜와 시간을 먼저 선택하게 한다.",
    )


def _decision(
    *,
    response_shape_key: str,
    response_shape: ResponseShape,
    template: TemplateName,
    required_slots: tuple[str, ...] = (),
    forbidden_behaviors: tuple[str, ...] = (),
    assistant_guidance: str = "",
) -> ResponseDecision:
    return ResponseDecision(
        response_shape=response_shape,
        template=template,
        required_slots=required_slots,
        forbidden_behaviors=forbidden_behaviors,
        assistant_guidance=assistant_guidance,
        metadata={"response_shape_key": response_shape_key},
    )


def _needs_location_for_nearby_stock(text: str) -> bool:
    return any(token in text for token in ("근처", "주변", "오늘", "당장", "장착"))


def _asks_noon(text: str) -> bool:
    normalized = text.replace(" ", "")
    return "12시" in normalized or "점심시간" in normalized


def _available_quantity(tool_result: dict[str, Any]) -> int:
    for key in ("available_qty", "stock_qty", "quantity", "qty"):
        value = _int_or_none(tool_result.get(key))
        if value is not None:
            return value
    stores = tool_result.get("stores")
    if isinstance(stores, list):
        return sum(
            _int_or_none(store.get("available_qty") or store.get("stock_qty")) or 0
            for store in stores
            if isinstance(store, dict)
        )
    return 0


def _has_inventory_rows(tool_result: dict[str, Any], key: str) -> bool:
    rows = tool_result.get(key)
    return isinstance(rows, list) and bool(rows)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
