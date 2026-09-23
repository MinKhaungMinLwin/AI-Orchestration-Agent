"""Deterministic response policy for leading-domain guardrails."""

from __future__ import annotations

import re
from typing import Any

_COMPLAINT_SCOPE_SUPPORT_CHIPS: list[dict] = [
    {"label": "타이어 추천", "domain": "DISCOVERY"},
    {"label": "가격 조회", "domain": "DISCOVERY"},
    {"label": "매장 찾기", "domain": "TRANSACTION"},
]

_COMPLAINT_TONE_RE = re.compile(
    r"짜증|화나|화가\s*나|열받|빡치|개빡|최악|엉망|이딴|드럽게|못해|못한다|되는\s*일이\s*없|"
    r"불만|클레임|항의|뭐\s*이런|제대로\s*해|어이\s*없|힘들|미칠|위로",
    re.IGNORECASE,
)
_TSTATION_COMPLAINT_SCOPE_RE = re.compile(
    r"타이어|상품|제품|주문|결제|배송|장착|예약|매장|지점|쿠폰|차량|차번호|챗봇|답변|상담|"
    r"티스테이션|T[\s-]*Station|한국타이어|벤투스|키너지|다이나프로|아이온|라우펜|가격|재고|"
    r"환불|반품|교환|취소|오류|에러",
    re.IGNORECASE,
)
_OUT_OF_SCOPE_COMPLAINT_RE = re.compile(
    r"주식|투자|증권|코스피|코스닥|나스닥|상장|주가|매수|매도|손실|수익률|취업|면접|회사\s*생활|"
    r"연애|정치|선거|법률|소송|의료|병원|건강|타사|다른\s*회사|은행|보험|부동산|코인|비트코인",
    re.IGNORECASE,
)
_LEGAL_ACTION_REQUEST_RE = re.compile(
    r"고소|소송|법적\s*(?:대응|조치|절차)|분쟁\s*조정|분쟁조정|내용\s*증명|내용증명|신고\s*(?:방법|절차|하는\s*법)",
    re.IGNORECASE,
)
_LEGAL_ACTION_TSTATION_SCOPE_RE = re.compile(
    r"티스테이션|T[\s-]*Station|한국타이어|매장|지점|[가-힣A-Za-z0-9]{2,20}점|"
    r"장착|예약|방문|응대|서비스|고객센터",
    re.IGNORECASE,
)
_PRIVATE_CONTACT_REQUEST_RE = re.compile(
    r"(?:관리자|직원|담당자|사장님|대표|매니저|점장|기사님|정비사|상담원|상담사).{0,16}"
    r"(?:개인\s*)?(?:휴대폰|핸드폰|폰|전화번호|번호|연락처|연락\s*번호)"
    r"|(?:개인\s*)?(?:휴대폰|핸드폰|폰|전화번호|번호|연락처|연락\s*번호).{0,16}"
    r"(?:관리자|직원|담당자|사장님|대표|매니저|점장|기사님|정비사|상담원|상담사)",
    re.IGNORECASE,
)
_STORE_OFFICIAL_CONTACT_ALLOWED_RE = re.compile(r"매장\s*(?:공식\s*)?(?:전화|연락처)|매장으로\s*전화", re.IGNORECASE)


def is_private_contact_request(text: str | None) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    if _STORE_OFFICIAL_CONTACT_ALLOWED_RE.search(value) and not re.search(
        r"개인|휴대폰|핸드폰|사장님|관리자|직원|담당자|매니저|점장",
        value,
        re.IGNORECASE,
    ):
        return False
    return bool(_PRIVATE_CONTACT_REQUEST_RE.search(value))


def is_tstation_legal_action_request(text: str | None) -> bool:
    value = str(text or "")
    return bool(_LEGAL_ACTION_REQUEST_RE.search(value) and _LEGAL_ACTION_TSTATION_SCOPE_RE.search(value))


def build_privacy_contact_request_event(text: str | None) -> dict | None:
    if not is_private_contact_request(text):
        return None
    has_store_anchor = bool(re.search(r"(?:[가-힣A-Za-z0-9]+점|티스테이션\s*[가-힣A-Za-z0-9]+)", str(text or "")))
    quick_replies = [
        {"label": "1:1 문의하기", "domain": "SUPPORT"},
        {"label": "고객센터 안내", "domain": "SUPPORT"},
    ]
    if has_store_anchor:
        quick_replies.append({"label": "매장 공식 연락처", "domain": "TRANSACTION"})
    else:
        quick_replies.append({"label": "매장 찾기", "domain": "TRANSACTION"})
    assistant_response = (
        "관리자나 직원의 개인 휴대폰 번호는 개인정보라 안내해드릴 수 없어요. "
        "문의나 불편사항은 공식 고객센터 또는 1:1 문의로 접수해 주세요."
    )
    if has_store_anchor:
        assistant_response += " 매장명이 확인된 경우에는 공개된 매장 공식 전화번호 기준으로만 안내할 수 있어요."
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "support",
        "assistant_response_source": "code_privacy_contact_request_guard",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": quick_replies,
            "predictedDomains": ["SUPPORT", "TRANSACTION"],
            "metadata": {
                "policy_intent": "privacy_contact_request",
                "hard_block": True,
                "safety_category": "privacy_contact_request",
                "storeOfficialContactAllowed": has_store_anchor,
            },
        },
    }


def infer_complaint_scope(text: str | None) -> str:
    value = str(text or "").strip()
    if not value or not (_COMPLAINT_TONE_RE.search(value) or _LEGAL_ACTION_REQUEST_RE.search(value)):
        return "none"
    if _LEGAL_ACTION_REQUEST_RE.search(value) and _LEGAL_ACTION_TSTATION_SCOPE_RE.search(value):
        return "tstation_service_complaint"
    if _OUT_OF_SCOPE_COMPLAINT_RE.search(value):
        return "out_of_scope_complaint"
    if _TSTATION_COMPLAINT_SCOPE_RE.search(value):
        return "tstation_service_complaint"
    return "unclear_complaint"


def complaint_scope_for_turn(text: str | None, routing_result: Any | None = None) -> str:
    scope = str(getattr(routing_result, "complaint_scope", "") or "").strip()
    if scope in {"none", "tstation_service_complaint", "out_of_scope_complaint", "unclear_complaint"}:
        if scope == "none":
            inferred = infer_complaint_scope(text)
            return inferred if inferred != "none" else scope
        return scope
    return infer_complaint_scope(text)


def build_complaint_scope_guard_event(scope: str) -> dict | None:
    if scope == "out_of_scope_complaint":
        return {
            "type": "data",
            "template": "quickReply",
            "data": {
                "assistantResponse": (
                    "말씀하신 내용은 제가 직접 도와드리기 어려운 주제예요. "
                    "저는 타이어 추천, 가격 조회, 매장 검색, 주문/장착 관련 문의를 도와드릴 수 있어요."
                ),
                "quickReplies": list(_COMPLAINT_SCOPE_SUPPORT_CHIPS),
                "predictedDomains": ["DISCOVERY", "TRANSACTION"],
            },
            "source_domain": "leading",
            "assistant_response_source": "code_complaint_scope_guard",
        }
    return None
