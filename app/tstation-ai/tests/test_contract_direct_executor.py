from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from schemas.tstation.slots import ConversationSlots
from services.tstation.executors.contract_required_tool_executor import (
    _recover_contract_required_tool,
    continue_active_flow_after_tool,
    contract_required_tool_start_event,
)
from services.tstation.policies.contract_direct_executor import evaluate_contract_direct_path
from services.tstation.policies.turn_contract import TurnContract
from services.tstation.policies.reservation_history_policy import (
    build_reservation_status_lookup_event,
    build_reservation_store_info_event,
    build_reservation_store_not_found_event,
    select_reservation_store_row,
)
from services.tstation.policies.support_response_policy import (
    build_general_cancel_fee_policy_event,
    build_general_card_cancel_timing_policy_event,
    build_support_faq_policy_event,
)


def test_contract_executor_and_base_agent_import_without_chat_module() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys;"
                "import services.tstation.executors.contract_required_tool_executor;"
                "raise SystemExit(1 if 'services.tstation.chat' in sys.modules else 0)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    base_agent_source = Path("app/tstation-ai/services/tstation/agents/base_agent.py").read_text(encoding="utf-8")
    assert "from services.tstation.chat import" not in base_agent_source


def test_reservation_history_policy_builds_store_info_without_chat_module() -> None:
    result = {
        "status": "success",
        "data": {
            "items": [
                {
                    "ord_no": "O123456789",
                    "shop_nm": "티스테이션 강남점",
                    "tel_no": "0212345678",
                    "road_addr_base": "서울 강남구",
                    "vst_rsv_dtime": "2026-07-04 10:00",
                }
            ]
        },
    }

    row, reason = select_reservation_store_row("예약한 매장 전화번호 알려줘", result)
    assert row is not None
    assert reason == "single_reservation"

    event = build_reservation_store_info_event(row, match_reason=reason)
    assert event["source_domain"] == "transaction"
    assert event["data"]["metadata"]["responseShapeKey"] == "reservation_store_info_lookup"
    assert event["data"]["metadata"]["telNo"] == "02-1234-5678"


def test_reservation_history_policy_builds_status_and_not_found_events() -> None:
    status_event = build_reservation_status_lookup_event({"status": "success", "data": {"items": []}})
    not_found_event = build_reservation_store_not_found_event("ambiguous")

    assert status_event["data"]["metadata"]["responseShapeKey"] == "reservation_status_lookup"
    assert status_event["data"]["metadata"]["reservationCount"] == 0
    assert not_found_event["data"]["metadata"]["matchReason"] == "ambiguous"


def test_support_policy_builders_do_not_depend_on_chat_module() -> None:
    cancel_event = build_general_cancel_fee_policy_event("예약 취소하면 비용 발생해?")
    card_event = build_general_card_cancel_timing_policy_event("카드 취소 반영 언제 돼?")
    faq_event = build_support_faq_policy_event("tire_condition_photo_policy", "사진 첨부해서 봐줘")

    assert cancel_event["source_domain"] == "transaction"
    assert cancel_event["data"]["metadata"]["responseShapeKey"] == "general_cancel_fee_policy_summary"
    assert card_event["source_domain"] == "support"
    assert card_event["data"]["metadata"]["responseShapeKey"] == "general_card_cancel_timing_policy"
    assert faq_event is not None
    assert faq_event["data"]["metadata"]["responseShapeKey"] == "tire_condition_photo_policy"


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


