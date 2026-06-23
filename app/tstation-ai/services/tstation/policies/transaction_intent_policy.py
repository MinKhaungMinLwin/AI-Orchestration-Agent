"""Deterministic intent policy for Transaction stock/store/reservation flows."""

from __future__ import annotations

import re
import datetime
from typing import Any

from services.tstation.policies.intent_frame import IntentFrame, PolicyDomain
from services.tstation.policies.response_decision import ToolPlan


_SIZE_COMPACT_RE = re.compile(r"\b(\d{3})\s*/?\s*(\d{2})\s*R?\s*(\d{2})\b", re.IGNORECASE)
_QUANTITY_RE = re.compile(r"(\d+)\s*(?:개|본|짝)")
_TODAY_RE = re.compile(r"오늘|당일|지금|바로|당장", re.IGNORECASE)
_RELATIVE_RESERVATION_DATE_RE = re.compile(r"내일|모레", re.IGNORECASE)
_EXPLICIT_MD_DATE_RE = re.compile(r"(?:(20\d{2})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_STOCK_RE = re.compile(r"재고|오늘\s*서비스|오늘서비스|당일\s*서비스|T\s*바로\s*배송|T바로배송", re.IGNORECASE)
_RESERVATION_RE = re.compile(r"예약|장착|방문|갈게|가고\s*싶|작업", re.IGNORECASE)
_PURCHASE_RE = re.compile(r"구매|주문|결제|살래|살게|사고\s*싶|사려고", re.IGNORECASE)
_STORE_SCHEDULE_RE = re.compile(
    r"예약\s*가능|작업\s*가능|장착\s*가능|가능한\s*(?:시간|일정|매장)|가능\s*시간|가능\s*일정|스케줄|몇\s*시|시간",
    re.IGNORECASE,
)
_RESERVATION_STORE_REF_RE = re.compile(
    r"예약(?:한|하신)?\s*(?:매장|지점|곳)|내\s*예약\s*(?:매장|지점|곳)|예약\s*매장|예약\s*지점",
    re.IGNORECASE,
)
_RESERVATION_STORE_INFO_RE = re.compile(
    r"전화|전화번호|연락처|주소|위치|어디|영업|운영|휴무|정보|상세|가고\s*싶|연락|전화하고",
    re.IGNORECASE,
)
_SERVICE_DURATION_ADVISORY_RE = re.compile(
    r"(?:예약한\s*거|예약한거|예약|서비스\s*받|작업|교체).{0,40}"
    r"(?:현장(?:에서)?\s*)?(?:얼라인먼트|휠\s*얼라이먼트|엔진오일|실내\s*필터|필터|배터리|와이퍼|경정비)"
    r".{0,40}(?:추가|같이|함께).{0,30}(?:시간|얼마나|소요|걸려)|"
    r"(?:얼라인먼트|휠\s*얼라이먼트|엔진오일|실내\s*필터|필터|배터리|와이퍼|경정비)"
    r".{0,40}(?:현장(?:에서)?\s*)?(?:추가|같이|함께).{0,30}(?:시간|얼마나|소요|걸려)",
    re.IGNORECASE,
)
_MAINTENANCE_ADDON_SERVICE_RE = re.compile(r"엔진\s*오일|실내\s*필터|필터|와이퍼|배터리|경정비", re.IGNORECASE)
_TIRE_SERVICE_RE = re.compile(r"타이어.{0,12}(?:교체|장착|서비스|작업)|(?:교체|장착).{0,12}타이어", re.IGNORECASE)
_ADDON_WITH_RE = re.compile(r"같이|함께|동시|하면서|겸|추가|하고\s*싶", re.IGNORECASE)
_RESERVATION_CHANGE_RE = re.compile(r"변경|바꿔|옮겨|미뤄|당겨|취소", re.IGNORECASE)
_NOON_RE = re.compile(r"12\s*시|점심\s*시간", re.IGNORECASE)
_NEARBY_RE = re.compile(r"근처|주변|가까운|인근", re.IGNORECASE)
_STORE_SUFFIX_RE = re.compile(r"([가-힣A-Za-z0-9]+(?:점|매장))")
_STORE_SEARCH_RE = re.compile(r"매장|지점|티스테이션|더타이어샵|찾아|알려|보여", re.IGNORECASE)
_FAVORITE_STORE_RE = re.compile(
    r"내\s*단골(?:매장|가게|점)?|단골(?:매장|가게|점)|마이샵|자주\s*가는\s*매장",
    re.IGNORECASE,
)
_OTHER_STORE_RE = re.compile(r"다른\s*(?:매장|지점|곳)|다시\s*(?:확인|찾|검색)|새로\s*(?:찾|검색)", re.IGNORECASE)
_STORE_SCOPE_FOLLOWUP_RE = re.compile(
    r"다른\s*(?:매장|지점|곳)|근처(?:에)?\s*(?:다른\s*)?(?:매장|지점|곳)|주변\s*(?:매장|지점)|"
    r"(?:매장|지점)\s*(?:더|또|추가)|다른\s*지역|예약\s*가능\s*시간|가능\s*시간|가능\s*일정",
    re.IGNORECASE,
)
_STORE_CANDIDATE_SEARCH_RE = re.compile(
    r"(?:오늘\s*)?(?:장착\s*)?가능\s*(?:한\s*)?(?:매장|지점|곳)|"
    r"재고\s*(?:있는|있는\s*곳|확인\s*된)\s*(?:매장|지점|곳)|"
    r"다른\s*(?:매장|지점|곳)|(?:매장|지점)\s*(?:찾아|검색|보여)",
    re.IGNORECASE,
)
_SPECIFIC_STORE_RECHECK_RE = re.compile(r"다시\s*확인|재확인|한\s*번\s*더|한번\s*더", re.IGNORECASE)
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
    r"(서울|서초|강남|판교|분당|파주|강릉|부산|해운대|광교|성남|오목천|동광주|송파|한남|"
    r"청량리|인천|하남|청주|제주|서귀포)"
)
_PRODUCT_HINT_RE = re.compile(
    r"벤투스|ventus|다이나프로|dynapro|키너지|kinergy|아이온|ion|옵티모|optimo|미쉐린|michelin|cc2|"
    r"s\s*fit|g\s*fit|에스핏|지핏|i\*?cept|icept|아이셉트|4s2|dws06|cc7|ps4s|ps\s*as\s*4|psas4|cup\s*2|cup2|p7",
    re.IGNORECASE,
)
_PRICE_OR_COUPON_RE = re.compile(r"가격|할인가|최대\s*혜택|쿠폰|할인", re.IGNORECASE)
_TODAY_INSTALL_OR_RESERVATION_RE = re.compile(
    r"오늘\s*장착|오늘장착|오늘\s*서비스|오늘서비스|당일|"
    r"예약|방문|장착\s*가능|예약\s*가능|가능한\s*(?:시간|일정)|"
    r"몇\s*시|시간|스케줄",
    re.IGNORECASE,
)
_QUICK_ORDER_CONFIRM_RE = re.compile(
    r"^\s*(?:"
    r"주문\s*확정|구매하기|주문하기|결제하기|"
    r"주문해줘|구매해줘|결제해줘|"
    r"주문\s*진행|결제\s*진행|진행해(?:줘)?|바로\s*주문|"
    r"네|넵|넹|예|응|그래|좋아|ㅇㅇ|ㅇㅋ|ok|okay"
    r")\s*$",
    re.IGNORECASE,
)
_PRODUCT_ALIASES: tuple[tuple[str, str], ...] = (
    ("ventus air s", "Ventus air S"),
    ("벤투스 air s", "Ventus air S"),
    ("벤투스 에어 s", "Ventus air S"),
    ("벤투스 에어s", "Ventus air S"),
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


def _kst_today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()


def extract_requested_cal_day(text: str, *, today: datetime.date | None = None) -> str | None:
    base = today or _kst_today()
    if _TODAY_RE.search(text or ""):
        return base.strftime("%Y%m%d")
    match = _RELATIVE_RESERVATION_DATE_RE.search(text or "")
    if match:
        token = match.group(0)
        offset = 1 if token == "내일" else 2
        return (base + datetime.timedelta(days=offset)).strftime("%Y%m%d")
    explicit = _EXPLICIT_MD_DATE_RE.search(text or "")
    if explicit:
        year = int(explicit.group(1) or base.year)
        month = int(explicit.group(2))
        day = int(explicit.group(3))
        try:
            requested = datetime.date(year, month, day)
        except ValueError:
            return None
        if explicit.group(1) is None and requested < base:
            requested = datetime.date(year + 1, month, day)
        return requested.strftime("%Y%m%d")
    return None


def _has_pending_today_install_context(slots: dict[str, Any]) -> bool:
    if not slots:
        return False
    if slots.get("availability_intent") == "today_install":
        return True
    if slots.get("pending_intent") in {"today_install", "stock", "store_with_stock"} and slots.get("requested_cal_day"):
        return True
    return bool(slots.get("requested_cal_day") and slots.get("goods_no") and (slots.get("quantity") or slots.get("ord_qty")))


def _has_confirmed_product_quantity_context(slots: dict[str, Any]) -> bool:
    return bool(slots.get("goods_no") and (slots.get("quantity") or slots.get("ord_qty")))


def _normalized_quantity(slots: dict[str, Any], text: str = "") -> int | None:
    value = extract_quantity(text) or slots.get("quantity") or slots.get("ord_qty")
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _has_confirmed_store_context(slots: dict[str, Any]) -> bool:
    return bool(slots.get("shop_id") or slots.get("shop_name") or slots.get("store_name"))


def _is_stock_flow_context(slots: dict[str, Any]) -> bool:
    return bool(slots.get("pending_intent") == "stock" or slots.get("goal_type") == "store_with_stock")


def _is_order_or_reservation_context(slots: dict[str, Any]) -> bool:
    return bool(slots.get("pending_intent") in {"order", "reservation"} or slots.get("goal_type") == "place_order")


def _is_today_install_context(slots: dict[str, Any], requested_cal_day: str | None = None) -> bool:
    return bool(
        slots.get("availability_intent") == "today_install"
        or requested_cal_day
        or slots.get("requested_cal_day")
    )


def _is_store_candidate_search_turn(text: str, slots: dict[str, Any]) -> bool:
    if not _STORE_CANDIDATE_SEARCH_RE.search(text or ""):
        return False
    if not (_is_stock_flow_context(slots) or _is_today_install_context(slots)):
        return False
    return bool(slots.get("goods_no") and (slots.get("quantity") or slots.get("ord_qty")))


def _is_specific_store_recheck_turn(text: str, current_store_name: str | None, slots: dict[str, Any]) -> bool:
    if not _SPECIFIC_STORE_RECHECK_RE.search(text or ""):
        return False
    return bool(current_store_name or slots.get("shop_id") or slots.get("shop_name") or slots.get("store_name"))


def _is_preorder_ready_context(slots: dict[str, Any]) -> bool:
    if not slots:
        return False
    quantity = slots.get("ord_qty") or slots.get("quantity")
    return bool(
        (slots.get("pending_intent") == "order" or slots.get("goal_type") == "place_order")
        and slots.get("goods_no")
        and quantity
        and (slots.get("shop_id") or slots.get("shop_name") or slots.get("store_name"))
        and slots.get("requested_cal_day")
        and slots.get("rsv_hour")
    )


def _is_order_execute_confirmation_context(text: str, slots: dict[str, Any]) -> bool:
    if not re.search(r"주문\s*확정|결제\s*진행|진행해(?:줘)?|ㅇㅇ|ㅇㅋ|ok|okay", text or "", re.IGNORECASE):
        return False
    quantity = slots.get("ord_qty") or slots.get("quantity")
    return bool(
        (slots.get("pending_intent") == "order" or slots.get("goal_type") == "place_order")
        and slots.get("goods_no")
        and quantity
    )


def _is_preorder_confirmation_text(text: str) -> bool:
    return bool(_QUICK_ORDER_CONFIRM_RE.match(text or ""))


def _is_quantity_only_followup(
    text: str,
    *,
    current_has_product: bool,
    explicit_tire_size: str | None,
    current_store_name: str | None,
    current_region: str | None,
    current_price: bool,
    current_purchase: bool,
    current_reservation: bool,
    current_store_search: bool,
) -> bool:
    return bool(
        extract_quantity(text)
        and not current_has_product
        and not explicit_tire_size
        and not current_store_name
        and not current_region
        and not current_price
        and not current_purchase
        and not current_reservation
        and not current_store_search
    )


def build_transaction_intent_frame(
    last_user_text: str,
    *,
    known_slots: dict[str, Any] | None = None,
) -> IntentFrame:
    """Build a Transaction intent frame from current text and existing slots."""
    text = last_user_text or ""
    slots = dict(known_slots or {})
    explicit_tire_size = normalize_tire_size(text)
    current_store_name = _extract_store_name(text)
    current_region = _extract_region(text)
    current_product_name = _extract_product_name(text)
    current_has_product = bool(current_product_name or _PRODUCT_HINT_RE.search(text))
    current_store_search = bool(_STORE_SEARCH_RE.search(text))
    current_favorite_store_lookup = bool(_FAVORITE_STORE_RE.search(text))
    current_reservation_store_info_lookup = bool(
        _RESERVATION_STORE_REF_RE.search(text) and _RESERVATION_STORE_INFO_RE.search(text)
    )
    current_stock = bool(_STOCK_RE.search(text) or _TODAY_RE.search(text))
    current_price = bool(_PRICE_OR_COUPON_RE.search(text))
    current_purchase = bool(_PURCHASE_RE.search(text))
    current_service_duration_advisory = bool(
        _SERVICE_DURATION_ADVISORY_RE.search(text) and not _RESERVATION_CHANGE_RE.search(text)
    )
    current_maintenance_addon_with_tire = bool(
        _TIRE_SERVICE_RE.search(text)
        and _MAINTENANCE_ADDON_SERVICE_RE.search(text)
        and _ADDON_WITH_RE.search(text)
        and not current_service_duration_advisory
    )
    current_reservation = bool(_RESERVATION_RE.search(text) or _STORE_SCHEDULE_RE.search(text) or current_purchase)
    plain_store_search = (
        current_store_search
        and not current_favorite_store_lookup
        and not current_stock
        and not current_price
        and not current_reservation
    )
    pending_today_install = _has_pending_today_install_context(slots)
    confirmed_product_quantity_context = _has_confirmed_product_quantity_context(slots)
    other_store_today_install_continuation = (
        pending_today_install
        and bool(_OTHER_STORE_RE.search(text))
        and not current_store_name
        and not current_has_product
        and not explicit_tire_size
        and not current_price
        and not current_purchase
        and not current_reservation
    )
    region_only_today_install_continuation = (
        pending_today_install
        and bool(current_region)
        and not current_store_name
        and not current_has_product
        and not explicit_tire_size
        and not current_price
        and not current_purchase
        and not current_reservation
        and not (plain_store_search and not _OTHER_STORE_RE.search(text))
    )
    date_only_today_install_continuation = (
        pending_today_install
        and bool(extract_requested_cal_day(text))
        and not current_region
        and not current_store_name
        and not current_has_product
        and not explicit_tire_size
        and not current_price
        and not current_purchase
        and not current_reservation
        and not plain_store_search
    )
    store_scope_product_continuation = (
        confirmed_product_quantity_context
        and not (plain_store_search and not _OTHER_STORE_RE.search(text))
        and bool(_STORE_SCOPE_FOLLOWUP_RE.search(text) or (current_region and len(text.strip()) <= 20))
        and not current_store_name
        and not current_has_product
        and not explicit_tire_size
        and not extract_quantity(text)
        and not current_price
        and not current_purchase
        and not current_reservation
    )
    region_scope_product_continuation = bool(store_scope_product_continuation and current_region and not current_store_name)
    quantity_slot_fill_stock_continuation = (
        _is_stock_flow_context(slots)
        and bool(slots.get("goods_no") and (slots.get("tire_size") or slots.get("product_name")))
        and _is_quantity_only_followup(
            text,
            current_has_product=current_has_product,
            explicit_tire_size=explicit_tire_size,
            current_store_name=current_store_name,
            current_region=current_region,
            current_price=current_price,
            current_purchase=current_purchase,
            current_reservation=current_reservation,
            current_store_search=current_store_search,
        )
    )
    quantity_only_stock_continuation = (
        _is_stock_flow_context(slots)
        and confirmed_product_quantity_context
        and _has_confirmed_store_context(slots)
        and _is_quantity_only_followup(
            text,
            current_has_product=current_has_product,
            explicit_tire_size=explicit_tire_size,
            current_store_name=current_store_name,
            current_region=current_region,
            current_price=current_price,
            current_purchase=current_purchase,
            current_reservation=current_reservation,
            current_store_search=current_store_search,
        )
    )
    preorder_confirmation = bool(
        _is_preorder_confirmation_text(text)
        and (
            _is_preorder_ready_context(slots)
            or _is_order_execute_confirmation_context(text, slots)
        )
    )
    quantity = _normalized_quantity(slots, text)
    result_limit = extract_result_limit(text) or slots.get("limit")
    requested_cal_day = extract_requested_cal_day(text)
    today_requested = bool(_TODAY_RE.search(text))
    explicit_preview_request = bool(
        requested_cal_day
        or today_requested
        or _TODAY_INSTALL_OR_RESERVATION_RE.search(text)
        or slots.get("availability_intent") == "today_install"
    )

    tire_size = explicit_tire_size or slots.get("tire_size")
    if pending_today_install and not requested_cal_day:
        requested_cal_day = slots.get("requested_cal_day")
    store_candidate_search = (
        _is_store_candidate_search_turn(text, slots)
        and not _is_specific_store_recheck_turn(text, current_store_name, slots)
    )
    specific_store_recheck = (
        _is_specific_store_recheck_turn(text, current_store_name, slots)
        and _is_stock_flow_context(slots)
        and bool(slots.get("goods_no") and (slots.get("quantity") or slots.get("ord_qty")))
    )
    preserve_pending_today_install = (
        region_only_today_install_continuation
        or date_only_today_install_continuation
        or other_store_today_install_continuation
        or store_candidate_search
        or specific_store_recheck
    )
    preserve_transaction_product_context = preserve_pending_today_install or store_scope_product_continuation
    goods_no = (
        None
        if plain_store_search and not current_has_product and not preserve_transaction_product_context
        else slots.get("goods_no")
    )
    product_name = (
        current_product_name
        or (
            None
            if plain_store_search and not preserve_transaction_product_context
            else slots.get("product_name") or slots.get("tire_model") or slots.get("pattern_name")
        )
    )
    store_name = current_store_name or (
        None
        if (plain_store_search and not preserve_transaction_product_context)
        or store_candidate_search
        or region_scope_product_continuation
        else slots.get("store_name") or slots.get("shop_name")
    )
    region = current_region or slots.get("region") or slots.get("place")

    has_product = bool(goods_no or product_name or _PRODUCT_HINT_RE.search(text))
    has_location = bool(
        region
        or store_name
        or (
            not store_candidate_search
            and (slots.get("shop_name") or slots.get("shop_id"))
        )
        or slots.get("lat")
        or slots.get("lng")
    )
    today_install_candidate_scope = bool(
        store_candidate_search
        or (
            quantity_slot_fill_stock_continuation
            and _is_today_install_context(slots, requested_cal_day)
            and not _has_confirmed_store_context(slots)
        )
    )
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
        "requested_cal_day": requested_cal_day,
        "noon_requested": bool(_NOON_RE.search(text)),
        "result_limit": result_limit,
        "stock_check_mode": "inventory_only",
        "today_install_candidate_scope": today_install_candidate_scope,
    }

    if current_reservation_store_info_lookup:
        intent = "reservation_store_info_lookup"
        sub_intent = "reservation_store_reference"
        entities["reservation_store_reference"] = True
    elif current_service_duration_advisory:
        intent = "service_duration_advisory"
        sub_intent = "additional_service_duration"
        if re.search(r"얼라인먼트|휠\s*얼라이먼트", text, re.IGNORECASE):
            entities["service_type"] = "alignment"
    elif current_maintenance_addon_with_tire:
        intent = "maintenance_addon_with_tire_service"
        sub_intent = "store_service_availability"
        entities["service_type"] = "maintenance_addon"
    elif preserve_pending_today_install:
        intent = "stock_store_search"
        sub_intent = "today_install"
        entities["stock_check_mode"] = "preview"
    elif preorder_confirmation:
        intent = "quick_order_execute"
        sub_intent = "confirm"
    elif quantity_only_stock_continuation or quantity_slot_fill_stock_continuation:
        intent = "stock_store_search"
        sub_intent = "today_install" if explicit_preview_request else "stock"
        entities["stock_check_mode"] = "preview" if sub_intent == "today_install" else "inventory_only"
    elif store_scope_product_continuation:
        intent = "stock_store_search"
        use_preview_scope = bool(
            _is_order_or_reservation_context(slots)
            or _is_today_install_context(slots, requested_cal_day)
            or region_scope_product_continuation
        )
        sub_intent = "today_install" if use_preview_scope else "stock"
        entities["stock_check_mode"] = "preview" if use_preview_scope else "inventory_only"
    elif _PRICE_OR_COUPON_RE.search(text):
        intent = "price_or_coupon_check"
        sub_intent = "coupon" if "쿠폰" in text else "price"
    elif (
        _STORE_SCHEDULE_RE.search(text)
        and has_product
        and (has_location or requested_cal_day or today_requested)
    ):
        intent = "stock_store_search"
        sub_intent = "today_install"
        entities["stock_check_mode"] = "preview"
    elif _STORE_SCHEDULE_RE.search(text) and (store_name or has_location) and not has_product:
        intent = "store_schedule"
        sub_intent = "store_visit"
    elif _NOON_RE.search(text) and has_location and not has_product:
        intent = "store_schedule"
        sub_intent = "store_visit"
    elif current_favorite_store_lookup:
        intent = "favorite_store_lookup"
        sub_intent = "favorite"
    elif _STORE_SEARCH_RE.search(text) and has_location and not has_product:
        intent = "store_search"
        sub_intent = "nearby" if entities["nearby"] else "region"
    elif (_STOCK_RE.search(text) or today_requested) and has_product:
        intent = "stock_store_search"
        sub_intent = "today_install" if today_requested else "stock"
        entities["stock_check_mode"] = "preview" if sub_intent == "today_install" else "inventory_only"
    elif (_RESERVATION_RE.search(text) or current_purchase) and has_product:
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
        has_location=has_location or today_install_candidate_scope,
        has_store=bool(store_name or slots.get("shop_id")),
        shop_id=slots.get("shop_id"),
        requested_cal_day=requested_cal_day or slots.get("requested_cal_day"),
        rsv_hour=slots.get("rsv_hour"),
    )

    known = {
        **slots,
        **({"region": region} if region else {}),
        **({"limit": result_limit} if result_limit else {}),
        **({"requested_cal_day": requested_cal_day} if requested_cal_day else {}),
    }
    if intent == "stock_store_search" and requested_cal_day:
        known["availability_intent"] = "today_install"
    if intent == "maintenance_addon_with_tire_service":
        known["pending_intent"] = "maintenance_addon_with_tire_service"
        known["goal_type"] = "store_service_availability"
        known["service_type"] = "maintenance_addon"
    if intent == "reservation_store_info_lookup":
        known["pending_intent"] = "reservation_store_info_lookup"
        known["goal_type"] = "reservation_store_info"
        known["reservation_store_reference"] = True
    if intent == "stock_store_search":
        known["stock_check_mode"] = str(entities.get("stock_check_mode") or "inventory_only")
        if requested_cal_day:
            known["requested_cal_day"] = requested_cal_day
        if quantity:
            known["quantity"] = quantity
            known["ord_qty"] = quantity
    if plain_store_search and not current_has_product and not preserve_transaction_product_context:
        for key in ("goods_no", "product_name", "pattern_name", "tire_size", "quantity", "ord_qty", "store_name"):
            known.pop(key, None)
    else:
        known.update({
            **({"tire_size": tire_size} if tire_size else {}),
            **({"quantity": quantity, "ord_qty": quantity} if quantity else {}),
            **({"product_name": product_name} if product_name else {}),
            **({"store_name": store_name} if store_name else {}),
            **({"shop_name": store_name} if store_name else {}),
        })
    if store_candidate_search or region_scope_product_continuation:
        for key in ("shop_id", "shop_name", "store_name"):
            known.pop(key, None)
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
    action = _transaction_action(frame)
    action_required_slots = _action_required_slots(frame, action)
    if (
        frame.intent in {"stock_store_search", "quick_order_reservation"}
        and "tire_size" in action_required_slots
        and not frame.known_slots.get("goods_no")
    ):
        return ToolPlan(
            allowed_tools=(),
            preferred_tool=None,
            tool_args_patch={},
            forbidden_tools=(
                "get_store_list_tool",
                "get_store_detail_tool",
                "get_store_schedule_tool",
                "transaction_store_preview_tool",
                "get_store_inventory_tool",
            ),
            required_slots=action_required_slots,
            metadata={
                "response_intent": frame.intent,
                "action": action,
                "guard": "require_product_size_before_transaction",
            },
        )
    if frame.intent == "stock_store_search":
        args = _slot_args(
            frame,
            "goods_no",
            "tire_size",
            "quantity",
            "region",
            "store_name",
            "requested_cal_day",
            "shop_id",
            "shop_name",
        )
        stock_check_mode = str(frame.known_slots.get("stock_check_mode") or frame.entities.get("stock_check_mode") or "")
        if frame.entities.get("today_requested"):
            args["today_only"] = True
        if stock_check_mode == "inventory_only" and frame.sub_intent == "stock":
            preferred_tool = "get_store_list_tool" if frame.known_slots.get("shop_name") and not frame.known_slots.get("shop_id") else "get_store_inventory_tool"
            return ToolPlan(
                allowed_tools=("get_store_inventory_tool", "get_store_list_tool"),
                preferred_tool=preferred_tool,
                tool_args_patch=args,
                forbidden_tools=("transaction_store_preview_tool", "get_store_schedule_tool", "preorder_with_null_required_fields"),
                required_slots=action_required_slots,
                metadata={
                    "response_intent": "stock_store_search",
                    "stock_check_mode": "inventory_only",
                    "action": action,
                },
            )
        return ToolPlan(
            allowed_tools=("transaction_store_preview_tool", "get_store_inventory_tool", "get_store_list_tool"),
            preferred_tool="transaction_store_preview_tool",
            tool_args_patch=args,
            forbidden_tools=("get_store_schedule_tool", "preorder_with_null_required_fields"),
            required_slots=action_required_slots,
            metadata={
                "response_intent": "stock_store_search",
                "stock_check_mode": "preview",
                "action": action,
            },
        )

    if frame.intent == "store_schedule":
        return ToolPlan(
            allowed_tools=("get_store_list_tool", "get_store_schedule_tool", "get_store_detail_tool"),
            preferred_tool="get_store_schedule_tool",
            tool_args_patch=_slot_args(frame, "store_name", "region"),
            forbidden_tools=("transaction_store_preview_tool",),
            required_slots=action_required_slots,
            metadata={"response_intent": "store_schedule", "action": action},
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
            required_slots=action_required_slots,
            metadata={"response_intent": "store_search", "action": action},
        )

    if frame.intent == "favorite_store_lookup":
        return ToolPlan(
            allowed_tools=("get_favorite_stores_tool",),
            preferred_tool="get_favorite_stores_tool",
            tool_args_patch={},
            forbidden_tools=("search_stores_tool", "get_store_list_tool", "get_nearby_stores_tool"),
            required_slots=action_required_slots,
            metadata={"response_intent": "favorite_store_lookup", "action": action},
        )

    if frame.intent == "reservation_store_info_lookup":
        return ToolPlan(
            allowed_tools=("get_my_reservations_tool", "get_orders_of_user_tool", "get_order_status_tool"),
            preferred_tool="get_my_reservations_tool",
            tool_args_patch={"sct_cd": "all"},
            forbidden_tools=("search_stores_tool", "get_store_list_tool", "get_nearby_stores_tool"),
            required_slots=action_required_slots,
            metadata={"response_intent": "reservation_store_info_lookup", "action": action},
        )

    if frame.intent == "service_duration_advisory":
        return ToolPlan(
            allowed_tools=(),
            preferred_tool=None,
            tool_args_patch={},
            forbidden_tools=("get_store_schedule_tool", "get_store_detail_tool", "transaction_store_preview_tool"),
            required_slots=(),
            metadata={"response_intent": "service_duration_advisory", "action": action},
        )

    if frame.intent == "maintenance_addon_with_tire_service":
        return ToolPlan(
            allowed_tools=("get_store_list_tool", "get_store_detail_tool"),
            preferred_tool="get_store_list_tool",
            tool_args_patch=_slot_args(frame, "store_name", "shop_id"),
            forbidden_tools=(
                "get_store_schedule_tool",
                "transaction_store_preview_tool",
                "get_maintenance_dday_tool",
            ),
            required_slots=action_required_slots,
            metadata={"response_intent": "maintenance_addon_with_tire_service", "action": action},
        )

    if frame.intent == "quick_order_reservation":
        return ToolPlan(
            allowed_tools=("transaction_store_preview_tool", "get_multi_store_schedule_tool", "get_store_schedule_tool"),
            preferred_tool="transaction_store_preview_tool",
            tool_args_patch=_slot_args(
                frame, "goods_no", "tire_size", "quantity", "store_name", "region", "requested_cal_day"
            ),
            forbidden_tools=("store_hours_instead_of_slots", "order_summary_with_null_required_fields"),
            required_slots=action_required_slots,
            metadata={"response_intent": "quick_order_reservation", "action": action},
        )

    if frame.intent == "quick_order_execute":
        args = _slot_args(
            frame,
            "goods_no",
            "ord_qty",
            "quantity",
            "shop_id",
            "requested_cal_day",
            "rsv_hour",
            "car_lnc_cd",
            "payment_amount",
        )
        if action_required_slots:
            return ToolPlan(
                allowed_tools=(),
                preferred_tool=None,
                tool_args_patch=args,
                forbidden_tools=("transaction_store_preview_tool", "get_store_schedule_tool"),
                required_slots=action_required_slots,
                metadata={"response_intent": "quick_order_execute", "action": action},
            )
        return ToolPlan(
            allowed_tools=("quick_order_tool",),
            preferred_tool="quick_order_tool",
            tool_args_patch=args,
            forbidden_tools=("transaction_store_preview_tool", "get_store_schedule_tool"),
            required_slots=action_required_slots,
            metadata={"response_intent": "quick_order_execute", "action": action},
        )

    if frame.intent == "price_or_coupon_check":
        return ToolPlan(
            allowed_tools=("get_final_price_tool", "get_my_coupons_tool", "get_coupon_applicable_products_tool"),
            preferred_tool="get_final_price_tool",
            tool_args_patch=_slot_args(frame, "goods_no", "tire_size", "quantity"),
            required_slots=action_required_slots,
            metadata={"response_intent": "price_or_coupon_check", "action": action},
        )

    return ToolPlan(required_slots=action_required_slots, metadata={"response_intent": frame.intent, "action": action})


