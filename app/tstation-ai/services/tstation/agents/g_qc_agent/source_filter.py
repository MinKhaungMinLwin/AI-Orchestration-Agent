"""Filter tool outputs to keep only QC-relevant fields before passing to QC Agent.

Reduces token count and prevents Lost-in-the-Middle issues by stripping
fields the QC Agent never needs to verify (images, scores, biz hours, etc.).
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_LIST_ITEMS = 10

# tool_name → {list_key, keep_fields} for list-type responses
_LIST_TOOL_RULES: dict[str, dict[str, Any]] = {
    "get_nearby_stores_tool": {
        "list_key": "stores",
        "keep": {"shop_id", "shop_nm", "distance_km", "addr_base"},
    },
    "get_store_list_tool": {
        "list_key": "stores",
        "keep": {"shop_id", "shop_nm", "addr_base"},
    },
    "get_products_recommendations_tool": {
        "list_key": "items",
        "keep": {"goods_no", "goods_nm", "extra_fvr_sale_prc", "extra_fvr_sale_per"},
    },
    "search_product_tool": {
        "list_key": "items",
        "keep": {"goods_no", "goods_nm", "tire_size_1"},
    },
    "get_faq_tool": {
        "list_key": "faqs",
        "keep": {"cust_quest", "pc_ans_cont"},
    },
    "get_orders_of_user_tool": {
        "list_key": "orders",
        "keep": {"ord_no", "goods_nm", "ord_qty", "sys_reg_dtime"},
    },
}

# tool_name → drop_keys for single-object responses
_DROP_TOOL_RULES: dict[str, set[str]] = {
    "get_product_description_tool": {"images", "reviews", "pc_prod_remark_desc", "pc_prod_tech_desc", "slogan"},
}


def _filter_list(items: list[dict], keep: set[str]) -> list[dict]:
    """Keep only whitelisted keys from each item, limit to MAX_LIST_ITEMS."""
    filtered = []
    for item in items[:MAX_LIST_ITEMS]:
        if isinstance(item, dict):
            filtered.append({k: v for k, v in item.items() if k in keep})
        else:
            filtered.append(item)
    total = len(items)
    if total > MAX_LIST_ITEMS:
        filtered.append({"_truncated": f"{total - MAX_LIST_ITEMS} more items omitted"})
    return filtered


def _filter_drop(data: dict, drop_keys: set[str]) -> dict:
    """Remove specified keys from a dict."""
    return {k: v for k, v in data.items() if k not in drop_keys}


# --- Context filter rules (for conversation context preservation) ---
# Keeps more fields than QC filter to maintain conversational references.
_CONTEXT_LIST_RULES: dict[str, dict[str, Any]] = {
    "get_products_recommendations_tool": {
        "list_key": "items",
        "keep": {
            "goods_no", "goods_nm", "tire_size_1",
            "extra_fvr_sale_prc", "extra_fvr_sale_per",
            "tot_scr", "t_comfort", "t_silence", "t_life_span",
        },
    },
    "search_product_tool": {
        "list_key": "items",
        "keep": {"goods_no", "goods_nm", "tire_size_1", "extra_fvr_sale_prc"},
    },
    "get_nearby_stores_tool": {
        "list_key": "stores",
        "keep": {"shop_id", "shop_nm", "distance_km", "addr_base", "tel_no"},
    },
    "get_store_list_tool": {
        "list_key": "stores",
        "keep": {"shop_id", "shop_nm", "addr_base", "tel_no"},
    },
    "get_store_inventory_tool": {
        "list_key": "items",
        "keep": {"goods_no", "goods_nm", "tire_size_1", "stock_qty"},
    },
    "get_orders_of_user_tool": {
        "list_key": "orders",
        "keep": {"ord_no", "goods_nm", "ord_qty", "ord_stat_nm", "sys_reg_dtime"},
    },
    "check_compatibility_tool": {
        "list_key": "tire_sizes",
        "keep": {"tire_size", "rim_size", "is_oem"},
    },
}

_CONTEXT_MAX_ITEMS = 10

# Whitelist for tool input fields safe to persist into prompt context.
# Excludes PII: car_no, owner_nm, mbr_no, user_id, user_xpos, user_ypos, access_token
_SAFE_INPUT_FIELDS = {
    # product/search
    "tire_size", "goods_no", "keyword", "limit", "size", "brand", "brand_cd",
    "rcmd_type", "entr_yn", "entr_no", "car_lnc_cd",
    # store
    "shop_id", "shop_nm", "store_nm", "region_code",
    "radius_km", "svc_codes", "all_my_t_only", "chl_sct_cd",
    # vehicle (non-PII)
    "car_model", "car_year", "car_grade", "car_engine", "rim_size",
    # order/price
    "ord_no", "member_type", "sort", "category",
    # inventory
    "goods_list", "shop_id_list",
}


def _filter_input(tool_input: dict) -> dict:
    """Keep only safe, non-PII fields from tool input (for prompt display)."""
    return {k: v for k, v in tool_input.items() if v is not None and k in _SAFE_INPUT_FIELDS}


def _dedup_input(tool_input: dict) -> dict:
    """Build dedup-safe input: safe fields as-is, PII fields as stable hashes."""
    import hashlib
    result = {}
    for k, v in tool_input.items():
        if v is None:
            continue
        if k in _SAFE_INPUT_FIELDS:
            result[k] = v
        else:
            # Hash PII values so dedup works without storing raw PII
            result[k] = hashlib.sha256(str(v).encode()).hexdigest()[:12]
    return result


def filter_for_context(tool_name: str, raw_output: str, tool_input: dict | None = None) -> dict | None:
    """Filter tool output for conversation context preservation.

    Returns a compact dict with tool name, input summary, and filtered output.
    Returns None if the tool has no context-relevant data.
    """
    try:
        data = json.loads(raw_output) if isinstance(raw_output, str) else raw_output
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    inner = data.get("data", data)

    # Skip error responses
    if data.get("status") == "error":
        return None

    # Tools with specific list filtering
    if tool_name in _CONTEXT_LIST_RULES:
        rule = _CONTEXT_LIST_RULES[tool_name]
        list_key = rule["list_key"]
        keep = rule["keep"]

        items = None
        if isinstance(inner, dict) and list_key in inner and isinstance(inner[list_key], list):
            items = inner[list_key]
        elif isinstance(inner, dict):
            for k, v in inner.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    items = v
                    break

        if items:
            filtered_items = _filter_list(items, keep)
            result = {"tool": tool_name, "data": filtered_items}
            if tool_input:
                result["input"] = _filter_input(tool_input)
                result["_dedup_input"] = _dedup_input(tool_input)
            return result

    # Single-object tools (price, product description, etc.)
    if tool_name in ("get_final_price_tool", "get_product_description_tool"):
        if isinstance(inner, dict):
            # Keep key pricing/product fields
            compact = {}
            for k in ("goods_no", "goods_nm", "tire_size_1", "sale_prc", "extra_fvr_sale_prc",
                       "rating_avg", "review_count", "slogan"):
                if k in inner and inner[k] is not None:
                    compact[k] = inner[k]
            if compact:
                result = {"tool": tool_name, "data": compact}
                if tool_input:
                    result["input"] = _filter_input(tool_input)
                    result["_dedup_input"] = _dedup_input(tool_input)
                return result

    return None


def filter_source_data(tool_name: str, raw_output: str) -> str:
    """Filter tool output JSON, keeping only QC-relevant fields.

    Args:
        tool_name: LangChain tool name (e.g. "get_nearby_stores_tool").
        raw_output: Original JSON string from the tool.

    Returns:
        Compact JSON string with irrelevant fields removed.
    """
    # No rule for this tool → pass through as-is
    if tool_name not in _LIST_TOOL_RULES and tool_name not in _DROP_TOOL_RULES:
        return raw_output

    try:
        data = json.loads(raw_output) if isinstance(raw_output, str) else raw_output
    except (json.JSONDecodeError, TypeError):
        return raw_output

    if not isinstance(data, dict):
        return raw_output

    inner = data.get("data", data)

    # List-type filtering
    if tool_name in _LIST_TOOL_RULES:
        rule = _LIST_TOOL_RULES[tool_name]
        list_key = rule["list_key"]
        keep = rule["keep"]

        if isinstance(inner, dict) and list_key in inner and isinstance(inner[list_key], list):
            inner[list_key] = _filter_list(inner[list_key], keep)
        elif isinstance(inner, dict):
            # Try to find any list in the response
            for k, v in inner.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    inner[k] = _filter_list(v, keep)
                    break

    # Drop-key filtering
    if tool_name in _DROP_TOOL_RULES:
        drop_keys = _DROP_TOOL_RULES[tool_name]
        if isinstance(inner, dict):
            filtered_inner = _filter_drop(inner, drop_keys)
            if "data" in data:
                data["data"] = filtered_inner
            else:
                data = filtered_inner

    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
