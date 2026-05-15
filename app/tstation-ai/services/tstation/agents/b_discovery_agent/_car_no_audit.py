"""Deterministic car_no audit shared across the Discovery turn.

The Discovery agent prompt repeatedly fails to honor "user-supplied car_no
must exact-match a registered car" — the LLM either calls a downstream tool
on a registered car that the user did not name, or injects placeholder
cards. Prompt guards alone have been insufficient.

This module records the user's latest message and the registered car_no list
returned by `get_my_cars_tool` as contextvars (per-request, asyncio-safe).
Downstream tools call `detect_car_no_mismatch()` and short-circuit before
issuing BE calls when a mismatch is detected.
"""

from __future__ import annotations

import re
from contextvars import ContextVar

# Korean license plates: 2-3 digits + 1 Hangul + 4 digits (whitespace tolerated).
_CAR_NO_RE = re.compile(r"\d{2,3}\s?[가-힣]\s?\d{4}")

_user_message: ContextVar[str] = ContextVar("car_audit_user_message", default="")
_registered_car_nos: ContextVar[tuple[str, ...]] = ContextVar(
    "car_audit_registered_car_nos", default=()
)


def _normalize(s: str) -> str:
    return s.replace(" ", "").replace("-", "")


def set_user_message(msg: str | None) -> None:
    """Record the user's latest message; resets registered list for this turn."""
    _user_message.set(msg or "")
    _registered_car_nos.set(())


def set_registered_car_nos(car_nos: list[str] | tuple[str, ...]) -> None:
    """Cache the registered car_no list pulled from get_my_cars_tool."""
    normalized = tuple(_normalize(c) for c in car_nos if c)
    _registered_car_nos.set(normalized)


def extract_user_car_nos() -> set[str]:
    return {_normalize(m) for m in _CAR_NO_RE.findall(_user_message.get())}


def detect_car_no_mismatch() -> str | None:
    """Return the first unmatched user-supplied car_no, or None if no mismatch.

    Returns None when:
      - user message contains no license plate pattern (nothing to check), or
      - registered list is empty (audit cannot tell), or
      - at least one user-supplied plate matches a registered plate.
    """
    user_car_nos = extract_user_car_nos()
    if not user_car_nos:
        return None
    registered = set(_registered_car_nos.get())
    if not registered:
        return None
    if user_car_nos & registered:
        return None
    return next(iter(user_car_nos))
