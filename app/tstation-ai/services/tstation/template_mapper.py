"""
Code-based template mapper — replaces LLM UI Template Agent for deterministic tool→template conversion.

Maps domain agent tool outputs directly to FE template format without an LLM call.
"""
import logging

logger = logging.getLogger(__name__)

# Domain tool → FE template name
_TOOL_TEMPLATE_MAP = {
    "search_product_tool": "product",
    "get_products_recommendations_tool": "product",
}


def _map_product(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Map search_product_tool / get_products_recommendations_tool output to product template."""
    items = []
    metadata = []

    for entry in tool_data_list:
        tool_name = entry.get("tool", "")
        if tool_name not in ("search_product_tool", "get_products_recommendations_tool"):
            continue

        raw = entry.get("data", {})
        if isinstance(raw, dict) and raw.get("status") == "success":
            raw = raw.get("data", raw)

        # search_product_tool → list at top level or under "items"
        # get_products_recommendations_tool → list at top level or under "items"
        rows = raw if isinstance(raw, list) else raw.get("items", [])
        if not isinstance(rows, list):
            continue

        for row in rows:
            if not isinstance(row, dict):
                continue
            goods_no = row.get("goods_no", "")
            goods_nm = row.get("goods_nm") or row.get("title") or ""
            tire_size = row.get("tire_size_1") or row.get("tire_size_2") or ""
            title = f"{goods_nm} {tire_size}".strip() if tire_size else goods_nm
            image_url = row.get("image_url") or ""
            price = row.get("price") or row.get("extra_fvr_sale_prc") or 0
            rate = row.get("rate") or 0.0
            total_qty = row.get("totalQuantity") or row.get("total_qty") or 0
            comfort = row.get("comfort") or ""
            tires = row.get("tires") or ""

            items.append({
                "imageUrl": image_url,
                "title": title,
                "tires": tires,
                "comfort": str(comfort) if comfort else "",
                "price": int(price) if price else 0,
                "rate": float(rate) if rate else 0.0,
                "totalQuantity": int(total_qty) if total_qty else 0,
                "description": "",
            })
            metadata.append({"goodsId": goods_no})

    if not items:
        return None

    # Max 5 items for card carousel
    items = items[:5]
    metadata = metadata[:5]

    return {
        "type": "data",
        "template": "product",
        "data": {
            "products": items,
            "assistantResponse": assistant_text,
            "metadata": metadata,
        },
    }


def try_build_template(accumulated_tool_data: list[dict], assistant_text: str) -> dict | None:
    """Try to build a template event from accumulated tool data using code mapping.

    Returns a template event dict if a code mapper handled it, or None to fall through to UI Template Agent.
    """
    if not accumulated_tool_data:
        return None

    # Check if any tool has a code mapper
    tool_names = {entry.get("tool", "") for entry in accumulated_tool_data}
    mapped_tools = tool_names & set(_TOOL_TEMPLATE_MAP.keys())

    if not mapped_tools:
        return None

    # Product template
    if mapped_tools & {"search_product_tool", "get_products_recommendations_tool"}:
        result = _map_product(accumulated_tool_data, assistant_text)
        if result:
            logger.info("[TEMPLATE_MAPPER] Built product template from code (skipped UI Template Agent)")
            return result

    return None
