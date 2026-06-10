from services.tstation.policies.discovery_intent_policy import (
    best_seller_period_from_text,
    build_discovery_intent_frame,
    is_default_tire_shopping_request,
    plan_discovery_tools,
)


def test_tc004_unsized_summer_performance_recommendation_keeps_conditions() -> None:
    frame = build_discovery_intent_frame("퍼포먼스 성능 좋은 여름용 타이어 3개만 추천해줘")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.entities["season"] == "summer"
    assert frame.entities["performance"] == "performance"
    assert frame.entities["tire_size"] is None
    assert plan.preferred_tool == "get_products_recommendations_tool"
    assert plan.tool_args_patch == {"rcmd_type": "performance", "season_nm": "여름"}


def test_welcome_popular_tire_question_uses_three_month_best_sellers() -> None:
    frame = build_discovery_intent_frame("지금 가장 인기 있는 타이어는?")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "best_seller_search"
    assert frame.entities["best_seller_period"] == "3months"
    assert plan.preferred_tool == "get_best_selling_products_tool"
    assert plan.tool_args_patch == {"period": "3months", "limit": 5}
    assert "get_products_recommendations_tool" in plan.forbidden_tools


def test_best_seller_period_mapping_preserves_explicit_periods() -> None:
    assert best_seller_period_from_text("오늘 인기 타이어는?") == "day"
    assert best_seller_period_from_text("이번 주 잘 팔리는 타이어") == "week"
    assert best_seller_period_from_text("이번 달 베스트셀러") == "month"
    assert best_seller_period_from_text("인기 타이어") == "3months"


def test_general_ev_recommendation_still_uses_recommendation_engine() -> None:
    frame = build_discovery_intent_frame("전기차용 타이어 추천해줘")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "general_recommendation"
    assert plan.preferred_tool == "get_products_recommendations_tool"


def test_default_tbot_shopping_cta_uses_basic_recommendation_flow() -> None:
    frame = build_discovery_intent_frame("T'Bot과 타이어 쇼핑하기")
    plan = plan_discovery_tools(frame)

    assert is_default_tire_shopping_request("T’Bot과 타이어 쇼핑하기") is True
    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "general_recommendation"
    assert frame.entities["default_tire_shopping"] is True
    assert plan.preferred_tool == "get_products_recommendations_tool"
    assert plan.tool_args_patch == {"rcmd_type": "tstation"}


def test_tc006_sized_all_weather_lowest_price_has_size_and_sort() -> None:
    frame = build_discovery_intent_frame("2454518 사이즈 올웨더 타이어 중 가장 저렴한거 알려줘")
    plan = plan_discovery_tools(frame)

    assert frame.entities["tire_size"] == "245/45R18"
    assert frame.entities["season"] == "all_weather"
    assert frame.entities["price_goal"] == "lowest"
    assert plan.tool_args_patch["tire_size"] == "245/45R18"
    assert plan.tool_args_patch["sort_by"] == "price_asc"


def test_tc016_winter_concept_then_recommendation_preserves_winter_condition() -> None:
    frame = build_discovery_intent_frame("윈터 타이어랑 사계절 타이어랑 어떤 의미야?")
    plan = plan_discovery_tools(build_discovery_intent_frame("특정 차량에 윈터타이어 추천해줘"))

    assert frame.intent == "product_description"
    assert frame.sub_intent == "season_concept_compare"
    assert frame.entities["season"] == "winter"
    assert plan.tool_args_patch == {"rcmd_type": "snow", "season_nm": "겨울"}


def test_tc017_product_noise_label_lookup_uses_product_search() -> None:
    frame = build_discovery_intent_frame("키너지 EX 소음등급은 어떤거고?")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_description"
    assert frame.sub_intent == "product_attribute_lookup"
    assert frame.entities["label_metric"] == "noise"
    assert frame.entities["attribute_metrics"] == ("noise",)
    assert frame.entities["product_names"] == ("Kinergy EX",)
    assert plan.preferred_tool == "search_product_tool"
    assert plan.tool_args_patch == {"keyword": "Kinergy EX"}
    assert "get_products_recommendations_tool" in plan.forbidden_tools


def test_short_alias_only_query_uses_product_search() -> None:
    frame = build_discovery_intent_frame("s fit as")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "product_name_search"
    assert frame.entities["product_names"] == ("S FIT AS", "S FIT")
    assert frame.entities["brand_cd"] == "LF"
    assert plan.preferred_tool == "search_product_tool"
    assert plan.tool_args_patch == {"keyword": "S FIT AS", "brand_cd": "LF"}


