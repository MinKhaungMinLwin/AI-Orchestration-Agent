import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from services.tstation.common.tstation_be_client import get_tstation_be_client
from langchain.tools import tool
from common.tool_cache import tool_cache

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
from common.tstation_be_api_client.hkt_api_client.models import RcmdType


# Event/Deal
from common.tstation_be_api_client.hkt_api_client.api.event_deal_af_이벤트_및_기획전_조회.get_events_api_events_get import sync_detailed as get_events
from common.tstation_be_api_client.hkt_api_client.api.event_deal_af_이벤트_및_기획전_조회.get_deals_api_events_deals_get import sync_detailed as get_deals

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


def _fetch_description(goods_no: str) -> dict:
    """Fetch product description for a single goods_no, return merged fields or empty dict on failure."""
    try:
        response = get_product_description(client=get_client(), goods_no=goods_no)
        if response.parsed is None:
            return {}
        desc = _to_dict(response.parsed)
        return {
            "pc_prod_remark_desc": desc.get("pc_prod_remark_desc"),
            "pc_prod_tech_desc": desc.get("pc_prod_tech_desc"),
            "slogan": desc.get("slogan"),
            "images": desc.get("images"),
            "rating": desc.get("rating"),
            "reviews": desc.get("reviews"),
        }
    except Exception:
        logger.warning("[_fetch_description] Failed for goods_no=%s", goods_no)
        return {}


def _enrich_items_with_descriptions(items: list[dict]) -> list[dict]:
    """Parallel-fetch descriptions for each item and merge into item dicts."""
    if not items:
        return items

    goods_nos = [item.get("goods_no") for item in items if item.get("goods_no")]
    if not goods_nos:
        return items

    desc_map: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(len(goods_nos), 5)) as executor:
        futures = {executor.submit(_fetch_description, gno): gno for gno in goods_nos}
        for future in as_completed(futures):
            gno = futures[future]
            desc_map[gno] = future.result()

    return [{**item, **desc_map.get(item.get("goods_no"), {})} for item in items]


@tool
def check_compatibility_tool(goods_no: str, car_no: str, owner_nm: str):
    """
    차량-상품 타이어 호환 검증.

    When to use:
    - ONLY when tire_size is NOT yet confirmed AND user explicitly provides car_no + owner_nm

    When NOT to use:
    - If tire_size is already confirmed → compare product's tire_size directly (no tool needed)
    - If user only mentions car model name → use CAR MODEL DISPLAY (own knowledge) instead

    Args:
        goods_no (str): 상품 번호
        car_no (str): 차량 번호
        owner_nm (str): 차량 소유주

    Example Inputs:
        - {"goods_no": "GXXXXXXXXXXXX", "car_no": "12가3456", "owner_nm": "홍길동"}
        - {"goods_no": "GXXXXXXXXXXXX", "car_no": "34나5678", "owner_nm": "홍길동"}
        - {"goods_no": "GXXXXXXXXXXXX", "car_no": "56다7890", "owner_nm": "홍길동"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    logger.info("[TOOL][check_compatibility_tool] Called with: goods_no=%s, car_no=%s, owner_nm=%s", goods_no, car_no, owner_nm)

    try:
        response = check_compatibility(client=get_client(), goods_no=goods_no, car_no=car_no, owner_nm=owner_nm)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to check tire compatibility"
            )
        logger.info("[TOOL][check_compatibility_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][check_compatibility_tool] Failed")
        return _error_response(None, str(e), "Failed to check tire compatibility")


@tool
@tool_cache(ttl=300)
def search_product_tool(keyword: str, limit: int = 5, size: str | None = None, brand_cd: str = "HK"):
    """
    상품 검색.

    When to use:
    - User searches for a specific tire by name/keyword
    - Resolving goods_no for price/stock/order handoff (Flow C/D)

    Important: Translate Korean product names to English before calling.
    - 벤투스→Ventus, 키네르기→Kinergy, 옵티모→Optimo, 다이나프로→Dynapro, 에보→evo

    Brand detection: Set brand_cd from product name (MC=Michelin, PI=Pirelli, BS=Bridgestone,
    CT=Continental, GY=Goodyear, LF=Laufenn). Default: HK.
    Unsupported brands (금호, 넥센 etc.) → decline, do not search.

    Args:
        keyword (str): 검색할 제품명 키워드 — English name preferred (예: 'Ventus S2', 'Kinergy EX')
        limit (int): 반환할 최대 상품 수 Default: 20.
        size (str | None): 타이어 사이즈 필터 (예: '225/45R17' 또는 '2254517'). Optional.
        brand_cd (str): 브랜드 코드. Default: HK.
            - HK: Hankook 한국타이어
            - LF: Laufenn 라우펜
            - MC: Michelin 미쉐린
            - PI: Pirelli 피렐리
            - BS: Bridgestone 브리지스톤
            - CT: Continental 콘티넨탈
            - GY: Goodyear 굿이어

    Example Inputs:
        - {"keyword": "벤투스 S2", "limit": 5, "size": "225/45R17"}
        - {"keyword": "Ventus S2", "limit": 5, "size": "2254517"}
        - {"keyword": "Pilot Sport", "limit": 5, "brand_cd": "MC"}
        - {"keyword": "s1-evo", "limit": 5}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    logger.info("[TOOL][search_product_tool] Called with: keyword=%s, limit=%s, size=%s, brand_cd=%s", keyword, limit, size, brand_cd)

    try:
        response = search_product(client=get_client(), keyword=keyword, limit=limit, size=size, brand_cd=brand_cd)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to search products"
            )
        logger.info("[TOOL][search_product_tool] Response: %s", response.parsed)
        data = _to_dict(response.parsed)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            data["items"] = _enrich_items_with_descriptions(data["items"])
        return _success_response(response.status_code, data)
    except Exception as e:
        logger.exception("[TOOL][search_product_tool] Failed")
        return _error_response(None, str(e), "Failed to search products")


