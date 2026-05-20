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
    _discovery_recovery_chips_for_text,
    _looks_like_generic_dead_end_chips,
    _should_replace_discovery_dead_end_chips,
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


# --------------------------------------------------------------------------- #
#  Discovery normal guidance must not dead-end into support chips
# --------------------------------------------------------------------------- #


def test_detects_generic_dead_end_chip_pair() -> None:
    assert _looks_like_generic_dead_end_chips([
        {"label": "1:1 문의하기", "domain": "SUPPORT"},
        {"label": "처음으로", "domain": "LEADING"},
    ])


def test_discovery_vehicle_size_guidance_replaces_dead_end_chips() -> None:
    text = (
        "등록 차량에는 트럭이 확인되지 않아, 정확한 안내를 원하시면 "
        "트럭의 타이어 사이즈나 차량번호+소유주명을 알려주세요."
    )
    assert _should_replace_discovery_dead_end_chips(text, "discovery")
    recovery = _discovery_recovery_chips_for_text(text, "discovery")
    assert recovery is not None
    chips, label = recovery
    assert label == "discovery_size_vehicle"
    assert _labels(chips) == ["사이즈 직접 입력", "차량번호로 찾기", "타이어 추천 받기"]


def test_discovery_no_result_guidance_uses_search_recovery_chips() -> None:
    recovery = _discovery_recovery_chips_for_text(
        "해당 조건에 맞는 타이어를 찾을 수 없어요.",
        "discovery",
    )
    assert recovery is not None
    chips, label = recovery
    assert label == "discovery_no_result"
    assert _labels(chips) == ["다시 검색", "다른 조건으로 찾기", "타이어 추천 받기"]


def test_discovery_fitment_answer_uses_size_vehicle_chips() -> None:
    recovery = _discovery_recovery_chips_for_text(
        "SUV용과 승용차용 타이어는 하중과 설계 특성이 달라요.",
        "discovery",
    )
    assert recovery is not None
    chips, label = recovery
    assert label == "discovery_size_vehicle"
    assert _labels(chips) == ["사이즈 직접 입력", "차량번호로 찾기", "타이어 추천 받기"]


def test_discovery_generic_answer_uses_discovery_default_chips() -> None:
    recovery = _discovery_recovery_chips_for_text(
        "조건을 조금 더 알려주시면 이어서 찾아드릴게요.",
        "discovery",
    )
    assert recovery is not None
    chips, label = recovery
    assert label == "discovery_default"
    assert _labels(chips) == ["상품 검색", "타이어 추천", "처음으로"]


def test_discovery_explicit_support_text_keeps_dead_end_chips() -> None:
    text = "정확한 확인은 1:1 문의로 문의해 주세요."
    assert not _should_replace_discovery_dead_end_chips(text, "discovery")


def test_discovery_policy_dead_end_keeps_dead_end_chips() -> None:
    text = "특정 제조 주차를 사전에 확정해 안내드리기는 어려워요."
    assert not _should_replace_discovery_dead_end_chips(text, "discovery")


def test_non_discovery_domain_keeps_dead_end_chips() -> None:
    text = "타이어 사이즈나 차량번호를 알려주세요."
    assert not _should_replace_discovery_dead_end_chips(text, "support")
