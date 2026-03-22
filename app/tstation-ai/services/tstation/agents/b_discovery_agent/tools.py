import logging
from typing import Optional

from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from services.tstation.common.tstation_be_client import get_tstation_be_client
from langchain.tools import tool

logger = logging.getLogger(__name__)

# Product Compatibility
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.vehicle_verify_owner_api_vehicle_verify_owner_post import sync as post_vehicle_verify_owner
from common.tstation_be_api_client.hkt_api_client.models import VerifyOwnerRequest
# from common.tstation_be_api_client.hkt_api_client.models import CompatibilityRequest
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.get_compatible_product_api_product_compatible_get import sync as get_compatible_product
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.get_user_vehicles_api_user_vehicles_get import sync as get_user_vehicles
# from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.get_compatibility import sync as get_compatibility


# Product Description
from common.tstation_be_api_client.hkt_api_client.api.product_description_af_상품_설명.get_description_api_product_detail_goods_no_get import sync as get_product_description

# Product Recommendation
from common.tstation_be_api_client.hkt_api_client.api.product_recommendation_af_상품_추천.get_recommendations_api_product_recommend_get import sync as get_products_recommendations
from common.tstation_be_api_client.hkt_api_client.models import RcmdType

# Product Search (NEW - not yet implemented in tools)
# from common.tstation_be_api_client.hkt_api_client.api.product_search_af_상품_검색.search_products_api_product_search_get import sync as search_products

def get_client() -> AuthenticatedClient:
    """Get authenticated client for tstation-be API."""
    return get_tstation_be_client()


