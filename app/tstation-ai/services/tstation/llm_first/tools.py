from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from services.tstation.llm_first.models import AgentFlow


SIDE_EFFECT_TOOLS = frozenset({
    "quick_order_tool",
    "save_to_cart_tool",
    "issue_coupon_tool",
    "transfer_to_qna_tool",
    "escalate_tool",
})


@dataclass(frozen=True)
class ToolSpec:
    name: str
    afs: frozenset[AgentFlow]
    factory: Callable[[], Any]
    read_only: bool = True
    required_args: frozenset[str] = frozenset()

    def load(self) -> Any:
        return self.factory()


def _tx_tool(name: str) -> Any:
    from services.tstation.agents.c_transaction_agent import tools

    return getattr(tools, name)


def _discovery_tool(name: str) -> Any:
    from services.tstation.agents.b_discovery_agent import tools

    return getattr(tools, name)


def _support_tool(name: str) -> Any:
    from services.tstation.agents.e_support_agent import tools

    return getattr(tools, name)


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "search_place_tool": ToolSpec("search_place_tool", frozenset({AgentFlow.STORE}), lambda: _tx_tool("search_place_tool"), required_args=frozenset({"query"})),
    "get_nearby_stores_tool": ToolSpec("get_nearby_stores_tool", frozenset({AgentFlow.STORE}), lambda: _tx_tool("get_nearby_stores_tool")),
    "search_stores_tool": ToolSpec("search_stores_tool", frozenset({AgentFlow.STORE}), lambda: _tx_tool("search_stores_tool")),
    "search_stores_complex_tool": ToolSpec("search_stores_complex_tool", frozenset({AgentFlow.STORE}), lambda: _tx_tool("search_stores_complex_tool")),
    "get_store_detail_tool": ToolSpec("get_store_detail_tool", frozenset({AgentFlow.STORE}), lambda: _tx_tool("get_store_detail_tool"), required_args=frozenset({"shop_id"})),
    "get_store_schedule_tool": ToolSpec("get_store_schedule_tool", frozenset({AgentFlow.QUICK_SHOPPING, AgentFlow.STORE}), lambda: _tx_tool("get_store_schedule_tool"), required_args=frozenset({"shop_id", "mode"})),
    "get_final_price_tool": ToolSpec("get_final_price_tool", frozenset({AgentFlow.PRICE, AgentFlow.QUICK_SHOPPING}), lambda: _tx_tool("get_final_price_tool"), required_args=frozenset({"goods_no"})),
    "get_my_coupons_tool": ToolSpec("get_my_coupons_tool", frozenset({AgentFlow.PRICE}), lambda: _tx_tool("get_my_coupons_tool")),
    "get_my_reservations_tool": ToolSpec("get_my_reservations_tool", frozenset({AgentFlow.ORDER_DELIVERY}), lambda: _tx_tool("get_my_reservations_tool")),
    "get_maintenance_history_tool": ToolSpec("get_maintenance_history_tool", frozenset({AgentFlow.ORDER_DELIVERY}), lambda: _tx_tool("get_maintenance_history_tool")),
    "get_orders_of_user_tool": ToolSpec("get_orders_of_user_tool", frozenset({AgentFlow.ORDER_DELIVERY}), lambda: _tx_tool("get_orders_of_user_tool")),
    "get_coupon_applicable_products_tool": ToolSpec("get_coupon_applicable_products_tool", frozenset({AgentFlow.PRICE}), lambda: _tx_tool("get_coupon_applicable_products_tool")),
    "get_product_promotions_tool": ToolSpec("get_product_promotions_tool", frozenset({AgentFlow.PRICE}), lambda: _tx_tool("get_product_promotions_tool"), required_args=frozenset({"goods_no"})),
    "transaction_store_preview_tool": ToolSpec("transaction_store_preview_tool", frozenset({AgentFlow.INVENTORY, AgentFlow.QUICK_SHOPPING}), lambda: _tx_tool("transaction_store_preview_tool"), required_args=frozenset({"goods_no", "ord_qty"})),
    "get_store_inventory_tool": ToolSpec("get_store_inventory_tool", frozenset({AgentFlow.INVENTORY}), lambda: _tx_tool("get_store_inventory_tool"), required_args=frozenset({"goods_list", "shop_id_list"})),
    "get_logistics_inventory_tool": ToolSpec("get_logistics_inventory_tool", frozenset({AgentFlow.INVENTORY}), lambda: _tx_tool("get_logistics_inventory_tool"), required_args=frozenset({"goods_no"})),
    "search_product_tool": ToolSpec("search_product_tool", frozenset({AgentFlow.PRODUCT_RECOMMENDATION, AgentFlow.PRODUCT_DESCRIPTION, AgentFlow.PRICE}), lambda: _discovery_tool("search_product_tool")),
    "get_products_recommendations_tool": ToolSpec("get_products_recommendations_tool", frozenset({AgentFlow.PRODUCT_RECOMMENDATION}), lambda: _discovery_tool("get_products_recommendations_tool")),
    "get_best_selling_products_tool": ToolSpec("get_best_selling_products_tool", frozenset({AgentFlow.PRODUCT_RECOMMENDATION}), lambda: _discovery_tool("get_best_selling_products_tool")),
    "get_newest_products_tool": ToolSpec("get_newest_products_tool", frozenset({AgentFlow.PRODUCT_RECOMMENDATION}), lambda: _discovery_tool("get_newest_products_tool")),
    "get_product_description_tool": ToolSpec("get_product_description_tool", frozenset({AgentFlow.PRODUCT_DESCRIPTION}), lambda: _discovery_tool("get_product_description_tool"), required_args=frozenset({"goods_no"})),
    "search_product_summary_tool": ToolSpec("search_product_summary_tool", frozenset({AgentFlow.PRODUCT_DESCRIPTION}), lambda: _discovery_tool("search_product_summary_tool")),
    "compare_discount_tool": ToolSpec("compare_discount_tool", frozenset({AgentFlow.PRODUCT_DESCRIPTION}), lambda: _discovery_tool("compare_discount_tool")),
    "search_faq_hybrid_tool": ToolSpec("search_faq_hybrid_tool", frozenset({AgentFlow.FAQ}), lambda: _support_tool("search_faq_hybrid_tool")),
    "search_faq_rag_tool": ToolSpec("search_faq_rag_tool", frozenset({AgentFlow.FAQ}), lambda: _support_tool("search_faq_rag_tool")),
    "get_faq_tool": ToolSpec("get_faq_tool", frozenset({AgentFlow.FAQ}), lambda: _support_tool("get_faq_tool")),
    "get_card_installments_tool": ToolSpec("get_card_installments_tool", frozenset({AgentFlow.FAQ}), lambda: _support_tool("get_card_installments_tool")),
    "get_my_warranties_tool": ToolSpec("get_my_warranties_tool", frozenset({AgentFlow.FAQ}), lambda: _support_tool("get_my_warranties_tool")),
    "quick_order_tool": ToolSpec("quick_order_tool", frozenset({AgentFlow.QUICK_SHOPPING}), lambda: _tx_tool("quick_order_tool"), read_only=False),
    "save_to_cart_tool": ToolSpec("save_to_cart_tool", frozenset({AgentFlow.QUICK_SHOPPING}), lambda: _tx_tool("save_to_cart_tool"), read_only=False),
}


def invoke_tool(name: str, args: dict[str, Any], *, af: AgentFlow | None = None) -> Any:
    spec = TOOL_REGISTRY[name]
    if af is not None and af not in spec.afs:
        raise PermissionError(f"tool {name} is not allowed for {af.value}")
    if not spec.read_only or name in SIDE_EFFECT_TOOLS:
        raise PermissionError(f"side-effect tool blocked in LLM-first MVP: {name}")
    missing_args = [arg for arg in spec.required_args if args.get(arg) in (None, "")]
    if missing_args:
        raise ValueError(f"tool {name} missing required args: {', '.join(sorted(missing_args))}")
    tool = spec.load()
    if hasattr(tool, "invoke"):
        return tool.invoke(args)
    return tool(**args)
