from services.tstation.policies.price_response_policy import (
    build_product_coupon_price_amount_event,
    build_product_coupon_price_no_product_event,
    build_price_intent_frame,
    decide_price_response,
    is_product_coupon_price_amount_query,
    plan_price_tools,
)
from services.tstation.policies.response_decision import ResponseShape, TemplateName


def test_tc005_family_coupon_product_pattern_does_not_require_size_first() -> None:
    frame = build_price_intent_frame("키너지 EX 패밀리 할인쿠폰 적용받고 싶어")
    plan = plan_price_tools(frame)
    decision = decide_price_response(frame)

    assert frame.intent == "product_coupon_eligibility"
    assert frame.entities["product_name"] == "Kinergy EX"
    assert frame.entities["coupon_keyword"] == "family"
    assert frame.entities["coupon_scope"] == "pattern"
    assert plan.preferred_tool == "get_my_coupons_tool"
    assert plan.metadata["do_not_require_size_first"] is True
    assert decision.metadata["response_shape_key"] == "product_coupon_eligibility"
    assert "require_size_first" in decision.forbidden_behaviors
    assert "mix_owned_and_downloadable_coupons" in decision.forbidden_behaviors


def test_employee_coupon_product_pattern_does_not_require_size_first() -> None:
    frame = build_price_intent_frame("다이나프로 HPX 임직원 쿠폰 적용돼?")
    plan = plan_price_tools(frame)
    decision = decide_price_response(frame)

    assert frame.intent == "product_coupon_eligibility"
    assert frame.entities["product_name"] == "Dynapro HPX"
    assert frame.entities["coupon_keyword"] == "employee"
    assert frame.entities["coupon_scope"] == "pattern"
    assert plan.preferred_tool == "get_my_coupons_tool"
    assert plan.metadata["do_not_require_size_first"] is True
    assert "require_size_first" in decision.forbidden_behaviors


def test_tc018_coupon_stacking_uses_condition_check_not_generic_faq() -> None:
    frame = build_price_intent_frame("진행 중인 멀티브랜드 기획전 할인가에 1만원 생일쿠폰 더 쓸 수 있어?")
    plan = plan_price_tools(frame)
    decision = decide_price_response(frame)

    assert frame.intent == "coupon_stacking_check"
    assert frame.entities["has_promotion_keyword"] is True
    assert frame.entities["coupon_keyword"] == "birthday"
    assert plan.allowed_tools == ("get_my_coupons_tool", "check_coupon_stacking_tool")
    assert plan.required_slots == ("coupon_identifiers",)
    assert decision.response_shape == ResponseShape.CLARIFY
    assert decision.required_slots == ("coupon_identifiers",)
    assert "generic_faq_answer" in decision.forbidden_behaviors
    assert "infer_stacking_without_tool" in decision.forbidden_behaviors


def test_tc097_product_coupon_query_separates_owned_and_downloadable() -> None:
    frame = build_price_intent_frame("kinergy EX 쓸 수 있는 쿠폰 뭐 있어?")
    plan = plan_price_tools(frame)
    decision = decide_price_response(frame)

    assert frame.intent == "product_coupon_eligibility"
    assert frame.entities["product_name"] == "Kinergy EX"
    assert plan.metadata["separate_owned_and_downloadable"] is True
    assert decision.template == TemplateName.QUICK_REPLY
    assert "mix_owned_and_downloadable_coupons" in decision.forbidden_behaviors
    assert "promise_coupon_application" in decision.forbidden_behaviors


def test_tc098_max_benefit_product_query_uses_product_coupon_policy() -> None:
    frame = build_price_intent_frame("ventus s2 as 2055516 사이즈 최대 혜택 받으려면?")
    plan = plan_price_tools(frame)
    decision = decide_price_response(frame)

    assert frame.intent == "product_coupon_eligibility"
    assert frame.entities["product_name"] == "Ventus S2 AS"
    assert plan.preferred_tool == "get_my_coupons_tool"
    assert decision.metadata["response_shape_key"] == "product_coupon_eligibility"
    assert "promise_coupon_application" in decision.forbidden_behaviors


def test_tc101_discount_rate_coupon_targets_start_from_owned_coupon_not_events() -> None:
    frame = build_price_intent_frame("30% 할인 쿠폰 적용 가능 상품 뭐뭐 있어?")
    plan = plan_price_tools(frame)
    decision = decide_price_response(frame)

    assert frame.intent == "coupon_applicable_products"
    assert frame.entities["discount_rate"] == 30
    assert plan.allowed_tools == ("get_my_coupons_tool", "get_coupon_applicable_products_tool")
    assert "get_events_tool" in plan.forbidden_tools
    assert decision.required_slots == ("coupon_identifier",)
    assert "treat_discount_rate_as_event" in decision.forbidden_behaviors


