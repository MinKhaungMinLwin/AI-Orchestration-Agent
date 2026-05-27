"""Deterministic intent policy for Transaction stock/store/reservation flows."""

from __future__ import annotations

import re
from typing import Any

from services.tstation.policies.intent_frame import IntentFrame, PolicyDomain
from services.tstation.policies.response_decision import ToolPlan


_SIZE_COMPACT_RE = re.compile(r"\b(\d{3})\s*/?\s*(\d{2})\s*R?\s*(\d{2})\b", re.IGNORECASE)
_QUANTITY_RE = re.compile(r"(\d+)\s*(?:개|본|짝)")
_TODAY_RE = re.compile(r"오늘|당일|지금|바로|당장", re.IGNORECASE)
_STOCK_RE = re.compile(r"재고|오늘\s*서비스|오늘서비스|T\s*바로\s*배송|T바로배송", re.IGNORECASE)
_RESERVATION_RE = re.compile(r"예약|장착|방문|갈게|가고\s*싶|작업", re.IGNORECASE)
_STORE_SCHEDULE_RE = re.compile(
    r"예약\s*가능|작업\s*가능|장착\s*가능|가능한\s*(?:시간|일정|매장)|가능\s*시간|가능\s*일정|스케줄|몇\s*시|시간",
    re.IGNORECASE,
)
_NOON_RE = re.compile(r"12\s*시|점심\s*시간", re.IGNORECASE)
_NEARBY_RE = re.compile(r"근처|주변|가까운|인근", re.IGNORECASE)
_STORE_SUFFIX_RE = re.compile(r"([가-힣A-Za-z0-9]+(?:점|매장))")
_STORE_SEARCH_RE = re.compile(r"매장|지점|티스테이션|더타이어샵|찾아|알려|보여", re.IGNORECASE)
_RESULT_LIMIT_RE = re.compile(r"(\d+)\s*(?:개|곳|군데)\s*(?:만|까지)?")
_KOREAN_RESULT_LIMITS = {
    "한": 1,
    "두": 2,
    "세": 3,
    "네": 4,
    "다섯": 5,
    "여섯": 6,
    "일곱": 7,
    "여덟": 8,
    "아홉": 9,
    "열": 10,
}
_KOREAN_RESULT_LIMIT_RE = re.compile(
    r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(?:개|곳|군데)\s*(?:만|까지)?"
)
_KNOWN_UNVERIFIED_STORE_NAMES = frozenset({"강남점", "티스테이션 강남점"})
_REGION_HINT_RE = re.compile(
    r"(서울|서초|강남|판교|분당|파주|강릉|부산|광교|성남|오목천|동광주|송파|한남|"
    r"청량리|인천|하남|청주|제주|서귀포)"
)
_PRODUCT_HINT_RE = re.compile(
    r"벤투스|ventus|다이나프로|dynapro|키너지|kinergy|아이온|ion|옵티모|optimo|미쉐린|michelin|cc2|"
    r"s\s*fit|g\s*fit|에스핏|지핏|i\*?cept|icept|아이셉트|4s2|dws06|cc7|ps4s|ps\s*as\s*4|psas4|cup\s*2|cup2|p7",
    re.IGNORECASE,
)
_PRICE_OR_COUPON_RE = re.compile(r"가격|할인가|최대\s*혜택|쿠폰|할인", re.IGNORECASE)
_PRODUCT_ALIASES: tuple[tuple[str, str], ...] = (
    ("ventus air s", "Ventus air S"),
    ("벤투스 air s", "Ventus air S"),
    ("벤투스 에어 s", "Ventus air S"),
    ("dynapro hpx", "Dynapro HPX"),
    ("다이나프로 hpx", "Dynapro HPX"),
    ("kinergy ex", "Kinergy EX"),
    ("키너지 ex", "Kinergy EX"),
    ("kinergy st as", "Kinergy ST AS"),
    ("키너지 st as", "Kinergy ST AS"),
    ("ion evo as", "iON evo AS"),
    ("아이온 evo as", "iON evo AS"),
    ("아이온 에보 as", "iON evo AS"),
    ("ion evo", "iON evo"),
    ("아이온 evo", "iON evo"),
    ("아이온 에보", "iON evo"),
    ("s fit as", "S FIT AS"),
    ("s fit", "S FIT"),
    ("에스핏", "S FIT"),
    ("g fit as", "G FIT AS"),
    ("g fit", "G FIT"),
    ("지핏", "G FIT"),
    ("i*cept", "i*cept"),
    ("icept", "i*cept"),
    ("아이셉트", "아이셉트"),
    ("4s2", "4S2"),
    ("dws06", "DWS06"),
    ("cc7", "CC7"),
    ("ps4s", "PS4S"),
    ("ps as 4", "PS AS 4"),
    ("psas4", "PS AS 4"),
    ("cup2", "CUP2"),
    ("cup 2", "CUP2"),
    ("p7", "P7"),
)


