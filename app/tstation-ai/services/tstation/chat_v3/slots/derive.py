"""Deterministic slot derivation — the V3 port of V2's `_apply_tool_derived_slots`.

Users never type goods_no/shop_id; those arrive through tools and FE card
clicks. Three sources, applied via `ConversationSlots.apply_runtime_values`
(conflict-aware, handles dependency resets):
1. Tool INPUT — the LLM calling get_final_price_tool(goods_no=…) IS a selection.
2. Tool OUTPUT — a search that returns exactly one row resolves the entity.
3. FE payload — request.slots / ui_action.slots / chip metadata from card clicks.
"""

import json
import logging

from schemas.tstation.slots import ConversationSlots
from schemas.tstation.chat import TStationChatRequest

logger = logging.getLogger(__name__)

# Tool input args worth lifting into slots when the LLM passes them.
_INPUT_FIELDS: dict[str, tuple[str, ...]] = {
    "get_product_description_tool": ("goods_no",),
    "check_compatibility_tool": ("goods_no",),
    "get_final_price_tool": ("goods_no", "shop_id", "ord_qty"),
    "transaction_store_preview_tool": ("goods_no", "shop_id", "ord_qty", "requested_cal_day", "rsv_hour"),
    "quick_order_tool": ("goods_no", "shop_id", "ord_qty"),
    "save_to_cart_tool": ("goods_no", "ord_qty"),
    "get_store_inventory_tool": ("goods_no", "shop_id"),
    "get_logistics_inventory_tool": ("goods_no",),
    "get_store_detail_tool": ("shop_id",),
    "get_store_schedule_tool": ("shop_id",),
}

# Tool outputs that resolve an entity when they contain EXACTLY one row.
_SINGLE_ROW_FIELDS: dict[str, str] = {
    "search_product_tool": "goods_no",
    "search_stores_tool": "shop_id",
    "get_store_list_tool": "shop_id",
    "get_nearby_stores_tool": "shop_id",
}

# FE payloads use camelCase in places; normalize to slot field names.
_FE_KEY_ALIASES = {
    "goodsId": "goods_no",
    "goodsNo": "goods_no",
    "shopId": "shop_id",
    "ordQty": "ord_qty",
    "tireSize": "tire_size",
}


def _single_row(parsed: object) -> dict | None:
    data = parsed.get("data", parsed) if isinstance(parsed, dict) else parsed
    if isinstance(data, dict):
        for key in ("items", "stores"):
            if key in data:
                rows = data[key]
                return rows[0] if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) else None
    if isinstance(data, list):
        return data[0] if len(data) == 1 and isinstance(data[0], dict) else None
    return None


def _coerce(field: str, value: object) -> object:
    if field == "ord_qty" and isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def derive_slots_from_tool_calls(slots: ConversationSlots, tool_calls: list[dict]) -> ConversationSlots:
    """Stage goods_no/shop_id/… resolved by this turn's tool activity."""
    values: dict = {}
    for call in tool_calls:
        name = call.get("name") or ""
        args = call.get("args") or {}
        for field in _INPUT_FIELDS.get(name, ()):
            if args.get(field) not in (None, ""):
                values[field] = _coerce(field, args[field])

        single_field = _SINGLE_ROW_FIELDS.get(name)
        output = str(call.get("output") or "")
        if single_field and not output.startswith("Tool error"):
            try:
                row = _single_row(json.loads(output))
            except (ValueError, TypeError):
                row = None
            if row:
                value = row.get(single_field) or row.get(_snake_to_camel(single_field))
                if value:
                    values[single_field] = str(value)
                product_name = row.get("goods_nm") or row.get("goodsNm") or row.get("product_name")
                if single_field == "goods_no" and product_name:
                    values.setdefault("tire_model", str(product_name).strip())
    if not values:
        return slots
    logger.info("[CHAT_V3] tool-derived slots: %s", values)
    return slots.apply_runtime_values(values, source="chat_v3:tool_derived")


def _snake_to_camel(field: str) -> str:
    head, *rest = field.split("_")
    return head + "".join(part.capitalize() for part in rest)


def fe_slot_patch(request: TStationChatRequest) -> dict:
    """Slot values the FE sent with this turn (card click / chip metadata)."""
    chip_metadata = (request.chip_context or {}).get("metadata") or {}
    merged: dict = {}
    for source in (
        request.slots,
        (request.ui_action or {}).get("slots"),
        chip_metadata.get("slots") if isinstance(chip_metadata, dict) else None,
    ):
        if isinstance(source, dict):
            merged.update(source)
    normalized = {_FE_KEY_ALIASES.get(key, key): value for key, value in merged.items()}
    return {
        field: _coerce(field, value)
        for field, value in normalized.items()
        if field in ConversationSlots.model_fields and value not in (None, "")
    }


def apply_fe_slots(slots: ConversationSlots, request: TStationChatRequest) -> ConversationSlots:
    values = fe_slot_patch(request)
    if not values:
        return slots
    logger.info("[CHAT_V3] FE slot patch: %s", values)
    return slots.apply_runtime_values(values, source="chat_v3:fe_patch")