def test_product_name_with_size_search_passes_size_to_search_tool() -> None:
    frame = build_discovery_intent_frame("벤투스 S2 AS 225/45R17")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "product_name_search"
    assert frame.entities["product_names"] == ("Ventus S2 AS",)
    assert frame.entities["tire_size"] == "225/45R17"
    assert plan.preferred_tool == "search_product_tool"
    assert plan.tool_args_patch == {"keyword": "Ventus S2 AS", "size": "225/45R17", "brand_cd": "HK"}


def test_short_alias_infers_non_default_brand_code() -> None:
    frame = build_discovery_intent_frame("p7")
    plan = plan_discovery_tools(frame)

    assert frame.entities["product_names"] == ("P7",)
    assert frame.entities["brand_cd"] == "PI"
    assert plan.tool_args_patch == {"keyword": "P7", "brand_cd": "PI"}


def test_tc017_general_noise_label_question_is_not_recommendation() -> None:
    frame = build_discovery_intent_frame("소음 등급은 어떻게 돼?")

    assert frame.intent == "product_description"
    assert frame.sub_intent == "product_attribute_explanation"
    assert frame.entities["label_metric"] == "noise"


def test_product_attribute_lookup_supports_non_noise_fields() -> None:
    frame = build_discovery_intent_frame("키너지 EX 연비랑 원산지는 어떻게 돼?")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_description"
    assert frame.sub_intent == "product_attribute_lookup"
    assert frame.entities["attribute_metrics"] == ("fuel_efficiency", "origin")
    assert plan.preferred_tool == "search_product_tool"
    assert plan.tool_args_patch == {"keyword": "Kinergy EX"}


def test_tc021_product_mileage_compare_uses_metric_not_card_first() -> None:
    frame = build_discovery_intent_frame("ventus air S, dynapro HPX, optimo, 미쉐린 CC2 어떤거 가장 오래 탈 수 있어?")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_comparison"
    assert frame.sub_intent == "mileage_compare"
    assert frame.entities["compare_metric"] == "mileage"
    assert frame.entities["product_names"] == ("Ventus air S", "Dynapro HPX", "Optimo", "Michelin CC2")
    assert plan.preferred_tool == "search_product_tool"


def test_tc037_sound_absorber_with_size_maps_to_technology_filter() -> None:
    frame = build_discovery_intent_frame("흡음재 부착된 235/5519 타이어 알려줄래?")
    plan = plan_discovery_tools(frame)

    assert frame.entities["technology"] == "sound_absorber"
    assert frame.entities["rcmd_type"] == "sound_absorber"
    assert frame.entities["tire_size"] == "235/55R19"
    assert plan.tool_args_patch == {"rcmd_type": "sound_absorber", "tire_size": "235/55R19"}


def test_tc044_sound_absorber_explain_and_buy_keeps_sound_absorber_recommendation() -> None:
    frame = build_discovery_intent_frame("흡음재가 뭐야? 그거들어간 타이어 종류추천해줘 구매할래.")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "technology_explain_then_recommend"
    assert frame.entities["purchase_intent"] is True
    assert plan.tool_args_patch == {"rcmd_type": "sound_absorber"}


def test_safe_service_question_uses_safe_kids_recommendation_filter() -> None:
    frame = build_discovery_intent_frame("안심서비스 가능한 타이어는?")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "condition_recommendation"
    assert frame.entities["service_program"] == "safe_service"
    assert frame.entities["rcmd_type"] == "safe_kids"
    assert plan.tool_args_patch == {"rcmd_type": "safe_kids", "brand_cd": "HK"}


def test_tc047_similar_price_recommendation_does_not_inject_confirmed_size() -> None:
    frame = build_discovery_intent_frame(
        "비슷한 가격대의 타이어 더 추천해줘",
        known_slots={"tire_size": "205/55R16"},
    )
    plan = plan_discovery_tools(frame)

    assert frame.sub_intent == "similar_price_recommendation"
    assert frame.entities["price_goal"] == "similar_range"
    assert "tire_size" not in plan.tool_args_patch


def test_tc215_mileage_product_with_occupation_bias_is_product_description_guardrail() -> None:
    frame = build_discovery_intent_frame("마일리지 타이어 이거는 택시기사들이 쓰는거 아냐? 별로지?")

    assert frame.intent == "product_search"
    assert frame.entities["guardrail"] == "occupation_neutral"
    assert frame.entities["product_keyword"] == "마일리지"
    assert frame.entities["product_names"] == ("Mileage Plus",)


def test_mileage_product_recommendation_searches_product_name_not_attribute() -> None:
    frame = build_discovery_intent_frame("마일리지 타이어 추천")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "product_name_search"
    assert frame.entities["product_keyword"] == "마일리지"
    assert plan.preferred_tool == "search_product_tool"


