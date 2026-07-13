"""The router call: one mini-model structured-output invocation per turn.

Replaces V2's regex guards + 3-layer classifier + regex slot extraction.
Returns None on any failure — the caller degrades to pure chat.
"""

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from common.curr_time import get_current_time
from schemas.tstation.chat import TStationChatRequest
from schemas.tstation.slots import ConversationSlots
from services.tstation.chat_v3.llm import get_router_llm
from services.tstation.chat_v3.prompts.router import ROUTER_PROMPT
from services.tstation.chat_v3.router.schemas import Domain, GuardId, RouteDecision
from services.tstation.policies.delivery_policy_gate import DeliveryPolicyIntent, decide_delivery_policy_gate
from services.tstation.policies.late_night_store_hours_gate import is_late_night_store_hours_policy_request
from services.tstation.policies.pickup_service_gate import decide_pickup_service_gate

logger = logging.getLogger(__name__)

_HISTORY_TURNS = 6
_MAX_CHARS_PER_MESSAGE = 500
_DELIVERY_POLICY_INTENTS: dict[DeliveryPolicyIntent, str] = {
    DeliveryPolicyIntent.DIRECT_HOME_DELIVERY: "direct_home_delivery",
    DeliveryPolicyIntent.SHIPPING_FEE_REGION: "shipping_fee_region",
    DeliveryPolicyIntent.SHIPPING_FEE_FOLLOWUP: "shipping_fee_region",
    DeliveryPolicyIntent.ONLINE_STORE_PRICE_POLICY: "online_store_price_policy",
    DeliveryPolicyIntent.REGIONAL_PRICE_POLICY: "regional_price_policy",
}
_STATIC_FAQ_GUARD_INTENTS: dict[GuardId, str] = {
    GuardId.PAST_EVENT_PAGE: "past_event_page",
    GuardId.VEHICLE_TYPE_COMPATIBILITY: "vehicle_type_compatibility",
    GuardId.DIRECT_HOME_DELIVERY: "direct_home_delivery",
    GuardId.SHIPPING_FEE_REGION: "shipping_fee_region",
    GuardId.ONLINE_STORE_PRICE_POLICY: "online_store_price_policy",
    GuardId.REGIONAL_PRICE_POLICY: "regional_price_policy",
}
_PICKUP_FAQ_INTENTS = {"pickup_status", "pickup_info"}
_RUNFLAT_TERMS = ("런플랫", "런 플랫", "runflat", "run flat", "run-flat")
_RUNFLAT_MIXED_INSTALL_TERMS = (
    "일반 타이어",
    "일반타이어",
    "앞바퀴",
    "뒷바퀴",
    "2짝",
    "두짝",
    "2개",
    "두 개",
    "혼용",
    "바꿔도",
    "교체",
)


def _router_input(request: TStationChatRequest, known_slots: ConversationSlots | None = None) -> str:
    lines = [f"오늘 날짜/시간: {get_current_time()}", "## 최근 대화"]
    for msg in request.messages[-_HISTORY_TURNS:]:
        role = "사용자" if msg.get("role") == "user" else "챗봇"
        lines.append(f"{role}: {str(msg.get('content') or '')[:_MAX_CHARS_PER_MESSAGE]}")
    if request.chip_context:
        lines.append("## 사용자가 누른 버튼 (chip_context)")
        lines.append(json.dumps(request.chip_context, ensure_ascii=False)[:_MAX_CHARS_PER_MESSAGE])
    if request.ui_action:
        lines.append("## UI 액션 (ui_action)")
        lines.append(json.dumps(request.ui_action, ensure_ascii=False)[:_MAX_CHARS_PER_MESSAGE])
    if known_slots is not None:
        slot_values = {k: v for k, v in known_slots.model_dump(mode="json").items() if v is not None}
        if slot_values:
            lines.append("## 현재 확인된 대화 슬롯")
            lines.append(json.dumps(slot_values, ensure_ascii=False)[:_MAX_CHARS_PER_MESSAGE])
    return "\n".join(lines)


def _last_user_text(request: TStationChatRequest) -> str:
    for msg in reversed(request.messages):
        if msg.get("role") == "user":
            return str(msg.get("content") or "")
    return ""


