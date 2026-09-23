import contextvars
import logging
import re
from common.tool_cache import tool_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, List, Dict

from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from services.tstation.common.tstation_be_client import (
    get_client,
    _error_response,
    _success_response,
    _to_dict,
)
from services.tstation.policies.domestic_region_gate import decide_domestic_search_area
from services.tstation.policies.reservation_template_policy import reservation_sale_min_install_date
from services.tstation.agents.c_transaction_agent.install_availability import combine_install_availability
from langchain_core.tools import tool
from common.brand_mapping import normalize_brand_name

# STORE AF
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_list_api_store_list_get import sync_detailed as get_store_list
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_detail_api_store_detail_get import sync_detailed as get_store_detail
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_schedule_api_store_schedule_get import sync_detailed as get_store_schedule
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_install_availability_api_store_install_availability_post import sync_detailed as get_store_install_availability
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.search_stores_complex_api_store_complex_search_get import sync_detailed as search_stores_complex
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.search_place_api_store_place_search_get import sync_detailed as search_place
from common.tstation_be_api_client.hkt_api_client.models import ScheduleMode

# PRICE AF
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_price_api_prices_final_get import sync_detailed as get_price
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_my_coupons_api_prices_coupons_mine_get import sync_detailed as get_my_coupons

# EVENT / DEAL AF — 상품번호 기준 진행 중 기획전+쿠폰 조회
from common.tstation_be_api_client.hkt_api_client.api.event_deal_af_이벤트_및_기획전_조회.get_deals_by_product_api_events_deals_by_product_get import sync_detailed as get_deals_by_product

# COUPON AF — 쿠폰 발급 / 적용 상품 조회
from common.tstation_be_api_client.hkt_api_client.api.coupon_af_쿠폰_발급.issue_coupon_by_goods_api_coupons_issue_goods_post import sync_detailed as issue_coupon_by_goods
from common.tstation_be_api_client.hkt_api_client.api.coupon_af_쿠폰_발급.issue_coupon_by_cpn_api_coupons_issue_cpn_post import sync_detailed as issue_coupon_by_cpn
from common.tstation_be_api_client.hkt_api_client.api.coupon_af_쿠폰_발급.get_coupon_applicable_products_api_coupons_applicable_products_get import sync_detailed as get_coupon_applicable_products
from common.tstation_be_api_client.hkt_api_client.models import (
    GoodsCouponIssueRequest,
    CpnCouponIssueRequest,
)

# INVENTORY AF
from common.tstation_be_api_client.hkt_api_client.api.inventory_af_재고_조회.get_logistics_inventory_api_inventory_logistics_post import sync_detailed as get_logistics_inventory
from common.tstation_be_api_client.hkt_api_client.api.inventory_af_재고_조회.get_store_inventory_api_inventory_store_post import sync_detailed as get_store_inventory
from common.tstation_be_api_client.hkt_api_client.models import (
    LogisticsRequest,
    StoreInventoryRequest,
    GoodsItem,
    ShopIdItem,
    StoreInstallAvailabilityRequest,
)

# QUICK SHOPPING AF (setOrderFormAI - 퀵쇼핑/장바구니 통합 API)
from common.tstation_be_api_client.hkt_api_client.api.quick_shopping_af_퀵_쇼핑주문서_초안_생성.set_order_form_ai_api_quick_order_order_set_order_form_ai_do_post import sync_detailed as set_order_form_ai
from common.tstation_be_api_client.hkt_api_client.models import SetOrderFormAIRequest

# ORDER & DELIVERY AF
from common.tstation_be_api_client.hkt_api_client.api.order_delivery_af_주문_및_배송_추적.get_order_delivery_api_orders_summary_get import sync_detailed as get_order_delivery
from common.tstation_be_api_client.hkt_api_client.api.order_delivery_af_주문_및_배송_추적.get_orders_api_orders_get import sync_detailed as get_orders
from common.tstation_be_api_client.hkt_api_client.api.maintenance_history_af_정비이력_조회.get_maintenance_history_api_member_maintenance_history_get import sync_detailed as get_maintenance_history

# Reservation AF — 매장 방문 예약 조회
from common.tstation_be_api_client.hkt_api_client.api.reservation_af_매장_방문_예약_조회.get_reservations_api_reservations_get import sync_detailed as get_reservations

# Member AF — 회원 단골매장 조회
from common.tstation_be_api_client.hkt_api_client.api.member_af_회원_정보_조회.get_favorite_stores_api_member_favorite_stores_get import sync_detailed as get_favorite_stores

logger = logging.getLogger(__name__)
current_transaction_store_preview_tool_patch: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "current_transaction_store_preview_tool_patch", default={}
)

_KOREA_ADDRESS_PREFIX_RE = re.compile(
    r"^(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)"
)
_FOREIGN_REGION_QUERY_RE = re.compile(
    r"^(평양|북한|베이징|북경|상하이|상해|러시아|일본|중국|미국|대만|타이완|홍콩|마카오|"
    r"싱가포르|베트남|태국|방콕|도쿄|동경|오사카|교토|후쿠오카|파리|런던|독일|프랑스|유럽)$",
    re.IGNORECASE,
)
_BUSINESS_PLACE_SUFFIX_RE = re.compile(
    r"(주유소|충전소|식당|반점|냉면|카페|커피|병원|의원|약국|마트|상사|모텔|호텔|"
    r"부동산|공인중개사|교회|성당|학원|학교|아파트|빌라|오피스텔|공장)$"
)
_LANDMARK_REGION_SUFFIX_RE = re.compile(
    r"(역|구청|시청|군청|도청|터미널|공항|항구|IC|나들목|대교|시장|광장|공원|타워|몰|시티)$",
    re.IGNORECASE,
)


def _apply_store_preview_policy_patch(
    *,
    patch: dict[str, Any],
    goods_no: str | None,
    ord_qty: int | None,
    region_code: str | None,
    store_nm: str | None,
    user_xpos: float | None,
    user_ypos: float | None,
) -> tuple[str | None, int | None, str | None, str | None, float | None, float | None]:
    """Fill only missing preview args from the request-scoped Transaction ToolPlan."""
    if not patch:
        return goods_no, ord_qty, region_code, store_nm, user_xpos, user_ypos
    preserve_confirmed = bool(patch.get("preserve_confirmed_product_slots"))
    if patch.get("goods_no") and (not goods_no or (preserve_confirmed and goods_no != str(patch["goods_no"]))):
        goods_no = str(patch["goods_no"])
    if (patch.get("ord_qty") or patch.get("quantity")) and (
        ord_qty is None or ord_qty < 1 or preserve_confirmed
    ):
        try:
            ord_qty = int(patch.get("ord_qty") or patch.get("quantity"))
        except (TypeError, ValueError):
            pass
    if not region_code and patch.get("region"):
        region_code = str(patch["region"])
    if not store_nm and patch.get("store_name"):
        store_nm = str(patch["store_name"])
    if user_xpos is None and patch.get("user_xpos") is not None:
        try:
            user_xpos = float(patch["user_xpos"])
        except (TypeError, ValueError):
            pass
    if user_ypos is None and patch.get("user_ypos") is not None:
        try:
            user_ypos = float(patch["user_ypos"])
        except (TypeError, ValueError):
            pass
    return goods_no, ord_qty, region_code, store_nm, user_xpos, user_ypos


_STORE_BRAND_PREFIXES = ("티스테이션 ", "더타이어샵 ")


def _strip_brand_prefix(shop_nm: str) -> str:
    for prefix in _STORE_BRAND_PREFIXES:
        if shop_nm.startswith(prefix):
            return shop_nm[len(prefix):]
    return shop_nm


def _validate_store_nm_exact_match(user_input: str, stores: List[dict]) -> dict | None:
    """Validate user's store_nm input against returned shop_nm values (after brand prefix strip).

    Fires only when user_input (or its brand-stripped form) looks like a branch name (ends with "점").

    Returns:
        None — validation passes (Case b) or doesn't apply (region search, brand-only, etc.)
        dict — override tool response payload for Case (a) empty or Case (c) mismatch
    """
    if not user_input:
        return None

    user_branch = _strip_brand_prefix(user_input)
    if not user_branch.endswith("점"):
        return None

    if not stores:
        region = user_branch[:-1]
        # 복합 지역명 휴리스틱: stripped 이 4자 이상이면 사용자가 두 지역명을 붙여 입력했을
        # 가능성이 높다 (예: "분당판교점" → "분당" + "판교"). 한국 주요 지하철/구/동 이름이
        # 대부분 2글자이므로 2+2 분할을 1순위 후보로 제시. 4자 이상은 단일 동/지명일
        # 가능성도 있으므로 (예: "광교신도시") "지역명을 다시 입력" chip 으로 안전한 fallback 제공.
        if len(region) >= 4 and len(region) % 2 == 0:
            first_half = region[: len(region) // 2]
            second_half = region[len(region) // 2 :]
            confirmation_msg = (
                f"고객님, '{user_input}'으로 검색되는 매장이 없습니다. "
                f"혹시 '{first_half}' 또는 '{second_half}' 지역 중 어느 매장을 찾으시나요?"
            )
            quick_replies_hint = (
                f'[{{"label":"{first_half} 지역 검색","domain":"TRANSACTION"}}, '
                f'{{"label":"{second_half} 지역 검색","domain":"TRANSACTION"}}, '
                f'{{"label":"다른 매장 찾기","domain":"TRANSACTION"}}]'
            )
            return {
                "status": "store_name_no_match",
                "http_status": 200,
                "data": {
                    "user_input": user_input,
                    "region_candidates": [first_half, second_half],
                    "stores": [],
                    "validation_message": confirmation_msg,
                    "instruction_to_agent": (
                        f"DETERMINISTIC GUARD: 사용자 입력 '{user_input}' 으로 매장 검색 결과 없음. "
                        f"복합 지역명 의심 ('{first_half}' + '{second_half}'). "
                        f"validation_message 를 그대로 emit + quickReplies: {quick_replies_hint}. "
                        f"이 턴에 다른 store/schedule/inventory 도구 호출 절대 금지. STOP."
                    ),
                },
            }
        confirmation_msg = (
            f"고객님, '{user_input}'으로 검색되는 매장이 없습니다. "
            f"'{region}' 지역으로 검색해 드릴까요?"
        )
        return {
            "status": "store_name_no_match",
            "http_status": 200,
            "data": {
                "user_input": user_input,
                "suggested_region": region,
                "stores": [],
                "validation_message": confirmation_msg,
                "instruction_to_agent": (
                    f"DETERMINISTIC GUARD: 사용자 입력 '{user_input}' 으로 매장 검색 결과 없음. "
                    f"validation_message 를 그대로 emit + quickReplies: "
                    f"[\"네, {region} 지역으로 검색\", \"다른 매장 찾기\"]. "
                    f"이 턴에 다른 store/schedule/inventory 도구 호출 절대 금지. STOP."
                ),
            },
        }

    branch_names = [_strip_brand_prefix(s.get("shop_nm", "")) for s in stores]
    if any(b == user_branch for b in branch_names):
        return None

    candidate_names = [s.get("shop_nm", "") for s in stores]
    candidate_stores = [
        {
            "shop_id": s.get("shop_id"),
            "shop_nm": s.get("shop_nm", ""),
        }
        for s in stores
        if isinstance(s, dict) and s.get("shop_nm")
    ]
    if len(candidate_names) == 1:
        confirmation_msg = (
            f"고객님, 요청하신 '{user_input}'으로 검색한 결과 "
            f"'{candidate_names[0]}' 매장이 있는데 이 매장이 맞을까요?"
        )
        quick_reply_hint = '["네, 맞아요", "다른 매장 찾기"]'
    else:
        joined = "\n".join(f"- {name}" for name in candidate_names)
        confirmation_msg = (
            f"고객님, 요청하신 '{user_input}'으로 검색한 결과 다음 매장들이 있는데, "
            f"원하시는 매장이 있나요?\n{joined}"
        )
        quick_reply_hint = "각 candidates 매장명을 chip 으로 + [\"다른 매장 찾기\"]"
    return {
        "status": "store_name_mismatch",
        "http_status": 200,
        "data": {
            "user_input": user_input,
            "candidates": candidate_names,
            "candidate_stores": candidate_stores,
            "stores": [],
            "validation_message": confirmation_msg,
            "instruction_to_agent": (
                f"DETERMINISTIC GUARD: 사용자 입력 '{user_input}' 과 매칭된 매장 분점명이 정확히 일치하지 않음 "
                f"(candidates={candidate_names}). "
                f"validation_message 를 그대로 emit + quickReplies: {quick_reply_hint}. "
                f"get_store_install_availability_tool / get_store_detail_tool 절대 호출 금지. STOP."
            ),
        },
    }




def _fetch_order_detail(ord_no: str, client: AuthenticatedClient | None = None) -> dict:
    """Fetch order delivery detail for a single ord_no, return detail dict or empty on failure."""
    try:
        response = get_order_delivery(client=client or get_client(), query_no=ord_no)
        if response.parsed is None:
            return {}
        return _to_dict(response.parsed)
    except Exception:
        logger.warning("[_fetch_order_detail] Failed for ord_no=%s", ord_no)
        return {}


def _enrich_orders_with_detail(orders: list[dict]) -> list[dict]:
    """Parallel-fetch order detail for each order and merge into order dicts."""
    if not orders:
        return orders

    ord_nos = [o.get("ord_no") for o in orders if o.get("ord_no")]
    if not ord_nos:
        return orders

    detail_map: dict[str, dict] = {}
    detail_client = get_client()
    with ThreadPoolExecutor(max_workers=min(len(ord_nos), 20)) as executor:
        futures = {executor.submit(_fetch_order_detail, ono, detail_client): ono for ono in ord_nos}
        for future in as_completed(futures):
            ono = futures[future]
            detail_map[ono] = future.result()

    return [{**order, "detail": detail_map.get(order.get("ord_no"), {})} for order in orders]


# =====================================================
# PRICING TOOLS
# =====================================================

@tool
@tool_cache(ttl=300)
def get_final_price_tool(goods_no: str, member_type: str | None = None):
    """
    Get product price and discount (base price, promotion, coupon, labor cost).

    Response fields:
        - sale_prc: 정가 (PR_ITEM_PRC_INFO.SALE_PRC)
        - extra_fvr_sale_prc / extra_fvr_sale_per: 사이트 일반 노출 혜택가
          (PR_GOODS_DSCNT_PRC_INFO.EXTRA_FVR_SALE_PRC). "모든 쿠폰 적용 가정" 의
          기대 가격 — 회원이 실제 보유한 쿠폰과 일치하지 않을 수 있다.
        - wage_prc / wage_today_prc: 공임비
        - cheapest_final_prc: **회원 보유 쿠폰 3-stage 그리디 적용 후 최저가**.
          사이트 결제 페이지가 표시하는 paymentAmount 와 일치한다. 사용 시 이 값을
          우선하라.
        - cheapest_total_discount: sale_prc - cheapest_final_prc
        - cheapest_applied_coupons[]: 단계별 적용 쿠폰 {stage, cpn_no, cpn_nm,
          discount_amt}. 자연어 답변에 cpn_nm 인용 권장.
        - smrt_pay_yn: 스마트페이 가능 여부. "Y"이면 스마트페이 월 납부액 계산 가능,
          "N"이면 스마트페이 할부서비스 미지원 상품으로 안내하라.
        - smrt_pay_prc: 스마트페이 월 납부액 계산 기준 금액
          (PR_ITEM_PRC_INFO.SMRT_PAY_PRC). 이 값은 타이어 1개 기준 금액이므로
          스마트페이 문의는 이 값에 4를 곱한 뒤 12/24로 나누고 반올림해 안내하라.
          이 1개 기준값 자체를 '기준금액'으로 사용자에게 노출하지 마라 —
          사용자에게 보이는 스마트페이 기준금액은 항상 4개 기준(smrt_pay_prc * 4)이다.
          extra_fvr_sale_prc, wage_prc,
          cheapest_final_prc, payment_amount 를 스마트페이 계산에 사용하지 마라.

    paymentAmount 우선순위 (preOrder / orderComplete 카드 채울 때):
        cheapest_final_prc → extra_fvr_sale_prc → sale_prc (fallback 순서).
        cheapest_final_prc 가 non-null 이면 무조건 그것을 써라 — 사이트 결제
        금액과 일치하는 유일한 값이다.

    Args:
        goods_no (str): Product number (e.g., GXXXXXXXXXXXX).
        member_type (str | None): Member type (e.g., 'general', 'PARTNER').

    Example: {"goods_no": "GXXXXXXXXXXXX", "member_type": "general"}
    """
    logger.debug("[TOOL][get_final_price_tool] Called with: goods_no=%s, member_type=%s", goods_no, member_type)

    try:
        response = get_price(client=get_client(), goods_no=goods_no, member_type=member_type)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get product price"
            )
        # logger.debug("[TOOL][get_final_price_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_final_price_tool] Failed")
        return _error_response(None, str(e), "Failed to get product price")


@tool
def get_my_coupons_tool(lang_cd: str = "ko"):
    """
    내 쿠폰 목록 조회.

    Use when user asks "내 쿠폰", "쿠폰 목록", "my coupons".

    Args:
        lang_cd (str): Language code (default: 'ko').
    """
    logger.debug("[TOOL][get_my_coupons_tool] Called with: lang_cd=%s", lang_cd)

    try:
        response = get_my_coupons(client=get_client(), lang_cd=lang_cd)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get my coupons"
            )
        # logger.debug("[TOOL][get_my_coupons_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_my_coupons_tool] Failed")
        return _error_response(None, str(e), "Failed to get my coupons")


