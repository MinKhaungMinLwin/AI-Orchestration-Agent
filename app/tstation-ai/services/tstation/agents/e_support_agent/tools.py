import logging
import os
from typing import Any

from common.qna_payload import make_qna_payload_urls
from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from services.tstation.common.tstation_be_client import get_tstation_be_client
from common.tstation_be_api_client.hkt_api_client.api.faq_af_일반_문의.get_faq_api_faq_get import sync_detailed as get_faq
from common.tstation_be_api_client.hkt_api_client.api.fallback_escalation_af_상담_연결.escalate_api_escalation_post import sync_detailed as post_escalate
from common.tstation_be_api_client.hkt_api_client.models import EscalationRequest
from langchain.tools import tool
from services.tstation.rag import (
    get_qdrant_service,
    get_embedding_service,
    get_reranker_service,
)
from services.tstation.rag.rag_config import RAGDynamicConfig
from config.env import settings

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
    [PRIMARY] Get FAQ list from database API.

    Retrieve frequently asked questions from CS_CUST_INQ_MGMT_INFO.
    Only FAQ data (INQ_TYPE_CD='FAQ') is retrieved. 1:1 inquiry history
    is excluded for privacy protection.

    Can filter by large category (lrcl_cd) and medium category (mdcl_cd).

    Args:
        lrcl_cd (str | None): Large category code filter (LRCL_CD).
            Supported values:
                - "C01": 회원/주문/장착 관련 (membership, order, installation)
                - "C02": 상품/타이어 관련 (product, tire info)
                - "C03": 매장/서비스 관련 (store, service)
                - None: search all categories
        mdcl_cd (str | None): Medium category code filter (MDCL_CD).
            Known values (use when determinable):
                - C01 → "C0103" (회원가입/계정), "C0106" (장착일정/예약)
                - C02 → "C0201" (타이어 상품정보/수명)
                - C03 → "C0302" (매장서비스/보관)
                - None: search all medium categories within lrcl_cd
        limit (int): Number of FAQs to return (default 50, max 200).

    Call strategy:
        Step 1: Call with limit=50 (and lrcl_cd inferred from user question if possible)
        Step 2: If no relevant result, call with limit=100
        Step 3: If still no result, call with limit=200 (MAX)
        Step 4: If still no result after limit=200, fall back to search_faq_rag_tool

    Example Inputs:
        - {"lrcl_cd": "C01", "mdcl_cd": "C0103", "limit": 50}
        - {"lrcl_cd": "C02", "mdcl_cd": "C0201", "limit": 50}
        - {"lrcl_cd": "C03", "mdcl_cd": "C0303", "limit": 50}
        - {"lrcl_cd": None, "mdcl_cd": None, "limit": 50}

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
        
        parsed = _to_dict(response.parsed)
        # Inject source="db" into each FAQ item
        items = parsed.get("items", []) if isinstance(parsed, dict) else []
        for item in items:
            item["source"] = "FAQ DB"
        logger.info("[TOOL][get_faq_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_faq_tool] Failed")
        return _error_response(None, str(e), "Failed to get FAQ")
    
