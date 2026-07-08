"""Chat V3 entrypoint — orchestrates route → guard/tools → answer.

Turn pipeline (all decisions LLM-made, zero regex):
  router (guard? domain? slots?) → guard: canned answer
                                 → pass:  tool loop → QC → quick replies
"""

import logging
import time

from fastapi.responses import StreamingResponse

from config.env import settings
from schemas.tstation.chat import TStationChatRequest, TStationChatResponse
from services.tstation.agents.b_discovery_agent._car_no_audit import set_user_message as _audit_set_user_message
from services.tstation.chat_v3 import composer, context, memory, qc, sse, templates
from services.tstation.chat_v3.executor import ToolLoopExecutor
from services.tstation.chat_v3.prompts.persona import ERROR_RESPONSE, SYSTEM_PROMPT, TRANSACTION_WRITE_GUIDANCE
from services.tstation.chat_v3.router.guards import get_guard
from services.tstation.chat_v3.router.route import route_request
from services.tstation.chat_v3.slots.store import apply_patch, load_slots, save_slots, slots_context_block
from services.tstation.chat_v3.tools import tools_for_domains
from services.tstation.common.tstation_be_client import set_tstation_be_token, set_tstation_origin_host

logger = logging.getLogger(__name__)

_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _tool_display_names() -> dict[str, str]:
    from services.tstation.agents.base_agent import TOOL_DISPLAY_NAMES

    return TOOL_DISPLAY_NAMES


def _tokens_enabled() -> bool:
    return bool(getattr(settings, "AI_CHAT_V3_STREAM_TOKENS", True))


async def _run_turn(request: TStationChatRequest, result: dict):
    t0 = time.perf_counter()
    set_tstation_be_token(request.access_token)
    set_tstation_origin_host(request.origin_host)
    user_text = context.last_user_text(request)
    # Deterministic guard inside discovery tools against recommending for a
    # registered car the user did not name — V2 seeds this the same way.
    _audit_set_user_message(user_text)

    yield sse.status("생각 중...")
    decision = await route_request(request)
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
        for event in sse.done():
            yield event
        return

    slots = await load_slots(request.session_id)
    slots = apply_patch(slots, decision.slots_patch if decision else None)
    domains = decision.all_domains() if decision else ["LEADING"]
    domain = domains[0]

    extra_context = []
    if "TRANSACTION" in domains:
        extra_context.append(TRANSACTION_WRITE_GUIDANCE)
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
    )
    yield sse.agent_flow(f"[V3 {'+'.join(domains)} FLOW]", "start")
    async for event in executor.stream():
        yield event
    t_tools = time.perf_counter()

    # Part B: capture resolved order IDs (goods_no/shop_id/payment_amount) from this
    # turn's tool outputs into slots so the preOrder card + next-turn quick_order_tool
    # have their required args even when a later turn no longer re-calls the tools.
    slots = templates.harvest_order_slots(slots, executor.tool_calls)

    answer = executor.final_text.strip() or ERROR_RESPONSE
    corrected = await qc.verify_answer(answer, executor.tool_calls)
    if corrected != answer:
        yield sse.sse({"type": "qc_correction", "assistantResponse": corrected})
        answer = corrected
    answer = templates.format_location_answer(answer, executor.tool_calls)
    answer = templates.compact_answer_spacing(answer)
    qna_event = templates.build_qna_complete_event(answer, executor.tool_calls)
    if qna_event:
        answer = qna_event["data"]["assistantResponse"]

    result["answer"] = answer
    yield sse.message(answer)
    chips: list[dict] = []
    quantity_chips = templates.quantity_quick_replies(answer)
    rich_event = qna_event or (None if quantity_chips else await templates.build_rich_data_event(answer, executor.tool_calls))
    # K2 fallback: when the model answered with a plain order summary instead of
    # emitting the preOrder card via present_order_preview_tool (K1 → rich_event),
    # rebuild the card from slots. Guarded by build_preorder_fallback (needs goods_no).
    preorder_event = (
        None if (quantity_chips or rich_event) else templates.build_preorder_fallback(answer, slots, decision)
    )
    if quantity_chips:
        chips = quantity_chips
        predicted_domains = ["TRANSACTION"]
        yield sse.data_event(
            "quickReply",
            {"assistantResponse": answer, "quickReplies": chips, "predictedDomains": predicted_domains},
            source_domain=domain,
        )
    elif rich_event:
        predicted_domains = [domain]
        yield sse.sse({**rich_event, "source_domain": domain})
    elif preorder_event:
        predicted_domains = ["TRANSACTION"]
        yield sse.sse({**preorder_event, "source_domain": domain})
    else:
        chips = await composer.suggest_quick_replies(user_text, answer)
        # V2 semantics: predictedDomains = likely domains of the user's NEXT turn.
        # The chips are exactly the next actions we offer, so their domains are
        # the prediction; fall back to the current domain when there are no chips.
        predicted_domains = list(dict.fromkeys(chip["domain"] for chip in chips)) or [domain]
        yield sse.data_event(
            "quickReply",
            {"assistantResponse": answer, "quickReplies": chips, "predictedDomains": predicted_domains},
            source_domain=domain,
        )
    yield sse.agent_flow("[DONE]", "success")
    for event in sse.done():
        yield event

    await save_slots(request.session_id, slots, user_id=request.user_id)
    await memory.persist_turn_context(
        request.session_id,
        tool_calls=executor.tool_calls,
        quick_reply_domains=[chip["domain"] for chip in chips],
        predicted_domains=predicted_domains,
        user_id=request.user_id,
    )
    logger.info(
        "[CHAT_V3] session=%s domains=%s tools=%d route=%.0fms tools_stage=%.0fms total=%.0fms",
        request.session_id,
        "+".join(domains),
        len(executor.tool_calls),
        (t_route - t0) * 1000,
        (t_tools - t_route) * 1000,
        (time.perf_counter() - t0) * 1000,
    )


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
