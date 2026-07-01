from __future__ import annotations

from typing import Any, Mapping

from services.tstation.policies.discovery_intent_policy import normalize_tire_size
from services.tstation.policies.resolved_context import canonical_context_from_tool_boundary


def _util_to_int(value: Any) -> int | None:
    if value in (None, "", [], {}):
        return None
    try:
        parsed = int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed


def util_preview_price_unit_and_basis(price_data: Mapping[str, Any] | None) -> tuple[int | None, str | None]:
    if not isinstance(price_data, Mapping):
        return None, None
    for key in (
        "cheapest_final_prc",
        "final_unit_price",
        "final_prc",
        "final_price",
        "finalPrice",
        "extra_fvr_sale_prc",
        "sale_prc",
    ):
        parsed = _util_to_int(price_data.get(key))
        if parsed is not None and parsed > 0:
            return int(parsed), key
    return None, None


def util_search_product_price_context(price_data: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(price_data, Mapping):
        return {}
    values: dict[str, Any] = {}
    for key in (
        "cheapest_final_prc",
        "final_unit_price",
        "final_prc",
        "final_price",
        "finalPrice",
        "extra_fvr_sale_prc",
        "sale_prc",
        "price",
    ):
        value = price_data.get(key)
        if value not in (None, "", [], {}):
            values[key] = value
    unit_price, price_basis = util_preview_price_unit_and_basis(price_data)
    if unit_price is not None and price_basis:
        values.setdefault(price_basis, unit_price)
        values["price_basis"] = price_basis
        values["price_source_tool"] = "search_product_tool"
    return values


def util_search_product_result_items(tool_result: Any) -> list[Any]:
    if isinstance(tool_result, list):
        return tool_result
    if not isinstance(tool_result, Mapping):
        return []
    data = tool_result.get("data")
    if isinstance(data, list):
        return data
    items = data.get("items") if isinstance(data, Mapping) else None
    return items if isinstance(items, list) else []


def util_single_resolved_search_product_row(
    tool_result: Any,
) -> dict[str, Any] | None:
    items = util_search_product_result_items(tool_result)
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], Mapping):
        return None
    raw_item = items[0]
    canonical = canonical_context_from_tool_boundary(raw_item)
    goods_no = str(canonical.get("goods_no") or raw_item.get("goods_no") or raw_item.get("goodsNo") or "").strip()
    if not goods_no:
        return None
    tire_size = normalize_tire_size(
        str(
            canonical.get("tire_size")
            or raw_item.get("tire_size")
            or raw_item.get("tire_size_1")
            or raw_item.get("tireSize")
            or raw_item.get("titleTires")
            or ""
        )
    )
    product_name = str(
        canonical.get("product_name")
        or raw_item.get("goods_nm")
        or raw_item.get("goodsNm")
        or raw_item.get("product_name")
        or raw_item.get("productName")
        or raw_item.get("titleProductName")
        or raw_item.get("title")
        or ""
    ).strip()
    return {
        "goods_no": goods_no,
        "tire_size": tire_size or None,
        "product_name": product_name or None,
        **util_search_product_price_context(raw_item),
    }


def util_resolve_stock_search_product_row(
    tool_result: Any,
    *,
    known_tire_size: str | None = None,
) -> dict[str, Any] | None:
    items = util_search_product_result_items(tool_result)
    if not isinstance(items, list) or not items:
        return None
    if len(items) == 1:
        return util_single_resolved_search_product_row(tool_result)
    normalized_known = normalize_tire_size(str(known_tire_size or "")) if known_tire_size else None
    for raw_item in items:
        if not isinstance(raw_item, Mapping):
            continue
        canonical = canonical_context_from_tool_boundary(raw_item)
        goods_no = str(canonical.get("goods_no") or "").strip()
        if not goods_no:
            continue
        item_tire_size = normalize_tire_size(str(canonical.get("tire_size") or "")) or None
        if normalized_known and item_tire_size and item_tire_size != normalized_known:
            continue
        return {
            "goods_no": goods_no,
            "tire_size": item_tire_size or normalized_known,
            "product_name": str(
                canonical.get("product_name") or canonical.get("goods_nm") or canonical.get("titleProductName") or ""
            ).strip()
            or None,
        }
    return None


