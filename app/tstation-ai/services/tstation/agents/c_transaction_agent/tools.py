import logging
from typing import Any, List, Dict

from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from services.tstation.common.tstation_be_client import get_tstation_be_client
from langchain.tools import tool
from common.brand_mapping import normalize_brand_name

logger = logging.getLogger(__name__)

# STORE AF
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_list_api_store_list_get import sync_detailed as get_store_list
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_detail_api_store_detail_get import sync_detailed as get_store_detail
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.search_place_api_store_place_search_get import sync_detailed as search_place

# PRICE AF
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_price_api_prices_final_get import sync_detailed as get_price
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_available_coupons_api_prices_coupons_available_get import sync_detailed as get_available_coupons
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_my_coupons_api_prices_coupons_mine_get import sync_detailed as get_my_coupons

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


# =====================================================
# PRICING TOOLS
# =====================================================

@tool
def get_final_price_tool(goods_no: str, member_type: str | None = None):
    """
    Get product price and discount.

    Retrieve base selling price, maximum discounted price (promotion + coupon),
    labor cost, and today's labor cost using the product number.

    Args:
        goods_no (str): Product number (e.g., GXXXXXXXXXXXX).
        member_type (str | None): Member type (e.g., 'general', 'PARTNER').

    Example Inputs:
        - {"goods_no": "GXXXXXXXXXXXX", "member_type": "general"}
        - {"goods_no": "GXXXXXXXXXXXX", "member_type": "PARTNER"}
        - {"goods_no": "GXXXXXXXXXXXX", "member_type": "general"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
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
def get_available_coupons_tool(lang_cd: str = "ko"):
    """
    다운로드 가능 쿠폰 조회.

    현재 사용자가 다운로드 가능한 쿠폰 목록을 조회합니다.

    Use this tool when:
    - User asks about coupons available for download
    - User asks "받을 수 있는 쿠폰", "쿠폰 조회", "available coupons"

    Args:
        lang_cd (str): Language code (default: 'ko' for Korean).

    Example Inputs:
        - {"lang_cd": "ko"}
        - {"lang_cd": "ko"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    logger.info("[TOOL][get_available_coupons_tool] Called with: lang_cd=%s", lang_cd)

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

    사용자가 보유한 사용 가능한 쿠폰 목록을 조회합니다.

    Use this tool when:
    - User asks about their owned coupons
    - User asks "내 쿠폰", "我的优惠券", "my coupons"

    Args:
        lang_cd (str): Language code (default: 'ko' for Korean).

    Example Inputs:
        - {"lang_cd": "ko"}
        - {"lang_cd": "ko"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
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


# =====================================================
# INVENTORY TOOLS
# =====================================================

@tool
def get_logistics_inventory_tool(goods_no: str):
    """
    물류 창고 재고 조회.

    When to use:
    - MANDATORY as STEP 3 in order flow — call before presenting store options
    - When user asks if product is in stock (warehouse level)

    Result:
    - logistics_qty > 0 → inventory_mode = LOGISTICS_AVAILABLE (all stores eligible)
    - logistics_qty = 0 → inventory_mode = LOGISTICS_UNAVAILABLE (must check store inventory)
    - rsv_sale_yn: "Y" → reservation order available (장착 워킹데이 기준 14일 이후)

    Args:
        goods_no (str): Product number.

    Example Inputs:
        - {"goods_no": "GXXXXXXXXXXXX"}
        - {"goods_no": "GXXXXXXXXXXXX"}
        - {"goods_no": "GXXXXXXXXXXXX"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": {"logistics_qty": int, "rsv_sale_yn": str|null, "rsv_install_date": str|null}}
        - logistics_qty: Logistics warehouse stock quantity (0 = out of stock). ⚠️ Do NOT expose quantity to user.
        - rsv_sale_yn: Reservation sale flag ("Y" = reservation order available). ⚠️ Do NOT expose raw value to user.
        - rsv_install_date: Earliest installation date for reservation orders (YYYY-MM-DD format, only present when rsv_sale_yn="Y"). Use this date in user-facing messages.
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

    Input product list and store list to check:
    - todayShopArray: Stores that can install today
    - tnaShopArray: Stores eligible for T-NA delivery

    Args:
        goods_list (List[Dict[str, Any]]): Product list for stock check.
            Each item: {"goodsNo": "G123", "qty": "4"} where qty is STRING type.
        shop_id_list (List[Dict[str, Any]]): Store list for stock check.
            Each item: {"shopId": "F0001"}

    Example Inputs:
        - {"goods_list": [{"goodsNo": "GXXXXXXXXXXXX", "qty": "4"}], "shop_id_list": [{"shopId": "BXXXXX"}]}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
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
def search_place_tool(query: str, size: int = 10):
    """
    위치 명칭 검색 (Kakao 키워드 검색)

    장소명, 건물명, 주소 등을 검색하여 좌표(x, y)를 반환합니다.
    반환된 좌표는 get_nearby_stores_tool의 user_xpos, user_ypos 파라미터로 사용할 수 있습니다.

    Args:
        query (str): 검색어 (예: '센텀시티', '강남역', '강남대로 100')
        size (int): 반환할 최대 결과 수 (기본 10)

    Example Inputs:
        - {"query": "센텀시티"}
        - {"query": "강남역"}
        - {"query": "강남대로 100"}

    Returns:
        dict: {"status": "success", "data": {"total": N, "items": [{"title": "...", "road_addr": "...", "x": "...", "y": "..."}]}}
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
def get_nearby_stores_tool(user_xpos: float, user_ypos: float, radius_km: float = 10.0, svc_codes: List[str] | None = None, all_my_t_only: bool = False, chl_sct_cd: str | None = None):
    """
    Get nearby stores.

    Retrieve stores within specified radius (default 10km) based on customer coordinates,
    including distance (km) from customer location.

    Response stores include is_installable field:
    - is_installable=true: 매장은 온라인 쇼핑 장착 가능 (SMART_CARE_SHOP_YN IN ('Y','E'))
    - is_installable=false: 매장은 온라인 쇼핑 장착 불가

    Args:
        user_xpos (float): Customer current X coordinate (longitude).
        user_ypos (float): Customer current Y coordinate (latitude).
        radius_km (float): Search radius in km (default 10km).
        svc_codes (List[str] | None): Service category codes.
            Returns stores that have ANY of the specified services.
            Example: ["101", "102"]
        all_my_t_only (bool): If True, only return "all my T" stores (SMART_CARE_SHOP_YN = 'Y').
            Default: False.
        chl_sct_cd (str | None): Channel section code for shop type filtering.
            F = T'Station (티스테이션)
            S = The Tire Shop (더타이어샵)
            Default: None (all shop types).

    Example Inputs:
        - {"user_xpos": 127.0276, "user_ypos": 37.4979, "radius_km": 20, "svc_codes": ["101", "102"]}
        - {"user_xpos": 126.9780, "user_ypos": 37.5665, "radius_km": 20, "chl_sct_cd": "F"}
        - {"user_xpos": 103.8198, "user_ypos": 1.3521, "radius_km": 20, "chl_sct_cd": "S"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
        Response data includes is_installable field per store.
    """
    logger.info("[TOOL][get_nearby_stores_tool] Called with: user_xpos=%s, user_ypos=%s, radius_km=%s, svc_codes=%s, all_my_t_only=%s, chl_sct_cd=%s", user_xpos, user_ypos, radius_km, svc_codes, all_my_t_only, chl_sct_cd)

    try:
        response = get_store_list(
            client=get_client(),
            xpos=user_xpos,
            ypos=user_ypos,
            radius_km=radius_km,
            svc_codes=svc_codes,
            all_my_t_only=all_my_t_only,
            chl_sct_cd=chl_sct_cd,
        )
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get nearby stores"
            )
        logger.info("[TOOL][get_nearby_stores_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_nearby_stores_tool] Failed")
        return _error_response(None, str(e), "Failed to get nearby stores")


@tool
def get_store_list_tool(region_code: str | None = None, store_nm: str | None = None, limit: int = 20, all_my_t_only: bool = False, chl_sct_cd: str | None = None):
    """
    Get store list by region and/or store name.

    Retrieve store list based on region name and/or store name keyword search.
    Returns all stores if no filters are provided.

    IMPORTANT — Parameter separation rules:
    - region_code: ONLY geographic location words (city, district, neighborhood).
        Examples: '서울', '강남', '부산', '수원', '송파'
    - store_nm: ONLY business/store name keywords.
        Examples: '티스테', '타이'

    When the user mentions BOTH a location and a store name, pass BOTH parameters simultaneously.
    Do NOT put the store name into region_code, or the region into store_nm.

    ⚠️ "all my T" 매장 필터 규칙:
    사용자가 아래 표현 중 하나라도 사용하면 all_my_t_only=True 로 설정하세요:
    - "all my T", "all my t", "All My T"
    - "올마이티", "올마이t", "올마이T"
    - "allMyT", "allmyt"

    해당 매장 결과에는 is_all_my_t 필드가 포함됩니다.
    is_all_my_t=true 인 매장은 응답 시 매장명 옆에 "[all my T]" 태그를 표시하세요.

    ⚠️ 매장 타입 필터 규칙 (chl_sct_cd):
    사용자가 특정 매장 타입을 언급하면 chl_sct_cd 를 설정하세요:
    - "티스테이션", "t'station", "T'Station", "티스테" → chl_sct_cd="F"
    - "더타이어샵", "the tire shop", "The Tire Shop", "타이어샵" → chl_sct_cd="S"
    일반 매장 검색(특정 타입 미언급)은 chl_sct_cd=None (기본값, 전체 매장).

    Response stores include is_installable field:
    - is_installable=true: 매장은 온라인 쇼핑 장착 가능 (SMART_CARE_SHOP_YN IN ('Y','E'))
    - is_installable=false: 매장은 온라인 쇼핑 장착 불가

    Args:
        region_code (str | None): Geographic region keyword — Korean city, district, or neighborhood.
            Used for ADDR_BASE / ADDR_DTL LIKE search.
            Examples: '서울', '강남', '부산'
        store_nm (str | None): Store or business name keyword.
            Examples: '티스테', '타이'
        limit (int): Maximum number of stores to return (default 20).
        all_my_t_only (bool): If True, only return "all my T" stores (SMART_CARE_SHOP_YN = 'Y').
            Default: False.
        chl_sct_cd (str | None): Channel section code for shop type filtering.
            F = T'Station (티스테이션)
            S = The Tire Shop (더타이어샵)
            Default: None (all shop types).

    Example Inputs:
        # User says "강남에 티스테 찾아줘" → pass BOTH
        - {"region_code": "강남", "store_nm": "티스테", "limit": 20}

        # User says "부산 한국타이어" → pass BOTH
        - {"region_code": "부산", "store_nm": "한국타이어", "limit": 20}

        # User says "서울 매장 보여줘" → region only
        - {"region_code": "서울", "store_nm": None, "limit": 20}

        # User says "극동상사 찾아줘" → store name only
        - {"region_code": None, "store_nm": "극동상사", "limit": 20}

        # User says "all my T 매장" → all_my_t_only=True
        - {"region_code": None, "store_nm": None, "limit": 20, "all_my_t_only": True}

        # User says "내주변 티스테이션 매장 찾아줘" → chl_sct_cd="F"
        - {"region_code": None, "store_nm": None, "limit": 20, "chl_sct_cd": "F"}

        # User says "강남 더타이어샵 매장" → region + chl_sct_cd
        - {"region_code": "강남", "store_nm": None, "limit": 20, "chl_sct_cd": "S"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
        Response data includes is_installable field per store.
    """
    # Normalize brand name to Korean equivalent (e.g., "T-Station" → "티스테이션")
    if store_nm:
        store_nm = normalize_brand_name(store_nm)

    logger.info("[TOOL][get_store_list_tool] Called with: region_code=%s, store_nm=%s (normalized), limit=%s, all_my_t_only=%s, chl_sct_cd=%s", region_code, store_nm, limit, all_my_t_only, chl_sct_cd)

    try:
        response = get_store_list(client=get_client(), region_code=region_code, store_nm=store_nm, limit=limit, all_my_t_only=all_my_t_only, chl_sct_cd=chl_sct_cd)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get store list"
            )
        logger.info("[TOOL][get_store_list_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_store_list_tool] Failed")
        return _error_response(None, str(e), "Failed to get store list")


