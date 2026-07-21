"""Tool registry: routed domain → tools bound to the LLM.

Imports are lazy — agent tool modules pull in the BE API client, so we
only pay that cost when a domain actually needs tools.
"""

# tool_profile → tool-name subset (V2 agent-profile port, LLM-first: the
# router picks the profile; this is only a name filter over the domain union).
# A profile missing here, a multi-domain turn, or a filter that would drop
# every tool all fall back to the full union.
PROFILE_TOOL_NAMES: dict[str, frozenset[str]] = {
    "transaction_store": frozenset({
        "search_stores_tool",
        "search_stores_complex_tool",
        "search_place_tool",
        "get_nearby_stores_tool",
        "get_store_list_tool",
        "get_store_detail_tool",
        "get_stores_with_time_filter_tool",
        "get_store_install_availability_tool",
        "get_favorite_stores_tool",
        "transaction_store_preview_tool",
        # staggered install-availability flow searches both sizes first
        "search_product_tool",
    }),
    "transaction_order": frozenset({
        "save_to_cart_tool",
        "quick_order_tool",
        "present_order_preview_tool",
        "get_order_status_tool",
        "get_orders_of_user_tool",
        "get_my_reservations_tool",
        "get_maintenance_history_tool",
        "get_final_price_tool",
        # installation schedule change keeps product/store but re-picks a slot
        "get_store_install_availability_tool",
        # reservation-status conversations sometimes resolve the store first
        # ("I'm at the store but there's no booking") — seen in real traces
        "search_stores_complex_tool",
    }),
    "transaction_coupon": frozenset({
        "get_my_coupons_tool",
        "get_coupon_applicable_products_tool",
        "get_product_promotions_tool",
        "get_final_price_tool",
        "issue_coupon_tool",
        "search_product_tool",
    }),
    "transaction_price_stock": frozenset({
        "get_final_price_tool",
        "get_product_promotions_tool",
        "get_my_coupons_tool",
        "get_coupon_applicable_products_tool",
        # get_final_price_tool requires goods_no; without a resolver a price question that
        # names a product has no reachable answer and the model calls nothing at all.
        "search_product_tool",
    }),
    "discovery_search": frozenset({
        "search_product_tool",
        "search_product_summary_tool",
        "get_products_recommendations_tool",
        "get_newest_products_tool",
        "get_best_selling_products_tool",
        "get_product_description_tool",
        "compare_discount_tool",
        "get_final_price_tool",
    }),
    "discovery_recommendation": frozenset({
        "get_my_cars_tool",
        "get_user_vehicles_tool",
        "search_car_model_tool",
        "search_car_model_groups_tool",
        "get_car_trims_tool",
        "get_products_recommendations_tool",
        "get_product_description_tool",
        "search_product_tool",
        "search_product_summary_tool",
    }),
    "discovery_event_content": frozenset({
        "get_events_tool",
        "get_deals_tool",
        "get_benefit_event_deal_list_tool",
        "search_benefit_applicable_products_tool",
        "get_event_applicable_products_tool",
        "get_product_applicable_events_tool",
        "search_product_tool",
    }),
}


def tools_for_domain(domain: str) -> list:
    if domain == "DISCOVERY":
        from services.tstation.chat_v3.tools.discovery import DISCOVERY_TOOLS

        return DISCOVERY_TOOLS
    if domain == "TRANSACTION":
        from services.tstation.chat_v3.tools.transaction import TRANSACTION_TOOLS

        return TRANSACTION_TOOLS
    if domain == "SUPPORT":
        from services.tstation.chat_v3.tools.support import SUPPORT_TOOLS

        return SUPPORT_TOOLS
    return []  # LEADING — pure conversation, no tools


def tools_for_domains(domains: list[str], tool_profile: str | None = None) -> list:
    """Union of the domains' tools, deduped by tool name (V2 chained agents
    per domain; V3 gives one LLM every tool the turn needs instead).

    A narrow ``tool_profile`` filters the union by name, but only for
    single-domain turns — multi-domain turns keep the full union.
    """
    seen: set[str] = set()
    union = []
    for domain in domains:
        for tool in tools_for_domain(domain):
            if tool.name not in seen:
                seen.add(tool.name)
                union.append(tool)
    profile_names = PROFILE_TOOL_NAMES.get(tool_profile or "")
    if profile_names and len(domains) == 1:
        filtered = [tool for tool in union if tool.name in profile_names]
        if filtered:
            return filtered
    return union