def util_store_slots_from_tool_boundary(
    *,
    tool_name: str,
    tool_input: Mapping[str, Any] | None,
    parsed_data: Mapping[str, Any] | None,
) -> dict[str, Any]:
    store_slots: dict[str, Any] = {}
    input_data = dict(tool_input or {})
    if tool_name in {"get_store_schedule_tool", "get_store_detail_tool"}:
        shop_id = str(input_data.get("shop_id") or "").strip()
        if shop_id:
            store_slots["shop_id"] = shop_id
    if tool_name == "get_store_inventory_tool":
        shop_ids = input_data.get("shop_id_list")
        if isinstance(shop_ids, list) and shop_ids and isinstance(shop_ids[0], Mapping):
            shop_id = str(shop_ids[0].get("shopId") or shop_ids[0].get("shop_id") or "").strip()
            if shop_id:
                store_slots["shop_id"] = shop_id

    payload = (parsed_data or {}).get("data") if isinstance(parsed_data, Mapping) else None
    if not isinstance(payload, Mapping):
        payload = parsed_data if isinstance(parsed_data, Mapping) else {}
    candidate: Any = None
    for key in ("items", "stores"):
        rows = payload.get(key) if isinstance(payload, Mapping) else None
        if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], Mapping):
            candidate = rows[0]
            break
    if candidate is None and isinstance(payload, Mapping):
        candidate = payload
    if isinstance(candidate, Mapping):
        canonical = canonical_context_from_tool_boundary(candidate)
        shop_id = str(
            canonical.get("shop_id")
            or candidate.get("shopId")
            or candidate.get("shop_id")
            or candidate.get("shopSeq")
            or ""
        ).strip()
        shop_name = str(
            canonical.get("shop_name")
            or candidate.get("shopName")
            or candidate.get("shop_nm")
            or candidate.get("nameAddress")
            or candidate.get("name")
            or ""
        ).strip()
        if shop_id:
            store_slots["shop_id"] = shop_id
        if shop_name:
            store_slots["shop_name"] = shop_name
    if store_slots.get("shop_id"):
        store_slots["source_tool"] = tool_name
    return store_slots


def util_product_flow_values_from_resolved_search(
    *,
    resolved_row: Mapping[str, Any],
    slots: Any | None,
) -> dict[str, Any]:
    ord_qty = None
    pending_intent = None
    goal_type = None
    stock_check_mode = None
    store_values: dict[str, Any] = {}
    if slots is not None:
        ord_qty = getattr(slots, "ord_qty", None) or getattr(slots, "quantity", None)
        pending_intent = getattr(slots, "pending_intent", None)
        goal_type = getattr(slots, "goal_type", None)
        stock_check_mode = getattr(slots, "stock_check_mode", None)
        for key in ("shop_id", "shop_name", "store_name", "region", "place_query", "user_xpos", "user_ypos"):
            value = getattr(slots, key, None)
            if value not in (None, "", [], {}):
                store_values[key] = value
    if str(stock_check_mode or "").strip() == "inventory_only":
        pending_intent = pending_intent or "stock"
        goal_type = goal_type or "store_with_stock"
    values: dict[str, Any] = {
        "goods_no": resolved_row.get("goods_no"),
        "product_name": resolved_row.get("product_name"),
        "tire_model": resolved_row.get("product_name"),
        "pending_product_name": resolved_row.get("product_name"),
        "tire_size": resolved_row.get("tire_size") or (getattr(slots, "tire_size", None) if slots else None),
        "ord_qty": ord_qty,
        "pending_intent": pending_intent,
        "goal_type": goal_type,
        "stock_check_mode": stock_check_mode,
        **store_values,
        **util_search_product_price_context(resolved_row),
    }
    return {key: value for key, value in values.items() if value not in (None, "", [], {})}


def util_active_flow_values_from_slots(slots: Any | None) -> dict[str, Any]:
    if slots is None:
        return {}
    values = {
        "goods_no": getattr(slots, "goods_no", None),
        "product_name": getattr(slots, "tire_model", None) or getattr(slots, "pending_product_name", None),
        "tire_model": getattr(slots, "tire_model", None),
        "pending_product_name": getattr(slots, "pending_product_name", None),
        "tire_size": getattr(slots, "tire_size", None),
        "ord_qty": getattr(slots, "ord_qty", None),
        "shop_id": getattr(slots, "shop_id", None),
        "shop_name": getattr(slots, "shop_name", None),
        "region": getattr(slots, "region", None),
        "pending_intent": getattr(slots, "pending_intent", None),
        "goal_type": getattr(slots, "goal_type", None),
        "stock_check_mode": getattr(slots, "stock_check_mode", None),
        "schedule_mode": getattr(slots, "schedule_mode", None),
        "schedule_tier": getattr(slots, "schedule_tier", None),
        "inventory_mode": getattr(slots, "inventory_mode", None),
    }
    return {key: value for key, value in values.items() if value not in (None, "", [], {})}
