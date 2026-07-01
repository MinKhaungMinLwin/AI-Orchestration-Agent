from services.tstation.policies.discovery_intent_policy import (
    best_seller_search_params_from_text,
    best_seller_period_from_text,
    build_discovery_intent_frame,
    extract_best_seller_vehicle_query,
    extract_quantity_options,
    has_registered_vehicle_ownership_signal,
    is_best_seller_request,
    is_default_benefit_request,
    is_default_tire_shopping_request,
    is_deal_list_request,
    is_external_price_comparison_request,
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


def test_plain_good_performance_wording_does_not_mean_sports_performance() -> None:
    frame = build_discovery_intent_frame("성능 좋은 타이어 추천해줘")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "general_recommendation"
    assert "performance" not in frame.entities
    assert plan.preferred_tool == "get_products_recommendations_tool"
    assert plan.tool_args_patch == {"rcmd_type": "tstation"}


def test_braking_or_cornering_wording_maps_to_performance() -> None:
    for text in ("코너링 좋은 타이어 추천해줘", "제동능력 좋은 타이어 추천해줘"):
        frame = build_discovery_intent_frame(text)
        plan = plan_discovery_tools(frame)

        assert frame.entities["recommendation_scenario"] == "handling"
        assert plan.tool_args_patch == {"rcmd_type": "performance"}


def test_welcome_popular_tire_question_uses_three_month_best_sellers() -> None:
    frame = build_discovery_intent_frame("지금 가장 인기 있는 타이어는?")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "best_seller_search"
    assert frame.entities["best_seller_period"] == "3months"
    assert plan.preferred_tool == "get_best_selling_products_tool"
    assert plan.tool_args_patch == {"limit": 5}
    assert "get_products_recommendations_tool" in plan.forbidden_tools


def test_demographic_preference_uses_three_month_best_sellers_not_segmented_recommendation() -> None:
    frame = build_discovery_intent_frame("20대가 선호하는 타이어는?")
    plan = plan_discovery_tools(frame)

    assert best_seller_period_from_text("20대가 선호하는 타이어는?") == "3months"
    assert frame.intent == "product_search"
    assert frame.sub_intent == "best_seller_search"
    assert frame.entities["best_seller_period"] == "3months"
    assert plan.preferred_tool == "get_best_selling_products_tool"
    assert plan.tool_args_patch == {"limit": 5}
    assert "get_products_recommendations_tool" in plan.forbidden_tools


def test_gender_purchase_wording_uses_best_sellers() -> None:
    frame = build_discovery_intent_frame("여성이 많이 사는 타이어 추천해줘")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "best_seller_search"
    assert frame.entities["best_seller_period"] == "3months"
    assert plan.preferred_tool == "get_best_selling_products_tool"


def test_best_seller_period_mapping_preserves_explicit_periods() -> None:
    assert best_seller_period_from_text("오늘 인기 타이어는?") == "day"
    assert best_seller_period_from_text("이번 주 잘 팔리는 타이어") == "week"
    assert best_seller_period_from_text("이번 달 베스트셀러") == "month"
    assert best_seller_period_from_text("인기 타이어") == "3months"
    assert best_seller_search_params_from_text("3개월 베스트셀러") == {"months": 3}
    assert best_seller_search_params_from_text("6개월 베스트셀러") == {"months": 6}


def test_unspecified_current_popularity_wording_uses_best_sellers() -> None:
    for text in (
        "요즘 젤 잘 팔리는거 알려줘",
        "요즘 제일 인기 있는 거",
        "요즘 잘 팔리는 타이어",
    ):
        frame = build_discovery_intent_frame(text)
        plan = plan_discovery_tools(frame)

        assert is_best_seller_request(text)
        assert frame.intent == "product_search"
        assert frame.sub_intent == "best_seller_search"
        assert frame.entities["best_seller_period"] == "3months"
        assert plan.allowed_tools == ("get_best_selling_products_tool",)
        assert plan.tool_args_patch == {"limit": 5}


def test_non_sales_popularity_or_review_wording_does_not_use_best_sellers() -> None:
    assert not is_best_seller_request("내가 쓴 베스트리뷰 어디서 봐")
    assert not is_best_seller_request("요즘 되는 일이 없어")

    frame = build_discovery_intent_frame("요즘 좋은 타이어 추천해줘")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "general_recommendation"
    assert plan.preferred_tool == "get_products_recommendations_tool"


def test_aggregate_purchase_wording_uses_best_seller_not_purchase_flow() -> None:
    for text in (
        "이번달 사람들이 젤 많이 구매한 타이어가 뭘까",
        "이번 달 제일 많이 산 타이어",
        "이번달 베스트셀러",
    ):
        frame = build_discovery_intent_frame(text)
        plan = plan_discovery_tools(frame)

        assert frame.intent == "product_search"
        assert frame.sub_intent == "best_seller_search"
        assert frame.entities["best_seller_period"] == "month"
        assert plan.allowed_tools == ("get_best_selling_products_tool",)
        assert plan.preferred_tool == "get_best_selling_products_tool"
        assert plan.tool_args_patch["limit"] == 5
        assert "from_date" in plan.tool_args_patch
        assert "to_date" in plan.tool_args_patch
        assert "get_products_recommendations_tool" in plan.forbidden_tools


def test_vehicle_best_seller_query_populates_vehicle_query() -> None:
    frame = build_discovery_intent_frame("그랜저 최근 3개월 베스트셀러 보여줘")
    plan = plan_discovery_tools(frame)

    assert extract_best_seller_vehicle_query("그랜저 최근 3개월 베스트셀러 보여줘") == "그랜저"
    assert frame.entities["vehicle_query"] == "그랜저"
    assert plan.tool_args_patch == {"limit": 5, "months": 3, "vehicle_query": "그랜저"}


def test_general_ev_recommendation_still_uses_recommendation_engine() -> None:
    frame = build_discovery_intent_frame("전기차용 타이어 추천해줘")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "condition_recommendation"
    assert plan.preferred_tool == "get_products_recommendations_tool"
    assert plan.tool_args_patch == {"vehicle_type": "ev"}


def test_registered_vehicle_size_lookup_variants_use_vehicle_information_contract() -> None:
    cases = (
        ("내가 등록한 차 중에 제타 사이즈가 뭐야", "제타"),
        ("내 등록 차 중 제타 규격 알려줘", "제타"),
        ("내가 등록해둔 차량 타이어 사이즈 보여줘", None),
    )
    for text, expected_vehicle_anchor in cases:
        frame = build_discovery_intent_frame(text)
        plan = plan_discovery_tools(frame)

        assert has_registered_vehicle_ownership_signal(text)
        assert frame.intent == "product_description"
        assert frame.sub_intent == "vehicle_information"
        assert frame.entities["vehicle_information_request"] == "tire_size_lookup"
        if expected_vehicle_anchor:
            assert frame.entities["named_registered_vehicle_anchor"] == expected_vehicle_anchor
        else:
            assert "named_registered_vehicle_anchor" not in frame.entities
        assert plan.allowed_tools == ("get_my_cars_tool",)
        assert plan.preferred_tool == "get_my_cars_tool"


def test_ev_low_noise_recommendation_keeps_ev_axis() -> None:
    frame = build_discovery_intent_frame("전기차 타이어 저소음으로 추천해줘")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "condition_recommendation"
    assert frame.entities["vehicle_category"] == "ev"
    assert frame.entities["quiet_focus"] is True
    assert plan.preferred_tool == "get_products_recommendations_tool"
    assert plan.tool_args_patch == {"rcmd_type": "low_vibration", "vehicle_type": "ev"}


def test_suv_value_recommendation_keeps_vehicle_axis() -> None:
    frame = build_discovery_intent_frame("SUV용 가성비 타이어 추천해줘")
    plan = plan_discovery_tools(frame)

    assert frame.entities["vehicle_category"] == "suv"
    assert frame.entities["value_focus"] is True
    assert plan.tool_args_patch == {"vehicle_type": "suv", "rcmd_type": "value"}


def test_low_noise_recommendation_maps_to_low_vibration() -> None:
    frame = build_discovery_intent_frame("저소음 타이어 추천해줘")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "condition_recommendation"
    assert frame.entities["quiet_focus"] is True
    assert plan.tool_args_patch == {"rcmd_type": "low_vibration"}


def test_default_tbot_shopping_cta_uses_basic_recommendation_flow() -> None:
    frame = build_discovery_intent_frame("T'Bot과 타이어 쇼핑하기")
    plan = plan_discovery_tools(frame)

    assert is_default_tire_shopping_request("T’Bot과 타이어 쇼핑하기") is True
    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "general_recommendation"
    assert frame.entities["default_tire_shopping"] is True
    assert plan.preferred_tool == "get_products_recommendations_tool"
    assert plan.tool_args_patch == {"rcmd_type": "tstation"}


def test_plain_tire_recommendation_uses_general_tstation_recommendation() -> None:
    frame = build_discovery_intent_frame("타이어 추천")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "general_recommendation"
    assert plan.preferred_tool == "get_products_recommendations_tool"
    assert plan.tool_args_patch == {"rcmd_type": "tstation"}


def test_default_benefit_cta_uses_events_and_deals_not_coupons() -> None:
    frame = build_discovery_intent_frame("지금 받을 수 있는 혜택은?")
    plan = plan_discovery_tools(frame)

    assert is_default_benefit_request("지금 받을 수 있는 혜택은?") is True
    assert frame.intent == "product_search"
    assert frame.sub_intent == "benefit_event_list_lookup"
    assert frame.entities["default_benefit"] is True
    assert plan.allowed_tools == ("get_events_tool", "get_deals_tool")
    assert plan.preferred_tool == "get_events_tool"
    assert "get_my_coupons_tool" in plan.forbidden_tools


def test_event_list_request_uses_events_and_deals() -> None:
    frame = build_discovery_intent_frame("진행 중인 이벤트")
    plan = plan_discovery_tools(frame)

    assert is_default_benefit_request("진행 중인 이벤트") is True
    assert frame.intent == "product_search"
    assert frame.sub_intent == "benefit_event_list_lookup"
    assert frame.entities["default_benefit"] is True
    assert plan.allowed_tools == ("get_events_tool", "get_deals_tool")
    assert plan.preferred_tool == "get_events_tool"
    assert "get_my_coupons_tool" in plan.forbidden_tools


def test_deal_list_request_uses_deals_only() -> None:
    frame = build_discovery_intent_frame("진행 중인 기획전")
    plan = plan_discovery_tools(frame)

    assert is_default_benefit_request("진행 중인 기획전") is False
    assert is_deal_list_request("진행 중인 기획전") is True
    assert frame.intent == "product_search"
    assert frame.sub_intent == "benefit_deal_list"
    assert frame.entities["deal_list_only"] is True
    assert plan.allowed_tools == ("get_deals_tool",)
    assert plan.preferred_tool == "get_deals_tool"
    assert "get_events_tool" in plan.forbidden_tools
    assert "get_my_coupons_tool" in plan.forbidden_tools


def test_tc006_sized_all_weather_lowest_price_has_size_and_sort() -> None:
    frame = build_discovery_intent_frame("2454518 사이즈 올웨더 타이어 중 가장 저렴한거 알려줘")
    plan = plan_discovery_tools(frame)

    assert frame.entities["tire_size"] == "245/45R18"
    assert frame.entities["season"] == "all_weather"
    assert frame.entities["price_goal"] == "lowest"
    assert plan.tool_args_patch["tire_size"] == "245/45R18"
    assert plan.tool_args_patch["sort_by"] == "price_asc"


def test_external_price_comparison_request_uses_external_sub_intent() -> None:
    for text in (
        "벤투스 air S 2354518 다나와에서 최저가 찾아줘",
        "벤투스 air S 2354518 구글에서 최저가 찾아줘",
        "벤투스 air S 2354518 네이버에서 최저가 찾아줘",
        "벤투스 air S 네이버 쇼핑 최저가",
        "벤투스 air S 쿠팡에서 싼 곳 찾아줘",
        "벤투스 air S 오픈마켓 가격 비교해줘",
    ):
        frame = build_discovery_intent_frame(text)
        plan = plan_discovery_tools(frame)

        assert is_external_price_comparison_request(text)
        assert frame.intent == "product_search"
        assert frame.sub_intent == "external_price_comparison_request"
        assert frame.entities["external_price_comparison"] is True
        assert plan.preferred_tool == "search_product_tool"
        assert plan.tool_args_patch["sort_by"] == "price_asc"
        assert "get_product_description_tool" in plan.forbidden_tools
        assert "get_products_recommendations_tool" in plan.forbidden_tools


def test_external_price_comparison_anchor_is_required_for_lowest_price_flows() -> None:
    size_only = build_discovery_intent_frame("2354518 최저가")
    explanation = build_discovery_intent_frame("벤투스 air S 설명해줘")
    internal_price = build_discovery_intent_frame("벤투스 air S 할인가 얼마야")

    assert not is_external_price_comparison_request("2354518 최저가")
    assert size_only.sub_intent == "condition_recommendation"
    assert explanation.sub_intent == "product_detail"
    assert internal_price.sub_intent == "product_name_search"


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
    assert plan.tool_args_patch == {"keyword": "Kinergy EX", "brand_cd": "HK"}
    assert "get_products_recommendations_tool" in plan.forbidden_tools


def test_short_alias_only_query_uses_product_search() -> None:
    frame = build_discovery_intent_frame("s fit as")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "product_name_search"
    assert frame.entities["product_names"] == ("S FIT AS",)
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


def test_quantity_benefit_comparison_preserves_quantities_and_requires_size() -> None:
    text = "옵티모 상품 2개살까 4개살까 고민 중인데 4개 사면 더 할인해줘?"
    frame = build_discovery_intent_frame(text)
    plan = plan_discovery_tools(frame)

    assert extract_quantity_options(text) == (2, 4)
    assert frame.intent == "product_comparison"
    assert frame.sub_intent == "quantity_benefit_comparison"
    assert frame.entities["product_names"] == ("Optimo",)
    assert frame.entities["quantity_options"] == (2, 4)
    assert frame.entities["compare_metric"] == "discount"
    assert frame.missing_slots == ("tire_size",)
    assert plan.preferred_tool == "search_product_tool"
    assert plan.tool_args_patch == {"keyword": "Optimo", "brand_cd": "HK"}


def test_sized_quantity_benefit_comparison_keeps_search_size() -> None:
    frame = build_discovery_intent_frame("옵티모 2155017 2개랑 4개 할인 비교해줘")
    plan = plan_discovery_tools(frame)

    assert frame.sub_intent == "quantity_benefit_comparison"
    assert frame.entities["tire_size"] == "215/50R17"
    assert frame.entities["quantity_options"] == (2, 4)
    assert frame.missing_slots == ()
    assert plan.tool_args_patch == {"keyword": "Optimo", "size": "215/50R17", "brand_cd": "HK"}


def test_plain_optimo_search_does_not_become_quantity_comparison() -> None:
    frame = build_discovery_intent_frame("옵티모 상품 알려줘")

    assert frame.intent == "product_search"
    assert frame.sub_intent == "product_name_search"
    assert "quantity_options" not in frame.entities


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
    assert plan.tool_args_patch == {"keyword": "Kinergy EX", "brand_cd": "HK"}


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


def test_tc215_mileage_tire_with_occupation_bias_is_description_guardrail() -> None:
    frame = build_discovery_intent_frame("마일리지 타이어 이거는 택시기사들이 쓰는거 아냐? 별로지?")

    assert frame.intent == "product_description"
    assert frame.sub_intent == "mileage_bias_guardrail"
    assert frame.entities["guardrail"] == "occupation_neutral"
    assert frame.entities["compare_metric"] == "mileage"


def test_mileage_plus_with_occupation_bias_stays_product_search_guardrail() -> None:
    frame = build_discovery_intent_frame("마일리지 플러스 이거는 택시기사들이 쓰는거 아냐? 별로지?")

    assert frame.intent == "product_search"
    assert frame.sub_intent == "product_name_search"
    assert frame.entities["guardrail"] == "occupation_neutral"
    assert frame.entities["product_keyword"] == "마일리지"
    assert frame.entities["product_names"] == ("Mileage Plus",)


def test_mileage_tire_recommendation_uses_attribute_recommendation() -> None:
    frame = build_discovery_intent_frame("마일리지 타이어 추천")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.sub_intent == "condition_recommendation"
    assert frame.entities["recommendation_scenario"] == "long_distance"
    assert "product_keyword" not in frame.entities
    assert plan.preferred_tool == "get_products_recommendations_tool"
    assert plan.tool_args_patch["rcmd_type"] == "long_distance"


def test_mileage_plus_recommendation_searches_product_name() -> None:
    frame = build_discovery_intent_frame("마일리지 플러스 추천")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "product_name_search"
    assert frame.entities["product_keyword"] == "마일리지"
    assert frame.entities["product_names"] == ("Mileage Plus",)
    assert plan.preferred_tool == "search_product_tool"


def test_product_name_stock_store_request_searches_product_name_first() -> None:
    frame = build_discovery_intent_frame("dynapro HPX 오늘 장착 가능한 근처 매장 알려줘")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "product_name_search"
    assert frame.entities["product_names"] == ("Dynapro HPX",)
    assert frame.entities["tire_size"] is None
    assert plan.preferred_tool == "search_product_tool"
    assert plan.tool_args_patch == {"keyword": "Dynapro HPX", "brand_cd": "HK"}
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
        {"rcmd_type": "all_weather", "season_nm": "사계절", "label": "사계절"},
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


def test_product_store_purchase_intent_uses_product_search_not_recommendation() -> None:
    frame = build_discovery_intent_frame("판교점에서 dynapro hpx 2개 구매하고싶어")
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "product_name_search"
    assert frame.entities["product_names"] == ("Dynapro HPX",)
    assert frame.entities["purchase_intent"] is True
    assert plan.preferred_tool == "search_product_tool"
    assert plan.tool_args_patch == {"keyword": "Dynapro HPX", "brand_cd": "HK"}


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
    assert frame.sub_intent == "condition_recommendation"
    assert frame.entities["recommendation_scenario"] == "long_distance"
    assert "product_keyword" not in frame.entities
    assert plan.preferred_tool == "get_products_recommendations_tool"
    assert plan.tool_args_patch["rcmd_type"] == "long_distance"
    assert plan.metadata["recommendation_expected_tool_args"] == {"rcmd_type": "long_distance"}


def test_router_mileage_scenario_uses_long_distance_recommendation_contract() -> None:
    frame = build_discovery_intent_frame(
        "우버 운영하고 있는데 마일리지 무조건 긴거 추천",
        known_slots={"recommendation_scenario": "mileage"},
    )
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_recommendation"
    assert frame.entities["recommendation_scenario"] == "long_distance"
    assert plan.preferred_tool == "get_products_recommendations_tool"
    assert plan.tool_args_patch["rcmd_type"] == "long_distance"
    assert plan.metadata["recommendation_expected_tool_args"] == {"rcmd_type": "long_distance"}


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
