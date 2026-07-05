from __future__ import annotations

import base64
import json
from types import SimpleNamespace

from services.tstation.policies.conversation_context_policy import (
    build_recent_interaction_summary,
    insert_recent_interaction_router_message,
)
from services.tstation.policies.discovery_intent_policy import build_discovery_intent_frame, plan_discovery_tools
from services.tstation.policies.discovery_response_policy import decide_discovery_response
from services.tstation.policies.intent_frame import IntentFrame, PolicyDomain
from services.tstation.policies.response_decision import ToolPlan
from services.tstation.policies.router_context import compact_router_messages
from services.tstation.policies.router_evidence import (
    build_router_evidence,
    merge_router_evidence_known_slots,
)
from services.tstation.policies.transaction_intent_policy import build_transaction_intent_frame, plan_transaction_tools
from services.tstation.policies.turn_contract import build_turn_contract


def _routing_result(
    *,
    primary_action: str,
    entity_candidates: dict,
    requested_product_attribute: str = "none",
    execution_plan: list[str] | None = None,
    domains: list[str] | None = None,
    policy_intent: str = "none",
) -> SimpleNamespace:
    return SimpleNamespace(
        reason="test",
        domains=domains or ["discovery"],
        execution_plan=execution_plan or ["discovery:test"],
        user_behavior="test",
        flow="test",
        claim_check_type="none",
        complaint_scope="none",
        requested_product_attribute=requested_product_attribute,
        policy_intent=policy_intent,
        primary_action=primary_action,
        entity_candidates={
            **{
                "registered_vehicle": {
                    "mentioned": False,
                    "anchor": "",
                    "reference_text": "",
                    "confidence": 0.0,
                },
                "store": {
                    "mentioned": False,
                    "name": "",
                    "type": "",
                    "reference_text": "",
                    "confidence": 0.0,
                },
                "coupon": {
                    "mentioned": False,
                    "name": "",
                    "type": "",
                    "reference_text": "",
                    "confidence": 0.0,
                },
                "benefit": {
                    "mentioned": False,
                    "name": "",
                    "type": "",
                    "reference_text": "",
                    "confidence": 0.0,
                },
                "location": {
                    "mentioned": False,
                    "name": "",
                    "type": "",
                    "reference_text": "",
                    "confidence": 0.0,
                },
            },
            **entity_candidates,
        },
        planner_confidence=0.9,
        agent_prompt_profile="discovery_recommendation",
    )


def test_router_evidence_keeps_registered_vehicle_anchor_and_recommend_action() -> None:
    routing = _routing_result(
        primary_action="recommend",
        requested_product_attribute="noise",
        entity_candidates={
            "registered_vehicle": {
                "mentioned": True,
                "anchor": "제타",
                "reference_text": "내가 닷컴에 등록해놓은 제타",
                "confidence": 0.9,
            }
        },
        execution_plan=["discovery:vehicle_tire_recommendation"],
    )

    evidence = build_router_evidence(routing, domains=["discovery"])

    assert evidence["primary_action"] == "recommend"
    assert evidence["entities"]["registered_vehicle"]["anchor"] == "제타"
    assert evidence["entities"]["registered_vehicle"]["source"] == "router"
    assert routing.requested_product_attribute == "noise"


def test_router_evidence_keeps_store_coupon_and_location_candidates() -> None:
    store_routing = _routing_result(
        primary_action="reserve",
        entity_candidates={
            "store": {
                "mentioned": True,
                "name": "판교점",
                "type": "store",
                "reference_text": "티스테이션 판교점",
                "confidence": 0.9,
            }
        },
        execution_plan=["transaction:store_schedule_lookup"],
    )
    coupon_routing = _routing_result(
        primary_action="coupon_use",
        entity_candidates={
            "coupon": {
                "mentioned": True,
                "name": "생일 쿠폰",
                "type": "coupon",
                "reference_text": "생일 쿠폰",
                "confidence": 0.85,
            }
        },
        execution_plan=["support:coupon_usage_policy"],
    )
    location_routing = _routing_result(
        primary_action="store_search",
        entity_candidates={
            "location": {
                "mentioned": True,
                "name": "강남역",
                "type": "station",
                "reference_text": "강남역 근처",
                "confidence": 0.9,
            }
        },
        execution_plan=["transaction:store_search"],
    )

    store_evidence = build_router_evidence(store_routing, domains=["transaction"])
    coupon_evidence = build_router_evidence(coupon_routing, domains=["support"])
    location_evidence = build_router_evidence(location_routing, domains=["transaction"])

    assert store_evidence["entities"]["store"]["name"] == "판교점"
    assert store_evidence["primary_action"] == "reserve"
    assert coupon_evidence["entities"]["coupon"]["name"] == "생일 쿠폰"
    assert coupon_evidence["primary_action"] == "coupon_use"
    assert location_evidence["entities"]["location"]["name"] == "강남역"
    assert location_evidence["entities"]["location"]["type"] == "station"


