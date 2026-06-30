"""Controller for transaction slot-fill turns.

This module coordinates slot-fill evidence with flow-state recalculation so
`chat.py` does not decide transaction flow transitions directly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from schemas.tstation.slots import ConversationSlots
from services.tstation.policies.flow_controller import resolve_purchase_order_flow
from services.tstation.policies.resolved_context import canonical_context_from_template_boundary
from services.tstation.policies.slot_fill_policy import expected_slot_fill_precheck


@dataclass(frozen=True)
class SlotFillDecision:
    slots: ConversationSlots
    matched: bool = False
    slot_patch: Mapping[str, Any] = field(default_factory=dict)
    filled_slot: str = "none"
    precheck: Mapping[str, Any] = field(default_factory=dict)
    flow_state_reconciliation: Mapping[str, Any] = field(default_factory=dict)
    routing_override: Mapping[str, Any] = field(default_factory=dict)
    trace_metadata: Mapping[str, Any] = field(default_factory=dict)


def build_router_slot_fill_context(
    *,
    slots: ConversationSlots | None,
    user_text: str = "",
    latest_product_tmpl: Mapping[str, Any] | None,
    latest_location_tmpl: Mapping[str, Any] | None,
    latest_datepick_tmpl: Mapping[str, Any] | None,
    has_purchase_anchor: bool = False,
) -> dict[str, Any]:
    """Build router slot-fill context from current flow state and recent templates."""
    current_flow = _router_slot_fill_current_flow(
        slots,
        user_text=user_text,
        has_purchase_anchor=has_purchase_anchor,
    )
    known_slots = _router_slot_fill_known_slots(slots)
    flow_step = _router_slot_fill_flow_step(current_flow, known_slots)
    if current_flow == "quick_order_reservation":
        flow_state = resolve_purchase_order_flow(intent="quick_order_reservation", known_slots=known_slots)
        missing_slots = [
            _normalize_router_missing_slot(slot)
            for slot in (flow_state.missing_slots if flow_state is not None else ())
        ]
    else:
        missing_slots = _router_slot_fill_missing_slots(current_flow, known_slots)

    last_requested_slot = str(getattr(slots, "pending_required_slot", None) or "").strip()
    if last_requested_slot == "booking_datetime":
        last_requested_slot = "schedule"
    if not last_requested_slot and missing_slots:
        last_requested_slot = missing_slots[0]

    last_candidates: list[dict[str, Any]] = []
    last_candidates.extend(_router_slot_fill_product_candidates(latest_product_tmpl))
    last_candidates.extend(_router_slot_fill_store_candidates(latest_location_tmpl))
    last_candidates.extend(_router_slot_fill_schedule_candidates(latest_datepick_tmpl))
    return {
        "current_flow": current_flow,
        "flow_step": flow_step,
        "known_slots": known_slots,
        "missing_slots": missing_slots,
        "last_requested_slot": last_requested_slot or "none",
        "last_candidates": [row for row in last_candidates if row.get("label")],
    }


def resolve_pre_router_slot_fill(
    *,
    user_text: str,
    regex_slots: ConversationSlots,
    merged_slots: ConversationSlots,
    router_context: Mapping[str, Any],
    region_store_input_resolution: Any | None = None,
    has_purchase_anchor: bool = False,
) -> SlotFillDecision:
    """Apply slot-fill evidence and reconcile the next flow from merged state."""
    precheck = expected_slot_fill_precheck(
        user_text=user_text,
        regex_slots=regex_slots,
        merged_slots=merged_slots,
        router_context=router_context,
        region_store_input_resolution=region_store_input_resolution,
        has_purchase_anchor=has_purchase_anchor,
    )
    if not precheck.get("matched"):
        return SlotFillDecision(
            slots=merged_slots,
            precheck=precheck,
            trace_metadata={"expected_slot_fill_precheck": precheck},
        )

    slot_patch = {
        key: value
        for key, value in dict(precheck.get("slot_patch") or {}).items()
        if value not in (None, "", [], {})
    }
    resolved_slots = (
        merged_slots.apply_runtime_values(slot_patch, source="expected_slot_fill_precheck")
        if slot_patch
        else merged_slots
    )
    flow_state_reconciliation = _flow_state_reconciliation(
        user_text=user_text,
        merged_slots=resolved_slots,
        slot_patch=slot_patch,
        precheck=precheck,
    )
    reconciliation_slot_patch = dict(flow_state_reconciliation.get("slot_patch") or {})
    if reconciliation_slot_patch:
        resolved_slots = resolved_slots.apply_runtime_values(
            reconciliation_slot_patch,
            source="flow_state_after_slot_patch",
        )
    routing_override = _routing_override(
        router_context=router_context,
        flow_state_reconciliation=flow_state_reconciliation,
    )

    trace_metadata: dict[str, Any] = {
        "expected_slot_fill_precheck": precheck,
        "slot_patch": slot_patch,
        "filled_slot": str(precheck.get("filled_slot") or "none"),
    }
    if flow_state_reconciliation:
        trace_metadata["flow_state_reconciliation"] = flow_state_reconciliation
    if routing_override:
        trace_metadata["routing_override"] = routing_override

    return SlotFillDecision(
        slots=resolved_slots,
        matched=True,
        slot_patch=slot_patch,
        filled_slot=str(precheck.get("filled_slot") or "none"),
        precheck=precheck,
        flow_state_reconciliation=flow_state_reconciliation,
        routing_override=routing_override,
        trace_metadata=trace_metadata,
    )


def _routing_override(
    *,
    router_context: Mapping[str, Any],
    flow_state_reconciliation: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the executable flow override owned by the slot-fill controller."""
    if flow_state_reconciliation:
        intent = str(flow_state_reconciliation.get("intent") or "").strip()
        if intent in {"quick_order_reservation", "stock_store_search", "store_schedule"}:
            return {
                "intent": intent,
                "source": str(flow_state_reconciliation.get("source") or "flow_state_reconciliation"),
            }

    intent = str(router_context.get("current_flow") or "").strip()
    if intent in {"quick_order_reservation", "stock_store_search", "store_schedule"}:
        return {"intent": intent, "source": "router_slot_fill_context"}
    return {}


