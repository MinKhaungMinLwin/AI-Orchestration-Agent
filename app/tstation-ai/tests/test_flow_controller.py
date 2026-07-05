from __future__ import annotations

from services.tstation.policies.flow_controller import (
    evaluate_flow_compatibility,
    resolve_purchase_order_flow,
    transition_current_flow,
)
from services.tstation.policies.response_decision import TemplateName


def _purchase_slots(**overrides: object) -> dict[str, object]:
    slots: dict[str, object] = {
        "goods_no": "G000000309783",
        "product_name": "Ventus S2 AS",
        "tire_size": "225/45R17",
        "ord_qty": 4,
        "pending_intent": "order",
        "goal_type": "place_order",
    }
    slots.update(overrides)
    return slots


def test_purchase_product_quantity_region_resolves_store_candidates_before_schedule() -> None:
    state = resolve_purchase_order_flow(
        intent="quick_order_reservation",
        known_slots=_purchase_slots(region="Pangyo"),
    )

    assert state is not None
    assert state.flow_step == "show_store_candidates"
    assert state.template == TemplateName.LOCATION
    assert state.preferred_tool == "transaction_store_preview_tool"
    assert state.allowed_tools == ("transaction_store_preview_tool",)
    assert "get_store_schedule_tool" in state.forbidden_tools
    assert "quick_order_tool" in state.forbidden_tools


def test_purchase_ambiguous_product_forbids_store_preview_until_variant_selected() -> None:
    # goods_no unresolved (multiple same-spec variants, e.g. 흡음재 Y / 컴포트 N).
    # A region-less transaction_store_preview_tool must stay forbidden so the flow
    # re-offers variant selection instead of dead-ending on "매장을 찾지 못했어요".
    state = resolve_purchase_order_flow(
        intent="quick_order_reservation",
        known_slots={
            "product_name": "벤투스 에어S",
            "tire_model": "벤투스 에어S",
            "tire_size": "245/45R19",
            "ord_qty": 4,
            "pending_intent": "order",
            "goal_type": "place_order",
        },
    )

    assert state is not None
    assert state.flow_step == "resolve_product"
    assert "transaction_store_preview_tool" in state.forbidden_tools
    assert "transaction_store_preview_tool" not in state.allowed_tools


def test_purchase_product_quantity_store_resolves_schedule_before_preorder() -> None:
    state = resolve_purchase_order_flow(
        intent="quick_order_reservation",
        known_slots=_purchase_slots(shop_id="F00721", shop_name="T-Station Pangyo"),
    )

    assert state is not None
    assert state.flow_step == "show_schedule"
    assert state.template == TemplateName.DATE_PICK
    assert state.preferred_tool == "get_store_schedule_tool"
    assert state.allowed_tools == ("get_store_schedule_tool", "get_multi_store_schedule_tool")
    assert "quick_order_tool" in state.forbidden_tools


def test_purchase_schedule_complete_requires_price_before_preorder() -> None:
    state = resolve_purchase_order_flow(
        intent="quick_order_reservation",
        known_slots=_purchase_slots(
            shop_id="F00721",
            shop_name="T-Station Pangyo",
            requested_cal_day="20260705",
            rsv_hour="17",
        ),
    )

    assert state is not None
    assert state.flow_step == "resolve_price"
    assert state.template == TemplateName.QUICK_REPLY
    assert state.preferred_tool == "get_final_price_tool"
    assert state.allowed_tools == ("get_final_price_tool",)
    assert "quick_order_tool" in state.forbidden_tools
    assert "get_store_schedule_tool" in state.forbidden_tools
    assert state.response_shape_key == "reservation_price_lookup"


def test_purchase_complete_slots_with_price_can_build_preorder() -> None:
    state = resolve_purchase_order_flow(
        intent="quick_order_reservation",
        known_slots=_purchase_slots(
            shop_id="F00721",
            shop_name="T-Station Pangyo",
            requested_cal_day="20260705",
            rsv_hour="17",
            payment_amount=420000,
            price_basis="cheapest_final_prc",
        ),
    )

    assert state is not None
    assert state.flow_step == "build_preorder"
    assert state.template == TemplateName.PRE_ORDER
    assert state.preferred_tool is None
    assert "quick_order_tool" in state.forbidden_tools


def test_purchase_execute_after_preorder_allows_only_quick_order_tool() -> None:
    state = resolve_purchase_order_flow(
        intent="quick_order_execute",
        known_slots=_purchase_slots(
            shop_id="F00721",
            shop_name="T-Station Pangyo",
            requested_cal_day="20260705",
            rsv_hour="17",
            payment_amount=420000,
            price_basis="cheapest_final_prc",
        ),
    )

    assert state is not None
    assert state.flow_step == "execute_order"
    assert state.template == TemplateName.ORDER_COMPLETE
    assert state.preferred_tool == "quick_order_tool"
    assert state.allowed_tools == ("quick_order_tool",)


