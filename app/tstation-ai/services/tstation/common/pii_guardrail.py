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
    # ── 주민등록번호 / 외국인등록번호 ──
    # 구분자 형식: 900101-1234567
    ("주민등록번호", re.compile(r"\d{6}\s*[-–]\s*[1-4]\d{6}")),
    # 13자리 연속 (구분자 없음): 9001011234567
    ("주민등록번호", re.compile(r"\b\d{13}\b")),
    # 외국인등록번호: 뒤 첫자리 5~8
    ("외국인등록번호", re.compile(r"\d{6}\s*[-–]\s*[5-8]\d{6}")),
    # 키워드 기반: "주민번호 ..." / "주민등록번호 ..."
    ("주민등록번호", re.compile(r"주민(?:등록)?(?:번호)?.{0,10}\d{6,13}")),

    # ── 카드번호 ──
    # 구분자 형식: 4459-1234-5558-4495
    ("카드번호", re.compile(r"\d{4}\s*[-–\s]\s*\d{4}\s*[-–\s]\s*\d{4}\s*[-–\s]\s*\d{4}")),
    # 16자리 연속: 4459123455584495
    ("카드번호", re.compile(r"\b\d{16}\b")),
    # 키워드 기반: "카드번호 4459123455584495", "카드 정보는 ..."
    ("카드번호", re.compile(r"카드.{0,10}\d{10,16}")),

    # ── 계좌번호 ──
    # 구분자 형식: 110-123-456789
    # \b : 숫자 중간 매칭 방지 (예: "2026"의 "026" 방지)
    # (?!(?:19|20)\d{2}[-–]) : ISO 날짜 YYYY-MM-DD 오탐 방지 (예: 2026-06-04)
    ("계좌번호", re.compile(r"\b(?!(?:19|20)\d{2}[-–])\d{3,4}\s*[-–]\s*\d{2,6}\s*[-–]\s*\d{2,6}(?:\s*[-–]\s*\d{1,4})?")),
    # 키워드 기반: "계좌번호는 123556958496"
    ("계좌번호", re.compile(r"계좌.{0,10}\d{10,16}")),

    # ── 결제정보 ──
    # CVC/CVV: 3~4자리
    ("결제정보", re.compile(r"(?:CVC|CVV|시큐리티\s*코드|보안\s*코드).{0,10}(?:알려|보여|확인|조회)", re.IGNORECASE)),
    ("결제정보", re.compile(r"(?:CVC|CVV|시큐리티\s*코드|보안\s*코드).{0,10}\d{3,4}", re.IGNORECASE)),
    # 유효기간: MM/YY, MM-YY
    ("결제정보", re.compile(r"(?:유효\s*기간|만료\s*일|expir).{0,10}\d{2}\s*[/\-]\s*\d{2,4}", re.IGNORECASE)),
    # 결제 키워드 + 숫자 조합
    ("결제정보", re.compile(r"결제.{0,5}(?:정보|번호|비번).{0,10}\d{4,}")),

    # ── 비밀번호 / PIN ──
    ("비밀번호", re.compile(r"(?:비밀\s*번호|비번|패스워드|password|PIN\s*번호|PIN\s*코드).{0,10}\d{4,}", re.IGNORECASE)),
    # 비밀번호 자체를 알려주는 경우: "비밀번호는 abc123", "비번 qwer1234", "password는 mypass123"
    # 값에 숫자나 영문이 포함되어야 함 (한국어 동사 "변경하고" 등 오탐 방지)
    ("비밀번호", re.compile(r"(?:비밀\s*번호|비번|패스워드|password|passwd|pw)(?:는|은|이|가|:\s*|\s+)\s*(?=\S*[A-Za-z0-9])\S{4,}", re.IGNORECASE)),

    # ── OTP / 인증 토큰 ──
    ("OTP", re.compile(r"(?:OTP|오티피|인증\s*번호|인증\s*코드|인증\s*토큰|보안\s*토큰).{0,10}\d{4,8}", re.IGNORECASE)),

    # ── 연락처 ──
    # 휴대폰: 010-XXXX-XXXX (하이픈 포함/미포함)
    ("연락처", re.compile(r"01[016789]\s*[-–.]?\s*\d{3,4}\s*[-–.]?\s*\d{4}")),
    # 일반전화: 02-XXXX-XXXX, 031-XXX-XXXX
    ("연락처", re.compile(r"0\d{1,2}\s*[-–.]\s*\d{3,4}\s*[-–.]\s*\d{4}")),
    # 키워드 기반: "연락처 01012345678", "전화번호는 ..."
    ("연락처", re.compile(r"(?:연락처|전화\s*번호|핸드폰|휴대폰).{0,10}0\d{8,10}")),

    # ── 여권번호 ──
    # Exclude: goods_no (G+10+), shop_id (F+5), order_no (O+15+)
    ("여권번호", re.compile(r"(?!G\d{10,}|F\d{5}|O\d{10,})[A-Za-z]{1,2}\d{7,8}")),

    # ── 운전면허번호 ──
    ("운전면허번호", re.compile(r"\d{2}\s*[-–]\s*\d{2}\s*[-–]\s*\d{6}\s*[-–]\s*\d{2}")),

    # ── 이메일 ──
    ("이메일", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
]

