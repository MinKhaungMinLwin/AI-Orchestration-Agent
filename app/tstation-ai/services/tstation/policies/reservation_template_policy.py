"""Reservation/store template policy helpers.

This module owns deterministic corrections around store booking templates:
preview schedule slots should render as `datepick`, while stock-store contexts
must stay on the location path.
"""
import datetime
import json
import re
from typing import Any

_RESERVATION_TIME_CHIP_RE = re.compile(r"^\s*(?:[01]?\d|2[0-3])\s*시\s*예약\s*$")
_RESERVATION_OTHER_TIME_LABELS = {"다른 시간 선택", "다른 시간대 선택"}
_WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")
_WEEKDAY_REQUEST_RE = re.compile(
    r"(?:이번\s*주|다음\s*주|다다음\s*주)?\s*(월|화|수|목|금|토|일)\s*(?:요일|욜)"
)
_WEEKEND_REQUEST_RE = re.compile(r"(?:이번\s*주말|다음\s*주말|주말)")
_EXACT_DATE_REQUEST_RE = re.compile(
    r"(?:(?P<year>\d{2,4})\s*년\s*)?(?P<month>\d{1,2})\s*(?:/\s*|월\s*)(?P<day>3[01]|[12]?\d)(?:\s*일)?"
)
_STOCK_STORE_TEXT_RE = re.compile(r"재고\s*(있는|가\s*확인된)\s*매장|재고있는\s*매장")
_GENERIC_DISCOVERY_FALLBACK_TEXT_RE = re.compile(
    r"검색된\s*상품\s*정보를\s*기준으로\s*안내|상품명이나\s*조건을\s*조금\s*더\s*구체적으로|"
    r"차량에\s*맞는\s*규격\s*확인",
    re.IGNORECASE,
)
_GENERIC_DISCOVERY_FALLBACK_LABELS = {"보유차량 중 선택", "차번+이름으로 검색", "사이즈 직접 입력"}
_OTHER_STORE_REQUEST_RE = re.compile(
    r"(?:다른|추가|더)\s*(?:매장|지점)|(?:매장|지점)\s*(?:더|또|추가)"
)
_SCHEDULE_CONFIRMATION_RE = re.compile(
    r"장착\s*가능\s*일정|가능\s*일정|예약\s*가능\s*(?:일정|시간)|"
    r"선택\s*가능한\s*(?:장착\s*)?일정|예약\s*시간|일정\s*맞|시간\s*맞",
    re.IGNORECASE,
)
_SCHEDULE_REQUEST_RE = re.compile(
    r"예약\s*(?:가능|해|시간|일정|스케줄)|"
    r"장착\s*(?:가능|예약|시간|일정)|"
    r"방문\s*(?:예약|시간|일정)|"
    r"가능한\s*(?:날짜|시간|일정)|"
    r"스케줄(?:표)?|시간표",
    re.IGNORECASE,
)
_NEW_STORE_SCOPE_REQUEST_RE = re.compile(
    r"(?:오늘|내일|모레).{0,30}(?:지역|근처|주변|매장|지점)|"
    r"(?:지역|근처|주변).{0,20}(?:매장|지점)|"
    r"(?:매장|지점).{0,20}(?:찾|검색|알려|보여)",
    re.IGNORECASE,
)


def yyyymmdd_to_korean_date(s: str) -> str:
    try:
        dt = datetime.datetime.strptime(s, "%Y%m%d")
    except (TypeError, ValueError):
        return s
    return f"{dt.year}년 {dt.month}월 {dt.day}일 ({_WEEKDAY_KO[dt.weekday()]})"


def parse_slot_hour(tm: object, *, exclude_noon: bool = True) -> int | None:
    s = str(tm or "").strip()
    if not s.isdigit():
        return None
    if len(s) <= 2:
        hour = int(s)
    elif len(s) == 4:
        hour = int(s[:2])
    else:
        return None
    if exclude_noon and hour == 12:
        return None
    return hour if 0 <= hour <= 23 else None


def _extract_shop_ids(values: object) -> set[str]:
    if not isinstance(values, list):
        return set()
    shop_ids: set[str] = set()
    for item in values:
        if isinstance(item, dict):
            sid = item.get("shop_id") or item.get("shopId") or item.get("shop_seq") or item.get("shopSeq")
        else:
            sid = item
        if sid:
            shop_ids.add(str(sid))
    return shop_ids


