from services.tstation.policies.response_decision import ResponseDecision, ResponseShape, TemplateName
from services.tstation.template_mapper import (
    current_price_summary_context,
    current_transaction_response_decision,
    try_build_template,
)


def test_price_or_coupon_summary_uses_context_quantity_and_coupon_names() -> None:
    price_token = current_price_summary_context.set(
        {
            "product_name": "벤투스 S2 AS",
            "tire_size": "245/45R19",
            "ord_qty": 2,
        }
    )
    decision_token = current_transaction_response_decision.set(
        ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            metadata={"response_shape_key": "price_coupon_summary"},
        )
    )
    try:
        event = try_build_template(
            [
                {
                    "tool": "get_final_price_tool",
                    "args": {"goods_no": "G000000310126"},
                    "data": {
                        "status": "success",
                        "data": {
                            "goods_no": "G000000310126",
                            "sale_prc": 231700,
                            "cheapest_final_prc": 180500,
                            "cheapest_total_discount": 51200,
                            "cheapest_applied_coupons": [{"cpn_nm": "패밀리쿠폰 30%"}],
                        },
                    },
                }
            ],
            "할인 내역을 확인했어요.",
        )
    finally:
        current_transaction_response_decision.reset(decision_token)
        current_price_summary_context.reset(price_token)

    assert event is not None
    assert event["template"] == "quickReply"
    response = event["data"]["assistantResponse"]
    assert "벤투스 S2 AS 245/45R19 2개 기준" in response
    assert "정가 합계: 463,400원" in response
    assert "쿠폰/혜택 할인액: 102,400원" in response
    assert "최종 혜택가: 361,000원" in response
    assert "패밀리쿠폰 30%" in response
