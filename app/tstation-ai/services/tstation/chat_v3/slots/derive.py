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
    "carModel": "car_model",
    "carModelDet": "car_model",
    "carName": "car_model",
    "car_model_det": "car_model",
    "car_nm": "car_model",
    "carType": "car_type",
    "vehicleType": "vehicle_type",
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


def _vehicle_size_patch(merged: dict, *, allow_selected_size: bool = True) -> dict:
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
        if allow_selected_size and explicit_selected_size in {front_size, rear_size}:
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


# Staggered vehicles allow at most 2 tires per order, typed input included.
STAGGERED_MAX_ORD_QTY = 2

# Consecutive same-guard turns past this hand off to the domain agent instead of repeating.
GUARD_REPEAT_ESCALATION_THRESHOLD = 2


def track_guard_repeat(guard_id: str, slots: ConversationSlots) -> ConversationSlots:
    """Count consecutive turns the router has fired the same policy guard."""
    if guard_id == "none":
        if slots.last_guard_id is None and slots.guard_repeat_count is None:
            return slots
        return slots.model_copy(update={"last_guard_id": None, "guard_repeat_count": None})
    repeat_count = (slots.guard_repeat_count or 0) + 1 if slots.last_guard_id == guard_id else 1
    return slots.model_copy(update={"last_guard_id": guard_id, "guard_repeat_count": repeat_count})


def reset_for_supported_brand_switch(slots: ConversationSlots) -> ConversationSlots:
    """Clear stale product and guard state while preserving vehicle fitment context."""
    reset_fields = {
        "tire_model",
        "pending_product_name",
        "last_guard_id",
        "guard_repeat_count",
        *ConversationSlots.DEPENDENT_RESETS["tire_model"],
    }
    return slots.model_copy(update={field: None for field in reset_fields})


def is_staggered_vehicle(slots: ConversationSlots) -> bool:
    front = str(slots.tire_size_front or "").strip()
    rear = str(slots.tire_size_rear or "").strip()
    return bool(front and rear and front != rear)


def clamp_staggered_ord_qty(slots: ConversationSlots) -> ConversationSlots:
    if not is_staggered_vehicle(slots):
        return slots
    qty = slots.ord_qty
    if isinstance(qty, int) and qty > STAGGERED_MAX_ORD_QTY:
        return slots.model_copy(update={"ord_qty": STAGGERED_MAX_ORD_QTY})
    return slots


def _clear_unconfirmed_staggered_size(slots: ConversationSlots, values: dict) -> ConversationSlots:
    if (
        "tire_size" not in values
        and slots.tire_size
        and slots.tire_size_front
        and slots.tire_size_rear
        and slots.tire_size_front != slots.tire_size_rear
    ):
        return slots.model_copy(update={"tire_size": None})
    return slots


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
    car_maker = next((row.get(key) for key in ("car_maker", "carMaker") if row.get(key)), None)
    if car_maker:
        values["car_maker"] = str(car_maker).strip()
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


def _match_key(value: object) -> str:
    return "".join(str(value or "").lower().split())


def promote_selected_vehicle(
    slots: ConversationSlots,
    tool_calls: list[dict],
    *,
    car_model_hint: str | None = None,
) -> ConversationSlots:
    """Promote an explicitly identified registered vehicle into canonical slots.

    Selection evidence may come from a plate/launch code or from the router's
    structured model hint. A generic vehicle-list result is never auto-selected.
    """
    candidates = slots.vehicle_candidates or []
    if not candidates:
        return slots

    identifiers = {_match_key(slots.car_no), _match_key(slots.car_lnc_cd)}
    for call in tool_calls:
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        identifiers.update({_match_key(args.get("car_no")), _match_key(args.get("car_lnc_cd"))})
    identifiers.discard("")
    matches = [
        candidate
        for candidate in candidates
        if identifiers.intersection({_match_key(candidate.get("car_no")), _match_key(candidate.get("car_lnc_cd"))})
    ]

    hint = _match_key(car_model_hint or slots.car_model)
    if len(matches) != 1 and len(hint) >= 2:
        matches = [
            candidate
            for candidate in candidates
            if any(
                hint in label or label in hint
                for label in (
                    _match_key(candidate.get("car_maker")),
                    _match_key(candidate.get("car_model")),
                )
                if len(label) >= 2
            )
        ]
    if len(matches) != 1:
        return slots

    selected = matches[0]
    prior_selected_size = normalize_tire_size(str(slots.tire_size or ""))
    values = {key: value for key, value in selected.items() if key in ConversationSlots.model_fields}
    updated = slots.apply_runtime_values(values, source="chat_v3:selected_vehicle")
    confirmed_sizes = {
        str(updated.tire_size_front or "").strip(),
        str(updated.tire_size_rear or "").strip(),
    }
    if is_staggered_vehicle(updated):
        updated = updated.model_copy(
            update={"tire_size": prior_selected_size if prior_selected_size in confirmed_sizes else None}
        )
    return updated


def _snake_to_camel(field: str) -> str:
    head, *rest = field.split("_")
    return head + "".join(part.capitalize() for part in rest)


def fe_slot_patch(request: TStationChatRequest) -> dict:
    """Slot values the FE sent with this turn (card click / chip metadata)."""
    chip_metadata = (request.chip_context or {}).get("metadata") or {}
    ui_action = request.ui_action or {}
    action_type = str(ui_action.get("action_type") or ui_action.get("cta_action") or "").strip()
    merged: dict = {}
    has_chip_slots = False
    for source in (
        request.slots,
        ui_action.get("slots"),
        chip_metadata.get("slots") if isinstance(chip_metadata, dict) else None,
    ):
        if isinstance(source, dict):
            merged.update(source)
            has_chip_slots = has_chip_slots or source is chip_metadata.get("slots")
    normalized = {_FE_KEY_ALIASES.get(key, key): value for key, value in merged.items()}
    vehicle_size_values = _vehicle_size_patch(
        merged,
        allow_selected_size=not (
            action_type == "select_vehicle_candidate"
            or (
                not action_type
                and not has_chip_slots
                and any(key in normalized for key in ("car_no", "car_lnc_cd", "mbr_car_reg_seq"))
            )
        ),
    )
    normalized.update(vehicle_size_values)
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
    updated = slots.apply_runtime_values(values, source="chat_v3:fe_patch")
    return _clear_unconfirmed_staggered_size(updated, values)


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
    updated = slots.apply_runtime_values(matches[0], source="chat_v3:text_vehicle_selection")
    return _clear_unconfirmed_staggered_size(updated, matches[0])
