from __future__ import annotations

from datetime import datetime, timezone

from services.tstation.policies.flow_state import (
    commit_flow_state,
    commit_purchase_flow_state,
    evaluate_flow_progress,
    FlowState,
    flow_state_from_slot_values,
    prune_dormant_flows,
    resume_dormant_flow,
    flow_state_values_from_slot_values,
    selected_store_slots_from_active_flow_context,
    store_candidate_selection_patch,
    store_candidates_flow_delta,
    upsert_dormant_flow,
)
from schemas.tstation.slots import ConversationSlots
from services.tstation.policies.flow_controller import resolve_purchase_order_flow, transition_current_flow


def test_flow_state_values_reads_active_context_before_legacy_pending_context() -> None:
    values = flow_state_values_from_slot_values(
        {
            "availability_context": {
                "active_flow_context": {
                    "flow_type": "purchase",
                    "product": {"goods_no": "G-ACTIVE", "tire_size": "245/45R19", "ord_qty": 2},
                    "store": {"region": "고양시"},
                    "intent": {"pending_intent": "order", "goal_type": "place_order"},
                },
                "pending_order_context": {
                    "goods_no": "G-LEGACY",
                    "tire_size": "225/45R17",
                    "ord_qty": 4,
                    "region": "분당",
                    "pending_intent": "order",
                    "goal_type": "place_order",
                },
            }
        },
        source="test",
    )

    assert values["goods_no"] == "G-ACTIVE"
    assert values["tire_size"] == "245/45R19"
    assert values["ord_qty"] == 2
    assert values["region"] == "고양시"
    assert values["pending_intent"] == "order"


def test_flow_state_values_applies_current_turn_region_over_legacy_context() -> None:
    values = flow_state_values_from_slot_values(
        {
            "region": "고양시",
            "availability_context": {
                "pending_order_context": {
                    "goods_no": "G-LEGACY",
                    "tire_size": "225/45R17",
                    "ord_qty": 4,
                    "region": "분당",
                    "shop_id": "S1",
                    "requested_cal_day": "20260710",
                    "rsv_hour": "15",
                    "pending_intent": "order",
                    "goal_type": "place_order",
                }
            },
        },
        source="test",
    )

    assert values["region"] == "고양시"
    assert values["goods_no"] == "G-LEGACY"
    assert values["ord_qty"] == 4
    assert "shop_id" not in values
    assert "requested_cal_day" not in values
    assert "rsv_hour" not in values


def test_flow_state_values_preserves_active_stock_sub_flow_on_current_turn_patch() -> None:
    slot_values = {
        "region": "고양시",
        "availability_context": {
            "active_flow_context": {
                "flow_type": "commerce",
                "flow_step": "ask_store",
                "product": {"goods_no": "G-STOCK", "tire_size": "245/45R19", "ord_qty": 2},
                "intent": {
                    "sub_flow_type": "stock",
                    "pending_intent": "stock",
                    "goal_type": "store_with_stock",
                    "stock_check_mode": "inventory_only",
                },
            },
        },
    }

    state = flow_state_from_slot_values(slot_values, source="test")
    values = state.to_pending_order_context()
    progress = evaluate_flow_progress(state)

    assert values["flow_type"] == "commerce"
    assert values["sub_flow_type"] == "stock"
    assert values["pending_intent"] == "stock"
    assert values["goal_type"] == "store_with_stock"
    assert values["stock_check_mode"] == "inventory_only"
    assert values["region"] == "고양시"
    assert progress["target_action"] == "get_store_inventory_tool"
    assert progress["next_tool"] == "get_store_list_tool"
    assert progress["tool_args_patch"] == {"limit": 10, "region_code": "고양시"}


def test_purchase_preview_store_selection_progresses_to_schedule_without_relisting() -> None:
    location_event = {
        "template": "location",
        "data": {
            "isBookingFlow": True,
            "contractMetadata": {"response_shape_key": "reservation_store_candidates"},
            "stores": [{"name": "T-Station Hannam", "nameAddress": "T-Station Hannam"}],
            "metadata": [
                {
                    "sourceTool": "transaction_store_preview_tool",
                    "shopId": "F00777",
                    "shopName": "T-Station Hannam",
                    "goodsNo": "G000000309783",
                    "productName": "Ventus S2 AS",
                    "tireSize": "245/45R19",
                    "ordQty": 2,
                }
            ],
        },
    }

    candidate_delta = store_candidates_flow_delta(event=location_event)

    assert candidate_delta["flow_type"] == "purchase"
    assert candidate_delta["pending_intent"] == "order"
    assert candidate_delta["goal_type"] == "place_order"

    selected_patch = store_candidate_selection_patch(
        active_flow_context=candidate_delta,
        user_text="T-Station Hannam",
    )

    assert selected_patch["_flow_type"] == "purchase"
    assert selected_patch["flow_step"] == "store_selected"
    assert selected_patch["shop_id"] == "F00777"
    assert selected_patch["goods_no"] == "G000000309783"
    assert selected_patch["tire_size"] == "245/45R19"
    assert selected_patch["ord_qty"] == 2
    assert selected_patch["pending_intent"] == "order"
    assert selected_patch["goal_type"] == "place_order"

    selected_slots = selected_store_slots_from_active_flow_context(
        commit_flow_state(
            candidate_delta,
            {key: value for key, value in selected_patch.items() if not key.startswith("_")},
            source="location_selection:purchase",
            flow_type="purchase",
            flow_step="store_selected",
            status="resumed",
        ).state.to_active_flow_context(),
        allowed_flow_types=frozenset({"purchase"}),
    )
    next_state = resolve_purchase_order_flow(intent="quick_order_reservation", known_slots=selected_slots)

    assert next_state is not None
    assert next_state.flow_step == "show_schedule"
    assert next_state.preferred_tool == "get_store_schedule_tool"
    assert next_state.allowed_tools == ("get_store_schedule_tool", "get_multi_store_schedule_tool")


