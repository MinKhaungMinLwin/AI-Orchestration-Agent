"""Discovery tools — product recommendation, compatibility, vehicle lookup.

Re-exports from agents/b_discovery_agent/tools.py; V3 never reimplements tools.
"""

from services.tstation.agents.b_discovery_agent.tools import (
    check_compatibility_tool,
    compare_discount_tool,
    get_benefit_event_deal_list_tool,
    get_best_selling_products_tool,
    get_car_trims_tool,
    get_cheapest_price_tool,
    get_deals_tool,
    get_event_applicable_products_tool,
    get_events_tool,
    get_final_price_tool,
    get_my_cars_tool,
    get_newest_products_tool,
    get_product_applicable_events_tool,
    get_product_description_tool,
    get_products_recommendations_tool,
    get_user_vehicles_tool,
    search_benefit_applicable_products_tool,
    search_car_model_groups_tool,
    search_car_model_tool,
    search_product_summary_tool,
    search_product_tool,
)

DISCOVERY_TOOLS = [
    search_product_tool,
    search_product_summary_tool,
    get_products_recommendations_tool,
    get_best_selling_products_tool,
    get_newest_products_tool,
    get_product_description_tool,
    check_compatibility_tool,
    get_user_vehicles_tool,
    get_my_cars_tool,
    search_car_model_tool,
    search_car_model_groups_tool,
    get_car_trims_tool,
    get_events_tool,
    get_deals_tool,
    get_benefit_event_deal_list_tool,
    search_benefit_applicable_products_tool,
    get_event_applicable_products_tool,
    get_product_applicable_events_tool,
    compare_discount_tool,
    get_cheapest_price_tool,
    get_final_price_tool,
]
