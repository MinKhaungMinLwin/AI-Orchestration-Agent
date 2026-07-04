"""Shared price-basis predicates for purchase/reservation boundaries."""

from __future__ import annotations

import re
from typing import Any, Mapping


PRICE_BASIS_FIELDS = (
    "payment_amount",
    "paymentAmount",
    "cheapest_final_prc",
    "final_unit_price",
    "final_prc",
    "final_price",
    "finalPrice",
    "price",
    "extra_fvr_sale_prc",
    "sale_prc",
)


def has_price_basis(slots: Mapping[str, Any] | None) -> bool:
    if not isinstance(slots, Mapping):
        return False
    return any(is_positive_number_like(slots.get(field)) for field in PRICE_BASIS_FIELDS)


def is_positive_number_like(value: Any) -> bool:
    if value in (None, "") or isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return value > 0
    text = str(value).strip().replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return False
    return any(char != "0" for char in text if char.isdigit())
