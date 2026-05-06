import logging
from common.tool_cache import tool_cache
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
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


def _next_cal_days(n: int = 3) -> list[str]:
    """Return today + next n days as YYYYMMDD strings, using project timezone (TZ_OFFSET env)."""
    tz_offset = int(os.getenv("TZ_OFFSET", "0"))
    tz = timezone(timedelta(hours=tz_offset))
    today = datetime.now(tz).date()
    return [(today + timedelta(days=i)).strftime("%Y%m%d") for i in range(0, n + 1)]


def _fetch_store_detail_once(shop_id: str, cal_day: str, is_logistics_delivery: bool = False) -> dict:
    """Fetch store_detail for a single (shop_id, cal_day) pair. Returns {} on failure.

    When ``is_logistics_delivery=True``, the backend applies
    ``AND CAL_DAY >= FN_GET_NDATE_STR(SYSDATE, B.SHOP_SEQ)`` so only slots after the
    store-delivery lead time are returned (store-inventory empty + logistics-inventory available).
    """
    try:
        response = get_store_detail(
            client=get_client(),
            shop_id=shop_id,
            cal_day=cal_day,
            is_logistics_delivery=is_logistics_delivery,
        )
        if response.parsed is not None:
            return _to_dict(response.parsed)
    except Exception:
        logger.warning("[_fetch_store_detail_once] Failed for shop_id=%s cal_day=%s", shop_id, cal_day)
    return {}


def _count_available_slots(detail: dict) -> int:
    """Count non-empty available slots in a store_detail response."""
    if not isinstance(detail, dict):
        return 0
    slots = detail.get("available_slots") or detail.get("time_slots") or []
    return len(slots) if isinstance(slots, list) else 0


