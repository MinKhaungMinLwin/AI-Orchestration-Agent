from common.tstation_be_api_client.hkt_api_client.client import Client
from config.env import settings
from langchain.tools import tool


client = Client(base_url=settings.TSTATION_BE_API)

DOMAIN = {
    # Quick Order
    "create_quick_order",

    # Order / Delivery
    "get_order_delivery",
}