@tool
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
        car_no (str): Vehicle registration number (차량번호).
        owner_nm (str): Owner name (소유주명).

    Example Inputs:
        - {"car_no": "12가3456", "owner_nm": "홍길동"}
        - {"car_no": "34나5678", "owner_nm": "홍길동"}
        - {"car_no": "56다7890", "owner_nm": "홍길동"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    logger.info("[TOOL][get_user_vehicles_tool] Called with: car_no=%s, owner_nm=%s", car_no, owner_nm)

    try:
        response = get_user_vehicles(client=get_client(), car_no=car_no, owner_nm=owner_nm)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get user vehicles"
            )
        logger.info("[TOOL][get_user_vehicles_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_user_vehicles_tool] Failed")
        return _error_response(None, str(e), "Failed to get user vehicles")


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
        mbr_no (str): Member number (from user context provided by the system).

    Example Inputs:
        - {"mbr_no": "MXXXXXXXXX"}
        - {"mbr_no": "MXXXXXXXXX"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    logger.info("[TOOL][get_my_cars_tool] Called with: mbr_no=%s", mbr_no)

    try:
        response = get_member_cars(client=get_client(), mbr_no=mbr_no)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get member cars"
            )
        logger.info("[TOOL][get_my_cars_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_my_cars_tool] Failed")
        return _error_response(None, str(e), "Failed to get member cars")


