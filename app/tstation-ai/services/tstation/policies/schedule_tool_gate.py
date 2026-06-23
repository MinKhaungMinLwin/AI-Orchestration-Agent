"""Pre-tool guard for store schedule lookups.

The schedule tool renders a datepick card, so calling it for status/arrival
questions creates a misleading booking flow. Keep the common allow/block check
near tool execution instead of relying only on prompts.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from textwrap import dedent
from typing import Literal

from langchain_litellm import ChatLiteLLM
from pydantic import BaseModel, Field

from config.env import settings

logger = logging.getLogger(__name__)


ScheduleGateAction = Literal["allow", "answer_from_context", "check_order", "ask_clarify"]


class ScheduleToolGateDecision(BaseModel):
    allow: bool = Field(description="Whether get_store_schedule_tool is allowed for this user turn.")
    action: ScheduleGateAction = Field(description="Next action when blocked, or allow when allowed.")
    reason: str = Field(description="Short English reason for trace/debug only.")


_EXPLICIT_SCHEDULE_REQUEST_RE = re.compile(
    r"예약\s*(?:가능|해|잡|변경|시간|일정|스케줄)"
    r"|장착\s*(?:가능|예약|시간|일정)"
    r"|방문\s*(?:예약|시간|일정)"
    r"|가능한\s*(?:날짜|시간|일정)"
    r"|(?:언제|몇\s*시|시간|날짜).{0,30}(?:예약|방문|장착).{0,30}(?:한가|한산|여유|덜\s*붐비|덜\s*바쁘|안\s*붐비)"
    r"|(?:예약|방문|장착).{0,30}(?:언제|몇\s*시|시간|날짜).{0,30}(?:한가|한산|여유|덜\s*붐비|덜\s*바쁘|안\s*붐비)"
    r"|(?:한가|한산|여유|덜\s*붐비|덜\s*바쁘|안\s*붐비).{0,30}(?:예약|방문|장착|시간|날짜)"
    r"|스케줄(?:표)?"
    r"|시간표"
    r"|(?:내일|오늘|모레|이번\s*주|다음\s*주|[0-9]{1,2}\s*시).{0,20}(?:가능|예약|되|돼|비어|장착)"
    r"|(?:예약|장착).{0,20}(?:내일|오늘|모레|[0-9]{1,2}\s*시)",
    re.IGNORECASE,
)
_ARRIVAL_OR_STATUS_VISIT_RE = re.compile(
    r"(?:타이어|상품|물건|주문|매장).{0,20}(?:도착|입고|왔다|왔대|왔다고|전화|연락)"
    r"|(?:도착|입고).{0,20}(?:전화|연락|문자)"
    r"|(?:지금|바로|오늘).{0,10}(?:가도|가면|방문해도|방문하면)\s*(?:돼|되|되나|될까|가능)",
    re.IGNORECASE,
)
_RESERVATION_STATUS_RE = re.compile(
    r"예약.{0,12}(?:됐|되었|잡혔|맞|확인)"
    r"|방문만\s*하면\s*(?:돼|되)"
    r"|그냥\s*(?:가도|가면)\s*(?:돼|되)",
    re.IGNORECASE,
)
_STORE_NAME_SELECTION_RE = re.compile(r"(?:티스테이션|점\s*$)", re.IGNORECASE)
_STORE_SELECTION_CONTEXT_RE = re.compile(
    r"(?:원하시는|선택하신|요청하신\s*조건).{0,40}매장.{0,20}선택"
    r"|원하시는\s*매장.{0,20}(?:있나요|맞나요|어느\s*곳)"
    r"|매장\s*[0-9]+\s*곳.{0,30}선택"
    r"|매장을\s*선택",
    re.IGNORECASE,
)


def deterministic_schedule_gate_decision(
    user_text: str,
    *,
    tool_args: dict | None = None,
    recent_context: str = "",
) -> ScheduleToolGateDecision | None:
    """Return a deterministic decision for high-confidence cases."""
    text = (user_text or "").strip()
    if not text:
        return None

    if (
        isinstance(tool_args, dict)
        and tool_args.get("shop_id")
        and _STORE_NAME_SELECTION_RE.search(text)
        and _STORE_SELECTION_CONTEXT_RE.search(recent_context or "")
    ):
        return ScheduleToolGateDecision(
            allow=True,
            action="allow",
            reason="User selected a store from the previous booking/store candidate list.",
        )
    if _EXPLICIT_SCHEDULE_REQUEST_RE.search(text):
        return ScheduleToolGateDecision(
            allow=True,
            action="allow",
            reason="User explicitly asks for available reservation or install time slots.",
        )
    if _ARRIVAL_OR_STATUS_VISIT_RE.search(text):
        return ScheduleToolGateDecision(
            allow=False,
            action="check_order",
            reason="Arrival or store-visit status question should not render booking slots.",
        )
    if _RESERVATION_STATUS_RE.search(text):
        return ScheduleToolGateDecision(
            allow=False,
            action="check_order",
            reason="Reservation/status confirmation question should use existing order or reservation context.",
        )
    return None


@lru_cache(maxsize=1)
def _schedule_gate_model():
    llm = ChatLiteLLM(
        api_base=settings.AI_GATEWAY_BASE_URL,
        api_key=settings.AI_GATEWAY_API_KEY,
        model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL_MINI}",
        streaming=False,
        request_timeout=8,
    )
    return llm.with_structured_output(ScheduleToolGateDecision)


def decide_schedule_tool_gate(
    *,
    user_text: str,
    tool_args: dict | None = None,
    recent_context: str = "",
    allowed_by_tool_plan: bool = False,
) -> ScheduleToolGateDecision:
    """Decide whether the datepick-producing schedule tool may run."""
    deterministic = deterministic_schedule_gate_decision(
        user_text,
        tool_args=tool_args,
        recent_context=recent_context,
    )
    if deterministic is not None:
        return deterministic
    if allowed_by_tool_plan:
        return ScheduleToolGateDecision(
            allow=True,
            action="allow",
            reason="ToolPlan allows get_store_schedule_tool; schedule gate is advisory for this action.",
        )

    prompt = dedent(f"""
    You are a pre-tool safety gate for a Korean tire-commerce chatbot.
    Decide whether calling get_store_schedule_tool is appropriate for the CURRENT user message.

    get_store_schedule_tool returns a reservation date/time picker. Allow it only when the user is asking to see,
    choose, change, or verify available reservation/install time slots.

    Block it when the user is asking about order status, tire arrival at a store, whether they can just visit now
    after receiving a store call/message, reservation status confirmation, cancellation, delivery, product, price,
    coupon, or generic store information. In blocked cases choose:
    - check_order: order, arrival, delivery, reservation-status, or "can I go now" after arrival notification
    - answer_from_context: generic text answer can be made from existing context
    - ask_clarify: insufficient information or truly ambiguous

    Current user message:
    {user_text}

    Candidate tool args:
    {tool_args or {}}

    Recent context summary:
    {recent_context[-1200:]}
    """).strip()

    try:
        decision = _schedule_gate_model().invoke(prompt)
        if isinstance(decision, ScheduleToolGateDecision):
            return decision
        return ScheduleToolGateDecision.model_validate(decision)
    except Exception as exc:
        logger.warning("[SCHEDULE_TOOL_GATE] LLM decision failed; blocking conservatively: %s", exc)
        return ScheduleToolGateDecision(
            allow=False,
            action="ask_clarify",
            reason="LLM gate failed; conservatively blocked schedule tool.",
        )


def build_blocked_schedule_event(
    *,
    decision: ScheduleToolGateDecision,
    user_text: str,
) -> dict:
    """Build a user-facing quickReply when the schedule tool is blocked."""
    if decision.action == "check_order":
        assistant_response = (
            "매장에서 타이어 도착 연락을 받으신 상황이라면 예약 시간과 매장 작업 상황 기준으로 방문 가능 여부가 달라질 수 있어요. "
            "예약/주문 내역을 먼저 확인해 드릴게요."
        )
        quick_replies = [
            {"label": "주문 내역 확인", "domain": "TRANSACTION"},
            {"label": "예약 내역 확인", "domain": "TRANSACTION"},
        ]
    elif decision.action == "answer_from_context":
        assistant_response = "예약 가능 시간표를 새로 열기보다는 현재 진행 중인 주문/매장 정보를 기준으로 확인해야 해요."
        quick_replies = [
            {"label": "주문 내역 확인", "domain": "TRANSACTION"},
            {"label": "매장 상세 보기", "domain": "TRANSACTION"},
        ]
    else:
        assistant_response = "방문 예약 시간을 확인하려는 건지, 이미 도착한 타이어를 찾으러 가도 되는지 확인하려는 건지 알려주세요."
        quick_replies = [
            {"label": "예약 가능 시간 보기", "domain": "TRANSACTION"},
            {"label": "주문 내역 확인", "domain": "TRANSACTION"},
        ]

    return {
        "type": "data",
        "template": "quickReply",
        "assistant_response_source": "schedule_tool_gate",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": quick_replies,
            "predictedDomains": ["TRANSACTION"],
        },
    }
