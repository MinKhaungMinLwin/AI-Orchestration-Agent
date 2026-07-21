"""User-visible price policy for Chat V3 tool data."""

from __future__ import annotations

import json
from typing import Any


PERSONALIZED_PRICE_FIELDS = frozenset(
    {
        "cheapest_final_prc",
        "cheapest_total_discount",
        "cheapest_applied_coupons",
        "cheapest_goods_no",
        "cheapest_price",
    }
)


def remove_personalized_price_fields(value: Any) -> Any:
    """Copy tool data without member-held-coupon price fields."""
    if isinstance(value, dict):
        return {
            key: remove_personalized_price_fields(item)
            for key, item in value.items()
            if str(key).lower() not in PERSONALIZED_PRICE_FIELDS
        }
    if isinstance(value, list):
        return [remove_personalized_price_fields(item) for item in value]
    return value


def redact_personalized_price_output(output: Any) -> Any:
    """Remove personalized prices while preserving the input representation."""
    if isinstance(output, str):
        try:
            parsed = json.loads(output)
        except (TypeError, ValueError):
            return output
        return json.dumps(remove_personalized_price_fields(parsed), ensure_ascii=False, default=str)
    return remove_personalized_price_fields(output)