def test_purchase_store_ui_action_preserves_product_and_quantity_for_schedule() -> None:
    transition = transition_current_flow(
        user_text="T-Station Hannam",
        router_evidence={
            "domain": "transaction",
            "intent": "quick_order_reservation",
            "execution_plan": ["transaction:quick_order_reservation:slot_fill:store"],
            "is_slot_fill": True,
            "filled_slot": "store",
        },
        existing_slots=ConversationSlots(
            availability_context={
                "active_flow_context": {
                    "flow_type": "purchase",
                    "status": "active",
                    "flow_step": "quantity_selected",
                    "product": {
                        "goods_no": "G000000309783",
                        "product_name": "Ventus S2 AS",
                        "tire_size": "245/45R19",
                        "ord_qty": 2,
                    },
                    "intent": {"pending_intent": "order", "goal_type": "place_order"},
                }
            }
        ),
        extracted_slots=ConversationSlots(),
        ui_action={
            "action_type": "select_store",
            "selection_source": "location_template",
            "entity_id": "F00777",
            "entity_label": "T-Station Hannam",
            "slots": {"shopId": "F00777", "shopName": "T-Station Hannam"},
        },
        resume_source="validated_ui_action_slot_fill:store",
    )

    assert transition.metadata["selected_store_resolved"] is True
    assert transition.flow_transition["reason"] == "selected_store_flow_state"
    active_context = transition.flow_transition["active_flow_context"]
    assert active_context["flow_step"] == "store_selected"
    assert active_context["product"]["goods_no"] == "G000000309783"
    assert active_context["product"]["ord_qty"] == 2
    assert active_context["store"]["shop_id"] == "F00777"

    selected_slots = selected_store_slots_from_active_flow_context(
        active_context,
        allowed_flow_types=frozenset({"purchase"}),
    )
    next_state = resolve_purchase_order_flow(intent="quick_order_reservation", known_slots=selected_slots)

    assert next_state is not None
    assert next_state.flow_step == "show_schedule"
    assert "store" not in next_state.missing_slots


