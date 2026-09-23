from __future__ import annotations

import json

from services.tstation.chat_v3.price_notice import PRICE_NOTICE, apply_price_notice


def _tool_call(payload: dict) -> dict:
    return {
        "name": "search_product_tool",
        "output": json.dumps({"status": "success", "data": payload}, ensure_ascii=False),
    }


def test_price_notice_is_appended_for_general_benefit_price() -> None:
    answer = apply_price_notice(
        "벤투스 S2 AS 혜택가는 120,800원입니다.",
        [_tool_call({"items": [{"extra_fvr_sale_prc": 120_800}]})],
    )

    assert answer == f"벤투스 S2 AS 혜택가는 120,800원입니다.\n{PRICE_NOTICE}"


def test_price_notice_is_appended_for_sale_price_fallback() -> None:
    answer = apply_price_notice(
        "기본가는 155,100원입니다.",
        [_tool_call({"sale_prc": "155100"})],
    )

    assert answer.endswith(PRICE_NOTICE)


def test_price_notice_is_not_appended_without_displayed_product_price() -> None:
    answer = apply_price_notice(
        "장착 공임은 매장에서 확인해 주세요.",
        [_tool_call({"wage_prc": 30_000})],
    )

    assert answer == "장착 공임은 매장에서 확인해 주세요."


def test_price_notice_is_not_duplicated() -> None:
    original = f"혜택가는 120,800원입니다.\n{PRICE_NOTICE}"

    assert apply_price_notice(original, [_tool_call({"price": 120_800})]) == original


def test_price_notice_can_be_the_only_answer_for_a_price_template() -> None:
    assert apply_price_notice("", [_tool_call({"paymentAmount": 241_600})]) == PRICE_NOTICE