def _recent_context_before_last_user(request: TStationChatRequest) -> str:
    context_lines: list[str] = []
    skipped_last_user = False
    for msg in reversed(request.messages):
        role = msg.get("role")
        if role == "user" and not skipped_last_user:
            skipped_last_user = True
            continue
        content = str(msg.get("content") or "").strip()
        if content:
            context_lines.append(content[:_MAX_CHARS_PER_MESSAGE])
        if len(context_lines) >= _HISTORY_TURNS:
            break
    return "\n".join(reversed(context_lines))


def _today() -> date:
    tz_offset = int(os.getenv("TZ_OFFSET", "0"))
    tz = timezone(timedelta(hours=tz_offset))
    return datetime.now(tz).date()


def _nested_value(data: Any, *path: str) -> Any:
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _requested_cal_day_from_request(request: TStationChatRequest) -> str:
    direct = request.slots.get("requested_cal_day") if isinstance(request.slots, dict) else None
    if direct:
        return str(direct).strip()
    for source in (request.ui_action, request.chip_context):
        if not isinstance(source, dict):
            continue
        for value in (
            _nested_value(source, "slots", "requested_cal_day"),
            _nested_value(source, "metadata", "slots", "requested_cal_day"),
            _nested_value(source, "ui_action", "slots", "requested_cal_day"),
            source.get("requested_cal_day"),
            source.get("requestedCalDay"),
        ):
            if value:
                return str(value).strip()
    return ""


def _parse_yyyymmdd(value: str) -> date | None:
    if len(value) != 8 or not value.isdigit():
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def _clear_in_range_reservation_date_guard(
    decision: RouteDecision,
    request: TStationChatRequest,
    *,
    today: date | None = None,
) -> RouteDecision:
    if decision.guard_id != GuardId.RESERVATION_DATE_RANGE:
        return decision
    requested = str(decision.slots_patch.requested_cal_day or "").strip() or _requested_cal_day_from_request(request)
    requested_day = _parse_yyyymmdd(requested)
    if requested_day is None:
        return decision
    base_day = today or _today()
    if base_day <= requested_day <= base_day + timedelta(days=30):
        logger.info(
            "[CHAT_V3] cleared reservation_date_range guard for in-range requested_cal_day=%s",
            requested,
        )
        decision.guard_id = GuardId.NONE
    return decision


def _clear_non_target_unsupported_brand_guard(decision: RouteDecision) -> RouteDecision:
    if decision.guard_id != GuardId.UNSUPPORTED_BRAND:
        return decision
    brand_context = decision.brand_context
    if brand_context.unsupported_brand_target or not brand_context.has_non_target_brand_context():
        return decision
    logger.info(
        "[CHAT_V3] cleared unsupported_brand guard for non-target brand context=%s",
        brand_context.model_dump(exclude_none=True),
    )
    decision.guard_id = GuardId.NONE
    decision.domain = Domain.DISCOVERY
    decision.extra_domains = []
    decision.needs_selection_card = True
    return decision


def _apply_delivery_policy_guard(decision: RouteDecision, request: TStationChatRequest) -> RouteDecision:
    policy = decide_delivery_policy_gate(
        user_text=_last_user_text(request),
        recent_context=_recent_context_before_last_user(request),
    )
    policy_key = _DELIVERY_POLICY_INTENTS.get(policy.intent)
    if not policy.is_actionable or policy_key is None:
        return decision
    if policy_key not in decision.intents:
        logger.info(
            "[CHAT_V3] applied delivery static FAQ policy=%s over router guard=%s reason=%s",
            policy_key,
            decision.guard_id.value,
            policy.reason,
        )
        decision.intents.insert(0, policy_key)
    decision.guard_id = GuardId.NONE
    decision.domain = Domain.SUPPORT
    decision.extra_domains = []
    decision.needs_selection_card = False
    return decision