@tool
def search_faq_rag_tool(
    query: str,
    top_k: int = 5,
    score_threshold: float = 0.6,
) -> dict:
    """
    [FALLBACK] Search FAQs using RAG (semantic vector search).

    Use this ONLY when get_faq_tool fails (API error, timeout) or returns
    no relevant results after limit=200.
    Do NOT call this as the first step — always try get_faq_tool first.

    Args:
        query (str): The user's search query.
        top_k (int): Maximum number of FAQ entries to return (default 5).
        score_threshold (float): Minimum relevance score to include a result (default 0.6).

    Returns:
        dict: {"status": "success", "http_status": 200, "data": [...]} or error dict.

    Example:
        result = search_faq_rag_tool(query="환불 가능한가요?", top_k=5, score_threshold=0.6)
    """
    logger.info(
        "[TOOL][search_faq_rag_tool] query=%s, top_k=%s, score_threshold=%s",
        query, top_k, score_threshold,
    )

    try:
        openai_api_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY

        # 1. Embed query — cached; repeat queries return in <1ms instead of ~200ms API call
        embedding_service = get_embedding_service(
            model=settings.EMBEDDING_MODEL,
            provider=settings.EMBEDDING_PROVIDER,
            api_key=openai_api_key,
        )
        query_embedding = embedding_service.embed_text_cached(query)

        qdrant_service = get_qdrant_service(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            api_key=settings.QDRANT_API_KEY or None,
        )

        # 2. Dynamic fetch_k: scales logarithmically with collection size (cached 5 min).
        #    Prevents both over-fetch (noise) and under-fetch (missing good docs).
        collection_size = qdrant_service.get_collection_size_cached(settings.QDRANT_COLLECTION_FAQ)
        fetch_k = RAGDynamicConfig.compute_fetch_k(collection_size=collection_size, final_top_k=top_k)
        logger.info(
            "[TOOL][search_faq_rag_tool] collection_size=%d, fetch_k=%d",
            collection_size, fetch_k,
        )

        # 3. Multi-vector hybrid search — 2 Qdrant calls run in parallel (ThreadPoolExecutor).
        #    No hard score_threshold here; adaptive threshold is applied after retrieval.
        try:
            raw_results = qdrant_service.search_multi_vector(
                collection_name=settings.QDRANT_COLLECTION_FAQ,
                query_vector=query_embedding,
                top_k=fetch_k,
                score_threshold=0.0,
            )
            logger.info("[TOOL][search_faq_rag_tool] Multi-vector search: %d candidates", len(raw_results))
        except Exception:
            logger.warning("[TOOL][search_faq_rag_tool] Multi-vector failed, falling back to single-vector")
            raw_results = qdrant_service.search(
                collection_name=settings.QDRANT_COLLECTION_FAQ,
                query_vector=query_embedding,
                top_k=fetch_k,
                score_threshold=None,
            )

        # 4. Adaptive threshold: detect natural score gap instead of using fixed 0.6.
        #    score_threshold param from the agent call acts as the absolute floor.
        retrieval_scores = [r.get("score", 0.0) for r in raw_results]
        effective_threshold = RAGDynamicConfig.adaptive_threshold(
            scores=retrieval_scores,
            base_threshold=score_threshold,
        )
        filtered = [r for r in raw_results if r.get("score", 0.0) >= effective_threshold]
        logger.info(
            "[TOOL][search_faq_rag_tool] adaptive_threshold=%.3f (base=%.3f) → %d/%d passed",
            effective_threshold, score_threshold, len(filtered), len(raw_results),
        )

        # 5. Rerank filtered candidates with keyword-overlap scoring
        reranker = get_reranker_service()
        reranked = reranker.rerank(query=query, results=filtered, top_k=top_k)

        # 4. Format RAG results
        formatted_results = [
            {
                "question": r.get("payload", {}).get("question", ""),
                "answer": r.get("payload", {}).get("answer", ""),
                "metadata": r.get("payload", {}).get("metadata", {}),
                "source": "FAQ RAG",
            }
            for r in reranked
        ]

        logger.info(
            "[TOOL][search_faq_rag_tool] Returned %d FAQs (RAG+DB, threshold=%.2f)",
            len(formatted_results), score_threshold,
        )
        return _success_response(200, formatted_results)

    except Exception as e:
        logger.exception("[TOOL][search_faq_rag_tool] Failed")
        return _error_response(None, str(e), "Failed to search FAQs using RAG")

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

    Example Inputs:
        - {"mbr_no": "M200012931", "inq_type_cd": "ORDER", "msg_count": 3, "summary": "Customer wants to cancel order"}
        - {"mbr_no": "M200012932", "inq_type_cd": "DELIVERY", "msg_count": 2, "summary": "Package delayed"}
        - {"mbr_no": "M200012933", "inq_type_cd": "CLAIM", "msg_count": 5, "summary": "Product damaged on delivery"}
        - {"mbr_no": "M200012934", "inq_type_cd": "MEMBERSHIP", "msg_count": 1, "summary": "Membership upgrade request"}
        - {"mbr_no": "M200012935", "inq_type_cd": "OTHER", "msg_count": 4, "summary": "General inquiry about products"}

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
        dict with keys:
            - status: "success" or "error"
            - response: Markdown string to display to the user verbatim (includes clickable link)
            - url: The generated inquiry page URL (used by UI template agent)
            - isMobile, cnsl_clss_seq, inq_tit_nm, ai_summary: metadata for UI template rendering
        ⚠️ Always output the `response` field verbatim as your reply to the user.
    """
    logger.info(
        "[TOOL][transfer_to_qna_tool] Called with: cnsl_clss_seq=%s, inq_tit_nm=%s, ai_summary=%s, is_mobile=%s",
        cnsl_clss_seq, inq_tit_nm, ai_summary, is_mobile,
    )

    try:
        redict_link = make_qna_payload_urls(
            cnsl_clss_seq=cnsl_clss_seq,
            inq_tit_nm=inq_tit_nm,
            ai_summary=ai_summary,
        )
        logger.info(f"[TOOL][transfer_to_qna_tool] Generated URLs: pc={redict_link['pc']}, mobile={redict_link['mobile']}")
        device_url = redict_link["mobile"] if is_mobile else redict_link["pc"]
        device = "모바일" if is_mobile else "PC"
        response_text = (
            f"✅ **1:1 문의 작성 페이지로 이동합니다**\n\n"
            f"📱 [{device}에서 열기]({device_url})\n\n"
            f"> 요청이 자동으로 등록되지 않습니다. 위 링크를 클릭하여 문의 내용을 확인하고 제출해주세요."
        )
        return {
            "status": "success",
            "response": response_text,
            "redictLink": redict_link,
            "cnsl_clss_seq": cnsl_clss_seq,
            "inq_tit_nm": inq_tit_nm,
            "ai_summary": ai_summary,
        }
    except Exception as e:
        logger.exception("[TOOL][transfer_to_qna_tool] Failed")
        return {"status": "error", "response": f"❌ **오류 발생**: {str(e)}\n\n> 다시 시도하시거나 고객센터로 직접 문의해주세요."}
