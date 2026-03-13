import logging

from common.tstation_be_api_client.hkt_api_client.client import Client
from config.env import settings
from langchain.tools import tool

logger = logging.getLogger(__name__)

# Store AF
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_nearby_stores_api_store_nearby_post import sync as get_nearby_stores
from common.tstation_be_api_client.hkt_api_client.models import NearbyStoreRequest
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_detail_api_store_detail_get import sync as get_store_details   
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_list_api_store_list_get import sync as get_store_list  

# Quick Shopping AF
from common.tstation_be_api_client.hkt_api_client.api.quick_shopping_af_퀵_쇼핑주문서_초안_생성.create_quick_order_api_quick_order_draft_post import sync as create_quick_order
from common.tstation_be_api_client.hkt_api_client.models import QuickOrderRequest

# Order & Delivery AF
from common.tstation_be_api_client.hkt_api_client.api.order_delivery_af_주문_및_배송_추적.get_order_delivery_api_orders_summary_get import sync as get_order_delivery


client = Client(base_url=settings.TSTATION_BE_API)

DOMAIN = {
    # Quick Order
        "create_quick_order",

        # Order / Delivery
        "get_order_delivery",
}

# =====================================================
# STORE AF
# =====================================================

@tool
def get_nearby_stores_tool(user_xpos: float, user_ypos: float):
    """
    Retrieve nearby stores based on the user's geographic coordinates.

    Using the user's longitude (USER_XPOS) and latitude (USER_YPOS),
    the system queries the Store AF service to locate stores near the user.
    The API calculates the distance between the user's coordinates and
    each store location, returning up to 20 stores sorted by proximity.

    This tool should be used when the user asks for:
    - stores near their current location
    - the closest store
    - nearby service centers
    - stores around their coordinates

    The response includes store information along with the distance (km)
    from the user's location.

    Args:
        user_xpos (float): User longitude coordinate.
        user_ypos (float): User latitude coordinate.

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        NearbyStoreResponse | HTTPValidationError
    """
    body = NearbyStoreRequest(
        user_xpos=user_xpos,
        user_ypos=user_ypos,
        svc_codes=None
    )

    logger.info("[TOOL][get_nearby_stores_tool] Called with: user_xpos=%s, user_ypos=%s", user_xpos, user_ypos)
    res = get_nearby_stores(
        client=client,
        body=body
    )

    logger.info("[TOOL][get_nearby_stores_tool] Response: %s", res)

    return res


@tool
def get_store_details_tool(shop_id: str, cal_day: str):
    """
    Retrieve store details and available reservation time slots.

    Using the store ID (SHOP_ID) and the requested date (CAL_DAY),
    the API retrieves detailed information about the store and the
    available reservation time slots for that day.

    The system queries the Store AF service to obtain:
    - Store information (name, address, contact details, etc.)
    - Available reservation time slots (hourly units)

    This tool should be used when the user asks for:
    - detailed information about a specific store
    - reservation availability for a store
    - available booking times for a specific date
    - service appointment slots at a store

    Args:
        shop_id (str): Store ID.
        cal_day (str): Date to check reservation availability (format: YYYYMMDD).

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        StoreDetailResponse | HTTPValidationError:
            Contains store information and available reservation time slots.
    """

    logger.info("[TOOL][get_store_details_tool] Called with: shop_id=%s, cal_day=%s", shop_id, cal_day)
    res = get_store_details(
        client=client,
        shop_id=shop_id,
        cal_day=cal_day
    )

    logger.info("[TOOL][get_store_details_tool] Response: %s", res)

    return res


@tool
def get_store_list_tool(region_code: str | None = None, limit: int = 20):
    """
    Retrieve a list of stores filtered by a region keyword.

    Using the region keyword (REGION_CODE), the system searches store
    road addresses (ROAD_ADDR_BASE) using a partial match (LIKE search)
    and returns stores located in the specified region.

    If REGION_CODE is not provided, the API returns stores from all regions
    up to the specified limit.

    This tool should be used when the user asks for:
    - stores located in a specific city or district
    - stores in a region (e.g., "stores in Seoul", "stores in Gangnam")
    - a list of stores within a particular area

    Do NOT use this tool when:
    - the user asks for stores near their current location (use the nearby store tool)
    - the user asks for reservation availability or store details for a specific store

    Args:
        region_code (str | None): Region keyword used to filter stores
            (e.g., "서울", "강남"). Optional.
        limit (int): Maximum number of stores to return. Default is 20.

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        StoreListResponse | HTTPValidationError:
            Contains a list of stores matching the region filter.
    """

    logger.info("[TOOL][get_store_list_tool] Called with: region_code=%s, limit=%s", region_code, limit)
    res = get_store_list(
        client=client,
        region_code=region_code,
        limit=limit
    )

    logger.info("[TOOL][get_store_list_tool] Response: %s", res)

    return res

# =====================================================
# QUICK SHOPPING AF
# =====================================================

@tool
def create_order_draft_tool(goods_no: str, ord_qty: int, mbr_no: str | None = None):
    """
    Create a quick shopping order draft and generate a checkout page URL.

    This tool calls the Quick Shopping API to validate a product and create
    an order draft for the user.

    The API checks the product information from PR_GOODS_BASE, including:
    - product sales status
    - minimum order quantity

    If the product is valid and the quantity is allowed, the system generates
    a REDIRECT_URL that leads to the order creation page where the user can
    complete the purchase.

    Use this tool when the user wants to:
    - buy a product immediately
    - create an order draft
    - proceed to checkout for a specific product

    Args:
        goods_no (str): Product number (e.g., G000000314254).
        ord_qty (int): Quantity the user wants to purchase, min is 1.
        mbr_no (None | str | Unset): Member number. If provided, the order draft
            will be created for that member. If not provided, the checkout
            page will ask the user to enter member information.

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        QuickOrderResponse | HTTPValidationError
            - redirect_url: URL to the order checkout page
            - validation error if the product or quantity is invalid
    """

    body = QuickOrderRequest(
        goods_no=goods_no,
        ord_qty=ord_qty,
        mbr_no=mbr_no,
    )

    logger.info("[TOOL][create_order_draft_tool] Called with: goods_no=%s, ord_qty=%s, mbr_no=%s", goods_no, ord_qty, mbr_no)
    res = create_quick_order(
        client=client,
        body=body,
    )

    logger.info("[TOOL][create_order_draft_tool] Response: %s", res)

    return res



# =====================================================
# ORDER & DELIVERY AF
# =====================================================

@tool
def get_order_status_tool(ord_no: str):
    """
    Retrieve order processing status and delivery tracking information.

    This tool queries the Order & Delivery API using the order number (ORD_NO).
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
        ord_no (str): Order number.

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        OrderDeliveryResponse | HTTPValidationError:
            - order status from OP_ORD_DTL_INFO
            - delivery status and tracking information from OP_ORD_DLV_DTL_INFO
    """

    logger.info("[TOOL][get_order_status_tool] Called with: ord_no=%s", ord_no)
    res = get_order_delivery(
        client=client,
        ord_no=ord_no
    )

    logger.info("[TOOL][get_order_status_tool] Response: %s", res)

    return res