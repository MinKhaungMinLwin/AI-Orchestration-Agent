import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from services.tstation.common.tstation_be_client import get_tstation_be_client
from langchain.tools import tool
from common.tool_cache import tool_cache

from services.tstation.agents.b_discovery_agent._car_no_audit import (
    detect_car_no_mismatch,
    set_registered_car_nos,
)

logger = logging.getLogger(__name__)

# Product Compatibility
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.check_compatibility_api_product_compatible_get import sync_detailed as check_compatibility
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.search_product_api_product_search_get import sync_detailed as search_product
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.get_user_vehicles_api_user_vehicles_get import sync_detailed as get_user_vehicles
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.search_car_model_api_vehicle_search_get import sync_detailed as search_car_model
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.search_car_model_groups_api_vehicle_models_get import sync_detailed as search_car_model_groups
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.get_car_trims_api_vehicle_trims_get import sync_detailed as get_car_trims

# Product Description
from common.tstation_be_api_client.hkt_api_client.api.product_description_af_상품_설명.get_description_api_product_detail_goods_no_get import sync_detailed as get_product_description

# Product Recommendation
from common.tstation_be_api_client.hkt_api_client.api.product_recommendation_af_상품_추천.get_recommendations_api_product_recommend_get import sync_detailed as get_products_recommendations
from common.tstation_be_api_client.hkt_api_client.api.product_recommendation_af_상품_추천.get_best_sellers_api_product_best_sellers_get import sync_detailed as get_best_sellers
from common.tstation_be_api_client.hkt_api_client.models import BestSellerPeriod
from common.tstation_be_api_client.hkt_api_client.models import RcmdType


# Event/Deal
from common.tstation_be_api_client.hkt_api_client.api.event_deal_af_이벤트_및_기획전_조회.get_events_api_events_get import sync_detailed as get_events
from common.tstation_be_api_client.hkt_api_client.api.event_deal_af_이벤트_및_기획전_조회.get_deals_api_events_deals_get import sync_detailed as get_deals
from common.tstation_be_api_client.hkt_api_client.api.event_deal_af_이벤트_및_기획전_조회.get_event_applicable_products_multi_api_events_applicable_products_get import sync_detailed as get_event_applicable_products
from common.tstation_be_api_client.hkt_api_client.api.event_deal_af_이벤트_및_기획전_조회.get_product_applicable_events_api_events_applicable_events_get import sync_detailed as get_product_applicable_events

# Price
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_discount_compare_api_prices_discount_compare_get import sync_detailed as get_discount_compare
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_price_api_prices_final_get import sync_detailed as get_price

# Member Car Info
from common.tstation_be_api_client.hkt_api_client.api.member_af_회원_정보_조회.get_member_cars_api_member_cars_get import sync_detailed as get_member_cars


def get_client() -> AuthenticatedClient:
    """Get authenticated client for tstation-be API."""
    return get_tstation_be_client()


DOMAIN_TOOL_MAP = {
    "discovery": {
        # Product Compatibility
        "check_compatibility",
        "search_product",
        "get_user_vehicles",
        "get_my_cars",
        "search_car_model",

        # Product Recommendation
        "get_recommendations",

        # Product Description
        "get_description",

        # Event/Deal
        "get_events",
        "get_deals",
        "get_event_applicable_products",
        "get_product_applicable_events",
    },
    "transaction": {
        # Price
        "get_price",

        # Inventory
        "get_logistics_inventory",
        "get_md_inventory",
        "get_store_inventory",

        # Store
        "get_nearby_stores",
        "get_store_list",
        "get_store_detail",
    },
    "order": {
        # Store
        "get_nearby_stores",
        "get_store_list",
        "get_store_detail",

        # Quick Order
        "create_quick_order",

        # Order / Delivery
        "get_order_delivery",
    },
    "support": {
        # FAQ
        "get_faq",

        # Escalation
        "escalate",
    }
}


def _to_dict(res: Any) -> Any:
    return res.to_dict() if hasattr(res, 'to_dict') else (res.model_dump() if hasattr(res, 'model_dump') else res)


def _error_response(http_status: int | None, reason: str, message: str) -> dict:
    return {"status": "error", "http_status": http_status, "reason": reason, "message": message}


def _success_response(http_status: int, data: Any) -> dict:
    return {"status": "success", "http_status": http_status, "data": data}


# Whitelist of fields kept in product items returned to the LLM. Everything
# else is stripped to keep tool-result payload compact (~10x reduction on a
# 5-item recommendation turn). Detail content (descriptions, full reviews) is
# still reachable via get_product_description_tool when the user explicitly asks.
_TRIM_KEEP_FIELDS: frozenset[str] = frozenset({
    # Identity
    "goods_no", "goods_nm", "title",
    # Product recency
    "sys_reg_dtime",
    # Tire size — used by the agent to differentiate same-name SKUs in card titles
    "tire_size_1", "tire_size_2",
    # Visual / pricing
    "image_url", "price", "sale_prc", "extra_fvr_sale_prc", "extra_fvr_sale_per",
    # Scoring used for sort priority and rcmd_type matching
    "tot_scr",
    "t_comfort", "t_silence", "t_life_span", "t_fuel_eff_convert",
    "wet", "t_snow", "t_ice",
    "t_highspd", "t_highspd_cd", "t_high_hand_avg",
    "t_com_sil_avg", "t_com_cvs", "t_milg_cvs",
    "t_wgt_idx", "t_wgt_idx_kg", "t_tray_ware", "t_rlx_isn_yn",
    # Categorical attributes referenced by the agent / template_mapper
    "goods_pfm_nm", "season_nm", "car_knd_nm", "prc_grd_nm", "wrt_grte_term",
    # EU 소음 라벨 (정숙성 점수 t_silence/t_com_sil_avg 와 별개. 표시용)
    "label_pnwave", "label_pnwave_nm", "label_pndb",
    # Rating / review (used for cards and sort_by="rating_desc"/"review_desc")
    "rating_avg", "rate", "review_count",
    # 상품 등록 일시 — used to identify newest product among same-keyword results
    "sys_reg_dtime",
})


# Sort key functions for user-intent-driven product ordering.
# Applied AFTER BE response + description enrichment, so all items have
# extra_fvr_sale_prc / rating_avg / review_count populated from `_fetch_description`.
# Missing values sort last for ascending (inf), first for descending (negated 0).
_SORT_KEY_FUNCS: dict[str, Any] = {
    # 가장 저렴한 / 제일 싼 / 최저가 → 할인가 오름차순 (없으면 맨 뒤)
    "price_asc": lambda x: (x.get("extra_fvr_sale_prc") or x.get("price") or float("inf")),
    # 비싼 순 / 고가 → 할인가 내림차순
    "price_desc": lambda x: -(x.get("extra_fvr_sale_prc") or x.get("price") or 0),
    # 평점 높은 순 / 별점 좋은 → rating_avg 내림차순
    "rating_desc": lambda x: -(x.get("rating_avg") or x.get("rate") or 0),
    # 리뷰 많은 순 / 후기 많은 → review_count 내림차순
    "review_desc": lambda x: -(x.get("review_count") or 0),
}