def test_transition_current_flow_resumes_dormant_purchase_on_explicit_order_anchor() -> None:
    dormant_purchase = commit_flow_state(
        None,
        {
            "goods_no": "G000000320152",
            "product_name": "Dynapro HP3",
            "tire_size": "245/45R19",
            "ord_qty": 2,
            "shop_id": "F00071",
            "shop_name": "티스테이션 분당정자점",
            "requested_cal_day": "20260705",
            "rsv_hour": "1700",
            "payment_amount": 288200,
            "price_basis": "extra_fvr_sale_prc",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
        source="test:purchase_ready",
        flow_type="purchase",
        flow_step="build_preorder",
        status="active",
    ).state.to_active_flow_context()
    dormant_flows = upsert_dormant_flow([], dormant_purchase)

    transition = transition_current_flow(
        user_text="주문하기",
        router_evidence={
            "domain": "transaction",
            "intent": "quick_order_reservation",
            "execution_plan": ["transaction:quick_order_reservation"],
        },
        existing_slots=ConversationSlots(
            goods_no="G000000320152",
            availability_context={"dormant_flows": dormant_flows},
        ),
        extracted_slots=ConversationSlots(),
        resume_source="explicit_user",
    )

    assert transition.flow_transition["reason"] == "dormant_flow_resume"
    assert transition.metadata["dormant_resume_status"] == "resumed"
    assert transition.metadata["dormant_resume_applied"] is True
    active_context = transition.flow_transition["active_flow_context"]
    assert active_context["status"] == "resumed"
    assert active_context["product"]["goods_no"] == "G000000320152"
    assert active_context["product"]["tire_size"] == "245/45R19"
    assert active_context["product"]["ord_qty"] == 2
    assert active_context["store"]["shop_id"] == "F00071"
    assert active_context["schedule"]["requested_cal_day"] == "20260705"
    assert active_context["schedule"]["rsv_hour"] == "1700"
    assert active_context["payment"]["payment_amount"] == 288200


def test_transition_current_flow_pivots_price_check_without_resuming_dormant_purchase() -> None:
    dormant_purchase = commit_flow_state(
        None,
        {
            "goods_no": "G000000320152",
            "product_name": "Dynapro HP3",
            "tire_size": "245/45R19",
            "ord_qty": 2,
            "pending_intent": "order",
            "goal_type": "place_order",
        },
        source="test:purchase_ready",
        flow_type="purchase",
        flow_step="ask_store",
        status="active",
    ).state.to_active_flow_context()
    dormant_flows = upsert_dormant_flow([], dormant_purchase)

    transition = transition_current_flow(
        user_text="가격이 얼마야?",
        router_evidence={
            "domain": "transaction",
            "intent": "price_lookup",
            "execution_plan": ["transaction:price_or_coupon_check"],
        },
        existing_slots=ConversationSlots(
            goods_no="G000000320152",
            availability_context={"dormant_flows": dormant_flows},
        ),
        extracted_slots=ConversationSlots(),
        resume_source="none",
    )

    assert transition.flow_transition["applied"] is True
    active_context = transition.flow_transition["active_flow_context"]
    assert active_context["intent"]["sub_flow_type"] == "price_check"
    assert transition.metadata["dormant_resume_status"] == "not_attempted"
    assert transition.metadata["dormant_resume_applied"] is False


def test_transition_current_flow_price_check_prefers_current_turn_product_snapshot() -> None:
    transition = transition_current_flow(
        user_text="새 상품 할인 얼마야?",
        router_evidence={
            "domain": "transaction",
            "intent": "price_or_coupon_check",
            "execution_plan": ["transaction:price_or_coupon_check"],
        },
        existing_slots=ConversationSlots(
            goods_no="G000000_OLD",
            tire_model="이전 상품",
            tire_size="245/45R19",
            ord_qty=4,
        ),
        extracted_slots=ConversationSlots(
            goods_no="G000000_NEW",
            tire_model="새 상품",
            tire_size="275/50R20",
            ord_qty=2,
        ),
        resume_source="none",
    )

    assert transition.flow_transition["applied"] is True
    active_context = transition.flow_transition["active_flow_context"]
    assert active_context["intent"]["sub_flow_type"] == "price_check"
    assert active_context["product"]["goods_no"] == "G000000_NEW"
    assert active_context["product"]["product_name"] == "새 상품"
    assert active_context["product"]["tire_size"] == "275/50R20"
    assert active_context["product"]["ord_qty"] == 2


def test_transition_current_flow_price_check_drops_stale_goods_no_for_new_product_identity() -> None:
    transition = transition_current_flow(
        user_text="새 상품 할인 얼마야?",
        router_evidence={
            "domain": "transaction",
            "intent": "price_or_coupon_check",
            "execution_plan": ["transaction:price_or_coupon_check"],
        },
        existing_slots=ConversationSlots(
            goods_no="G000000_OLD",
            tire_model="이전 상품",
            tire_size="245/45R19",
            ord_qty=4,
        ),
        extracted_slots=ConversationSlots(
            tire_model="새 상품",
        ),
        resume_source="none",
    )

    assert transition.flow_transition["applied"] is True
    product = transition.flow_transition["active_flow_context"]["product"]
    assert "goods_no" not in product
    assert product["product_name"] == "새 상품"
    assert product["tire_model"] == "새 상품"


def test_transition_current_flow_resumes_dormant_purchase_from_explicit_anchor() -> None:
    dormant_purchase = commit_flow_state(
        None,
        {
            "goods_no": "G000000320152",
            "product_name": "Dynapro HP3",
            "tire_size": "245/45R19",
            "ord_qty": 2,
            "shop_id": "F00123",
            "shop_name": "티스테이션 분당점",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
        source="test:purchase_store_selected",
        flow_type="purchase",
        flow_step="show_schedule",
        status="active",
    ).state.to_active_flow_context()
    dormant_flows = upsert_dormant_flow([], dormant_purchase)

    transition = transition_current_flow(
        user_text="계속 진행해줘",
        router_evidence={
            "domain": "transaction",
            "intent": "quick_order_reservation_continue",
            "execution_plan": ["transaction:quick_order_reservation_continue"],
        },
        existing_slots=ConversationSlots(availability_context={"dormant_flows": dormant_flows}),
        extracted_slots=ConversationSlots(),
        resume_source="none",
    )

    assert transition.metadata["dormant_resume_applied"] is True
    active_context = transition.flow_transition["active_flow_context"]
    assert active_context["status"] == "resumed"
    assert active_context["current_step"] == "resolve_schedule"
    assert active_context["next_tool"] == "get_store_schedule_tool"
    assert active_context["missing_slots"] == ["booking_datetime"]


def test_purchase_store_ui_action_accepts_template_slot_aliases_without_entity_metadata() -> None:
    transition = transition_current_flow(
        user_text="선택",
        router_evidence={
            "domain": "transaction",
            "intent": "quick_order_reservation",
            "execution_plan": ["transaction:quick_order_reservation:slot_fill:store"],
            "is_slot_fill": True,
            "filled_slot": "store",
        },
        existing_slots=ConversationSlots(
            availability_context={
                "active_flow_context": {
                    "flow_type": "purchase",
                    "status": "active",
                    "flow_step": "quantity_selected",
                    "product": {
                        "goods_no": "G000000309783",
                        "product_name": "Ventus S2 AS",
                        "tire_size": "245/45R19",
                        "ord_qty": 2,
                    },
                    "intent": {"pending_intent": "order", "goal_type": "place_order"},
                }
            }
        ),
        extracted_slots=ConversationSlots(),
        ui_action={
            "action_type": "select_store",
            "selection_source": "location_template",
            "slots": {
                "shopId": "F00777",
                "shopName": "T-Station Hannam",
                "goodsNo": "G000000309783",
                "ordQty": 2,
            },
        },
        resume_source="validated_ui_action_slot_fill:store",
    )

    assert transition.metadata["selected_store_resolved"] is True
    active_context = transition.flow_transition["active_flow_context"]
    assert active_context["flow_step"] == "store_selected"
    assert active_context["product"]["goods_no"] == "G000000309783"
    assert active_context["product"]["ord_qty"] == 2
    assert active_context["store"]["shop_id"] == "F00777"

    selected_slots = selected_store_slots_from_active_flow_context(
        active_context,
        allowed_flow_types=frozenset({"purchase"}),
    )
    next_state = resolve_purchase_order_flow(intent="quick_order_reservation", known_slots=selected_slots)

    assert next_state is not None
    assert next_state.flow_step == "show_schedule"
    assert "store" not in next_state.missing_slots


def test_pending_purchase_drops_action_label_residue_product_identity() -> None:
    result = commit_purchase_flow_state(
        {
            "tire_size": "225/45R17",
            "ord_qty": 4,
            "pending_intent": "order",
            "goal_type": "place_order",
        },
        {"product_name": "하기", "tire_model": "하기", "pending_product_name": "하기", "region": "분당"},
        source="cta_label_residue",
    )

    context = result.state.to_pending_order_context()
    assert "product_name" not in context
    assert "tire_model" not in context
    assert "pending_product_name" not in context
    assert context["tire_size"] == "225/45R17"
    assert context["ord_qty"] == 4
    assert context["region"] == "분당"


def test_active_purchase_drops_action_label_residue_product_identity() -> None:
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "ask_quantity",
            "product": {"tire_size": "225/45R17"},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
        {"product_name": "구매하기", "ord_qty": 4},
        source="cta_label_residue",
        flow_type="purchase",
        status="active",
    )

    context = result.state.to_active_flow_context()
    assert "product_name" not in context["product"]
    assert "tire_model" not in context["product"]
    assert "pending_product_name" not in context["product"]
    assert context["product"]["tire_size"] == "225/45R17"
    assert context["product"]["ord_qty"] == 4


def test_pending_purchase_new_product_identity_clears_stale_resolution() -> None:
    result = commit_purchase_flow_state(
        {
            "goods_no": "GOLD",
            "product_name": "다이나프로 HP3",
            "tire_model": "다이나프로 HP3",
            "pending_product_name": "다이나프로 HP3",
            "tire_size": "215/70R16",
            "ord_qty": 2,
            "region": "분당",
            "shop_id": "S1",
            "shop_name": "티스테이션 분당정자점",
            "requested_cal_day": "2026-07-01",
            "rsv_hour": "16:00",
            "payment_amount": 556000,
            "price_basis": "cheapest_final_prc",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
        {"product_name": "웨더플렉스", "pending_intent": "order", "goal_type": "place_order"},
        source="new_product_name_order",
    )

    context = result.state.to_pending_order_context()
    assert "goods_no" not in context
    assert context["product_name"] == "웨더플렉스"
    assert context["tire_model"] == "웨더플렉스"
    assert context["pending_product_name"] == "웨더플렉스"
    assert context["tire_size"] == "215/70R16"
    assert context["ord_qty"] == 2
    assert "shop_id" not in context
    assert "requested_cal_day" not in context
    assert "payment_amount" not in context
    assert "price_basis" not in context
    assert result.metadata["flow_state_conflicts"]["product_identity"] == {
        "existing": "다이나프로 HP3",
        "incoming": "웨더플렉스",
        "existing_goods_no": "GOLD",
    }
    assert "goods_no" in result.metadata["cleared_fields"]
    assert "payment_amount" in result.metadata["cleared_fields"]


def test_active_purchase_new_product_identity_returns_to_product_resolution() -> None:
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "show_schedule",
            "product": {
                "goods_no": "GOLD",
                "product_name": "다이나프로 HP3",
                "tire_model": "다이나프로 HP3",
                "pending_product_name": "다이나프로 HP3",
                "tire_size": "215/70R16",
                "ord_qty": 2,
            },
            "store": {"region": "분당", "shop_id": "S1", "shop_name": "티스테이션 분당정자점"},
            "schedule": {"requested_cal_day": "2026-07-01", "rsv_hour": "16:00"},
            "payment": {"payment_amount": 556000, "price_basis": "cheapest_final_prc"},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
            "last_candidates": [{"goods_no": "GOLD", "label": "다이나프로 HP3"}],
        },
        {"product_name": "웨더플렉스", "pending_intent": "order", "goal_type": "place_order"},
        source="active_new_product_name_order",
        flow_type="purchase",
        status="active",
    )

    context = result.state.to_active_flow_context()
    assert "goods_no" not in context["product"]
    assert context["product"]["product_name"] == "웨더플렉스"
    assert context["product"]["tire_size"] == "215/70R16"
    assert context["product"]["ord_qty"] == 2
    assert context["store"] == {"region": "분당"}
    assert "schedule" not in context
    assert "payment" not in context
    assert "last_candidates" not in context
    assert context["current_step"] == "resolve_product"
    assert context["missing_slots"] == ["goods_no"]
    assert context["next_tool"] == "search_product_tool"
    assert context["tool_args_patch"] == {"keyword": "웨더플렉스", "limit": 10, "size": "215/70R16"}
    assert "product_identity" in result.metadata["flow_state_conflicts"]
    assert "last_candidates" in result.metadata["cleared_fields"]


