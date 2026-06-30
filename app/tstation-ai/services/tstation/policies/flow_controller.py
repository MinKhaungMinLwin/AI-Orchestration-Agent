"""Shared purchase/order flow-step resolution for transaction policy layers."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Mapping

from services.tstation.common.cta_urls import CTAUrls
from services.tstation.policies.discovery_intent_policy import normalize_tire_size
from services.tstation.policies.response_decision import TemplateName


current_purchase_flow_state: ContextVar[dict[str, Any] | None] = ContextVar("current_purchase_flow_state", default=None)


@dataclass(frozen=True)
class FlowState:
    flow_id: str
    flow_step: str
    required_slots: tuple[str, ...] = ()
    missing_slots: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    preferred_tool: str | None = None
    template: TemplateName = TemplateName.QUICK_REPLY
    response_shape_key: str = "transaction_fallback"
    action_mode: str = "purchase_continuation"
    slot_patch: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "flow_id": self.flow_id,
            "flow_step": self.flow_step,
            "required_slots": list(self.required_slots),
            "missing_slots": list(self.missing_slots),
            "allowed_tools": list(self.allowed_tools),
            "forbidden_tools": list(self.forbidden_tools),
            "preferred_tool": self.preferred_tool,
            "template": self.template.value,
            "response_shape_key": self.response_shape_key,
            "action_mode": self.action_mode,
            "slot_patch": dict(self.slot_patch),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class FlowTransition:
    """Read-only current/parent flow snapshot for the next FlowController migration."""

    current_flow_state: Mapping[str, Any] = field(default_factory=dict)
    parent_flow_state: Mapping[str, Any] = field(default_factory=dict)
    flow_transition: Mapping[str, Any] = field(default_factory=dict)
    contract_seed: Mapping[str, Any] = field(default_factory=dict)
    context_evidence: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_flow_state": dict(self.current_flow_state),
            "parent_flow_state": dict(self.parent_flow_state),
            "flow_transition": dict(self.flow_transition),
            "contract_seed": dict(self.contract_seed),
            "context_evidence": dict(self.context_evidence),
            "metadata": dict(self.metadata),
        }


_PURCHASE_FLOW_ID = "purchase_order"
_CART_FLOW_ID = "cart_add"
_PURCHASE_FORBIDDEN_TOOLS = (
    "get_final_price_tool",
    "get_logistics_inventory_tool",
    "get_store_inventory_tool",
    "transaction_store_preview_tool",
    "get_store_schedule_tool",
    "get_multi_store_schedule_tool",
    "quick_order_tool",
)
_CART_FORBIDDEN_TOOLS = (
    "get_final_price_tool",
    "get_logistics_inventory_tool",
    "get_store_inventory_tool",
    "transaction_store_preview_tool",
    "get_store_schedule_tool",
    "get_multi_store_schedule_tool",
    "quick_order_tool",
)
_INVALID_REGION_LABELS = frozenset({
    "구매하기",
    "구매",
    "주문하기",
    "주문",
    "진행",
    "진행하기",
    "선택",
    "확인",
    "네",
    "예",
    "ㅇㅇ",
})
_STORE_SEARCH_FLOW_INTENTS = frozenset({
    "store_search",
    "open_store_search",
    "store_recommendation_by_vehicle_experience",
})
_SERVICE_MAINTENANCE_FLOW_INTENTS = frozenset({
    "maintenance_addon_with_tire_service",
    "service_duration_advisory",
    "store_attribute_inquiry",
    "store_service_advisory",
    "store_service_availability",
    "store_service_search",
    "unsupported_or_unmapped_store_service_policy",
})
_RESERVATION_MANAGEMENT_FLOW_INTENTS = frozenset({
    "reservation_store_info_lookup",
    "reservation_status_lookup",
    "reservation_change_request",
    "order_cancel_request",
    "order_cancel_status_lookup",
    "owned_order_cancel_fee_inquiry",
    "general_cancel_fee_policy",
    "reservation_window_policy",
    "delivery_delay_reservation_schedule_policy",
})
_RESERVATION_POLICY_ONLY_FLOW_INTENTS = frozenset({
    "general_cancel_fee_policy",
    "reservation_window_policy",
    "delivery_delay_reservation_schedule_policy",
})
_DISCOVERY_FLOW_INTENTS = frozenset({
    "product_search",
    "product_recommendation",
    "general_recommendation",
    "condition_recommendation",
    "similar_price_recommendation",
    "vehicle_based_recommendation_refinement",
    "vehicle_based_tire_recommendation",
    "vehicle_resolved_recommendation",
    "best_seller_search",
    "vehicle_best_seller_search",
    "resolve_or_describe_product",
})
_DISCOVERY_EXECUTION_PLAN_TOKENS = frozenset({
    "product_search",
    "product_recommendation",
    "general_recommendation",
    "condition_recommendation",
    "similar_price_recommendation",
    "vehicle_based_recommendation_refinement",
    "vehicle_based_tire_recommendation",
    "vehicle_resolved_recommendation",
    "best_seller_search",
    "get_best_selling_tires_for_vehicle",
    "get_best_selling_product_for_vehicle",
    "get_best_selling_products_for_vehicle",
    "get_best_selling_products_for_vehicle_timeframe",
    "get_products_recommendations_tool",
    "search_product_tool",
})
_SUPPORT_FLOW_INTENTS = frozenset({
    "support_faq",
    "coupon_usage_policy",
    "coupon_registration_policy",
    "coupon_stacking_policy",
    "signup_first_purchase_benefit_policy",
    "signup_coupon_guidance",
    "partner_member_coupon_policy",
    "general_cancel_fee_policy",
    "general_card_cancel_timing_policy",
    "reservation_policy_guidance",
    "reservation_window_policy",
    "installation_work_policy",
    "external_tire_install_policy",
    "promotion_gift_policy",
    "tire_condition_photo_policy",
    "tire_manufacture_date_policy",
    "tire_quality_warranty_policy",
    "assurance_service_policy",
    "maintenance_history_access_policy",
    "order_document_guidance",
    "payment_error_troubleshooting",
    "shipping_fee_policy",
    "online_store_price_policy",
    "regional_price_policy",
    "legal_action_guidance_denied",
    "human_escalation",
    "tstation_service_complaint",
    "policy_notice_or_escalation",
})
_SUPPORT_EXECUTION_PLAN_TOKENS = frozenset({
    "support_faq",
    "search_faq_hybrid_tool",
    "search_faq_rag_tool",
    "get_faq_tool",
    *_SUPPORT_FLOW_INTENTS,
})


def _normalized_region_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _is_invalid_region_text(value: Any) -> bool:
    normalized = _normalized_region_text(value)
    if not normalized:
        return False
    return normalized in _INVALID_REGION_LABELS


def location_source_type(known_slots: Mapping[str, Any] | None) -> str:
    slots = dict(known_slots or {})
    shop_id = str(slots.get("shop_id") or "").strip()
    store_name = str(slots.get("store_name") or slots.get("shop_name") or "").strip()
    place_query = str(slots.get("place_query") or slots.get("place") or "").strip()
    region = _normalized_region_text(slots.get("region"))
    user_xpos = slots.get("user_xpos") if slots.get("user_xpos") not in ("", None) else slots.get("xpos")
    user_ypos = slots.get("user_ypos") if slots.get("user_ypos") not in ("", None) else slots.get("ypos")

    if shop_id or store_name:
        return "store"
    if place_query:
        return "place"
    if user_xpos not in ("", None) and user_ypos not in ("", None):
        return "browser_location"
    if region and not _is_invalid_region_text(region):
        return "region"
    return "none"


def has_location_source(known_slots: Mapping[str, Any] | None) -> bool:
    return location_source_type(known_slots) != "none"


def _non_empty_mapping(values: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(values, Mapping):
        return {}
    return {key: value for key, value in dict(values).items() if value not in (None, "", [], {})}


def _mapping_value(values: Mapping[str, Any] | None, key: str) -> dict[str, Any]:
    value = values.get(key) if isinstance(values, Mapping) else None
    return dict(value) if isinstance(value, Mapping) else {}


def _availability_context_from_slots(slots: Any | Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(slots, Mapping):
        value = slots.get("availability_context")
    else:
        value = getattr(slots, "availability_context", None)
    return dict(value) if isinstance(value, Mapping) else {}


def _parent_flow_context(availability_context: Mapping[str, Any]) -> dict[str, Any]:
    for key in (
        "pending_order_context",
        "dormant_transaction_context",
        "dormant_purchase_context",
        "dormant_stock_context",
    ):
        context = _mapping_value(availability_context, key)
        if context:
            context.setdefault("context_key", key)
            return context
    return {}


def _compact_slot_snapshot(slots: Any | Mapping[str, Any] | None) -> dict[str, Any]:
    fields = (
        "goods_no",
        "product_name",
        "tire_model",
        "pending_product_name",
        "tire_size",
        "ord_qty",
        "shop_id",
        "shop_name",
        "store_name",
        "region",
        "place_query",
        "store_search_condition",
        "requested_vehicle_experience",
        "service_action_boundary",
        "service_name",
        "service_type",
        "reservation_management_action",
        "owned_record_target",
        "recommendation_scenario",
        "scenario",
        "rcmd_type",
        "season_nm",
        "brand_cd",
        "support_topic",
        "faq_topic",
        "policy_topic",
        "pending_intent",
        "goal_type",
        "requested_cal_day",
        "rsv_hour",
    )
    snapshot: dict[str, Any] = {}
    for field_name in fields:
        value = slots.get(field_name) if isinstance(slots, Mapping) else getattr(slots, field_name, None)
        if value not in (None, "", [], {}):
            snapshot[field_name] = value
    return snapshot


def _ui_action_snapshot(ui_action: Any | Mapping[str, Any] | None) -> dict[str, Any]:
    if ui_action is None:
        return {}
    snapshot: dict[str, Any] = {}
    for key in (
        "action_type",
        "cta_action",
        "selection_source",
        "expected_contract_intent",
        "entity_type",
        "entity_id",
        "entity_label",
    ):
        value = ui_action.get(key) if isinstance(ui_action, Mapping) else getattr(ui_action, key, None)
        if value not in (None, "", [], {}):
            snapshot[key] = value
    if snapshot.get("action_type") and "cta_action" not in snapshot:
        snapshot["cta_action"] = snapshot["action_type"]
    slots = _ui_action_slot_patch(ui_action)
    if slots:
        snapshot["slot_patch"] = slots
    return snapshot


def _ui_action_slot_patch(ui_action: Any | Mapping[str, Any] | None) -> dict[str, Any]:
    if ui_action is None:
        return {}
    raw_slots = None
    if isinstance(ui_action, Mapping):
        raw_slots = ui_action.get("slot_patch")
        if not isinstance(raw_slots, Mapping):
            raw_slots = ui_action.get("slots")
    else:
        raw_slots = getattr(ui_action, "slot_patch", None) or getattr(ui_action, "slots", None)
    return _non_empty_mapping(raw_slots) if isinstance(raw_slots, Mapping) else {}


def _selected_product_from_ui_action(ui_action_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if str(ui_action_snapshot.get("action_type") or "").strip() != "select_product":
        return {}
    slot_patch = ui_action_snapshot.get("slot_patch") if isinstance(ui_action_snapshot.get("slot_patch"), Mapping) else {}
    return {
        key: value
        for key, value in {
            "goods_no": ui_action_snapshot.get("entity_id") or slot_patch.get("goods_no"),
            "product_name": ui_action_snapshot.get("entity_label")
            or slot_patch.get("product_name")
            or slot_patch.get("tire_model"),
            "tire_size": slot_patch.get("tire_size"),
            "selection_source": ui_action_snapshot.get("selection_source"),
        }.items()
        if value not in (None, "", [], {})
    }


def _selected_quantity_from_ui_action(ui_action_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if str(ui_action_snapshot.get("action_type") or "").strip() != "select_quantity":
        return {}
    slot_patch = ui_action_snapshot.get("slot_patch") if isinstance(ui_action_snapshot.get("slot_patch"), Mapping) else {}
    quantity = slot_patch.get("ord_qty") or slot_patch.get("quantity")
    try:
        ord_qty = int(quantity)
    except (TypeError, ValueError):
        return {}
    if ord_qty <= 0:
        return {}
    return {
        "ord_qty": ord_qty,
        "selection_source": ui_action_snapshot.get("selection_source") or "ui_action",
    }


def _selected_quantity_from_slots(
    *,
    extracted_snapshot: Mapping[str, Any],
    existing_snapshot: Mapping[str, Any],
    active_flow: Mapping[str, Any],
    parent_flow_state: Mapping[str, Any],
    router_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    quantity = extracted_snapshot.get("ord_qty") or extracted_snapshot.get("quantity")
    try:
        ord_qty = int(quantity)
    except (TypeError, ValueError):
        return {}
    if ord_qty <= 0:
        return {}
    has_flow_context = bool(active_flow or parent_flow_state)
    has_transaction_slots = bool(existing_snapshot.get("goods_no") or existing_snapshot.get("tire_size"))
    router_domain = str(router_evidence.get("domain") or "").strip().lower()
    execution_plan = " ".join(str(item) for item in router_evidence.get("execution_plan") or ())
    router_intent = str(router_evidence.get("intent") or "").strip()
    has_transaction_router = router_domain == "transaction" or "transaction:" in execution_plan
    has_resume_anchor = router_intent in {
        "quick_order_reservation",
        "stock_store_search",
        "store_inventory_check",
        "fill_quantity_slot",
    }
    if not ((has_flow_context or has_transaction_slots) and (has_transaction_router or has_resume_anchor)):
        return {}
    return {"ord_qty": ord_qty, "selection_source": "current_user_text"}


def _selected_store_from_slots(
    *,
    extracted_snapshot: Mapping[str, Any],
    existing_snapshot: Mapping[str, Any],
    active_flow: Mapping[str, Any],
    router_evidence: Mapping[str, Any],
    resume_source: str,
) -> dict[str, Any]:
    resume = str(resume_source or "").strip()
    router_filled_slot = str(router_evidence.get("filled_slot") or "").strip()
    if "store" not in resume and router_filled_slot != "store":
        return {}
    shop_id = existing_snapshot.get("shop_id") or extracted_snapshot.get("shop_id")
    shop_name = existing_snapshot.get("shop_name") or extracted_snapshot.get("shop_name")
    if shop_id in (None, "", [], {}) and shop_name in (None, "", [], {}):
        return {}
    selected: dict[str, Any] = {
        key: value
        for key, value in {
            "shop_id": shop_id,
            "shop_name": shop_name,
            "region": existing_snapshot.get("region") or extracted_snapshot.get("region"),
            "selection_source": resume or "slot_fill:store",
        }.items()
        if value not in (None, "", [], {})
    }
    candidates = active_flow.get("last_candidates") if isinstance(active_flow.get("last_candidates"), list) else []
    selected_shop_id = str(selected.get("shop_id") or "").strip()
    selected_shop_name = str(selected.get("shop_name") or "").strip()
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        candidate_shop_id = str(candidate.get("shop_id") or "").strip()
        candidate_shop_name = str(candidate.get("shop_name") or candidate.get("label") or "").strip()
        if (
            selected_shop_id
            and candidate_shop_id == selected_shop_id
            or selected_shop_name
            and candidate_shop_name
            and selected_shop_name in candidate_shop_name
        ):
            for key in (
                "goods_no",
                "product_name",
                "tire_model",
                "pending_product_name",
                "tire_size",
                "ord_qty",
                "source_tool",
                "schedule_mode",
                "schedule_tier",
                "inventory_mode",
                "stock_check_mode",
                "pending_intent",
                "goal_type",
            ):
                if selected.get(key) in (None, "", [], {}) and candidate.get(key) not in (None, "", [], {}):
                    selected[key] = candidate[key]
            break
    return selected


def _selected_product_flow_type(
    *,
    current_flow_state: Mapping[str, Any],
    parent_flow_state: Mapping[str, Any],
    router_evidence: Mapping[str, Any],
    selected_product: Mapping[str, Any],
) -> str:
    slot_pending_intent = str(selected_product.get("pending_intent") or "").strip()
    slot_goal_type = str(selected_product.get("goal_type") or "").strip()
    if slot_pending_intent == "stock" or slot_goal_type == "store_with_stock":
        return "stock"
    if slot_pending_intent in {"order", "cart"} or slot_goal_type in {"place_order", "add_to_cart"}:
        return "purchase"
    parent_flow_type = str(parent_flow_state.get("flow_type") or "").strip()
    if parent_flow_type in {"purchase", "stock", "booking"}:
        return parent_flow_type
    current_flow_type = str(current_flow_state.get("flow_type") or "").strip()
    if current_flow_type in {"purchase", "recommendation", "stock", "booking"}:
        return current_flow_type
    router_intent = str(router_evidence.get("intent") or "").strip()
    execution_plan = " ".join(str(item or "") for item in (router_evidence.get("execution_plan") or ()))
    if (
        router_intent == "stock_store_search"
        or "stock_store" in execution_plan
        or "store_stock" in execution_plan
        or "store_inventory" in execution_plan
        or "store_schedule_check" in execution_plan
    ):
        return "stock"
    router_domain = str(router_evidence.get("domain") or "").strip().lower()
    if router_domain == "transaction":
        return "purchase"
    return "recommendation"


def _quantity_flow_type(
    *,
    current_flow_state: Mapping[str, Any],
    parent_flow_state: Mapping[str, Any],
    router_evidence: Mapping[str, Any],
    existing_snapshot: Mapping[str, Any],
) -> str:
    current_flow_type = str(current_flow_state.get("flow_type") or "").strip()
    if current_flow_type in {"purchase", "stock", "booking"}:
        return current_flow_type
    parent_flow_type = str(parent_flow_state.get("flow_type") or "").strip()
    if parent_flow_type in {"purchase", "stock", "booking"}:
        return parent_flow_type
    pending_intent = str(existing_snapshot.get("pending_intent") or "").strip()
    goal_type = str(existing_snapshot.get("goal_type") or "").strip()
    if pending_intent == "stock" or goal_type == "store_with_stock":
        return "stock"
    if pending_intent in {"order", "cart"} or goal_type in {"place_order", "add_to_cart"}:
        return "purchase"
    router_intent = str(router_evidence.get("intent") or "").strip()
    execution_plan = " ".join(str(item) for item in router_evidence.get("execution_plan") or ())
    if (
        "stock" in router_intent
        or "stock_store" in execution_plan
        or "store_stock" in execution_plan
        or "store_inventory" in execution_plan
    ):
        return "stock"
    return "purchase"


def _selected_store_flow_type(
    *,
    active_flow: Mapping[str, Any],
    parent_flow_state: Mapping[str, Any],
    router_evidence: Mapping[str, Any],
    existing_snapshot: Mapping[str, Any],
    selected_store: Mapping[str, Any],
) -> str:
    for values in (selected_store, existing_snapshot):
        pending_intent = str(values.get("pending_intent") or "").strip()
        goal_type = str(values.get("goal_type") or "").strip()
        if pending_intent == "stock" or goal_type == "store_with_stock":
            return "stock"
    active_flow_type = str(active_flow.get("flow_type") or "").strip()
    if active_flow_type == "stock":
        return "stock"
    if str(active_flow.get("target_action") or "").strip() == "get_store_inventory_tool":
        return "stock"
    router_intent = str(router_evidence.get("intent") or "").strip()
    execution_plan = " ".join(str(item or "") for item in (router_evidence.get("execution_plan") or ()))
    if "stock" in router_intent or "stock_store" in execution_plan or "store_inventory" in execution_plan:
        return "stock"
    parent_flow_type = str(parent_flow_state.get("flow_type") or "").strip()
    if parent_flow_type == "stock":
        return "stock"
    if parent_flow_type in {"purchase", "booking"}:
        return parent_flow_type
    return active_flow_type if active_flow_type in {"purchase", "booking", "store_schedule"} else "purchase"


def _selected_product_flow_context(
    *,
    current_flow_state: Mapping[str, Any],
    parent_flow_state: Mapping[str, Any],
    router_evidence: Mapping[str, Any],
    selected_product: Mapping[str, Any],
    ui_action_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    if not selected_product:
        return {}
    slot_patch = ui_action_snapshot.get("slot_patch") if isinstance(ui_action_snapshot.get("slot_patch"), Mapping) else {}
    flow_type = _selected_product_flow_type(
        current_flow_state=current_flow_state,
        parent_flow_state=parent_flow_state,
        router_evidence=router_evidence,
        selected_product={**dict(slot_patch), **dict(selected_product)},
    )
    product_name = selected_product.get("product_name") or slot_patch.get("product_name") or slot_patch.get("tire_model")
    product = {
        key: value
        for key, value in {
            "goods_no": selected_product.get("goods_no") or slot_patch.get("goods_no"),
            "product_name": product_name,
            "tire_model": product_name,
            "pending_product_name": product_name,
            "tire_size": selected_product.get("tire_size") or slot_patch.get("tire_size"),
            "ord_qty": slot_patch.get("ord_qty"),
        }.items()
        if value not in (None, "", [], {})
    }
    intent = {
        key: value
        for key, value in {
            "pending_intent": slot_patch.get("pending_intent"),
            "goal_type": slot_patch.get("goal_type"),
            "stock_check_mode": slot_patch.get("stock_check_mode"),
            "availability_intent": slot_patch.get("availability_intent"),
        }.items()
        if value not in (None, "", [], {})
    }
    payment = {
        key: value
        for key, value in {
            "payment_amount": slot_patch.get("payment_amount"),
            "price_basis": slot_patch.get("price_basis"),
            "price_source_tool": slot_patch.get("price_source_tool"),
            "sale_prc": slot_patch.get("sale_prc"),
            "extra_fvr_sale_prc": slot_patch.get("extra_fvr_sale_prc"),
            "cheapest_final_prc": slot_patch.get("cheapest_final_prc"),
            "final_unit_price": slot_patch.get("final_unit_price"),
            "final_prc": slot_patch.get("final_prc"),
            "final_price": slot_patch.get("final_price"),
            "finalPrice": slot_patch.get("finalPrice"),
            "price": slot_patch.get("price"),
            "wage_prc": slot_patch.get("wage_prc"),
        }.items()
        if value not in (None, "", [], {})
    }
    return {
        key: value
        for key, value in {
            "flow_type": flow_type,
            "status": "active",
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "flow_step": "product_selected",
            "product": product,
            "payment": payment,
            "intent": intent,
            "source": "flow_controller:select_product",
        }.items()
        if value not in (None, "", [], {})
    }


def _selected_quantity_flow_context(
    *,
    active_flow: Mapping[str, Any],
    current_flow_state: Mapping[str, Any],
    parent_flow_state: Mapping[str, Any],
    router_evidence: Mapping[str, Any],
    existing_snapshot: Mapping[str, Any],
    selected_quantity: Mapping[str, Any],
) -> dict[str, Any]:
    if not selected_quantity:
        return {}
    ord_qty = selected_quantity.get("ord_qty")
    if ord_qty in (None, "", 0, "0"):
        return {}
    flow_context = dict(active_flow) if isinstance(active_flow, Mapping) else {}
    flow_type = _quantity_flow_type(
        current_flow_state=current_flow_state,
        parent_flow_state=parent_flow_state,
        router_evidence=router_evidence,
        existing_snapshot=existing_snapshot,
    )
    product = dict(flow_context.get("product")) if isinstance(flow_context.get("product"), Mapping) else {}
    for key, value in {
        "goods_no": existing_snapshot.get("goods_no"),
        "tire_size": existing_snapshot.get("tire_size"),
        "product_name": existing_snapshot.get("product_name")
        or existing_snapshot.get("tire_model")
        or existing_snapshot.get("pending_product_name"),
        "tire_model": existing_snapshot.get("tire_model") or existing_snapshot.get("pending_product_name"),
        "pending_product_name": existing_snapshot.get("pending_product_name") or existing_snapshot.get("tire_model"),
    }.items():
        if value not in (None, "", [], {}) and product.get(key) in (None, "", [], {}):
            product[key] = value
    product["ord_qty"] = ord_qty

    intent = dict(flow_context.get("intent")) if isinstance(flow_context.get("intent"), Mapping) else {}
    for key, value in {
        "pending_intent": existing_snapshot.get("pending_intent"),
        "goal_type": existing_snapshot.get("goal_type"),
    }.items():
        if value not in (None, "", [], {}) and intent.get(key) in (None, "", [], {}):
            intent[key] = value

    flow_context.update({
        "flow_type": flow_type,
        "status": "active",
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "flow_step": "quantity_selected",
        "quantity": {"ord_qty": ord_qty, "source": selected_quantity.get("selection_source") or "current_user_text"},
        "source": "flow_controller:select_quantity",
    })
    if product:
        flow_context["product"] = product
    if intent:
        flow_context["intent"] = intent
    return {key: value for key, value in flow_context.items() if value not in (None, "", [], {})}


def _selected_store_flow_context(
    *,
    active_flow: Mapping[str, Any],
    parent_flow_state: Mapping[str, Any],
    router_evidence: Mapping[str, Any],
    existing_snapshot: Mapping[str, Any],
    selected_store: Mapping[str, Any],
) -> dict[str, Any]:
    if not selected_store:
        return {}
    flow_context = dict(active_flow) if isinstance(active_flow, Mapping) else {}
    flow_type = _selected_store_flow_type(
        active_flow=active_flow,
        parent_flow_state=parent_flow_state,
        router_evidence=router_evidence,
        existing_snapshot=existing_snapshot,
        selected_store=selected_store,
    )
    product = dict(flow_context.get("product")) if isinstance(flow_context.get("product"), Mapping) else {}
    product_name = (
        selected_store.get("product_name")
        or selected_store.get("tire_model")
        or selected_store.get("pending_product_name")
        or existing_snapshot.get("product_name")
        or existing_snapshot.get("tire_model")
        or existing_snapshot.get("pending_product_name")
    )
    for key, value in {
        "goods_no": selected_store.get("goods_no") or existing_snapshot.get("goods_no"),
        "product_name": product_name,
        "tire_model": product_name,
        "pending_product_name": product_name,
        "tire_size": selected_store.get("tire_size") or existing_snapshot.get("tire_size"),
        "ord_qty": selected_store.get("ord_qty") or existing_snapshot.get("ord_qty"),
    }.items():
        if value not in (None, "", [], {}):
            product[key] = value

    store = dict(flow_context.get("store")) if isinstance(flow_context.get("store"), Mapping) else {}
    for key, value in {
        "shop_id": selected_store.get("shop_id") or existing_snapshot.get("shop_id"),
        "shop_name": selected_store.get("shop_name") or existing_snapshot.get("shop_name"),
        "region": selected_store.get("region") or existing_snapshot.get("region"),
    }.items():
        if value not in (None, "", [], {}):
            store[key] = value

    intent = dict(flow_context.get("intent")) if isinstance(flow_context.get("intent"), Mapping) else {}
    for key, value in {
        "pending_intent": selected_store.get("pending_intent")
        or ("stock" if flow_type == "stock" else existing_snapshot.get("pending_intent")),
        "goal_type": selected_store.get("goal_type")
        or ("store_with_stock" if flow_type == "stock" else existing_snapshot.get("goal_type")),
        "stock_check_mode": selected_store.get("stock_check_mode") or existing_snapshot.get("stock_check_mode"),
        "schedule_mode": selected_store.get("schedule_mode") or existing_snapshot.get("schedule_mode"),
    }.items():
        if value not in (None, "", [], {}):
            intent[key] = value

    flow_context.update({
        "flow_type": flow_type,
        "status": "resumed",
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "flow_step": "store_selected",
        "source": selected_store.get("selection_source") or "flow_controller:select_store",
    })
    if product:
        flow_context["product"] = product
    if store:
        flow_context["store"] = store
    if intent:
        flow_context["intent"] = intent

    if flow_type == "stock" and product.get("goods_no") and product.get("ord_qty") and store.get("shop_id"):
        flow_context.update({
            "target_action": "get_store_inventory_tool",
            "current_step": "check_inventory",
            "missing_slots": [],
            "next_tool": "get_store_inventory_tool",
            "allowed_tools": ["get_store_inventory_tool"],
            "tool_args_patch": {
                "goods_list": [{"goodsNo": product["goods_no"], "qty": str(product["ord_qty"])}],
                "shop_id_list": [{"shopId": store["shop_id"]}],
            },
            "progress_source": "flow_controller:store_slot_fill",
        })
    return {
        key: value
        for key, value in flow_context.items()
        if value not in (None, "", {}) and (key == "missing_slots" or value != [])
    }


def _flow_state_summary(context: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(context, Mapping) or not context:
        return {}
    intent = _mapping_value(context, "intent")
    context_key = str(context.get("context_key") or "").strip()
    flow_type = context.get("flow_type") or _flow_type_from_context_key(context_key)
    return {
        key: value
        for key, value in {
            "flow_type": flow_type,
            "status": context.get("status"),
            "flow_step": context.get("flow_step") or context.get("pending_step"),
            "intent": intent.get("pending_intent") or context.get("pending_intent"),
            "goal_type": intent.get("goal_type") or context.get("goal_type"),
            "context_key": context_key,
        }.items()
        if value not in (None, "", [], {})
    }


def _flow_type_from_context_key(context_key: str) -> str:
    if context_key in {"pending_order_context", "dormant_purchase_context", "dormant_transaction_context"}:
        return "purchase"
    if context_key == "dormant_stock_context":
        return "stock"
    return ""


def _current_flow_state(active_flow: Mapping[str, Any], router_evidence: Mapping[str, Any]) -> dict[str, Any]:
    current = _flow_state_summary(active_flow)
    if current:
        return current
    router_intent = str(router_evidence.get("intent") or "").strip()
    router_domain = str(router_evidence.get("domain") or "").strip()
    if not router_intent and not router_domain:
        return {}
    return {
        key: value
        for key, value in {
            "flow_type": router_domain or "current_turn",
            "status": "observed",
            "flow_step": "router_observed",
            "intent": router_intent,
        }.items()
        if value not in (None, "", [], {})
    }


def _current_turn_flow_seed(router_evidence: Mapping[str, Any]) -> dict[str, Any]:
    router_intent = str(router_evidence.get("intent") or "").strip()
    router_domain = str(router_evidence.get("domain") or "").strip()
    if not router_intent and not router_domain:
        return {}
    return {
        key: value
        for key, value in {
            "flow_type": router_domain or "current_turn",
            "flow_step": "router_observed",
            "intent": router_intent,
        }.items()
        if value not in (None, "", [], {})
    }


def _router_execution_plan(router_evidence: Mapping[str, Any]) -> tuple[str, ...]:
    raw_plan = router_evidence.get("execution_plan")
    if not isinstance(raw_plan, (list, tuple)):
        return ()
    return tuple(str(item or "").strip() for item in raw_plan if str(item or "").strip())


def _current_turn_store_search_intent(router_evidence: Mapping[str, Any]) -> str:
    router_intent = str(router_evidence.get("intent") or "").strip()
    execution_plan = _router_execution_plan(router_evidence)
    if any("store_recommendation_by_vehicle_experience" in item for item in execution_plan):
        return "store_recommendation_by_vehicle_experience"
    if router_intent in _STORE_SEARCH_FLOW_INTENTS:
        return router_intent
    if any(item.endswith(":store_search") or item == "store_search" for item in execution_plan):
        return "store_search"
    return ""


def _current_turn_store_search_flow_context(
    *,
    router_evidence: Mapping[str, Any],
    existing_snapshot: Mapping[str, Any],
    extracted_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    intent = _current_turn_store_search_intent(router_evidence)
    if not intent:
        return {}

    region = _normalized_region_text(extracted_snapshot.get("region") or existing_snapshot.get("region"))
    place_query = str(extracted_snapshot.get("place_query") or existing_snapshot.get("place_query") or "").strip()
    shop_id = str(extracted_snapshot.get("shop_id") or existing_snapshot.get("shop_id") or "").strip()
    shop_name = str(extracted_snapshot.get("shop_name") or existing_snapshot.get("shop_name") or "").strip()
    store: dict[str, Any] = {
        key: value
        for key, value in {
            "region": region if region and not _is_invalid_region_text(region) else "",
            "place_query": place_query,
            "shop_id": shop_id,
            "shop_name": shop_name,
        }.items()
        if value not in (None, "", [], {})
    }
    if store.get("region") and not store.get("place_query"):
        store["place_query"] = store["region"]

    condition = str(
        extracted_snapshot.get("requested_vehicle_experience")
        or existing_snapshot.get("requested_vehicle_experience")
        or router_evidence.get("requested_vehicle_experience")
        or ""
    ).strip()
    search_condition = str(
        extracted_snapshot.get("store_search_condition")
        or existing_snapshot.get("store_search_condition")
        or router_evidence.get("store_search_condition")
        or ""
    ).strip()
    if intent == "store_recommendation_by_vehicle_experience":
        search_condition = search_condition or "vehicle_experience"

    return {
        key: value
        for key, value in {
            "flow_type": "store_search",
            "status": "active",
            "flow_step": "search_ready" if store else "ask_region",
            "store": store,
            "intent": {
                key: value
                for key, value in {
                    "pending_intent": intent,
                    "goal_type": "store_search",
                    "store_search_condition": search_condition,
                    "requested_vehicle_experience": condition,
                }.items()
                if value not in (None, "", [], {})
            },
            "source": "flow_controller:current_turn_store_search",
        }.items()
        if value not in (None, "", [], {})
    }


def _current_turn_discovery_intent(router_evidence: Mapping[str, Any]) -> str:
    router_intent = str(router_evidence.get("intent") or "").strip()
    router_domain = str(router_evidence.get("domain") or "").strip()
    execution_plan = _router_execution_plan(router_evidence)
    plan_tokens = {item.split(":", 1)[-1].strip() for item in execution_plan}
    if router_domain == "discovery" and router_intent in _DISCOVERY_FLOW_INTENTS:
        return router_intent
    if router_intent in _DISCOVERY_FLOW_INTENTS and any(item.startswith("discovery:") for item in execution_plan):
        return router_intent
    for token in plan_tokens:
        if token in _DISCOVERY_EXECUTION_PLAN_TOKENS:
            return token
    return ""


def _current_turn_discovery_flow_context(
    *,
    router_evidence: Mapping[str, Any],
    existing_snapshot: Mapping[str, Any],
    extracted_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    intent = _current_turn_discovery_intent(router_evidence)
    if not intent:
        return {}

    scenario = str(
        extracted_snapshot.get("recommendation_scenario")
        or existing_snapshot.get("recommendation_scenario")
        or extracted_snapshot.get("scenario")
        or existing_snapshot.get("scenario")
        or router_evidence.get("recommendation_scenario")
        or ""
    ).strip()
    recommendation = {
        key: value
        for key, value in {
            "scenario": scenario,
            "recommendation_scenario": scenario,
            "rcmd_type": extracted_snapshot.get("rcmd_type") or existing_snapshot.get("rcmd_type"),
            "season_nm": extracted_snapshot.get("season_nm") or existing_snapshot.get("season_nm"),
            "brand_cd": extracted_snapshot.get("brand_cd") or existing_snapshot.get("brand_cd"),
            "source_text": router_evidence.get("source_text"),
        }.items()
        if value not in (None, "", [], {})
    }
    product = {
        key: value
        for key, value in {
            "product_name": extracted_snapshot.get("product_name") or existing_snapshot.get("product_name"),
            "tire_model": extracted_snapshot.get("tire_model") or existing_snapshot.get("tire_model"),
            "pending_product_name": extracted_snapshot.get("pending_product_name")
            or existing_snapshot.get("pending_product_name"),
            "tire_size": extracted_snapshot.get("tire_size") or existing_snapshot.get("tire_size"),
        }.items()
        if value not in (None, "", [], {})
    }
    vehicle = {
        key: value
        for key, value in {
            "car_no": extracted_snapshot.get("car_no") or existing_snapshot.get("car_no"),
            "requested_vehicle_name": extracted_snapshot.get("requested_vehicle_name")
            or existing_snapshot.get("requested_vehicle_name"),
            "tire_size": extracted_snapshot.get("tire_size") or existing_snapshot.get("tire_size"),
        }.items()
        if value not in (None, "", [], {})
    }
    flow_step = "recommend"
    if intent in {"vehicle_based_recommendation_refinement", "vehicle_based_tire_recommendation", "vehicle_resolved_recommendation"}:
        flow_step = "select_vehicle"
    if intent in {"product_search", "resolve_or_describe_product"}:
        flow_step = "search_product"

    return {
        key: value
        for key, value in {
            "flow_type": "recommendation",
            "status": "active",
            "flow_step": flow_step,
            "product": product,
            "vehicle": vehicle,
            "recommendation": recommendation,
            "intent": {
                "pending_intent": intent,
                "goal_type": "recommend_tire" if "recommend" in intent or "best_selling" in intent else "product_search",
            },
            "source": "flow_controller:current_turn_discovery",
        }.items()
        if value not in (None, "", [], {})
    }


def _current_turn_support_intent(router_evidence: Mapping[str, Any]) -> str:
    router_intent = str(router_evidence.get("intent") or "").strip()
    router_domain = str(router_evidence.get("domain") or "").strip()
    execution_plan = _router_execution_plan(router_evidence)
    plan_tokens = {item.split(":", 1)[-1].strip() for item in execution_plan}
    if router_domain == "support" and (router_intent in _SUPPORT_FLOW_INTENTS or router_intent):
        return router_intent or "support_faq"
    if router_intent in _SUPPORT_FLOW_INTENTS and any(item.startswith("support:") for item in execution_plan):
        return router_intent
    for token in plan_tokens:
        if token in _SUPPORT_EXECUTION_PLAN_TOKENS:
            return token if token in _SUPPORT_FLOW_INTENTS else router_intent or "support_faq"
    return ""


def _current_turn_support_flow_context(*, router_evidence: Mapping[str, Any]) -> dict[str, Any]:
    intent = _current_turn_support_intent(router_evidence)
    if not intent:
        return {}
    return {
        key: value
        for key, value in {
            "flow_type": "support",
            "status": "active",
            "flow_step": "answer_faq",
            "intent": {
                key: value
                for key, value in {
                    "pending_intent": intent,
                    "goal_type": "support_faq",
                    "support_topic": router_evidence.get("support_topic"),
                    "faq_topic": router_evidence.get("faq_topic"),
                    "policy_topic": router_evidence.get("policy_topic") or intent,
                }.items()
                if value not in (None, "", [], {})
            },
            "source": "flow_controller:current_turn_support",
        }.items()
        if value not in (None, "", [], {})
    }


def _router_plan_has_intent(router_evidence: Mapping[str, Any], *intents: str) -> bool:
    execution_plan = _router_execution_plan(router_evidence)
    return any(any(intent in item for intent in intents) for item in execution_plan)


def _router_has_support_anchor(router_evidence: Mapping[str, Any]) -> bool:
    router_domain = str(router_evidence.get("domain") or "").strip()
    execution_plan = _router_execution_plan(router_evidence)
    return router_domain == "support" or any(item.startswith("support:") for item in execution_plan)


def _current_turn_service_maintenance_intent(router_evidence: Mapping[str, Any]) -> str:
    router_intent = str(router_evidence.get("intent") or "").strip()
    if router_intent in _SERVICE_MAINTENANCE_FLOW_INTENTS:
        return router_intent
    for intent in _SERVICE_MAINTENANCE_FLOW_INTENTS:
        if _router_plan_has_intent(router_evidence, intent):
            return intent
    return ""


def _current_turn_service_maintenance_flow_context(
    *,
    router_evidence: Mapping[str, Any],
    existing_snapshot: Mapping[str, Any],
    extracted_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    intent = _current_turn_service_maintenance_intent(router_evidence)
    if not intent:
        return {}

    boundary = str(
        extracted_snapshot.get("service_action_boundary")
        or existing_snapshot.get("service_action_boundary")
        or router_evidence.get("service_action_boundary")
        or ""
    ).strip()
    if not boundary:
        if intent in {"store_attribute_inquiry", "store_service_availability", "store_service_search"}:
            boundary = "store_verification"
        elif intent == "maintenance_addon_with_tire_service":
            boundary = "service_booking_support"
        else:
            boundary = "policy_answer"
    shop_id = str(extracted_snapshot.get("shop_id") or existing_snapshot.get("shop_id") or "").strip()
    shop_name = str(extracted_snapshot.get("shop_name") or existing_snapshot.get("shop_name") or "").strip()
    store_name = str(extracted_snapshot.get("store_name") or existing_snapshot.get("store_name") or "").strip()
    service_name = str(extracted_snapshot.get("service_name") or existing_snapshot.get("service_name") or "").strip()
    service_type = str(extracted_snapshot.get("service_type") or existing_snapshot.get("service_type") or "").strip()
    current_step = "verify_store_service" if boundary == "store_verification" else "answer_policy"
    allowed_tools = ["get_store_list_tool", "get_store_detail_tool"] if boundary == "store_verification" else ["search_faq_hybrid_tool"]
    preferred_tool = "get_store_list_tool" if boundary == "store_verification" else "search_faq_hybrid_tool"
    return {
        key: value
        for key, value in {
            "flow_type": "service_maintenance",
            "status": "active",
            "flow_step": current_step,
            "store": {
                key: value
                for key, value in {
                    "shop_id": shop_id,
                    "shop_name": shop_name,
                    "store_name": store_name,
                }.items()
                if value not in (None, "", [], {})
            },
            "intent": {
                key: value
                for key, value in {
                    "pending_intent": intent,
                    "goal_type": boundary,
                    "service_action_boundary": boundary,
                    "service_name": service_name,
                    "service_type": service_type,
                }.items()
                if value not in (None, "", [], {})
            },
            "target_action": boundary,
            "next_tool": preferred_tool,
            "allowed_tools": allowed_tools,
            "preferred_tool": preferred_tool,
            "source": "flow_controller:service_maintenance",
        }.items()
        if value not in (None, "", [], {}) and (key == "allowed_tools" or value != [])
    }


def _current_turn_reservation_management_intent(router_evidence: Mapping[str, Any]) -> str:
    router_intent = str(router_evidence.get("intent") or "").strip()
    if router_intent in _RESERVATION_POLICY_ONLY_FLOW_INTENTS and _router_has_support_anchor(router_evidence):
        return ""
    if router_intent in _RESERVATION_MANAGEMENT_FLOW_INTENTS:
        return router_intent
    for intent in _RESERVATION_MANAGEMENT_FLOW_INTENTS:
        if _router_plan_has_intent(router_evidence, intent):
            if intent in _RESERVATION_POLICY_ONLY_FLOW_INTENTS and _router_has_support_anchor(router_evidence):
                return ""
            return intent
    return ""


def _reservation_management_action_for_intent(intent: str, slots: Mapping[str, Any]) -> str:
    explicit = str(slots.get("reservation_management_action") or "").strip()
    if explicit:
        return explicit
    if intent in {"reservation_status_lookup", "reservation_store_info_lookup", "order_cancel_status_lookup"}:
        return "lookup"
    if intent == "reservation_change_request":
        return "change_request"
    if intent == "order_cancel_request":
        return "cancel_request"
    if intent in {"general_cancel_fee_policy", "reservation_window_policy", "delivery_delay_reservation_schedule_policy"}:
        return "policy_answer"
    return "lookup"


def _current_turn_reservation_management_flow_context(
    *,
    router_evidence: Mapping[str, Any],
    existing_snapshot: Mapping[str, Any],
    extracted_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    intent = _current_turn_reservation_management_intent(router_evidence)
    if not intent:
        return {}
    slots = {**existing_snapshot, **extracted_snapshot}
    action = _reservation_management_action_for_intent(intent, slots)
    if action == "lookup":
        allowed_tools = ["get_my_reservations_tool", "get_orders_of_user_tool", "get_order_status_tool"]
        preferred_tool = "get_my_reservations_tool"
        step = "lookup_owned_record"
    elif action == "policy_answer":
        allowed_tools = ["search_faq_hybrid_tool"]
        preferred_tool = "search_faq_hybrid_tool"
        step = "answer_policy"
    else:
        allowed_tools = []
        preferred_tool = ""
        step = "guide_user_action"
    return {
        key: value
        for key, value in {
            "flow_type": "reservation_management",
            "status": "active",
            "flow_step": step,
            "intent": {
                key: value
                for key, value in {
                    "pending_intent": intent,
                    "goal_type": "reservation_management",
                    "reservation_management_action": action,
                    "owned_record_target": slots.get("owned_record_target") or "reservation",
                }.items()
                if value not in (None, "", [], {})
            },
            "target_action": action,
            "next_tool": preferred_tool,
            "allowed_tools": allowed_tools,
            "preferred_tool": preferred_tool,
            "source": "flow_controller:reservation_management",
        }.items()
        if value not in (None, "", {}) and (key == "allowed_tools" or value != [])
    }


def _transition_kind(
    current_flow_state: Mapping[str, Any],
    parent_flow_state: Mapping[str, Any],
    router_evidence: Mapping[str, Any],
) -> str:
    current_type = str(current_flow_state.get("flow_type") or "").strip()
    parent_type = str(parent_flow_state.get("flow_type") or "").strip()
    router_intent = str(router_evidence.get("intent") or "").strip()
    if current_type and parent_type and current_type != parent_type:
        return "current_flow_with_parent_context"
    if current_type:
        return "current_flow_observed"
    if parent_type:
        return "parent_context_only"
    if router_intent:
        return "router_observed"
    return "none"


def transition_current_flow(
    *,
    user_text: str,
    router_evidence: Mapping[str, Any] | None = None,
    existing_slots: Any | Mapping[str, Any] | None = None,
    extracted_slots: Any | Mapping[str, Any] | None = None,
    ui_action: Mapping[str, Any] | None = None,
    resume_source: str = "none",
) -> FlowTransition:
    """Build read-only flow transition metadata; it must not authorize tool execution."""
    router_snapshot = _non_empty_mapping(router_evidence)
    availability_context = _availability_context_from_slots(existing_slots)
    active_flow = _mapping_value(availability_context, "active_flow_context")
    parent_flow = _parent_flow_context(availability_context)
    extracted_snapshot = _compact_slot_snapshot(extracted_slots)
    existing_snapshot = _compact_slot_snapshot(existing_slots)
    ui_action_snapshot = _ui_action_snapshot(ui_action)
    selected_product = _selected_product_from_ui_action(ui_action_snapshot)
    selected_quantity = _selected_quantity_from_ui_action(ui_action_snapshot)
    selected_store = _selected_store_from_slots(
        extracted_snapshot=extracted_snapshot,
        existing_snapshot=existing_snapshot,
        active_flow=active_flow,
        router_evidence=router_snapshot,
        resume_source=resume_source,
    )

    current_flow_state = _current_flow_state(active_flow, router_snapshot)
    parent_flow_state = _flow_state_summary(parent_flow)
    transition_kind = _transition_kind(current_flow_state, parent_flow_state, router_snapshot)
    if not selected_quantity:
        selected_quantity = _selected_quantity_from_slots(
            extracted_snapshot=extracted_snapshot,
            existing_snapshot=existing_snapshot,
            active_flow=active_flow,
            parent_flow_state=parent_flow_state,
            router_evidence=router_snapshot,
        )
    selected_product_flow_context = _selected_product_flow_context(
        current_flow_state=current_flow_state,
        parent_flow_state=parent_flow_state,
        router_evidence=router_snapshot,
        selected_product=selected_product,
        ui_action_snapshot=ui_action_snapshot,
    )
    selected_quantity_flow_context = _selected_quantity_flow_context(
        active_flow=active_flow,
        current_flow_state=current_flow_state,
        parent_flow_state=parent_flow_state,
        router_evidence=router_snapshot,
        existing_snapshot=existing_snapshot,
        selected_quantity=selected_quantity,
    )
    selected_store_flow_context = _selected_store_flow_context(
        active_flow=active_flow,
        parent_flow_state=parent_flow_state,
        router_evidence=router_snapshot,
        existing_snapshot=existing_snapshot,
        selected_store=selected_store,
    )
    current_turn_store_search_flow_context = _current_turn_store_search_flow_context(
        router_evidence=router_snapshot,
        existing_snapshot=existing_snapshot,
        extracted_snapshot=extracted_snapshot,
    )
    current_turn_service_maintenance_flow_context = _current_turn_service_maintenance_flow_context(
        router_evidence=router_snapshot,
        existing_snapshot=existing_snapshot,
        extracted_snapshot=extracted_snapshot,
    )
    current_turn_reservation_management_flow_context = _current_turn_reservation_management_flow_context(
        router_evidence=router_snapshot,
        existing_snapshot=existing_snapshot,
        extracted_snapshot=extracted_snapshot,
    )
    current_turn_discovery_flow_context = _current_turn_discovery_flow_context(
        router_evidence=router_snapshot,
        existing_snapshot=existing_snapshot,
        extracted_snapshot=extracted_snapshot,
    )
    current_turn_support_flow_context = _current_turn_support_flow_context(router_evidence=router_snapshot)
    active_flow_context = (
        selected_product_flow_context
        or selected_quantity_flow_context
        or selected_store_flow_context
        or current_turn_service_maintenance_flow_context
        or current_turn_support_flow_context
        or current_turn_reservation_management_flow_context
        or current_turn_store_search_flow_context
        or current_turn_discovery_flow_context
    )
    applied_reason = "metadata_only_shell"
    if selected_product_flow_context:
        applied_reason = "selected_product_flow_state"
    elif selected_quantity_flow_context:
        applied_reason = "selected_quantity_flow_state"
    elif selected_store_flow_context:
        applied_reason = "selected_store_flow_state"
    elif current_turn_service_maintenance_flow_context:
        applied_reason = "current_turn_service_maintenance_flow_state"
    elif current_turn_support_flow_context:
        applied_reason = "current_turn_support_flow_state"
    elif current_turn_reservation_management_flow_context:
        applied_reason = "current_turn_reservation_management_flow_state"
    elif current_turn_store_search_flow_context:
        applied_reason = "current_turn_store_search_flow_state"
    elif current_turn_discovery_flow_context:
        applied_reason = "current_turn_discovery_flow_state"
    current_turn_seed = _current_turn_flow_seed(router_snapshot)
    contract_seed = {
        "router_evidence": router_snapshot,
        "ui_action": ui_action_snapshot,
        "resume_source": resume_source if resume_source else "none",
        "current_flow": {
            key: current_turn_seed.get(key)
            for key in ("flow_type", "flow_step", "intent", "goal_type")
            if current_turn_seed.get(key) not in (None, "", [], {})
        },
    }
    context_evidence = {
        "active_flow_context": active_flow,
        "parent_flow_context": parent_flow,
        "existing_slots": existing_snapshot,
        "extracted_slots": extracted_snapshot,
        "selected_product": selected_product,
        "selected_quantity": selected_quantity,
        "selected_store": selected_store,
        "current_turn_service_maintenance_flow": current_turn_service_maintenance_flow_context,
        "current_turn_reservation_management_flow": current_turn_reservation_management_flow_context,
        "current_turn_store_search_flow": current_turn_store_search_flow_context,
        "current_turn_discovery_flow": current_turn_discovery_flow_context,
        "current_turn_support_flow": current_turn_support_flow_context,
    }
    context_evidence = {key: value for key, value in context_evidence.items() if value not in (None, "", [], {})}
    metadata = {
        "flow_transition_shell": True,
        "flow_transition_applied": bool(active_flow_context),
        "transition_kind": transition_kind,
        "current_flow_type": str(current_flow_state.get("flow_type") or "none"),
        "current_flow_step": str(current_flow_state.get("flow_step") or "none"),
        "parent_flow_type": str(parent_flow_state.get("flow_type") or "none"),
        "contract_seed_keys": sorted(contract_seed),
        "context_evidence_keys": sorted(context_evidence),
        "router_intent": str(router_snapshot.get("intent") or "none"),
        "selected_product_resolved": bool(selected_product),
        "selected_quantity_resolved": bool(selected_quantity),
        "selected_store_resolved": bool(selected_store),
        "current_turn_service_maintenance_resolved": bool(current_turn_service_maintenance_flow_context),
        "current_turn_reservation_management_resolved": bool(current_turn_reservation_management_flow_context),
        "current_turn_store_search_resolved": bool(current_turn_store_search_flow_context),
        "current_turn_discovery_resolved": bool(current_turn_discovery_flow_context),
        "current_turn_support_resolved": bool(current_turn_support_flow_context),
        "user_text_present": bool(str(user_text or "").strip()),
    }
    return FlowTransition(
        current_flow_state=current_flow_state,
        parent_flow_state=parent_flow_state,
        flow_transition={
            "kind": transition_kind,
            "applied": bool(active_flow_context),
            "reason": applied_reason,
            "active_flow_context": active_flow_context,
        },
        contract_seed=contract_seed,
        context_evidence=context_evidence,
        metadata=metadata,
    )


def resolve_purchase_order_flow(
    *,
    intent: str,
    known_slots: Mapping[str, Any] | None = None,
) -> FlowState | None:
    if intent not in {"quick_order_reservation", "quick_order_reservation_continue", "quick_order_execute"}:
        return None

    slots = dict(known_slots or {})
    goods_no = str(slots.get("goods_no") or "").strip()
    tire_size = normalize_tire_size(str(slots.get("tire_size") or ""))
    quantity = slots.get("ord_qty") or slots.get("quantity")
    shop_id = str(slots.get("shop_id") or "").strip()
    location_type = location_source_type(slots)
    requested_cal_day = str(slots.get("requested_cal_day") or "").strip()
    rsv_hour = str(slots.get("rsv_hour") or "").strip()
    pending_intent = str(slots.get("pending_intent") or "").strip()
    goal_type = str(slots.get("goal_type") or "").strip()
    is_cart_flow = pending_intent == "cart" or goal_type == "add_to_cart"

    base_patch = _purchase_slot_patch(slots)
    base_metadata = {
        "flow_id": _CART_FLOW_ID if is_cart_flow else _PURCHASE_FLOW_ID,
        "flow_slots": base_patch,
    }

    if intent == "quick_order_execute" and not is_cart_flow:
        execute_missing: list[str] = []
        if not goods_no:
            execute_missing.append("product")
        if quantity in (None, "", 0, "0"):
            execute_missing.append("quantity")
        if not shop_id:
            execute_missing.append("store")
        if not (requested_cal_day and rsv_hour):
            execute_missing.append("booking_datetime")
        if execute_missing:
            return FlowState(
                flow_id=_PURCHASE_FLOW_ID,
                flow_step="execute_order",
                required_slots=tuple(execute_missing),
                missing_slots=tuple(execute_missing),
                allowed_tools=(),
                forbidden_tools=(
                    "get_final_price_tool",
                    "get_logistics_inventory_tool",
                    "get_store_inventory_tool",
                    "transaction_store_preview_tool",
                    "get_store_schedule_tool",
                    "get_multi_store_schedule_tool",
                    "quick_order_tool",
                ),
                preferred_tool=None,
                template=TemplateName.QUICK_REPLY,
                response_shape_key="missing_order_execution_slots",
                action_mode="purchase_continuation",
                slot_patch=base_patch,
                metadata=base_metadata,
            )

    if not goods_no:
        product_name = str(
            slots.get("product_name") or slots.get("tire_model") or slots.get("pending_product_name") or ""
        ).strip()
        if product_name and not tire_size:
            return FlowState(
                flow_id=_PURCHASE_FLOW_ID,
                flow_step="ask_size",
                required_slots=("tire_size",),
                missing_slots=("tire_size",),
                allowed_tools=(),
                forbidden_tools=_PURCHASE_FORBIDDEN_TOOLS,
                preferred_tool=None,
                template=TemplateName.QUICK_REPLY,
                response_shape_key="missing_order_slots",
                action_mode="purchase_continuation",
                slot_patch=base_patch,
                metadata=base_metadata,
            )
        return FlowState(
            flow_id=_PURCHASE_FLOW_ID,
            flow_step="resolve_product",
            required_slots=("product",),
            missing_slots=("product",) if not product_name else (),
            allowed_tools=("search_product_tool",),
            forbidden_tools=tuple(tool for tool in _PURCHASE_FORBIDDEN_TOOLS if tool != "transaction_store_preview_tool"),
            preferred_tool="search_product_tool",
            template=TemplateName.QUICK_REPLY,
            response_shape_key="missing_order_slots" if product_name else "product_search_summary",
            action_mode="purchase_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    if quantity in (None, "", 0, "0"):
        return FlowState(
            flow_id=_CART_FLOW_ID if is_cart_flow else _PURCHASE_FLOW_ID,
            flow_step="ask_quantity",
            required_slots=("quantity",),
            missing_slots=("quantity",),
            allowed_tools=(),
            forbidden_tools=_CART_FORBIDDEN_TOOLS if is_cart_flow else _PURCHASE_FORBIDDEN_TOOLS,
            preferred_tool=None,
            template=TemplateName.QUICK_REPLY,
            response_shape_key="missing_order_slots",
            action_mode="purchase_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    if is_cart_flow:
        return FlowState(
            flow_id=_CART_FLOW_ID,
            flow_step="execute_cart",
            required_slots=(),
            missing_slots=(),
            allowed_tools=("save_to_cart_tool",),
            forbidden_tools=_CART_FORBIDDEN_TOOLS,
            preferred_tool="save_to_cart_tool",
            template=TemplateName.ORDER_COMPLETE,
            response_shape_key="cart_add_execute",
            action_mode="purchase_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    if not shop_id and location_type == "none":
        return FlowState(
            flow_id=_PURCHASE_FLOW_ID,
            flow_step="ask_store",
            required_slots=("store",),
            missing_slots=("store",),
            allowed_tools=(),
            forbidden_tools=_PURCHASE_FORBIDDEN_TOOLS,
            preferred_tool=None,
            template=TemplateName.QUICK_REPLY,
            response_shape_key="missing_order_slots",
            action_mode="purchase_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    if not shop_id and location_type in {"region", "place", "browser_location"}:
        return FlowState(
            flow_id=_PURCHASE_FLOW_ID,
            flow_step="show_store_candidates",
            required_slots=(),
            missing_slots=(),
            allowed_tools=("transaction_store_preview_tool",),
            forbidden_tools=(
                "get_final_price_tool",
                "get_logistics_inventory_tool",
                "get_store_inventory_tool",
                "get_store_schedule_tool",
                "get_multi_store_schedule_tool",
                "quick_order_tool",
            ),
            preferred_tool="transaction_store_preview_tool",
            template=TemplateName.LOCATION,
            response_shape_key="reservation_store_candidates",
            action_mode="purchase_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    if not shop_id and location_type == "store":
        return FlowState(
            flow_id=_PURCHASE_FLOW_ID,
            flow_step="resolve_store",
            required_slots=(),
            missing_slots=(),
            allowed_tools=("transaction_store_preview_tool",),
            forbidden_tools=(
                "get_final_price_tool",
                "get_logistics_inventory_tool",
                "get_store_inventory_tool",
                "quick_order_tool",
            ),
            preferred_tool="transaction_store_preview_tool",
            template=TemplateName.LOCATION,
            response_shape_key="reservation_store_candidates",
            action_mode="purchase_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    if not (requested_cal_day and rsv_hour):
        return FlowState(
            flow_id=_PURCHASE_FLOW_ID,
            flow_step="show_schedule",
            required_slots=(),
            missing_slots=("booking_datetime",),
            allowed_tools=("get_store_schedule_tool", "get_multi_store_schedule_tool"),
            forbidden_tools=(
                "get_final_price_tool",
                "get_logistics_inventory_tool",
                "get_store_inventory_tool",
                "quick_order_tool",
            ),
            preferred_tool="get_store_schedule_tool",
            template=TemplateName.DATE_PICK,
            response_shape_key="reservation_slots",
            action_mode="booking_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    if intent == "quick_order_execute":
        return FlowState(
            flow_id=_PURCHASE_FLOW_ID,
            flow_step="execute_order",
            required_slots=(),
            missing_slots=(),
            allowed_tools=("quick_order_tool",),
            forbidden_tools=(
                "get_final_price_tool",
                "get_logistics_inventory_tool",
                "get_store_inventory_tool",
                "transaction_store_preview_tool",
                "get_store_schedule_tool",
                "get_multi_store_schedule_tool",
            ),
            preferred_tool="quick_order_tool",
            template=TemplateName.ORDER_COMPLETE,
            response_shape_key="quick_order_execute",
            action_mode="purchase_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    return FlowState(
        flow_id=_PURCHASE_FLOW_ID,
        flow_step="build_preorder",
        required_slots=(),
        missing_slots=(),
        allowed_tools=(),
        forbidden_tools=(
            "get_logistics_inventory_tool",
            "get_store_inventory_tool",
            "transaction_store_preview_tool",
            "get_store_schedule_tool",
            "get_multi_store_schedule_tool",
            "quick_order_tool",
        ),
        preferred_tool=None,
        template=TemplateName.PRE_ORDER,
        response_shape_key="reservation_confirmation_ready",
        action_mode="purchase_continuation",
        slot_patch=base_patch,
        metadata=base_metadata,
    )


def build_purchase_flow_fallback_event(
    *,
    flow_state: FlowState | None = None,
    intent: str | None = None,
    known_slots: Mapping[str, Any] | None = None,
    tool_data_list: list[dict] | None = None,
    blocked_tool: str | None = None,
) -> dict[str, Any] | None:
    state = flow_state or resolve_purchase_order_flow(intent=intent or "", known_slots=known_slots)
    if state is None:
        return None

    slots = dict(known_slots or state.slot_patch or {})
    resolved_product = _resolved_purchase_product(slots=slots, tool_data_list=tool_data_list)
    merged_slots = {**slots, **resolved_product}
    if resolved_product:
        resumed_state = resolve_purchase_order_flow(intent=intent or "", known_slots=merged_slots)
        if resumed_state is not None:
            state = resumed_state
    metadata = {
        "flowId": state.flow_id,
        "flowStep": state.flow_step,
        "missingSlots": list(state.missing_slots),
        "response_shape_key": state.response_shape_key,
    }
    if blocked_tool:
        metadata["blockedTool"] = blocked_tool
    if merged_slots.get("goods_no"):
        metadata["goodsNo"] = merged_slots["goods_no"]
    if merged_slots.get("product_name"):
        metadata["productName"] = merged_slots["product_name"]
    if merged_slots.get("tire_size"):
        metadata["tireSize"] = merged_slots["tire_size"]
    if merged_slots.get("ord_qty") or merged_slots.get("quantity"):
        metadata["ordQty"] = merged_slots.get("ord_qty") or merged_slots.get("quantity")

    if state.flow_step == "ask_store":
        assistant_response = _purchase_missing_store_text(merged_slots)
    elif state.flow_step == "ask_quantity":
        assistant_response = _purchase_missing_quantity_text(merged_slots)
    elif state.flow_step in {"resolve_product", "ask_size"}:
        resolution_event = _purchase_product_resolution_event(
            state=state,
            slots=slots,
            tool_data_list=tool_data_list,
            blocked_tool=blocked_tool,
        )
        if resolution_event is not None:
            return resolution_event
        return None
    else:
        return None

    return {
        "type": "data",
        "template": state.template.value,
        "source_domain": "transaction",
        "assistant_response_source": "code_purchase_flow_fallback",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": _purchase_fallback_quick_replies(state.flow_step),
            "predictedDomains": ["TRANSACTION", "DISCOVERY"],
            "metadata": metadata,
        },
    }


def build_selected_store_confirmation_event(
    *,
    selected_store: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    selected = {key: value for key, value in dict(selected_store or {}).items() if value not in (None, "", [], {})}
    shop_id = str(selected.get("shop_id") or "").strip()
    shop_name = str(selected.get("shop_name") or selected.get("store_name") or "").strip()
    flow_type = str(selected.get("flow_type") or "").strip()
    if flow_type not in {"store_search", "store_service_search", "favorite_store"}:
        return None
    if not shop_id or not shop_name:
        return None

    quick_replies: list[dict[str, Any]] = [
        {
            "label": "매장 상세 페이지로 이동",
            "domain": "TRANSACTION",
            "url": CTAUrls.STORE_DETAIL.replace("<shop_seq>", shop_id),
        },
        {"label": "다른 매장 보기", "domain": "TRANSACTION"},
    ]
    return {
        "type": "data",
        "template": TemplateName.QUICK_REPLY.value,
        "source_domain": "transaction",
        "assistant_response_source": "code_selected_store_confirmation",
        "data": {
            "assistantResponse": f"{shop_name} 매장으로 선택했어요.",
            "quickReplies": quick_replies,
            "predictedDomains": ["TRANSACTION"],
            "metadata": {
                "response_shape_key": "selected_store_confirmation",
                "flowType": flow_type,
                "flowStep": str(selected.get("flow_step") or "store_selected"),
                "shopId": shop_id,
                "shopName": shop_name,
                "storeSelectionExecution": "none",
            },
        },
    }


def _purchase_slot_patch(slots: Mapping[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for key in (
        "goods_no",
        "product_name",
        "tire_model",
        "pending_product_name",
        "tire_size",
        "ord_qty",
        "quantity",
        "shop_id",
        "shop_name",
        "store_name",
        "region",
        "place_query",
        "user_xpos",
        "user_ypos",
        "xpos",
        "ypos",
        "place",
        "requested_cal_day",
        "rsv_hour",
        "pending_intent",
        "goal_type",
    ):
        value = slots.get(key)
        if value not in (None, ""):
            patch[key] = value
    if patch.get("pending_intent") in (None, ""):
        patch["pending_intent"] = "order"
    if patch.get("goal_type") in (None, ""):
        patch["goal_type"] = "place_order"
    if patch.get("pending_intent") == "cart":
        patch["goal_type"] = "add_to_cart"
    if patch.get("tire_size"):
        patch["tire_size"] = normalize_tire_size(str(patch["tire_size"]))
    return patch


def _resolved_purchase_product(*, slots: Mapping[str, Any], tool_data_list: list[dict] | None) -> dict[str, Any]:
    if slots.get("goods_no"):
        return {
            "goods_no": str(slots.get("goods_no") or "").strip(),
            "product_name": str(
                slots.get("product_name") or slots.get("tire_model") or slots.get("pending_product_name") or ""
            ).strip(),
            "tire_size": normalize_tire_size(str(slots.get("tire_size") or "")),
        }

    rows = _search_product_rows_from_entries(tool_data_list or [])
    if not rows:
        return {}

    target_name = str(
        slots.get("product_name") or slots.get("tire_model") or slots.get("pending_product_name") or ""
    ).strip()
    target_size = normalize_tire_size(str(slots.get("tire_size") or ""))
    matched_rows = rows
    if target_name:
        normalized_name = _normalize_product_key(target_name)
        name_rows = [
            row for row in matched_rows if normalized_name and normalized_name in _normalize_product_key(str(row.get("goods_nm") or ""))
        ]
        if name_rows:
            matched_rows = name_rows
    if target_size:
        size_rows = [
            row
            for row in matched_rows
            if normalize_tire_size(str(row.get("tire_size_1") or row.get("tire_size") or "")) == target_size
        ]
        if size_rows:
            matched_rows = size_rows
    if len(matched_rows) != 1:
        return {}
    row = matched_rows[0]
    return {
        "goods_no": str(row.get("goods_no") or "").strip(),
        "product_name": str(row.get("goods_nm") or target_name or "").strip(),
        "tire_size": normalize_tire_size(str(row.get("tire_size_1") or row.get("tire_size") or target_size or "")),
    }


def _search_product_rows_from_entries(entries: list[dict]) -> list[dict]:
    for entry in reversed(entries):
        if entry.get("tool") != "search_product_tool":
            continue
        payload = entry.get("data")
        for candidate in _search_payload_candidates(payload):
            if isinstance(candidate, list):
                rows = [row for row in candidate if isinstance(row, dict)]
                if rows:
                    return rows
    return []


def _search_payload_candidates(payload: Any) -> list[Any]:
    candidates: list[Any] = [payload]
    if isinstance(payload, dict):
        data = payload.get("data")
        candidates.append(data)
        if isinstance(data, dict):
            candidates.append(data.get("data"))
    expanded: list[Any] = []
    for candidate in candidates:
        expanded.append(candidate)
        if isinstance(candidate, dict):
            expanded.extend(candidate.get(key) for key in ("items", "products", "data"))
    return expanded


def _normalize_product_key(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def _matched_purchase_rows(*, slots: Mapping[str, Any], tool_data_list: list[dict] | None) -> list[dict]:
    rows = _search_product_rows_from_entries(tool_data_list or [])
    if not rows:
        return []

    target_name = str(
        slots.get("product_name") or slots.get("tire_model") or slots.get("pending_product_name") or ""
    ).strip()
    target_size = normalize_tire_size(str(slots.get("tire_size") or ""))
    matched_rows = rows
    if target_name:
        normalized_name = _normalize_product_key(target_name)
        name_rows = [
            row
            for row in matched_rows
            if normalized_name and normalized_name in _normalize_product_key(str(row.get("goods_nm") or ""))
        ]
        if name_rows:
            matched_rows = name_rows
    if target_size:
        size_rows = [
            row
            for row in matched_rows
            if normalize_tire_size(str(row.get("tire_size_1") or row.get("tire_size") or "")) == target_size
        ]
        if size_rows:
            matched_rows = size_rows
    return [row for row in matched_rows if isinstance(row, dict)]


def _purchase_product_resolution_event(
    *,
    state: FlowState,
    slots: Mapping[str, Any],
    tool_data_list: list[dict] | None,
    blocked_tool: str | None,
) -> dict[str, Any] | None:
    matched_rows = _matched_purchase_rows(slots=slots, tool_data_list=tool_data_list)
    if not matched_rows:
        return None

    sizes = _purchase_size_candidates(matched_rows)
    product_label = str(
        slots.get("product_name") or slots.get("tire_model") or slots.get("pending_product_name") or "해당 상품"
    ).strip() or "해당 상품"
    metadata = {
        "flowId": state.flow_id,
        "flowStep": state.flow_step,
        "missingSlots": list(state.missing_slots),
        "response_shape_key": state.response_shape_key,
        "productName": product_label,
        "pendingIntent": str(slots.get("pending_intent") or "order"),
        "goalType": str(slots.get("goal_type") or "place_order"),
    }
    if blocked_tool:
        metadata["blockedTool"] = blocked_tool
    quantity = slots.get("ord_qty") or slots.get("quantity")
    if quantity not in (None, "", 0, "0"):
        metadata["ordQty"] = quantity
    store_name = str(slots.get("shop_name") or slots.get("store_name") or "").strip()
    if store_name:
        metadata["shopName"] = store_name
    requested_cal_day = str(slots.get("requested_cal_day") or "").strip()
    if requested_cal_day:
        metadata["requestedCalDay"] = requested_cal_day
    availability_intent = str(slots.get("availability_intent") or "").strip()
    if availability_intent:
        metadata["availabilityIntent"] = availability_intent

    if sizes and not normalize_tire_size(str(slots.get("tire_size") or "")):
        return {
            "type": "data",
            "template": TemplateName.QUICK_REPLY.value,
            "source_domain": "transaction",
            "assistant_response_source": "code_purchase_flow_resolution_size_clarification",
            "data": {
                "assistantResponse": (
                    f"{product_label} 구매를 진행하려면 타이어 사이즈를 먼저 선택해 주세요.\n"
                    f"현재 확인되는 규격은 {', '.join(sizes[:8])}예요."
                ),
                "quickReplies": [
                    *({"label": size, "domain": "DISCOVERY"} for size in sizes[:6]),
                    {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
                ],
                "predictedDomains": ["TRANSACTION", "DISCOVERY"],
                "metadata": {**metadata, "sizes": sizes},
            },
        }

    candidate_quick_replies = _purchase_product_candidate_quick_replies(
        rows=matched_rows,
        slots=slots,
        flow_id=state.flow_id,
        flow_step=state.flow_step,
    )
    if candidate_quick_replies:
        return {
            "type": "data",
            "template": TemplateName.QUICK_REPLY.value,
            "source_domain": "transaction",
            "assistant_response_source": "code_purchase_flow_resolution_clarification",
            "data": {
                "assistantResponse": (
                    f"{product_label} 조건으로 확인되는 상품이 여러 개예요. "
                    "원하시는 상품을 선택해 주세요."
                ),
                "quickReplies": candidate_quick_replies,
                "predictedDomains": ["TRANSACTION", "DISCOVERY"],
                "metadata": {**metadata, "candidateCount": len(matched_rows), "sizes": sizes},
            },
        }

    return {
        "type": "data",
        "template": TemplateName.QUICK_REPLY.value,
        "source_domain": "transaction",
        "assistant_response_source": "code_purchase_flow_resolution_clarification",
        "data": {
            "assistantResponse": (
                f"{product_label} 조건으로 확인되는 상품이 여러 개예요. "
                "정확한 상품을 다시 선택하거나 규격을 알려주세요."
            ),
            "quickReplies": [
                {"label": "상품 다시 선택", "domain": "DISCOVERY"},
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
                {"label": "타이어 추천", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["TRANSACTION", "DISCOVERY"],
            "metadata": {**metadata, "candidateCount": len(matched_rows), "sizes": sizes},
        },
    }


def _purchase_product_candidate_quick_replies(
    *,
    rows: list[dict[str, Any]],
    slots: Mapping[str, Any],
    flow_id: str,
    flow_step: str,
) -> list[dict[str, Any]]:
    quick_replies: list[dict[str, Any]] = []
    seen_labels: set[str] = set()

    for row in rows[:6]:
        product_name = str(row.get("goods_nm") or "").strip()
        goods_no = str(row.get("goods_no") or "").strip()
        tire_size = normalize_tire_size(str(row.get("tire_size_1") or row.get("tire_size") or ""))
        if not (product_name and goods_no and tire_size):
            continue
        price_value = row.get("cheapest_final_prc") or row.get("sale_prc") or row.get("min_sale_prc")
        try:
            price_label = f" {int(price_value):,}원" if price_value not in (None, "", 0, "0") else ""
        except (TypeError, ValueError):
            price_label = ""
        label = f"{product_name} {tire_size}{price_label}".strip()
        if label in seen_labels:
            continue
        seen_labels.add(label)

        slot_values: dict[str, Any] = {
            "goods_no": goods_no,
            "tire_size": tire_size,
        }
        if product_name:
            slot_values["tire_model"] = product_name

        chip_metadata: dict[str, Any] = {
            "flowId": flow_id,
            "flowStep": flow_step,
            "goodsNo": goods_no,
            "tireSize": tire_size,
            "slots": slot_values,
        }

        quick_replies.append(
            {
                "label": label,
                "domain": "TRANSACTION",
                "cta_action": "select_product",
                "fills_slot": "product",
                "entity_id": goods_no,
                "source_intent": "quick_order_reservation",
                "expected_contract_intent": "quick_order_reservation",
                "expected_behavior": "slot_fill",
                "metadata": chip_metadata,
            }
        )
    return quick_replies


def _purchase_size_candidates(rows: list[dict]) -> list[str]:
    sizes: list[str] = []
    seen: set[str] = set()
    for row in rows:
        tire_size = normalize_tire_size(str(row.get("tire_size_1") or row.get("tire_size") or ""))
        compact = re.sub(r"[^0-9]", "", tire_size)
        if not compact or compact in seen:
            continue
        seen.add(compact)
        sizes.append(tire_size)
    return sizes


def _purchase_product_label(slots: Mapping[str, Any]) -> str:
    product_name = str(slots.get("product_name") or slots.get("tire_model") or slots.get("pending_product_name") or "").strip()
    tire_size = normalize_tire_size(str(slots.get("tire_size") or ""))
    return " ".join(part for part in (product_name, tire_size) if part)


def _purchase_missing_store_text(slots: Mapping[str, Any]) -> str:
    product_label = _purchase_product_label(slots)
    quantity = slots.get("ord_qty") or slots.get("quantity")
    if product_label and quantity not in (None, "", 0, "0"):
        return f"{product_label} {quantity}개 구매를 진행할 매장이나 지역을 알려주세요."
    if product_label:
        return f"{product_label} 구매를 진행할 매장이나 지역을 알려주세요."
    return "구매를 진행할 매장이나 지역을 알려주세요."


def _purchase_missing_quantity_text(slots: Mapping[str, Any]) -> str:
    product_label = _purchase_product_label(slots)
    store_name = str(slots.get("shop_name") or slots.get("store_name") or "").strip()
    if product_label and store_name:
        return f"{product_label} {store_name} 구매를 진행하려면 수량이 필요해요. 구매 수량을 알려주세요."
    if product_label:
        return f"{product_label} 구매를 진행하려면 수량이 필요해요. 구매 수량을 알려주세요."
    return "구매를 진행하려면 수량이 필요해요. 구매 수량을 알려주세요."


def _purchase_fallback_quick_replies(flow_step: str) -> list[dict[str, str]]:
    if flow_step == "ask_store":
        return [
            {"label": "내 주변 매장 찾기", "domain": "TRANSACTION"},
            {"label": "지역/매장 입력", "domain": "TRANSACTION"},
            {"label": "단골매장 보기", "domain": "TRANSACTION"},
        ]
    if flow_step == "ask_quantity":
        return [
            {"label": "2개", "domain": "TRANSACTION"},
            {"label": "4개", "domain": "TRANSACTION"},
            {"label": "수량 직접 입력", "domain": "TRANSACTION"},
        ]
    return []
