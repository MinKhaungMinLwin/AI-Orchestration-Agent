"""The router call: one mini-model structured-output invocation per turn.

Replaces V2's regex guards + 3-layer classifier + regex slot extraction.
Returns None on any failure — the caller degrades to pure chat.
"""

import json
import logging

from common.curr_time import get_current_time
from schemas.tstation.chat import TStationChatRequest
from services.tstation.chat_v3.llm import get_router_llm
from services.tstation.chat_v3.prompts.router import ROUTER_PROMPT
from services.tstation.chat_v3.router.schemas import RouteDecision

logger = logging.getLogger(__name__)

_HISTORY_TURNS = 6
_MAX_CHARS_PER_MESSAGE = 500


def _router_input(request: TStationChatRequest) -> str:
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
    return "\n".join(lines)


async def route_request(request: TStationChatRequest, trace_config: dict | None = None) -> RouteDecision | None:
    try:
        # json_schema (default) requires every field in `required` (OpenAI strict
        # mode), which optional-field models fail — function_calling does not.
        llm = get_router_llm().with_structured_output(RouteDecision, method="function_calling")
        messages = [("system", ROUTER_PROMPT), ("user", _router_input(request))]
        decision = await llm.ainvoke(messages, config=trace_config) if trace_config else await llm.ainvoke(messages)
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