def test_contract_direct_recommendation_defaults_rcmd_type_for_patch_only_input(monkeypatch) -> None:
    from services.tstation import template_mapper
    from services.tstation.agents.b_discovery_agent import tools as discovery_tools
    from services.tstation.executors import contract_required_tool_executor as executor

    calls: list[dict] = []

    def fake_tool_invoke(tool, tool_input: dict):
        assert tool.name == "get_products_recommendations_tool"
        calls.append(dict(tool_input))
        return {"status": "success", "data": {"items": [{"goods_no": "G1", "goods_nm": "SUV Tire"}]}}

    def fake_template(tool_data_list: list[dict], assistant_text: str):
        assert [entry["tool"] for entry in tool_data_list] == ["get_products_recommendations_tool"]
        assert tool_data_list[0]["args"]["rcmd_type"] == "tstation"
        return {
            "type": "data",
            "template": "product",
            "data": {"assistantResponse": assistant_text, "products": []},
        }

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(type(discovery_tools.get_products_recommendations_tool), "invoke", fake_tool_invoke)
    monkeypatch.setattr(template_mapper, "try_build_template", fake_template)
    monkeypatch.setattr(executor.asyncio, "to_thread", fake_to_thread)

    contract = TurnContract(
        domain="discovery",
        intent="product_recommendation",
        allowed_tools=("get_products_recommendations_tool",),
        preferred_tool="get_products_recommendations_tool",
        tool_args_patch={"vehicle_type": "suv", "tire_size": "245/45R19"},
        response_decision={"template": "product"},
    )

    recovery = asyncio.run(
        _recover_contract_required_tool(
            turn_contract=contract,
            user_text="suv 용으로 추천",
            merged_slots=None,
            blocked_fast_path_source="contract_direct_executor:product_recommendation",
            member_no="M123",
        )
    )

    assert recovery is not None
    assert recovery["tool_name"] == "get_products_recommendations_tool"
    assert calls == [{"vehicle_type": "suv", "tire_size": "245/45R19", "rcmd_type": "tstation"}]
    assert recovery["tool_input"] == calls[0]
    assert recovery["event"]["template"] == "product"


def test_contract_direct_recommendation_preserves_explicit_rcmd_type(monkeypatch) -> None:
    from services.tstation import template_mapper
    from services.tstation.agents.b_discovery_agent import tools as discovery_tools
    from services.tstation.executors import contract_required_tool_executor as executor

    calls: list[dict] = []

    def fake_tool_invoke(tool, tool_input: dict):
        assert tool.name == "get_products_recommendations_tool"
        calls.append(dict(tool_input))
        return {"status": "success", "data": {"items": [{"goods_no": "G2", "goods_nm": "Quiet Tire"}]}}

    def fake_template(tool_data_list: list[dict], assistant_text: str):
        assert tool_data_list[0]["args"]["rcmd_type"] == "low_vibration"
        return {
            "type": "data",
            "template": "product",
            "data": {"assistantResponse": assistant_text, "products": []},
        }

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(type(discovery_tools.get_products_recommendations_tool), "invoke", fake_tool_invoke)
    monkeypatch.setattr(template_mapper, "try_build_template", fake_template)
    monkeypatch.setattr(executor.asyncio, "to_thread", fake_to_thread)

    contract = TurnContract(
        domain="discovery",
        intent="product_recommendation",
        allowed_tools=("get_products_recommendations_tool",),
        preferred_tool="get_products_recommendations_tool",
        tool_args_patch={"vehicle_type": "suv", "tire_size": "245/45R19", "rcmd_type": "low_vibration"},
        response_decision={"template": "product"},
    )

    recovery = asyncio.run(
        _recover_contract_required_tool(
            turn_contract=contract,
            user_text="suv 용으로 정숙성 좋은 타이어 추천",
            merged_slots=None,
            blocked_fast_path_source="contract_direct_executor:product_recommendation",
            member_no="M123",
        )
    )

    assert recovery is not None
    assert calls == [{"vehicle_type": "suv", "tire_size": "245/45R19", "rcmd_type": "low_vibration"}]


