"""Optional fact-check pass over the final answer, gated by AI_QC_ENABLED.

LLM-based (mini model): compares the answer against raw tool outputs and
returns a corrected answer only when a factual mismatch is found.
"""

import logging

from pydantic import BaseModel, Field

from config.env import settings
from services.tstation.chat_v3.executor import _model_visible_tool_output
from services.tstation.chat_v3.llm import get_router_llm

logger = logging.getLogger(__name__)

_QC_PROMPT = (
    "당신은 챗봇 답변의 사실 검증기입니다. 도구 실행 결과(원본 데이터)와 챗봇 답변을 비교하세요.\n"
    "- 답변의 수치·가격·매장명·재고·날짜가 도구 결과와 다르면 passed=false와 reason을 작성하세요.\n"
    "- corrected_response는 디버그 참고용이며 사용자에게 그대로 적용되지 않습니다.\n"
    "- 도구 결과에 없는 내용이라도 일반 상식/안내 수준이면 통과시키세요.\n"
    "- 문제가 없으면 passed=true, reason과 corrected_response는 비워두세요."
)


class QCVerdict(BaseModel):
    passed: bool = Field(description="답변이 도구 결과와 사실적으로 일치하면 true")
    reason: str = Field(default="", description="passed=false일 때 불일치 사유")
    corrected_response: str = Field(default="", description="passed=false일 때 수정된 답변")


class QCResult(BaseModel):
    answer: str = Field(description="Original answer. QC never rewrites the user-visible response.")
    passed: bool = Field(default=True, description="Whether QC found a factual mismatch.")
    corrected_response: str = Field(default="", description="LLM-suggested correction retained for trace/debug only.")
    reason: str = Field(default="", description="Short machine-readable QC outcome reason.")

    @property
    def failed(self) -> bool:
        return not self.passed


async def verify_answer(answer: str, tool_calls: list[dict], trace_config: dict | None = None) -> QCResult:
    """Return QC verdict metadata while preserving the original answer."""
    if not settings.AI_QC_ENABLED or not tool_calls or not answer:
        return QCResult(answer=answer, reason="qc_disabled_or_noop")
    facts = "\n\n".join(
        f"[{call.get('name')}] input={call.get('args')}\n"
        f"{_model_visible_tool_output(str(call.get('name') or ''), str(call.get('output') or ''))[:4000]}"
        for call in tool_calls
    )
    try:
        llm = get_router_llm().with_structured_output(QCVerdict, method="function_calling")
        messages = [("system", _QC_PROMPT), ("user", f"## 도구 결과\n{facts[:12000]}\n\n## 챗봇 답변\n{answer}")]
        verdict = await llm.ainvoke(messages, config=trace_config) if trace_config else await llm.ainvoke(messages)
        failed_reason = verdict.reason.strip() or "qc_failed_correction_suppressed"
        if not verdict.passed and verdict.corrected_response.strip():
            logger.info("[CHAT_V3] QC flagged the answer; keeping original response")
            return QCResult(
                answer=answer,
                passed=False,
                corrected_response=verdict.corrected_response.strip(),
                reason=failed_reason,
            )
        if not verdict.passed:
            logger.info("[CHAT_V3] QC flagged the answer without a correction; keeping original response")
            return QCResult(answer=answer, passed=False, reason=failed_reason)
    except Exception:
        logger.exception("[CHAT_V3] QC verification failed — keeping original answer")
        return QCResult(answer=answer, reason="qc_error")
    return QCResult(answer=answer, reason="qc_passed")
