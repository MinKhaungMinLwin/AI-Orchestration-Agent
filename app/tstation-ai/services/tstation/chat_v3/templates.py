"""Rich FE templates: product cards, store lists, car picker, cheapest price.

The mini model maps raw tool output into the Pydantic template models from
`agents/templates/schemas.py` (single source of truth) — same approach V2
uses via RESPONSE_FORMAT, but as one dedicated call. Any failure returns
None and the turn falls back to the plain quickReply event.
"""

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, create_model

from schemas.tstation.slots import ConversationSlots
from services.tstation.agents.templates.schemas import (
    CarItem,
    CarMeta,
    CheapestProductTemplate,
    DatepickTemplate,
    ListCarTemplate,
    LocationItem,
    LocationMeta,
    LocationTemplate,
    OrderCompleteTemplate,
    PreOrderTemplate,
    ProductItem,
    ProductMeta,
    ProductTag,
    ProductTemplate,
    QnaCompleteTemplate,
)
from services.tstation.chat_v3.llm import get_router_llm
from services.tstation.chat_v3.prompts.templates import TEMPLATE_BUILDER_PROMPT
from services.tstation.chat_v3.router.schemas import RouteDecision
from services.tstation.common.cta_urls import CTAUrls
from services.tstation.policies.discovery_intent_policy import normalize_tire_size

logger = logging.getLogger(__name__)

_MAX_TOOL_OUTPUT_CHARS = 12000
# Concrete order slots the router can fill from the user's message. When one of these
# appears in this turn's slots_patch, the order just took shape → treat this as the
# preOrder confirmation moment (the flow-doc `order_slots_complete → build_preorder`
# transition). goal_type/pending_intent are excluded on purpose: the router re-emits
# them across many turns, so they don't mark *this* turn as the confirmation.
_CONFIRM_SLOT_KEYS = {"ord_qty", "shop_name", "requested_cal_day", "rsv_hour"}
_PRODUCT_FIELDS = ("product_name", "pending_product_name", "tire_model")
_STORE_SEARCH_TOOLS = {
    "search_stores_tool",
    "search_stores_complex_tool",
    "get_nearby_stores_tool",
    "get_store_list_tool",
    "get_stores_with_time_filter_tool",
    "transaction_store_preview_tool",
}
_PRODUCT_TOOLS = {
    "search_product_tool",
    "search_product_summary_tool",
    "get_products_recommendations_tool",
    "get_best_selling_products_tool",
    "get_newest_products_tool",
}
_QUANTITY_QUICK_REPLIES = (
    {"label": "1개", "domain": "TRANSACTION"},
    {"label": "2개", "domain": "TRANSACTION"},
    {"label": "3개", "domain": "TRANSACTION"},
    {"label": "4개", "domain": "TRANSACTION"},
)

_PRC_GRD_ALLOWED: frozenset[str] = frozenset({"프리미엄+", "프리미엄", "스탠다드", "이코노미"})
_PRC_GRD_DISPLAY: dict[str, str] = {"프리미엄+": "프리미엄"}
_GOODS_PFM_LABELS: dict[str, str] = {
    "COMFORT": "정숙/승차감",
    "SPORT": "고속/제동성",
    "RUNFLAT": "런플랫",
}

_SERVICE_LABELS = {
    "113": "타이어",
    "119": "타이어 보관서비스",
    "120": "수입타이어 취급",
    "121": "경정비",
    "122": "경정비",
    "124": "휠얼라이먼트",
    "125": "휠얼라이먼트",
    "126": "무상점검",
}

_CNSL_TYPE_MAP = {
    "10002": "\uc0c1\ud488\ubb38\uc758",
    "10006": "\uc8fc\ubb38/\uacb0\uc81c/\ubc30\uc1a1",
    "10010": "\ubc18\ud488/\uad50\ud658/\ud658\ubd88",
    "10013": "\uc81c\uacf5\uc11c\ube44\uc2a4/\uc774\ubca4\ud2b8/\ud61c\ud0dd",
    "10017": "\ud68c\uc6d0",
    "10019": "\uae30\ud0c0",
    "10025": "\uac00\ub9f9\uc810\uc81c\ud734\ubb38\uc758",
    "10034": "\uc774\ub825\uc11c\uc811\uc218",
}

# Which template a tool's output can feed — data availability, not routing.
_TOOL_TEMPLATES: dict[str, tuple[str, type[BaseModel]]] = {
    "search_product_tool": ("product", ProductTemplate),
    "search_product_summary_tool": ("product", ProductTemplate),
    "get_products_recommendations_tool": ("product", ProductTemplate),
    "get_best_selling_products_tool": ("product", ProductTemplate),
    "get_newest_products_tool": ("product", ProductTemplate),
    "search_benefit_applicable_products_tool": ("product", ProductTemplate),
    "get_event_applicable_products_tool": ("product", ProductTemplate),
    "get_coupon_applicable_products_tool": ("product", ProductTemplate),
    "search_stores_tool": ("location", LocationTemplate),
    "search_stores_complex_tool": ("location", LocationTemplate),
    "get_nearby_stores_tool": ("location", LocationTemplate),
    "get_store_list_tool": ("location", LocationTemplate),
    "get_stores_with_time_filter_tool": ("location", LocationTemplate),
    "get_user_vehicles_tool": ("listCar", ListCarTemplate),
    "get_my_cars_tool": ("listCar", ListCarTemplate),
    "get_cheapest_price_tool": ("cheapestProduct", CheapestProductTemplate),
    "get_final_price_tool": ("preOrder", PreOrderTemplate),
    "get_store_schedule_tool": ("datepick", DatepickTemplate),
    "get_multi_store_schedule_tool": ("datepick", DatepickTemplate),
    "transaction_store_preview_tool": ("location", LocationTemplate),
    "present_order_preview_tool": ("preOrder", PreOrderTemplate),
    "quick_order_tool": ("orderComplete", OrderCompleteTemplate),
}

_INFO_GATED_TOOLS = {"search_product_tool", "search_product_summary_tool"}


def _is_selection_search(call: dict) -> bool:
    """Price-range browse (min/max_price) is always a selection — show the card
    regardless of the router signal (deterministic; honors the 'price range' case)."""
    args = call.get("args") or {}
    return args.get("min_price") is not None or args.get("max_price") is not None


def _has_multiple_products(call: dict) -> bool:
    """True when a product search returned >=2 items: a genuine list to choose from."""
    parsed = _parse_tool_output(call.get("output"))
    payload = parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
    items = payload.get("items") if isinstance(payload, dict) else None
    return isinstance(items, list) and len(items) >= 2


def _has_rows(output: str) -> bool:
    """True when the tool output parses to non-empty JSON data."""
    try:
        parsed = json.loads(output)
    except (TypeError, ValueError):
        return bool(output and len(output) > 50)
    if isinstance(parsed, dict):
        return any(bool(v) for v in parsed.values())
    return bool(parsed)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_json(output: object) -> dict[str, Any]:
    if isinstance(output, dict):
        return output
    if not isinstance(output, str):
        return {}
    try:
        parsed = json.loads(output)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _set_if_present(slots: ConversationSlots, field: str, value: Any) -> None:
    if value in (None, ""):
        return
    setattr(slots, field, value)


def _single_product(data: dict[str, Any]) -> dict[str, Any] | None:
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    items = payload.get("items") if isinstance(payload, dict) else None
    if isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict):
        return items[0]
    return None


def _product_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = [data]
    if isinstance(data.get("data"), dict):
        candidates.append(data["data"])
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in ("items", "products", "data"):
            rows = candidate.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _compact_product_name(value: Any) -> str:
    return str(value or "").casefold().replace(" ", "")