def normalize_tire_size(text: str) -> str | None:
    match = _SIZE_COMPACT_RE.search(text or "")
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}R{match.group(3)}"


def extract_quantity(text: str) -> int | None:
    match = _QUANTITY_RE.search(text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def extract_result_limit(text: str) -> int | None:
    match = _RESULT_LIMIT_RE.search(text or "")
    if match:
        try:
            return max(1, min(int(match.group(1)), 10))
        except ValueError:
            return None
    korean_match = _KOREAN_RESULT_LIMIT_RE.search(text or "")
    if korean_match:
        return _KOREAN_RESULT_LIMITS.get(korean_match.group(1))
    return None


def build_transaction_intent_frame(
    last_user_text: str,
    *,
    known_slots: dict[str, Any] | None = None,
) -> IntentFrame:
    """Build a Transaction intent frame from current text and existing slots."""
    text = last_user_text or ""
    slots = dict(known_slots or {})
    explicit_tire_size = normalize_tire_size(text)
    tire_size = explicit_tire_size or slots.get("tire_size")
    quantity = extract_quantity(text) or slots.get("quantity") or slots.get("ord_qty")
    result_limit = extract_result_limit(text) or slots.get("limit")
    goods_no = slots.get("goods_no")
    product_name = slots.get("product_name") or slots.get("pattern_name") or _extract_product_name(text)
    store_name = slots.get("store_name") or _extract_store_name(text)
    region = slots.get("region") or slots.get("place") or _extract_region(text)

    has_product = bool(goods_no or product_name or _PRODUCT_HINT_RE.search(text))
    has_location = bool(region or store_name or slots.get("shop_id") or slots.get("lat") or slots.get("lng"))
    today_requested = bool(_TODAY_RE.search(text))

    entities: dict[str, Any] = {
        "tire_size": tire_size,
        "explicit_tire_size": explicit_tire_size,
        "quantity": quantity,
        "product_in_text": bool(_PRODUCT_HINT_RE.search(text)),
        "store_name": store_name,
        "region": region,
        "nearby": bool(_NEARBY_RE.search(text)),
        "today_requested": today_requested,
        "noon_requested": bool(_NOON_RE.search(text)),
        "result_limit": result_limit,
    }

    if _PRICE_OR_COUPON_RE.search(text):
        intent = "price_or_coupon_check"
        sub_intent = "coupon" if "쿠폰" in text else "price"
    elif _STORE_SCHEDULE_RE.search(text) and (store_name or has_location) and not has_product:
        intent = "store_schedule"
        sub_intent = "store_visit"
    elif _NOON_RE.search(text) and has_location and not has_product:
        intent = "store_schedule"
        sub_intent = "store_visit"
    elif _STORE_SEARCH_RE.search(text) and has_location and not has_product:
        intent = "store_search"
        sub_intent = "nearby" if entities["nearby"] else "region"
    elif (_STOCK_RE.search(text) or today_requested) and has_product:
        intent = "stock_store_search"
        sub_intent = "today_install" if today_requested else "stock"
    elif _RESERVATION_RE.search(text) and has_product:
        intent = "quick_order_reservation"
        sub_intent = "reservation"
    elif _STORE_SCHEDULE_RE.search(text) or _RESERVATION_RE.search(text):
        intent = "store_schedule"
        sub_intent = "store_visit"
    else:
        intent = "transaction_fallback"
        sub_intent = None

    missing_slots = _missing_slots_for_intent(
        intent=intent,
        has_product=has_product,
        goods_no=goods_no,
        tire_size=tire_size,
        quantity=quantity,
        has_location=has_location,
        has_store=bool(store_name or slots.get("shop_id")),
    )

    known = {
        **slots,
        **({"tire_size": tire_size} if tire_size else {}),
        **({"quantity": quantity} if quantity else {}),
        **({"product_name": product_name} if product_name else {}),
        **({"store_name": store_name} if store_name else {}),
        **({"region": region} if region else {}),
        **({"limit": result_limit} if result_limit else {}),
    }
    if store_name and "store_exact_match" not in known and store_name in _KNOWN_UNVERIFIED_STORE_NAMES:
        known["store_exact_match"] = False

    return IntentFrame(
        domain=PolicyDomain.TRANSACTION,
        intent=intent,
        sub_intent=sub_intent,
        entities=entities,
        known_slots=known,
        missing_slots=missing_slots,
        confidence=0.88,
        source="transaction_intent_policy",
    )


def plan_transaction_tools(frame: IntentFrame) -> ToolPlan:
    """Return the preferred Transaction tool family for the intent frame."""
    if frame.intent == "stock_store_search":
        args = _slot_args(frame, "goods_no", "tire_size", "quantity", "region", "store_name")
        if frame.entities.get("today_requested"):
            args["today_only"] = True
        return ToolPlan(
            allowed_tools=("transaction_store_preview_tool", "get_store_inventory_tool", "get_store_list_tool"),
            preferred_tool="transaction_store_preview_tool",
            tool_args_patch=args,
            forbidden_tools=("get_store_schedule_tool", "preorder_with_null_required_fields"),
            required_slots=frame.missing_slots,
            metadata={"response_intent": "stock_store_search"},
        )

    if frame.intent == "store_schedule":
        return ToolPlan(
            allowed_tools=("get_store_list_tool", "get_store_schedule_tool", "get_store_detail_tool"),
            preferred_tool="get_store_schedule_tool",
            tool_args_patch=_slot_args(frame, "store_name", "region"),
            forbidden_tools=("transaction_store_preview_tool",),
            required_slots=frame.missing_slots,
            metadata={"response_intent": "store_schedule"},
        )

    if frame.intent == "store_search":
        args = _slot_args(frame, "store_name", "limit")
        if frame.known_slots.get("region"):
            args["region_code"] = frame.known_slots["region"]
        if frame.entities.get("nearby") and frame.known_slots.get("region"):
            args["place_query"] = frame.known_slots["region"]
        return ToolPlan(
            allowed_tools=("search_stores_tool", "get_store_list_tool", "get_nearby_stores_tool"),
            preferred_tool="search_stores_tool",
            tool_args_patch=args,
            forbidden_tools=("get_store_schedule_tool", "transaction_store_preview_tool"),
            required_slots=frame.missing_slots,
            metadata={"response_intent": "store_search"},
        )

    if frame.intent == "quick_order_reservation":
        return ToolPlan(
            allowed_tools=("transaction_store_preview_tool", "get_multi_store_schedule_tool", "get_store_schedule_tool"),
            preferred_tool="transaction_store_preview_tool",
            tool_args_patch=_slot_args(frame, "goods_no", "tire_size", "quantity", "store_name", "region"),
            forbidden_tools=("store_hours_instead_of_slots", "order_summary_with_null_required_fields"),
            required_slots=frame.missing_slots,
            metadata={"response_intent": "quick_order_reservation"},
        )

    if frame.intent == "price_or_coupon_check":
        return ToolPlan(
            allowed_tools=("get_final_price_tool", "get_my_coupons_tool", "get_coupon_applicable_products_tool"),
            preferred_tool="get_final_price_tool",
            tool_args_patch=_slot_args(frame, "goods_no", "tire_size", "quantity"),
            required_slots=frame.missing_slots,
            metadata={"response_intent": "price_or_coupon_check"},
        )

    return ToolPlan(required_slots=frame.missing_slots, metadata={"response_intent": frame.intent})


def _missing_slots_for_intent(
    *,
    intent: str,
    has_product: bool,
    goods_no: Any,
    tire_size: Any,
    quantity: Any,
    has_location: bool,
    has_store: bool,
) -> tuple[str, ...]:
    missing: list[str] = []
    if intent == "stock_store_search":
        if not has_product:
            missing.append("product")
        if has_product and not goods_no and not tire_size:
            missing.append("tire_size")
        if has_product and not quantity:
            missing.append("quantity")
        if not has_location:
            missing.append("location")
    elif intent == "quick_order_reservation":
        if not (goods_no or tire_size):
            missing.append("tire_size")
        if not quantity:
            missing.append("quantity")
        if not has_store:
            missing.append("store")
    elif intent in ("store_schedule", "store_search"):
        if not has_location:
            missing.append("store")
    return tuple(missing)


def _slot_args(frame: IntentFrame, *keys: str) -> dict[str, Any]:
    args: dict[str, Any] = {}
    for key in keys:
        value = frame.known_slots.get(key)
        if value not in (None, ""):
            args[key] = value
    return args


def _extract_store_name(text: str) -> str | None:
    match = _STORE_SUFFIX_RE.search(text or "")
    if not match:
        return None
    return match.group(1)


def _extract_product_name(text: str) -> str | None:
    normalized = (text or "").casefold()
    for needle, display_name in _PRODUCT_ALIASES:
        if needle.casefold() in normalized:
            return display_name
    return None


def _extract_region(text: str) -> str | None:
    match = _REGION_HINT_RE.search(text or "")
    if not match:
        return None
    return match.group(1)
