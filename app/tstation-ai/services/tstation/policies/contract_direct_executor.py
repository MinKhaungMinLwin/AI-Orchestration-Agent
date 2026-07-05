"""Eligibility policy for skipping a domain-agent LLM after TurnContract."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from services.tstation.policies.intent_frame import PolicyDomain
from services.tstation.policies.turn_contract import TurnContract


_MIN_ROUTER_CONFIDENCE = 0.7
_DIRECT_TEMPLATE_TOOLS = frozenset({
    "get_my_cars_tool",
    "get_products_recommendations_tool",
    "search_product_summary_tool",
    "get_my_coupons_tool",
    "search_benefit_applicable_products_tool",
    "search_stores_tool",
    "search_stores_complex_tool",
    "get_store_list_tool",
    "get_nearby_stores_tool",
    "transaction_store_preview_tool",
    "get_store_schedule_tool",
    "get_final_price_tool",
    "get_my_reservations_tool",
    "get_orders_of_user_tool",
})
_COMPLEX_EXPLANATION_RE = re.compile(
    r"왜|이유|설명|자세히|장단점|비교|차이|정책|규정|불만|오류|에러|문제|안\s*되|안되|고장|환불|교환|보증",
    re.IGNORECASE,
)
_DIRECT_PRIMARY_ACTIONS = frozenset({
    "recommend",
    "search",
    "lookup",
    "compare",
    "book",
    "reserve",
    "coupon_lookup",
    "coupon_use",
    "use_coupon",
})


@dataclass(frozen=True)
class DirectPathDecision:
    checked: bool
    eligible: bool
    reason: str | None = None
    fallback_reason: str | None = None
    tool: str | None = None
    template: str | None = None

    def metadata(self) -> dict[str, Any]:
        return {
            "direct_path_checked": self.checked,
            "direct_path_eligible": self.eligible,
            "direct_path_reason": self.reason,
            "domain_agent_llm_skipped": self.eligible,
            "direct_tool": self.tool,
            "direct_template": self.template,
            "fallback_reason": self.fallback_reason,
        }


def evaluate_contract_direct_path(
    *,
    turn_contract: TurnContract | None,
    router_evidence: Mapping[str, Any] | None,
    user_text: str,
) -> DirectPathDecision:
    if turn_contract is None:
        return _fallback("missing_turn_contract")
    domain = str(turn_contract.domain or "").strip().lower()
    if domain not in {PolicyDomain.DISCOVERY.value, PolicyDomain.TRANSACTION.value}:
        return _fallback("support_policy_question")
    if (
        _router_confidence(router_evidence) < _MIN_ROUTER_CONFIDENCE
        and not _is_deterministic_benefit_applicable_products_contract(turn_contract)
    ):
        return _fallback("low_router_confidence")
    primary_action = str((router_evidence or {}).get("primary_action") or "").strip()
    if primary_action not in _DIRECT_PRIMARY_ACTIONS:
        return _fallback("unclear_primary_action")
    if _COMPLEX_EXPLANATION_RE.search(user_text or ""):
        if "비교" in str(user_text or ""):
            if str(getattr(turn_contract, "intent", "") or "") != "product_comparison":
                return _fallback("comparison_requires_llm")
        else:
            return _fallback("complex_explanation_request")
    if tuple(getattr(turn_contract, "blocking_required_slots", ()) or ()):
        return _fallback("missing_required_slot")
    preferred_tool = str(getattr(turn_contract, "preferred_tool", "") or "").strip()
    allowed_tools = tuple(str(tool) for tool in tuple(turn_contract.allowed_tools or ()) if str(tool).strip())
    forbidden_tools = {str(tool) for tool in tuple(turn_contract.forbidden_tools or ()) if str(tool).strip()}
    if preferred_tool and preferred_tool in forbidden_tools:
        return _fallback("contract_tool_conflict")
    clear_tool = preferred_tool if preferred_tool in allowed_tools else _default_contract_tool(
        turn_contract=turn_contract,
        allowed_tools=allowed_tools,
        forbidden_tools=forbidden_tools,
    )
    if not clear_tool:
        return _fallback("ambiguous_contract_tool")
    if clear_tool not in _DIRECT_TEMPLATE_TOOLS:
        return _fallback("no_deterministic_template")

    known_slots = turn_contract.known_slots or {}
    response_decision = turn_contract.response_decision or {}
    template = str(response_decision.get("template") or "").strip()
    if not template or template == "none":
        template = _template_for_tool(clear_tool)
    if not template:
        return _fallback("no_deterministic_template")

    if domain == PolicyDomain.DISCOVERY.value:
        return _evaluate_discovery_contract(
            turn_contract=turn_contract,
            router_evidence=router_evidence or {},
            tool=clear_tool,
            template=template,
            known_slots=known_slots,
        )
    return _evaluate_transaction_contract(
        turn_contract=turn_contract,
        router_evidence=router_evidence or {},
        tool=clear_tool,
        template=template,
        known_slots=known_slots,
    )


def _default_contract_tool(
    *,
    turn_contract: TurnContract,
    allowed_tools: tuple[str, ...],
    forbidden_tools: set[str],
) -> str:
    intent = str(turn_contract.intent or "").strip()
    preferred_by_intent = {
        "store_search": "get_store_list_tool",
        "open_store_search": "search_stores_complex_tool",
        "store_service_search": "search_stores_tool",
        "stock_store_search": "transaction_store_preview_tool",
        "price_or_coupon_check": "get_final_price_tool",
        "store_schedule": "get_store_schedule_tool",
        "selected_store_schedule": "get_store_schedule_tool",
        "reservation_status_lookup": "get_my_reservations_tool",
        "reservation_store_info_lookup": "get_my_reservations_tool",
        "order_history_lookup": "get_orders_of_user_tool",
    }
    preferred = preferred_by_intent.get(intent)
    if preferred and preferred in allowed_tools and preferred not in forbidden_tools:
        return preferred
    if len(allowed_tools) == 1 and allowed_tools[0] not in forbidden_tools:
        return allowed_tools[0]
    return ""


def _evaluate_discovery_contract(
    *,
    turn_contract: TurnContract,
    router_evidence: Mapping[str, Any],
    tool: str,
    template: str,
    known_slots: Mapping[str, Any],
) -> DirectPathDecision:
    intent = str(turn_contract.intent or "")
    if intent == "product_comparison" and tool == "search_product_summary_tool":
        return DirectPathDecision(True, True, "product_comparison_summary", None, tool, "quickReply")
    if intent == "event_applicable_products_lookup" and tool == "search_benefit_applicable_products_tool":
        query = str(
            (turn_contract.tool_args_patch or {}).get("query")
            or known_slots.get("benefit_applicable_products_query")
            or ""
        ).strip()
        if query:
            return DirectPathDecision(True, True, "event_applicable_products_lookup", None, tool, "quickReply")
        return _fallback("missing_required_slot")
    if intent != "product_recommendation":
        return _fallback("no_deterministic_template")
    if tool == "get_my_cars_tool":
        registered_vehicle = _entity(router_evidence, "registered_vehicle")
        anchor = str(registered_vehicle.get("anchor") or known_slots.get("named_registered_vehicle_anchor") or "").strip()
        allowed = set(str(item) for item in tuple(turn_contract.allowed_tools or ()) if str(item))
        if not anchor:
            return _fallback("missing_required_slot")
        if "get_products_recommendations_tool" not in allowed:
            return _fallback("contract_tool_conflict")
        return DirectPathDecision(True, True, "registered_vehicle_recommendation", None, tool, "product")
    if tool == "get_products_recommendations_tool":
        if known_slots.get("tire_size") or known_slots.get("car_lnc_cd"):
            return DirectPathDecision(True, True, "sized_product_recommendation", None, tool, template)
        return _fallback("missing_required_slot")
    return _fallback("no_deterministic_template")


def _evaluate_transaction_contract(
    *,
    turn_contract: TurnContract,
    router_evidence: Mapping[str, Any],
    tool: str,
    template: str,
    known_slots: Mapping[str, Any],
) -> DirectPathDecision:
    intent = str(turn_contract.intent or "").strip()
    if intent in {"store_search", "open_store_search", "store_service_search"} and tool in {
        "search_stores_tool",
        "search_stores_complex_tool",
        "get_store_list_tool",
        "get_nearby_stores_tool",
    }:
        if known_slots.get("place_query") or known_slots.get("region") or known_slots.get("store_name"):
            return DirectPathDecision(True, True, "store_search", None, tool, "location")
        return _fallback("missing_required_slot")
    if intent in {"store_schedule", "selected_store_schedule"} and tool == "get_store_schedule_tool":
        if known_slots.get("shop_id") or (turn_contract.tool_args_patch or {}).get("shop_id"):
            return DirectPathDecision(True, True, "store_schedule", None, tool, "datepick")
        return _fallback("missing_required_slot")
    if tool == "get_store_schedule_tool" and _is_reservation_datepick_contract(turn_contract):
        if known_slots.get("shop_id") or (turn_contract.tool_args_patch or {}).get("shop_id"):
            return DirectPathDecision(True, True, "reservation_schedule", None, tool, "datepick")
        return _fallback("missing_required_slot")
    if tool == "transaction_store_preview_tool" and intent in {
        "quick_order_reservation",
        "quick_order_with_product_and_quantity",
        "stock_store_search",
    }:
        tool_args_patch = turn_contract.tool_args_patch or {}
        has_quantity = known_slots.get("ord_qty") or known_slots.get("quantity") or tool_args_patch.get("ord_qty")
        has_location = (
            known_slots.get("shop_id")
            or known_slots.get("shop_name")
            or known_slots.get("store_name")
            or known_slots.get("region")
            or known_slots.get("place_query")
            or tool_args_patch.get("shop_id")
            or tool_args_patch.get("shop_name")
            or tool_args_patch.get("store_name")
            or tool_args_patch.get("region")
            or tool_args_patch.get("place_query")
        )
        if known_slots.get("goods_no") and known_slots.get("tire_size") and has_quantity and has_location:
            return DirectPathDecision(True, True, "transaction_store_preview", None, tool, "location")
        return _fallback("missing_required_slot")
    if intent == "price_or_coupon_check" and tool == "get_final_price_tool":
        if known_slots.get("goods_no") or (turn_contract.tool_args_patch or {}).get("goods_no"):
            return DirectPathDecision(True, True, "price_or_coupon_check", None, tool, "quickReply")
        return _fallback("missing_required_slot")
    if intent in {"reservation_status_lookup", "reservation_store_info_lookup"} and tool == "get_my_reservations_tool":
        return DirectPathDecision(True, True, "reservation_lookup", None, tool, "quickReply")
    if intent == "order_history_lookup" and tool == "get_orders_of_user_tool":
        return DirectPathDecision(True, True, "order_lookup", None, tool, "quickReply")
    if intent == "coupon_applicable_products" and tool == "search_benefit_applicable_products_tool":
        query = str(
            (turn_contract.tool_args_patch or {}).get("query")
            or known_slots.get("benefit_applicable_products_query")
            or ""
        ).strip()
        if query:
            return DirectPathDecision(True, True, "benefit_applicable_products_lookup", None, tool, "quickReply")
        return _fallback("missing_required_slot")
    if tool == "get_my_coupons_tool":
        if str((router_evidence or {}).get("domain") or "").strip() == PolicyDomain.SUPPORT.value:
            return _fallback("support_policy_question")
        return DirectPathDecision(True, True, "coupon_lookup", None, tool, "voucher")
    return _fallback("no_deterministic_template")


def _fallback(reason: str) -> DirectPathDecision:
    return DirectPathDecision(True, False, None, reason, None, None)


def _is_reservation_datepick_contract(turn_contract: TurnContract) -> bool:
    response_decision = turn_contract.response_decision or {}
    metadata = response_decision.get("metadata") if isinstance(response_decision, Mapping) else None
    response_shape_key = str(metadata.get("response_shape_key") or "") if isinstance(metadata, Mapping) else ""
    return str(response_decision.get("template") or "") == "datepick" and response_shape_key == "reservation_slots"

def _router_confidence(router_evidence: Mapping[str, Any] | None) -> float:
    try:
        return float((router_evidence or {}).get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _entity(router_evidence: Mapping[str, Any], name: str) -> dict[str, Any]:
    entities = router_evidence.get("entities") if isinstance(router_evidence.get("entities"), Mapping) else {}
    entity = entities.get(name) if isinstance(entities, Mapping) else {}
    return dict(entity) if isinstance(entity, Mapping) else {}


def _is_deterministic_benefit_applicable_products_contract(turn_contract: TurnContract) -> bool:
    domain = str(turn_contract.domain or "").strip().lower()
    intent = str(turn_contract.intent or "").strip()
    preferred_tool = str(getattr(turn_contract, "preferred_tool", "") or "").strip()
    allowed_tools = set(turn_contract.allowed_tools or ())
    if preferred_tool != "search_benefit_applicable_products_tool" or preferred_tool not in allowed_tools:
        return False
    if domain == PolicyDomain.DISCOVERY.value and intent == "event_applicable_products_lookup":
        query = str(
            (turn_contract.tool_args_patch or {}).get("query")
            or (turn_contract.known_slots or {}).get("benefit_applicable_products_query")
            or ""
        ).strip()
        return bool(query)
    return (
        domain == PolicyDomain.TRANSACTION.value
        and intent == "coupon_applicable_products"
    )


def _template_for_tool(tool: str) -> str:
    return {
        "get_my_cars_tool": "listCar",
        "get_products_recommendations_tool": "product",
        "get_my_coupons_tool": "voucher",
        "search_benefit_applicable_products_tool": "quickReply",
        "search_stores_tool": "location",
        "search_stores_complex_tool": "location",
        "get_store_list_tool": "location",
        "get_nearby_stores_tool": "location",
        "get_store_schedule_tool": "datepick",
        "get_final_price_tool": "quickReply",
        "get_my_reservations_tool": "quickReply",
        "get_orders_of_user_tool": "quickReply",
    }.get(tool, "")