def test_active_purchase_same_product_identity_preserves_resolution() -> None:
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "resolve_store",
            "product": {
                "goods_no": "GSAME",
                "product_name": "벤투스 S2 AS",
                "tire_size": "245/45R19",
                "ord_qty": 2,
            },
            "payment": {"payment_amount": 308200, "price_basis": "cheapest_final_prc"},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
        {"product_name": "벤투스 S2 AS", "pending_intent": "order", "goal_type": "place_order"},
        source="same_product_name_followup",
        flow_type="purchase",
        status="active",
    )

    context = result.state.to_active_flow_context()
    assert context["product"]["goods_no"] == "GSAME"
    assert context["payment"]["payment_amount"] == 308200
    assert "product_identity" not in result.metadata["flow_state_conflicts"]
    assert "goods_no" not in result.metadata["cleared_fields"]


def test_active_vehicle_change_clears_recommendation_product_and_payment_context() -> None:
    result = commit_flow_state(
        {
            "flow_type": "recommendation",
            "status": "active",
            "flow_step": "select_vehicle",
            "vehicle": {"car_no": "12가3456", "tire_size": "245/45R19"},
            "recommendation": {"rcmd_type": "comfort", "fitment_source": "selected_vehicle"},
            "product": {"goods_no": "GOLD", "product_name": "벤투스 S2 AS", "tire_size": "245/45R19"},
            "store": {"shop_id": "S1", "shop_name": "티스테이션 분당정자점"},
            "schedule": {"requested_cal_day": "2026-07-01", "rsv_hour": "16:00"},
            "payment": {"payment_amount": 308200, "price_basis": "cheapest_final_prc"},
            "last_candidates": [{"goods_no": "GOLD", "label": "벤투스 S2 AS"}],
        },
        {"car_no": "34나7890", "tire_size": "225/55R17"},
        source="vehicle_changed",
        flow_type="recommendation",
        status="active",
    )

    context = result.state.to_active_flow_context()
    assert context["vehicle"]["car_no"] == "34나7890"
    assert context["vehicle"]["tire_size"] == "225/55R17"
    assert context["product"]["tire_size"] == "225/55R17"
    assert "goods_no" not in context["product"]
    assert "product_name" not in context["product"]
    assert "recommendation" not in context
    assert "store" not in context
    assert "schedule" not in context
    assert "payment" not in context
    assert "last_candidates" not in context
    assert "vehicle" in result.metadata["flow_state_conflicts"]
    assert "product_name" in result.metadata["cleared_fields"]
    assert "rcmd_type" in result.metadata["cleared_fields"]


