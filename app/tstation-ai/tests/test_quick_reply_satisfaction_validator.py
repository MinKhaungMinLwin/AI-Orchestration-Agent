"""Unit tests for QuickReplyTemplate satisfaction-chip enforcement validator.

Locks in the deterministic fallback: when the assistant emits a satisfaction /
repurchase response AND the quickReplies contain any forbidden chip (구매하기,
다시 시도, 상담사 연결, 1:1 문의하기), the validator replaces the entire chip
set with the progress-oriented default `[상품 검색, 타이어 추천, 처음으로]`.

Does NOT fire when:
  - assistantResponse has no satisfaction pattern.
  - quickReplies contain no forbidden chip (prompt already emitted well).

Run from repo root with:

    cd app/tstation-ai && uv run pytest tests/test_quick_reply_satisfaction_validator.py -v
"""
from __future__ import annotations

import pytest

from services.tstation.agents.templates.schemas import (
    QuickReplyChip,
    QuickReplyTemplate,
)


_DEFAULT_LABELS = ["상품 검색", "타이어 추천", "처음으로"]
_DEFAULT_DOMAINS = ["DISCOVERY", "DISCOVERY", "LEADING"]


def _labels(tpl: QuickReplyTemplate) -> list[str]:
    return [c.label for c in tpl.quickReplies]


def _domains(tpl: QuickReplyTemplate) -> list[str | None]:
    return [c.domain for c in tpl.quickReplies]


# --------------------------------------------------------------------------- #
#  Trigger cases — auto-fix expected
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "prompt",
    [
        "고객님, 만족하셨다니 정말 기쁩니다! 😊",
        "원주점 이용에 만족하셨다니 정말 기쁘네요.",
        "구매에 만족하셨다니 감사합니다.",
        "다음에도 이용해 주시면 감사하겠습니다.",
        "또 이용해 주시면 더욱 노력하겠습니다.",
        "잘 받으셨다니 다행입니다.",
        "또 구매해 주셔서 감사합니다.",
        # 인사 / 환영 / 일반 도움 안내 (확장 패턴)
        "고객님, 안녕하세요! 😊 타이어 추천, 차량 호환성 확인까지 편하게 도와드릴게요. 무엇을 도와드릴까요?",
        "안녕하세요, 무엇을 도와드릴까요?",
        "고객님, 어떻게 도와드릴까요?",
        "고객님, 별말씀을요! 언제든지 도움이 필요하시면 편하게 말씀해 주세요 😊",
        "편하게 말씀해 주세요.",
        "반갑습니다. 무엇을 도와드릴까요?",
        # 답례 / 감사 표현 ("고마워" 응답 패턴)
        "고객님, 감사드립니다! 😊 더 필요하신 게 있으시면 언제든지 말씀해 주세요. 타이어 추천, 가격 조회, 매장 찾기 등 어떤 도움을 드릴까요?",
        "고객님, 별말씀을요! 더 궁금한 점이 있으면 말씀해 주세요.",
        "감사합니다. 다음에도 편하게 이용해 주세요.",
    ],
)
def test_satisfaction_with_forbidden_chips_is_replaced(prompt: str) -> None:
    tpl = QuickReplyTemplate(
        assistantResponse=prompt,
        quickReplies=[
            QuickReplyChip(label="다시 시도", domain="LEADING"),
            QuickReplyChip(label="상담사 연결", domain="SUPPORT"),
            QuickReplyChip(label="처음으로", domain="LEADING"),
        ],
    )
    assert _labels(tpl) == _DEFAULT_LABELS
    assert _domains(tpl) == _DEFAULT_DOMAINS


def test_satisfaction_with_구매하기_chip_is_replaced() -> None:
    tpl = QuickReplyTemplate(
        assistantResponse="만족하셨다니 정말 기쁩니다 😊",
        quickReplies=[
            QuickReplyChip(label="구매하기", domain="TRANSACTION"),
            QuickReplyChip(label="매장 찾기", domain="TRANSACTION"),
            QuickReplyChip(label="처음으로", domain="LEADING"),
        ],
    )
    assert _labels(tpl) == _DEFAULT_LABELS


def test_satisfaction_with_only_1to1_inquiry_chip_is_replaced() -> None:
    tpl = QuickReplyTemplate(
        assistantResponse="다음에도 이용하신다니 감사합니다.",
        quickReplies=[
            QuickReplyChip(label="1:1 문의하기", domain="SUPPORT"),
        ],
    )
    assert _labels(tpl) == _DEFAULT_LABELS


