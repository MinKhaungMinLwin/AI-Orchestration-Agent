"""Unit tests for chat._choose_quickreply_fallback() domain-aware routing.

Locks in:
  - LEADING domain → progress chips ([상품 검색, 타이어 추천, 처음으로])
  - Tool dispatch (order/coupon) overrides domain routing.
  - Unknown / non-LEADING domain → generic fallback ([1:1 문의하기, 처음으로])

Run from repo root:

    cd app/tstation-ai && uv run pytest tests/test_quickreply_fallback_routing.py -v
"""
from __future__ import annotations

import pytest

from services.tstation.chat import (
    _FALLBACK_COUPON,
    _FALLBACK_GENERIC,
    _FALLBACK_LEADING_PROGRESS,
    _FALLBACK_ORDER_LIST,
    _choose_quickreply_fallback,
)


def _labels(chips: list[dict]) -> list[str]:
    return [c["label"] for c in chips]


# --------------------------------------------------------------------------- #
#  LEADING domain → progress chips
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("source_domain", ["leading", "LEADING", "Leading"])
def test_leading_domain_returns_progress_chips(source_domain: str) -> None:
    chips, label = _choose_quickreply_fallback(set(), source_domain)
    assert _labels(chips) == ["상품 검색", "타이어 추천", "처음으로"]
    assert label == "leading_progress"


def test_leading_domain_first_chip_is_discovery() -> None:
    chips, _ = _choose_quickreply_fallback(set(), "leading")
    assert chips[0]["domain"] == "DISCOVERY"


# --------------------------------------------------------------------------- #
#  Tool dispatch beats domain routing
# --------------------------------------------------------------------------- #


def test_order_tool_overrides_leading_domain() -> None:
    chips, label = _choose_quickreply_fallback({"get_orders_of_user_tool"}, "leading")
    assert chips == _FALLBACK_ORDER_LIST
    assert label == "order"


def test_coupon_tool_overrides_leading_domain() -> None:
    chips, label = _choose_quickreply_fallback({"get_my_coupons_tool"}, "leading")
    assert chips == _FALLBACK_COUPON
    assert label == "coupon"


# --------------------------------------------------------------------------- #
#  Non-LEADING domains → generic
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "source_domain",
    [None, "", "transaction", "discovery", "support", "unknown"],
)
def test_non_leading_domain_returns_generic(source_domain: str | None) -> None:
    chips, label = _choose_quickreply_fallback(set(), source_domain)
    assert chips == _FALLBACK_GENERIC
    assert label == "generic"


def test_progress_constant_shape() -> None:
    assert len(_FALLBACK_LEADING_PROGRESS) == 3
    assert all("label" in c and "domain" in c for c in _FALLBACK_LEADING_PROGRESS)