def test_contract_recovery_runs_active_flow_transaction_next_tool_from_discovery_contract(monkeypatch) -> None:
    from services.tstation import template_mapper
    from services.tstation.agents.c_transaction_agent import tools as transaction_tools
    from services.tstation.executors import contract_required_tool_executor as executor

    captured_input: dict = {}

    def fake_store_list_invoke(tool_input: dict):
        captured_input.update(tool_input)
        return {
            "status": "success",
            "data": {
                "stores": [
                    {
                        "shop_id": "S001",
                        "shop_nm": "티스테이션 분당정자점",
                        "addr": "성남시 분당구",
                    }
                ]
            },
        }

    def fake_template(tool_data_list: list[dict], assistant_text: str):
        assert [entry["tool"] for entry in tool_data_list] == ["get_store_list_tool"]
        assert assistant_text == "요청하신 정보를 확인했어요."
        return {
            "type": "data",
            "template": "location",
            "data": {
                "assistantResponse": "매장을 확인했어요.",
                "stores": [{"nameAddress": "티스테이션 분당정자점"}],
                "metadata": [{"shopId": "S001"}],
            },
        }

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(transaction_tools, "get_store_list_tool", SimpleNamespace(invoke=fake_store_list_invoke))
    monkeypatch.setattr(template_mapper, "try_build_template", fake_template)
    monkeypatch.setattr(executor.asyncio, "to_thread", fake_to_thread)

    active_flow_context = {
        "flow_type": "commerce",
        "status": "active",
        "flow_step": "product_selected",
        "product": {
            "goods_no": "G000000310126",
            "product_name": "벤투스 S2 AS",
            "tire_size": "245/45R19",
            "ord_qty": 4,
        },
        "store": {"shop_name": "분당정자점"},
        "intent": {"sub_flow_type": "purchase", "pending_intent": "order", "goal_type": "place_order"},
        "target_action": "quick_order_tool",
        "current_step": "resolve_store",
        "missing_slots": ["shop_id"],
        "next_tool": "get_store_list_tool",
        "tool_args_patch": {"limit": 10, "store_nm": "분당정자점"},
        "allowed_tools": ["search_stores_tool", "get_store_list_tool"],
        "progress_source": "flow_state_evaluator",
    }
    contract = TurnContract(
        domain="discovery",
        intent="resolve_product_for_purchase_size_selection",
        sub_intent="reservation",
        known_slots={
            "goods_no": "G000000310126",
            "tire_size": "245/45R19",
            "ord_qty": 4,
            "shop_name": "분당정자점",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
        allowed_tools=("transaction_store_preview_tool",),
        forbidden_tools=("quick_order_tool", "get_final_price_tool", "get_logistics_inventory_tool"),
        preferred_tool="transaction_store_preview_tool",
        response_decision={"template": "location", "metadata": {"response_shape_key": "reservation_store_candidates"}},
        action_mode="purchase_continuation",
        context_state="active",
    )

    recovery = asyncio.run(
        _recover_contract_required_tool(
            turn_contract=contract,
            user_text="티스테이션 분당정자점에서 벤투스s2 as 4개 예약해줘",
            merged_slots=ConversationSlots(availability_context={"active_flow_context": active_flow_context}),
            blocked_fast_path_source="contract_required_tool_executor",
            member_no="M123",
        )
    )

    assert recovery is not None
    assert recovery["tool_name"] == "get_store_list_tool"
    assert recovery["tool_input"] == {"limit": 10, "store_nm": "분당정자점"}
    assert captured_input == {"limit": 10, "store_nm": "분당정자점"}
    assert recovery["event"]["source_domain"] == "transaction"
    assert recovery["event"]["tool_input_source"] == "flow_state_progress"


def test_contract_recovery_blocks_active_flow_next_tool_when_contract_forbids_it(monkeypatch) -> None:
    from services.tstation.agents.c_transaction_agent import tools as transaction_tools

    def fail_store_list_invoke(tool_input: dict):
        raise AssertionError(f"forbidden tool should not run: {tool_input}")

    monkeypatch.setattr(transaction_tools, "get_store_list_tool", SimpleNamespace(invoke=fail_store_list_invoke))

    active_flow_context = {
        "flow_type": "commerce",
        "status": "active",
        "flow_step": "product_selected",
        "intent": {"sub_flow_type": "purchase", "pending_intent": "order", "goal_type": "place_order"},
        "current_step": "resolve_store",
        "next_tool": "get_store_list_tool",
        "tool_args_patch": {"limit": 10, "store_nm": "분당정자점"},
        "allowed_tools": ["get_store_list_tool"],
    }
    contract = TurnContract(
        domain="discovery",
        intent="resolve_product_for_purchase_size_selection",
        allowed_tools=("transaction_store_preview_tool",),
        forbidden_tools=("get_store_list_tool",),
        preferred_tool="transaction_store_preview_tool",
        response_decision={"template": "location", "metadata": {"response_shape_key": "reservation_store_candidates"}},
        action_mode="purchase_continuation",
        context_state="active",
    )

    recovery = asyncio.run(
        _recover_contract_required_tool(
            turn_contract=contract,
            user_text="티스테이션 분당정자점에서 벤투스s2 as 4개 예약해줘",
            merged_slots=ConversationSlots(availability_context={"active_flow_context": active_flow_context}),
            blocked_fast_path_source="contract_required_tool_executor",
            member_no="M123",
        )
    )

    assert recovery is None


def test_continue_active_flow_after_search_product_runs_next_flow_tool(monkeypatch) -> None:
    from services.tstation import template_mapper
    from services.tstation.agents.c_transaction_agent import tools as transaction_tools
    from services.tstation.executors import contract_required_tool_executor as executor

    captured_input: dict = {}

    def fake_store_list_invoke(tool_input: dict):
        captured_input.update(tool_input)
        return {
            "status": "success",
            "data": {
                "stores": [
                    {
                        "shop_id": "S001",
                        "shop_nm": "티스테이션 분당정자점",
                        "addr": "성남시 분당구",
                    }
                ]
            },
        }

    def fake_template(tool_data_list: list[dict], assistant_text: str):
        assert [entry["tool"] for entry in tool_data_list] == ["get_store_list_tool"]
        return {
            "type": "data",
            "template": "location",
            "data": {
                "assistantResponse": assistant_text,
                "stores": [{"nameAddress": "티스테이션 분당정자점"}],
                "metadata": [{"shopId": "S001"}],
            },
        }

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(transaction_tools, "get_store_list_tool", SimpleNamespace(invoke=fake_store_list_invoke))
    monkeypatch.setattr(template_mapper, "try_build_template", fake_template)
    monkeypatch.setattr(executor.asyncio, "to_thread", fake_to_thread)

    active_flow_context = {
        "flow_type": "commerce",
        "status": "active",
        "flow_step": "product_selected",
        "product": {
            "goods_no": "G000000310126",
            "product_name": "벤투스 S2 AS",
            "tire_size": "245/45R19",
            "ord_qty": 4,
        },
        "store": {"shop_name": "분당정자점"},
        "intent": {"sub_flow_type": "purchase", "pending_intent": "order", "goal_type": "place_order"},
        "current_step": "resolve_store",
        "missing_slots": ["shop_id"],
        "next_tool": "get_store_list_tool",
        "tool_args_patch": {"limit": 10, "store_nm": "분당정자점"},
        "allowed_tools": ["search_stores_tool", "get_store_list_tool"],
    }
    contract = TurnContract(
        domain="discovery",
        intent="resolve_product_for_purchase_size_selection",
        allowed_tools=("transaction_store_preview_tool",),
        preferred_tool="transaction_store_preview_tool",
        response_decision={"template": "location", "metadata": {"response_shape_key": "reservation_store_candidates"}},
        action_mode="purchase_continuation",
        context_state="active",
    )

    recovery = asyncio.run(
        continue_active_flow_after_tool(
            turn_contract=contract,
            user_text="티스테이션 분당정자점에서 벤투스s2 as 4개 예약해줘",
            merged_slots=ConversationSlots(availability_context={"active_flow_context": active_flow_context}),
            last_tool_name="search_product_tool",
            blocked_fast_path_source="post_tool_flow_progress:search_product_tool",
            member_no="M123",
        )
    )

    assert recovery is not None
    assert recovery["tool_name"] == "get_store_list_tool"
    assert recovery["tool_input"] == {"limit": 10, "store_nm": "분당정자점"}
    assert captured_input == {"limit": 10, "store_nm": "분당정자점"}
    assert recovery["event"]["tool_input_source"] == "flow_state_progress"


def test_continue_active_flow_after_tool_skips_same_tool(monkeypatch) -> None:
    from services.tstation.agents.c_transaction_agent import tools as transaction_tools

    def fail_store_list_invoke(tool_input: dict):
        raise AssertionError(f"same tool should not be repeated: {tool_input}")

    monkeypatch.setattr(transaction_tools, "get_store_list_tool", SimpleNamespace(invoke=fail_store_list_invoke))

    active_flow_context = {
        "flow_type": "commerce",
        "status": "active",
        "flow_step": "product_selected",
        "intent": {"sub_flow_type": "purchase", "pending_intent": "order", "goal_type": "place_order"},
        "current_step": "resolve_store",
        "next_tool": "get_store_list_tool",
        "tool_args_patch": {"limit": 10, "store_nm": "분당정자점"},
        "allowed_tools": ["get_store_list_tool"],
    }

    recovery = asyncio.run(
        continue_active_flow_after_tool(
            turn_contract=TurnContract(
                domain="discovery",
                intent="resolve_product_for_purchase_size_selection",
                allowed_tools=("transaction_store_preview_tool",),
                preferred_tool="transaction_store_preview_tool",
                response_decision={
                    "template": "location",
                    "metadata": {"response_shape_key": "reservation_store_candidates"},
                },
            ),
            user_text="분당정자점에서 예약해줘",
            merged_slots=ConversationSlots(availability_context={"active_flow_context": active_flow_context}),
            last_tool_name="get_store_list_tool",
        )
    )

    assert recovery is None


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