def _parse_positive_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def reservation_sale_min_install_date(preview_payload: dict, shop_id: str) -> str | None:
    logistics = preview_payload.get("logistics")
    inventory = preview_payload.get("inventory")
    if not isinstance(logistics, dict) or not isinstance(inventory, dict):
        return None
    if _parse_positive_int(logistics.get("logistics_qty") or logistics.get("logisticsQty") or logistics.get("qty")) > 0:
        return None
    if str(logistics.get("rsv_sale_yn") or logistics.get("rsvSaleYn") or "").upper() != "Y":
        return None
    if shop_id in _extract_shop_ids(inventory.get("todayShopArray")):
        return None
    if shop_id in _extract_shop_ids(inventory.get("tnaShopArray")):
        return None
    rsv_install_date = re.sub(r"\D", "", str(logistics.get("rsv_install_date") or logistics.get("rsvInstallDate") or ""))
    return rsv_install_date if re.fullmatch(r"\d{8}", rsv_install_date) else None


def extract_preview_payload(parsed: dict) -> dict | None:
    if parsed.get("status") == "success" and isinstance(parsed.get("data"), dict):
        return parsed["data"]
    data = parsed.get("data")
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return parsed if isinstance(parsed, dict) else None


def should_keep_stock_location(
    *,
    pending_intent: str | None,
    goal_type: str | None,
    assistant_text: str,
    exact_order_preview: bool = False,
) -> bool:
    if exact_order_preview:
        return False
    if pending_intent == "stock" or goal_type == "store_with_stock":
        return True
    return bool(_STOCK_STORE_TEXT_RE.search(assistant_text or ""))


def is_other_store_request(user_text: str) -> bool:
    """True when the user is asking for alternative store candidates."""
    return bool(_OTHER_STORE_REQUEST_RE.search(user_text or ""))


def latest_template_data_from_messages(messages: list[dict], template_name: str) -> dict | None:
    """Return the newest template data payload from prefetched template history."""
    for message in messages:
        template_data = message.get("template_data")
        if not isinstance(template_data, dict) or template_data.get("template") != template_name:
            continue
        data = template_data.get("data")
        if isinstance(data, dict):
            return data
    return None


def build_datepick_from_preview_payload(
    preview_payload: dict,
    *,
    assistant_text: str,
    source_domain: str | None = None,
    assistant_response_source: str,
    require_single_store: bool,
) -> dict | None:
    schedule = preview_payload.get("schedule")
    if not isinstance(schedule, dict) or str(schedule.get("tier") or "").lower() == "none":
        return None
    schedule_stores = schedule.get("stores")
    if not isinstance(schedule_stores, list):
        return None
    if require_single_store and len(schedule_stores) != 1:
        return None

    for store in schedule_stores:
        if not isinstance(store, dict):
            continue
        shop_id = str(store.get("shop_id") or "").strip()
        slots = store.get("slots")
        if not shop_id or not isinstance(slots, list):
            continue
        min_install_date = reservation_sale_min_install_date(preview_payload, shop_id)
        by_day: dict[str, set[int]] = {}
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            cal_day = str(slot.get("cal_day") or "").strip()
            if min_install_date and cal_day < min_install_date:
                continue
            hour = parse_slot_hour(slot.get("tm"))
            if cal_day and hour is not None:
                by_day.setdefault(cal_day, set()).add(hour)
        if not by_day:
            continue

        dates: list[dict] = []
        selected_idx: int | None = None
        for idx, cal_day in enumerate(sorted(by_day.keys())):
            times = sorted(by_day[cal_day])
            available = bool(times)
            dates.append({
                "date": yyyymmdd_to_korean_date(cal_day),
                "available": available,
                "availableTimes": times,
                "index": idx,
            })
            if selected_idx is None and available:
                selected_idx = idx
        if selected_idx is None:
            continue

        metadata = {"shopId": shop_id}
        shop_name = str(store.get("shop_nm") or "").strip()
        if shop_name:
            metadata["shopName"] = shop_name
        event = {
            "type": "data",
            "template": "datepick",
            "assistant_response_source": assistant_response_source,
            "data": {
                "assistantResponse": assistant_text or "예약하려는 날짜와 시간을 선택해 주세요.",
                "dates": dates,
                "selectedDate": selected_idx,
                "metadata": metadata,
            },
        }
        if source_domain is not None:
            event["source_domain"] = source_domain
        return event
    return None


def _store_name_from_preview_payload(preview_payload: dict) -> str:
    schedule = preview_payload.get("schedule")
    if isinstance(schedule, dict):
        stores = schedule.get("stores")
        if isinstance(stores, list):
            for store in stores:
                if isinstance(store, dict):
                    shop_name = str(store.get("shop_nm") or "").strip()
                    if shop_name:
                        return shop_name
    stores = preview_payload.get("stores")
    if isinstance(stores, list):
        for store in stores:
            if isinstance(store, dict):
                shop_name = str(store.get("shop_nm") or "").strip()
                if shop_name:
                    return shop_name
    return ""


