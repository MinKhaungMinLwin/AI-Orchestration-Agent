"""Coupon-price notice policy for Chat V3 answers."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

COUPON_PRICE_NOTICE = (
    "※ 보유 쿠폰 기준 가격이며, 상품 상세 페이지에서 미 다운로드 쿠폰 적용 시 추가 할인 받으실 수 있습니다."
)

_COUPON_PRICE_FIELDS = frozenset({"cheapest_final_prc", "cheapest_price"})
_COUPON_LIST_FIELDS = frozenset({"cheapest_applied_coupons", "applied_coupons"})
_CHEAPEST_PRICE_TOOL = "get_cheapest_price_tool"


def apply_coupon_price_notice(answer: str, tool_calls: Iterable[Mapping[str, Any]]) -> str:
    """Append the coupon-price notice when tool data exposes coupon-based prices."""
    text = str(answer or "").strip()
    if not text or COUPON_PRICE_NOTICE in text:
        return text
    if not any(_tool_call_uses_coupon_price(call) for call in tool_calls):
        return text
    return f"{text}\n\n{COUPON_PRICE_NOTICE}"


def _tool_call_uses_coupon_price(call: Mapping[str, Any]) -> bool:
    output = _parse_output(call.get("output"))
    if not output:
        return False
    payload = output.get("data") if isinstance(output.get("data"), dict) else output
    if _contains_coupon_price_signal(payload):
        return True
    return str(call.get("name") or "") == _CHEAPEST_PRICE_TOOL and _contains_price_value(payload)


def _parse_output(output: Any) -> dict[str, Any]:
    if isinstance(output, dict):
        return output
    try:
        parsed = json.loads(str(output or ""))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _contains_coupon_price_signal(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _COUPON_PRICE_FIELDS and _has_value(item):
                return True
            if key in _COUPON_LIST_FIELDS and _has_coupon_items(item):
                return True
            if _contains_coupon_price_signal(item):
                return True
    elif isinstance(value, list):
        return any(_contains_coupon_price_signal(item) for item in value)
    return False


def _contains_price_value(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            (str(key).endswith("_prc") or str(key).endswith("_price") or key in {"finalPrice", "price"})
            and _has_value(item)
            or _contains_price_value(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_price_value(item) for item in value)
    return False


def _has_coupon_items(value: Any) -> bool:
    return isinstance(value, list) and any(isinstance(item, Mapping) and item for item in value)


def _has_value(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value > 0
    return True
