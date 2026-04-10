"""
PII (Personally Identifiable Information) Guardrail.

Detects sensitive personal information in user messages and blocks them
before they reach any AI agent. This is a hard filter — messages containing
PII patterns are rejected immediately with a user-friendly notice.
"""

import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  PII 패턴 정의
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    # 주민등록번호: 6자리-7자리 (예: 900101-1234567)
    ("주민등록번호", re.compile(r"\d{6}\s*[-–]\s*[1-4]\d{6}")),
    # 여권번호: 알파벳 1~2자리 + 숫자 7~8자리 (예: M12345678, AB1234567)
    # Exclude goods_no pattern G + 10+ digits and shop_id pattern F + 5 digits
    ("여권번호", re.compile(r"(?!G\d{10,}|F\d{5})[A-Za-z]{1,2}\d{7,8}")),
    # 운전면허번호: 지역코드 2자리-숫자 2자리-숫자 6자리-숫자 2자리 (예: 11-22-333333-44)
    ("운전면허번호", re.compile(r"\d{2}\s*[-–]\s*\d{2}\s*[-–]\s*\d{6}\s*[-–]\s*\d{2}")),
    # 계좌번호: 10~16자리 숫자 (하이픈 포함/미포함)
    ("계좌번호", re.compile(r"\d{3,4}\s*[-–]\s*\d{2,6}\s*[-–]\s*\d{2,6}(?:\s*[-–]\s*\d{1,4})?")),
    # 카드번호: 4자리-4자리-4자리-4자리 (하이픈/공백)
    ("카드번호", re.compile(r"\d{4}\s*[-–\s]\s*\d{4}\s*[-–\s]\s*\d{4}\s*[-–\s]\s*\d{4}")),
    # 휴대폰번호: 010-XXXX-XXXX (하이픈 포함/미포함)
    ("연락처", re.compile(r"01[016789]\s*[-–.]?\s*\d{3,4}\s*[-–.]?\s*\d{4}")),
    # 일반 전화번호: 02-XXXX-XXXX, 031-XXX-XXXX 등
    ("연락처", re.compile(r"0\d{1,2}\s*[-–.]\s*\d{3,4}\s*[-–.]\s*\d{4}")),
    # 이메일 주소
    ("이메일", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    # 외국인등록번호: 주민번호와 동일 형식이나 뒤 첫자리가 5~8
    ("외국인등록번호", re.compile(r"\d{6}\s*[-–]\s*[5-8]\d{6}")),
]

# 민감정보 기억/저장 관련 키워드
_REMEMBER_PII_RE = re.compile(
    r"(기억|저장|메모|보관|기록|등록).{0,20}"
    r"(주민등록|여권|면허|계좌|카드|전화|휴대폰|연락처|비밀번호|패스워드|주소|이메일|개인정보)"
    r"|"
    r"(주민등록|여권|면허|계좌|카드|전화|휴대폰|연락처|비밀번호|패스워드|주소|이메일|개인정보)"
    r".{0,20}(기억|저장|메모|보관|기록|등록)",
    re.IGNORECASE,
)

GUARDRAIL_RESPONSE = (
    "고객님의 소중한 개인정보 보호를 위해, "
    "민감한 개인정보는 입력하실 수 없으며 저장되지 않습니다.\n\n"
    "타이어 관련 문의사항이 있으시면 편하게 말씀해 주세요."
)


def check_pii(text: str) -> str | None:
    """
    Check if text contains PII patterns or PII-remember requests.

    Returns:
        The name of the detected PII category (e.g. "주민등록번호"),
        or None if no PII is found.
    """
    for name, pattern in _PII_PATTERNS:
        if pattern.search(text):
            logger.warning(f"[PII_GUARDRAIL] Detected: {name}")
            return name

    if _REMEMBER_PII_RE.search(text):
        logger.warning("[PII_GUARDRAIL] Detected: PII remember/store request")
        return "개인정보 저장 요청"

    return None
