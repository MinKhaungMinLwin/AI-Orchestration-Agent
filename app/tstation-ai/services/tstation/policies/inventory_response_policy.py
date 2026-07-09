"""Inventory-output policy for model-visible tool observations."""

from __future__ import annotations

import json
from typing import Any


INVENTORY_TOOL_NAMES = {
    "get_store_inventory_tool",
    "get_logistics_inventory_tool",
    "get_store_install_availability_tool",
}
_QUANTITY_KEY_PARTS = (
    "qty",
    "quantity",
    "stock",
    "jaego",
    "cnt",
    "count",
)
_KEEP_KEYS = {
    "shopid",
    "shop_id",
    "shopname",
    "shop_name",
    "storenm",
    "store_nm",
    "goodsno",
    "goods_no",
}
_DROP_TOP_LEVEL_KEYS = {"status"}
_AVAILABLE_QUANTITY = "available_quantity_redacted"
_UNAVAILABLE_QUANTITY = "unavailable_quantity_redacted"
_UNKNOWN_QUANTITY = "quantity_redacted"


def _normalized_key(key: Any) -> str:
    return str(key or "").replace("_", "").replace("-", "").lower()


def _is_quantity_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    if normalized in _KEEP_KEYS:
        return False
    return any(part in normalized for part in _QUANTITY_KEY_PARTS)


def _is_quantity_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return bool(stripped) and stripped.isdecimal()
    return False


def _quantity_signal(value: Any) -> str:
    if isinstance(value, bool):
        return _UNKNOWN_QUANTITY
    if isinstance(value, int | float):
        return _AVAILABLE_QUANTITY if value > 0 else _UNAVAILABLE_QUANTITY
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdecimal():
            return _AVAILABLE_QUANTITY if int(stripped) > 0 else _UNAVAILABLE_QUANTITY
    return _UNKNOWN_QUANTITY


def _redact_inventory_quantities(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, list):
        return [_redact_inventory_quantities(item, depth=depth) for item in value]
    if not isinstance(value, dict):
        return value

    redacted: dict[Any, Any] = {}
    for key, item in value.items():
        if depth == 0 and _normalized_key(key) in _DROP_TOP_LEVEL_KEYS:
            continue
        if _is_quantity_key(key) and _is_quantity_value(item):
            redacted[key] = _quantity_signal(item)
        else:
            redacted[key] = _redact_inventory_quantities(item, depth=depth + 1)
    return redacted


def redact_inventory_output_for_model(tool_name: str, output_text: str) -> str:
    """Redact exact stock counts from inventory tool output before the model sees it."""

    if tool_name not in INVENTORY_TOOL_NAMES or not output_text:
        return output_text
    try:
        payload = json.loads(output_text)
    except (TypeError, ValueError):
        return output_text
    try:
        return json.dumps(_redact_inventory_quantities(payload), ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return output_text
