"""Quick-reply chips for the final answer — suggested by the mini model.

Replaces V2's hardcoded chip tables: the LLM proposes context-relevant
buttons; on any failure the answer simply ships without chips.
"""

import logging

from pydantic import BaseModel, Field

from services.tstation.chat_v3.llm import get_router_llm
from services.tstation.chat_v3.prompts.composer import QUICK_REPLY_PROMPT

logger = logging.getLogger(__name__)

_DOMAINS = {"LEADING", "DISCOVERY", "TRANSACTION", "SUPPORT"}

# CALL actions are dead-ends: the bot cannot place calls and has no reliable
# store/support phone numbers. Only call-intent labels are blocked — chips
# about managing a phone number ("전화번호 변경" 등) stay allowed.
_BLOCKED_CALL_PHRASES = (
    "전화 문의",
    "전화문의",
    "전화 연결",
    "전화연결",
    "전화하기",
    "전화 걸기",
    "전화걸기",
    "통화 연결",
    "통화하기",
)


def _is_blocked_label(label: str) -> bool:
    normalized = label.strip()
    return any(phrase in normalized for phrase in _BLOCKED_CALL_PHRASES)


class QuickReplyChip(BaseModel):
    label: str = Field(description="버튼 라벨 (한국어, 12자 이내)")
    domain: str = Field(description="LEADING | DISCOVERY | TRANSACTION | SUPPORT")


class QuickReplySuggestion(BaseModel):
    quick_replies: list[QuickReplyChip] = Field(default_factory=list, max_length=2)


async def suggest_quick_replies(
    user_text: str,
    answer: str,
    trace_config: dict | None = None,
    flow_hint: str | None = None,
) -> list[dict]:
    """Return [{label, domain}, ...] chips for the FE, or [] on failure."""
    try:
        llm = get_router_llm().with_structured_output(QuickReplySuggestion, method="function_calling")
        user_content = f"사용자 질문:\n{user_text}\n\n챗봇 답변:\n{answer[:2000]}"
        if flow_hint:
            user_content += f"\n\n[진행 상태]\n{flow_hint}"
        messages = [
            ("system", QUICK_REPLY_PROMPT),
            ("user", user_content),
        ]
        suggestion = await llm.ainvoke(messages, config=trace_config) if trace_config else await llm.ainvoke(messages)
        return [
            {"label": chip.label, "domain": chip.domain}
            for chip in suggestion.quick_replies
            if chip.label and chip.domain in _DOMAINS and not _is_blocked_label(chip.label)
        ]
    except Exception:
        logger.exception("[CHAT_V3] quick reply suggestion failed")
        return []
