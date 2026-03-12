import logging
from typing import Optional, List, Dict, Any

from common.tstation_be_api_client.hkt_api_client.client import Client
from config.env import settings
from langchain.tools import tool

logger = logging.getLogger(__name__)

# STORE AF
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_nearby_stores_api_store_nearby_post import sync as get_nearby_stores
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_list_api_store_list_get import sync as get_store_list
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_detail_api_store_detail_get import sync as get_store_detail
from common.tstation_be_api_client.hkt_api_client.models import NearbyStoreRequest

# PRICE AF
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_price_api_prices_final_get import sync as get_price

# INVENTORY AF
from common.tstation_be_api_client.hkt_api_client.api.inventory_af_재고_조회.get_logistics_inventory_api_inventory_logistics_post import sync as get_logistics_inventory
from common.tstation_be_api_client.hkt_api_client.api.inventory_af_재고_조회.get_md_inventory_api_inventory_md_post import sync as get_md_inventory
from common.tstation_be_api_client.hkt_api_client.api.inventory_af_재고_조회.get_store_inventory_api_inventory_store_post import sync as get_store_inventory
from common.tstation_be_api_client.hkt_api_client.models import (
    LogisticsRequest,
    MdInventoryRequest,
    StoreInventoryRequest,
    GoodsItem,
    ShopIdItem
)


client = Client(base_url=settings.TSTATION_BE_API)


@tool
def get_final_price_tool(goods_no: str, member_type: str | None = None):
    """
    Get product price and discount.

    Retrieve base selling price, maximum discounted price (promotion + coupon),
    labor cost, and today's labor cost using the product number.

    Args:
        goods_no (str): Product number (e.g., G000000314254).
        member_type (str | None): Member type (e.g., 'general', 'PARTNER').

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        PriceResponse | HTTPValidationError
    """
    res = get_price(client=client, goods_no=goods_no, member_type=member_type)
    logger.info("[TOOL][get_final_price_tool]")
    logger.info(f"Response: {res}")
    return res


@tool
def get_logistics_inventory_tool(goods_no: str):
    """
    Get product logistics inventory.

    Retrieve logistics stock using the product number.
    Returns stock quantity from logistics warehouse.

    Args:
        goods_no (str): Product number.

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        LogisticsResponse | HTTPValidationError
    """
    body = LogisticsRequest(goods_no=goods_no)
    res = get_logistics_inventory(client=client, body=body)
    logger.info("[TOOL][get_logistics_inventory_tool]")
    logger.info(f"Response: {res}")
    return res


@tool
def get_md_inventory_tool(goods_no: str, shop_id: str):
    """
    Get MD stock at specific store.

    Retrieve MD stock information from PR_INV_MD_STOCK_INFO (backup DB).
    Returns INV_QTY (inventory quantity).

    Args:
        goods_no (str): Product number.
        shop_id (str): Store ID.

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        MdInventoryResponse | HTTPValidationError
    """
    body = MdInventoryRequest(goods_no=goods_no, shop_id=shop_id)
    res = get_md_inventory(client=client, body=body)
    logger.info("[TOOL][get_md_inventory_tool]")
    logger.info(f"Response: {res}")
    return res


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

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        StoreInventoryResponse | HTTPValidationError
    """
    g_items = [GoodsItem(goods_no=g["goodsNo"], qty=g["qty"]) for g in goods_list]
    s_items = [ShopIdItem(shop_id=s["shopId"]) for s in shop_id_list]
    body = StoreInventoryRequest(goods_list=g_items, shop_id_list=s_items)
    res = get_store_inventory(client=client, body=body)
    logger.info("[TOOL][get_store_inventory_tool]")
    logger.info(f"Response: {res}")
    return res


@tool
def get_nearby_stores_tool(user_xpos: float, user_ypos: float, svc_codes: List[str] | None = None):
    """
    Get nearby stores.

    Retrieve up to 20 nearest stores based on customer coordinates,
    including distance (km) from customer location.

    Args:
        user_xpos (float): Customer current X coordinate (longitude).
        user_ypos (float): Customer current Y coordinate (latitude).
        svc_codes (List[str] | None): Service category codes.
            Returns stores that have ANY of the specified services.
            Example: ["101", "102"]

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        NearbyStoreResponse | HTTPValidationError
    """
    body = NearbyStoreRequest(user_xpos=user_xpos, user_ypos=user_ypos, svc_codes=svc_codes)
    res = get_nearby_stores(client=client, body=body)
    logger.info("[TOOL][get_nearby_stores_tool]")
    logger.info(f"Response: {res}")
    return res


@tool
def get_store_list_tool(region_code: str | None = None, limit: int = 20):
    """
    Get store list by region.

    Retrieve store list based on region name (road address LIKE search).
    Returns all stores if region_code is not provided.

    Args:
        region_code (str | None): Region search term (road address LIKE search).
            Examples: '서울', '강남'
        limit (int): Maximum number of stores to return (default 20).

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        StoreListResponse | HTTPValidationError
    """
    res = get_store_list(client=client, region_code=region_code, limit=limit)
    logger.info("[TOOL][get_store_list_tool]")
    logger.info(f"Response: {res}")
    return res


@tool
def get_store_detail_tool(shop_id: str, cal_day: str):
    """
    Get store details and reservation availability.

    Retrieve store information and available reservation time slots (hourly)
    based on store ID and date.

    Args:
        shop_id (str): Store ID.
        cal_day (str): Query date in YYYYMMDD format.

    Raises:
        errors.UnexpectedStatus:
            If the server returns an undocumented status code and
            Client.raise_on_unexpected_status is True.

        httpx.TimeoutException:
            If the request takes longer than Client.timeout.

    Returns:
        StoreDetailResponse | HTTPValidationError
    """
    res = get_store_detail(client=client, shop_id=shop_id, cal_day=cal_day)
    logger.info("[TOOL][get_store_detail_tool]")
    logger.info(f"Response: {res}")
    return res
