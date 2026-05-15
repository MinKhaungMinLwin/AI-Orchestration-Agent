import logging
from common.tool_cache import tool_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, List, Dict

from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from services.tstation.common.tstation_be_client import get_tstation_be_client
from langchain.tools import tool
from common.brand_mapping import normalize_brand_name

logger = logging.getLogger(__name__)

# STORE AF
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_list_api_store_list_get import sync_detailed as get_store_list
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_detail_api_store_detail_get import sync_detailed as get_store_detail
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_schedule_api_store_schedule_get import sync_detailed as get_store_schedule
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.search_place_api_store_place_search_get import sync_detailed as search_place
from common.tstation_be_api_client.hkt_api_client.models import ScheduleMode

# PRICE AF
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_price_api_prices_final_get import sync_detailed as get_price
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_my_coupons_api_prices_coupons_mine_get import sync_detailed as get_my_coupons

# EVENT / DEAL AF — 상품번호 기준 진행 중 기획전+쿠폰 조회
from common.tstation_be_api_client.hkt_api_client.api.event_deal_af_이벤트_및_기획전_조회.get_deals_by_product_api_events_deals_by_product_get import sync_detailed as get_deals_by_product

# COUPON AF — 쿠폰 발급
from common.tstation_be_api_client.hkt_api_client.api.coupon_af_쿠폰_발급.issue_coupon_by_goods_api_coupons_issue_goods_post import sync_detailed as issue_coupon_by_goods
from common.tstation_be_api_client.hkt_api_client.api.coupon_af_쿠폰_발급.issue_coupon_by_cpn_api_coupons_issue_cpn_post import sync_detailed as issue_coupon_by_cpn
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
    ShopIdItem
)

# QUICK SHOPPING AF (setOrderFormAI - 퀵쇼핑/장바구니 통합 API)
from common.tstation_be_api_client.hkt_api_client.api.quick_shopping_af_퀵_쇼핑주문서_초안_생성.set_order_form_ai_api_quick_order_order_set_order_form_ai_do_post import sync_detailed as set_order_form_ai
from common.tstation_be_api_client.hkt_api_client.models import SetOrderFormAIRequest

# ORDER & DELIVERY AF
from common.tstation_be_api_client.hkt_api_client.api.order_delivery_af_주문_및_배송_추적.get_order_delivery_api_orders_summary_get import sync_detailed as get_order_delivery
from common.tstation_be_api_client.hkt_api_client.api.order_delivery_af_주문_및_배송_추적.get_orders_api_orders_get import sync_detailed as get_orders

# Reservation AF — 매장 방문 예약 조회
from common.tstation_be_api_client.hkt_api_client.api.reservation_af_매장_방문_예약_조회.get_reservations_api_reservations_get import sync_detailed as get_reservations


def get_client() -> AuthenticatedClient:
    """Get authenticated client for tstation-be API."""
    return get_tstation_be_client()


def _to_dict(res: Any) -> Any:
    return res.to_dict() if hasattr(res, 'to_dict') else (res.model_dump() if hasattr(res, 'model_dump') else res)


def _error_response(http_status: int | None, reason: str, message: str) -> dict:
    return {"status": "error", "http_status": http_status, "reason": reason, "message": message}


