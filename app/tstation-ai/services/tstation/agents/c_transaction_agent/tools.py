from common.tstation_be_api_client.hkt_api_client.client import Client
from config.env import settings
from langchain.tools import tool


client = Client(base_url=settings.TSTATION_BE_API)

DOMAIN = {
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
}