def _is_generic_discovery_fallback_quickreply(event_data: dict, assistant_text: str) -> bool:
    if _GENERIC_DISCOVERY_FALLBACK_TEXT_RE.search(assistant_text):
        return True
    quick_replies = event_data.get("quickReplies")
    if not isinstance(quick_replies, list):
        return False
    labels = {
        str(reply.get("label") or "").strip()
        for reply in quick_replies
        if isinstance(reply, dict)
    }
    return bool(labels & _GENERIC_DISCOVERY_FALLBACK_LABELS)


def _order_preview_datepick_assistant_text(
    event_data: dict,
    preview_payload: dict,
    assistant_text: str,
) -> str:
    if assistant_text and not _is_generic_discovery_fallback_quickreply(event_data, assistant_text):
        return assistant_text
    shop_name = _store_name_from_preview_payload(preview_payload)
    if shop_name:
        return f"{shop_name}에서 예약하려는 날짜와 시간을 선택해 주세요."
    return "예약하려는 날짜와 시간을 선택해 주세요."


def build_datepick_from_schedule_payload(
    schedule_payload: dict,
    *,
    assistant_text: str,
    source_domain: str | None = None,
    assistant_response_source: str,
) -> dict | None:
    """Build a datepick event from `get_store_schedule_tool` payload/context."""
    raw = schedule_payload.get("data") if isinstance(schedule_payload.get("data"), dict) else schedule_payload
    if not isinstance(raw, dict):
        return None

    shop_id = str(raw.get("shop_id") or raw.get("shopId") or "").strip()
    slots = raw.get("slots")
    if not shop_id or not isinstance(slots, list):
        return None

    by_day: dict[str, set[int]] = {}
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        cal_day = str(slot.get("cal_day") or slot.get("calDay") or "").strip()
        hour = parse_slot_hour(slot.get("tm"))
        if cal_day and hour is not None:
            by_day.setdefault(cal_day, set()).add(hour)
    if not by_day:
        return None

    dates: list[dict] = []
    selected_idx: int | None = None
    for idx, cal_day in enumerate(sorted(by_day.keys())):
        times = sorted(by_day[cal_day])
        available = bool(times)
        dates.append({
            "date": yyyymmdd_to_korean_date(cal_day),
            "available": available,
            "availableTimes": times,
            "index": idx,
        })
        if selected_idx is None and available:
            selected_idx = idx
    if selected_idx is None:
        return None

    metadata = {"shopId": shop_id}
    shop_name = str(raw.get("shop_nm") or raw.get("shopName") or "").strip()
    if shop_name:
        metadata["shopName"] = shop_name

    event = {
        "type": "data",
        "template": "datepick",
        "assistant_response_source": assistant_response_source,
        "data": {
            "assistantResponse": assistant_text or "예약하려는 날짜와 시간을 선택해 주세요.",
            "dates": dates,
            "selectedDate": selected_idx,
            "metadata": metadata,
        },
    }
    if source_domain is not None:
        event["source_domain"] = source_domain
    return event


def _date_label_has_weekday(date_item: dict, weekday: str) -> bool:
    label = str(date_item.get("date") or "")
    return f"({weekday})" in label or f"{weekday}요일" in label


def _replace_datepick_dates(event_data: dict, dates: list[dict]) -> None:
    normalized_dates = []
    for idx, date_item in enumerate(dates):
        normalized_item = dict(date_item)
        normalized_item["index"] = idx
        normalized_dates.append(normalized_item)
    event_data["dates"] = normalized_dates
    event_data["selectedDate"] = 0


def _extract_requested_month_day(user_text: str) -> tuple[int | None, int, int] | None:
    match = _EXACT_DATE_REQUEST_RE.search(user_text or "")
    if not match:
        return None
    year_text = match.group("year")
    year = int(year_text) if year_text else None
    if year is not None and year < 100:
        year += 2000
    return year, int(match.group("month")), int(match.group("day"))


def _parse_date_label_components(label: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?P<year>\d{4})년\s*(?P<month>\d{1,2})월\s*(?P<day>\d{1,2})일", label or "")
    if not match:
        return None
    return int(match.group("year")), int(match.group("month")), int(match.group("day"))


