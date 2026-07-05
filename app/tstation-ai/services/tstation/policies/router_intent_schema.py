"""Canonical router intent helpers.

The LLM router may describe a current-turn intent with a useful but non-canonical
label. Downstream execution should use only canonical labels while preserving the
raw label for trace/debugging.
"""

from __future__ import annotations

import re


UNCLEAR_INTENT = "unclear"
OUT_OF_SCOPE_INTENT = "out_of_scope"
UNSUPPORTED_INTENT = "unsupported"

_PRICE_OR_COUPON_ALIASES = {
    "applied_coupon_lookup",
    "applied_coupon_summary",
    "coupon_benefit_lookup",
    "coupon_or_discount_breakdown_inquiry",
    "discount_breakdown",
    "discount_breakdown_lookup",
    "discount_lookup",
    "discount_summary",
    "price_benefit_lookup",
    "price_or_benefit_lookup",
    "transaction_price_stock",
}

_GENERAL_ALIASES = {
    "continue_purchase": "quick_order_reservation",
    "quick_order_confirmed": "quick_order_execute",
    "resolve_product": "resolve_or_describe_product",
}


def canonical_router_intent(value: str | None) -> str:
    """Return the canonical executable intent for a router-supplied label."""

    normalized = normalize_router_intent_label(value)
    if not normalized:
        return ""
    if normalized in _PRICE_OR_COUPON_ALIASES:
        return "price_or_coupon_check"
    return _GENERAL_ALIASES.get(normalized, normalized)


def normalize_router_intent_label(value: str | None) -> str:
    """Normalize arbitrary router labels into comparable snake_case tokens."""

    return re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