def _router_slot_fill_current_flow(
    slots: ConversationSlots | None,
    *,
    user_text: str = "",
    has_purchase_anchor: bool = False,
) -> str:
    if slots is None:
        return "none"
    pending_intent = str(getattr(slots, "pending_intent", "") or "").strip()
    goal_type = str(getattr(slots, "goal_type", "") or "").strip()
    if pending_intent == "order" or goal_type == "place_order":
        return "quick_order_reservation"
    if pending_intent == "stock" or goal_type == "store_with_stock":
        return "stock_store_search"
    if pending_intent == "reservation" or goal_type == "store_schedule":
        return "store_schedule"

    has_product_anchor = bool(
        getattr(slots, "goods_no", None)
        or (
            getattr(slots, "tire_size", None)
            and (getattr(slots, "tire_model", None) or getattr(slots, "pending_product_name", None))
        )
    )
    if has_product_anchor and has_purchase_anchor:
        return "quick_order_reservation"
    if (
        has_product_anchor
        and re.search(r"재고|오늘\s*장착|당일\s*장착|장착\s*가능|가능\s*매장", user_text or "", re.IGNORECASE)
    ):
        return "stock_store_search"

    availability_context = getattr(slots, "availability_context", None)
    if isinstance(availability_context, Mapping):
        for key in ("pending_order_context", "dormant_purchase_context"):
            context = availability_context.get(key)
            if not isinstance(context, Mapping):
                continue
            if context.get("pending_intent") == "order" or context.get("goal_type") == "place_order":
                return "quick_order_reservation"
            if context.get("pending_intent") == "stock" or context.get("goal_type") == "store_with_stock":
                return "stock_store_search"
        for key in ("dormant_stock_context", "dormant_transaction_context"):
            context = availability_context.get(key)
            if isinstance(context, Mapping) and (
                context.get("pending_intent") == "stock" or context.get("goal_type") == "store_with_stock"
            ):
                return "stock_store_search"
    return "none"


def _router_slot_fill_known_slots(slots: ConversationSlots | None) -> dict[str, Any]:
    if slots is None:
        return {}
    values = {
        "product_name": getattr(slots, "tire_model", None) or getattr(slots, "pending_product_name", None),
        "goods_no": getattr(slots, "goods_no", None),
        "tire_size": getattr(slots, "tire_size", None),
        "ord_qty": getattr(slots, "ord_qty", None),
        "payment_amount": getattr(slots, "payment_amount", None),
        "region": getattr(slots, "region", None),
        "shop_id": getattr(slots, "shop_id", None),
        "shop_name": getattr(slots, "shop_name", None),
        "requested_cal_day": getattr(slots, "requested_cal_day", None),
        "rsv_hour": getattr(slots, "rsv_hour", None),
    }
    availability_context = getattr(slots, "availability_context", None)
    if isinstance(availability_context, Mapping):
        for context_key in (
            "pending_order_context",
            "dormant_purchase_context",
            "dormant_stock_context",
            "dormant_transaction_context",
        ):
            context = availability_context.get(context_key)
            if not isinstance(context, Mapping):
                continue
            for key in (
                "product_name",
                "goods_no",
                "tire_size",
                "ord_qty",
                "payment_amount",
                "region",
                "shop_id",
                "shop_name",
                "requested_cal_day",
                "rsv_hour",
                "pending_intent",
                "goal_type",
            ):
                if values.get(key) in (None, "", [], {}) and context.get(key) not in (None, "", [], {}):
                    values[key] = context.get(key)
    return {key: value for key, value in values.items() if value not in (None, "", [], {})}


