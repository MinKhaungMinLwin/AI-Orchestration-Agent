"""Transaction tools — pricing, coupons, stores, orders.

Re-exports from agents/c_transaction_agent/tools.py. Write tools
(order/cart/coupon) are listed separately so the executor prompt can
require explicit user confirmation before they run.
"""

from services.tstation.agents.c_transaction_agent.tools import (
    get_coupon_applicable_products_tool,
    get_favorite_stores_tool,
    get_final_price_tool,
    get_maintenance_history_tool,
    get_my_coupons_tool,
    get_my_reservations_tool,
    get_nearby_stores_tool,
    get_order_status_tool,
    get_orders_of_user_tool,
    get_product_promotions_tool,
    get_store_detail_tool,
    get_store_install_availability_tool,
    get_store_list_tool,
    get_stores_with_time_filter_tool,
    issue_coupon_tool,
    present_order_preview_tool,
    quick_order_tool,
    save_to_cart_tool,
    search_place_tool,
    search_stores_complex_tool,
    search_stores_tool,
    transaction_store_preview_tool,
)
from services.tstation.agents.b_discovery_agent.tools import search_product_tool

TRANSACTION_READ_TOOLS = [
    search_product_tool,
    get_final_price_tool,
    get_my_coupons_tool,
    get_coupon_applicable_products_tool,
    get_product_promotions_tool,
    get_store_install_availability_tool,
    search_place_tool,
    get_nearby_stores_tool,
    get_store_list_tool,
    search_stores_tool,
    search_stores_complex_tool,
    get_store_detail_tool,
    get_stores_with_time_filter_tool,
    transaction_store_preview_tool,
    present_order_preview_tool,
    get_order_status_tool,
    get_orders_of_user_tool,
    get_maintenance_history_tool,
    get_my_reservations_tool,
    get_favorite_stores_tool,
]

TRANSACTION_WRITE_TOOLS = [
    save_to_cart_tool,
    quick_order_tool,
    issue_coupon_tool,
]

TRANSACTION_TOOLS = TRANSACTION_READ_TOOLS + TRANSACTION_WRITE_TOOLS