def test_active_purchase_tire_size_change_requires_product_re_resolution() -> None:
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "show_schedule",
            "product": {
                "goods_no": "GOLD",
                "product_name": "벤투스 S2 AS",
                "tire_size": "245/45R19",
                "ord_qty": 2,
            },
            "store": {"shop_id": "S1", "shop_name": "티스테이션 분당정자점"},
            "schedule": {"requested_cal_day": "2026-07-01", "rsv_hour": "16:00"},
            "payment": {"payment_amount": 308200, "price_basis": "cheapest_final_prc"},
        },
        {"tire_size": "225/55R17"},
        source="tire_size_changed",
        flow_type="purchase",
        status="active",
    )

    context = result.state.to_active_flow_context()
    assert context["product"]["product_name"] == "벤투스 S2 AS"
    assert context["product"]["tire_size"] == "225/55R17"
    assert context["product"]["ord_qty"] == 2
    assert "goods_no" not in context["product"]
    assert "store" not in context
    assert "schedule" not in context
    assert "payment" not in context
    assert context["current_step"] == "resolve_product"
    assert context["tool_args_patch"] == {"keyword": "벤투스 S2 AS", "limit": 10, "size": "225/55R17"}
    assert result.metadata["flow_state_conflicts"]["tire_size"] == {
        "existing": "245/45R19",
        "incoming": "225/55R17",
    }


def test_active_purchase_schedule_change_marks_payment_stale() -> None:
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "resolve_schedule",
            "product": {"goods_no": "GSAME", "product_name": "벤투스 S2 AS", "tire_size": "245/45R19", "ord_qty": 2},
            "store": {"shop_id": "S1", "shop_name": "티스테이션 분당정자점"},
            "schedule": {"requested_cal_day": "2026-07-01", "rsv_hour": "16:00"},
            "payment": {"payment_amount": 308200, "price_basis": "cheapest_final_prc"},
        },
        {"requested_cal_day": "2026-07-02", "rsv_hour": "10:00"},
        source="schedule_changed",
        flow_type="purchase",
        status="active",
    )

    context = result.state.to_active_flow_context()
    assert context["schedule"] == {"requested_cal_day": "2026-07-02", "rsv_hour": "10:00"}
    assert context["payment"] == {"payment_amount_stale": True}
    assert result.metadata["payment_amount_stale"] is True
    assert "schedule" in result.metadata["flow_state_conflicts"]
    assert "payment_amount" in result.metadata["cleared_fields"]


def test_purchase_progress_requires_price_after_schedule_before_preorder() -> None:
    progress = evaluate_flow_progress(
        FlowState(
            flow_type="purchase",
            status="active",
            flow_step="show_schedule",
            product={
                "goods_no": "GSAME",
                "product_name": "ë²¤íˆ¬ìŠ¤ S2 AS",
                "tire_size": "245/45R19",
                "ord_qty": 2,
            },
            store={"shop_id": "S1", "shop_name": "í‹°ìŠ¤í…Œì´ì…˜ ë¶„ë‹¹ì •ìžì "},
            schedule={"requested_cal_day": "2026-07-01", "rsv_hour": "16:00"},
            intent={"pending_intent": "order", "goal_type": "place_order"},
        )
    )

    assert progress["current_step"] == "resolve_price"
    assert progress["next_tool"] == "get_final_price_tool"
    assert progress["allowed_tools"] == ["get_final_price_tool"]
    assert progress["tool_args_patch"] == {"goods_no": "GSAME"}
    assert "next_template" not in progress


def test_purchase_progress_can_build_preorder_after_price_basis() -> None:
    progress = evaluate_flow_progress(
        FlowState(
            flow_type="purchase",
            status="active",
            flow_step="show_schedule",
            product={
                "goods_no": "GSAME",
                "product_name": "ë²¤íˆ¬ìŠ¤ S2 AS",
                "tire_size": "245/45R19",
                "ord_qty": 2,
            },
            store={"shop_id": "S1", "shop_name": "í‹°ìŠ¤í…Œì´ì…˜ ë¶„ë‹¹ì •ìžì "},
            schedule={"requested_cal_day": "2026-07-01", "rsv_hour": "16:00"},
            payment={"payment_amount": 308200, "price_basis": "cheapest_final_prc"},
            intent={"pending_intent": "order", "goal_type": "place_order"},
        )
    )

    assert progress["current_step"] == "build_preorder"
    assert progress["next_template"] == "preOrder"
    assert "next_tool" not in progress


def test_active_purchase_to_store_search_pushes_purchase_to_dormant() -> None:
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "resolve_store",
            "product": {"goods_no": "GOLD", "product_name": "벤투스 S2 AS", "tire_size": "245/45R19", "ord_qty": 2},
            "store": {"shop_id": "S1", "shop_name": "티스테이션 분당정자점"},
            "payment": {"payment_amount": 308200},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
        {"region": "분당"},
        source="flow_type_changed",
        flow_type="store_search",
        flow_step="resolve_store",
        status="active",
    )

    context = result.state.to_active_flow_context()
    assert context["flow_type"] == "commerce"
    assert context["intent"]["sub_flow_type"] == "store_search"
    assert context["flow_step"] == "resolve_store"
    assert context["store"]["region"] == "분당"
    assert context["product"]["goods_no"] == "GOLD"
    assert context["payment"]["payment_amount"] == 308200
    assert "flow_type" not in result.metadata["flow_state_conflicts"]
    assert "dormant_flows" not in result.metadata["committed_fields"]


