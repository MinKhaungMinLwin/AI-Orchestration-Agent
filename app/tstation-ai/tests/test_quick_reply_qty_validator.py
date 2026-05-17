"""Unit tests for QuickReplyTemplate qty-chip enforcement validator.

Locks in the deterministic fallback: when the assistant asks for tire qty,
quickReplies must contain ["1개", "2개", "3개", "4개"] in full. Validator
auto-fills any missing chips, but never fires on qty-confirm prompts (where
the chips are intentionally suppressed) or on unrelated quickReply turns.

Run from repo root with:

    cd app/tstation-ai && uv run pytest tests/test_quick_reply_qty_validator.py -v
"""
from __future__ import annotations

import pytest

from services.tstation.agents.templates.schemas import (
    QuickReplyChip,
    QuickReplyTemplate,
)


_QTY_CHIPS = ["1개", "2개", "3개", "4개"]


def _labels(tpl: QuickReplyTemplate) -> list[str]:
    return [c.label for c in tpl.quickReplies]


# --------------------------------------------------------------------------- #
#  Trigger cases — auto-fix expected
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "prompt",
    [
        "구매하실 타이어 수량을 알려주세요 😊",
        "장착하실 타이어 수량을 알려주세요.",
        "몇 개 주문하시겠습니까?",
        "몇개 확인해 드릴까요?",
        "수량을 선택해 주세요.",
    ],
)
def test_qty_question_with_missing_chips_is_autofilled(prompt: str) -> None:
    tpl = QuickReplyTemplate(
        assistantResponse=prompt,
        quickReplies=[
            QuickReplyChip(label="2개", domain="TRANSACTION"),
            QuickReplyChip(label="4개", domain="TRANSACTION"),
            QuickReplyChip(label="1:1 문의하기"),
            QuickReplyChip(label="처음으로"),
        ],
    )
    assert _labels(tpl) == _QTY_CHIPS
    assert all(c.domain == "TRANSACTION" for c in tpl.quickReplies)


def test_qty_question_with_empty_chips_is_autofilled() -> None:
    tpl = QuickReplyTemplate(
        assistantResponse="구매하실 타이어 수량을 알려주세요 😊",
        quickReplies=[],
    )
    assert _labels(tpl) == _QTY_CHIPS


def test_qty_question_with_only_first_two_chips_is_autofilled() -> None:
    tpl = QuickReplyTemplate(
        assistantResponse="몇 개를 확인하시겠습니까?",
        quickReplies=[
            QuickReplyChip(label="1개", domain="TRANSACTION"),
            QuickReplyChip(label="2개", domain="TRANSACTION"),
        ],
    )
    assert _labels(tpl) == _QTY_CHIPS


# --------------------------------------------------------------------------- #
#  Pass-through cases — no modification expected
# --------------------------------------------------------------------------- #


def test_qty_question_with_all_four_chips_is_preserved() -> None:
    chips = [QuickReplyChip(label=lbl, domain="TRANSACTION") for lbl in _QTY_CHIPS]
    tpl = QuickReplyTemplate(
        assistantResponse="구매하실 타이어 수량을 알려주세요 😊",
        quickReplies=chips,
    )
    assert _labels(tpl) == _QTY_CHIPS


def test_qty_confirm_pattern_is_skipped() -> None:
    """L1310 의 '수량은 [N]개 맞으시죠?' 확인 질문은 chip 없이 emit. validator 가 끼어들면 안 됨."""
    tpl = QuickReplyTemplate(
        assistantResponse="수량은 4개 맞으시죠? 변경이 필요하시면 말씀해 주세요.",
        quickReplies=[QuickReplyChip(label="다음")],
    )
    assert _labels(tpl) == ["다음"]


def test_qty_confirm_with_arbitrary_chips_is_skipped() -> None:
    tpl = QuickReplyTemplate(
        assistantResponse="수량은 2개 맞으시죠?",
        quickReplies=[QuickReplyChip(label="주문 진행"), QuickReplyChip(label="처음으로")],
    )
    assert _labels(tpl) == ["주문 진행", "처음으로"]


def test_unrelated_quickreply_is_preserved() -> None:
    tpl = QuickReplyTemplate(
        assistantResponse="원하시는 지역을 알려주세요.",
        quickReplies=[
            QuickReplyChip(label="한남"),
            QuickReplyChip(label="분당"),
            QuickReplyChip(label="해운대"),
            QuickReplyChip(label="다른 지역 찾기"),
        ],
    )
    assert _labels(tpl) == ["한남", "분당", "해운대", "다른 지역 찾기"]


def test_statement_mentioning_qty_does_not_trigger() -> None:
    """LLM 이 '수량 4개로 주문되었어요' 처럼 상태 보고만 하는 경우 validator 가 fire 안 됨."""
    tpl = QuickReplyTemplate(
        assistantResponse="수량 4개로 주문이 완료되었어요.",
        quickReplies=[QuickReplyChip(label="주문 내역 보기"), QuickReplyChip(label="처음으로")],
    )
    assert _labels(tpl) == ["주문 내역 보기", "처음으로"]


# --------------------------------------------------------------------------- #
#  Interaction with existing truncate field_validator
# --------------------------------------------------------------------------- #


def test_truncate_happens_before_qty_check_then_autofills() -> None:
    """field_validator(truncate) 가 5개를 4개로 자른 뒤에도 1개/3개 누락이면 model_validator 가 보정."""
    tpl = QuickReplyTemplate(
        assistantResponse="장착하실 타이어 수량을 알려주세요.",
        quickReplies=[
            QuickReplyChip(label="2개"),
            QuickReplyChip(label="4개"),
            QuickReplyChip(label="처음으로"),
            QuickReplyChip(label="1:1 문의하기"),
            QuickReplyChip(label="다시 추천"),  # _MAX_QUICK_REPLIES=4 로 잘림
        ],
    )
    assert _labels(tpl) == _QTY_CHIPS
