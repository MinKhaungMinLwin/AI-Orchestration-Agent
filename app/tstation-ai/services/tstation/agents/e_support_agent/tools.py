import logging
from typing import Any

from common.qna_payload import make_qna_payload_url
from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from services.tstation.common.tstation_be_client import get_tstation_be_client
from common.tstation_be_api_client.hkt_api_client.api.faq_af_일반_문의.get_faq_api_faq_get import sync_detailed as get_faq
from common.tstation_be_api_client.hkt_api_client.api.fallback_escalation_af_상담_연결.escalate_api_escalation_post import sync_detailed as post_escalate
from common.tstation_be_api_client.hkt_api_client.models import EscalationRequest
from langchain.tools import tool

logger = logging.getLogger(__name__)


def get_client() -> AuthenticatedClient:
    """Get authenticated client for tstation-be API."""
    return get_tstation_be_client()


DOMAIN = {
    # FAQ
    "get_faq",

    # Escalation
    "escalate",
}


def _to_dict(res: Any) -> Any:
    return res.to_dict() if hasattr(res, 'to_dict') else (res.model_dump() if hasattr(res, 'model_dump') else res)


def _error_response(http_status: int | None, reason: str, message: str) -> dict:
    return {"status": "error", "http_status": http_status, "reason": reason, "message": message}


def _success_response(http_status: int, data: Any) -> dict:
    return {"status": "success", "http_status": http_status, "data": data}


@tool
def get_faq_tool(lrcl_cd: str | None = None, mdcl_cd: str | None = None, limit: int = 50):
    """
    Get FAQ list.

    Retrieve frequently asked questions from CS_CUST_INQ_MGMT_INFO.
    Only FAQ data (INQ_TYPE_CD='FAQ') is retrieved. 1:1 inquiry history
    is excluded for privacy protection.

    Can filter by large category (lrcl_cd) and medium category (mdcl_cd).

    Args:
        lrcl_cd (str | None): Large category code filter (LRCL_CD).
        mdcl_cd (str | None): Medium category code filter (MDCL_CD).
        limit (int): Number of FAQs to return (default 50, max 200).

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    logger.info("[TOOL][get_faq_tool] Called with: lrcl_cd=%s, mdcl_cd=%s, limit=%s", lrcl_cd, mdcl_cd, limit)

    try:
        response = get_faq(client=get_client(), lrcl_cd=lrcl_cd, mdcl_cd=mdcl_cd, limit=limit)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get FAQ"
            )
        logger.info("[TOOL][get_faq_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_faq_tool] Failed")
        return _error_response(None, str(e), "Failed to get FAQ")


@tool
def escalate_tool(
        mbr_no: None | str = None,
        inq_type_cd: None | str = None,
        msg_count: int = 0,
        summary: None | str = None,
):
    """
    Escalate to customer service agent.

    Handle consultation requests based on conversation volume and inquiry type.
    There are 3 branches:

    - **with_summary**: If message count ≥ threshold (ESCALATION_MSG_THRESHOLD, default 3)
      and summary exists, pass summary as URL-encoded query parameter
    - **direct**: If conversation is short or no summary, redirect to consultation page directly
    - **policy**: If inq_type_cd is registered in policy table, branch to specified channel (call/email, etc.)

    Args:
        mbr_no (str | None): Member number.
        inq_type_cd (str): Inquiry type code (e.g., ORDER, DELIVERY, CLAIM, etc.).
        msg_count (int): Number of messages in conversation.
        summary (str | None): Conversation summary (URL encoded).

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    body = EscalationRequest(
        inq_type_cd=inq_type_cd,
        mbr_no=mbr_no,
        msg_count=msg_count,
        summary=summary,
    )
    logger.info("[TOOL][escalate_tool] Called with: inq_type_cd=%s, mbr_no=%s, summary=%s", inq_type_cd, mbr_no, summary)

    try:
        response = post_escalate(client=get_client(), body=body)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to escalate to human agent"
            )
        logger.info("[TOOL][escalate_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][escalate_tool] Failed")
        return _error_response(None, str(e), "Failed to escalate to human agent")


@tool
def transfer_to_qna_tool(
        cnsl_clss_seq: str | None = None,
        inq_tit_nm: str | None = None,
        ai_summary: str | None = None,
        is_mobile: bool = False,
):
    """
    Create encrypted QnA write URL to transfer user to 1:1 inquiry write page.

    Data is AES-128 ECB encrypted with Base64 URL-safe encoding.
    Use this when user wants to write a 1:1 inquiry with AI-summarized content.

    Args:
        cnsl_clss_seq (str | None): Consultation type code.
            - 10002: 상품문의 (Product inquiry)
            - 10006: 주문/결제/배송 (Order/Payment/Delivery)
            - 10010: 반품/교환/환불 (Return/Exchange/Refund)
            - 10013: 제공서비스/이벤트/혜택 (Service/Event/Benefits)
            - 10017: 회원 (Member)
            - 10019: 기타 (Other)
            - 10025: 가맹점제휴문의 (Franchise inquiry)
            - 10034: 이력서접수 (Resume submission)
            If not provided, omit and AI will auto-select.
        inq_tit_nm (str | None): Inquiry title (max 100 chars).
        ai_summary (str | None): Inquiry content (max 1000 chars).
        is_mobile (bool): Use mobile URL if True.

    Returns:
        str: Markdown with link to QnA page or error message.
    """
    logger.info(
        "[TOOL][transfer_to_qna_tool] Called with: cnsl_clss_seq=%s, inq_tit_nm=%s, ai_summary=%s, is_mobile=%s",
        cnsl_clss_seq, inq_tit_nm, ai_summary, is_mobile,
    )

    try:
        url = make_qna_payload_url(
            cnsl_clss_seq=cnsl_clss_seq,
            inq_tit_nm=inq_tit_nm,
            ai_summary=ai_summary,
            is_mobile=is_mobile,
        )
        logger.info(f"[TOOL][transfer_to_qna_tool] Generated URL: {url}")
        device = "모바일" if is_mobile else "PC"
        return (
            f"✅ **1:1 문의 작성 페이지로 이동합니다**\n\n"
            f"📱 [{device}에서 열기]({url})\n\n"
            f"> 요청이 자동으로 등록되지 않습니다. 위 링크를 클릭하여 문의 내용을 확인하고 제출해주세요."
        )
    except Exception as e:
        logger.exception("[TOOL][transfer_to_qna_tool] Failed")
        return f"❌ **오류 발생**: {str(e)}\n\n> 다시 시도하시거나 고객센터로 직접 문의해주세요."
