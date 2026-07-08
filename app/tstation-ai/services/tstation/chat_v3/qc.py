"""Optional fact-check pass over the final answer, gated by AI_QC_ENABLED.

LLM-based (mini model): compares the answer against raw tool outputs and
returns a corrected answer only when a factual mismatch is found.
"""

import logging

from pydantic import BaseModel, Field

from config.env import settings
from services.tstation.chat_v3.llm import get_router_llm

logger = logging.getLogger(__name__)

_QC_PROMPT = (
    "당신은 챗봇 답변의 사실 검증기입니다. 도구 실행 결과(원본 데이터)와 챗봇 답변을 비교하세요.\n"
    "- 답변의 수치·가격·매장명·재고·날짜가 도구 결과와 다르면 passed=false, 도구 결과 기준으로 고친 "
    "corrected_response를 작성하세요 (원래 답변의 어조 유지).\n"
    "- 도구 결과에 없는 내용이라도 일반 상식/안내 수준이면 통과시키세요.\n"
    "- 문제가 없으면 passed=true, corrected_response는 비워두세요."
)


class QCVerdict(BaseModel):
    passed: bool = Field(description="답변이 도구 결과와 사실적으로 일치하면 true")
    corrected_response: str = Field(default="", description="passed=false일 때 수정된 답변")


async def verify_answer(answer: str, tool_calls: list[dict], trace_config: dict | None = None) -> str:
    """Return the (possibly corrected) answer. No-op unless AI_QC_ENABLED."""
    if not settings.AI_QC_ENABLED or not tool_calls or not answer:
        return answer
    facts = "\n\n".join(
        f"[{call['name']}] input={call['args']}\n{call['output'][:3000]}" for call in tool_calls
    )
    try:
        llm = get_router_llm().with_structured_output(QCVerdict, method="function_calling")
        messages = [("system", _QC_PROMPT), ("user", f"## 도구 결과\n{facts[:12000]}\n\n## 챗봇 답변\n{answer}")]
        verdict = await llm.ainvoke(messages, config=trace_config) if trace_config else await llm.ainvoke(messages)
        if not verdict.passed and verdict.corrected_response.strip():
            logger.info("[CHAT_V3] QC corrected the answer")
            return verdict.corrected_response.strip()
    except Exception:
        logger.exception("[CHAT_V3] QC verification failed — keeping original answer")
    return answer
