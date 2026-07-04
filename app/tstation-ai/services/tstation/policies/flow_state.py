from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Mapping

from schemas.tstation.slots import is_invalid_product_identity_value
from services.tstation.policies.price_basis_policy import has_price_basis


_EMPTY_VALUES = (None, "", [], {})

_PRODUCT_FIELDS = ("goods_no", "product_name", "tire_model", "pending_product_name", "tire_size", "ord_qty")
_PRODUCT_RESOLUTION_FIELDS = ("goods_no", "product_name", "tire_model", "pending_product_name", "tire_size")
_VEHICLE_FIELDS = (
    "selection_required",
    "named_registered_vehicle_anchor",
    "requested_vehicle_name",
    "car_model",
    "car_nm",
    "car_name",
    "car_no",
    "car_lnc_cd",
    "mbr_car_reg_seq",
    "tire_size",
    "tire_size_front",
    "tire_size_rear",
    "vehicle_type",
    "car_type",
)
_RECOMMENDATION_FIELDS = (
    "scenario",
    "recommendation_scenario",
    "rcmd_type",
    "season_nm",
    "brand_cd",
    "allow_cross_brand_fill",
    "min_price",
    "max_price",
    "tool_args_patch",
    "expected_tool_args",
    "source_text",
    "scope",
    "fitment_source",
)
_STORE_FIELDS = ("region", "shop_id", "shop_name", "store_name", "place_query")
_SCHEDULE_FIELDS = ("requested_cal_day", "rsv_hour")
_PAYMENT_FIELDS = (
    "payment_amount",
    "payment_amount_source",
    "price_basis",
    "price_source_tool",
    "payment_amount_stale",
    "sale_prc",
    "extra_fvr_sale_prc",
    "cheapest_final_prc",
    "final_unit_price",
    "final_prc",
    "final_price",
    "finalPrice",
    "price",
    "wage_prc",
)
_PAYMENT_UNIT_PRICE_FIELDS = (
    "cheapest_final_prc",
    "final_unit_price",
    "final_prc",
    "final_price",
    "finalPrice",
    "extra_fvr_sale_prc",
    "sale_prc",
    "price",
)
_DEPENDENCY_FIELD_BLOCKS: dict[str, frozenset[str]] = {
    "product_changed": frozenset({
        "goods_no",
        "shop_id",
        "shop_name",
        "store_name",
        "requested_cal_day",
        "rsv_hour",
        "payment_amount",
        "payment_amount_source",
        "price_basis",
        "price_source_tool",
        "payment_amount_stale",
        "sale_prc",
        "extra_fvr_sale_prc",
        "cheapest_final_prc",
        "final_unit_price",
        "final_prc",
        "final_price",
        "finalPrice",
        "price",
        "wage_prc",
    }),
    "tire_size_changed": frozenset({
        "goods_no",
        "shop_id",
        "shop_name",
        "store_name",
        "requested_cal_day",
        "rsv_hour",
        "payment_amount",
        "payment_amount_source",
        "price_basis",
        "price_source_tool",
        "payment_amount_stale",
        "sale_prc",
        "extra_fvr_sale_prc",
        "cheapest_final_prc",
        "final_unit_price",
        "final_prc",
        "final_price",
        "finalPrice",
        "price",
        "wage_prc",
    }),
    "quantity_changed": frozenset({
        "requested_cal_day",
        "rsv_hour",
        "payment_amount",
        "payment_amount_source",
        "price_basis",
        "price_source_tool",
        "payment_amount_stale",
        "sale_prc",
        "extra_fvr_sale_prc",
        "cheapest_final_prc",
        "final_unit_price",
        "final_prc",
        "final_price",
        "finalPrice",
        "price",
        "wage_prc",
    }),
    "store_changed": frozenset({
        "shop_id",
        "shop_name",
        "store_name",
        "requested_cal_day",
        "rsv_hour",
        "payment_amount",
        "payment_amount_source",
        "price_basis",
        "price_source_tool",
        "payment_amount_stale",
    }),
    "region_changed": frozenset({
        "shop_id",
        "shop_name",
        "store_name",
        "requested_cal_day",
        "rsv_hour",
        "payment_amount",
        "payment_amount_source",
        "price_basis",
        "price_source_tool",
        "payment_amount_stale",
    }),
    "schedule_changed": frozenset({
        "payment_amount",
        "payment_amount_source",
        "payment_amount_stale",
    }),
    "vehicle_changed": frozenset({
        "goods_no",
        "product_name",
        "tire_model",
        "pending_product_name",
        "tire_size",
        "shop_id",
        "shop_name",
        "store_name",
        "requested_cal_day",
        "rsv_hour",
        "payment_amount",
        "payment_amount_source",
        "price_basis",
        "price_source_tool",
        "payment_amount_stale",
        "sale_prc",
        "extra_fvr_sale_prc",
        "cheapest_final_prc",
        "final_unit_price",
        "final_prc",
        "final_price",
        "finalPrice",
        "price",
        "wage_prc",
    }),
    "product_size_no_result": frozenset({
        "goods_no",
        "tire_size",
        "shop_id",
        "shop_name",
        "store_name",
        "requested_cal_day",
        "rsv_hour",
        "payment_amount",
        "payment_amount_source",
        "price_basis",
        "price_source_tool",
        "payment_amount_stale",
        "sale_prc",
        "extra_fvr_sale_prc",
        "cheapest_final_prc",
        "final_unit_price",
        "final_prc",
        "final_price",
        "finalPrice",
        "price",
        "wage_prc",
    }),
}
_DEPENDENCY_EVENT_KEYS = (
    "flow_state_dependency_event",
    "flow_state_dependency_events",
)
_INTENT_FIELDS = (
    "sub_flow_type",
    "pending_intent",
    "goal_type",
    "stock_check_mode",
    "schedule_mode",
    "availability_intent",
    "store_search_condition",
    "requested_vehicle_experience",
    "support_topic",
    "faq_topic",
    "policy_topic",
    "service_action_boundary",
    "service_name",
    "service_type",
    "reservation_management_action",
    "owned_record_target",
)
_FLOW_PROGRESS_META_FIELDS = (
    "target_action",
    "current_step",
    "missing_slots",
    "next_tool",
    "preferred_tool",
    "tool_args_patch",
    "allowed_tools",
    "next_template",
    "response_shape_key",
    "progress_source",
)
_ACTIVE_FLOW_TYPES = {
    "commerce",
    "purchase",
    "recommendation",
    "stock",
    "booking",
    "store_search",
    "store_schedule",
    "store_service_search",
    "favorite_store",
    "support",
    "service_maintenance",
    "reservation_management",
}
_CANONICAL_FLOW_TYPES = {"commerce", "support", "reservation_management"}
_COMMERCE_SUB_FLOW_TYPES = {
    "purchase",
    "recommendation",
    "stock",
    "booking",
    "store_search",
    "store_schedule",
    "store_service_search",
    "favorite_store",
    "service_maintenance",
}
_COMMERCE_PURCHASE_LIKE_FLOW_TYPES = {"purchase", "stock", "booking"}
_COMMERCE_STORE_LIKE_FLOW_TYPES = {"store_search", "store_schedule", "store_service_search", "favorite_store"}
_STORE_CANDIDATE_SOURCE_TOOLS = {
    "transaction_store_preview_tool",
    "get_store_list_tool",
    "search_stores_tool",
    "get_nearby_stores_tool",
    "search_stores_complex_tool",
    "get_favorite_stores_tool",
}
_STORE_SCHEDULE_RESPONSE_SHAPES = {
    "reservation_store_candidates",
    "reservation_store_info_lookup",
    "selected_store_schedule",
    "store_schedule",
    "store_visit_schedule",
    "unverified_store_schedule_lookup",
}
_STORE_SERVICE_RESPONSE_SHAPES = {
    "open_store_filter",
    "open_store_search",
    "store_service_search",
}
_STOCK_STORE_RESPONSE_SHAPES = {
    "stock_inventory_lookup",
    "stock_store_candidates",
}
_STOCK_STORE_INTENTS = {
    "fill_quantity_slot",
    "stock_store_search",
    "store_inventory_check",
}
_FLOW_EVENT_TYPES = {
    "activate",
    "deactivate",
    "resume",
    "ambiguous_resume",
    "prune",
    "upsert_dormant",
}
_DEFAULT_MAX_DORMANT_FLOWS = 5
_DEFAULT_DORMANT_TTL_SECONDS = 60 * 60 * 24
_STORE_SELECTION_CHIPS = {"이 매장 선택", "이 매장으로", "이곳 선택"}
_SELECTION_ORDINALS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("첫번째", "첫째", "첫 번", "첫번", "1번째", "1번", "1.", "1)"), 0),
    (("두번째", "둘째", "두 번", "두번", "2번째", "2번", "2.", "2)"), 1),
    (("세번째", "셋째", "세 번", "세번", "3번째", "3번", "3.", "3)"), 2),
    (("네번째", "넷째", "네 번", "네번", "4번째", "4번", "4.", "4)"), 3),
    (("다섯번째", "다섯째", "5번째", "5번", "5.", "5)"), 4),
)