def _first_contiguous_weekend_dates(dates: list[dict]) -> list[dict]:
    weekend_dates: list[dict] = []
    for date_item in dates:
        if not isinstance(date_item, dict):
            continue
        is_weekend = _date_label_has_weekday(date_item, "토") or _date_label_has_weekday(date_item, "일")
        if is_weekend:
            weekend_dates.append(date_item)
            continue
        if weekend_dates:
            break
    return weekend_dates


def filter_datepick_to_requested_weekday(event: dict, user_text: str) -> dict | None:
    """Narrow datepick dates when the user explicitly asks for a weekday or weekend."""
    if event.get("template") != "datepick":
        return None
    event_data = event.get("data")
    if not isinstance(event_data, dict):
        return None
    dates = event_data.get("dates")
    if not isinstance(dates, list) or len(dates) <= 1:
        return None

    if _WEEKEND_REQUEST_RE.search(user_text or ""):
        weekend_dates = _first_contiguous_weekend_dates(dates)
        if not weekend_dates:
            return None
        _replace_datepick_dates(event_data, weekend_dates)
        has_default_response = (
            not event_data.get("assistantResponse")
            or event_data["assistantResponse"] == "예약하려는 날짜와 시간을 선택해 주세요."
        )
        if has_default_response:
            event_data["assistantResponse"] = "이번 주말 예약 가능한 시간을 선택해 주세요."
        return event

    match = _WEEKDAY_REQUEST_RE.search(user_text or "")
    if not match:
        return None
    requested_weekday = match.group(1)
    for date_item in dates:
        if not isinstance(date_item, dict):
            continue
        if not _date_label_has_weekday(date_item, requested_weekday):
            continue
        label = str(date_item.get("date") or "")
        _replace_datepick_dates(event_data, [date_item])
        has_default_response = (
            not event_data.get("assistantResponse")
            or event_data["assistantResponse"] == "예약하려는 날짜와 시간을 선택해 주세요."
        )
        if has_default_response:
            event_data["assistantResponse"] = f"{label} 예약 가능한 시간을 선택해 주세요."
        return event
    return None


def coerce_reservation_quickreply_to_datepick(
    event: dict,
    structured_sources: list[tuple[str, dict]],
    slot_state: Any | None,
) -> dict | None:
    """Convert LLM reservation-time chips to the datepick template."""
    if event.get("template") != "quickReply":
        return None
    event_data = event.get("data")
    if not isinstance(event_data, dict):
        return None
    chips = event_data.get("quickReplies")
    if not isinstance(chips, list) or not chips:
        return None
    labels = [
        str(chip.get("label", "")).strip()
        for chip in chips
        if isinstance(chip, dict)
    ]
    has_reservation_time_chip = any(_RESERVATION_TIME_CHIP_RE.match(label) for label in labels)
    has_only_reservation_chips = all(
        _RESERVATION_TIME_CHIP_RE.match(label) or label in _RESERVATION_OTHER_TIME_LABELS
        for label in labels
    )
    if not has_reservation_time_chip or not has_only_reservation_chips:
        return None

    pending_intent = getattr(slot_state, "pending_intent", None)
    goal_type = getattr(slot_state, "goal_type", None)
    assistant_text = str(event_data.get("assistantResponse") or "")
    if should_keep_stock_location(
        pending_intent=pending_intent,
        goal_type=goal_type,
        assistant_text=assistant_text,
    ):
        return None

    preview_payload = None
    for tool_name, parsed in reversed(structured_sources):
        if tool_name != "transaction_store_preview_tool" or not isinstance(parsed, dict):
            continue
        preview_payload = extract_preview_payload(parsed)
        if isinstance(preview_payload, dict):
            break
    if not isinstance(preview_payload, dict):
        return None

    return build_datepick_from_preview_payload(
        preview_payload,
        assistant_text=assistant_text,
        source_domain=event.get("source_domain"),
        assistant_response_source="code_mapper_preview_quickreply",
        require_single_store=False,
    )


