from __future__ import annotations

import base64

from services.tstation.chat import AgentPromptProfile, MultiAgentDomain
from services.tstation.policies.router_context import compact_router_messages
from services.tstation.policies.router_evidence import build_router_evidence


def _routing_result(
    *,
    primary_action: str,
    entity_candidates: dict,
    requested_product_attribute: str = "none",
    execution_plan: list[str] | None = None,
) -> MultiAgentDomain:
    return MultiAgentDomain(
        reason="test",
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        execution_plan=execution_plan or ["discovery:test"],
        user_behavior="test",
        flow="test",
        claim_check_type="none",
        complaint_scope="none",
        requested_product_attribute=requested_product_attribute,
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
        agent_prompt_profile=AgentPromptProfile.DISCOVERY_RECOMMENDATION,
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

    evidence = build_router_evidence(routing, domains=[MultiAgentDomain.Domain.DISCOVERY])

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

    store_evidence = build_router_evidence(store_routing, domains=[MultiAgentDomain.Domain.TRANSACTION])
    coupon_evidence = build_router_evidence(coupon_routing, domains=[MultiAgentDomain.Domain.SUPPORT])
    location_evidence = build_router_evidence(location_routing, domains=[MultiAgentDomain.Domain.TRANSACTION])

    assert store_evidence["entities"]["store"]["name"] == "판교점"
    assert store_evidence["primary_action"] == "reserve"
    assert coupon_evidence["entities"]["coupon"]["name"] == "생일 쿠폰"
    assert coupon_evidence["primary_action"] == "coupon_use"
    assert location_evidence["entities"]["location"]["name"] == "강남역"
    assert location_evidence["entities"]["location"]["type"] == "station"


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
