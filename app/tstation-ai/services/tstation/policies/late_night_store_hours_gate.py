"""Policy gate for late-night store-hours questions."""

from __future__ import annotations

import re

_LATE_NIGHT_RE = re.compile(
    r"심야|야간|밤\s*늦|밤늦|늦게|저녁\s*늦|퇴근\s*후|퇴근후|"
    r"19\s*시\s*이후|오후\s*7\s*시\s*이후|저녁\s*7\s*시\s*이후",
    re.IGNORECASE,
)
_STORE_CONTEXT_RE = re.compile(
    r"티스테이션|매장|지점|곳|영업|운영|문\s*열|문\s*여|예약|장착|교체|작업",
    re.IGNORECASE,
)
_STORE_HOURS_RE = re.compile(r"영업|운영|문\s*열|문\s*여|오픈|마감|닫", re.IGNORECASE)
_TIME_AFTER_19_RE = re.compile(r"19\s*시\s*이후|오후\s*7\s*시\s*이후|저녁\s*7\s*시\s*이후", re.IGNORECASE)
_LATE_INSTALL_PLACE_RE = re.compile(
    r"(?:예약|장착|교체|작업).{0,12}(?:곳|매장|지점)|(?:곳|매장|지점).{0,12}(?:예약|장착|교체|작업)",
    re.IGNORECASE,
)


def is_late_night_store_hours_policy_request(user_text: str) -> bool:
    """Return True when the turn asks for late-night operating-hours guidance."""

    text = str(user_text or "")
    if not (_LATE_NIGHT_RE.search(text) and _STORE_CONTEXT_RE.search(text)):
        return False
    if _TIME_AFTER_19_RE.search(text):
        return True
    if _LATE_INSTALL_PLACE_RE.search(text):
        return True
    return bool(_STORE_HOURS_RE.search(text))
