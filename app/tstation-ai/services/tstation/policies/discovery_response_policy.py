"""Deterministic response decisions for Discovery product flows."""

from __future__ import annotations

from services.tstation.policies.discovery_intent_policy import IntentFrame
from services.tstation.policies.response_decision import ResponseDecision, ResponseShape, TemplateName


def decide_discovery_response(frame: IntentFrame) -> ResponseDecision:
    entities = frame.entities
    tire_size = entities.get("tire_size")

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
            metadata={"response_shape_key": "metric_comparison_summary", "compare_metric": "mileage"},
        )

    if frame.sub_intent in ("attribute_compare", "latest_compare"):
        compare_metric = str(entities.get("compare_metric") or "detail")
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("product_card_first_response", "generic_unsized_summary", "comparison_without_db_basis"),
            assistant_guidance="비교 대상 상품을 DB 필드 기준으로 비교하고, 규격별 값 차이가 있을 수 있음을 밝힌다.",
            metadata={"response_shape_key": "metric_comparison_summary", "compare_metric": compare_metric},
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
            metadata={"response_shape_key": "grade_comparison_summary"},
        )

    if frame.sub_intent in ("product_attribute_lookup", "product_attribute_explanation"):
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("generic_unsized_summary", "omit_requested_product_attribute_when_available"),
            assistant_guidance="사용자가 물은 상품 상세 항목을 DB 필드 기준으로 안내한다.",
            metadata={"response_shape_key": "product_attribute_summary"},
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
        return ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=(),
            forbidden_behaviors=("product_card_without_size", "price_without_size", "drop_season_constraint"),
            assistant_guidance="사이즈가 없으면 카드/가격 대신 조건에 맞는 패턴 설명 중심으로 안내한다.",
            metadata={"response_shape_key": "unsized_recommendation_summary"},
        )

    if frame.intent == "product_search":
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
            metadata={"response_shape_key": "neutral_product_description"},
        )

    return ResponseDecision(
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        required_slots=(),
        forbidden_behaviors=(),
        assistant_guidance="Discovery 정책 범위 안에서 상품 정보와 다음 확인 단계를 안내한다.",
        metadata={"response_shape_key": "discovery_summary"},
    )
