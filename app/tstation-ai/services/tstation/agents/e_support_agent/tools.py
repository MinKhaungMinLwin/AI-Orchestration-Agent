import logging
import os
from typing import Any

from common.qna_payload import make_qna_payload_url
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


# RAG category_lv1 → DB lrcl_cd 매핑 (키워드 기반 추론용)
_KEYWORD_TO_LRCL = {
    "배송": "배송/장착", "장착": "배송/장착", "매장": "배송/장착",
    "주문": "주문/결제", "결제": "주문/결제", "반품": "주문/결제", "환불": "주문/결제", "교환": "주문/결제",
    "쿠폰": "혜택/프로모션", "할인": "혜택/프로모션", "프로모션": "혜택/프로모션", "이벤트": "혜택/프로모션",
    "회원": "회원/계정", "가입": "회원/계정", "탈퇴": "회원/계정", "비밀번호": "회원/계정",
    "워런티": "워런티", "보증": "워런티", "A/S": "워런티",
    "타이어": "상품/서비스", "경정비": "상품/서비스",
}


def _infer_lrcl_cd(query: str, rag_results: list[dict]) -> str | None:
    """RAG 결과의 category_lv1 또는 쿼리 키워드로 DB lrcl_cd를 추론한다."""
    # 1순위: RAG 최상위 결과의 카테고리
    if rag_results:
        category = rag_results[0].get("payload", {}).get("metadata", {}).get("category_lv1")
        if category:
            return category

    # 2순위: 쿼리 키워드 매칭
    for keyword, lrcl in _KEYWORD_TO_LRCL.items():
        if keyword in query:
            return lrcl

    return None


def _fallback_db_faq(query: str, rag_results: list[dict], top_k: int) -> list[dict]:
    """RAG 점수가 낮을 때 DB FAQ API로 카테고리 기반 보충 검색."""
    lrcl_cd = _infer_lrcl_cd(query, rag_results)

    try:
        response = get_faq(client=get_client(), lrcl_cd=lrcl_cd, limit=top_k)
        if response.parsed is None:
            return []

        parsed = response.parsed
        items = parsed.items if hasattr(parsed, "items") else []

        # RAG에 이미 있는 질문은 중복 제거
        existing_questions = {
            r.get("payload", {}).get("question", "") for r in rag_results
        }

        results = []
        for item in items:
            item_dict = _to_dict(item)
            question = item_dict.get("cust_quest", "")
            if question in existing_questions:
                continue
            results.append({
                "id": None,
                "question": question,
                "answer": item_dict.get("pc_ans_cont", ""),
                "metadata": {
                    "category_lv1": item_dict.get("lrcl_cd", ""),
                    "category_lv2": item_dict.get("mdcl_cd", ""),
                },
                "source": "db",
            })

        return results[:top_k]

    except Exception as e:
        logger.warning("[TOOL][_fallback_db_faq] DB fallback failed: %s", e)
        return []

@tool
def search_faq_rag_tool(
    query: str,
    top_k: int = 5,
    score_threshold: float = 0.6,
) -> dict:
    """
    Search FAQs using Retrieval-Augmented Generation (RAG) with multi-vector hybrid search.

    Performs semantic search over the FAQ database using named vectors ('question' and 'answer'),
    fused with Reciprocal Rank Fusion (RRF), then reranks results with keyword-overlap scoring.

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

        # 1. Embed the query
        embedding_service = get_embedding_service(
            model=settings.EMBEDDING_MODEL,
            provider=settings.EMBEDDING_PROVIDER,
            api_key=openai_api_key,
        )
        query_embedding = embedding_service.embed_text(query)
        logger.debug("[TOOL][search_faq_rag_tool] Embedding dim: %d", len(query_embedding))

        qdrant_service = get_qdrant_service(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            api_key=settings.QDRANT_API_KEY or None,
        )

        # 2. Multi-vector hybrid search (RRF fusion of question + answer vectors).
        #    Retrieve top_k + 5 extra candidates for reranker headroom.
        fetch_k = top_k + 5
        try:
            raw_results = qdrant_service.search_multi_vector(
                collection_name=settings.QDRANT_COLLECTION_FAQ,
                query_vector=query_embedding,
                top_k=fetch_k,
                score_threshold=score_threshold,
            )
            logger.info("[TOOL][search_faq_rag_tool] Multi-vector search: %d candidates", len(raw_results))
        except Exception:
            # Fallback to single-vector search for collections without named vectors
            logger.warning("[TOOL][search_faq_rag_tool] Multi-vector failed, falling back to single-vector")
            raw_results = qdrant_service.search(
                collection_name=settings.QDRANT_COLLECTION_FAQ,
                query_vector=query_embedding,
                top_k=fetch_k,
                score_threshold=score_threshold,
            )

        # 3. Rerank candidates with keyword-overlap scoring
        reranker = get_reranker_service()
        reranked = reranker.rerank(query=query, results=raw_results, top_k=top_k)

        # 4. Format RAG results
        formatted_results = [
            {
                "id": r.get("id"),
                "question": r.get("payload", {}).get("question", ""),
                "answer": r.get("payload", {}).get("answer", ""),
                "metadata": r.get("payload", {}).get("metadata", {}),
                "source": "rag",
            }
            for r in reranked
        ]

        # 5. DB fallback: if RAG best score < 0.4, supplement with DB FAQ
        best_score = reranked[0].get("score", 0.0) if reranked else 0.0
        if best_score < 0.4:
            db_results = _fallback_db_faq(query, reranked, top_k)
            if db_results:
                formatted_results.extend(db_results)
                logger.info(
                    "[TOOL][search_faq_rag_tool] DB fallback added %d FAQs", len(db_results),
                )

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
