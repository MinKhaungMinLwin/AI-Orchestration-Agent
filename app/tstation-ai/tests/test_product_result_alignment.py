from __future__ import annotations

from services.tstation.policies.result_alignment import product_price_alignment_notice
from services.tstation.template_mapper import current_user_text, try_build_template


def test_product_price_alignment_notice_reports_lower_fallback_for_missing_requested_range() -> None:
    notice = product_price_alignment_notice(
        user_text="컴포트한 타이어로 2355519 사이즈 개당 30만원대 추천해주라. 돈이 별로 없네.",
        products=[
            {"title": "A", "price": 171000},
            {"title": "B", "price": 165000},
        ],
    )

    assert notice == "요청하신 30만원대 상품은 현재 결과에 없어서, 확인 가능한 더 낮은 가격대 상품을 보여드릴게요."


def test_product_price_alignment_notice_omits_notice_when_any_product_matches_range() -> None:
    notice = product_price_alignment_notice(
        user_text="2355519 사이즈 30만원대 추천해줘",
        products=[
            {"title": "A", "price": 171000},
            {"title": "B", "price": 318000},
        ],
    )

    assert notice == ""


def test_product_template_response_compares_requested_price_range_with_result_prices() -> None:
    token = current_user_text.set("컴포트한 타이어로 2355519 사이즈 개당 30만원대 추천해주라. 돈이 별로 없네.")
    try:
        event = try_build_template(
            [
                {
                    "tool": "get_products_recommendations_tool",
                    "args": {
                        "tire_size": "235/55R19",
                        "rcmd_type": "family",
                        "min_price": 300000,
                        "max_price": 399999,
                    },
                    "data": {
                        "status": "success",
                        "data": {
                            "items": [
                                {
                                    "goods_no": "G1",
                                    "goods_nm": "컴포트 타이어 A",
                                    "tire_size_1": "235/55R19",
                                    "extra_fvr_sale_prc": 171000,
                                },
                                {
                                    "goods_no": "G2",
                                    "goods_nm": "컴포트 타이어 B",
                                    "tire_size_1": "235/55R19",
                                    "extra_fvr_sale_prc": 165000,
                                },
                            ]
                        },
                    },
                }
            ],
            "235/55R19 승차감 조건으로 찾은 상품 2개입니다. 원하시는 상품을 선택해 주세요.",
        )
    finally:
        current_user_text.reset(token)

    assert event is not None
    assert event["template"] == "product"
    response = event["data"]["assistantResponse"]
    assert response.startswith("요청하신 30만원대 상품은 현재 결과에 없어서")
    assert "235/55R19 승차감 조건으로 찾은 상품 2개입니다" in response
