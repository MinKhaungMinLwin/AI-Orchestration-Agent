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


class QuickReplyChip(BaseModel):
    label: str = Field(description="버튼 라벨 (한국어, 12자 이내)")
    domain: str = Field(description="LEADING | DISCOVERY | TRANSACTION | SUPPORT")


class QuickReplySuggestion(BaseModel):
    quick_replies: list[QuickReplyChip] = Field(default_factory=list, max_length=4)


async def suggest_quick_replies(user_text: str, answer: str) -> list[dict]:
    """Return [{label, domain}, ...] chips for the FE, or [] on failure."""
    try:
        llm = get_router_llm().with_structured_output(QuickReplySuggestion, method="function_calling")
        suggestion = await llm.ainvoke(
            [
                ("system", QUICK_REPLY_PROMPT),
                ("user", f"사용자 질문:\n{user_text}\n\n챗봇 답변:\n{answer[:2000]}"),
            ]
        )
        return [
            {"label": chip.label, "domain": chip.domain}
            for chip in suggestion.quick_replies
            if chip.label and chip.domain in _DOMAINS
        ]
    except Exception:
        logger.exception("[CHAT_V3] quick reply suggestion failed")
        return []
