"""
QnA Payload Encryption Utility

AES-128 ECB + PKCS5Padding → Base64 URL-safe encoding
for secure transfer of 1:1 inquiry data via URL payload parameter.
"""

import binascii
import logging
from urllib.parse import quote

from Crypto.Cipher import AES

from config.env import settings
from services.tstation.common.tstation_be_client import get_tstation_origin_host

logger = logging.getLogger(__name__)

AES_KEY: bytes = b"K7mN9pQ2xR4vW8zA"

QNA_WRITE_PATH = "/customer-service/qna.do"

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


def _build_payload(
        cnsl_clss_seq: str | None,
        inq_tit_nm: str | None,
        ai_summary: str | None,
) -> str:
    """Encrypt inquiry fields into a URL-safe Base64 payload string."""
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
    return b64.replace("+", "-").replace("/", "_").rstrip("=")




def make_qna_payload_urls(
        cnsl_clss_seq: str | None = None,
        inq_tit_nm: str | None = None,
        ai_summary: str | None = None,
) -> dict[str, str]:
    """
    Create encrypted QnA write URLs for both PC and mobile.

    Returns:
        {"pc": "<PC URL>", "mobile": "<mobile URL>"}
    """
    payload = _build_payload(cnsl_clss_seq, inq_tit_nm, ai_summary)
    base_urls = _qna_base_urls()

    return {
        "pc": f"{base_urls['pc']}{QNA_WRITE_PATH}?mode=write&payload={payload}",
        "mobile": f"{base_urls['mobile']}{QNA_WRITE_PATH}?mode=write&payload={payload}",
    }


def _qna_base_urls() -> dict[str, str]:
    origin_host = str(get_tstation_origin_host() or "").strip()
    if origin_host:
        origin_base = f"https://{origin_host}".rstrip("/")
        return {"pc": origin_base, "mobile": origin_base}
    return {
        "pc": settings.TSTATION_WEB_PC_BASE.rstrip("/"),
        "mobile": settings.TSTATION_WEB_MOBILE_BASE.rstrip("/"),
    }