def _apply_pickup_service_policy(decision: RouteDecision, request: TStationChatRequest) -> RouteDecision:
    pickup = decide_pickup_service_gate(
        user_text=_last_user_text(request),
        recent_context=_recent_context_before_last_user(request),
    )
    if not pickup.is_pickup or pickup.intent == "none":
        original_intents = list(decision.intents)
        decision.intents = [intent for intent in decision.intents if intent not in _PICKUP_FAQ_INTENTS]
        if decision.guard_id in {GuardId.PICKUP_STATUS, GuardId.PICKUP_INFO}:
            decision.guard_id = GuardId.NONE
        if original_intents != decision.intents:
            logger.info(
                "[CHAT_V3] stripped unverified pickup intents=%s reason=%s",
                original_intents,
                pickup.reason,
            )
        return decision
    policy_key = "pickup_status" if pickup.intent == "pickup_status" else "pickup_info"
    if policy_key not in decision.intents:
        logger.info(
            "[CHAT_V3] applied pickup FAQ intent=%s over router guard=%s reason=%s",
            policy_key,
            decision.guard_id.value,
            pickup.reason,
        )
        decision.intents.insert(0, policy_key)
    decision.guard_id = GuardId.NONE
    decision.domain = Domain.SUPPORT
    decision.extra_domains = []
    decision.needs_selection_card = False
    return decision


def _move_static_faq_guard_to_intent(decision: RouteDecision) -> RouteDecision:
    policy_key = _STATIC_FAQ_GUARD_INTENTS.get(decision.guard_id)
    if policy_key is None:
        return decision
    logger.info("[CHAT_V3] moved static FAQ guard=%s to support intent", decision.guard_id.value)
    if policy_key not in decision.intents:
        decision.intents.insert(0, policy_key)
    decision.guard_id = GuardId.NONE
    decision.domain = Domain.SUPPORT
    decision.extra_domains = []
    decision.needs_selection_card = False
    return decision


def _apply_runflat_mixed_install_policy(decision: RouteDecision, request: TStationChatRequest) -> RouteDecision:
    text = _last_user_text(request).lower()
    has_runflat = any(term in text for term in _RUNFLAT_TERMS)
    has_mixed_install = any(term in text for term in _RUNFLAT_MIXED_INSTALL_TERMS)
    if not has_runflat or not has_mixed_install:
        return decision
    policy_key = "runflat_mixed_install_policy"
    if policy_key not in decision.intents:
        logger.info(
            "[CHAT_V3] applied runflat mixed-install static FAQ policy over guard=%s intents=%s",
            decision.guard_id.value,
            decision.intents,
        )
        decision.intents.insert(0, policy_key)
    decision.guard_id = GuardId.NONE
    decision.domain = Domain.SUPPORT
    decision.extra_domains = []
    decision.needs_selection_card = False
    return decision


def _apply_late_night_store_hours_policy(decision: RouteDecision, request: TStationChatRequest) -> RouteDecision:
    if not is_late_night_store_hours_policy_request(_last_user_text(request)):
        return decision
    policy_key = "late_night_store_hours_policy"
    if policy_key not in decision.intents:
        logger.info(
            "[CHAT_V3] applied late-night store hours static FAQ policy over guard=%s intents=%s",
            decision.guard_id.value,
            decision.intents,
        )
        decision.intents.insert(0, policy_key)
    decision.guard_id = GuardId.NONE
    decision.domain = Domain.SUPPORT
    decision.extra_domains = []
    decision.needs_selection_card = False
    return decision


async def route_request(
    request: TStationChatRequest,
    trace_config: dict | None = None,
    known_slots: ConversationSlots | None = None,
) -> RouteDecision | None:
    try:
        # json_schema (default) requires every field in `required` (OpenAI strict
        # mode), which optional-field models fail — function_calling does not.
        llm = get_router_llm().with_structured_output(RouteDecision, method="function_calling")
        messages = [("system", ROUTER_PROMPT), ("user", _router_input(request, known_slots))]
        decision = await llm.ainvoke(messages, config=trace_config) if trace_config else await llm.ainvoke(messages)
        decision = _clear_in_range_reservation_date_guard(decision, request)
        decision = _clear_non_target_unsupported_brand_guard(decision)
        decision = _move_static_faq_guard_to_intent(decision)
        decision = _apply_runflat_mixed_install_policy(decision, request)
        decision = _apply_late_night_store_hours_policy(decision, request)
        decision = _apply_pickup_service_policy(decision, request)
        decision = _apply_delivery_policy_guard(decision, request)
        logger.info(
            "[CHAT_V3] route guard=%s domains=%s intents=%s slots=%s",
            decision.guard_id.value,
            "+".join(decision.all_domains()),
            decision.intents,
            decision.slots_patch.non_empty(),
        )
        return decision
    except Exception:
        logger.exception("[CHAT_V3] router call failed — degrading to pure chat")
        return None
