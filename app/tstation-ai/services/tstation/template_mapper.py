"""
Code-based template mapper — replaces LLM UI Template Agent for deterministic tool→template conversion.

Maps domain agent tool outputs directly to FE template format without an LLM call.
Handles 9 templates (product, listCar, voucher, qnaComplete, cheapestProduct,
previewYoutube, location, datepick, event); remaining 2 (preOrder, orderComplete)
fall through to the LLM UI Template Agent because they require cross-tool context
(car info + price + store + booking time) that the mapper cannot reconstruct from
a single tool output.
"""
import contextvars
import datetime
import logging
import re
from typing import Any

from services.tstation.common.cta_urls import CTAUrls
from services.tstation.policies.reservation_template_policy import (
    build_datepick_from_preview_payload,
    extract_preview_payload,
    is_other_store_request,
    reservation_sale_min_install_date,
    should_keep_stock_location,
    yyyymmdd_to_korean_date,
)
from services.tstation.policies.response_decision import ResponseDecision, TemplateName
from services.tstation.policies.store_service_gate import unverifiable_store_preference_labels

logger = logging.getLogger(__name__)

# Per-request goal_type, set by the chat service before agent.stream() runs.
# Read by _map_location / _map_product to set isBookingFlow when the active
# goal expects a downstream tool call after the user's card pick.
# ContextVar gives request-scoped propagation through the streaming generator
# without threading goal_type through every signature in the agent → mapper
# chain. None means "no active goal / don't override the tool-based default".
current_goal_type: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_goal_type", default=None
)

# Per-request pending_intent, set by the chat service before agent.stream() runs.
# Used by _map_location to detect order/stock flows that arrive via casual conversation
# rather than the formal goal checklist (where goal_type would already be set).
current_pending_intent: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_pending_intent", default=None
)

# True only for turns where the user explicitly asks for normal tire vs run-flat
# price/additional-cost comparison. Prevents generic cheapest/discount compare
# turns from being hijacked just because the candidate set contains RUNFLAT.
current_runflat_comparison: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "current_runflat_comparison", default=False
)

# True only for turns where the user asks whether a regular/named tire is
# suitable for a vehicle category or why a category-specific tire should be
# used. In that case the answer is a fitment guardrail, not a generic product
# card list that may imply a size/product recommendation without vehicle data.
current_ev_suitability_comparison: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "current_ev_suitability_comparison", default=False
)

# True when the current turn is triggered by a return-visit CTA chip
# ("<지역> 매장 다시 이용하기" / "<지역>점 다시 이용하기"). Forces isBookingFlow=True
# on the resulting location card so the FE click handler routes to /chat (not
# /append), enabling product/quantity continuation after store selection.
current_return_visit_store_flow: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "current_return_visit_store_flow", default=False
)
current_excluded_store_ids: contextvars.ContextVar[set[str]] = contextvars.ContextVar(
    "current_excluded_store_ids", default=set()
)

# True when the current turn asks whether a store is open/closed or bookable on
# a specific date. In that case a single-day `get_store_detail_tool` result
# with slots is the answer, even if there is no product/order booking context.
current_store_date_availability: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "current_store_date_availability", default=False
)
current_user_text: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_text", default=""
)
current_user_preferences_text: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_preferences_text", default=""
)
current_discovery_response_decision: contextvars.ContextVar[ResponseDecision | None] = contextvars.ContextVar(
    "current_discovery_response_decision", default=None
)
current_transaction_response_decision: contextvars.ContextVar[ResponseDecision | None] = contextvars.ContextVar(
    "current_transaction_response_decision", default=None
)

_STOCK_OR_INSTALL_REQUEST_RE = re.compile(
    r"재고|오늘\s*서비스|오늘서비스|오늘\s*장착|당일|지금|바로|당장|장착\s*가능|매장|근처|주변",
    re.IGNORECASE,
)
_POSSESSIVE_VEHICLE_MODEL_RE = re.compile(
    r"(?:내\s*차|내차|내\s*차량|내차량|내)\s+"
    r"(?P<model>[0-9A-Za-z가-힣][0-9A-Za-z가-힣\s._-]{1,24}?)(?="
    r"\s*(?:인데|인데요|이야|야|은|는|이|가|에|에는|으로|로|타이어|추천|하중|적재|짐|호환|맞|가능|$)"
    r")",
    re.IGNORECASE,
)
_POSSESSIVE_VEHICLE_MODEL_STOPWORDS = {
    "내",
    "내차",
    "차",
    "차량",
    "타이어",
    "상품",
    "추천",
    "맞는",
    "하중",
    "적재",
    "짐",
    "호환",
    "가능",
}
_EXPLICIT_VEHICLE_LIST_REQUEST_RE = re.compile(
    r"내\s*차\s*목록|내차\s*목록|내차목록|내\s*차량|내차량|보유\s*차량|보유차량|"
    r"보유차량\s*확인|내\s*등록차|등록차량|등록차|내\s*차\s*보여|내차\s*보여|내차보여|"
    r"내\s*차\s*(?:사이즈|규격|로\s*다시)|내차\s*(?:사이즈|규격|로\s*다시)",
    re.IGNORECASE,
)
_STORE_QUALITY_PREFERENCE_RE = re.compile(
    r"친절|서비스\s*좋|평점\s*좋|별점\s*높|평이\s*좋|추천\s*매장|매장\s*추천|"
    r"방문하기\s*좋|여성\s*(?:운전자|방문|고객)",
    re.IGNORECASE,
)
_EV_SPECIALTY_PREFERENCE_RE = re.compile(
    r"(전기차|(?<![A-Za-z])EV(?![A-Za-z])|electric).{0,12}(전문|특화)|"
    r"(전문|특화).{0,12}(전기차|(?<![A-Za-z])EV(?![A-Za-z])|electric)",
    re.IGNORECASE,
)
_EV_CHARGE_PREFERENCE_RE = re.compile(
    r"충전\s*(?:가능|되는|되나|지원|되는지)?|충전기|전기차\s*충전",
    re.IGNORECASE,
)
_CART_ALREADY_EXISTS_RE = re.compile(r"이미\s*장바구니|장바구니에\s*담겨", re.IGNORECASE)
_EXACT_TIME_REQUEST_RE = re.compile(
    r"(?P<prefix>오전|새벽|오후|저녁|밤)?\s*(?P<hour>\d{1,2})\s*시"
    r"(?!\s*(?:이후|부터|넘어서|후|뒤))"
)

# Goals whose checklist ends in a downstream tool call after a list-pick.
# Card emits in these goals get isBookingFlow=True so the FE click handler
# routes to /chat (advancing the flow) instead of /append (which only shows
# the description bubble and stops).
# product_recommend is intentionally excluded — it has no checklist; clicking
# a recommended product should still surface the rich description.
_GOAL_BOOKING_FOLLOWUP = frozenset({
    "store_with_stock",
    "place_order",
    "price_inquiry",
})

_DISCOVERY_POLICY_QUICKREPLY_CHIPS = [
    {"label": "보유차량 중 선택", "domain": "DISCOVERY"},
    {"label": "차번+이름으로 검색", "domain": "DISCOVERY"},
    {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
]
_DISCOVERY_SIZED_PRODUCT_CHIPS = [
    {"label": "가격 확인", "domain": "TRANSACTION"},
    {"label": "재고/장착 매장 확인", "domain": "TRANSACTION"},
    {"label": "구매하기", "domain": "TRANSACTION"},
]
_VEHICLE_PLATE_RE = re.compile(r"\d{2,3}\s*[가-힣]\s*\d{4}")
_VEHICLE_OWNER_RE = re.compile(
    r"(?:\d{2,3}\s*[가-힣]\s*\d{4}\s+[가-힣]{2,4}|[가-힣]{2,4}\s+\d{2,3}\s*[가-힣]\s*\d{4})"
)
_DISCOVERY_RESTOCK_CHIPS = [
    {"label": "지역 입력", "domain": "TRANSACTION"},
    {"label": "매장명 입력", "domain": "TRANSACTION"},
    {"label": "대체상품 찾기", "domain": "DISCOVERY"},
]
_BEST_SELLER_PERIOD_DISPLAY: dict[str, str] = {
    "day": "오늘",
    "week": "이번 주",
    "month": "이번 달",
    "3months": "최근 3개월",
}
_RCMD_TYPE_DISPLAY: dict[str, str] = {
    "performance": "퍼포먼스",
    "sound_absorber": "흡음재",
    "snow": "겨울용",
    "all_weather": "올웨더",
    "value": "가성비",
    "family": "승차감",
    "ev": "전기차용",
}

_INTERNAL_POLICY_TEXT_RE = re.compile(
    r"기준으로\s*답하고|이전\s*추천\s*결과로\s*대체|"
    r"재확인하지\s*말고|누락\s*정보만|확정된\s*슬롯|"
    r"도구\s*결과\s*범위|assistant_guidance|forbidden_behaviors|"
    r"response_shape_key|required_slots|instruction_to_agent",
    re.IGNORECASE,
)
_GENERIC_PRODUCT_RESPONSE_RE = re.compile(
    r"(추천\s*상품\s*\d*개?.*선택해\s*주세요|추천\s*상품을\s*확인했어요|상품을\s*검색했습니다)",
    re.IGNORECASE,
)
_BEST_SELLER_COUNT_QUERY_RE = re.compile(r"몇\s*개|몇개|판매량|팔렸", re.IGNORECASE)
_DEMOGRAPHIC_AGE_GENDER_RE = re.compile(
    r"10대|20대|30대|40대|50대|60대|연령대|성별|남성|여성|남자|여자",
    re.IGNORECASE,
)
_DEMOGRAPHIC_PREFERENCE_RE = re.compile(r"선호|좋아하는|많이\s*사는|인기|추천", re.IGNORECASE)
_DEMOGRAPHIC_CAVEAT_TEXT = "특정 나이대나 성별 기준으로 추천드리기는 어렵지만, 최근 인기 상품 위주로 안내드릴게요. "


def _current_turn_user_text() -> str:
    text = current_user_text.get() or ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else text.strip()


def sanitize_user_facing_response(text: str, fallback: str | None = None) -> str:
    """Replace internal policy/procedure text before it reaches the user."""
    cleaned = (text or "").strip()
    if cleaned and not _INTERNAL_POLICY_TEXT_RE.search(cleaned):
        return cleaned
    if fallback is not None:
        return fallback
    return _product_search_policy_fallback_response()


def _is_goal_booking_followup() -> bool:
    """Read the request-scoped goal_type and decide if isBookingFlow should be
    forced True. Returns False when no goal is set (preserves legacy behavior).
    """
    return current_goal_type.get() in _GOAL_BOOKING_FOLLOWUP


def _single_product_transaction_handoff_event(items: list[dict], metadata: list[dict]) -> dict | None:
    if len(items) != 1 or len(metadata) != 1 or not _is_goal_booking_followup():
        return None
    goal_type = current_goal_type.get()
    pending_intent = current_pending_intent.get()
    if goal_type == "price_inquiry" or pending_intent == "price":
        action_text = "가격 확인을 이어갈게요."
    elif goal_type == "store_with_stock" or pending_intent == "stock":
        action_text = "장착 가능 매장 확인을 이어갈게요."
    else:
        action_text = "오늘서비스 구매 진행을 이어갈게요."
    title = str(items[0].get("title") or items[0].get("titleProductName") or "상품").strip()
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": f"{title} 상품 확인했어요. {action_text}",
            "quickReplies": [],
            "predictedDomains": ["TRANSACTION"],
            "metadata": metadata[0],
        },
        "assistant_response_source": "code_single_product_transaction_handoff",
        "nextAction": {"type": "continue", "domain": "transaction"},
    }

# ── Domain tool → FE template mapping ──────────────────────────────────────────
_TOOL_TEMPLATE_MAP: dict[str, str] = {
    # product
    "search_product_tool": "product",
    "get_newest_products_tool": "product",
    "get_products_recommendations_tool": "product",
    "get_best_selling_products_tool": "product",
    # listCar
    "get_my_cars_tool": "listCar",
    "get_user_vehicles_tool": "listCar",
    # voucher
    "get_my_coupons_tool": "voucher",
    # qnaComplete
    "transfer_to_qna_tool": "qnaComplete",
    # cheapestProduct
    "compare_discount_tool": "cheapestProduct",
    "get_cheapest_price_tool": "cheapestProduct",
    # event — FE에 event 렌더러 없음, LLM fallback
    # "get_events_tool": "event",
    # previewYoutube
    "search_youtube_video_tool": "previewYoutube",
    # location
    "search_stores_tool": "location",
    "search_stores_complex_tool": "location",
    "get_store_list_tool": "location",
    "get_nearby_stores_tool": "location",
    "transaction_store_preview_tool": "location",
    "get_stores_with_time_filter_tool": "location",
    "get_favorite_stores_tool": "location",
    # datepick
    "get_store_schedule_tool": "datepick",
    # orderComplete (cart-save / quick-order — terminal step in transaction flow)
    "save_to_cart_tool": "orderComplete",
    "quick_order_tool": "orderComplete",
}

_DISCOVERY_POLICY_SOURCE_TOOLS = frozenset({
    "search_product_tool",
    "get_newest_products_tool",
    "get_products_recommendations_tool",
    "get_best_selling_products_tool",
})

_DISCOVERY_POLICY_BLOCKING_TOOLS = frozenset({
    "search_stores_tool",
    "search_stores_complex_tool",
    "get_store_list_tool",
    "get_nearby_stores_tool",
    "get_favorite_stores_tool",
    "get_stores_with_time_filter_tool",
    "get_store_detail_tool",
    "transaction_store_preview_tool",
    "get_store_inventory_tool",
    "get_logistics_inventory_tool",
    "get_store_schedule_tool",
    "get_multi_store_schedule_tool",
    "get_orders_of_user_tool",
    "get_order_detail_tool",
    "get_my_coupons_tool",
    "get_available_coupons_tool",
})

# Booking-flow signals: tools that imply the customer is mid-purchase, not just
# browsing for store info. Used by `_map_location` to set `isBookingFlow`.
# Notably excludes `get_store_detail_tool` — Flow 5 General now calls it as a
# description-enrichment companion to `get_store_list_tool` (info-only intent),
# so its presence is not a booking signal. Date-specific schedule/detail flows
# either trip the schedule mapper first (datepick) or are guarded out earlier.
_BOOKING_SIGNAL_TOOLS = frozenset({
    "get_store_inventory_tool",
    "get_logistics_inventory_tool",
    "get_store_schedule_tool",
    "get_multi_store_schedule_tool",
    "get_final_price_tool",
    "save_to_cart_tool",
    "quick_order_tool",
    "transaction_store_preview_tool",
})

_MY_COUPON_LINK = {
    "pc": CTAUrls.MY_COUPON_LIST_PC,
    "mobile": CTAUrls.MY_COUPON_LIST_MOBILE,
}

_CNSL_TYPE_MAP = {
    "10002": "상품문의",
    "10006": "주문/결제/배송",
    "10010": "반품/교환/환불",
    "10013": "제공서비스/이벤트/혜택",
    "10017": "회원",
    "10019": "기타",
    "10025": "가맹점제휴문의",
    "10034": "이력서접수",
}


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _unwrap(entry: dict) -> dict | list:
    """Unwrap API response: {status: success, data: {actual}} → actual."""
    raw = entry.get("data", {})
    if isinstance(raw, dict) and raw.get("status") == "success":
        return raw.get("data", raw)
    return raw


