import logging
from typing import Any

from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from services.tstation.common.tstation_be_client import get_tstation_be_client
from langchain.tools import tool

logger = logging.getLogger(__name__)

# Store AF
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_nearby_stores_api_store_nearby_post import sync_detailed as get_nearby_stores
from common.tstation_be_api_client.hkt_api_client.models import NearbyStoreRequest
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_detail_api_store_detail_get import sync_detailed as get_store_details
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_list_api_store_list_get import sync_detailed as get_store_list

# Quick Shopping AF
from common.tstation_be_api_client.hkt_api_client.api.quick_shopping_af_퀵_쇼핑주문서_초안_생성.create_quick_order_api_quick_order_draft_post import sync_detailed as create_quick_order
from common.tstation_be_api_client.hkt_api_client.models import QuickOrderRequest

# Order & Delivery AF
from common.tstation_be_api_client.hkt_api_client.api.order_delivery_af_주문_및_배송_추적.get_order_delivery_api_orders_summary_get import sync_detailed as get_order_delivery


def get_client() -> AuthenticatedClient:
    """Get authenticated client for tstation-be API."""
    return get_tstation_be_client()


DOMAIN = {
    # Quick Order
        "create_quick_order",

        # Order / Delivery
        "get_order_delivery",
}


def _to_dict(res: Any) -> Any:
    return res.to_dict() if hasattr(res, 'to_dict') else (res.model_dump() if hasattr(res, 'model_dump') else res)


def _error_response(http_status: int | None, reason: str, message: str) -> dict:
    return {"status": "error", "http_status": http_status, "reason": reason, "message": message}