def test_router_benefit_entity_fills_applicable_products_query_slot() -> None:
    routing = _routing_result(
        primary_action="lookup",
        entity_candidates={
            "benefit": {
                "mentioned": True,
                "name": "반짝블랙딜",
                "type": "deal",
                "reference_text": "반짝블랙딜에 적용 가능한 상품",
                "confidence": 0.91,
            }
        },
        execution_plan=["discovery:event_applicable_products_lookup"],
    )

    evidence = build_router_evidence(routing, domains=["discovery"])
    known_slots = merge_router_evidence_known_slots({}, evidence, preserve_existing=False)
    frame = build_discovery_intent_frame("반짝블랙딜에 적용 가능한 상품이 뭐야", known_slots=known_slots)
    plan = plan_discovery_tools(frame)

    assert evidence["entities"]["benefit"]["name"] == "반짝블랙딜"
    assert known_slots["benefit_applicable_products_query"] == "반짝블랙딜"
    assert plan.preferred_tool == "search_benefit_applicable_products_tool"
    assert plan.tool_args_patch == {"query": "반짝블랙딜", "lang_cd": "ko"}


def test_router_evidence_canonicalizes_price_benefit_alias_and_preserves_raw_intent() -> None:
    routing = _routing_result(
        primary_action="lookup",
        entity_candidates={},
        execution_plan=["transaction:price_or_benefit_lookup"],
        domains=["transaction"],
        policy_intent="price_or_benefit_lookup",
    )

    evidence = build_router_evidence(routing, domains=["transaction"])

    assert evidence["intent"] == "price_or_coupon_check"
    assert evidence["raw_intent"] == "price_or_benefit_lookup"
    assert evidence["policy_intent"] == "price_or_coupon_check"
    assert evidence["raw_policy_intent"] == "price_or_benefit_lookup"


def test_router_context_compacts_append_description_and_card_payload() -> None:
    encoded = base64.b64encode(("상품 상세 설명" * 80).encode()).decode()
    messages = [
        {"role": "user", "content": "벤투스 에어S 보여줘"},
        {
            "role": "assistant",
            "content": "[이전 선택된 상품 데이터]\n" + encoded,
            "template_data": {
                "template": "product",
                "data": {
                    "products": [
                        {
                            "productName": "벤투스 에어S",
                            "description": "긴 카드 설명" * 200,
                            "imageUrl": "https://example.invalid/image.png",
                        }
                    ],
                    "metadata": {"response_shape_key": "product_search_summary"},
                },
                "assistant_response_source": "code_template_mapper",
            },
        },
        {"role": "user", "content": "# Respond in Korean language\n강남역 근처 장착점 찾아줘"},
    ]

    result = compact_router_messages(messages)
    compact_text = "\n".join(str(message.get("content") or "") for message in result.messages)

    assert result.metadata["router_compacted"] is True
    assert result.metadata["router_input_chars_after"] < result.metadata["router_input_chars_before"]
    assert encoded not in compact_text
    assert "긴 카드 설명" not in compact_text
    assert "강남역 근처 장착점 찾아줘" in compact_text


def test_router_context_includes_recent_interaction_summary_as_reference_only() -> None:
    latest_quickreply = {
        "template": "quickReply",
        "assistant_response_source": "code_coupon_resolver",
        "data": {
            "assistantResponse": "‘쿠폰 뱃지 테스트’ 적용 가능 상품은 9개예요.\n- 키너지 EX",
            "quickReplies": [{"label": "구매하기", "domain": "TRANSACTION"}],
            "predictedDomains": ["TRANSACTION"],
        },
    }
    summary = build_recent_interaction_summary(latest_quickreply_tmpl=latest_quickreply)
    messages = insert_recent_interaction_router_message(
        [
            {"role": "user", "content": "쿠폰 뱃지 테스트에 적용 가능한 상품은 뭐야?"},
            {
                "role": "assistant",
                "content": "‘쿠폰 뱃지 테스트’ 적용 가능 상품은 9개예요.",
                "template_data": latest_quickreply,
            },
            {"role": "user", "content": "1월 키너지EX 특가전은?"},
        ],
        summary,
    )

    result = compact_router_messages(messages)
    compact_message = next(
        message for message in result.messages if str(message.get("content") or "").startswith("ROUTER COMPACT CONTEXT:")
    )
    compact_payload = json.loads(str(compact_message["content"]).split("\n", 1)[1])
    recent_summary = compact_payload["recent_interaction_summary"]

    assert recent_summary["reference_only"] is True
    assert recent_summary["do_not_execute_from_context"] is True
    assert recent_summary["last_task"] == "applicable_products_lookup"
    assert recent_summary["last_subject"] == "쿠폰 뱃지 테스트"
    assert recent_summary["last_result_type"] == "applicable_products"