def _router_slot_fill_flow_step(current_flow: str, known_slots: Mapping[str, Any]) -> str:
    if current_flow == "quick_order_reservation":
        state = resolve_purchase_order_flow(intent="quick_order_reservation", known_slots=known_slots)
        return state.flow_step if state is not None else "none"
    if current_flow == "stock_store_search":
        missing = _router_slot_fill_missing_slots(current_flow, known_slots)
        if missing:
            return f"ask_{missing[0]}"
        if known_slots.get("region") or known_slots.get("shop_id") or known_slots.get("shop_name"):
            return "show_store_candidates"
        return "stock_check"
    if current_flow == "store_schedule":
        missing = _router_slot_fill_missing_slots(current_flow, known_slots)
        if missing:
            return f"ask_{missing[0]}"
        return "show_schedule"
    return "none"


def _normalize_router_missing_slot(slot: str) -> str:
    return "schedule" if slot == "booking_datetime" else slot


def _router_slot_fill_missing_slots(current_flow: str, known_slots: Mapping[str, Any]) -> list[str]:
    if current_flow == "none":
        return []
    missing: list[str] = []
    if current_flow == "store_schedule":
        if not (known_slots.get("shop_id") or known_slots.get("shop_name")):
            missing.append("store")
        elif not (known_slots.get("requested_cal_day") and known_slots.get("rsv_hour")):
            missing.append("schedule")
        return missing
    if not known_slots.get("goods_no") and not known_slots.get("product_name"):
        missing.append("product")
    elif known_slots.get("product_name") and not known_slots.get("goods_no"):
        missing.append("product")
    if current_flow == "quick_order_reservation":
        if known_slots.get("goods_no") and not known_slots.get("ord_qty"):
            missing.append("quantity")
        if known_slots.get("goods_no") and known_slots.get("ord_qty") and not (
            known_slots.get("region") or known_slots.get("shop_id") or known_slots.get("shop_name")
        ):
            missing.append("store")
        if known_slots.get("shop_id") and not (
            known_slots.get("requested_cal_day") and known_slots.get("rsv_hour")
        ):
            missing.append("schedule")
    elif current_flow == "stock_store_search":
        if known_slots.get("goods_no") and not known_slots.get("ord_qty"):
            missing.append("quantity")
        if known_slots.get("goods_no") and known_slots.get("ord_qty") and not (
            known_slots.get("region") or known_slots.get("shop_id") or known_slots.get("shop_name")
        ):
            missing.append("region")
    return missing