@tool
@tool_cache(ttl=3600)
def search_car_model_tool(keyword: str, limit: int = 20):
    """
    차량 모델 검색 (car_lnc_cd 조회용).

    When to use:
    - ONLY after get_user_vehicles_tool fails as a last fallback to get car_lnc_cd
    - When another flow explicitly requires car_lnc_cd lookup

    When NOT to use:
    - Do NOT call when user just mentions a car model name for tire recommendation
      → Instead, use your own knowledge to describe representative trims/tire sizes (CAR MODEL DISPLAY)
    - Do NOT call as first step for car model mentions

    Args:
        keyword (str): 차량 모델명 키워드 (한국어, 브랜드명 제외. 예: '소나타', '그랜저', 'BMW')
        limit (int): 최대 결과 수. Default: 20.

    Example Inputs:
        - {"keyword": "소나타", "limit": 20}
        - {"keyword": "그랜저", "limit": 20}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    logger.info("[TOOL][search_car_model_tool] Called with: keyword=%s, limit=%s", keyword, limit)

    try:
        response = search_car_model(client=get_client(), keyword=keyword, limit=limit)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to search car models"
            )
        logger.info("[TOOL][search_car_model_tool] Response: %s", response.parsed)
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
    - Use this INSTEAD of LLM own knowledge for the CAR MODEL DISPLAY flow
    - Step 1 of 2: returns model groups with year ranges → user selects → call get_car_trims_tool

    When NOT to use:
    - Do NOT call when user already provided car_no + owner_nm (use get_user_vehicles_tool)
    - Do NOT call when car is already confirmed from get_my_cars_tool result

    Returns grouped car models with year range so user can identify their generation.
    Each group has car_model_det (e.g., "더 뉴 K7(VG)"), year_from, year_to, trim_count.

    Args:
        keyword (str): 차량 모델명 키워드 (예: 'K7', '소나타', '팰리세이드', 'BMW 5시리즈')

    Example Inputs:
        - {"keyword": "K7"}
        - {"keyword": "소나타"}
        - {"keyword": "팰리세이드"}

    Returns:
        dict: {"status": "success", "data": {"keyword": "...", "items": [{"car_model_det": "...", "year_from": 2019, "year_to": 2023, "trim_count": 8}]}}
    """
    logger.info("[TOOL][search_car_model_groups_tool] Called with: keyword=%s", keyword)

    try:
        response = search_car_model_groups(client=get_client(), keyword=keyword)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to search car model groups"
            )
        logger.info("[TOOL][search_car_model_groups_tool] Response: %s", response.parsed)
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
    - Returns all trims with car_lnc_cd AND tire_size_fr/re directly
    - Step 2 of 2: once user selects a trim, extract tire_size_fr → RECOMMEND ENGINE

    Returns each trim with: car_lnc_cd, car_nm, car_year, tire_size_fr, tire_size_re.
    If user selects a trim → use tire_size_fr directly for get_products_recommendations_tool.
    If only 1 trim exists → auto-select, extract tire_size_fr, proceed to RECOMMEND ENGINE.

    Args:
        car_model_det (str): 차량 상세 모델명 from search_car_model_groups_tool result
            (예: "더 뉴 K7(VG)", "쏘나타 DN8")

    Example Inputs:
        - {"car_model_det": "더 뉴 K7(VG)"}
        - {"car_model_det": "쏘나타 DN8"}

    Returns:
        dict: {"status": "success", "data": {"car_model_det": "...", "items": [{"car_lnc_cd": "...", "car_nm": "...", "car_year": 2021, "tire_size_fr": "225/45R18", "tire_size_re": "225/45R18"}]}}
    """
    logger.info("[TOOL][get_car_trims_tool] Called with: car_model_det=%s", car_model_det)

    try:
        response = get_car_trims(client=get_client(), car_model_det=car_model_det)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get car trims"
            )
        logger.info("[TOOL][get_car_trims_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_car_trims_tool] Failed")
        return _error_response(None, str(e), "Failed to get car trims")


@tool
@tool_cache(ttl=600)
def get_product_description_tool(goods_no: str):
    """
    Get product description.

    Retrieve detailed product information by joining PR_GOODS_BASE and PR_PATTERN_BASE
    using the product number.

    The API returns:
    - Key features (PC_PROD_REMARK_DESC)
    - Technology description (PC_PROD_TECH_DESC)
    - Product slogan (SLOGAN)
    - Product images (images)
    - Rating info: review_count (리뷰 수), rating_avg (평점 평균)
    - Review list: gdas_score (평점), gdas_cont (리뷰 내용), reg_dtime (등록일)

    Args:
        goods_no (str): Product number.

    Example Inputs:
        - {"goods_no": "GXXXXXXXXXXXX"}
        - {"goods_no": "GXXXXXXXXXXXX"}
        - {"goods_no": "GXXXXXXXXXXXX"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    logger.info("[TOOL][get_product_description_tool] Called with: goods_no=%s", goods_no)

    try:
        response = get_product_description(client=get_client(), goods_no=goods_no)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get product description"
            )
        logger.info("[TOOL][get_product_description_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_product_description_tool] Failed")
        return _error_response(None, str(e), "Failed to get product description")