def coerce_order_preview_quickreply_to_datepick(
    event: dict,
    structured_sources: list[tuple[str, dict]],
    slot_state: Any | None,
) -> dict | None:
    """Recover order-preview turns where the LLM emits a generic quickReply.

    `transaction_store_preview_tool` is enough to render the next required step
    for a named-store order: date/time selection. This guard is intentionally
    narrower than `coerce_reservation_quickreply_to_datepick()` so pure stock
    checks can keep their location/stock response.
    """
    if event.get("template") != "quickReply":
        return None
    event_data = event.get("data")
    if not isinstance(event_data, dict):
        return None

    pending_intent = getattr(slot_state, "pending_intent", None)
    goal_type = getattr(slot_state, "goal_type", None)
    assistant_text = str(event_data.get("assistantResponse") or "")
    if should_keep_stock_location(
        pending_intent=pending_intent,
        goal_type=goal_type,
        assistant_text=assistant_text,
        exact_order_preview=True,
    ):
        return None
    if pending_intent not in {"order", "reservation"} and goal_type != "place_order":
        return None

    for tool_name, parsed in reversed(structured_sources):
        if tool_name != "transaction_store_preview_tool" or not isinstance(parsed, dict):
            continue
        preview_payload = extract_preview_payload(parsed)
        if not isinstance(preview_payload, dict):
            continue
        datepick_assistant_text = _order_preview_datepick_assistant_text(
            event_data,
            preview_payload,
            assistant_text,
        )
        event = build_datepick_from_preview_payload(
            preview_payload,
            assistant_text=datepick_assistant_text,
            source_domain=event.get("source_domain"),
            assistant_response_source="code_mapper_order_preview_quickreply",
            require_single_store=True,
        )
        if event is not None:
            return event
    return None


def coerce_schedule_confirmation_quickreply_to_datepick(
    event: dict,
    *,
    user_text: str,
    latest_datepick_data: dict | None,
    structured_sources: list[tuple[str, dict]] | None = None,
    default_source_domain: str = "transaction",
) -> dict | None:
    """Re-render the previous date picker for schedule clarification turns.

    If the user asks "장착 가능일정이야?" right after a datepick card, the agent
    may answer in prose with an empty quickReply. Generic fallback chips then
    add "1:1 문의하기", contradicting the text that asks the user to select a
    date/time. In that narrow case, reuse the latest datepick card.
    """
    if event.get("template") != "quickReply":
        return None
    if str(event.get("assistant_response_source") or "") == "discovery_policy":
        return None
    event_data = event.get("data")
    if not isinstance(event_data, dict):
        return None
    is_schedule_followup = bool(
        _SCHEDULE_CONFIRMATION_RE.search(user_text or "")
        or _SCHEDULE_REQUEST_RE.search(user_text or "")
    )
    if not is_schedule_followup:
        return None
    if _NEW_STORE_SCOPE_REQUEST_RE.search(user_text or ""):
        return None

    assistant_text = str(event_data.get("assistantResponse") or "")
    if isinstance(latest_datepick_data, dict):
        dates = latest_datepick_data.get("dates")
        if isinstance(dates, list) and dates:
            datepick_data = json.loads(json.dumps(latest_datepick_data, ensure_ascii=False))
            if assistant_text:
                datepick_data["assistantResponse"] = assistant_text
            else:
                datepick_data.setdefault("assistantResponse", "예약하려는 날짜와 시간을 선택해 주세요.")
            return {
                "type": "data",
                "template": "datepick",
                "source_domain": event.get("source_domain") or default_source_domain,
                "assistant_response_source": "code_mapper_schedule_confirmation",
                "data": datepick_data,
            }

    for tool_name, parsed in reversed(structured_sources or []):
        if tool_name != "get_store_schedule_tool" or not isinstance(parsed, dict):
            continue
        rebuilt = build_datepick_from_schedule_payload(
            parsed,
            assistant_text=assistant_text,
            source_domain=event.get("source_domain") or default_source_domain,
            assistant_response_source="code_mapper_schedule_confirmation",
        )
        if rebuilt is not None:
            return rebuilt
    return None


def filter_datepick_to_requested_date(event: dict, user_text: str) -> dict | None:
    """Narrow datepick dates when the user explicitly asks for a concrete date."""
    if event.get("template") != "datepick":
        return None
    event_data = event.get("data")
    if not isinstance(event_data, dict):
        return None
    dates = event_data.get("dates")
    if not isinstance(dates, list) or len(dates) <= 1:
        return None

    requested = _extract_requested_month_day(user_text)
    if requested is None:
        return None
    requested_year, requested_month, requested_day = requested
    for date_item in dates:
        if not isinstance(date_item, dict):
            continue
        components = _parse_date_label_components(str(date_item.get("date") or ""))
        if components is None:
            continue
        year, month, day = components
        if month != requested_month or day != requested_day:
            continue
        if requested_year is not None and year != requested_year:
            continue
        label = str(date_item.get("date") or "")
        _replace_datepick_dates(event_data, [date_item])
        has_default_response = (
            not event_data.get("assistantResponse")
            or event_data["assistantResponse"] == "예약하려는 날짜와 시간을 선택해 주세요."
        )
        if has_default_response:
            event_data["assistantResponse"] = f"{label} 예약 가능한 시간을 선택해 주세요."
        return event
    return None