def _sort_items(items: list[dict], sort_by: str | None) -> list[dict]:
    """Sort product items based on user intent.

    Supported sort_by values:
      - price_asc: 가장 저렴한 순 (cheapest first)
      - price_desc: 비싼 순 (most expensive first)
      - rating_desc: 평점 높은 순 (highest rating first)
      - review_desc: 리뷰 많은 순 (most reviews first)

    Unknown / None sort_by passes through unchanged so the BE-determined
    rcmd_type ordering is preserved when the user does not express a sort
    intent.
    """
    if not sort_by or not items:
        return items
    if sort_by == "newest_desc":
        return sorted(items, key=lambda x: x.get("sys_reg_dtime") or "", reverse=True)
    key_func = _SORT_KEY_FUNCS.get(sort_by)
    if key_func is None:
        logger.warning("[_sort_items] Unknown sort_by=%s; passing through", sort_by)
        return items
    return sorted(items, key=key_func)


def _filter_by_price(
    items: list[dict],
    min_price: int | None,
    max_price: int | None,
) -> list[dict]:
    """Filter items by effective price (sale price preferred over original).

    Items with no price information are excluded when a price filter is active —
    we cannot verify they are within budget.

    Applied BEFORE _enrich_items_with_descriptions to avoid fetching descriptions
    for items that will be discarded. extra_fvr_sale_prc comes from the main
    search/recommendation BE response so it is available on raw items.
    """
    if not min_price and not max_price:
        return items
    result = []
    for item in items:
        effective_price = item.get("extra_fvr_sale_prc") or item.get("price") or 0
        if not effective_price:
            continue
        if min_price and effective_price < min_price:
            continue
        if max_price and effective_price > max_price:
            continue
        result.append(item)
    return result


def _slim_product_item(item: dict) -> dict:
    """Strip noise fields from a product item before returning to the LLM.

    Drops pc_prod_remark_desc, pc_prod_tech_desc, slogan, images (full array),
    reviews, nested rating object, and any unknown future bloat. Keeps only
    fields in _TRIM_KEEP_FIELDS.
    """
    return {k: v for k, v in item.items() if k in _TRIM_KEEP_FIELDS}


# brand_cd 가 이미 브랜드 필터링을 수행하는데 keyword 에도 한글 브랜드명을
# 넣으면 GOODS_NM LIKE '%브리지스톤%' 매칭에서 0건이 발생한다 (DB GOODS_NM 에는
# 한글 브랜드명이 저장돼 있지 않고 모델명만 들어 있음). 이런 경우를 방어하기 위해
# 키워드가 브랜드명 단어들로만 구성됐는지 검사한다.
_BRAND_ONLY_WORDS: frozenset[str] = frozenset({
    # Korean brand names
    "한국타이어", "한국", "라우펜", "미쉐린", "피렐리",
    "브리지스톤", "브릿지스톤", "콘티넨탈", "굿이어",
    # English / Romanized brand names
    "hankook", "laufenn", "michelin", "pirelli",
    "bridgestone", "continental", "conti", "goodyear",
})


def _strip_brand_only_keyword(keyword: str | None) -> str | None:
    """키워드가 브랜드명 단어들로만 이루어진 경우 None 반환.

    예시:
      "브리지스톤"        → None
      "  미쉐린 "         → None
      "Pirelli"           → None
      "브리지스톤 포텐자" → "브리지스톤 포텐자" (모델명 포함 시 원본 유지)

    brand_cd 파라미터가 이미 브랜드 필터링을 담당하므로, 브랜드명만 들어온 경우
    keyword 를 비워 GOODS_NM LIKE 매칭에서 모든 후보가 제외되는 0-건 버그를 방지한다.
    모델명이 함께 있을 때는 BE 의 alias 확장과 LIKE 매칭으로 모델명을 잡아내므로
    원본을 그대로 전달한다.
    """
    if not keyword:
        return None
    tokens = [t for t in keyword.strip().lower().split() if t]
    if not tokens:
        return None
    if all(t in _BRAND_ONLY_WORDS for t in tokens):
        return None
    return keyword


def _fetch_description(goods_no: str, client: AuthenticatedClient) -> dict:
    """Fetch product description and return flat fields the LLM whitelist keeps.

    The description endpoint returns nested `images: [{img_path_nm, thnl_path_nm}, ...]`
    and `rating: {review_count, rating_avg}` objects. The LLM whitelist
    (`_TRIM_KEEP_FIELDS`) keeps only flat fields, so we flatten here:
      - `image_url` ← first image's full URL (img_path_nm > thnl_path_nm fallback)
      - `rating_avg` / `rate` ← rating.rating_avg (rate is the FE alias)
      - `review_count` ← rating.review_count (used for sort_by="review_desc")
    """
    try:
        response = get_product_description(client=client, goods_no=goods_no)
        if response.parsed is None:
            return {}
        desc = _to_dict(response.parsed)
        images = desc.get("images") or []
        first_image = images[0] if images else {}
        image_url = first_image.get("img_path_nm") or first_image.get("thnl_path_nm") or ""
        rating = desc.get("rating") or {}
        rating_avg = rating.get("rating_avg") or 0
        review_count = rating.get("review_count") or 0
        return {
            "image_url": image_url,
            "rating_avg": rating_avg,
            "rate": rating_avg,
            "review_count": review_count,
        }
    except Exception:
        logger.warning("[_fetch_description] Failed for goods_no=%s", goods_no)
        return {}


def _fetch_price_fields(goods_no: str, client: AuthenticatedClient) -> dict:
    """Fetch price fields needed to display discount-card backup data."""
    try:
        response = get_price(client=client, goods_no=goods_no, member_type=None)
        if response.parsed is None:
            return {}
        price = _to_dict(response.parsed)
        return {
            key: price[key]
            for key in ("sale_prc", "extra_fvr_sale_prc", "extra_fvr_sale_per")
            if price.get(key) not in (None, "", 0)
        }
    except Exception:
        logger.warning("[_fetch_price_fields] Failed for goods_no=%s", goods_no)
        return {}


