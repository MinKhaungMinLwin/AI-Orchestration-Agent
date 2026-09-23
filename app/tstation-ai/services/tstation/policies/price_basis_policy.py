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
    return any(any(is_positive_number_like(context.get(field)) for field in PRICE_BASIS_FIELDS) for context in _price_contexts(slots))

def _price_contexts(slots: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    contexts: list[Mapping[str, Any]] = [slots]
    availability_context = slots.get("availability_context")
    if isinstance(availability_context, Mapping):
        for key in (
            "pending_order_context",
            "active_flow_context",
            "dormant_purchase_context",
            "dormant_stock_context",
            "dormant_transaction_context",
        ):
            value = availability_context.get(key)
            if isinstance(value, Mapping):
                contexts.append(value)
                payment = value.get("payment")
                if isinstance(payment, Mapping):
                    contexts.append(payment)
    return tuple(contexts)


def is_positive_number_like(value: Any) -> bool:
    if value in (None, "") or isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return value > 0
    text = str(value).strip().replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return False
    return any(char != "0" for char in text if char.isdigit())