def _success_response(http_status: int, data: Any) -> dict:
    return {"status": "success", "http_status": http_status, "data": data}


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
            "stores": [],
            "validation_message": confirmation_msg,
            "instruction_to_agent": (
                f"DETERMINISTIC GUARD: 사용자 입력 '{user_input}' 과 매칭된 매장 분점명이 정확히 일치하지 않음 "
                f"(candidates={candidate_names}). "
                f"validation_message 를 그대로 emit + quickReplies: {quick_reply_hint}. "
                f"get_store_schedule_tool / get_store_detail_tool / get_store_inventory_tool / "
                f"get_multi_store_schedule_tool 절대 호출 금지. STOP."
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
    물류 창고 재고 조회.

    MANDATORY as STEP 3 in order flow — call before presenting store options.

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
    Check store inventory availability.

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
        limit (int): 반환 매장 수 상한 (1-10). Default 10. 사용자가 "N개"를 명시하면
            그 값을 전달. location 카드 max_length=10 제약 때문에 10 초과 시 10으로 클램핑.

    Example: {"user_xpos": 127.0276, "user_ypos": 37.4979, "radius_km": 20, "chl_sct_cd": "F", "limit": 5}
    """
    logger.debug(
        "[TOOL][get_nearby_stores_tool] Called with: user_xpos=%s, user_ypos=%s, radius_km=%s, svc_codes=%s, "
        "all_my_t_only=%s, imported_car_only=%s, chl_sct_cd=%s",
        user_xpos, user_ypos, radius_km, svc_codes, all_my_t_only, imported_car_only, chl_sct_cd,
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
        )
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get nearby stores"
            )
        # logger.debug("[TOOL][get_nearby_stores_tool] Response: %s", response.parsed)
        data = _to_dict(response.parsed)

        # Truncate to top `limit` stores (clamped to 10 — LocationTemplate
        # max_length=10). Sort: is_installable=true first (matters for purchase
        # flows), then by distance_km ascending. Response shape is preserved.
        cap = max(1, min(int(limit), 10))
        stores = data.get("stores") if isinstance(data, dict) else None
        if isinstance(stores, list) and len(stores) > cap:
            original_count = len(stores)
            sorted_stores = sorted(
                stores,
                key=lambda s: (
                    not bool(s.get("is_installable", False)),
                    s.get("distance_km") if isinstance(s.get("distance_km"), (int, float)) else float("inf"),
                ),
            )
            data["stores"] = sorted_stores[:cap]
            logger.debug(
                "[TOOL][get_nearby_stores_tool] Truncated %d stores -> top %d (installable-first, distance-asc)",
                original_count, cap,
            )

        return _success_response(response.status_code, data)
    except Exception as e:
        logger.exception("[TOOL][get_nearby_stores_tool] Failed")
        return _error_response(None, str(e), "Failed to get nearby stores")


@tool_cache(ttl=1800)
def _get_store_list_cached(
    region_code: str | None = None,
    store_nm: str | None = None,
    limit: int = 10,
    svc_codes: List[str] | None = None,
    all_my_t_only: bool = False,
    imported_car_only: bool = False,
    chl_sct_cd: str | None = None,
) -> dict:
    """Internal cached BE call. Validation runs in `get_store_list_tool` after this returns."""
    logger.debug(
        "[TOOL][_get_store_list_cached] Called with: region_code=%s, store_nm=%s (normalized), limit=%s, "
        "svc_codes=%s, all_my_t_only=%s, imported_car_only=%s, chl_sct_cd=%s",
        region_code, store_nm, limit, svc_codes, all_my_t_only, imported_car_only, chl_sct_cd,
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

    Examples:
        - {"region_code": "강남", "store_nm": "티스테", "limit": 5}
        - {"region_code": "서울", "limit": 5}
        - {"region_code": None, "store_nm": "극동상사", "limit": 5}
        - {"region_code": "강남", "limit": 5, "imported_car_only": True}
        - {"region_code": "강남", "svc_codes": ["121"], "limit": 5}  # 강남에서 경정비 가능
        - {"store_nm": "광교신도시", "svc_codes": ["121"]}  # 광교신도시점이 경정비 가능한지 확인
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
    Get reservation slots for a single store using mode-based cal_day range (single BE call).

    The backend applies a different cal_day range per mode based on inventory state.
    Choose mode AFTER inspecting get_store_inventory_tool + get_logistics_inventory_tool
    results for this shop and goods_no:

    | mode                          | When to use                                      |
    |-------------------------------|--------------------------------------------------|
    | today_only                    | shop ∈ todayShopArray (오늘서비스만)             |
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
    Flow 3.5 — find earliest reservation slots across up to 3 stores using **tier cascade**.

    The tool selects ONE tier across the whole batch based on inventory state:

    | Tier | Trigger condition                                       | mode used      |
    |------|---------------------------------------------------------|----------------|
    | 1    | At least one candidate ∈ todayShopArray                 | today_only     |
    | 2    | Tier 1 empty AND ≥1 candidate ∈ tnaShopArray            | tna_only       |
    | 3    | Tiers 1–2 empty AND has_logistics=True                  | logistics_only |
    | none | All tiers empty                                         | (no BE call)   |

    Tier 1 queries the today_only intersection; tier 2 the tna intersection; tier 3
    the remaining candidates not already in today/tna arrays. The first non-empty
    tier is returned — earlier tiers always win (today > tna > 일반배송).

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

    # Tier 1 — today_only on candidates ∩ todayShopArray
    tier1_shops = [sid for sid in candidates if sid in today_set]
    if tier1_shops:
        results = _fetch_schedule_for_shops(tier1_shops, ScheduleMode.TODAY_ONLY)
        if any(r.get("slots") for r in results.values()):
            return _success_response(200, {
                "tier": "today_only",
                "stores": [{"shop_id": sid, **(results.get(sid) or {})} for sid in tier1_shops],
                "candidate_shop_ids": candidates,
            })

    # Tier 2 — tna_only on candidates ∩ tnaShopArray
    tier2_shops = [sid for sid in candidates if sid in tna_set]
    if tier2_shops:
        results = _fetch_schedule_for_shops(tier2_shops, ScheduleMode.TNA_ONLY)
        if any(r.get("slots") for r in results.values()):
            return _success_response(200, {
                "tier": "tna_only",
                "stores": [{"shop_id": sid, **(results.get(sid) or {})} for sid in tier2_shops],
                "candidate_shop_ids": candidates,
            })

    # Tier 3 — logistics_only on remaining candidates (not in today/tna sets)
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


def _extract_stores(data: Any) -> list[dict]:
    if not isinstance(data, dict):
        return []
    stores = data.get("stores") or data.get("items") or []
    return stores if isinstance(stores, list) else []


def _shop_id(store: dict) -> str | None:
    value = store.get("shop_id") or store.get("shopId") or store.get("shop_seq") or store.get("shopSeq")
    return str(value) if value else None


def _extract_logistics_qty(data: Any) -> int:
    if not isinstance(data, dict):
        return 0
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


@tool
@tool_cache(ttl=120)
def transaction_store_preview_tool(
    goods_no: str,
    ord_qty: int,
    region_code: str | None = None,
    store_nm: str | None = None,
    user_xpos: float | None = None,
    user_ypos: float | None = None,
    include_price: bool = True,
    svc_codes: List[str] | None = None,
    all_my_t_only: bool = False,
    imported_car_only: bool = False,
    chl_sct_cd: str | None = None,
):
    """
    Composite preview for purchase/store flow: store candidates + price + stock + earliest schedule.

    Use when goods_no and quantity are known and the user wants nearby/regional stores,
    stock, or available reservation dates. This is a preview only; never creates an order.
    """
    logger.debug(
        "[TOOL][transaction_store_preview_tool] Called with: goods_no=%s, ord_qty=%s, region_code=%s, "
        "store_nm=%s, user_xpos=%s, user_ypos=%s, include_price=%s",
        goods_no, ord_qty, region_code, store_nm, user_xpos, user_ypos, include_price,
    )

    if not goods_no or ord_qty < 1:
        return _error_response(None, "invalid_input", "goods_no and ord_qty are required")

    if store_nm:
        store_nm = normalize_brand_name(store_nm)

    if user_xpos is not None and user_ypos is not None:
        store_response = get_store_list(
            client=get_client(),
            xpos=user_xpos,
            ypos=user_ypos,
            radius_km=10.0,
            svc_codes=svc_codes,
            all_my_t_only=all_my_t_only,
            imported_car_only=imported_car_only,
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
    candidates = sorted(
        stores,
        key=lambda s: (
            not bool(s.get("is_installable", False)),
            s.get("distance_km") if isinstance(s.get("distance_km"), (int, float)) else float("inf"),
        ),
    )[:3]
    shop_ids = [sid for store in candidates if (sid := _shop_id(store))]
    if not shop_ids:
        return _success_response(store_response.status_code, {
            "stores": [],
            "message": "No store candidates found",
            "price": None,
            "logistics": None,
            "inventory": None,
            "schedule": None,
        })

    goods_list = [{"goodsNo": goods_no, "qty": str(ord_qty)}]
    shop_id_list = [{"shopId": sid} for sid in shop_ids]

    def _fetch_logistics():
        body = LogisticsRequest(goods_no=goods_no)
        return get_logistics_inventory(client=get_client(), body=body)

    def _fetch_store_inventory():
        g_items = [GoodsItem(goods_no=g["goodsNo"], qty=str(g["qty"])) for g in goods_list]
        s_items = [ShopIdItem(shop_id=s["shopId"]) for s in shop_id_list]
        return get_store_inventory(client=get_client(), body=StoreInventoryRequest(goods_list=g_items, shop_id_list=s_items))

    def _fetch_price():
        return get_price(client=get_client(), goods_no=goods_no, member_type=None)

    tasks = {"logistics": _fetch_logistics, "store_inventory": _fetch_store_inventory}
    if include_price:
        tasks["price"] = _fetch_price

    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            response = future.result()
            results[name] = _to_dict(response.parsed) if response.parsed is not None else None

    logistics_qty = _extract_logistics_qty(results.get("logistics"))
    today_shop_ids = _extract_inventory_shop_ids(results.get("store_inventory"), "todayShopArray")
    tna_shop_ids = _extract_inventory_shop_ids(results.get("store_inventory"), "tnaShopArray")
    schedule = get_multi_store_schedule_tool.func(
        shop_id_list=shop_ids,
        today_shop_ids=today_shop_ids,
        tna_shop_ids=tna_shop_ids,
        has_logistics=logistics_qty > 0,
    )

    return _success_response(200, {
        "price": results.get("price"),
        "logistics": results.get("logistics"),
        "inventory": results.get("store_inventory"),
        "schedule": schedule.get("data") if isinstance(schedule, dict) else schedule,
        "stores": [{"shop_id": _shop_id(store), **store} for store in candidates],
        "candidate_shop_ids": shop_ids,
    })


# =====================================================
# ORDER TOOLS
# =====================================================

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
      1. get_logistics_inventory_tool called (inventory_mode set)
      2. get_store_detail_tool called → is_installable=true confirmed
      3. If LOGISTICS_UNAVAILABLE: get_store_inventory_tool verified shop in todayShopArray/tnaShopArray
      4. Pre-order preview shown, user confirmed

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
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to create quick order"
            )
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
def get_my_reservations_tool(sct_cd: str = "100"):
    """
    Retrieve authenticated user's shop visit reservations from ET_SHOP_RSV_INFO.

    Args:
        sct_cd: Reservation category filter (default "100"). Values:
            - "100": 방문예약 (simple shop visit reservation — default)
            - "200": 구매후방문예약 (post-purchase visit, has ord_no)
            - "300": 오프라인예약 (offline reservation)
            - "all": all categories

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