DOMAIN_TOOL_MAP = {
    "discovery": {
        # Product Compatibility
        "vehicle_verify_owner",
        "get_compatible_product",
        "get_user_vehicles",

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


@tool
def post_vehicle_verify_owner_tool(car_no: str):
    """
    Verify vehicle ownership.

    This API verifies whether the user is the registered owner of a vehicle
    based on the provided request information.

    Args:
        car_no (str): Request payload containing the information
            required to verify vehicle ownership.

    Returns:
        dict: {"status": "success", "data": ...} or {"status": "error", "reason": ..., "message": ...}
    """
    logger.info("[TOOL][post_vehicle_verify_owner_tool] Called with: car_no=%s", car_no)

    try:
        body = VerifyOwnerRequest(car_no=car_no)
        res = post_vehicle_verify_owner(
            client=get_client(),
            body=body,
        )
        logger.info("[TOOL][post_vehicle_verify_owner_tool] Response: %s", res)
        return {
            "status": "success",
            "data": res.to_dict() if hasattr(res, 'to_dict') else (res.model_dump() if hasattr(res, 'model_dump') else res),
        }
    except Exception as e:
        logger.exception("[TOOL][post_vehicle_verify_owner_tool] Failed")
        return {
            "status": "error",
            "reason": str(e),
            "message": "Failed to verify vehicle ownership"
        }

@tool
def get_compatible_product_tool(goods_no: str):
    """
    Get compatible products.

    Retrieve products that are compatible with the given product number.
    This is typically used to find alternative or similar tire products
    that match the same specifications or compatibility conditions.

    Args:
        goods_no (str): Product number.

    Returns:
        dict: {"status": "success", "data": ...} or {"status": "error", "reason": ..., "message": ...}
    """
    logger.info("[TOOL][get_compatible_product_tool] Called with: goods_no=%s", goods_no)

    try:
        res = get_compatible_product(
            client=get_client(),
            goods_no=goods_no,
        )
        logger.info("[TOOL][get_compatible_product_tool] Response: %s", res)
        return {
            "status": "success",
            "data": res.to_dict() if hasattr(res, 'to_dict') else (res.model_dump() if hasattr(res, 'model_dump') else res),
        }
    except Exception as e:
        logger.exception("[TOOL][get_compatible_product_tool] Failed")
        return {
            "status": "error",
            "reason": str(e),
            "message": "Failed to get compatible products"
        }

@tool
def get_user_vehicles_tool(car_no: str):
    """
    Get user vehicles.

    Retrieve vehicle information associated with the given vehicle
    registration number.

    Args:
        car_no (str): Vehicle registration number.

    Returns:
        dict: {"status": "success", "data": ...} or {"status": "error", "reason": ..., "message": ...}
    """
    logger.info("[TOOL][get_user_vehicles_tool] Called with: car_no=%s", car_no)

    try:
        res = get_user_vehicles(
            client=get_client(),
            car_no=car_no,
        )
        logger.info("[TOOL][get_user_vehicles_tool] Response: %s", res)
        return {
            "status": "success",
            "data": res.to_dict() if hasattr(res, 'to_dict') else (res.model_dump() if hasattr(res, 'model_dump') else res),
        }
    except Exception as e:
        logger.exception("[TOOL][get_user_vehicles_tool] Failed")
        return {
            "status": "error",
            "reason": str(e),
            "message": "Failed to get user vehicles"
        }


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

    It also retrieves image and thumbnail paths from PR_PTRN_IMG_INFO.

    Args:
        goods_no (str): Product number.

    Returns:
        dict: {"status": "success", "data": ...} or {"status": "error", "reason": ..., "message": ...}
    """
    logger.info("[TOOL][get_product_description_tool] Called with: goods_no=%s", goods_no)

    try:
        res = get_product_description(
            client=get_client(),
            goods_no=goods_no
        )
        logger.info("[TOOL][get_product_description_tool] Response: %s", res)
        return {
            "status": "success",
            "data": res.to_dict() if hasattr(res, 'to_dict') else (res.model_dump() if hasattr(res, 'model_dump') else res),
        }
    except Exception as e:
        logger.exception("[TOOL][get_product_description_tool] Failed")
        return {
            "status": "error",
            "reason": str(e),
            "message": "Failed to get product description"
        }


@tool
def get_products_recommendations_tool(rcmd_type: RcmdType, limit: int = 20, brand_cd: str = "HK", entr_yn: str = "n", entr_no: str | None = None):
    """
    Product Recommendation

    Returns the top N products based on the selected recommendation type (rcmd_type).

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
        brand_cd (str, optional): Brand code (HK / LF / MC / PI / BS / CT / GY). Default is HK.
        entr_yn (str, optional): Affiliate site (y/n). Default is n.
        entr_no (str | None, optional): Affiliate number (required if entr_yn=y).

    Returns:
        dict: {"status": "success", "data": ...} or {"status": "error", "reason": ..., "message": ...}
    """
    logger.info("[TOOL][get_products_recommendations_tool] Called with: rcmd_type=%s, limit=%s, brand_cd=%s, entr_yn=%s, entr_no=%s", rcmd_type, limit, brand_cd, entr_yn, entr_no)

    try:
        res = get_products_recommendations(
            client=get_client(),
            rcmd_type=rcmd_type,
            limit=limit,
            brand_cd=brand_cd,
            entr_yn=entr_yn,
            entr_no=entr_no,
        )
        logger.info("[TOOL][get_products_recommendations_tool] Response: %s", res)
        return {
            "status": "success",
            "data": res.to_dict() if hasattr(res, 'to_dict') else (res.model_dump() if hasattr(res, 'model_dump') else res),
        }
    except Exception as e:
        logger.exception("[TOOL][get_products_recommendations_tool] Failed")
        return {
            "status": "error",
            "reason": str(e),
            "message": "Failed to get product recommendations"
        }

# --- New. COMPATIBILITY TOOL ---
@tool
def get_compatibility_tool(goods_no: str, car_no: Optional[str] = None, car_nm: Optional[str] = None):
    """
    Check if a specific tire fits a vehicle.
    Must provide either the vehicle plate number (car_no) OR the vehicle model name (car_nm).

    Args:
        goods_no (str): The product ID to check.
        car_no (Optional[str]): The vehicle license plate number (e.g., '12가3456').
        car_nm (Optional[str]): The vehicle model name (e.g., '쏘나타', '아반떼').
    """
    logger.info(f"[TOOL][get_compatibility_tool] Called with: goods_no={goods_no}, car_no={car_no}, car_nm={car_nm}")

    try:
        # Note: Your auto-generated CompatibilityRequest model must be updated 
        # by regenerating the client to accept car_nm!
        body = CompatibilityRequest(
            car_no=car_no,
            car_nm=car_nm, 
            goods_no=goods_no
        )
        res = get_compatibility(
            client=get_client(),
            body=body
        )
        logger.info(f"[TOOL][get_compatibility_tool] Response: {res}")
        return {
            "status": "success",
            "data": res,
        }
    except Exception as e:
        logger.exception("[TOOL][get_compatibility_tool] Failed")
        return {
            "status": "error",
            "reason": str(e),
            "message": "Failed to check compatibility."
        }

# --- NEW PRODUCT SEARCH TOOL ---
@tool
def search_product_tool(keyword: str):
    """
    Search for a tire product by its name or keyword.
    
    Returns the goods_no, goods_nm (product name), tire_size_1 (front), and tire_size_2 (rear).
    Use this tool when the user asks for a specific tire model (e.g., '벤투스', '키너지') 
    so you can find its goods_no to use in other tools.

    Args:
        keyword (str): The name of the tire to search for.
    """
    logger.info(f"[TOOL][search_product_tool] Called with: keyword={keyword}")

    try:
        
        res = search_products(client=get_client(), keyword=keyword)
        logger.info(f"[TOOL][search_product_tool] Response: {res}")
        return {"status": "success", "data": res}
        
        return {
            "status": "pending",
            "message": "Waiting for backend client regeneration to execute API call."
        }
    except Exception as e:
        logger.exception("[TOOL][search_product_tool] Failed")
        return {
            "status": "error",
            "reason": str(e),
            "message": "Failed to search for product."
        }