def _parallel_fetch_store_days(
    shop_ids: list[str],
    cal_days: list[str],
    is_logistics_delivery: bool = False,
    max_workers: int = 9,
) -> dict:
    """Parallel-fetch all (shop_id, cal_day) combinations. Returns {shop_id: {cal_day: detail}}.

    When ``is_logistics_delivery=True``, every BE call applies the store-delivery
    lead-time filter (`AND CAL_DAY >= FN_GET_NDATE_STR(SYSDATE, B.SHOP_SEQ)`). The
    flag is uniform across stores in a batch because logistics inventory is
    goods-level, not per-store, so the caller decides once for the whole call.
    """
    results: dict[str, dict[str, dict]] = {sid: {} for sid in shop_ids}
    pairs = [(sid, day) for sid in shop_ids for day in cal_days]
    if not pairs:
        return results

    with ThreadPoolExecutor(max_workers=min(len(pairs), max_workers)) as executor:
        futures = {
            executor.submit(_fetch_store_detail_once, sid, day, is_logistics_delivery): (sid, day)
            for sid, day in pairs
        }
        for future in as_completed(futures):
            sid, day = futures[future]
            results[sid][day] = future.result()
    return results


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

    Store fields: is_installable (온라인 장착 가능), is_imported_car (수입차 특화점).
    ⚠️ 수입차 특화점: 사용자가 "수입차 특화점/전문매장/전문점/매장, 외제차 특화점/전문매장" 언급 시 imported_car_only=True.

    Args:
        user_xpos (float): X 좌표 (경도).
        user_ypos (float): Y 좌표 (위도).
        radius_km (float): 검색 반경 km (default 10).
        svc_codes (List[str] | None): 서비스 코드 필터 (e.g., ["101", "102"]).
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

        # Truncate to top 5 stores so the LLM's `location` template (max_length=5
        # per LocationTemplate schema) doesn't fail structured-output validation
        # and silently drop the entire response. Sort: is_installable=true first
        # (matters for purchase flows), then by distance_km ascending. Response
        # shape is preserved.
        stores = data.get("stores") if isinstance(data, dict) else None
        if isinstance(stores, list) and len(stores) > 5:
            original_count = len(stores)
            sorted_stores = sorted(
                stores,
                key=lambda s: (
                    not bool(s.get("is_installable", False)),
                    s.get("distance_km") if isinstance(s.get("distance_km"), (int, float)) else float("inf"),
                ),
            )
            data["stores"] = sorted_stores[:5]
            logger.info(
                "[TOOL][get_nearby_stores_tool] Truncated %d stores -> top 5 (installable-first, distance-asc)",
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
    limit: int = 5,
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

    Store fields: is_installable (온라인 장착 가능), is_imported_car (수입차 특화점).

    Args:
        region_code (str | None): 지역명 키워드 (e.g., '서울', '강남', '부산').
        store_nm (str | None): 매장명 키워드 (e.g., '티스테', '극동상사').
        limit (int): 최대 반환 매장 수 (default 5).
        all_my_t_only (bool): True → all my T 매장만. Default False.
        imported_car_only (bool): True → 수입차 특화점만. Default False.
        chl_sct_cd (str | None): F=티스테이션, S=더타이어샵, None=전체.

    Examples:
        - {"region_code": "강남", "store_nm": "티스테", "limit": 5}
        - {"region_code": "서울", "limit": 5}
        - {"region_code": None, "store_nm": "극동상사", "limit": 5}
        - {"region_code": "강남", "limit": 5, "imported_car_only": True}
    """
    # Normalize brand name to Korean equivalent (e.g., "T-Station" → "티스테이션")
    if store_nm:
        store_nm = normalize_brand_name(store_nm)

    logger.info(
        "[TOOL][get_store_list_tool] Called with: region_code=%s, store_nm=%s (normalized), limit=%s, "
        "all_my_t_only=%s, imported_car_only=%s, chl_sct_cd=%s",
        region_code, store_nm, limit, all_my_t_only, imported_car_only, chl_sct_cd,
    )

    try:
        response = get_store_list(
            client=get_client(),
            region_code=region_code,
            store_nm=store_nm,
            limit=limit,
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
def get_store_schedule_tool(
    shop_id: str,
    days: int = 7,
    is_logistics_delivery: bool = False,
    auto_extend_days: int = 14,
):
    """
    Get store reservation schedule for a range of days (parallel fetch).

    Use instead of calling get_store_detail_tool multiple times.
    Fetches TODAY through TODAY+(days-1) in parallel.

    Adaptive auto-extend: if all Phase 1 days have zero installable slots AND auto_extend_days>0,
    automatically fetches the next auto_extend_days days (total window: up to days+auto_extend_days).

    Args:
        shop_id (str): Store ID.
        days (int): Days to fetch from today (default 7, clamped to [1,7]).
        is_logistics_delivery (bool): Same as get_store_detail_tool. Default False.
        auto_extend_days (int): Extra days to scan when Phase 1 is empty (default 14, clamped to [0,21]).

    Examples:
        - {"shop_id": "BXXXXX"}
        - {"shop_id": "FXXXXX", "days": 4}
        - {"shop_id": "BXXXXX", "is_logistics_delivery": true}
    """
    logger.info(
        "[TOOL][get_store_schedule_tool] Called with: shop_id=%s, days=%s, "
        "is_logistics_delivery=%s, auto_extend_days=%s",
        shop_id, days, is_logistics_delivery, auto_extend_days,
    )
    days = max(1, min(days, 7))
    auto_extend_days = max(0, min(auto_extend_days, 21))

    def _fetch_window(cal_days_to_fetch: list[str]) -> list[dict]:
        out: list[dict] = []
        if not cal_days_to_fetch:
            return out
        with ThreadPoolExecutor(max_workers=min(len(cal_days_to_fetch), 9)) as executor:
            futures = {
                executor.submit(
                    get_store_detail,
                    client=get_client(),
                    shop_id=shop_id,
                    cal_day=cal_day,
                    is_logistics_delivery=is_logistics_delivery,
                ): cal_day
                for cal_day in cal_days_to_fetch
            }
            for future in as_completed(futures):
                cal_day = futures[future]
                try:
                    response = future.result()
                    if response.parsed is not None:
                        detail = _to_dict(response.parsed)
                        out.append({
                            "cal_day": cal_day,
                            "available_slots": detail.get("available_slots") or [],
                            "is_installable": detail.get("is_installable", False),
                            "is_tna_delivery": detail.get("is_tna_delivery", False),
                        })
                    else:
                        out.append({"cal_day": cal_day, "available_slots": [], "is_installable": False, "is_tna_delivery": False})
                except Exception:
                    logger.warning("[get_store_schedule_tool] Failed for shop_id=%s cal_day=%s", shop_id, cal_day)
                    out.append({"cal_day": cal_day, "available_slots": [], "is_installable": False, "is_tna_delivery": False})
        return out

    # Phase 1 — initial window
    phase1_cal_days = _next_cal_days(days - 1)
    schedule = _fetch_window(phase1_cal_days)

    # Phase 2 — auto-extend when Phase 1 has no installable slots anywhere
    extended = False
    has_any_slot = any(
        entry.get("is_installable") and (entry.get("available_slots") or [])
        for entry in schedule
    )
    if not has_any_slot and auto_extend_days > 0:
        full_cal_days = _next_cal_days(days + auto_extend_days - 1)
        phase2_cal_days = [d for d in full_cal_days if d not in phase1_cal_days]
        if phase2_cal_days:
            logger.info(
                "[TOOL][get_store_schedule_tool] Phase 1 empty for shop_id=%s; "
                "auto-extending +%d days (%d new days)",
                shop_id, auto_extend_days, len(phase2_cal_days),
            )
            schedule.extend(_fetch_window(phase2_cal_days))
            extended = True

    schedule.sort(key=lambda x: x["cal_day"])
    return _success_response(200, {
        "shop_id": shop_id,
        "schedule": schedule,
        "extended": extended,
        "days_fetched": len(schedule),
    })


@tool
def get_multi_store_schedule_tool(
    shop_id_list: list[str],
    initial_days: int = 2,
    extend_days: int = 1,
    is_logistics_delivery: bool = False,
):
    """
    Get reservation schedule for multiple stores (up to 3) with adaptive day extension.

    Use for "가장 빨리 방문 가능한 매장" queries — fetches all (shop_id × cal_day) pairs in ONE parallel call.
    Use INSTEAD OF calling get_store_detail_tool N×M times.

    Adaptive: Phase 1 fetches initial_days. If ALL stores have zero slots AND extend_days>0,
    Phase 2 extends window by extend_days.

    Args:
        shop_id_list (list[str]): Up to 3 shop IDs (extras truncated).
        initial_days (int): Days to fetch initially (default 2 = TODAY, +1).
        extend_days (int): Extra days if initial window is empty (default 1).
        is_logistics_delivery (bool): True when logistics_qty > 0 for the goods being
            checked (regardless of per-store stock). Backend then applies
            `AND CAL_DAY >= FN_GET_NDATE_STR(SYSDATE, B.SHOP_SEQ)` to all stores in
            this batch. Default False (e.g., logistics_qty == 0). Set this AFTER
            running get_logistics_inventory_tool — do NOT call this tool in parallel
            with the logistics check.

    Example: {"shop_id_list": ["BXXXXX", "FXXXXX", "CXXXXX"], "is_logistics_delivery": true}
    """
    logger.info(
        "[TOOL][get_multi_store_schedule_tool] Called with: shop_id_list=%s, initial_days=%s, "
        "extend_days=%s, is_logistics_delivery=%s",
        shop_id_list, initial_days, extend_days, is_logistics_delivery,
    )

    shop_ids = [sid for sid in (shop_id_list or []) if sid][:3]
    if not shop_ids:
        return _error_response(None, "invalid_input", "shop_id_list is empty")

    initial_days = max(1, min(initial_days, 7))
    extend_days = max(0, min(extend_days, 5))

    # Phase 1 — initial window (e.g., 2 days = TODAY, +1)
    phase1_cal_days = _next_cal_days(initial_days - 1)
    phase1_results = _parallel_fetch_store_days(
        shop_ids, phase1_cal_days, is_logistics_delivery=is_logistics_delivery
    )

    # Per-store empty check: stores that have zero slots across all initial days
    stores_without_slots = [
        sid for sid in shop_ids
        if not any(
            _count_available_slots(phase1_results.get(sid, {}).get(day, {})) > 0
            for day in phase1_cal_days
        )
    ]

    merged: dict[str, dict[str, dict]] = phase1_results
    extended = False
    all_cal_days = list(phase1_cal_days)

    # Phase 2 — extend ONLY the stores whose initial window is empty.
    # Fetching per-store preserves correctness (a store that needs day +2 still
    # gets its +2 data) while avoiding wasted BE calls for stores already filled.
    if stores_without_slots and extend_days > 0:
        full_cal_days = _next_cal_days(initial_days + extend_days - 1)
        phase2_cal_days = [d for d in full_cal_days if d not in phase1_cal_days]
        if phase2_cal_days:
            phase2_results = _parallel_fetch_store_days(
                stores_without_slots, phase2_cal_days, is_logistics_delivery=is_logistics_delivery
            )
            for sid in stores_without_slots:
                merged[sid] = {**phase1_results.get(sid, {}), **phase2_results.get(sid, {})}
            all_cal_days.extend(phase2_cal_days)
            extended = True

    # Shape output: one entry per shop with sorted schedule
    stores_out = []
    for sid in shop_ids:
        schedule = []
        for day in sorted(merged.get(sid, {}).keys()):
            detail = merged[sid].get(day) or {}
            schedule.append({
                "cal_day": day,
                "available_slots": detail.get("available_slots") or [],
                "is_installable": detail.get("is_installable", False),
                "is_tna_delivery": detail.get("is_tna_delivery", False),
            })
        stores_out.append({"shop_id": sid, "schedule": schedule})

    return _success_response(200, {
        "stores": stores_out,
        "extended": extended,
        "days_fetched": len(set(all_cal_days)),
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