@tool
def issue_coupon_tool(goods_no: str | None = None, cpn_no: str | None = None):
    """
    쿠폰 발급 (다운로드) — 정확히 한쪽만 입력 (XOR):
    - goods_no 모드: 상품에 해당하는 최저가 혜택 쿠폰(상품쿠폰 + 결제쿠폰) 묶음 발급
    - cpn_no 모드: 지정된 쿠폰번호 단일 발급

    Use when: 사용자가 쿠폰 수령/다운로드 요청 ("쿠폰 받아줘", "발급해줘").
    DO NOT pass both arguments — choose exactly one.

    Args:
        goods_no (str | None): 상품 번호. cpn_no와 동시 입력 불가.
        cpn_no (str | None): 쿠폰 번호. goods_no와 동시 입력 불가.

    Examples:
        - {"goods_no": "G000000314254"}   # 상품 기준 최저가 쿠폰 묶음
        - {"cpn_no": "C00000123"}         # 특정 쿠폰 단일 발급

    Response code: 100=발급 성공, 900=실패(이미 보유 또는 대상 아님).
    """
    logger.debug(
        "[TOOL][issue_coupon_tool] Called with: goods_no=%s, cpn_no=%s",
        goods_no, cpn_no,
    )

    # XOR 검증
    if (goods_no is None) == (cpn_no is None):
        return _error_response(
            None,
            "InvalidArguments",
            "issue_coupon_tool requires exactly one of goods_no or cpn_no",
        )

    try:
        if goods_no is not None:
            body = GoodsCouponIssueRequest(goods_no=goods_no)
            response = issue_coupon_by_goods(client=get_client(), body=body)
        else:
            body = CpnCouponIssueRequest(cpn_no=cpn_no)
            response = issue_coupon_by_cpn(client=get_client(), body=body)

        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to issue coupon",
            )
        # logger.debug("[TOOL][issue_coupon_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][issue_coupon_tool] Failed")
        return _error_response(None, str(e), "Failed to issue coupon")


@tool
def get_coupon_applicable_products_tool(
    cpn_no: List[str] | None = None,
    deal_no: List[str] | None = None,
):
    """
    쿠폰(cpn_no) 또는 기획전(deal_no) 에 적용 가능한 상품/매장 조회.

    Use when 사용자가 "이 쿠폰 어디에 쓸 수 있어?", "이 쿠폰 적용 상품", "이 쿠폰 어느
    매장에서 써?", "기획전 상품", "기획전에 어떤 상품 있어" 류 질문을 했을 때.
    cpn_no, deal_no 중 한쪽 또는 양쪽을 리스트로 전달한다. 각 최대 10개. 둘 다 비우면
    빈 응답.

    Args:
        cpn_no (List[str] | None): 쿠폰 번호 리스트. 예: ["C0000001234"], ["C1","C2"].
        deal_no (List[str] | None): 기획전 번호 리스트. 예: ["D0000001234"].

    Response shape:
        {
          "total_coupons": int,         # coupons[] 그룹 수
          "total_deals": int,
          "total_products": int,        # coupons[].items + deals[].items 합계
          "total_store_coupons": int,   # stores[] 그룹 수
          "total_stores": int,          # stores[].items 합계
          "coupons": [{"cpn_no": str, "total": int, "items": [{ptrn_cd, goods_nm}]}],
          "deals":   [{"deal_no": str, "total": int, "items": [{ptrn_cd, goods_nm}]}],
          "stores":  [{"cpn_no": str, "total": int, "items": [{shop_id, shop_nm}]}]
        }

    매핑 타입:
    - coupons[] / deals[].items: 패턴(PTRN_CD) 기준 대표 상품 — ptrn_cd / goods_nm 만 포함.
    - stores[].items: **매장 한정 쿠폰** — 특정 매장에서만 쓸 수 있는 쿠폰. shop_id +
      shop_nm 만 포함, 상품 정보 없음.

    하나의 cpn_no 가 상품 매핑과 매장 매핑 둘 다 가질 수도 있다 (드물지만 가능).
    coupons[] 와 stores[] 양쪽에 동일 cpn_no 가 등장할 수 있다.
    """
    cpn_csv = ",".join(cpn_no) if cpn_no else ""
    deal_csv = ",".join(deal_no) if deal_no else ""
    logger.debug(
        "[TOOL][get_coupon_applicable_products_tool] Called with: cpn_no=%s deal_no=%s",
        cpn_csv, deal_csv,
    )

    try:
        response = get_coupon_applicable_products(
            client=get_client(),
            cpn_no=cpn_csv,
            deal_no=deal_csv,
        )
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get coupon applicable products",
            )
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_coupon_applicable_products_tool] Failed")
        return _error_response(None, str(e), "Failed to get coupon applicable products")


# =====================================================
# PROMOTION (DEAL + COUPON BY PRODUCT) TOOLS
# =====================================================

@tool
@tool_cache(ttl=300)
def get_product_promotions_tool(goods_no: str):
    """
    상품번호 기준 진행 중 기획전 + 매핑된 활성 쿠폰(C301) 목록 조회.

    Use when:
    - 상품이 특정된(goods_no 확보) 상태에서 사용자가 다음과 같이 물을 때:
      "이 상품에 적용 가능한 쿠폰 알려줘", "이 상품 기획전 알려줘",
      "이 상품에 진행 중인 프로모션 / 혜택 / 행사 / 이벤트 있어?".
    - 이 도구는 "특정 상품에 매핑된 진행 중 기획전쿠폰"만 반환.

    Pre-condition:
    - goods_no must be confirmed (slot 또는 직전 도구 결과). 없으면 사용 금지.

    Args:
        goods_no (str): 상품 번호 (예: GXXXXXXXXXXXX).

    Response shape:
        {
          "goods_no": "...",
          "total": <int>,
          "items": [
            {
              "deal_no": "...",
              "deal_nm": "...",
              "disp_strt_dtime": "YYYY-MM-DD HH:MM:SS",
              "disp_end_dtime": "YYYY-MM-DD HH:MM:SS",
              "coupons": [
                {"cpn_no": "...", "cpn_knd_cd": "C301", "cpn_prgs_stat_cd": "40"}
              ]
            }
          ]
        }

    Example: {"goods_no": "G000000314254"}
    """
    logger.debug("[TOOL][get_product_promotions_tool] Called with: goods_no=%s", goods_no)

    if not goods_no or not goods_no.strip():
        return _error_response(None, "InvalidArguments", "goods_no는 필수 입력입니다.")

    try:
        response = get_deals_by_product(client=get_client(), goods_no=goods_no.strip())
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get product promotions",
            )
        # logger.debug("[TOOL][get_product_promotions_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_product_promotions_tool] Failed")
        return _error_response(None, str(e), "Failed to get product promotions")


# =====================================================
# INVENTORY TOOLS
# =====================================================

@tool
def get_logistics_inventory_tool(goods_no: str):
    """
    DEPRECATED: use get_store_install_availability_tool instead.

    물류 창고 재고 조회.

    Deprecated compatibility tool only. Do not call in new flows.
    get_store_install_availability_tool now calculates logistics availability,
    store inventory availability, and schedule slots in one backend request.

    Result interpretation:
    - logistics_qty > 0 → LOGISTICS_AVAILABLE (all stores eligible)
    - logistics_qty = 0 → LOGISTICS_UNAVAILABLE (must check store inventory)
    - rsv_sale_yn="Y" → reservation order available; use rsv_install_date for user-facing date.
    ⚠️ Never expose logistics_qty or rsv_sale_yn raw value to user.

    Args:
        goods_no (str): Product number.

    Example: {"goods_no": "GXXXXXXXXXXXX"}
    """
    body = LogisticsRequest(goods_no=goods_no)
    logger.debug("[TOOL][get_logistics_inventory_tool] Called with: goods_no=%s", goods_no)

    try:
        response = get_logistics_inventory(client=get_client(), body=body)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get logistics inventory"
            )
        # logger.debug("[TOOL][get_logistics_inventory_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_logistics_inventory_tool] Failed")
        return _error_response(None, str(e), "Failed to get logistics inventory")


@tool
def get_store_inventory_tool(goods_list: List[Dict[str, Any]], shop_id_list: List[Dict[str, Any]]):
    """
    DEPRECATED: use get_store_install_availability_tool instead.

    Check store inventory availability.

    Deprecated compatibility tool only. Do not call in new flows.
    get_store_install_availability_tool now returns today/T-NA/logistics flags
    and installable schedule slots for each store.

    Returns todayShopArray (stores that can install today) and tnaShopArray (T-NA delivery eligible).

    Args:
        goods_list (List[Dict]): [{"goodsNo": "G123", "qty": "4"}] — qty is STRING type.
        shop_id_list (List[Dict]): [{"shopId": "F0001"}]

    Example: {"goods_list": [{"goodsNo": "GXXXXXXXXXXXX", "qty": "4"}], "shop_id_list": [{"shopId": "BXXXXX"}]}
    """
    g_items = [GoodsItem(goods_no=g["goodsNo"], qty=str(g["qty"])) for g in goods_list]
    s_items = [ShopIdItem(shop_id=s["shopId"]) for s in shop_id_list]
    body = StoreInventoryRequest(goods_list=g_items, shop_id_list=s_items)
    logger.debug("[TOOL][get_store_inventory_tool] Called with: goods_list=%s, shop_id_list=%s", goods_list, shop_id_list)

    try:
        response = get_store_inventory(client=get_client(), body=body)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get store inventory"
            )
        # logger.debug("[TOOL][get_store_inventory_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_store_inventory_tool] Failed")
        return _error_response(None, str(e), "Failed to get store inventory")


