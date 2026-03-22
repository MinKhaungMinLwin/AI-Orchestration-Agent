"""
QnA Payload Encryption Utility

AES-128 ECB + PKCS5Padding → Base64 URL-safe encoding
for secure transfer of 1:1 inquiry data via URL payload parameter.
"""

import binascii
import logging
from urllib.parse import quote

from Crypto.Cipher import AES

logger = logging.getLogger(__name__)

AES_KEY: bytes = b"K7mN9pQ2xR4vW8zA"

QnA_WRITE_URL_PC = "https://wwwqa.tstation.com/customer-service/qna.do"
QnA_WRITE_URL_MOBILE = "https://mqa.tstation.com/customer-service/qna.do"

CSL_CLS_SEQ_MAP: dict[str, str] = {
    "상품문의": "10002",
    "주문/결제/배송": "10006",
    "반품/교환/환불": "10010",
    "제공서비스/이벤트/혜택": "10013",
    "회원": "10017",
    "기타": "10019",
    "가맹점제휴문의": "10025",
    "이력서접수": "10034",
}


def _pkcs5_pad(data: bytes, block_size: int = 16) -> bytes:
    padding_len = block_size - (len(data) % block_size)
    return data + bytes([padding_len] * padding_len)


def _url_encode_value(value: str) -> str:
    return quote(value, safe="")


def make_qna_payload_url(
        cnsl_clss_seq: str | None = None,
        inq_tit_nm: str | None = None,
        ai_summary: str | None = None,
        is_mobile: bool = False,
) -> str:
    """
    Create encrypted QnA write URL with payload parameter.

    Args:
        cnsl_clss_seq: Consultation type code (e.g., "10006").
                       If not provided, AI will select automatically.
        inq_tit_nm: Inquiry title (max 100 chars).
        ai_summary: Inquiry content (max 1000 chars).
        is_mobile: Use mobile URL if True.

    Returns:
        Full URL with encrypted payload, e.g.:
        https://wwwqa.tstation.com/customer-service/qna.do?mode=write&payload=...
    """
    base_url = QnA_WRITE_URL_MOBILE if is_mobile else QnA_WRITE_URL_PC

    parts: list[str] = []
    if cnsl_clss_seq:
        parts.append(f"cnslClssSeq={cnsl_clss_seq}")
    if inq_tit_nm:
        parts.append(f"inqTitNm={_url_encode_value(inq_tit_nm)}")
    if ai_summary:
        parts.append(f"aiSummary={_url_encode_value(ai_summary)}")

    plain_query = "&".join(parts)
    logger.debug(f"[qna_payload] Plain query: {plain_query}")

    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    padded = _pkcs5_pad(plain_query.encode("utf-8"))
    encrypted = cipher.encrypt(padded)

    b64 = binascii.b2a_base64(encrypted).decode().rstrip("\n")
    payload = b64.replace("+", "-").replace("/", "_").rstrip("=")

    return f"{base_url}?mode=write&payload={payload}"