@tool
def get_store_detail_tool(shop_id: str, cal_day: str):
    """
    Get store details and reservation availability.

    Retrieve store information and available reservation time slots (hourly)
    based on store ID and date.

    Response includes is_installable and is_tna_delivery fields:
    - is_installable=true: 매장은 온라인 쇼핑 장착 가능 (SMART_CARE_SHOP_YN IN ('Y','E'))
    - is_installable=false: 매장은 온라인 쇼핑 장착 불가
    - is_tna_delivery=true: T바로배송(한국타이어 퀵배송) 가능 매장
    - is_tna_delivery=false: T바로배송 불가 매장

    Args:
        shop_id (str): Store ID.
        cal_day (str): Query date in YYYYMMDD format.

    Example Inputs:
        - {"shop_id": "BXXXXX", "cal_day": "20260401"}
        - {"shop_id": "BXXXXX", "cal_day": "20250225"}
        - {"shop_id": "FXXXXX", "cal_day": "20260320"}
        - {"shop_id": "FXXXXX", "cal_day": "20260401"}
        - {"shop_id": "CXXXXX", "cal_day": "20250225"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
        Response data includes is_installable field.
    """
    logger.info("[TOOL][get_store_detail_tool] Called with: shop_id=%s, cal_day=%s", shop_id, cal_day)

    try:
        response = get_store_detail(client=get_client(), shop_id=shop_id, cal_day=cal_day)
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