def _success_response(http_status: int, data: Any) -> dict:
    return {"status": "success", "http_status": http_status, "data": data}


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

    Example Inputs:
        - {"user_xpos": 127.0276, "user_ypos": 37.4979}
        - {"user_xpos": 126.9780, "user_ypos": 37.5665}
        - {"user_xpos": 103.8198, "user_ypos": 1.3521}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    body = NearbyStoreRequest(
        user_xpos=user_xpos,
        user_ypos=user_ypos,
        svc_codes=None
    )

    logger.info("[TOOL][get_nearby_stores_tool] Called with: user_xpos=%s, user_ypos=%s", user_xpos, user_ypos)

    try:
        response = get_nearby_stores(client=get_client(), body=body)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to retrieve nearby stores"
            )
        logger.info("[TOOL][get_nearby_stores_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_nearby_stores_tool] Failed")
        return _error_response(None, str(e), "Failed to retrieve nearby stores")


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
        shop_id (str): Store ID in the correct format (e.g., "C01294", "B01260", "A00123").
        cal_day (str): Date to check reservation availability (format: YYYYMMDD).

    Example Inputs:
        - {"shop_id": "B00712", "cal_day": "20260401"}
        - {"shop_id": "B01018", "cal_day": "20250225"}
        - {"shop_id": "F00015", "cal_day": "20260320"}
        - {"shop_id": "F00098", "cal_day": "20260401"}
        - {"shop_id": "C07941", "cal_day": "20250225"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """

    logger.info("[TOOL][get_store_details_tool] Called with: shop_id=%s, cal_day=%s", shop_id, cal_day)

    try:
        response = get_store_details(client=get_client(), shop_id=shop_id, cal_day=cal_day)
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to retrieve store details"
            )
        logger.info("[TOOL][get_store_details_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_store_details_tool] Failed")
        return _error_response(None, str(e), "Failed to retrieve store details")


@tool
def get_store_list_tool(
    region_code: str | None = None,
    store_nm: str | None = None,
    limit: int = 20
):
    """
    Retrieve a list of stores filtered by region keyword and/or store name.

    The system searches store addresses using partial match (LIKE search) on region,
    and/or searches store names using partial match on store_nm.

    If neither REGION_CODE nor STORE_NM is provided, the API returns all stores
    up to the specified limit.

    This tool should be used when the user asks for:
    - User mentions a store by name (e.g. "삼송타이어", "극동상사")
    - User searches for stores in a specific city or district (e.g. "서울", "강남")
    - a list of stores within a particular area
    - User need to look up shop_id before calling get_store_details_tool


    Do NOT use this tool when:
    - the user asks for stores near their current location (use the nearby store tool)
    - the user asks for reservation availability or store details for a specific store

    Args:
        region_code (str | None): Region keyword for address search (Korean address).
            Examples: '서울', '강남', '부산', '송파구'. Optional.
        store_nm (str | None): Store name keyword for partial match search.
            Use this when the user mentions a store by name.
            Examples: '삼송타이어', '극동상사', '한국타이어'. Optional.
        limit (int): Maximum number of stores to return. Default is 20.

    Example Inputs:
        - {"region_code": "서울", "store_nm": "삼송타이어", "limit": 20}
        - {"region_code": "강남", "store_nm": "극동상사", "limit": 20}
        - {"region_code": "부산", "store_nm": "한국타이어", "limit": 20}
        - {"region_code": "송파구", "store_nm": "삼송타이어", "limit": 20}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """

    logger.info("[TOOL][get_store_list_tool] Called with: region_code=%s, limit=%s", region_code, limit)

    try:
        response = get_store_list(
            client=get_client(), 
            region_code=region_code, 
            store_nm=store_nm,
            limit=limit
        )
        if response.parsed is None:
            return _error_response(
                response.status_code,
                f"HTTP {response.status_code}",
                response.content.decode(errors="ignore") or "Failed to retrieve store list"
            )
        logger.info("[TOOL][get_store_list_tool] Response: %s", response.parsed)
        return _success_response(response.status_code, _to_dict(response.parsed))
    except Exception as e:
        logger.exception("[TOOL][get_store_list_tool] Failed")
        return _error_response(None, str(e), "Failed to retrieve store list")


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

    Example Inputs:
        - {"goods_no": "G000000313165", "ord_qty": 2, "mbr_no": "M200012931"}
        - {"goods_no": "G000000309860", "ord_qty": 1, "mbr_no": "M200012932"}
        - {"goods_no": "G000000313073", "ord_qty": 3, "mbr_no": "M200012933"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """

    # TODO: [MOCK] Remove mock and use real API
    logger.info("[TOOL][create_order_draft_tool] [MOCK] Called with: goods_no=%s, ord_qty=%s, mbr_no=%s", goods_no, ord_qty, mbr_no)
    return _success_response(200, {"redirect_url": "https://example.com/quick-order/draft"})

    # body = QuickOrderRequest(
    #     goods_no=goods_no,
    #     ord_qty=ord_qty,
    #     mbr_no=mbr_no,
    # )
    #
    # logger.info("[TOOL][create_order_draft_tool] Called with: goods_no=%s, ord_qty=%s, mbr_no=%s", goods_no, ord_qty, mbr_no)
    #
    # try:
    #     response = create_quick_order(client=get_client(), body=body)
    #     if response.parsed is None:
    #         return _error_response(
    #             response.status_code,
    #             f"HTTP {response.status_code}",
    #             response.content.decode(errors="ignore") or "Failed to create quick order draft"
    #         )
    #     logger.info("[TOOL][create_order_draft_tool] Response: %s", response.parsed)
    #     return _success_response(response.status_code, _to_dict(response.parsed))
    # except Exception as e:
    #     logger.exception("[TOOL][create_order_draft_tool] Failed")
    #     return _error_response(None, str(e), "Failed to create quick order draft")



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

    Example Inputs:
        - {"ord_no": "ORD20260325001"}
        - {"ord_no": "ORD20260325002"}
        - {"ord_no": "ORD20260325003"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """

    # TODO: [MOCK] Remove mock and use real API
    logger.info("[TOOL][get_order_status_tool] [MOCK] Called with: ord_no=%s", ord_no)
    mock_data = {
        "ord_no": ord_no,
        "ord_status": "ORDER_RECEIVED",
        "ord_status_nm": "Order Received",
        "dlv_status": "PREPARING",
        "dlv_status_nm": "Preparing for Shipment",
        "tracking_no": "MOCK-TRACK-123456",
        "dlv_company_nm": "CJ Korea Express",
        "ord_qty": 4,
        "goods_nm": "Hankook Tire Ventus V12 evo2 K120",
        "store_nm": "Mock Store Name",
        "ord_dt": "2026-03-24 10:30:00",
        "dlv_est_dt": "2026-03-27",
    }
    return _success_response(200, mock_data)

    # logger.info("[TOOL][get_order_status_tool] Called with: ord_no=%s", ord_no)
    #
    # try:
    #     response = get_order_delivery(client=get_client(), ord_no=ord_no)
    #     if response.parsed is None:
    #         return _error_response(
    #             response.status_code,
    #             f"HTTP {response.status_code}",
    #             response.content.decode(errors="ignore") or "Failed to retrieve order status"
    #         )
    #     logger.info("[TOOL][get_order_status_tool] Response: %s", response.parsed)
    #     return _success_response(response.status_code, _to_dict(response.parsed))
    # except Exception as e:
    #     logger.exception("[TOOL][get_order_status_tool] Failed")
    #     return _error_response(None, str(e), "Failed to retrieve order status")
