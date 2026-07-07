from __future__ import annotations

import datetime
import re
from typing import Any

_KST = datetime.timezone(datetime.timedelta(hours=9))


def _kst_now() -> datetime.datetime:
    return datetime.datetime.now(_KST)


def _digits_date(value: Any) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) >= 8:
        return digits[:8]
    return None


def _hour(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 4:
        digits = digits[:2]
    if len(digits) in {1, 2}:
        hour = int(digits)
        if 0 <= hour <= 23:
            return f"{hour:02d}"
    match = re.search(r"(\d{1,2})\s*시", text)
    if not match:
        return None
    hour = int(match.group(1))
    return f"{hour:02d}" if 0 <= hour <= 23 else None


def selected_schedule_datetime(
    date_value: Any,
    time_value: Any,
    *,
    now: datetime.datetime | None = None,
) -> datetime.datetime | None:
    date_digits = _digits_date(date_value)
    hour_text = _hour(time_value)
    if not (date_digits and hour_text):
        return None
    now = now or _kst_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=_KST)
    try:
        return datetime.datetime(
            int(date_digits[:4]),
            int(date_digits[4:6]),
            int(date_digits[6:8]),
            int(hour_text),
            0,
            tzinfo=now.tzinfo,
        )
    except ValueError:
        return None


def build_past_schedule_selection_event(
    date_value: Any,
    time_value: Any,
    *,
    now: datetime.datetime | None = None,
) -> dict[str, Any] | None:
    selected = selected_schedule_datetime(date_value, time_value, now=now)
    if selected is None:
        return None
    now = now or _kst_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=_KST)
    if selected.date() >= now.date():
        return None
    today_label = now.strftime("%Y-%m-%d")
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": (
                "지난 날짜의 예약 가능 여부는 조회가 불가능합니다. "
                f"오늘 날짜 {today_label} 이후로 다시 선택해 주세요."
            ),
            "quickReplies": [
                {"label": "예약 가능 날짜 보기", "domain": "TRANSACTION"},
                {"label": "다른 매장 보기", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["TRANSACTION"],
            "metadata": {
                "source": "llm_first_schedule_selection_past_datetime",
                "response_shape_key": "schedule_selection_past_datetime",
            },
        },
    }
