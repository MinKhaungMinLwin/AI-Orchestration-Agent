import os
from urllib.parse import urlencode

from fastapi import APIRouter
from app.schemas import EscalationRequest, EscalationResponse

router = APIRouter(
    prefix="/api/escalation",
    tags=["Fallback / Escalation AF - 상담 연결"],
)

# 상담 페이지 베이스 URL - 환경변수로 설정
_ESCALATION_BASE_URL = os.getenv("ESCALATION_BASE_URL", "http://cs.example.com")

# "대화량 충분" 판단 기준: 메시지 수 (환경변수로 조정 가능)
_MSG_THRESHOLD = int(os.getenv("ESCALATION_MSG_THRESHOLD", "3"))

# 문의 유형별 상담 채널 정책
# 미지정 또는 미등록 유형은 "chat"(기본)으로 처리
_CHANNEL_POLICY: dict[str, str] = {
    "PAYMENT":   "call",   # 결제 문의 → 전화 상담
    "COMPLAINT": "call",   # 불만 접수 → 전화 상담
    "EMAIL":     "email",  # 이메일 문의
}

# 채널별 상담 페이지 경로
_CHANNEL_PATH: dict[str, str] = {
    "chat":  "/cs/chat",
    "call":  "/cs/call",
    "email": "/cs/email",
}


# --------------------------------------------------------------------------- #
#  내부 유틸                                                                    #
# --------------------------------------------------------------------------- #

def _resolve_channel(inq_type_cd: str | None) -> tuple[str, bool]:
    """문의 유형으로 채널을 결정합니다.

    Returns:
        (channel, is_policy_routed)
    """
    if inq_type_cd and inq_type_cd.upper() in _CHANNEL_POLICY:
        return _CHANNEL_POLICY[inq_type_cd.upper()], True
    return "chat", False


def _build_url(channel: str, params: dict) -> str:
    base = _ESCALATION_BASE_URL.rstrip("/")
    path = _CHANNEL_PATH.get(channel, "/cs/chat")
    qs = urlencode({k: v for k, v in params.items() if v is not None})
    return f"{base}{path}?{qs}" if qs else f"{base}{path}"


# --------------------------------------------------------------------------- #
#  엔드포인트                                                                   #
# --------------------------------------------------------------------------- #

@router.post(
    "",
    response_model=EscalationResponse,
    summary="상담 연결 분기 처리",
    description=(
        "대화량과 문의 유형에 따라 3가지 분기로 처리합니다.\n\n"
        "- **with_summary**: 대화 메시지 수 ≥ 기준치(`ESCALATION_MSG_THRESHOLD`, 기본 3)이고 "
        "요약(`summary`)이 있는 경우 — 요약을 `summary` 쿼리 파라미터로 URL 인코딩하여 전달\n"
        "- **direct**: 대화량이 적거나 요약이 없는 경우 — 요약 없이 상담 페이지로 바로 전달\n"
        "- **policy**: `inq_type_cd`가 정책 테이블에 등록된 경우 — 지정 채널(call/email 등)로 분기\n\n"
        "**summary URL 파라미터 규격**: `summary` 키, URL 인코딩(percent-encoding) 적용, "
        "예) `?inq_type_cd=ORDER&mbr_no=M001&summary=%EB%B0%B0%EC%86%A1+...`"
    ),
)
async def escalate(body: EscalationRequest) -> EscalationResponse:

    # ── 1. 채널 결정 (정책 기반 분기) ────────────────────────────────────────
    channel, is_policy = _resolve_channel(body.inq_type_cd)

    # ── 2. 요약 포함 여부 결정 ────────────────────────────────────────────────
    has_summary = (
        body.msg_count >= _MSG_THRESHOLD
        and bool(body.summary)
    )

    # ── 3. 분기 유형 결정 ─────────────────────────────────────────────────────
    if is_policy:
        branch = "policy"
    elif has_summary:
        branch = "with_summary"
    else:
        branch = "direct"

    # ── 4. 리다이렉트 URL 생성 ────────────────────────────────────────────────
    # summary는 urlencode 내부에서 percent-encoding 처리됨
    url_params: dict = {}
    if body.inq_type_cd:
        url_params["inq_type_cd"] = body.inq_type_cd
    if body.mbr_no:
        url_params["mbr_no"] = body.mbr_no
    if has_summary and body.summary:
        url_params["summary"] = body.summary

    redirect_url = _build_url(channel, url_params)

    return EscalationResponse(
        channel=channel,
        branch=branch,
        has_summary=has_summary,
        redirect_url=redirect_url,
    )
