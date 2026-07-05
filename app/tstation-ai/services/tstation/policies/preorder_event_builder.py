"""Contract-based preOrder event construction.

This module keeps preOrder eligibility and payload assembly independent from
entry-path details such as schedule UI actions or QC correction paths.
"""

from __future__ import annotations

import datetime
from typing import Any, Mapping

from services.tstation.policies.discovery_intent_policy import normalize_tire_size
from services.tstation.policies.flow_state import flow_state_values_from_slot_values

_WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")


def can_emit_preorder(contract: Any | None, slots: Mapping[str, Any] | Any | None) -> bool:
    """Return whether the current contract state is ready for a preOrder card."""

    slot_values = _slot_values(slots)
    if str(getattr(contract, "domain", "") or "").lower() != "transaction":
        return False

    response_decision = getattr(contract, "response_decision", None) or {}
    response_metadata = response_decision.get("metadata") if isinstance(response_decision, Mapping) else {}
    response_shape_key = str((response_metadata or {}).get("response_shape_key") or "")
    response_template = str(response_decision.get("template") or "") if isinstance(response_decision, Mapping) else ""
    flow_step = str(getattr(contract, "flow_step", "") or (response_metadata or {}).get("flow_step") or "")
    action_mode = str(getattr(contract, "action_mode", "") or "")
    intent = str(getattr(contract, "intent", "") or "")

    contract_ready = (
        response_shape_key == "reservation_confirmation_ready"
        and flow_step == "build_preorder"
        and response_template in {"", "preOrder"}
        and (action_mode == "purchase_continuation" or intent.startswith("quick_order_reservation"))
    )
    return bool(
        contract_ready
        and _has_ready_preorder_slots(slot_values)
        and _product_name(slot_values)
        and _payment_amount(slot_values)[0] is not None
    )


def build_preorder_event(
    contract: Any | None,
    slots: Mapping[str, Any] | Any | None,
) -> dict[str, Any] | None:
    """Build a deterministic preOrder event from normalized contract slots."""

    if not can_emit_preorder(contract, slots):
        return None
    slot_values = _slot_values(slots)
    goods_no = str(slot_values.get("goods_no") or "").strip()
    tire_size = normalize_tire_size(str(slot_values.get("tire_size") or "")) or ""
    shop_id = str(slot_values.get("shop_id") or "").strip()
    shop_name = str(slot_values.get("shop_name") or slot_values.get("store_name") or "").strip()
    requested_cal_day = str(slot_values.get("requested_cal_day") or "").strip()
    rsv_hour = str(slot_values.get("rsv_hour") or "").strip()

    try:
        ord_qty = int(slot_values.get("ord_qty") or slot_values.get("quantity") or 0)
    except (TypeError, ValueError):
        return None
    if ord_qty <= 0:
        return None

    product_name = _product_name(slot_values)
    product_label = f"{product_name} {tire_size}".strip() if product_name else tire_size
    booking_datetime = _booking_datetime(requested_cal_day, rsv_hour)
    payment_amount, price_basis, price_source_tool, payment_amount_source = _payment_amount(slot_values)
    car_info = _car_info(slot_values)

    event = {
        "type": "data",
        "template": "preOrder",
        "source_domain": "transaction",
        "assistant_response_source": "code_reservation_confirmation_ready",
        "data": {
            "assistantResponse": "주문 정보를 확인해 주세요.",
            "orderInfo": {
                "carInfo": car_info,
                "product": product_label,
                "quantity": ord_qty,
                "storeName": shop_name,
                "bookingDateTime": booking_datetime,
                "paymentAmount": payment_amount,
            },
            "isReadyToOrder": True,
            "isReadyToAddToCart": False,
            "metadata": {
                "goodsNo": goods_no,
                "goodsId": goods_no,
                "shopId": shop_id,
                "shopName": shop_name,
                "storeName": shop_name,
                "ordQty": ord_qty,
                "quantity": ord_qty,
                "requestedCalDay": requested_cal_day,
                "rsvHour": rsv_hour,
                "bookingDateTime": booking_datetime,
                "paymentAmount": payment_amount,
                "productName": product_name or None,
                "tireSize": tire_size,
                "priceBasis": price_basis,
                "priceSourceTool": price_source_tool,
                "paymentAmountSource": payment_amount_source,
                "paymentAmountMissingReason": None if payment_amount is not None else "missing_payment_amount",
                "carNo": _str_or_none(slot_values.get("car_no")),
                "carLncCd": _str_or_none(slot_values.get("car_lnc_cd")),
                "missingPreorderContext": _missing_preorder_context(product_name, tire_size, payment_amount),
            },
        },
        "nextAction": {"type": "stop", "domain": None},
    }
    return event


