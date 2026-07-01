from __future__ import annotations

import asyncio

from services.tstation.executors.contract_required_tool_executor import (
    _recover_contract_required_tool,
    contract_required_tool_start_event,
)
from services.tstation.policies.contract_direct_executor import evaluate_contract_direct_path
from services.tstation.policies.turn_contract import TurnContract


def _evidence(
    *,
    primary_action: str = "recommend",
    confidence: float = 0.9,
    entities: dict | None = None,
    domain: str = "discovery",
) -> dict:
    return {
        "domain": domain,
        "primary_action": primary_action,
        "confidence": confidence,
        "entities": entities or {},
    }


def test_direct_path_allows_registered_vehicle_recommendation_contract() -> None:
    contract = TurnContract(
        domain="discovery",
        intent="product_recommendation",
        sub_intent="vehicle_resolved_recommendation",
        known_slots={"named_registered_vehicle_anchor": "제타"},
        allowed_tools=("get_my_cars_tool", "get_products_recommendations_tool"),
        preferred_tool="get_my_cars_tool",
        tool_args_patch={"rcmd_type": "low_vibration"},
        response_decision={"template": "product", "metadata": {"response_shape_key": "vehicle_resolved_recommendation"}},
    )

    decision = evaluate_contract_direct_path(
        turn_contract=contract,
        router_evidence=_evidence(
            entities={"registered_vehicle": {"anchor": "제타", "confidence": 0.9}},
        ),
        user_text="내가 등록해놓은 제타에 맞는 정숙성 좋은 타이어 추천해줘",
    )

    assert decision.eligible is True
    assert decision.reason == "registered_vehicle_recommendation"
    assert decision.metadata()["domain_agent_llm_skipped"] is True


def test_direct_path_blocks_complex_comparison_and_forbidden_tool() -> None:
    comparison_contract = TurnContract(
        domain="discovery",
        intent="product_recommendation",
        allowed_tools=("get_products_recommendations_tool",),
        preferred_tool="get_products_recommendations_tool",
        known_slots={"tire_size": "225/45R17"},
        response_decision={"template": "product"},
    )
    comparison = evaluate_contract_direct_path(
        turn_contract=comparison_contract,
        router_evidence=_evidence(primary_action="recommend"),
        user_text="두 제품 장단점 자세히 비교해줘",
    )

    conflict_contract = TurnContract(
        domain="transaction",
        intent="store_search",
        known_slots={"place_query": "강남역"},
        allowed_tools=("search_stores_tool",),
        forbidden_tools=("search_stores_tool",),
        preferred_tool="search_stores_tool",
        response_decision={"template": "location"},
    )
    conflict = evaluate_contract_direct_path(
        turn_contract=conflict_contract,
        router_evidence=_evidence(primary_action="search", domain="transaction"),
        user_text="강남역 근처 장착점 찾아줘",
    )

    assert comparison.eligible is False
    assert comparison.fallback_reason == "comparison_requires_llm"
    assert conflict.eligible is False
    assert conflict.fallback_reason == "contract_tool_conflict"


def test_direct_path_allows_location_store_search_and_coupon_lookup() -> None:
    location_contract = TurnContract(
        domain="transaction",
        intent="store_search",
        known_slots={"place_query": "강남역", "location_name": "강남역"},
        allowed_tools=("search_stores_tool",),
        preferred_tool="search_stores_tool",
        tool_args_patch={"place_query": "강남역", "limit": 10},
        response_decision={"template": "location"},
    )
    coupon_contract = TurnContract(
        domain="transaction",
        intent="price_or_coupon_check",
        known_slots={"coupon_name_candidate": "생일 쿠폰"},
        allowed_tools=("get_my_coupons_tool",),
        preferred_tool="get_my_coupons_tool",
        response_decision={"template": "voucher"},
    )

    location = evaluate_contract_direct_path(
        turn_contract=location_contract,
        router_evidence=_evidence(primary_action="search", domain="transaction"),
        user_text="강남역 근처 장착점 찾아줘",
    )
    coupon = evaluate_contract_direct_path(
        turn_contract=coupon_contract,
        router_evidence=_evidence(primary_action="use_coupon", domain="transaction"),
        user_text="생일 쿠폰 쓸 수 있어?",
    )

    assert location.eligible is True
    assert location.reason == "store_search"
    assert location.template == "location"
    assert coupon.eligible is True
    assert coupon.reason == "coupon_lookup"
    assert coupon.template == "voucher"


