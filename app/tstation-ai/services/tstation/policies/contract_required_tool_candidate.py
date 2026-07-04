from dataclasses import dataclass
import re
from typing import Any, Mapping

from schemas.tstation.slots import ConversationSlots
from services.tstation.policies.discovery_intent_policy import (
    best_seller_search_params_from_text,
    build_discovery_intent_frame,
    extract_best_seller_vehicle_query,
    extract_product_names,
    normalize_tire_size,
    plan_discovery_tools,
)
from services.tstation.policies.flow_state import (
    flow_type_matches_allowed,
    flow_progress_from_active_context,
    flow_progress_tool_candidate,
    selected_store_slots_from_active_flow_context,
)
from services.tstation.policies.intent_frame import PolicyDomain
from services.tstation.policies.transaction_intent_policy import stock_inventory_store_lookup_tool_input
from services.tstation.policies.turn_contract import TurnContract
from services.tstation.template_mapper import current_transaction_tool_plan


_FAST_PATH_TRANSACTION_RECOVERY_BLOCKLIST = frozenset({
    "quick_order_tool",
    "transaction_store_preview_tool",
    "get_multi_store_schedule_tool",
    "get_final_price_tool",
    "get_logistics_inventory_tool",
})
_FAST_PATH_TRANSACTION_RECOVERY_ALLOWED_TOOLS = frozenset({
    "get_store_schedule_tool",
    "get_store_inventory_tool",
    "get_store_list_tool",
    "search_stores_tool",
    "get_my_reservations_tool",
    "get_orders_of_user_tool",
    "get_order_status_tool",
})
_OWNED_RECORD_RECOVERY_TOOLS = frozenset({
    "get_my_reservations_tool",
    "get_orders_of_user_tool",
    "get_order_status_tool",
})
_OWNED_RECORD_RECOVERY_INTENTS = frozenset({
    "reservation_status_lookup",
    "reservation_store_info_lookup",
    "order_cancel_status_lookup",
    "order_arrival_status_lookup",
})
_TRANSACTION_STORE_PREVIEW_RECOVERY_INTENTS = frozenset({
    "quick_order_reservation",
    "quick_order_with_product_and_quantity",
    "stock_store_search",
})
_FAST_PATH_DISCOVERY_RECOVERY_ALLOWED_TOOLS = frozenset({
    "search_product_summary_tool",
    "search_product_tool",
    "get_product_description_tool",
    "get_products_recommendations_tool",
    "get_best_selling_products_tool",
    "get_my_cars_tool",
    "get_events_tool",
    "get_product_applicable_events_tool",
    "get_event_applicable_products_tool",
})
_FLOW_PROGRESS_TRANSACTION_TOOLS = frozenset({
    "search_stores_tool",
    "get_store_list_tool",
    "get_store_schedule_tool",
    "get_store_inventory_tool",
    "get_final_price_tool",
})
_DIRECT_SUPPORT_FAQ_POLICY_INTENTS = frozenset({
    "card_installment_lookup",
    "coupon_usage_policy",
    "coupon_registration_policy",
    "signup_first_purchase_benefit_policy",
    "reservation_verification_guidance",
    "tire_condition_photo_policy",
    "tire_manufacture_date_policy",
    "tire_quality_warranty_policy",
    "assurance_service_policy",
    "delivery_delay_reservation_schedule_policy",
    "reservation_window_policy",
    "reservation_policy_guidance",
    "installation_work_policy",
    "external_tire_install_policy",
    "promotion_gift_policy",
})
_SIZED_RECOMMENDATION_RESPONSE_SHAPE_KEYS = frozenset({
    "sized_product_recommendation",
    "sized_lowest_price_recommendation",
    "sized_technology_recommendation_cards",
    "sized_safe_service_recommendation_cards",
    "vehicle_based_recommendation_refinement",
})


@dataclass(frozen=True)
class _ContractRequiredToolCandidate:
    tool_name: str
    tool_input: dict[str, Any]
    tool_input_source: str
    display_name: str
    source_domain: str


