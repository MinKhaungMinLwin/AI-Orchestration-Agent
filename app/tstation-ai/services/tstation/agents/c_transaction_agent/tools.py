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
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_available_coupons_api_prices_coupons_available_get import sync_detailed as get_available_coupons
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_my_coupons_api_prices_coupons_mine_get import sync_detailed as get_my_coupons

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


def get_client() -> AuthenticatedClient:
    """Get authenticated client for tstation-be API."""
    return get_tstation_be_client()


def _to_dict(res: Any) -> Any:
    return res.to_dict() if hasattr(res, 'to_dict') else (res.model_dump() if hasattr(res, 'model_dump') else res)


def _error_response(http_status: int | None, reason: str, message: str) -> dict:
    return {"status": "error", "http_status": http_status, "reason": reason, "message": message}


def _success_response(http_status: int, data: Any) -> dict:
    return {"status": "success", "http_status": http_status, "data": data}




def _fetch_order_detail(ord_no: str) -> dict:
    """Fetch order delivery detail for a single ord_no, return detail dict or empty on failure."""
    try:
        response = get_order_delivery(client=get_client(), query_no=ord_no)
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
    with ThreadPoolExecutor(max_workers=min(len(ord_nos), 5)) as executor:
        futures = {executor.submit(_fetch_order_detail, ono): ono for ono in ord_nos}
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
    logger.info("[TOOL][get_final_price_tool] Called with: goods_no=%s, member_type=%s", goods_no, member_type)

    try:
        response = get_price(client=get_client(), goods_no=goods_no, member_type=member_type)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get product price"
            )
        logger.info("[TOOL][get_final_price_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_final_price_tool] Failed")
        return _error_response(None, str(e), "Failed to get product price")


@tool
@tool_cache(ttl=600)
def get_available_coupons_tool(mbr_no: str | None = None, lang_cd: str = "ko"):
    """
    다운로드 가능 쿠폰 조회.

    Use when user asks "받을 수 있는 쿠폰", "쿠폰 조회", "available coupons".

    Args:
        mbr_no (str | None): 회원번호 (used for per-user cache key scoping).
        lang_cd (str): Language code (default: 'ko').
    """
    logger.info("[TOOL][get_available_coupons_tool] Called with: mbr_no=%s, lang_cd=%s", mbr_no, lang_cd)

    try:
        response = get_available_coupons(client=get_client(), lang_cd=lang_cd)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get available coupons"
            )
        logger.info("[TOOL][get_available_coupons_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_available_coupons_tool] Failed")
        return _error_response(None, str(e), "Failed to get available coupons")


@tool
def get_my_coupons_tool(lang_cd: str = "ko"):
    """
    내 쿠폰 목록 조회.

    Use when user asks "내 쿠폰", "쿠폰 목록", "my coupons".

    Args:
        lang_cd (str): Language code (default: 'ko').
    """
    logger.info("[TOOL][get_my_coupons_tool] Called with: lang_cd=%s", lang_cd)

    try:
        response = get_my_coupons(client=get_client(), lang_cd=lang_cd)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get my coupons"
            )
        logger.info("[TOOL][get_my_coupons_tool] Response: %s", response.parsed)
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
    logger.info(
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
        logger.info("[TOOL][issue_coupon_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][issue_coupon_tool] Failed")
        return _error_response(None, str(e), "Failed to issue coupon")


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
    logger.info("[TOOL][get_logistics_inventory_tool] Called with: goods_no=%s", goods_no)

    try:
        response = get_logistics_inventory(client=get_client(), body=body)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get logistics inventory"
            )
        logger.info("[TOOL][get_logistics_inventory_tool] Response: %s", response.parsed)
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
    logger.info("[TOOL][get_store_inventory_tool] Called with: goods_list=%s, shop_id_list=%s", goods_list, shop_id_list)

    try:
        response = get_store_inventory(client=get_client(), body=body)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get store inventory"
            )
        logger.info("[TOOL][get_store_inventory_tool] Response: %s", response.parsed)
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
    logger.info("[TOOL][search_place_tool] Called with: query=%s, size=%s", query, size)

    try:
        response = search_place(client=get_client(), query=query, size=size)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to search place"
            )
        logger.info("[TOOL][search_place_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][search_place_tool] Failed")
        return _error_response(None, str(e), "Failed to search place")