def _non_empty_mapping(values: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(values, Mapping):
        return {}
    return {key: value for key, value in dict(values or {}).items() if value not in _EMPTY_VALUES}


def _has_active_flow_context_shape(values: Mapping[str, Any]) -> bool:
    if any(values.get(key) not in _EMPTY_VALUES for key in ("flow_type", "flow_step", "current_step", "target_action")):
        return True
    if any(isinstance(values.get(key), Mapping) and values.get(key) for key in (
        "product",
        "vehicle",
        "recommendation",
        "store",
        "schedule",
        "payment",
        "intent",
    )):
        return True
    if values.get("dormant_flows") or values.get("flow_events"):
        return True
    return str(values.get("status") or "").strip() in {"dormant", "resumed", "completed"}


def canonical_flow_type(flow_type: Any) -> str:
    value = str(flow_type or "").strip()
    if value in _COMMERCE_SUB_FLOW_TYPES:
        return "commerce"
    if value in {"support", "reservation_management"}:
        return value
    if value == "commerce":
        return "commerce"
    return ""


def commerce_sub_flow_type(flow_type: Any, intent: Mapping[str, Any] | None = None) -> str:
    values = _non_empty_mapping(intent)
    sub_flow_type = str(values.get("sub_flow_type") or "").strip()
    if sub_flow_type in _COMMERCE_SUB_FLOW_TYPES:
        return sub_flow_type
    value = str(flow_type or "").strip()
    return value if value in _COMMERCE_SUB_FLOW_TYPES else ""


def effective_flow_type(flow_type: Any, intent: Mapping[str, Any] | None = None) -> str:
    canonical = canonical_flow_type(flow_type)
    if canonical == "commerce":
        return commerce_sub_flow_type(flow_type, intent) or "purchase"
    return canonical


def flow_type_matches_allowed(
    flow_type: Any,
    allowed_flow_types: set[str] | frozenset[str] | None,
    intent: Mapping[str, Any] | None = None,
) -> bool:
    if allowed_flow_types is None:
        return True
    allowed = {str(value or "").strip() for value in allowed_flow_types if str(value or "").strip()}
    canonical = canonical_flow_type(flow_type)
    effective = effective_flow_type(flow_type, intent)
    if canonical in allowed or effective in allowed:
        return True
    return bool(canonical == "commerce" and allowed.intersection(_COMMERCE_SUB_FLOW_TYPES))


def _normalize_flow_type_and_intent(flow_type: Any, intent: Mapping[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    values = _non_empty_mapping(intent)
    raw_flow_type = str(flow_type or "").strip()
    canonical = canonical_flow_type(raw_flow_type) or "commerce"
    if canonical == "commerce":
        sub_flow_type = commerce_sub_flow_type(raw_flow_type, values) or "purchase"
        values["sub_flow_type"] = sub_flow_type
    else:
        values.pop("sub_flow_type", None)
    return canonical, values


def _sanitize_product_identity_values(values: dict[str, Any]) -> None:
    for field_name in ("product_name", "tire_model", "pending_product_name"):
        if is_invalid_product_identity_value(values.get(field_name)):
            values.pop(field_name, None)


def _normalize_product_aliases(values: dict[str, Any]) -> None:
    _sanitize_product_identity_values(values)
    product_name = values.get("product_name") or values.get("tire_model") or values.get("pending_product_name")
    if product_name in _EMPTY_VALUES:
        return
    values.setdefault("product_name", product_name)
    values.setdefault("tire_model", product_name)
    values.setdefault("pending_product_name", product_name)


def _normalized_product_identity(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[\s\-_/()]+", "", text)


def _product_identity(values: Mapping[str, Any]) -> str:
    return str(
        _first_non_empty(values.get("product_name"), values.get("tire_model"), values.get("pending_product_name"))
        or ""
    ).strip()


def _product_identity_changed(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> bool:
    if incoming.get("goods_no") not in _EMPTY_VALUES:
        return False
    existing_identity = _normalized_product_identity(_product_identity(existing))
    incoming_identity = _normalized_product_identity(_product_identity(incoming))
    return bool(existing.get("goods_no") and existing_identity and incoming_identity and existing_identity != incoming_identity)


def _normalized_scalar(value: Any) -> str:
    return str(value or "").strip()


def _field_changed(existing: Mapping[str, Any], incoming: Mapping[str, Any], field_name: str) -> bool:
    if incoming.get(field_name) in _EMPTY_VALUES:
        return False
    existing_value = _normalized_scalar(existing.get(field_name))
    incoming_value = _normalized_scalar(incoming.get(field_name))
    return bool(existing_value and incoming_value and existing_value != incoming_value)


def _product_resolution_change(
    existing: Mapping[str, Any],
    incoming: Mapping[str, Any],
) -> tuple[str, dict[str, Any], bool] | None:
    existing_goods_no = str(existing.get("goods_no") or "").strip()
    incoming_goods_no = str(incoming.get("goods_no") or "").strip()
    if existing_goods_no and incoming_goods_no and existing_goods_no != incoming_goods_no:
        return "goods_no", {"existing": existing_goods_no, "incoming": incoming_goods_no}, False
    if _product_identity_changed(existing, incoming):
        return (
            "product_identity",
            {
                "existing": _product_identity(existing),
                "incoming": _product_identity(incoming),
                "existing_goods_no": existing_goods_no,
            },
            True,
        )
    return None


def _tire_size_changed(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> bool:
    if incoming.get("tire_size") in _EMPTY_VALUES:
        return False
    existing_size = _normalize_vehicle_tire_size(existing.get("tire_size"))
    incoming_size = _normalize_vehicle_tire_size(incoming.get("tire_size"))
    return bool(existing_size and incoming_size and existing_size != incoming_size)


def _vehicle_identity(values: Mapping[str, Any]) -> tuple[str, str] | None:
    for field_name in ("mbr_car_reg_seq", "car_no", "car_lnc_cd", "requested_vehicle_name", "named_registered_vehicle_anchor"):
        value = _normalized_scalar(values.get(field_name))
        if value:
            return field_name, value
    return None


def _vehicle_changed(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> tuple[dict[str, Any], bool] | None:
    existing_identity = _vehicle_identity(existing)
    incoming_identity = _vehicle_identity(incoming)
    if not existing_identity or not incoming_identity:
        return None
    existing_field, existing_value = existing_identity
    incoming_field, incoming_value = incoming_identity
    if existing_field == incoming_field and existing_value == incoming_value:
        return None
    return (
        {
            "existing": existing_value,
            "incoming": incoming_value,
            "existing_field": existing_field,
            "incoming_field": incoming_field,
        },
        existing_value != incoming_value,
    )


def _schedule_changed(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> bool:
    return _field_changed(existing, incoming, "requested_cal_day") or _field_changed(existing, incoming, "rsv_hour")


def _clear_product_dependent_context(
    state: "FlowState",
    cleared_fields: list[str],
    *,
    clear_goods_no: bool,
    clear_product_resolution: bool = False,
) -> None:
    product_fields = _PRODUCT_RESOLUTION_FIELDS if clear_product_resolution else ("goods_no",)
    if clear_goods_no:
        for field_name in product_fields:
            if state.product.pop(field_name, None) not in _EMPTY_VALUES:
                cleared_fields.append(field_name)
    cleared_fields.extend(_clear_section(state.store))
    cleared_fields.extend(_clear_section(state.schedule))
    cleared_fields.extend(_clear_section(state.payment))
    if state.candidates:
        state.candidates = []
        cleared_fields.append("last_candidates")


def _clear_recommendation_context(state: "FlowState", cleared_fields: list[str]) -> None:
    cleared_fields.extend(_clear_section(state.recommendation))


def _clear_payment_context(state: "FlowState", cleared_fields: list[str]) -> None:
    cleared_fields.extend(_clear_section(state.payment))


def _cleared_context_fields(state: "FlowState") -> list[str]:
    cleared: list[str] = []
    for section_name in ("product", "vehicle", "recommendation", "store", "schedule", "payment", "intent", "meta"):
        section = getattr(state, section_name)
        cleared.extend(f"{section_name}.{key}" for key, value in section.items() if value not in _EMPTY_VALUES)
    if state.candidates:
        cleared.append("last_candidates")
    return cleared


def _normalize_vehicle_tire_size(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    match = re.search(r"(\d{3})\s*/?\s*(\d{2})\s*R?\s*(\d{2})", text)
    if not match:
        return text
    return f"{match.group(1)}/{match.group(2)}R{match.group(3)}"


def _is_purchase_intent_group(values: Mapping[str, Any]) -> bool:
    return (
        str(values.get("pending_intent") or "").strip() == "order"
        or str(values.get("goal_type") or "").strip() == "place_order"
    )


def _is_stock_intent_group(values: Mapping[str, Any]) -> bool:
    return (
        str(values.get("pending_intent") or "").strip() == "stock"
        or str(values.get("goal_type") or "").strip() == "store_with_stock"
    )


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in _EMPTY_VALUES:
            return value
    return None


def flow_state_dependency_events(context: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    values = _non_empty_mapping(context)
    events: list[dict[str, Any]] = []
    for key in _DEPENDENCY_EVENT_KEYS:
        raw = values.get(key)
        if isinstance(raw, Mapping):
            event = _non_empty_mapping(raw)
            if event:
                events.append(event)
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, Mapping):
                    event = _non_empty_mapping(item)
                    if event:
                        events.append(event)
    return events


def flow_state_dependency_blocked_fields(context: Mapping[str, Any] | None) -> set[str]:
    blocked: set[str] = set()
    for event in flow_state_dependency_events(context):
        event_name = str(event.get("event") or event.get("type") or "").strip()
        blocked.update(_DEPENDENCY_FIELD_BLOCKS.get(event_name, frozenset()))
        for field_name in event.get("blocked_fields") or ():
            field = str(field_name or "").strip()
            if field:
                blocked.add(field)
    return blocked


def _flow_quantity(value: Any) -> int | None:
    try:
        quantity = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return quantity if quantity > 0 else None


def _store_lookup_tool_and_args(store: Mapping[str, Any]) -> tuple[str | None, dict[str, Any]]:
    place_query = str(store.get("place_query") or "").strip()
    region = str(store.get("region") or "").strip()
    store_name = str(store.get("shop_name") or store.get("store_name") or "").strip()
    if place_query:
        return "search_stores_tool", {"limit": 10, "place_query": place_query}
    if store_name:
        return "get_store_list_tool", {"limit": 10, "store_nm": store_name}
    if region:
        return "get_store_list_tool", {"limit": 10, "region_code": region}
    return None, {}


def flow_identity_for_context(context: Mapping[str, Any] | None) -> str:
    values = _non_empty_mapping(context)
    flow_type = canonical_flow_type(values.get("flow_type"))
    if flow_type not in _CANONICAL_FLOW_TYPES:
        return ""

    product = _section_values(values, "product", _PRODUCT_FIELDS)
    _normalize_product_aliases(product)
    vehicle = _section_values(values, "vehicle", _VEHICLE_FIELDS)
    recommendation = _section_values(values, "recommendation", _RECOMMENDATION_FIELDS)
    store = _section_values(values, "store", _STORE_FIELDS)
    intent = _section_values(values, "intent", _INTENT_FIELDS)
    sub_flow_type = commerce_sub_flow_type(values.get("flow_type"), intent)

    if flow_type == "commerce" and sub_flow_type in _COMMERCE_PURCHASE_LIKE_FLOW_TYPES:
        product_key = str(product.get("goods_no") or _product_identity(product) or "").strip()
        tire_size = _normalize_vehicle_tire_size(product.get("tire_size"))
        if not product_key and not tire_size:
            return ""
        parts = [flow_type, sub_flow_type, product_key, tire_size]
    elif flow_type == "commerce" and sub_flow_type in _COMMERCE_STORE_LIKE_FLOW_TYPES:
        store_key = str(
            _first_non_empty(store.get("shop_id"), store.get("shop_name"), store.get("store_name"), store.get("region"), store.get("place_query"))
            or ""
        ).strip()
        parts = [flow_type, sub_flow_type, store_key]
    elif flow_type == "commerce" and sub_flow_type == "recommendation":
        vehicle_identity = _vehicle_identity(vehicle)
        vehicle_key = vehicle_identity[1] if vehicle_identity else ""
        scenario = str(
            _first_non_empty(
                recommendation.get("recommendation_scenario"),
                recommendation.get("scenario"),
                recommendation.get("rcmd_type"),
                intent.get("goal_type"),
            )
            or ""
        ).strip()
        tire_size = _normalize_vehicle_tire_size(product.get("tire_size") or vehicle.get("tire_size"))
        parts = [flow_type, sub_flow_type, scenario, vehicle_key, tire_size]
    elif flow_type == "support":
        policy_key = str(
            _first_non_empty(intent.get("pending_intent"), intent.get("policy_topic"), intent.get("faq_topic"), intent.get("goal_type"))
            or ""
        ).strip()
        parts = [flow_type, policy_key]
    elif flow_type == "commerce" and sub_flow_type == "service_maintenance":
        service_key = str(
            _first_non_empty(intent.get("service_name"), intent.get("service_type"), intent.get("pending_intent"))
            or ""
        ).strip()
        boundary = str(_first_non_empty(intent.get("service_action_boundary"), intent.get("goal_type")) or "").strip()
        store_key = str(
            _first_non_empty(store.get("shop_id"), store.get("shop_name"), store.get("store_name"), store.get("region"))
            or ""
        ).strip()
        parts = [flow_type, sub_flow_type, boundary, service_key, store_key]
    elif flow_type == "reservation_management":
        action = str(_first_non_empty(intent.get("reservation_management_action"), intent.get("pending_intent")) or "").strip()
        target = str(_first_non_empty(intent.get("owned_record_target"), intent.get("goal_type")) or "").strip()
        parts = [flow_type, action, target]
    else:
        parts = [flow_type]

    normalized = [_normalized_product_identity(part) for part in parts if str(part or "").strip()]
    if len(normalized) <= 1:
        return flow_type
    return ":".join(normalized)


def _flow_updated_at(context: Mapping[str, Any]) -> str:
    updated_at = str(context.get("updated_at") or "").strip()
    return updated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _flow_context_without_history(context: Mapping[str, Any] | None) -> dict[str, Any]:
    values = _non_empty_mapping(context)
    values.pop("dormant_flows", None)
    values.pop("flow_events", None)
    return values


def _parse_flow_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _dormant_flow_values(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    dormant_flows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        dormant = DormantFlow.from_mapping(item)
        if dormant is None:
            continue
        dormant_flows.append(dormant.to_dict())
    return dormant_flows


def _flow_event_values(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    events: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        event = FlowEvent.from_mapping(item)
        if event is not None:
            events.append(event.to_dict())
    return events


def _new_flow_event(
    event_type: str,
    *,
    source: str,
    flow_identity: str = "",
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return FlowEvent(
        event_type=event_type,
        source=source,
        flow_identity=flow_identity,
        details=_non_empty_mapping(details),
    ).to_dict()


def upsert_dormant_flow(
    dormant_flows: list[Mapping[str, Any]] | None,
    flow_context: Mapping[str, Any] | None,
    *,
    max_flows: int = _DEFAULT_MAX_DORMANT_FLOWS,
    ttl_seconds: int = _DEFAULT_DORMANT_TTL_SECONDS,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    context = _non_empty_mapping(flow_context)
    if not context:
        return prune_dormant_flows(dormant_flows, max_flows=max_flows, ttl_seconds=ttl_seconds, now=now)
    context = FlowState.from_active_flow_context(context).to_active_flow_context()
    context["status"] = "dormant"
    context["updated_at"] = _flow_updated_at(context)
    identity = flow_identity_for_context(context)
    if not identity:
        return prune_dormant_flows(dormant_flows, max_flows=max_flows, ttl_seconds=ttl_seconds, now=now)

    existing = _dormant_flow_values(list(dormant_flows or []))
    upserted = DormantFlow(flow_identity=identity, context=context, updated_at=context["updated_at"]).to_dict()
    replaced = False
    merged: list[dict[str, Any]] = []
    for dormant in existing:
        if str(dormant.get("flow_identity") or "") == identity:
            merged.append(upserted)
            replaced = True
        else:
            merged.append(dormant)
    if not replaced:
        merged.append(upserted)
    return prune_dormant_flows(merged, max_flows=max_flows, ttl_seconds=ttl_seconds, now=now)


def prune_dormant_flows(
    dormant_flows: list[Mapping[str, Any]] | None,
    *,
    max_flows: int = _DEFAULT_MAX_DORMANT_FLOWS,
    ttl_seconds: int = _DEFAULT_DORMANT_TTL_SECONDS,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    current_time = now or datetime.now(timezone.utc)
    max_count = max(0, int(max_flows))
    ttl = max(0, int(ttl_seconds))
    kept: list[dict[str, Any]] = []
    for dormant in _dormant_flow_values(list(dormant_flows or [])):
        updated_at = _parse_flow_time(dormant.get("updated_at"))
        if ttl and updated_at and (current_time - updated_at).total_seconds() > ttl:
            continue
        kept.append(dormant)
    kept.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return kept[:max_count] if max_count else []


def resume_dormant_flow(
    active_flow_context: Mapping[str, Any] | None,
    dormant_flows: list[Mapping[str, Any]] | None,
    *,
    resume_anchor: Mapping[str, Any] | None,
    source: str,
) -> DormantFlowResumeResult:
    anchor = _non_empty_mapping(resume_anchor)
    if not anchor:
        return DormantFlowResumeResult(status="not_found", dormant_flows=_dormant_flow_values(list(dormant_flows or [])))
    target_identity = flow_identity_for_context(anchor)
    target_flow_type = str(anchor.get("flow_type") or "").strip()
    normalized_product = _normalized_product_identity(
        _first_non_empty(anchor.get("goods_no"), anchor.get("product_name"), anchor.get("tire_model"), anchor.get("pending_product_name"))
    )
    normalized_store = _normalized_product_identity(
        _first_non_empty(anchor.get("shop_id"), anchor.get("shop_name"), anchor.get("store_name"), anchor.get("region"), anchor.get("place_query"))
    )

    matches: list[dict[str, Any]] = []
    for dormant in _dormant_flow_values(list(dormant_flows or [])):
        context = _non_empty_mapping(dormant.get("context"))
        if target_identity and target_identity != target_flow_type and dormant.get("flow_identity") == target_identity:
            matches.append(dormant)
            continue
        context_intent = context.get("intent") if isinstance(context.get("intent"), Mapping) else {}
        if target_flow_type and not flow_type_matches_allowed(
            context.get("flow_type"),
            frozenset({target_flow_type}),
            context_intent,
        ):
            continue
        if target_flow_type and not normalized_product and not normalized_store:
            matches.append(dormant)
            continue
        if normalized_product:
            product = _section_values(context, "product", _PRODUCT_FIELDS)
            candidate_product = _normalized_product_identity(
                _first_non_empty(product.get("goods_no"), product.get("product_name"), product.get("tire_model"), product.get("pending_product_name"))
            )
            if candidate_product == normalized_product:
                matches.append(dormant)
                continue
        if normalized_store:
            store = _section_values(context, "store", _STORE_FIELDS)
            candidate_store = _normalized_product_identity(
                _first_non_empty(store.get("shop_id"), store.get("shop_name"), store.get("store_name"), store.get("region"), store.get("place_query"))
            )
            if candidate_store == normalized_store:
                matches.append(dormant)

    if not matches:
        return DormantFlowResumeResult(status="not_found", dormant_flows=_dormant_flow_values(list(dormant_flows or [])))
    if len(matches) > 1:
        return DormantFlowResumeResult(
            status="ambiguous",
            dormant_flows=_dormant_flow_values(list(dormant_flows or [])),
            candidates=matches,
            metadata={"flow_event": _new_flow_event("ambiguous_resume", source=source, details={"candidate_count": len(matches)})},
        )

    resumed = dict(matches[0])
    resumed_identity = str(resumed.get("flow_identity") or "").strip()
    resumed_context = _non_empty_mapping(resumed.get("context"))
    resumed_context["status"] = "resumed"
    resumed_context["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    remaining = [
        dormant
        for dormant in _dormant_flow_values(list(dormant_flows or []))
        if str(dormant.get("flow_identity") or "") != resumed_identity
    ]
    current_active = _non_empty_mapping(active_flow_context)
    if current_active:
        remaining = upsert_dormant_flow(remaining, current_active)
    remaining = prune_dormant_flows(remaining)
    event = _new_flow_event("resume", source=source, flow_identity=resumed_identity)
    resumed_context["dormant_flows"] = remaining
    resumed_context["flow_events"] = [event, *_flow_event_values(resumed_context.get("flow_events"))]
    return DormantFlowResumeResult(
        status="resumed",
        active_flow_context=resumed_context,
        dormant_flows=remaining,
        metadata={"flow_event": event, "resumed_flow_identity": resumed_identity},
    )


def evaluate_flow_progress(state: "FlowState") -> dict[str, Any]:
    """Compute the next missing slot/tool for an active flow without executing it."""

    if state.status not in {"active", "resumed"}:
        return {}
    product = _non_empty_mapping(state.product)
    store = _non_empty_mapping(state.store)
    payment = _non_empty_mapping(state.payment)
    intent = _non_empty_mapping(state.intent)
    flow_type = effective_flow_type(state.flow_type, intent)
    goods_no = str(product.get("goods_no") or "").strip()
    product_name = str(
        _first_non_empty(product.get("product_name"), product.get("tire_model"), product.get("pending_product_name"))
        or ""
    ).strip()
    tire_size = str(product.get("tire_size") or "").strip()
    quantity = _flow_quantity(_first_non_empty(product.get("ord_qty"), product.get("quantity")))
    shop_id = str(store.get("shop_id") or "").strip()
    shop_name = str(_first_non_empty(store.get("shop_name"), store.get("store_name")) or "").strip()
    requested_cal_day = str(state.schedule.get("requested_cal_day") or "").strip()
    rsv_hour = str(state.schedule.get("rsv_hour") or "").strip()
    lookup_tool, lookup_args = _store_lookup_tool_and_args(store)

    if flow_type == "stock":
        base = {
            "target_action": "get_store_inventory_tool",
            "progress_source": "flow_state_evaluator",
        }
        if not goods_no:
            if product_name:
                args = {"keyword": product_name, "limit": 10}
                if tire_size:
                    args["size"] = tire_size
                return {
                    **base,
                    "current_step": "resolve_product",
                    "missing_slots": ["goods_no"],
                    "next_tool": "search_product_tool",
                    "allowed_tools": ["search_product_tool"],
                    "tool_args_patch": args,
                }
            return {**base, "current_step": "ask_product", "missing_slots": ["product"]}
        if not quantity:
            return {**base, "current_step": "ask_quantity", "missing_slots": ["ord_qty"]}
        if not shop_id:
            if lookup_tool:
                return {
                    **base,
                    "current_step": "resolve_store",
                    "missing_slots": ["shop_id"],
                    "next_tool": lookup_tool,
                    "allowed_tools": ["search_stores_tool", "get_store_list_tool"],
                    "tool_args_patch": lookup_args,
                }
            return {**base, "current_step": "ask_store", "missing_slots": ["shop_id"]}
        return {
            **base,
            "current_step": "check_inventory",
            "missing_slots": [],
            "next_tool": "get_store_inventory_tool",
            "allowed_tools": ["get_store_inventory_tool"],
            "tool_args_patch": {
                "goods_list": [{"goodsNo": goods_no, "qty": str(quantity)}],
                "shop_id_list": [{"shopId": shop_id}],
            },
        }

    if flow_type == "purchase":
        base = {
            "target_action": "quick_order_tool",
            "progress_source": "flow_state_evaluator",
        }
        if not goods_no:
            if product_name:
                args = {"keyword": product_name, "limit": 10}
                if tire_size:
                    args["size"] = tire_size
                return {
                    **base,
                    "current_step": "resolve_product",
                    "missing_slots": ["goods_no"],
                    "next_tool": "search_product_tool",
                    "allowed_tools": ["search_product_tool"],
                    "tool_args_patch": args,
                }
            return {**base, "current_step": "ask_product", "missing_slots": ["product"]}
        if not quantity:
            return {**base, "current_step": "ask_quantity", "missing_slots": ["ord_qty"]}
        if not shop_id:
            if lookup_tool:
                return {
                    **base,
                    "current_step": "resolve_store",
                    "missing_slots": ["shop_id"],
                    "next_tool": lookup_tool,
                    "allowed_tools": ["search_stores_tool", "get_store_list_tool"],
                    "tool_args_patch": lookup_args,
                }
            return {**base, "current_step": "ask_store", "missing_slots": ["shop_id"]}
        if requested_cal_day and rsv_hour and not has_price_basis(payment):
            return {
                **base,
                "current_step": "resolve_price",
                "missing_slots": [],
                "next_tool": "get_final_price_tool",
                "allowed_tools": ["get_final_price_tool"],
                "tool_args_patch": {"goods_no": goods_no},
                "response_shape_key": "reservation_price_lookup",
            }
        if requested_cal_day and rsv_hour:
            return {
                **base,
                "current_step": "build_preorder",
                "missing_slots": [],
                "next_template": "preOrder",
                "response_shape_key": "reservation_confirmation_ready",
            }
        schedule_mode = str(intent.get("schedule_mode") or "general").strip()
        return {
            **base,
            "current_step": "resolve_schedule",
            "missing_slots": ["booking_datetime"],
            "next_tool": "get_store_schedule_tool",
            "allowed_tools": ["get_store_schedule_tool"],
            "tool_args_patch": {"shop_id": shop_id, "mode": schedule_mode},
        }

    if flow_type == "store_schedule":
        base = {
            "target_action": "get_store_schedule_tool",
            "progress_source": "flow_state_evaluator",
        }
        if not shop_id:
            if lookup_tool:
                return {
                    **base,
                    "current_step": "resolve_store",
                    "missing_slots": ["shop_id"],
                    "next_tool": lookup_tool,
                    "allowed_tools": ["search_stores_tool", "get_store_list_tool"],
                    "tool_args_patch": lookup_args,
                }
            return {**base, "current_step": "ask_store", "missing_slots": ["shop_id"]}
        return {
            **base,
            "current_step": "show_schedule",
            "missing_slots": [],
            "next_tool": "get_store_schedule_tool",
            "allowed_tools": ["get_store_schedule_tool"],
            "tool_args_patch": {"shop_id": shop_id, "mode": "general"},
        }

    if shop_name and flow_type in {"store_search", "store_service_search", "favorite_store"}:
        return {
            "target_action": "store_lookup",
            "current_step": "resolve_store",
            "missing_slots": ["shop_id"],
            "next_tool": "get_store_list_tool",
            "allowed_tools": ["get_store_list_tool"],
            "tool_args_patch": {"limit": 10, "store_nm": shop_name},
            "progress_source": "flow_state_evaluator",
        }
    return {}


def _refresh_flow_progress(state: "FlowState") -> None:
    progress = evaluate_flow_progress(state)
    if not progress:
        return
    for key in _FLOW_PROGRESS_META_FIELDS:
        state.meta.pop(key, None)
    state.meta.update(progress)


def flow_progress_from_active_context(
    active_flow_context: Mapping[str, Any] | None,
    *,
    allowed_flow_types: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    state = FlowState.from_active_flow_context(active_flow_context)
    if state.status not in {"active", "resumed"}:
        return {}
    if not flow_type_matches_allowed(state.flow_type, allowed_flow_types, state.intent):
        return {}
    context = state.to_active_flow_context()
    progress = {
        key: context[key]
        for key in _FLOW_PROGRESS_META_FIELDS
        if context.get(key) not in _EMPTY_VALUES
    }
    if not progress:
        progress = evaluate_flow_progress(state)
    if not progress:
        return {}
    progress["flow_type"] = state.flow_type
    progress["sub_flow_type"] = effective_flow_type(state.flow_type, state.intent)
    progress["flow_step"] = state.flow_step
    return progress


def flow_progress_tool_candidate(
    progress: Mapping[str, Any] | None,
    *,
    domain: str,
    contract_intent: str,
    response_shape_key: str,
    allowed_tools: tuple[str, ...],
    forbidden_tools: set[str],
) -> dict[str, Any]:
    """Return a safe tool candidate from stored flow progress without executing it."""

    if not isinstance(progress, Mapping) or not progress:
        return {}
    normalized_domain = str(domain or "").strip().lower()
    flow_type = effective_flow_type(progress.get("flow_type"), {"sub_flow_type": progress.get("sub_flow_type")})
    current_step = str(progress.get("current_step") or "").strip()
    next_tool = str(progress.get("next_tool") or "").strip()
    intent = str(contract_intent or "").strip()
    shape = str(response_shape_key or "").strip()

    if (
        normalized_domain == "discovery"
        and flow_type in {"stock", "purchase"}
        and current_step == "resolve_product"
        and next_tool == "search_product_tool"
    ):
        if intent not in {"product_search", "resolve_or_describe_product"} and shape not in {
            "product_search_summary",
            "missing_stock_search_slots",
            "missing_order_slots",
        }:
            return {}
        display_name = "상품 검색 중..."
    elif normalized_domain == "transaction":
        if flow_type == "stock":
            intent_aligned = (
                intent in {"stock_store_search", "stock_store_search_slot_fill_store", "fill_quantity_slot"}
                or shape == "stock_inventory_lookup"
            )
        elif flow_type == "store_schedule":
            intent_aligned = intent in {"store_schedule", "selected_store_schedule"} or shape in {
                "reservation_slots",
                "unverified_store_schedule_lookup",
            }
        else:
            intent_aligned = intent in {
                "quick_order_reservation",
                "quick_order_reservation_continue",
                "store_schedule",
                "selected_store_schedule",
            }
        if not intent_aligned:
            return {}
        if next_tool not in {
            "search_stores_tool",
            "get_store_list_tool",
            "get_store_schedule_tool",
            "get_store_inventory_tool",
            "get_final_price_tool",
        }:
            return {}
        display_name = {
            "search_stores_tool": "매장 정보 확인 중...",
            "get_store_list_tool": "매장 정보 확인 중...",
            "get_store_schedule_tool": "예약 가능 일정 확인 중...",
            "get_store_inventory_tool": "매장 재고 확인 중...",
        }.get(next_tool, "정보 확인 중...")
    else:
        return {}

    if not next_tool or next_tool not in allowed_tools or next_tool in forbidden_tools:
        return {}
    tool_input = {
        str(key): value
        for key, value in dict(progress.get("tool_args_patch") or {}).items()
        if value not in _EMPTY_VALUES
    }
    if not tool_input:
        return {}
    if next_tool == "search_product_tool" and not tool_input.get("keyword"):
        return {}
    return {
        "tool_name": next_tool,
        "tool_input": tool_input,
        "tool_input_source": "flow_state_progress",
        "display_name": display_name,
        "source_domain": normalized_domain,
    }


@dataclass(slots=True)
class FlowStateMergeResult:
    state: "FlowState"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FlowEvent:
    event_type: str
    source: str
    flow_identity: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        event_type = self.event_type if self.event_type in _FLOW_EVENT_TYPES else "activate"
        return _non_empty_mapping({
            "event_type": event_type,
            "source": self.source,
            "flow_identity": self.flow_identity,
            "details": _non_empty_mapping(self.details),
            "created_at": self.created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "FlowEvent | None":
        event = _non_empty_mapping(values)
        event_type = str(event.get("event_type") or "").strip()
        if event_type not in _FLOW_EVENT_TYPES:
            return None
        return cls(
            event_type=event_type,
            source=str(event.get("source") or "").strip(),
            flow_identity=str(event.get("flow_identity") or "").strip(),
            details=_non_empty_mapping(event.get("details")),
            created_at=str(event.get("created_at") or "").strip(),
        )


@dataclass(slots=True)
class DormantFlow:
    flow_identity: str
    context: dict[str, Any]
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        context = _non_empty_mapping(self.context)
        flow_identity = self.flow_identity or flow_identity_for_context(context)
        updated_at = self.updated_at or str(context.get("updated_at") or "")
        return _non_empty_mapping({
            "flow_identity": flow_identity,
            "updated_at": updated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "context": context,
        })

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "DormantFlow | None":
        data = _non_empty_mapping(values)
        if not data:
            return None
        raw_context = data.get("context") if isinstance(data.get("context"), Mapping) else data
        context = _non_empty_mapping(raw_context)
        if not context:
            return None
        if canonical_flow_type(context.get("flow_type")) not in _CANONICAL_FLOW_TYPES:
            return None
        context = FlowState.from_active_flow_context(context).to_active_flow_context()
        context["status"] = "dormant"
        identity = str(data.get("flow_identity") or flow_identity_for_context(context)).strip()
        if not identity:
            return None
        updated_at = str(data.get("updated_at") or context.get("updated_at") or "").strip()
        return cls(flow_identity=identity, context=context, updated_at=updated_at)


@dataclass(slots=True)
class DormantFlowResumeResult:
    status: str
    active_flow_context: dict[str, Any] = field(default_factory=dict)
    dormant_flows: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FlowState:
    flow_type: str
    status: str = "active"
    flow_step: str | None = None
    product: dict[str, Any] = field(default_factory=dict)
    vehicle: dict[str, Any] = field(default_factory=dict)
    recommendation: dict[str, Any] = field(default_factory=dict)
    store: dict[str, Any] = field(default_factory=dict)
    schedule: dict[str, Any] = field(default_factory=dict)
    payment: dict[str, Any] = field(default_factory=dict)
    intent: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    dormant_flows: list[dict[str, Any]] = field(default_factory=list)
    flow_events: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def purchase(cls, status: str = "active") -> "FlowState":
        state = cls(flow_type="commerce", status=status)
        state.intent["sub_flow_type"] = "purchase"
        return state

    @classmethod
    def from_active_flow_context(cls, context: Mapping[str, Any] | None) -> "FlowState":
        flat = _non_empty_mapping(context)
        if flat and not _has_active_flow_context_shape(flat):
            flat = {}
        flow_type, normalized_intent = _normalize_flow_type_and_intent(flat.get("flow_type"))
        state = cls(
            flow_type=flow_type,
            status=str(flat.get("status") or "active"),
            flow_step=str(flat.get("flow_step") or "") or None,
        )
        state.product = _section_values(flat, "product", _PRODUCT_FIELDS)
        _normalize_product_aliases(state.product)
        state.vehicle = _section_values(flat, "vehicle", _VEHICLE_FIELDS)
        state.recommendation = _section_values(flat, "recommendation", _RECOMMENDATION_FIELDS)
        state.store = _section_values(flat, "store", _STORE_FIELDS)
        state.schedule = _section_values(flat, "schedule", _SCHEDULE_FIELDS)
        state.payment = _section_values(flat, "payment", _PAYMENT_FIELDS)
        state.intent = _section_values(flat, "intent", _INTENT_FIELDS)
        state.intent = {**normalized_intent, **state.intent}
        state.flow_type, state.intent = _normalize_flow_type_and_intent(state.flow_type, state.intent)
        state.meta = {
            key: flat[key]
            for key in ("source", "updated_at", "awaiting_store_region", "pending_step", *_FLOW_PROGRESS_META_FIELDS)
            if flat.get(key) not in _EMPTY_VALUES
        }
        state.candidates = _candidate_values(flat.get("last_candidates"))
        state.dormant_flows = _dormant_flow_values(flat.get("dormant_flows"))
        state.flow_events = _flow_event_values(flat.get("flow_events"))
        return state

    @classmethod
    def from_pending_order_context(cls, context: Mapping[str, Any] | None) -> "FlowState":
        flat = _non_empty_mapping(context)
        state = cls.purchase(status=str(flat.get("context_state") or flat.get("status") or "active"))
        state.flow_step = str(flat.get("flow_step") or flat.get("pending_step") or "") or None
        state.product = {key: flat[key] for key in _PRODUCT_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        _normalize_product_aliases(state.product)
        state.vehicle = {key: flat[key] for key in _VEHICLE_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.store = {key: flat[key] for key in _STORE_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.schedule = {key: flat[key] for key in _SCHEDULE_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.payment = {key: flat[key] for key in _PAYMENT_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.intent = {key: flat[key] for key in _INTENT_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.meta = {
            key: flat[key]
            for key in ("source", "updated_at", "awaiting_store_region", "pending_step", *_FLOW_PROGRESS_META_FIELDS)
            if flat.get(key) not in _EMPTY_VALUES
        }
        state.dormant_flows = _dormant_flow_values(flat.get("dormant_flows"))
        state.flow_events = _flow_event_values(flat.get("flow_events"))
        return state

    @classmethod
    def from_flat_delta(
        cls,
        values: Mapping[str, Any] | None,
        *,
        source: str,
        flow_type: str = "purchase",
        flow_step: str | None = None,
    ) -> "FlowState":
        flat = _non_empty_mapping(values)
        normalized_flow_type, normalized_intent = _normalize_flow_type_and_intent(flow_type)
        state = cls(flow_type=normalized_flow_type, flow_step=flow_step)
        state.product = _section_values(flat, "product", _PRODUCT_FIELDS)
        _normalize_product_aliases(state.product)
        state.vehicle = _section_values(flat, "vehicle", _VEHICLE_FIELDS)
        state.recommendation = _section_values(flat, "recommendation", _RECOMMENDATION_FIELDS)
        state.store = _section_values(flat, "store", _STORE_FIELDS)
        state.schedule = _section_values(flat, "schedule", _SCHEDULE_FIELDS)
        state.payment = _section_values(flat, "payment", _PAYMENT_FIELDS)
        state.intent = _section_values(flat, "intent", _INTENT_FIELDS)
        state.intent = {**normalized_intent, **state.intent}
        state.flow_type, state.intent = _normalize_flow_type_and_intent(state.flow_type, state.intent)
        state.meta = {
            key: flat[key]
            for key in ("awaiting_store_region", "pending_step", *_FLOW_PROGRESS_META_FIELDS)
            if flat.get(key) not in _EMPTY_VALUES
        }
        state.candidates = _candidate_values(flat.get("last_candidates"))
        state.dormant_flows = _dormant_flow_values(flat.get("dormant_flows"))
        state.flow_events = _flow_event_values(flat.get("flow_events"))
        state.meta["source"] = source
        return state

    def to_active_flow_context(self) -> dict[str, Any]:
        context: dict[str, Any] = {
            "flow_type": self.flow_type,
            "status": self.status,
            "updated_at": str(
                self.meta.get("updated_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
            ),
        }
        if self.flow_step:
            context["flow_step"] = self.flow_step
        for section_name in (
            "product",
            "vehicle",
            "recommendation",
            "store",
            "schedule",
            "payment",
            "intent",
        ):
            values = _non_empty_mapping(getattr(self, section_name))
            if values:
                context[section_name] = values
        if self.meta.get("source") not in _EMPTY_VALUES:
            context["source"] = self.meta["source"]
        for key in _FLOW_PROGRESS_META_FIELDS:
            if self.meta.get(key) not in _EMPTY_VALUES:
                context[key] = self.meta[key]
        if self.candidates:
            context["last_candidates"] = [dict(candidate) for candidate in self.candidates]
        if self.dormant_flows:
            context["dormant_flows"] = [dict(dormant) for dormant in self.dormant_flows]
        if self.flow_events:
            context["flow_events"] = [dict(event) for event in self.flow_events]
        return _non_empty_mapping(context)

    def to_pending_order_context(self) -> dict[str, Any]:
        flat: dict[str, Any] = {}
        for section in (self.product, self.vehicle, self.store, self.schedule, self.payment, self.intent, self.meta):
            flat.update(_non_empty_mapping(section))
        flat["source"] = str(self.meta.get("source") or flat.get("source") or "")
        flat["status"] = self.status
        flat["flow_type"] = self.flow_type
        flat["updated_at"] = str(
            self.meta.get("updated_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
        )
        return _non_empty_mapping(flat)

    def merge(self, delta: "FlowState", *, source: str) -> FlowStateMergeResult:
        if effective_flow_type(self.flow_type, self.intent) != "purchase" or effective_flow_type(
            delta.flow_type,
            delta.intent,
        ) != "purchase":
            return self._merge_active(delta, source=source)
        before = self.to_pending_order_context()
        merged = FlowState.from_pending_order_context(before)
        committed_fields: list[str] = []
        preserved_fields: list[str] = []
        cleared_fields: list[str] = []
        conflicts: dict[str, dict[str, Any]] = {}
        invalidated_sections: set[str] = set()
        existing_product = dict(merged.product)
        existing_schedule = dict(merged.schedule)

        product_change = _product_resolution_change(existing_product, delta.product)
        if product_change:
            conflict_key, conflict_values, clear_goods_no = product_change
            conflicts[conflict_key] = conflict_values
            _clear_product_dependent_context(merged, cleared_fields, clear_goods_no=clear_goods_no)
            invalidated_sections.update(("store", "schedule", "payment"))

        if _tire_size_changed(existing_product, delta.product):
            conflicts["tire_size"] = {
                "existing": _normalize_vehicle_tire_size(existing_product.get("tire_size")),
                "incoming": _normalize_vehicle_tire_size(delta.product.get("tire_size")),
            }
            _clear_product_dependent_context(merged, cleared_fields, clear_goods_no=True)
            invalidated_sections.update(("store", "schedule", "payment"))

        existing_shop_id = str(merged.store.get("shop_id") or "").strip()
        incoming_shop_id = str(delta.store.get("shop_id") or "").strip()
        if existing_shop_id and incoming_shop_id and existing_shop_id != incoming_shop_id:
            conflicts["shop_id"] = {"existing": existing_shop_id, "incoming": incoming_shop_id}
            cleared_fields.extend(_clear_section(merged.schedule))
            cleared_fields.extend(_clear_section(merged.payment))
            invalidated_sections.update(("schedule", "payment"))

        existing_region = str(merged.store.get("region") or "").strip()
        incoming_region = str(delta.store.get("region") or "").strip()
        if existing_region and incoming_region and existing_region != incoming_region and not delta.store.get("shop_id"):
            cleared_fields.extend(_clear_section(merged.schedule))
            cleared_fields.extend(_clear_section(merged.payment))
            invalidated_sections.update(("schedule", "payment"))
            for field_name in ("shop_id", "shop_name"):
                if merged.store.pop(field_name, None) not in _EMPTY_VALUES:
                    cleared_fields.append(field_name)

        if _schedule_changed(existing_schedule, delta.schedule) and delta.payment.get("payment_amount") in _EMPTY_VALUES:
            conflicts["schedule"] = {
                "existing": _non_empty_mapping(existing_schedule),
                "incoming": _non_empty_mapping(delta.schedule),
            }
            _clear_payment_context(merged, cleared_fields)
            invalidated_sections.add("payment")
            merged.payment["payment_amount_stale"] = True
            committed_fields.append("payment_amount_stale")

        qty_changed = _quantity_changed(merged.product.get("ord_qty"), delta.product.get("ord_qty"))
        if qty_changed and delta.payment.get("payment_amount") in _EMPTY_VALUES:
            if merged.payment.pop("payment_amount", None) not in _EMPTY_VALUES:
                cleared_fields.append("payment_amount")
            if not any(merged.payment.get(field) not in _EMPTY_VALUES for field in _PAYMENT_UNIT_PRICE_FIELDS):
                if merged.payment.pop("price_basis", None) not in _EMPTY_VALUES:
                    cleared_fields.append("price_basis")
                if merged.payment.pop("price_source_tool", None) not in _EMPTY_VALUES:
                    cleared_fields.append("price_source_tool")
            invalidated_sections.add("payment")
            merged.payment.pop("payment_amount_stale", None)
            merged.payment["payment_amount_stale"] = True
            committed_fields.append("payment_amount_stale")

        preserve_purchase_intent = _is_purchase_intent_group(merged.intent) and _is_stock_intent_group(delta.intent)

        for section_name in ("product", "vehicle", "store", "schedule", "payment", "intent"):
            if section_name in invalidated_sections:
                continue
            target = getattr(merged, section_name)
            incoming = getattr(delta, section_name)
            for key, value in incoming.items():
                if value in _EMPTY_VALUES:
                    continue
                if preserve_purchase_intent and section_name == "intent" and key in {
                    "pending_intent",
                    "goal_type",
                    "stock_check_mode",
                }:
                    preserved_fields.append(key)
                    continue
                if target.get(key) not in _EMPTY_VALUES and target.get(key) == value:
                    preserved_fields.append(key)
                    continue
                target[key] = value
                committed_fields.append(key)

        if merged.payment.get("payment_amount") not in _EMPTY_VALUES:
            merged.payment.pop("payment_amount_stale", None)
        _normalize_product_aliases(merged.product)
        merged.meta.update(_non_empty_mapping(delta.meta))
        if delta.candidates:
            merged.candidates = [dict(candidate) for candidate in delta.candidates]
            committed_fields.append("last_candidates")
        merged.meta["source"] = source
        merged.meta["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        merged.status = (
            delta.status if delta.status in {"active", "dormant", "resumed", "completed"} else merged.status
        )
        after = merged.to_pending_order_context()

        return FlowStateMergeResult(
            state=merged,
            metadata={
                "slot_commit_event": source,
                "committed_fields": sorted(dict.fromkeys(committed_fields)),
                "preserved_fields": sorted(dict.fromkeys(preserved_fields)),
                "cleared_fields": sorted(dict.fromkeys(cleared_fields)),
                "flow_state_before": before,
                "flow_state_delta": delta.to_pending_order_context(),
                "flow_state_after": after,
                "flow_state_commit_source": source,
                "flow_state_conflicts": conflicts,
                "payment_amount_stale": bool(after.get("payment_amount_stale")),
            },
        )

    def _merge_active(self, delta: "FlowState", *, source: str) -> FlowStateMergeResult:
        before = self.to_active_flow_context()
        merged = FlowState.from_active_flow_context(before)
        committed_fields: list[str] = []
        preserved_fields: list[str] = []
        cleared_fields: list[str] = []
        conflicts: dict[str, dict[str, Any]] = {}
        invalidated_sections: set[str] = set()
        existing_product = dict(merged.product)
        existing_vehicle = dict(merged.vehicle)
        existing_schedule = dict(merged.schedule)

        if delta.flow_type and merged.flow_type != delta.flow_type and _is_empty_implicit_flow_state(merged):
            merged = FlowState(flow_type=delta.flow_type, status=delta.status, flow_step=delta.flow_step)
            existing_product = {}
            existing_vehicle = {}
            existing_schedule = {}
            committed_fields.append("flow_type")
        elif delta.flow_type and merged.flow_type != delta.flow_type:
            conflicts["flow_type"] = {"existing": merged.flow_type, "incoming": delta.flow_type}
            previous_identity = flow_identity_for_context(before)
            dormant_flows = upsert_dormant_flow(
                merged.dormant_flows,
                _flow_context_without_history(before),
            )
            flow_events = [
                _new_flow_event(
                    "deactivate",
                    source=source,
                    flow_identity=previous_identity,
                    details={"incoming_flow_type": delta.flow_type},
                ),
                *_flow_event_values(merged.flow_events),
            ]
            merged = FlowState(flow_type=delta.flow_type, status=delta.status, flow_step=delta.flow_step)
            merged.dormant_flows = dormant_flows
            merged.flow_events = flow_events
            committed_fields.append("flow_type")
            if previous_identity:
                committed_fields.append("dormant_flows")
            existing_product = {}
            existing_vehicle = {}
            existing_schedule = {}
        elif delta.flow_step:
            merged.flow_step = delta.flow_step
            committed_fields.append("flow_step")

        vehicle_change = _vehicle_changed(existing_vehicle, delta.vehicle)
        if vehicle_change:
            conflict_values, changed = vehicle_change
            if changed:
                conflicts["vehicle"] = conflict_values
                _clear_recommendation_context(merged, cleared_fields)
                _clear_product_dependent_context(
                    merged,
                    cleared_fields,
                    clear_goods_no=True,
                    clear_product_resolution=True,
                )
                invalidated_sections.update(("store", "schedule", "payment"))

        product_change = _product_resolution_change(existing_product, delta.product)
        if product_change:
            conflict_key, conflict_values, clear_goods_no = product_change
            conflicts[conflict_key] = conflict_values
            _clear_product_dependent_context(merged, cleared_fields, clear_goods_no=clear_goods_no)
            invalidated_sections.update(("store", "schedule", "payment"))

        if _tire_size_changed(existing_product, delta.product):
            conflicts["tire_size"] = {
                "existing": _normalize_vehicle_tire_size(existing_product.get("tire_size")),
                "incoming": _normalize_vehicle_tire_size(delta.product.get("tire_size")),
            }
            _clear_product_dependent_context(merged, cleared_fields, clear_goods_no=True)
            invalidated_sections.update(("store", "schedule", "payment"))

        existing_shop_id = str(merged.store.get("shop_id") or "").strip()
        incoming_shop_id = str(delta.store.get("shop_id") or "").strip()
        if existing_shop_id and incoming_shop_id and existing_shop_id != incoming_shop_id:
            conflicts["shop_id"] = {"existing": existing_shop_id, "incoming": incoming_shop_id}
            cleared_fields.extend(_clear_section(merged.schedule))
            cleared_fields.extend(_clear_section(merged.payment))
            invalidated_sections.update(("schedule", "payment"))

        existing_region = str(merged.store.get("region") or "").strip()
        incoming_region = str(delta.store.get("region") or "").strip()
        if existing_region and incoming_region and existing_region != incoming_region and not delta.store.get("shop_id"):
            cleared_fields.extend(_clear_section(merged.schedule))
            cleared_fields.extend(_clear_section(merged.payment))
            invalidated_sections.update(("schedule", "payment"))
            for field_name in ("shop_id", "shop_name"):
                if merged.store.pop(field_name, None) not in _EMPTY_VALUES:
                    cleared_fields.append(field_name)

        if _schedule_changed(existing_schedule, delta.schedule) and delta.payment.get("payment_amount") in _EMPTY_VALUES:
            conflicts["schedule"] = {
                "existing": _non_empty_mapping(existing_schedule),
                "incoming": _non_empty_mapping(delta.schedule),
            }
            _clear_payment_context(merged, cleared_fields)
            invalidated_sections.add("payment")
            merged.payment["payment_amount_stale"] = True
            committed_fields.append("payment_amount_stale")

        if _quantity_changed(merged.product.get("ord_qty"), delta.product.get("ord_qty")):
            if merged.payment.pop("payment_amount", None) not in _EMPTY_VALUES:
                cleared_fields.append("payment_amount")
            if not any(merged.payment.get(field) not in _EMPTY_VALUES for field in _PAYMENT_UNIT_PRICE_FIELDS):
                if merged.payment.pop("price_basis", None) not in _EMPTY_VALUES:
                    cleared_fields.append("price_basis")
                if merged.payment.pop("price_source_tool", None) not in _EMPTY_VALUES:
                    cleared_fields.append("price_source_tool")
            invalidated_sections.add("payment")
            merged.payment.pop("payment_amount_stale", None)
            if delta.payment.get("payment_amount") in _EMPTY_VALUES:
                merged.payment["payment_amount_stale"] = True
                committed_fields.append("payment_amount_stale")

        for section_name in (
            "product",
            "vehicle",
            "recommendation",
            "store",
            "schedule",
            "payment",
            "intent",
        ):
            if section_name in invalidated_sections:
                continue
            target = getattr(merged, section_name)
            incoming = getattr(delta, section_name)
            for key, value in incoming.items():
                if value in _EMPTY_VALUES:
                    continue
                if target.get(key) == value:
                    preserved_fields.append(key)
                    continue
                target[key] = value
                committed_fields.append(key)

        if merged.payment.get("payment_amount") not in _EMPTY_VALUES:
            merged.payment.pop("payment_amount_stale", None)
        if delta.candidates:
            merged.candidates = [dict(candidate) for candidate in delta.candidates]
            committed_fields.append("last_candidates")
        if delta.dormant_flows:
            merged.dormant_flows = prune_dormant_flows([*merged.dormant_flows, *delta.dormant_flows])
            committed_fields.append("dormant_flows")
        if delta.flow_events:
            merged.flow_events = [*delta.flow_events, *merged.flow_events]
            committed_fields.append("flow_events")
        merged.meta.update(_non_empty_mapping(delta.meta))
        merged.meta["source"] = source
        merged.meta["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        merged.status = (
            delta.status if delta.status in {"active", "dormant", "resumed", "completed"} else merged.status
        )
        _refresh_flow_progress(merged)
        after = merged.to_active_flow_context()
        return FlowStateMergeResult(
            state=merged,
            metadata={
                "slot_commit_event": source,
                "committed_fields": sorted(dict.fromkeys(committed_fields)),
                "preserved_fields": sorted(dict.fromkeys(preserved_fields)),
                "cleared_fields": sorted(dict.fromkeys(cleared_fields)),
                "flow_state_before": before,
                "flow_state_delta": delta.to_active_flow_context(),
                "flow_state_after": after,
                "flow_state_commit_source": source,
                "flow_state_conflicts": conflicts,
                "payment_amount_stale": bool(
                    merged.payment.get("payment_amount_stale")
                    and merged.payment.get("payment_amount") in _EMPTY_VALUES
                ),
            },
        )


def _is_empty_implicit_flow_state(state: FlowState) -> bool:
    return (
        state.flow_type == "commerce"
        and state.status == "active"
        and state.flow_step is None
        and not state.product
        and not state.vehicle
        and not state.recommendation
        and not state.store
        and not state.schedule
        and not state.payment
        and state.intent == {"sub_flow_type": "purchase"}
        and not state.candidates
        and not state.dormant_flows
        and not state.flow_events
    )


def is_purchase_flow_context(*contexts: Mapping[str, Any] | None) -> bool:
    for context in contexts:
        values = _non_empty_mapping(context)
        intent = values.get("intent") if isinstance(values.get("intent"), Mapping) else values
        if effective_flow_type(values.get("flow_type"), intent) == "purchase":
            return True
        if values.get("pending_intent") == "order" or values.get("goal_type") == "place_order":
            return True
    return False


def commit_purchase_flow_state(
    existing_context: Mapping[str, Any] | None,
    delta: Mapping[str, Any] | None,
    *,
    source: str,
    status: str = "active",
) -> FlowStateMergeResult:
    existing_state = FlowState.from_pending_order_context(existing_context)
    delta_state = FlowState.from_flat_delta(delta, source=source)
    delta_state.status = status
    return existing_state.merge(delta_state, source=source)


def commit_flow_state(
    existing_context: Mapping[str, Any] | None,
    delta: Mapping[str, Any] | None,
    *,
    source: str,
    flow_type: str,
    flow_step: str | None = None,
    status: str = "active",
) -> FlowStateMergeResult:
    existing_state = FlowState.from_active_flow_context(existing_context)
    delta_state = FlowState.from_flat_delta(delta, source=source, flow_type=flow_type, flow_step=flow_step)
    delta_state.status = status
    return existing_state._merge_active(delta_state, source=source)


def latest_router_evidence(
    routing_result: Any | None,
    *,
    domains: tuple[Any, ...] | list[Any] | None = None,
    source: str = "llm_router",
) -> dict[str, Any]:
    if routing_result is None:
        return {}
    execution_plan = tuple(
        str(item or "").strip()
        for item in tuple(getattr(routing_result, "execution_plan", ()) or ())
        if str(item or "").strip()
    )
    router_intent = _router_current_turn_intent(routing_result, execution_plan)
    router_domain = _router_current_turn_domain(routing_result, domains, execution_plan)
    if not router_intent and not router_domain:
        return {}
    confidence = getattr(routing_result, "planner_confidence", None)
    evidence: dict[str, Any] = {
        "domain": router_domain,
        "intent": router_intent,
        "policy_intent": str(getattr(routing_result, "policy_intent", "") or "").strip(),
        "execution_plan": list(execution_plan),
        "flow": str(getattr(routing_result, "flow", "") or "").strip(),
        "source": source,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if confidence not in _EMPTY_VALUES:
        evidence["confidence"] = confidence
    return _non_empty_mapping(evidence)


def apply_latest_router_evidence(
    slots: Any,
    routing_result: Any | None,
    *,
    domains: tuple[Any, ...] | list[Any] | None = None,
    source: str = "llm_router",
) -> tuple[Any, dict[str, Any]]:
    evidence = latest_router_evidence(routing_result, domains=domains, source=source)
    return apply_router_evidence_snapshot(slots, evidence, source=source)


def apply_router_evidence_snapshot(
    slots: Any,
    evidence: Mapping[str, Any] | None,
    *,
    source: str = "llm_router",
) -> tuple[Any, dict[str, Any]]:
    evidence = _non_empty_mapping(evidence)
    if not evidence:
        return slots, {}
    availability_context = (
        dict(slots.availability_context)
        if isinstance(getattr(slots, "availability_context", None), Mapping)
        else {}
    )
    previous_evidence = availability_context.get("latest_router_evidence")
    availability_context["latest_router_evidence"] = evidence
    if hasattr(slots, "availability_context"):
        slots.availability_context = availability_context
    return slots, {
        "latest_router_evidence_saved": True,
        "latest_router_evidence_source": source,
        "latest_router_evidence_before": (
            dict(previous_evidence) if isinstance(previous_evidence, Mapping) else {}
        ),
        "latest_router_evidence_after": evidence,
    }


def _router_current_turn_intent(routing_result: Any, execution_plan: tuple[str, ...]) -> str:
    for attr in ("intent", "slot_fill_intent", "policy_intent"):
        value = str(getattr(routing_result, attr, "") or "").strip()
        if value and value != "none":
            return value
    for item in execution_plan:
        if ":" in item:
            intent = item.split(":", 1)[1].strip()
            if intent:
                return intent
    return ""


def _router_current_turn_domain(
    routing_result: Any,
    domains: tuple[Any, ...] | list[Any] | None,
    execution_plan: tuple[str, ...],
) -> str:
    for domain in tuple(domains or ()):
        value = _domain_value(domain)
        if value:
            return value
    for domain in tuple(getattr(routing_result, "domains", ()) or ()):
        value = _domain_value(domain)
        if value:
            return value
    for item in execution_plan:
        if ":" in item:
            return item.split(":", 1)[0].strip()
    return ""


def _domain_value(domain: Any) -> str:
    value = getattr(domain, "value", domain)
    return str(value or "").strip().lower()


def store_candidates_flow_delta(
    *,
    event: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        return {}
    if event.get("template") == "location":
        event_data = event.get("data") if isinstance(event.get("data"), Mapping) else {}
    elif isinstance(event.get("stores"), list):
        event_data = event
    else:
        return {}
    stores = event_data.get("stores") if isinstance(event_data, Mapping) else None
    metadata = event_data.get("metadata") if isinstance(event_data, Mapping) else None
    if not isinstance(stores, list) or not isinstance(metadata, list):
        return {}
    event_metadata = _event_contract_metadata(event_data)
    event_contract_intent = str(event.get("contract_intent") or event_metadata.get("contract_intent") or "").strip()
    event_response_shape = str(
        event_metadata.get("response_shape_key")
        or event_metadata.get("responseShapeKey")
        or event_metadata.get("response_intent")
        or ""
    ).strip()

    candidates: list[dict[str, Any]] = []
    known_slots: dict[str, Any] = {}
    flow_type = ""
    for idx, meta in enumerate(metadata):
        if not isinstance(meta, Mapping):
            continue
        source_tool = str(meta.get("sourceTool") or meta.get("source_tool") or "").strip()
        if source_tool not in _STORE_CANDIDATE_SOURCE_TOOLS:
            continue
        candidate_flow_type = _store_candidate_flow_type(
            meta,
            event_contract_intent=event_contract_intent,
            event_response_shape=event_response_shape,
        )
        if not candidate_flow_type:
            continue
        shop_id = str(meta.get("shopId") or meta.get("shop_id") or "").strip()
        if not shop_id:
            continue
        store = stores[idx] if idx < len(stores) and isinstance(stores[idx], Mapping) else {}
        candidate = _store_candidate_from_metadata(store, meta, flow_type=candidate_flow_type)
        if not candidate:
            continue
        candidate["flow_type"] = candidate_flow_type
        candidates.append(candidate)
        if not flow_type:
            flow_type = candidate_flow_type
        for key in ("goods_no", "product_name", "tire_model", "pending_product_name", "tire_size", "ord_qty", "region"):
            if known_slots.get(key) in _EMPTY_VALUES and candidate.get(key) not in _EMPTY_VALUES:
                known_slots[key] = candidate[key]
        if candidate_flow_type in {"stock", "purchase"}:
            intent_keys = ("pending_intent", "goal_type", "stock_check_mode") if candidate_flow_type == "stock" else (
                "pending_intent",
                "goal_type",
            )
            for key in intent_keys:
                if known_slots.get(key) in _EMPTY_VALUES and candidate.get(key) not in _EMPTY_VALUES:
                    known_slots[key] = candidate[key]
    if not candidates:
        return {}
    if not flow_type:
        flow_type = "store_search"
    flow_step = "show_store_candidates"
    return {
        "flow_type": flow_type,
        "status": "active",
        "flow_step": flow_step,
        "last_candidates": candidates,
        **(
            {
                "stock_check_mode": known_slots.get("stock_check_mode") or "preview",
                "pending_intent": "stock",
                "goal_type": "store_with_stock",
            }
            if flow_type == "stock"
            else {}
        ),
        **known_slots,
    }


def store_candidate_selection_patch(
    *,
    active_flow_context: Mapping[str, Any] | None,
    user_text: str,
    selection_hint: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    active_flow = FlowState.from_active_flow_context(active_flow_context)
    active_flow_type = effective_flow_type(active_flow.flow_type, active_flow.intent)
    if active_flow_type not in {
        "purchase",
        "stock",
        "store_search",
        "store_schedule",
        "store_service_search",
        "favorite_store",
    }:
        return {}
    if active_flow.flow_step != "show_store_candidates":
        return {}
    if active_flow.status not in {"active", "resumed"}:
        return {}
    candidates = [candidate for candidate in active_flow.candidates if isinstance(candidate, Mapping)]
    if not candidates:
        return {}

    selected, ambiguous = _select_store_candidate(
        candidates,
        user_text=user_text,
        selection_hint=_non_empty_mapping(selection_hint),
    )
    if not selected:
        return {"_store_candidate_ambiguous": True} if ambiguous else {}

    patch = {
        key: selected[key]
        for key in (
            "shop_id",
            "shop_name",
            "schedule_mode",
            "schedule_tier",
            "inventory_mode",
            "source_tool",
            "product_name",
            "tire_model",
            "pending_product_name",
            "goods_no",
            "tire_size",
            "ord_qty",
            "region",
            "payment_amount",
            "pending_intent",
            "goal_type",
            "stock_check_mode",
        )
        if selected.get(key) not in _EMPTY_VALUES
    }
    patch["_flow_type"] = active_flow_type
    if active_flow_type == "stock":
        patch.update({
            "pending_intent": "stock",
            "goal_type": "store_with_stock",
            "stock_check_mode": patch.get("stock_check_mode") or "preview",
            "flow_step": (
                "store_selected" if patch.get("stock_check_mode") == "inventory_only" else "selected_store_schedule"
            ),
        })
    else:
        patch["flow_step"] = "store_selected"
    return patch


def selected_store_slots_from_active_flow_context(
    active_flow_context: Mapping[str, Any] | None,
    *,
    allowed_flow_types: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    active_flow = FlowState.from_active_flow_context(active_flow_context)
    if active_flow.status not in {"active", "resumed"}:
        return {}
    if active_flow.flow_step not in {"store_selected", "selected_store_schedule"}:
        return {}
    active_flow_type = effective_flow_type(active_flow.flow_type, active_flow.intent)
    if not flow_type_matches_allowed(active_flow.flow_type, allowed_flow_types, active_flow.intent):
        return {}
    if not active_flow.store.get("shop_id"):
        return {}
    selected: dict[str, Any] = {
        "flow_type": active_flow_type,
        "flow_step": active_flow.flow_step,
        **{
            key: active_flow.store[key]
            for key in ("shop_id", "shop_name", "region")
            if active_flow.store.get(key) not in _EMPTY_VALUES
        },
    }
    selected_shop_id = str(selected.get("shop_id") or "").strip()
    selected_candidate = next(
        (
            candidate
            for candidate in active_flow.candidates
            if str(candidate.get("shop_id") or "").strip() == selected_shop_id
        ),
        {},
    )
    if isinstance(selected_candidate, Mapping):
        for key in (
            "goods_no",
            "product_name",
            "tire_model",
            "pending_product_name",
            "tire_size",
            "ord_qty",
            "payment_amount",
            "payment_amount_source",
            "price_basis",
            "price_source_tool",
            "sale_prc",
            "extra_fvr_sale_prc",
            "cheapest_final_prc",
            "final_unit_price",
            "final_prc",
            "final_price",
            "finalPrice",
            "price",
            "wage_prc",
            "source_tool",
            "schedule_mode",
            "schedule_tier",
            "inventory_mode",
            "stock_check_mode",
            "pending_intent",
            "goal_type",
        ):
            if selected.get(key) in _EMPTY_VALUES and selected_candidate.get(key) not in _EMPTY_VALUES:
                selected[key] = selected_candidate[key]
    for section in (active_flow.product, active_flow.payment, active_flow.intent):
        for key in (
            "goods_no",
            "product_name",
            "tire_model",
            "pending_product_name",
            "tire_size",
            "ord_qty",
            "payment_amount",
            "payment_amount_source",
            "price_basis",
            "price_source_tool",
            "sale_prc",
            "extra_fvr_sale_prc",
            "cheapest_final_prc",
            "final_unit_price",
            "final_prc",
            "final_price",
            "finalPrice",
            "price",
            "wage_prc",
            "source_tool",
            "schedule_mode",
            "inventory_mode",
            "stock_check_mode",
            "pending_intent",
            "goal_type",
        ):
            if selected.get(key) in _EMPTY_VALUES and section.get(key) not in _EMPTY_VALUES:
                selected[key] = section[key]
    return _non_empty_mapping(selected)


def recommendation_listcar_flow_delta(
    *,
    event: Mapping[str, Any] | None,
    recommendation_context: Mapping[str, Any] | None,
    recommendation_scenario: str | None = None,
    contract_intent: str | None = None,
    response_shape_key: str | None = None,
) -> dict[str, Any]:
    if not isinstance(event, Mapping) or event.get("template") != "listCar":
        return {}
    event_data = event.get("data") if isinstance(event.get("data"), Mapping) else {}
    contract_metadata = _event_contract_metadata(event_data)
    effective_response_shape_key = str(
        response_shape_key
        or contract_metadata.get("response_shape_key")
        or contract_metadata.get("responseShapeKey")
        or ""
    ).strip()
    effective_contract_intent = str(contract_intent or contract_metadata.get("contract_intent") or "").strip()
    if (
        effective_response_shape_key != "vehicle_resolved_recommendation"
        and effective_contract_intent != "vehicle_resolved_recommendation"
    ):
        return {}
    metadata = event_data.get("metadata") if isinstance(event_data, Mapping) else None
    listcar_metadata = metadata if isinstance(metadata, list) else []
    if not listcar_metadata:
        return {}
    expected_intents = {
        str(item.get("expected_contract_intent") or item.get("expectedContractIntent") or "").strip()
        for item in listcar_metadata
        if isinstance(item, Mapping)
    }
    if expected_intents and "vehicle_resolved_recommendation" not in expected_intents:
        return {}
    normalized_context = _recommendation_context_dict(recommendation_context)
    scenario = str(
        recommendation_scenario
        or normalized_context.get("recommendation_scenario")
        or normalized_context.get("scenario")
        or ""
    ).strip()
    tool_args_patch = _non_empty_mapping(normalized_context.get("tool_args_patch"))
    expected_tool_args = _non_empty_mapping(normalized_context.get("expected_tool_args"))
    if not normalized_context and not scenario and not tool_args_patch and not expected_tool_args:
        return {}

    recommendation = {
        key: value
        for key, value in {
            "scenario": scenario or None,
            "recommendation_scenario": scenario or None,
            "tool_args_patch": tool_args_patch or None,
            "expected_tool_args": expected_tool_args or None,
            "rcmd_type": tool_args_patch.get("rcmd_type") or expected_tool_args.get("rcmd_type"),
            "season_nm": tool_args_patch.get("season_nm") or expected_tool_args.get("season_nm"),
            "brand_cd": tool_args_patch.get("brand_cd") or expected_tool_args.get("brand_cd"),
            "allow_cross_brand_fill": tool_args_patch.get("allow_cross_brand_fill")
            if "allow_cross_brand_fill" in tool_args_patch
            else expected_tool_args.get("allow_cross_brand_fill"),
            "source_text": normalized_context.get("source_text"),
            "scope": normalized_context.get("scope"),
            "fitment_source": normalized_context.get("fitment_source"),
        }.items()
        if value not in _EMPTY_VALUES
    }
    return {
        "flow_type": "recommendation",
        "status": "active",
        "flow_step": "select_vehicle",
        "pending_intent": "product_recommendation",
        "goal_type": "recommend_tire",
        "selection_required": True,
        **recommendation,
    }


def recommendation_named_vehicle_flow_delta(
    *,
    recommendation_context: Mapping[str, Any] | None,
    named_vehicle_anchor: str | None,
    source_text: str | None = None,
) -> dict[str, Any]:
    anchor = str(named_vehicle_anchor or "").strip()
    if not anchor:
        return {}
    normalized_context = _recommendation_context_dict(recommendation_context)
    tool_args_patch = _non_empty_mapping(normalized_context.get("tool_args_patch"))
    expected_tool_args = _non_empty_mapping(normalized_context.get("expected_tool_args"))
    if not tool_args_patch and not expected_tool_args:
        return {}
    scenario = str(
        normalized_context.get("recommendation_scenario")
        or normalized_context.get("scenario")
        or ""
    ).strip()
    recommendation = {
        key: value
        for key, value in {
            "scenario": scenario or None,
            "recommendation_scenario": scenario or None,
            "tool_args_patch": tool_args_patch or None,
            "expected_tool_args": expected_tool_args or None,
            "rcmd_type": tool_args_patch.get("rcmd_type") or expected_tool_args.get("rcmd_type"),
            "season_nm": tool_args_patch.get("season_nm") or expected_tool_args.get("season_nm"),
            "brand_cd": tool_args_patch.get("brand_cd") or expected_tool_args.get("brand_cd"),
            "min_price": tool_args_patch.get("min_price") or expected_tool_args.get("min_price"),
            "max_price": tool_args_patch.get("max_price") or expected_tool_args.get("max_price"),
            "source_text": normalized_context.get("source_text") or source_text,
            "fitment_source": "named_registered_vehicle",
        }.items()
        if value not in _EMPTY_VALUES
    }
    return {
        "flow_type": "recommendation",
        "status": "active",
        "flow_step": "resolve_named_vehicle",
        "pending_intent": "product_recommendation",
        "goal_type": "recommend_tire",
        "selection_required": False,
        "named_registered_vehicle_anchor": anchor,
        "requested_vehicle_name": anchor,
        "missing_slots": ("tire_size",),
        "next_tool": "get_my_cars_tool",
        "target_action": "recommend_products",
        "allowed_tools": ("get_my_cars_tool", "get_products_recommendations_tool"),
        "progress_source": "recommendation_named_vehicle_flow",
        **recommendation,
    }


def recommendation_vehicle_selection_patch(
    *,
    active_flow_context: Mapping[str, Any] | None,
    selected_vehicle_slots: Mapping[str, Any] | None,
) -> dict[str, Any]:
    active_flow = FlowState.from_active_flow_context(active_flow_context)
    if effective_flow_type(active_flow.flow_type, active_flow.intent) != "recommendation" or active_flow.flow_step != "select_vehicle":
        return {}
    if active_flow.status not in {"active", "resumed"}:
        return {}
    vehicle_slots = _non_empty_mapping(selected_vehicle_slots)
    tire_size = str(vehicle_slots.get("tire_size") or "").strip()
    tire_size_front = str(vehicle_slots.get("tire_size_front") or "").strip()
    tire_size_rear = str(vehicle_slots.get("tire_size_rear") or "").strip()
    if not tire_size and tire_size_front and tire_size_rear and tire_size_front != tire_size_rear:
        return {}
    car_lnc_cd = str(vehicle_slots.get("car_lnc_cd") or "").strip()
    if not tire_size and not car_lnc_cd:
        return {}

    recommendation_context = dict(active_flow.recommendation)
    tool_args_patch = _non_empty_mapping(recommendation_context.get("tool_args_patch"))
    expected_tool_args = _non_empty_mapping(recommendation_context.get("expected_tool_args"))
    scenario = str(
        recommendation_context.get("recommendation_scenario")
        or recommendation_context.get("scenario")
        or ""
    ).strip()
    if not scenario and not tool_args_patch and not expected_tool_args:
        return {}

    if tire_size:
        recommendation_context["tire_size"] = tire_size
    if car_lnc_cd:
        recommendation_context["car_lnc_cd"] = car_lnc_cd
    recommendation_context["fitment_source"] = "selected_vehicle"

    patch: dict[str, Any] = {
        "discovery_followup_action": "vehicle_based_recommendation_refinement",
        "recommendation_context": recommendation_context,
    }
    if scenario:
        patch["recommendation_scenario"] = scenario
    for key in ("tire_size", "car_lnc_cd", "vehicle_type", "car_type", "mbr_car_reg_seq", "car_no"):
        if vehicle_slots.get(key) not in _EMPTY_VALUES:
            patch[key] = vehicle_slots[key]
    for source_patch in (expected_tool_args, tool_args_patch, recommendation_context):
        for key in ("rcmd_type", "season_nm", "brand_cd", "allow_cross_brand_fill"):
            if source_patch.get(key) not in _EMPTY_VALUES:
                patch.setdefault(key, source_patch[key])
    return patch


def purchase_context_vehicle_selection_patch(
    *,
    parent_context: Mapping[str, Any] | None,
    selected_vehicle_slots: Mapping[str, Any] | None,
    current_slots: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a purchase-flow delta when a recommendation vehicle pick resolves the missing size."""

    context = _non_empty_mapping(parent_context)
    if not context:
        return {}
    pending_intent = str(context.get("pending_intent") or "").strip()
    goal_type = str(context.get("goal_type") or "").strip()
    if pending_intent in {"stock", "reservation"} or goal_type == "store_with_stock":
        return {}

    has_purchase_marker = pending_intent == "order" or goal_type == "place_order"
    has_order_shape = bool(
        context.get("ord_qty")
        and (context.get("shop_id") or context.get("shop_name") or context.get("region"))
    )
    if not (has_purchase_marker or has_order_shape):
        return {}

    vehicle_slots = _non_empty_mapping(selected_vehicle_slots)
    current = _non_empty_mapping(current_slots)
    tire_size = _normalize_vehicle_tire_size(vehicle_slots.get("tire_size"))
    tire_size_front = _normalize_vehicle_tire_size(vehicle_slots.get("tire_size_front"))
    tire_size_rear = _normalize_vehicle_tire_size(vehicle_slots.get("tire_size_rear"))
    if not tire_size and tire_size_front and tire_size_front == tire_size_rear:
        tire_size = tire_size_front
    if not tire_size:
        return {}

    patch: dict[str, Any] = {
        "tire_size": tire_size,
        "pending_intent": "order",
        "goal_type": "place_order",
    }
    for key in (
        "goods_no",
        "product_name",
        "pending_product_name",
        "tire_model",
        "ord_qty",
        "shop_id",
        "shop_name",
        "region",
    ):
        value = current.get(key)
        if value in _EMPTY_VALUES:
            value = context.get(key)
        if value not in _EMPTY_VALUES:
            patch[key] = value
    return patch


def _candidate_values(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_non_empty_mapping(item) for item in value if isinstance(item, Mapping)]


def _store_candidate_flow_type(
    meta: Mapping[str, Any],
    *,
    event_contract_intent: str,
    event_response_shape: str,
) -> str:
    source_tool = str(meta.get("sourceTool") or meta.get("source_tool") or "").strip()
    pending_intent = str(meta.get("pendingIntent") or meta.get("pending_intent") or "").strip()
    goal_type = str(meta.get("goalType") or meta.get("goal_type") or "").strip()
    stock_check_mode = str(meta.get("stockCheckMode") or meta.get("stock_check_mode") or "").strip()
    inventory_mode = str(meta.get("inventoryMode") or meta.get("inventory_mode") or "").strip()
    raw_qty = meta.get("ordQty") if meta.get("ordQty") not in _EMPTY_VALUES else meta.get("ord_qty")
    contract_intent = str(event_contract_intent or "").strip()
    response_shape = str(event_response_shape or "").strip()

    if pending_intent in {"order", "cart"} or goal_type in {"place_order", "add_to_cart"}:
        return "purchase"
    if (
        pending_intent == "stock"
        or goal_type == "store_with_stock"
        or stock_check_mode == "inventory_only"
        or inventory_mode == "inventory_only"
        or contract_intent in _STOCK_STORE_INTENTS
        or response_shape in _STOCK_STORE_RESPONSE_SHAPES
    ):
        return "stock"
    if (
        source_tool == "transaction_store_preview_tool"
        and raw_qty not in _EMPTY_VALUES
        and raw_qty not in (0, "0")
        and any(
            meta.get(key) not in _EMPTY_VALUES
            for key in ("goodsNo", "goods_no", "productName", "product_name", "tireSize", "tire_size")
        )
    ):
        return "purchase"
    if source_tool == "get_favorite_stores_tool" or contract_intent == "favorite_store_lookup":
        return "favorite_store"
    if contract_intent in {"store_schedule", "selected_store_schedule"} or response_shape in _STORE_SCHEDULE_RESPONSE_SHAPES:
        return "store_schedule"
    if (
        contract_intent in {"open_store_search", "store_service_search"}
        or response_shape in _STORE_SERVICE_RESPONSE_SHAPES
        or source_tool == "search_stores_complex_tool"
    ):
        return "store_service_search"
    if source_tool in _STORE_CANDIDATE_SOURCE_TOOLS:
        return "store_search"
    return ""


def _store_candidate_from_metadata(
    store: Mapping[str, Any],
    meta: Mapping[str, Any],
    *,
    flow_type: str,
) -> dict[str, Any]:
    shop_id = str(meta.get("shopId") or meta.get("shop_id") or "").strip()
    shop_name = str(
        meta.get("shopName")
        or meta.get("shop_name")
        or store.get("nameAddress")
        or store.get("name")
        or store.get("title")
        or ""
    ).strip()
    source_tool = str(meta.get("sourceTool") or meta.get("source_tool") or "").strip()
    stock_check_mode = str(meta.get("stockCheckMode") or meta.get("stock_check_mode") or "").strip()
    schedule_mode = str(meta.get("scheduleMode") or meta.get("schedule_mode") or "").strip()
    inventory_mode = str(
        meta.get("inventoryMode")
        or meta.get("inventory_mode")
        or schedule_mode
        or ("inventory_only" if flow_type == "stock" and source_tool == "get_store_list_tool" else "")
    ).strip()
    if not shop_id:
        return {}
    if flow_type == "stock" and source_tool == "transaction_store_preview_tool" and not schedule_mode:
        return {}
    stable_id = str(meta.get("stableId") or meta.get("stable_id") or shop_id).strip()
    candidate = {
        "type": "store",
        "stable_id": stable_id,
        "label": shop_name or shop_id,
        "shop_id": shop_id,
        "shop_name": shop_name,
        "schedule_mode": schedule_mode,
        "schedule_tier": str(meta.get("scheduleTier") or meta.get("schedule_tier") or schedule_mode).strip(),
        "inventory_mode": inventory_mode,
        "source_tool": source_tool or "transaction_store_preview_tool",
        "region": str(meta.get("region") or "").strip(),
    }
    if flow_type in {"stock", "purchase"}:
        product_name = str(
            meta.get("productName")
            or meta.get("product_name")
            or meta.get("goodsNm")
            or meta.get("goods_nm")
            or ""
        ).strip()
        candidate.update({
            "goods_no": str(meta.get("goodsNo") or meta.get("goods_no") or "").strip(),
            "product_name": product_name,
            "tire_model": product_name,
            "pending_product_name": product_name,
            "tire_size": str(meta.get("tireSize") or meta.get("tire_size") or "").strip(),
            "pending_intent": str(
                meta.get("pendingIntent")
                or meta.get("pending_intent")
                or ("stock" if flow_type == "stock" else "order")
            ).strip(),
            "goal_type": str(
                meta.get("goalType")
                or meta.get("goal_type")
                or ("store_with_stock" if flow_type == "stock" else "place_order")
            ).strip(),
        })
        if flow_type == "stock":
            candidate["stock_check_mode"] = stock_check_mode
        raw_qty = meta.get("ordQty") if meta.get("ordQty") not in _EMPTY_VALUES else meta.get("ord_qty")
        try:
            qty = int(raw_qty)
        except (TypeError, ValueError):
            qty = 0
        if qty > 0:
            candidate["ord_qty"] = qty
        payment_amount = meta.get("paymentAmount") if meta.get("paymentAmount") not in _EMPTY_VALUES else meta.get(
            "payment_amount"
        )
        if payment_amount not in _EMPTY_VALUES:
            candidate["payment_amount"] = payment_amount
    return _non_empty_mapping(candidate)


def _select_store_candidate(
    candidates: list[Mapping[str, Any]],
    *,
    user_text: str,
    selection_hint: Mapping[str, Any],
) -> tuple[Mapping[str, Any] | None, bool]:
    hinted_id = str(
        selection_hint.get("stable_id")
        or selection_hint.get("stableId")
        or selection_hint.get("shop_id")
        or selection_hint.get("shopId")
        or selection_hint.get("entity_id")
        or ""
    ).strip()
    if hinted_id:
        exact = [
            candidate
            for candidate in candidates
            if hinted_id
            in {
                str(candidate.get("stable_id") or "").strip(),
                str(candidate.get("shop_id") or "").strip(),
            }
        ]
        if len(exact) == 1:
            return exact[0], False
        if len(exact) > 1:
            return None, True

    hinted_label = str(
        selection_hint.get("label")
        or selection_hint.get("entity_label")
        or selection_hint.get("shop_name")
        or selection_hint.get("shopName")
        or ""
    ).strip()
    text = hinted_label or str(user_text or "").strip()
    if text in _STORE_SELECTION_CHIPS and len(candidates) == 1:
        return candidates[0], False
    ordinal_idx = _selection_ordinal_index(text, len(candidates))
    if ordinal_idx is not None:
        return candidates[ordinal_idx], False
    normalized_text = _normalize_store_label(text)
    if not normalized_text:
        return None, False

    exact_matches = [
        candidate
        for candidate in candidates
        if any(
            _normalize_store_label(value) == normalized_text
            for value in (candidate.get("label"), candidate.get("shop_name"))
            if value not in _EMPTY_VALUES
        )
    ]
    if len(exact_matches) == 1:
        return exact_matches[0], False
    if len(exact_matches) > 1:
        return None, True

    partial_matches = [
        candidate
        for candidate in candidates
        if any(
            normalized_text in _normalize_store_label(value) or _normalize_store_label(value) in normalized_text
            for value in (candidate.get("label"), candidate.get("shop_name"))
            if value not in _EMPTY_VALUES
        )
    ]
    if len(partial_matches) == 1:
        return partial_matches[0], False
    return None, len(partial_matches) > 1


def _selection_ordinal_index(user_text: str, item_count: int) -> int | None:
    normalized = _normalize_store_label(user_text)
    if not normalized:
        return None
    for labels, index in _SELECTION_ORDINALS:
        if index < item_count and any(normalized.startswith(_normalize_store_label(label)) for label in labels):
            return index
    return None


def _normalize_store_label(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[\s\-_()]+", "", text)
    return text.replace("티스테이션", "").replace("tstation", "")


def _clear_section(section: dict[str, Any]) -> list[str]:
    cleared = [key for key, value in section.items() if value not in _EMPTY_VALUES]
    section.clear()
    return cleared


def _quantity_changed(existing: Any, incoming: Any) -> bool:
    if existing in _EMPTY_VALUES or incoming in _EMPTY_VALUES:
        return False
    try:
        return int(existing) != int(incoming)
    except (TypeError, ValueError):
        return False


def _section_values(flat: Mapping[str, Any], section_name: str, fields: tuple[str, ...]) -> dict[str, Any]:
    section = flat.get(section_name)
    if isinstance(section, Mapping):
        return _non_empty_mapping(section)
    return {key: flat[key] for key in fields if flat.get(key) not in _EMPTY_VALUES}


def _event_contract_metadata(event_data: Any) -> dict[str, Any]:
    if not isinstance(event_data, Mapping):
        return {}
    metadata = event_data.get("metadata")
    if isinstance(metadata, Mapping):
        return dict(metadata)
    contract_metadata = event_data.get("contractMetadata")
    if isinstance(contract_metadata, Mapping):
        return dict(contract_metadata)
    return {}


def _recommendation_context_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return _non_empty_mapping(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
        except TypeError:
            return {}
        if isinstance(dumped, Mapping):
            return _non_empty_mapping(dumped)
    return {}