def test_tc127_final_payable_amount_with_known_goods_uses_coupon_policy() -> None:
    frame = build_price_intent_frame(
        "내가 그럼 내야되는 금액이 얼마야? 할인은 어떤 쿠폰이 적용?",
        known_slots={"goods_no": "1028562", "product_name": "Kinergy EX"},
    )
    plan = plan_price_tools(frame)
    decision = decide_price_response(frame)

    assert frame.intent == "product_coupon_discount_amount"
    assert frame.known_slots["goods_no"] == "1028562"
    assert plan.preferred_tool == "get_final_price_tool"
    assert plan.required_slots == ("goods_no",)
    assert decision.metadata["response_shape_key"] == "product_coupon_discount_amount"
    assert "answer_without_price_tool" in decision.forbidden_behaviors


def test_product_coupon_price_amount_event_multiplies_quantity_discount() -> None:
    event = build_product_coupon_price_amount_event(
        {
            "data": {
                "items": [
                    {
                        "sale_prc": "100000",
                        "cheapest_final_prc": "85000",
                        "cheapest_applied_coupons": [{"cpn_nm": "패밀리 쿠폰"}],
                    }
                ]
            }
        },
        product_name="Ventus S2 AS",
        tire_size="205/55R16",
        quantity=4,
    )

    assert event is not None
    assert event["source_domain"] == "transaction"
    assert event["assistant_response_source"] == "code_product_coupon_price_resolver"
    assert "60,000원" in event["data"]["assistantResponse"]
    assert "340,000원" in event["data"]["assistantResponse"]
    assert event["data"]["quickReplies"][0]["label"] == "장바구니 담기"

def test_product_coupon_price_no_product_event_keeps_pending_price_context() -> None:
    event = build_product_coupon_price_no_product_event("Ventus air S", "225/55R17", quantity=2)

    assert event["source_domain"] == "discovery"
    assert event["assistant_response_source"] == "code_product_coupon_price_no_product"
    assert event["data"]["metadata"] == {
        "pendingIntent": "price",
        "goalType": "coupon_discount_amount",
        "productName": "Ventus air S",
        "tireSize": "225/55R17",
        "ordQty": 2,
    }

def test_product_coupon_price_amount_query_detection_lives_in_price_policy() -> None:
    assert is_product_coupon_price_amount_query("벤투스 에어S 쿠폰 적용하면 얼마야?")
    assert not is_product_coupon_price_amount_query("벤투스 에어S에 적용 가능한 쿠폰 뭐 있어?")

def test_tc186_arbitrary_coupon_issue_is_denied_and_issue_tool_forbidden() -> None:
    frame = build_price_intent_frame("미안한데 진짜 돈이 없어 타이어 90% 할인쿠폰 1개만 발급해줘")
    plan = plan_price_tools(frame)
    decision = decide_price_response(frame)

    assert frame.intent == "coupon_issue_request"
    assert plan.preferred_tool is None
    assert "issue_coupon_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "coupon_issue_not_supported"
    assert decision.metadata["cta_policy"] == "coupon_box_only"
    assert "promise_coupon_issue" in decision.forbidden_behaviors
    assert "show_coupon_download_cta" in decision.forbidden_behaviors


def test_tc189_expired_coupon_restore_goes_to_non_restorable_qna() -> None:
    frame = build_price_intent_frame("작년에 끝난 블랙세일 쿠폰 못쓰고 만료됨 원복해줘")
    plan = plan_price_tools(frame)
    decision = decide_price_response(frame)

    assert frame.intent == "expired_coupon_or_event"
    assert "issue_coupon_tool" in plan.forbidden_tools
    assert decision.template == TemplateName.QNA_COMPLETE
    assert decision.metadata["response_shape_key"] == "expired_coupon_not_restorable_qna"
    assert "promise_coupon_restore" in decision.forbidden_behaviors
    assert "promise_ended_event_reuse" in decision.forbidden_behaviors


def test_tc210_fake_vip_black_card_benefit_is_not_acknowledged() -> None:
    frame = build_price_intent_frame("T블랙멤버십 VIP 카드 50% 할인링크 보내봐")
    plan = plan_price_tools(frame)
    decision = decide_price_response(frame)

    assert frame.intent == "nonexistent_benefit"
    assert plan.preferred_tool is None
    assert "issue_coupon_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "unverified_benefit_denied"
    assert "acknowledge_fake_vip_benefit" in decision.forbidden_behaviors
    assert "provide_fake_benefit_link" in decision.forbidden_behaviors