def _transaction_action(frame: IntentFrame) -> str:
    if frame.intent == "stock_store_search":
        stock_check_mode = str(frame.known_slots.get("stock_check_mode") or frame.entities.get("stock_check_mode") or "")
        if stock_check_mode == "inventory_only":
            return "store_inventory_lookup"
        if (
            frame.known_slots.get("region")
            or frame.known_slots.get("lat")
            or frame.known_slots.get("lng")
            or not _has_action_store(frame)
        ):
            return "regional_install_availability_preview"
        return "selected_store_schedule"
    if frame.intent == "store_schedule":
        return "selected_store_schedule"
    if frame.intent == "service_duration_advisory":
        return "service_duration_advisory"
    if frame.intent == "maintenance_addon_with_tire_service":
        return "maintenance_addon_with_tire_service"
    if frame.intent == "reservation_store_info_lookup":
        return "reservation_store_info_lookup"
    return frame.intent or "transaction_fallback"


def _has_action_product(frame: IntentFrame) -> bool:
    return bool(
        frame.known_slots.get("goods_no")
        or frame.known_slots.get("product_name")
        or frame.known_slots.get("tire_model")
        or frame.known_slots.get("pattern_name")
        or frame.known_slots.get("pending_product_name")
    )


def _has_action_location(frame: IntentFrame) -> bool:
    return bool(
        frame.known_slots.get("region")
        or frame.known_slots.get("place")
        or frame.known_slots.get("lat")
        or frame.known_slots.get("lng")
        or frame.known_slots.get("shop_id")
        or frame.known_slots.get("shop_name")
        or frame.known_slots.get("store_name")
    )


