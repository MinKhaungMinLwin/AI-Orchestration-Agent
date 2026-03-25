import logging
from typing import Any, List, Dict

from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from services.tstation.common.tstation_be_client import get_tstation_be_client
from langchain.tools import tool

logger = logging.getLogger(__name__)

# STORE AF
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_nearby_stores_api_store_nearby_post import sync_detailed as get_nearby_stores
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_list_api_store_list_get import sync_detailed as get_store_list
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_detail_api_store_detail_get import sync_detailed as get_store_detail
from common.tstation_be_api_client.hkt_api_client.models import NearbyStoreRequest

# PRICE AF
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_price_api_prices_final_get import sync_detailed as get_price

# INVENTORY AF
from common.tstation_be_api_client.hkt_api_client.api.inventory_af_재고_조회.get_logistics_inventory_api_inventory_logistics_post import sync_detailed as get_logistics_inventory
from common.tstation_be_api_client.hkt_api_client.api.inventory_af_재고_조회.get_store_inventory_api_inventory_store_post import sync_detailed as get_store_inventory
from common.tstation_be_api_client.hkt_api_client.models import (
    LogisticsRequest,
    StoreInventoryRequest,
    GoodsItem,
    ShopIdItem
)

# QUICK SHOPPING AF
from common.tstation_be_api_client.hkt_api_client.api.quick_shopping_af_퀵_쇼핑주문서_초안_생성.create_quick_order_api_quick_order_draft_post import sync_detailed as create_quick_order
from common.tstation_be_api_client.hkt_api_client.models import QuickOrderRequest

# ORDER & DELIVERY AF
from common.tstation_be_api_client.hkt_api_client.api.order_delivery_af_주문_및_배송_추적.get_order_delivery_api_orders_summary_get import sync_detailed as get_order_delivery


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
        goods_no (str): Product number (e.g., G000000314254).
        member_type (str | None): Member type (e.g., 'general', 'PARTNER').

    Example Inputs:
        - {"goods_no": "G000000314254", "member_type": "general"}
        - {"goods_no": "G000000312692", "member_type": "PARTNER"}
        - {"goods_no": "G000000310122", "member_type": "general"}

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


# =====================================================
# INVENTORY TOOLS
# =====================================================

@tool
def get_logistics_inventory_tool(goods_no: str):
    """
    Get product logistics inventory.

    Retrieve logistics stock using the product number.
    Returns stock quantity from logistics warehouse.

    Args:
        goods_no (str): Product number.

    Example Inputs:
        - {"goods_no": "G000000313165"}
        - {"goods_no": "G000000309860"}
        - {"goods_no": "G000000313073"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
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
            Input format: [{"goodsNo": "G123", "qty": 4}]
        shop_id_list (List[Dict[str, Any]]): Store list for stock check.
            Input format: [{"shopId": "F0001"}]

    Example Inputs:
        - {"goods_list": [{"goodsNo": "G000000309860", "qty": "4"}], "shop_id_list": [{"shopId": "B01018"}]}

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
def get_nearby_stores_tool(user_xpos: float, user_ypos: float, radius_km: float = 20.0, svc_codes: List[str] | None = None):
    """
    Get nearby stores.

    Retrieve stores within specified radius (default 20km) based on customer coordinates,
    including distance (km) from customer location.

    Args:
        user_xpos (float): Customer current X coordinate (longitude).
        user_ypos (float): Customer current Y coordinate (latitude).
        radius_km (float): Search radius in km (default 20km).
        svc_codes (List[str] | None): Service category codes.
            Returns stores that have ANY of the specified services.
            Example: ["101", "102"]

    Example Inputs:
        - {"user_xpos": 127.0276, "user_ypos": 37.4979, "radius_km": 20, "svc_codes": ["101", "102"]}
        - {"user_xpos": 126.9780, "user_ypos": 37.5665, "radius_km": 20, "svc_codes": ["101"]}
        - {"user_xpos": 103.8198, "user_ypos": 1.3521, "radius_km": 20, "svc_codes": []}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    body = NearbyStoreRequest(user_xpos=user_xpos, user_ypos=user_ypos, radius_km=radius_km, svc_codes=svc_codes)
    logger.info("[TOOL][get_nearby_stores_tool] Called with: user_xpos=%s, user_ypos=%s, radius_km=%s, svc_codes=%s", user_xpos, user_ypos, radius_km, svc_codes)

    try:
        response = get_nearby_stores(client=get_client(), body=body)
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
def get_store_list_tool(region_code: str | None = None, store_nm: str | None = None, limit: int = 20):
    """
    Get store list by region.

    Retrieve store list based on region name (ADDR_BASE, ADDR_DTL LIKE search).
    Returns all stores if region_code is not provided.

    Args:
        region_code (str | None): Region search term (ADDR_BASE, ADDR_DTL LIKE search), Using Korean address, Examples: '서울', '강남'
        store_nm (str | None): Store name search term.
        limit (int): Maximum number of stores to return (default 20).

    Example Inputs:
        - {"region_code": "서울", "store_nm": "삼송타이어", "limit": 20}
        - {"region_code": "강남", "store_nm": "극동상사", "limit": 20}
        - {"region_code": "부산", "store_nm": "한국타이어", "limit": 20}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
    """
    logger.info("[TOOL][get_store_list_tool] Called with: region_code=%s, store_nm=%s, limit=%s", region_code, store_nm, limit)

    try:
        response = get_store_list(client=get_client(), region_code=region_code, store_nm=store_nm, limit=limit)
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

    Args:
        shop_id (str): Store ID.
        cal_day (str): Query date in YYYYMMDD format.

    Example Inputs:
        - {"shop_id": "B00712", "cal_day": "20260401"}
        - {"shop_id": "B01018", "cal_day": "20250225"}
        - {"shop_id": "F00015", "cal_day": "20260320"}
        - {"shop_id": "F00098", "cal_day": "20260401"}
        - {"shop_id": "C07941", "cal_day": "20250225"}

    Returns:
        dict: {"status": "success", "http_status": ..., "data": ...} or {"status": "error", "http_status": ..., "reason": ..., "message": ...}
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