def _router_slot_fill_product_candidates(template_data: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(template_data, Mapping):
        return []
    data = template_data.get("data") if isinstance(template_data.get("data"), Mapping) else template_data
    products = data.get("products") if isinstance(data, Mapping) else None
    metadata = data.get("metadata") if isinstance(data, Mapping) else None
    if not isinstance(products, list):
        return []
    rows: list[dict[str, Any]] = []
    metadata_list = metadata if isinstance(metadata, list) else []
    for idx, product in enumerate(products[:5]):
        if not isinstance(product, Mapping):
            continue
        meta = metadata_list[idx] if idx < len(metadata_list) and isinstance(metadata_list[idx], Mapping) else {}
        canonical = canonical_context_from_template_boundary({**dict(product), **dict(meta)})
        label_parts = [
            str(canonical.get("product_name") or product.get("titleProductName") or product.get("title") or ""),
            str(canonical.get("tire_size") or product.get("titleTires") or ""),
        ]
        price = product.get("price") or product.get("finalPrice") or meta.get("price")
        if price not in (None, "", 0):
            try:
                label_parts.append(f"{int(str(price).replace(',', '')):,}원")
            except (TypeError, ValueError):
                label_parts.append(str(price))
        label = " ".join(part.strip() for part in label_parts if part and str(part).strip())
        rows.append({
            "type": "product",
            "label": label,
            "stable_id_summary": str(canonical.get("goods_no") or meta.get("entity_id") or "")[:24],
        })
    return rows


def _router_slot_fill_store_candidates(template_data: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(template_data, Mapping):
        return []
    data = template_data.get("data") if isinstance(template_data.get("data"), Mapping) else template_data
    stores = data.get("stores") if isinstance(data, Mapping) else None
    metadata = data.get("metadata") if isinstance(data, Mapping) else None
    if not isinstance(stores, list):
        return []
    metadata_list = metadata if isinstance(metadata, list) else []
    rows: list[dict[str, Any]] = []
    for idx, store in enumerate(stores[:5]):
        if not isinstance(store, Mapping):
            continue
        meta = metadata_list[idx] if idx < len(metadata_list) and isinstance(metadata_list[idx], Mapping) else {}
        canonical = canonical_context_from_template_boundary({**dict(store), **dict(meta)})
        label = str(
            canonical.get("shop_name")
            or store.get("nameAddress")
            or store.get("name")
            or store.get("title")
            or ""
        ).strip()
        rows.append({
            "type": "store",
            "label": label,
            "stable_id_summary": str(canonical.get("shop_id") or "")[:24],
        })
    return rows


def _router_slot_fill_schedule_candidates(template_data: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(template_data, Mapping):
        return []
    data = template_data.get("data") if isinstance(template_data.get("data"), Mapping) else template_data
    quick_replies = data.get("quickReplies") if isinstance(data, Mapping) else None
    if not isinstance(quick_replies, list):
        return []
    rows: list[dict[str, Any]] = []
    for chip in quick_replies[:8]:
        if not isinstance(chip, Mapping):
            continue
        label = str(chip.get("label") or chip.get("text") or chip.get("title") or "").strip()
        if label:
            rows.append({"type": "schedule", "label": label, "stable_id_summary": ""})
    return rows


def _flow_state_reconciliation(
    *,
    user_text: str,
    merged_slots: ConversationSlots,
    slot_patch: Mapping[str, Any],
    precheck: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute transaction continuation from merged flow state after a slot patch."""
    filled_slot = str(precheck.get("filled_slot") or "none")
    if filled_slot not in {"product", "quantity", "region", "store", "schedule"}:
        return {}

    availability_context = (
        merged_slots.availability_context
        if isinstance(getattr(merged_slots, "availability_context", None), Mapping)
        else {}
    )
    parent_purchase_context: Mapping[str, Any] = {}
    for key in ("pending_order_context", "dormant_purchase_context"):
        context = availability_context.get(key) if isinstance(availability_context, Mapping) else None
        if not isinstance(context, Mapping):
            continue
        if context.get("pending_intent") in {"order", "reservation", "cart"} or context.get("goal_type") in {
            "place_order",
            "add_to_cart",
        }:
            parent_purchase_context = context
            break

    top_level_purchase_context = bool(
        getattr(merged_slots, "pending_intent", None) in {"order", "reservation", "cart"}
        or getattr(merged_slots, "goal_type", None) in {"place_order", "add_to_cart"}
    )
    if not parent_purchase_context and not top_level_purchase_context:
        return {}

    purchase_slots: dict[str, Any] = {}
    if isinstance(parent_purchase_context, Mapping):
        purchase_slots.update({
            key: value
            for key, value in dict(parent_purchase_context).items()
            if value not in (None, "", [], {})
        })
    for key in (
        "goods_no",
        "tire_size",
        "ord_qty",
        "quantity",
        "shop_id",
        "shop_name",
        "store_name",
        "region",
        "payment_amount",
        "price_basis",
        "price_source_tool",
        "requested_cal_day",
        "rsv_hour",
    ):
        value = getattr(merged_slots, key, None)
        if value not in (None, "", [], {}):
            purchase_slots[key] = value
    product_name = (
        getattr(merged_slots, "tire_model", None)
        or getattr(merged_slots, "product_name", None)
        or getattr(merged_slots, "pending_product_name", None)
        or purchase_slots.get("product_name")
    )
    if product_name not in (None, "", [], {}):
        purchase_slots["product_name"] = product_name
    for key, value in dict(slot_patch or {}).items():
        if value not in (None, "", [], {}) and key not in {"pending_intent", "goal_type"}:
            purchase_slots[key] = value

    purchase_slots["pending_intent"] = "cart" if purchase_slots.get("pending_intent") == "cart" else "order"
    purchase_slots["goal_type"] = "add_to_cart" if purchase_slots.get("goal_type") == "add_to_cart" else "place_order"

    flow_state = resolve_purchase_order_flow(intent="quick_order_reservation", known_slots=purchase_slots)
    if flow_state is None:
        return {}
    if filled_slot == "schedule" and flow_state.flow_step != "build_preorder":
        return {}

    return {
        "intent": "quick_order_reservation",
        "sub_intent": "reservation",
        "flow_step": flow_state.flow_step,
        "template": flow_state.template.value,
        "response_shape_key": flow_state.response_shape_key,
        "required_slots": list(flow_state.required_slots),
        "missing_slots": list(flow_state.missing_slots),
        "preferred_tool": flow_state.preferred_tool,
        "allowed_tools": list(flow_state.allowed_tools),
        "slot_patch": {
            "pending_intent": purchase_slots["pending_intent"],
            "goal_type": purchase_slots["goal_type"],
        },
        "source": "flow_state_after_slot_patch",
        "filled_slot": filled_slot,
        "user_text": user_text,
    }
