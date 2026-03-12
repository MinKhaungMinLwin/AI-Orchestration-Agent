from typing import Optional, List, Dict, Any # Added Dict and Any here
from pydantic import BaseModel, Field
from langchain.tools import tool
from config.env import settings
from common.tstation_be_api_client.hkt_api_client.client import Client

# --- STORE AF (Imports) ---
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_nearby_stores_api_store_nearby_post import sync as get_nearby_stores
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_list_api_store_list_get import sync as get_store_list
from common.tstation_be_api_client.hkt_api_client.api.store_af_매장_정보_및_예약_조회.get_store_detail_api_store_detail_get import sync as get_store_detail
from common.tstation_be_api_client.hkt_api_client.models import NearbyStoreRequest

# --- PRICE AF Imports ---
from common.tstation_be_api_client.hkt_api_client.api.price_af_가격_및_할인_조회.get_price_api_prices_final_get import sync as get_price

# --- INVENTORY AF Imports ---
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

# Initialize the API Client
client = Client(base_url=settings.TSTATION_BE_API)


# ==========================================
# STORE AF TOOLS
# ==========================================

@tool
def get_nearby_stores_tool(user_xpos: float, user_ypos: float, svc_codes: Optional[List[str]] = None):
    """
    Retrieve nearby stores based on user coordinates.
    Returns the closest stores (max 20) and their distance in km.
    """
    body = NearbyStoreRequest(user_xpos=user_xpos, user_ypos=user_ypos, svc_codes=svc_codes)
    res = get_nearby_stores(client=client, body=body)
    print("[TOOL][get_nearby_stores_tool]\n", res)
    return res

@tool
def get_store_list_tool(region_code: Optional[str] = None, limit: int = 20):
    """
    Retrieve store list based on region keyword.
    Uses ROAD_ADDR_BASE LIKE search (e.g., '서울', '강남'). If region_code is empty, retrieves all.
    """
    res = get_store_list(client=client, region_code=region_code, limit=limit)
    print("[TOOL][get_store_list_tool]\n", res)
    return res

@tool
def get_store_detail_tool(shop_id: str, cal_day: str):
    """
    Retrieve store details and available reservation times.
    cal_day must be in YYYYMMDD format.
    """
    res = get_store_detail(client=client, shop_id=shop_id, cal_day=cal_day)
    print("[TOOL][get_store_detail_tool]\n", res)
    return res


# ==========================================
# PRICE AF TOOLS
# ==========================================

@tool
def get_final_price_tool(goods_no: str, member_type: Optional[str] = None):
    """
    Price AF: GET /api/prices/final
    Retrieve product base price, discount price, and labor cost.
    """
    res = get_price(client=client, goods_no=goods_no, member_type=member_type)
    print("[TOOL][get_final_price_tool]\n", res)
    return res


# ==========================================
# INVENTORY AF TOOLS
# ==========================================
@tool
def get_logistics_inventory_tool(goods_no: str):
    """
    Inventory AF: POST /api/inventory/logistics
    Retrieve logistics inventory quantity for a specific product.
    """
    body = LogisticsRequest(goods_no=goods_no)
    res = get_logistics_inventory(client=client, body=body)
    print("[TOOL][get_logistics_inventory_tool]\n", res)
    return res

@tool
def get_md_inventory_tool(goods_no: str, shop_id: str):
    """
    Inventory AF: POST /api/inventory/md
    Retrieve MD inventory quantity for a specific product at a specific shop.
    """
    body = MdInventoryRequest(goods_no=goods_no, shop_id=shop_id)
    res = get_md_inventory(client=client, body=body)
    print("[TOOL][get_md_inventory_tool]\n", res)
    return res

@tool
def get_store_inventory_tool(goods_list: List[Dict[str, Any]], shop_id_list: List[Dict[str, Any]]):
    """
    Inventory AF: POST /api/inventory/store
    Check if a product is available at specific stores today or via T-NA delivery.
    
    Args:
        goods_list: List of dicts, e.g., [{"goodsNo": "G123", "qty": 4}]
        shop_id_list: List of dicts, e.g., [{"shopId": "F0001"}]
    """
    # Parse generic dicts into Pydantic models required by the API
    g_items = [GoodsItem(goodsNo=g["goodsNo"], qty=g["qty"]) for g in goods_list]
    s_items = [ShopIdItem(shopId=s["shopId"]) for s in shop_id_list]
    
    body = StoreInventoryRequest(goodsList=g_items, shopIdList=s_items)
    res = get_store_inventory(client=client, body=body)
    print("[TOOL][get_store_inventory_tool]\n", res)
    return res