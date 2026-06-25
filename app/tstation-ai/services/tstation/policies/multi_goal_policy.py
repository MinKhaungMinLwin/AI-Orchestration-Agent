"""Lightweight multi-goal metadata for TurnContract/QC interpretation.

This module does not execute goals. It only describes clearly composite turns so
contract and QC guards can interpret prerequisite tools and same-turn produced
slots without treating them as drift.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

_OWN_VEHICLE_RE = re.compile(
    r"내\s*차에\s*(?:맞|적합)|내차에\s*(?:맞|적합)|"
    r"내\s*차\s*기준|내차\s*기준|내\s*차량\s*기준|내차량\s*기준|"
    r"내\s*차로\s*(?:추천|확인)|내차로\s*(?:추천|확인)",
    re.IGNORECASE,
)
_RECOMMEND_RE = re.compile(r"추천|찾|골라|보여|알려", re.IGNORECASE)
_COMPARE_RE = re.compile(r"비교|장단점|차이|뭐가\s*달라|각각", re.IGNORECASE)

_GOAL_DEFINITIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "resolve_vehicle": {
        "required_slots": ("mbr_no",),
        "produced_slots": ("vehicle", "tire_size"),
        "allowed_tools": ("get_my_cars_tool",),
    },
    "recommend_products": {
        "required_slots": ("tire_size",),
        "produced_slots": ("product_set",),
        "allowed_tools": ("get_products_recommendations_tool",),
    },
    "compare_products": {
        "required_slots": ("product_set",),
        "produced_slots": ("comparison_summary",),
        "allowed_tools": ("get_product_description_tool",),
    },
    "resolve_store": {
        "required_slots": ("store_query",),
        "produced_slots": ("store", "shop_id", "shop_name"),
        "allowed_tools": ("get_store_list_tool", "get_nearby_stores_tool", "get_favorite_stores_tool"),
    },
    "answer_store_attribute": {
        "required_slots": ("store",),
        "produced_slots": ("store_attribute_answer",),
        "allowed_tools": ("get_store_detail_tool",),
    },
    "resolve_tire_size": {
        "required_slots": ("product_name",),
        "produced_slots": ("tire_size",),
        "allowed_tools": ("search_product_tool",),
    },
    "resolve_product": {
        "required_slots": ("product_name", "tire_size"),
        "produced_slots": ("product", "goods_no", "product_name"),
        "allowed_tools": ("search_product_tool", "get_product_description_tool"),
    },
    "resolve_order": {
        "required_slots": ("member",),
        "produced_slots": ("order", "ord_no"),
        "allowed_tools": ("get_orders_of_user_tool",),
    },
    "answer_order_status": {
        "required_slots": ("order",),
        "produced_slots": ("order_status",),
        "allowed_tools": ("get_order_status_tool", "get_orders_of_user_tool"),
    },
}


def build_goal_steps(
    *,
    user_text: str,
    domain: str,
    intent: str,
    sub_intent: str | None = None,
    known_slots: Mapping[str, Any] | None = None,
    required_slots: tuple[str, ...] = (),
    execution_plan: tuple[str, ...] = (),
    tool_plan_metadata: Mapping[str, Any] | None = None,
    response_metadata: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return ordered goal metadata for the first narrow multi-goal rollout."""

    _ = domain
    metadata_steps = _normalize_metadata_goal_steps(tool_plan_metadata) or _normalize_metadata_goal_steps(
        response_metadata
    )
    if metadata_steps:
        return metadata_steps

    text = user_text or ""
    slots = known_slots or {}
    normalized_intent = str(intent or "")
    normalized_sub_intent = str(sub_intent or "")
    plan_text = " ".join(str(item or "").lower() for item in execution_plan)
    steps: list[str] = []

    if _is_vehicle_recommendation_goal(text, normalized_intent, normalized_sub_intent, plan_text, slots):
        steps.extend(["resolve_vehicle", "recommend_products"])
        if _COMPARE_RE.search(text) or "compare" in plan_text or "comparison" in plan_text:
            steps.append("compare_products")
    elif _is_recommend_then_compare_goal(text, normalized_intent, plan_text):
        steps.extend(["recommend_products", "compare_products"])

    if _is_store_attribute_goal(normalized_intent, slots, plan_text):
        steps = _append_goal_pair(steps, "resolve_store", "answer_store_attribute")

    if _is_product_resolution_after_size_goal(normalized_intent, slots, required_slots, plan_text):
        steps = _append_goal_pair(steps, "resolve_tire_size", "resolve_product")

    if _is_order_status_goal(normalized_intent, plan_text):
        steps = _append_goal_pair(steps, "resolve_order", "answer_order_status")

    return tuple(_goal_payload(seq, goal) for seq, goal in enumerate(steps, start=1))


