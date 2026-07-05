"""Slot-fill precheck policy for transaction flow resumption."""
from __future__ import annotations

import re
from typing import Any, Mapping

from schemas.tstation.slots import ConversationSlots
from services.tstation.policies.ui_action_policy import (
    _cal_day_from_korean_date_text,
    _reservation_hour_from_text,
)


_SUPPORT_OR_POLICY_ANCHOR_RE = r"보증|워런티|무상|품질|불량|환불|취소|쿠폰|사은품|문의|상담|클레임|고소|소송"


def _current_turn_place_patch(
    *,
    regex_slots: ConversationSlots,
    region_store_input_resolution: Any | None,
) -> dict[str, Any]:
    if region_store_input_resolution is not None and getattr(region_store_input_resolution, "resolved", False):
        return {
            key: value
            for key, value in dict(getattr(region_store_input_resolution, "slots_to_promote", {}) or {}).items()
            if key in {"region", "shop_id", "shop_name"} and value not in (None, "", [], {})
        }
    patch: dict[str, Any] = {}
    if getattr(regex_slots, "region", None) not in (None, "", [], {}):
        patch["region"] = regex_slots.region
    if getattr(regex_slots, "shop_name", None) not in (None, "", [], {}):
        patch["shop_name"] = regex_slots.shop_name
    return patch


def filled_slot_from_slot_patch(slot_patch: Mapping[str, Any]) -> str:
    """Derive filled_slot metadata from the actual slot patch keys."""
    keys = {str(key) for key, value in dict(slot_patch or {}).items() if value not in (None, "", [], {})}
    if {"requested_cal_day", "rsv_hour"} <= keys:
        return "schedule"
    if "shop_id" in keys or "shop_name" in keys:
        return "store"
    if "region" in keys:
        return "region"
    if "ord_qty" in keys:
        return "quantity"
    if "goods_no" in keys or "product_name" in keys or "pending_product_name" in keys or "tire_model" in keys:
        return "product"
    return "none"


def expected_slot_fill_precheck(
    *,
    user_text: str,
    regex_slots: ConversationSlots,
    merged_slots: ConversationSlots,
    router_context: Mapping[str, Any],
    region_store_input_resolution: Any | None = None,
    has_purchase_anchor: bool = False,
) -> dict[str, Any]:
    """Return a safe slot patch for the active transaction flow, if current input fills one."""
    current_flow = str(router_context.get("current_flow") or "none")
    if current_flow not in {"quick_order_reservation", "stock_store_search", "store_schedule"}:
        return {"matched": False, "reason": "no_active_flow"}
    text = user_text or ""

    if re.search(_SUPPORT_OR_POLICY_ANCHOR_RE, text, re.IGNORECASE):
        return {"matched": False, "reason": "support_or_policy_anchor"}

    missing_slots = {
        str(slot or "").strip()
        for slot in (router_context.get("missing_slots") or [])
        if str(slot or "").strip()
    }
    last_requested_slot = str(router_context.get("last_requested_slot") or "none").strip()
    slot_patch: dict[str, Any] = {}
    current_requested_cal_day = (
        str(getattr(regex_slots, "requested_cal_day", None) or "").strip()
        or _cal_day_from_korean_date_text(text)
    )
    current_rsv_hour = (
        str(getattr(regex_slots, "rsv_hour", None) or "").strip()
        or _reservation_hour_from_text(text)
    )
    has_current_schedule_signal = bool(current_requested_cal_day or current_rsv_hour)
    current_turn_place_patch = _current_turn_place_patch(
        regex_slots=regex_slots,
        region_store_input_resolution=region_store_input_resolution,
    )

    if current_flow == "quick_order_reservation" and has_purchase_anchor and not current_turn_place_patch:
        pass
    elif "quantity" in missing_slots and getattr(regex_slots, "ord_qty", None) is not None:
        slot_patch["ord_qty"] = regex_slots.ord_qty
    elif (
        has_current_schedule_signal
        and current_flow in {"quick_order_reservation", "stock_store_search", "store_schedule"}
        and getattr(merged_slots, "requested_cal_day", None)
        and getattr(merged_slots, "rsv_hour", None)
    ):
        slot_patch.update({
            "requested_cal_day": merged_slots.requested_cal_day,
            "rsv_hour": merged_slots.rsv_hour,
        })
    elif (
        region_store_input_resolution is not None
        and getattr(region_store_input_resolution, "resolved", False)
        and (
            last_requested_slot in {"region", "store"}
            or "region" in missing_slots
            or "store" in missing_slots
            or str(router_context.get("flow_step") or "") in {"show_store_candidates", "resolve_store"}
        )
    ):
        slot_patch.update(dict(getattr(region_store_input_resolution, "slots_to_promote", {}) or {}))
    elif (
        str(router_context.get("flow_step") or "") in {"show_store_candidates", "resolve_store"}
        and current_flow in {"quick_order_reservation", "stock_store_search"}
        and getattr(merged_slots, "goods_no", None)
        and getattr(merged_slots, "ord_qty", None)
        and current_turn_place_patch
    ):
        for key in (
            "product_name",
            "tire_model",
            "pending_product_name",
            "goods_no",
            "tire_size",
            "ord_qty",
            "payment_amount",
            "availability_intent",
            "stock_check_mode",
        ):
            value = getattr(merged_slots, key, None)
            if value not in (None, "", [], {}):
                slot_patch[key] = value
        slot_patch.update(current_turn_place_patch)
        if slot_patch.get("product_name") in (None, "", [], {}):
            derived_product_name = slot_patch.get("tire_model") or slot_patch.get("pending_product_name")
            if derived_product_name not in (None, "", [], {}):
                slot_patch["product_name"] = derived_product_name
    elif (
        ("schedule" in missing_slots or last_requested_slot == "schedule")
        and has_current_schedule_signal
        and getattr(merged_slots, "requested_cal_day", None)
        and getattr(merged_slots, "rsv_hour", None)
    ):
        slot_patch.update({
            "requested_cal_day": merged_slots.requested_cal_day,
            "rsv_hour": merged_slots.rsv_hour,
        })

    filled_slot = filled_slot_from_slot_patch(slot_patch)
    if filled_slot == "none":
        return {"matched": False, "reason": "input_does_not_fill_expected_slot"}

    return {
        "matched": True,
        "current_flow": current_flow,
        "filled_slot": filled_slot,
        "slot_patch": {key: value for key, value in slot_patch.items() if value not in (None, "", [], {})},
        "resume_source": f"expected_slot_fill:{filled_slot}",
        "flow_step_before": router_context.get("flow_step"),
        "missing_slots": list(router_context.get("missing_slots") or []),
    }