# 민감정보 기억/저장/삭제/변경 관련 키워드
_REMEMBER_PII_RE = re.compile(
    r"(기억|저장|메모|보관|기록|등록|삭제|지워|제거|파기|정정|변경|수정).{0,20}"
    r"(주민등록|주민번호|여권|면허|계좌|카드|전화|휴대폰|연락처|비밀번호|비번|패스워드|OTP|인증번호|PIN|주소|이메일|개인정보)"
    r"|"
    r"(주민등록|주민번호|여권|면허|계좌|카드|전화|휴대폰|연락처|비밀번호|비번|패스워드|OTP|인증번호|PIN|주소|이메일|개인정보)"
    r".{0,20}(기억|저장|메모|보관|기록|등록|삭제|지워|제거|파기|정정|변경|수정)",
    re.IGNORECASE,
)

# 저장된/소유한 민감정보를 채팅창에 표시하거나, 숫자가 아닌 말/글자/띄어쓰기 등으로 변환해 달라는 요청.
# 실제 값이 메시지에 없어도 exfiltration/transform request 자체가 위험하므로 hard block 한다.
_PII_SENSITIVE_INFO_RE = (
    r"연락처|전화\s*번호|휴대폰|핸드폰|폰\s*번호|비밀\s*번호|비번|패스워드|password|passwd|"
    r"카드\s*번호|카드\s*정보|계좌\s*번호|계좌\s*정보|주민\s*(?:등록)?\s*번호|주민번호|"
    r"여권\s*번호|운전\s*면허\s*번호|면허\s*번호|인증\s*번호|인증\s*코드|OTP|오티피|"
    r"이메일|메일\s*주소|개인\s*정보|민감\s*정보"
)
_PII_SELF_OR_STORED_RE = r"내|나의|제|저의|회원\s*정보|저장된|등록된|내\s*계정|계정에|마이페이지"
_PII_EXFILTRATION_ACTION_RE = (
    r"알려\s*줘|보여\s*줘|말해\s*줘|읽어\s*줘|써\s*줘|표시|노출|확인해\s*줘|채팅창에|"
    r"변환해\s*줘|풀어\s*줘|마스킹\s*풀|전체|일부\s*말고|일부만\s*말고|원문"
)
_PII_OBFUSCATION_RE = (
    r"공일공|영일영|하나둘셋|숫자\s*아니니까|숫자\s*말고|글자로|한글로|띄어서|"
    r"분리해서|마스킹\s*풀어서|일부\s*말고\s*전체|일부만\s*말고\s*전체|채팅창에|"
    r"변환해\s*줘|읽어\s*줘"
)
_PII_EXFILTRATION_OR_TRANSFORM_RE = re.compile(
    rf"(?:{_PII_SELF_OR_STORED_RE}).{{0,30}}(?:{_PII_SENSITIVE_INFO_RE}).{{0,40}}"
    rf"(?:{_PII_EXFILTRATION_ACTION_RE}|{_PII_OBFUSCATION_RE})|"
    rf"(?:{_PII_SENSITIVE_INFO_RE}).{{0,40}}(?:{_PII_OBFUSCATION_RE})|"
    rf"(?:{_PII_SENSITIVE_INFO_RE}).{{0,30}}(?:{_PII_EXFILTRATION_ACTION_RE}).{{0,30}}"
    rf"(?:{_PII_SELF_OR_STORED_RE})",
    re.IGNORECASE,
)

GUARDRAIL_RESPONSE = (
    "보안상 비밀번호, 카드번호, 주민번호, 여권번호, 연락처 같은 개인정보나 민감정보는 "
    "채팅창에 표시하거나 다른 형태로 변환해 드릴 수 없어요."
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

    if _PII_EXFILTRATION_OR_TRANSFORM_RE.search(text):
        logger.warning("[PII_GUARDRAIL] Detected: PII exfiltration/transform request")
        return "개인정보 노출/변환 요청"

    if _REMEMBER_PII_RE.search(text):
        logger.warning("[PII_GUARDRAIL] Detected: PII remember/store request")
        return "개인정보 저장 요청"

    return None
