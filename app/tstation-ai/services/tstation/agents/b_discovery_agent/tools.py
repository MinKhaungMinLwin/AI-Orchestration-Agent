import logging
from typing import Any

from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from services.tstation.common.tstation_be_client import get_tstation_be_client
from langchain.tools import tool

logger = logging.getLogger(__name__)

# Product Compatibility
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.vehicle_verify_owner_api_vehicle_verify_owner_post import sync_detailed as post_vehicle_verify_owner
from common.tstation_be_api_client.hkt_api_client.models import VerifyOwnerRequest
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.check_compatibility_api_product_compatible_get import sync_detailed as check_compatibility
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.search_product_api_product_search_get import sync_detailed as search_product
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.get_user_vehicles_api_user_vehicles_get import sync_detailed as get_user_vehicles
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.search_car_model_api_vehicle_search_get import sync_detailed as search_car_model

# Product Description
from common.tstation_be_api_client.hkt_api_client.api.product_description_af_상품_설명.get_description_api_product_detail_goods_no_get import sync_detailed as get_product_description

# Product Recommendation
from common.tstation_be_api_client.hkt_api_client.api.product_recommendation_af_상품_추천.get_recommendations_api_product_recommend_get import sync_detailed as get_products_recommendations
from common.tstation_be_api_client.hkt_api_client.models import RcmdType


def get_client() -> AuthenticatedClient:
    """Get authenticated client for tstation-be API."""
    return get_tstation_be_client()


DOMAIN_TOOL_MAP = {
    "discovery": {
        # Product Compatibility
        "vehicle_verify_owner",
        "check_compatibility",
        "search_product",
        "get_user_vehicles",
        "search_car_model",

        # Product Recommendation
        "get_recommendations",

        # Product Description
        "get_description",
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


@tool
def post_vehicle_verify_owner_tool(car_no: str):
    """
    Verify vehicle ownership.

    This API verifies whether the user is the registered owner of a vehicle
    based on the provided request information.

    Args:
        car_no (str): Request payload containing the information
            required to verify vehicle ownership.

    Example Inputs:
        - {"car_no": "33가3333"}
        - {"car_no": "11가0000"}
        - {"car_no": "29조3344"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    logger.info("[TOOL][post_vehicle_verify_owner_tool] Called with: car_no=%s", car_no)

    try:
        body = VerifyOwnerRequest(car_no=car_no)
        response = post_vehicle_verify_owner(client=get_client(), body=body)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to verify vehicle ownership"
            )
        logger.info("[TOOL][post_vehicle_verify_owner_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][post_vehicle_verify_owner_tool] Failed")
        return _error_response(None, str(e), "Failed to verify vehicle ownership")


@tool
def check_compatibility_tool(goods_no: str, car_no: str, owner_nm: str):
    """
    차량-상품 타이어 호환 검증

    차량번호(CAR_NO)와 소유주명(OWNER_NM)으로 차량 타이어 사이즈를 조회하고,
    상품번호(GOODS_NO)로 타이어 스펙(단면폭/편평비/인치)을 조회하여 호환 여부를 반환합니다.

    Args:
        goods_no (str): 상품 번호
        car_no (str): 차량 번호
        owner_nm (str): 차량 소유주

    Example Inputs:
        - {"goods_no": "G000000313165", "car_no": "33가3333", "owner_nm": "공태웅"}
        - {"goods_no": "G000000309860", "car_no": "11가0000", "owner_nm": "공태웅"}
        - {"goods_no": "G000000313073", "car_no": "29조3344", "owner_nm": "공태웅"}

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
def search_product_tool(keyword: str, limit: int = 20):
    """
    상품 검색

    제품명 키워드로 상품을 검색합니다. 한글/영문 혼용, 부분 키워드 지원.
    (예: '벤투스', 's1 evo', '아이온 suv')

    Args:
        keyword (str): 검색할 제품명 키워드 (예: '벤투스 S2', 's1-evo')
        limit (int): 반환할 최대 상품 수 Default: 20.

    Example Inputs:
        - {"keyword": "벤투스 S2", "limit": 20}
        - {"keyword": "Ventus S2", "limit": 20}
        - {"keyword": "s1-evo", "limit": 20}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    logger.info("[TOOL][search_product_tool] Called with: keyword=%s, limit=%s", keyword, limit)

    try:
        response = search_product(client=get_client(), keyword=keyword, limit=limit)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to search products"
            )
        logger.info("[TOOL][search_product_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][search_product_tool] Failed")
        return _error_response(None, str(e), "Failed to search products")


@tool
def get_user_vehicles_tool(car_no: str, owner_nm: str):
    """
    Get user vehicles.

    Retrieve vehicle information associated with the given vehicle
    registration number and owner name.

    Args:
        car_no (str): Vehicle registration number.
        owner_nm (str): Owner name.

    Example Inputs:
        - {"car_no": "33가3333", "owner_nm": "공태웅"}
        - {"car_no": "11가0000", "owner_nm": "공태웅"}
        - {"car_no": "29조3344", "owner_nm": "공태웅"}

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
def search_car_model_tool(keyword: str, limit: int = 20):
    """
    차량 모델 검색

    차량 모델명 키워드로 PR_CAR_BASE에서 차량을 검색합니다. alias 확장 지원.

    Args:
        keyword (str): 검색할 차량 모델명 키워드 (예: '소나타', '그랜저')
        limit (int): 반환할 최대 차량 수 Default: 20.

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
        - {"goods_no": "G000000312692"}
        - {"goods_no": "G000000313186"}
        - {"goods_no": "G000000310122"}

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
def get_products_recommendations_tool(rcmd_type: RcmdType, limit: int = 20, brand_cd: str = "HK", entr_yn: str = "n", entr_no: str | None = None, car_lnc_cd: str | None = None, tire_size: str | None = None):
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
        - {"rcmd_type": "tstation", "limit": 10, "brand_cd": "HK", "car_lnc_cd": "LNC12345", "tire_size": None}
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
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_products_recommendations_tool] Failed")
        return _error_response(None, str(e), "Failed to get product recommendations")


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
                formatted_results.append({
                    "title": res.get("title"),
                    "channel": res.get("channel"),  # Keep original casing for display
                    "views": res.get("views"),
                    "duration": res.get("duration"),
                    "url": f"https://www.youtube.com{res.get('url_suffix')}"
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