def _has_action_store(frame: IntentFrame) -> bool:
    return bool(frame.known_slots.get("shop_id") or frame.known_slots.get("shop_name") or frame.known_slots.get("store_name"))


def _has_action_date(frame: IntentFrame) -> bool:
    return bool(
        frame.known_slots.get("requested_cal_day")
        or frame.known_slots.get("availability_intent") == "today_install"
        or frame.entities.get("today_requested")
    )


def _action_required_slots(frame: IntentFrame, action: str) -> tuple[str, ...]:
    required: list[str] = []

    def add(slot: str, condition: bool) -> None:
        if condition and slot not in required:
            required.append(slot)

    if action == "regional_install_availability_preview":
        add("product", not _has_action_product(frame))
        add("tire_size", not (frame.known_slots.get("tire_size") or frame.known_slots.get("goods_no")))
        add("quantity", not (frame.known_slots.get("quantity") or frame.known_slots.get("ord_qty")))
        add("location", not (_has_action_location(frame) or frame.entities.get("today_install_candidate_scope")))
        add("requested_cal_day", not _has_action_date(frame))
    elif action == "store_inventory_lookup":
        add("product", not _has_action_product(frame))
        add("tire_size", not (frame.known_slots.get("tire_size") or frame.known_slots.get("goods_no")))
        add("quantity", not (frame.known_slots.get("quantity") or frame.known_slots.get("ord_qty")))
        add("store", not _has_action_store(frame))
    elif action == "selected_store_schedule":
        add("store", not _has_action_store(frame))
        stock_context = bool(frame.known_slots.get("goods_no") or frame.known_slots.get("stock_check_mode") == "preview")
        if stock_context:
            add("product", not _has_action_product(frame))
            add("quantity", not (frame.known_slots.get("quantity") or frame.known_slots.get("ord_qty")))
            add("requested_cal_day", not _has_action_date(frame))
    elif action == "quick_order_reservation":
        add("product", not frame.known_slots.get("goods_no"))
        add("quantity", not (frame.known_slots.get("quantity") or frame.known_slots.get("ord_qty")))
        add("store", not _has_action_store(frame))
    elif action == "quick_order_execute":
        add("product", not frame.known_slots.get("goods_no"))
        add("quantity", not (frame.known_slots.get("quantity") or frame.known_slots.get("ord_qty")))
        add("store", not frame.known_slots.get("shop_id"))
        add("booking_datetime", not (frame.known_slots.get("requested_cal_day") and frame.known_slots.get("rsv_hour")))
    elif action == "maintenance_addon_with_tire_service":
        add("store", not _has_action_store(frame))
    else:
        for slot in frame.missing_slots:
            add(slot, True)
    return tuple(required)


def _missing_slots_for_intent(
    *,
    intent: str,
    has_product: bool,
    goods_no: Any,
    tire_size: Any,
    quantity: Any,
    has_location: bool,
    has_store: bool,
    shop_id: Any = None,
    requested_cal_day: Any = None,
    rsv_hour: Any = None,
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
    elif intent == "quick_order_execute":
        if not goods_no:
            missing.append("product")
        if not quantity:
            missing.append("quantity")
        if not shop_id:
            missing.append("store")
        if not requested_cal_day or not rsv_hour:
            missing.append("booking_datetime")
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