def test_router_registered_vehicle_anchor_reaches_discovery_contract() -> None:
    routing = _routing_result(
        primary_action="recommend",
        requested_product_attribute="noise",
        entity_candidates={
            "registered_vehicle": {
                "mentioned": True,
                "anchor": "제타",
                "reference_text": "내가 닷컴에 등록해놓은 제타",
                "confidence": 0.9,
            }
        },
        execution_plan=["discovery:vehicle_tire_recommendation"],
    )
    evidence = build_router_evidence(routing, domains=["discovery"])
    known_slots = merge_router_evidence_known_slots(
        {"requested_product_attribute": routing.requested_product_attribute},
        evidence,
        preserve_existing=False,
    )

    frame = build_discovery_intent_frame("그 차에 맞는 정숙성 좋은 타이어 추천해줘", known_slots=known_slots)
    plan = plan_discovery_tools(frame)
    contract = build_turn_contract(
        user_text="그 차에 맞는 정숙성 좋은 타이어 추천해줘",
        intent_frame=frame,
        tool_plan=plan,
        routing_result=routing,
        merged_slots={"availability_context": {"latest_router_evidence": evidence}},
    )

    assert frame.entities["named_registered_vehicle_anchor"] == "제타"
    assert frame.entities["requested_product_attribute"] == "noise"
    assert plan.allowed_tools == ("get_my_cars_tool", "get_products_recommendations_tool")
    assert plan.preferred_tool == "get_my_cars_tool"
    assert contract.known_slots["named_registered_vehicle_anchor"] == "제타"
    assert contract.known_slots["slot_sources"]["named_registered_vehicle_anchor"] == "router_evidence"


def test_router_store_name_reaches_store_schedule_tool_args() -> None:
    routing = _routing_result(
        primary_action="book",
        domains=["transaction"],
        entity_candidates={
            "store": {
                "mentioned": True,
                "name": "판교점",
                "reference_text": "티스테이션 판교점",
                "confidence": 0.9,
            }
        },
        execution_plan=["transaction:store_schedule"],
    )
    evidence = build_router_evidence(routing, domains=["transaction"])
    known_slots = merge_router_evidence_known_slots({}, evidence, preserve_existing=False)

    frame = build_transaction_intent_frame("예약 가능해?", known_slots=known_slots)
    plan = plan_transaction_tools(frame)

    assert frame.known_slots["store_name_candidate"] == "판교점"
    assert frame.known_slots["store_name"] == "판교점"
    assert plan.preferred_tool == "get_store_schedule_tool"
    assert plan.tool_args_patch["store_name"] == "판교점"


def test_router_generic_compare_does_not_override_multi_product_description_request() -> None:
    routing = _routing_result(
        primary_action="lookup",
        execution_plan=[
            "identify the two products",
            "retrieve or summarize their product details",
            "present a concise comparison-friendly description",
        ],
        entity_candidates={},
        domains=["discovery"],
    )
    routing.comparison_followup_intent = "generic_compare"
    routing.comparison_metric = "detail"
    evidence = build_router_evidence(routing, domains=["discovery"])
    frame = build_discovery_intent_frame("kinergy EX, Ventus S2 AS 설명해줘")
    plan = plan_discovery_tools(frame)
    response_decision = decide_discovery_response(frame)
    contract = build_turn_contract(
        user_text="kinergy EX, Ventus S2 AS 설명해줘",
        intent_frame=frame,
        tool_plan=plan,
        response_decision=response_decision,
        routing_result=routing,
        merged_slots={"availability_context": {"latest_router_evidence": evidence}},
    )

    assert frame.intent == "product_description"
    assert frame.entities["multi_product_description_request"] is True
    assert contract.intent != "product_comparison"
    assert contract.response_decision["metadata"]["response_shape_key"] == "neutral_product_description"
    assert contract.router_wins_applied is False


def test_purchase_product_resolution_prefers_normalized_tool_keyword_over_polluted_slot() -> None:
    frame = build_discovery_intent_frame(
        "아이온 에보 as suv 구매할래",
        known_slots={
            "router_primary_action": "buy",
            "pending_intent": "order",
            "goal_type": "place_order",
            "pending_product_name": "아이온 에보 as suv 할래",
            "tire_model": "아이온 에보 as suv 할래",
            "slot_sources": {
                "pending_product_name": "regex_supplemental",
                "tire_model": "regex_supplemental",
            },
        },
    )
    plan = plan_discovery_tools(frame)
    response_decision = decide_discovery_response(frame)
    contract = build_turn_contract(
        user_text="아이온 에보 as suv 구매할래",
        intent_frame=frame,
        tool_plan=plan,
        response_decision=response_decision,
        action_mode="purchase_continuation",
        context_state="resumed",
        resume_source="explicit_user",
    )

    assert plan.tool_args_patch["keyword"] == "iON evo AS SUV"
    assert contract.known_slots["pending_product_name"] == "iON evo AS SUV"
    assert contract.known_slots["tire_model"] == "iON evo AS SUV"
    assert contract.known_slots["slot_sources"]["pending_product_name"] == "router_evidence"
    assert contract.known_slots["slot_sources"]["tire_model"] == "router_evidence"