def _matching_single_product(data: dict[str, Any], slots: ConversationSlots) -> dict[str, Any] | None:
    rows = _product_rows(data)
    if not rows:
        return _single_product(data)

    target_size = normalize_tire_size(str(slots.tire_size or ""))
    target_name = _compact_product_name(_product_label(slots.model_dump(mode="json", exclude_none=True)))
    matched_rows = rows
    if target_size:
        size_rows = [
            row
            for row in matched_rows
            if normalize_tire_size(str(row.get("tire_size_1") or row.get("tire_size") or "")) == target_size
        ]
        if size_rows:
            matched_rows = size_rows
    if target_name:
        name_rows = []
        for row in matched_rows:
            row_name = _compact_product_name(row.get("goods_nm") or row.get("product_name") or row.get("title"))
            if row_name and (row_name in target_name or target_name in row_name):
                name_rows.append(row)
        if name_rows:
            matched_rows = name_rows
    if len(matched_rows) == 1:
        return matched_rows[0]
    return None


def _single_store(data: dict[str, Any]) -> dict[str, Any] | None:
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    stores = payload.get("stores") if isinstance(payload, dict) else None
    if isinstance(stores, list) and len(stores) == 1 and isinstance(stores[0], dict):
        return stores[0]
    return None


def _extract_payment_amount(data: dict[str, Any], ord_qty: int | None) -> int | None:
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(payload, dict):
        return None
    unit = _as_int(payload.get("cheapest_final_prc"))
    if unit is None:
        unit = _as_int(payload.get("extra_fvr_sale_prc"))
    if unit is None:
        unit = _as_int(payload.get("sale_prc"))
    wage = _as_int(payload.get("wage_prc")) or 0
    if unit is None or not ord_qty or ord_qty <= 0:
        return None
    return (unit + wage) * ord_qty


def _product_label(snapshot: dict[str, Any]) -> str:
    product = ""
    for field in _PRODUCT_FIELDS:
        text = str(snapshot.get(field) or "").strip()
        if text:
            product = text
            break
    tire_size = str(snapshot.get("tire_size") or "").strip()
    if product and tire_size and tire_size not in product:
        return f"{product} {tire_size}"
    return product or tire_size or str(snapshot.get("goods_no") or "").strip()


def _with_slot_fallback(snapshot: dict[str, Any], slots: ConversationSlots | None) -> dict[str, Any]:
    if slots is None:
        return snapshot
    slot_values = slots.model_dump(mode="json", exclude_none=True)
    present_snapshot = {key: value for key, value in snapshot.items() if value not in (None, "", [])}
    return {**slot_values, **present_snapshot}


def _booking_datetime(snapshot: dict[str, Any]) -> str | None:
    day = str(snapshot.get("requested_cal_day") or "").strip()
    hour = str(snapshot.get("rsv_hour") or "").strip()
    if len(day) != 8 or not day.isdigit() or not hour:
        return None
    hour = hour.split(":", 1)[0].zfill(2)
    return f"{day[:4]}년 {day[4:6]}월 {day[6:8]}일 {hour}:00"


def build_preorder_data_event(answer: str, snapshot: dict[str, Any], *, source: str) -> dict | None:
    goods_no = str(snapshot.get("goods_no") or "").strip()
    ord_qty = _as_int(snapshot.get("ord_qty"))
    if not goods_no or ord_qty is None or ord_qty <= 0:
        return None

    pending_intent = str(snapshot.get("pending_intent") or "").strip()
    goal_type = str(snapshot.get("goal_type") or "").strip()
    # K1 tool passes the flag explicitly; K2 (slots snapshot) derives it from intent.
    is_ready_to_add_to_cart = (
        bool(snapshot.get("is_ready_to_add_to_cart")) or pending_intent == "cart" or goal_type == "add_to_cart"
    )
    is_ready_to_order = not is_ready_to_add_to_cart
    tire_size = str(snapshot.get("tire_size") or "").strip() or None

    payload = PreOrderTemplate(
        orderInfo={
            "carInfo": str(snapshot.get("car_no") or "").strip() or None,
            "product": _product_label(snapshot),
            "quantity": ord_qty,
            "storeName": str(snapshot.get("shop_name") or "").strip() or None,
            "bookingDateTime": _booking_datetime(snapshot),
            "paymentAmount": _as_int(snapshot.get("payment_amount")),
        },
        isReadyToOrder=is_ready_to_order,
        isReadyToAddToCart=is_ready_to_add_to_cart,
        metadata={
            "goodsId": goods_no,
            "goodsNo": goods_no,
            "goods_no": goods_no,
            "productName": str(snapshot.get("product_name") or snapshot.get("pending_product_name") or "").strip() or None,
            "tireSize": tire_size,
            "tire_size": tire_size,
            "quantity": ord_qty,
            "ordQty": ord_qty,
            "ord_qty": ord_qty,
            "shopId": str(snapshot.get("shop_id") or "").strip() or None,
            "shop_id": str(snapshot.get("shop_id") or "").strip() or None,
            "storeName": str(snapshot.get("shop_name") or "").strip() or None,
            "requestedCalDay": str(snapshot.get("requested_cal_day") or "").strip() or None,
            "requested_cal_day": str(snapshot.get("requested_cal_day") or "").strip() or None,
            "rsvHour": str(snapshot.get("rsv_hour") or "").strip() or None,
            "rsv_hour": str(snapshot.get("rsv_hour") or "").strip() or None,
            "carNo": str(snapshot.get("car_no") or "").strip() or None,
            "carLncCd": str(snapshot.get("car_lnc_cd") or "").strip() or None,
            "source": source,
        },
    )
    return {
        "type": "data",
        "template": "preOrder",
        "data": payload.model_dump(mode="json", exclude_none=True),
    }


def _ready_order_slots(slots: ConversationSlots) -> bool:
    return bool(
        slots.goods_no
        and slots.shop_id
        and slots.ord_qty
        and slots.requested_cal_day
        and slots.rsv_hour
        and (slots.pending_intent == "order" or slots.goal_type == "place_order")
    )


def _ready_cart_slots(slots: ConversationSlots) -> bool:
    return bool(
        slots.goods_no
        and slots.ord_qty
        and (slots.pending_intent == "cart" or slots.goal_type == "add_to_cart")
    )


def _looks_like_confirmation_turn(decision: RouteDecision | None) -> bool:
    """True when this turn filled a concrete order slot — the build_preorder transition.

    Re-shows (order already complete, no new slot filled this turn) are handled by K1
    (the LLM re-calling present_order_preview_tool), so no answer-text keyword matching
    is needed here — the confirmation signal comes entirely from the router's slots_patch.
    """
    patch = decision.slots_patch.non_empty() if decision else {}
    return any(key in patch for key in _CONFIRM_SLOT_KEYS)


def build_preorder_fallback(answer: str, slots: ConversationSlots, decision: RouteDecision | None) -> dict | None:
    if not _looks_like_confirmation_turn(decision):
        return None
    if not (_ready_order_slots(slots) or _ready_cart_slots(slots)):
        return None
    return build_preorder_data_event(
        answer,
        slots.model_dump(mode="json", exclude_none=True),
        source="chat_v3_slot_fallback_preorder",
    )


def build_final_price_preorder_event(answer: str, slots: ConversationSlots | None, call: dict) -> dict | None:
    if slots is None or not _ready_order_slots(slots):
        return None
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    args_goods_no = str(args.get("goods_no") or "").strip()
    if args_goods_no and args_goods_no != str(slots.goods_no or "").strip():
        return None
    payment_amount = _extract_payment_amount(_tool_payload(call.get("output")), slots.ord_qty)
    if payment_amount is None:
        payment_amount = _as_int(slots.payment_amount)
    if payment_amount is None:
        return None

    snapshot = slots.model_dump(mode="json", exclude_none=True)
    snapshot["payment_amount"] = payment_amount
    return build_preorder_data_event(
        answer,
        snapshot,
        source="chat_v3_final_price_preorder",
    )


