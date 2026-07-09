from services.tstation.policies.internal_product_code_policy import sanitize_internal_product_codes


def test_sanitize_internal_product_codes_removes_only_obvious_goods_no_tokens() -> None:
    answer = "벤투스 S2 AS 상품코드는 G000000309780 입니다. goods_no는 G000000319584 값입니다."

    sanitized = sanitize_internal_product_codes(answer)

    assert "G000000309780" not in sanitized
    assert "G000000319584" not in sanitized
    assert "상품코드는" in sanitized
    assert "goods_no는" in sanitized


def test_sanitize_internal_product_codes_does_not_touch_short_or_non_goods_codes() -> None:
    answer = "규격은 245/45R18이고 매장 F00721, 상품명 Ventus S2 AS를 확인했어요."

    assert sanitize_internal_product_codes(answer) == answer