def _enrich_items_with_price_fields(items: list[dict]) -> list[dict]:
    """Fill missing sale_prc for discount recommendations.

    Recommendation rows already provide discount price/rate, but not always the
    base sale_prc. The product card needs sale_prc to expose originalPrice and
    discountAmount, so enrich only this narrow discount-card path.
    """
    if not items:
        return items

    goods_nos = [
        item.get("goods_no")
        for item in items
        if item.get("goods_no") and not item.get("sale_prc")
    ]
    if not goods_nos:
        return items

    price_map: dict[str, dict] = {}
    client = get_client()
    with ThreadPoolExecutor(max_workers=min(len(goods_nos), 10)) as executor:
        futures = {executor.submit(_fetch_price_fields, gno, client): gno for gno in goods_nos}
        for future in as_completed(futures):
            gno = futures[future]
            price_map[gno] = future.result()

    enriched: list[dict] = []
    for item in items:
        goods_no = item.get("goods_no")
        merged = dict(item)
        for key, value in price_map.get(goods_no, {}).items():
            if merged.get(key) in (None, "", 0):
                merged[key] = value
        enriched.append(merged)
    return enriched


def _enrich_items_with_descriptions(items: list[dict]) -> list[dict]:
    """Parallel-fetch descriptions for each item, merge into item dicts, then slim.

    Enrichment fetch is preserved so future field needs can be served by
    widening _TRIM_KEEP_FIELDS — the LLM-visible payload is filtered to
    that whitelist to prevent context bloat (HTML descs, reviews, etc.).
    """
    if not items:
        return items

    goods_nos = [item.get("goods_no") for item in items if item.get("goods_no")]
    if not goods_nos:
        return [_slim_product_item(item) for item in items]

    desc_map: dict[str, dict] = {}
    client = get_client()
    with ThreadPoolExecutor(max_workers=min(len(goods_nos), 20)) as executor:
        futures = {executor.submit(_fetch_description, gno, client): gno for gno in goods_nos}
        for future in as_completed(futures):
            gno = futures[future]
            desc_map[gno] = future.result()

    return [
        _slim_product_item({**item, **desc_map.get(item.get("goods_no"), {})})
        for item in items
    ]


@tool
@tool_cache(ttl=3600)
def check_compatibility_tool(goods_no: str, car_no: str, owner_nm: str):
    """
    차량-상품 타이어 호환 검증.

    When to use:
    - ONLY when tire_size is NOT yet confirmed AND user explicitly provides car_no + owner_nm

    When NOT to use:
    - If tire_size is already confirmed → compare product's tire_size directly (no tool needed)
    - If user only mentions car model name → use CAR MODEL DISPLAY instead

    Args:
        goods_no (str): 상품 번호.
        car_no (str): 차량 번호 (e.g., "12가3456").
        owner_nm (str): 차량 소유주명.

    Example: {"goods_no": "GXXXXXXXXXXXX", "car_no": "12가3456", "owner_nm": "홍길동"}
    """
    logger.debug("[TOOL][check_compatibility_tool] Called with: goods_no=%s, car_no=%s, owner_nm=%s", goods_no, car_no, owner_nm)

    try:
        response = check_compatibility(client=get_client(), goods_no=goods_no, car_no=car_no, owner_nm=owner_nm)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to check tire compatibility"
            )
        # logger.debug("[TOOL][check_compatibility_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][check_compatibility_tool] Failed")
        return _error_response(None, str(e), "Failed to check tire compatibility")