def harvest_order_slots(slots: ConversationSlots, tool_calls: list[dict]) -> ConversationSlots:
    for call in tool_calls:
        name = str(call.get("name") or "")
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        parsed = _parse_json(call.get("output"))

        _set_if_present(slots, "goods_no", args.get("goods_no"))
        _set_if_present(slots, "ord_qty", _as_int(args.get("ord_qty")))
        _set_if_present(slots, "shop_id", args.get("shop_id"))
        _set_if_present(slots, "requested_cal_day", args.get("rsv_date") or args.get("requested_cal_day"))
        _set_if_present(slots, "rsv_hour", args.get("rsv_hour"))
        _set_if_present(slots, "car_lnc_cd", args.get("car_lnc_cd"))

        if name in _PRODUCT_TOOLS:
            item = _matching_single_product(parsed, slots)
            if item:
                _set_if_present(slots, "goods_no", item.get("goods_no"))
                _set_if_present(slots, "tire_model", item.get("goods_nm"))
                _set_if_present(slots, "pending_product_name", item.get("goods_nm"))
                _set_if_present(slots, "tire_size", normalize_tire_size(str(item.get("tire_size_1") or "")))

        if name in _STORE_SEARCH_TOOLS:
            store = _single_store(parsed)
            if store:
                _set_if_present(slots, "shop_id", store.get("shop_id") or store.get("shopId"))
                _set_if_present(slots, "shop_name", store.get("shop_nm") or store.get("shopName"))

        if name in {"get_final_price_tool", "transaction_store_preview_tool"}:
            payment_amount = _extract_payment_amount(parsed.get("data", {}).get("price", parsed), slots.ord_qty)
            if payment_amount is not None:
                slots.payment_amount = payment_amount
                slots.price_basis = "payment_amount"
                slots.price_source_tool = name
                slots.source_tool = name

    return slots


def _product_resolved_this_turn(
    slots: ConversationSlots | None,
    previous_slots: ConversationSlots | None,
) -> bool:
    return bool(slots and slots.goods_no and previous_slots and not previous_slots.goods_no)


def _should_skip_product_source(
    template_name: str,
    slots: ConversationSlots | None,
    previous_slots: ConversationSlots | None = None,
) -> bool:
    return (
        template_name == "product"
        and bool(slots and slots.goods_no and _is_booking_location_context(slots))
        and not _product_resolved_this_turn(slots, previous_slots)
    )


def _answer_requests_store_selection(answer: str) -> bool:
    text = str(answer or "").replace(" ", "")
    if not any(anchor in text for anchor in ("장착매장", "매장", "지역", "장소", "근처", "지점")):
        return False
    return any(action in text for action in ("알려", "선택", "골라", "말씀", "입력", "정해"))


def _has_product_size_quantity(slots: ConversationSlots | None) -> bool:
    if slots is None:
        return False
    return bool(slots.goods_no and slots.tire_size and _has_confirmed_quantity(slots))


def _pick_source(
    tool_calls: list[dict],
    slots: ConversationSlots | None = None,
    previous_slots: ConversationSlots | None = None,
) -> tuple[str, type[BaseModel], dict] | None:
    """Most recent tool call whose output can feed a rich template."""
    candidates: list[tuple[str, type[BaseModel], dict]] = []
    for call in reversed(tool_calls):
        entry = _TOOL_TEMPLATES.get(call.get("name") or "")
        output = str(call.get("output") or "")
        if entry and _should_skip_product_source(entry[0], slots, previous_slots):
            continue
        if entry and not output.startswith("Tool error") and _has_rows(output):
            candidates.append((entry[0], entry[1], call))
    if not candidates:
        return None

    if _has_product_size_quantity(slots):
        if not slots.shop_id:
            for candidate in candidates:
                if candidate[0] == "location":
                    return candidate
            return None
        for candidate in candidates:
            if candidate[0] == "datepick":
                return candidate

    return candidates[0]


def _should_gate_info_product_source(
    call: dict,
    *,
    allow_selection_cards: bool,
    slots: ConversationSlots | None,
    previous_slots: ConversationSlots | None,
) -> bool:
    if call.get("name") not in _INFO_GATED_TOOLS or _is_selection_search(call):
        return False
    if _product_resolved_this_turn(slots, previous_slots):
        return False
    return not allow_selection_cards or not _has_multiple_products(call)


_RELEVANCE_WRAPPERS: dict[str, type[BaseModel]] = {}


def _relevance_wrapper(template_model: type[BaseModel]) -> type[BaseModel]:
    """Wrap a template model with an `applicable` flag the LLM can set to false.

    In a multi-round tool loop, `_pick_source` can only see WHICH tool ran
    most recently — not whether the final answer is still about it. E.g. a
    product tool run to confirm a quantity, followed by a final answer that
    pivots to asking the user for a store location, leaves a stale product
    call as the "most recent" one. Folding `applicable` into the SAME
    structured-output call (instead of a separate check) lets the model
    judge relevance against the actual final answer text at no extra cost.
    """
    wrapper = _RELEVANCE_WRAPPERS.get(template_model.__name__)
    if wrapper is None:
        wrapper = create_model(
            f"{template_model.__name__}Decision",
            applicable=(
                bool,
                Field(description="답변이 실제로 이 도구 결과를 보여주는 중이면 true, 다른 주제로 넘어갔으면 false"),
            ),
            payload=(template_model | None, Field(default=None, description="applicable=true일 때만 채우세요")),
        )
        _RELEVANCE_WRAPPERS[template_model.__name__] = wrapper
    return wrapper


def _parse_tool_output(output: object) -> dict[str, Any]:
    if isinstance(output, dict):
        return output
    try:
        parsed = json.loads(str(output or ""))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _tool_payload(output: object) -> dict[str, Any]:
    parsed = _parse_tool_output(output)
    data = parsed.get("data")
    return data if isinstance(data, dict) else parsed


