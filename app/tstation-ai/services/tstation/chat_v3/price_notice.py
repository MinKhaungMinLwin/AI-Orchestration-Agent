"""User-visible price notice policy for Chat V3 answers."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any


PRICE_NOTICE = (
    "※ 실제 결제 금액은 보유 쿠폰을 기준으로 적용됩니다. "
    "다운로드 가능한 쿠폰은 상품 상세 또는 이벤트 페이지에서 확인해 주세요."
)

_VISIBLE_PRICE_FIELDS = frozenset({
    "extra_fvr_sale_prc",
    "sale_prc",
    "price",
    "final_unit_price",
    "final_price",
    "total_product_price",
    "payment_amount",
    "paymentamount",
})


def apply_price_notice(answer: str, tool_calls: Iterable[Mapping[str, Any]]) -> str:
    """Append the payment notice once when tool data contains a displayed price."""
    text = str(answer or "").strip()
    if PRICE_NOTICE in text:
        return text
    if not any(_tool_call_contains_visible_price(call) for call in tool_calls):
        return text
    return f"{text}\n{PRICE_NOTICE}" if text else PRICE_NOTICE


def _tool_call_contains_visible_price(call: Mapping[str, Any]) -> bool:
    output = _parse_output(call.get("output"))
    if not output:
        return False
    payload = output.get("data") if isinstance(output.get("data"), dict) else output
    return _contains_visible_price(payload)


def _parse_output(output: Any) -> dict[str, Any]:
    if isinstance(output, dict):
        return output
    try:
        parsed = json.loads(str(output or ""))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _contains_visible_price(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in _VISIBLE_PRICE_FIELDS and _has_price(item):
                return True
            if _contains_visible_price(item):
                return True
    elif isinstance(value, list):
        return any(_contains_visible_price(item) for item in value)
    return False


def _has_price(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        try:
            return float(value.replace(",", "")) > 0
        except ValueError:
            return False
    return False
