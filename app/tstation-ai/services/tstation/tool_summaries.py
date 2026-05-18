"""One-line summaries of tool results, formatted for the Langfuse trace tree.

Each summary is a short human-readable string ("3 hits", "₩119,000", "qty=8")
that is placed on a manual `🔧 tool:<name>` span so the Langfuse tree shows
what the tool actually returned without expanding the raw JSON output.

The full raw JSON is still captured by the LangChain auto-span — this is a
read-only convenience layer for analysts.
"""
from __future__ import annotations

from typing import Any


def _data(result: Any) -> dict:
    """Return ``result['data']`` when result is a dict, else ``{}``."""
    if isinstance(result, dict):
        d = result.get("data")
        if isinstance(d, dict):
            return d
        if isinstance(d, list):
            return {"_list": d}
    return {}


def _items(result: Any) -> list:
    d = _data(result)
    items = d.get("items") if isinstance(d, dict) else None
    if isinstance(items, list):
        return items
    if "_list" in d and isinstance(d["_list"], list):
        return d["_list"]
    return []


def _status(result: Any) -> str:
    if isinstance(result, dict):
        s = result.get("status")
        if s:
            return str(s)
    return "?"


def _won(value: Any) -> str:
    """Format a number as ₩-prefixed amount, falling back to str(value)."""
    try:
        return f"₩{int(value):,}"
    except (TypeError, ValueError):
        return str(value) if value is not None else "?"


def summarize_tool(name: str, result: Any) -> str:
    """Return a single-line summary for a tool result.

    Falls back to ``status=<value>`` for tools without a dedicated summary —
    which is still more useful in the trace tree than the raw JSON preview.
    """
    if name in ("search_product_tool", "get_products_recommendations_tool"):
        items = _items(result)
        if not items:
            return "0 hits"
        first = items[0] if isinstance(items[0], dict) else {}
        head = first.get("goodsNo") or first.get("goods_no") or first.get("name", "")
        return f"{len(items)} hits → {head}" if head else f"{len(items)} hits"

    if name == "get_final_price_tool":
        d = _data(result)
        price = d.get("finalPrice") or d.get("final_price") or d.get("price")
        rate = d.get("discountRate") or d.get("discount_rate")
        if price is None:
            return f"status={_status(result)}"
        return f"{_won(price)}" + (f" (-{rate}%)" if rate else "")

    if name in ("get_logistics_inventory_tool", "get_store_inventory_tool"):
        d = _data(result)
        qty = d.get("availableQty") or d.get("available_qty") or d.get("qty")
        return f"qty={qty}" if qty is not None else f"status={_status(result)}"

    if name in ("get_nearby_stores_tool", "get_store_list_tool", "get_favorite_stores_tool"):
        items = _items(result)
        return f"{len(items)} stores"

    if name == "get_store_detail_tool":
        d = _data(result)
        sid = d.get("shopId") or d.get("shop_id")
        return f"shop_id={sid}" if sid else f"status={_status(result)}"

    if name in ("get_my_cars_tool", "get_user_vehicles_tool"):
        items = _items(result)
        return f"{len(items)} vehicles"

    if name == "get_my_coupons_tool":
        items = _items(result)
        return f"{len(items)} coupons"

    if name == "compare_discount_tool":
        d = _data(result)
        cheapest = d.get("cheapest") or {}
        if isinstance(cheapest, dict):
            price = cheapest.get("finalPrice") or cheapest.get("final_price")
            if price is not None:
                return f"cheapest={_won(price)}"
        return f"status={_status(result)}"

    if name == "get_cheapest_price_tool":
        d = _data(result)
        items = d.get("items") or []
        if isinstance(items, list) and items:
            prices = [it.get("final_prc") for it in items if isinstance(it, dict)]
            valid = [p for p in prices if p is not None]
            if valid:
                return f"{len(items)} items, min={_won(min(valid))}"
        return f"status={_status(result)}"

    if name == "get_product_description_tool":
        d = _data(result)
        gn = d.get("goodsNo") or d.get("goods_no")
        return f"goods_no={gn}" if gn else f"status={_status(result)}"

    if name in ("save_to_cart_tool", "quick_order_tool"):
        d = _data(result)
        oid = d.get("orderNo") or d.get("order_no") or d.get("cartNo")
        return f"order={oid}" if oid else f"status={_status(result)}"

    if name == "get_order_status_tool":
        d = _data(result)
        oid = d.get("orderNo") or d.get("order_no")
        st = d.get("orderStatus") or d.get("status")
        return f"order={oid} status={st}" if oid else f"status={_status(result)}"

    if name == "get_orders_of_user_tool":
        items = _items(result)
        return f"{len(items)} orders"

    if name in ("get_faq_tool", "search_faq_rag_tool"):
        items = _items(result)
        return f"{len(items)} faq matches"

    if name == "transfer_to_qna_tool":
        return "qna handoff"

    if name == "escalate_tool":
        d = _data(result)
        ticket = d.get("ticketId") or d.get("ticket_id")
        return f"ticket={ticket}" if ticket else f"status={_status(result)}"

    if name == "search_youtube_video_tool":
        items = _items(result)
        return f"{len(items)} videos"

    if name == "search_place_tool":
        items = _items(result)
        return f"{len(items)} places"

    if name == "check_compatibility_tool":
        d = _data(result)
        compat = d.get("compatible") if isinstance(d, dict) else None
        if compat is True:
            return "compatible"
        if compat is False:
            return "incompatible"
        return f"status={_status(result)}"

    return f"status={_status(result)}"
