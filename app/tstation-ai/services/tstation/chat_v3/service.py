"""Chat V3 entrypoint — orchestrates route → guard/tools → answer.

Turn pipeline (all decisions LLM-made, zero regex):
  router (guard? domain? slots?) → guard: canned answer
                                 → pass:  tool loop → QC → quick replies
"""

import json
import logging
import time
from collections.abc import Callable

from fastapi.responses import StreamingResponse

from config.env import settings
from config.tracing import _tracing_enabled, build_trace_config, safe_trace_update, set_trace_name, tracer, truncate_for_trace
from schemas.tstation.chat import TStationChatRequest, TStationChatResponse
from schemas.tstation.slots import ConversationSlots
from services.tstation.agents.b_discovery_agent._car_no_audit import set_user_message as _audit_set_user_message
from services.tstation.chat_v3 import composer, context, memory, monitoring, qc, sse, templates
from services.tstation.chat_v3.executor import ToolLoopExecutor, _tool_output_text
from services.tstation.chat_v3.prompts.persona import (
    ERROR_RESPONSE,
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
from services.tstation.chat_v3.router.schemas import Domain, RouteDecision
from services.tstation.chat_v3.slots.derive import apply_fe_slots, apply_text_vehicle_selection, derive_slots_from_tool_calls
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
_CART_CONFIRMATION_INTENT = "cart_confirmation"
_ORDER_PREVIEW_TOOL = "present_order_preview_tool"
_SAVE_TO_CART_TOOL = "save_to_cart_tool"
_FRONT_TIRE_CHIP_LABEL = "앞바퀴사이즈"
_REAR_TIRE_CHIP_LABEL = "뒷바퀴사이즈"
_CUSTOM_TIRE_CHIP_LABEL = "다른 사이즈 입력"


def _tool_display_names() -> dict[str, str]:
    from services.tstation.agents.base_agent import TOOL_DISPLAY_NAMES

    return TOOL_DISPLAY_NAMES


def _tokens_enabled() -> bool:
    return bool(getattr(settings, "AI_CHAT_V3_STREAM_TOKENS", True))


def _is_confirmed_cart_turn(
    decision: RouteDecision | None,
    slots: ConversationSlots,
) -> bool:
    if decision is None:
        return False
    cart_confirmation_intent = _CART_CONFIRMATION_INTENT in decision.intents
    ready_cart_reaffirmed = (
        _ADD_TO_CART_INTENT in decision.intents
        and slots.goods_no
        and slots.ord_qty
    )
    return bool(
        (cart_confirmation_intent or ready_cart_reaffirmed)
        and slots.goods_no
        and slots.ord_qty
    )


def _normalize_add_to_cart_slots(decision: RouteDecision | None, slots: ConversationSlots) -> ConversationSlots:
    if decision is None or _ADD_TO_CART_INTENT not in decision.intents:
        return slots
    return slots.apply_runtime_values(
        {"pending_intent": "cart", "goal_type": "add_to_cart"},
        source="chat_v3:add_to_cart_intent",
        fill_only=True,
    )


def _cart_tool_args(slots: ConversationSlots) -> dict:
    args = {"goods_no": slots.goods_no, "ord_qty": slots.ord_qty}
    if slots.car_lnc_cd:
        args["car_lnc_cd"] = slots.car_lnc_cd
    return args


def _cart_tool_args_from_mapping(args: dict, slots: ConversationSlots) -> dict | None:
    goods_no = str(args.get("goods_no") or slots.goods_no or "").strip()
    ord_qty = _as_int(args.get("ord_qty") or slots.ord_qty)
    if not goods_no or ord_qty is None:
        return None
    cart_args: dict[str, object] = {"goods_no": goods_no, "ord_qty": ord_qty}
    car_lnc_cd = str(args.get("car_lnc_cd") or slots.car_lnc_cd or "").strip()
    if car_lnc_cd:
        cart_args["car_lnc_cd"] = car_lnc_cd
    return cart_args


def _as_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ready_cart_slots(slots: ConversationSlots) -> bool:
    return bool(
        slots.goods_no
        and slots.ord_qty
        and (slots.pending_intent == "cart" or slots.goal_type == "add_to_cart")
    )


def _staggered_tire_size_choice_event(slots: ConversationSlots) -> dict | None:
    front_size = str(slots.tire_size_front or "").strip()
    rear_size = str(slots.tire_size_rear or "").strip()
    selected_size = str(slots.tire_size or "").strip()
    if not front_size or not rear_size or front_size == rear_size or selected_size:
        return None

    base_slots = slots.model_dump(mode="json", exclude_none=True)
    front_slots = {**base_slots, "tire_size": front_size, "tire_size_front": front_size, "tire_size_rear": rear_size}
    rear_slots = {**base_slots, "tire_size": rear_size, "tire_size_front": front_size, "tire_size_rear": rear_size}
    car_model = str(slots.car_model or "").strip()
    car_no = str(slots.car_no or "").strip()
    if car_model or car_no:
        vehicle_name = car_model or car_no
        detail_lines = [f"선택하신 차량은 **{vehicle_name}**입니다."]
        if car_no and car_no != vehicle_name:
            detail_lines.append(f"- 차량번호: **{car_no}**")
        if car_model and car_model != vehicle_name:
            detail_lines.append(f"- 모델: **{car_model}**")
        detail_lines.extend([
            f"- 앞 타이어: **{front_size}**",
            f"- 뒤 타이어: **{rear_size}**",
            "",
            "이 차량은 앞/뒤 타이어 규격이 다른 차량이라, 타이어 추천이나 구매 시 어떤 사이즈로 진행할지 먼저 확인해드릴게요.",
        ])
        answer = "\n".join(detail_lines)
    else:
        answer = (
            f"차량의 앞/뒤 타이어 사이즈가 다릅니다. 전륜 **{front_size}**, 후륜 **{rear_size}** 중 "
            "어떤 사이즈로 진행할까요?"
        )
    chips = [
        {"label": _FRONT_TIRE_CHIP_LABEL, "domain": "DISCOVERY", "metadata": {"slots": front_slots}},
        {"label": _REAR_TIRE_CHIP_LABEL, "domain": "DISCOVERY", "metadata": {"slots": rear_slots}},
        {"label": _CUSTOM_TIRE_CHIP_LABEL, "domain": "DISCOVERY"},
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


def _add_to_cart_tool_normalizer(slots: ConversationSlots, *, enabled: bool) -> Callable[[dict], dict]:
    def normalize(call: dict) -> dict:
        if not enabled or (call.get("name") or "") != _ORDER_PREVIEW_TOOL:
            return call
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        cart_args = _cart_tool_args_from_mapping(args, slots)
        if cart_args is None:
            return call

        normalized = dict(call)
        normalized["name"] = _SAVE_TO_CART_TOOL
        normalized["args"] = cart_args
        return normalized

    return normalize


def _cart_tool_success(output_text: str) -> bool:
    try:
        parsed = json.loads(output_text)
    except (TypeError, ValueError):
        return False
    return isinstance(parsed, dict) and parsed.get("status") == "success"


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


def _trace_config(
    request: TStationChatRequest,
    *,
    run_name: str,
    prompt_name: str,
    tags: list[str],
    parent_span_id: str | None = None,
) -> dict:
    return build_trace_config(
        run_name=run_name,
        session_id=request.session_id,
        user_id=request.user_id,
        trace_id=request.tracing_id,
        parent_span_id=parent_span_id,
        tags=["chat_v3", *tags],
        extra_metadata={"runtime": "chat_v3"},
        prompt_name=prompt_name,
    )


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
    fallback_used: bool = False,
    qc_corrected: bool = False,
    qc_failed: bool = False,
    qc_reason: str = "",
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
    if trace_observation is not None:
        safe_trace_update(trace_observation, trace=True, **trace_update)
    if trace_id:
        trace_context = {"trace_id": trace_id}
        if parent_span_id:
            trace_context["parent_span_id"] = parent_span_id
        try:
            event = tracer.create_event(
                trace_context=trace_context,
                name="customer_monitoring",
                input=truncate_for_trace(user_text) if user_text is not None else None,
                output={
                    "final_status": monitoring_payload["metadata"].get("final_status"),
                    "error_reason": monitoring_payload["metadata"].get("error_reason"),
                    "primary_domain": monitoring_payload["metadata"].get("primary_domain"),
                    "primary_af": monitoring_payload["metadata"].get("primary_af"),
                    "primary_tool": monitoring_payload["metadata"].get("primary_tool"),
                    "final_template": final_template,
                },
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
    try:
        tracer.update_current_trace(**trace_update)
    except Exception:
        logger.debug("[CHAT_V3] Langfuse customer monitoring update failed", exc_info=True)


async def _run_turn(request: TStationChatRequest, result: dict):
    t0 = time.perf_counter()
    set_tstation_be_token(request.access_token)
    set_tstation_origin_host(request.origin_host)
    user_text = context.last_user_text(request)
    message_id = str((request.metadata or {}).get("message_id") or "")
    set_trace_name(user_text[:60] if user_text else "chat_v3")
    parent_span = None
    parent_span_id = None
    if _tracing_enabled:
        try:
            parent_span = tracer.start_span(
                name="chat_v3",
                trace_context={"trace_id": request.tracing_id},
                input=truncate_for_trace(user_text),
                metadata={"runtime": "chat_v3"},
            )
            parent_span_id = parent_span.id
            safe_trace_update(
                parent_span,
                trace=True,
                name=user_text[:60] if user_text else "chat_v3",
                session_id=request.session_id,
                user_id=request.user_id,
                input=truncate_for_trace(user_text),
                metadata={"runtime": "chat_v3"},
            )
        except Exception:
            logger.debug("[CHAT_V3] parent Langfuse span failed", exc_info=True)
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
        ),
        known_slots=slots,
    )
    t_route = time.perf_counter()

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
        if parent_span is not None:
            parent_span.end()
        _flush_trace()
        for event in sse.done():
            yield event
        return

    domains = decision.all_domains() if decision else ["LEADING"]
    domain = domains[0]
    recovered_staggered_size_event = (
        _staggered_tire_size_choice_event(slots) if domain in {"DISCOVERY", "TRANSACTION"} else None
    )
    slots = apply_patch(slots, decision.slots_patch if decision else None)
    slots = _normalize_add_to_cart_slots(decision, slots)

    staggered_size_event = recovered_staggered_size_event or (
        _staggered_tire_size_choice_event(slots) if domain in {"DISCOVERY", "TRANSACTION"} else None
    )
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
        if parent_span is not None:
            parent_span.end()
        _flush_trace()
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

    if _is_confirmed_cart_turn(decision, slots):
        tool = next((candidate for candidate in tools_for_domains(["TRANSACTION"]) if candidate.name == _SAVE_TO_CART_TOOL), None)
        args = _cart_tool_args(slots)
        display = _tool_display_names().get(_SAVE_TO_CART_TOOL, _SAVE_TO_CART_TOOL)
        yield sse.agent_flow("[V3 TRANSACTION FLOW]", "start")
        yield sse.tool_start(_SAVE_TO_CART_TOOL, display)
        if tool is None:
            output_text = f"Unknown tool: {_SAVE_TO_CART_TOOL}"
        else:
            try:
                output = await tool.ainvoke(
                    args,
                    config=_trace_config(
                        request,
                        run_name="chat_v3_confirmed_cart_tool",
                        prompt_name="chat_v3_confirmed_cart_tool",
                        tags=["tool_loop", "cart_confirmation"],
                        parent_span_id=parent_span_id,
                    ),
                )
                output_text = _tool_output_text(output)
            except Exception as exc:
                logger.exception("[CHAT_V3] confirmed cart tool failed")
                output_text = f"Tool error: {exc}"
        tool_call = {"name": _SAVE_TO_CART_TOOL, "args": args, "output": output_text}
        success = _cart_tool_success(output_text)
        yield sse.tool_result(_SAVE_TO_CART_TOOL, args, output_text[:4000])
        yield sse.agent_flow(display, "success" if success else "error")
        if success:
            answer = "장바구니에 담았어요. 바로 주문하시겠어요?"
            chips = [
                {"label": "장바구니 확인", "domain": "TRANSACTION", "url": CTAUrls.CART},
                {"label": "주문 내역 보기", "domain": "TRANSACTION", "url": CTAUrls.ORDER_HISTORY},
            ]
        else:
            answer = "장바구니 담기 중 문제가 생겼어요. 다시 시도해 주세요."
            chips = [{"label": "장바구니 확인", "domain": "TRANSACTION", "url": CTAUrls.CART}]
        result["answer"] = answer
        if _tokens_enabled():
            yield sse.token(answer)
        yield sse.message(answer)
        yield sse.data_event(
            "quickReply",
            {"assistantResponse": answer, "quickReplies": chips, "predictedDomains": ["TRANSACTION"]},
            source_domain="TRANSACTION",
        )
        _update_trace_monitoring(
            route_domains=domains,
            tool_calls=[tool_call],
            final_template="quickReply",
            trace_id=request.tracing_id,
            parent_span_id=parent_span_id,
            session_id=request.session_id,
            user_id=request.user_id,
            answer=answer,
            user_text=user_text,
            message_id=message_id,
            route_intents=list(decision.intents if decision else []),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            trace_observation=parent_span,
        )
        if parent_span is not None:
            parent_span.end()
        _flush_trace()
        yield sse.agent_flow("[DONE]", "success")
        for event in sse.done():
            yield event
        slots = derive_slots_from_tool_calls(slots, [tool_call])
        await save_slots(request.session_id, slots, user_id=request.user_id)
        await memory.persist_turn_context(
            request.session_id,
            tool_calls=[tool_call],
            quick_reply_domains=[chip["domain"] for chip in chips],
            predicted_domains=["TRANSACTION"],
            user_id=request.user_id,
        )
        return

    extra_context = []
    if "TRANSACTION" in domains:
        extra_context.append(TRANSACTION_WRITE_GUIDANCE)
        extra_context.append(STORE_SEARCH_FLOW_GUIDANCE)
        extra_context.append(ORDER_HISTORY_GUIDANCE)
        extra_context.append(RESERVATION_HISTORY_GUIDANCE)
        extra_context.append(SMART_PAY_GUIDANCE)
    if "DISCOVERY" in domains:
        extra_context.append(VEHICLE_LOOKUP_GUIDANCE)
    static_faq_context = _static_faq_policy_context(decision)
    if static_faq_context:
        extra_context.append(static_faq_context)
    slots_block = slots_context_block(slots)
    if slots_block:
        extra_context.append(slots_block)
    tool_ctx_block = await memory.load_tool_context_block(request.session_id)
    if tool_ctx_block:
        extra_context.append(tool_ctx_block)
    messages = context.build_messages(request, system_prompt=SYSTEM_PROMPT, extra_context=extra_context)

    executor = ToolLoopExecutor(
        messages,
        tools_for_domains(domains),
        _tool_display_names(),
        stream_tokens=_tokens_enabled(),
        trace_config=_trace_config(
            request,
            run_name="chat_v3_tool_loop",
            prompt_name="chat_v3_chat",
            tags=["tool_loop"],
            parent_span_id=parent_span_id,
        ),
        tool_call_normalizer=_add_to_cart_tool_normalizer(
            slots,
            enabled=bool(decision and {_ADD_TO_CART_INTENT, _CART_CONFIRMATION_INTENT}.intersection(decision.intents)),
        ),
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
    t_tools = time.perf_counter()

    # Part B: capture resolved order IDs (goods_no/shop_id/payment_amount) from this
    # turn's tool outputs into slots so the preOrder card + next-turn quick_order_tool
    # have their required args even when a later turn no longer re-calls the tools.
    slots_before_harvest = slots.model_copy()
    slots = templates.harvest_order_slots(slots, executor.tool_calls)

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
        if qc_failed:
            yield sse.sse({
                "type": "qc_result",
                "passed": False,
                "reason": qc_reason,
                "correctionApplied": False,
            })
    answer = templates.format_location_answer(answer, executor.tool_calls)
    answer = templates.compact_answer_spacing(answer)
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
    preorder_event = templates.build_preorder_fallback(answer, slots, decision)
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
            ),
            slots=slots,
            previous_slots=slots_before_harvest,
            allow_selection_cards=_allow_selection_cards(decision),
        )
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
                ),
                flow_hint=templates.booking_flow_hint(slots),
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
        fallback_used=fallback_used,
        qc_corrected=qc_corrected,
        qc_failed=qc_failed,
        qc_reason=qc_reason,
        latency_ms=int((time.perf_counter() - t0) * 1000),
        trace_observation=parent_span,
    )
    if parent_span is not None:
        parent_span.end()
    _flush_trace()

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
