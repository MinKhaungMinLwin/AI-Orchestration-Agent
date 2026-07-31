"""Chat V3 entrypoint — orchestrates route → guard/tools → answer.

Turn pipeline (all decisions LLM-made, zero regex):
  router (guard? domain? slots?) → guard: canned answer
                                 → pass:  tool loop → QC → quick replies
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable

from fastapi.responses import StreamingResponse

from config.env import settings
from config.tracing import (
    active_trace_span,
    build_trace_config,
    safe_trace_update,
    set_trace_name,
    tracer,
    truncate_for_trace,
)
from schemas.tstation.chat import TStationChatRequest, TStationChatResponse
from schemas.tstation.slots import ConversationSlots
from services.tstation.agents.b_discovery_agent._car_no_audit import set_user_message as _audit_set_user_message
from services.tstation.chat_v3 import composer, context, memory, monitoring, qc, schedule_validation, sse, templates
from services.tstation.chat_v3.executor import ToolLoopExecutor
from services.tstation.chat_v3.price_notice import apply_price_notice
from services.tstation.chat_v3.token_usage import TurnTokenUsage
from services.tstation.quota_service import record_monthly_tokens
from services.tstation.chat_v3.prompts.persona import (
    BENEFIT_INQUIRY_GUIDANCE,
    COMPETITOR_CHARACTERISTIC_GUIDANCE,
    ERROR_RESPONSE,
    MAINTENANCE_HISTORY_GUIDANCE,
    MY_COUPONS_GUIDANCE,
    ORDER_HISTORY_GUIDANCE,
    RESERVATION_HISTORY_GUIDANCE,
    SMART_PAY_GUIDANCE,
    STORE_SEARCH_FLOW_GUIDANCE,
    SYSTEM_PROMPT,
    TRANSACTION_WRITE_GUIDANCE,
    VEHICLE_LOOKUP_GUIDANCE,
)
from services.tstation.chat_v3.router.guards import get_guard
from services.tstation.chat_v3.router.route import route_request
from services.tstation.chat_v3.router.schemas import Domain, GuardId, RouteDecision
from services.tstation.chat_v3.slots.derive import (
    STAGGERED_MAX_ORD_QTY,
    apply_fe_slots,
    apply_text_vehicle_selection,
    clamp_staggered_ord_qty,
    derive_slots_from_tool_calls,
    is_staggered_vehicle,
    promote_selected_vehicle,
    reset_for_supported_brand_switch,
    track_guard_repeat,
)
from services.tstation.chat_v3.slots.enrich import backfill_product_label
from services.tstation.chat_v3.slots.store import apply_patch, load_slots, save_slots, slots_context_block
from services.tstation.chat_v3.tools import tools_for_domains
from services.tstation.common.cta_urls import CTAUrls
from services.tstation.common.tstation_be_client import set_tstation_be_token, set_tstation_origin_host
from services.tstation.policies.cta_registry import normalize_quickreply_ctas
from services.tstation.policies.internal_product_code_policy import sanitize_internal_product_codes
from services.tstation.policies.static_faq_policy import STATIC_FAQ_POLICY_DATABASE

logger = logging.getLogger(__name__)

_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
_ADD_TO_CART_INTENT = "add_to_cart"
_PLACE_ORDER_INTENT = "place_order"
_INSTALLATION_SCHEDULE_CHANGE_INTENT = "installation_schedule_change"
_SAVE_TO_CART_TOOL = "save_to_cart_tool"
_PRESENT_ORDER_PREVIEW_TOOL = "present_order_preview_tool"
_QUICK_ORDER_TOOL = "quick_order_tool"
_STAGGERED_SIMULTANEOUS_PURCHASE_INTENTS = {
    "simultaneous_purchase_inquiry",
    "staggered_simultaneous_purchase_inquiry",
}
# Staggered vehicles show exactly 2 buttons labeled with the size values.
_FRONT_TIRE_CHIP_PREFIX = "앞 타이어"
_REAR_TIRE_CHIP_PREFIX = "뒤 타이어"
_SELECTED_TIRE_SIZE_KEYS = {"tire_size", "tireSize"}
_TRANSACTION_SLOT_FILL_FIELDS = {"region", "shop_id", "shop_name", "requested_cal_day", "rsv_hour"}


def _tool_display_names() -> dict[str, str]:
    from services.tstation.agents.base_agent import TOOL_DISPLAY_NAMES

    return TOOL_DISPLAY_NAMES


def _tokens_enabled() -> bool:
    return bool(getattr(settings, "AI_CHAT_V3_STREAM_TOKENS", True))


def _normalize_transaction_goal_slots(decision: RouteDecision | None, slots: ConversationSlots) -> ConversationSlots:
    if decision is None:
        return slots
    if _PLACE_ORDER_INTENT in decision.intents:
        return slots.apply_runtime_values(
            {"pending_intent": "order", "goal_type": "place_order"},
            source="chat_v3:place_order_intent",
        )
    if _ADD_TO_CART_INTENT in decision.intents:
        return slots.apply_runtime_values(
            {"pending_intent": "cart", "goal_type": "add_to_cart"},
            source="chat_v3:add_to_cart_intent",
            fill_only=True,
        )
    return slots


def _apply_installation_schedule_change_intent(
    decision: RouteDecision | None,
    slots: ConversationSlots,
) -> ConversationSlots:
    if decision is None or not (
        decision.installation_schedule_change or _INSTALLATION_SCHEDULE_CHANGE_INTENT in decision.intents
    ):
        return slots
    return slots.model_copy(update={
        "requested_cal_day": None,
        "rsv_hour": None,
        "payment_amount": None,
        "price_basis": None,
        "price_source_tool": None,
        "price_facts": None,
        "coupon_facts": None,
    })


def _as_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _staggered_size_chip_slots(slots: ConversationSlots, *, tire_size: str, front_size: str, rear_size: str) -> dict:
    values = {
        "car_no": slots.car_no,
        "car_lnc_cd": slots.car_lnc_cd,
        "mbr_car_reg_seq": slots.mbr_car_reg_seq,
        "car_model": slots.car_model,
        "car_type": slots.car_type,
        "vehicle_type": slots.vehicle_type,
        "tire_size": tire_size,
        "tire_size_front": front_size,
        "tire_size_rear": rear_size,
    }
    return {key: value for key, value in values.items() if value not in (None, "", [], {})}


def _staggered_tire_size_choice_event(slots: ConversationSlots) -> dict | None:
    front_size = str(slots.tire_size_front or "").strip()
    rear_size = str(slots.tire_size_rear or "").strip()
    selected_size = str(slots.tire_size or "").strip()
    if not front_size or not rear_size or front_size == rear_size or selected_size:
        return None

    front_slots = _staggered_size_chip_slots(
        slots,
        tire_size=front_size,
        front_size=front_size,
        rear_size=rear_size,
    )
    rear_slots = _staggered_size_chip_slots(
        slots,
        tire_size=rear_size,
        front_size=front_size,
        rear_size=rear_size,
    )
    # notice message + exactly 2 front/rear size buttons.
    answer = "\n".join([
        "앞/뒤 타이어 규격이 다른 차량으로 확인되었습니다.",
        f"- 앞 타이어: {front_size}",
        f"- 뒤 타이어: {rear_size}",
        "",
        "계속 진행할 규격을 선택해 주세요.",
    ])
    chips = [
        {"label": f"{_FRONT_TIRE_CHIP_PREFIX} {front_size}", "domain": "DISCOVERY", "metadata": {"slots": front_slots}},
        {"label": f"{_REAR_TIRE_CHIP_PREFIX} {rear_size}", "domain": "DISCOVERY", "metadata": {"slots": rear_slots}},
    ]
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": answer,
            "quickReplies": chips,
            "predictedDomains": ["DISCOVERY", "TRANSACTION"],
        },
        "source_domain": "DISCOVERY",
        "assistant_response_source": "code_chat_v3_staggered_tire_size_choice",
    }


def _staggered_tire_quantity_choice_event(slots: ConversationSlots) -> dict | None:
    """Request quantity before tools run for the selected staggered tire size."""
    front_size = str(slots.tire_size_front or "").strip()
    rear_size = str(slots.tire_size_rear or "").strip()
    selected_size = str(slots.tire_size or "").strip()
    if (
        not front_size
        or not rear_size
        or front_size == rear_size
        or selected_size not in {front_size, rear_size}
        or (isinstance(slots.ord_qty, int) and slots.ord_qty > 0)
    ):
        return None

    answer = f"{selected_size} 기준으로 확인하겠습니다. 필요한 타이어 수량을 선택해 주세요."
    # Quantity here scopes a *recommendation* — no product is chosen yet — so the chips
    # must stay in DISCOVERY like the size chips above. A TRANSACTION label routes the
    # next turn to TRANSACTION, which binds no recommendation tool at all.
    #
    # They must also carry the size the customer just picked: _clear_unconfirmed_staggered_size
    # drops tire_size whenever an FE slot payload does not mention it, so a quantity-only chip
    # wipes the selection and bounces the flow back to "choose a size".
    size_slots = _staggered_size_chip_slots(
        slots,
        tire_size=selected_size,
        front_size=front_size,
        rear_size=rear_size,
    )
    chips = [
        {
            "label": f"{quantity}개",
            "domain": "DISCOVERY",
            "metadata": {"slots": {**size_slots, "ord_qty": quantity}},
        }
        for quantity in range(1, STAGGERED_MAX_ORD_QTY + 1)
    ]
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": answer,
            "quickReplies": chips,
            "predictedDomains": ["DISCOVERY", "TRANSACTION"],
        },
        "source_domain": "DISCOVERY",
        "assistant_response_source": "code_chat_v3_staggered_tire_quantity_choice",
    }


def _staggered_sizes(slots: ConversationSlots) -> tuple[str, str]:
    front_size = str(slots.tire_size_front or "").strip()
    rear_size = str(slots.tire_size_rear or "").strip()
    if front_size and rear_size:
        return front_size, rear_size
    car_no = str(slots.car_no or "").strip()
    for candidate in slots.vehicle_candidates or []:
        if car_no and str(candidate.get("car_no") or "").strip() != car_no:
            continue
        front_size = str(candidate.get("tire_size_front") or "").strip()
        rear_size = str(candidate.get("tire_size_rear") or "").strip()
        if front_size and rear_size:
            return front_size, rear_size
    return "", ""


def _store_visit_schedule_redirect_event(slots: ConversationSlots) -> dict | None:
    if not (slots.shop_id and slots.requested_cal_day and slots.rsv_hour):
        return None
    if any((slots.goods_no, slots.tire_size, slots.tire_model, slots.pending_product_name)):
        return None
    if slots.goal_type in {"place_order", "add_to_cart"} or slots.pending_intent in {"order", "cart"}:
        return None

    cal_day = str(slots.requested_cal_day)
    if len(cal_day) == 8 and cal_day.isdigit():
        date_text = f"{cal_day[:4]}년 {cal_day[4:6]}월 {cal_day[6:]}일"
    else:
        date_text = cal_day
    hour_text = str(slots.rsv_hour).zfill(2)
    shop_name = str(slots.shop_name or "선택하신 매장").strip()
    answer = (
        f"{shop_name} {date_text} {hour_text}:00 방문 가능 시간으로 확인됩니다.\n\n"
        "방문 예약은 티스테이션닷컴 매장 상세 페이지에서 진행해 주세요."
    )
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "TRANSACTION",
        "assistant_response_source": "code_store_visit_schedule_redirect",
        "data": {
            "assistantResponse": answer,
            "quickReplies": [
                {
                    "label": "매장 상세 페이지로 이동",
                    "url": CTAUrls.STORE_DETAIL.replace("<shop_seq>", str(slots.shop_id)),
                    "domain": "TRANSACTION",
                },
                {"label": "다른 시간 선택", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["TRANSACTION"],
            "metadata": {
                "responseShapeKey": "store_visit_schedule_redirect",
                "shopId": slots.shop_id,
                "shopName": slots.shop_name,
                "requestedCalDay": slots.requested_cal_day,
                "rsvHour": slots.rsv_hour,
            },
        },
    }


def _request_has_selected_tire_size(request: TStationChatRequest) -> bool:
    chip_metadata = (request.chip_context or {}).get("metadata") or {}
    sources = [
        request.slots,
        (request.ui_action or {}).get("slots"),
        chip_metadata.get("slots") if isinstance(chip_metadata, dict) else None,
    ]
    return any(
        isinstance(source, dict) and any(source.get(key) not in (None, "") for key in _SELECTED_TIRE_SIZE_KEYS)
        for source in sources
    )


def _fills_transaction_slot(decision: RouteDecision | None) -> bool:
    if decision is None or decision.slots_patch is None:
        return False
    return bool(_TRANSACTION_SLOT_FILL_FIELDS.intersection(decision.slots_patch.non_empty()))


def _staggered_simultaneous_purchase_event(
    decision: RouteDecision | None,
    slots: ConversationSlots,
    *,
    size_selected_from_ui: bool = False,
) -> dict | None:
    if decision is None or not _STAGGERED_SIMULTANEOUS_PURCHASE_INTENTS.intersection(decision.intents):
        return None
    if size_selected_from_ui:
        return None
    front_size, rear_size = _staggered_sizes(slots)
    selected_size = str(slots.tire_size or "").strip()
    if not front_size or not rear_size or front_size == rear_size:
        return None
    if selected_size and selected_size not in {front_size, rear_size}:
        return None
    if selected_size and _fills_transaction_slot(decision):
        return None

    front_slots = _staggered_size_chip_slots(
        slots,
        tire_size=front_size,
        front_size=front_size,
        rear_size=rear_size,
    )
    rear_slots = _staggered_size_chip_slots(
        slots,
        tire_size=rear_size,
        front_size=front_size,
        rear_size=rear_size,
    )
    answer = "\n".join([
        "전/후륜 규격이 다른 차량이라 두 규격을 한 번에 함께 구매 가능한지는 상품과 장착 매장 조건을 각각 확인해야 해요.",
        "현재 채팅에서는 선택한 규격 하나씩 추천/구매를 진행할 수 있습니다.",
        f"- 앞 타이어: **{front_size}**",
        f"- 뒤 타이어: **{rear_size}**",
        "",
        "먼저 진행할 규격을 선택해 주세요.",
    ])
    chips = [
        {"label": f"{_FRONT_TIRE_CHIP_PREFIX} {front_size}", "domain": "DISCOVERY", "metadata": {"slots": front_slots}},
        {"label": f"{_REAR_TIRE_CHIP_PREFIX} {rear_size}", "domain": "DISCOVERY", "metadata": {"slots": rear_slots}},
    ]
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": answer,
            "quickReplies": chips,
            "predictedDomains": ["DISCOVERY", "TRANSACTION"],
        },
        "source_domain": "TRANSACTION",
        "assistant_response_source": "code_chat_v3_staggered_simultaneous_purchase",
    }


_CART_BUTTON_ACTION = "add_to_cart"
_CART_ACTION_KEYS = ("cta_action", "ctaAction", "actionId", "action_id")


def _request_has_cart_button_action(request: TStationChatRequest) -> bool:
    chip_metadata = (request.chip_context or {}).get("metadata") or {}
    ui_action = request.ui_action or {}
    ui_metadata = ui_action.get("metadata") if isinstance(ui_action.get("metadata"), dict) else {}
    sources = [chip_metadata, ui_action, ui_metadata]
    return any(
        isinstance(source, dict)
        and any(str(source.get(key) or "").strip() == _CART_BUTTON_ACTION for key in _CART_ACTION_KEYS)
        for source in sources
    )


def _cart_write_guard(decision: RouteDecision | None, request: TStationChatRequest) -> Callable[[dict], str | None]:
    """Save_to_cart_tool only runs on an explicit add-to-cart
    request in the current turn or the Add-to-Cart button — enforced in code, not
    only in prompts."""
    allowed = bool(decision and _ADD_TO_CART_INTENT in decision.intents) or _request_has_cart_button_action(request)

    def guard(call: dict) -> str | None:
        if (call.get("name") or "") != _SAVE_TO_CART_TOOL or allowed:
            return None
        return (
            "save_to_cart_tool is only allowed when the user explicitly asked to add to cart "
            "in the current turn or pressed the add-to-cart button. Do not add to cart now — "
            "ask the user whether they want to add the item to the cart instead."
        )

    return guard


_UNSELECTED_STAGGERED_ORDER_TOOLS = {
    _PRESENT_ORDER_PREVIEW_TOOL,
    _QUICK_ORDER_TOOL,
    _SAVE_TO_CART_TOOL,
}
_CONFIRMED_SCHEDULE_ORDER_TOOLS = {
    _PRESENT_ORDER_PREVIEW_TOOL,
    _QUICK_ORDER_TOOL,
}


def _transaction_tool_guard(
    decision: RouteDecision | None,
    request: TStationChatRequest,
    slots: ConversationSlots,
) -> Callable[[dict], str | None]:
    """Enforce transaction boundaries that must not depend on model compliance."""
    cart_guard = _cart_write_guard(decision, request)
    front_size = str(slots.tire_size_front or "").strip()
    rear_size = str(slots.tire_size_rear or "").strip()
    selected_size = str(slots.tire_size or "").strip()
    has_selected_size = selected_size in {front_size, rear_size}
    must_select_size = bool(front_size and rear_size and front_size != rear_size and not has_selected_size)

    def guard(call: dict) -> str | None:
        name = str(call.get("name") or "")
        if must_select_size and name in _UNSELECTED_STAGGERED_ORDER_TOOLS:
            return (
                "The front and rear tire sizes differ, but no single size has been selected for this order. "
                "Do not create an order, cart item, or pre-order preview until the user selects one size."
            )
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        requires_confirmed_schedule = name in _CONFIRMED_SCHEDULE_ORDER_TOOLS and not (
            name == _PRESENT_ORDER_PREVIEW_TOOL and bool(args.get("is_ready_to_add_to_cart"))
        )
        if requires_confirmed_schedule:
            confirmed_day = str(slots.requested_cal_day or "").strip()
            confirmed_hour = str(slots.rsv_hour or "").strip()
            confirmed_hour = confirmed_hour.zfill(2) if confirmed_hour else ""
            proposed_day = str(args.get("requested_cal_day") or args.get("rsv_date") or "").strip()
            proposed_hour = str(args.get("rsv_hour") or "").strip()
            proposed_hour = proposed_hour.zfill(2) if proposed_hour else ""
            if not (confirmed_day and confirmed_hour):
                return (
                    "The installation schedule has not been confirmed by the user. Availability-tool fields such as "
                    "first_available_slot are candidates, not user selections. Show the date/time choices and wait "
                    "for the user to select one before creating a pre-order preview or order."
                )
            if (proposed_day and proposed_day != confirmed_day) or (
                proposed_hour and proposed_hour != confirmed_hour
            ):
                return (
                    "The proposed installation schedule differs from the date/time confirmed in conversation slots. "
                    "Use only the user's confirmed schedule."
                )
        return cart_guard(call)

    return guard


_QTY_CAPPED_TOOLS = {_SAVE_TO_CART_TOOL, _QUICK_ORDER_TOOL}


def _staggered_qty_tool_normalizer(slots: ConversationSlots) -> Callable[[dict], dict]:
    """Cap quantities the LLM passes as tool args at 2 for staggered vehicles."""

    def normalize(call: dict) -> dict:
        if not is_staggered_vehicle(slots) or (call.get("name") or "") not in _QTY_CAPPED_TOOLS:
            return call
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        qty = _as_int(args.get("ord_qty"))
        if qty is None or qty <= STAGGERED_MAX_ORD_QTY:
            return call
        return {**call, "args": {**args, "ord_qty": STAGGERED_MAX_ORD_QTY}}

    return normalize


def _allow_selection_cards(decision: RouteDecision | None) -> bool:
    """Whether product-search cards may show this turn (issue 3).

    Honors the router's needs_selection_card, but force-enables when DISCOVERY is a
    SECONDARY domain: the router only adds it to run a product search so the user can
    pick a product to proceed (e.g. ordering an unresolved product — "벤투스 주문해줘").
    That card is a selection step, so it must never be hidden by a stray info flag.
    """
    if decision is None:
        return True
    if Domain.DISCOVERY in decision.extra_domains:
        return True
    return decision.needs_selection_card


def _sanitize_data_event_assistant_response(event: dict | None) -> None:
    if not isinstance(event, dict):
        return
    data = event.get("data")
    if not isinstance(data, dict):
        return
    assistant_response = data.get("assistantResponse")
    if isinstance(assistant_response, str):
        data["assistantResponse"] = sanitize_internal_product_codes(assistant_response)


def _static_faq_policy_context(decision: RouteDecision | None) -> str | None:
    if decision is None:
        return None
    policy_key = next((intent for intent in decision.intents if intent in STATIC_FAQ_POLICY_DATABASE), None)
    if not policy_key:
        return None
    return (
        "STATIC FAQ POLICY ROUTING:\n"
        f"- The router selected policy_key={policy_key}.\n"
        "- Before answering, call get_static_faq_policy_tool with exactly this policy_key.\n"
        "- Use the returned answer as the official policy text. Do not use FAQ/RAG search for this policy."
    )


def _static_faq_policy_event(decision: RouteDecision | None) -> dict | None:
    if decision is None:
        return None
    policy_key = next((intent for intent in decision.intents if intent in STATIC_FAQ_POLICY_DATABASE), None)
    if not policy_key:
        return None
    policy = STATIC_FAQ_POLICY_DATABASE[policy_key]
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "SUPPORT",
        "assistant_response_source": "code_static_faq_policy",
        "data": {
            "assistantResponse": policy["answer"],
            "quickReplies": policy["quick_replies"],
            "predictedDomains": policy["predicted_domains"],
            "metadata": {"policyKey": policy_key},
        },
    }


def _tool_call_succeeded(call: dict) -> bool:
    output = str(call.get("output") or "").strip()
    if not output or output.startswith("Tool error"):
        return False
    try:
        parsed = json.loads(output)
    except (TypeError, ValueError):
        return True
    return not (isinstance(parsed, dict) and parsed.get("status") == "error")


def _has_successful_support_tool_call(tool_calls: list[dict]) -> bool:
    support_tool_names = {tool.name for tool in tools_for_domains([Domain.SUPPORT.value])}
    return any(str(call.get("name") or "") in support_tool_names and _tool_call_succeeded(call) for call in tool_calls)


def _support_answer_is_ungrounded(decision: RouteDecision | None, tool_calls: list[dict]) -> bool:
    if decision is None or Domain.SUPPORT.value not in decision.all_domains():
        return False
    if decision.support_needs_clarification:
        return False
    return not _has_successful_support_tool_call(tool_calls)


def _trace_config(
    request: TStationChatRequest,
    *,
    run_name: str,
    prompt_name: str,
    tags: list[str],
    parent_span_id: str | None = None,
    usage_tracker: TurnTokenUsage | None = None,
) -> dict:
    config = build_trace_config(
        run_name=run_name,
        session_id=request.session_id,
        user_id=request.user_id,
        trace_id=request.tracing_id,
        parent_span_id=parent_span_id,
        tags=["chat_v3", *tags],
        extra_metadata={"runtime": "chat_v3"},
        prompt_name=prompt_name,
        inherit_active_trace=True,
    )
    if usage_tracker is not None:
        config.setdefault("callbacks", []).append(usage_tracker.callback())
    return config


async def _record_real_usage(request: TStationChatRequest, usage_tracker: TurnTokenUsage) -> None:
    """Report this turn's real LLM token usage to the shared monthly quota counter.

    chat_v3 self-reports real usage (summed from actual usage_metadata across
    every LLM call this turn) instead of the text-length estimate used by
    legacy/llm_first — see api/tstation/chat_message.py, which skips its own
    estimate-based increment whenever chat_v3 is the active runtime.
    """
    if not request.user_id or not usage_tracker.total_tokens:
        return
    try:
        await asyncio.to_thread(
            record_monthly_tokens,
            request.user_id,
            usage_tracker.total_tokens,
            request.tracing_id or "",
            settings.MONTHLY_TOKEN_LIMIT,
        )
        # The monthly_tokens_used score record_monthly_tokens just posted is created
        # AFTER this turn's _flush_trace(), so flush again or it stays queued and may
        # never reach Langfuse (works on dev by background-export luck; not on staging).
        await asyncio.to_thread(_flush_trace)
    except Exception:
        logger.debug("[CHAT_V3] quota usage recording failed", exc_info=True)


def _flush_trace() -> None:
    try:
        tracer.flush()
    except Exception:
        logger.debug("[CHAT_V3] Langfuse flush failed", exc_info=True)


def _update_trace_monitoring(
    *,
    trace_observation=None,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    route_domains: list[str],
    tool_calls: list[dict],
    final_template: str,
    answer: str | None = None,
    user_text: str | None = None,
    message_id: str | None = None,
    route_intents: list[str] | None = None,
    route_profile: str = "",
    fallback_used: bool = False,
    qc_corrected: bool = False,
    qc_failed: bool = False,
    qc_reason: str = "",
    selector_model_fallback_used: bool = False,
    composer_model_fallback_used: bool = False,
    selector_model_fallback_reason: str = "",
    runtime_error: bool = False,
    latency_ms: int | None = None,
) -> None:
    monitoring_payload = monitoring.build_customer_monitoring(
        route_domains=route_domains,
        tool_calls=tool_calls,
        final_template=final_template,
        fallback_used=fallback_used,
        qc_corrected=qc_corrected,
        qc_failed=qc_failed,
        qc_reason=qc_reason,
        runtime_error=runtime_error,
        latency_ms=latency_ms,
    )
    monitoring_payload["metadata"].update({
        "selector_model_fallback_used": selector_model_fallback_used,
        "composer_model_fallback_used": composer_model_fallback_used,
        "selector_model_fallback_reason": selector_model_fallback_reason,
    })
    trace_update = dict(monitoring_payload)
    if user_text is not None:
        trace_update["input"] = truncate_for_trace(user_text)
        trace_update["name"] = user_text[:60] if user_text else "chat_v3"
    if answer is not None:
        trace_update["output"] = truncate_for_trace(answer)
    if message_id:
        trace_update["metadata"]["message_id"] = message_id
    if route_intents:
        trace_update["metadata"]["route_intents"] = route_intents
        trace_update["tags"].extend(f"intent:{monitoring._slug(intent)}" for intent in route_intents)
    if route_profile:
        trace_update["metadata"]["route_profile"] = route_profile
        trace_update["tags"].append(f"profile:{monitoring._slug(route_profile)}")
    if trace_observation is not None:
        observation_update = {
            key: value
            for key, value in {
                "input": truncate_for_trace(user_text) if user_text is not None else None,
                "output": truncate_for_trace(answer) if answer is not None else None,
            }.items()
            if value is not None
        }
        if observation_update:
            safe_trace_update(trace_observation, **observation_update)
        safe_trace_update(trace_observation, trace=True, **trace_update)
    if trace_id:
        try:
            event = tracer.create_event(
                name="customer_monitoring",
                input=truncate_for_trace(user_text) if user_text is not None else None,
                output=truncate_for_trace(answer) if answer is not None else None,
                metadata={
                    **monitoring_payload["metadata"],
                    "session_id": session_id,
                    "user_id": user_id,
                    "trace_id": trace_id,
                    "tags": trace_update["tags"],
                    "message_id": message_id,
                    "route_intents": route_intents or [],
                    "assistant_response": truncate_for_trace(answer) if answer is not None else None,
                },
            )
            event.score_trace(
                name="customer_final_status",
                value=monitoring_payload["metadata"].get("final_status") or "unknown",
                data_type="CATEGORICAL",
            )
        except Exception:
            logger.debug("[CHAT_V3] Langfuse customer monitoring event failed", exc_info=True)
    # User/session identity is propagated by the active turn context. The event
    # metadata remains useful for operations, but is not the source of truth for
    # Langfuse's formal user_id/session_id fields.


async def _run_turn(request: TStationChatRequest, result: dict):
    user_text = context.last_user_text(request)
    trace_name = user_text[:60] if user_text else "chat_v3"
    set_trace_name(trace_name)
    try:
        with active_trace_span(
            name="chat_v3",
            trace_id=request.tracing_id,
            session_id=request.session_id,
            user_id=request.user_id,
            trace_name=trace_name,
            input=user_text,
            metadata={"runtime": "chat_v3"},
        ) as parent_span:
            safe_trace_update(
                parent_span,
                trace=True,
                name=trace_name,
                session_id=request.session_id,
                user_id=request.user_id,
                input=truncate_for_trace(user_text),
                metadata={"runtime": "chat_v3"},
            )
            async for event in _run_turn_impl(
                request,
                result,
                parent_span=parent_span,
                parent_span_id=parent_span.id,
            ):
                yield event
    finally:
        _flush_trace()


async def _run_turn_impl(
    request: TStationChatRequest,
    result: dict,
    *,
    parent_span,
    parent_span_id: str | None,
):
    t0 = time.perf_counter()
    usage_tracker = TurnTokenUsage()
    set_tstation_be_token(request.access_token)
    set_tstation_origin_host(request.origin_host)
    user_text = context.last_user_text(request)
    message_id = str((request.metadata or {}).get("message_id") or "")
    set_trace_name(user_text[:60] if user_text else "chat_v3")
    # Deterministic guard inside discovery tools against recommending for a
    # registered car the user did not name — V2 seeds this the same way.
    _audit_set_user_message(user_text)

    yield sse.status("생각 중...")
    slots = await load_slots(request.session_id)
    slots = apply_fe_slots(slots, request)  # card-click payload: goods_no/shop_id/…
    slots = apply_text_vehicle_selection(slots, user_text)
    decision = await route_request(
        request,
        trace_config=_trace_config(
            request,
            run_name="chat_v3_router",
            prompt_name="chat_v3_router",
            tags=["router"],
            parent_span_id=parent_span_id,
            usage_tracker=usage_tracker,
        ),
        known_slots=slots,
    )
    t_route = time.perf_counter()

    if decision and decision.brand_context.switch_to_supported_alternative:
        slots = reset_for_supported_brand_switch(slots)
    slots = track_guard_repeat(decision.guard_id.value if decision else "none", slots)
    guard = get_guard(decision.guard_id) if decision else None
    if guard:
        logger.info("[CHAT_V3] guard=%s for session=%s", guard.id, request.session_id)
        guard_text = templates.compact_answer_spacing(guard.text)
        result["answer"] = guard_text
        if _tokens_enabled():
            yield sse.token(guard_text)
        yield sse.message(guard_text)
        yield sse.data_event(
            "quickReply",
            {
                "assistantResponse": guard_text,
                "quickReplies": guard.chips,
                "predictedDomains": guard.predicted_domains,
            },
            assistant_response_source=f"llm_guard_{guard.id}",
        )
        _update_trace_monitoring(
            route_domains=[(decision.domain.value if decision else "LEADING")],
            tool_calls=[],
            final_template="quickReply",
            trace_id=request.tracing_id,
            parent_span_id=parent_span_id,
            session_id=request.session_id,
            user_id=request.user_id,
            answer=guard_text,
            user_text=user_text,
            message_id=message_id,
            route_intents=list(decision.intents if decision else []),
            fallback_used=False,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            trace_observation=parent_span,
        )
        _flush_trace()
        await _record_real_usage(request, usage_tracker)
        await save_slots(request.session_id, slots, user_id=request.user_id)
        for event in sse.done():
            yield event
        return

    static_faq_event = _static_faq_policy_event(decision)
    if static_faq_event is not None:
        answer = templates.compact_answer_spacing(str(static_faq_event["data"]["assistantResponse"]))
        static_faq_event["data"]["assistantResponse"] = answer
        chips = [chip for chip in static_faq_event["data"]["quickReplies"] if isinstance(chip, dict)]
        predicted_domains = list(static_faq_event["data"]["predictedDomains"])
        result["answer"] = answer
        if _tokens_enabled():
            yield sse.token(answer)
        yield sse.message(answer)
        yield sse.sse(static_faq_event)
        _update_trace_monitoring(
            route_domains=decision.all_domains() if decision else ["SUPPORT"],
            tool_calls=[],
            final_template="quickReply",
            trace_id=request.tracing_id,
            parent_span_id=parent_span_id,
            session_id=request.session_id,
            user_id=request.user_id,
            answer=answer,
            user_text=user_text,
            message_id=message_id,
            route_intents=list(decision.intents if decision else []),
            fallback_used=False,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            trace_observation=parent_span,
        )
        _flush_trace()
        await _record_real_usage(request, usage_tracker)
        await save_slots(request.session_id, slots, user_id=request.user_id)
        await memory.persist_turn_context(
            request.session_id,
            tool_calls=[],
            quick_reply_domains=[str(chip.get("domain") or "") for chip in chips],
            predicted_domains=predicted_domains,
            user_id=request.user_id,
        )
        for event in sse.done():
            yield event
        return

    domains = decision.all_domains() if decision else ["LEADING"]
    domain = domains[0]
    recovered_staggered_size_event = _staggered_tire_size_choice_event(slots)
    slots = apply_patch(slots, decision.slots_patch if decision else None)
    # Staggered vehicles: even a typed quantity is capped at 2.
    slots = clamp_staggered_ord_qty(slots)
    slots = _normalize_transaction_goal_slots(decision, slots)
    slots = _apply_installation_schedule_change_intent(decision, slots)

    store_visit_schedule_event = _store_visit_schedule_redirect_event(slots)
    if store_visit_schedule_event:
        answer = str(store_visit_schedule_event["data"]["assistantResponse"])
        chips = store_visit_schedule_event["data"]["quickReplies"]
        predicted_domains = store_visit_schedule_event["data"]["predictedDomains"]
        result["answer"] = answer
        if _tokens_enabled():
            yield sse.token(answer)
        yield sse.message(answer)
        yield sse.sse(store_visit_schedule_event)
        _update_trace_monitoring(
            route_domains=domains,
            tool_calls=[],
            final_template="quickReply",
            trace_id=request.tracing_id,
            parent_span_id=parent_span_id,
            session_id=request.session_id,
            user_id=request.user_id,
            answer=answer,
            user_text=user_text,
            message_id=message_id,
            route_intents=list(decision.intents if decision else []),
            fallback_used=False,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            trace_observation=parent_span,
        )
        _flush_trace()
        await _record_real_usage(request, usage_tracker)
        await save_slots(request.session_id, slots, user_id=request.user_id)
        await memory.persist_turn_context(
            request.session_id,
            tool_calls=[],
            quick_reply_domains=[str(chip.get("domain") or "") for chip in chips],
            predicted_domains=predicted_domains,
            user_id=request.user_id,
        )
        for event in sse.done():
            yield event
        return

    staggered_simultaneous_purchase_event = _staggered_simultaneous_purchase_event(
        decision,
        slots,
        size_selected_from_ui=_request_has_selected_tire_size(request),
    )
    if staggered_simultaneous_purchase_event:
        answer = str(staggered_simultaneous_purchase_event["data"]["assistantResponse"])
        chips = staggered_simultaneous_purchase_event["data"]["quickReplies"]
        result["answer"] = answer
        if _tokens_enabled():
            yield sse.token(answer)
        yield sse.message(answer)
        yield sse.sse(staggered_simultaneous_purchase_event)
        _update_trace_monitoring(
            route_domains=domains,
            tool_calls=[],
            final_template="quickReply",
            trace_id=request.tracing_id,
            parent_span_id=parent_span_id,
            session_id=request.session_id,
            user_id=request.user_id,
            answer=answer,
            user_text=user_text,
            message_id=message_id,
            route_intents=list(decision.intents if decision else []),
            fallback_used=True,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            trace_observation=parent_span,
        )
        _flush_trace()
        await _record_real_usage(request, usage_tracker)
        for event in sse.done():
            yield event
        await save_slots(request.session_id, slots, user_id=request.user_id)
        await memory.persist_turn_context(
            request.session_id,
            tool_calls=[],
            quick_reply_domains=[chip["domain"] for chip in chips],
            predicted_domains=staggered_simultaneous_purchase_event["data"]["predictedDomains"],
            user_id=request.user_id,
        )
        return

    staggered_size_event = (
        _staggered_tire_size_choice_event(slots)
        if _fills_transaction_slot(decision)
        else recovered_staggered_size_event or _staggered_tire_size_choice_event(slots)
    )
    if staggered_size_event is None:
        staggered_size_event = _staggered_tire_quantity_choice_event(slots)
    if staggered_size_event:
        answer = str(staggered_size_event["data"]["assistantResponse"])
        chips = staggered_size_event["data"]["quickReplies"]
        result["answer"] = answer
        if _tokens_enabled():
            yield sse.token(answer)
        yield sse.message(answer)
        yield sse.sse(staggered_size_event)
        _update_trace_monitoring(
            route_domains=domains,
            tool_calls=[],
            final_template="quickReply",
            trace_id=request.tracing_id,
            parent_span_id=parent_span_id,
            session_id=request.session_id,
            user_id=request.user_id,
            answer=answer,
            user_text=user_text,
            message_id=message_id,
            route_intents=list(decision.intents if decision else []),
            fallback_used=True,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            trace_observation=parent_span,
        )
        _flush_trace()
        await _record_real_usage(request, usage_tracker)
        for event in sse.done():
            yield event
        await save_slots(request.session_id, slots, user_id=request.user_id)
        await memory.persist_turn_context(
            request.session_id,
            tool_calls=[],
            quick_reply_domains=[chip["domain"] for chip in chips],
            predicted_domains=staggered_size_event["data"]["predictedDomains"],
            user_id=request.user_id,
        )
        return

    extra_context = []
    if "TRANSACTION" in domains:
        extra_context.append(TRANSACTION_WRITE_GUIDANCE)
        extra_context.append(STORE_SEARCH_FLOW_GUIDANCE)
        extra_context.append(ORDER_HISTORY_GUIDANCE)
        extra_context.append(RESERVATION_HISTORY_GUIDANCE)
        extra_context.append(MAINTENANCE_HISTORY_GUIDANCE)
        extra_context.append(MY_COUPONS_GUIDANCE)
        extra_context.append(SMART_PAY_GUIDANCE)
        if decision and (decision.installation_schedule_change or _INSTALLATION_SCHEDULE_CHANGE_INTENT in decision.intents):
            extra_context.append(
                "INSTALLATION SCHEDULE CHANGE:\n"
                "- The user wants to change the selected installation date or time for the active order.\n"
                "- Keep the confirmed product, quantity, and store.\n"
                "- Do not emit preOrder with the old schedule. Show available installation schedule choices first."
            )
    if "DISCOVERY" in domains:
        extra_context.append(VEHICLE_LOOKUP_GUIDANCE)
        if decision and "competitor_counterpart_guidance" in decision.intents:
            extra_context.append(COMPETITOR_CHARACTERISTIC_GUIDANCE)
    if "SUPPORT" in domains:
        extra_context.append(BENEFIT_INQUIRY_GUIDANCE)
    static_faq_context = _static_faq_policy_context(decision)
    if static_faq_context:
        extra_context.append(static_faq_context)
    slots_block = slots_context_block(slots)
    if slots_block:
        extra_context.append(slots_block)
    tool_ctx_items = await memory.load_tool_context(request.session_id) or []
    tool_ctx_block = memory.tool_context_block(tool_ctx_items)
    if tool_ctx_block:
        extra_context.append(tool_ctx_block)
    messages = context.build_messages(request, system_prompt=SYSTEM_PROMPT, extra_context=extra_context)

    vehicle_policy_state = {"slots": slots}

    def stop_for_staggered_vehicle(tool_calls: list[dict]) -> bool:
        derived = derive_slots_from_tool_calls(vehicle_policy_state["slots"], tool_calls)
        promoted = promote_selected_vehicle(
            derived,
            tool_calls,
            car_model_hint=(decision.slots_patch.car_model if decision else None),
        )
        staggered_event = _staggered_tire_size_choice_event(promoted)
        # Preserve the existing same-size flow exactly. Promotion is committed
        # here only when the additional staggered-size selection step is needed.
        vehicle_policy_state["slots"] = promoted if staggered_event else derived
        return bool(staggered_event)

    route_profile = decision.tool_profile.value if decision else ""
    executor = ToolLoopExecutor(
        messages,
        tools_for_domains(
            domains,
            tool_profile=route_profile,
            intents=(decision.intents if decision else None),
        ),
        _tool_display_names(),
        stream_tokens=_tokens_enabled(),
        trace_config=_trace_config(
            request,
            run_name="chat_v3_tool_loop",
            prompt_name="chat_v3_chat",
            tags=["tool_loop"],
            parent_span_id=parent_span_id,
            usage_tracker=usage_tracker,
        ),
        tool_call_normalizer=_staggered_qty_tool_normalizer(slots),
        tool_call_guard=_transaction_tool_guard(decision, request, slots),
        stop_after_tool=stop_for_staggered_vehicle,
    )
    yield sse.agent_flow(f"[V3 {'+'.join(domains)} FLOW]", "start")
    token_events: list[str] = []
    async for event in executor.stream():
        try:
            payload = json.loads(event.strip()[6:]) if event.strip().startswith("data: ") else {}
        except json.JSONDecodeError:
            payload = {}
        if payload.get("type") == "token":
            token_events.append(event)
            continue
        yield event

    schedule_completed_this_turn = schedule_validation.schedule_completed_this_turn(request, decision)
    schedule_validation_required = schedule_validation.needs_preorder_schedule_validation(
        request,
        decision,
        slots,
        executor.tool_calls,
    )
    schedule_evidence = schedule_validation.current_turn_evidence(executor.tool_calls, slots)
    if schedule_validation_required:
        if (
            not schedule_evidence.checked
            and (
                schedule_validation.is_schedule_ui_selection(request)
                or not schedule_completed_this_turn
            )
        ):
            schedule_evidence = schedule_validation.context_evidence(tool_ctx_items, slots)
        if not schedule_evidence.checked:
            token_events = []
            async for event in executor.run_required_tool(
                schedule_validation.AVAILABILITY_TOOL,
                schedule_validation.availability_args(slots),
            ):
                yield event
            schedule_evidence = schedule_validation.current_turn_evidence(executor.tool_calls, slots)
        executor.final_text = schedule_validation.validation_answer(slots, schedule_evidence)
        token_events = []
    t_tools = time.perf_counter()

    if _support_answer_is_ungrounded(decision, executor.tool_calls):
        guard = get_guard(GuardId.OUT_OF_SCOPE)
        if guard:
            logger.info("[CHAT_V3] blocked ungrounded SUPPORT answer for session=%s", request.session_id)
            guard_text = templates.compact_answer_spacing(guard.text)
            result["answer"] = guard_text
            if _tokens_enabled():
                yield sse.token(guard_text)
            yield sse.message(guard_text)
            yield sse.data_event(
                "quickReply",
                {
                    "assistantResponse": guard_text,
                    "quickReplies": guard.chips,
                    "predictedDomains": guard.predicted_domains,
                },
                assistant_response_source=f"llm_guard_{guard.id}",
            )
            _update_trace_monitoring(
                route_domains=domains,
                tool_calls=executor.tool_calls,
                final_template="quickReply",
                trace_id=request.tracing_id,
                parent_span_id=parent_span_id,
                session_id=request.session_id,
                user_id=request.user_id,
                answer=guard_text,
                user_text=user_text,
                message_id=message_id,
                route_intents=list(decision.intents if decision else []),
                route_profile=route_profile,
                fallback_used=False,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                trace_observation=parent_span,
            )
            _flush_trace()
            await _record_real_usage(request, usage_tracker)
            await save_slots(request.session_id, slots, user_id=request.user_id)
            for event in sse.done():
                yield event
            return

    slots = vehicle_policy_state["slots"]
    post_tool_staggered_event = _staggered_tire_size_choice_event(slots)
    if getattr(executor, "stopped_after_tool", False) and post_tool_staggered_event:
        answer = str(post_tool_staggered_event["data"]["assistantResponse"])
        chips = post_tool_staggered_event["data"]["quickReplies"]
        result["answer"] = answer
        if _tokens_enabled():
            yield sse.token(answer)
        yield sse.message(answer)
        yield sse.sse(post_tool_staggered_event)
        _update_trace_monitoring(
            route_domains=domains,
            tool_calls=executor.tool_calls,
            final_template="quickReply",
            trace_id=request.tracing_id,
            parent_span_id=parent_span_id,
            session_id=request.session_id,
            user_id=request.user_id,
            answer=answer,
            user_text=user_text,
            message_id=message_id,
            route_intents=list(decision.intents if decision else []),
            route_profile=route_profile,
            fallback_used=True,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            trace_observation=parent_span,
        )
        _flush_trace()
        await _record_real_usage(request, usage_tracker)
        await save_slots(request.session_id, slots, user_id=request.user_id)
        await memory.persist_turn_context(
            request.session_id,
            tool_calls=executor.tool_calls,
            quick_reply_domains=[chip["domain"] for chip in chips],
            predicted_domains=post_tool_staggered_event["data"]["predictedDomains"],
            user_id=request.user_id,
        )
        for event in sse.done():
            yield event
        return

    # Part B: capture resolved order IDs (goods_no/shop_id/payment_amount) from this
    # turn's tool outputs into slots so the preOrder card + next-turn quick_order_tool
    # have their required args even when a later turn no longer re-calls the tools.
    slots_before_harvest = slots.model_copy()
    slots = templates.harvest_order_slots(slots, executor.tool_calls)
    slots = clamp_staggered_ord_qty(slots)
    slots = await backfill_product_label(slots)

    answer = executor.final_text.strip() or ERROR_RESPONSE
    qc_result = await qc.verify_answer(
        answer,
        executor.tool_calls,
        trace_config=_trace_config(
            request,
            run_name="chat_v3_qc",
            prompt_name="chat_v3_qc",
            tags=["qc"],
            parent_span_id=parent_span_id,
            usage_tracker=usage_tracker,
        ),
    )
    if isinstance(qc_result, str):
        qc_corrected = qc_result != answer
        qc_failed = qc_corrected
        qc_reason = "legacy_qc_string_result" if qc_corrected else ""
        if qc_corrected:
            answer = qc_result
    else:
        qc_corrected = False
        qc_failed = qc_result.failed
        qc_reason = qc_result.reason
        recompose_with_fallback = getattr(executor, "recompose_with_fallback", None)
        selector_fallback_used = bool(getattr(executor, "selector_fallback_used", False))
        if qc_failed and executor.tool_calls and not selector_fallback_used and callable(recompose_with_fallback):
            fallback_answer = await recompose_with_fallback(
                qc_reason,
                trace_config=_trace_config(
                    request,
                    run_name="chat_v3_composer_fallback",
                    prompt_name="chat_v3_composer_fallback",
                    tags=["composer", "fallback"],
                    parent_span_id=parent_span_id,
                    usage_tracker=usage_tracker,
                ),
            )
            if fallback_answer:
                fallback_qc = await qc.verify_answer(fallback_answer, executor.tool_calls)
                fallback_failed = (
                    fallback_qc != fallback_answer if isinstance(fallback_qc, str) else fallback_qc.failed
                )
                if not fallback_failed:
                    answer = fallback_answer
                    token_events = []
                    qc_corrected = True
                    qc_failed = False
                    qc_reason = "qc_fallback_passed"
        if qc_failed:
            yield sse.sse({
                "type": "qc_result",
                "passed": False,
                "reason": qc_reason,
                "correctionApplied": False,
            })
    answer = templates.format_location_answer(answer, executor.tool_calls)
    answer = templates.compact_answer_spacing(answer)
    notice_answer = apply_price_notice(answer, executor.tool_calls)
    if notice_answer != answer:
        answer = notice_answer
        token_events = []
    qna_event = templates.build_qna_complete_event(answer, executor.tool_calls)
    if qna_event:
        answer = qna_event["data"]["assistantResponse"]
    current_events_event = templates.build_current_events_quickreply_event(executor.tool_calls)
    current_events_chips: list[dict] = []
    if current_events_event:
        current_events_data = current_events_event.get("data") if isinstance(current_events_event.get("data"), dict) else {}
        answer = str(current_events_data.get("assistantResponse") or answer)
        current_events_chips = [
            chip for chip in current_events_data.get("quickReplies", []) if isinstance(chip, dict)
        ]
        token_events = []
    sanitized_answer = sanitize_internal_product_codes(answer)
    if sanitized_answer != answer:
        answer = sanitized_answer
        token_events = []

    chips: list[dict] = []
    # Shared across the 3 calls below: a turn that cascades through several template
    # fallbacks (product skip → datepick fallback → quickReply) asks the model this
    # at most once, not once per fallback stage.
    answer_ui_intent = templates.AnswerUiIntentCache(
        answer,
        trace_config=_trace_config(
            request,
            run_name="chat_v3_answer_ui_intent",
            prompt_name="chat_v3_answer_ui_intent",
            tags=["template"],
            parent_span_id=parent_span_id,
            usage_tracker=usage_tracker,
        ),
    )
    preorder_event = templates.build_present_order_preview_event(
        answer,
        slots,
        executor.tool_calls,
    ) if not schedule_validation_required or schedule_evidence.available else None
    preorder_event = preorder_event or templates.build_preorder_fallback(
        answer,
        slots,
        decision,
        schedule_verified=schedule_evidence.available,
    )
    rich_event = qna_event or (
        None
        if preorder_event or current_events_event
        else await templates.build_rich_data_event(
            answer,
            executor.tool_calls,
            trace_config=_trace_config(
                request,
                run_name="chat_v3_template_builder",
                prompt_name="chat_v3_template_builder",
                tags=["template"],
                parent_span_id=parent_span_id,
                usage_tracker=usage_tracker,
            ),
            slots=slots,
            previous_slots=slots_before_harvest,
            allow_selection_cards=_allow_selection_cards(decision),
            user_text=user_text,
            answer_ui_intent=answer_ui_intent,
        )
    )
    if rich_event is None and preorder_event is None and current_events_event is None:
        rich_event = await templates.build_datepick_fallback(
            answer,
            slots,
            executor.tool_calls,
            tool_ctx_items,
            answer_ui_intent=answer_ui_intent,
        )
    quantity_chips = [] if rich_event or preorder_event else templates.quantity_quick_replies(slots, decision)
    if quantity_chips:
        answer = templates.ensure_quantity_options(answer, slots, decision)
        token_events = []
    result["answer"] = answer
    final_template = "quickReply"
    fallback_used = bool(quantity_chips)
    if (rich_event or preorder_event or {}).get("template") != "preOrder":
        for event in token_events:
            yield event
        yield sse.message(answer)
    if rich_event:
        final_template = str(rich_event.get("template") or "")
        predicted_domains = [domain]
        _sanitize_data_event_assistant_response(rich_event)
        yield sse.sse({**rich_event, "source_domain": domain})
    elif preorder_event:
        final_template = str(preorder_event.get("template") or "preOrder")
        predicted_domains = ["TRANSACTION"]
        _sanitize_data_event_assistant_response(preorder_event)
        yield sse.sse({**preorder_event, "source_domain": domain})
    else:
        chips = current_events_chips or quantity_chips
        if not chips:
            chips = await composer.suggest_quick_replies(
                user_text,
                answer,
                trace_config=_trace_config(
                    request,
                    run_name="chat_v3_quick_replies",
                    prompt_name="chat_v3_quick_replies",
                    tags=["quick_reply"],
                    parent_span_id=parent_span_id,
                    usage_tracker=usage_tracker,
                ),
                flow_hint=templates.booking_flow_hint(slots),
            )
        # booking_flow_hint 는 slot 기준이라 answer 가 수량을 묻는 turn 에서도 매장
        # chip 을 지시할 수 있다 — answer 텍스트 기준으로 수량 chip 을 강제한다.
        chips = await templates.enforce_quantity_chips(
            answer,
            chips,
            slots,
            answer_ui_intent=answer_ui_intent,
        )
        quick_reply_event = {
            "type": "data",
            "template": "quickReply",
            "data": {"assistantResponse": answer, "quickReplies": chips, "predictedDomains": []},
            "source_domain": domain,
        }
        # V2 parity: only registered CTAs (URL/dynamic-pattern match) survive as clickable
        # actions — label-only chips with no executable action are dropped (cta_registry.py).
        normalize_quickreply_ctas(quick_reply_event, source_intent=domain)
        chips = quick_reply_event["data"]["quickReplies"]
        # V2 semantics: predictedDomains = likely domains of the user's NEXT turn.
        # The chips are exactly the next actions we offer, so their domains are
        # the prediction; fall back to the current domain when there are no chips.
        predicted_domains = list(dict.fromkeys(chip["domain"] for chip in chips)) or [domain]
        quick_reply_event["data"]["predictedDomains"] = predicted_domains
        yield sse.sse(quick_reply_event)
    logger.info(
        "[CHAT_V3] session=%s domains=%s tools=%d route=%.0fms tools_stage=%.0fms total=%.0fms",
        request.session_id,
        "+".join(domains),
        len(executor.tool_calls),
        (t_route - t0) * 1000,
        (t_tools - t_route) * 1000,
        (time.perf_counter() - t0) * 1000,
    )
    _update_trace_monitoring(
        route_domains=domains,
        tool_calls=executor.tool_calls,
        final_template=final_template,
        trace_id=request.tracing_id,
        parent_span_id=parent_span_id,
        session_id=request.session_id,
        user_id=request.user_id,
        answer=answer,
        user_text=user_text,
        message_id=message_id,
        route_intents=list(decision.intents if decision else []),
        route_profile=route_profile,
        fallback_used=fallback_used,
        qc_corrected=qc_corrected,
        qc_failed=qc_failed,
        qc_reason=qc_reason,
        selector_model_fallback_used=bool(getattr(executor, "selector_fallback_used", False)),
        composer_model_fallback_used=bool(getattr(executor, "composer_fallback_used", False)),
        selector_model_fallback_reason=str(getattr(executor, "selector_fallback_reason", "")),
        latency_ms=int((time.perf_counter() - t0) * 1000),
        trace_observation=parent_span,
    )
    _flush_trace()
    await _record_real_usage(request, usage_tracker)

    slots = derive_slots_from_tool_calls(slots, executor.tool_calls)
    await save_slots(request.session_id, slots, user_id=request.user_id)
    await memory.persist_turn_context(
        request.session_id,
        tool_calls=executor.tool_calls,
        quick_reply_domains=[chip["domain"] for chip in chips],
        predicted_domains=predicted_domains,
        user_id=request.user_id,
    )
    yield sse.agent_flow("[DONE]", "success")
    for event in sse.done():
        yield event


async def _run_turn_safe(request: TStationChatRequest, result: dict):
    """Never lets an exception kill the SSE stream — degrades to an error message."""
    try:
        async for event in _run_turn(request, result):
            yield event
    except Exception:
        logger.exception("[CHAT_V3] turn failed for session=%s", request.session_id)
        result["answer"] = ERROR_RESPONSE
        if _tokens_enabled():
            yield sse.token(ERROR_RESPONSE)
        yield sse.message(ERROR_RESPONSE)
        yield sse.data_event(
            "quickReply",
            {"assistantResponse": ERROR_RESPONSE, "quickReplies": [], "predictedDomains": []},
        )
        for event in sse.done():
            yield event
        _update_trace_monitoring(
            route_domains=["UNKNOWN"],
            tool_calls=[],
            final_template="quickReply",
            fallback_used=False,
            runtime_error=True,
        )
        _flush_trace()


class TStationChatServiceV3:
    """V3 chat service: LLM-first, streams the same SSE contract as V2."""

    @staticmethod
    async def chat(request: TStationChatRequest):
        logger.info("[CHAT_V3] chat for session=%s stream=%s", request.session_id, request.stream)
        result: dict = {}
        if request.stream:
            return StreamingResponse(
                _run_turn_safe(request, result),
                media_type="text/event-stream",
                headers=_STREAM_HEADERS,
            )
        async for _ in _run_turn_safe(request, result):
            pass
        return TStationChatResponse(content=result.get("answer") or ERROR_RESPONSE)


async def chat(request: TStationChatRequest):
    return await TStationChatServiceV3.chat(request)


def enabled() -> bool:
    return bool(getattr(settings, "AI_CHAT_V3_PURE_LLM_ENABLED", False))