def _slot_values(slots: Mapping[str, Any] | Any | None) -> dict[str, Any]:
    if slots is None:
        return {}
    if hasattr(slots, "model_dump"):
        return _with_context_vehicle_values(dict(slots.model_dump(exclude_none=True)))
    if isinstance(slots, Mapping):
        return _with_context_vehicle_values(dict(slots))
    return {
        key: value
        for key in (
            "goods_no",
            "product_name",
            "pending_product_name",
            "tire_model",
            "tire_size",
            "ord_qty",
            "quantity",
            "shop_id",
            "shop_name",
            "store_name",
            "requested_cal_day",
            "rsv_hour",
            "payment_amount",
            "price_basis",
            "price_source_tool",
            "payment_amount_source",
            "cheapest_final_prc",
            "final_unit_price",
            "final_prc",
            "final_price",
            "finalPrice",
            "extra_fvr_sale_prc",
            "sale_prc",
            "price",
            "car_no",
            "car_nm",
            "car_name",
            "car_model",
            "car_lnc_cd",
            "availability_context",
        )
        if (value := getattr(slots, key, None)) not in (None, "", [], {})
    }
def _with_context_vehicle_values(values: dict[str, Any]) -> dict[str, Any]:
    if values.get("car_no") and (values.get("car_model") or values.get("car_nm") or values.get("car_name")):
        return values
    availability_context = values.get("availability_context") if isinstance(values.get("availability_context"), Mapping) else {}
    context_candidates: list[Mapping[str, Any]] = [
        flow_state_values_from_slot_values(values, source="preorder_vehicle_context")
    ]
    for key in ("dormant_purchase_context", "dormant_transaction_context"):
        context = availability_context.get(key)
        if isinstance(context, Mapping):
            context_candidates.append(context)
    active_flow_context = availability_context.get("active_flow_context")
    if isinstance(active_flow_context, Mapping):
        context_candidates.append(active_flow_context)
        vehicle_context = active_flow_context.get("vehicle")
        if isinstance(vehicle_context, Mapping):
            context_candidates.append(vehicle_context)

    for context in context_candidates:
        for key in ("car_no", "car_lnc_cd", "car_model", "car_nm", "car_name"):
            value = context.get(key)
            if values.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
                values[key] = value
    return values


def _has_ready_preorder_slots(slots: Mapping[str, Any]) -> bool:
    try:
        has_quantity = int(slots.get("ord_qty") or slots.get("quantity") or 0) > 0
    except (TypeError, ValueError):
        has_quantity = bool(slots.get("ord_qty") or slots.get("quantity"))
    return bool(
        slots.get("goods_no")
        and normalize_tire_size(str(slots.get("tire_size") or ""))
        and slots.get("shop_id")
        and (slots.get("shop_name") or slots.get("store_name"))
        and slots.get("requested_cal_day")
        and slots.get("rsv_hour")
        and has_quantity
    )


def _product_name(slots: Mapping[str, Any]) -> str:
    for context in _product_context_candidates(slots):
        for key in ("goods_nm", "goodsNm", "tire_model", "pending_product_name", "product_name"):
            product_name = str(context.get(key) or "").strip()
            if product_name:
                return product_name
    return ""


def _payment_amount(slots: Mapping[str, Any]) -> tuple[int | None, str | None, str | None, str | None]:
    quantity = _quantity(slots)
    for context in _context_candidates(slots):
        direct_amount = _int_or_none(context.get("payment_amount") or context.get("paymentAmount"))
        if direct_amount is not None:
            payment_amount_source = _str_or_none(
                context.get("payment_amount_source") or context.get("paymentAmountSource")
            )
            price_basis = _str_or_none(context.get("price_basis") or context.get("priceBasis"))
            price_source_tool = _str_or_none(context.get("price_source_tool") or context.get("priceSourceTool"))
            if _is_unit_payment_amount_source(
                payment_amount_source=payment_amount_source,
                price_source_tool=price_source_tool,
            ) and quantity > 0:
                return (
                    direct_amount * quantity,
                    price_basis,
                    price_source_tool,
                    payment_amount_source or "selected_product_candidate_unit_price",
                )
            return (
                direct_amount,
                price_basis,
                price_source_tool,
                payment_amount_source,
            )
        unit_price, price_basis = _unit_price_and_basis(context)
        if unit_price is not None and quantity > 0:
            return (
                unit_price * quantity,
                price_basis,
                _str_or_none(context.get("price_source_tool") or context.get("priceSourceTool")) or "context_price",
                _str_or_none(context.get("payment_amount_source") or context.get("paymentAmountSource"))
                or "context_unit_price",
            )
    return None, None, None, None