@tool
@tool_cache(ttl=600)
def search_product_tool(
    keyword: str | None = None,
    limit: int = 10,
    size: str | None = None,
    brand_cd: str = "HK",
    sort_by: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
):
    """
    상품 검색.

    When to use:
    - User searches for a specific tire by name/keyword
    - Resolving goods_no for price/stock/order handoff (Flow C/D)
    - User mentions ONLY a brand name with size → keyword=None, use brand_cd + size

    Important: keyword는 **한글로 전달**한다. BE는 한글 GOODS_NM에 LIKE 매칭하고
    alias.json으로 한글→영문을 자동 확장한다 (영문→한글 역확장은 없음).
    - 사용자가 한글로 입력 → 그대로 전달 (벤투스 S2, 다이나프로 HPX, 키너지 EX 등)
    - 사용자가 영문/로마자로 입력 → 한글로 변환 (Ventus→벤투스, Kinergy→키너지,
      Optimo→옵티모, Dynapro→다이나프로, iON→아이온)
    - 모델 코드(S1, S2, evo, evo3, HPX, EX 등)는 원형 유지
    - ❌ NEVER translate Korean → English
    - ❌ NEVER put a brand name into keyword — use brand_cd instead

    Brand codes: HK=Hankook (default), LF=Laufenn, MC=Michelin, PI=Pirelli,
                 BS=Bridgestone, CT=Continental, GY=Goodyear.
    Unsupported brands (금호, 넥센 etc.) → decline, do not search.

    Args:
        keyword (str | None): 검색할 제품명 키워드 — Korean preferred (예: '벤투스 S2', '다이나프로 HPX', '키너지 EX').
            브랜드명만 있는 경우 None 으로 두고 brand_cd 로 필터링한다.
            방어적으로, 브랜드명만 들어오면 자동으로 None 으로 정규화된다.
        limit (int): 반환할 최대 상품 수 Default: 10.
        size (str | None): 타이어 사이즈 필터 (예: '225/45R17' 또는 '2254517'). Optional.
        brand_cd (str): 브랜드 코드. Default: HK.
            - HK: Hankook 한국타이어
            - LF: Laufenn 라우펜
            - MC: Michelin 미쉐린
            - PI: Pirelli 피렐리
            - BS: Bridgestone 브리지스톤
            - CT: Continental 콘티넨탈
            - GY: Goodyear 굿이어
        sort_by (str | None): 정렬 의도. 사용자가 정렬을 명시하면 전달한다. Optional.
            - "price_asc": 가장 저렴한 순 (가장 저렴한, 제일 싼, 최저가, 싼 것부터)
            - "price_desc": 비싼 순 (비싼 것부터, 고가, 프리미엄 순)
            - "rating_desc": 평점 높은 순 (별점 좋은, 평점순)
            - "review_desc": 리뷰 많은 순 (후기 많은, 리뷰순)
            None 이면 BE 기본 순서 유지.
        min_price (int | None): 최소 가격 필터 (원 단위). Optional.
            예: 200_000 ("20만원 이상")
        max_price (int | None): 최대 가격 필터 (원 단위). Optional.
            예: 300_000 ("30만원 이하")

    Notes:
        - 가격 필터는 BE 응답 후 클라이언트 사이드에서 extra_fvr_sale_prc (할인가) 기준으로 적용.
        - 가격 필터 활성 시 BE에서 limit×4 개 fetch 후 필터링하여 limit 개 반환.
        - 가격 정보 없는 상품은 필터 적용 시 제외됨.

    Examples:
        - {"keyword": "벤투스 S2", "limit": 5, "size": "225/45R17"}
        - {"keyword": "다이나프로 HPX", "limit": 5, "size": "235/55R19"}
        - {"keyword": "Pilot Sport", "limit": 5, "brand_cd": "MC"}
        - {"keyword": "s1 evo3", "limit": 5}
        - {"size": "235/55R19", "brand_cd": "BS"}  # 브리지스톤 사이즈만으로 검색
        - {"size": "225/45R17", "sort_by": "price_asc"}  # 가장 저렴한 순으로 정렬
        - {"keyword": "벤투스", "size": "225/45R17", "sort_by": "rating_desc"}  # 평점 높은 순
        - {"brand_cd": "HK", "max_price": 300_000, "sort_by": "price_asc"}  # 30만원 이하 한국타이어
        - {"keyword": "벤투스 S2", "min_price": 200_000, "max_price": 300_000}  # 20~30만원 사이

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...}
              or {"status": "no_results", "reason": "no_products_in_price_range", "min_price": ..., "max_price": ...}
              or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    normalized_keyword = _strip_brand_only_keyword(keyword)
    if normalized_keyword != keyword:
        logger.debug(
            "[TOOL][search_product_tool] Stripped brand-only keyword: %r → None (brand_cd=%s)",
            keyword, brand_cd,
        )
    has_price_filter = bool(min_price or max_price)
    has_newest_sort = sort_by == "newest_desc"
    fetch_limit = limit * 4 if has_price_filter else limit
    if has_newest_sort:
        fetch_limit = max(fetch_limit, 100)
    logger.debug(
        "[TOOL][search_product_tool] Called with: keyword=%s, limit=%s, size=%s, brand_cd=%s, sort_by=%s, min_price=%s, max_price=%s",
        normalized_keyword, limit, size, brand_cd, sort_by, min_price, max_price,
    )

    try:
        response = search_product(client=get_client(), keyword=normalized_keyword, limit=fetch_limit, size=size, brand_cd=brand_cd)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to search products"
            )
        # logger.debug("[TOOL][search_product_tool] Response: %s", response.parsed)
        data = _to_dict(response.parsed)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            if has_price_filter:
                data["items"] = _filter_by_price(data["items"], min_price, max_price)
                if not data["items"]:
                    return {"status": "no_results", "reason": "no_products_in_price_range", "min_price": min_price, "max_price": max_price}
            data["items"] = _enrich_items_with_descriptions(data["items"])
            data["items"] = _sort_items(data["items"], sort_by)
            if has_price_filter or has_newest_sort:
                data["items"] = data["items"][:limit]
        return _success_response(response.status_code, data)
    except Exception as e:
        logger.exception("[TOOL][search_product_tool] Failed")
        return _error_response(None, str(e), "Failed to search products")


@tool
@tool_cache(ttl=3600)
def get_user_vehicles_tool(car_no: str, owner_nm: str):
    """
    차량번호+소유주명으로 차량 조회.

    When to use:
    - FALLBACK only: after get_my_cars_tool returns 0 cars AND user provides car_no + owner_nm
    - Also when user provides someone else's vehicle number

    When NOT to use:
    - Do NOT use before trying get_my_cars_tool first
    - Do NOT use if tire_size is already confirmed

    Args:
        car_no (str): 차량번호 (e.g., "12가3456").
        owner_nm (str): 소유주명.

    Example: {"car_no": "12가3456", "owner_nm": "홍길동"}
    """
    logger.debug("[TOOL][get_user_vehicles_tool] Called with: car_no=%s, owner_nm=%s", car_no, owner_nm)

    try:
        response = get_user_vehicles(client=get_client(), car_no=car_no, owner_nm=owner_nm)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get user vehicles"
            )
        # logger.debug("[TOOL][get_user_vehicles_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_user_vehicles_tool] Failed")
        return _error_response(None, str(e), "Failed to get user vehicles")


@tool_cache(ttl=600)
def _get_my_cars_cached(mbr_no: str):
    """Internal cached BE call. Public wrapper applies the audit hook below."""
    logger.debug("[TOOL][get_my_cars_tool] Called with: mbr_no=%s", mbr_no)

    try:
        response = get_member_cars(client=get_client(), mbr_no=mbr_no)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get member cars"
            )
        # logger.debug("[TOOL][get_my_cars_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_my_cars_tool] Failed")
        return _error_response(None, str(e), "Failed to get member cars")


@tool
def get_my_cars_tool(mbr_no: str):
    """
    사용자 등록 차량 조회 (회원번호 기준).

    When to use:
    - FIRST step for ANY vehicle-related request (tire recommendation, compatibility, price by vehicle)
    - Call immediately using mbr_no from JWT — do NOT ask user questions first

    Result handling:
    - 1 car → auto-select, use tire_size_fr and car_lnc_cd
    - 2+ cars → show ALL in numbered list, wait for user to select
    - 0 cars → guide user to provide car_no+owner_nm or car model name

    Args:
        mbr_no (str): 회원번호 (from user context).

    Example: {"mbr_no": "MXXXXXXXXX"}
    """
    result = _get_my_cars_cached(mbr_no)
    # Record registered car_no list for downstream mismatch audit. Runs on
    # cache hit as well, so subsequent tools in the same turn always see it.
    if isinstance(result, dict) and result.get("status") == "success":
        data = result.get("data") or {}
        items = data.get("items") if isinstance(data, dict) else None
        if isinstance(items, list):
            car_nos = [it.get("car_no", "") for it in items if isinstance(it, dict)]
            set_registered_car_nos(car_nos)
    return result


@tool
@tool_cache(ttl=3600)
def search_car_model_tool(keyword: str, limit: int = 20):
    """
    차량 모델 검색 (car_lnc_cd 조회용).

    When to use:
    - ONLY after get_user_vehicles_tool fails as a last fallback to get car_lnc_cd
    - When another flow explicitly requires car_lnc_cd lookup

    When NOT to use:
    - Do NOT call when user just mentions a car model name → use search_car_model_groups_tool (CAR MODEL DISPLAY)
    - Do NOT call as first step for car model mentions

    Args:
        keyword (str): 차량 모델명 키워드 (한국어, e.g., '소나타', '그랜저').
        limit (int): 최대 결과 수. Default: 20.

    Example: {"keyword": "소나타", "limit": 20}
    """
    logger.debug("[TOOL][search_car_model_tool] Called with: keyword=%s, limit=%s", keyword, limit)

    try:
        response = search_car_model(client=get_client(), keyword=keyword, limit=limit)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to search car models"
            )
        # logger.debug("[TOOL][search_car_model_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][search_car_model_tool] Failed")
        return _error_response(None, str(e), "Failed to search car models")


@tool
@tool_cache(ttl=3600)
def search_car_model_groups_tool(keyword: str):
    """
    차종 모델 그룹 검색 — CAR MODEL DISPLAY step 1.

    When to use:
    - User mentions a car model name (e.g., "K7", "소나타", "팰리세이드") for tire recommendation
    - Step 1 of 2: returns model groups with year ranges → user selects → call get_car_trims_tool

    When NOT to use:
    - Do NOT call when user already provided car_no + owner_nm (use get_user_vehicles_tool)
    - Do NOT call when car is already confirmed from get_my_cars_tool result

    Each group has car_model_det (e.g., "더 뉴 K7(VG)"), year_from, year_to, trim_count.

    Args:
        keyword (str): 차량 모델명 키워드 (e.g., 'K7', '소나타', '팰리세이드').

    Example: {"keyword": "K7"}
    """
    logger.debug("[TOOL][search_car_model_groups_tool] Called with: keyword=%s", keyword)

    try:
        response = search_car_model_groups(client=get_client(), keyword=keyword)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to search car model groups"
            )
        # logger.debug("[TOOL][search_car_model_groups_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][search_car_model_groups_tool] Failed")
        return _error_response(None, str(e), "Failed to search car model groups")


@tool
@tool_cache(ttl=3600)
def get_car_trims_tool(car_model_det: str):
    """
    차량 트림 목록 조회 — CAR MODEL DISPLAY step 2.

    When to use:
    - After search_car_model_groups_tool, user selects a car_model_det
    - Step 2 of 2: returns trims with car_lnc_cd AND tire_size_fr/re

    If user selects a trim → use tire_size_fr for get_products_recommendations_tool.
    If only 1 trim → auto-select and proceed to RECOMMEND ENGINE.

    Args:
        car_model_det (str): 차량 상세 모델명 from search_car_model_groups_tool (e.g., "더 뉴 K7(VG)").

    Example: {"car_model_det": "더 뉴 K7(VG)"}
    """
    logger.debug("[TOOL][get_car_trims_tool] Called with: car_model_det=%s", car_model_det)

    try:
        response = get_car_trims(client=get_client(), car_model_det=car_model_det)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get car trims"
            )
        # logger.debug("[TOOL][get_car_trims_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_car_trims_tool] Failed")
        return _error_response(None, str(e), "Failed to get car trims")


@tool
@tool_cache(ttl=600)
def get_product_description_tool(goods_no: str):
    """
    Get detailed product information (features, tech description, slogan, images, rating, reviews).

    Args:
        goods_no (str): Product number.

    Example: {"goods_no": "GXXXXXXXXXXXX"}
    """
    logger.debug("[TOOL][get_product_description_tool] Called with: goods_no=%s", goods_no)

    try:
        response = get_product_description(client=get_client(), goods_no=goods_no)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get product description"
            )
        # logger.debug("[TOOL][get_product_description_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_product_description_tool] Failed")
        return _error_response(None, str(e), "Failed to get product description")


@tool
@tool_cache(ttl=300)
def get_products_recommendations_tool(
    rcmd_type: RcmdType,
    limit: int = 3,
    brand_cd: str = "HK",
    car_lnc_cd: str | None = None,
    tire_size: str | None = None,
    sort_by: str | None = None,
    season_nm: str | None = None,
    pfm_nm: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
):
    """
    Product Recommendation — top N products by rcmd_type.

    제휴 회원 여부(entr_yn)/제휴사 번호(entr_no)는 JWT에서 자동 추출됩니다.

    rcmd_type values:
    - tstation: 티스테이션 추천 (TOT_SCR 높은 순)
    - discount: 최고 할인율 (EXTRA_FVR_SALE_PER 높은 순)
    - value: 가성비 (할인가 ≤200,000원, 수명·연비 우선)
    - wet: 빗길 (WET 높은 순)
    - snow: 눈길/빙판 (T_SNOW, T_ICE 높은 순)
    - high_speed: 고속 주행 (T_HIGHSPD 높은 순)
    - handling: 핸들링 (T_HIGH_HAND_AVG 높은 순)
    - low_vibration: 진동 적음/정숙 (T_COM_SIL_AVG, T_COM_CVS 높은 순)
    - performance: 퍼포먼스/스포츠 (GOODS_PFM_NM='SPORT')
    - commute: 출퇴근 (SEASON_NM='사계절', T_MILG_CVS 높은 순)
    - long_distance: 장거리 (T_COM_SIL_AVG, T_MILG_CVS 높은 순)
    - urban: 도심 주행 (SEASON_NM='사계절', GOODS_PFM_NM='COMFORT')
    - family: 가족용 (GOODS_PFM_NM IN ('COMFORT','RUNFLAT'))
    - ev: 전기차용 (CAR_KND_NM='전기차')
    - heavy_load: 짐 많이 싣는 차 (T_WGT_IDX, T_WGT_IDX_KG 높은 순)
    - weekend: 주말용 (SEASON_NM='사계절', T_TRAY_WARE 높은 순)
    - safe_kids: 안전 (T_RLX_ISN_YN='O', 정숙·하중 우선)
    - all_weather: 전천후 (WET, T_SNOW, T_ICE 높은 순)
    - warranty: 워런티 가능 (WRT_GRTE_TERM 긴 순)
    - summer: 여름용 (SEASON_NM='여름', WET·T_HIGH_HAND_AVG 높은 순)

    Args:
        rcmd_type (RcmdType): Recommendation type.
        limit (int, optional): Number of products to return. Default is 3, maximum is 100.
        brand_cd (str, optional): Brand code. Default is HK.
            - HK: Hankook 한국타이어 (Hankook Tire)
            - LF: Laufenn 라우펜
            - MC: Michelin 미쉐린
            - PI: Pirelli 피렐리
            - BS: Bridgestone 브리지스톤
            - CT: Continental 콘티넨탈
            - GY: Goodyear 굿이어
        car_lnc_cd (str | None, optional): 차량 런칭 코드. 입력 시 타이어 사이즈보다 우선 적용
        tire_size (str | None, optional): 타이어 사이즈 문자열 (예: "245/45R18", 공백/소문자 허용)
        sort_by (str | None, optional): 사용자 의도 기반 정렬. rcmd_type 과 독립적으로 동작하며,
            BE 응답 + description enrichment 후 클라이언트 측에서 정렬한다.
            - "price_asc": 가장 저렴한 순 (가장 저렴한, 제일 싼, 최저가, 싼 것부터)
            - "price_desc": 비싼 순 (비싼 것부터, 고가, 프리미엄 순)
            - "rating_desc": 평점 높은 순 (별점 좋은, 평점순)
            - "review_desc": 리뷰 많은 순 (후기 많은, 리뷰순)
            None 이면 rcmd_type 의 BE 정렬 그대로 유지.
        season_nm (str | None, optional): 계절 직교 필터. rcmd_type 과 직교로 적용된다.
            - "여름": 여름용 타이어만 (PR_GOODS_BASE.SEASON_NM='여름')
            - "겨울": 겨울용 타이어만 (PR_GOODS_BASE.SEASON_NM='겨울')
            - "사계절": 사계절 타이어만 (PR_GOODS_BASE.SEASON_NM='사계절')
            - "올웨더": 올웨더 패턴만 (PR_PATTERN_BASE.ALLWEATHER_YN='Y')
              ⚠️ 사용자가 "올웨더 / all-weather / 올시즌 / 전천후" 라고 명시하면
              `season_nm="올웨더"` 사용. "사계절" 이라고 명시하면 `season_nm="사계절"`.
            ⚠️ 신규(동적) rcmd_type 에만 적용됨 (tstation/discount/value 제외).
            "여름용 타이어 추천" 단일 의도면 rcmd_type="summer" 사용 (필터 불필요).
        pfm_nm (str | None, optional): 성능 등급 직교 필터. rcmd_type 과 직교로 적용된다.
            - "SPORT": 스포츠/퍼포먼스
            - "COMFORT": 편안한 승차감
            - "RUNFLAT": 런플랫
            ⚠️ 신규(동적) rcmd_type + "tstation" 에 적용됨 (discount/value 는 미적용).
            "퍼포먼스 타이어 추천" 단일 의도면 rcmd_type="performance" 사용 (필터 불필요).
            "런플랫 타이어 추천" 단일 의도면 rcmd_type="tstation" + pfm_nm="RUNFLAT" 사용
              (rcmd_type="family" 는 데이터상 RUNFLAT 결과 0건이므로 사용 금지).
        min_price (int | None, optional): 최소 가격 필터 (원 단위). Optional.
            예: 200_000 ("20만원 이상")
        max_price (int | None, optional): 최대 가격 필터 (원 단위). Optional.
            예: 300_000 ("30만원 이하")

    Combined-intent guidance (직교 필터):
        - "퍼포먼스 좋은 여름용" → rcmd_type="performance", season_nm="여름"
        - "조용한 사계절" → rcmd_type="low_vibration", season_nm="사계절"
        - "런플랫 중에 빗길 강한" → rcmd_type="wet", pfm_nm="RUNFLAT"
        - "30만원 이하 사계절 타이어" → rcmd_type="all_weather", max_price=300_000
        - "20만원~30만원 가성비 타이어" → rcmd_type="value", min_price=200_000, max_price=300_000

    Notes:
        - 가격 필터는 BE 응답 후 클라이언트 사이드에서 extra_fvr_sale_prc (할인가) 기준으로 적용.
        - 가격 필터 활성 시 BE에서 limit×4 개 fetch 후 필터링하여 limit 개 반환.

    Examples:
        - {"rcmd_type": "tstation", "limit": 3, "brand_cd": "HK"}
        - {"rcmd_type": "wet", "limit": 5, "brand_cd": "HK", "tire_size": "245/45R18"}
        - {"rcmd_type": "ev", "limit": 5, "brand_cd": "HK", "car_lnc_cd": "LNCXXXXXX"}
        - {"rcmd_type": "warranty", "limit": 5, "brand_cd": "HK"}
        - {"rcmd_type": "all_weather", "tire_size": "245/45R18", "sort_by": "price_asc"}  # 가장 저렴한 사계절 타이어
        - {"rcmd_type": "tstation", "tire_size": "225/45R17", "sort_by": "rating_desc"}   # 평점 높은 순
        - {"rcmd_type": "performance", "season_nm": "여름"}  # 퍼포먼스 좋은 여름용
        - {"rcmd_type": "tstation", "pfm_nm": "RUNFLAT", "limit": 3}  # 런플랫 단독 추천
        - {"rcmd_type": "wet", "pfm_nm": "RUNFLAT"}        # 런플랫 중 빗길 강한 것
        - {"rcmd_type": "value", "max_price": 300_000, "sort_by": "price_asc"}  # 30만원 이하 가성비
        - {"rcmd_type": "tstation", "tire_size": "225/45R17", "min_price": 200_000, "max_price": 300_000}  # 20~30만원 사이

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...}
              or {"status": "no_results", "reason": "no_products_in_price_range", "min_price": ..., "max_price": ...}
              or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    # Deterministic guard: if the user named a car_no in this turn and it
    # does not match any registered car, short-circuit before issuing the
    # BE call. The LLM has repeatedly ignored prompt-only rules and proceeded
    # to recommend tires for an unrelated registered car.
    mismatched_plate = detect_car_no_mismatch()
    if mismatched_plate is not None:
        logger.info(
            "[TOOL][get_products_recommendations_tool] BLOCKED by car_no audit: "
            "user requested %s but it is not in get_my_cars_tool result",
            mismatched_plate,
        )
        return _error_response(
            http_status=412,
            reason="CAR_NO_MISMATCH",
            message=(
                f"유저가 명시한 차량번호 '{mismatched_plate}' 가 get_my_cars_tool 의 등록 차량 목록에 없습니다. "
                "이 차량에 대해 추천을 진행하지 마세요. 대신 listCar 템플릿으로 등록된 차량만 노출하고 "
                f"assistantResponse 를 정확히 다음과 같이 작성하세요: "
                f"\"**{mismatched_plate}** 은(는) 등록된 차량 목록에 없어요. "
                "등록된 차량 중에서 골라주시거나, 정확한 차량번호+소유주명을 다시 알려주세요 😊\""
            ),
        )

    has_price_filter = bool(min_price or max_price)
    has_newest_sort = sort_by == "newest_desc"
    fetch_limit = limit * 4 if has_price_filter else limit
    if has_newest_sort:
        fetch_limit = max(fetch_limit, 100)
    logger.debug(
        "[TOOL][get_products_recommendations_tool] Called with: rcmd_type=%s, limit=%s, brand_cd=%s, car_lnc_cd=%s, tire_size=%s, sort_by=%s, season_nm=%s, pfm_nm=%s, min_price=%s, max_price=%s",
        rcmd_type, limit, brand_cd, car_lnc_cd, tire_size, sort_by, season_nm, pfm_nm, min_price, max_price,
    )

    try:
        response = get_products_recommendations(
            client=get_client(),
            rcmd_type=rcmd_type,
            limit=fetch_limit,
            brand_cd=brand_cd,
            car_lnc_cd=car_lnc_cd,
            tire_size=tire_size,
            season_nm=season_nm,
            pfm_nm=pfm_nm,
        )
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get product recommendations"
            )
        # logger.debug("[TOOL][get_products_recommendations_tool] Response: %s", response.parsed)
        data = _to_dict(response.parsed)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            if has_price_filter:
                data["items"] = _filter_by_price(data["items"], min_price, max_price)
                if not data["items"]:
                    return {"status": "no_results", "reason": "no_products_in_price_range", "min_price": min_price, "max_price": max_price}
            if str(rcmd_type) == "discount":
                data["items"] = _enrich_items_with_price_fields(data["items"])
            data["items"] = _enrich_items_with_descriptions(data["items"])
            data["items"] = _sort_items(data["items"], sort_by)
            if has_price_filter or has_newest_sort:
                data["items"] = data["items"][:limit]
        return _success_response(response.status_code, data)
    except Exception as e:
        logger.exception("[TOOL][get_products_recommendations_tool] Failed")
        return _error_response(None, str(e), "Failed to get product recommendations")