def test_registered_vehicle_direct_executor_runs_car_lookup_then_recommendation(monkeypatch) -> None:
    from services.tstation.agents.b_discovery_agent import tools as discovery_tools
    from services.tstation import template_mapper
    from services.tstation.executors import contract_required_tool_executor as executor

    calls: list[tuple[str, dict]] = []

    def fake_tool_invoke(tool, tool_input: dict):
        if tool.name == "get_my_cars_tool":
            calls.append(("get_my_cars_tool", dict(tool_input)))
            return {
                "status": "success",
                "data": {
                    "items": [
                        {
                            "car_mdl_nm": "폭스바겐 제타",
                            "tire_size_fr": "2254517",
                            "car_lnc_cd": "W036270",
                            "vehicle_type": "passenger",
                        }
                    ]
                },
            }
        if tool.name == "get_products_recommendations_tool":
            calls.append(("get_products_recommendations_tool", dict(tool_input)))
            return {"status": "success", "data": {"items": [{"goods_no": "G1", "goods_nm": "Quiet Tire"}]}}
        raise AssertionError(f"unexpected tool: {tool.name}")

    def fake_template(tool_data_list: list[dict], assistant_text: str):
        assert [entry["tool"] for entry in tool_data_list] == [
            "get_my_cars_tool",
            "get_products_recommendations_tool",
        ]
        return {
            "type": "data",
            "template": "product",
            "data": {"assistantResponse": assistant_text, "products": []},
        }

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(type(discovery_tools.get_my_cars_tool), "invoke", fake_tool_invoke)
    monkeypatch.setattr(template_mapper, "try_build_template", fake_template)
    monkeypatch.setattr(executor.asyncio, "to_thread", fake_to_thread)

    contract = TurnContract(
        domain="discovery",
        intent="product_recommendation",
        sub_intent="vehicle_resolved_recommendation",
        known_slots={"named_registered_vehicle_anchor": "제타"},
        allowed_tools=("get_my_cars_tool", "get_products_recommendations_tool"),
        preferred_tool="get_my_cars_tool",
        tool_args_patch={"rcmd_type": "low_vibration"},
        response_decision={"template": "product", "metadata": {"response_shape_key": "vehicle_resolved_recommendation"}},
    )

    recovery = asyncio.run(
        _recover_contract_required_tool(
            turn_contract=contract,
            user_text="내가 등록해놓은 제타에 맞는 정숙성 좋은 타이어 추천해줘",
            merged_slots=None,
            blocked_fast_path_source="contract_direct_executor:registered_vehicle_recommendation",
            member_no="M123",
        )
    )

    assert recovery is not None
    assert recovery["tool_name"] == "get_products_recommendations_tool"
    assert calls[0] == ("get_my_cars_tool", {"mbr_no": "M123"})
    assert calls[1][0] == "get_products_recommendations_tool"
    assert calls[1][1]["tire_size"] == "225/45R17"
    assert calls[1][1]["vehicle_type"] == "passenger"
    assert calls[1][1]["rcmd_type"] == "low_vibration"
    assert recovery["event"]["template"] == "product"


