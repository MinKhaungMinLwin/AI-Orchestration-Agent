"""Controller for transaction slot-fill turns.

This module coordinates slot-fill evidence with flow-state recalculation so
`chat.py` does not decide transaction flow transitions directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from schemas.tstation.slots import ConversationSlots
from services.tstation.policies.flow_controller import resolve_purchase_order_flow
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