def test_active_purchase_to_nested_store_search_preserves_search_intent() -> None:
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "ask_schedule",
            "product": {"goods_no": "GOLD", "product_name": "벤투스 S2 AS", "tire_size": "245/45R19", "ord_qty": 2},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
        {
            "flow_type": "store_search",
            "status": "active",
            "flow_step": "ask_region",
            "store": {"place_query": "분당"},
            "intent": {
                "pending_intent": "store_recommendation_by_vehicle_experience",
                "goal_type": "store_search",
                "store_search_condition": "vehicle_experience",
                "requested_vehicle_experience": "BMW 정비 경험",
            },
        },
        source="flow_controller:current_turn_store_search",
        flow_type="store_search",
        flow_step="ask_region",
        status="active",
    )

    context = result.state.to_active_flow_context()
    assert context["flow_type"] == "commerce"
    assert context["intent"]["sub_flow_type"] == "store_search"
    assert context["store"]["place_query"] == "분당"
    assert context["intent"]["pending_intent"] == "store_recommendation_by_vehicle_experience"
    assert context["intent"]["store_search_condition"] == "vehicle_experience"
    assert context["intent"]["requested_vehicle_experience"] == "BMW 정비 경험"
    assert context["product"]["goods_no"] == "GOLD"
    assert "dormant_flows" not in context


def test_active_purchase_to_support_faq_preserves_support_intent() -> None:
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "ask_schedule",
            "product": {"goods_no": "GOLD", "product_name": "벤투스 S2 AS", "tire_size": "245/45R19", "ord_qty": 2},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
        {
            "flow_type": "support",
            "status": "active",
            "flow_step": "answer_faq",
            "intent": {
                "pending_intent": "coupon_registration_policy",
                "goal_type": "support_faq",
                "policy_topic": "coupon_registration_policy",
            },
        },
        source="flow_controller:current_turn_support",
        flow_type="support",
        flow_step="answer_faq",
        status="active",
    )

    context = result.state.to_active_flow_context()
    assert context["flow_type"] == "support"
    assert context["flow_step"] == "answer_faq"
    assert context["intent"]["pending_intent"] == "coupon_registration_policy"
    assert context["intent"]["policy_topic"] == "coupon_registration_policy"
    assert context["dormant_flows"][0]["context"]["flow_type"] == "commerce"
    assert context["dormant_flows"][0]["context"]["intent"]["sub_flow_type"] == "purchase"
    assert context["dormant_flows"][0]["context"]["product"]["goods_no"] == "GOLD"


def test_product_change_updates_dormant_flow_and_clears_execution_context() -> None:
    dormant_flows = upsert_dormant_flow(
        [],
        {
            "flow_type": "purchase",
            "status": "active",
            "product": {
                "goods_no": "G-OLD-DORMANT",
                "product_name": "벤투스 S2 AS",
                "tire_size": "245/45R19",
                "ord_qty": 2,
            },
            "store": {"shop_id": "S1", "shop_name": "티스테이션 분당정자점"},
            "schedule": {"requested_cal_day": "20260708", "rsv_hour": "16"},
            "payment": {"payment_amount": 308200, "price_basis": "cheapest_final_prc"},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
    )
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "product": {
                "goods_no": "G-OLD-ACTIVE",
                "product_name": "벤투스 S2 AS",
                "tire_size": "245/45R19",
                "ord_qty": 2,
            },
            "store": {"shop_id": "S1", "shop_name": "티스테이션 분당정자점"},
            "schedule": {"requested_cal_day": "20260708", "rsv_hour": "16"},
            "payment": {"payment_amount": 308200, "price_basis": "cheapest_final_prc"},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
            "dormant_flows": dormant_flows,
        },
        {
            "flow_type": "purchase",
            "status": "active",
            "product": {"product_name": "다이나프로 HP3", "tire_size": "255/45R19", "ord_qty": 2},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
        source="test_product_change",
        flow_type="purchase",
        status="active",
    )

    dormant_context = result.state.to_active_flow_context()["dormant_flows"][0]["context"]
    assert dormant_context["product"]["product_name"] == "다이나프로 HP3"
    assert dormant_context["product"]["tire_size"] == "255/45R19"
    assert "goods_no" not in dormant_context["product"]
    assert "store" not in dormant_context
    assert "schedule" not in dormant_context
    assert "payment" not in dormant_context
    assert "dormant_flows" in result.metadata["committed_fields"]
    assert result.metadata["dormant_dependency_cleared_fields"]


def test_store_change_updates_dormant_flow_and_clears_schedule_but_preserves_payment() -> None:
    dormant_flows = upsert_dormant_flow(
        [],
        {
            "flow_type": "purchase",
            "status": "active",
            "product": {"goods_no": "G-1", "product_name": "벤투스 S2 AS", "tire_size": "245/45R19", "ord_qty": 2},
            "store": {"shop_id": "S1", "shop_name": "티스테이션 분당정자점"},
            "schedule": {"requested_cal_day": "20260708", "rsv_hour": "16"},
            "payment": {"payment_amount": 308200, "price_basis": "cheapest_final_prc"},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
    )
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "product": {"goods_no": "G-1", "product_name": "벤투스 S2 AS", "tire_size": "245/45R19", "ord_qty": 2},
            "store": {"shop_id": "S1", "shop_name": "티스테이션 분당정자점"},
            "schedule": {"requested_cal_day": "20260708", "rsv_hour": "16"},
            "payment": {"payment_amount": 308200, "price_basis": "cheapest_final_prc"},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
            "dormant_flows": dormant_flows,
        },
        {
            "flow_type": "purchase",
            "status": "active",
            "product": {"goods_no": "G-1", "product_name": "벤투스 S2 AS", "tire_size": "245/45R19", "ord_qty": 2},
            "store": {"shop_id": "S2", "shop_name": "티스테이션 정발산점"},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
        source="test_store_change",
        flow_type="purchase",
        status="active",
    )

    dormant_context = result.state.to_active_flow_context()["dormant_flows"][0]["context"]
    assert dormant_context["store"]["shop_id"] == "S2"
    assert dormant_context["store"]["shop_name"] == "티스테이션 정발산점"
    assert "schedule" not in dormant_context
    assert dormant_context["payment"] == {"payment_amount": 308200, "price_basis": "cheapest_final_prc"}
    assert "dormant_flows" in result.metadata["committed_fields"]


