from __future__ import annotations

import datetime
import re
from typing import Any

_KST = datetime.timezone(datetime.timedelta(hours=9))
_EXPLICIT_DATE_RE = re.compile(
    r"(?:(?P<year>20\d{2})\s*(?:년|[./-])\s*)?"
    r"(?P<month>1[0-2]|0?[1-9])\s*(?:월|[./-])\s*"
    r"(?P<day>3[01]|[12]?\d)\s*일?",
    re.IGNORECASE,
)
_WEEKEND_RE = re.compile(r"(?:이번\s*주말|주말)", re.IGNORECASE)
_TIME_AFTER_RE = re.compile(r"(?:(?:오후|저녁)\s*)?(?P<hour>\d{1,2})\s*(?:시|:)", re.IGNORECASE)
_TIME_AFTER_HOUR_RE = re.compile(r"(?P<hour>\d{1,2})\s*시\s*이후", re.IGNORECASE)


def _kst_today() -> datetime.date:
    return datetime.datetime.now(_KST).date()


def normalize_store_place_query(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    compact = re.sub(r"\s+", "", text)
    if compact == "강남":
        return "강남역"
    if compact in {"경기권", "경기지역"}:
        return "경기도"
    return text


def _parse_explicit_date(text: str, *, today: datetime.date) -> datetime.date | None:
    match = _EXPLICIT_DATE_RE.search(text or "")
    if not match:
        return None
    year_text = match.group("year")
    year = int(year_text) if year_text else today.year
    month = int(match.group("month"))
    day = int(match.group("day"))
    try:
        parsed = datetime.date(year, month, day)
    except ValueError:
        return None
    if not year_text and parsed < today:
        parsed = datetime.date(today.year + 1, month, day)
    return parsed


def _requested_cal_days(user_text: str, known: dict[str, Any]) -> list[str]:
    today = _kst_today()
    date_text = str(known.get("date") or "").strip()
    text = user_text or ""

    if "오늘" in text:
        return [today.strftime("%Y%m%d")]
    if "내일" in text:
        return [(today + datetime.timedelta(days=1)).strftime("%Y%m%d")]
    if "모레" in text:
        return [(today + datetime.timedelta(days=2)).strftime("%Y%m%d")]
    if _WEEKEND_RE.search(text):
        week_start = today - datetime.timedelta(days=today.weekday())
        saturday = week_start + datetime.timedelta(days=5)
        sunday = week_start + datetime.timedelta(days=6)
        if sunday < today:
            saturday += datetime.timedelta(days=7)
            sunday += datetime.timedelta(days=7)
        return [saturday.strftime("%Y%m%d"), sunday.strftime("%Y%m%d")]

    explicit = _parse_explicit_date(text, today=today) or _parse_explicit_date(date_text, today=today)
    if explicit is not None:
        return [explicit.strftime("%Y%m%d")]

    digits = re.sub(r"\D", "", date_text)
    if len(digits) >= 8:
        return [digits[:8]]
    return []


def _requested_time_after_hour(user_text: str, known: dict[str, Any]) -> int | None:
    time_text = str(known.get("time") or "").strip()
    match = _TIME_AFTER_HOUR_RE.search(user_text or "") or _TIME_AFTER_RE.search(time_text)
    if not match:
        return None
    try:
        hour = int(match.group("hour"))
    except (TypeError, ValueError):
        return None
    return hour if 0 <= hour <= 23 else None


def resolve_store_schedule_search(user_text: str, known: dict[str, Any]) -> dict[str, Any] | None:
    cal_days = _requested_cal_days(user_text, known)
    if not cal_days:
        return None
    filters: dict[str, Any] = {
        "cal_days": cal_days,
        "open_only": True,
    }
    time_after_hour = _requested_time_after_hour(user_text, known)
    if time_after_hour is not None:
        filters["time_after_hour"] = time_after_hour
    return filters
