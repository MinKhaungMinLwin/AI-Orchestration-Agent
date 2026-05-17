"""Unit tests for chat._is_service_reservation_redirect + payload builder.

Locks in:
  - All three trigger conditions must hold (datepick pattern AND
    pending_intent='reservation' AND no tire-product context).
  - Tire-product keywords (goods_no / size / model name) anywhere in
    recent history block the intercept so the tire preOrder flow is
    untouched.
  - Payload always includes the deterministic redirect text and the two
    fallback chips ("다른 시간 선택" / "다른 매장 찾기"); the URL chip is
    added only when a shop_seq is discoverable in history.

Run from repo root:

    cd app/tstation-ai && uv run pytest tests/test_service_reservation_redirect.py -v
"""
from __future__ import annotations

import pytest

from services.tstation.chat import (
    _build_service_reservation_redirect_payload,
    _is_service_reservation_redirect,
)


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


# --------------------------------------------------------------------------- #
#  Detection: trigger conditions
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "user_text",
    [
        "2026년 5월 18일 (월)\n17:00",
        "2026년 12월 3일 (수)\n09:30",
        "2026년 1월 2일 (목)\n14:00",
        "  2026년 5월 18일 (월)\n17:00  ",  # surrounding whitespace
    ],
)
def test_datepick_pattern_with_reservation_intent_triggers(user_text: str) -> None:
    messages = [
        _msg("user", "와이퍼 교체 예약하고싶어"),
        _msg("assistant", "강남에서 와이퍼 교체 가능한 매장을 찾았어요."),
        _msg("user", "분당"),
        _msg("assistant", "티스테이션 판교점 예약 가능한 날짜를 확인했어요."),
        _msg("user", user_text),
    ]
    assert _is_service_reservation_redirect(user_text, "reservation", messages) is True


def test_non_datepick_user_text_does_not_trigger() -> None:
    messages = [_msg("user", "강남")]
    assert _is_service_reservation_redirect("강남", "reservation", messages) is False


def test_missing_pending_intent_does_not_trigger() -> None:
    messages = [_msg("user", "2026년 5월 18일 (월)\n17:00")]
    assert _is_service_reservation_redirect("2026년 5월 18일 (월)\n17:00", None, messages) is False
    assert _is_service_reservation_redirect("2026년 5월 18일 (월)\n17:00", "order", messages) is False


@pytest.mark.parametrize(
    "tire_marker",
    [
        "벤투스 S2 AS 245/45R18",
        "키너지 EX",
        "goods_no=G123456789012",
        "G123456789012",
        "255/45R20",
        "Ventus S1",
    ],
)
def test_tire_context_blocks_intercept(tire_marker: str) -> None:
    messages = [
        _msg("user", f"{tire_marker} 4개 장착 예약"),
        _msg("assistant", "예약 가능한 날짜를 확인했어요."),
        _msg("user", "2026년 5월 18일 (월)\n17:00"),
    ]
    assert (
        _is_service_reservation_redirect(
            "2026년 5월 18일 (월)\n17:00", "reservation", messages
        )
        is False
    )


def test_empty_inputs_safe() -> None:
    assert _is_service_reservation_redirect(None, "reservation", []) is False
    assert _is_service_reservation_redirect("", "reservation", []) is False


# --------------------------------------------------------------------------- #
#  Payload builder
# --------------------------------------------------------------------------- #


def test_payload_contains_store_name_date_time_and_fallback_chips() -> None:
    messages = [
        _msg("user", "와이퍼 교체 예약"),
        _msg("assistant", "티스테이션 판교점 예약 가능한 날짜를 확인했어요."),
        _msg("user", "2026년 5월 18일 (월)\n17:00"),
    ]
    payload = _build_service_reservation_redirect_payload(
        "2026년 5월 18일 (월)\n17:00", messages
    )

    assert "티스테이션 판교점" in payload["text"]
    assert "2026-05-18 17:00" in payload["text"]
    assert "매장 상세 페이지" in payload["text"]

    labels = [c["label"] for c in payload["chips"]]
    # "다른 시간 선택" and "다른 매장 찾기" always present
    assert "다른 시간 선택" in labels
    assert "다른 매장 찾기" in labels


def test_payload_includes_url_chip_when_shop_seq_present() -> None:
    messages = [
        _msg("assistant", '... "shopSeq": "F203675962" ... 티스테이션 판교점 ...'),
        _msg("user", "2026년 5월 18일 (월)\n17:00"),
    ]
    payload = _build_service_reservation_redirect_payload(
        "2026년 5월 18일 (월)\n17:00", messages
    )

    assert payload["shop_seq"] == "F203675962"
    url_chips = [c for c in payload["chips"] if c.get("url")]
    assert len(url_chips) == 1
    assert "F203675962" in url_chips[0]["url"]
    assert url_chips[0]["label"] == "매장 상세 페이지로 이동"


def test_payload_omits_url_chip_when_shop_seq_missing() -> None:
    messages = [
        _msg("assistant", "티스테이션 판교점 일정을 확인했어요."),  # no shopSeq quoted
        _msg("user", "2026년 5월 18일 (월)\n17:00"),
    ]
    payload = _build_service_reservation_redirect_payload(
        "2026년 5월 18일 (월)\n17:00", messages
    )

    assert payload["shop_seq"] is None
    url_chips = [c for c in payload["chips"] if c.get("url")]
    assert url_chips == []
    # Fallback chips still emitted
    assert len(payload["chips"]) == 2


def test_payload_falls_back_to_generic_store_name() -> None:
    messages = [_msg("user", "2026년 5월 18일 (월)\n17:00")]
    payload = _build_service_reservation_redirect_payload(
        "2026년 5월 18일 (월)\n17:00", messages
    )
    assert payload["store_name"] == "선택하신 매장"
    assert "선택하신 매장" in payload["text"]


def test_payload_date_padding() -> None:
    """Single-digit month/day/hour are zero-padded in the display string."""
    payload = _build_service_reservation_redirect_payload(
        "2026년 1월 2일 (목)\n9:05", [_msg("user", "x")]
    )
    assert "2026-01-02 09:05" in payload["text"]
