from typing import Optional, List, Dict, Any
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
    주변 매장 목록 조회
    
    고객 좌표 기준으로 가까운 매장 최대 20개와 거리(km)를 반환합니다.
    """
    body = NearbyStoreRequest(user_xpos=user_xpos, user_ypos=user_ypos, svc_codes=svc_codes)
    res = get_nearby_stores(client=client, body=body)
    print("[TOOL][get_nearby_stores_tool]\n", res)
    return res

@tool
def get_store_list_tool(region_code: Optional[str] = None, limit: int = 20):
    """
    매장 목록 조회
    
    지역명(도로명주소 LIKE 검색) 기준으로 매장 목록을 반환합니다. region_code 미입력 시 전체 조회.
    """
    res = get_store_list(client=client, region_code=region_code, limit=limit)
    print("[TOOL][get_store_list_tool]\n", res)
    return res

@tool
def get_store_detail_tool(shop_id: str, cal_day: str):
    """
    매장 상세 정보 및 예약 가능 시간 조회
    
    매장 ID와 날짜를 기준으로 매장 정보와 예약 가능 시간 슬롯(시 단위)을 반환합니다.
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
    상품 가격 및 할인 조회
    
    상품 번호로 기본 판매가, 최대 혜택가(프로모션·쿠폰 적용), 공임비 및 오늘의 공임비를 반환합니다.
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
    상품 물류 재고 조회
    
    물류 재고(오라클 함수 FN_GET_GOODS_STOCK_QTY)를 반환합니다.
    """
    body = LogisticsRequest(goods_no=goods_no)
    res = get_logistics_inventory(client=client, body=body)
    print("[TOOL][get_logistics_inventory_tool]\n", res)
    return res

@tool
def get_md_inventory_tool(goods_no: str, shop_id: str):
    """
    MD 재고 조회 (참고용)
    
    PR_INV_MD_STOCK_INFO (백업용 DB) - INV_QTY (재고 수량)
    """
    body = MdInventoryRequest(goods_no=goods_no, shop_id=shop_id)
    res = get_md_inventory(client=client, body=body)
    print("[TOOL][get_md_inventory_tool]\n", res)
    return res

@tool
def get_store_inventory_tool(goods_list: List[Dict[str, Any]], shop_id_list: List[Dict[str, Any]]):
    """
    매장 재고 가용 여부 조회
    
    상품 목록과 매장 목록을 입력받아 오늘 장착 가능 매장(todayShopArray)과 T바로배송 가능 매장(tnaShopArray)을 반환합니다.
    
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