@tool
@tool_cache(ttl=600)
def get_events_tool(lang_cd: str = "ko"):
    """이벤트 목록 조회 — 현재 전시 중인 이벤트 목록.

    Args:
        lang_cd (str): 언어코드 (default: 'ko').

    Example: {"lang_cd": "ko"}
    """
    logger.debug("[TOOL][get_events_tool] Called with: lang_cd=%s", lang_cd)

    try:
        response = get_events(client=get_client(), lang_cd=lang_cd)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get events"
            )
        # logger.debug("[TOOL][get_events_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_events_tool] Failed")
        return _error_response(None, str(e), "Failed to get events")


@tool
@tool_cache(ttl=600)
def get_event_applicable_products_tool(evt_no_list: list[str]):
    """이벤트 적용 가능 상품 조회 — 여러 이벤트에 적용 가능한 상품 목록을 이벤트별 그룹핑하여 반환.

    Use when user asks "이 이벤트에 어떤 상품이 적용돼?", "이벤트 대상 상품 보여줘",
    "이벤트 적용 가능한 상품 알려줘" 등. 단일 이벤트도 1개 list 로 전달.

    Args:
        evt_no_list (list[str]): 이벤트 번호 목록 (1~10개). 예: ["E000001234", "E000005678"].

    Example: {"evt_no_list": ["E000001234", "E000005678"]}
    """
    logger.debug("[TOOL][get_event_applicable_products_tool] Called with: evt_no_list=%s", evt_no_list)

    if not evt_no_list:
        return _error_response(None, "evt_no_list is empty", "evt_no_list는 최소 1개 이상 필요합니다.")

    # BE 는 [E1, E2] 또는 E1,E2 형식의 단일 쿼리 문자열을 받음
    evt_no_param = f"[{','.join(str(e).strip() for e in evt_no_list)}]"

    try:
        response = get_event_applicable_products(client=get_client(), evt_no=evt_no_param)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get applicable products"
            )
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_event_applicable_products_tool] Failed")
        return _error_response(None, str(e), "Failed to get applicable products")


