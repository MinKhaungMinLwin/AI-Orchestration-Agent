"""Current-turn installation schedule validation for preOrder rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from schemas.tstation.chat import TStationChatRequest
from schemas.tstation.slots import ConversationSlots
from services.tstation.chat_v3.router.schemas import RouteDecision

AVAILABILITY_TOOL = "get_store_install_availability_tool"
_SCHEDULE_FIELDS = frozenset({"requested_cal_day", "rsv_hour"})
_SCHEDULE_ACTIONS = frozenset({"select_schedule"})
_PREORDER_SOURCE_TOOLS = frozenset({"present_order_preview_tool", "get_final_price_tool"})


@dataclass(frozen=True)
class ScheduleEvidence:
    checked: bool = False
    available: bool = False
    reason: str = "not_checked"


def schedule_completed_this_turn(
    request: TStationChatRequest,
    decision: RouteDecision | None,
) -> bool:
    patch = decision.slots_patch.non_empty() if decision and decision.slots_patch else {}
    if _SCHEDULE_FIELDS.intersection(patch):
        return True
    ui_action = request.ui_action if isinstance(request.ui_action, Mapping) else {}
    action = str(ui_action.get("action_type") or ui_action.get("cta_action") or "").strip()
    return action in _SCHEDULE_ACTIONS


def needs_preorder_schedule_validation(
    request: TStationChatRequest,
    decision: RouteDecision | None,
    slots: ConversationSlots,
    tool_calls: Sequence[Mapping[str, Any]] = (),
) -> bool:
    has_preorder_source = any(
        str(call.get("name") or "") in _PREORDER_SOURCE_TOOLS
        for call in tool_calls
    )
    return bool(
        (schedule_completed_this_turn(request, decision) or has_preorder_source)
        and slots.goods_no
        and slots.shop_id
        and slots.ord_qty
        and slots.requested_cal_day
        and slots.rsv_hour
        and (slots.pending_intent == "order" or slots.goal_type == "place_order")
    )


def is_schedule_ui_selection(request: TStationChatRequest) -> bool:
    ui_action = request.ui_action if isinstance(request.ui_action, Mapping) else {}
    action = str(ui_action.get("action_type") or ui_action.get("cta_action") or "").strip()
    return action in _SCHEDULE_ACTIONS


def availability_args(slots: ConversationSlots) -> dict[str, Any]:
    return {
        "shop_id_list": [str(slots.shop_id)],
        "goods_no": str(slots.goods_no),
        "ord_qty": int(slots.ord_qty or 1),
        "requested_cal_day": str(slots.requested_cal_day),
    }


def current_turn_evidence(
    tool_calls: Sequence[Mapping[str, Any]],
    slots: ConversationSlots,
) -> ScheduleEvidence:
    for call in reversed(tool_calls):
        if str(call.get("name") or "") != AVAILABILITY_TOOL:
            continue
        return _evidence_from_payload(call.get("output"), slots)
    return ScheduleEvidence()


def context_evidence(
    context_items: Sequence[Mapping[str, Any]],
    slots: ConversationSlots,
) -> ScheduleEvidence:
    for item in context_items:
        if str(item.get("tool") or "") != AVAILABILITY_TOOL:
            continue
        evidence = _evidence_from_payload(item.get("data"), slots)
        if evidence.checked:
            return evidence
    return ScheduleEvidence()


def validation_answer(slots: ConversationSlots, evidence: ScheduleEvidence) -> str:
    shop_name = str(slots.shop_name or "선택하신 매장")
    day = str(slots.requested_cal_day or "")
    hour = _normalized_hour(slots.rsv_hour)
    date_label = f"{day[:4]}년 {day[4:6]}월 {day[6:8]}일" if len(day) == 8 and day.isdigit() else day
    time_label = f"{hour}시" if hour else "선택하신 시간"
    if evidence.available:
        return f"{shop_name}에서 {date_label} {time_label} 장착 가능 여부를 확인했어요. 주문 정보를 확인해 주세요."
    if evidence.reason == "no_inventory":
        return (
            f"{shop_name}에는 요청하신 상품의 재고가 없어 {date_label} {time_label} 장착이 어렵습니다. "
            "다른 매장이나 날짜로 찾아드릴까요?"
        )
    if evidence.reason == "tool_error":
        return "장착 가능 여부를 확인하지 못해 주문 확인 단계로 진행하지 않았어요. 잠시 후 다시 확인해 주세요."
    return (
        f"{shop_name}에서 {date_label} {time_label}에는 장착 가능한 일정이 확인되지 않았어요. "
        "다른 시간이나 매장을 찾아드릴까요?"
    )


def _evidence_from_payload(raw: Any, slots: ConversationSlots) -> ScheduleEvidence:
    payload = _parse_payload(raw)
    if payload is None:
        return ScheduleEvidence(checked=True, reason="tool_error")
    if str(payload.get("status") or "").lower() == "error":
        return ScheduleEvidence(checked=True, reason="tool_error")
    data = payload.get("data") if isinstance(payload.get("data"), Mapping) else payload
    items = data.get("items") if isinstance(data.get("items"), list) else []
    shop_id = str(slots.shop_id or "")
    matching_items = [
        item
        for item in items
        if isinstance(item, Mapping) and str(item.get("shop_id") or item.get("shopId") or "") == shop_id
    ]
    if matching_items and all(str(item.get("status") or "") == "no_inventory" for item in matching_items):
        return ScheduleEvidence(checked=True, reason="no_inventory")

    schedule = data.get("schedule") if isinstance(data.get("schedule"), Mapping) else {}
    stores = schedule.get("stores") if isinstance(schedule.get("stores"), list) else []
    candidates = [*matching_items, *(store for store in stores if isinstance(store, Mapping))]
    requested_day = str(slots.requested_cal_day or "")
    requested_hour = _normalized_hour(slots.rsv_hour)
    for store in candidates:
        candidate_shop_id = str(store.get("shop_id") or store.get("shopId") or "")
        if candidate_shop_id and candidate_shop_id != shop_id:
            continue
        for slot in store.get("slots") or []:
            if not isinstance(slot, Mapping):
                continue
            cal_day = str(slot.get("cal_day") or slot.get("calDay") or "")
            hour = _normalized_hour(slot.get("tm") or slot.get("hour") or slot.get("rsv_hour"))
            if cal_day == requested_day and hour == requested_hour:
                return ScheduleEvidence(checked=True, available=True, reason="matching_slot")
    return ScheduleEvidence(checked=True, reason="slot_unavailable")


def _parse_payload(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, Mapping):
        return dict(raw)
    text = str(raw or "").strip()
    if not text or text.startswith("Tool error"):
        return None
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalized_hour(value: Any) -> str:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if not digits:
        return ""
    return digits[:2].zfill(2)
