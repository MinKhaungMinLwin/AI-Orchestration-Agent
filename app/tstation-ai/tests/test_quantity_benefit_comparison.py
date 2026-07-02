from services.tstation.chat import (
    _build_quantity_benefit_comparison_event,
    _build_quantity_benefit_missing_event,
    _goods_no_from_template_event,
    _quantity_benefit_continuation_frame_from_pending,
    _quantity_price_summary,
)
from services.tstation.policies.discovery_intent_policy import build_discovery_intent_frame
from schemas.tstation.slots import ConversationSlots


def _price_result(quantity: int, final_unit: int, total_discount: int) -> dict:
    return {
        "status": "success",
        "data": {
            "items": [
                {
                    "goods_no": "G000000000001",
                    "goods_nm": "옵티모 H426",
                    "sale_prc": 100_000,
                    "final_prc": final_unit,
                    "total_discount": total_discount,
                    "applied_coupons": [{"cpn_nm": "테스트 쿠폰", "discount_amt": total_discount}],
                }
            ],
            "quantity": quantity,
        },
    }


def test_quantity_price_summary_computes_totals_from_unit_prices() -> None:
    summary = _quantity_price_summary(_price_result(4, 72_000, 28_000), 4)

    assert summary is not None
    assert summary["quantity"] == 4
    assert summary["sale_unit"] == 100_000
    assert summary["final_unit"] == 72_000
    assert summary["base_total"] == 400_000
    assert summary["final_total"] == 288_000
    assert summary["discount_total"] == 112_000


def test_quantity_benefit_event_answers_four_tires_more_discounted_by_unit_price() -> None:
    event = _build_quantity_benefit_comparison_event({
        2: _price_result(2, 80_000, 20_000),
        4: _price_result(4, 72_000, 28_000),
    })

    assert event is not None
    assert event["template"] == "quickReply"
    assert event["source_domain"] == "transaction"
    response = event["data"]["assistantResponse"]
    assert "2개와 4개 실제 혜택가" in response
    assert "| 2개 | 200,000원 | -40,000원 | 160,000원 | 80,000원 |" in response
    assert "| 4개 | 400,000원 | -112,000원 | 288,000원 | 72,000원 |" in response
    assert "4개 구매가 개당 기준으로 더 저렴합니다" in response
    assert event["data"]["metadata"]["quantityOptions"] == [2, 4]


def test_quantity_benefit_event_distinguishes_total_discount_from_unit_discount() -> None:
    event = _build_quantity_benefit_comparison_event({
        2: _price_result(2, 80_000, 20_000),
        4: _price_result(4, 80_000, 20_000),
    })

    assert event is not None
    response = event["data"]["assistantResponse"]
    assert "총 할인액은 더 크지만" in response
    assert "개당 혜택은 2개와 동일" in response


def test_goods_no_from_single_product_handoff_event() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "옵티모 H426 235/55R19 상품 확인했어요. 가격 확인을 이어갈게요.",
            "quickReplies": [],
            "predictedDomains": ["TRANSACTION"],
            "metadata": {"goodsId": "G000000309970"},
        },
        "nextAction": {"type": "continue", "domain": "transaction"},
    }

    assert _goods_no_from_template_event(event) == "G000000309970"


def test_quantity_benefit_missing_event_carries_pending_metadata() -> None:
    frame = build_discovery_intent_frame("옵티모 상품 2개살까 4개살까 고민 중인데 4개 사면 더 할인해줘?")

    event = _build_quantity_benefit_missing_event(frame)

    assert event["assistant_response_source"] == "code_quantity_benefit_missing_slots"
    assert event["data"]["metadata"] == {
        "pendingIntent": "quantity_benefit_comparison",
        "quantityOptions": [2, 4],
        "productName": "Optimo",
        "missingSlot": "tire_size",
    }


def test_quantity_benefit_pending_slots_continue_with_product_and_size() -> None:
    slots = ConversationSlots(
        pending_intent="quantity_benefit_comparison",
        pending_product_name="옵티모",
        pending_quantity_options=[2, 4],
        pending_required_slot="tire_size",
    )

    frame = _quantity_benefit_continuation_frame_from_pending("옵티모 2454519", slots=slots)

    assert frame is not None
    assert frame.sub_intent == "quantity_benefit_comparison"
    assert frame.entities["product_names"] == ("Optimo",)
    assert frame.entities["tire_size"] == "245/45R19"
    assert frame.entities["quantity_options"] == (2, 4)
    assert frame.missing_slots == ()


def test_quantity_benefit_pending_template_continues_after_history_summary() -> None:
    previous_event = _build_quantity_benefit_missing_event(
        build_discovery_intent_frame("옵티모 상품 2개살까 4개살까 고민 중인데 4개 사면 더 할인해줘?")
    )

    frame = _quantity_benefit_continuation_frame_from_pending(
        "2454519",
        slots=ConversationSlots(),
        latest_quickreply_tmpl=previous_event,
    )

    assert frame is not None
    assert frame.entities["product_names"] == ("Optimo",)
    assert frame.entities["tire_size"] == "245/45R19"
    assert frame.entities["quantity_options"] == (2, 4)


def test_plain_product_size_does_not_trigger_quantity_benefit_without_pending_state() -> None:
    frame = _quantity_benefit_continuation_frame_from_pending("옵티모 2454519", slots=ConversationSlots())

    assert frame is None