def test_contract_direct_executor_previews_tool_start_status_before_recovery() -> None:
    contract = TurnContract(
        domain="discovery",
        intent="product_recommendation",
        sub_intent="vehicle_resolved_recommendation",
        known_slots={"named_registered_vehicle_anchor": "제타"},
        allowed_tools=("get_my_cars_tool", "get_products_recommendations_tool"),
        preferred_tool="get_my_cars_tool",
        tool_args_patch={"rcmd_type": "low_vibration"},
        response_decision={"template": "product", "metadata": {"response_shape_key": "vehicle_resolved_recommendation"}},
    )

    event = contract_required_tool_start_event(
        turn_contract=contract,
        user_text="내가 등록해놓은 제타에 맞는 정숙성 좋은 타이어 추천해줘",
        merged_slots=None,
        blocked_fast_path_source="contract_direct_executor:registered_vehicle_recommendation",
        member_no="M123",
    )

    assert event == {
        "type": "status",
        "status": "tool_start",
        "tool": "get_my_cars_tool",
        "display_name": "등록 차량 조회 중...",
        "source_domain": "discovery",
    }


def test_registered_vehicle_direct_executor_falls_back_to_general_recommendation_when_no_match(monkeypatch) -> None:
    from services.tstation.agents.b_discovery_agent import tools as discovery_tools
    from services.tstation import template_mapper
    from services.tstation.executors import contract_required_tool_executor as executor

    calls: list[tuple[str, dict]] = []

    def fake_tool_invoke(tool, tool_input: dict):
        if tool.name == "get_my_cars_tool":
            calls.append(("get_my_cars_tool", dict(tool_input)))
            return {
                "status": "success",
                "data": {
                    "items": [
                        {
                            "car_mdl_nm": "폭스바겐 제타",
                            "tire_size_fr": "2254517",
                            "car_lnc_cd": "W036270",
                            "vehicle_type": "passenger",
                        }
                    ]
                },
            }
        if tool.name == "get_products_recommendations_tool":
            calls.append(("get_products_recommendations_tool", dict(tool_input)))
            return {"status": "success", "data": {"items": [{"goods_no": "G2", "goods_nm": "Popular Tire"}]}}
        raise AssertionError(f"unexpected tool: {tool.name}")

    def fake_template(tool_data_list: list[dict], assistant_text: str):
        assert [entry["tool"] for entry in tool_data_list] == [
            "get_my_cars_tool",
            "get_products_recommendations_tool",
        ]
        return {
            "type": "data",
            "template": "product",
            "data": {"assistantResponse": assistant_text, "products": []},
        }

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(type(discovery_tools.get_my_cars_tool), "invoke", fake_tool_invoke)
    monkeypatch.setattr(template_mapper, "try_build_template", fake_template)
    monkeypatch.setattr(executor.asyncio, "to_thread", fake_to_thread)

    contract = TurnContract(
        domain="discovery",
        intent="product_recommendation",
        sub_intent="vehicle_resolved_recommendation",
        known_slots={"named_registered_vehicle_anchor": "아반떼"},
        allowed_tools=("get_my_cars_tool", "get_products_recommendations_tool"),
        preferred_tool="get_my_cars_tool",
        tool_args_patch={"rcmd_type": "tstation"},
        response_decision={"template": "product", "metadata": {"response_shape_key": "vehicle_resolved_recommendation"}},
    )

    recovery = asyncio.run(
        _recover_contract_required_tool(
            turn_contract=contract,
            user_text="아반떼에 제일 인기 있는 타이어가 뭐야",
            merged_slots=None,
            blocked_fast_path_source="contract_direct_executor:registered_vehicle_recommendation",
            member_no="M123",
        )
    )

    assert recovery is not None
    assert recovery["tool_name"] == "get_products_recommendations_tool"
    assert calls[0] == ("get_my_cars_tool", {"mbr_no": "M123"})
    assert calls[1] == ("get_products_recommendations_tool", {"rcmd_type": "tstation"})
    assert "tire_size" not in calls[1][1]
    assert "car_lnc_cd" not in calls[1][1]
    assert recovery["event"]["template"] == "product"
    assert recovery["event"]["recovery_reason"] == "registered_vehicle_no_match_general_recommendation"