def test_flow_compatibility_pivots_price_question_instead_of_region_slot_fill() -> None:
    decision = evaluate_flow_compatibility(
        active_flow={
            "flow_type": "commerce",
            "status": "active",
            "product": {"goods_no": "G000000309783", "tire_size": "245/45R19", "ord_qty": 4},
            "intent": {"sub_flow_type": "purchase", "pending_intent": "order", "goal_type": "place_order"},
            "current_step": "ask_store",
            "missing_slots": ["shop_id"],
        },
        proposed_slot_patch={"region": "분당"},
        router_evidence={"intent": "price_or_coupon_check", "execution_plan": ["transaction:price_or_coupon_check"]},
    )

    assert decision.action == "pivot"
    assert decision.expected_slot == "store"
    assert decision.proposed_slot == "region"


def test_flow_compatibility_pivots_price_benefit_alias_instead_of_region_slot_fill() -> None:
    decision = evaluate_flow_compatibility(
        active_flow={
            "flow_type": "commerce",
            "status": "active",
            "product": {"goods_no": "G000000309783", "tire_size": "245/45R19", "ord_qty": 4},
            "intent": {"sub_flow_type": "purchase", "pending_intent": "order", "goal_type": "place_order"},
            "current_step": "ask_store",
            "missing_slots": ["shop_id"],
        },
        proposed_slot_patch={"region": "분당"},
        router_evidence={"intent": "price_or_benefit_lookup", "execution_plan": ["transaction:price_or_benefit_lookup"]},
    )

    assert decision.action == "pivot"
    assert decision.current_intent == "price_or_coupon_check"
    assert decision.expected_slot == "store"
    assert decision.proposed_slot == "region"


def test_flow_compatibility_allows_region_when_active_flow_expects_store() -> None:
    decision = evaluate_flow_compatibility(
        active_flow={
            "flow_type": "commerce",
            "status": "active",
            "product": {"goods_no": "G000000309783", "tire_size": "245/45R19", "ord_qty": 4},
            "intent": {"sub_flow_type": "purchase", "pending_intent": "order", "goal_type": "place_order"},
            "current_step": "ask_store",
            "missing_slots": ["shop_id"],
        },
        proposed_slot_patch={"region": "분당"},
        router_evidence={"intent": "quick_order_reservation", "execution_plan": ["transaction:quick_order_reservation"]},
    )

    assert decision.compatible is True
    assert decision.reason == "region_can_resolve_store"


def test_flow_compatibility_allows_region_slot_fill_intent_when_active_flow_expects_store() -> None:
    decision = evaluate_flow_compatibility(
        active_flow={
            "flow_type": "commerce",
            "status": "active",
            "product": {"goods_no": "G000000309783", "tire_size": "245/45R19", "ord_qty": 4},
            "intent": {"sub_flow_type": "purchase", "pending_intent": "order", "goal_type": "place_order"},
            "current_step": "ask_store",
            "missing_slots": ["shop_id"],
        },
        proposed_slot_patch={"region": "분당"},
        router_evidence={
            "intent": "quick_order_reservation_slot_fill_region",
            "execution_plan": ["transaction:quick_order_reservation:slot_fill:region"],
        },
    )

    assert decision.compatible is True
    assert decision.reason == "region_can_resolve_store"


def test_current_turn_store_search_router_location_does_not_keep_stale_selected_store() -> None:
    transition = transition_current_flow(
        user_text="고양시에는 없어?",
        router_evidence={
            "domain": "transaction",
            "intent": "store_service_search",
            "policy_intent": "store_service_search",
            "primary_action": "store_search",
            "execution_plan": ["transaction:store_search"],
            "entities": {"location": {"name": "고양시"}},
        },
        existing_slots={
            "region": "분당",
            "shop_id": "F00071",
            "shop_name": "티스테이션 분당정자점",
            "availability_context": {
                "active_flow_context": {
                    "flow_type": "commerce",
                    "status": "active",
                    "flow_step": "search_ready",
                    "store": {
                        "region": "분당",
                        "place_query": "분당",
                        "shop_id": "F00071",
                        "shop_name": "티스테이션 분당정자점",
                    },
                    "intent": {
                        "sub_flow_type": "store_search",
                        "pending_intent": "store_search",
                        "goal_type": "store_search",
                    },
                }
            },
        },
        extracted_slots={},
    )

    active = transition.flow_transition["active_flow_context"]

    assert transition.flow_transition["reason"] == "current_turn_store_search_flow_state"
    assert active["store"]["region"] == "고양시"
    assert active["store"]["place_query"] == "고양시"
    assert "shop_id" not in active["store"]
    assert "shop_name" not in active["store"]