def test_router_coupon_name_is_preserved_without_forcing_support_to_transaction() -> None:
    routing = _routing_result(
        primary_action="use_coupon",
        domains=["transaction"],
        entity_candidates={
            "coupon": {
                "mentioned": True,
                "name": "생일 쿠폰",
                "reference_text": "생일 쿠폰",
                "confidence": 0.85,
            }
        },
        execution_plan=["transaction:owned_coupon_lookup"],
    )
    evidence = build_router_evidence(routing, domains=["transaction"])
    known_slots = merge_router_evidence_known_slots({}, evidence, preserve_existing=False)
    frame = build_transaction_intent_frame("쿠폰 쓸 수 있어?", known_slots=known_slots)
    plan = plan_transaction_tools(frame)

    assert frame.known_slots["coupon_name_candidate"] == "생일 쿠폰"
    assert frame.known_slots["coupon_name"] == "생일 쿠폰"
    assert "get_my_coupons_tool" in plan.allowed_tools

    support_routing = _routing_result(
        primary_action="ask_policy",
        domains=["support"],
        policy_intent="coupon_registration_policy",
        entity_candidates={
            "coupon": {
                "mentioned": True,
                "name": "생일 쿠폰",
                "reference_text": "생일 쿠폰 어디서 봐",
                "confidence": 0.85,
            }
        },
        execution_plan=["support:coupon_registration_policy"],
    )
    support_evidence = build_router_evidence(support_routing, domains=["support"])
    support_contract = build_turn_contract(
        user_text="생일 쿠폰은 어디서 봐?",
        intent_frame=IntentFrame(
            domain=PolicyDomain.SUPPORT,
            intent="coupon_registration_policy",
            known_slots={},
        ),
        tool_plan=ToolPlan(
            allowed_tools=("search_faq_hybrid_tool",),
            preferred_tool="search_faq_hybrid_tool",
        ),
        routing_result=support_routing,
        merged_slots={"availability_context": {"latest_router_evidence": support_evidence}},
        action_mode="support_policy_answer",
    )

    assert support_contract.domain == "support"
    assert support_contract.intent == "coupon_registration_policy"
    assert support_contract.known_slots["coupon_name_candidate"] == "생일 쿠폰"


def test_router_location_reaches_store_search_args_and_regex_does_not_override() -> None:
    routing = _routing_result(
        primary_action="search",
        domains=["transaction"],
        entity_candidates={
            "location": {
                "mentioned": True,
                "name": "강남역",
                "type": "station",
                "reference_text": "강남역 근처",
                "confidence": 0.9,
            }
        },
        execution_plan=["transaction:store_search"],
    )
    evidence = build_router_evidence(routing, domains=["transaction"])
    known_slots = merge_router_evidence_known_slots(
        {"location_name": "정규식후보"},
        evidence,
        preserve_existing=False,
    )

    frame = build_transaction_intent_frame("장착점 찾아줘", known_slots=known_slots)
    plan = plan_transaction_tools(frame)

    assert frame.known_slots["location_name"] == "강남역"
    assert frame.known_slots["location_type"] == "station"
    assert plan.preferred_tool in {"search_stores_tool", "search_stores_complex_tool"}
    assert plan.tool_args_patch["place_query"] == "강남역"


def test_router_evidence_regex_fallback_only_fills_empty_entities() -> None:
    routing = _routing_result(
        primary_action="search",
        domains=["transaction"],
        entity_candidates={
            "store": {
                "mentioned": True,
                "name": "판교점",
                "reference_text": "티스테이션 판교점",
                "confidence": 0.9,
            }
        },
        execution_plan=["transaction:store_search"],
    )

    evidence = build_router_evidence(
        routing,
        domains=["transaction"],
        regex_candidates={"store": {"name": "정규식점", "confidence": 0.4}},
    )
    fallback = build_router_evidence(
        _routing_result(
            primary_action="search",
            domains=["transaction"],
            entity_candidates={},
            execution_plan=["transaction:store_search"],
        ),
        domains=["transaction"],
        regex_candidates={"store": {"name": "정규식점", "confidence": 0.4}},
    )

    assert evidence["entities"]["store"]["name"] == "판교점"
    assert fallback["entities"]["store"]["name"] == "정규식점"
    assert fallback["entities"]["store"]["source"] == "regex_supplemental"