def test_product_name_stock_store_request_searches_product_name_first() -> None:
    frame = build_discovery_intent_frame("dynapro HPX 오늘 장착 가능한 근처 매장 알려줘")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "product_name_search"
    assert frame.entities["product_names"] == ("Dynapro HPX",)
    assert frame.entities["tire_size"] is None
    assert plan.preferred_tool == "search_product_tool"
    assert plan.tool_args_patch == {"keyword": "Dynapro HPX"}
    assert "get_products_recommendations_tool" in plan.forbidden_tools


def test_brand_hint_is_preserved_for_vehicle_recommendation() -> None:
    frame = build_discovery_intent_frame("내 차 GV70인데 미쉐린 타이어 추천해줘")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.entities["brand_cd"] == "MC"
    assert plan.preferred_tool == "get_products_recommendations_tool"
    assert plan.tool_args_patch["brand_cd"] == "MC"


def test_multi_brand_recommendation_extracts_brand_codes_and_variants() -> None:
    frame = build_discovery_intent_frame("미쉐린, 콘티넨탈, 브리지스톤 상품 1개씩 BMW 3시리즈에 맞는 타이어 추천해줘")

    assert frame.intent == "product_recommendation"
    assert frame.entities["brand_cd"] == "MC"
    assert frame.entities["brand_codes"] == ("MC", "CT", "BS")
    assert frame.entities["variant_constraints"] == (
        {"brand_cd": "MC"},
        {"brand_cd": "CT"},
        {"brand_cd": "BS"},
    )


def test_multi_brand_recommendation_preserves_requested_per_brand_quantity_in_followup_parser() -> None:
    frame = build_discovery_intent_frame("한국타이어, 미쉐린을 각각 2개씩 추천해줘")

    assert frame.intent == "product_recommendation"
    assert frame.entities["brand_codes"] == ("HK", "MC")
    assert frame.entities["variant_constraints"] == (
        {"brand_cd": "HK"},
        {"brand_cd": "MC"},
    )


def test_multi_season_recommendation_extracts_variant_constraints() -> None:
    frame = build_discovery_intent_frame("여름용이랑 사계절 타이어 각각 1개씩 BMW 3시리즈에 맞는 거 추천해줘")

    assert frame.intent == "product_recommendation"
    assert frame.entities["variant_constraints"] == (
        {"season_nm": "여름", "label": "여름용"},
        {"rcmd_type": "all_weather", "label": "사계절"},
    )


def test_tc015_restock_question_keeps_restock_inquiry_intent() -> None:
    frame = build_discovery_intent_frame("미쉐린 CC2 235/5519 품절인데 재입고 언제 되나요?")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "restock_inquiry"
    assert frame.entities["product_names"] == ("Michelin CC2",)
    assert frame.entities["tire_size"] == "235/55R19"
    assert frame.entities["restock_inquiry"] is True
    assert plan.preferred_tool == "search_product_tool"


def test_tc026_latest_compare_uses_registration_metric() -> None:
    frame = build_discovery_intent_frame("dynapro HPX, dynapro HP3 중에 최신상품이 뭐야? 헷갈리넹")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_comparison"
    assert frame.sub_intent == "latest_compare"
    assert frame.entities["compare_metric"] == "release"
    assert frame.entities["product_names"] == ("Dynapro HPX", "Dynapro HP3")
    assert plan.preferred_tool == "search_product_tool"


def test_tc032_product_fuel_efficiency_compare_uses_attribute_compare() -> None:
    frame = build_discovery_intent_frame("키너지 EX랑 벤투스 air S 연비 기준으로 비교해줘")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_comparison"
    assert frame.sub_intent == "attribute_compare"
    assert frame.entities["compare_metric"] == "fuel_efficiency"
    assert frame.entities["attribute_metrics"] == ("fuel_efficiency",)
    assert plan.preferred_tool == "search_product_tool"


def test_mileage_attribute_recommendation_remains_attribute_recommendation() -> None:
    frame = build_discovery_intent_frame("마일리지 좋은 타이어")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "general_recommendation"
    assert "product_keyword" not in frame.entities
    assert plan.preferred_tool == "get_products_recommendations_tool"


def test_fuel_efficiency_recommendation_uses_recommendation_flow_not_explanation() -> None:
    frame = build_discovery_intent_frame("연비 좋은 타이어 추천해줘")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "condition_recommendation"
    assert frame.entities["recommendation_metric"] == "fuel_efficiency"
    assert plan.preferred_tool == "get_products_recommendations_tool"
    assert plan.tool_args_patch == {"rcmd_type": "fuel_efficiency"}


def test_tc216_kinergy_ex_and_ventus_air_s_are_recognized_for_grade_compare() -> None:
    frame = build_discovery_intent_frame("키너지 EX가 벤투스 air S 보다 프리미엄 등급 맞지?")

    assert frame.intent == "product_comparison"
    assert frame.sub_intent == "grade_compare"
    assert frame.entities["compare_metric"] == "grade"
    assert frame.entities["product_names"] == ("Ventus air S", "Kinergy EX")