@tool
@tool_cache(ttl=600)
def get_product_applicable_events_tool(goods_no: str, lang_cd: str = "ko"):
    """상품 적용 가능 이벤트 조회 — 특정 상품에 적용 가능한 진행 중 이벤트 목록.

    Use when user asks "이 상품에 어떤 이벤트가 적용돼?", "이 상품에 적용 가능한 이벤트 알려줘",
    "지금 이 타이어 사면 어떤 행사 받을 수 있어?" 등. 진행 중(EVT_PRGS_STAT_CD='10')
    이벤트만 반환되며 50(상품 매핑) / 80(패턴 매핑) 양쪽 모두 포함.

    Args:
        goods_no (str): 상품 번호 (예: 'G000000317693').
        lang_cd (str): 이벤트명 언어 코드. Default 'ko'.

    Example: {"goods_no": "G000000317693", "lang_cd": "ko"}
    """
    logger.debug(
        "[TOOL][get_product_applicable_events_tool] Called with: goods_no=%s, lang_cd=%s",
        goods_no, lang_cd,
    )

    try:
        response = get_product_applicable_events(client=get_client(), goods_no=goods_no, lang_cd=lang_cd)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get applicable events"
            )
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_product_applicable_events_tool] Failed")
        return _error_response(None, str(e), "Failed to get applicable events")


