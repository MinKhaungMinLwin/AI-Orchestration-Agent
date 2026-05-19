import logging
import os
from typing import Any

from common.qna_payload import make_qna_payload_urls
from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from services.tstation.common.tstation_be_client import get_tstation_be_client
from common.tstation_be_api_client.hkt_api_client.api.faq_af_일반_문의.get_faq_api_faq_get import sync_detailed as get_faq
from common.tstation_be_api_client.hkt_api_client.api.fallback_escalation_af_상담_연결.escalate_api_escalation_post import sync_detailed as post_escalate
from common.tstation_be_api_client.hkt_api_client.api.maintenance_d_day_af_정비_d_day_안내.get_maintenance_dday_api_member_maintenance_dday_get import (
    sync_detailed as get_maintenance_dday,
)
# Cross-agent reuse: b_discovery 의 get_my_cars_tool 을 SUPPORT 에서도 호출해
# 정비 D-day 안내 시 차량 컨텍스트가 없으면 직접 listCar 카드를 emit 한다.
# template_mapper 가 tool name 기준으로 listCar 템플릿을 발동하므로 호출 주체가
# SUPPORT 여도 동일하게 동작.
from services.tstation.agents.b_discovery_agent.tools import (
    get_my_cars_tool,  # noqa: F401  # re-exported via SupportSubAgent.tools
    search_product_tool,  # noqa: F401  # warranty Path B 에서 상품명→goods_no 추출용
    get_deals_tool,  # noqa: F401  # Coupon stacking Path B 에서 "반짝블랙딜" 류 자연어 매칭용
)
# Coupon stacking Path B — 사용자가 컨텍스트 cpn_no + "생일쿠폰" 류 자연어로 다른
# 쿠폰을 지칭하면 보유 쿠폰에서 이름 매칭으로 cpn_no 를 찾아 stacking_check 호출.
from services.tstation.agents.c_transaction_agent.tools import (
    get_my_coupons_tool,  # noqa: F401  # re-exported via SupportSubAgent.tools
)
from common.tstation_be_api_client.hkt_api_client.api.warranty_af_워런티_조회.get_my_warranties_api_member_warranties_get import (
    sync_detailed as get_my_warranties,
)
from common.tstation_be_api_client.hkt_api_client.api.installment_af_무이자_할부_조회.get_card_installments_api_installments_cards_get import (
    sync_detailed as get_card_installments,
)
from common.tstation_be_api_client.hkt_api_client.api.coupon_af_쿠폰_발급.stacking_check_api_coupons_stacking_check_get import (
    sync_detailed as stacking_check,
)
from common.tstation_be_api_client.hkt_api_client.api.warranty_af_워런티_조회.get_product_warranties_api_products_goods_no_warranties_get import (
    sync_detailed as get_product_warranties,
)
from common.tstation_be_api_client.hkt_api_client.models import EscalationRequest
from langchain.tools import tool
from common.tool_cache import tool_cache
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
@tool_cache(ttl=3600)
def get_faq_tool(lrcl_cd: str | None = None, mdcl_cd: str | None = None, limit: int = 50):
    """
    [PRIMARY] Get FAQ list from database.

    Args:
        lrcl_cd (str | None): Large category — "C01" (회원/주문/장착) | "C02" (상품/타이어) | "C03" (매장/서비스) | None (all).
        mdcl_cd (str | None): Medium category — C01→"C0103"(회원가입/계정),"C0106"(장착/예약) | C02→"C0201"(타이어 상품정보) | C03→"C0302"(매장서비스) | None (all).
        limit (int): FAQs to return (default 50, max 200).

    Call strategy: limit=50 → retry 100 → retry 200 → fall back to search_faq_rag_tool on failure.

    Example: {"lrcl_cd": "C01", "mdcl_cd": "C0103", "limit": 50}
    """
    logger.debug("[TOOL][get_faq_tool] Called with: lrcl_cd=%s, mdcl_cd=%s, limit=%s", lrcl_cd, mdcl_cd, limit)

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
        logger.debug("[TOOL][get_faq_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, parsed)
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

    Use ONLY when get_faq_tool fails or returns no relevant results after limit=200.
    Do NOT call as the first step.

    Args:
        query (str): 사용자 검색어.
        top_k (int): 최대 반환 FAQ 수 (default 5).
        score_threshold (float): 최소 관련성 점수 (default 0.6).

    Example: {"query": "환불 가능한가요?", "top_k": 5}
    """
    logger.debug(
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
        logger.debug(
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
            logger.debug("[TOOL][search_faq_rag_tool] Multi-vector search: %d candidates", len(raw_results))
        except Exception:
            logger.warning("[TOOL][search_faq_rag_tool] Multi-vector failed, falling back to single-vector")
            raw_results = qdrant_service.search(
                collection_name=settings.QDRANT_COLLECTION_FAQ,
                query_vector=query_embedding,
                top_k=fetch_k,
                score_threshold=None,
                using="question",
            )

        # 4. Adaptive threshold: detect natural score gap instead of using fixed 0.6.
        #    score_threshold param from the agent call acts as the absolute floor.
        retrieval_scores = [r.get("score", 0.0) for r in raw_results]
        effective_threshold = RAGDynamicConfig.adaptive_threshold(
            scores=retrieval_scores,
            base_threshold=score_threshold,
        )
        filtered = [r for r in raw_results if r.get("score", 0.0) >= effective_threshold]
        logger.debug(
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

        logger.debug(
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

    Branches: with_summary (msg_count ≥ threshold + summary) | direct (short conversation) | policy (inq_type_cd in policy table).

    Args:
        mbr_no (str | None): 회원번호.
        inq_type_cd (str): Inquiry type (ORDER, DELIVERY, CLAIM, MEMBERSHIP, OTHER, etc.).
        msg_count (int): 대화 메시지 수.
        summary (str | None): 대화 요약.

    Example: {"mbr_no": "MXXXXXXXXX", "inq_type_cd": "ORDER", "msg_count": 3, "summary": "주문 취소 요청"}
    """
    body = EscalationRequest(
        inq_type_cd=inq_type_cd,
        mbr_no=mbr_no,
        msg_count=msg_count,
        summary=summary,
    )
    logger.debug("[TOOL][escalate_tool] Called with: inq_type_cd=%s, mbr_no=%s, summary=%s", inq_type_cd, mbr_no, summary)

    try:
        response = post_escalate(client=get_client(), body=body)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to escalate to human agent"
            )
        logger.debug("[TOOL][escalate_tool] Response: %s", response.parsed)
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

    Args:
        cnsl_clss_seq (str | None): 10002=상품 / 10006=주문·결제·배송 / 10010=반품·교환·환불 / 10013=서비스·이벤트 / 10017=회원 / 10019=기타 / 10025=가맹점제휴 / 10034=이력서.
        inq_tit_nm (str | None): 문의 제목 (max 100자).
        ai_summary (str | None): 문의 내용 요약 (max 400자, 1인칭 한국어).
        is_mobile (bool): True → mobile URL 사용.
    """
    logger.debug(
        "[TOOL][transfer_to_qna_tool] Called with: cnsl_clss_seq=%s, inq_tit_nm=%s, ai_summary=%s, is_mobile=%s",
        cnsl_clss_seq, inq_tit_nm, ai_summary, is_mobile,
    )

    try:
        redict_link = make_qna_payload_urls(
            cnsl_clss_seq=cnsl_clss_seq,
            inq_tit_nm=inq_tit_nm,
            ai_summary=ai_summary,
        )
        logger.debug(f"[TOOL][transfer_to_qna_tool] Generated URLs: pc={redict_link['pc']}, mobile={redict_link['mobile']}")
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


@tool
def get_maintenance_dday_tool(mbr_car_reg_seq: str | None = None) -> dict:
    """
    회원 등록차량의 정비 D-day 매트릭스 조회 (7개 정비 항목).

    Args:
        mbr_car_reg_seq (str | None): 특정 차량의 정비 일정만 조회할 때 사용 (예: "2000002944").
            None 이면 회원의 모든 등록차량 매트릭스 반환.

    Returns:
        {"status": "success", "data": {"cars": [
          {"mbr_car_reg_seq": "...", "car_nm": "현대 그랜저",
           "items": [
             {"kind_cd": "001", "kind_nm": "얼라인먼트 점검",
              "exp_dt": "2026-10-31", "dday": 165,
              "status": "future|upcoming|expired",
              "source": "noti_record|car_reg_fallback"}, ... (7개)
           ]}, ...
        ]}}

    항목 코드:
        001=얼라인먼트 점검 / 002=all my T 무상점검 / 003=엔진오일 교체 /
        004=실내필터 교체 / 005=와이퍼 교체 / 006=타이어 교체 / 007=배터리 교체

    Status:
        - expired:  D+ (만기 경과)
        - upcoming: D-0 ~ D-30 (만기 임박)
        - future:   D-31 이상

    Source:
        - noti_record:      ST_NOTI_DDAY_INFO 의 실제 만기일
        - car_reg_fallback: 행 없음 → 차량등록일 + 권장 개월수로 계산한 추정 만기일
    """
    logger.debug("[TOOL][get_maintenance_dday_tool] Called with: mbr_car_reg_seq=%s", mbr_car_reg_seq)

    try:
        response = get_maintenance_dday(client=get_client(), mbr_car_reg_seq=mbr_car_reg_seq)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get maintenance D-day",
            )
        logger.debug("[TOOL][get_maintenance_dday_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_maintenance_dday_tool] Failed")
        return _error_response(None, str(e), "Failed to get maintenance D-day")


# --------------------------------------------------------------------------- #
#  Warranty (워런티 조회)                                                       #
# --------------------------------------------------------------------------- #

@tool
@tool_cache(ttl=600)
def get_product_warranties_tool(goods_no: str):
    """
    상품에 적용 가능한 워런티 종류를 조회한다 (ET_DGTL_WRT_APLY_INFO).

    Use when: 사용자가 "이 타이어에 안심서비스 돼?", "이 상품 워런티 뭐 돼?",
    "다이나프로 HPX 품질보증 가입 가능해?", "이 상품 30일 해피보증 적용돼?"
    처럼 특정 상품의 워런티 적용 가능성을 묻는 경우.

    Args:
        goods_no (str): 상품 번호 (PR_GOODS_BASE.GOODS_NO). 직전 상품 카드/검색
            결과에서 가져온 값을 그대로 사용. 사용자가 상품명만 언급하고
            goods_no 가 컨텍스트에 없으면 먼저 search_product_tool 등으로
            확인할 것 (이 도구는 search 하지 않는다).

    Returns: status/http_status/data. data 구조:
        {"goods_no": "...", "ptrn_cd": "K129",
         "warranties": [{"wrt_tp_cd":"10","wrt_nm":"품질보증","is_plus":false}, ...]}

        - wrt_tp_cd: "10"=품질보증 / "20"=안심서비스 (PLPR_YN='Y' 이면 동일 코드로
          "안심플러스" 행이 추가됨, is_plus=true) / "30"=30일 해피보증 /
          "40"=코드절상 무상교환.
        - 상품이 없으면 ptrn_cd=null, warranties=[].
        - 패턴은 있지만 적용 가능한 워런티가 0건이면 ptrn_cd 채워짐 + warranties=[].
    """
    logger.debug("[TOOL][get_product_warranties_tool] goods_no=%s", goods_no)
    try:
        response = get_product_warranties(goods_no=goods_no, client=get_client())
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get product warranties",
            )
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_product_warranties_tool] Failed")
        return _error_response(None, str(e), "Failed to get product warranties")


@tool
@tool_cache(ttl=300)
def get_my_warranties_tool():
    """
    JWT 회원이 보유한 워런티 목록을 조회한다 (ET_DGTL_WRT_REG_INFO).

    Use when: 사용자가 "내 워런티 알려줘", "내가 가입한 안심서비스 만료일",
    "내 품질보증 언제까지야?", "내 워런티 현황", "내 워런티 보유 내역"
    처럼 본인 보유 워런티를 묻는 경우. 인증된 JWT 의 회원번호를 자동 사용.

    Returns: status/http_status/data. data 구조:
        {"warranties": [
            {"wrt_tp_cd":"10","wrt_nm":"품질보증",
             "wrt_reg_date":"2025-04-15","wrt_exp_date":"2027-04-15",
             "wrt_prgs_stat_cd":"200","wrt_prgs_stat_nm":"가입완료"},
            ...
        ]}

        - 진행상태: "200"=가입완료 / "300"=기간만료 / "400"=보상완료.
          ("100"=가입대기는 BE 단에서 응답에서 제외됨 — 노출 금지.)
        - 가입일자 내림차순. 보유 워런티 0건이면 warranties=[].
        - 회원 보유 응답에는 안심플러스 구분 컬럼이 없어 wrt_tp_cd='20' 은 모두
          "안심서비스" 로 노출됨. "안심플러스 가입 여부" 같은 세부 구분은
          현 BE 응답으로 단정 불가.
    """
    logger.debug("[TOOL][get_my_warranties_tool] called")
    try:
        response = get_my_warranties(client=get_client())
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get my warranties",
            )
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_my_warranties_tool] Failed")
        return _error_response(None, str(e), "Failed to get my warranties")


@tool
@tool_cache(ttl=3600)
def get_card_installments_tool(tgt_amt: int | None = None):
    """
    진행중인 카드사별 무이자 할부 가능 정보를 조회한다 (OP_NINT_INST_BASE + OP_NINT_INST_DTL_INFO).

    Use when: 사용자가 "무이자 할부 카드 알려줘", "신한카드 무이자 돼?",
    "12개월 무이자 어떤 카드?", "30만원 결제 시 무이자 가능?" 처럼 카드사별
    무이자 할부 적용 가능성을 묻는 경우. 결제 시점 직전 (preOrder/cart 컨텍스트) 에서
    같은 질문이 나오면 c_transaction_agent 가 cross-agent 로 호출한다.

    Args:
        tgt_amt: 결제 예상 금액(원). 지정하면 NDI.TGT_AMT <= tgt_amt 인 행만 반환
            (즉 그 금액 이상부터 적용되는 무이자 행). 미지정 시 전체 진행중 카드.

    Returns: status/http_status/data. data 구조:
        {"cards": [
            {"iscm_cd":"01","iscm_nm":"신한카드","tgt_amt":50000,
             "months":[2,3,6,12],"payment_type":"일반"},
            {"iscm_cd":"01","iscm_nm":"신한카드","tgt_amt":300000,
             "months":[12,24],"payment_type":"스마트페이"},
            ...
        ]}

        - 진행중 (SYSDATE BETWEEN APLY_STRT_DTIME AND APLY_END_DTIME) 만 포함.
        - 같은 카드사라도 결제유형(일반/스마트페이) 또는 기준금액별로 row 분리.
        - months 는 NINT_N_MM_YN='Y' 인 N 만 오름차순. N ∈ {2,3,...,12,24}.
        - iscm_nm 은 FN_GET_COMMON_NAME_AI('PAY014') 결과 — 매핑 부재 시 null.
        - payment_type 은 사용자 응답에 노출 금지 (실제 결제는 챗봇 밖에서 진행).
    """
    logger.debug("[TOOL][get_card_installments_tool] tgt_amt=%s", tgt_amt)
    try:
        kwargs: dict[str, Any] = {"client": get_client()}
        if tgt_amt is not None:
            kwargs["tgt_amt"] = tgt_amt
        response = get_card_installments(**kwargs)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get card installments",
            )
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_card_installments_tool] Failed")
        return _error_response(None, str(e), "Failed to get card installments")


@tool
@tool_cache(ttl=600)
def check_coupon_stacking_tool(cpn_no_list: list[str]):
    """
    두 개 이상의 쿠폰을 동시에 사용할 수 있는지 (중복 적용 가능 여부) 를 조회한다.

    Use when: 사용자가 "이 쿠폰이랑 저 쿠폰 같이 써도 돼?", "기획전 할인가에 생일쿠폰
    더 쓸 수 있어?", "C72... 랑 C68... 같이 돼?" 처럼 두 개 이상의 쿠폰 ID 가 식별된
    상태에서 중복 적용 가능 여부를 묻는 경우.

    Args:
        cpn_no_list: 비교할 쿠폰 번호 목록. 2개 이상 5개 이하. 1개는 비교 불가 (400).

    Returns: status/http_status/data. data 구조:
        {
          "coupons": [
            {"cpn_no":"C111","cpn_nm":"상품쿠폰A","cpn_tp_cd":"10",
             "cpn_tp_nm":"상품쿠폰","cpn_dup_use_yn":"Y","found":true},
            ...
          ],
          "pairs": [
            {"cpn_no_a":"C111","cpn_no_b":"C222",
             "can_stack":true,
             "reason":"두 쿠폰 모두 중복 사용이 가능합니다."},
            ...
          ]
        }

        - pairs 는 입력 cpn_no 들의 모든 2-조합 (N개 → C(N,2) 개).
        - can_stack: true=중복 가능, false=중복 불가, null=정책 안내 불가 (DBA 가이드
          명시 없는 조합 — same TP, 30+30, 40+40, 30+40, 마스터 미발견 등).
        - cpn_no, cpn_tp_cd, cpn_dup_use_yn 은 사용자 응답에 노출 금지 (내부 코드값).
          cpn_nm, cpn_tp_nm, reason 만 사용자 응답에 사용.
    """
    logger.debug("[TOOL][check_coupon_stacking_tool] cpn_no_list=%s", cpn_no_list)
    try:
        if not cpn_no_list or len(cpn_no_list) < 2:
            return _error_response(
                400,
                "InvalidInput",
                "cpn_no_list 는 최소 2개 이상이어야 합니다.",
            )
        cpn_no_csv = ",".join(cpn_no_list)
        response = stacking_check(client=get_client(), cpn_no=cpn_no_csv)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to check coupon stacking",
            )
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][check_coupon_stacking_tool] Failed")
        return _error_response(None, str(e), "Failed to check coupon stacking")