@tool
def get_nearby_stores_tool(
    user_xpos: float,
    user_ypos: float,
    radius_km: float = 10.0,
    svc_codes: List[str] | None = None,
    all_my_t_only: bool = False,
    imported_car_only: bool = False,
    chl_sct_cd: str | None = None,
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

    Example: {"user_xpos": 127.0276, "user_ypos": 37.4979, "radius_km": 20, "chl_sct_cd": "F"}
    """
    logger.info(
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
        logger.info("[TOOL][get_nearby_stores_tool] Response: %s", response.parsed)
        data = _to_dict(response.parsed)

        # Truncate to top 10 stores so the LLM's `location` template (max_length=10
        # per LocationTemplate schema) doesn't fail structured-output validation
        # and silently drop the entire response. Sort: is_installable=true first
        # (matters for purchase flows), then by distance_km ascending. Response
        # shape is preserved.
        stores = data.get("stores") if isinstance(data, dict) else None
        if isinstance(stores, list) and len(stores) > 10:
            original_count = len(stores)
            sorted_stores = sorted(
                stores,
                key=lambda s: (
                    not bool(s.get("is_installable", False)),
                    s.get("distance_km") if isinstance(s.get("distance_km"), (int, float)) else float("inf"),
                ),
            )
            data["stores"] = sorted_stores[:10]
            logger.info(
                "[TOOL][get_nearby_stores_tool] Truncated %d stores -> top 10 (installable-first, distance-asc)",
                original_count,
            )

        return _success_response(response.status_code, data)
    except Exception as e:
        logger.exception("[TOOL][get_nearby_stores_tool] Failed")
        return _error_response(None, str(e), "Failed to get nearby stores")


@tool
@tool_cache(ttl=1800)
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
        limit (int): 최대 반환 매장 수 (default 5).
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
    # Normalize brand name to Korean equivalent (e.g., "T-Station" → "티스테이션")
    if store_nm:
        store_nm = normalize_brand_name(store_nm)

    logger.info(
        "[TOOL][get_store_list_tool] Called with: region_code=%s, store_nm=%s (normalized), limit=%s, "
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
        logger.info("[TOOL][get_store_list_tool] Response: %s", response.parsed)
        data = _to_dict(response.parsed)
        return _success_response(response.status_code, data)
    except Exception as e:
        logger.exception("[TOOL][get_store_list_tool] Failed")
        return _error_response(None, str(e), "Failed to get store list")


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
    logger.info(
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
        logger.info("[TOOL][get_store_detail_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_store_detail_tool] Failed")
        return _error_response(None, str(e), "Failed to get store details")


@tool
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
    logger.info(
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
        logger.info("[TOOL][get_store_schedule_tool] Response: %s", response.parsed)
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
    logger.info(
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
    logger.info("[TOOL][save_to_cart_tool] Called with: goods_info=%s, car_lnc_cd=%s", goods_info_arr_str, car_lnc_cd)

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
        logger.info("[TOOL][save_to_cart_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][save_to_cart_tool] Failed")
        return _error_response(None, str(e), "Failed to save to cart")


@tool
def quick_order_tool(goods_no: str, ord_qty: int, shop_id: str, car_lnc_cd: str | None = None):
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

    Example: {"goods_no": "GXXXXXXXXXXXX", "ord_qty": 4, "shop_id": "CXXXXX"}
    """
    goods_info_arr_str = f"{goods_no}|{ord_qty}"
    logger.info("[TOOL][quick_order_tool] Called with: goods_info=%s, shop_id=%s, car_lnc_cd=%s", goods_info_arr_str, shop_id, car_lnc_cd)

    try:
        body = SetOrderFormAIRequest(
            goods_info_arr_str=goods_info_arr_str,
            smrt_pay_yn="N",
            drt_pur_yn="Y",
            shop_seq=shop_id,
            car_lnc_cd=car_lnc_cd,
        )
        response = set_order_form_ai(client=get_client(), body=body)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to create quick order"
            )
        logger.info("[TOOL][quick_order_tool] Response: %s", response.parsed)
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
    logger.info("[TOOL][get_order_status_tool] Called with: query_no=%s", query_no)

    try:
        response = get_order_delivery(client=get_client(), query_no=query_no)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to retrieve order status"
            )
        logger.info("[TOOL][get_order_status_tool] Response: %s", response.parsed)
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
    logger.info("[TOOL][get_orders_of_user_tool] Called")

    try:
        response = get_orders(client=get_client())
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to retrieve order list"
            )
        logger.info("[TOOL][get_orders_of_user_tool] Response: %s", response.parsed)
        data = _to_dict(response.parsed)
        if isinstance(data, dict) and isinstance(data.get("orders"), list):
            data["orders"] = _enrich_orders_with_detail(data["orders"])
        return _success_response(response.status_code, data)
    except Exception as e:
        logger.exception("[TOOL][get_orders_of_user_tool] Failed")
        return _error_response(None, str(e), "Failed to retrieve order list")
