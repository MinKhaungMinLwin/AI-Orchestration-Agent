from common.tstation_be_api_client.hkt_api_client.client import Client
from common.tstation_be_api_client.hkt_api_client.api.faq_af_일반_문의.get_faq_api_faq_get import sync as get_faq
from common.tstation_be_api_client.hkt_api_client.api.fallback_escalation_af_상담_연결.escalate_api_escalation_post import sync as post_escalate
from common.tstation_be_api_client.hkt_api_client.models import EscalationRequest
from config.env import settings
from langchain.tools import tool


client = Client(base_url=settings.TSTATION_BE_API)

DOMAIN = {
    # FAQ
    "get_faq",

    # Escalation
    "escalate",
}


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

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        FaqListResponse | HTTPValidationError
    """
    res = get_faq(
        client=client,
        lrcl_cd=lrcl_cd,
        mdcl_cd=mdcl_cd,
        limit=limit,
    )
    print("[TOOL][get_faq_tool]")
    print(res)

    return res


@tool
def escalate_tool(
    inq_type_cd: str,
    mbr_no: str | None = None,
    summary: str | None = None,
    messages: list[dict] | None = None
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
        inq_type_cd (str): Inquiry type code (e.g., ORDER, DELIVERY, CLAIM, etc.).
        mbr_no (str | None): Member number.
        summary (str | None): Conversation summary (URL encoded).
        messages (list[dict] | None): List of conversation messages for context.

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        EscalationResponse | HTTPValidationError
    """
    body = EscalationRequest(
        inq_type_cd=inq_type_cd,
        mbr_no=mbr_no,
        summary=summary,
        messages=messages,
    )
    res = post_escalate(
        client=client,
        body=body,
    )
    print("[TOOL][escalate_tool]")
    print(res)

    return res