# =====================================================
# ORDER TOOLS
# =====================================================

@tool
def save_to_cart_tool(goods_no: str, ord_qty: int, car_lnc_cd: str | None = None):
    """
    장바구니에 상품을 저장합니다.

    매장을 선택하지 않고 상품과 수량만으로 장바구니에 담는 API입니다.
    setOrderFormAI API를 drtPurYn="N" (장바구니 모드)으로 호출합니다.

    Use this tool when:
    - User has confirmed goods_no and quantity but does NOT want to select a store
    - User explicitly says "장바구니에 담아줘", "장바구니 저장", "나중에 주문할게"
    - User skips store selection step

    Args:
        goods_no (str): Product number (e.g., GXXXXXXXXXXXX).
        ord_qty (int): Quantity to add to cart, min is 1.
        car_lnc_cd (str | None): Vehicle launch code (optional, for vehicle info).

    Example Inputs:
        - {"goods_no": "GXXXXXXXXXXXX", "ord_qty": 4}
        - {"goods_no": "GXXXXXXXXXXXX", "ord_qty": 2, "car_lnc_cd": "LNCXXXXXX"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", ...}
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

    When to use:
    - User confirmed goods_no + ord_qty + selected shop_id
    - Pre-conditions MUST all pass before calling:
      1. get_logistics_inventory_tool called (inventory_mode set)
      2. get_store_detail_tool called → is_installable=true confirmed
      3. If LOGISTICS_UNAVAILABLE: get_store_inventory_tool verified shop in todayShopArray/tnaShopArray
      4. Pre-order preview shown, user confirmed in a separate turn

    When NOT to use:
    - shop_id is not yet confirmed from tool result (never fabricate shop_id)
    - is_installable not yet verified

    Args:
        goods_no (str): Product number (e.g., GXXXXXXXXXXXX).
        ord_qty (int): Quantity to order, min is 1.
        shop_id (str): Store ID from store tool results (e.g., "CXXXXX", "BXXXXX").
        car_lnc_cd (str | None): Vehicle launch code (optional, for vehicle info).

    Example Inputs:
        - {"goods_no": "GXXXXXXXXXXXX", "ord_qty": 4, "shop_id": "CXXXXX"}
        - {"goods_no": "GXXXXXXXXXXXX", "ord_qty": 2, "shop_id": "BXXXXX", "car_lnc_cd": "LNCXXXXXX"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", ...}
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
    Retrieve order processing status and delivery tracking information.

    This tool queries the Order & Delivery API using a query number.
    If query_no starts with 'O', it queries by order number.
    If query_no starts with 'D', it queries by delivery number.

    The system retrieves order progress data from OP_ORD_DTL_INFO and delivery
    tracking information from OP_ORD_DLV_DTL_INFO.

    It returns the current order status (such as order received, processing,
    shipped, or completed) together with delivery progress and shipping
    tracking details if available.

    Use this tool when the user wants to:
    - check order status
    - track delivery progress
    - view shipping or tracking information for an order

    Args:
        query_no (str): Query number. Order number starts with 'O' (e.g., 'O...'),
            delivery number starts with 'D' (e.g., 'D...').

    Example Inputs:
        - {"query_no": "O100017122"}
        - {"query_no": "D201805160015211"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
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
    Retrieve the list of orders for the authenticated user.

    This tool queries the Order & Delivery API to get all orders associated
    with the current user. It returns order summaries including:
    - Order number (ord_no)
    - Product name (goods_nm)
    - Order quantity (ord_qty)
    - Registration date (sys_reg_dtime)

    Use this tool when the user wants to:
    - check their orders
    - see their order history
    - list all their orders
    - find a specific order number

    This tool should be called FIRST when user asks about their orders.
    After receiving the order list:
    - If only 1 order: you can automatically call get_order_status_tool with that order number
    - If multiple orders: show the list to user and ask which one they want details for

    Returns:
        dict: {"status": "success", "http_status": ..., "data": {"orders": [...]}} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
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
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_orders_of_user_tool] Failed")
        return _error_response(None, str(e), "Failed to retrieve order list")