def test_weak_flat_purchase_metadata_does_not_become_dormant_purchase() -> None:
    result = commit_flow_state(
        {
            "pending_intent": "order",
            "goal_type": "place_order",
            "product_name": "Ventus S2 AS",
            "tire_size": "245/45R19",
            "template_data": {
                "template": "preOrder",
                "metadata": {"pendingIntent": "order", "goalType": "place_order"},
            },
        },
        {
            "flow_type": "support",
            "status": "active",
            "flow_step": "answer_faq",
            "intent": {
                "pending_intent": "general_cancel_fee_policy",
                "goal_type": "support_faq",
                "policy_topic": "general_cancel_fee_policy",
            },
        },
        source="flow_controller:current_turn_support",
        flow_type="support",
        flow_step="answer_faq",
        status="active",
    )

    context = result.state.to_active_flow_context()
    assert context["flow_type"] == "support"
    assert context["intent"]["pending_intent"] == "general_cancel_fee_policy"
    assert context["intent"]["goal_type"] == "support_faq"
    assert "dormant_flows" not in context
    assert "product" not in context
    assert result.metadata["flow_state_conflicts"] == {}


def test_active_purchase_to_service_maintenance_preserves_action_boundary() -> None:
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "ask_schedule",
            "product": {"goods_no": "GOLD", "product_name": "벤투스 S2 AS", "tire_size": "245/45R19", "ord_qty": 2},
            "store": {"shop_id": "S1", "shop_name": "티스테이션 분당정자점"},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
        {
            "flow_type": "service_maintenance",
            "status": "active",
            "flow_step": "verify_store_service",
            "store": {"shop_id": "S1", "shop_name": "티스테이션 분당정자점"},
            "intent": {
                "pending_intent": "store_attribute_inquiry",
                "goal_type": "store_verification",
                "service_action_boundary": "store_verification",
                "service_name": "얼라인먼트",
                "service_type": "wheel_alignment",
            },
            "target_action": "store_verification",
            "next_tool": "get_store_list_tool",
            "preferred_tool": "get_store_list_tool",
            "allowed_tools": ["get_store_list_tool", "get_store_detail_tool"],
        },
        source="flow_controller:service_maintenance",
        flow_type="service_maintenance",
        flow_step="verify_store_service",
        status="active",
    )

    context = result.state.to_active_flow_context()
    assert context["flow_type"] == "commerce"
    assert context["intent"]["sub_flow_type"] == "service_maintenance"
    assert context["flow_step"] == "verify_store_service"
    assert context["intent"]["service_action_boundary"] == "store_verification"
    assert context["intent"]["service_name"] == "얼라인먼트"
    assert context["intent"]["service_type"] == "wheel_alignment"
    assert context["target_action"] == "store_verification"
    assert context["preferred_tool"] == "get_store_list_tool"
    assert context["allowed_tools"] == ["get_store_list_tool", "get_store_detail_tool"]
    assert context["product"]["goods_no"] == "GOLD"
    assert "dormant_flows" not in context


def test_service_maintenance_to_reservation_management_preserves_boundaries_separately() -> None:
    service = commit_flow_state(
        {},
        {
            "flow_type": "service_maintenance",
            "status": "active",
            "flow_step": "answer_policy",
            "intent": {
                "pending_intent": "maintenance_addon_with_tire_service",
                "goal_type": "service_booking_support",
                "service_action_boundary": "service_booking_support",
                "service_name": "엔진오일",
            },
            "target_action": "service_booking_support",
            "next_tool": "search_faq_hybrid_tool",
            "preferred_tool": "search_faq_hybrid_tool",
            "allowed_tools": ["search_faq_hybrid_tool"],
        },
        source="flow_controller:service_maintenance",
        flow_type="service_maintenance",
        flow_step="answer_policy",
        status="active",
    )

    result = commit_flow_state(
        service.state.to_active_flow_context(),
        {
            "flow_type": "reservation_management",
            "status": "active",
            "flow_step": "guide_user_action",
            "intent": {
                "pending_intent": "reservation_change_request",
                "goal_type": "reservation_management",
                "reservation_management_action": "change_request",
                "owned_record_target": "reservation",
            },
            "target_action": "change_request",
            "allowed_tools": [],
        },
        source="flow_controller:reservation_management",
        flow_type="reservation_management",
        flow_step="guide_user_action",
        status="active",
    )

    context = result.state.to_active_flow_context()
    assert context["flow_type"] == "reservation_management"
    assert context["flow_step"] == "guide_user_action"
    assert context["intent"]["reservation_management_action"] == "change_request"
    assert context["intent"]["owned_record_target"] == "reservation"
    assert context["target_action"] == "change_request"
    assert context["dormant_flows"][0]["context"]["flow_type"] == "commerce"
    assert context["dormant_flows"][0]["context"]["intent"]["sub_flow_type"] == "service_maintenance"
    assert context["dormant_flows"][0]["context"]["intent"]["service_action_boundary"] == "service_booking_support"
    assert context["dormant_flows"][0]["flow_identity"] == "commerce:servicemaintenance:servicebookingsupport:엔진오일"