@tool
@tool_cache(ttl=300)
def get_products_recommendations_tool(rcmd_type: RcmdType, limit: int = 5, brand_cd: str = "HK", entr_yn: str = "n", entr_no: str | None = None, car_lnc_cd: str | None = None, tire_size: str | None = None):
    """
    Product Recommendation

    Returns the top N products based on the selected recommendation type (rcmd_type).

    **API UPDATE: 차량 정보로 추천 가능합니다**
    - car_lnc_cd: 차량 런칭 코드 (car_lnc_cd 입력 시 tire_size보다 우선 적용)
    - tire_size: 타이어 사이즈 문자열 (예: "245/45R18", 공백/소문자 허용)

    Recommendation types:
    - tstation: T-Station recommended products
      (TOT_SCR (if FST_DISP_YN='Y' then TOT_SCR = TOT_SCR*10) sorted by highest,
      from PR_GOODS_RCMD_SUM)

    - discount: Highest discount rate
      (sorted by highest EXTRA_FVR_SALE_PER, from PR_GOODS_DSCNT_PRC_INFO)

    - value: Best value products
      (discounted price ≤ 200,000 KRW, sorted by high durability and fuel efficiency,
      from PR_GOODS_DSCNT_PRC_INFO + PR_GOODS_RCMD_SUM)

    Args:
        rcmd_type (RcmdType): Recommendation type.
        limit (int, optional): Number of products to return. Default is 10, maximum is 100.
        brand_cd (str, optional): Brand code. Default is HK.
            - HK: Hankook 한국타이어 (Hankook Tire)
            - LF: Laufenn 라우펜
            - MC: Michelin 미쉐린
            - PI: Pirelli 피렐리
            - BS: Bridgestone 브리지스톤
            - CT: Continental 콘티넨탈
            - GY: Goodyear 굿이어
        entr_yn (str, optional): Affiliate site (y/n). Default is n.
        entr_no (str | None, optional): Affiliate number (required if entr_yn=y).
        car_lnc_cd (str | None, optional): 차량 런칭 코드. 입력 시 타이어 사이즈보다 우선 적용
        tire_size (str | None, optional): 타이어 사이즈 문자열 (예: "245/45R18", 공백/소문자 허용)

    Example Inputs:
        - {"rcmd_type": "tstation", "limit": 10, "brand_cd": "HK", "entr_yn": "n", "entr_no": None, "car_lnc_cd": None, "tire_size": None}
        - {"rcmd_type": "tstation", "limit": 10, "brand_cd": "HK", "car_lnc_cd": "LNCXXXXXX", "tire_size": None}
        - {"rcmd_type": "tstation", "limit": 10, "brand_cd": "HK", "car_lnc_cd": None, "tire_size": "245/45R18"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    logger.info("[TOOL][get_products_recommendations_tool] Called with: rcmd_type=%s, limit=%s, brand_cd=%s, entr_yn=%s, entr_no=%s, car_lnc_cd=%s, tire_size=%s", rcmd_type, limit, brand_cd, entr_yn, entr_no, car_lnc_cd, tire_size)

    try:
        response = get_products_recommendations(
            client=get_client(),
            rcmd_type=rcmd_type,
            limit=limit,
            brand_cd=brand_cd,
            entr_yn=entr_yn,
            entr_no=entr_no,
            car_lnc_cd=car_lnc_cd,
            tire_size=tire_size,
        )
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get product recommendations"
            )
        logger.info("[TOOL][get_products_recommendations_tool] Response: %s", response.parsed)
        data = _to_dict(response.parsed)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            data["items"] = _enrich_items_with_descriptions(data["items"])
        return _success_response(response.status_code, data)
    except Exception as e:
        logger.exception("[TOOL][get_products_recommendations_tool] Failed")
        return _error_response(None, str(e), "Failed to get product recommendations")


@tool
@tool_cache(ttl=600)
def get_events_tool(lang_cd: str = "ko"):
    """이벤트 목록 조회

    현재 전시 중인 이벤트 목록을 조회합니다.
    (전시여부, 전시기간, 적용시각, 전시요일 조건 적용)

    Args:
        lang_cd (str): 언어코드 (기본값: ko)

    Example Inputs:
        - {"lang_cd": "ko"}
        - {"lang_cd": "en"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", ...}
    """
    logger.info("[TOOL][get_events_tool] Called with: lang_cd=%s", lang_cd)

    try:
        response = get_events(client=get_client(), lang_cd=lang_cd)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get events"
            )
        logger.info("[TOOL][get_events_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_events_tool] Failed")
        return _error_response(None, str(e), "Failed to get events")


@tool
@tool_cache(ttl=600)
def get_deals_tool():
    """기획전 목록 조회

    현재 전시 중인 기획전 목록을 조회합니다.
    (전시여부, 전시기간, 적용시각, 전시요일 조건 적용)

    Example Inputs:
        - {}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", ...}
    """
    logger.info("[TOOL][get_deals_tool] Called")

    try:
        response = get_deals(client=get_client())
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to get deals"
            )
        logger.info("[TOOL][get_deals_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_deals_tool] Failed")
        return _error_response(None, str(e), "Failed to get deals")


@tool
def compare_discount_tool(goods_no_list: list[str], quantity: int = 1):
    """Compare discount prices across multiple products.

    Input multiple product numbers and quantity to compare:
    - Regular price (sale_prc)
    - Product discount (product_discount)
    - Coupon discount (coupon_discount)
    - Final unit price (final_unit_price)
    - Total final price (final_price)
    - Cheapest product number (cheapest_goods_no)

    JWT token's affiliate_yn value automatically distinguishes general/affiliate members.
    Returns cheapest_goods_no to identify the lowest-priced product.

    Use this when:
    - User wants to compare prices between two or more products
    - User asks "which is cheaper", "price comparison", "비교" (compare)
    - User has multiple product numbers and wants to find the best deal
    - User asks for "cheapest", "가장 저렴한", "가장 싼" product

    Args:
        goods_no_list (list[str]): List of product numbers (e.g., ['GXXXXXXXXXXXX', 'GXXXXXXXXXXXX']).
            Supports 2 or more products for comparison.
        quantity (int): Quantity (minimum 1, default 1). Use 4 for full tire set.

    Example Inputs:
        - {"goods_no_list": ["GXXXXXXXXXXXX", "GXXXXXXXXXXXX"], "quantity": 4}
        - {"goods_no_list": ["GXXXXXXXXXXXX", "GXXXXXXXXXXXX", "GXXXXXXXXXXXX"], "quantity": 2}
        - {"goods_no_list": ["GXXXXXXXXXXXX", "GXXXXXXXXXXXX"], "quantity": 1}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", ...}
    """
    logger.info("[TOOL][compare_discount_tool] Called with: goods_no_list=%s, quantity=%s", goods_no_list, quantity)

    try:
        response = get_discount_compare(client=get_client(), goods_no_list=goods_no_list, quantity=quantity)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to compare discount prices"
            )
        logger.info("[TOOL][compare_discount_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][compare_discount_tool] Failed")
        return _error_response(None, str(e), "Failed to compare discount prices")


# Add this new tool for YouTube video search related to hankook tire and tstation tv. This will allow the agent to fetch relevant videos when users ask for reviews, tests, or visual content about specific tires or brands.

@tool
def search_youtube_video_tool(query: str, max_results: int = 3):
    """유튜브 영상 검색 (YouTube Video Search)
    
    Searches YouTube for official videos related to a specific tire or brand.
    This tool is strictly filtered to ONLY return videos from the official 
    'Hankook Tire' and 'Tstation TV' channels.
    
    Args:
        query (str): The search query (e.g., '벤투스 S1 evo3 리뷰', 'iON evo').
        max_results (int): The maximum number of videos to return. Default is 3.
        
    Returns:
        dict: A dictionary containing the video titles, channel names, and direct URLs.
    """
    logger.info("[TOOL][search_youtube_video_tool] Called with: query=%s, max_results=%s", query, max_results)

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
                
        logger.info("[TOOL][search_youtube_video_tool] Found %d official videos", len(formatted_results))
        
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
def get_final_price_tool(goods_no: str, member_type: str | None = None):
    """Get product final price and discount info.

    Use this after search_product_tool to fetch real price for a specific goods_no.

    Args:
        goods_no (str): Product number (e.g., GXXXXXXXXXXXX).
        member_type (str | None): Member type (e.g., 'general', 'PARTNER').

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", ...}
    """
    logger.info("[TOOL][get_final_price_tool] Called with: goods_no=%s, member_type=%s", goods_no, member_type)
    try:
        response = get_price(client=get_client(), goods_no=goods_no, member_type=member_type)
        if response.parsed is None:
            return {"status": "error", "http_status": response.status_code, "reason": f"HTTP {response.status_code}", "message": "Failed to get product price"}
        logger.info("[TOOL][get_final_price_tool] Response: %s", response.parsed)
        data = response.parsed.to_dict() if hasattr(response.parsed, "to_dict") else dict(response.parsed)
        return {"status": "success", "http_status": response.status_code, "data": data}
    except Exception as e:
        logger.exception("[TOOL][get_final_price_tool] Failed")
        return {"status": "error", "reason": str(e), "message": "Failed to get product price"}