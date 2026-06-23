"""Deterministic response decisions for Discovery product flows."""

from __future__ import annotations

from services.tstation.policies.discovery_intent_policy import IntentFrame
from services.tstation.policies.response_decision import ResponseDecision, ResponseShape, TemplateName


def _metadata(frame: IntentFrame, **values: object) -> dict[str, object]:
    metadata = dict(values)
    claim_check_type = frame.entities.get("claim_check_type")
    if claim_check_type and claim_check_type != "none":
        metadata["claim_check_type"] = claim_check_type
    requested_product_attribute = str(frame.entities.get("requested_product_attribute") or "")
    if requested_product_attribute:
        metadata["requested_product_attribute"] = requested_product_attribute
    compare_metric = str(frame.entities.get("compare_metric") or "")
    if compare_metric:
        metadata["compare_metric"] = compare_metric
    comparison_followup_intent = str(frame.entities.get("comparison_followup_intent") or "")
    if comparison_followup_intent:
        metadata["comparison_followup_intent"] = comparison_followup_intent
    recent_product_set_followup_type = str(frame.entities.get("recent_product_set_followup_type") or "")
    if recent_product_set_followup_type:
        metadata["recent_product_set_followup_type"] = recent_product_set_followup_type
    recent_product_set_metric = str(frame.entities.get("recent_product_set_metric") or "")
    if recent_product_set_metric:
        metadata["recent_product_set_metric"] = recent_product_set_metric
    recent_product_set_direction = str(frame.entities.get("recent_product_set_direction") or "")
    if recent_product_set_direction:
        metadata["recent_product_set_direction"] = recent_product_set_direction
    recent_product_set_price_basis = str(frame.entities.get("recent_product_set_price_basis") or "")
    if recent_product_set_price_basis:
        metadata["recent_product_set_price_basis"] = recent_product_set_price_basis
    oe_replacement_type = str(frame.entities.get("oe_replacement_type") or "")
    if oe_replacement_type:
        metadata["oe_replacement_type"] = oe_replacement_type
    for key in (
        "recommendation_scenario",
        "recommendation_scenario_label",
        "applied_rcmd_type",
        "applied_vehicle_type",
        "applied_season_nm",
        "approximation",
        "approximation_basis",
    ):
        value = frame.entities.get(key)
        if value not in (None, ""):
            metadata[key] = value
    return metadata


