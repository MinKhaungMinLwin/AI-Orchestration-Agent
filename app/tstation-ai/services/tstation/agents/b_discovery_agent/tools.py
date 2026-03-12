import logging

from common.tstation_be_api_client.hkt_api_client.client import Client
from config.env import settings
from langchain.tools import tool

logger = logging.getLogger(__name__)

# Product Compatibility
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.check_compatibility_api_compatiblity_get import sync as get_compatibility
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.vehicle_verify_owner_api_vehicle_verify_owner_post import sync as post_vehicle_verify_owner
from common.tstation_be_api_client.hkt_api_client.models import VerifyOwnerRequest
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.get_compatible_product_api_product_compatible_get import sync as get_compatible_product
from common.tstation_be_api_client.hkt_api_client.api.product_compatibility_af_차량_및_상품_호환_검증.get_user_vehicles_api_user_vehicles_get import sync as get_user_vehicles

# Product Description
from common.tstation_be_api_client.hkt_api_client.api.product_description_af_상품_설명.get_description_api_product_detail_goods_no_get import sync as get_product_description

# Product Recommendation
from common.tstation_be_api_client.hkt_api_client.api.product_recommendation_af_상품_추천.get_recommendations_api_product_recommend_get import sync as get_products_recommendations
from common.tstation_be_api_client.hkt_api_client.models import RcmdType

client = Client(base_url=settings.TSTATION_BE_API)

DOMAIN_TOOL_MAP = {
    "discovery": {
        # Product Compatibility
        "check_compatibility",
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
def get_compatibility_tool(car_no: str, goods_no: str):
    """
    Check tire compatibility between a vehicle and a product.

    Using the vehicle number (CAR_NO), the API retrieves the front and rear tire sizes
    from PR_CAR_BASE and PR_CAR_ATTR. Using the product number (GOODS_NO), it retrieves
    the tire specifications (section width, aspect ratio, and rim inch) from PR_GOODS_BASE.
    The system then verifies whether the tire product is compatible with the vehicle.

    Until the CarZen API integration is completed, the system prioritizes internal
    database information for compatibility checks.

    Args:
        car_no (str): Vehicle number.
        goods_no (str): Product number.

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        CompatibilityResponse | HTTPValidationError
    """
    res = get_compatibility(
        client=client,
        car_no=car_no,
        goods_no=goods_no
    )
    logger.info("[TOOL][get_compatibility_tool]")
    logger.info(f"Response: {res}")

    return res

@tool
def post_vehicle_verify_owner_tool(car_no: str):
    """
    Verify vehicle ownership.

    This API verifies whether the user is the registered owner of a vehicle
    based on the provided request information.

    Args:
        car_no (str): Request payload containing the information
            required to verify vehicle ownership.

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | VerifyOwnerResponse]
    """
    body = VerifyOwnerRequest(car_no=car_no)
    res = post_vehicle_verify_owner(
            client=client,
            body=body,
        )
    logger.info("[TOOL][post_vehicle_verify_owner_tool]")
    logger.info(f"Response: {res}")

    return res

@tool
def get_compatible_product_tool(goods_no: str):
    """
    Get compatible products.

    Retrieve products that are compatible with the given product number.
    This is typically used to find alternative or similar tire products
    that match the same specifications or compatibility conditions.

    Args:
        goods_no (str): Product number.

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """
    res = get_compatible_product(
        client=client,
        goods_no=goods_no,
    )
    logger.info("[TOOL][get_compatible_product_tool]")
    logger.info(f"Response: {res}")

    return res

@tool
def get_user_vehicles_tool(car_no: str):
    """
    Get user vehicles.

    Retrieve vehicle information associated with the given vehicle
    registration number.

    Args:
        car_no (str): Vehicle registration number.

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """
    res = get_user_vehicles(
        client=client,
        car_no=car_no,
    )
    logger.info("[TOOL][get_user_vehicles_tool]")
    logger.info(f"Response: {res}")

    return res


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

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProductDescResponse
    """

    res = get_product_description(
        client=client,
        goods_no=goods_no
    )
    logger.info("[TOOL][get_product_description_tool]")
    logger.info(f"Response: {res}")

    return res


@tool
def get_products_recommendations_tool(rcmd_type: RcmdType, limit: int = 10):
    """
    Product Recommendation

    Returns the top N products based on the selected recommendation type (rcmd_type).

    Recommendation types:
    - tstation: T-Station recommended products
      (FST_DISP_YN='Y', sorted by highest TOT_SCR*10, from PR_GOODS_RCMD_SUM)

    - discount: Highest discount rate
      (sorted by highest EXTRA_FVR_SALE_PER, from PR_GOODS_DSCNT_PRC_INFO)

    - value: Best value products
      (discounted price ≤ 200,000 KRW, sorted by high durability and fuel efficiency,
      from PR_GOODS_DSCNT_PRC_INFO + PR_GOODS_RCMD_SUM)

    Args:
        rcmd_type (RcmdType): Recommendation type.
        limit (int, optional): Number of products to return. Default is 10, maximum is 100.

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RecommendationResponse
    """

    res = get_products_recommendations(
        client=client,
        rcmd_type=rcmd_type,
        limit=limit,
    )
    logger.info("[TOOL][get_products_recommendations_tool]")
    logger.info(f"Response: {res}")

    return res
