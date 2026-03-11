from common.tstation_be_api_client.hkt_api_client.client import Client
from config.env import settings
from langchain.tools import tool

# Store AF
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_nearby_stores_api_store_nearby_post import sync as get_nearby_stores
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_detail_api_store_detail_get import sync as get_store_details   
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_list_api_store_list_get import sync as get_store_list  

# Quick Shopping AF
from common.tstation_be_api_client.hkt_api_client.api.quick_shopping_af_퀵쇼핑.create_quick_order_api_quick_order_post import sync as create_quick_order

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
    Retrieve nearby T-Station stores based on user coordinates.

    Args:
        user_xpos (float): User longitude coordinate.
        user_ypos (float): User latitude coordinate.

    Returns:
        StoreNearbyResponse | HTTPValidationError
    """

    res = get_nearby_stores(
        client=client,
        user_xpos=user_xpos,
        user_ypos=user_ypos
    )

    print("[TOOL][get_nearby_stores_tool]")
    print(res)

    return res


@tool
def get_store_details_tool(store_id: str, cal_day: str):
    """
    Retrieve store details and available reservation slots.

    Args:
        store_id (str): Store ID.
        cal_day (str): Date in YYYYMMDD format.

    Returns:
        StoreDetailResponse | HTTPValidationError
    """

    res = get_store_details(
        client=client,
        shop_id=store_id,
        cal_day=cal_day
    )

    print("[TOOL][get_store_details_tool]")
    print(res)

    return res


@tool
def get_store_list_tool(region: str | None = None):
    """
    Retrieve store list by region.

    Args:
        region (str | None): Region name (optional).

    Returns:
        StoreListResponse | HTTPValidationError
    """

    res = get_store_list(
        client=client,
        region=region
    )

    print("[TOOL][get_store_list_tool]")
    print(res)

    return res

# =====================================================
# QUICK SHOPPING AF
# =====================================================

@tool
def create_order_draft_tool(goods_no: str, store_id: str, quantity: int):
    """
    Create a quick order draft.

    This API generates a draft order for conversational checkout.

    Args:
        goods_no (str): Product number.
        store_id (str): Store ID.
        quantity (int): Quantity of tires.

    Returns:
        QuickOrderResponse | HTTPValidationError
    """

    body = QuickOrderRequest(
        goods_no=goods_no,
        store_id=store_id,
        quantity=quantity,
    )

    res = create_quick_order(
        client=client,
        body=body,
    )

    print("[TOOL][create_order_draft_tool]")
    print(res)

    return res

@tool
def generate_checkout_link_tool(order_id: str):
    """
    Generate checkout link for payment.

    This tool generates a payment link based on the created order draft.

    Args:
        order_id (str): Order ID.

    Returns:
        CheckoutLinkResponse
    """

    checkout_url = f"https://tstation.com/order/checkout?order_id={order_id}"

    res = {
        "order_id": order_id,
        "checkout_url": checkout_url
    }

    print("[TOOL][generate_checkout_link_tool]")
    print(res)

    return res

    # =====================================================
# ORDER & DELIVERY AF
# =====================================================

@tool
def get_order_status_tool(order_id: str):
    """
    Retrieve order and delivery status.

    Args:
        order_id (str): Order number.

    Returns:
        OrderDeliveryResponse | HTTPValidationError
    """

    res = get_order_delivery(
        client=client,
        ord_no=order_id
    )

    print("[TOOL][get_order_status_tool]")
    print(res)

    return res


@tool
def check_order_modification_tool(order_id: str):
    """
    Check whether an order can be modified or cancelled.

    Args:
        order_id (str): Order number.

    Returns:
        dict
    """

    res = get_order_delivery(
        client=client,
        ord_no=order_id
    )

    modification_allowed = res.ord_prgs_stat_cd in ["10", "20"]

    result = {
        "order_id": order_id,
        "modification_allowed": modification_allowed,
        "status": res.ord_prgs_stat_cd
    }

    print("[TOOL][check_order_modification_tool]")
    print(result)

    return result