def _get_str(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _truthy_flag(value: object) -> bool:
    return str(value or "").strip().upper() in {"Y", "O", "TRUE", "1"}


def _get_num(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            continue
    return None


def _parse_schedule_hour(value: object) -> int | None:
    text = str(value or "").strip()
    if not text.isdigit():
        return None
    if len(text) <= 2:
        hour = int(text)
    elif len(text) == 4:
        hour = int(text[:2])
    else:
        return None
    return hour if 0 <= hour <= 23 else None


def _schedule_slots_by_day(rows: object) -> dict[str, set[int]]:
    by_day: dict[str, set[int]] = {}
    if not isinstance(rows, list):
        return by_day
    for row in rows:
        if not isinstance(row, dict):
            continue
        cal_day = _get_str(row, "cal_day", "calDay")
        hour = _parse_schedule_hour(row.get("tm") or row.get("time") or row.get("hour"))
        if len(cal_day) != 8 or not cal_day.isdigit() or hour is None or hour == 12:
            continue
        by_day.setdefault(cal_day, set()).add(hour)
    return by_day


def _datepick_response(shop_name: str, dates: list[dict[str, Any]]) -> str:
    first = next((date for date in dates if date.get("availableTimes")), None)
    if not first:
        return "예약 가능한 일정을 확인했어요. 원하시는 날짜와 시간을 선택해 주세요."
    times = ", ".join(f"{hour}시" for hour in first["availableTimes"][:8])
    subject = f"{shop_name}에서 " if shop_name else ""
    return f"{subject}예약 가능한 일정을 확인했어요.\n{first['date']}: {times}\n원하시는 날짜와 시간을 선택해 주세요."


def _get_store_schedule_datepick_event(answer: str, call: dict, slots: ConversationSlots | None = None) -> dict | None:
    payload = _tool_payload(call.get("output"))
    by_day = _schedule_slots_by_day(payload.get("slots"))
    if not by_day:
        return None

    dates: list[dict[str, Any]] = []
    selected_idx: int | None = None
    for index, cal_day in enumerate(sorted(by_day.keys())):
        times = sorted(by_day[cal_day])
        dates.append({
            "date": _format_korean_date(cal_day),
            "available": bool(times),
            "availableTimes": times,
            "index": index,
        })
        if selected_idx is None and times:
            selected_idx = index
    if selected_idx is None:
        return None

    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    shop_id = _get_str(payload, "shop_id", "shopId") or _get_str(args, "shop_id", "shopId")
    shop_name = _get_str(payload, "shop_nm", "shopName", "storeName") or str(getattr(slots, "shop_name", "") or "")
    metadata = {"shopId": shop_id or None}
    if shop_name:
        metadata["shopName"] = shop_name
    datepick = DatepickTemplate(
        assistantResponse=_datepick_response(shop_name, dates) or answer,
        dates=dates,
        selectedDate=selected_idx,
        metadata=metadata,
    )
    _normalize_datepick_payload(datepick, slots)
    return {
        "type": "data",
        "template": "datepick",
        "data": datepick.model_dump(mode="json", exclude_none=True),
        "source_tool": call["name"],
        "assistant_response_source": "code_chat_v3_get_store_schedule",
    }


def _latest_tool_output(tool_calls: list[dict], tool_name: str) -> dict[str, Any]:
    for call in reversed(tool_calls):
        if call.get("name") == tool_name:
            return _parse_tool_output(call.get("output"))
    return {}


def _benefit_items_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, dict):
        rows = data.get("items")
    else:
        rows = payload.get("items")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _benefit_date(value: str) -> str:
    return str(value or "").strip()[:10]


def _benefit_total(raw: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    data = raw.get("data")
    total = data.get("total") if isinstance(data, dict) else None
    return total if isinstance(total, int) and total > 0 else len(rows)


def _append_benefit_rows(
    lines: list[str],
    rows: list[dict[str, Any]],
    *,
    name_keys: tuple[str, ...],
    start_keys: tuple[str, ...],
    end_keys: tuple[str, ...],
) -> None:
    for index, row in enumerate(rows[:5], start=1):
        name = _get_str(row, *name_keys)
        if not name:
            continue
        start = _benefit_date(_get_str(row, *start_keys))
        end = _benefit_date(_get_str(row, *end_keys))
        lines.append(f"{index}. **{name}**")
        if start and end:
            lines.append(f"   - 기간: {start} ~ {end}")
        elif start or end:
            lines.append(f"   - 기간: {start or end}")


def _benefit_quick_replies(*, has_events: bool, has_deals: bool) -> list[dict[str, str]]:
    chips: list[dict[str, str]] = []
    if has_events:
        chips.append({"label": "진행 중인 이벤트", "url": CTAUrls.PROMOTION_EVENT_LIST, "domain": "DISCOVERY"})
    if has_deals:
        chips.append({"label": "진행 중인 기획전", "url": CTAUrls.PROMOTION_DEAL_LIST, "domain": "DISCOVERY"})
    return chips or [{"label": "진행 중인 이벤트", "url": CTAUrls.PROMOTION_EVENT_LIST, "domain": "DISCOVERY"}]


def _format_benefit_answer(lines: list[str]) -> str:
    text = "\n".join(line.rstrip() for line in lines).replace("\r\n", "\n").replace("\r", "\n")
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()


def build_current_events_quickreply_event(tool_calls: list[dict]) -> dict | None:
    event_raw = _latest_tool_output(tool_calls, "get_events_tool")
    deal_raw = _latest_tool_output(tool_calls, "get_deals_tool")
    event_rows = _benefit_items_from_payload(event_raw) if event_raw.get("status") == "success" else []
    deal_rows = _benefit_items_from_payload(deal_raw) if deal_raw.get("status") == "success" else []
    if not event_raw and not deal_raw:
        return None
    if not event_rows and not deal_rows:
        if event_raw and deal_raw:
            assistant_response = "현재 진행 중인 이벤트나 기획전이 없어요. 잠시 후에 다시 확인해 주세요."
        elif deal_raw:
            assistant_response = "현재 진행 중인 기획전이 없어요. 잠시 후에 다시 확인해 주세요."
        else:
            assistant_response = "현재 진행 중인 이벤트가 없어요. 잠시 후에 다시 확인해 주세요."
    else:
        if event_rows and deal_rows:
            lines = [
                (
                    f"현재 진행 중인 이벤트는 총 {_benefit_total(event_raw, event_rows)}개, "
                    f"기획전은 총 {_benefit_total(deal_raw, deal_rows)}개입니다."
                ),
                "",
                "진행 중인 이벤트",
            ]
            _append_benefit_rows(
                lines,
                event_rows,
                name_keys=("evt_nm", "event_nm", "title", "name"),
                start_keys=("evt_strt_dtime", "start_date", "startDate"),
                end_keys=("evt_end_dtime", "end_date", "endDate"),
            )
            lines.extend(["", "진행 중인 기획전"])
            _append_benefit_rows(
                lines,
                deal_rows,
                name_keys=("deal_nm", "deal_nm_ko", "title", "name"),
                start_keys=("deal_strt_dtime", "start_date", "startDate"),
                end_keys=("deal_end_dtime", "end_date", "endDate"),
            )
            lines.extend(["", "원하시면 특정 이벤트나 기획전의 대상 상품과 적용 가능한 혜택도 확인해드릴게요."])
        elif deal_rows:
            lines = [f"현재 진행 중인 기획전은 총 {_benefit_total(deal_raw, deal_rows)}개입니다.", "", "진행 중인 기획전"]
            _append_benefit_rows(
                lines,
                deal_rows,
                name_keys=("deal_nm", "deal_nm_ko", "title", "name"),
                start_keys=("deal_strt_dtime", "start_date", "startDate"),
                end_keys=("deal_end_dtime", "end_date", "endDate"),
            )
            lines.extend(["", "원하시면 특정 기획전의 대상 상품이나 적용 가능한 혜택도 확인해드릴게요."])
        else:
            lines = [f"현재 진행 중인 이벤트는 총 {_benefit_total(event_raw, event_rows)}개입니다.", "", "진행 중인 이벤트"]
            _append_benefit_rows(
                lines,
                event_rows,
                name_keys=("evt_nm", "event_nm", "title", "name"),
                start_keys=("evt_strt_dtime", "start_date", "startDate"),
                end_keys=("evt_end_dtime", "end_date", "endDate"),
            )
            lines.extend(["", "원하시면 특정 이벤트의 대상 상품이나 적용 가능한 혜택도 확인해드릴게요."])
        assistant_response = _format_benefit_answer(lines)
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": _benefit_quick_replies(has_events=bool(event_raw), has_deals=bool(deal_raw)),
            "predictedDomains": ["DISCOVERY"],
            "metadata": {
                "source": "chat_v3_current_events",
                "response_shape_key": "benefit_event_list_lookup",
                "eventCount": len(event_rows),
                "dealCount": len(deal_rows),
            },
        },
        "assistant_response_source": "code_chat_v3_current_events",
    }