@tool
@tool_cache(ttl=600)
def get_deals_tool():
    """기획전 목록 조회 — 현재 전시 중인 기획전 목록."""
    logger.debug("[TOOL][get_deals_tool] Called")

    try:
        response = get_deals(client=get_client())
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get deals"
            )
        # logger.debug("[TOOL][get_deals_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_deals_tool] Failed")
        return _error_response(None, str(e), "Failed to get deals")


@tool
def compare_discount_tool(goods_no_list: list[str], quantity: int = 1):
    """Compare discount prices across multiple products.

    Use when user asks to compare prices, "가장 저렴한/싼" product, or "비교".
    Returns: sale_prc, product_discount, coupon_discount, final_unit_price, final_price, cheapest_goods_no.

    Args:
        goods_no_list (list[str]): 2+ product numbers to compare.
        quantity (int): Quantity (min 1, default 1; use 4 for full tire set).

    Example: {"goods_no_list": ["GXXXXXXXXXXXX", "GXXXXXXXXXXXX"], "quantity": 4}
    """
    logger.debug("[TOOL][compare_discount_tool] Called with: goods_no_list=%s, quantity=%s", goods_no_list, quantity)

    try:
        response = get_discount_compare(client=get_client(), goods_no_list=goods_no_list, quantity=quantity)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to compare discount prices"
            )
        # logger.debug("[TOOL][compare_discount_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][compare_discount_tool] Failed")
        return _error_response(None, str(e), "Failed to compare discount prices")


# Add this new tool for YouTube video search related to hankook tire and tstation tv. This will allow the agent to fetch relevant videos when users ask for reviews, tests, or visual content about specific tires or brands.

