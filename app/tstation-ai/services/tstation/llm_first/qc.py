from __future__ import annotations

from services.tstation import qc_verifier
from services.tstation.llm_first.models import FactBundle
from services.tstation.llm_first.tooling.registry import CONFIRMABLE_SIDE_EFFECT_TOOLS, SIDE_EFFECT_TOOLS

_COMPLETE_FORBIDDEN = ("주문이 완료", "예약이 완료", "장바구니에 담았", "쿠폰을 발급", "1:1 문의가 등록")


def _is_successful_tool_result(result: object) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("status") == "error":
        return False
    data = result.get("data")
    if isinstance(data, dict):
        if data.get("result") is True:
            return True
        nested = data.get("data")
        if nested not in (None, "", {}, []):
            return True
    return result.get("status") == "success"


def verify_response(text: str, bundle: FactBundle) -> tuple[str, dict | None]:
    for call in bundle.tool_calls:
        if call.tool_name in SIDE_EFFECT_TOOLS and not call.blocked:
            if call.tool_name in CONFIRMABLE_SIDE_EFFECT_TOOLS and _is_successful_tool_result(call.result):
                continue
            return "side_effect_tool_executed", _guard_event("요청하신 실행 작업은 MVP에서는 바로 처리하지 않고 확인 단계까지만 안내할 수 있어요.")
    successful_cart = any(
        call.tool_name == "save_to_cart_tool"
        and not call.blocked
        and _is_successful_tool_result(call.result)
        for call in bundle.tool_calls
    )
    for phrase in _COMPLETE_FORBIDDEN:
        if phrase == "장바구니에 담았" and successful_cart:
            continue
        if phrase in text:
            return "completion_claim_blocked", _guard_event("현재 MVP에서는 주문/예약/쿠폰발급/1:1 문의 등록을 완료 처리하지 않습니다. 확인 단계까지만 도와드릴게요.")

    sources = [(call.tool_name, call.result) for call in bundle.tool_calls if not call.blocked]
    mismatches = qc_verifier.verify_draft(text, sources)
    if mismatches:
        return "fact_mismatch", None
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