def _best_seller_tool_input_from_text(
    user_text: str | None,
    *,
    limit: int = 5,
    known_slots: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    tool_input: dict[str, Any] = {"limit": limit}
    tool_input.update(best_seller_search_params_from_text(str(user_text or "")))
    vehicle_query = ""
    if isinstance(known_slots, Mapping):
        vehicle_query = str(known_slots.get("vehicle_query") or "").strip()
    if not vehicle_query:
        vehicle_query = str(extract_best_seller_vehicle_query(str(user_text or "")) or "").strip()
    if vehicle_query:
        tool_input["vehicle_query"] = vehicle_query
    return tool_input


def _is_sized_recommendation_response_shape_key(response_shape_key: str) -> bool:
    key = str(response_shape_key or "").strip()
    return key in _SIZED_RECOMMENDATION_RESPONSE_SHAPE_KEYS or (
        key.startswith("sized_") and "recommendation" in key
    )


def _is_active_order_flow_slots(slots: Any | None) -> bool:
    if slots is None:
        return False
    return getattr(slots, "pending_intent", None) == "order" or getattr(slots, "goal_type", None) == "place_order"


def _card_installment_payment_type_from_text(text: str) -> str:
    normalized = str(text or "")
    if re.search(r"(?:일반.{0,12}스마트\s*페이|스마트\s*페이.{0,12}일반|둘\s*다|둘다|모두|전체|비교)", normalized, re.IGNORECASE):
        return "전체"
    if re.search(r"스마트\s*페이|smart\s*pay|smartpay", normalized, re.IGNORECASE) and re.search(
        r"현대카드|신한카드|삼성카드|국민카드|롯데카드|하나카드|농협카드|우리카드|비씨카드|BC카드|현대|신한|삼성|국민|롯데|하나|농협|우리|비씨|BC",
        normalized,
        re.IGNORECASE,
    ):
        return "전체"
    if re.search(r"스마트\s*페이|smart\s*pay|smartpay", normalized, re.IGNORECASE):
        return "스마트페이"
    return "일반"


def _card_installment_amount_from_text(text: str) -> int | None:
    manwon_match = re.search(r"(\d{1,4}(?:\.\d+)?)\s*만\s*원", str(text or ""), re.IGNORECASE)
    if manwon_match is not None:
        try:
            return int(float(manwon_match.group(1)) * 10000)
        except (TypeError, ValueError):
            return None
    won_match = re.search(r"(\d{1,3}(?:,\d{3})+|\d{4,9})\s*원", str(text or ""), re.IGNORECASE)
    if won_match is not None:
        try:
            return int(str(won_match.group(1)).replace(",", ""))
        except (TypeError, ValueError):
            return None
    return None


def _is_vehicle_selection_recommendation_contract(turn_contract: TurnContract | None) -> bool:
    if turn_contract is None:
        return False
    if str(turn_contract.domain or "").strip().lower() != PolicyDomain.DISCOVERY.value:
        return False
    if str(turn_contract.intent or "").strip() != "product_recommendation":
        return False
    if str(getattr(turn_contract, "preferred_tool", "") or "").strip() != "get_products_recommendations_tool":
        return False
    allowed_tools = {str(tool) for tool in tuple(turn_contract.allowed_tools or ()) if str(tool).strip()}
    if "get_products_recommendations_tool" not in allowed_tools:
        return False
    contract_seed = turn_contract.contract_seed if isinstance(turn_contract.contract_seed, Mapping) else {}
    ui_action = contract_seed.get("ui_action") if isinstance(contract_seed.get("ui_action"), Mapping) else {}
    action_type = str(ui_action.get("action_type") or ui_action.get("cta_action") or "").strip()
    expected_intent = str(ui_action.get("expected_contract_intent") or "").strip()
    if action_type not in {"select_vehicle", "select_vehicle_candidate"} and expected_intent != (
        "vehicle_resolved_recommendation"
    ):
        return False
    tool_args_patch = turn_contract.tool_args_patch if isinstance(turn_contract.tool_args_patch, Mapping) else {}
    known_slots = turn_contract.known_slots if isinstance(turn_contract.known_slots, Mapping) else {}
    return bool(
        tool_args_patch.get("tire_size")
        or known_slots.get("tire_size")
        or tool_args_patch.get("car_lnc_cd")
        or known_slots.get("car_lnc_cd")
    )


def _is_contract_required_vehicle_recommendation(
    turn_contract: TurnContract | None,
    slots: Any | None = None,
) -> bool:
    if turn_contract is None:
        return False
    if str(turn_contract.domain or "").strip().lower() != PolicyDomain.DISCOVERY.value:
        return False
    if str(turn_contract.intent or "").strip() != "product_recommendation":
        return False
    response_decision = turn_contract.response_decision or {}
    response_metadata = response_decision.get("metadata") if isinstance(response_decision, Mapping) else {}
    response_shape_key = str(response_metadata.get("response_shape_key") or "") if isinstance(response_metadata, Mapping) else ""
    contract_sub_intent = str(turn_contract.sub_intent or "").strip()
    is_vehicle_recommendation = contract_sub_intent == "vehicle_based_recommendation_refinement"
    is_sized_recommendation = _is_sized_recommendation_response_shape_key(response_shape_key)
    is_vehicle_selection_recommendation = _is_vehicle_selection_recommendation_contract(turn_contract)
    if not (is_vehicle_recommendation or is_sized_recommendation or is_vehicle_selection_recommendation):
        return False
    if not is_vehicle_selection_recommendation and str(response_decision.get("template") or "").strip().lower() != "product":
        return False
    allowed_tools = {str(tool) for tool in tuple(turn_contract.allowed_tools or ()) if str(tool).strip()}
    if "get_products_recommendations_tool" not in allowed_tools:
        return False

    pending_intent = str(
        getattr(slots, "pending_intent", None) or turn_contract.known_slots.get("pending_intent") or ""
    ).strip()
    goal_type = str(getattr(slots, "goal_type", None) or turn_contract.known_slots.get("goal_type") or "").strip()
    if pending_intent in {"order", "stock"} or goal_type in {"place_order", "store_with_stock"}:
        return False

    if _is_active_order_flow_slots(slots):
        return False

    tire_size = str(getattr(slots, "tire_size", None) or turn_contract.known_slots.get("tire_size") or "").strip()
    car_lnc_cd = str(getattr(slots, "car_lnc_cd", None) or turn_contract.known_slots.get("car_lnc_cd") or "").strip()
    return bool(tire_size or car_lnc_cd)


def _contract_required_recommendation_tool_input(
    *,
    turn_contract: TurnContract,
    known_slots: Mapping[str, Any],
    merged_slots: ConversationSlots | None,
) -> dict[str, Any]:
    if str(turn_contract.domain or "").strip().lower() != PolicyDomain.DISCOVERY.value:
        return {}
    if str(turn_contract.intent or "").strip() != "product_recommendation":
        return {}
    response_decision = turn_contract.response_decision or {}
    response_metadata = response_decision.get("metadata") if isinstance(response_decision, Mapping) else {}
    response_shape_key = str(response_metadata.get("response_shape_key") or "") if isinstance(response_metadata, Mapping) else ""
    contract_sub_intent = str(turn_contract.sub_intent or "").strip()
    is_vehicle_recommendation = contract_sub_intent == "vehicle_based_recommendation_refinement"
    is_sized_recommendation = _is_sized_recommendation_response_shape_key(response_shape_key)
    is_vehicle_selection_recommendation = _is_vehicle_selection_recommendation_contract(turn_contract)
    if not (is_vehicle_recommendation or is_sized_recommendation or is_vehicle_selection_recommendation):
        return {}
    response_template = str(response_decision.get("template") or "").strip().lower()
    if not is_vehicle_selection_recommendation and response_template and response_template != "product":
        return {}
    allowed_tools = {str(tool) for tool in tuple(turn_contract.allowed_tools or ()) if str(tool).strip()}
    if "get_products_recommendations_tool" not in allowed_tools:
        return {}

    tool_input: dict[str, Any] = {}
    recommendation_context = known_slots.get("recommendation_context")
    if isinstance(recommendation_context, Mapping):
        tool_args_patch = recommendation_context.get("tool_args_patch")
        if isinstance(tool_args_patch, Mapping):
            for key, value in tool_args_patch.items():
                if value not in (None, "", [], {}):
                    tool_input[str(key)] = value
        for key in ("rcmd_type", "season_nm", "brand_cd", "allow_cross_brand_fill"):
            value = recommendation_context.get(key)
            if value not in (None, "", [], {}):
                tool_input.setdefault(str(key), value)

    pending_check_topic = str(known_slots.get("pending_check_topic") or "").strip()
    is_safe_service_recommendation = (
        response_shape_key == "sized_safe_service_recommendation_cards" or pending_check_topic == "safe_service"
    )
    if is_safe_service_recommendation:
        tool_input.setdefault("rcmd_type", "safe_kids")
        tool_input.setdefault("brand_cd", known_slots.get("brand_cd") or "HK")
    elif response_shape_key == "sized_technology_recommendation_cards":
        tool_input.setdefault("rcmd_type", "sound_absorber")
    else:
        tool_input.setdefault("rcmd_type", "tstation")

    slot_sources = (
        turn_contract.tool_args_patch if isinstance(turn_contract.tool_args_patch, Mapping) else {},
        known_slots,
        merged_slots.model_dump() if merged_slots is not None else {},
    )
    for key in ("tire_size", "car_lnc_cd", "vehicle_type"):
        for source in slot_sources:
            if not isinstance(source, Mapping):
                continue
            value = source.get(key)
            if value in (None, "", [], {}):
                continue
            tool_input[key] = value
            break

    if tool_input.get("tire_size") in (None, "") and isinstance(recommendation_context, Mapping):
        value = recommendation_context.get("tire_size")
        if value not in (None, "", [], {}):
            tool_input["tire_size"] = value
    if tool_input.get("car_lnc_cd") in (None, "") and isinstance(recommendation_context, Mapping):
        value = recommendation_context.get("car_lnc_cd")
        if value not in (None, "", [], {}):
            tool_input["car_lnc_cd"] = value

    if tool_input.get("tire_size") in (None, "") and tool_input.get("car_lnc_cd") in (None, ""):
        return {}
    return tool_input


def _selected_store_slots_from_merged_slots(
    merged_slots: ConversationSlots | None,
    *,
    allowed_flow_types: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    availability_context = getattr(merged_slots, "availability_context", None) if merged_slots is not None else None
    active_flow_context = (
        availability_context.get("active_flow_context")
        if isinstance(availability_context, Mapping)
        and isinstance(availability_context.get("active_flow_context"), Mapping)
        else {}
    )
    return selected_store_slots_from_active_flow_context(active_flow_context, allowed_flow_types=allowed_flow_types)


def _active_flow_context_from_slots(merged_slots: ConversationSlots | None) -> dict[str, Any]:
    availability_context = getattr(merged_slots, "availability_context", None) if merged_slots is not None else None
    active_flow_context = (
        availability_context.get("active_flow_context")
        if isinstance(availability_context, Mapping)
        and isinstance(availability_context.get("active_flow_context"), Mapping)
        else {}
    )
    return dict(active_flow_context) if isinstance(active_flow_context, Mapping) else {}


def _active_flow_read_through_slots(
    merged_slots: ConversationSlots | None,
    *,
    allowed_flow_types: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    active_flow_context = _active_flow_context_from_slots(merged_slots)
    if not active_flow_context:
        return {}
    flow_type = str(active_flow_context.get("flow_type") or "").strip()
    intent = active_flow_context.get("intent") if isinstance(active_flow_context.get("intent"), Mapping) else {}
    if not flow_type_matches_allowed(flow_type, allowed_flow_types, intent):
        return {}

    values: dict[str, Any] = {}
    for section_name in ("product", "quantity", "store", "intent"):
        section = active_flow_context.get(section_name)
        if isinstance(section, Mapping):
            values.update({str(key): value for key, value in section.items() if value not in (None, "", [], {})})
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
        "pending_intent",
        "goal_type",
        "stock_check_mode",
        "schedule_mode",
        "inventory_mode",
        "source_tool",
        "requested_cal_day",
        "rsv_hour",
    ):
        value = active_flow_context.get(key)
        if value not in (None, "", [], {}):
            values.setdefault(key, value)
    return values


def _contract_read_through_known_slots(
    turn_contract: TurnContract | None,
    merged_slots: ConversationSlots | None,
    *,
    allowed_flow_types: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    values = _active_flow_read_through_slots(merged_slots, allowed_flow_types=allowed_flow_types)
    if merged_slots is not None and hasattr(merged_slots, "model_dump"):
        values.update({
            str(key): value
            for key, value in merged_slots.model_dump().items()
            if value not in (None, "", [], {}) and key != "availability_context"
        })
    if turn_contract is not None:
        values.update({
            str(key): value
            for key, value in dict(turn_contract.known_slots or {}).items()
            if value not in (None, "", [], {})
        })
    return values


def _effective_known_slots_with_selected_store(
    turn_contract: TurnContract,
    merged_slots: ConversationSlots | None,
    *,
    allowed_flow_types: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    known_slots = _contract_read_through_known_slots(turn_contract, merged_slots, allowed_flow_types=allowed_flow_types)
    selected_store_slots = _selected_store_slots_from_merged_slots(merged_slots, allowed_flow_types=allowed_flow_types)
    for key, value in selected_store_slots.items():
        if value not in (None, "", [], {}) and known_slots.get(key) in (None, "", [], {}):
            known_slots[key] = value
    return known_slots


def _is_contract_required_selected_store_schedule(
    turn_contract: TurnContract | None,
    *,
    merged_slots: ConversationSlots | None = None,
) -> bool:
    if turn_contract is None:
        return False
    if str(turn_contract.domain or "").strip().lower() != PolicyDomain.TRANSACTION.value:
        return False
    contract_intent = str(turn_contract.intent or "").strip()
    if contract_intent not in {
        "stock_store_search",
        "stock_store_search_slot_fill_store",
        "store_schedule",
        "selected_store_schedule",
    }:
        return False
    response_decision = turn_contract.response_decision or {}
    if str(response_decision.get("template") or "").strip() != "datepick":
        return False
    metadata = response_decision.get("metadata")
    response_shape_key = str(metadata.get("response_shape_key") or "") if isinstance(metadata, Mapping) else ""
    if response_shape_key and response_shape_key != "reservation_slots":
        return False
    allowed_tools = {str(tool) for tool in tuple(turn_contract.allowed_tools or ()) if str(tool).strip()}
    if "get_store_schedule_tool" not in allowed_tools:
        return False
    if "get_store_schedule_tool" in {str(tool) for tool in tuple(turn_contract.forbidden_tools or ()) if str(tool).strip()}:
        return False
    if tuple(turn_contract.blocking_required_slots or ()):
        return False
    selected_store_slots = _selected_store_slots_from_merged_slots(
        merged_slots,
        allowed_flow_types=frozenset({"stock", "store_schedule"}),
    )
    known_slots = _effective_known_slots_with_selected_store(
        turn_contract,
        merged_slots,
        allowed_flow_types=frozenset({"stock", "store_schedule"}),
    )
    schedule_mode = str(known_slots.get("schedule_mode") or known_slots.get("inventory_mode") or "").strip()
    if contract_intent in {"store_schedule", "selected_store_schedule"}:
        return bool(selected_store_slots.get("flow_type") == "store_schedule" and selected_store_slots.get("shop_id"))
    return bool(
        known_slots.get("shop_id")
        and schedule_mode
        and known_slots.get("goods_no")
        and known_slots.get("tire_size")
        and (known_slots.get("ord_qty") or known_slots.get("quantity"))
        and str(known_slots.get("source_tool") or "") == "transaction_store_preview_tool"
    )


def _contract_required_selected_store_schedule_tool_input(
    turn_contract: TurnContract,
    *,
    merged_slots: ConversationSlots | None = None,
) -> dict[str, Any]:
    if not _is_contract_required_selected_store_schedule(turn_contract, merged_slots=merged_slots):
        return {}
    known_slots = _effective_known_slots_with_selected_store(
        turn_contract,
        merged_slots,
        allowed_flow_types=frozenset({"stock", "store_schedule"}),
    )
    shop_id = str(known_slots.get("shop_id") or "").strip()
    schedule_mode = str(known_slots.get("schedule_mode") or known_slots.get("inventory_mode") or "").strip()
    if str(turn_contract.intent or "").strip() in {"store_schedule", "selected_store_schedule"}:
        schedule_mode = schedule_mode or "general"
    if not shop_id or not schedule_mode:
        return {}
    return {"shop_id": shop_id, "mode": schedule_mode}


def _is_contract_required_stock_inventory_selected_store(
    turn_contract: TurnContract | None,
    *,
    merged_slots: ConversationSlots | None = None,
) -> bool:
    if turn_contract is None:
        return False
    if str(turn_contract.domain or "").strip().lower() != PolicyDomain.TRANSACTION.value:
        return False
    if tuple(turn_contract.blocking_required_slots or ()):
        return False
    allowed_tools = {str(tool) for tool in tuple(turn_contract.allowed_tools or ()) if str(tool).strip()}
    forbidden_tools = {str(tool) for tool in tuple(turn_contract.forbidden_tools or ()) if str(tool).strip()}
    if "get_store_inventory_tool" not in allowed_tools or "get_store_inventory_tool" in forbidden_tools:
        return False
    known_slots = _effective_known_slots_with_selected_store(
        turn_contract,
        merged_slots,
        allowed_flow_types=frozenset({"stock"}),
    )
    stock_check_mode = str(known_slots.get("stock_check_mode") or "").strip()
    return bool(
        stock_check_mode == "inventory_only"
        and known_slots.get("shop_id")
        and known_slots.get("goods_no")
        and (known_slots.get("ord_qty") or known_slots.get("quantity"))
    )


def _contract_required_stock_inventory_selected_store_tool_input(
    turn_contract: TurnContract,
    *,
    merged_slots: ConversationSlots | None = None,
) -> dict[str, Any]:
    if not _is_contract_required_stock_inventory_selected_store(turn_contract, merged_slots=merged_slots):
        return {}
    known_slots = _effective_known_slots_with_selected_store(
        turn_contract,
        merged_slots,
        allowed_flow_types=frozenset({"stock"}),
    )
    goods_no = str(known_slots.get("goods_no") or "").strip()
    shop_id = str(known_slots.get("shop_id") or "").strip()
    raw_qty = known_slots.get("ord_qty") or known_slots.get("quantity")
    try:
        qty = int(raw_qty)
    except (TypeError, ValueError):
        qty = 0
    if not goods_no or not shop_id or qty <= 0:
        return {}
    return {
        "goods_list": [{"goodsNo": goods_no, "qty": str(qty)}],
        "shop_id_list": [{"shopId": shop_id}],
    }


def _is_contract_required_stock_inventory_store_lookup(
    turn_contract: TurnContract | None,
    *,
    merged_slots: ConversationSlots | None = None,
) -> bool:
    if turn_contract is None:
        return False
    if str(turn_contract.domain or "").strip().lower() != PolicyDomain.TRANSACTION.value:
        return False
    if tuple(turn_contract.blocking_required_slots or ()):
        return False
    known_slots = _contract_read_through_known_slots(turn_contract, merged_slots, allowed_flow_types=frozenset({"stock"}))
    stock_check_mode = str(known_slots.get("stock_check_mode") or "").strip()
    if stock_check_mode != "inventory_only":
        return False
    response_decision = turn_contract.response_decision or {}
    if str(response_decision.get("template") or "").strip() != "location":
        return False
    metadata = response_decision.get("metadata")
    response_shape_key = str(metadata.get("response_shape_key") or "") if isinstance(metadata, Mapping) else ""
    if response_shape_key != "stock_inventory_lookup":
        return False
    allowed_tools = {str(tool) for tool in tuple(turn_contract.allowed_tools or ()) if str(tool).strip()}
    forbidden_tools = {str(tool) for tool in tuple(turn_contract.forbidden_tools or ()) if str(tool).strip()}
    if not ({"get_store_list_tool", "search_stores_tool"} & allowed_tools):
        return False
    if {"get_store_list_tool", "search_stores_tool"} <= forbidden_tools:
        return False
    return bool(
        known_slots.get("goods_no")
        and known_slots.get("tire_size")
        and (known_slots.get("ord_qty") or known_slots.get("quantity"))
        and (known_slots.get("region") or known_slots.get("place_query") or known_slots.get("shop_name"))
        and not known_slots.get("shop_id")
    )


def _contract_required_stock_inventory_store_lookup_tool_input(
    turn_contract: TurnContract,
    *,
    merged_slots: ConversationSlots | None = None,
    preferred_tool: str | None = None,
) -> dict[str, Any]:
    if not _is_contract_required_stock_inventory_store_lookup(turn_contract, merged_slots=merged_slots):
        return {}
    known_slots = _contract_read_through_known_slots(turn_contract, merged_slots, allowed_flow_types=frozenset({"stock"}))
    tool = str(preferred_tool or "").strip()
    allowed_tools = {str(item) for item in tuple(turn_contract.allowed_tools or ()) if str(item).strip()}
    if not tool or tool not in allowed_tools:
        tool = "search_stores_tool" if "search_stores_tool" in allowed_tools and known_slots.get("place_query") else ""
    if not tool or tool not in allowed_tools:
        tool = "get_store_list_tool" if "get_store_list_tool" in allowed_tools else ""
    return stock_inventory_store_lookup_tool_input(known_slots, preferred_tool=tool)


def _is_contract_required_transaction_store_preview(
    turn_contract: TurnContract | None,
    *,
    merged_slots: ConversationSlots | None = None,
) -> bool:
    if turn_contract is None:
        return False
    if str(turn_contract.domain or "").strip().lower() != PolicyDomain.TRANSACTION.value:
        return False
    if str(getattr(turn_contract, "preferred_tool", "") or "").strip() != "transaction_store_preview_tool":
        return False
    allowed_tools = {str(tool) for tool in tuple(turn_contract.allowed_tools or ()) if str(tool).strip()}
    forbidden_tools = {str(tool) for tool in tuple(turn_contract.forbidden_tools or ()) if str(tool).strip()}
    if "transaction_store_preview_tool" not in allowed_tools or "transaction_store_preview_tool" in forbidden_tools:
        return False
    if tuple(getattr(turn_contract, "blocking_required_slots", ()) or ()):
        return False
    if str(getattr(turn_contract, "context_state", "") or "").strip() not in {"active", "resumed"}:
        return False

    contract_intent = str(turn_contract.intent or "").strip()
    response_decision = turn_contract.response_decision or {}
    response_metadata = response_decision.get("metadata") if isinstance(response_decision, Mapping) else {}
    response_shape_key = str(response_metadata.get("response_shape_key") or "") if isinstance(response_metadata, Mapping) else ""
    if contract_intent not in _TRANSACTION_STORE_PREVIEW_RECOVERY_INTENTS and response_shape_key not in {
        "reservation_store_candidates",
        "stock_store_preview",
    }:
        return False

    contract_seed = turn_contract.contract_seed if isinstance(turn_contract.contract_seed, Mapping) else {}
    ui_action = contract_seed.get("ui_action") if isinstance(contract_seed.get("ui_action"), Mapping) else {}
    expected_intent = str(ui_action.get("expected_contract_intent") or "").strip()
    action_type = str(ui_action.get("action_type") or ui_action.get("cta_action") or "").strip()
    resume_source = str(getattr(turn_contract, "resume_source", "") or contract_seed.get("resume_source") or "").strip()
    action_mode = str(getattr(turn_contract, "action_mode", "") or "").strip()
    current_turn_grounded = (
        resume_source not in {"", "none"}
        or (action_type == "select_product" and expected_intent in {"quick_order_reservation", "stock_store_search"})
        or action_mode in {"purchase_continuation", "stock_check"}
    )
    if not current_turn_grounded:
        return False

    known_slots = _contract_read_through_known_slots(
        turn_contract,
        merged_slots,
        allowed_flow_types=frozenset({"purchase", "stock"}),
    )
    return bool(
        known_slots.get("goods_no")
        and known_slots.get("tire_size")
        and (known_slots.get("ord_qty") or known_slots.get("quantity"))
        and (
            known_slots.get("shop_id")
            or known_slots.get("shop_name")
            or known_slots.get("store_name")
            or known_slots.get("region")
        )
    )


def _contract_required_transaction_store_preview_tool_input(
    turn_contract: TurnContract,
    *,
    merged_slots: ConversationSlots | None = None,
) -> dict[str, Any]:
    if not _is_contract_required_transaction_store_preview(turn_contract, merged_slots=merged_slots):
        return {}
    known_slots = _contract_read_through_known_slots(
        turn_contract,
        merged_slots,
        allowed_flow_types=frozenset({"purchase", "stock"}),
    )
    tool_args_patch = (
        dict(turn_contract.tool_args_patch) if isinstance(getattr(turn_contract, "tool_args_patch", None), Mapping) else {}
    )
    tool_input = {str(key): value for key, value in {**known_slots, **tool_args_patch}.items() if value not in (None, "", [], {})}
    if tool_input.get("quantity") in (None, "", [], {}) and tool_input.get("ord_qty") not in (None, "", [], {}):
        tool_input["quantity"] = tool_input["ord_qty"]
    if tool_input.get("store_name") in (None, "", [], {}) and tool_input.get("shop_name") not in (None, "", [], {}):
        tool_input["store_name"] = tool_input["shop_name"]
    if tool_input.get("pending_intent") == "order" or tool_input.get("goal_type") == "place_order":
        tool_input["pending_intent"] = "order"
        tool_input["goal_type"] = "place_order"
        tool_input["sub_flow_type"] = "purchase"
        tool_input["stock_check_mode"] = "preview"
    return tool_input


def _contract_required_transaction_tool_input(
    *,
    turn_contract: TurnContract,
    preferred_tool: str,
    merged_slots: ConversationSlots | None = None,
) -> tuple[dict[str, Any], str, str] | None:
    if str(turn_contract.domain or "").strip().lower() != PolicyDomain.TRANSACTION.value:
        return None
    if preferred_tool == "transaction_store_preview_tool":
        preview_input = _contract_required_transaction_store_preview_tool_input(turn_contract, merged_slots=merged_slots)
        if preview_input:
            return preview_input, "turn_contract_required_transaction_store_preview", "장착 가능 매장 확인 중..."
        return None
    if preferred_tool in _OWNED_RECORD_RECOVERY_TOOLS:
        if str(turn_contract.intent or "").strip() not in _OWNED_RECORD_RECOVERY_INTENTS:
            return None
        if preferred_tool in {str(tool) for tool in tuple(turn_contract.forbidden_tools or ()) if str(tool).strip()}:
            return None
        tool_args_patch = (
            dict(turn_contract.tool_args_patch)
            if isinstance(getattr(turn_contract, "tool_args_patch", None), Mapping)
            else {}
        )
        tool_input = {str(key): value for key, value in tool_args_patch.items() if value not in (None, "", [], {})}
        if preferred_tool == "get_my_reservations_tool":
            tool_input.setdefault("sct_cd", "all")
            return tool_input, "turn_contract_required_owned_record_lookup", "예약 내역 조회 중..."
        if preferred_tool == "get_orders_of_user_tool":
            return tool_input, "turn_contract_required_owned_record_lookup", "주문 내역 조회 중..."
        if preferred_tool == "get_order_status_tool":
            if not tool_input.get("query_no"):
                return None
            return tool_input, "turn_contract_required_owned_record_lookup", "주문 현황 조회 중..."
        return None
    if preferred_tool and (
        preferred_tool in _FAST_PATH_TRANSACTION_RECOVERY_BLOCKLIST
        or preferred_tool not in _FAST_PATH_TRANSACTION_RECOVERY_ALLOWED_TOOLS
    ):
        return None
    if preferred_tool in {str(tool) for tool in tuple(turn_contract.forbidden_tools or ()) if str(tool).strip()}:
        return None

    if preferred_tool == "get_store_schedule_tool":
        schedule_input = _contract_required_selected_store_schedule_tool_input(turn_contract, merged_slots=merged_slots)
        if schedule_input:
            return schedule_input, "turn_contract_required_selected_store_schedule", "예약 가능 일정 확인 중..."
        return None

    if preferred_tool == "get_store_inventory_tool":
        inventory_input = _contract_required_stock_inventory_selected_store_tool_input(turn_contract, merged_slots=merged_slots)
        if inventory_input:
            return inventory_input, "turn_contract_required_stock_inventory_selected_store", "매장 재고 확인 중..."
        return None

    if preferred_tool in {"", "get_store_list_tool", "search_stores_tool"}:
        stock_store_input = _contract_required_stock_inventory_store_lookup_tool_input(
            turn_contract,
            merged_slots=merged_slots,
            preferred_tool=preferred_tool,
        )
        if stock_store_input:
            return stock_store_input, "turn_contract_required_stock_inventory_store_lookup", "매장 재고 조회 매장 확인 중..."

    response_decision = turn_contract.response_decision or {}
    response_metadata = response_decision.get("metadata") if isinstance(response_decision, Mapping) else {}
    tool_args_patch = response_metadata.get("tool_args_patch") if isinstance(response_metadata, Mapping) else None
    if not isinstance(tool_args_patch, Mapping):
        tool_args_patch = getattr(turn_contract, "tool_args_patch", None)
    if not isinstance(tool_args_patch, Mapping):
        tool_args_patch = turn_contract.known_slots.get("tool_args_patch")
    if not isinstance(tool_args_patch, Mapping):
        return None

    tool_input = {str(key): value for key, value in tool_args_patch.items() if value not in (None, "", [], {})}
    if not tool_input:
        return None
    if preferred_tool == "search_stores_tool":
        if not (
            tool_input.get("place_query")
            or tool_input.get("region_code")
            or tool_input.get("store_nm")
            or tool_input.get("shop_name")
            or tool_input.get("region")
        ):
            return None
        return tool_input, "turn_contract_required_store_search", "매장 검색 중..."
    if preferred_tool == "get_store_list_tool":
        if not (tool_input.get("store_nm") or tool_input.get("shop_name") or tool_input.get("region")):
            return None
        return tool_input, "turn_contract_required_tool_args_patch", "매장 정보 확인 중..."
    return None


def _contract_required_tool_candidate(
    *,
    turn_contract: TurnContract,
    user_text: str,
    merged_slots: ConversationSlots | None,
    member_no: str | None = None,
) -> _ContractRequiredToolCandidate | None:
    allowed_tools = tuple(str(tool) for tool in (turn_contract.allowed_tools or ()) if str(tool))
    forbidden_tools = {str(tool) for tool in (turn_contract.forbidden_tools or ()) if str(tool)}
    if not allowed_tools:
        return None

    known_slots = dict(turn_contract.known_slots or {})
    domain = str(turn_contract.domain or "").strip().lower()
    progress_candidate = _contract_required_tool_candidate_from_flow_progress(
        turn_contract=turn_contract,
        merged_slots=merged_slots,
        allowed_tools=allowed_tools,
        forbidden_tools=forbidden_tools,
        domain=domain,
    )
    if progress_candidate is not None:
        return progress_candidate
    preferred_tool = ""
    tool_input: dict[str, Any] = {}
    tool_input_source = ""
    display_name = "정보 확인 중..."
    source_domain = domain or "discovery"

    if domain == PolicyDomain.DISCOVERY.value:
        contract_required_recommendation_input = _contract_required_recommendation_tool_input(
            turn_contract=turn_contract,
            known_slots=known_slots,
            merged_slots=merged_slots,
        )
        contract_preferred_tool = str(getattr(turn_contract, "preferred_tool", None) or "").strip()
        if contract_preferred_tool and contract_preferred_tool in allowed_tools:
            preferred_tool = contract_preferred_tool
            tool_input = {
                key: value
                for key, value in dict(getattr(turn_contract, "tool_args_patch", {}) or {}).items()
                if value not in (None, "", [], {})
            }
            tool_input_source = "turn_contract_tool_args_patch" if tool_input else "turn_contract_preferred_tool"
            if preferred_tool == "get_products_recommendations_tool" and contract_required_recommendation_input:
                tool_input = dict(contract_required_recommendation_input)
                tool_input_source = "turn_contract_required_recommendation"
        discovery_known_slots = {
            key: value
            for key, value in {
                "tire_size": known_slots.get("tire_size") or getattr(merged_slots, "tire_size", None),
                "goods_no": known_slots.get("goods_no") or getattr(merged_slots, "goods_no", None),
                "vehicle_type": known_slots.get("vehicle_type") or getattr(merged_slots, "vehicle_type", None),
                "car_lnc_cd": known_slots.get("car_lnc_cd") or getattr(merged_slots, "car_lnc_cd", None),
                "brand_cd": known_slots.get("brand_cd"),
                "discovery_followup_action": known_slots.get("discovery_followup_action"),
                "pending_check_topic": known_slots.get("pending_check_topic"),
                "pending_check_object_type": known_slots.get("pending_check_object_type"),
                "pending_check_object_value": known_slots.get("pending_check_object_value"),
            }.items()
            if value not in (None, "")
        }
        if not preferred_tool:
            frame = build_discovery_intent_frame(user_text, known_slots=discovery_known_slots)
            tool_plan = plan_discovery_tools(frame)
            planned_preferred_tool = str(getattr(tool_plan, "preferred_tool", None) or "")
            if planned_preferred_tool and planned_preferred_tool in allowed_tools:
                preferred_tool = planned_preferred_tool
                tool_input = {
                    key: value
                    for key, value in dict(getattr(tool_plan, "tool_args_patch", {}) or {}).items()
                    if value not in (None, "", [], {})
                }
                tool_input_source = "discovery_tool_plan"
                if preferred_tool == "get_products_recommendations_tool" and contract_required_recommendation_input:
                    tool_input = dict(contract_required_recommendation_input)
                    tool_input_source = "turn_contract_required_recommendation"
        if not preferred_tool and len(allowed_tools) == 1:
            preferred_tool = allowed_tools[0]
            if preferred_tool == "get_products_recommendations_tool" and contract_required_recommendation_input:
                tool_input = dict(contract_required_recommendation_input)
                tool_input_source = "turn_contract_required_recommendation"

        if preferred_tool not in _FAST_PATH_DISCOVERY_RECOVERY_ALLOWED_TOOLS:
            return None
        if preferred_tool in forbidden_tools or preferred_tool in _FAST_PATH_TRANSACTION_RECOVERY_BLOCKLIST:
            return None

        if preferred_tool in {"search_product_summary_tool", "search_product_tool"}:
            product_names = extract_product_names(user_text)
            if preferred_tool == "search_product_summary_tool" and len(product_names) >= 2 and not tool_input:
                tool_input = {"keywords": list(product_names[:5]), "limit": 5}
                brand_cd = str(known_slots.get("brand_cd") or "").strip()
                if brand_cd:
                    tool_input["brand_cd"] = brand_cd
                tool_input_source = "current_turn_product_names"
            preferred_keyword = str(
                known_slots.get("pending_product_name")
                or known_slots.get("tire_model")
                or getattr(merged_slots, "pending_product_name", None)
                or getattr(merged_slots, "tire_model", None)
                or ""
            ).strip()
            if preferred_keyword:
                tool_input["keyword"] = preferred_keyword
            if not tool_input:
                keyword = preferred_keyword
                if not keyword:
                    keyword = str(product_names[0] if product_names else "").strip()
                if not keyword:
                    return None
                tool_input = {"keyword": keyword, "limit": 10}
                brand_cd = str(known_slots.get("brand_cd") or "").strip()
                if brand_cd:
                    tool_input["brand_cd"] = brand_cd
                tire_size = normalize_tire_size(str(known_slots.get("tire_size") or ""))
                if tire_size:
                    tool_input["size"] = tire_size
                tool_input_source = tool_input_source or "known_slots"
            if preferred_tool == "search_product_summary_tool":
                tool_input.pop("size", None)
                tool_input.setdefault("limit", 5)
                display_name = "상품 정보 확인 중..."
            else:
                display_name = "상품 검색 중..."
        elif preferred_tool == "get_product_description_tool":
            if not tool_input:
                goods_no = str(known_slots.get("goods_no") or getattr(merged_slots, "goods_no", None) or "").strip()
                if not goods_no:
                    return None
                tool_input = {"goods_no": goods_no}
                tool_input_source = "known_slots"
            display_name = "상품 정보 확인 중..."
        elif preferred_tool == "get_best_selling_products_tool":
            if not tool_input:
                tool_input = _best_seller_tool_input_from_text(user_text, limit=5, known_slots=known_slots)
                tool_input_source = "user_text"
            display_name = "인기 상품 조회 중..."
        elif preferred_tool == "get_my_cars_tool":
            member_no_value = str(member_no or "").strip()
            if not member_no_value:
                return None
            tool_input = {"mbr_no": member_no_value}
            tool_input_source = "user_context"
            display_name = "등록 차량 조회 중..."
        elif preferred_tool == "get_events_tool":
            tool_input.setdefault("lang_cd", "ko")
            tool_input_source = tool_input_source or "contract_tool_plan"
            display_name = "이벤트/기획전 조회 중..."
        elif preferred_tool == "get_product_applicable_events_tool":
            ptrn_cd = str(known_slots.get("ptrn_cd") or "").strip()
            if ptrn_cd:
                tool_input = {"ptrn_cd": ptrn_cd, "lang_cd": "ko"}
                tool_input_source = "known_slots"
            if not tool_input:
                return None
            display_name = "상품 적용 이벤트 조회 중..."
        elif preferred_tool == "get_event_applicable_products_tool":
            if not tool_input:
                return None
            display_name = "이벤트 적용 상품 조회 중..."
        elif preferred_tool == "get_products_recommendations_tool":
            if str(turn_contract.intent or "").strip() != "product_recommendation":
                return None
            if not tool_input:
                tool_input = dict(contract_required_recommendation_input)
                tool_input_source = tool_input_source or "turn_contract_required_recommendation"
            if not tool_input:
                return None
            tool_input.setdefault("rcmd_type", "tstation")
            display_name = "추천 상품 확인 중..."
    elif domain == PolicyDomain.SUPPORT.value:
        contract_preferred_tool = str(getattr(turn_contract, "preferred_tool", None) or "").strip()
        if contract_preferred_tool and contract_preferred_tool in allowed_tools:
            preferred_tool = contract_preferred_tool
        elif len(allowed_tools) == 1:
            preferred_tool = allowed_tools[0]
        if preferred_tool in forbidden_tools:
            return None
        if str(turn_contract.intent or "") not in _DIRECT_SUPPORT_FAQ_POLICY_INTENTS:
            return None
        if preferred_tool == "search_faq_hybrid_tool":
            tool_input = {"query": user_text, "top_k": 8}
            tool_input_source = "user_text"
            display_name = "FAQ 확인 중..."
        elif preferred_tool == "get_card_installments_tool":
            tool_input = {"payment_type": _card_installment_payment_type_from_text(user_text)}
            tgt_amt = _card_installment_amount_from_text(user_text)
            if tgt_amt is not None:
                tool_input["tgt_amt"] = tgt_amt
            tool_input_source = "user_text"
            display_name = "무이자 할부 카드 조회 중..."
        else:
            return None
    elif domain == PolicyDomain.TRANSACTION.value:
        contract_preferred_tool = str(getattr(turn_contract, "preferred_tool", None) or "").strip()
        if contract_preferred_tool and contract_preferred_tool in allowed_tools and contract_preferred_tool not in forbidden_tools:
            preferred_tool = contract_preferred_tool
        elif len(allowed_tools) == 1:
            preferred_tool = allowed_tools[0]
        if not preferred_tool:
            planned_tool_plan = current_transaction_tool_plan.get()
            planned_preferred_tool = str(getattr(planned_tool_plan, "preferred_tool", None) or "").strip()
            if planned_preferred_tool in allowed_tools and planned_preferred_tool not in forbidden_tools:
                preferred_tool = planned_preferred_tool
        contract_required_tool_input = _contract_required_transaction_tool_input(
            turn_contract=turn_contract,
            preferred_tool=preferred_tool,
            merged_slots=merged_slots,
        )
        if contract_required_tool_input is None:
            return None
        tool_input, tool_input_source, display_name = contract_required_tool_input
        if not preferred_tool and tool_input_source == "turn_contract_required_stock_inventory_store_lookup":
            preferred_tool = "get_store_list_tool"
        source_domain = PolicyDomain.TRANSACTION.value
    else:
        return None

    if not preferred_tool:
        return None
    if not tool_input and preferred_tool not in {"get_orders_of_user_tool", "get_my_reservations_tool"}:
        return None
    if preferred_tool in _FAST_PATH_TRANSACTION_RECOVERY_BLOCKLIST and not (
        preferred_tool == "transaction_store_preview_tool"
        and _is_contract_required_transaction_store_preview(turn_contract, merged_slots=merged_slots)
    ):
        return None
    return _ContractRequiredToolCandidate(
        tool_name=preferred_tool,
        tool_input=tool_input,
        tool_input_source=tool_input_source or "contract_tool_plan",
        display_name=display_name,
        source_domain=source_domain,
    )


def _contract_required_tool_candidate_from_flow_progress(
    *,
    turn_contract: TurnContract,
    merged_slots: ConversationSlots | None,
    allowed_tools: tuple[str, ...],
    forbidden_tools: set[str],
    domain: str,
) -> _ContractRequiredToolCandidate | None:
    availability_context = getattr(merged_slots, "availability_context", None) if merged_slots is not None else None
    active_flow_context = (
        availability_context.get("active_flow_context")
        if isinstance(availability_context, Mapping)
        and isinstance(availability_context.get("active_flow_context"), Mapping)
        else {}
    )
    progress = flow_progress_from_active_context(
        active_flow_context,
        allowed_flow_types=frozenset({"stock", "purchase", "store_schedule"}),
    )
    if not progress:
        return None
    contract_intent = str(turn_contract.intent or "").strip()
    response_decision = turn_contract.response_decision or {}
    response_metadata = response_decision.get("metadata") if isinstance(response_decision, Mapping) else {}
    response_shape_key = str(response_metadata.get("response_shape_key") or "") if isinstance(response_metadata, Mapping) else ""
    next_tool = str(progress.get("next_tool") or "").strip()
    progress_allowed_tools = tuple(
        str(tool)
        for tool in tuple(progress.get("allowed_tools") or ())
        if str(tool).strip()
    )
    candidate_allowed_tools = progress_allowed_tools or allowed_tools
    candidate_domain = domain
    candidate_intent = contract_intent
    candidate_shape = response_shape_key
    flow_type = str(progress.get("sub_flow_type") or progress.get("flow_type") or "").strip()
    if next_tool in _FLOW_PROGRESS_TRANSACTION_TOOLS:
        candidate_domain = PolicyDomain.TRANSACTION.value
        if domain != PolicyDomain.TRANSACTION.value:
            if flow_type == "stock":
                candidate_intent = "stock_store_search"
                candidate_shape = candidate_shape or "stock_inventory_lookup"
            elif flow_type == "store_schedule":
                candidate_intent = "store_schedule"
                candidate_shape = candidate_shape or "reservation_slots"
            elif flow_type == "purchase":
                candidate_intent = "quick_order_reservation"
                candidate_shape = candidate_shape or "reservation_store_candidates"
    candidate = flow_progress_tool_candidate(
        progress,
        domain=candidate_domain,
        contract_intent=candidate_intent,
        response_shape_key=candidate_shape,
        allowed_tools=candidate_allowed_tools,
        forbidden_tools=forbidden_tools,
    )
    if not candidate:
        return None
    next_tool = str(candidate.get("tool_name") or "").strip()
    source_domain = str(candidate.get("source_domain") or candidate_domain or domain)
    if (
        source_domain == PolicyDomain.TRANSACTION.value
        and next_tool in _FAST_PATH_TRANSACTION_RECOVERY_BLOCKLIST
        and next_tool != "get_final_price_tool"
    ):
        return None
    return _ContractRequiredToolCandidate(
        tool_name=next_tool,
        tool_input=dict(candidate.get("tool_input") or {}),
        tool_input_source=str(candidate.get("tool_input_source") or "flow_state_progress"),
        display_name=str(candidate.get("display_name") or "정보 확인 중..."),
        source_domain=source_domain,
    )