def test_dormant_purchase_resumes_only_with_explicit_anchor() -> None:
    dormant_flows = upsert_dormant_flow(
        [],
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "resolve_store",
            "product": {"goods_no": "GOLD", "product_name": "벤투스 S2 AS", "tire_size": "245/45R19", "ord_qty": 2},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
    )

    no_anchor = resume_dormant_flow(
        {"flow_type": "store_search", "status": "active"},
        dormant_flows,
        resume_anchor={},
        source="resume_without_anchor",
    )
    assert no_anchor.status == "not_found"

    resumed = resume_dormant_flow(
        {"flow_type": "store_search", "status": "active", "store": {"region": "분당"}},
        dormant_flows,
        resume_anchor={"flow_type": "purchase", "goods_no": "GOLD", "tire_size": "245/45R19"},
        source="explicit_purchase_resume",
    )
    assert resumed.status == "resumed"
    assert resumed.active_flow_context["flow_type"] == "commerce"
    assert resumed.active_flow_context["intent"]["sub_flow_type"] == "purchase"
    assert resumed.active_flow_context["status"] == "resumed"
    assert resumed.active_flow_context["product"]["goods_no"] == "GOLD"
    assert resumed.dormant_flows[0]["context"]["flow_type"] == "commerce"
    assert resumed.dormant_flows[0]["context"]["intent"]["sub_flow_type"] == "store_search"


def test_same_product_size_purchase_dormant_upserts_instead_of_duplicating() -> None:
    now = datetime(2026, 6, 30, 3, 0, tzinfo=timezone.utc)
    first = upsert_dormant_flow(
        [],
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "ask_quantity",
            "product": {"goods_no": "GOLD", "product_name": "벤투스 S2 AS", "tire_size": "245/45R19"},
            "updated_at": "2026-06-30T01:00:00+00:00",
        },
        now=now,
    )
    second = upsert_dormant_flow(
        first,
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "resolve_store",
            "product": {"goods_no": "GOLD", "product_name": "벤투스 S2 AS", "tire_size": "245/45R19", "ord_qty": 4},
            "updated_at": "2026-06-30T02:00:00+00:00",
        },
        now=now,
    )

    assert len(second) == 1
    assert second[0]["flow_identity"] == "commerce:purchase:gold:24545r19"
    assert second[0]["context"]["flow_step"] == "resolve_store"
    assert second[0]["context"]["product"]["ord_qty"] == 4


def test_different_dormant_flow_types_are_preserved_together() -> None:
    now = datetime(2026, 6, 30, 4, 0, tzinfo=timezone.utc)
    dormant = upsert_dormant_flow(
        [],
        {
            "flow_type": "purchase",
            "product": {"goods_no": "GOLD", "tire_size": "245/45R19"},
            "updated_at": "2026-06-30T01:00:00+00:00",
        },
        now=now,
    )
    dormant = upsert_dormant_flow(
        dormant,
        {
            "flow_type": "recommendation",
            "recommendation": {"scenario": "comfort"},
            "vehicle": {"car_no": "12가3456"},
            "updated_at": "2026-06-30T02:00:00+00:00",
        },
        now=now,
    )
    dormant = upsert_dormant_flow(
        dormant,
        {
            "flow_type": "store_search",
            "store": {"region": "분당"},
            "updated_at": "2026-06-30T03:00:00+00:00",
        },
        now=now,
    )

    assert {item["context"]["flow_type"] for item in dormant} == {"commerce"}
    assert {item["context"]["intent"]["sub_flow_type"] for item in dormant} == {
        "purchase",
        "recommendation",
        "store_search",
    }
    assert {item["flow_identity"].split(":", 2)[1] for item in dormant} == {
        "purchase",
        "recommendation",
        "storesearch",
    }


def test_dormant_resume_returns_ambiguous_when_multiple_candidates_match_anchor() -> None:
    dormant = upsert_dormant_flow(
        [],
        {
            "flow_type": "purchase",
            "product": {"goods_no": "GOLD", "product_name": "벤투스 S2 AS", "tire_size": "245/45R19"},
        },
    )
    dormant = upsert_dormant_flow(
        dormant,
        {
            "flow_type": "purchase",
            "product": {"goods_no": "SILVER", "product_name": "키너지", "tire_size": "225/55R17"},
        },
    )

    result = resume_dormant_flow(
        {"flow_type": "store_search", "status": "active"},
        dormant,
        resume_anchor={"flow_type": "purchase"},
        source="ambiguous_purchase_resume",
    )

    assert result.status == "ambiguous"
    assert len(result.candidates) == 2
    assert not result.active_flow_context


def test_dormant_flows_prune_by_ttl_and_max_count() -> None:
    now = datetime(2026, 6, 30, 3, 0, tzinfo=timezone.utc)
    dormant = [
        {
            "flow_identity": "purchase:g1:24545r19",
            "updated_at": "2026-06-30T00:00:00+00:00",
            "context": {"flow_type": "purchase", "product": {"goods_no": "G1", "tire_size": "245/45R19"}},
        },
        {
            "flow_identity": "purchase:g2:24545r19",
            "updated_at": "2026-06-30T02:00:00+00:00",
            "context": {"flow_type": "purchase", "product": {"goods_no": "G2", "tire_size": "245/45R19"}},
        },
        {
            "flow_identity": "purchase:g3:24545r19",
            "updated_at": "2026-06-30T02:30:00+00:00",
            "context": {"flow_type": "purchase", "product": {"goods_no": "G3", "tire_size": "245/45R19"}},
        },
    ]

    pruned = prune_dormant_flows(dormant, max_flows=1, ttl_seconds=60 * 60 * 2, now=now)

    assert len(pruned) == 1
    assert pruned[0]["flow_identity"] == "purchase:g3:24545r19"