def _get_str(d: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def _get_num(d: dict, *keys: str, default: int | float = 0) -> int | float:
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return type(default)(v)
            except (ValueError, TypeError):
                pass
    return default


def _normalize_vehicle_key(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def _vehicle_aliases(row: dict) -> set[str]:
    aliases: set[str] = set()
    for key in ("car_nm", "car_model_det", "car_engine", "ver_opt_choc", "car_maker"):
        normalized = _normalize_vehicle_key(row.get(key))
        if len(normalized) >= 2:
            aliases.add(normalized)
    for key in ("car_nm", "car_model_det", "car_engine"):
        value = str(row.get(key) or "")
        for token in re.findall(r"[A-Za-z가-힣]*\d+[A-Za-z가-힣]*|[A-Za-z]{2,}|[가-힣]{2,}", value):
            normalized = _normalize_vehicle_key(token)
            if len(normalized) >= 2:
                aliases.add(normalized)
    maker = _normalize_vehicle_key(row.get("car_maker"))
    model = _normalize_vehicle_key(row.get("car_model_det") or row.get("car_nm"))
    if maker and model:
        aliases.add(f"{maker}{model}")
    return aliases


def _possessive_vehicle_model_mentions(user_text: str) -> list[str]:
    mentions: list[str] = []
    for match in _POSSESSIVE_VEHICLE_MODEL_RE.finditer(user_text or ""):
        raw = re.sub(r"\s+", " ", match.group("model") or "").strip(" ._-")
        normalized = _normalize_vehicle_key(raw)
        if len(normalized) < 2 or normalized in _POSSESSIVE_VEHICLE_MODEL_STOPWORDS:
            continue
        mentions.append(normalized)
    return mentions


def _should_suppress_listcar_for_possessive_model_mismatch(rows: list[dict]) -> bool:
    user_text = current_user_text.get() or ""
    if _EXPLICIT_VEHICLE_LIST_REQUEST_RE.search(user_text):
        return False
    requested_models = _possessive_vehicle_model_mentions(user_text)
    if not requested_models or not rows:
        return False
    for row in rows:
        aliases = _vehicle_aliases(row)
        for requested in requested_models:
            if any(alias and (requested in alias or alias in requested) for alias in aliases):
                return False
    return True


def _normalize_brand_name(value: str) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def _inventory_shop_ids(raw_inventory: object, key: str) -> set[str]:
    """Extract shop IDs from inventory arrays such as todayShopArray/tnaShopArray."""
    if not isinstance(raw_inventory, dict):
        return set()
    rows = raw_inventory.get(key)
    if not isinstance(rows, list):
        return set()
    ids: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            shop_id = _get_str(row, "shopId", "shop_id")
            if shop_id:
                ids.add(shop_id)
    return ids


def _preview_location_assistant_response(tier: str, region: str, item_count: int) -> str | None:
    """Build preview-specific location copy from resolved inventory/schedule tier."""
    tier_normalized = (tier or "").strip().lower()
    if not tier_normalized:
        return None
    count_text = f"{item_count}곳"
    region_prefix = f"{region}에서 " if region else ""
    today_requested = bool(re.search(r"오늘|당일|지금|바로|당장", current_user_text.get() or ""))
    if tier_normalized == "logistics_only":
        if today_requested:
            return (
                f"{region_prefix}오늘 바로 장착 가능한 매장은 없어요. "
                f"물류 배송 후 장착 가능한 매장 {count_text}입니다. 원하시는 매장을 선택해 주세요."
            )
        return f"{region_prefix}물류 배송 후 장착 가능한 매장 {count_text}입니다. 원하시는 매장을 선택해 주세요."
    if tier_normalized in {"today_only", "tna_only"}:
        return f"{region_prefix}오늘 장착 가능한 매장 {count_text}입니다. 원하시는 매장을 선택해 주세요."
    return None


def _kst_today_yyyymmdd() -> str:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y%m%d")


def _preview_schedule_stores_by_shop_id(raw: dict) -> dict[str, dict]:
    schedule = raw.get("schedule") if isinstance(raw.get("schedule"), dict) else {}
    schedule_stores = schedule.get("stores") if isinstance(schedule, dict) else None
    if not isinstance(schedule_stores, list):
        return {}
    stores_by_shop_id: dict[str, dict] = {}
    for store in schedule_stores:
        if not isinstance(store, dict):
            continue
        shop_id = _get_str(store, "shop_id")
        if shop_id:
            stores_by_shop_id[shop_id] = store
    return stores_by_shop_id


def _store_has_bookable_slot_on_day(store: dict, cal_day: str) -> bool:
    slots = store.get("slots")
    if not isinstance(slots, list):
        return False
    for slot in slots:
        if not isinstance(slot, dict) or _get_str(slot, "cal_day") != cal_day:
            continue
        hour = _parse_tm_to_hour(_get_str(slot, "tm"))
        if hour is not None and _is_bookable_hour(hour):
            return True
    return False


def _today_service_context(assistant_text: str = "") -> bool:
    text = "\n".join(part for part in [current_user_text.get() or "", assistant_text or ""] if part)
    return bool(_TODAY_SERVICE_DATEPICK_RE.search(text))


def _earliest_preview_schedule_label(raw: dict) -> str:
    best_day = ""
    for store in _preview_schedule_stores_by_shop_id(raw).values():
        slots = store.get("slots")
        if not isinstance(slots, list):
            continue
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            cal_day = _get_str(slot, "cal_day")
            hour = _parse_tm_to_hour(_get_str(slot, "tm"))
            if cal_day and hour is not None and _is_bookable_hour(hour) and (not best_day or cal_day < best_day):
                best_day = cal_day
    return yyyymmdd_to_korean_date(best_day) if best_day else ""


def _preview_schedule_starts_after_today(raw: dict) -> bool:
    best_day = ""
    for store in _preview_schedule_stores_by_shop_id(raw).values():
        slots = store.get("slots")
        if not isinstance(slots, list):
            continue
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            cal_day = _get_str(slot, "cal_day")
            hour = _parse_tm_to_hour(_get_str(slot, "tm"))
            if cal_day and hour is not None and _is_bookable_hour(hour) and (not best_day or cal_day < best_day):
                best_day = cal_day
    return bool(best_day and best_day > _kst_today_yyyymmdd())


def _same_turn_inventory_has_no_stock(tool_data_list: list[dict]) -> bool:
    """True when get_store_inventory_tool ran this turn and found no eligible shops."""
    labels = _same_turn_inventory_stock_labels(tool_data_list)
    return labels == {}


def _same_turn_inventory_stock_labels(tool_data_list: list[dict]) -> dict[str, str] | None:
    """Return same-turn stock labels by shop_id, or None if no inventory ran."""
    inventory_entries = _find_entries(tool_data_list, "get_store_inventory_tool")
    if not inventory_entries:
        return None
    raw = _unwrap(inventory_entries[-1])
    if not isinstance(raw, dict):
        return None
    labels: dict[str, str] = {}
    for sid in _inventory_shop_ids(raw, "todayShopArray"):
        labels[sid] = "매장재고"
    for sid in _inventory_shop_ids(raw, "tnaShopArray"):
        labels.setdefault(sid, "T바로배송")
    return labels


def _same_turn_logistics_schedule_has_slots(tool_data_list: list[dict]) -> bool:
    schedule_entries = _find_entries(tool_data_list, "get_store_schedule_tool")
    if not schedule_entries:
        return False
    raw = _unwrap(schedule_entries[-1])
    if not isinstance(raw, dict):
        return False
    if _get_str(raw, "mode").lower() != "logistics_only":
        return False
    slots = raw.get("slots")
    return isinstance(slots, list) and any(isinstance(slot, dict) for slot in slots)


def _map_inventory_stock_result(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Map explicit store-inventory checks when no eligible stock exists."""
    labels = _same_turn_inventory_stock_labels(tool_data_list)
    if labels is None or labels:
        return None
    if _same_turn_logistics_schedule_has_slots(tool_data_list):
        return None
    if current_pending_intent.get() != "stock" and current_goal_type.get() != "store_with_stock":
        return None
    short = (assistant_text or "").strip()
    if not short or len(short) > 160 or not re.search(r"없|불가|확인되지|품절|부족", short):
        short = "요청하신 조건으로 바로 장착 가능한 매장 재고가 확인되지 않았어요. 다른 매장이나 날짜로 다시 확인해 드릴게요."
    return {
        "type": "data",
        "template": "quickReply",
        "assistant_response_source": "code_mapper",
        "data": {
            "assistantResponse": short,
            "quickReplies": [
                {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
                {"label": "다른 날짜 확인", "domain": "TRANSACTION"},
                {"label": "대체상품 찾기", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["TRANSACTION", "DISCOVERY"],
        },
    }


def _preview_has_no_fulfillment(raw: dict) -> bool:
    """True when a product/store preview found no stock, logistics, or schedule path."""
    logistics = raw.get("logistics") if isinstance(raw.get("logistics"), dict) else {}
    try:
        logistics_qty = int(logistics.get("logistics_qty") or 0)
    except (TypeError, ValueError):
        logistics_qty = 0

    inventory = raw.get("inventory") if isinstance(raw.get("inventory"), dict) else {}
    today_ids = _inventory_shop_ids(inventory, "todayShopArray")
    tna_ids = _inventory_shop_ids(inventory, "tnaShopArray")

    schedule = raw.get("schedule") if isinstance(raw.get("schedule"), dict) else {}
    schedule_stores = schedule.get("stores") if isinstance(schedule, dict) else None
    schedule_empty = (
        _get_str(schedule, "tier").lower() == "none"
        or (isinstance(schedule_stores, list) and not schedule_stores)
    )
    return logistics_qty <= 0 and not today_ids and not tna_ids and schedule_empty


def _map_preview_no_fulfillment_quickreply(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Block product order/stock previews from falling through to a general store schedule."""
    for entry in reversed(_find_entries(tool_data_list, "transaction_store_preview_tool")):
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        raw = _unwrap(entry)
        if not isinstance(args, dict) or not isinstance(raw, dict):
            continue
        if not args.get("goods_no"):
            continue
        stores = raw.get("stores")
        if not isinstance(stores, list) or not stores:
            continue
        if not _preview_has_no_fulfillment(raw):
            continue

        region = _get_str(args, "region_code") or _get_str(args, "store_nm")
        prefix = f"{region} 기준으로 " if region else ""
        short = (assistant_text or "").strip()
        if (
            not short
            or len(short) > 160
            or "```" in short
            or re.search(r"선택|예약 가능|주문 가능|장착 가능 여부가 확인|확인했어요", short)
            or not re.search(r"없|불가|확인되지|품절|부족|재고", short)
        ):
            short = (
                f"{prefix}요청하신 상품과 수량으로 바로 장착 가능한 재고가 확인되지 않았어요. "
                "다른 지역이나 다른 상품으로 다시 확인해 드릴게요."
            )
        return {
            "type": "data",
            "template": "quickReply",
            "assistant_response_source": "code_mapper",
            "data": {
                "assistantResponse": short,
                "quickReplies": [
                    {"label": "다른 지역 찾기", "domain": "TRANSACTION"},
                    {"label": "다른 상품 보기", "domain": "DISCOVERY"},
                ],
                "predictedDomains": ["TRANSACTION", "DISCOVERY"],
            },
        }
    return None


def _map_store_validation_quickreply(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Render deterministic quickReply for store-name validation guards.

    These tool responses are follow-up pivots, not generic prose:
      - exact-branch mismatch -> confirm a candidate store
      - no exact match -> confirm a fallback region
    Persist the candidate metadata so the next user chip can reuse the previous
    list directly without re-running store-name search.
    """
    for entry in reversed(_find_entries(tool_data_list, "transaction_store_preview_tool", "get_store_list_tool")):
        raw = _unwrap(entry)
        if not isinstance(raw, dict) or not raw.get("validation_message"):
            continue
        if not raw.get("instruction_to_agent"):
            continue

        quick_replies: list[dict] = []
        metadata: dict[str, object] = {"storeConfirmation": {}}
        confirmation_meta = metadata["storeConfirmation"]
        assert isinstance(confirmation_meta, dict)

        candidate_stores = raw.get("candidate_stores")
        if isinstance(candidate_stores, list) and candidate_stores:
            chips: list[dict] = []
            stored_candidates: list[dict] = []
            for candidate in candidate_stores:
                if not isinstance(candidate, dict):
                    continue
                shop_name = _get_str(candidate, "shop_nm", "shopName")
                shop_id = _get_str(candidate, "shop_id", "shopId")
                if not shop_name:
                    continue
                stored_candidate = {"shopName": shop_name}
                if shop_id:
                    stored_candidate["shopId"] = shop_id
                stored_candidates.append(stored_candidate)
                if len(candidate_stores) > 1:
                    chips.append({"label": shop_name, "domain": "TRANSACTION"})
            if stored_candidates:
                confirmation_meta["candidateStores"] = stored_candidates
            if len(stored_candidates) == 1:
                quick_replies = [
                    {"label": "네, 맞아요", "domain": "TRANSACTION"},
                    {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
                ]
            elif chips:
                quick_replies = chips + [{"label": "다른 매장 찾기", "domain": "TRANSACTION"}]

        region_candidates = raw.get("region_candidates")
        if not quick_replies and isinstance(region_candidates, list) and region_candidates:
            labels: list[dict] = []
            stored_regions: list[str] = []
            for region in region_candidates:
                region_text = str(region or "").strip()
                if not region_text:
                    continue
                stored_regions.append(region_text)
                labels.append({"label": f"{region_text} 지역 검색", "domain": "TRANSACTION"})
            if stored_regions:
                confirmation_meta["regionCandidates"] = stored_regions
                quick_replies = labels + [{"label": "다른 매장 찾기", "domain": "TRANSACTION"}]

        suggested_region = _get_str(raw, "suggested_region")
        if not quick_replies and suggested_region:
            confirmation_meta["suggestedRegion"] = suggested_region
            quick_replies = [
                {"label": f"네, {suggested_region} 지역으로 검색", "domain": "TRANSACTION"},
                {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
            ]

        if not quick_replies:
            continue

        return {
            "type": "data",
            "template": "quickReply",
            "assistant_response_source": "code_mapper",
            "data": {
                "assistantResponse": _get_str(raw, "validation_message") or assistant_text,
                "quickReplies": quick_replies,
                "predictedDomains": ["TRANSACTION"],
                "metadata": metadata,
            },
        }
    return None


def _find_entries(tool_data_list: list[dict], *tool_names: str) -> list[dict]:
    """Filter accumulated_tool_data by tool name; skip error-status entries.

    Tool wrappers emit `{"status": "error", "http_status": ..., ...}` on failure
    (e.g. BE 404). Without this filter, downstream mappers fall through to
    `_unwrap` which returns the error dict as-is, and the mapper produces a
    placeholder row with all-empty fields — visible to the user as a blank
    card next to real results.
    """
    out: list[dict] = []
    for e in tool_data_list:
        if e.get("tool", "") not in tool_names:
            continue
        data = e.get("data")
        if isinstance(data, dict) and data.get("status") == "error":
            continue
        out.append(e)
    return out


def _same_turn_reservation_sale_min_install_date(tool_data_list: list[dict], shop_id: str) -> str | None:
    """Return rsv_install_date when same-turn preview says this shop is reservation-sale fallback only."""
    if not shop_id:
        return None
    for entry in reversed(_find_entries(tool_data_list, "transaction_store_preview_tool")):
        raw = entry.get("data")
        if not isinstance(raw, dict):
            continue
        preview_payload = extract_preview_payload(raw)
        if not isinstance(preview_payload, dict):
            continue
        min_install_date = reservation_sale_min_install_date(preview_payload, shop_id)
        if min_install_date:
            return min_install_date
    return None


def _yyyymmdd_to_plain_korean_date(s: str) -> str:
    try:
        dt = datetime.datetime.strptime(s, "%Y%m%d")
    except (TypeError, ValueError):
        return s
    return f"{dt.year}년 {dt.month}월 {dt.day}일"


def _reservation_sale_date_quickreply(min_install_date: str) -> dict:
    install_date = _yyyymmdd_to_plain_korean_date(min_install_date)
    return {
        "type": "data",
        "template": "quickReply",
        "assistant_response_source": "code_mapper_reservation_sale_date_guard",
        "data": {
            "assistantResponse": f"해당 상품은 {install_date} 이후 장착 가능합니다. 다른 날짜를 선택해 주세요.",
            "quickReplies": [{"label": "다른 날짜 확인", "domain": "TRANSACTION"}],
            "predictedDomains": ["TRANSACTION"],
        },
    }


def _unverifiable_store_preference_labels(text: str) -> list[str]:
    return unverifiable_store_preference_labels(text)


def _maybe_prepend_unverifiable_store_guidance(short: str) -> str:
    preference_text = (current_user_preferences_text.get() or "").strip()
    labels = _unverifiable_store_preference_labels(preference_text)
    if not labels:
        return short
    joined = "/".join(labels[:3])
    guidance = (
        f"요청하신 조건 중 '{joined}' 같은 항목은 시스템에서 바로 확인이 어려워요. "
        "매장 목록을 먼저 안내드릴게요. 원하시는 매장을 고르시면 연락처와 기본 정보를 함께 확인하실 수 있어요.\n\n"
    )
    if (
        "시스템에서" in short
        and "확인" in short
        and "어려" in short
        and any(label in short for label in labels)
    ):
        return short
    return f"{guidance}{short}"


def _requested_store_specialty_filters(text: str) -> tuple[bool, bool]:
    if not text:
        return False, False
    return bool(_EV_SPECIALTY_PREFERENCE_RE.search(text)), bool(_EV_CHARGE_PREFERENCE_RE.search(text))


def _preview_tool_requires_location(tool_data_list: list[dict]) -> bool:
    for entry in reversed(_find_entries(tool_data_list, "transaction_store_preview_tool")):
        raw = _unwrap(entry)
        if not isinstance(raw, dict):
            continue
        stores = raw.get("stores")
        if not isinstance(stores, list) or not stores:
            continue
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        schedule = raw.get("schedule") if isinstance(raw.get("schedule"), dict) else {}
        candidate_ids = schedule.get("candidate_shop_ids") or raw.get("candidate_shop_ids") or []
        if isinstance(args, dict) and args.get("store_nm") and len(stores) == 1 and candidate_ids:
            continue
        instruction = _get_str(raw, "instruction_to_agent")
        if not instruction or "location" in instruction.lower() or "stores" in instruction.lower():
            return True
    return False


def _store_quality_preference_response_text(tool_data_list: list[dict], count: int) -> str | None:
    preference_text = (current_user_preferences_text.get() or "").strip()
    if not preference_text or not _STORE_QUALITY_PREFERENCE_RE.search(preference_text):
        return None
    requested_region = ""
    sort_by = ""
    for entry in _find_entries(
        tool_data_list,
        "search_stores_tool",
        "search_stores_complex_tool",
        "get_store_list_tool",
        "get_nearby_stores_tool",
    ):
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        if not isinstance(args, dict):
            continue
        requested_region = _get_str(args, "place_query") or _get_str(args, "region_code") or _get_str(args, "store_nm")
        sort_by = _get_str(args, "sort_by")
        if requested_region or sort_by:
            break
    region_prefix = f"{requested_region} 지역에서 " if requested_region else ""
    basis = "평점 기준으로 " if sort_by == "rating" else ""
    return f"{region_prefix}{basis}추천 가능한 매장 {count}곳을 안내드립니다. 원하시는 매장을 선택해 주세요."


def _store_specialty_labels(*, is_ev_specialty: bool, is_ev_charge_available: bool) -> list[str]:
    labels: list[str] = []
    if is_ev_specialty:
        labels.append("전기차 특화점")
    if is_ev_charge_available:
        labels.append("충전 가능")
    return labels


def _store_specialty_response_text(region: str, count: int, *, require_ev_specialty: bool, require_ev_charge: bool) -> str:
    if require_ev_specialty and require_ev_charge:
        condition = "전기차 특화점이면서 충전 가능한"
    elif require_ev_specialty:
        condition = "전기차 특화"
    elif require_ev_charge:
        condition = "충전 가능한"
    else:
        return ""
    if region:
        return f"{region} 주변에서 {condition} 매장 {count}곳을 찾았어요. 원하시는 매장을 선택해 주세요."
    return f"{condition} 매장 {count}곳을 찾았어요. 원하시는 매장을 선택해 주세요."


def _store_specialty_no_match_quickreply(region: str, *, require_ev_specialty: bool, require_ev_charge: bool) -> dict:
    if require_ev_specialty and require_ev_charge:
        condition = "전기차 특화점이면서 충전 가능한"
    elif require_ev_specialty:
        condition = "전기차 특화"
    else:
        condition = "충전 가능한"
    region_prefix = f"{region} 주변 " if region else ""
    return {
        "type": "data",
        "template": "quickReply",
        "assistant_response_source": "code_mapper",
        "data": {
            "assistantResponse": (
                f"{region_prefix}매장을 찾았지만, 요청하신 {condition} 조건에 맞는 매장은 현재 확인되지 않았어요."
            ),
            "quickReplies": [
                {"label": "다른 지역 찾기", "domain": "TRANSACTION"},
                {"label": "다른 조건으로 찾기", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["TRANSACTION"],
        },
    }


def _has_tool_entry(tool_data_list: list[dict], *tool_names: str) -> bool:
    """Return whether a tool ran, including error-status results."""
    return any(e.get("tool", "") in tool_names for e in tool_data_list)


def _format_tire_size_for_user(value: object) -> str:
    raw = str(value or "").strip().upper()
    if re.fullmatch(r"\d{7,8}", raw):
        return f"{raw[:3]}/{raw[3:5]}R{raw[5:]}"
    return raw


def _map_vehicle_recommendation_no_results(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Avoid falling back to listCar after an identified-vehicle recommendation found no items."""
    if not _has_tool_entry(tool_data_list, "get_my_cars_tool", "get_user_vehicles_tool"):
        return None
    recommendation_entries = [
        e for e in tool_data_list if e.get("tool") == "get_products_recommendations_tool"
    ]
    if not recommendation_entries:
        return None

    has_items = False
    latest_size = ""
    for entry in recommendation_entries:
        args = entry.get("args") or entry.get("input") or {}
        latest_size = str(args.get("tire_size") or latest_size or "")
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if isinstance(rows, list) and any(isinstance(row, dict) for row in rows):
            has_items = True
            break
    if has_items:
        return None

    size_text = _format_tire_size_for_user(latest_size)
    if size_text:
        response = f"확인된 차량 규격 **{size_text}** 기준으로 현재 추천 가능한 상품을 찾지 못했어요."
    else:
        response = "확인된 차량 기준으로 현재 추천 가능한 상품을 찾지 못했어요."
    response += "\n\n다른 조건으로 다시 찾아보거나, 타이어 사이즈를 직접 입력해 주세요."
    return _build_event(
        "quickReply",
        {
            "assistantResponse": response,
            "quickReplies": [
                {"label": "다른 조건으로 찾기", "domain": "DISCOVERY"},
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
                {"label": "타이어 추천 받기", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
        },
        response,
        0,
    )


def _map_recommendation_no_results(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Normalize empty recommendation results into a deterministic no-result quickReply.

    Without this guard, the LLM may fall back to explanatory prose from the
    previous turn ("RR/회전저항으로 확인해요") even though the recommendation
    tool already ran and returned 0 items. When recommendation lookup fails, the
    user needs a concrete next-step response, not another concept explanation.
    """
    recommendation_entries = [
        e for e in tool_data_list if e.get("tool") == "get_products_recommendations_tool"
    ]
    if not recommendation_entries:
        return None

    latest_args: dict[str, Any] = {}
    has_items = False
    for entry in recommendation_entries:
        args = entry.get("args") or entry.get("input") or {}
        if isinstance(args, dict):
            latest_args = args
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if isinstance(rows, list) and any(isinstance(row, dict) for row in rows):
            has_items = True
            break
    if has_items:
        return None

    tire_size = _format_tire_size_for_user(latest_args.get("tire_size") or "")
    rcmd_type = str(latest_args.get("rcmd_type") or "").strip().lower()
    if tire_size:
        response = f"확인된 조건과 규격 **{tire_size}** 기준으로 현재 추천 가능한 상품을 찾지 못했어요."
    else:
        response = "확인된 조건으로 현재 추천 가능한 상품을 찾지 못했어요."

    if rcmd_type == "value":
        response += "\n\n예산 조건을 조금 넓혀 보시거나, 다른 성향으로 다시 추천해 드릴게요."
    else:
        response += "\n\n다른 조건으로 다시 찾아보거나, 타이어 사이즈를 직접 입력해 주세요."

    return _build_event(
        "quickReply",
        {
            "assistantResponse": response,
            "quickReplies": [
                {"label": "다시 검색", "domain": "DISCOVERY"},
                {"label": "다른 조건으로 찾기", "domain": "DISCOVERY"},
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
        },
        response,
        0,
    )


_LOCATION_SELECTION_TEXT_RE = re.compile(
    r"원하시는\s*매장|매장을?\s*선택|선택해\s*주세요|골라\s*주세요|"
    r"매장\s*\d+\s*곳",
    re.IGNORECASE,
)


def _looks_like_location_selection_prompt(text: str | None) -> bool:
    return bool(text and _LOCATION_SELECTION_TEXT_RE.search(text))


def _normalize_time(s: str) -> str:
    """Normalize a BE business-hours value to ``HH:MM``.

    The store endpoints return inconsistent shapes — sometimes ``"09:00"``,
    sometimes just ``"09"`` — which produces awkward mixed output like
    ``평일 09~19 / 토요일 09:00~16:00``. Pad single-hour, ``"H"`` (e.g. ``"9"``)
    and ``"HHMM"`` (e.g. ``"0930"``) shapes; pass through anything else
    unchanged so we never silently mangle a value we don't recognise.
    """
    s = (s or "").strip()
    if not s:
        return s
    if ":" in s:
        h, _, m = s.partition(":")
        try:
            return f"{int(h):02d}:{int(m):02d}"
        except ValueError:
            return s
    if s.isdigit():
        try:
            if len(s) <= 2:
                return f"{int(s):02d}:00"
            if len(s) == 4:
                return f"{int(s[:2]):02d}:{int(s[2:]):02d}"
        except ValueError:
            return s
    return s


def _format_phone(s: str) -> str:
    """Format a Korean landline/mobile phone number for display.

    BE returns ``tel_no`` as raw digits (e.g. ``"0313810285"``); the FE bubble
    looks much nicer with hyphenated form. Returns the original string when
    the digit count doesn't match a known pattern so we never garble already-
    formatted input or international numbers we don't recognise.
    """
    digits = "".join(c for c in (s or "") if c.isdigit())
    if not digits:
        return ""
    if digits.startswith("02"):
        if len(digits) == 10:
            return f"02-{digits[2:6]}-{digits[6:]}"
        if len(digits) == 9:
            return f"02-{digits[2:5]}-{digits[5:]}"
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return s


# ── 1. product ──────────────────────────────────────────────────────────────────

# Tag chip 매핑 (BE → FE)
# - primary chip (chatbox-product-tag-primary): prc_grd_nm 화이트리스트만 통과.
#   BE 가 이미 한글로 저장 (PR_GOODS_BASE.PRC_GRD_NM) → 그대로 노출.
# - secondary chip (chatbox-product-tag-secondary): goods_pfm_nm 영문 코드를
#   한글 라벨로 매핑. 매핑되지 않은 코드는 chip skip.
_PRC_GRD_ALLOWED: frozenset[str] = frozenset({"프리미엄+", "프리미엄", "스탠다드", "이코노미"})
# `프리미엄+` (플래그십)·`프리미엄` (고급) 두 등급은 FE chip 에서 동일하게 "프리미엄" 으로 노출.
# BE 원본(`prc_grd_nm`)은 그대로 두고 표시 라벨만 통일.
_PRC_GRD_DISPLAY: dict[str, str] = {"프리미엄+": "프리미엄"}
_GOODS_PFM_LABELS: dict[str, str] = {
    "COMFORT": "정숙/승차감",
    "SPORT": "고속/제동성",
    "RUNFLAT": "런플랫",
}
_GOODS_PFM_SUMMARY_LABELS: dict[str, str] = {
    "COMFORT": "컴포트",
    "SPORT": "스포츠",
    "RUNFLAT": "런플랫",
}


def _tool_args(entry: dict) -> dict:
    args = entry.get("args") or entry.get("input") or {}
    return args if isinstance(args, dict) else {}


def _has_size_arg(entry: dict) -> bool:
    args = _tool_args(entry)
    return bool(args.get("size") or args.get("tire_size") or args.get("car_lnc_cd"))


def _numeric_score(row: dict, *keys: str) -> float:
    for key in keys:
        value = _get_num(row, key, default=0.0)
        if value:
            return float(value)
    return 0.0


def _tire_summary_first_line(row: dict) -> str:
    parts: list[str] = []
    car_kind = _get_str(row, "car_knd_nm")
    season = _get_str(row, "season_nm")
    goods_pfm = _GOODS_PFM_SUMMARY_LABELS.get(_get_str(row, "goods_pfm_nm").upper())
    if car_kind:
        parts.append(f"{car_kind}용")
    if season:
        parts.append(season)
    if goods_pfm and goods_pfm not in parts:
        parts.append(goods_pfm)
    if parts:
        return f"{' '.join(parts)} 타이어입니다."
    if _numeric_score(row, "t_life_span") >= 4:
        return "마일리지/수명 성능이 확인된 타이어입니다."
    return "상품 정보가 확인된 타이어입니다."


def _tire_summary_second_line(row: dict) -> str:
    car_kind = _get_str(row, "car_knd_nm")
    goods_pfm = _get_str(row, "goods_pfm_nm").upper()
    life_score = _numeric_score(row, "t_life_span")
    if "전기차" in car_kind:
        return "정숙성과 승차감 중심의 타이어입니다."
    if goods_pfm == "COMFORT":
        if life_score > 0:
            return "승차감과 마일리지 중심의 타이어입니다."
        return "정숙성과 승차감 중심의 타이어입니다."
    if goods_pfm == "SPORT":
        return "고속 주행과 제동 성능 중심의 타이어입니다."
    if goods_pfm == "RUNFLAT":
        return "주행 안정성과 비상 주행 특성을 고려한 타이어입니다."
    if life_score >= 4.5:
        return "수명/마일리지 성능이 강점인 타이어입니다."
    if life_score >= 4:
        return "마일리지 성능을 고려해 검토할 수 있는 타이어입니다."
    if _numeric_score(row, "wet", "t_dryroad_brk") > 0:
        return "제동 성능을 고려해 검토할 수 있는 타이어입니다."
    return "주행 조건에 맞춰 검토할 수 있는 타이어입니다."


_PRODUCT_SEARCH_SIZE_INTENT_RE = re.compile(r"사이즈|규격|호환\s*사이즈|몇\s*인치|몇인치", re.IGNORECASE)
_POPULAR_UNSIZED_REQUEST_RE = re.compile(
    r"인기|베스트\s*셀러|베스트|잘\s*팔리|많이\s*팔린|많이\s*사는|잘\s*나가",
    re.IGNORECASE,
)


def _map_product_search_size_summary(tool_data_list: list[dict]) -> dict | None:
    """Answer size/fitment-size questions from product search results.

    Product search results should serve the user's purpose. If the user asks
    which sizes a searched product family has, a generic "size not confirmed"
    summary is the wrong answer; list the SKU sizes returned by search instead.
    """
    user_text = current_user_text.get()
    if not _PRODUCT_SEARCH_SIZE_INTENT_RE.search(user_text):
        return None

    grouped: dict[str, list[str]] = {}
    found = False
    for entry in _find_entries(tool_data_list, "search_product_tool"):
        if _has_size_arg(entry):
            continue
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        found = True
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = _get_str(row, "goods_nm", "title")
            size = _get_str(row, "tire_size_1", "tire_size_2")
            if not name or not size:
                continue
            sizes = grouped.setdefault(name, [])
            if size not in sizes:
                sizes.append(size)

    if not found or not grouped:
        return None

    lines = ["검색된 상품은 현재 아래 사이즈로 확인돼요."]
    for name, sizes in list(grouped.items())[:5]:
        lines.append(f"- {name}: {', '.join(sizes[:12])}")
    lines.extend([
        "",
        "차량에 장착 가능한지는 차량번호나 현재 타이어 규격 기준으로 다시 확인해 주세요.",
    ])
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": [
                {"label": "내 차량 보기", "domain": "DISCOVERY"},
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
        },
        "assistant_response_source": "code_mapper",
    }


def _product_search_policy_response(tool_data_list: list[dict]) -> str:
    user_text = current_user_text.get() or ""
    decision = current_discovery_response_decision.get()
    if (
        decision is not None
        and str(decision.metadata.get("response_shape_key") or "") == "product_search_summary"
        and "occupation_stereotype" in decision.forbidden_behaviors
        and "마일리지" in user_text
    ):
        names: list[str] = []
        grades: list[str] = []
        for entry in _find_entries(tool_data_list, "search_product_tool"):
            raw = _unwrap(entry)
            rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = _get_str(row, "goods_nm", "title")
                grade = _get_str(row, "prc_grd_nm")
                if name and name not in names:
                    names.append(name)
                if grade and grade not in grades:
                    grades.append(grade)
        product_line = f"현재 확인되는 상품으로는 {', '.join(names[:3])}가 있어요." if names else ""
        grade_line = f"상품 등급은 {', '.join(grades[:3])}로 확인돼요." if grades else ""
        lines = [
            "마일리지 타이어가 특정 직업군만 쓰는 타이어라서 별로라고 보긴 어려워요.",
            "보통은 수명과 유지비를 중요하게 보는 주행 환경에서 많이 찾는 편이고, 용도에 맞으면 충분히 선택할 수 있어요.",
        ]
        if product_line:
            lines.extend(["", product_line])
        if grade_line:
            lines.append(grade_line)
        lines.extend([
            "",
            "고객님 차량이나 주행 스타일에 맞는지까지 보시려면 차량 정보나 타이어 사이즈 기준으로 다시 확인해 드릴게요.",
        ])
        return "\n".join(lines)

    requested_size = ""
    grouped: dict[str, dict[str, object]] = {}
    for entry in _find_entries(tool_data_list, "search_product_tool"):
        args = _tool_args(entry)
        if not requested_size:
            requested_size = _get_str(args, "size", "tire_size")
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = _get_str(row, "goods_nm", "title")
            if not name:
                continue
            bucket = grouped.setdefault(name, {"row": row, "sizes": []})
            size = _get_str(row, "tire_size_1", "tire_size_2")
            sizes = bucket["sizes"]
            if size and isinstance(sizes, list) and size not in sizes:
                sizes.append(size)

    if not grouped:
        return ""

    stock_or_install_request = bool(_STOCK_OR_INSTALL_REQUEST_RE.search(current_user_text.get() or ""))
    if requested_size:
        intro = f"입력하신 {requested_size} 규격 기준으로 상품을 확인했어요."
    elif stock_or_install_request:
        intro = "상품은 확인했어요. 장착 가능 여부 확인을 위해 먼저 규격을 확인할게요."
    else:
        intro = "검색된 상품 기준으로 안내드릴게요."
    lines = [intro]
    for name, data in list(grouped.items())[:5]:
        row = data["row"] if isinstance(data.get("row"), dict) else {}
        sizes = data["sizes"] if isinstance(data.get("sizes"), list) else []
        size_label = "입력 규격" if requested_size else "대표 규격"
        size_text = f" {size_label}: {', '.join(str(size) for size in sizes[:3])}" if sizes else ""
        lines.append(f"- {name}: {_tire_summary_first_line(row)}{size_text}")
        lines.append(f"  {_tire_summary_second_line(row)}")
    if requested_size:
        lines.extend([
            "",
            "가격, 재고, 구매를 이어서 확인할 수 있어요.",
        ])
    else:
        lines.extend([
            "",
            "차량에 맞는 규격 확인을 위해 차량번호나 현재 타이어 사이즈를 알려주세요.",
        ])
    return "\n".join(lines)


def _product_search_policy_requested_size(tool_data_list: list[dict]) -> str:
    for entry in _find_entries(tool_data_list, "search_product_tool"):
        args = _tool_args(entry)
        requested_size = _get_str(args, "size", "tire_size")
        if requested_size:
            return requested_size
    return ""


def _product_search_policy_fallback_response(tool_data_list: list[dict] | None = None) -> str:
    if tool_data_list:
        for entry in reversed(_find_entries(tool_data_list, "search_product_tool")):
            args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
            if not isinstance(args, dict):
                continue
            keyword = _get_str(args, "keyword")
            size = _get_str(args, "size")
            if _STOCK_OR_INSTALL_REQUEST_RE.search(current_user_text.get() or "") and keyword and size:
                return (
                    f"입력하신 {keyword} {size} 상품은 현재 확인되지 않아요.\n"
                    "상품명이나 규격을 다시 확인해 주세요.\n"
                    "정확한 상품이 확인되면 그 기준으로 장착 가능 여부를 안내해 드릴게요."
                )
            if keyword and size:
                return (
                    f"입력하신 {keyword} {size} 상품은 현재 확인되지 않아요.\n"
                    "다른 사이즈나 비슷한 상품으로 다시 찾아드릴 수 있어요."
                )
    if not _STOCK_OR_INSTALL_REQUEST_RE.search(current_user_text.get() or ""):
        return (
            "검색된 상품 정보를 기준으로 안내드릴게요.\n"
            "정확한 상품 목록은 상품명이나 조건을 조금 더 구체적으로 알려주시면 다시 확인해 드릴 수 있어요."
        )
    return (
        "상품은 확인했어요. 장착 가능 여부를 확인하려면 타이어 사이즈와 지역 정보가 필요해요.\n"
        "보유차량 중 선택하거나, 차량번호+소유주명으로 찾거나, 현재 타이어 사이즈를 직접 입력해 주세요."
    )


_PRODUCT_ATTRIBUTE_METRIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("noise", re.compile(r"소음\s*(?:등급|라벨)|저소음\s*등급|소음도|데시벨|dB", re.IGNORECASE)),
    ("fuel_efficiency", re.compile(r"연비|회전\s*저항|rr\b", re.IGNORECASE)),
    ("wet", re.compile(r"빗길|젖은\s*노면|젖은노면|wet|제동\s*등급", re.IGNORECASE)),
    ("price_grade", re.compile(r"상품\s*등급|가격\s*등급|(?<!소음)\s*등급|프리미엄|스탠다드|이코노미", re.IGNORECASE)),
    ("release", re.compile(r"출시|출시일|출시년도|등록일", re.IGNORECASE)),
    ("origin", re.compile(r"원산지|생산국|제조국|어느\s*나라", re.IGNORECASE)),
    ("load", re.compile(r"하중|하중지수|무게", re.IGNORECASE)),
    ("speed", re.compile(r"속도\s*기호|속도|고속", re.IGNORECASE)),
    ("season", re.compile(r"계절|사계절|겨울용|여름용|올웨더|올시즌", re.IGNORECASE)),
    ("car_type", re.compile(r"차종|승용차|suv|전기차용|전기차", re.IGNORECASE)),
)


def _requested_product_attribute_metrics() -> list[str]:
    user_text = current_user_text.get()
    metrics: list[str] = []
    for metric, pattern in _PRODUCT_ATTRIBUTE_METRIC_PATTERNS:
        if pattern.search(user_text) and metric not in metrics:
            metrics.append(metric)
    return metrics or ["noise"]


def _explicit_requested_product_attribute_metrics() -> list[str]:
    user_text = current_user_text.get()
    metrics: list[str] = []
    for metric, pattern in _PRODUCT_ATTRIBUTE_METRIC_PATTERNS:
        if pattern.search(user_text) and metric not in metrics:
            metrics.append(metric)
    return metrics


def _collect_product_attribute_rows(tool_data_list: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for entry in _find_entries(tool_data_list, "search_product_tool"):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = _get_str(row, "goods_nm", "title")
            if not name:
                continue
            grouped.setdefault(name, []).append(row)
    return grouped


def _comparison_group_name(entry: dict, row: dict) -> str:
    keyword = _get_str(_tool_args(entry), "keyword")
    normalized = keyword.casefold().strip()
    if normalized in {"cc2", "미쉐린 cc2", "michelin cc2"}:
        return "미쉐린 CC2"
    if "옵티모" in normalized or "optimo" in normalized:
        return "옵티모"
    if "kinergy ex" in normalized:
        return "키너지 EX"
    if "ventus air" in normalized:
        return "벤투스 에어S"
    if "dynapro hpx" in normalized:
        return "다이나프로 HPX"
    if "dynapro hp3" in normalized:
        return "다이나프로 HP3"
    if keyword:
        return keyword
    return _get_str(row, "goods_nm", "title")


def _collect_product_comparison_rows(tool_data_list: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for entry in _find_entries(tool_data_list, "search_product_tool"):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = _comparison_group_name(entry, row)
            if not name:
                continue
            grouped.setdefault(name, []).append(row)
    return grouped


def _unique_nonempty(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    return unique


def _format_noise_label(rows: list[dict]) -> tuple[str, bool]:
    labels: list[str] = []
    has_missing = False
    for row in rows:
        grade = _get_str(row, "label_pnwave")
        grade_name = _get_str(row, "label_pnwave_nm")
        db = _get_str(row, "label_pndb")
        if grade or grade_name or db:
            label = grade
            if grade_name:
                label = f"{label}({grade_name})" if label else grade_name
            if db:
                label = f"{label}, {db}dB" if label else f"{db}dB"
            labels.append(label)
        else:
            has_missing = True
    labels = _unique_nonempty(labels)
    if labels:
        return f"소음 등급 {', '.join(labels[:3])}", has_missing
    return "소음 등급 표시가 확인되지 않음", has_missing


def _format_product_attribute(metric: str, rows: list[dict]) -> tuple[str, bool]:
    if metric == "noise":
        return _format_noise_label(rows)
    if metric == "fuel_efficiency":
        values = _unique_nonempty([_get_str(row, "rr") for row in rows])
        return (f"회전저항/RR {', '.join(values[:3])}등급" if values else "회전저항/RR 정보 확인되지 않음", False)
    if metric == "wet":
        values = _unique_nonempty([_get_str(row, "wet") for row in rows])
        return (f"젖은노면 제동 {', '.join(values[:3])}등급" if values else "젖은노면 제동 등급 확인되지 않음", False)
    if metric == "price_grade":
        values = _unique_nonempty([_get_str(row, "prc_grd_nm") for row in rows])
        return (f"상품 등급 {', '.join(values[:3])}" if values else "상품 등급 확인되지 않음", False)
    if metric == "release":
        values = _unique_nonempty([_get_str(row, "t_rls_yearmon") for row in rows])
        return (f"출시 시점 {', '.join(values[:3])}" if values else "출시 시점 확인되지 않음", False)
    if metric == "origin":
        values = _unique_nonempty([_get_str(row, "orpl_nm") for row in rows])
        return (f"원산지 {', '.join(values[:3])}" if values else "원산지 확인되지 않음", False)
    if metric == "load":
        values = _unique_nonempty([
            " ".join(filter(None, [_get_str(row, "t_wgt_idx"), _get_str(row, "t_wgt_idx_kg")]))
            for row in rows
        ])
        return (f"하중지수 {', '.join(values[:3])}" if values else "하중지수 확인되지 않음", False)
    if metric == "speed":
        values = _unique_nonempty([_get_str(row, "t_wgt_spd", "t_highspd", "t_highspd_cd") for row in rows])
        return (f"속도기호 {', '.join(values[:3])}" if values else "속도기호 확인되지 않음", False)
    if metric == "season":
        values = _unique_nonempty([_get_str(row, "season_nm") for row in rows])
        return (f"계절 구분 {', '.join(values[:3])}" if values else "계절 구분 확인되지 않음", False)
    if metric == "car_type":
        values = _unique_nonempty([_get_str(row, "car_knd_nm") for row in rows])
        return (f"차종 구분 {', '.join(values[:3])}" if values else "차종 구분 확인되지 않음", False)
    return "", False


def _product_attribute_explanation(metrics: list[str]) -> str:
    if "noise" in metrics:
        return (
            "타이어 소음 등급은 타이어 라벨에 표시되는 외부 주행 소음 기준입니다.\n"
            "A/AA처럼 등급으로 표시되거나 dB 값으로 함께 제공되며, dB 값은 낮을수록 조용한 편이에요.\n\n"
            "특정 상품의 소음 등급은 상품명이나 사이즈를 알려주시면 DB 기준으로 확인해 드릴게요."
        )
    if "fuel_efficiency" in metrics:
        return (
            "타이어 연비 관련 정보는 보통 회전저항(RR) 등급으로 확인합니다.\n"
            "회전저항이 낮을수록 연비 효율에 유리한 편이며, 상품별 등급은 상품명이나 사이즈 기준으로 확인할 수 있어요."
        )
    if "wet" in metrics:
        return (
            "빗길 성능은 젖은노면 제동 등급으로 확인합니다.\n"
            "상품명이나 사이즈를 알려주시면 해당 상품의 젖은노면 제동 등급을 DB 기준으로 확인해 드릴게요."
        )
    return "상품명을 알려주시면 등급, 출시 시점, 원산지, 하중지수, 속도기호 같은 상세 정보를 확인해 드릴게요."


def _product_attribute_no_results_response(tool_data_list: list[dict]) -> str:
    for entry in _find_entries(tool_data_list, "search_product_tool"):
        args = entry.get("args") or entry.get("input") or {}
        if not isinstance(args, dict):
            continue
        keyword = str(args.get("keyword") or "").strip()
        size = _format_tire_size_for_user(args.get("size"))
        if keyword and size:
            return (
                f"고객님 차량 규격 **{size}** 기준으로는 **{keyword}** 상품이 확인되지 않아요.\n\n"
                "다른 차량을 선택하시거나, 같은 상품의 다른 규격을 확인해 드릴게요."
            )
        if keyword:
            return f"**{keyword}** 상품의 요청하신 상세 정보를 찾지 못했어요. 정확한 상품명이나 규격을 알려주세요."
    return ""


def _product_attribute_policy_response(tool_data_list: list[dict]) -> str:
    metrics = _requested_product_attribute_metrics()
    grouped = _collect_product_attribute_rows(tool_data_list)

    if grouped:
        if metrics == ["price_grade"] and len(grouped) == 1:
            name, rows = next(iter(grouped.items()))
            detail, _ = _format_product_attribute("price_grade", rows)
            grade = detail.removeprefix("상품 등급 ").strip() if detail.startswith("상품 등급 ") else ""
            if grade:
                return (
                    f"고객님, {name}의 상품 등급은 {grade}입니다.\n\n"
                    "등급 체계상 프리미엄 > 스탠다드 > 이코노미 순으로 보시면 돼요 😊"
                )
        lines = ["조회된 상품의 상세 정보는 아래처럼 확인돼요."]
        has_partial_missing = False
        for name, rows in list(grouped.items())[:5]:
            details: list[str] = []
            for metric in metrics:
                detail, partial_missing = _format_product_attribute(metric, rows)
                if detail:
                    details.append(detail)
                has_partial_missing = has_partial_missing or partial_missing
            lines.append(f"- {name}: {' / '.join(details) if details else '요청하신 상세 정보가 확인되지 않아요.'}")
        if has_partial_missing:
            lines.append("  일부 규격은 요청하신 상세 정보 표시가 없을 수 있어요.")
        if "noise" in metrics:
            lines.extend(["", "소음 등급은 보통 A/AA처럼 표시되고, dB 값은 낮을수록 조용한 편입니다."])
        return "\n".join(lines)

    no_results_response = _product_attribute_no_results_response(tool_data_list)
    if no_results_response:
        return no_results_response

    return _product_attribute_explanation(metrics)


def _parse_datetime_score(value: str) -> float:
    value = (value or "").strip()
    if not value:
        return 0.0
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y년 %m월"):
        try:
            return datetime.datetime.strptime(value, fmt).timestamp()
        except ValueError:
            continue
    match = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월", value)
    if match:
        return datetime.datetime(int(match.group(1)), int(match.group(2)), 1).timestamp()
    return 0.0


def _comparison_metric_from_decision() -> str:
    decision = current_discovery_response_decision.get()
    if decision is not None:
        metric = str(decision.metadata.get("compare_metric") or "")
        if metric:
            return metric
    user_text = current_user_text.get()
    if re.search(r"최신|신상|신제품|최근(?:에)?\s*(?:출시|나온)|등록일", user_text, re.IGNORECASE):
        return "release"
    if re.search(r"연비|회전\s*저항|rr\b", user_text, re.IGNORECASE):
        return "fuel_efficiency"
    if re.search(r"오래\s*(?:타|탈)|수명|내구|마일리지\s*(?:좋|높|긴)", user_text, re.IGNORECASE):
        return "mileage"
    return "mileage"


def _best_metric_for_rows(rows: list[dict], metric: str) -> tuple[float | None, str]:
    if metric == "mileage":
        scores = [_numeric_score(row, "t_life_span") for row in rows]
        score = max(scores) if scores else 0.0
        return (score if score else None, f"수명/마일리지 점수 {score:g}/5" if score else "수명/마일리지 정보 확인되지 않음")
    if metric == "fuel_efficiency":
        scores = [_numeric_score(row, "rr") for row in rows]
        scores = [score for score in scores if score > 0]
        score = min(scores) if scores else 0.0
        return (score if score else None, f"회전저항/RR {score:g}등급" if score else "회전저항/RR 정보 확인되지 않음")
    if metric == "release":
        best_row: dict | None = None
        best_score = 0.0
        for row in rows:
            score = _parse_datetime_score(_get_str(row, "sys_reg_dtime")) or _parse_datetime_score(
                _get_str(row, "t_rls_yearmon")
            )
            if score > best_score:
                best_score = score
                best_row = row
        if best_row:
            registered = _get_str(best_row, "sys_reg_dtime")
            released = _get_str(best_row, "t_rls_yearmon")
            if registered and released:
                return best_score, f"등록일 {registered[:10]}, 출시 {released}"
            return best_score, f"등록일 {registered[:10]}" if registered else f"출시 {released}"
        return None, "등록일/출시 정보 확인되지 않음"
    if metric == "wet":
        scores = [_numeric_score(row, "wet") for row in rows]
        scores = [score for score in scores if score > 0]
        score = min(scores) if scores else 0.0
        return (score if score else None, f"젖은노면 제동 {score:g}등급" if score else "젖은노면 제동 정보 확인되지 않음")
    return None, "비교 가능한 상세 정보가 확인되지 않음"


def _product_metric_comparison_policy_response(tool_data_list: list[dict]) -> str:
    metric = _comparison_metric_from_decision()
    grouped = _collect_product_comparison_rows(tool_data_list)
    if not grouped:
        return ""

    ranked: list[tuple[str, float | None, str]] = []
    for name, rows in grouped.items():
        score, display = _best_metric_for_rows(rows, metric)
        ranked.append((name, score, display))

    if metric in ("fuel_efficiency", "wet"):
        ranked.sort(key=lambda item: (item[1] is None, item[1] if item[1] is not None else 9999, item[0]))
    else:
        ranked.sort(key=lambda item: (item[1] is not None, item[1] if item[1] is not None else -1), reverse=True)

    best_name, best_score, _ = ranked[0]
    tied_best = [
        name
        for name, score, _ in ranked
        if best_score is not None and score is not None and abs(float(score) - float(best_score)) < 0.0001
    ]
    lines: list[str] = []
    if metric == "release":
        if best_score is not None:
            lines.append(f"최신 상품은 {best_name}입니다.")
        else:
            lines.append("비교 대상의 최신 여부를 판단할 등록일/출시 정보가 충분하지 않아요.")
    elif metric == "fuel_efficiency":
        if best_score is not None:
            if len(tied_best) > 1:
                lines.append(f"회전저항/RR 기준으로는 {', '.join(tied_best[:3])}이 같은 수준으로 확인돼요.")
            else:
                lines.append(f"회전저항/RR 기준으로는 {best_name}이 연비 효율에 가장 유리한 편입니다.")
        else:
            lines.append("비교 대상의 회전저항/RR 정보가 충분하지 않아요.")
    elif metric == "wet":
        if best_score is not None:
            lines.append(f"젖은노면 제동 등급 기준으로는 {best_name}이 가장 유리한 편입니다.")
        else:
            lines.append("비교 대상의 젖은노면 제동 정보가 충분하지 않아요.")
    else:
        if best_score is not None:
            lines.append(f"DB 수명/마일리지 지표 기준으로는 {best_name}이 가장 높게 확인돼요.")
        else:
            lines.append("비교 대상의 수명/마일리지 지표가 충분하지 않아요.")

    for name, _, display in ranked[:6]:
        lines.append(f"- {name}: {display}")

    lines.append("")
    if metric == "fuel_efficiency":
        lines.append("회전저항/RR은 등급 숫자가 낮을수록 연비 효율에 유리한 편입니다.")
    elif metric == "release":
        lines.append("최신 여부는 DB의 상품 등록일을 우선 기준으로 비교했습니다.")
    elif metric == "wet":
        lines.append("젖은노면 제동 등급은 규격별로 표시가 다를 수 있어요.")
    else:
        lines.append("마일리지와 수명은 규격, 차종 호환, 주행환경에 따라 체감이 달라질 수 있어요.")
    return "\n".join(lines)


def _product_restock_policy_response(tool_data_list: list[dict]) -> str:
    first_name = ""
    first_size = ""
    for entry in _find_entries(tool_data_list, "search_product_tool"):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            first_name = _get_str(row, "goods_nm", "title")
            first_size = _get_str(row, "tire_size_1", "tire_size_2")
            if first_name:
                break
        if first_name:
            break

    product_label = "해당 상품"
    if first_name and first_size:
        product_label = f"{first_name} {first_size}"
    elif first_name:
        product_label = first_name
    elif first_size:
        product_label = first_size

    logistics_qty: int | None = None
    for entry in reversed(_find_entries(tool_data_list, "get_logistics_inventory_tool")):
        raw = _unwrap(entry)
        if not isinstance(raw, dict):
            continue
        try:
            logistics_qty = int(raw.get("logistics_qty"))
        except (TypeError, ValueError):
            logistics_qty = None
        break

    if logistics_qty is not None and logistics_qty > 0:
        return (
            f"{product_label} 물류 재고는 확인돼요. "
            "지역이나 매장을 알려주시면 장착 가능한 매장 재고를 확인해 드릴게요."
        )
    if logistics_qty is not None and logistics_qty <= 0:
        return (
            f"{product_label} 물류 재고는 현재 확인되지 않아요. "
            "다만 지역이나 매장을 알려주시면 매장 재고가 있는지 확인해 드릴게요."
        )
    return (
        f"{product_label} 재입고 일정은 현재 바로 확인하기 어려워요. "
        "원하시면 지역이나 매장을 알려주시면 매장 재고가 있는지 먼저 확인해 드릴게요."
    )


def _product_result_context_message(tool_data_list: list[dict], item_count: int) -> str:
    for entry in reversed(_find_entries(tool_data_list, "get_best_selling_products_tool")):
        raw = _unwrap(entry)
        rows = raw.get("items") if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        args = args if isinstance(args, dict) else {}

        period = _get_str(args, "period").lower() or "month"
        period_label = _BEST_SELLER_PERIOD_DISPLAY.get(period, "이번 달")
        top_name = ""
        if isinstance(rows, list) and rows:
            first = rows[0]
            if isinstance(first, dict):
                top_name = _get_str(first, "goods_nm", "title")

        user_text = _current_turn_user_text()
        caveat = ""
        if _DEMOGRAPHIC_AGE_GENDER_RE.search(user_text) and _DEMOGRAPHIC_PREFERENCE_RE.search(user_text):
            caveat = _DEMOGRAPHIC_CAVEAT_TEXT

        if top_name and _BEST_SELLER_COUNT_QUERY_RE.search(user_text):
            return (
                f"{caveat}{period_label} 베스트셀러는 {top_name}예요. "
                f"정확한 판매 개수는 바로 안내드리기 어렵지만, 인기 상품 {item_count}개를 안내드립니다."
            )
        if top_name:
            return f"{caveat}{period_label} 베스트셀러는 {top_name}예요. 인기 상품 {item_count}개를 안내드립니다."
        return f"{caveat}{period_label} 인기 상품 {item_count}개를 안내드립니다. 원하시는 상품을 선택해 주세요."

    for entry in reversed(_find_entries(tool_data_list, "search_product_tool")):
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        if not isinstance(args, dict):
            continue
        keyword = _get_str(args, "keyword")
        size = _get_str(args, "size")
        if keyword and size:
            return f"{keyword} {size} 검색 결과 {item_count}개입니다. 원하시는 상품을 선택해 주세요."
        if keyword:
            return f"{keyword} 검색 결과 {item_count}개입니다. 원하시는 상품을 선택해 주세요."

    for entry in reversed(_find_entries(tool_data_list, "get_products_recommendations_tool")):
        raw = _unwrap(entry)
        fallback = raw.get("recommendation_fallback") if isinstance(raw, dict) else None
        if isinstance(fallback, dict):
            fallback_season = _get_str(fallback, "applied_season_nm")
            requested_season = _get_str(fallback, "requested_season_nm")
            if fallback_season and requested_season:
                return (
                    f"{requested_season} 상품은 현재 확인되지 않아 "
                    f"{fallback_season} 대안 상품 {item_count}개를 찾았어요. 원하시는 상품을 선택해 주세요."
                )

        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        if not isinstance(args, dict):
            continue
        tire_size = _get_str(args, "tire_size")
        season = _get_str(args, "season_nm")
        rcmd_type = _get_str(args, "rcmd_type")
        if tire_size and season:
            return f"{tire_size} {season} 조건으로 찾은 상품 {item_count}개입니다. 원하시는 상품을 선택해 주세요."
        if tire_size:
            return f"{tire_size} 기준으로 찾은 상품 {item_count}개입니다. 원하시는 상품을 선택해 주세요."
        if season:
            return f"{season} 조건으로 찾은 상품 {item_count}개입니다. 원하시는 상품을 선택해 주세요."
        rcmd_label = _RCMD_TYPE_DISPLAY.get(rcmd_type.lower()) if rcmd_type else ""
        if rcmd_label:
            return f"{rcmd_label} 조건으로 찾은 상품 {item_count}개입니다. 원하시는 상품을 선택해 주세요."
        if rcmd_type:
            return f"조건에 맞는 상품 {item_count}개입니다. 원하시는 상품을 선택해 주세요."

    return _TEMPLATE_DEFAULTS.get("product", "").format(n=item_count)


def _technology_unsized_policy_response(tool_data_list: list[dict]) -> str:
    technology = ""
    rows: list[dict] = []
    for entry in reversed(_find_entries(tool_data_list, "get_products_recommendations_tool")):
        args = _tool_args(entry)
        raw = _unwrap(entry)
        candidate_rows = raw.get("items") if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        if not isinstance(candidate_rows, list):
            continue
        rcmd_type = _get_str(args, "rcmd_type").lower()
        if rcmd_type == "sound_absorber":
            technology = "sound_absorber"
            rows = [row for row in candidate_rows if isinstance(row, dict)]
            break

    if technology == "sound_absorber":
        lines = ["흡음재는 타이어 내부에 부착해 주행 중 노면 소음을 줄여주는 소재예요."]
        if rows:
            names: list[str] = []
            for row in rows:
                name = _get_str(row, "goods_nm", "title")
                if name and name not in names:
                    names.append(name)
                if len(names) >= 3:
                    break
            if names:
                lines.extend([
                    "",
                    f"현재 확인되는 흡음재 적용 상품으로는 {', '.join(names)}가 있어요.",
                    "구매를 원하시면 보유차량이나 타이어 사이즈 기준으로 맞는 규격을 찾아드릴게요 😊",
                ])
                return "\n".join(lines)
        lines.extend([
            "",
            "현재 확인되는 흡음재 적용 상품은 차량이나 타이어 사이즈 기준으로 다시 찾아드릴게요 😊",
        ])
        return "\n".join(lines)

    return ""


def _safe_service_unsized_policy_response(tool_data_list: list[dict]) -> str:
    rows: list[dict] = []
    for entry in reversed(_find_entries(tool_data_list, "get_products_recommendations_tool")):
        args = _tool_args(entry)
        raw = _unwrap(entry)
        candidate_rows = raw.get("items") if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        if not isinstance(candidate_rows, list):
            continue
        rcmd_type = _get_str(args, "rcmd_type").lower()
        if rcmd_type in {"safe_kids", "warranty"}:
            rows = [row for row in candidate_rows if isinstance(row, dict)]
            break

    lines = [
        "안심서비스는 티스테이션에서 대상 한국타이어를 구매/장착한 뒤 "
        "주행 중 예기치 못한 타이어 손상이 생겼을 때 보상받을 수 있는 서비스예요.",
        "안심플러스는 보장 범위를 더 넓힌 추가 보장 프로그램으로, 가입 조건과 보장 내용은 상품/주문 단계에서 확인돼요.",
    ]

    names: list[str] = []
    for row in rows:
        if _get_str(row, "t_rlx_isn_yn").upper() not in {"", "O", "Y"}:
            continue
        name = _get_str(row, "goods_nm", "title")
        if name and name not in names:
            names.append(name)
        if len(names) >= 3:
            break
    if names:
        lines.extend([
            "",
            f"현재 확인되는 안심서비스 가능 대표 상품으로는 {', '.join(names)}가 있어요.",
            "차량이나 타이어 사이즈를 알려주시면 장착 가능한 규격 기준으로 다시 확인해 드릴게요 😊",
        ])
    else:
        lines.extend([
            "",
            "차량이나 타이어 사이즈를 알려주시면 안심서비스 가능 상품을 규격 기준으로 확인해 드릴게요 😊",
        ])
    return "\n".join(lines)


def _map_discovery_policy_quickreply(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Honor Discovery policy decisions that forbid card-first rendering."""
    decision = current_discovery_response_decision.get()
    if decision is None or decision.template != TemplateName.QUICK_REPLY:
        return None
    called_tools = {str(entry.get("tool") or "") for entry in tool_data_list if isinstance(entry, dict)}
    if called_tools & _DISCOVERY_POLICY_BLOCKING_TOOLS:
        return None
    if not called_tools & _DISCOVERY_POLICY_SOURCE_TOOLS:
        return None
    response_shape_key = str(decision.metadata.get("response_shape_key") or "")
    if response_shape_key not in {
        "technology_explanation_then_unsized_recommendation_summary",
        "safe_service_explanation_then_unsized_recommendation_summary",
        "metric_comparison_summary",
        "grade_comparison_summary",
        "similar_price_range_recommendation",
        "product_search_summary",
        "product_attribute_summary",
        "restock_inquiry_summary",
    }:
        return None
    if response_shape_key == "similar_price_range_recommendation":
        for entry in _find_entries(tool_data_list, "get_products_recommendations_tool", "search_product_tool"):
            raw = _unwrap(entry)
            rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
            if isinstance(rows, list) and any(isinstance(row, dict) for row in rows):
                return None
    response = sanitize_user_facing_response(assistant_text, "") or decision.assistant_guidance
    if response_shape_key == "product_attribute_summary":
        response = _product_attribute_policy_response(tool_data_list)
    if response_shape_key == "technology_explanation_then_unsized_recommendation_summary":
        response = _technology_unsized_policy_response(tool_data_list) or response
    if response_shape_key == "safe_service_explanation_then_unsized_recommendation_summary":
        response = _safe_service_unsized_policy_response(tool_data_list) or response
    if response_shape_key == "metric_comparison_summary":
        response = _product_metric_comparison_policy_response(tool_data_list) or response
    if response_shape_key == "restock_inquiry_summary":
        response = _product_restock_policy_response(tool_data_list) or response
    if response_shape_key == "product_search_summary" and (
        not response
        or response == decision.assistant_guidance
        or "카드" in response
        or "선택해 주세요" in response
        or "추천 상품" in response
        or "기준으로 답하고" in response
    ):
        response = _product_search_policy_response(tool_data_list) or _product_search_policy_fallback_response(tool_data_list)
    response = sanitize_user_facing_response(response)
    if not response:
        return None
    if response_shape_key == "product_search_summary" and _product_search_policy_requested_size(tool_data_list):
        quick_replies = _DISCOVERY_SIZED_PRODUCT_CHIPS
        predicted_domains = ["TRANSACTION"]
    else:
        quick_replies = _DISCOVERY_POLICY_QUICKREPLY_CHIPS
        predicted_domains = ["DISCOVERY"]
    if response_shape_key == "restock_inquiry_summary":
        quick_replies = _DISCOVERY_RESTOCK_CHIPS
        predicted_domains = ["DISCOVERY", "SUPPORT"]
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": response,
            "quickReplies": quick_replies,
            "predictedDomains": predicted_domains,
        },
        "assistant_response_source": "discovery_policy",
    }


def _map_unsized_tire_summary(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Summarize tire patterns as text when no vehicle/size is confirmed.

    In this state SKU cards are misleading because the same tire appears in
    many unrelated sizes. Keep this as quickReply text until the user provides
    a vehicle or tire size.
    """
    if _find_entries(tool_data_list, "get_my_cars_tool", "get_user_vehicles_tool"):
        return None
    decision = current_discovery_response_decision.get()
    response_shape_key = str((decision.metadata or {}).get("response_shape_key") or "") if decision else ""
    is_neutral_product_description = response_shape_key == "neutral_product_description"
    is_popular_unsized_request = bool(_POPULAR_UNSIZED_REQUEST_RE.search(current_user_text.get() or ""))
    if response_shape_key == "similar_price_range_recommendation":
        for entry in _find_entries(
            tool_data_list,
            "search_product_tool",
            "get_newest_products_tool",
            "get_products_recommendations_tool",
        ):
            raw = _unwrap(entry)
            rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
            if isinstance(rows, list) and any(isinstance(row, dict) for row in rows):
                return None
    product_search_size_summary = _map_product_search_size_summary(tool_data_list)
    if product_search_size_summary:
        return product_search_size_summary
    discovery_policy_quickreply = _map_discovery_policy_quickreply(tool_data_list, assistant_text)
    if discovery_policy_quickreply:
        return discovery_policy_quickreply
    if _explicit_requested_product_attribute_metrics() and _find_entries(tool_data_list, "search_product_tool"):
        response = _product_attribute_policy_response(tool_data_list)
        response = sanitize_user_facing_response(response)
        if response:
            return {
                "type": "data",
                "template": "quickReply",
                "data": {
                    "assistantResponse": response,
                    "quickReplies": _DISCOVERY_POLICY_QUICKREPLY_CHIPS,
                    "predictedDomains": ["DISCOVERY"],
                },
                "assistant_response_source": "code_mapper",
            }
    if current_pending_intent.get() in ("stock", "order", "reservation") or current_goal_type.get() in (
        "store_with_stock",
        "place_order",
        "price_inquiry",
    ):
        return None

    rows_by_name: dict[str, dict] = {}
    found_product_tool = False
    for entry in _find_entries(
        tool_data_list,
        "search_product_tool",
        "get_newest_products_tool",
        "get_products_recommendations_tool",
    ):
        found_product_tool = True
        if _has_size_arg(entry):
            return None
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = _get_str(row, "goods_nm", "big_goods_nm", "ptrn_d_nm", "title")
            if name and name not in rows_by_name:
                rows_by_name[name] = row
    if not found_product_tool or not rows_by_name:
        return None

    skip_size_missing_notice = is_neutral_product_description or is_popular_unsized_request
    lines = [] if skip_size_missing_notice else ["사이즈가 아직 확인되지 않아 타이어 기준으로 안내드릴게요."]
    for name, row in list(rows_by_name.items())[:5]:
        if is_neutral_product_description:
            lines.extend([
                "",
                f"{name}: {_tire_summary_first_line(row)}",
                _tire_summary_second_line(row),
            ])
        else:
            lines.extend([
                "",
                f"- {name}: {_tire_summary_first_line(row)}",
                f"  {_tire_summary_second_line(row)}",
            ])
    if skip_size_missing_notice:
        lines = [line for line in lines if line]
    elif not is_popular_unsized_request:
        lines.extend([
            "",
            "정확한 장착 가능 여부와 가격은 차량 모델 또는 타이어 사이즈를 확인한 뒤 안내드릴 수 있어요.",
        ])

    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": [
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
                {"label": "차량번호로 확인", "domain": "DISCOVERY"},
                {"label": "내 차량 보기", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
        },
        "assistant_response_source": "code_mapper",
    }


def _map_product(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    # Build goods_no → 회원 결제가 lookup from any get_final_price_tool calls in
    # this turn. Discovery's Flow B/C invokes get_final_price_tool in parallel
    # for each search result; pairing by `input.goods_no` is the only robust
    # way (parallel completion order is non-deterministic).
    #
    # Price priority: cheapest_final_prc (회원 보유 쿠폰 적용 후 최저가, 사이트
    # 결제 페이지와 일치) → extra_fvr_sale_prc (사이트 일반 노출 혜택가, "모든
    # 쿠폰 적용 가정") → sale_prc (정가). cheapest_final_prc 가 non-null 이면
    # 무조건 그것을 써야 결제 카드 paymentAmount 가 사이트와 일치한다.
    price_map: dict[str, int] = {}
    for entry in _find_entries(tool_data_list, "get_final_price_tool"):
        # base_agent.py populates `args` (line 319); chat.py path uses `input`.
        # Accept both so the mapper works in either invocation path.
        goods_no = (entry.get("args") or entry.get("input") or {}).get("goods_no")
        if not goods_no:
            continue
        price_data = _unwrap(entry)
        if not isinstance(price_data, dict):
            continue
        price = int(_get_num(price_data, "cheapest_final_prc", default=0))
        if not price:
            price = int(_get_num(price_data, "extra_fvr_sale_prc", default=0))
        if not price:
            price = int(_get_num(price_data, "sale_prc", default=0))
        if price:
            price_map[goods_no] = price

    items, metadata = [], []
    seen_goods_ids: set[str] = set()
    # 회원 보유 쿠폰이 적용된 상품이 1건이라도 있으면 응답 말미에 안내 추가.
    has_cheapest_applied = False
    for entry in _find_entries(
        tool_data_list,
        "search_product_tool",
        "get_newest_products_tool",
        "get_products_recommendations_tool",
        "get_best_selling_products_tool",
    ):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            applied_coupons = row.get("cheapest_applied_coupons")
            if isinstance(applied_coupons, list) and applied_coupons:
                has_cheapest_applied = True
            goods_no = _get_str(row, "goods_no")
            if goods_no and goods_no in seen_goods_ids:
                continue
            goods_nm = _get_str(row, "goods_nm", "title")
            tire_size = _get_str(row, "tire_size_1", "tire_size_2")
            title = f"{goods_nm} {tire_size}".strip() if tire_size else goods_nm
            # Price priority: matched get_final_price_tool result > inline row
            # field (cheapest_final_prc > price/extra_fvr_sale_prc fallback).
            # cheapest_final_prc 는 BE 가 enrich 한 회원 보유 쿠폰 적용 후 최저가 —
            # 사이트 결제 페이지와 일치한다. 없으면 사이트 노출가로 fallback.
            price = (
                price_map.get(goods_no)
                or int(_get_num(row, "cheapest_final_prc", default=0))
                or int(_get_num(row, "price", "extra_fvr_sale_prc", default=0))
            )
            original_price = int(_get_num(row, "sale_prc", default=0)) or None
            discount_rate = float(_get_num(row, "extra_fvr_sale_per", default=0.0)) or None
            discount_amount = (
                original_price - price
                if original_price and price and original_price > price
                else None
            )
            # Tag chips:
            # - primary: prc_grd_nm 화이트리스트 (한글 그대로). 그 외 값은 skip.
            # - secondary: goods_pfm_nm 영문 코드 → 한글 라벨 매핑. 매핑 외 코드는 skip.
            # 각 chip 의 primary 플래그는 FE 클래스 결정 (위치 무관) — primary 누락 시
            # secondary 가 primary 로 보일 일 없음.
            tags: list[dict] = []
            prc_grd = _get_str(row, "prc_grd_nm")
            if prc_grd in _PRC_GRD_ALLOWED:
                tags.append({"text": _PRC_GRD_DISPLAY.get(prc_grd, prc_grd), "primary": True})
            goods_pfm_code = _get_str(row, "goods_pfm_nm").upper()
            goods_pfm_label = _GOODS_PFM_LABELS.get(goods_pfm_code)
            if goods_pfm_label:
                tags.append({"text": goods_pfm_label, "primary": False})
            items.append({
                "imageUrl": _get_str(row, "image_url"),
                "title": title,
                "tires": "",
                "titleProductName": goods_nm,
                "titleTires": tire_size,
                "brandName": _normalize_brand_name(_get_str(row, "brand_nm")),
                "oeBadgeYn": _get_str(row, "oe_badge_yn"),
                "oeMaker": _get_str(row, "t_oe_maker_1"),
                "smrtPayYn": _get_str(row, "smrt_pay_yn"),
                "comfort": "",
                "price": price,
                "originalPrice": original_price,
                "discountRate": discount_rate,
                "discountAmount": discount_amount,
                "rate": float(_get_num(row, "rate", "rating_avg", default=0.0)),
                "totalQuantity": int(_get_num(row, "totalQuantity", "total_qty", default=0)),
                "tags": tags,
                "description": "",
            })
            metadata.append({"goodsId": goods_no})
            if goods_no:
                seen_goods_ids.add(goods_no)
    if not items:
        return None
    items, metadata = items[:10], metadata[:10]

    # Mirror LocationTemplate.isBookingFlow — driven purely by goal_type since
    # product cards don't co-occur with the inventory/schedule signal tools.
    # When the active goal is checklist-driven (stock/order/price), a click on
    # a product card should advance the flow (qty → shop → tool call), so the
    # FE must route to /chat instead of /append.
    short, response_source = _summarize_with_source(assistant_text, "product", len(items))
    if _find_entries(tool_data_list, "get_best_selling_products_tool"):
        short = _product_result_context_message(tool_data_list, len(items))
        response_source = "code_mapper"
    elif response_source == "default" or _GENERIC_PRODUCT_RESPONSE_RE.search(short):
        short = _product_result_context_message(tool_data_list, len(items))
        response_source = "code_mapper"

    # 회원 보유 쿠폰 적용된 상품이 1건 이상이면 결정적으로 안내 문구 추가.
    # _summarize_with_source 의 첫 문장 컷팅 뒤에 붙여서 truncation 회피.
    _COUPON_FOOTNOTE = "*해당 혜택가는 현재 보유 쿠폰 기준으로 적용된 가격입니다."
    if has_cheapest_applied and _COUPON_FOOTNOTE not in short:
        short = f"{short.rstrip()}\n\n{_COUPON_FOOTNOTE}" if short else _COUPON_FOOTNOTE

    handoff_event = _single_product_transaction_handoff_event(items, metadata)
    if handoff_event is not None:
        return handoff_event

    return {
        "type": "data",
        "template": "product",
        "data": {
            "products": items,
            "metadata": metadata,
            "isBookingFlow": _is_goal_booking_followup(),
            "assistantResponse": short,
        },
        "assistant_response_source": response_source,
    }


def inject_product_tags_and_sanitize(
    data_event: dict | None,
    accumulated_tool_data: list[dict],
) -> None:
    """LLM-driven product event 후처리: tags 결정형 주입 + 알수없는 필드 strip.

    LLM 이 OUTPUT_TEMPLATE 을 통해 fenced JSON 으로 product 템플릿을 직접
    emit 하는 경로 (`base_agent._build_data_event_from_text`) 에서, tags 는
    BE row 에서 결정되어야 하므로 매퍼와 동일 규칙으로 덮어쓰고, comfort 같은
    스키마 외 hallucinated 필드는 제거한다.

    Mutation in place. data_event 가 product 템플릿이 아니면 no-op.
    """
    if not isinstance(data_event, dict) or data_event.get("template") != "product":
        return
    data = data_event.get("data")
    if not isinstance(data, dict):
        return
    products = data.get("products")
    metadata = data.get("metadata")
    if not isinstance(products, list):
        return

    # Build goodsId → BE row lookup from accumulated tool data
    rows_by_goods: dict[str, dict] = {}
    for entry in _find_entries(
        accumulated_tool_data,
        "search_product_tool",
        "get_newest_products_tool",
        "get_products_recommendations_tool",
        "get_best_selling_products_tool",
    ):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            goods_no = _get_str(row, "goods_no")
            if goods_no:
                rows_by_goods[goods_no] = row

    # Allowed keys derived from ProductItem schema (single source of truth).
    # Lazy import — avoid template_mapper ↔ schemas circular imports at module load.
    from services.tstation.agents.templates.schemas import ProductItem
    allowed_keys = frozenset(ProductItem.model_fields.keys())

    meta_list = metadata if isinstance(metadata, list) else []
    for i, product in enumerate(products):
        if not isinstance(product, dict):
            continue
        # Strip unknown keys (LLM hallucinations like comfort)
        for key in list(product.keys()):
            if key not in allowed_keys:
                product.pop(key, None)
        # Inject deterministic tags from BE row matched by metadata[i].goodsId.
        meta = meta_list[i] if i < len(meta_list) and isinstance(meta_list[i], dict) else {}
        goods_id = meta.get("goodsId")
        row = rows_by_goods.get(goods_id) if isinstance(goods_id, str) else None
        tags: list[dict] = []
        if row is not None:
            prc_grd = _get_str(row, "prc_grd_nm")
            if prc_grd in _PRC_GRD_ALLOWED:
                tags.append({"text": _PRC_GRD_DISPLAY.get(prc_grd, prc_grd), "primary": True})
            goods_pfm_code = _get_str(row, "goods_pfm_nm").upper()
            goods_pfm_label = _GOODS_PFM_LABELS.get(goods_pfm_code)
            if goods_pfm_label:
                tags.append({"text": goods_pfm_label, "primary": False})
            product["titleProductName"] = _get_str(row, "goods_nm", "title")
            product["titleTires"] = _get_str(row, "tire_size_1", "tire_size_2")
            product["brandName"] = _normalize_brand_name(_get_str(row, "brand_nm"))
            product["oeBadgeYn"] = _get_str(row, "oe_badge_yn")
            product["oeMaker"] = _get_str(row, "t_oe_maker_1")
            product["smrtPayYn"] = _get_str(row, "smrt_pay_yn")
        product["tags"] = tags


# ── 2. listCar ──────────────────────────────────────────────────────────────────

def _map_list_car(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    # Maintenance D-day flow guard: when get_maintenance_dday_tool ran in the
    # same turn, get_my_cars_tool was used only to map car_no → mbr_car_reg_seq.
    # Emitting a listCar card here would duplicate the vehicle list next to
    # the D-day answer; suppress so quickReply owns the turn.
    if _find_entries(tool_data_list, "get_maintenance_dday_tool"):
        return None
    # Recommendation-entry guard: when the same turn already used
    # get_my_cars_tool only to recover car_lnc_cd / tire_size for
    # get_products_recommendations_tool, a zero-result recommendation should
    # fall through to the agent's quickReply guidance instead of re-showing the
    # exact same vehicle card. Successful recommendation turns are handled by
    # the higher-priority product mapper above, so suppressing here is safe.
    if _has_tool_entry(tool_data_list, "get_products_recommendations_tool"):
        return None
    # Generic advice guard: Discovery sometimes calls get_my_cars_tool only to
    # ground an answer about the user's vehicle ("내차는 트럭인데..." etc.) without
    # actually asking the user to choose one car. In those turns, re-rendering
    # the full vehicle list is misleading noise. Only render listCar when the
    # assistant text clearly asks the user to pick / confirm a vehicle.
    text = (assistant_text or "").strip()
    if text and not any(
        needle in text
        for needle in (
            "선택",
            "골라",
            "어떤 차량",
            "이 차량으로 진행",
            "차량을 확인해",
            "등록된 차량",
            "차량 목록",
        )
    ):
        return None
    items, metadata = [], []
    all_rows: list[dict] = []
    for entry in _find_entries(tool_data_list, "get_my_cars_tool", "get_user_vehicles_tool"):
        raw = _unwrap(entry)
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict):
            # get_my_cars_tool → MemberCarListResponse { items: [] }
            # get_user_vehicles_tool → single dict { car_model, car_model_det, car_nm, ... }
            rows = raw.get("items") if "items" in raw else [raw]
        else:
            rows = []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            all_rows.append(row)
            car_nm = _get_str(row, "car_model_det", "car_nm")
            car_maker = _get_str(row, "car_maker")
            car_info = f"{car_maker} {car_nm}" if car_maker and car_nm else (car_nm or car_maker)
            items.append({
                "licensePlate": _get_str(row, "car_no"),
                "info": car_info,
                "description": car_info,
                "imageUrl": _get_str(row, "thnl_img_path_nm", "mo_img_path_nm", "pc_img_path_nm"),
            })
            metadata.append({
                "carNo": _get_str(row, "car_no"),
                "carLncCd": _get_str(row, "car_lnc_cd"),
                "mbrCarRegSeq": _get_str(row, "mbr_car_reg_seq", "mbr_car_unif_no") or None,
                "carMaker": _get_str(row, "car_maker") or None,
                "carModelDet": _get_str(row, "car_model_det") or None,
                "carName": _get_str(row, "car_nm") or None,
                "carTrim": _get_str(row, "ver_opt_choc") or None,
                "carEngine": _get_str(row, "car_engine") or None,
                # Persist front/rear tire sizes alongside the car identifier so
                # the coordinator's selection-time resolver can recover
                # tire_size from the listCar template metadata when the user
                # later picks a car. Without this, filter_for_context drops
                # car_no as PII and the resolver has no source to match on.
                "tireSize": _get_str(row, "tire_size_fr") or None,
                "tireSizeRe": _get_str(row, "tire_size_re") or None,
            })
    if not items:
        return None
    if _should_suppress_listcar_for_possessive_model_mismatch(all_rows):
        return None
    user_text = current_user_text.get() or ""
    plate_match = _VEHICLE_PLATE_RE.search(user_text)
    if plate_match:
        requested_plate = re.sub(r"[^0-9가-힣]", "", plate_match.group(0))
        returned_plates = {
            re.sub(r"[^0-9가-힣]", "", str(meta.get("carNo") or ""))
            for meta in metadata
            if isinstance(meta, dict)
        }
        if requested_plate and requested_plate not in returned_plates:
            if _VEHICLE_OWNER_RE.search(user_text):
                assistant_response = (
                    f"입력하신 **{requested_plate}** 차량 정보를 확인하지 못했어요.\n"
                    "차량번호와 소유주명을 다시 확인해 주세요."
                )
                quick_replies = [
                    {"label": "차번+이름 다시 입력", "domain": "DISCOVERY"},
                    {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
                    {"label": "내 차량 보기", "domain": "DISCOVERY"},
                ]
            else:
                assistant_response = (
                    f"**{requested_plate}** 은(는) 등록된 차량 목록에 없어요.\n"
                    "해당 차량으로 찾으시려면 **차량번호 + 소유주명**을 입력해 주세요. "
                    "예: 12가3456 홍길동"
                )
                quick_replies = [
                    {"label": "차번+이름으로 검색", "domain": "DISCOVERY"},
                    {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
                    {"label": "내 차량 보기", "domain": "DISCOVERY"},
                ]
            return _build_event(
                "quickReply",
                {
                    "assistantResponse": assistant_response,
                    "quickReplies": quick_replies,
                    "predictedDomains": ["DISCOVERY"],
                },
                assistant_response,
                0,
            )
    # 차량이 1대여도 자동 선택하지 않고 listCar 카드를 노출하여 유저가 직접 선택하도록 유도한다.
    return _build_event("listCar", {"listCar": items, "metadata": metadata}, assistant_text, len(items))


# ── 3. voucher ──────────────────────────────────────────────────────────────────

def _map_voucher(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    vouchers, metadata = [], []
    for entry in _find_entries(tool_data_list, "get_my_coupons_tool"):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else ((raw.get("coupons") or raw.get("items") or []) if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            cpn_no = _get_str(row, "cpn_no", "cpn_issu_no")
            vouchers.append({
                "nameVoucher": _get_str(row, "cpn_nm", "disp_nm"),
                "discount": _get_str(row, "rt_amt_val"),
                "dateVoucher": _get_str(row, "use_end_dtime").split(" ")[0],
                "downloadLink": "",
                "myCouponLink": _MY_COUPON_LINK,
            })
            metadata.append({"couponId": cpn_no})
    if not vouchers:
        return None
    return _build_event("voucher", {"vouchers": vouchers, "metadata": metadata}, assistant_text, len(vouchers))


# ── 4. qnaComplete ──────────────────────────────────────────────────────────────

def _map_qna_complete(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    entries = _find_entries(tool_data_list, "transfer_to_qna_tool")
    if not entries:
        return None
    raw = _unwrap(entries[-1])
    if not isinstance(raw, dict):
        return None

    redict_link = raw.get("redictLink") or raw.get("redict_link") or {}
    cnsl_seq = str(raw.get("cnsl_clss_seq") or "")
    cnsl_type = _CNSL_TYPE_MAP.get(cnsl_seq, cnsl_seq)
    title = _get_str(raw, "inq_tit_nm")
    summary = _get_str(raw, "ai_summary")

    if not redict_link:
        return None

    data = {
        "redictLink": redict_link,
        "cnslType": cnsl_type,
        "title": title,
        "summary": summary,
    }
    short = assistant_text.strip() if assistant_text and len(assistant_text.strip()) <= 120 else "1:1 문의가 접수되었습니다. 아래 버튼을 눌러 확인해 주세요."
    if re.search(r"쿠폰", f"{title}\n{summary}") and re.search(r"만료|원복|복구|다시\s*쓸|재사용", f"{title}\n{summary}"):
        short = (
            "만료된 쿠폰은 원칙적으로 원복이 어렵습니다. "
            "다만 자세한 확인이 필요하시면 아래 버튼을 눌러 1:1 문의를 진행해 주세요."
        )
    return {"type": "data", "template": "qnaComplete", "data": {**data, "assistantResponse": short}}


# ── 5. cheapestProduct ──────────────────────────────────────────────────────────

def _map_cheapest_product(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    # 두 도구를 모두 처리: compare_discount_tool (기존: cheapest_goods_no 1건) +
    # get_cheapest_price_tool (신규: 회원 보유 쿠폰 3-stage 시뮬레이션, 상품별 1건).
    entries = _find_entries(tool_data_list, "compare_discount_tool", "get_cheapest_price_tool")
    if not entries:
        return None
    raw = _unwrap(entries[-1])
    if not isinstance(raw, dict):
        return None

    rows = raw.get("items", [])
    if not isinstance(rows, list) or not rows:
        return None

    cheapest_no = _get_str(raw, "cheapest_goods_no")
    quantity = int(_get_num(raw, "quantity", default=1))

    items, metadata = [], []
    for row in rows:
        if not isinstance(row, dict):
            continue
        goods_no = _get_str(row, "goods_no")
        # cheapest_goods_no가 있으면 그것만 (compare_discount_tool 경로)
        if cheapest_no and goods_no != cheapest_no:
            continue

        # get_cheapest_price_tool: applied_coupons 에서 stage별 합산
        applied = row.get("applied_coupons")
        if isinstance(applied, list) and applied:
            product_discount = sum(
                int(c.get("discount_amt", 0)) for c in applied
                if isinstance(c, dict) and c.get("stage") == "product"
            )
            coupon_discount = sum(
                int(c.get("discount_amt", 0)) for c in applied
                if isinstance(c, dict) and c.get("stage") in ("payment", "plus")
            )
            final_price = int(_get_num(row, "final_prc", "final_unit_price", default=0))
        else:
            product_discount = int(_get_num(row, "product_discount", default=0))
            coupon_discount = int(_get_num(row, "coupon_discount", default=0))
            final_price = int(_get_num(row, "final_unit_price", "final_prc", default=0))

        items.append({
            "title": _get_str(row, "goods_nm", "title", default=goods_no),
            "originalPrice": int(_get_num(row, "sale_prc", default=0)),
            "quantity": quantity,
            "totalDiscount": int(_get_num(row, "total_discount", default=0)),
            "productDiscount": product_discount,
            "couponDiscount": coupon_discount,
            "finalPrice": final_price,
        })
        metadata.append({"goodsId": goods_no})

    if not items:
        return None
    return _build_event("cheapestProduct", {"cheapestProduct": items, "metadata": metadata}, assistant_text, len(items))


# ── 5.5 run-flat comparison ───────────────────────────────────────────────────

def _is_runflat_product(row: dict) -> bool:
    pfm = _get_str(row, "goods_pfm_nm").upper()
    if pfm == "RUNFLAT":
        return True
    name = _get_str(row, "goods_nm", "title").lower()
    return "런플랫" in name or "runflat" in name or "run-flat" in name


def _map_runflat_price_comparison(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Build a deterministic quickReply table for normal tire vs run-flat price.

    This owns TC-110-style turns where Discovery first searches by size/model,
    verifies both product groups really exist, then calls compare_discount_tool.
    Without this mapper, the generic priority order renders search results as
    product cards and loses the comparison answer.
    """
    if not current_runflat_comparison.get():
        return None

    compare_entries = _find_entries(tool_data_list, "compare_discount_tool")
    if not compare_entries:
        return None

    product_by_goods_no: dict[str, dict] = {}
    for entry in _find_entries(tool_data_list, "search_product_tool", "get_products_recommendations_tool"):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            goods_no = _get_str(row, "goods_no")
            if goods_no:
                product_by_goods_no[goods_no] = row

    if not product_by_goods_no:
        return None

    compare_raw = _unwrap(compare_entries[-1])
    if not isinstance(compare_raw, dict):
        return None
    price_rows = compare_raw.get("items", [])
    if not isinstance(price_rows, list):
        return None

    rows: list[dict] = []
    for price_row in price_rows:
        if not isinstance(price_row, dict):
            continue
        goods_no = _get_str(price_row, "goods_no")
        product_row = product_by_goods_no.get(goods_no)
        if not product_row:
            continue
        final_unit_price = int(_get_num(price_row, "final_unit_price", default=0))
        if not final_unit_price:
            continue
        rows.append({
            "goods_no": goods_no,
            "goods_nm": _get_str(product_row, "goods_nm", "title", default=goods_no),
            "tire_size": _get_str(product_row, "tire_size_1", "tire_size_2"),
            "is_runflat": _is_runflat_product(product_row),
            "final_unit_price": final_unit_price,
        })

    normal_rows = [row for row in rows if not row["is_runflat"]]
    runflat_rows = [row for row in rows if row["is_runflat"]]
    if not normal_rows or not runflat_rows:
        return None

    # Use the lowest normal tire as the visible baseline for "how much more".
    baseline = min(normal_rows, key=lambda row: row["final_unit_price"])
    display_rows = sorted(
        sorted(normal_rows, key=lambda row: row["final_unit_price"])[:2]
        + sorted(runflat_rows, key=lambda row: row["final_unit_price"])[:2],
        key=lambda row: (row["is_runflat"], row["final_unit_price"]),
    )

    lines = [
        "고객님, 같은 조건에서 일반 타이어와 런플랫 상품이 함께 확인되어 가격을 비교했어요.",
        "",
        "| 상품 | 런플랫 | 1개 기준 최종가 | 일반 타이어 대비 |",
        "|---|---:|---:|---:|",
    ]
    for row in display_rows:
        delta = row["final_unit_price"] - baseline["final_unit_price"]
        if row["goods_no"] == baseline["goods_no"]:
            delta_text = "기준"
        elif delta > 0:
            delta_text = f"+{delta:,}원"
        elif delta < 0:
            delta_text = f"{delta:,}원"
        else:
            delta_text = "동일"
        product = f"{row['goods_nm']} {row['tire_size']}".strip()
        lines.append(
            f"| {product} | {'O' if row['is_runflat'] else 'X'} | {row['final_unit_price']:,}원 | {delta_text} |"
        )
    lines.extend([
        "",
        "런플랫은 보통 일반 타이어보다 비싼 편이지만, 차이는 모델과 사이즈별로 달라요.",
        "",
        "현재 조회된 같은 조건 상품 기준의 비교입니다.",
        "",
        "온라인 주문 기준 무료 배송/무료 장착 정책은 일반 타이어와 런플랫에 동일하게 적용됩니다. 별도 추가 장착비는 확인된 금액이 있을 때만 안내할 수 있어요.",
    ])

    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": [
                {"label": "런플랫 상품 보기", "domain": "DISCOVERY"},
                {"label": "일반 타이어 보기", "domain": "DISCOVERY"},
                {"label": "구매하기", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["DISCOVERY", "TRANSACTION"],
        },
        "assistant_response_source": "code_mapper",
    }


# ── 6. event ────────────────────────────────────────────────────────────────────

def _is_ev_product(row: dict) -> bool:
    car_kind = _get_str(row, "car_knd_nm").lower()
    return "전기차" in car_kind or car_kind == "ev" or "electric" in car_kind


def _display_product_name(row: dict) -> str:
    name = _get_str(row, "goods_nm", "title", default="상품")
    size = _get_str(row, "tire_size_1", "tire_size_2", "tire_size")
    return f"{name} {size}".strip()


def _map_ev_suitability_comparison(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Build a deterministic quickReply for EV tire suitability comparisons."""
    if not current_ev_suitability_comparison.get():
        return None
    if current_pending_intent.get() in ("stock", "order", "reservation") or current_goal_type.get() in (
        "store_with_stock",
        "place_order",
    ):
        return None

    rows: list[dict] = []
    seen: set[str] = set()
    for entry in _find_entries(tool_data_list, "search_product_tool", "get_products_recommendations_tool"):
        raw = _unwrap(entry)
        items = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(items, list):
            continue
        for row in items:
            if not isinstance(row, dict):
                continue
            key = _get_str(row, "goods_no") or _display_product_name(row)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)

    if not rows:
        return None

    non_ev_rows = [row for row in rows if not _is_ev_product(row)]
    non_ev_product_names = []
    seen_non_ev_names: set[str] = set()
    for row in non_ev_rows:
        name = _get_str(row, "goods_nm", "title")
        if not name or name in seen_non_ev_names:
            continue
        seen_non_ev_names.add(name)
        non_ev_product_names.append(name)

    lines = [
        "타이어는 차량 유형뿐 아니라 차량 모델, 순정 규격, 하중지수, 속도지수까지 함께 맞아야 합니다.",
        "",
        "따라서 전기차, SUV, 경차 같은 차량 카테고리만으로는 특정 상품이나 규격을 바로 추천드리기 어렵습니다.",
        "",
        "보유차량을 확인하거나 차종을 알려주시면, 해당 차량 규격 기준으로 장착 가능한 타이어를 안내드릴게요.",
    ]
    if non_ev_product_names:
        lines.extend(
            [
                "",
                f"{', '.join(non_ev_product_names[:2])} 같은 상품도 장착 가능 여부는 차량 카테고리만이 아니라 실제 차량 규격과 하중지수 기준으로 확인해야 합니다.",
            ]
        )

    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": [
                {"label": "보유차량 확인", "domain": "DISCOVERY"},
                {"label": "차종으로 추천", "domain": "DISCOVERY"},
                {"label": "규격으로 찾기", "domain": "DISCOVERY"},
                {"label": "구매하기", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["DISCOVERY", "TRANSACTION"],
        },
        "assistant_response_source": "code_mapper",
    }


def _map_event(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    items, metadata = [], []
    for entry in _find_entries(tool_data_list, "get_events_tool"):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            start = _get_str(row, "evt_strt_dtime")
            end = _get_str(row, "evt_end_dtime")
            period = f"{start} ~ {end}" if start and end else start or end or ""
            items.append({
                "eventName": _get_str(row, "evt_nm"),
                "bannerImage": _get_str(row, "bnr_img_url_addr"),
                "eventUrl": _get_str(row, "evt_url_addr"),
                "badge": _get_str(row, "evt_badge_nm"),
                "period": period,
                "actionLink": _get_str(row, "evt_url_addr", "dtl_conts_url_addr"),
                "actionText": "자세히 보기",
            })
            metadata.append({"eventId": _get_str(row, "evt_no")})
    if not items:
        return None
    items, metadata = items[:5], metadata[:5]
    return _build_event("event", {"events": items, "metadata": metadata}, assistant_text, len(items))


# ── 7. previewYoutube ───────────────────────────────────────────────────────────

def _map_preview_youtube(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    items = []
    for entry in _find_entries(tool_data_list, "search_youtube_video_tool"):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else ((raw.get("data") or raw.get("items") or []) if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            items.append({
                "title": _get_str(row, "title"),
                "thumbnailUrl": _get_str(row, "thumbnailUrl", "thumbnail_url"),
                "youtubeUrl": _get_str(row, "url", "youtubeUrl", "youtube_url"),
                "videoId": _get_str(row, "videoId", "video_id"),
            })
    if not items:
        return None
    items = items[:5]
    short, response_source = _summarize_with_source(assistant_text, "previewYoutube", len(items))
    # previewYoutube: FE reads data.text (not assistantResponse) for intro text
    return {"type": "data", "template": "previewYoutube", "data": {
        "items": items,
        "text": short,
        "assistantResponse": short,
    }, "assistant_response_source": response_source}


# ── 8. location ─────────────────────────────────────────────────────────────────

# 매장 보유 서비스 코드 → 사용자 노출 라벨 매핑.
# 113 (타이어 - 온라인) 은 거의 모든 매장 보유라 노출 생략 (가독성).
# 124/125 (얼라인먼트 오프라인/온라인) 은 사용자 입장에서 동일 의미라 같은 라벨로 통합.
_SVC_CODE_LABELS: dict[str, str] = {
    "116": "배터리",
    "119": "타이어 보관",
    "120": "수입타이어",
    "121": "경정비",
    "122": "경정비 당일",
    "124": "얼라인먼트",
    "125": "얼라인먼트",
    "126": "무상점검",
}


def _svc_code_label_list(svc_codes: object) -> list[str]:
    """svc_codes (list[str]) → 중복 제거된 사용자 라벨 리스트 (입력 순서 유지)."""
    if not isinstance(svc_codes, list):
        return []
    labels: list[str] = []
    seen: set[str] = set()
    for code in svc_codes:
        label = _SVC_CODE_LABELS.get(str(code))
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    return labels


_STORE_RESULT_LIMIT_RE = re.compile(r"(\d+)\s*(?:개|곳|군데)\s*(?:만|까지)?")
_STORE_RESULT_LIMIT_KO = {
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
_STORE_RESULT_LIMIT_KO_RE = re.compile(
    r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(?:개|곳|군데)\s*(?:만|까지)?"
)


def _store_result_limit_from_text(text: str) -> int | None:
    match = _STORE_RESULT_LIMIT_RE.search(text or "")
    if match:
        try:
            return max(1, min(int(match.group(1)), 10))
        except ValueError:
            return None
    ko_match = _STORE_RESULT_LIMIT_KO_RE.search(text or "")
    if ko_match:
        return _STORE_RESULT_LIMIT_KO.get(ko_match.group(1))
    return None


def _store_result_limit(tool_data_list: list[dict]) -> int:
    requested = _store_result_limit_from_text(current_user_text.get() or "")
    if requested is not None:
        return requested
    for entry in reversed(tool_data_list):
        if entry.get("tool") not in {
            "search_stores_tool",
            "search_stores_complex_tool",
            "get_store_list_tool",
            "get_nearby_stores_tool",
        }:
            continue
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        if not isinstance(args, dict) or args.get("limit") is None:
            continue
        try:
            return max(1, min(int(args["limit"]), 10))
        except (TypeError, ValueError):
            continue
    return 10


def _has_store_candidates(tool_data_list: list[dict]) -> bool:
    for entry in _find_entries(
        tool_data_list,
        "search_stores_tool",
        "search_stores_complex_tool",
        "get_store_list_tool",
        "get_nearby_stores_tool",
        "transaction_store_preview_tool",
        "get_favorite_stores_tool",
    ):
        raw = _unwrap(entry)
        stores = raw.get("stores") if isinstance(raw, dict) else None
        if isinstance(stores, list) and any(isinstance(store, dict) for store in stores):
            return True
    return False


def _is_plain_store_search_user_text() -> bool:
    text = current_user_text.get() or ""
    if not text:
        return False
    has_store_search = bool(re.search(r"매장|지점|티스테이션|더타이어샵|근처|주변|찾아|알려|보여", text, re.IGNORECASE))
    has_transaction_stock = bool(re.search(r"재고|오늘\s*장착|당일\s*장착|장착\s*가능|예약|구매|주문", text, re.IGNORECASE))
    has_product = bool(
        re.search(
            r"벤투스|ventus|다이나프로|dynapro|키너지|kinergy|아이온|ion|옵티모|optimo|미쉐린|michelin|cc2",
            text,
            re.IGNORECASE,
        )
    )
    return has_store_search and not has_transaction_stock and not has_product


def _map_location(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    called_tools = {e.get("tool", "") for e in tool_data_list}
    transaction_decision = current_transaction_response_decision.get()
    required_slots = set(transaction_decision.required_slots or ()) if transaction_decision else set()
    has_store_candidates = _has_store_candidates(tool_data_list)
    if (
        transaction_decision
        and transaction_decision.template == TemplateName.QUICK_REPLY
        and transaction_decision.required_slots
        and not (required_slots <= {"store"} and has_store_candidates)
        and not _preview_tool_requires_location(tool_data_list)
        and called_tools
        & {
            "search_stores_tool",
            "search_stores_complex_tool",
            "get_store_list_tool",
            "get_nearby_stores_tool",
            "transaction_store_preview_tool",
        }
    ):
        return None
    # Flow 3.5 (빠른 방문) calls store_list + multi_store_schedule and renders a
    # comparison table as `quickReply`, not a `location` card. Defer to LLM.
    if "get_multi_store_schedule_tool" in called_tools:
        return None
    # Flow 3 STEP A calls store_list + store_inventory in the same turn. When
    # inventory has eligible shops, render only those shops as location cards.
    # When inventory has no eligible shops, `_map_inventory_stock_result` owns
    # the quickReply fallback.
    inventory_stock_labels = _same_turn_inventory_stock_labels(tool_data_list)
    if "get_store_inventory_tool" in called_tools and not inventory_stock_labels:
        return None
    # Flow 3 STEP C / Flow 5.1 (date-specific) → datepick after detail. If
    # `get_store_schedule_tool` ran, the datepick mapper already wins via
    # priority; for `get_store_detail_tool` with a single shop + non-empty
    # slots, the agent emits its own datepick JSON (mapper has no cal_day in
    # response). Don't second-guess by also producing a location card.
    if "get_store_schedule_tool" in called_tools:
        return None

    no_fulfillment_preview = _map_preview_no_fulfillment_quickreply(tool_data_list, assistant_text)
    if no_fulfillment_preview is not None:
        return no_fulfillment_preview

    # `transaction_store_preview_tool` with no available schedule. The preview
    # tool runs in purchase flow ("이 상품 N개 [매장/근처] 오늘 가능?"); when its
    # `schedule.tier == "none"` (or `schedule.stores` is empty), today install
    # is unavailable across all candidates. Rendering a location card here is
    # a dead end — clicking any store (isBookingFlow=true) routes back through
    # the same flow that just returned no slot. Emit a quickReply with chips
    # guiding the user to broaden the search or shift the date instead.
    if "transaction_store_preview_tool" in called_tools:
        if _is_other_store_request():
            for entry in _find_entries(tool_data_list, "transaction_store_preview_tool"):
                raw = _unwrap(entry)
                if not isinstance(raw, dict):
                    continue
                stores = raw.get("stores")
                if not isinstance(stores, list) or len(stores) != 1:
                    continue
                shop_nm = _get_str(stores[0], "shop_nm") or "선택된 매장"
                return {
                    "type": "data",
                    "template": "quickReply",
                    "assistant_response_source": "code_mapper",
                    "data": {
                        "assistantResponse": f"현재 조건으로는 {shop_nm}만 예약 가능해요. 다른 지역으로도 찾아드릴까요?",
                        "quickReplies": [
                            {"label": "다른 지역 찾기", "domain": "TRANSACTION"},
                            {"label": "다른 상품 보기", "domain": "DISCOVERY"},
                        ],
                        "predictedDomains": ["TRANSACTION"],
                    },
                }
        for entry in _find_entries(tool_data_list, "transaction_store_preview_tool"):
            raw = _unwrap(entry)
            if not isinstance(raw, dict):
                continue
            schedule = raw.get("schedule") if isinstance(raw.get("schedule"), dict) else {}
            schedule_stores = schedule.get("stores") if isinstance(schedule, dict) else None
            schedule_empty = (
                _get_str(schedule, "tier").lower() == "none"
                or (isinstance(schedule_stores, list) and not schedule_stores)
            )
            if not schedule_empty:
                continue
            # DETERMINISTIC GUARD on the tool response (region search or
            # multi-candidate tier=none) — the tool already instructed the
            # agent to STOP and render `location`. Fall through to the
            # location render below so the candidate list reaches the FE.
            stores = raw.get("stores")
            args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
            candidate_ids = schedule.get("candidate_shop_ids") or raw.get("candidate_shop_ids") or []
            if isinstance(stores, list) and stores and not (
                isinstance(args, dict) and args.get("store_nm") and len(stores) == 1 and candidate_ids
            ):
                break
            if raw.get("instruction_to_agent"):
                break
            # candidate_shop_ids non-empty (single named-store case) means future
            # slots may exist — let the agent call get_store_schedule_tool for a
            # datepick instead of dead-ending here.
            if candidate_ids:
                return None
            store_nm = _get_str(args, "store_nm") if isinstance(args, dict) else ""
            short = (assistant_text or "").strip()
            if not short or len(short) > 120:
                short = (
                    f"{store_nm} 기준으로 오늘 장착 가능 일정이 확인되지 않았어요."
                    if store_nm
                    else "근처 매장에서 오늘 장착 가능 일정이 확인되지 않았어요."
                )
            return {
                "type": "data",
                "template": "quickReply",
                "assistant_response_source": "code_mapper",
                "data": {
                    "assistantResponse": short,
                    "quickReplies": [
                        {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
                        {"label": "다른 날짜 확인", "domain": "TRANSACTION"},
                    ],
                    "predictedDomains": ["TRANSACTION"],
                },
            }

    # Flow 5 General — info-only store attribute query (운영시간/주소/전화/휴무일/
    # 서비스 가능 여부/올마이T·T바로배송·수입차 가능 등). When no booking signal
    # ran this turn AND the active goal isn't booking-followup AND isn't list
    # browsing (`store_finder`), the user is asking ABOUT a specific store, not
    # picking one. The agent's text answer carries the response; rendering a
    # single-item clickable card implies a selection action that doesn't exist
    # and risks showing default-False fields (tnaDelivery/todayInstall) as if
    # they were authoritative when the list endpoint simply omits them.
    complex_has_schedule_filter = False
    for entry in _find_entries(tool_data_list, "search_stores_complex_tool"):
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        raw = _unwrap(entry)
        stores = raw.get("stores") if isinstance(raw, dict) else None
        complex_has_schedule_filter = bool(
            isinstance(args, dict)
            and (args.get("cal_days") or args.get("open_only") or args.get("time_after_hour") is not None)
        ) or bool(
            isinstance(stores, list)
            and any(isinstance(store, dict) and (store.get("slots") or store.get("is_open") is not None) for store in stores)
        )
        if complex_has_schedule_filter:
            break
    has_booking_signal = bool(called_tools & _BOOKING_SIGNAL_TOOLS) or complex_has_schedule_filter
    is_list_browsing = current_goal_type.get() == "store_finder"
    # Booking-implying intents that arrived via casual conversation ("구매한다고",
    # "재고 확인해줘", "와이퍼 예약좀") rather than the formal goal checklist.
    # ⚠️ ContextVar holds the raw `PendingIntent` enum value
    # ("price"/"stock"/"order"/"reservation"), NOT the Korean prompt labels
    # ("주문 진행"/"재고 확인"/"방문 예약"). Compare against enum values.
    # "reservation" is included so 매장 방문 예약 (와이퍼/배터리/얼라인먼트 등 부가
    # 서비스 예약 포함) 컨텍스트에서 location 카드가 isBookingFlow=true 로 emit되어
    # FE 매장 클릭이 /chat chain (다음 step datepick) 으로 이어진다.
    plain_store_search_user_text = _is_plain_store_search_user_text()
    has_booking_intent = (
        current_pending_intent.get() in ("order", "stock", "reservation") and not plain_store_search_user_text
    )
    # 단골매장 조회는 사용자가 직접 발화로 요청한 명시적 컨텍스트 — booking signal/
    # intent 가 없어도 항상 카드 노출 (info-only guard 우회). 1건이라도 사용자가
    # 클릭으로 선택해야 다음 단계로 진행됨.
    has_favorite_stores = "get_favorite_stores_tool" in called_tools
    if (
        not has_booking_signal
        and not _is_goal_booking_followup()
        and not is_list_browsing
        and not has_booking_intent
        and not has_favorite_stores
        and not _looks_like_location_selection_prompt(assistant_text)
    ):
        return None

    # Build shop_id → detail map from same-turn `get_store_detail_tool` calls.
    # `get_store_detail_tool` carries the rich fields the list endpoint omits
    # (tel_no, holiday, is_tna_delivery), so when the agent calls both in the
    # same turn — explicitly the "store info / store selection" flow — we merge
    # them into a single richer description. The detail response itself does
    # NOT include shop_id, so we correlate via the tool's input `args.shop_id`.
    detail_by_shop_id: dict[str, dict] = {}
    for entry in _find_entries(tool_data_list, "get_store_detail_tool"):
        args = entry.get("args") or {}
        shop_id = _get_str(args, "shop_id") if isinstance(args, dict) else ""
        if not shop_id:
            continue
        raw = _unwrap(entry)
        if isinstance(raw, dict):
            detail_by_shop_id[shop_id] = raw

    preference_text = (current_user_preferences_text.get() or "").strip()
    require_ev_specialty, require_ev_charge = _requested_store_specialty_filters(preference_text)

    stock_filter_context = (
        not plain_store_search_user_text
        and (
            current_pending_intent.get() == "stock"
            or current_goal_type.get() == "store_with_stock"
            or bool(re.search(r"재고\s*(있는|가\s*확인된)\s*매장|재고있는\s*매장", assistant_text or ""))
        )
    )
    items, metadata = [], []
    stock_filtered_preview = False
    stock_filtered_region = ""
    other_store_request = _is_other_store_request()
    excluded_store_ids = current_excluded_store_ids.get() if other_store_request else set()
    exact_schedule_filter = _requested_exact_schedule_filter()
    had_location_candidate = False
    filtered_by_exact_time = False
    filtered_by_other_store = False
    filtered_by_today_schedule = False
    earliest_filtered_schedule_label = ""
    for entry in _find_entries(
        tool_data_list,
        "search_stores_tool",
        "search_stores_complex_tool",
        "get_store_list_tool",
        "get_nearby_stores_tool",
        "transaction_store_preview_tool",
        "get_favorite_stores_tool",
    ):
        raw = _unwrap(entry)
        if not isinstance(raw, dict):
            continue
        stores = raw.get("stores")
        if not isinstance(stores, list):
            continue
        stock_labels_by_shop_id: dict[str, str] = {}
        preview_today_schedule_by_shop_id: dict[str, dict] = {}
        if entry.get("tool") == "transaction_store_preview_tool" and _today_service_context(assistant_text):
            preview_today_schedule_by_shop_id = _preview_schedule_stores_by_shop_id(raw)
            earliest_filtered_schedule_label = earliest_filtered_schedule_label or _earliest_preview_schedule_label(raw)
        if entry.get("tool") in {
            "search_stores_tool",
            "search_stores_complex_tool",
            "get_store_list_tool",
            "get_nearby_stores_tool",
        }:
            if inventory_stock_labels and stock_filter_context:
                stock_labels_by_shop_id.update(inventory_stock_labels)
                args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
                if isinstance(args, dict) and not stock_filtered_region:
                    stock_filtered_region = _get_str(args, "region_code") or _get_str(args, "place_query")
        if entry.get("tool") == "transaction_store_preview_tool" and stock_filter_context:
            today_ids = _inventory_shop_ids(raw.get("inventory"), "todayShopArray")
            tna_ids = _inventory_shop_ids(raw.get("inventory"), "tnaShopArray")
            for sid in today_ids:
                stock_labels_by_shop_id[sid] = "매장재고"
            for sid in tna_ids:
                stock_labels_by_shop_id.setdefault(sid, "T바로배송")
            if stock_labels_by_shop_id:
                stock_filtered_preview = True
                args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
                if isinstance(args, dict):
                    stock_filtered_region = _get_str(args, "region_code")
        if inventory_stock_labels and stock_filter_context:
            stock_filtered_preview = True

        for row in stores:
            if not isinstance(row, dict):
                continue
            shop_id = _get_str(row, "shop_id")
            if not shop_id:
                continue
            had_location_candidate = True
            if shop_id in excluded_store_ids:
                filtered_by_other_store = True
                continue
            stock_label = stock_labels_by_shop_id.get(shop_id)
            if stock_labels_by_shop_id and not stock_label:
                continue
            preview_schedule_store = preview_today_schedule_by_shop_id.get(shop_id)
            if preview_schedule_store is not None:
                today_yyyymmdd = _kst_today_yyyymmdd()
                if not _store_has_bookable_slot_on_day(preview_schedule_store, today_yyyymmdd):
                    filtered_by_today_schedule = True
                    continue
                today_slots = [
                    slot
                    for slot in preview_schedule_store.get("slots", [])
                    if isinstance(slot, dict) and _get_str(slot, "cal_day") == today_yyyymmdd
                ]
                if today_slots:
                    row = {**row, "slots": today_slots}
            row_slots_for_filter = row.get("slots") if isinstance(row.get("slots"), list) else []
            if exact_schedule_filter is not None and row_slots_for_filter:
                filtered_slots = [
                    slot
                    for slot in row_slots_for_filter
                    if isinstance(slot, dict) and _slot_matches_exact_filter(slot, exact_schedule_filter)
                ]
                if not filtered_slots:
                    filtered_by_exact_time = True
                    continue
                row = {**row, "slots": filtered_slots}

            detail = detail_by_shop_id.get(shop_id, {})

            road_base = _get_str(row, "road_addr_base")
            road_dtl = _get_str(row, "road_addr_dtl")
            road_full = " ".join(p for p in [road_base, road_dtl] if p).strip()
            # Fallback when no road address — combine base + dtl so the user
            # sees the full address ("경상남도 거창군 거창읍 강남로 72") instead
            # of just the prefecture/gu portion ("경상남도 거창군").
            jibun_base = _get_str(row, "addr_base")
            jibun_dtl = _get_str(row, "addr_dtl")
            jibun_full = " ".join(p for p in [jibun_base, jibun_dtl] if p).strip()
            detail_addr = road_full or jibun_full

            # Detail endpoint overrides the list endpoint where overlapping (it
            # is the more authoritative source for is_all_my_t / is_installable
            # at lookup time).
            is_all_my_t = bool(detail.get("is_all_my_t", row.get("is_all_my_t", False)))
            is_installable = bool(detail.get("is_installable", row.get("is_installable", False)))
            is_tna_delivery = bool(detail.get("is_tna_delivery", False))
            is_ev_specialty = bool(detail.get("is_ev_specialty", row.get("is_ev_specialty", False)))
            is_ev_charge_available = bool(
                detail.get("is_ev_charge_available", row.get("is_ev_charge_available", False))
            )
            if require_ev_specialty and not is_ev_specialty:
                continue
            if require_ev_charge and not is_ev_charge_available:
                continue

            biz_strt_wday = _get_str(detail, "shop_biz_strt_wday") or _get_str(row, "shop_biz_strt_wday")
            biz_end_wday = _get_str(detail, "shop_biz_end_wday") or _get_str(row, "shop_biz_end_wday")
            biz_wday = f"{biz_strt_wday}~{biz_end_wday}" if biz_strt_wday and biz_end_wday else ""

            biz_strt_time = _normalize_time(_get_str(detail, "shop_biz_strt_time") or _get_str(row, "shop_biz_strt_time"))
            biz_end_time = _normalize_time(_get_str(detail, "shop_biz_end_time") or _get_str(row, "shop_biz_end_time"))
            sat_strt_time = _normalize_time(_get_str(detail, "shop_sat_strt_time") or _get_str(row, "shop_sat_strt_time"))
            sat_end_time = _normalize_time(_get_str(detail, "shop_sat_end_time") or _get_str(row, "shop_sat_end_time"))
            biz_weekday_str = f"평일 {biz_strt_time}~{biz_end_time}" if biz_strt_time and biz_end_time else ""
            biz_sat_str = f"토요일 {sat_strt_time}~{sat_end_time}" if sat_strt_time and sat_end_time else ""
            biz_hours = " / ".join(p for p in [biz_weekday_str, biz_sat_str] if p)

            # tel_no: prefer detail (most authoritative when get_store_detail_tool
            # ran in the same turn), fall back to the list row so basic store
            # search results always show the phone number.
            tel_no = _get_str(detail, "tel_no") or _get_str(row, "tel_no")
            holiday = _get_str(detail, "holiday")
            rating = _get_num(detail, "rating_idx", default=0.0) or _get_num(row, "rating_idx", default=0.0)
            review_count_raw = detail.get("review_count")
            if review_count_raw is None:
                review_count_raw = row.get("review_count")
            try:
                review_count = int(review_count_raw) if review_count_raw is not None else None
            except (TypeError, ValueError):
                review_count = None

            services: list[str] = []
            if is_all_my_t:
                services.append("올마이T")
            services.append("온라인 장착 가능" if is_installable else "온라인 장착 불가")
            if is_tna_delivery:
                services.append("T바로배송")
            services.extend(
                _store_specialty_labels(
                    is_ev_specialty=is_ev_specialty,
                    is_ev_charge_available=is_ev_charge_available,
                )
            )
            # 매장 보유 svc_codes (BE 화이트리스트: 113/116/119/120/121/122/124/125/126)
            # 를 사용자 라벨로 변환해 description 의 "서비스:" 라인에 노출.
            svc_codes_raw = detail.get("svc_codes") or row.get("svc_codes")
            services.extend(_svc_code_label_list(svc_codes_raw))
            services_text = " | ".join(services)

            description_lines: list[str] = []
            if road_full:
                description_lines.append(f"📍 {road_full}")
            if biz_wday:
                description_lines.append(f"영업일: {biz_wday}")
            if biz_hours:
                description_lines.append(f"영업시간: {biz_hours}")
            if holiday:
                description_lines.append(f"휴무일: {holiday}")
            if tel_no:
                description_lines.append(f"전화: {tel_no}")
            if rating:
                description_lines.append(f"⭐ {rating:.1f}")
            if review_count is not None:
                description_lines.append(f"리뷰 {review_count}건")
            if services_text:
                description_lines.append(f"서비스: {services_text}")
            row_slots = row.get("slots") if isinstance(row.get("slots"), list) else []
            slots_by_day: dict[str, set[int]] = {}
            for slot in row_slots:
                if not isinstance(slot, dict):
                    continue
                cal_day = _get_str(slot, "cal_day")
                hour = _parse_tm_to_hour(_get_str(slot, "tm"))
                if cal_day and hour is not None and _is_bookable_hour(hour):
                    slots_by_day.setdefault(cal_day, set()).add(hour)
            if slots_by_day:
                first_day = sorted(slots_by_day.keys())[0]
                slot_text = ", ".join(f"{hour:02d}:00" for hour in sorted(slots_by_day[first_day])[:5])
                description_lines.append(f"예약 가능일: {yyyymmdd_to_korean_date(first_day)}")
                if slot_text:
                    description_lines.append(f"예약 가능 시간: {slot_text}")
            if stock_label:
                description_lines.append(f"[{stock_label}]")
            description = "\n ".join(description_lines)

            distance_km = row.get("distance_km")
            distance_str = f"{distance_km:.1f}km" if isinstance(distance_km, (int, float)) else ""

            # `todayInstall` is the today-only variant of stock availability.
            # The list endpoint cannot tell us; the detail endpoint signals it
            # only indirectly via `available_slots` for cal_day=TODAY. Leave
            # False — over-claiming "today install" is worse than understating.
            items.append({
                "nameAddress": _get_str(detail, "shop_nm") or _get_str(row, "shop_nm", default=shop_id),
                "distance": distance_str,
                "detailAddress": detail_addr,
                "isAllMyT": is_all_my_t,
                "todayInstall": is_all_my_t and stock_label == "매장재고",
                "tnaDelivery": is_tna_delivery or stock_label == "T바로배송",
                "description": description,
            })
            metadata.append({"shopId": shop_id})

    if not items:
        if filtered_by_today_schedule:
            earliest_suffix = (
                f" 가장 빠른 예약 가능 일정은 {earliest_filtered_schedule_label}부터예요."
                if earliest_filtered_schedule_label
                else ""
            )
            return {
                "type": "data",
                "template": "quickReply",
                "assistant_response_source": "code_mapper_today_schedule_filter",
                "data": {
                    "assistantResponse": f"오늘 장착 가능한 매장 일정이 확인되지 않아요.{earliest_suffix} 다른 날짜나 다른 매장으로 확인해 주세요.",
                    "quickReplies": [
                        {"label": "다른 날짜 확인", "domain": "TRANSACTION"},
                        {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
                    ],
                    "predictedDomains": ["TRANSACTION"],
                },
            }
        if filtered_by_exact_time:
            return _exact_time_no_slot_quickreply()
        if other_store_request and filtered_by_other_store and had_location_candidate:
            return {
                "type": "data",
                "template": "quickReply",
                "assistant_response_source": "code_mapper_other_store",
                "data": {
                    "assistantResponse": "앞서 안내한 매장 외에 추가로 확인되는 매장이 없어요. 다른 지역으로 확인해 주세요.",
                    "quickReplies": [
                        {"label": "다른 지역 찾기", "domain": "TRANSACTION"},
                        {"label": "처음으로", "domain": "LEADING"},
                    ],
                    "predictedDomains": ["TRANSACTION"],
                },
            }
        if require_ev_specialty or require_ev_charge:
            requested_region = ""
            for entry in _find_entries(
                tool_data_list,
                "search_stores_tool",
                "search_stores_complex_tool",
                "get_store_list_tool",
                "get_nearby_stores_tool",
                "transaction_store_preview_tool",
            ):
                args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
                if not isinstance(args, dict):
                    continue
                requested_region = (
                    _get_str(args, "place_query")
                    or _get_str(args, "region_code")
                    or _get_str(args, "store_nm")
                )
                if requested_region:
                    break
            return _store_specialty_no_match_quickreply(
                requested_region,
                require_ev_specialty=require_ev_specialty,
                require_ev_charge=require_ev_charge,
            )
        return None
    store_limit = _store_result_limit(tool_data_list)
    items, metadata = items[:store_limit], metadata[:store_limit]

    # In order context, when the agent calls get_store_list_tool with a
    # `store_nm` arg (user named a specific branch) and gets back exactly 1
    # store, this is a shop_id resolution turn — the user already selected a
    # store from a previously shown list and the agent is resolving the name
    # to an ID before calling inventory/schedule tools. Rendering the card
    # again creates an infinite loop because the FE re-sends the store name
    # on each click. Region-only searches (`region_code=...`) that happen to
    # yield 1 store do NOT loop — the user hasn't named that store yet, so
    # we must render the card for selection.
    called_with_store_nm = False
    for entry in _find_entries(tool_data_list, "search_stores_tool", "search_stores_complex_tool", "get_store_list_tool"):
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        if isinstance(args, dict) and args.get("store_nm"):
            called_with_store_nm = True
            break
    is_shopid_resolution = (
        called_with_store_nm
        and has_booking_intent
        and len(items) == 1
        and "get_nearby_stores_tool" not in called_tools
        and "search_place_tool" not in called_tools
    )
    if is_shopid_resolution:
        return None

    # `isBookingFlow` controls FE click routing (True → /chat to advance the
    # flow; False → /append, just renders the description bubble). True when
    # either: (a) this turn explicitly carries a transactional signal —
    # inventory, schedule, price, cart, or order tool ran together with the
    # store list; or (b) the request-scoped goal_type is one of
    # store_with_stock / place_order / price_inquiry, meaning a downstream
    # tool call must follow the user's pick even if that tool didn't run in
    # this turn (e.g., inventory check fires AFTER store selection).
    # Pure Flow 4/5 info lookups with no goal still stay False so clicking a
    # card surfaces the rich description without spuriously advancing.
    is_booking_flow = (
        has_booking_signal
        or (_is_goal_booking_followup() and not plain_store_search_user_text)
        or has_booking_intent
        or current_return_visit_store_flow.get()
    )

    guarded_preview_region = ""
    guarded_preview_is_order = False
    preview_schedule_tier = ""
    preview_schedule_region = ""
    for entry in _find_entries(tool_data_list, "transaction_store_preview_tool"):
        raw = _unwrap(entry)
        schedule = raw.get("schedule") if isinstance(raw.get("schedule"), dict) else {}
        schedule_stores = schedule.get("stores") if isinstance(schedule, dict) else None
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        if (
            not preview_schedule_tier
            and isinstance(schedule_stores, list)
            and schedule_stores
        ):
            preview_schedule_tier = _get_str(schedule, "tier").lower()
            preview_schedule_region = _get_str(args, "region_code") if isinstance(args, dict) else ""
        if not isinstance(raw, dict) or not raw.get("instruction_to_agent"):
            continue
        schedule_empty = (
            _get_str(schedule, "tier").lower() == "none"
            or (isinstance(schedule_stores, list) and not schedule_stores)
        )
        if not schedule_empty:
            continue
        guarded_preview_region = _get_str(args, "region_code") if isinstance(args, dict) else ""
        guarded_preview_is_order = current_pending_intent.get() == "order"
        break

    short, response_source = _summarize_with_source(assistant_text, "location", len(items))
    if stock_filtered_preview and items:
        short = (
            f"{stock_filtered_region}에서 오늘 장착 가능한 매장입니다. 원하시는 매장을 선택해 주세요."
            if stock_filtered_region
            else "오늘 장착 가능한 매장입니다. 원하시는 매장을 선택해 주세요."
        )
        response_source = "code_mapper"
    elif require_ev_specialty or require_ev_charge:
        requested_region = ""
        for entry in _find_entries(
            tool_data_list,
            "search_stores_tool",
            "search_stores_complex_tool",
            "get_store_list_tool",
            "get_nearby_stores_tool",
        ):
            args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
            if not isinstance(args, dict):
                continue
            requested_region = _get_str(args, "place_query") or _get_str(args, "region_code")
            if requested_region:
                break
        specialty_short = _store_specialty_response_text(
            requested_region,
            len(items),
            require_ev_specialty=require_ev_specialty,
            require_ev_charge=require_ev_charge,
        )
        if specialty_short:
            short = specialty_short
            response_source = "code_mapper"
    elif guarded_preview_is_order and items:
        short = (
            f"{guarded_preview_region} 근처 주문 가능한 매장입니다. 원하시는 매장을 선택해 주세요."
            if guarded_preview_region
            else "주문 가능한 매장입니다. 원하시는 매장을 선택해 주세요."
        )
        response_source = "code_mapper"
    elif preview_schedule_tier and items:
        preview_short = _preview_location_assistant_response(
            preview_schedule_tier,
            preview_schedule_region,
            len(items),
        )
        if preview_short:
            short = preview_short
            response_source = "code_mapper"
    elif quality_short := _store_quality_preference_response_text(tool_data_list, len(items)):
        short = quality_short
        response_source = "code_mapper"
    elif has_booking_intent and items:
        today_prefix = "오늘 " if re.search(r"오늘|당일|지금|바로|당장", current_user_text.get() or "") else ""
        short = f"요청하신 조건으로 {today_prefix}장착 가능 여부가 확인된 매장 {len(items)}곳입니다. 원하시는 매장을 선택해 주세요."
        response_source = "code_mapper"
    elif plain_store_search_user_text and items and re.search(r"오늘\s*장착|장착 가능 여부|재고", short or ""):
        short = f"요청하신 지역의 매장 {len(items)}곳을 안내드립니다. 원하시는 매장을 선택해 주세요."
        response_source = "code_mapper"
    # Favorite-store lookup is an explicit new user request ("내 단골매장").
    # Do not carry over stale special-store preferences such as a previous
    # "리프트 있는 매장" query into this independent list response.
    if not has_favorite_stores:
        short = _maybe_prepend_unverifiable_store_guidance(short)
    return {
        "type": "data",
        "template": "location",
        "assistant_response_source": response_source,
        "data": {
            "stores": items,
            "metadata": metadata,
            "isBookingFlow": is_booking_flow,
            "assistantResponse": short,
        },
    }


def _format_time_filter_slot(slot: object) -> str:
    hour = _parse_tm_to_hour(str(slot))
    return f"{hour:02d}:00" if hour is not None else str(slot)


def _map_time_filter_location(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    for entry in _find_entries(tool_data_list, "get_stores_with_time_filter_tool"):
        raw = _unwrap(entry)
        if not isinstance(raw, dict):
            continue

        stores = raw.get("stores_available")
        if not isinstance(stores, list):
            continue

        region_code = _get_str(raw, "region_code")
        threshold = raw.get("time_threshold_hour")
        kst = datetime.timezone(datetime.timedelta(hours=9))
        today_yyyymmdd = datetime.datetime.now(kst).strftime("%Y%m%d")
        items, metadata = [], []
        for row in stores:
            if not isinstance(row, dict):
                continue
            shop_id = _get_str(row, "shop_id")
            if not shop_id:
                continue

            raw_slots = row.get("qualifying_slots") if isinstance(row.get("qualifying_slots"), list) else []
            slots = [
                s for s in raw_slots
                if (hour := _parse_tm_to_hour(str(s))) is not None and _is_bookable_hour(hour)
            ]
            if not slots:
                continue
            slot_text = ", ".join(_format_time_filter_slot(s) for s in slots[:5])
            cal_day_raw = _get_str(row, "cal_day")
            cal_day = yyyymmdd_to_korean_date(cal_day_raw)
            address = _get_str(row, "address")
            tel = _format_phone(_get_str(row, "tel"))
            rating = _get_num(row, "rating_idx")
            is_all_my_t = bool(row.get("is_all_my_t", False))
            is_tna_delivery = bool(row.get("is_tna_delivery", False))
            today_install = bool(is_all_my_t and cal_day_raw == today_yyyymmdd and slots)
            description_lines: list[str] = []
            if address:
                description_lines.append(f"📍 {address}")
            if cal_day:
                description_lines.append(f"예약 가능일: {cal_day}")
            if slot_text:
                description_lines.append(f"예약 가능 시간: {slot_text}")
            if tel:
                description_lines.append(f"전화: {tel}")
            if rating:
                description_lines.append(f"⭐ {rating:.1f}")

            items.append({
                "nameAddress": _get_str(row, "shop_nm", default=shop_id),
                "distance": "",
                "detailAddress": address,
                "isAllMyT": is_all_my_t,
                "todayInstall": today_install,
                "tnaDelivery": is_tna_delivery,
                "description": "\n ".join(description_lines),
            })
            metadata.append({"shopId": shop_id})

        if not items:
            return {
                "type": "data",
                "template": "quickReply",
                "assistant_response_source": "code_mapper",
                "data": {
                    "assistantResponse": f"{region_code}에서 {threshold}시 이후 예약 가능한 매장이 현재 없어요. 다른 시간대나 지역으로 찾아드릴까요?",
                    "quickReplies": [
                        {"label": "다른 시간대 찾기", "domain": "TRANSACTION"},
                        {"label": "다른 지역 찾기", "domain": "TRANSACTION"},
                        {"label": "처음으로", "domain": "LEADING"},
                    ],
                    "predictedDomains": ["TRANSACTION"],
                },
            }

        items, metadata = items[:10], metadata[:10]
        short, response_source = _summarize_with_source(assistant_text, "location", len(items))
        if not assistant_text.strip():
            short = f"{region_code}에서 {threshold}시 이후 예약 가능한 매장 {len(items)}곳을 안내드립니다. 원하시는 매장을 선택해 주세요."
            response_source = "default"
        return {
            "type": "data",
            "template": "location",
            "assistant_response_source": response_source,
            "data": {
                "stores": items,
                "metadata": metadata,
                "isBookingFlow": True,
                "assistantResponse": short,
            },
        }

    return None


# ── 9. datepick ─────────────────────────────────────────────────────────────────

def _parse_tm_to_hour(tm: str) -> int | None:
    """Parse a BE `tm` slot value to an integer hour (0-23).

    BE OpenAPI spec says `tm` is `HHMM` (e.g. "0900", "1030"), but observed
    runtime payloads also send hour-only ("13"). Accept both, return the hour
    portion. Returns None for unparseable / out-of-range values.
    """
    s = (tm or "").strip()
    if not s.isdigit():
        return None
    if len(s) <= 2:
        h = int(s)
    elif len(s) == 4:
        h = int(s[:2])
    else:
        return None
    return h if 0 <= h <= 23 else None


def _is_bookable_hour(hour: int) -> bool:
    """Return whether a parsed hour may be shown as a selectable booking slot."""
    return hour != 12


def _requested_exact_schedule_filter() -> tuple[set[str], int] | None:
    """Return requested exact schedule days/hour from recent user text.

    "9시" asks for the 9 o'clock slot. "9시 이후/부터" is a range request and is
    intentionally left to existing time_after_hour handling.
    """
    text = current_user_text.get() or ""
    selected_text = text
    match = None
    for line in reversed([line.strip() for line in text.splitlines() if line.strip()]):
        line_matches = list(_EXACT_TIME_REQUEST_RE.finditer(line))
        if line_matches:
            selected_text = line
            match = line_matches[-1]
            break
    if match is None:
        matches = list(_EXACT_TIME_REQUEST_RE.finditer(text))
        match = matches[-1] if matches else None
    if not match:
        return None
    try:
        hour = int(match.group("hour"))
    except (TypeError, ValueError):
        return None
    prefix = match.group("prefix") or ""
    if prefix in {"오후", "저녁", "밤"} and 1 <= hour <= 11:
        hour += 12
    if not (0 <= hour <= 23):
        return None

    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()
    days: set[str] = set()
    date_text = selected_text if re.search(r"오늘|당일|내일", selected_text) else text
    if re.search(r"오늘|당일", date_text):
        days.add(today.strftime("%Y%m%d"))
    if "내일" in date_text:
        days.add((today + datetime.timedelta(days=1)).strftime("%Y%m%d"))
    return days, hour


def _slot_matches_exact_filter(slot: dict, exact_filter: tuple[set[str], int] | None) -> bool:
    if exact_filter is None:
        return True
    days, requested_hour = exact_filter
    cal_day = _get_str(slot, "cal_day")
    hour = _parse_tm_to_hour(_get_str(slot, "tm"))
    if hour != requested_hour:
        return False
    return not days or cal_day in days


def _exact_time_no_slot_quickreply(shop_nm: str = "") -> dict:
    exact_filter = _requested_exact_schedule_filter()
    hour_text = ""
    if exact_filter is not None:
        hour_text = f" {exact_filter[1]}시"
    subject = f"{shop_nm}은" if shop_nm else "요청하신 조건에서는"
    return {
        "type": "data",
        "template": "quickReply",
        "assistant_response_source": "code_mapper_exact_time",
        "data": {
            "assistantResponse": f"{subject} 해당 날짜{hour_text} 예약 가능 시간이 확인되지 않아요. 다른 시간이나 다른 매장으로 확인해 주세요.",
            "quickReplies": [
                {"label": "다른 시간 확인", "domain": "TRANSACTION"},
                {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["TRANSACTION"],
        },
    }


def _map_datepick_from_preview(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Build a date picker from transaction_store_preview_tool schedule slots.

    The preview tool can already resolve the only installable store and its
    slots. In booking/order contexts, rendering all candidate stores as a
    location card makes the user pick among stores that may not have matching
    inventory. Keep stock-check contexts on the location path, where the card
    intentionally shows the stock-positive store list.
    """
    if _is_other_store_request():
        return None

    for entry in reversed(_find_entries(tool_data_list, "transaction_store_preview_tool")):
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        args = args if isinstance(args, dict) else {}
        exact_order_preview = bool(
            _get_str(args, "store_nm")
            and _get_str(args, "goods_no")
            and args.get("ord_qty")
            and args.get("include_price")
        )
        pending_intent = current_pending_intent.get()
        goal_type = current_goal_type.get()
        if should_keep_stock_location(
            pending_intent=pending_intent,
            goal_type=goal_type,
            assistant_text=assistant_text or "",
            exact_order_preview=exact_order_preview,
        ):
            return None

        raw = _unwrap(entry)
        if not isinstance(raw, dict):
            continue
        event = build_datepick_from_preview_payload(
            raw,
            assistant_text=assistant_text,
            assistant_response_source="code_mapper",
            require_single_store=True,
        )
        if event:
            schedule = raw.get("schedule") if isinstance(raw.get("schedule"), dict) else {}
            schedule_tier = _get_str(schedule, "tier").lower()
            force_today_service_response = (
                schedule_tier in {"tna_only", "logistics_only"} and _preview_schedule_starts_after_today(raw)
            )
            today_service_response = _today_service_datepick_response(event, force=force_today_service_response)
            if today_service_response:
                event["assistant_response_source"] = "code_mapper_today_service"
                event["data"]["assistantResponse"] = today_service_response
                return event
            dates = event.get("data", {}).get("dates", [])
            short, response_source = _summarize_with_source(assistant_text, "datepick", len(dates))
            event["assistant_response_source"] = response_source
            event["data"]["assistantResponse"] = short
            return event
    return None


def _map_datepick(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Map slot-emitting tools to a `datepick` event.

    Three sources supported:

    1. ``get_store_schedule_tool`` (StoreScheduleResponse):
       ``{shop_id, shop_nm, mode, is_installable, is_tna_delivery,
       slots: [{cal_day, tm}, ...]}`` — flat list grouped by day.

    2. ``get_store_detail_tool`` (Flow 5.1 / 5.5 single-day lookup):
       response has ``available_slots`` (hour strings, e.g. ``["09","10"]``)
       and the ``cal_day`` is taken from the tool's input args. Without this
       path the agent's intended datepick gets overridden by the location
       mapper when a sibling ``transaction_store_preview_tool`` ran.

    3. ``transaction_store_preview_tool`` (single resolved schedule store):
       response has ``schedule.stores[0].slots`` and can go straight to
       datepick in booking/order contexts.

    Schedule-tool path wins when both are present (richer multi-day shape).
    """
    transaction_decision = current_transaction_response_decision.get()
    if transaction_decision and (
        transaction_decision.forbids("datepick_for_unverified_store")
        or transaction_decision.forbids("datepick_for_unavailable_stock")
    ):
        return None
    if _same_turn_inventory_has_no_stock(tool_data_list) and (
        current_pending_intent.get() == "stock" or current_goal_type.get() == "store_with_stock"
    ) and not _same_turn_logistics_schedule_has_slots(tool_data_list):
        return None

    entries = _find_entries(tool_data_list, "get_store_schedule_tool")
    if not entries:
        return _map_datepick_from_preview(tool_data_list, assistant_text) or _map_datepick_from_detail(
            tool_data_list,
            assistant_text,
        )
    raw = _unwrap(entries[-1])
    if not isinstance(raw, dict):
        return _map_datepick_from_preview(tool_data_list, assistant_text) or _map_datepick_from_detail(
            tool_data_list,
            assistant_text,
        )

    shop_id = _get_str(raw, "shop_id")
    shop_nm = _get_str(raw, "shop_nm")
    slots = raw.get("slots")
    if not shop_id or not isinstance(slots, list):
        return _map_datepick_from_preview(tool_data_list, assistant_text) or _map_datepick_from_detail(
            tool_data_list,
            assistant_text,
        )

    # `is_installable` means online-shopping tire installation support. It
    # should block tire/order schedule modes, but not store-visit style modes
    # where the backend's returned slots are already the authoritative answer.
    mode = _get_str(raw, "mode").lower()
    allow_slots = bool(raw.get("is_installable", True)) or mode in {"general", "logistics_only"}

    # Group slots by cal_day, dedupe to hour integers. BE returns ascending,
    # but we sort cal_day strings before emitting to avoid relying on that.
    min_install_date = _same_turn_reservation_sale_min_install_date(tool_data_list, shop_id)
    exact_filter = _requested_exact_schedule_filter()
    by_day: dict[str, set[int]] = {}
    for s in slots:
        if not isinstance(s, dict):
            continue
        if not _slot_matches_exact_filter(s, exact_filter):
            continue
        cal_day = _get_str(s, "cal_day")
        hour = _parse_tm_to_hour(_get_str(s, "tm"))
        if not cal_day or hour is None:
            continue
        if min_install_date and cal_day < min_install_date:
            continue
        bucket = by_day.setdefault(cal_day, set())
        if allow_slots and _is_bookable_hour(hour):
            bucket.add(hour)

    if not by_day:
        if exact_filter is not None:
            return _exact_time_no_slot_quickreply(shop_nm)
        return None

    dates: list[dict] = []
    selected_idx: int | None = None
    for i, cal_day in enumerate(sorted(by_day.keys())):
        times = sorted(by_day[cal_day])
        available = bool(times)
        dates.append({
            "date": yyyymmdd_to_korean_date(cal_day),
            "available": available,
            "availableTimes": times,
            "index": i,
        })
        if selected_idx is None and available:
            selected_idx = i

    # All days empty → let the LLM emit the "no slots" friendly quickReply
    # ("현재 예약 가능한 시간이 없어요. 다른 날짜를 확인해 보시겠어요?").
    if selected_idx is None:
        return None

    metadata: dict = {"shopId": shop_id}
    if shop_nm:
        metadata["shopName"] = shop_nm
    event = {
        "type": "data",
        "template": "datepick",
        "data": {
            "dates": dates,
            "selectedDate": selected_idx,
            "metadata": metadata,
        },
    }
    today_service_response = _today_service_datepick_response(event)
    if today_service_response:
        event["assistant_response_source"] = "code_mapper_today_service"
        event["data"]["assistantResponse"] = today_service_response
        return event
    short, response_source = _summarize_with_source(assistant_text, "datepick", len(dates))
    event["assistant_response_source"] = response_source
    event["data"]["assistantResponse"] = short
    return event


def _map_datepick_from_detail(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Build a single-day `datepick` from `get_store_detail_tool` slots.

    Detail-tool response carries ``available_slots`` (hour strings) for one
    cal_day; cal_day itself isn't in the response, so we read it from the
    tool's input args. Falls back to None when args.cal_day is missing or
    slots are empty/unparseable.

    Intent guard: when the same turn carries no booking-signal tool and the
    user did not ask about a specific date's opening/availability, treat it as
    plain store info. Returning None lets `_map_store_detail_info` render the
    info card instead of an unwanted reservation picker.
    """
    called_tools = {e.get("tool", "") for e in tool_data_list}
    treat_as_datepick = _should_treat_store_detail_slots_as_datepick()
    if not (called_tools & _BOOKING_SIGNAL_TOOLS) and not treat_as_datepick:
        return None
    for entry in _find_entries(tool_data_list, "get_store_detail_tool"):
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        if not isinstance(args, dict):
            continue
        cal_day = _get_str(args, "cal_day")
        shop_id = _get_str(args, "shop_id")
        if not cal_day or not shop_id:
            continue
        min_install_date = _same_turn_reservation_sale_min_install_date(tool_data_list, shop_id)
        if min_install_date and cal_day < min_install_date:
            return _reservation_sale_date_quickreply(min_install_date)
        raw = _unwrap(entry)
        if not isinstance(raw, dict):
            continue
        slot_strs = raw.get("available_slots")
        if not isinstance(slot_strs, list) or not slot_strs:
            continue
        exact_filter = _requested_exact_schedule_filter()
        hours: list[int] = []
        for s in slot_strs:
            h = _parse_tm_to_hour(str(s))
            if exact_filter is not None and h != exact_filter[1]:
                continue
            if h is not None and _is_bookable_hour(h):
                hours.append(h)
        hours = sorted(set(hours))
        if not hours:
            if exact_filter is not None:
                return _exact_time_no_slot_quickreply(_get_str(raw, "shop_nm"))
            continue
        shop_nm = _get_str(raw, "shop_nm")
        metadata: dict = {"shopId": shop_id}
        if shop_nm:
            metadata["shopName"] = shop_nm
        if treat_as_datepick:
            date_label = yyyymmdd_to_korean_date(cal_day)
            shop_label = f"{shop_nm}은" if shop_nm else "해당 매장은"
            short = f"{date_label} {shop_label} 영업하며 예약 가능한 시간이 있습니다."
            response_source = "code_mapper"
        else:
            response_source = "llm_prose"
            short = ""
        event = {
            "type": "data",
            "template": "datepick",
            "data": {
                "dates": [{
                    "date": yyyymmdd_to_korean_date(cal_day),
                    "available": True,
                    "availableTimes": hours,
                    "index": 0,
                }],
                "selectedDate": 0,
                "metadata": metadata,
            },
        }
        if treat_as_datepick:
            event["assistant_response_source"] = response_source
            event["data"]["assistantResponse"] = short
            return event
        today_service_response = _today_service_datepick_response(event)
        if today_service_response:
            event["assistant_response_source"] = "code_mapper_today_service"
            event["data"]["assistantResponse"] = today_service_response
            return event
        short, response_source = _summarize_with_source(assistant_text, "datepick", 1)
        event["assistant_response_source"] = response_source
        event["data"]["assistantResponse"] = short
        return event
    return None


# ── 10. orderComplete ───────────────────────────────────────────────────────────

def _map_order_complete(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """save_to_cart_tool / quick_order_tool 결과를 orderComplete 카드로 변환.

    cart 흐름은 LLM 의 fenced JSON 생성에 의존하면 종종 누락되어 base_agent 의
    `_VALIDATION_FALLBACK_QUICK_REPLIES` 경로로 빠지면서 ["다시 시도", "상담사 연결",
    "처음으로"] chips 가 사용자에게 노출됐다. 이 mapper 가 결정적으로 카드를
    만들어 fallback 경로 자체를 우회한다.
    """
    entries = _find_entries(tool_data_list, "save_to_cart_tool", "quick_order_tool")
    if not entries:
        return None
    entry = entries[-1]
    flow_type = "cart" if entry.get("tool") == "save_to_cart_tool" else "order"

    args = entry.get("args") if isinstance(entry.get("args"), dict) else {}
    goods_no = _get_str(args, "goods_no")
    if not goods_no:
        return None
    ord_qty = int(_get_num(args, "ord_qty", default=0)) or 1
    shop_id = _get_str(args, "shop_id")
    car_lnc_cd = _get_str(args, "car_lnc_cd")

    raw = _unwrap(entry)
    is_success = bool(raw.get("result")) if isinstance(raw, dict) else False
    outer = entry.get("data") if isinstance(entry.get("data"), dict) else {}
    if outer.get("status") == "error":
        is_success = False
    result_message = _get_str(raw, "message") if isinstance(raw, dict) else ""
    is_already_in_cart = bool(result_message and _CART_ALREADY_EXISTS_RE.search(result_message))

    ord_no: str | None = None
    if isinstance(raw, dict):
        inner = raw.get("data")
        if isinstance(inner, str) and inner.strip():
            ord_no = inner.strip()
        elif isinstance(inner, dict):
            ord_no = _get_str(inner, "ord_no", "ordNo") or None

    # Enrich product label from same-turn product/recommend/cheapest tool data.
    # 사용자 노출용이라 goods_no 는 표기하지 않고 "goods_nm tire_size" 로만 보여준다.
    goods_nm = ""
    tire_size = ""
    for product_entry in _find_entries(
        tool_data_list,
        "search_product_tool",
        "get_products_recommendations_tool",
        "get_best_selling_products_tool",
        "compare_discount_tool",
    ):
        praw = _unwrap(product_entry)
        rows = praw.get("items") if isinstance(praw, dict) else (praw if isinstance(praw, list) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and _get_str(row, "goods_no") == goods_no:
                goods_nm = _get_str(row, "goods_nm", "title")
                tire_size = _get_str(row, "tire_size_1", "tire_size_2")
                break
        if goods_nm:
            break
    if goods_nm and tire_size:
        product_label = f"{goods_nm} {tire_size}"
    elif goods_nm:
        product_label = goods_nm
    else:
        product_label = goods_no

    # Enrich carInfo from same-turn vehicle tools (match by car_lnc_cd).
    car_info: str | None = None
    if car_lnc_cd:
        for car_entry in _find_entries(tool_data_list, "get_my_cars_tool", "get_user_vehicles_tool"):
            craw = _unwrap(car_entry)
            if isinstance(craw, list):
                rows = craw
            elif isinstance(craw, dict):
                rows = craw.get("items") if "items" in craw else [craw]
            else:
                rows = []
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict) and _get_str(row, "car_lnc_cd") == car_lnc_cd:
                    car_nm = _get_str(row, "car_model_det", "car_nm")
                    car_no = _get_str(row, "car_no")
                    if car_nm and car_no:
                        car_info = f"{car_nm} ({car_no})"
                    elif car_nm:
                        car_info = car_nm
                    break
            if car_info:
                break

    # Enrich storeName from same-turn store tools (match by shop_id).
    store_name: str | None = None
    if shop_id:
        for store_entry in _find_entries(tool_data_list, "get_store_list_tool", "get_nearby_stores_tool"):
            sraw = _unwrap(store_entry)
            stores = sraw.get("stores") if isinstance(sraw, dict) else []
            if not isinstance(stores, list):
                continue
            for store in stores:
                if isinstance(store, dict) and _get_str(store, "shop_id") == shop_id:
                    shop_nm = _get_str(store, "shop_nm")
                    if shop_nm:
                        store_name = shop_nm
                    break
            if store_name:
                break
        if not store_name:
            for detail_entry in _find_entries(tool_data_list, "get_store_detail_tool"):
                dargs = detail_entry.get("args") if isinstance(detail_entry.get("args"), dict) else {}
                if _get_str(dargs, "shop_id") != shop_id:
                    continue
                draw = _unwrap(detail_entry)
                if isinstance(draw, dict):
                    shop_nm = _get_str(draw, "shop_nm")
                    if shop_nm:
                        store_name = shop_nm
                        break

    # Enrich paymentAmount from same-turn price tool.
    # Definition mirrors get_final_price_tool docs: (FINAL + wage_prc) × qty,
    # with FINAL resolved as cheapest_final_prc → extra_fvr_sale_prc → sale_prc.
    payment_amount: int | None = None
    for price_entry in _find_entries(tool_data_list, "get_final_price_tool"):
        praw = _unwrap(price_entry)
        if not isinstance(praw, dict):
            continue
        final_unit = _get_num(
            praw,
            "cheapest_final_prc",
            "extra_fvr_sale_prc",
            "sale_prc",
            "final_unit_price",
            default=0,
        )
        wage = _get_num(praw, "wage_prc", default=0)
        if final_unit:
            payment_amount = int((final_unit + wage) * ord_qty)
            break

    # cart 흐름은 카트 카드 대신 짧은 confirmation 메시지 + 다음 액션 chips
    # ("주문하기" / "처음으로") 만 노출하기로 결정. orderComplete 카드는 quick_order
    # 흐름에서만 사용한다.
    if flow_type == "cart":
        if is_success:
            cart_msg = "장바구니에 담았어요. 😊\n\n바로 주문하시겠어요?"
            cart_chips = [
                {"label": "주문하기", "domain": "TRANSACTION"},
                {"label": "처음으로", "domain": "LEADING"},
            ]
        elif is_already_in_cart:
            cart_msg = "이미 장바구니에 담겨있는 상품이에요. 장바구니에서 확인해 주세요. 😊"
            cart_chips = [
                {"label": "장바구니 확인", "domain": "TRANSACTION", "url": CTAUrls.CART},
                {"label": "주문하기", "domain": "TRANSACTION"},
            ]
        else:
            cart_msg = "장바구니 담기 중 문제가 생겼어요. 다시 시도해 주세요."
            cart_chips = [
                {"label": "다시 시도", "domain": "TRANSACTION"},
                {"label": "처음으로", "domain": "LEADING"},
            ]
        metadata: dict[str, object] = {"goodsId": goods_no, "quantity": ord_qty, "ordQty": ord_qty}
        if goods_nm:
            metadata["productName"] = goods_nm
        if tire_size:
            metadata["tireSize"] = tire_size
        return {
            "type": "data",
            "template": "quickReply",
            "data": {
                "assistantResponse": cart_msg,
                "quickReplies": cart_chips,
                "metadata": metadata,
            },
        }

    order_form_data = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else None

    # order (quick_order_tool) 는 주문/결제 페이지로 이동하기 전 주문서 생성 단계다.
    default_msg = (
        "주문서가 준비되었습니다. 주문/결제 페이지에서 결제를 진행해 주세요."
        if is_success
        else "주문 처리 중 문제가 발생했어요. 다시 시도해 주세요."
    )
    text = (assistant_text or "").strip()
    assistant_response = default_msg if is_success else text if text and len(text) <= 120 else default_msg

    if is_success:
        quick_replies = [
            {"label": "주문 내역 확인", "domain": "TRANSACTION"},
            {"label": "배송 상태 확인", "domain": "TRANSACTION"},
            {"label": "처음으로", "domain": "LEADING"},
        ]
    else:
        quick_replies = [
            {"label": "다시 시도", "domain": "TRANSACTION"},
            {"label": "처음으로", "domain": "LEADING"},
        ]

    return {
        "type": "data",
        "template": "orderComplete",
        "data": {
            "assistantResponse": assistant_response,
            "orderInfo": {
                "carInfo": car_info,
                "product": product_label,
                "quantity": ord_qty,
                "storeName": store_name,
                "bookingDateTime": None,
                "paymentAmount": payment_amount,
            },
            "isSuccess": is_success,
            "type": flow_type,
            "message": None if is_success else default_msg,
            "render": False if is_success and order_form_data else True,
            "autoMoveOrderPage": True if is_success and order_form_data else False,
            "moveOrderPageData": order_form_data,
            "data": {"status": "success" if is_success else "error"},
            "metadata": {
                "ordNo": ord_no,
                "goodsId": goods_no,
                "shopId": shop_id or None,
            },
            "quickReplies": quick_replies,
        },
    }


# ── 11. quickReply (store detail info-only) ────────────────────────────────────

def _map_store_detail_info(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Deterministic ``quickReply`` for Flow 5 General single-store info lookup.

    The transaction agent's prompt expects a full text answer in
    ``assistantResponse`` (line 1066-1072 of c_transaction_agent/agent.py) when
    ``get_store_detail_tool`` runs without slot results, but in practice the
    LLM often slips into PROSE-MODE ("매장 상세정보를 확인했어요.") and the
    actual fields never reach the user — only QC catches it. Build the answer
    in code so the response is correct on the first emission and QC has
    nothing to rewrite.

    Skip rules:
    - Schedule tools own their own templates (datepick / multi-store).
    - Booking-signal tools (price, stock, cart, order) own theirs — those
      cases defer to `_map_datepick_from_detail` for the date picker.

    Note: non-empty ``available_slots`` no longer skips info rendering, and
    a future ``cal_day`` no longer defers to the LLM. When the turn carries
    no booking-signal tool the user is asking for plain store info (e.g.
    clicking a card after a Flow 5.5T region/time search) — render the
    deterministic info card regardless of which cal_day was queried.
    """
    called_tools = {e.get("tool", "") for e in tool_data_list}
    if "get_store_schedule_tool" in called_tools or "get_multi_store_schedule_tool" in called_tools:
        return None
    if called_tools & _BOOKING_SIGNAL_TOOLS:
        return None

    entries = _find_entries(tool_data_list, "get_store_detail_tool")
    if not entries:
        return None
    entry = entries[-1]
    raw = _unwrap(entry)
    if not isinstance(raw, dict):
        return None

    shop_nm = _get_str(raw, "shop_nm")
    if not shop_nm:
        return None

    tel_no = _format_phone(_get_str(raw, "tel_no"))
    holiday = _get_str(raw, "holiday")
    biz_wday_start = _get_str(raw, "shop_biz_strt_wday")
    biz_wday_end = _get_str(raw, "shop_biz_end_wday")
    biz_start = _normalize_time(_get_str(raw, "shop_biz_strt_time"))
    biz_end = _normalize_time(_get_str(raw, "shop_biz_end_time"))
    sat_start = _normalize_time(_get_str(raw, "shop_sat_strt_time"))
    sat_end = _normalize_time(_get_str(raw, "shop_sat_end_time"))

    biz_hours = f"{biz_start}~{biz_end}" if biz_start and biz_end else ""
    sat_hours = f"{sat_start}~{sat_end}" if sat_start and sat_end else ""
    # When Saturday has its own line, the weekday line implicitly means Mon-Fri.
    # Otherwise fall back to BE's reported range (e.g. 월요일~일요일 for shops
    # without a separate Saturday schedule).
    if sat_hours:
        biz_wday_label = "평일"
    elif biz_wday_start and biz_wday_end:
        biz_wday_label = f"{biz_wday_start}~{biz_wday_end}"
    else:
        biz_wday_label = "평일"

    lines: list[str] = [f"고객님, {shop_nm} 매장 정보를 안내드릴게요. 😊", ""]
    lines.append(f"• 매장명: {shop_nm}")
    if tel_no:
        lines.append(f"• 전화번호: {tel_no}")
    if biz_hours:
        lines.append(f"• {biz_wday_label} 영업시간: {biz_hours}")
    if sat_hours:
        lines.append(f"• 토요일 영업시간: {sat_hours}")
    if holiday:
        lines.append(f"• 휴무일: {holiday}")
    if "is_all_my_t" in raw:
        lines.append("• 올마이T: 이용 가능" if raw.get("is_all_my_t") else "• 올마이T: 이용 불가")
    if "is_installable" in raw:
        lines.append("• 온라인 장착: 가능" if raw.get("is_installable") else "• 온라인 장착: 불가")
    if "is_tna_delivery" in raw:
        lines.append("• T바로배송: 가능" if raw.get("is_tna_delivery") else "• T바로배송: 불가")
    if "is_imported_car" in raw:
        lines.append("• 수입차 장착: 가능" if raw.get("is_imported_car") else "• 수입차 장착: 불가")

    svc_labels = _svc_code_label_list(raw.get("svc_codes"))
    if svc_labels:
        lines.append(f"• 제공 서비스: {' | '.join(svc_labels)}")

    return {
        "type": "data",
        "template": "quickReply",
        "assistant_response_source": "code_mapper",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": [
                {"label": "다른 매장 정보", "domain": "TRANSACTION"},
                {"label": "예약 가능 시간 확인", "domain": "TRANSACTION"},
                {"label": "1:1 문의하기", "domain": "SUPPORT"},
            ],
            "predictedDomains": ["TRANSACTION"],
        },
    }


# ── Common builder ──────────────────────────────────────────────────────────────

def _build_event(template: str, data: dict, assistant_text: str, item_count: int) -> dict:
    """Build a type:data event with a concise assistantResponse."""
    short, response_source = _summarize_with_source(assistant_text, template, item_count)
    data["assistantResponse"] = short
    return {
        "type": "data",
        "template": template,
        "data": data,
        "assistant_response_source": response_source,
    }


_TEMPLATE_DEFAULTS: dict[str, str] = {
    "product": "고객님, 추천 상품 {n}개를 안내드립니다. 원하시는 상품을 선택해 주세요.",
    "listCar": "등록된 차량 {n}대를 확인했어요. 안내받으실 차량을 선택해 주세요.",
    "voucher": "고객님, 사용 가능한 쿠폰 {n}개를 안내드립니다.",
    "cheapestProduct": "고객님, 가장 저렴한 상품의 가격을 안내드립니다.",
    "event": "현재 진행 중인 이벤트 {n}개를 안내드립니다.",
    "previewYoutube": "관련 영상 {n}개를 안내드립니다.",
    "qnaComplete": "1:1 문의가 접수되었습니다. 아래 버튼을 눌러 확인해 주세요.",
    "location": "고객님, 매장 {n}곳을 안내드립니다. 원하시는 매장을 선택해 주세요.",
    "datepick": "예약 가능한 날짜와 시간을 선택해 주세요.",
    "orderComplete": "처리되었습니다. 😊",
}


def _summarize(full_text: str, template: str, item_count: int) -> str:
    return _summarize_with_source(full_text, template, item_count)[0]


_BULLET_PATTERN = re.compile(r"\n-\s+\*\*")
def _is_other_store_request() -> bool:
    return is_other_store_request(current_user_text.get() or "")


_KOREAN_DATE_LABEL_RE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")
_TODAY_SERVICE_DATEPICK_RE = re.compile(
    r"오늘\s*서비스|오늘서비스|오늘\s*장착|당일\s*장착|오늘\s*가능|당일|지금|바로|당장",
    re.IGNORECASE,
)
_STORE_BOOKING_FOLLOWUP_SIGNAL_RE = re.compile(
    r"예약|장착|방문|스케줄|시간표|가능\s*(?:해|하|한|하냐|하냐고|하나요|여부)?|돼\??|되\??",
    re.IGNORECASE,
)
_STORE_OPERATION_INFO_SIGNAL_RE = re.compile(
    r"영업|운영|휴무|휴일|쉬어|문\s*열|문\s*닫|열어|닫아|여나|하나",
    re.IGNORECASE,
)
_STORE_DATE_REFERENCE_RE = re.compile(
    r"\d{1,2}\s*/\s*\d{1,2}|(?:\d{2,4}\s*년\s*)?\d{1,2}\s*월\s*\d{1,2}\s*일|"
    r"오늘|내일|모레|이번\s*주|다음\s*주|주말|월요일|화요일|수요일|목요일|금요일|토요일|일요일",
    re.IGNORECASE,
)


def _parse_korean_date_label(label: str) -> datetime.date | None:
    match = _KOREAN_DATE_LABEL_RE.search(label or "")
    if not match:
        return None
    try:
        return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _today_service_datepick_response(event: dict, *, force: bool = False) -> str | None:
    user_text = current_user_text.get() or ""
    if not force and not _TODAY_SERVICE_DATEPICK_RE.search(user_text):
        return None
    event_data = event.get("data")
    if not isinstance(event_data, dict):
        return None
    dates = event_data.get("dates")
    if not isinstance(dates, list) or not dates:
        return None

    earliest_label: str | None = None
    earliest_date: datetime.date | None = None
    for date_item in dates:
        if not isinstance(date_item, dict) or not date_item.get("available"):
            continue
        label = _get_str(date_item, "date")
        parsed = _parse_korean_date_label(label)
        if not label or parsed is None:
            continue
        earliest_label = label
        earliest_date = parsed
        break

    if earliest_label is None or earliest_date is None:
        return None
    if earliest_date <= datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date():
        return None
    return f"오늘서비스는 어렵고, 가장 빠른 예약 가능 일정은 {earliest_label}부터예요. 가능한 날짜와 시간을 선택해 주세요."


def _should_treat_store_detail_slots_as_datepick() -> bool:
    user_text = current_user_text.get() or ""
    if user_text and _STORE_OPERATION_INFO_SIGNAL_RE.search(user_text) and not _STORE_BOOKING_FOLLOWUP_SIGNAL_RE.search(
        user_text
    ):
        return False
    if current_store_date_availability.get():
        return True
    if not user_text:
        return False
    return bool(
        _STORE_DATE_REFERENCE_RE.search(user_text)
        and _STORE_BOOKING_FOLLOWUP_SIGNAL_RE.search(user_text)
    )


def _summarize_with_source(full_text: str, template: str, item_count: int) -> tuple[str, str]:
    """Domain Agent 텍스트에서 첫 문장만 추출하거나, 기본 안내를 반환한다.

    PROSE MODE 도입 후 LLM이 1–2문장의 짧은 prose("...찾았어요. ...선택해 주세요 😊")를
    내보내는데, 첫 문장에서 자르면 후반부 + 마지막 emoji가 사라진다. 길이가 120자
    이하라면 그대로 유지하고, 그보다 길 때만 첫 문장 컷을 적용한다.

    EXCEPTION — product 템플릿 + bullet 패턴(``\\n- **``) 검출 시 전체 텍스트 유지.
    추천 응답 (인트로 + 상품당 1줄 bullet 요약) 은 길이가 120자를 넘기지만 전체가
    의도된 형식이므로 컷 금지. FE 는 markdown bullet 으로 렌더한다.
    """
    text = (full_text or "").strip()
    if _INTERNAL_POLICY_TEXT_RE.search(text):
        return sanitize_user_facing_response(text), "policy_guard_fallback"
    if not text:
        return _TEMPLATE_DEFAULTS.get(template, "").format(n=item_count), "default"

    if template == "product" and _BULLET_PATTERN.search(text):
        return text, "llm_prose_with_bullets"

    if len(text) <= 120:
        return text, "llm_prose"

    # 길면 첫 문장으로 컷 (줄바꿈 또는 문장 부호 기준)
    for sep in ["\n", ".\n", "!\n", "?\n", ". ", "! ", "? "]:
        idx = text.find(sep)
        if 0 < idx <= 120:
            return text[: idx + 1].strip(), "llm_prose"

    return _TEMPLATE_DEFAULTS.get(template, "").format(n=item_count), "default"


# ── Mapper registry ─────────────────────────────────────────────────────────────

_MAPPERS: dict[str, Any] = {
    "search_product_tool": _map_product,
    "get_newest_products_tool": _map_product,
    "get_products_recommendations_tool": _map_product,
    "get_best_selling_products_tool": _map_product,
    "get_my_cars_tool": _map_list_car,
    "get_user_vehicles_tool": _map_list_car,
    "get_my_coupons_tool": _map_voucher,
    "transfer_to_qna_tool": _map_qna_complete,
    "compare_discount_tool": _map_cheapest_product,
    "get_cheapest_price_tool": _map_cheapest_product,
    # "get_events_tool": _map_event,  # FE에 event 렌더러 없음
    "search_youtube_video_tool": _map_preview_youtube,
    "search_stores_tool": _map_location,
    "search_stores_complex_tool": _map_location,
    "get_store_list_tool": _map_location,
    "get_nearby_stores_tool": _map_location,
    "transaction_store_preview_tool": _map_location,
    "get_favorite_stores_tool": _map_location,
    "get_stores_with_time_filter_tool": _map_time_filter_location,
    "get_store_schedule_tool": _map_datepick,
    "get_store_detail_tool": _map_store_detail_info,
    "save_to_cart_tool": _map_order_complete,
    "quick_order_tool": _map_order_complete,
}


def try_build_template(accumulated_tool_data: list[dict], assistant_text: str) -> dict | None:
    """Try to build a template event from accumulated tool data using code mapping.

    Returns a template event dict if a code mapper handled it, or None to fall through
    to the LLM UI Template Agent.
    """
    if not accumulated_tool_data:
        return None

    runflat_comparison = _map_runflat_price_comparison(accumulated_tool_data, assistant_text)
    if runflat_comparison is not None:
        return runflat_comparison

    ev_suitability_comparison = _map_ev_suitability_comparison(accumulated_tool_data, assistant_text)
    if ev_suitability_comparison is not None:
        return ev_suitability_comparison

    vehicle_recommendation_no_results = _map_vehicle_recommendation_no_results(accumulated_tool_data, assistant_text)
    if vehicle_recommendation_no_results is not None:
        return vehicle_recommendation_no_results

    recommendation_no_results = _map_recommendation_no_results(accumulated_tool_data, assistant_text)
    if recommendation_no_results is not None:
        return recommendation_no_results

    unsized_tire_summary = _map_unsized_tire_summary(accumulated_tool_data, assistant_text)
    if unsized_tire_summary is not None:
        return unsized_tire_summary

    # When multiple tools are called, pick the most important UI template.
    # Priority order is intentional:
    #   datepick > product > listCar > voucher > cheapestProduct > previewYoutube
    #   > qnaComplete > location
    # - datepick is the terminal step in store-stock/booking flows; if the agent
    #   produced a schedule in this turn, that's the answer (regardless of any
    #   earlier store_list call this turn).
    # - location is intermediate (user still has to pick a store), so it sits at
    #   the bottom — almost any other mapped tool that ran in the same turn
    #   represents a more advanced step.
    # - This also handles: get_my_cars → get_products_recommendations →
    #   compare_discount, where product cards should be shown, not
    #   cheapestProduct.
    _PRIORITY = [
        # Cart/order are terminal steps in the transaction flow — when they ran,
        # any other tool in the same turn was preparation (product lookup, store
        # selection, price calc) and the orderComplete card is the answer.
        ("save_to_cart_tool", _map_order_complete),
        ("quick_order_tool", _map_order_complete),
        ("transaction_store_preview_tool", _map_store_validation_quickreply),
        ("get_store_list_tool", _map_store_validation_quickreply),
        ("get_store_inventory_tool", _map_inventory_stock_result),
        ("transaction_store_preview_tool", _map_preview_no_fulfillment_quickreply),
        ("get_store_schedule_tool", _map_datepick),
        # Date-specific detail lookup (Flow 5.1 / 5.5) — `get_store_detail_tool`
        # with args.cal_day + non-empty available_slots is a datepick signal.
        # Must outrank the location mappers below; otherwise a sibling
        # `transaction_store_preview_tool(tier=none)` causes `_map_location` to
        # render a store card instead of the intended time-slot picker.
        ("get_store_detail_tool", _map_datepick),
        ("transaction_store_preview_tool", _map_datepick),
        ("search_product_tool", _map_product),
        ("get_newest_products_tool", _map_product),
        ("get_products_recommendations_tool", _map_product),
        ("get_best_selling_products_tool", _map_product),
        ("get_my_cars_tool", _map_list_car),
        ("get_user_vehicles_tool", _map_list_car),
        ("get_my_coupons_tool", _map_voucher),
        ("compare_discount_tool", _map_cheapest_product),
        ("get_cheapest_price_tool", _map_cheapest_product),
        ("search_youtube_video_tool", _map_preview_youtube),
        ("transfer_to_qna_tool", _map_qna_complete),
        ("get_stores_with_time_filter_tool", _map_time_filter_location),
        ("search_stores_complex_tool", _map_location),
        ("search_stores_tool", _map_location),
        ("get_nearby_stores_tool", _map_location),
        ("get_store_list_tool", _map_location),
        ("transaction_store_preview_tool", _map_location),
        ("get_favorite_stores_tool", _map_location),
        # Lowest priority — only fires when neither the location card path
        # (info-only `_map_location` returns None) nor any higher-priority
        # template applies. Owns the Flow 5 General single-store info answer.
        ("get_store_detail_tool", _map_store_detail_info),
    ]

    called_tools = {e.get("tool", "") for e in accumulated_tool_data}

    # In product-specific coupon queries both sibling tools serve as data sources,
    # not renderers — let the LLM's quickReply fenced JSON win instead.
    _product_coupon_query = "get_product_promotions_tool" in called_tools

    for tool_name, mapper in _PRIORITY:
        if tool_name in called_tools:
            if _product_coupon_query and tool_name in {"search_product_tool", "get_my_coupons_tool"}:
                continue
            result = mapper(accumulated_tool_data, assistant_text)
            if result:
                logger.debug(
                    "[TEMPLATE_MAPPER] Built '%s' template from %s (skipped UI Template Agent)",
                    result.get("template"),
                    tool_name,
                )
                return result

    return None
