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
from services.tstation.policies.discovery_intent_policy import normalize_tire_size

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
    "get_store_install_availability_tool": ("goods_no", "ord_qty", "requested_cal_day"),
    "get_store_detail_tool": ("shop_id",),
    "get_store_schedule_tool": ("shop_id",),
}

# Tool outputs that resolve an entity when they contain EXACTLY one row.
_SINGLE_ROW_FIELDS: dict[str, str] = {
    "search_product_tool": "goods_no",
    "search_stores_tool": "shop_id",
    "get_store_list_tool": "shop_id",
    "get_nearby_stores_tool": "shop_id",
    "get_store_install_availability_tool": "shop_id",
}

_VEHICLE_LIST_TOOLS = {"get_my_cars_tool", "get_user_vehicles_tool"}

# FE payloads use camelCase in places; normalize to slot field names.
_FE_KEY_ALIASES = {
    "carNo": "car_no",
    "licensePlate": "car_no",
    "carLncCd": "car_lnc_cd",
    "goodsId": "goods_no",
    "goodsNo": "goods_no",
    "shopId": "shop_id",
    "ordQty": "ord_qty",
    "tireSize": "tire_size",
    "tireSizeFr": "tire_size_front",
    "tireSizeFront": "tire_size_front",
    "tireSizeRe": "tire_size_rear",
    "tireSizeRear": "tire_size_rear",
}


def _vehicle_size_patch(merged: dict) -> dict:
    front_raw = (
        merged.get("tire_size_front")
        or merged.get("tire_size_fr")
        or merged.get("tireSizeFront")
        or merged.get("tireSizeFr")
        or merged.get("tireSize")
    )
    rear_raw = (
        merged.get("tire_size_rear")
        or merged.get("tire_size_re")
        or merged.get("tireSizeRear")
        or merged.get("tireSizeRe")
    )
    front_size = normalize_tire_size(str(front_raw or ""))
    rear_size = normalize_tire_size(str(rear_raw or ""))
    if not front_size and not rear_size:
        return {}
    if front_size and rear_size and front_size != rear_size:
        values = {"tire_size": None, "tire_size_front": front_size, "tire_size_rear": rear_size}
        explicit_selected_size = normalize_tire_size(str(merged.get("tire_size") or ""))
        if explicit_selected_size in {front_size, rear_size}:
            values["tire_size"] = explicit_selected_size
        return values
    selected_size = front_size or rear_size
    values = {"tire_size": selected_size}
    if front_size and rear_size:
        values.update({"tire_size_front": selected_size, "tire_size_rear": selected_size})
    elif front_size and any(
        key in merged for key in ("tire_size_front", "tire_size_fr", "tireSizeFront", "tireSizeFr")
    ):
        values["tire_size_front"] = front_size
    elif rear_size:
        values["tire_size_rear"] = rear_size
    return values


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


def _rows_from_vehicle_output(parsed: object) -> list[dict]:
    data = parsed.get("data", parsed) if isinstance(parsed, dict) else parsed
    if isinstance(data, dict):
        rows = data.get("items") or data.get("vehicles")
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _compact_identifier(value: object) -> str:
    return "".join(str(value or "").split())


def _vehicle_candidate_from_row(row: dict) -> dict:
    values: dict = {}
    for field, *keys in (
        ("car_no", "car_no", "carNo", "licensePlate"),
        ("car_lnc_cd", "car_lnc_cd", "carLncCd"),
        ("mbr_car_reg_seq", "mbr_car_reg_seq", "mbr_car_unif_no", "mbrCarRegSeq"),
        ("car_model", "car_model_det", "carModelDet", "car_nm", "carName", "car_model", "carModel"),
        ("car_type", "car_type", "carType"),
        ("vehicle_type", "vehicle_type", "vehicleType"),
    ):
        value = next((row.get(key) for key in keys if row.get(key) not in (None, "")), None)
        if value not in (None, ""):
            values[field] = str(value)
    values.update(_vehicle_size_patch(row))
    return {key: value for key, value in values.items() if value not in (None, "", [], {})}


def _vehicle_candidates_from_tool_output(output: str) -> list[dict]:
    try:
        rows = _rows_from_vehicle_output(json.loads(output))
    except (ValueError, TypeError):
        return []
    candidates = [_vehicle_candidate_from_row(row) for row in rows]
    return [candidate for candidate in candidates if candidate.get("car_no")]


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
        output = str(call.get("output") or "")
        for field in _INPUT_FIELDS.get(name, ()):
            if args.get(field) not in (None, ""):
                values[field] = _coerce(field, args[field])

        if name in _VEHICLE_LIST_TOOLS:
            candidates = _vehicle_candidates_from_tool_output(output)
            if candidates:
                values["vehicle_candidates"] = candidates

        single_field = _SINGLE_ROW_FIELDS.get(name)
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
    normalized.update(_vehicle_size_patch(merged))
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


def apply_text_vehicle_selection(slots: ConversationSlots, user_text: str) -> ConversationSlots:
    candidates = slots.vehicle_candidates or []
    selected = _compact_identifier(user_text)
    if not selected or not candidates:
        return slots
    matches = [
        candidate
        for candidate in candidates
        if _compact_identifier(candidate.get("car_no")) == selected
    ]
    if len(matches) != 1:
        return slots
    logger.info("[CHAT_V3] text vehicle selection patch: %s", matches[0])
    return slots.apply_runtime_values(matches[0], source="chat_v3:text_vehicle_selection")