def _normalize_availability_goods_items(
    goods_no: str | None,
    ord_qty: int,
    goods_items: List[Dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Validate the public tool boundary for single- or multi-product input."""
    if goods_items is None:
        try:
            safe_qty = max(1, int(ord_qty or 1))
        except (TypeError, ValueError):
            safe_qty = 1
        return [{"goods_no": str(goods_no).strip() if goods_no else None, "ord_qty": safe_qty}], None
    if goods_no or not goods_items:
        return [], "provide either goods_no or a non-empty goods_items list"

    normalized = []
    for item in goods_items:
        item_goods_no = str(item.get("goods_no") or "").strip() if isinstance(item, dict) else ""
        if not item_goods_no:
            return [], "each goods_items entry requires goods_no"
        try:
            item_qty = max(1, int(item.get("ord_qty") or 1))
        except (TypeError, ValueError):
            return [], f"invalid ord_qty for goods_no={item_goods_no}"
        normalized.append({"goods_no": item_goods_no, "ord_qty": item_qty})
    return normalized, None


def _get_store_install_availability_result(
    *,
    candidates: list[str],
    goods_no: str | None,
    ord_qty: int,
    requested_cal_day: str | None,
) -> dict:
    """Call the unified BE availability endpoint for one product."""
    body = StoreInstallAvailabilityRequest(shop_ids=candidates, goods_no=goods_no, qty=ord_qty)
    response = get_store_install_availability(client=get_client(), body=body)
    if response.parsed is None:
        return _error_response(
            response.status_code,
            f"HTTP {response.status_code}",
            response.content.decode(errors="ignore") or "Failed to get store install availability",
        )
    data = _to_dict(response.parsed)
    data["inventory"] = _availability_inventory_payload(data)
    data["logistics"] = {"has_logistics_stock": _availability_has_logistics(data)}
    data["schedule"] = _availability_schedule_payload(
        data,
        candidate_shop_ids=candidates,
        requested_cal_day=requested_cal_day,
    )
    return _success_response(response.status_code, data)


@tool
def get_store_install_availability_tool(
    shop_id_list: List[str],
    goods_no: str | None = None,
    ord_qty: int = 1,
    requested_cal_day: str | None = None,
    goods_items: List[Dict[str, Any]] | None = None,
):
    """
    Unified store install availability lookup.

    Use this single tool for:
    - 가장 빠른 장착 가능일/시간 확인
    - 특정 날짜 장착 가능 여부 확인
    - 상품/수량이 있는 주문·재고·예약 가능성 확인
    - 상품이 아직 없는 일반 매장 방문 예약 스케줄 확인 (goods_no=None)

    This replaces the old three-step flow:
    get_logistics_inventory_tool → get_store_inventory_tool → get_store_schedule_tool.
    Do not call those deprecated tools in new flows.

    Args:
        shop_id_list (List[str]): Store IDs to check. Use IDs from store search results.
        goods_no (str | None): Product number. Pass None for a general store visit schedule.
        ord_qty (int): Quantity when goods_no is present. Default 1.
        goods_items (List[Dict] | None): Products that must all be available, formatted as
            [{"goods_no": "G...", "ord_qty": 2}, ...]. Do not also pass goods_no.
        requested_cal_day (str | None): YYYYMMDD date. REQUIRED whenever the user asked about a specific
            day (including "today"/"tomorrow") — pass that day here. The returned schedule is then filtered
            to that day, and an empty schedule means that day has no slots, which you must state plainly.
            Leave it None only when the user named no day and just wants the earliest availability.

    Returns:
        {
          "items": [{shop_id, status, mode, has_today_stock, has_tna_stock,
                     has_logistics_stock, first_available_slot, slots}],
          "inventory": {todayShopArray, tnaShopArray},
          "logistics": {has_logistics_stock},
          "schedule": {tier, stores, candidate_shop_ids, requested_cal_day?}
        }
    """
    candidates = [str(shop_id).strip() for shop_id in (shop_id_list or []) if str(shop_id).strip()]
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        return _error_response(None, "invalid_input", "shop_id_list is empty")
    normalized_items, validation_error = _normalize_availability_goods_items(goods_no, ord_qty, goods_items)
    if validation_error:
        return _error_response(None, "invalid_input", validation_error)
    logger.debug(
        "[TOOL][get_store_install_availability_tool] Called with shop_id_list=%s goods_no=%s ord_qty=%s "
        "goods_items=%s requested_cal_day=%s",
        candidates,
        goods_no,
        ord_qty,
        normalized_items if goods_items is not None else None,
        requested_cal_day,
    )

    try:
        results = [
            _get_store_install_availability_result(
                candidates=candidates,
                goods_no=item["goods_no"],
                ord_qty=item["ord_qty"],
                requested_cal_day=requested_cal_day,
            )
            for item in normalized_items
        ]
        failed = next((result for result in results if result.get("status") != "success"), None)
        if failed is not None:
            return failed
        if len(results) == 1:
            return results[0]
        return _success_response(
            200,
            combine_install_availability(
                results=results,
                candidate_shop_ids=candidates,
                requested_cal_day=requested_cal_day,
            ),
        )
    except Exception as e:
        logger.exception("[TOOL][get_store_install_availability_tool] Failed")
        return _error_response(None, str(e), "Failed to get store install availability")


# =====================================================
# STORE TOOLS
# =====================================================

@tool
@tool_cache(ttl=3600)
def search_place_tool(query: str, size: int = 10):
    """
    위치 명칭 검색 (Kakao 키워드 검색) — 반환된 x,y 좌표를 get_nearby_stores_tool에 사용.
    ⚠️ 좌표(x,y)는 내부 파라미터 전용 — 사용자에게 절대 노출하지 마세요.

    Args:
        query (str): 검색어 (e.g., '센텀시티', '강남역').
        size (int): 최대 결과 수 (default 10).

    Example: {"query": "강남역"}
    """
    logger.debug("[TOOL][search_place_tool] Called with: query=%s, size=%s", query, size)

    try:
        response = search_place(client=get_client(), query=query, size=size)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to search place"
            )
        # logger.debug("[TOOL][search_place_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][search_place_tool] Failed")
        return _error_response(None, str(e), "Failed to search place")


@tool
@tool_cache(ttl=300)
def get_nearby_stores_tool(
    user_xpos: float,
    user_ypos: float,
    radius_km: float = 10.0,
    svc_codes: List[str] | None = None,
    all_my_t_only: bool = False,
    imported_car_only: bool = False,
    chl_sct_cd: str | None = None,
    sort_by: str | None = None,
    limit: int = 10,
):
    """
    Get nearby stores within radius based on coordinates.

    Store fields: is_installable (온라인 장착 가능), is_imported_car (수입차 특화점),
    svc_codes (매장이 보유한 서비스 코드 리스트).

    ⚠️ 수입차 특화점: 사용자가 "수입차 특화점/전문매장/전문점/매장, 외제차 특화점/전문매장" 언급 시 imported_car_only=True.

    Args:
        user_xpos (float): X 좌표 (경도).
        user_ypos (float): Y 좌표 (위도).
        radius_km (float): 검색 반경 km (default 10).
        svc_codes (List[str] | None): 매장 서비스 필터 (OR 조건: 하나라도 보유한 매장 반환).
            응답의 svc_codes 필드와 동일 코드 체계.
            - "113": 타이어 (온라인 주문)
            - "116": 배터리 (온라인 주문)
            - "119": 타이어 보관서비스 (윈터타이어 주문 시 113과 함께 필요)
            - "120": 수입타이어 취급 (수입차 특화점은 imported_car_only 별도 사용)
            - "121": 경정비 - 온라인 (엔진오일세트/와이퍼/실내필터 등 배터리 외 경정비)
            - "122": 경정비 - 오늘장착 (당일 경정비)
            - "124": 휠얼라이먼트 - 오프라인
            - "125": 휠얼라이먼트 - 온라인
            - "126": 무상점검
            예: 엔진오일 가능 매장 = ["121"], 휠얼라이먼트 가능 매장 = ["124","125"]
        all_my_t_only (bool): True → "all my T" 매장만 (SMART_CARE_SHOP_YN='Y'). Default False.
        imported_car_only (bool): True → 수입차 특화점만. Default False.
        chl_sct_cd (str | None): F=티스테이션, S=더타이어샵, None=전체.
        sort_by (str | None): 정렬 기준. None(default)=좌표 있으면 거리순 / "rating"=평점순(SHOP_EVAL_CVRT_IDX
            DESC NULLS LAST) / "review_count"=리뷰 많은 순(서브쿼리 활성) / "distance"=거리순(좌표 필수).
            사용자가 "근처/가까운"만 표현하면 None, "평점 좋은/별점 높은/친절한/직원이 친절한/직원 친절도/
            서비스 좋은/서비스 제일 좋은/눈탱이 안치는/바가지 안치는/믿을 수 있는/신뢰할 수 있는/추천/
            얼라인먼트 잘 보는/얼라인먼트 잘하는"이면 "rating", "리뷰 많은/후기 많은"이면 "review_count".
            ⚠️ 얼라인먼트 관련 검색 시: sort_by="rating"과 함께 svc_codes=["124","125"] 를 반드시 함께 전달.
        limit (int): 반환 매장 수 상한 (1-10). Default 10. 사용자가 "N개"를 명시하면
            그 값을 전달. location 카드 max_length=10 제약 때문에 10 초과 시 10으로 클램핑.

    Example: {"user_xpos": 127.0276, "user_ypos": 37.4979, "radius_km": 20, "chl_sct_cd": "F", "limit": 5}
    """
    logger.debug(
        "[TOOL][get_nearby_stores_tool] Called with: user_xpos=%s, user_ypos=%s, radius_km=%s, svc_codes=%s, "
        "all_my_t_only=%s, imported_car_only=%s, chl_sct_cd=%s, sort_by=%s",
        user_xpos, user_ypos, radius_km, svc_codes, all_my_t_only, imported_car_only, chl_sct_cd, sort_by,
    )

    try:
        response = get_store_list(
            client=get_client(),
            xpos=user_xpos,
            ypos=user_ypos,
            radius_km=radius_km,
            svc_codes=svc_codes,
            all_my_t_only=all_my_t_only,
            imported_car_only=imported_car_only,
            chl_sct_cd=chl_sct_cd,
            sort_by=sort_by,
        )
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get nearby stores"
            )
        # logger.debug("[TOOL][get_nearby_stores_tool] Response: %s", response.parsed)
        data = _to_dict(response.parsed)

        # Truncate to top `limit` stores (clamped to 10 — LocationTemplate max_length=10).
        cap = max(1, min(int(limit), 10))
        stores = data.get("stores") if isinstance(data, dict) else None
        if isinstance(stores, list) and len(stores) > cap:
            original_count = len(stores)
            data["stores"] = _sort_store_candidates(stores, sort_by)[:cap]
            logger.debug(
                "[TOOL][get_nearby_stores_tool] Truncated %d stores -> top %d (sort_by=%s)",
                original_count, cap, sort_by,
            )

        return _success_response(response.status_code, data)
    except Exception as e:
        logger.exception("[TOOL][get_nearby_stores_tool] Failed")
        return _error_response(None, str(e), "Failed to get nearby stores")


def _clamp_int(value: int | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _sort_store_candidates(stores: list[dict], sort_by: str | None) -> list[dict]:
    # An explicit sort_by is the user's ordering — the BE already returned the rows in
    # that order (rating: SHOP_EVAL_CVRT_IDX DESC NULLS LAST). Re-ranking all_my_t stores
    # to the front here would silently break the requested order, so keep BE order as-is.
    # all_my_t priority still applies to the default/distance modes below.
    if sort_by in ("rating", "review_count"):
        return list(stores)
    return sorted(
        stores,
        key=lambda s: (
            not bool(s.get("is_all_my_t", False)),
            not bool(s.get("is_installable", False)),
            s.get("distance_km") if isinstance(s.get("distance_km"), (int, float)) else float("inf"),
        ),
    )


def _first_place_coordinates(place_data: dict) -> tuple[float | None, float | None, dict | None]:
    items = place_data.get("items") or place_data.get("documents") or place_data.get("places")
    if not isinstance(items, list) or not items:
        return None, None, None
    place = items[0] if isinstance(items[0], dict) else {}
    x_raw = place.get("x") or place.get("longitude") or place.get("lng")
    y_raw = place.get("y") or place.get("latitude") or place.get("lat")
    try:
        return float(x_raw), float(y_raw), place
    except (TypeError, ValueError):
        return None, None, None


def _place_title(place: dict | None) -> str:
    if not isinstance(place, dict):
        return ""
    return str(
        place.get("place_name")
        or place.get("title")
        or place.get("name")
        or ""
    ).strip()


def _place_address(place: dict | None) -> str:
    if not isinstance(place, dict):
        return ""
    return str(
        place.get("road_addr")
        or place.get("road_address_name")
        or place.get("address_name")
        or place.get("address")
        or ""
    ).strip()


def _place_meta(place: dict | None) -> dict[str, str | None]:
    title = _place_title(place)
    address = _place_address(place)
    return {
        "place_name": title or None,
        "address_name": address or None,
    }


def _compact_place_text(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def _is_usable_region_place_fallback(query: str | None, place: dict | None) -> bool:
    """Return True when a zero-result region query can safely use Kakao place coordinates.

    Region fallback exists for domestic aliases/landmarks such as "광교" or "강남구청".
    Kakao also returns business POIs for unsupported/out-of-country names like "평양"
    ("평양주유소") or "베이징" ("베이징반점"). Those must not become store-search
    coordinates unless the user explicitly used the place-query path.
    """
    query_text = (query or "").strip()
    if not query_text:
        return False
    query_key = _compact_place_text(query_text)
    if _FOREIGN_REGION_QUERY_RE.fullmatch(query_key):
        return False

    title = _place_title(place)
    address = _place_address(place)
    if not title or not address or _KOREA_ADDRESS_PREFIX_RE.search(address) is None:
        return False

    title_key = _compact_place_text(title)
    address_key = _compact_place_text(address)
    if query_key in address_key:
        return True
    if title_key == query_key:
        return True
    if _LANDMARK_REGION_SUFFIX_RE.search(query_text):
        return query_key in title_key
    if query_key in title_key and _BUSINESS_PLACE_SUFFIX_RE.search(title):
        return False
    return False


@tool_cache(ttl=1800)
def _get_store_list_cached(
    region_code: str | None = None,
    store_nm: str | None = None,
    limit: int = 10,
    svc_codes: List[str] | None = None,
    all_my_t_only: bool = False,
    imported_car_only: bool = False,
    chl_sct_cd: str | None = None,
    sort_by: str | None = None,
) -> dict:
    """Internal cached BE call. Validation runs in `get_store_list_tool` after this returns."""
    logger.debug(
        "[TOOL][_get_store_list_cached] Called with: region_code=%s, store_nm=%s (normalized), limit=%s, "
        "svc_codes=%s, all_my_t_only=%s, imported_car_only=%s, chl_sct_cd=%s, sort_by=%s",
        region_code, store_nm, limit, svc_codes, all_my_t_only, imported_car_only, chl_sct_cd, sort_by,
    )
    try:
        response = get_store_list(
            client=get_client(),
            region_code=region_code,
            store_nm=store_nm,
            limit=limit,
            svc_codes=svc_codes,
            all_my_t_only=all_my_t_only,
            imported_car_only=imported_car_only,
            chl_sct_cd=chl_sct_cd,
            sort_by=sort_by,
        )
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get store list"
            )
        data = _to_dict(response.parsed)
        return _success_response(response.status_code, data)
    except Exception as e:
        logger.exception("[TOOL][_get_store_list_cached] Failed")
        return _error_response(None, str(e), "Failed to get store list")


@tool
def get_store_list_tool(
    region_code: str | None = None,
    store_nm: str | None = None,
    limit: int = 10,
    svc_codes: List[str] | None = None,
    all_my_t_only: bool = False,
    imported_car_only: bool = False,
    chl_sct_cd: str | None = None,
    sort_by: str | None = None,
):
    """
    Get store list by region and/or store name.

    Parameter rules:
    - region_code: geographic location only (e.g., '서울', '강남', '부산').
    - store_nm: business name only (e.g., '티스테', '극동상사').
    - Pass BOTH when user mentions location AND store name simultaneously.

    Filter flags:
    - all_my_t_only=True: "all my T"/"올마이티"/"올마이T" 표현 시. 결과에 is_all_my_t 포함, True면 "[all my T]" 표시.
    - imported_car_only=True: "수입차 특화점/전문매장/전문점/매장, 외제차 특화점/전문매장" 표현 시. True면 "[수입차 특화점]" 표시.
    - chl_sct_cd: "티스테이션/t'station/티스테" → "F", "더타이어샵/the tire shop/타이어샵" → "S", None=전체.
    - svc_codes: 매장 보유 서비스 코드 (OR 필터 + 응답에 동일 필드 노출). 아래 코드 매핑 참고.
    - sort_by: 정렬 기준. None=좌표 있으면 거리순, 없으면 SHOP_ID 순(default).
        "rating"=평점순(친절/평점/별점/추천 표현), "review_count"=리뷰 많은 순(리뷰·후기 많은 표현).

    Store fields: is_installable (온라인 장착 가능), is_imported_car (수입차 특화점),
    svc_codes (매장이 보유한 서비스 코드 리스트, 예: ["113","121","124"]).

    Args:
        region_code (str | None): 지역명 키워드 (e.g., '서울', '강남', '부산').
        store_nm (str | None): 매장명 키워드 (e.g., '티스테', '극동상사').
        limit (int): 최대 반환 매장 수 (default 10). 사용자가 "N개" 명시 시 그 값 전달.
        svc_codes (List[str] | None): 매장 서비스 필터 (OR 조건: 하나라도 보유한 매장 반환).
            응답의 svc_codes 필드와 동일 코드 체계.
            - "113": 타이어 (온라인 주문)
            - "116": 배터리 (온라인 주문)
            - "119": 타이어 보관서비스 (윈터타이어 주문 시 113과 함께 필요)
            - "120": 수입타이어 취급 (수입차 특화점은 imported_car_only 별도 사용)
            - "121": 경정비 - 온라인 (엔진오일세트/와이퍼/실내필터 등 배터리 외 경정비)
            - "122": 경정비 - 오늘장착 (당일 경정비)
            - "124": 휠얼라이먼트 - 오프라인
            - "125": 휠얼라이먼트 - 온라인
            - "126": 무상점검
            예: 엔진오일 가능 매장 = ["121"], 휠얼라이먼트 가능 매장 = ["124","125"]
        all_my_t_only (bool): True → all my T 매장만. Default False.
        imported_car_only (bool): True → 수입차 특화점만. Default False.
        chl_sct_cd (str | None): F=티스테이션, S=더타이어샵, None=전체.
        sort_by (str | None): None(default) / "rating" / "review_count" / "distance"(좌표 필수).

    Examples:
        - {"region_code": "강남", "store_nm": "티스테", "limit": 5}
        - {"region_code": "서울", "limit": 5}
        - {"region_code": None, "store_nm": "극동상사", "limit": 5}
        - {"region_code": "강남", "limit": 5, "imported_car_only": True}
        - {"region_code": "강남", "svc_codes": ["121"], "limit": 5}  # 강남에서 경정비 가능
        - {"store_nm": "광교신도시", "svc_codes": ["121"]}  # 광교신도시점이 경정비 가능한지 확인
        - {"region_code": "강남", "sort_by": "rating", "limit": 5}  # 강남에서 평점 좋은 매장
        - {"region_code": "서울", "sort_by": "review_count"}  # 서울에서 리뷰 많은 매장
    """
    if store_nm:
        store_nm = normalize_brand_name(store_nm)

    result = _get_store_list_cached(
        region_code=region_code,
        store_nm=store_nm,
        limit=limit,
        svc_codes=svc_codes,
        all_my_t_only=all_my_t_only,
        imported_car_only=imported_car_only,
        chl_sct_cd=chl_sct_cd,
        sort_by=sort_by,
    )

    if store_nm and isinstance(result, dict) and result.get("status") == "success":
        data = result.get("data") or {}
        stores = data.get("stores", []) if isinstance(data, dict) else []
        validation_override = _validate_store_nm_exact_match(user_input=store_nm, stores=stores)
        if validation_override is not None:
            logger.info(
                "[TOOL][get_store_list_tool] store_nm validation override: status=%s, user_input=%s",
                validation_override.get("status"), store_nm,
            )
            return validation_override
    return result


@tool
@tool_cache(ttl=300)
def search_stores_tool(
    place_query: str | None = None,
    region_code: str | None = None,
    store_nm: str | None = None,
    xpos: float | None = None,
    ypos: float | None = None,
    radius_km: float = 20.0,
    candidate_limit: int = 20,
    limit: int = 10,
    svc_codes: List[str] | None = None,
    all_my_t_only: bool = False,
    imported_car_only: bool = False,
    chl_sct_cd: str | None = None,
    sort_by: str | None = None,
):
    """
    통합 매장 검색 v1. 장소명/좌표/지역명/매장명 검색을 한 번에 처리합니다.

    v1 scope:
    - place_query가 있으면 장소 검색으로 좌표를 얻은 뒤 주변 매장을 조회합니다.
    - xpos/ypos가 있으면 좌표 기반 주변 매장을 조회합니다.
    - 그 외에는 region_code/store_nm 기반 매장 목록을 조회합니다.
    - 날짜/요일 영업 여부, 예약 슬롯, 재고 확인은 하지 않습니다. 해당 확인은
      get_store_install_availability_tool 을 후속 호출하세요.

    Args:
        place_query (str | None): 랜드마크/장소명 (예: "남산타워", "강남역").
        region_code (str | None): 지역명 키워드 (예: "인천", "강릉").
        store_nm (str | None): 매장명 키워드 (예: "안양점").
        xpos/ypos (float | None): 직접 전달된 좌표.
        radius_km (float): 좌표 검색 반경 km.
        candidate_limit (int): 내부 후보 조회 수 (1-30). 조건 적용 후 limit로 잘라 반환.
        limit (int): 최종 반환 매장 수 (1-10). 사용자가 "N개"를 말하면 이 값에 반영.
        svc_codes/all_my_t_only/imported_car_only/chl_sct_cd/sort_by: get_store_list_tool과 동일 필터.

    Example: {"place_query": "남산타워", "limit": 5, "svc_codes": ["126"]}
    """
    final_limit = _clamp_int(limit, default=10, minimum=1, maximum=10)
    candidate_cap = _clamp_int(candidate_limit, default=max(20, final_limit), minimum=final_limit, maximum=30)
    normalized_store_nm = normalize_brand_name(store_nm) if store_nm else None

    logger.debug(
        "[TOOL][search_stores_tool] Called with: place_query=%s, region_code=%s, store_nm=%s, "
        "xpos=%s, ypos=%s, radius_km=%s, candidate_limit=%s, limit=%s, svc_codes=%s, "
        "all_my_t_only=%s, imported_car_only=%s, chl_sct_cd=%s, sort_by=%s",
        place_query, region_code, normalized_store_nm, xpos, ypos, radius_km, candidate_cap, final_limit,
        svc_codes, all_my_t_only, imported_car_only, chl_sct_cd, sort_by,
    )

    try:
        search_meta: dict[str, Any] = {
            "source": "list",
            "filters": {
                "svc_codes": svc_codes,
                "all_my_t_only": all_my_t_only,
                "imported_car_only": imported_car_only,
                "chl_sct_cd": chl_sct_cd,
                "sort_by": sort_by,
            },
            "requested_limit": final_limit,
            "candidate_limit": candidate_cap,
        }
        region_place_override_query = (
            _region_coordinate_search_override(region_code)
            if region_code and not normalized_store_nm and not place_query and xpos is None and ypos is None
            else None
        )

        if place_query:
            place_response = search_place(client=get_client(), query=place_query, size=1)
            if place_response.parsed is None:
                return _error_response(
                    place_response.status_code,
                    f"HTTP {place_response.status_code}",
                    place_response.content.decode(errors="ignore") or "Failed to search place",
                )
            place_data = _to_dict(place_response.parsed)
            found_xpos, found_ypos, place = _first_place_coordinates(place_data if isinstance(place_data, dict) else {})
            if found_xpos is None or found_ypos is None:
                return _success_response(
                    place_response.status_code,
                    {"stores": [], "search": {**search_meta, "source": "place", "place_query": place_query}},
                )
            xpos, ypos = found_xpos, found_ypos
            search_meta.update({
                "source": "place",
                "place_query": place_query,
                "place": _place_meta(place),
            })
        elif region_place_override_query:
            place_response = search_place(client=get_client(), query=region_place_override_query, size=1)
            if place_response.parsed is None:
                return _error_response(
                    place_response.status_code,
                    f"HTTP {place_response.status_code}",
                    place_response.content.decode(errors="ignore") or "Failed to search place",
                )
            place_data = _to_dict(place_response.parsed)
            found_xpos, found_ypos, place = _first_place_coordinates(place_data if isinstance(place_data, dict) else {})
            if found_xpos is None or found_ypos is None:
                return _success_response(
                    place_response.status_code,
                    {
                        "stores": [],
                        "search": {
                            **search_meta,
                            "source": "region_place_override",
                            "region_code": region_code,
                            "place_query": region_place_override_query,
                        },
                    },
                )
            xpos, ypos = found_xpos, found_ypos
            search_meta.update({
                "source": "region_place_override",
                "region_code": region_code,
                "place_query": region_place_override_query,
                "place": _place_meta(place),
            })

        if xpos is not None and ypos is not None:
            response = get_store_list(
                client=get_client(),
                xpos=xpos,
                ypos=ypos,
                radius_km=radius_km,
                svc_codes=svc_codes,
                all_my_t_only=all_my_t_only,
                imported_car_only=imported_car_only,
                chl_sct_cd=chl_sct_cd,
                sort_by=sort_by,
                limit=candidate_cap,
            )
            source_status = response.status_code
            if response.parsed is None:
                return _error_response(
                    response.status_code,
                    f"HTTP {response.status_code}",
                    response.content.decode(errors="ignore") or "Failed to search stores",
                )
            data = _to_dict(response.parsed)
            search_meta.setdefault("source", "coords")
            if search_meta.get("source") == "list":
                search_meta["source"] = "coords"
        else:
            result = _get_store_list_cached(
                region_code=region_code,
                store_nm=normalized_store_nm,
                limit=candidate_cap,
                svc_codes=svc_codes,
                all_my_t_only=all_my_t_only,
                imported_car_only=imported_car_only,
                chl_sct_cd=chl_sct_cd,
                sort_by=sort_by,
            )
            if normalized_store_nm and isinstance(result, dict) and result.get("status") == "success":
                raw_data = result.get("data") or {}
                stores_for_validation = raw_data.get("stores", []) if isinstance(raw_data, dict) else []
                validation_override = _validate_store_nm_exact_match(
                    user_input=normalized_store_nm,
                    stores=stores_for_validation,
                )
                if validation_override is not None:
                    logger.info(
                        "[TOOL][search_stores_tool] store_nm validation override: status=%s, user_input=%s",
                        validation_override.get("status"), normalized_store_nm,
                    )
                    return validation_override
            if not isinstance(result, dict) or result.get("status") != "success":
                return result
            source_status = result.get("http_status") or 200
            data = result.get("data") or {}
            stores = data.get("stores") if isinstance(data, dict) else None
            if (
                isinstance(stores, list)
                and not stores
                and region_code
                and not normalized_store_nm
                and not place_query
            ):
                domestic_decision = decide_domestic_search_area(region_code)
                if not domestic_decision.is_domestic_search_area:
                    search_meta.update({
                        "source": "region_place_fallback_blocked",
                        "region_code": region_code,
                        "reason": "not_domestic_search_area",
                        "gate": domestic_decision.model_dump(),
                    })
                else:
                    place_response = search_place(client=get_client(), query=region_code, size=1)
                    if place_response.parsed is not None:
                        place_data = _to_dict(place_response.parsed)
                        found_xpos, found_ypos, place = _first_place_coordinates(
                            place_data if isinstance(place_data, dict) else {}
                        )
                        if (
                            found_xpos is not None
                            and found_ypos is not None
                            and _is_usable_region_place_fallback(region_code, place)
                        ):
                            response = get_store_list(
                                client=get_client(),
                                xpos=found_xpos,
                                ypos=found_ypos,
                                radius_km=radius_km,
                                svc_codes=svc_codes,
                                all_my_t_only=all_my_t_only,
                                imported_car_only=imported_car_only,
                                chl_sct_cd=chl_sct_cd,
                                sort_by=sort_by,
                                limit=candidate_cap,
                            )
                            if response.parsed is None:
                                return _error_response(
                                    response.status_code,
                                    f"HTTP {response.status_code}",
                                    response.content.decode(errors="ignore") or "Failed to search stores",
                                )
                            source_status = response.status_code
                            data = _to_dict(response.parsed)
                            search_meta.update({
                                "source": "region_place_fallback",
                                "region_code": region_code,
                                "place": _place_meta(place),
                                "gate": domestic_decision.model_dump(),
                            })
                        elif found_xpos is not None and found_ypos is not None:
                            search_meta.update({
                                "source": "region_place_fallback_blocked",
                                "region_code": region_code,
                                "place": _place_meta(place),
                                "reason": "place_result_not_region_or_domestic_landmark",
                                "gate": domestic_decision.model_dump(),
                            })

        if not isinstance(data, dict):
            return _success_response(source_status, data)

        stores = data.get("stores")
        if isinstance(stores, list):
            candidate_stores = [s for s in stores if isinstance(s, dict)]
            if _should_apply_preferred_region_address_filter(
                region_code=region_code,
                store_nm=normalized_store_nm,
                place_query=place_query,
                xpos=xpos,
                ypos=ypos,
                source=search_meta.get("source"),
            ):
                candidate_stores = _filter_stores_by_preferred_region_address(region_code, candidate_stores)
            sorted_stores = _sort_store_candidates(candidate_stores, sort_by)
            data["stores"] = sorted_stores[:final_limit]
            search_meta["candidate_count"] = len(candidate_stores)
            search_meta["returned_count"] = len(data["stores"])
            data["search"] = search_meta
        return _success_response(source_status, data)
    except Exception as e:
        logger.exception("[TOOL][search_stores_tool] Failed")
        return _error_response(None, str(e), "Failed to search stores")


def _next_cal_days(days: int = 3) -> list[str]:
    today = datetime.now()
    return [(today + timedelta(days=delta)).strftime("%Y%m%d") for delta in range(max(days, 0))]


def _slot_hour(slot: object) -> int | None:
    if isinstance(slot, int):
        return slot
    if isinstance(slot, str):
        raw = slot.strip()
        if not raw:
            return None
        head = raw.split(":", 1)[0]
        if head.isdigit():
            return int(head[:2]) if len(head) == 4 else int(head)
    if isinstance(slot, dict):
        return _slot_hour(slot.get("tm"))
    return None


def _store_address(store: dict) -> str:
    road_full = " ".join(filter(None, [store.get("road_addr_base"), store.get("road_addr_dtl")])).strip()
    jibun_full = " ".join(filter(None, [store.get("addr_base"), store.get("addr_dtl")])).strip()
    return road_full or jibun_full


def _first_qualifying_slot(slots: list, threshold_hour: int) -> tuple[str, list]:
    by_day: dict[str, list] = {}
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        cal_day = str(slot.get("cal_day") or "").strip()
        hour = _slot_hour(slot)
        if not cal_day or hour is None or hour < threshold_hour:
            continue
        by_day.setdefault(cal_day, []).append(slot.get("tm") or f"{hour:02d}00")
    if not by_day:
        return "", []
    cal_day = sorted(by_day.keys())[0]
    qualifying = sorted(by_day[cal_day], key=lambda value: (_slot_hour(value) is None, _slot_hour(value) or 99))
    return cal_day, qualifying


@tool
@tool_cache(ttl=300)
def search_stores_complex_tool(
    place_query: str | None = None,
    region_code: str | None = None,
    store_nm: str | None = None,
    xpos: float | None = None,
    ypos: float | None = None,
    radius_km: float = 20.0,
    svc_codes: List[str] | None = None,
    all_my_t_only: bool = False,
    imported_car_only: bool = False,
    ev_specialty_only: bool = False,
    ev_charge_available_only: bool = False,
    installable_only: bool = False,
    chl_sct_cd: str | None = None,
    cal_days: List[str] | None = None,
    open_only: bool = False,
    time_after_hour: int | None = None,
    sort_by: str | None = None,
    limit: int = 10,
):
    """
    지역/장소/매장명 + 특화 서비스 + 특정 날짜 영업/예약 가능 조건을 한 번에 검색합니다.

    Use when the user combines store search with any of:
    - 전기차 특화점/전기차 전문 매장 → ev_specialty_only=True
    - 전기차 충전 가능 → ev_charge_available_only=True
    - 수입차 특화 → imported_car_only=True
    - 특정 날짜/요일 영업 또는 예약 가능 여부 → cal_days=["YYYYMMDD"], open_only=True
    - N시 이후 예약 가능 → time_after_hour=N, cal_days provided. 날짜가 없으면 get_stores_with_time_filter_tool 사용.

    Args:
        place_query: 랜드마크/장소명. 있으면 좌표로 변환 후 주변 검색.
        region_code: 지역명 키워드.
        store_nm: 매장명 키워드.
        xpos/ypos: 직접 전달된 좌표.
        cal_days: 조회 날짜 목록(YYYYMMDD). 여러 날짜 가능.
        open_only: True면 cal_days 기준 예약 가능 슬롯이 있는 매장만 반환.
        time_after_hour: 해당 시각 이후 슬롯만 반환. 반드시 cal_days와 함께 사용.
        limit: 최종 반환 매장 수.
    """
    final_limit = _clamp_int(limit, default=10, minimum=1, maximum=10)
    normalized_store_nm = normalize_brand_name(store_nm) if store_nm else None
    normalized_cal_days = [str(day).strip() for day in (cal_days or []) if str(day).strip()]

    logger.debug(
        "[TOOL][search_stores_complex_tool] place_query=%s, region_code=%s, store_nm=%s, xpos=%s, ypos=%s, "
        "cal_days=%s, open_only=%s, time_after_hour=%s, ev_specialty_only=%s, ev_charge_available_only=%s",
        place_query, region_code, normalized_store_nm, xpos, ypos, normalized_cal_days, open_only,
        time_after_hour, ev_specialty_only, ev_charge_available_only,
    )

    try:
        search_meta: dict[str, Any] = {
            "source": "complex",
            "requested_limit": final_limit,
            "filters": {
                "svc_codes": svc_codes,
                "all_my_t_only": all_my_t_only,
                "imported_car_only": imported_car_only,
                "ev_specialty_only": ev_specialty_only,
                "ev_charge_available_only": ev_charge_available_only,
                "installable_only": installable_only,
                "chl_sct_cd": chl_sct_cd,
                "cal_days": normalized_cal_days,
                "open_only": open_only,
                "time_after_hour": time_after_hour,
                "sort_by": sort_by,
            },
        }

        if place_query:
            place_response = search_place(client=get_client(), query=place_query, size=1)
            if place_response.parsed is None:
                return _error_response(
                    place_response.status_code,
                    f"HTTP {place_response.status_code}",
                    place_response.content.decode(errors="ignore") or "Failed to search place",
                )
            place_data = _to_dict(place_response.parsed)
            found_xpos, found_ypos, place = _first_place_coordinates(place_data if isinstance(place_data, dict) else {})
            if found_xpos is None or found_ypos is None:
                return _success_response(200, {"stores": [], "search": {**search_meta, "source": "place"}})
            xpos, ypos = found_xpos, found_ypos
            search_meta.update({"source": "place", "place_query": place_query, "place": _place_meta(place)})

        response = search_stores_complex(
            client=get_client(),
            region_code=region_code,
            store_nm=normalized_store_nm,
            xpos=xpos,
            ypos=ypos,
            radius_km=radius_km,
            svc_codes=svc_codes,
            all_my_t_only=all_my_t_only,
            imported_car_only=imported_car_only,
            ev_specialty_only=ev_specialty_only,
            ev_charge_available_only=ev_charge_available_only,
            installable_only=installable_only,
            chl_sct_cd=chl_sct_cd,
            cal_days=normalized_cal_days or None,
            open_only=open_only,
            time_after_hour=time_after_hour,
            sort_by=sort_by,
            limit=final_limit,
        )
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to search stores",
            )
        data = _to_dict(response.parsed)
        if not isinstance(data, dict):
            return _success_response(response.status_code, data)
        stores = data.get("stores")
        if isinstance(stores, list):
            data["stores"] = stores[:final_limit]
            search_meta["candidate_count"] = len(stores)
            search_meta["returned_count"] = len(data["stores"])
            data["search"] = search_meta
        return _success_response(response.status_code, data)
    except Exception as e:
        logger.exception("[TOOL][search_stores_complex_tool] Failed")
        return _error_response(None, str(e), "Failed to search stores")


@tool
def get_store_detail_tool(shop_id: str, cal_day: str, is_logistics_delivery: bool = False):
    """
    Get store details and available reservation time slots for a specific date.

    Store fields: is_installable (온라인 장착 가능), is_tna_delivery (T바로배송), is_imported_car (수입차 특화점).

    Args:
        shop_id (str): Store ID.
        cal_day (str): Query date in YYYYMMDD format.
        is_logistics_delivery (bool): True when store has NO store inventory but logistics IS available
            (Flow 3 STEP B) — backend filters slots by store-delivery lead time. Default False.

    Example: {"shop_id": "BXXXXX", "cal_day": "20260401"}
    """
    logger.debug(
        "[TOOL][get_store_detail_tool] Called with: shop_id=%s, cal_day=%s, is_logistics_delivery=%s",
        shop_id, cal_day, is_logistics_delivery,
    )

    try:
        response = get_store_detail(
            client=get_client(),
            shop_id=shop_id,
            cal_day=cal_day,
            is_logistics_delivery=is_logistics_delivery,
        )
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get store details"
            )
        # logger.debug("[TOOL][get_store_detail_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_store_detail_tool] Failed")
        return _error_response(None, str(e), "Failed to get store details")


@tool
@tool_cache(ttl=120)
def get_store_schedule_tool(shop_id: str, mode: str):
    """
    DEPRECATED: use get_store_install_availability_tool instead.

    Get reservation slots for a single store using mode-based cal_day range (single BE call).

    Deprecated compatibility tool only. New flows must call
    get_store_install_availability_tool with shop_id_list=[shop_id]. Pass goods_no=None
    for general store visit schedules.

    The backend applies a different cal_day range per mode based on inventory state.
    Choose mode AFTER inspecting get_store_inventory_tool + get_logistics_inventory_tool
    results for this shop and goods_no:

    | mode                          | When to use                                      |
    |-------------------------------|--------------------------------------------------|
    | today_only                    | 사용자가 오늘/당일 장착을 명시한 경우만         |
    | tna_only                      | shop ∈ tnaShopArray, NOT in todayShopArray       |
    | logistics_only                | 매장재고 X + 물류재고 O                          |
    | in_store_only                 | 매장재고 O + 물류재고 X (오늘 ∪ T바로배송)       |
    | in_store_logistics_combined   | 매장재고 O + 물류재고 O (오늘 ∪ T바로 ∪ 일반배송)|
    | general                       | 단순 매장 방문 (no tire context)                 |

    Args:
        shop_id (str): Store ID.
        mode (str): One of the ScheduleMode values listed above.

    Examples:
        - {"shop_id": "BXXXXX", "mode": "in_store_logistics_combined"}
        - {"shop_id": "FXXXXX", "mode": "logistics_only"}
        - {"shop_id": "BXXXXX", "mode": "general"}
    """
    logger.debug(
        "[TOOL][get_store_schedule_tool] Called with: shop_id=%s, mode=%s",
        shop_id, mode,
    )

    try:
        mode_enum = ScheduleMode(mode)
    except ValueError:
        valid = [m.value for m in ScheduleMode]
        return _error_response(None, "invalid_mode", f"mode must be one of {valid}; got {mode!r}")

    try:
        response = get_store_schedule(client=get_client(), shop_id=shop_id, mode=mode_enum)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get store schedule"
            )
        # logger.debug("[TOOL][get_store_schedule_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_store_schedule_tool] Failed")
        return _error_response(None, str(e), "Failed to get store schedule")


def _fetch_schedule_for_shops(shop_ids: list[str], mode: ScheduleMode) -> dict[str, dict]:
    """Parallel-fetch /api/store/schedule for multiple shops with the same mode.

    Returns {shop_id: parsed_dict}. Empty dict for failed shops.
    """
    results: dict[str, dict] = {sid: {} for sid in shop_ids}
    if not shop_ids:
        return results

    with ThreadPoolExecutor(max_workers=min(len(shop_ids), 9)) as executor:
        futures = {
            executor.submit(get_store_schedule, client=get_client(), shop_id=sid, mode=mode): sid
            for sid in shop_ids
        }
        for future in as_completed(futures):
            sid = futures[future]
            try:
                response = future.result()
                if response.parsed is not None:
                    results[sid] = _to_dict(response.parsed)
            except Exception:
                logger.warning("[_fetch_schedule_for_shops] Failed for shop_id=%s mode=%s", sid, mode.value)
    return results


@tool
def get_multi_store_schedule_tool(
    shop_id_list: list[str],
    today_shop_ids: list[str] | None = None,
    tna_shop_ids: list[str] | None = None,
    has_logistics: bool = False,
):
    """
    DEPRECATED: use get_store_install_availability_tool instead.

    Flow 3.5 — find earliest reservation slots across up to 3 stores using **tier cascade**.

    Deprecated compatibility tool only. New flows must call
    get_store_install_availability_tool once with the candidate shop_id_list.

    The tool selects ONE tier across the whole batch based on inventory state:

    | Tier | Trigger condition                                       | mode used      |
    |------|---------------------------------------------------------|----------------|
    | 1    | Candidate ∈ todayShopArray and has_logistics=True       | combined       |
    | 2    | Candidate ∈ todayShopArray                              | in_store_only  |
    | 3    | Tier 1–2 empty AND ≥1 candidate ∈ tnaShopArray          | tna_only       |
    | 4    | Earlier tiers empty AND has_logistics=True              | logistics_only |
    | none | All tiers empty                                         | (no BE call)   |

    `todayShopArray` means "today is available", not "show only today". For normal
    booking previews, today-capable stores use a broader schedule mode so customers
    can choose other dates too. The first non-empty tier is returned.

    Caller MUST first run get_store_inventory_tool + get_logistics_inventory_tool
    so todayShopArray/tnaShopArray/logistics_qty are known.

    Args:
        shop_id_list (list[str]): Up to 3 candidate shop IDs (extras truncated).
        today_shop_ids (list[str] | None): shop_ids in todayShopArray from get_store_inventory_tool.
        tna_shop_ids (list[str] | None): shop_ids in tnaShopArray from get_store_inventory_tool.
        has_logistics (bool): True if logistics_qty > 0 (from get_logistics_inventory_tool).

    Example:
        {
          "shop_id_list": ["BXXXXX", "FXXXXX", "CXXXXX"],
          "today_shop_ids": ["BXXXXX"],
          "tna_shop_ids": ["FXXXXX"],
          "has_logistics": true
        }
    """
    logger.debug(
        "[TOOL][get_multi_store_schedule_tool] Called with: shop_id_list=%s, "
        "today_shop_ids=%s, tna_shop_ids=%s, has_logistics=%s",
        shop_id_list, today_shop_ids, tna_shop_ids, has_logistics,
    )

    candidates = [sid for sid in (shop_id_list or []) if sid][:3]
    if not candidates:
        return _error_response(None, "invalid_input", "shop_id_list is empty")

    today_set = set(today_shop_ids or [])
    tna_set = set(tna_shop_ids or [])

    # Tier 1/2 — today-capable stores, but show a broader booking range by default.
    tier1_shops = [sid for sid in candidates if sid in today_set]
    if tier1_shops:
        mode = ScheduleMode.IN_STORE_LOGISTICS_COMBINED if has_logistics else ScheduleMode.IN_STORE_ONLY
        results = _fetch_schedule_for_shops(tier1_shops, mode)
        if any(r.get("slots") for r in results.values()):
            return _success_response(200, {
                "tier": mode.value,
                "stores": [{"shop_id": sid, **(results.get(sid) or {})} for sid in tier1_shops],
                "candidate_shop_ids": candidates,
            })

    # Tier 3 — tna_only on candidates ∩ tnaShopArray
    tier2_shops = [sid for sid in candidates if sid in tna_set]
    if tier2_shops:
        results = _fetch_schedule_for_shops(tier2_shops, ScheduleMode.TNA_ONLY)
        if any(r.get("slots") for r in results.values()):
            return _success_response(200, {
                "tier": "tna_only",
                "stores": [{"shop_id": sid, **(results.get(sid) or {})} for sid in tier2_shops],
                "candidate_shop_ids": candidates,
            })

    # Tier 4 — logistics_only on remaining candidates (not in today/tna sets)
    if has_logistics:
        tier3_shops = [sid for sid in candidates if sid not in today_set and sid not in tna_set]
        # Fall back to all candidates if filtering removed every shop
        if not tier3_shops:
            tier3_shops = list(candidates)
        results = _fetch_schedule_for_shops(tier3_shops, ScheduleMode.LOGISTICS_ONLY)
        if any(r.get("slots") for r in results.values()):
            return _success_response(200, {
                "tier": "logistics_only",
                "stores": [{"shop_id": sid, **(results.get(sid) or {})} for sid in tier3_shops],
                "candidate_shop_ids": candidates,
            })

    return _success_response(200, {
        "tier": "none",
        "stores": [],
        "candidate_shop_ids": candidates,
    })


@tool
def get_stores_with_time_filter_tool(region_code: str, time_threshold_hour: int) -> dict:
    """
    Find stores in a region with reservation slots available at or after a given hour (Flow 5.5T).

    Use this tool when the user asks for stores available "N시 이후" / "저녁 N시" / "오후 N시"
    in a region, without specifying a particular store name or goods_no.

    Uses backend complex search for today→+2 day reservation slots, then returns pre-filtered
    raw store data for the location mapper.

    Args:
        region_code (str): Region name (e.g., '인천', '부산', '강남').
        time_threshold_hour (int): 24-hour integer (0–23). Convert Korean time expressions:
            "오전 N시" / "새벽 N시" → N          (e.g., "오전 9시"  → 9)
            "오후 N시"              → 12 + N    (e.g., "오후 3시"  → 15, "오후 6시" → 18)
            "저녁 N시"              → 12 + N    (e.g., "저녁 6시"  → 18, "저녁 9시" → 21)
            "밤 N시"                → 12 + N    (e.g., "밤 10시"   → 22)
            "N시 이후" (no prefix)  → 12 + N if N ≤ 12 and evening context, else N

    Returns:
        {
            "stores_available":   [{"shop_id", "shop_nm", "address", "tel", "cal_day", "qualifying_slots"}],
            "stores_unavailable": [{"shop_id", "shop_nm", "address", "tel", "reason"}],
            "time_threshold_hour": int,
            "region_code": str,
        }
    """
    logger.debug(
        "[TOOL][get_stores_with_time_filter_tool] region_code=%s, time_threshold_hour=%s",
        region_code, time_threshold_hour,
    )

    cal_days = _next_cal_days(3)
    try:
        response = search_stores_complex(
            client=get_client(),
            region_code=region_code,
            cal_days=cal_days,
            open_only=True,
            time_after_hour=time_threshold_hour,
            limit=50,
        )
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to search stores",
            )
        data = _to_dict(response.parsed)
    except Exception as e:
        logger.exception("[TOOL][get_stores_with_time_filter_tool] complex search failed")
        return _error_response(None, str(e), "Failed to search stores")

    stores_raw = data.get("stores") if isinstance(data, dict) else []
    stores_available: list[dict] = []
    stores_unavailable: list[dict] = []
    if not isinstance(stores_raw, list):
        stores_raw = []

    for store in stores_raw:
        if not isinstance(store, dict):
            continue
        shop_id = store.get("shop_id") or store.get("shop_seq")
        slots = store.get("slots") if isinstance(store.get("slots"), list) else []
        cal_day, qualifying = _first_qualifying_slot(slots, time_threshold_hour)
        if not shop_id or not qualifying:
            stores_unavailable.append({
                "shop_id": shop_id,
                "shop_nm": store.get("shop_nm") or "",
                "address": _store_address(store),
                "tel": store.get("tel_no") or "",
                "reason": f"{time_threshold_hour}시 이후 예약 가능 슬롯 없음",
            })
            continue
        stores_available.append({
            "shop_id": shop_id,
            "shop_nm": store.get("shop_nm") or "",
            "address": _store_address(store),
            "tel": store.get("tel_no") or "",
            "cal_day": cal_day,
            "qualifying_slots": qualifying,
            "is_all_my_t": bool(store.get("is_all_my_t", False)),
            "is_tna_delivery": bool(store.get("is_tna_delivery", False)),
            "rating_idx": store.get("rating_idx"),
        })

    stores_available.sort(key=lambda row: (
        row.get("cal_day") or "99999999",
        min((_slot_hour(s) for s in row.get("qualifying_slots", []) if _slot_hour(s) is not None), default=99),
        row.get("shop_nm") or "",
    ))

    return _success_response(200, {
        "stores_available": stores_available,
        "stores_unavailable": stores_unavailable,
        "time_threshold_hour": time_threshold_hour,
        "region_code": region_code,
        "cal_days": cal_days,
    })


def _extract_stores(data: Any) -> list[dict]:
    if not isinstance(data, dict):
        return []
    stores = data.get("stores") or data.get("items") or []
    return stores if isinstance(stores, list) else []


def _shop_id(store: dict) -> str | None:
    value = store.get("shop_id") or store.get("shopId") or store.get("shop_seq") or store.get("shopSeq")
    return str(value) if value else None


_PREFERRED_REGION_ADDRESS_TOKENS = {
    "강남": ("강남구",),
}
_REGION_COORDINATE_SEARCH_OVERRIDES = {
    "강남": "강남역",
}


def _should_apply_preferred_region_address_filter(
    *,
    region_code: str | None,
    store_nm: str | None,
    place_query: str | None,
    xpos: float | None,
    ypos: float | None,
    source: str | None,
) -> bool:
    return bool(
        region_code
        and not store_nm
        and not place_query
        and xpos is None
        and ypos is None
        and str(source or "") == "list"
    )


def _region_coordinate_search_override(region_code: str | None) -> str | None:
    if not region_code:
        return None
    return _REGION_COORDINATE_SEARCH_OVERRIDES.get(region_code.strip())


def _filter_stores_by_preferred_region_address(region_code: str | None, stores: list[dict]) -> list[dict]:
    """Prefer address matches for ambiguous region terms in booking preview.

    `/api/store/list` also searches SHOP_NM for region_code to support cases
    like "광교". In order/booking preview, ambiguous terms such as "강남"
    should not pull in a remote branch whose name merely contains the token.
    """
    if not region_code or not stores:
        return stores

    tokens = _PREFERRED_REGION_ADDRESS_TOKENS.get(region_code.strip())
    if not tokens:
        return stores

    matched: list[dict] = []
    for store in stores:
        address = " ".join(
            str(store.get(key) or "")
            for key in ("addr_base", "addr_dtl", "road_addr_base", "road_addr_dtl")
        )
        if any(token in address for token in tokens):
            matched.append(store)

    return matched or stores


def _scheduled_shop_ids_with_slots(schedule_data: Any) -> list[str]:
    if not isinstance(schedule_data, dict):
        return []
    stores = schedule_data.get("stores")
    if not isinstance(stores, list):
        return []

    shop_ids: list[str] = []
    for store in stores:
        if not isinstance(store, dict):
            continue
        slots = store.get("slots")
        if not isinstance(slots, list) or not slots:
            continue
        shop_id = store.get("shop_id") or store.get("shopId")
        if shop_id:
            shop_ids.append(str(shop_id))
    return shop_ids


def _availability_items(data: Any) -> list[dict]:
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _availability_inventory_payload(data: Any) -> dict[str, list[dict[str, str]]]:
    today: list[dict[str, str]] = []
    tna: list[dict[str, str]] = []
    for item in _availability_items(data):
        shop_id = str(item.get("shop_id") or "").strip()
        if not shop_id:
            continue
        if item.get("has_today_stock"):
            today.append({"shopId": shop_id})
        if item.get("has_tna_stock"):
            tna.append({"shopId": shop_id})
    return {"todayShopArray": today, "tnaShopArray": tna}


def _availability_has_logistics(data: Any) -> bool:
    return any(bool(item.get("has_logistics_stock")) for item in _availability_items(data))


def _availability_schedule_payload(
    data: Any,
    *,
    candidate_shop_ids: list[str],
    requested_cal_day: str | None = None,
) -> dict[str, Any]:
    requested_day = str(requested_cal_day or "").strip()
    stores: list[dict[str, Any]] = []
    first_tier = ""
    for item in _availability_items(data):
        shop_id = str(item.get("shop_id") or "").strip()
        if not shop_id:
            continue
        slots = item.get("slots") if isinstance(item.get("slots"), list) else []
        if requested_day:
            slots = [
                slot
                for slot in slots
                if isinstance(slot, dict) and str(slot.get("cal_day") or "").strip() == requested_day
            ]
        if not slots:
            continue
        mode = str(item.get("mode") or "").strip()
        if not first_tier:
            first_tier = mode
        stores.append({
            "shop_id": shop_id,
            "shop_nm": item.get("shop_nm"),
            "mode": mode or None,
            "status": item.get("status"),
            "is_installable": bool(item.get("is_installable", False)),
            "is_tna_delivery": bool(item.get("is_tna_delivery", False)),
            "slots": slots,
        })

    payload: dict[str, Any] = {
        "tier": first_tier or "none",
        "stores": stores,
        "candidate_shop_ids": candidate_shop_ids,
    }
    if requested_day:
        payload["requested_cal_day"] = requested_day
    return payload


def _extract_logistics_qty(data: Any) -> int:
    if not isinstance(data, dict):
        return 0
    if data.get("has_logistics_stock") is True:
        return 1
    value = data.get("logistics_qty") or data.get("logisticsQty") or data.get("qty") or 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _extract_inventory_shop_ids(data: Any, key: str) -> list[str]:
    if not isinstance(data, dict):
        return []
    values = data.get(key) or data.get(key[0].lower() + key[1:]) or []
    if not isinstance(values, list):
        return []
    shop_ids: list[str] = []
    for item in values:
        if isinstance(item, dict):
            sid = item.get("shop_id") or item.get("shopId") or item.get("shop_seq") or item.get("shopSeq")
        else:
            sid = item
        if sid:
            shop_ids.append(str(sid))
    return shop_ids


def _filter_reservation_sale_schedule(schedule_data: Any, preview_payload: dict[str, Any]) -> Any:
    if not isinstance(schedule_data, dict):
        return schedule_data
    stores = schedule_data.get("stores")
    if not isinstance(stores, list):
        return schedule_data

    filtered_stores: list[Any] = []
    changed = False
    for store in stores:
        if not isinstance(store, dict):
            filtered_stores.append(store)
            continue
        shop_id = str(store.get("shop_id") or store.get("shopId") or "").strip()
        slots = store.get("slots")
        min_install_date = reservation_sale_min_install_date(preview_payload, shop_id)
        if not shop_id or not min_install_date or not isinstance(slots, list):
            filtered_stores.append(store)
            continue

        filtered_slots = [
            slot
            for slot in slots
            if isinstance(slot, dict) and str(slot.get("cal_day") or "").strip() >= min_install_date
        ]
        changed = changed or len(filtered_slots) != len(slots)
        if filtered_slots:
            filtered_stores.append({**store, "slots": filtered_slots})
        else:
            changed = True

    if not changed:
        return schedule_data

    filtered_schedule = {**schedule_data, "stores": filtered_stores}
    if not filtered_stores:
        filtered_schedule["tier"] = "none"
    return filtered_schedule


def _filter_schedule_by_cal_day(schedule_data: Any, requested_cal_day: str | None) -> Any:
    cal_day = str(requested_cal_day or "").strip()
    if not cal_day or not isinstance(schedule_data, dict):
        return schedule_data
    stores = schedule_data.get("stores")
    if not isinstance(stores, list):
        return schedule_data

    filtered_stores: list[Any] = []
    changed = False
    for store in stores:
        if not isinstance(store, dict):
            changed = True
            continue
        slots = store.get("slots")
        if not isinstance(slots, list):
            changed = True
            continue
        filtered_slots = [
            slot
            for slot in slots
            if isinstance(slot, dict) and str(slot.get("cal_day") or "").strip() == cal_day
        ]
        changed = changed or len(filtered_slots) != len(slots)
        if filtered_slots:
            filtered_stores.append({**store, "slots": filtered_slots})
        else:
            changed = True

    if not changed:
        return schedule_data

    filtered_schedule = {**schedule_data, "stores": filtered_stores, "requested_cal_day": cal_day}
    if not filtered_stores:
        filtered_schedule["tier"] = "none"
    return filtered_schedule


@tool
@tool_cache(ttl=120)
def transaction_store_preview_tool(
    goods_no: str,
    ord_qty: int,
    region_code: str | None = None,
    store_nm: str | None = None,
    user_xpos: float | None = None,
    user_ypos: float | None = None,
    radius_km: float | None = None,
    exclude_shop_ids: List[str] | None = None,
    stock_check_mode: str | None = None,
    include_price: bool = True,
    svc_codes: List[str] | None = None,
    all_my_t_only: bool = False,
    imported_car_only: bool = False,
    chl_sct_cd: str | None = None,
    requested_cal_day: str | None = None,
):
    """
    Composite preview for purchase/store flow: store candidates + price + stock + earliest schedule.

    Use when goods_no and quantity are known and the user wants nearby/regional stores,
    stock, or available reservation dates. This is a preview only; never creates an order.
    """
    policy_patch = current_transaction_store_preview_tool_patch.get()
    if policy_patch:
        before_policy = {
            "goods_no": goods_no,
            "ord_qty": ord_qty,
            "region_code": region_code,
            "store_nm": store_nm,
            "user_xpos": user_xpos,
            "user_ypos": user_ypos,
            "radius_km": radius_km,
            "requested_cal_day": requested_cal_day,
        }
        goods_no, ord_qty, region_code, store_nm, user_xpos, user_ypos = _apply_store_preview_policy_patch(
            patch=policy_patch,
            goods_no=goods_no,
            ord_qty=ord_qty,
            region_code=region_code,
            store_nm=store_nm,
            user_xpos=user_xpos,
            user_ypos=user_ypos,
        )
        if not requested_cal_day and policy_patch.get("requested_cal_day"):
            requested_cal_day = str(policy_patch["requested_cal_day"])
        logger.info(
            "[TOOL][transaction_store_preview_tool] Applied transaction policy patch=%s before=%s after=%s",
            policy_patch,
            before_policy,
            {
                "goods_no": goods_no,
                "ord_qty": ord_qty,
                "region_code": region_code,
                "store_nm": store_nm,
                "user_xpos": user_xpos,
                "user_ypos": user_ypos,
                "radius_km": radius_km,
                "requested_cal_day": requested_cal_day,
            },
        )

    logger.debug(
        "[TOOL][transaction_store_preview_tool] Called with: goods_no=%s, ord_qty=%s, region_code=%s, "
        "store_nm=%s, user_xpos=%s, user_ypos=%s, radius_km=%s, include_price=%s, stock_check_mode=%s",
        goods_no, ord_qty, region_code, store_nm, user_xpos, user_ypos, radius_km, include_price, stock_check_mode,
    )

    if not goods_no or ord_qty is None or ord_qty < 1:
        return _error_response(None, "invalid_input", "goods_no and ord_qty are required")

    has_region = bool(region_code and region_code.strip())
    has_store = bool(store_nm and store_nm.strip())
    has_coords = user_xpos is not None and user_ypos is not None
    if not (has_region or has_store or has_coords):
        return _error_response(
            None,
            "missing_location_filter",
            "region_code, store_nm, or user_xpos/user_ypos is required — "
            "ask the user for a region/store/landmark before calling this tool",
        )

    if store_nm:
        store_nm = normalize_brand_name(store_nm)
    effective_radius_km = float(radius_km or 10.0)

    if user_xpos is not None and user_ypos is not None:
        store_response = get_store_list(
            client=get_client(),
            xpos=user_xpos,
            ypos=user_ypos,
            radius_km=effective_radius_km,
            svc_codes=svc_codes,
            all_my_t_only=all_my_t_only,
            imported_car_only=imported_car_only,
            installable_only=True,
            chl_sct_cd=chl_sct_cd,
        )
    else:
        store_response = get_store_list(
            client=get_client(),
            region_code=region_code,
            store_nm=store_nm,
            limit=10,
            svc_codes=svc_codes,
            all_my_t_only=all_my_t_only,
            imported_car_only=imported_car_only,
            installable_only=True,
            chl_sct_cd=chl_sct_cd,
        )

    if store_response.parsed is None:
        return _error_response(
            store_response.status_code,
            f"HTTP {store_response.status_code}",
            store_response.content.decode(errors="ignore") or "Failed to get store candidates",
        )

    store_data = _to_dict(store_response.parsed)
    stores = _extract_stores(store_data)
    place_fallback: dict[str, Any] | None = None
    if has_region and not has_store and not has_coords and not stores:
        domestic_decision = decide_domestic_search_area(region_code)
        if not domestic_decision.is_domestic_search_area:
            place_fallback = {
                "source": "place_fallback_blocked",
                "query": region_code.strip(),
                "reason": "not_domestic_search_area",
                "gate": domestic_decision.model_dump(),
            }
        else:
            place_response = search_place(client=get_client(), query=region_code.strip(), size=1)
            if place_response.parsed is not None:
                place_data = _to_dict(place_response.parsed)
                found_xpos, found_ypos, place = _first_place_coordinates(
                    place_data if isinstance(place_data, dict) else {}
                )
                if (
                    found_xpos is not None
                    and found_ypos is not None
                    and _is_usable_region_place_fallback(region_code, place)
                ):
                    store_response = get_store_list(
                        client=get_client(),
                        xpos=found_xpos,
                        ypos=found_ypos,
                        radius_km=effective_radius_km,
                        svc_codes=svc_codes,
                        all_my_t_only=all_my_t_only,
                        imported_car_only=imported_car_only,
                        installable_only=True,
                        chl_sct_cd=chl_sct_cd,
                    )
                    if store_response.parsed is None:
                        return _error_response(
                            store_response.status_code,
                            f"HTTP {store_response.status_code}",
                            store_response.content.decode(errors="ignore") or "Failed to get nearby store candidates",
                        )
                    store_data = _to_dict(store_response.parsed)
                    stores = _extract_stores(store_data)
                    place_fallback = {
                        "source": "place_fallback",
                        "query": region_code.strip(),
                        "place": _place_meta(place),
                        "gate": domestic_decision.model_dump(),
                    }
                elif found_xpos is not None and found_ypos is not None:
                    place_fallback = {
                        "source": "place_fallback_blocked",
                        "query": region_code.strip(),
                        "place": _place_meta(place),
                        "reason": "place_result_not_region_or_domestic_landmark",
                        "gate": domestic_decision.model_dump(),
                    }
    if has_region and not has_store and not has_coords and place_fallback is None:
        stores = _filter_stores_by_preferred_region_address(region_code, stores)
    excluded_shop_ids = {str(shop_id).strip() for shop_id in (exclude_shop_ids or []) if str(shop_id).strip()}
    if excluded_shop_ids:
        stores = [store for store in stores if _shop_id(store) not in excluded_shop_ids]

    # store_nm 으로 검색했는데 결과가 0건/exact 분점명 미일치인 경우 결정적 guard 적용.
    # 이게 없으면 LLM 이 silent "No store candidates found" 만 받고 generic 응답을
    # 생성하거나 다른 도구를 fan-out 한다 (예: "분당판교점" 같은 복합 지역명 오입력).
    if store_nm:
        validation_override = _validate_store_nm_exact_match(user_input=store_nm, stores=stores)
        if validation_override is not None:
            logger.info(
                "[TOOL][transaction_store_preview_tool] store_nm validation override: status=%s, user_input=%s",
                validation_override.get("status"), store_nm,
            )
            payload = dict(validation_override.get("data") or {})
            payload.setdefault("price", None)
            payload.setdefault("logistics", None)
            payload.setdefault("inventory", None)
            payload.setdefault("schedule", None)
            return _success_response(
                validation_override.get("http_status", 200),
                payload,
            )

    candidates = sorted(
        stores,
        key=lambda s: (
            not bool(s.get("is_installable", False)),
            s.get("distance_km") if isinstance(s.get("distance_km"), (int, float)) else float("inf"),
        ),
    )[:3]
    shop_ids = [sid for store in candidates if (sid := _shop_id(store))]
    if not shop_ids:
        empty_data = {
            "stores": [],
            "message": "No store candidates found",
            "price": None,
            "logistics": None,
            "inventory": None,
            "schedule": None,
        }
        if place_fallback is not None:
            empty_data["search"] = place_fallback
        return _success_response(store_response.status_code, empty_data)

    be_client = get_client()

    def _fetch_availability():
        body = StoreInstallAvailabilityRequest(shop_ids=shop_ids, goods_no=goods_no, qty=ord_qty)
        return get_store_install_availability(client=be_client, body=body)

    def _fetch_price():
        return get_price(client=be_client, goods_no=goods_no, member_type=None)

    tasks = {"availability": _fetch_availability}
    if include_price:
        tasks["price"] = _fetch_price

    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            response = future.result()
            if response.status_code >= 400:
                logger.warning(
                    "[TOOL][transaction_store_preview_tool] %s sub-call failed: status=%s body=%s",
                    name,
                    response.status_code,
                    response.content.decode(errors="ignore")[:300],
                )
            results[name] = _to_dict(response.parsed) if response.parsed is not None else None

    availability_data = results.get("availability") if isinstance(results.get("availability"), dict) else {}
    inventory_data = _availability_inventory_payload(availability_data)
    logistics_data = {"has_logistics_stock": _availability_has_logistics(availability_data)}
    schedule_data = _availability_schedule_payload(
        availability_data,
        candidate_shop_ids=shop_ids,
        requested_cal_day=requested_cal_day,
    )
    scheduled_shop_ids = _scheduled_shop_ids_with_slots(schedule_data)
    if requested_cal_day:
        scheduled_set = set(scheduled_shop_ids)
        candidates = [store for store in candidates if (_shop_id(store) in scheduled_set)]
        shop_ids = [sid for sid in shop_ids if sid in scheduled_set]
    elif scheduled_shop_ids:
        scheduled_set = set(scheduled_shop_ids)
        candidates = [store for store in candidates if (_shop_id(store) in scheduled_set)]
        shop_ids = [sid for sid in shop_ids if sid in scheduled_set]

    result_data: dict[str, Any] = {
        "price": results.get("price"),
        "logistics": logistics_data,
        "inventory": inventory_data,
        "availability": availability_data,
        "schedule": schedule_data,
        "stores": [{"shop_id": _shop_id(store), **store} for store in candidates],
        "candidate_shop_ids": shop_ids,
    }
    if requested_cal_day:
        result_data["requested_cal_day"] = str(requested_cal_day)
    if place_fallback is not None:
        result_data["search"] = place_fallback
    result_data["schedule"] = _filter_reservation_sale_schedule(result_data["schedule"], result_data)

    schedule_data = result_data["schedule"] if isinstance(result_data["schedule"], dict) else {}
    tier = schedule_data.get("tier")
    is_single_named_store = bool(store_nm) and len(shop_ids) == 1
    if tier == "none" and shop_ids:
        if is_single_named_store:
            # 사용자가 특정 매장명(예: "판교점") 으로 검색해 단일 매장만 매칭된 경우 —
            # 매장 확정 상태로 간주. tier="none" 은 빠른 슬롯(오늘/T바로배송) cascade 결과일
            # 뿐, 일반 예약 슬롯은 정상 존재 가능. agent 가 location 카드로 다시 매장 선택을
            # 요청하면 사용자에게 무한 루프로 보임 — 즉시 schedule 도구 체이닝 강제.
            result_data["instruction_to_agent"] = (
                f"DETERMINISTIC GUARD: 사용자가 특정 매장명(`{store_nm}`)으로 검색해 단일 매장만 "
                "매칭됨 — 사용자가 이미 매장을 확정한 상태. 다음 액션을 즉시 수행: "
                "(1) get_store_install_availability_tool(shop_id_list=[candidate_shop_ids[0]], goods_no=None) 호출, "
                "(2) 응답으로 datepick 템플릿 emit. "
                "⛔ 금지: location 카드 emit, \"원하시는 매장을 선택해 주세요\" / "
                "\"주문 가능한 매장을 확인했어요\" 류 quickReply emit, fallback chip "
                "(\"1:1 문의하기\"/\"처음으로\") 으로 종료, schedule 도구 호출 누락. "
                "사용자는 이미 단일 매장을 지정했으므로 매장 재선택 요청 절대 금지."
            )
        else:
            result_data["instruction_to_agent"] = (
                "DETERMINISTIC GUARD: 사용자가 매장을 아직 선택하지 않았음 — "
                "자동으로 candidate_shop_ids[0] 를 픽해서 get_store_install_availability_tool / "
                "get_store_detail_tool 등 후속 도구를 호출하거나 "
                "datepick 을 emit 하면 절대 안 됨. 다음 액션: "
                "(1) 'stores' 리스트로 `location` 템플릿 emit, "
                "(2) assistantResponse 는 **사용자의 직전 발화 의도** 와 **검색 경로** 에 맞춰 작성: "
                "[A] 사용자가 '오늘 장착', '당일 장착', '지금 장착' 등 오늘/당일 장착 의도 명시 시 → "
                "\"오늘 바로 장착 가능한 매장은 없지만, 일반 예약 가능한 매장 목록입니다. 원하시는 매장을 선택해 주세요 😊\". "
                "[B] 그 외 (지역명/매장명/근처 등만 언급) — region 검색(region_code 사용)이면 "
                "\"주소에 '[지역]'이/가 포함된 매장을 검색했어요. 원하시는 매장을 선택해 주세요 😊\" "
                "(받침 있으면 '이', 없으면 '가'), 좌표 기반이면 "
                "\"고객님, [명칭] 주변 매장을 검색했어요. 원하시는 매장을 선택해 주세요 😊\". "
                "(3) 동일 턴에 schedule/inventory/detail 도구 호출 금지, "
                "(4) STOP and wait for user to pick a store. "
                "⚠️ 케이스 [B] 에서 \"오늘 장착 가능한 매장이 없어요\" 류 문구는 거짓이 될 수 있으므로 절대 사용 금지 — "
                "각 매장의 일반 예약 슬롯은 정상 존재할 수 있음 (schedule.tier 는 빠른 슬롯 cascade 결과일 뿐)."
            )

    return _success_response(200, result_data)


# =====================================================
# ORDER TOOLS
# =====================================================

@tool
def present_order_preview_tool(
    goods_no: str,
    ord_qty: int,
    shop_id: str | None = None,
    shop_name: str | None = None,
    requested_cal_day: str | None = None,
    rsv_hour: str | None = None,
    payment_amount: int | None = None,
    product_name: str | None = None,
    tire_size: str | None = None,
    car_no: str | None = None,
    car_lnc_cd: str | None = None,
    is_ready_to_add_to_cart: bool = False,
):
    """확정된 주문 내용을 사용자에게 최종 확인용 카드(preOrder)로 보여줄 때 호출.

    ⚠️ 실제 주문을 생성하지 않는다 (preview 전용). 주문 실행은 사용자가 확인한 뒤 quick_order_tool 로 한다.
    주문(place_order): goods_no·수량·매장·희망일정·결제금액이 모두 확정된 뒤에만 호출.
    장바구니(add_to_cart): goods_no·수량만 확정되면 호출하고 is_ready_to_add_to_cart=True 로 설정.
    값은 이전 도구 결과/대화에서 확정된 것만 넣고 지어내지 말 것.
    product_name·tire_size 는 이전 도구 결과에 있으면 반드시 함께 전달하라 — 카드의 구매상품 표시에
    사용되며, 없으면 상품명 없이 카드가 노출된다 (내부 상품코드 goods_no 는 절대 표시되지 않는다).
    """
    return {
        "status": "ok",
        "goods_no": goods_no,
        "ord_qty": ord_qty,
        "shop_id": shop_id,
        "shop_name": shop_name,
        "requested_cal_day": requested_cal_day,
        "rsv_hour": rsv_hour,
        "payment_amount": payment_amount,
        "product_name": product_name,
        "tire_size": tire_size,
        "car_no": car_no,
        "car_lnc_cd": car_lnc_cd,
        "is_ready_to_add_to_cart": bool(is_ready_to_add_to_cart),
        "is_ready_to_order": not bool(is_ready_to_add_to_cart),
    }


@tool
def save_to_cart_tool(goods_no: str, ord_qty: int, car_lnc_cd: str | None = None):
    """
    장바구니에 상품 저장 (매장 선택 없이).

    Use when: 사용자가 매장 선택 없이 장바구니에 담기를 원할 때 ("장바구니에 담아줘", "나중에 주문할게").

    Args:
        goods_no (str): Product number.
        ord_qty (int): Quantity (min 1).
        car_lnc_cd (str | None): Vehicle launch code (optional).

    Example: {"goods_no": "GXXXXXXXXXXXX", "ord_qty": 4}
    """
    goods_info_arr_str = f"{goods_no}|{ord_qty}"
    logger.debug("[TOOL][save_to_cart_tool] Called with: goods_info=%s, car_lnc_cd=%s", goods_info_arr_str, car_lnc_cd)

    try:
        body = SetOrderFormAIRequest(
            goods_info_arr_str=goods_info_arr_str,
            smrt_pay_yn="N",
            drt_pur_yn="N",
            car_lnc_cd=car_lnc_cd,
        )
        response = set_order_form_ai(client=get_client(), body=body)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to save to cart"
            )
        # logger.debug("[TOOL][save_to_cart_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][save_to_cart_tool] Failed")
        return _error_response(None, str(e), "Failed to save to cart")


@tool
def quick_order_tool(
    goods_no: str,
    ord_qty: int,
    shop_id: str,
    car_lnc_cd: str | None = None,
    rsv_date: str | None = None,
    rsv_hour: str | None = None,
):
    """
    퀵쇼핑 주문 실행 (매장 선택 포함).

    Pre-conditions MUST all pass before calling:
      1. get_store_install_availability_tool confirmed the selected shop has an installable slot for this order
      2. Pre-order preview shown, user confirmed

    When NOT to use:
    - shop_id not yet confirmed from tool result (never fabricate shop_id)
    - is_installable not yet verified

    Args:
        goods_no (str): Product number.
        ord_qty (int): Quantity (min 1).
        shop_id (str): Store ID from store tool results (e.g., "CXXXXX").
        car_lnc_cd (str | None): Vehicle launch code (optional).
        rsv_date (str | None): 방문 예약일자 YYYYMMDD (e.g., "20260423"). datepick 선택값을 변환해서 전달.
        rsv_hour (str | None): 방문 예약시간 HH 00~23 두 자리 (e.g., "11"). datepick 선택값의 시(hour)만 두 자리로 전달.

    Example: {"goods_no": "GXXXXXXXXXXXX", "ord_qty": 4, "shop_id": "CXXXXX", "rsv_date": "20260423", "rsv_hour": "11"}
    """
    goods_info_arr_str = f"{goods_no}|{ord_qty}"
    logger.debug(
        "[TOOL][quick_order_tool] Called with: goods_info=%s, shop_id=%s, car_lnc_cd=%s, rsv_date=%s, rsv_hour=%s",
        goods_info_arr_str, shop_id, car_lnc_cd, rsv_date, rsv_hour,
    )

    try:
        body = SetOrderFormAIRequest(
            goods_info_arr_str=goods_info_arr_str,
            smrt_pay_yn="N",
            drt_pur_yn="Y",
            shop_seq=shop_id,
            car_lnc_cd=car_lnc_cd,
            rsv_date=rsv_date,
            rsv_hour=rsv_hour,
        )
        response = set_order_form_ai(client=get_client(), body=body)
        if response.parsed is None:
            body_text = response.content.decode(errors="ignore") or "Failed to create quick order"
            logger.warning(
                "[TOOL][quick_order_tool] BE order failed: status=%s goods_info=%s shop_id=%s "
                "rsv_date=%s rsv_hour=%s body=%s",
                response.status_code, goods_info_arr_str, shop_id, rsv_date, rsv_hour, body_text[:500],
            )
            return _error_response(response.status_code, f"HTTP {response.status_code}", body_text)
        # logger.debug("[TOOL][quick_order_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][quick_order_tool] Failed")
        return _error_response(None, str(e), "Failed to create quick order")


@tool
def get_order_status_tool(query_no: str):
    """
    Retrieve order status and delivery tracking.

    Args:
        query_no (str): Order number (starts with 'O') or delivery number (starts with 'D').

    Example: {"query_no": "O100017122"}
    """
    logger.debug("[TOOL][get_order_status_tool] Called with: query_no=%s", query_no)

    try:
        response = get_order_delivery(client=get_client(), query_no=query_no)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to retrieve order status"
            )
        # logger.debug("[TOOL][get_order_status_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_order_status_tool] Failed")
        return _error_response(None, str(e), "Failed to retrieve order status")


@tool
def get_orders_of_user_tool():
    """
    Retrieve authenticated user's order list (ord_no, goods_nm, ord_qty, sys_reg_dtime).

    Call FIRST when user asks about their orders.
    - 1 order → auto-call get_order_status_tool with that order number
    - Multiple orders → show list, ask which one they want details for
    """
    logger.debug("[TOOL][get_orders_of_user_tool] Called")

    try:
        response = get_orders(client=get_client())
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to retrieve order list"
            )
        # logger.debug("[TOOL][get_orders_of_user_tool] Response: %s", response.parsed)
        data = _to_dict(response.parsed)
        if isinstance(data, dict) and isinstance(data.get("orders"), list):
            data["orders"] = _enrich_orders_with_detail(data["orders"])
        return _success_response(response.status_code, data)
    except Exception as e:
        logger.exception("[TOOL][get_orders_of_user_tool] Failed")
        return _error_response(None, str(e), "Failed to retrieve order list")


@tool
def get_maintenance_history_tool(mbr_car_reg_seq: str | None = None, limit: int = 5):
    """
    Retrieve authenticated user's recent maintenance/service history.

    Use when the user asks for 정비이력/정비내역/관리받은 내역/서비스 이력.
    The backend unions offline completed maintenance history and online completed
    installation history, sorted by service date descending.

    Args:
        mbr_car_reg_seq: Optional registered car sequence when a specific vehicle is selected.
        limit: Number of recent history rows. Always use 5 unless user explicitly asks for fewer.

    Returns:
        {"items": [
          {"car_svc_dt":"2026-05-20", "shop_nm":"티스테이션 ...",
           "car_svc_info":"...", "car_svc_qty":"4", "svc_tp":"온라인/장착", ...}
        ]}
    """
    safe_limit = max(1, min(int(limit or 5), 5))
    logger.debug(
        "[TOOL][get_maintenance_history_tool] Called mbr_car_reg_seq=%s limit=%s",
        mbr_car_reg_seq, safe_limit,
    )

    try:
        response = get_maintenance_history(
            client=get_client(),
            mbr_car_reg_seq=mbr_car_reg_seq,
            limit=safe_limit,
        )
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to retrieve maintenance history",
            )
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_maintenance_history_tool] Failed")
        return _error_response(None, str(e), "Failed to retrieve maintenance history")


@tool
def get_my_reservations_tool(sct_cd: str = "all"):
    """
    Retrieve authenticated user's shop visit reservations from ET_SHOP_RSV_INFO.

    Args:
        sct_cd: Reservation category filter (default "all"). Values:
            - "100": 방문예약 (simple shop visit reservation)
            - "200": 구매후방문예약 (post-purchase visit, has ord_no)
            - "300": 오프라인예약 (offline reservation)
            - "all": all categories — default for reservation-history lookup

    Returns response with `reservations` list. Each item includes:
        shop_rsv_seq, shop_rsv_no, ord_no, shop_id, shop_nm, tel_no,
        vst_rsv_dtime (YYYY-MM-DD HH:MI), rsv_req_desc,
        shop_rsv_sct_cd / shop_rsv_sct_label (방문예약/구매후방문예약/오프라인예약),
        shop_vst_rsv_sts_cd / shop_vst_rsv_sts_label (예약대기/예약완료/서비스완료/서비스취소).

    Sorted by vst_rsv_dtime DESC.

    Call when user asks about their reservations (예: "내 예약 보여줘", "예약 어떻게 돼있어?",
    "다음 방문 언제야?", "내 예약 취소된 거 있어?").
    """
    logger.debug("[TOOL][get_my_reservations_tool] Called sct_cd=%s", sct_cd)

    try:
        response = get_reservations(client=get_client(), sct_cd=sct_cd)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to retrieve reservations"
            )
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_my_reservations_tool] Failed")
        return _error_response(None, str(e), "Failed to retrieve reservations")


@tool
@tool_cache(ttl=300)
def get_favorite_stores_tool():
    """
    회원 단골매장 목록 조회.

    Call ONLY when the user explicitly references their favorite/regular store —
    e.g. "내 단골매장", "단골 가게 보여줘", "자주 가는 매장", "마이샵", "단골점".
    DO NOT call as a generic store search fallback. For "근처 매장"/"강남 매장"
    use `get_store_list_tool` or `get_nearby_stores_tool` instead.

    Auth: 회원번호는 JWT 토큰에서 자동 추출. 인자 없음.

    Response (success):
      {"status": "success", "data": {"stores": [FavoriteStoreItem, ...]}}
      각 FavoriteStoreItem 은 매장 검색 결과(`get_store_list_tool`) 와 동일한
      StoreListItem shape 에 단골 등록 일시(`favored_at`) 가 추가된 형태:
        shop_id, shop_seq, shop_nm, addr_base, addr_dtl, road_addr_base,
        road_addr_dtl, tel_no, shop_biz_strt_time/end_time,
        shop_biz_strt_wday/end_wday, shop_sat_strt_time/end_time,
        is_all_my_t, is_installable, rating_idx, favored_at.
      매장명 가나다 순 정렬. 폐점/비활성 매장은 자동 제외됨.

    Empty result handling:
      `stores: []` 일 때 — 사용자에게 "등록된 단골매장이 없어요" 안내 + quickReply
      ["매장 검색", "처음으로"] emit. 다른 store 도구로 자동 전환 금지.
    """
    logger.debug("[TOOL][get_favorite_stores_tool] Called")

    try:
        response = get_favorite_stores(client=get_client())
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get favorite stores"
            )
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_favorite_stores_tool] Failed")
        return _error_response(None, str(e), "Failed to get favorite stores")