def decide_discovery_response(frame: IntentFrame) -> ResponseDecision:
    entities = frame.entities
    tire_size = entities.get("tire_size")

    if frame.sub_intent == "external_price_comparison_request":
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=(
                "claim_external_price_checked",
                "external_price_scraping",
                "product_description_answer",
                "generic_recommendation_cta",
            ),
            assistant_guidance=(
                "다나와/구글/네이버/오픈마켓 등 외부 사이트 실시간 최저가 비교는 하지 않는다고 명확히 밝힌다. "
                "대신 T'Station 내부 가격과 회원 쿠폰 기준 최저 혜택가만 안내할 수 있다."
            ),
            metadata={"response_shape_key": "external_price_comparison_unavailable_internal_price"},
        )

    if frame.sub_intent == "season_concept_compare":
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("drop_winter_constraint", "recommend_non_winter_for_winter_request"),
            assistant_guidance=(
                "윈터와 사계절 개념을 먼저 설명하고, 후속 추천이 이어지면 겨울/윈터 조건을 유지한다."
            ),
            metadata={"response_shape_key": "concept_explanation_then_optional_winter_recommendation"},
        )

    if frame.sub_intent == "mileage_compare":
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("product_card_first_response", "generic_unsized_summary"),
            assistant_guidance="DB의 마일리지/수명 지표로 비교하고 차종 호환과 주행환경에 따라 달라질 수 있음을 밝힌다.",
            metadata=_metadata(frame, response_shape_key="metric_comparison_summary", compare_metric="mileage"),
        )

    if frame.sub_intent == "quantity_benefit_comparison":
        quantity_options = tuple(entities.get("quantity_options") or ())
        if tire_size or frame.known_slots.get("goods_no"):
            return ResponseDecision(
                response_shape=ResponseShape.SUMMARY,
                template=TemplateName.QUICK_REPLY,
                required_slots=(),
                forbidden_behaviors=("answer_without_price_tool", "summarize_product_family_instead_of_comparing"),
                assistant_guidance="확정 상품의 2개/4개 실제 혜택가를 각각 조회한 뒤 총액과 개당가 기준으로 비교한다.",
                metadata={
                    "response_shape_key": "quantity_benefit_comparison",
                    "quantity_options": quantity_options,
                },
            )
        return ResponseDecision(
            response_shape=ResponseShape.CLARIFY,
            template=TemplateName.QUICK_REPLY,
            required_slots=("tire_size",),
            forbidden_behaviors=(
                "product_search_summary_as_final_answer",
                "price_without_size",
                "answer_without_price_tool",
            ),
            assistant_guidance=(
                "2개/4개 혜택 비교는 정확한 상품 규격이 필요하므로 상품군 설명으로 끝내지 말고 "
                "타이어 사이즈 또는 차량 확인을 요청한다."
            ),
            metadata={
                "response_shape_key": "quantity_benefit_comparison_missing_product_or_size",
                "quantity_options": quantity_options,
            },
        )

    if frame.sub_intent == "recent_product_set_ranking":
        metric = str(entities.get("recent_product_set_metric") or "")
        price_basis = str(entities.get("recent_product_set_price_basis") or "")
        criterion = {
            "price": f"{price_basis or 'cheapest_final_prc'} 기준",
            "noise": "소음 dB/소음 라벨 기준",
            "wet": "빗길 성능 등급 기준",
            "snow": "눈길/빙판 성능 지표 기준",
            "release": "출시월/등록일 기준",
            "review": "리뷰 수 기준",
            "rating": "평점 기준",
            "grade": "상품 등급 기준",
            "vehicle_type": "차종 필드 기준",
            "mileage": "마일리지/수명 지표 기준",
            "detail": "상품 상세 필드 기준",
        }.get(metric, "선택한 비교 기준")
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("recent_product_set_ranking_without_tool_context", "ranking_without_criterion"),
            assistant_guidance=(
                "최근 상품 목록 tool context만 기준으로 순위를 판단한다. 답변에는 반드시 기준을 명시한다 "
                f"({criterion}). 사이즈가 없거나 서로 다른 규격이면 대표 규격 기준이며 실제 차량 규격별 가격/성능은 달라질 수 있음을 밝힌다. "
                "필드가 없으면 단정하지 말고 확인 어렵다고 답한다."
            ),
            metadata=_metadata(frame, response_shape_key="recent_product_set_ranking_summary"),
        )

    if frame.sub_intent in ("attribute_compare", "latest_compare", "general_compare"):
        compare_metric = str(entities.get("compare_metric") or "detail")
        response_shape_key = (
            "grade_comparison_summary"
            if compare_metric in {"grade", "price_grade"} or frame.sub_intent == "grade_compare"
            else "metric_comparison_summary"
        )
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("product_card_first_response", "generic_unsized_summary", "comparison_without_db_basis"),
            assistant_guidance="비교 대상 상품을 DB 필드 기준으로 비교하고, 규격별 값 차이가 있을 수 있음을 밝힌다.",
            metadata=_metadata(frame, response_shape_key=response_shape_key, compare_metric=compare_metric),
        )

    if frame.sub_intent == "mileage_bias_guardrail":
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("occupation_stereotype", "treat_mileage_as_only_attribute"),
            assistant_guidance="직업군 평가는 배제하고 마일리지 플러스 2/3 같은 상품명과 내구 특성을 중립적으로 구분한다.",
            metadata={"response_shape_key": "neutral_product_description"},
        )

    if frame.sub_intent == "grade_compare":
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("misrecognize_ventus_air_s", "claim_kinergy_ex_is_premium_above_ventus"),
            assistant_guidance="상품명을 정확히 인식하고 각 상품의 등급/포지션 근거로 비교한다.",
            metadata=_metadata(frame, response_shape_key="grade_comparison_summary", compare_metric="grade"),
        )

    if frame.sub_intent == "oe_re_concept_explanation":
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("generic_unsized_summary", "claim_all_products_are_re"),
            assistant_guidance=(
                "OE/RE 개념만 설명하고, 현재 상품 데이터에 직접 확인 가능한 필드가 없으면 "
                "특정 상품을 OE 또는 RE로 단정하지 않는다."
            ),
            metadata=_metadata(frame, response_shape_key="oe_re_concept_explanation"),
        )

    if frame.sub_intent == "oe_re_product_filter":
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=(
                "generic_unsized_summary",
                "claim_all_products_are_re",
                "invent_oe_re_classification",
            ),
            assistant_guidance=(
                "OE 여부는 oe_badge_yn, t_oe_maker_1, certify_brand_nm 같은 실제 상품 필드로만 설명한다. "
                "RE 전용 확정 필드가 부족하면 교체용 판매 개념만 설명하고 특정 상품을 RE라고 단정하지 않는다."
            ),
            metadata=_metadata(frame, response_shape_key="oe_re_product_filter_summary"),
        )

    if frame.sub_intent in ("product_attribute_lookup", "product_attribute_explanation"):
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("generic_unsized_summary", "omit_requested_product_attribute_when_available"),
            assistant_guidance="사용자가 물은 상품 상세 항목을 DB 필드 기준으로 안내한다.",
            metadata=_metadata(frame, response_shape_key="product_attribute_summary"),
        )

    if frame.sub_intent == "similar_price_recommendation":
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=(
                "require_size_unconditionally",
                "inject_stale_confirmed_tire_size",
                "drop_latest_size_specific_context",
                "price_without_basis",
            ),
            assistant_guidance=(
                "정가 기준 가격대 range로 유사 상품을 추천한다. 최신 흐름이 사이즈 없는 상품군 설명이면 "
                "사이즈를 주입하지 말고, 최신 흐름에서 특정 사이즈/SKU가 확인됐거나 사용자가 해당 사이즈를 "
                "가리키면 그 tire_size를 유지한다."
            ),
            metadata={"response_shape_key": "similar_price_range_recommendation"},
        )

    if entities.get("technology") == "sound_absorber":
        if tire_size:
            return ResponseDecision(
                response_shape=ResponseShape.CARD,
                template=TemplateName.PRODUCT,
                required_slots=("tire_size",),
                forbidden_behaviors=("drop_sound_absorber_filter", "use_generic_noise_filter"),
                assistant_guidance="DB의 흡음재 적용 태그와 요청 규격을 함께 만족하는 상품만 카드/가격으로 안내한다.",
                metadata={"response_shape_key": "sized_technology_recommendation_cards"},
            )
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("drop_sound_absorber_filter", "product_card_without_size", "price_without_size"),
            assistant_guidance="흡음재 의미를 설명한 뒤 흡음재 적용 상품군을 요약하고 차량/규격 확인으로 유도한다.",
            metadata={"response_shape_key": "technology_explanation_then_unsized_recommendation_summary"},
        )

    if entities.get("service_program") == "safe_service":
        if tire_size:
            return ResponseDecision(
                response_shape=ResponseShape.CARD,
                template=TemplateName.PRODUCT,
                required_slots=("tire_size",),
                forbidden_behaviors=("drop_safe_service_filter", "claim_safe_service_without_hankook_basis"),
                assistant_guidance="안심서비스 가능 조건과 요청 규격을 함께 만족하는 한국타이어 상품만 카드/가격으로 안내한다.",
                metadata={"response_shape_key": "sized_safe_service_recommendation_cards"},
            )
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=(
                "generic_unsized_summary",
                "product_card_without_size",
                "price_without_size",
                "claim_safe_service_without_hankook_basis",
            ),
            assistant_guidance="안심서비스/안심플러스를 간략히 설명한 뒤 가능 대표 상품을 요약하고 차량/규격 확인으로 유도한다.",
            metadata={"response_shape_key": "safe_service_explanation_then_unsized_recommendation_summary"},
        )

    if entities.get("price_goal") == "lowest" and tire_size:
        return ResponseDecision(
            response_shape=ResponseShape.CARD,
            template=TemplateName.PRODUCT,
            required_slots=("tire_size",),
            forbidden_behaviors=("omit_discount_rate", "omit_badge_on_premium_alternatives"),
            assistant_guidance="요청 규격의 최저가 기준 상품을 가격/최대혜택 할인율과 함께 안내한다.",
            metadata={"response_shape_key": "sized_lowest_price_recommendation"},
        )

    if frame.sub_intent == "best_seller_search":
        return ResponseDecision(
            response_shape=ResponseShape.CARD,
            template=TemplateName.PRODUCT,
            required_slots=(),
            forbidden_behaviors=("use_generic_recommendation_engine", "expose_sales_count"),
            assistant_guidance="최근 3개월 등 요청 기간의 베스트셀러 도구 결과를 product 카드로 안내하고 판매 수량은 노출하지 않는다.",
            metadata={"response_shape_key": "best_seller_product_cards"},
        )

    if frame.intent == "product_recommendation" and not tire_size:
        if entities.get("discovery_followup_action") == "vehicle_based_recommendation_refinement":
            return ResponseDecision(
                response_shape=ResponseShape.CARD,
                template=TemplateName.PRODUCT,
                required_slots=("tire_size",),
                forbidden_behaviors=("drop_previous_recommendation_filter",),
                assistant_guidance=(
                    "등록 차량 조회로 tire_size를 해소한 뒤 직전 추천 조건을 유지해 상품을 추천한다. "
                    "차량 조회 실패 또는 등록 차량 없음이면 차량번호나 사이즈 확인 quickReply로 안내한다."
                ),
                metadata=_metadata(frame, response_shape_key="vehicle_based_recommendation_refinement"),
            )
        if entities.get("recommendation_scenario"):
            return ResponseDecision(
                response_shape=ResponseShape.SUMMARY,
                template=TemplateName.QUICK_REPLY,
                required_slots=(),
                forbidden_behaviors=(
                    "product_card_without_size",
                    "price_without_size",
                    "drop_recommendation_scenario",
                    "claim_unsupported_scenario_as_exact",
                ),
                assistant_guidance=(
                    "catalog recommendation scenario와 실제 적용된 tool 조건만 설명한다. "
                    "approximation=true이면 전용 상품이라고 단정하지 말고 근사 기준을 밝힌다."
                ),
                metadata=_metadata(frame, response_shape_key="catalog_unsized_recommendation_summary"),
            )
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("product_card_without_size", "price_without_size", "drop_season_constraint"),
            assistant_guidance="사이즈가 없으면 카드/가격 대신 조건에 맞는 패턴 설명 중심으로 안내한다.",
            metadata={"response_shape_key": "unsized_recommendation_summary"},
        )

    if frame.intent == "product_search":
        if frame.sub_intent in {
            "product_event_lookup",
            "product_deal_lookup",
            "product_coupon_lookup",
            "product_benefit_lookup",
        }:
            return ResponseDecision(
                response_shape=ResponseShape.SUMMARY,
                template=TemplateName.QUICK_REPLY,
                required_slots=(),
                forbidden_behaviors=(
                    "product_description_answer",
                    "ask_size_for_product_benefit_lookup",
                    "route_product_benefit_to_order_flow",
                    "datepick_or_preorder_for_product_benefit_lookup",
                ),
                assistant_guidance=(
                    "상품명+행사/이벤트/기획전/쿠폰/혜택 질의는 상품 설명이나 규격 선택으로 끝내지 않는다. "
                    "사이즈 없이 search_product_tool로 상품을 resolve한 뒤 적용 가능한 이벤트/기획전/쿠폰 tool 결과만 요약한다. "
                    "가격/주문/예약/장착 가능 여부로 확장하지 않는다."
                ),
                metadata={
                    "response_shape_key": frame.sub_intent,
                    "goal_type": "product_event_lookup",
                },
            )
        if frame.sub_intent == "restock_inquiry":
            return ResponseDecision(
                response_shape=ResponseShape.SUMMARY,
                template=TemplateName.QUICK_REPLY,
                required_slots=(),
                forbidden_behaviors=(
                    "product_card_first_response",
                    "promise_restock_date_without_source",
                    "treat_restock_question_as_product_recommendation",
                ),
                assistant_guidance="재입고 일정은 단정하지 말고, 품절/재입고 문의 답변과 다음 액션을 안내한다.",
                metadata={"response_shape_key": "restock_inquiry_summary"},
            )
        forbidden_behaviors = [
            "treat_product_name_as_attribute_recommendation",
            "answer_from_previous_recommendation",
        ]
        if entities.get("guardrail") == "occupation_neutral":
            forbidden_behaviors.append("occupation_stereotype")
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=tuple(forbidden_behaviors),
            assistant_guidance="상품명 검색 결과 기준으로 답하고 이전 추천 결과로 대체하지 않는다.",
            metadata={"response_shape_key": "product_search_summary"},
        )

    if frame.intent == "product_description":
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("generic_unsized_summary", "unrequested_size_missing_notice"),
            assistant_guidance="상품 설명 요청에는 상품 특성만 간결히 안내하고, 사용자가 묻지 않은 사이즈 미확정 안내를 덧붙이지 않는다.",
            metadata=_metadata(frame, response_shape_key="neutral_product_description"),
        )

    return ResponseDecision(
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        required_slots=(),
        forbidden_behaviors=(),
        assistant_guidance="Discovery 정책 범위 안에서 상품 정보와 다음 확인 단계를 안내한다.",
        metadata={"response_shape_key": "discovery_summary"},
    )
