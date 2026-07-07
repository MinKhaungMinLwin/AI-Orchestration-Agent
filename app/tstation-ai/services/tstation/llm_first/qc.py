from __future__ import annotations

from services.tstation import qc_verifier
from services.tstation.llm_first.models import FactBundle
from services.tstation.llm_first.tools import SIDE_EFFECT_TOOLS

_COMPLETE_FORBIDDEN = ("주문이 완료", "예약이 완료", "장바구니에 담았", "쿠폰을 발급", "1:1 문의가 등록")


def verify_response(text: str, bundle: FactBundle) -> tuple[str, dict | None]:
    for call in bundle.tool_calls:
        if call.tool_name in SIDE_EFFECT_TOOLS and not call.blocked:
            return "side_effect_tool_executed", _guard_event("요청하신 실행 작업은 MVP에서는 바로 처리하지 않고 확인 단계까지만 안내할 수 있어요.")
    if any(phrase in text for phrase in _COMPLETE_FORBIDDEN):
        return "completion_claim_blocked", _guard_event("현재 MVP에서는 주문/예약/장바구니/쿠폰발급/1:1 문의 등록을 완료 처리하지 않습니다. 확인 단계까지만 도와드릴게요.")

    sources = [(call.tool_name, call.result) for call in bundle.tool_calls if not call.blocked]
    mismatches = qc_verifier.verify_draft(text, sources)
    if mismatches:
        return "fact_mismatch", _guard_event("도구 결과와 답변 숫자가 맞지 않아 단정 안내를 중단했습니다. 다시 확인해 드릴게요.")
    return "ok", None


def _guard_event(message: str) -> dict:
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": message,
            "quickReplies": [{"label": "다시 확인", "domain": "LEADING"}],
            "metadata": {"source": "llm_first_qc_guard"},
        },
    }