@tool
def search_youtube_video_tool(query: str, max_results: int = 3):
    """유튜브 영상 검색 — 한국타이어/Tstation TV 공식 채널만 반환.

    Args:
        query (str): 검색어 (e.g., '벤투스 S1 evo3 리뷰', 'iON evo').
        max_results (int): 최대 반환 영상 수. Default 3.
    """
    logger.debug("[TOOL][search_youtube_video_tool] Called with: query=%s, max_results=%s", query, max_results)

    try:
        from youtube_search import YoutubeSearch
        
        # 1. Define the allowed official channel names (lowercase for easy matching)
        allowed_channels = ["한국타이어", "hankook tire", "티스테이션", "tstation tv"]
        
        # 2. Secretly bias the query so YouTube ranks official videos at the top
        biased_query = f"{query} 한국타이어 티스테이션"
        
        # 3. Fetch a larger pool of results (20) so we have enough left after filtering
        raw_results = YoutubeSearch(biased_query, max_results=20).to_dict()
        
        formatted_results = []
        for res in raw_results:
            channel_name = res.get("channel", "").lower()
            
            # 4. Strictly filter: Check if the video's channel matches our allowed list
            is_official_channel = any(allowed in channel_name for allowed in allowed_channels)
            
            if is_official_channel:
                thumbs = res.get("thumbnails") or []
                formatted_results.append({
                    "title": res.get("title"),
                    "channel": res.get("channel"),
                    "views": res.get("views"),
                    "duration": res.get("duration"),
                    "url": f"https://www.youtube.com{res.get('url_suffix')}",
                    "thumbnailUrl": thumbs[0] if thumbs else None,
                    "videoId": res.get("id"),
                })
                
            # 5. Stop once we have gathered enough official videos
            if len(formatted_results) >= max_results:
                break
                
        logger.debug("[TOOL][search_youtube_video_tool] Found %d official videos", len(formatted_results))
        
        if not formatted_results:
             return {
                 "status": "success", 
                 "message": "No official videos found on Hankook Tire or Tstation TV for that query."
             }
             
        return {
            "status": "success",
            "data": formatted_results
        }
        
    except ImportError:
        logger.error("youtube-search library is not installed.")
        return {"status": "error", "message": "The youtube-search library is missing."}
    except Exception as e:
        logger.exception("[TOOL][search_youtube_video_tool] Failed")
        return {"status": "error", "reason": str(e), "message": "Failed to search YouTube videos."}


@tool
@tool_cache(ttl=600)
def get_newest_products_tool(brand_cd: str = "HK", limit: int = 20):
    """
    최신/신제품 타이어 상품 조회.

    Use this tool when the user intent is to find the newest/latest/new tire
    products in general, without naming a specific model to compare.
    Do not use `search_product_tool` for that general newest-product intent.
    This tool sorts product search results by `sys_reg_dtime` descending; no
    product name is hardcoded.

    Args:
        brand_cd (str): 브랜드 코드. Default HK.
        limit (int): 반환할 최대 상품 수. Default 20.

    Returns:
        dict: {"status": "success", "http_status": ..., "data": {"items": [...]}}
    """
    logger.debug("[TOOL][get_newest_products_tool] Called with: brand_cd=%s, limit=%s", brand_cd, limit)
    if not isinstance(limit, int) or not (1 <= limit <= 50):
        return {
            "status": "error",
            "reason": "InvalidArguments",
            "message": "limit must be an int between 1 and 50",
        }

    try:
        response = search_product(client=get_client(), keyword=None, limit=max(limit, 100), size=None, brand_cd=brand_cd)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to search newest products",
            )
        data = _to_dict(response.parsed)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            data["items"] = _enrich_items_with_descriptions(data["items"])
            data["items"] = _sort_items(data["items"], "newest_desc")[:limit]
        return _success_response(response.status_code, data)
    except Exception as e:
        logger.exception("[TOOL][get_newest_products_tool] Failed")
        return _error_response(None, str(e), "Failed to search newest products")


@tool
@tool_cache(ttl=300)
def get_final_price_tool(goods_no: str, member_type: str | None = None):
    """Get product final price and discount info.

    Use this after search_product_tool to fetch real price for a specific goods_no.

    Args:
        goods_no (str): Product number (e.g., GXXXXXXXXXXXX).
        member_type (str | None): Member type (e.g., 'general', 'PARTNER').

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", ...}
    """
    logger.debug("[TOOL][get_final_price_tool] Called with: goods_no=%s, member_type=%s", goods_no, member_type)
    try:
        response = get_price(client=get_client(), goods_no=goods_no, member_type=member_type)
        if response.parsed is None:
            return {"status": "error", "http_status": response.status_code, "reason": f"HTTP {response.status_code}", "message": "Failed to get product price"}
        # logger.debug("[TOOL][get_final_price_tool] Response: %s", response.parsed)
        data = response.parsed.to_dict() if hasattr(response.parsed, "to_dict") else dict(response.parsed)
        return {"status": "success", "http_status": response.status_code, "data": data}
    except Exception as e:
        logger.exception("[TOOL][get_final_price_tool] Failed")
        return {"status": "error", "reason": str(e), "message": "Failed to get product price"}


_BEST_SELLER_PERIOD_MAP: dict[str, BestSellerPeriod] = {
    "day": BestSellerPeriod.DAY,
    "week": BestSellerPeriod.WEEK,
    "month": BestSellerPeriod.MONTH,
    "3months": BestSellerPeriod.VALUE_3,
}


@tool
@tool_cache(ttl=600)
def get_best_selling_products_tool(period: str = "month", limit: int = 5):
    """
    기간별 베스트셀러 상품 조회 (PR_GOODS_SUM 판매 수량 기준 정렬).

    Period mapping (사용자 표현 → period 값):
    - "오늘 가장 많이 팔린 상품 / 오늘의 베스트" → period="day"
    - "이번 주 / 금주 베스트" → period="week"
    - "이번 달 / 이달의 / 월별 베스트" → period="month"
    - "요즘 / 최근 / 인기 / 잘 나가는 / 잘 팔리는" → period="month" (모호한 최근성 표현은 month로 매핑)
    - "최근 3개월 / 분기 베스트" → period="3months"

    Args:
        period (str): "day" | "week" | "month" | "3months". Default "month".
        limit (int): 반환 상품 수 (1-50). Default 5.

    Response: BestSellerResponse — items 의 각 행에 goods_no, goods_nm,
        tire_size_1/2, image_url, extra_fvr_sale_prc, extra_fvr_sale_per, sale_qty.

    Example: {"period": "month", "limit": 5}
    """
    logger.debug("[TOOL][get_best_selling_products_tool] Called with: period=%s, limit=%s", period, limit)

    period_enum = _BEST_SELLER_PERIOD_MAP.get(period)
    if period_enum is None:
        return {
            "status": "error",
            "reason": "InvalidArguments",
            "message": f"period must be one of {sorted(_BEST_SELLER_PERIOD_MAP.keys())}; got {period!r}",
        }
    if not isinstance(limit, int) or not (1 <= limit <= 50):
        return {
            "status": "error",
            "reason": "InvalidArguments",
            "message": "limit must be an int between 1 and 50",
        }

    try:
        response = get_best_sellers(client=get_client(), period=period_enum, limit=limit)
        if response.parsed is None:
            return {
                "status": "error",
                "http_status": response.status_code,
                "reason": f"HTTP {response.status_code}",
                "message": response.content.decode(errors="ignore") or "Failed to get best-selling products",
            }
        # logger.debug("[TOOL][get_best_selling_products_tool] Response: %s", response.parsed)
        data = response.parsed.to_dict() if hasattr(response.parsed, "to_dict") else dict(response.parsed)
        return {"status": "success", "http_status": response.status_code, "data": data}
    except Exception as e:
        logger.exception("[TOOL][get_best_selling_products_tool] Failed")
        return {"status": "error", "reason": str(e), "message": "Failed to get best-selling products"}