def _is_unit_payment_amount_source(*, payment_amount_source: str | None, price_source_tool: str | None) -> bool:
    if payment_amount_source in {
        "selected_product_candidate_unit_price",
        "context_unit_price",
        "pending_order_context.unit_price",
        "active_flow_context.payment.unit_price",
    }:
        return True
    return price_source_tool in {"selected_product_candidate", "product_template", "quickreply_metadata"}


def _quantity(slots: Mapping[str, Any]) -> int:
    try:
        return int(slots.get("ord_qty") or slots.get("quantity") or 0)
    except (TypeError, ValueError):
        return 0


def _unit_price_and_basis(values: Mapping[str, Any]) -> tuple[int | None, str | None]:
    for key in (
        "cheapest_final_prc",
        "final_unit_price",
        "final_prc",
        "final_price",
        "finalPrice",
        "extra_fvr_sale_prc",
        "sale_prc",
        "price",
    ):
        price = _int_or_none(values.get(key))
        if price is not None:
            return price, key
    return None, None


def _context_candidates(slots: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    contexts: list[Mapping[str, Any]] = [slots]
    availability_context = slots.get("availability_context") if isinstance(slots.get("availability_context"), Mapping) else {}
    _append_availability_contexts(contexts, availability_context)
    return contexts


def _product_context_candidates(slots: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    contexts: list[Mapping[str, Any]] = []
    availability_context = slots.get("availability_context") if isinstance(slots.get("availability_context"), Mapping) else {}
    flow_context = flow_state_values_from_slot_values(
        {"availability_context": availability_context},
        source="preorder_product_context_candidates",
    )
    _append_product_context(contexts, flow_context)
    for key in ("pending_order_context", "dormant_purchase_context", "dormant_stock_context", "dormant_transaction_context"):
        value = availability_context.get(key)
        if isinstance(value, Mapping):
            _append_product_context(contexts, value)
    active_flow = availability_context.get("active_flow_context")
    if isinstance(active_flow, Mapping):
        product_context = active_flow.get("product")
        if isinstance(product_context, Mapping):
            _append_product_context(contexts, product_context)
        _append_product_context(contexts, active_flow)
    _append_product_context(contexts, slots)
    return contexts


def _append_product_context(contexts: list[Mapping[str, Any]], context: Mapping[str, Any]) -> None:
    if context and context not in contexts:
        contexts.append(context)


def _append_availability_contexts(contexts: list[Mapping[str, Any]], availability_context: Mapping[str, Any]) -> None:
    flow_context = flow_state_values_from_slot_values(
        {"availability_context": availability_context},
        source="preorder_context_candidates",
    )
    if flow_context:
        contexts.append(flow_context)
    for key in ("dormant_purchase_context", "dormant_stock_context", "dormant_transaction_context"):
        value = availability_context.get(key)
        if isinstance(value, Mapping):
            contexts.append(value)
    active_flow = availability_context.get("active_flow_context")
    if isinstance(active_flow, Mapping):
        contexts.append(active_flow)
        for key in ("product", "payment", "intent", "store", "quantity"):
            value = active_flow.get(key)
            if isinstance(value, Mapping):
                contexts.append(value)
    for nested_key in ("dormant_store_finder_context", "dormant_purchase_finder_context"):
        nested = availability_context.get(nested_key)
        if not isinstance(nested, Mapping):
            continue
        nested_availability = nested.get("availability_context")
        if isinstance(nested_availability, Mapping):
            _append_availability_contexts(contexts, nested_availability)


def _booking_datetime(requested_cal_day: str, rsv_hour: str) -> str | None:
    try:
        order_day = datetime.datetime.strptime(requested_cal_day, "%Y%m%d")
        return (
            f"{order_day.year}년 {order_day.month}월 {order_day.day}일 "
            f"({_WEEKDAY_KO[order_day.weekday()]}) {int(rsv_hour):02d}:00"
        )
    except (TypeError, ValueError):
        return None


def _car_info(slots: Mapping[str, Any]) -> str | None:
    car_no = str(slots.get("car_no") or "").strip()
    car_name = str(slots.get("car_nm") or slots.get("car_name") or slots.get("car_model") or "").strip()
    if car_name and car_no:
        return f"{car_name} ({car_no})"
    return car_name or car_no or None


def _int_or_none(value: Any) -> int | None:
    if value in (None, "", []):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _str_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _missing_preorder_context(product_name: str, tire_size: str, payment_amount: int | None) -> list[str]:
    missing: list[str] = []
    if not product_name:
        missing.append("product_name")
    if not tire_size:
        missing.append("tire_size")
    if payment_amount is None:
        missing.append("payment_amount")
    return missing