# --------------------------------------------------------------------------- #
#  No-fire cases — validator must NOT touch the chips
# --------------------------------------------------------------------------- #


def test_satisfaction_with_no_forbidden_chip_passes_through() -> None:
    original_labels = ["상품 검색", "타이어 추천", "처음으로"]
    tpl = QuickReplyTemplate(
        assistantResponse="만족하셨다니 정말 기쁩니다 😊",
        quickReplies=[
            QuickReplyChip(label=lbl, domain="DISCOVERY") for lbl in original_labels
        ],
    )
    assert _labels(tpl) == original_labels


def test_satisfaction_with_매장찾기_only_passes_through() -> None:
    tpl = QuickReplyTemplate(
        assistantResponse="다음에도 이용해 주시면 감사하겠습니다.",
        quickReplies=[
            QuickReplyChip(label="매장 찾기", domain="TRANSACTION"),
            QuickReplyChip(label="처음으로", domain="LEADING"),
        ],
    )
    assert _labels(tpl) == ["매장 찾기", "처음으로"]


def test_no_satisfaction_pattern_with_forbidden_chip_passes_through() -> None:
    tpl = QuickReplyTemplate(
        assistantResponse="주문이 정상적으로 처리되지 않았어요.",
        quickReplies=[
            QuickReplyChip(label="다시 시도", domain="LEADING"),
            QuickReplyChip(label="상담사 연결", domain="SUPPORT"),
        ],
    )
    assert _labels(tpl) == ["다시 시도", "상담사 연결"]


def test_no_satisfaction_pattern_with_empty_chips_passes_through() -> None:
    tpl = QuickReplyTemplate(
        assistantResponse="고객님 무엇을 도와드릴까요?",
        quickReplies=[],
    )
    assert _labels(tpl) == []


# --------------------------------------------------------------------------- #
#  Idempotency & qty-validator disjointness
# --------------------------------------------------------------------------- #


def test_idempotent_when_already_default() -> None:
    tpl1 = QuickReplyTemplate(
        assistantResponse="만족하셨다니 정말 기쁩니다 😊",
        quickReplies=[QuickReplyChip(label="다시 시도", domain="LEADING")],
    )
    assert _labels(tpl1) == _DEFAULT_LABELS

    tpl2 = QuickReplyTemplate(
        assistantResponse=tpl1.assistantResponse,
        quickReplies=tpl1.quickReplies,
    )
    assert _labels(tpl2) == _DEFAULT_LABELS


def test_qty_question_does_not_trigger_satisfaction_validator() -> None:
    tpl = QuickReplyTemplate(
        assistantResponse="몇 개 주문하시겠습니까?",
        quickReplies=[
            QuickReplyChip(label="2개", domain="TRANSACTION"),
            QuickReplyChip(label="4개", domain="TRANSACTION"),
        ],
    )
    assert _labels(tpl) == ["1개", "2개", "3개", "4개"]


def test_satisfaction_pattern_partial_match_in_unrelated_response() -> None:
    tpl = QuickReplyTemplate(
        assistantResponse="고객님께서 만족하실 만한 상품을 찾아드릴게요.",
        quickReplies=[
            QuickReplyChip(label="타이어 추천", domain="DISCOVERY"),
            QuickReplyChip(label="매장 찾기", domain="TRANSACTION"),
        ],
    )
    assert _labels(tpl) == ["타이어 추천", "매장 찾기"]


def test_greeting_without_forbidden_chip_passes_through() -> None:
    """인사 매칭 + chip 에 FORBIDDEN 없으면 통과 (prompt 가 잘 emit 한 경우)."""
    tpl = QuickReplyTemplate(
        assistantResponse="안녕하세요! 무엇을 도와드릴까요?",
        quickReplies=[
            QuickReplyChip(label="타이어 추천", domain="DISCOVERY"),
            QuickReplyChip(label="매장 찾기", domain="TRANSACTION"),
            QuickReplyChip(label="주문 조회", domain="TRANSACTION"),
        ],
    )
    assert _labels(tpl) == ["타이어 추천", "매장 찾기", "주문 조회"]


def test_plain_안녕하세요_without_도와드릴_does_not_trigger() -> None:
    """단순 '안녕하세요' 만 있고 '도와드릴' 표현 없으면 매칭 안 됨 (false-positive 방지)."""
    tpl = QuickReplyTemplate(
        assistantResponse="안녕하세요 고객님. 주문번호를 알려주세요.",
        quickReplies=[
            QuickReplyChip(label="1:1 문의하기", domain="SUPPORT"),
        ],
    )
    assert _labels(tpl) == ["1:1 문의하기"]
