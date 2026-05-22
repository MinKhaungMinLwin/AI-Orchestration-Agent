"""Unit tests for chat._choose_quickreply_fallback() domain-aware routing.

Locks in:
  - LEADING domain → progress chips ([상품 검색, 타이어 추천])
  - Tool dispatch (order/coupon) overrides domain routing.
  - Unknown / non-LEADING domain → generic fallback ([1:1 문의하기])

Run from repo root:

    cd app/tstation-ai && uv run pytest tests/test_quickreply_fallback_routing.py -v
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.tstation.chat import (
    _FALLBACK_COUPON,
    _FALLBACK_GENERIC,
    _FALLBACK_LEADING_PROGRESS,
    _FALLBACK_ORDER_LIST,
    _choose_quickreply_fallback,
    _coerce_reservation_quickreply_to_datepick,
    _discovery_recovery_chips_for_text,
    _infer_followup_recommendation_context,
    _is_ev_suitability_turn,
    _looks_like_generic_dead_end_chips,
    _remove_home_quick_reply_chips,
    _should_replace_discovery_dead_end_chips,
)


def _labels(chips: list[dict]) -> list[str]:
    return [c["label"] for c in chips]


# --------------------------------------------------------------------------- #
#  EV suitability intent detection
# --------------------------------------------------------------------------- #


def test_ev_suitability_detects_explicit_ev_explanation_question() -> None:
    text = "내 차는 전기차인데 그냥 dynapro HPX 끼면 안돼? ion evo AS를 꼭 껴야하는 이유가 있어?"
    assert _is_ev_suitability_turn(text) is True


def test_vehicle_category_suitability_detects_non_ev_question() -> None:
    text = "내 차는 SUV인데 경차용 타이어 그냥 껴도 되나?"
    assert _is_ev_suitability_turn(text) is True


def test_ev_suitability_does_not_treat_evo_as_ev_context() -> None:
    text = "파주 시청 근처 더타이어샵 매장에 iON evo 재고 있을까? 오늘 당장 장착해야 하는데"
    assert _is_ev_suitability_turn(text, pending_intent="stock", goal_type="store_with_stock") is False


def test_ev_suitability_does_not_override_stock_turn_even_for_ev_owner() -> None:
    text = "전기차 타는데 iON evo 재고 있을까? 오늘 당장 장착해야 해"
    assert _is_ev_suitability_turn(text, pending_intent="stock", goal_type="store_with_stock") is False


def test_followup_size_input_preserves_ev_recommendation_context() -> None:
    messages = [
        {
            "role": "user",
            "content": "내 차는 전기차인데 그냥 dynapro HPX 끼면 안돼? ion evo AS를 꼭 껴야하는 이유가 있어?",
        },
        {
            "role": "assistant",
            "content": "전기차는 전기차용 타이어를 우선 확인하는 것이 좋아요. 정확한 차량이나 규격을 확인해 주세요.",
        },
        {"role": "user", "content": "규격으로 찾기"},
        {"role": "user", "content": "2355519"},
    ]

    context = _infer_followup_recommendation_context(messages, "2355519")

    assert context is not None
    assert "전기차용" in context
    assert "rcmd_type='ev'" in context


def test_followup_size_input_preserves_non_ev_vehicle_category_context() -> None:
    messages = [
        {"role": "user", "content": "내 차는 SUV인데 승용차용 타이어 껴도 돼?"},
        {"role": "assistant", "content": "SUV는 하중과 차종 조건이 중요해요. 차량이나 규격을 확인해 주세요."},
        {"role": "user", "content": "사이즈 직접 입력"},
        {"role": "user", "content": "2355519"},
    ]

    context = _infer_followup_recommendation_context(messages, "2355519")

    assert context is not None
    assert "SUV 차량용" in context
    assert "rcmd_type='tstation'" in context


def test_followup_size_input_ignores_plain_size_without_prior_scenario() -> None:
    messages = [
        {"role": "user", "content": "안녕하세요"},
        {"role": "assistant", "content": "무엇을 도와드릴까요?"},
        {"role": "user", "content": "2355519"},
    ]

    assert _infer_followup_recommendation_context(messages, "2355519") is None


# --------------------------------------------------------------------------- #
#  LEADING domain → progress chips
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("source_domain", ["leading", "LEADING", "Leading"])
def test_leading_domain_returns_progress_chips(source_domain: str) -> None:
    chips, label = _choose_quickreply_fallback(set(), source_domain)
    assert _labels(chips) == ["상품 검색", "타이어 추천"]
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
    assert len(_FALLBACK_LEADING_PROGRESS) == 2
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
    assert _labels(chips) == ["상품 검색", "타이어 추천"]


def test_remove_home_quick_reply_chips_strips_button_and_predicted_domain() -> None:
    event_data = {
        "assistantResponse": "무엇을 도와드릴까요?",
        "quickReplies": [
            {"label": "상품 검색", "domain": "DISCOVERY"},
            {"label": "처음으로", "domain": "LEADING"},
        ],
        "predictedDomains": ["DISCOVERY", "LEADING"],
    }

    assert _remove_home_quick_reply_chips(event_data)
    assert _labels(event_data["quickReplies"]) == ["상품 검색"]
    assert event_data["predictedDomains"] == ["DISCOVERY"]


def test_discovery_explicit_support_text_keeps_dead_end_chips() -> None:
    text = "정확한 확인은 1:1 문의로 문의해 주세요."
    assert not _should_replace_discovery_dead_end_chips(text, "discovery")


def test_discovery_policy_dead_end_keeps_dead_end_chips() -> None:
    text = "특정 제조 주차를 사전에 확정해 안내드리기는 어려워요."
    assert not _should_replace_discovery_dead_end_chips(text, "discovery")


def test_non_discovery_domain_keeps_dead_end_chips() -> None:
    text = "타이어 사이즈나 차량번호를 알려주세요."
    assert not _should_replace_discovery_dead_end_chips(text, "support")


# --------------------------------------------------------------------------- #
#  Reservation-time quickReply chips → datepick, narrowly
# --------------------------------------------------------------------------- #


def _preview_source() -> tuple[str, dict]:
    return (
        "transaction_store_preview_tool",
        {
            "status": "success",
            "data": {
                "schedule": {
                    "tier": "today_only",
                    "stores": [{
                        "shop_id": "T02396",
                        "shop_nm": "티스테이션 강릉강남점",
                        "slots": [
                            {"cal_day": "20260521", "tm": "09"},
                            {"cal_day": "20260521", "tm": "10"},
                            {"cal_day": "20260521", "tm": "12"},
                            {"cal_day": "20260521", "tm": "13"},
                        ],
                    }],
                },
            },
        },
    )


def test_reservation_time_quickreply_is_coerced_to_datepick() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "data": {
            "assistantResponse": "강릉에서 장착 예약 가능한 시간을 확인했어요.",
            "quickReplies": [
                {"label": "09시 예약", "domain": "TRANSACTION"},
                {"label": "13시 예약", "domain": "TRANSACTION"},
                {"label": "다른 시간 선택", "domain": "TRANSACTION"},
            ],
        },
    }

    result = _coerce_reservation_quickreply_to_datepick(
        event,
        [_preview_source()],
        SimpleNamespace(pending_intent="order", goal_type="place_order"),
    )

    assert result is not None
    assert result["template"] == "datepick"
    assert result["data"]["metadata"] == {
        "shopId": "T02396",
        "shopName": "티스테이션 강릉강남점",
    }
    assert result["data"]["dates"] == [{
        "date": "2026년 5월 21일 (목)",
        "available": True,
        "availableTimes": [9, 10, 13],
        "index": 0,
    }]


def test_reservation_time_quickreply_stock_context_is_not_coerced() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "강릉에서 재고가 확인된 매장입니다.",
            "quickReplies": [{"label": "09시 예약", "domain": "TRANSACTION"}],
        },
    }

    result = _coerce_reservation_quickreply_to_datepick(
        event,
        [_preview_source()],
        SimpleNamespace(pending_intent="stock", goal_type="store_with_stock"),
    )

    assert result is None


def test_non_time_quickreply_is_not_coerced() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "주문을 진행할까요?",
            "quickReplies": [{"label": "주문하기", "domain": "TRANSACTION"}],
        },
    }

    result = _coerce_reservation_quickreply_to_datepick(
        event,
        [_preview_source()],
        SimpleNamespace(pending_intent="order", goal_type="place_order"),
    )

    assert result is None
