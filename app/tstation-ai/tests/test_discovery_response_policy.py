from services.tstation.policies.discovery_intent_policy import build_discovery_intent_frame
from services.tstation.policies.discovery_response_policy import decide_discovery_response
from services.tstation.policies.response_decision import ResponseShape, TemplateName


def test_tc004_no_size_recommendation_forbids_cards_and_prices() -> None:
    decision = decide_discovery_response(
        build_discovery_intent_frame("퍼포먼스 성능 좋은 여름용 타이어 3개만 추천해줘")
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "catalog_unsized_recommendation_summary"
    assert "product_card_without_size" in decision.forbidden_behaviors
    assert "price_without_size" in decision.forbidden_behaviors
    assert "drop_recommendation_scenario" in decision.forbidden_behaviors


def test_welcome_popular_tire_question_uses_product_cards_not_generic_summary() -> None:
    decision = decide_discovery_response(build_discovery_intent_frame("지금 가장 인기 있는 타이어는?"))

    assert decision.template == TemplateName.PRODUCT
    assert decision.response_shape == ResponseShape.CARD
    assert decision.metadata["response_shape_key"] == "best_seller_product_cards"
    assert "use_generic_recommendation_engine" in decision.forbidden_behaviors


def test_tc006_sized_lowest_price_allows_product_template_with_discount_guidance() -> None:
    decision = decide_discovery_response(
        build_discovery_intent_frame("2454518 사이즈 올웨더 타이어 중 가장 저렴한거 알려줘")
    )

    assert decision.template == TemplateName.PRODUCT
    assert decision.response_shape == ResponseShape.CARD
    assert decision.metadata["response_shape_key"] == "sized_lowest_price_recommendation"
    assert decision.required_slots == ("tire_size",)
    assert "omit_discount_rate" in decision.forbidden_behaviors


def test_external_price_comparison_decision_forbids_external_scraping_claims() -> None:
    decision = decide_discovery_response(
        build_discovery_intent_frame("벤투스 air S 2354518 네이버 쇼핑 최저가")
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "external_price_comparison_unavailable_internal_price"
    assert "claim_external_price_checked" in decision.forbidden_behaviors
    assert "product_description_answer" in decision.forbidden_behaviors


def test_tc016_winter_concept_decision_forbids_dropping_winter_constraint() -> None:
    decision = decide_discovery_response(build_discovery_intent_frame("윈터 타이어랑 사계절 타이어랑 어떤 의미야?"))

    assert decision.metadata["response_shape_key"] == "concept_explanation_then_optional_winter_recommendation"
    assert "drop_winter_constraint" in decision.forbidden_behaviors
    assert "recommend_non_winter_for_winter_request" in decision.forbidden_behaviors


def test_tc017_product_attribute_decision_forbids_generic_summary() -> None:
    decision = decide_discovery_response(build_discovery_intent_frame("키너지 EX 소음등급은 어떤거고?"))

    assert decision.metadata["response_shape_key"] == "product_attribute_summary"
    assert decision.template == TemplateName.QUICK_REPLY
    assert "generic_unsized_summary" in decision.forbidden_behaviors
    assert "omit_requested_product_attribute_when_available" in decision.forbidden_behaviors


def test_product_description_decision_forbids_unrequested_size_missing_notice() -> None:
    decision = decide_discovery_response(build_discovery_intent_frame("kinergy ex 설명해줘"))

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "neutral_product_description"
    assert "generic_unsized_summary" in decision.forbidden_behaviors
    assert "unrequested_size_missing_notice" in decision.forbidden_behaviors


def test_tc021_mileage_compare_prefers_metric_summary_over_cards() -> None:
    decision = decide_discovery_response(
        build_discovery_intent_frame("ventus air S, dynapro HPX, optimo, 미쉐린 CC2 어떤거 가장 오래 탈 수 있어?")
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "metric_comparison_summary"
    assert decision.metadata["compare_metric"] == "mileage"
    assert "product_card_first_response" in decision.forbidden_behaviors


def test_quantity_benefit_comparison_missing_size_asks_for_size_not_product_summary() -> None:
    decision = decide_discovery_response(
        build_discovery_intent_frame("옵티모 상품 2개살까 4개살까 고민 중인데 4개 사면 더 할인해줘?")
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.CLARIFY
    assert decision.required_slots == ("tire_size",)
    assert decision.metadata["response_shape_key"] == "quantity_benefit_comparison_missing_product_or_size"
    assert decision.metadata["quantity_options"] == (2, 4)
    assert "product_search_summary_as_final_answer" in decision.forbidden_behaviors
    assert "answer_without_price_tool" in decision.forbidden_behaviors


def test_sized_quantity_benefit_comparison_requires_price_tool_basis() -> None:
    decision = decide_discovery_response(build_discovery_intent_frame("옵티모 2155017 2개랑 4개 할인 비교해줘"))

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.required_slots == ()
    assert decision.metadata["response_shape_key"] == "quantity_benefit_comparison"
    assert decision.metadata["quantity_options"] == (2, 4)
    assert "answer_without_price_tool" in decision.forbidden_behaviors


def test_tc026_latest_compare_uses_metric_summary() -> None:
    decision = decide_discovery_response(
        build_discovery_intent_frame("dynapro HPX, dynapro HP3 중에 최신상품이 뭐야? 헷갈리넹")
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "metric_comparison_summary"
    assert decision.metadata["compare_metric"] == "release"
    assert "comparison_without_db_basis" in decision.forbidden_behaviors


def test_tc032_fuel_compare_uses_metric_summary() -> None:
    decision = decide_discovery_response(
        build_discovery_intent_frame("키너지 EX랑 벤투스 air S 연비 기준으로 비교해줘")
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "metric_comparison_summary"
    assert decision.metadata["compare_metric"] == "fuel_efficiency"


def test_tc037_sized_sound_absorber_uses_product_cards_but_keeps_filter() -> None:
    decision = decide_discovery_response(build_discovery_intent_frame("흡음재 부착된 235/5519 타이어 알려줄래?"))

    assert decision.template == TemplateName.PRODUCT
    assert decision.metadata["response_shape_key"] == "sized_technology_recommendation_cards"
    assert decision.required_slots == ("tire_size",)
    assert "drop_sound_absorber_filter" in decision.forbidden_behaviors


def test_tc044_unsized_sound_absorber_explains_then_summarizes_without_cards() -> None:
    decision = decide_discovery_response(
        build_discovery_intent_frame("흡음재가 뭐야? 그거들어간 타이어 종류추천해줘 구매할래.")
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "technology_explanation_then_unsized_recommendation_summary"
    assert "drop_sound_absorber_filter" in decision.forbidden_behaviors
    assert "product_card_without_size" in decision.forbidden_behaviors


def test_safe_service_unsized_question_explains_service_before_products() -> None:
    decision = decide_discovery_response(build_discovery_intent_frame("안심서비스 가능한 타이어는?"))

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "safe_service_explanation_then_unsized_recommendation_summary"
    assert "generic_unsized_summary" in decision.forbidden_behaviors
    assert "claim_safe_service_without_hankook_basis" in decision.forbidden_behaviors


def test_tc047_similar_price_does_not_require_size_unconditionally() -> None:
    decision = decide_discovery_response(
        build_discovery_intent_frame(
            "비슷한 가격대의 타이어 더 추천해줘",
            known_slots={"tire_size": "205/55R16"},
        )
    )

    assert decision.metadata["response_shape_key"] == "similar_price_range_recommendation"
    assert decision.required_slots == ()
    assert "require_size_unconditionally" in decision.forbidden_behaviors
    assert "inject_stale_confirmed_tire_size" in decision.forbidden_behaviors
    assert "drop_latest_size_specific_context" in decision.forbidden_behaviors


def test_tc215_mileage_tire_bias_response_is_neutral_description() -> None:
    decision = decide_discovery_response(
        build_discovery_intent_frame("마일리지 타이어 이거는 택시기사들이 쓰는거 아냐? 별로지?")
    )

    assert decision.metadata["response_shape_key"] == "neutral_product_description"
    assert "occupation_stereotype" in decision.forbidden_behaviors


def test_mileage_plus_product_bias_response_is_neutral_search_summary() -> None:
    decision = decide_discovery_response(
        build_discovery_intent_frame("마일리지 플러스 이거는 택시기사들이 쓰는거 아냐? 별로지?")
    )

    assert decision.metadata["response_shape_key"] == "product_search_summary"
    assert "occupation_stereotype" in decision.forbidden_behaviors


def test_tc015_restock_inquiry_uses_summary_not_product_cards() -> None:
    decision = decide_discovery_response(
        build_discovery_intent_frame("미쉐린 CC2 235/5519 품절인데 재입고 언제 되나요?")
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "restock_inquiry_summary"
    assert "product_card_first_response" in decision.forbidden_behaviors
    assert "promise_restock_date_without_source" in decision.forbidden_behaviors


def test_mileage_tire_recommendation_uses_catalog_summary() -> None:
    decision = decide_discovery_response(build_discovery_intent_frame("마일리지 타이어 추천"))

    assert decision.metadata["response_shape_key"] == "catalog_unsized_recommendation_summary"
    assert decision.template == TemplateName.QUICK_REPLY
    assert "drop_recommendation_scenario" in decision.forbidden_behaviors


def test_mileage_plus_product_search_summary_does_not_promise_cards() -> None:
    decision = decide_discovery_response(build_discovery_intent_frame("마일리지 플러스 추천"))

    assert decision.metadata["response_shape_key"] == "product_search_summary"
    assert decision.template == TemplateName.QUICK_REPLY
    assert "treat_product_name_as_attribute_recommendation" in decision.forbidden_behaviors


def test_tc216_grade_compare_forbids_ventus_air_s_misrecognition() -> None:
    decision = decide_discovery_response(build_discovery_intent_frame("키너지 EX가 벤투스 air S 보다 프리미엄 등급 맞지?"))

    assert decision.metadata["response_shape_key"] == "grade_comparison_summary"
    assert "misrecognize_ventus_air_s" in decision.forbidden_behaviors
    assert "claim_kinergy_ex_is_premium_above_ventus" in decision.forbidden_behaviors