def _answer_without_urls(answer: str) -> str:
    lines = []
    for line in str(answer or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if "http://" in line or "https://" in line:
            continue
        cleaned = line.strip()
        if cleaned:
            lines.append(cleaned)
    return compact_answer_spacing("\n".join(lines))


def _cnsl_type_label(cnsl_clss_seq: object) -> str:
    seq = str(cnsl_clss_seq or "").strip()
    return _CNSL_TYPE_MAP.get(seq, seq or "1:1")


def build_qna_complete_event(answer: str, tool_calls: list[dict]) -> dict | None:
    """Build qnaComplete directly from transfer_to_qna_tool output."""
    raw = _latest_tool_output(tool_calls, "transfer_to_qna_tool")
    if not raw or raw.get("status") != "success":
        return None
    redict_link = raw.get("redictLink") or raw.get("redict_link")
    if not isinstance(redict_link, dict) or not redict_link.get("pc") or not redict_link.get("mobile"):
        return None

    title = str(raw.get("inq_tit_nm") or "1:1 문의").strip()
    summary = str(raw.get("ai_summary") or title).strip()
    assistant_response = _answer_without_urls(answer) or summary
    payload = QnaCompleteTemplate(
        assistantResponse=assistant_response,
        redictLink=redict_link,
        cnslType=_cnsl_type_label(raw.get("cnsl_clss_seq")),
        title=title,
        summary=summary,
    )
    return {
        "type": "data",
        "template": "qnaComplete",
        "data": payload.model_dump(mode="json", exclude_none=True),
        "source_tool": "transfer_to_qna_tool",
    }


def _store_rows_from_output(output: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(output)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, dict):
        return []
    data = parsed.get("data")
    candidates = [data, parsed]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in ("stores", "items", "stores_available"):
            rows = candidate.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _car_rows_from_output(output: str) -> list[dict[str, Any]]:
    parsed = _parse_tool_output(output)
    if not parsed:
        return []
    data = parsed.get("data")
    if isinstance(data, list):
        return _rows_from_any(data)
    candidates = [data, parsed]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        rows = _rows_from_any(candidate.get("items"))
        if rows:
            return rows
    if any(_get_str(parsed, key) for key in ("car_no", "carNo", "licensePlate")):
        return [parsed]
    return []


def _car_available_sizes(row: dict[str, Any]) -> list[str]:
    raw_sizes = (
        row.get("available_sizes") or row.get("availableSizes") or row.get("valid_sizes") or row.get("validSizes")
    )
    candidates = raw_sizes if isinstance(raw_sizes, list) else []
    sizes: list[str] = []
    for raw_size in [
        *candidates,
        row.get("tire_size_fr"),
        row.get("tireSize"),
        row.get("tire_size_re"),
        row.get("tireSizeRe"),
    ]:
        size = normalize_tire_size(str(raw_size or ""))
        if size and size not in sizes:
            sizes.append(size)
    return sizes


def _listcar_contract_intent(slots: ConversationSlots | None) -> str:
    if slots is None:
        return "vehicle_resolved_recommendation"
    if slots.pending_intent == "order" or slots.goal_type == "place_order":
        return "quick_order_reservation"
    if slots.pending_intent == "stock" or slots.goal_type == "store_with_stock":
        return "stock_store_search"
    return "vehicle_resolved_recommendation"


def build_listcar_data_event(answer: str, call: dict, slots: ConversationSlots | None = None) -> dict | None:
    rows = _car_rows_from_output(str(call.get("output") or ""))
    if not rows:
        return None

    items: list[CarItem] = []
    metadata: list[CarMeta] = []
    source_intent = _listcar_contract_intent(slots)
    for row in rows[:5]:
        car_no = _get_str(row, "car_no", "carNo", "licensePlate")
        if not car_no:
            continue
        car_model = _get_str(row, "car_model_det", "carModelDet", "car_nm", "carName", "car_model", "carModel")
        car_maker = _get_str(row, "car_maker", "carMaker")
        car_info = " ".join(part for part in (car_maker, car_model) if part).strip() or car_no
        available_sizes = _car_available_sizes(row)
        multiple_sizes = len(available_sizes) > 1
        tire_size = None if multiple_sizes else (normalize_tire_size(_get_str(row, "tire_size_fr", "tireSize")) or None)
        tire_size_re = (
            None if multiple_sizes else (normalize_tire_size(_get_str(row, "tire_size_re", "tireSizeRe")) or None)
        )
        items.append(
            CarItem(
                licensePlate=car_no,
                info=car_info,
                description=car_info,
                imageUrl=_get_str(row, "thnl_img_path_nm", "mo_img_path_nm", "pc_img_path_nm", "imageUrl"),
            )
        )
        metadata.append(
            CarMeta(
                carNo=car_no,
                car_no=car_no,
                carLncCd=_get_str(row, "car_lnc_cd", "carLncCd") or None,
                car_lnc_cd=_get_str(row, "car_lnc_cd", "carLncCd") or None,
                mbrCarRegSeq=_get_str(row, "mbr_car_reg_seq", "mbr_car_unif_no", "mbrCarRegSeq") or None,
                mbr_car_reg_seq=_get_str(row, "mbr_car_reg_seq", "mbr_car_unif_no", "mbrCarRegSeq") or None,
                carMaker=car_maker or None,
                carModelDet=_get_str(row, "car_model_det", "carModelDet") or None,
                car_model_det=_get_str(row, "car_model_det", "carModelDet") or None,
                carName=_get_str(row, "car_nm", "carName") or None,
                car_nm=_get_str(row, "car_nm", "carName") or None,
                carTrim=_get_str(row, "ver_opt_choc", "carTrim") or None,
                carEngine=_get_str(row, "car_engine", "carEngine") or None,
                carType=_get_str(row, "car_type", "carType") or None,
                car_type=_get_str(row, "car_type", "carType") or None,
                vehicleType=_get_str(row, "vehicle_type", "vehicleType") or None,
                vehicle_type=_get_str(row, "vehicle_type", "vehicleType") or None,
                tireSize=tire_size,
                tire_size_fr=tire_size,
                tireSizeRe=tire_size_re,
                tire_size_re=tire_size_re,
                availableSizes=available_sizes or None,
                available_sizes=available_sizes or None,
                ctaAction="select_vehicle_candidate",
                cta_action="select_vehicle_candidate",
                sourceIntent=source_intent,
                source_intent=source_intent,
                expectedContractIntent=source_intent,
                expected_contract_intent=source_intent,
            )
        )

    if not items:
        return None
    payload = ListCarTemplate(assistantResponse=answer, listCar=items, metadata=metadata)
    return {
        "type": "data",
        "template": "listCar",
        "data": payload.model_dump(mode="json", exclude_none=True),
        "source_tool": call["name"],
    }


def _rows_from_any(value: object) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _product_rows_from_output(output: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(output)
    except (TypeError, ValueError):
        return []
    if isinstance(parsed, list):
        return _rows_from_any(parsed)
    if not isinstance(parsed, dict):
        return []

    for key in ("products", "items", "results"):
        rows = _rows_from_any(parsed.get(key))
        if rows:
            return rows
    data = parsed.get("data")
    if isinstance(data, list):
        return _rows_from_any(data)
    if isinstance(data, dict):
        for key in ("products", "items", "results"):
            rows = _rows_from_any(data.get(key))
            if rows:
                return rows
    return []


def _product_tags_from_row(row: dict[str, Any]) -> list[ProductTag]:
    tags: list[ProductTag] = []
    price_grade = _get_str(row, "prc_grd_nm")
    if price_grade in _PRC_GRD_ALLOWED:
        tags.append(ProductTag(text=_PRC_GRD_DISPLAY.get(price_grade, price_grade), primary=True))

    performance = _GOODS_PFM_LABELS.get(_get_str(row, "goods_pfm_nm").upper())
    if performance:
        tags.append(ProductTag(text=performance, primary=False))

    if _truthy_flag(row.get("sound_absorber_yn")) or "흡음" in _get_str(row, "goods_dtl_pfm_nm"):
        tags.append(ProductTag(text="흡음재", primary=False))
    return tags


def _product_price(row: dict[str, Any]) -> int | None:
    price = _get_num(row, "cheapest_final_prc", "extra_fvr_sale_prc", "final_unit_price", "final_prc", "price")
    return int(price) if price else None


def _product_original_price(row: dict[str, Any], price: int | None) -> int | None:
    original = _get_num(row, "sale_prc", "originalPrice", "original_price")
    if original:
        return int(original)
    return price


def _product_discount_amount(row: dict[str, Any], price: int | None, original_price: int | None) -> int | None:
    discount = _get_num(row, "discountAmount", "discount_amount")
    if discount:
        return int(discount)
    if price and original_price and original_price > price:
        return original_price - price
    return None


def _product_discount_rate(row: dict[str, Any], discount_amount: int | None, original_price: int | None) -> float | None:
    rate = _get_num(row, "extra_fvr_sale_per", "discountRate", "discount_rate")
    if rate:
        return rate
    if discount_amount and original_price:
        return round(discount_amount / original_price * 100, 1)
    return None


def _product_item_from_row(row: dict[str, Any]) -> ProductItem:
    goods_name = _get_str(row, "goods_nm", "goodsNm", "title", "name")
    tire_size = _get_str(row, "tire_size_1", "tire_size_2", "tire_size", "size")
    price = _product_price(row)
    original_price = _product_original_price(row, price)
    discount_amount = _product_discount_amount(row, price, original_price)
    discount_rate = _product_discount_rate(row, discount_amount, original_price)
    brand = _get_str(row, "brand_nm", "brandName", "brand_name")
    return ProductItem(
        imageUrl=_get_str(row, "image_url", "imageUrl"),
        title=f"{goods_name} {tire_size}".strip() or tire_size or _get_str(row, "goods_no"),
        tires=tire_size,
        titleProductName=goods_name,
        titleTires=tire_size,
        brandName=brand.replace(" ", "").upper() if brand else "",
        oeBadgeYn=_get_str(row, "oe_badge_yn", "oeBadgeYn", "oeBadgeYN"),
        oeMaker=_get_str(row, "t_oe_maker_1", "oeMaker"),
        smrtPayYn=_get_str(row, "smrt_pay_yn", "smrtPayYn"),
        price=price,
        originalPrice=original_price,
        discountRate=discount_rate,
        discountAmount=discount_amount,
        rate=_get_num(row, "rate", "rating_avg", "rating") or 0.0,
        totalQuantity=int(_get_num(row, "totalQuantity", "total_qty", "review_count") or 0),
        tags=_product_tags_from_row(row),
    )


def _normalize_product_payload(payload: BaseModel, tool_output: str) -> None:
    raw_products = _product_rows_from_output(tool_output)
    products = getattr(payload, "products", None)
    metadata = getattr(payload, "metadata", None)
    if not raw_products or not isinstance(products, list):
        return

    source_rows = raw_products[:10]
    rebuilt_products: list[ProductItem] = []
    rebuilt_metadata: list[ProductMeta] = []
    for row in source_rows:
        goods_no = _get_str(row, "goods_no", "goodsNo", "goods_id", "goodsId")
        if not goods_no:
            continue
        rebuilt_products.append(_product_item_from_row(row))
        rebuilt_metadata.append(ProductMeta(goodsId=goods_no))
    if rebuilt_products:
        payload.products = rebuilt_products
        payload.metadata = rebuilt_metadata
        return

    rows_by_goods = {
        goods_no: row
        for row in raw_products
        if (goods_no := _get_str(row, "goods_no", "goodsNo", "goods_id", "goodsId"))
    }
    for index, product in enumerate(products):
        meta = metadata[index] if isinstance(metadata, list) and index < len(metadata) else None
        goods_id = getattr(meta, "goodsId", "") if meta is not None else ""
        row = rows_by_goods.get(str(goods_id or "").strip())
        if row is None and index < len(raw_products):
            row = raw_products[index]
        if row is None:
            continue

        goods_name = _get_str(row, "goods_nm", "goodsNm", "title", "name")
        tire_size = _get_str(row, "tire_size_1", "tire_size_2", "tire_size", "size")
        if goods_name:
            product.titleProductName = goods_name
            product.title = f"{goods_name} {tire_size}".strip() if tire_size else goods_name
        if tire_size:
            product.titleTires = tire_size
            product.tires = tire_size
        brand = _get_str(row, "brand_nm", "brandName", "brand_name")
        if brand:
            product.brandName = brand.replace(" ", "").upper()
        image_url = _get_str(row, "image_url", "imageUrl")
        if image_url:
            product.imageUrl = image_url
        price = _product_price(row)
        original_price = _product_original_price(row, price)
        discount_amount = _product_discount_amount(row, price, original_price)
        discount_rate = _product_discount_rate(row, discount_amount, original_price)
        product.price = price
        product.originalPrice = original_price
        product.discountAmount = discount_amount
        product.discountRate = discount_rate
        product.rate = _get_num(row, "rate", "rating_avg", "rating") or 0.0
        product.totalQuantity = int(_get_num(row, "totalQuantity", "total_qty", "review_count") or 0)
        product.tags = _product_tags_from_row(row)
        product.oeBadgeYn = _get_str(row, "oe_badge_yn", "oeBadgeYn", "oeBadgeYN")
        product.oeMaker = _get_str(row, "t_oe_maker_1", "oeMaker")
        product.smrtPayYn = _get_str(row, "smrt_pay_yn", "smrtPayYn")


def _product_selection_contract_intent(slots: ConversationSlots | None) -> str:
    if slots is not None and (slots.pending_intent == "stock" or slots.goal_type == "store_with_stock"):
        return "stock_store_search"
    return "quick_order_reservation"


def _normalize_product_selection_payload(payload: BaseModel, slots: ConversationSlots | None = None) -> None:
    if not _is_booking_location_context(slots):
        return
    products = getattr(payload, "products", None)
    metadata = getattr(payload, "metadata", None)
    if not isinstance(products, list) or not isinstance(metadata, list):
        return
    if len(products) != len(metadata):
        return

    payload.isBookingFlow = True
    expected_intent = _product_selection_contract_intent(slots)
    for product, meta in zip(products, metadata):
        if not isinstance(meta, ProductMeta):
            continue
        goods_no = str(meta.goodsId or meta.goodsNo or meta.goods_no or "").strip()
        product_name = str(getattr(product, "titleProductName", None) or getattr(product, "title", None) or "").strip()
        tire_size = str(getattr(product, "titleTires", None) or getattr(product, "tires", None) or "").strip()
        slots_payload = {"goods_no": goods_no}
        if product_name:
            slots_payload.update({
                "product_name": product_name,
                "tire_model": product_name,
                "pending_product_name": product_name,
            })
        if tire_size:
            slots_payload["tire_size"] = tire_size

        meta.goodsNo = goods_no
        meta.goods_no = goods_no
        meta.productName = product_name or None
        meta.product_name = product_name or None
        meta.tireSize = tire_size or None
        meta.tire_size = tire_size or None
        meta.domain = meta.domain or "TRANSACTION"
        meta.cta_action = "select_product"
        meta.fills_slot = "product"
        meta.entity_id = meta.entity_id or goods_no
        meta.source_intent = meta.source_intent or expected_intent
        meta.expected_contract_intent = meta.expected_contract_intent or expected_intent
        meta.expected_behavior = meta.expected_behavior or "slot_fill"
        meta.slots = slots_payload
        meta.ui_action = {
            "action_type": "select_product",
            "cta_action": "select_product",
            "fills_slot": "product",
            "expected_behavior": meta.expected_behavior,
            "source_intent": meta.source_intent,
            "expected_contract_intent": meta.expected_contract_intent,
            "entity_type": "product",
            "entity_id": goods_no,
            "entity_label": product_name or None,
            "slots": slots_payload,
        }


def _join_address(*parts: object) -> str:
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def _format_hour(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if ":" in text:
        return text
    if text.isdigit() and len(text) <= 2:
        return f"{int(text):02d}:00"
    return text


def _format_time_range(start: object, end: object) -> str:
    start_text = _format_hour(start)
    end_text = _format_hour(end)
    if start_text and end_text:
        return f"{start_text}~{end_text}"
    return start_text or end_text or "-"


def _format_korean_date(value: object) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}년 {text[4:6]}월 {text[6:8]}일"
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        year, month, day = text.split("-", 2)
        if len(year) == 4 and len(month) == 2 and len(day) == 2 and year.isdigit() and month.isdigit() and day.isdigit():
            return f"{year}년 {month}월 {day}일"
    return text


def _closed_days(row: dict[str, Any]) -> str:
    end_day = str(row.get("shop_biz_end_wday") or "").strip()
    if end_day == "일요일":
        return "없음"
    if end_day == "토요일":
        return "일요일"
    if end_day == "금요일":
        return "토요일, 일요일"
    return "-"


def _feature_labels(row: dict[str, Any]) -> list[str]:
    labels = []
    if row.get("is_all_my_t"):
        labels.append("all my T")
    if row.get("is_installable"):
        labels.append("온라인 장착 가능")
    if row.get("is_imported_car"):
        labels.append("수입차 특화점")
    if row.get("is_ev_specialty"):
        labels.append("전기차 특화점")
    if row.get("is_ev_charge_available"):
        labels.append("전기차 충전 가능")
    return labels


def _service_labels(row: dict[str, Any]) -> list[str]:
    raw_codes = row.get("svc_codes") or []
    if isinstance(raw_codes, str):
        raw_codes = [raw_codes]
    labels = []
    seen = set()
    for code in raw_codes if isinstance(raw_codes, list) else []:
        label = _SERVICE_LABELS.get(str(code))
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    return labels


def _store_info_lines(row: dict[str, Any]) -> list[str]:
    return [
        f"주소: {_join_address(row.get('addr_base'), row.get('addr_dtl')) or '-'}",
        f"연락처: {str(row.get('tel_no') or '').strip() or '-'}",
        f"평일: {_format_time_range(row.get('shop_biz_strt_time'), row.get('shop_biz_end_time'))}",
        f"토요일: {_format_time_range(row.get('shop_sat_strt_time'), row.get('shop_sat_end_time'))}",
        f"휴무일: {_closed_days(row)}",
        f"특징: {', '.join(_feature_labels(row)) or '-'}",
        f"서비스: {', '.join(_service_labels(row)) or '-'}",
    ]


def _intro_from_answer(answer: str) -> str:
    intro = (answer or "").split("\n\n", 1)[0].strip()
    return intro if intro and not intro.startswith("1.") else "확인된 매장 정보입니다."


def compact_answer_spacing(answer: str) -> str:
    text = str(answer or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    while "\n\n" in text:
        text = text.replace("\n\n", "\n")
    return text.strip()


def _has_confirmed_quantity(slots: ConversationSlots | None) -> bool:
    if slots is None:
        return False
    qty = slots.ord_qty
    return isinstance(qty, int) and qty > 0


def _is_quantity_required_flow(slots: ConversationSlots | None, decision: RouteDecision | None = None) -> bool:
    if slots is None or _has_confirmed_quantity(slots):
        return False
    if not slots.goods_no:
        return False
    pending_intent = str(slots.pending_intent or "").strip()
    goal_type = str(slots.goal_type or "").strip()
    if pending_intent in {"order", "reservation", "cart"}:
        return True
    if goal_type in {"place_order", "add_to_cart", "store_with_stock"}:
        return True
    patch = decision.slots_patch.non_empty() if decision else {}
    if str(patch.get("pending_intent") or "").strip() in {"order", "reservation", "cart"}:
        return True
    if str(patch.get("goal_type") or "").strip() in {"place_order", "add_to_cart", "store_with_stock"}:
        return True
    return False


def _has_all_quantity_options(answer: str) -> bool:
    text = str(answer or "")
    return all(chip["label"] in text for chip in _QUANTITY_QUICK_REPLIES)


def quantity_quick_replies(slots: ConversationSlots | None, decision: RouteDecision | None = None) -> list[dict[str, str]]:
    if not _is_quantity_required_flow(slots, decision):
        return []
    return [dict(chip) for chip in _QUANTITY_QUICK_REPLIES]


def ensure_quantity_options(answer: str, slots: ConversationSlots | None, decision: RouteDecision | None = None) -> str:
    if not quantity_quick_replies(slots, decision) or _has_all_quantity_options(answer):
        return answer
    return compact_answer_spacing(f"{answer}\n수량은 1개, 2개, 3개, 4개 중에서 선택해 주세요.")


def format_location_answer(answer: str, tool_calls: list[dict]) -> str:
    source = _pick_source(tool_calls)
    if source is None or source[0] != "location":
        return answer
    raw_stores = _store_rows_from_output(str(source[2].get("output") or ""))
    if not raw_stores:
        return answer

    sections = [_intro_from_answer(answer)]
    for index, row in enumerate(raw_stores[:5], start=1):
        shop_name = str(row.get("shop_nm") or "").strip() or f"매장 {index}"
        lines = "\n   ".join(_store_info_lines(row))
        sections.append(f"{index}. **{shop_name}**\n   {lines}")
    return "\n\n".join(sections)


def _location_slot_values(shop_id: str, shop_name: str, slots: ConversationSlots | None) -> dict[str, Any]:
    values = slots.model_dump(mode="json", exclude_none=True) if slots else {}
    values.update({"shop_id": shop_id, "shop_name": shop_name, "store_name": shop_name})
    return {key: value for key, value in values.items() if value not in (None, "", [])}


def _normalize_location_payload(payload: BaseModel, tool_output: str, slots: ConversationSlots | None = None) -> None:
    raw_stores = _store_rows_from_output(tool_output)
    stores = getattr(payload, "stores", None)
    metadata = getattr(payload, "metadata", None)
    if not raw_stores or not isinstance(stores, list):
        return

    for index, (item, raw) in enumerate(zip(stores, raw_stores)):
        shop_name = str(raw.get("shop_nm") or "").strip()
        if shop_name:
            item.nameAddress = shop_name
        detail_address = _join_address(raw.get("addr_base"), raw.get("addr_dtl"))
        if detail_address:
            item.detailAddress = detail_address
        item.description = "\n".join(_store_info_lines(raw))
        if isinstance(metadata, list) and index < len(metadata):
            meta = metadata[index]
            shop_id = str(raw.get("shop_id") or "").strip()
            if shop_id:
                meta.shopId = shop_id
            if shop_name:
                meta.shopName = shop_name
            if _is_booking_location_context(slots):
                slots_payload = _location_slot_values(shop_id, shop_name, slots)
                meta.domain = meta.domain or "TRANSACTION"
                meta.cta_action = "select_store"
                meta.ctaAction = "select_store"
                meta.fills_slot = "store"
                meta.fillsSlot = "store"
                meta.entity_id = shop_id or None
                meta.entity_label = shop_name or None
                meta.source_intent = meta.source_intent or "quick_order_reservation"
                meta.expected_contract_intent = meta.expected_contract_intent or "quick_order_reservation"
                meta.expected_behavior = meta.expected_behavior or "slot_fill"
                meta.slots = slots_payload
                meta.ui_action = {
                    "action_type": "select_store",
                    "cta_action": "select_store",
                    "fills_slot": "store",
                    "expected_behavior": meta.expected_behavior,
                    "source_intent": meta.source_intent,
                    "expected_contract_intent": meta.expected_contract_intent,
                    "entity_type": "store",
                    "entity_id": shop_id or None,
                    "entity_label": shop_name or None,
                    "slots": slots_payload,
                }


def build_location_data_event(answer: str, call: dict, slots: ConversationSlots | None = None) -> dict | None:
    raw_stores = _store_rows_from_output(str(call.get("output") or ""))
    if not raw_stores:
        return None

    stores: list[LocationItem] = []
    metadata: list[LocationMeta] = []
    for index, row in enumerate(raw_stores[:10], start=1):
        shop_id = _get_str(row, "shop_id", "shopId")
        if not shop_id:
            continue
        shop_name = _get_str(row, "shop_nm", "shopName", "storeName", "name") or f"매장 {index}"
        stores.append(
            LocationItem(
                nameAddress=shop_name,
                distance=_get_str(row, "distance", "distance_km", "distanceKm", "dist"),
                detailAddress=_join_address(row.get("addr_base"), row.get("addr_dtl")),
                isAllMyT=_truthy_flag(row.get("is_all_my_t") or row.get("all_my_t_yn") or row.get("allMyT")),
                todayInstall=_truthy_flag(row.get("today_install") or row.get("todayInstall")),
                tnaDelivery=_truthy_flag(row.get("tna_delivery") or row.get("tnaDelivery")),
                description="\n".join(_store_info_lines(row)),
            )
        )
        metadata.append(
            LocationMeta(
                shopId=shop_id,
                shopName=shop_name,
                sourceTool=str(call.get("name") or "") or None,
                source_tool=str(call.get("name") or "") or None,
                isInstallable=row.get("is_installable"),
            )
        )

    if not stores:
        return None

    payload = LocationTemplate(
        assistantResponse=answer,
        stores=stores,
        metadata=metadata,
        isBookingFlow=_is_booking_location_context(slots),
    )
    _normalize_location_payload(payload, str(call.get("output") or ""), slots)
    return {
        "type": "data",
        "template": "location",
        "data": payload.model_dump(mode="json", exclude_none=True),
        "source_tool": call["name"],
    }


def _is_booking_location_context(slots: ConversationSlots | None) -> bool:
    if slots is None:
        return False
    pending_intent = str(slots.pending_intent or "").strip()
    goal_type = str(slots.goal_type or "").strip()
    if pending_intent in {"order", "reservation", "stock"}:
        return True
    if goal_type in {"place_order", "store_with_stock"}:
        return True
    return bool(slots.goods_no and slots.ord_qty)


def booking_flow_hint(slots: ConversationSlots | None) -> str | None:
    """Guidance for the quick-reply composer when the user is mid order/booking flow.

    Steps must not skip ahead: store first, then schedule, then order. Without a store
    yet, hinting date/time makes the composer offer 날짜/시간 chips while the answer is
    still asking for a region/store (issue 4).
    """
    if not _is_booking_location_context(slots):
        return None
    if not slots.shop_id:
        return "사용자는 상품·수량은 정했지만 아직 장착 매장을 정하지 않았습니다. 다음 행동으로 지역/매장 선택을 제안하세요. 날짜/시간 선택은 제안하지 마세요."
    if not (slots.requested_cal_day and slots.rsv_hour):
        return "사용자는 상품과 매장까지 정했고 아직 예약 일정(날짜/시간)을 정하지 않았습니다. 다음 행동으로 예약 가능한 일정 확인을 제안하세요."
    return "사용자는 주문/예약을 진행하는 중입니다. 다음 행동으로 주문 진행을 제안하세요."


def _metadata_value(metadata: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, "", []):
            return value
    return None


def _datepick_slot_values(payload: BaseModel, slots: ConversationSlots | None) -> dict[str, Any]:
    metadata = getattr(payload, "metadata", None)
    metadata = metadata if isinstance(metadata, dict) else {}
    values = slots.model_dump(mode="json", exclude_none=True) if slots else {}
    aliases = {
        "goods_no": ("goods_no", "goodsNo", "goodsId"),
        "ord_qty": ("ord_qty", "ordQty", "quantity"),
        "tire_model": ("tire_model", "productName", "product_name"),
        "pending_product_name": ("pending_product_name", "productName", "product_name"),
        "tire_size": ("tire_size", "tireSize"),
        "shop_id": ("shop_id", "shopId"),
        "shop_name": ("shop_name", "shopName", "storeName"),
        "store_name": ("store_name", "storeName", "shopName"),
        "requested_cal_day": ("requested_cal_day", "requestedCalDay"),
        "rsv_hour": ("rsv_hour", "rsvHour"),
        "payment_amount": ("payment_amount", "paymentAmount"),
        "pending_intent": ("pending_intent", "pendingIntent"),
        "goal_type": ("goal_type", "goalType"),
        "car_no": ("car_no", "carNo"),
        "car_lnc_cd": ("car_lnc_cd", "carLncCd"),
    }
    return {
        field: values.get(field) or _metadata_value(metadata, *keys)
        for field, keys in aliases.items()
        if values.get(field) not in (None, "", []) or _metadata_value(metadata, *keys) not in (None, "", [])
    }


def _normalize_datepick_payload(
    payload: BaseModel,
    slots: ConversationSlots | None = None,
) -> None:
    for item in getattr(payload, "dates", None) or []:
        item.date = _format_korean_date(getattr(item, "date", ""))
    metadata = getattr(payload, "metadata", None)
    if not isinstance(metadata, dict):
        payload.metadata = {}
        metadata = payload.metadata

    slot_values = _datepick_slot_values(payload, slots)
    contract_intent = "quick_order_reservation" if _is_booking_location_context(slots) else "store_schedule"
    metadata["domain"] = metadata.get("domain") or "TRANSACTION"
    metadata["cta_action"] = metadata.get("cta_action") or "select_schedule"
    metadata["source_intent"] = metadata.get("source_intent") or contract_intent
    metadata["expected_contract_intent"] = metadata.get("expected_contract_intent") or contract_intent
    metadata["expected_behavior"] = metadata.get("expected_behavior") or "slot_fill"
    metadata["currentStep"] = metadata.get("currentStep") or "select_schedule"
    metadata["current_step"] = metadata.get("current_step") or "select_schedule"
    metadata["slots"] = {key: value for key, value in slot_values.items() if value not in (None, "", [])}
    metadata["ui_action"] = {
        "action_type": "select_schedule",
        "cta_action": "select_schedule",
        "expected_behavior": metadata["expected_behavior"],
        "source_intent": metadata["source_intent"],
        "expected_contract_intent": metadata["expected_contract_intent"],
        "entity_type": "schedule",
        "entity_id": str(slot_values.get("shop_id") or "").strip() or None,
        "entity_label": str(slot_values.get("shop_name") or slot_values.get("store_name") or "").strip() or None,
        "fills_slot": "requested_cal_day,rsv_hour",
        "slots": metadata["slots"],
    }


async def build_rich_data_event(
    answer: str,
    tool_calls: list[dict],
    trace_config: dict | None = None,
    *,
    slots: ConversationSlots | None = None,
    previous_slots: ConversationSlots | None = None,
    allow_selection_cards: bool = True,
) -> dict | None:
    """Return a validated FE data event dict, or None to fall back to quickReply."""
    source = _pick_source(tool_calls, slots, previous_slots)
    if source is None:
        return None
    template_name, template_model, call = source
    if template_name == "listCar":
        return build_listcar_data_event(answer, call, slots)
    if template_name == "preOrder":
        if call.get("name") == "get_final_price_tool":
            return build_final_price_preorder_event(answer, slots, call)
        # K1: the model emitted the order via present_order_preview_tool. Build the card
        # in code from that snapshot (never via the generic LLM template builder — it
        # cannot set isReadyToOrder / metadata.goodsId reliably). None → K2 slot fallback.
        return build_preorder_data_event(
            answer,
            _with_slot_fallback(_parse_tool_output(call.get("output")), slots),
            source="chat_v3_k1_order_preview",
        )
    if template_name == "location":
        if not _is_booking_location_context(slots):
            logger.info("[CHAT_V3] location template skipped — plain store search context")
            return None
        return build_location_data_event(answer, call, slots)
    if template_name == "datepick" and call.get("name") == "get_store_schedule_tool":
        event = _get_store_schedule_datepick_event(answer, call, slots)
        if event is not None:
            return event

    if template_name == "product" and _is_quantity_required_flow(slots):
        logger.info("[CHAT_V3] product template skipped — order flow is asking for quantity")
        return None

    if (
        template_name == "product"
        and _is_booking_location_context(slots)
        and not slots.shop_id
        and _answer_requests_store_selection(answer)
    ):
        logger.info("[CHAT_V3] product template skipped — answer is asking for store/location selection")
        return None

    if _should_gate_info_product_source(
        call,
        allow_selection_cards=allow_selection_cards,
        slots=slots,
        previous_slots=previous_slots,
    ):
        return None
    try:
        wrapper_model = _relevance_wrapper(template_model)
        llm = get_router_llm().with_structured_output(wrapper_model, method="function_calling")
        messages = [
            ("system", TEMPLATE_BUILDER_PROMPT),
            (
                "user",
                f"## 도구: {call['name']}\n## 도구 결과\n{str(call['output'])[:_MAX_TOOL_OUTPUT_CHARS]}\n\n"
                f"## 챗봇 답변\n{answer[:2000]}",
            ),
        ]
        relevance = await llm.ainvoke(messages, config=trace_config) if trace_config else await llm.ainvoke(messages)
        if not relevance.applicable or relevance.payload is None:
            logger.info(
                "[CHAT_V3] rich template '%s' skipped (tool=%s) — answer moved to a different topic",
                template_name,
                call["name"],
            )
            return None
        payload = relevance.payload
        if not getattr(payload, "assistantResponse", ""):
            payload.assistantResponse = answer
        if template_name == "product":
            _normalize_product_payload(payload, str(call["output"]))
            _normalize_product_selection_payload(payload, slots)
        if template_name == "location":
            _normalize_location_payload(payload, str(call["output"]), slots)
            payload.isBookingFlow = _is_booking_location_context(slots)
        elif template_name == "datepick":
            _normalize_datepick_payload(payload, slots)
        return {
            "type": "data",
            "template": template_name,
            "data": payload.model_dump(mode="json", exclude_none=True),
            "source_tool": call["name"],
        }
    except Exception:
        logger.exception("[CHAT_V3] rich template build failed (%s) — falling back to quickReply", template_name)
        return None