def test_explicit_resume_anchor_restores_single_dormant_purchase_context_by_slots() -> None:
    transition = transition_current_flow(
        user_text="계속 진행해줘",
        router_evidence={
            "domain": "transaction",
            "intent": "quick_order_reservation",
            "execution_plan": ["transaction:quick_order_reservation"],
        },
        existing_slots={
            "availability_context": {
                "dormant_purchase_context": {
                    "goods_no": "G000000309783",
                    "product_name": "Ventus S2 AS",
                    "tire_size": "225/45R17",
                    "ord_qty": 4,
                    "region": "분당",
                    "pending_intent": "order",
                    "goal_type": "place_order",
                    "flow_step": "build_preorder",
                    "context_state": "dormant",
                }
            }
        },
        extracted_slots={},
        resume_source="explicit_user",
    )

    active = transition.flow_transition["active_flow_context"]

    assert transition.metadata["dormant_resume_status"] == "resumed"
    assert transition.flow_transition["reason"] == "dormant_flow_resume"
    assert active["status"] == "resumed"
    assert active["flow_step"] == "resolve_store"
    assert active["current_step"] == "resolve_store"
    assert active["next_tool"] in {"search_stores_tool", "get_store_list_tool"}
    assert active["store"]["region"] == "분당"


def test_explicit_resume_dedupes_legacy_dormant_purchase_context_and_dormant_flows() -> None:
    dormant_flow = {
        "flow_identity": "commerce:G000000309783:F00721",
        "context": {
            "flow_type": "purchase",
            "status": "dormant",
            "product": {"goods_no": "G000000309783", "tire_size": "225/45R17", "ord_qty": 4},
            "store": {"shop_id": "F00721", "shop_name": "티스테이션 분당점"},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
    }
    transition = transition_current_flow(
        user_text="계속 진행해줘",
        router_evidence={
            "domain": "transaction",
            "intent": "quick_order_reservation",
            "execution_plan": ["transaction:quick_order_reservation"],
        },
        existing_slots={
            "availability_context": {
                "dormant_flows": [dormant_flow],
                "dormant_purchase_context": {
                    "goods_no": "G000000309783",
                    "tire_size": "225/45R17",
                    "ord_qty": 4,
                    "shop_id": "F00721",
                    "shop_name": "티스테이션 분당점",
                    "pending_intent": "order",
                    "goal_type": "place_order",
                    "context_state": "dormant",
                },
            }
        },
        extracted_slots={},
        resume_source="explicit_user",
    )

    assert transition.metadata["dormant_resume_status"] == "resumed"
    assert transition.flow_transition["active_flow_context"]["store"]["shop_id"] == "F00721"


def test_resume_anchor_without_dormant_flow_does_not_create_purchase_context() -> None:
    transition = transition_current_flow(
        user_text="계속 진행해줘",
        router_evidence={
            "domain": "transaction",
            "intent": "quick_order_reservation",
            "execution_plan": ["transaction:quick_order_reservation"],
        },
        existing_slots={"availability_context": {}},
        extracted_slots={},
        resume_source="explicit_user",
    )

    assert transition.metadata["dormant_resume_status"] == "not_attempted"
    assert transition.flow_transition["applied"] is False


def test_store_card_ui_action_resumes_dormant_purchase_context_with_selected_store() -> None:
    transition = transition_current_flow(
        user_text="티스테이션 분당점",
        router_evidence={
            "domain": "transaction",
            "intent": "quick_order_reservation",
            "execution_plan": ["transaction:quick_order_reservation"],
        },
        existing_slots={
            "availability_context": {
                "dormant_purchase_context": {
                    "goods_no": "G000000309783",
                    "product_name": "Ventus S2 AS",
                    "tire_size": "225/45R17",
                    "ord_qty": 4,
                    "pending_intent": "order",
                    "goal_type": "place_order",
                    "context_state": "dormant",
                }
            }
        },
        extracted_slots={},
        ui_action={
            "action_type": "select_store",
            "entity_id": "F00721",
            "entity_label": "티스테이션 분당점",
            "slots": {"shop_id": "F00721", "shop_name": "티스테이션 분당점", "region": "분당"},
        },
        resume_source="ui_action:select_store",
    )

    active = transition.flow_transition["active_flow_context"]

    assert transition.flow_transition["reason"] == "selected_store_flow_state"
    assert active["status"] == "resumed"
    assert active["product"]["goods_no"] == "G000000309783"
    assert active["store"]["shop_id"] == "F00721"
    assert active["flow_step"] == "store_selected"