def turn_complexity(goal_steps: tuple[Mapping[str, Any], ...]) -> str:
    return "multi_goal" if len(goal_steps) >= 2 else "simple"


def allowed_tools_from_goal_steps(goal_steps: tuple[Mapping[str, Any], ...]) -> tuple[str, ...]:
    return _tuple_from_steps(goal_steps, "allowed_tools")


def produced_slots_from_goal_steps(goal_steps: tuple[Mapping[str, Any], ...]) -> tuple[str, ...]:
    return _tuple_from_steps(goal_steps, "produced_slots")


def produced_slots_for_called_tools(
    goal_steps: tuple[Mapping[str, Any], ...],
    called_tools: tuple[str, ...],
) -> tuple[str, ...]:
    called = {str(tool) for tool in called_tools if str(tool).strip()}
    produced: list[str] = []
    for step in goal_steps:
        allowed = {str(tool) for tool in step.get("allowed_tools") or () if str(tool).strip()}
        if not allowed or not called.intersection(allowed):
            continue
        for slot in step.get("produced_slots") or ():
            text = str(slot or "").strip()
            if text and text not in produced:
                produced.append(text)
    return tuple(produced)


def _is_vehicle_recommendation_goal(
    text: str,
    intent: str,
    sub_intent: str,
    plan_text: str,
    slots: Mapping[str, Any],
) -> bool:
    if not (_OWN_VEHICLE_RE.search(text) or slots.get("requires_vehicle_resolution")):
        return False
    if intent == "product_recommendation" or sub_intent == "vehicle_based_recommendation_refinement":
        return True
    return bool("recommend" in plan_text or _RECOMMEND_RE.search(text))


def _is_recommend_then_compare_goal(text: str, intent: str, plan_text: str) -> bool:
    has_recommend = intent == "product_recommendation" or "recommend" in plan_text or _RECOMMEND_RE.search(text)
    has_compare = "compare" in plan_text or "comparison" in plan_text or _COMPARE_RE.search(text)
    return bool(has_recommend and has_compare)


def _is_store_attribute_goal(intent: str, slots: Mapping[str, Any], plan_text: str) -> bool:
    return (
        intent == "store_attribute_inquiry"
        or str(slots.get("goal_type") or "") == "store_attribute_inquiry"
        or "answer_store_attribute" in plan_text
        or "store_attribute" in plan_text
    )


def _is_product_resolution_after_size_goal(
    intent: str,
    slots: Mapping[str, Any],
    required_slots: tuple[str, ...],
    plan_text: str,
) -> bool:
    has_product_hint = bool(slots.get("product_name") or slots.get("tire_model") or slots.get("product_family_names"))
    requires_size = "tire_size" in required_slots or "resolve_tire_size" in plan_text
    return has_product_hint and requires_size and (
        intent in {"resolve_or_describe_product", "product_search", "price_or_coupon_check"}
        or "resolve_product" in plan_text
    )


def _is_order_status_goal(intent: str, plan_text: str) -> bool:
    return intent in {"order_cancel_status_lookup", "order_arrival_status_lookup", "reservation_status_lookup"} or (
        "resolve_order" in plan_text and ("order_status" in plan_text or "answer_order_status" in plan_text)
    )


def _append_goal_pair(steps: list[str], first: str, second: str) -> list[str]:
    for goal in (first, second):
        if goal not in steps:
            steps.append(goal)
    return steps


def _goal_payload(seq: int, goal: str) -> dict[str, Any]:
    definition = _GOAL_DEFINITIONS.get(goal, {})
    return {
        "seq": seq,
        "goal": goal,
        "required_slots": list(definition.get("required_slots") or ()),
        "produced_slots": list(definition.get("produced_slots") or ()),
        "allowed_tools": list(definition.get("allowed_tools") or ()),
    }


def _tuple_from_steps(goal_steps: tuple[Mapping[str, Any], ...], field: str) -> tuple[str, ...]:
    values: list[str] = []
    for step in goal_steps:
        for item in step.get(field) or ():
            text = str(item or "").strip()
            if text and text not in values:
                values.append(text)
    return tuple(values)


def _normalize_metadata_goal_steps(metadata: Mapping[str, Any] | None) -> tuple[dict[str, Any], ...]:
    if not isinstance(metadata, Mapping):
        return ()
    raw_steps = metadata.get("goal_steps")
    if not isinstance(raw_steps, list | tuple):
        return ()
    steps: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, Mapping):
            continue
        goal = str(raw.get("goal") or "").strip()
        if goal not in _GOAL_DEFINITIONS:
            continue
        payload = _goal_payload(index, goal)
        for key in ("required_slots", "produced_slots", "allowed_tools"):
            value = raw.get(key)
            if isinstance(value, list | tuple):
                payload[key] = [str(item) for item in value if str(item).strip()]
        steps.append(payload)
    return tuple(steps)
