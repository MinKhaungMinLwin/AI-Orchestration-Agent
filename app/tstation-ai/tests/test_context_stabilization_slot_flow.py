from __future__ import annotations

from schemas.tstation.slots import ConversationSlots
from services.tstation.policies.slot_fill_controller import _flow_state_reconciliation
from services.tstation.policies.ui_action_policy import (
    _with_existing_transaction_slot_fill_state,
    prepare_ui_action_state,
    resolve_ui_action_context,
)


def test_schedule_slot_reconciliation_promotes_full_purchase_slots() -> None:
    slots = ConversationSlots(
        pending_intent="stock",
        goal_type="store_with_stock",
        requested_cal_day="20260708",
        rsv_hour="16",
        availability_context={
            "pending_order_context": {
                "goods_no": "G000000320151",
                "product_name": "Dynapro HP3",
                "tire_size": "235/55R19",
                "ord_qty": 4,
                "shop_id": "F00262",
                "shop_name": "T-Station Dongtan",
                "payment_amount": 420000,
                "price_basis": "payment_amount",
                "pending_intent": "order",
                "goal_type": "place_order",
            },
        },
    )

    reconciliation = _flow_state_reconciliation(
        user_text="2026-07-08 16:00",
        merged_slots=slots,
        slot_patch={"requested_cal_day": "20260708", "rsv_hour": "16"},
        precheck={"filled_slot": "schedule"},
    )

    assert reconciliation["intent"] == "quick_order_reservation"
    assert reconciliation["flow_step"] == "build_preorder"
    assert reconciliation["slot_patch"]["goods_no"] == "G000000320151"
    assert reconciliation["slot_patch"]["tire_size"] == "235/55R19"
    assert reconciliation["slot_patch"]["ord_qty"] == 4
    assert reconciliation["slot_patch"]["shop_id"] == "F00262"
    assert reconciliation["slot_patch"]["requested_cal_day"] == "20260708"
    assert reconciliation["slot_patch"]["rsv_hour"] == "16"
    assert reconciliation["slot_patch"]["payment_amount"] == 420000
    assert reconciliation["slot_patch"]["pending_intent"] == "order"
    assert reconciliation["slot_patch"]["goal_type"] == "place_order"


def test_schedule_ui_action_recovers_purchase_context_from_pending_order() -> None:
    action_context = resolve_ui_action_context(
        raw_action={
            "action_type": "select_schedule",
            "source_intent": "quick_order_reservation",
            "expected_contract_intent": "quick_order_reservation",
            "slots": {"requested_cal_day": "20260708", "rsv_hour": "15"},
        },
        selected_vehicle=None,
        selection_source="ui_action",
    )

    updated_context = _with_existing_transaction_slot_fill_state(
        action_context,
        ConversationSlots(
            pending_intent="stock",
            goal_type="store_with_stock",
            availability_context={
                "pending_order_context": {
                    "goods_no": "G000000320151",
                    "product_name": "Dynapro HP3",
                    "tire_size": "235/55R19",
                    "ord_qty": 4,
                    "shop_id": "F00262",
                    "shop_name": "T-Station Dongtan",
                    "payment_amount": 420000,
                    "price_basis": "payment_amount",
                    "pending_intent": "order",
                    "goal_type": "place_order",
                }
            },
        ),
    )

    assert updated_context.slot_patch["goods_no"] == "G000000320151"
    assert updated_context.slot_patch["tire_size"] == "235/55R19"
    assert updated_context.slot_patch["ord_qty"] == 4
    assert updated_context.slot_patch["shop_id"] == "F00262"
    assert updated_context.slot_patch["payment_amount"] == 420000
    assert updated_context.slot_patch["pending_intent"] == "order"
    assert updated_context.slot_patch["goal_type"] == "place_order"
    assert updated_context.trace_metadata["schedule_action_flow_type"] == "purchase"


def test_prepare_ui_action_state_applies_request_slots_before_schedule_context_recovery() -> None:
    request_slots = {
        "pending_intent": "stock",
        "goal_type": "store_with_stock",
        "availability_context": {
            "pending_order_context": {
                "goods_no": "G000000320151",
                "product_name": "Dynapro HP3",
                "tire_size": "235/55R19",
                "ord_qty": 4,
                "shop_id": "F00262",
                "shop_name": "T-Station Dongtan",
                "payment_amount": 420000,
                "price_basis": "payment_amount",
                "pending_intent": "order",
                "goal_type": "place_order",
            }
        },
    }

    prepared = prepare_ui_action_state(
        ui_action={
            "action_type": "select_schedule",
            "source_intent": "quick_order_reservation",
            "expected_contract_intent": "quick_order_reservation",
            "slots": {"requested_cal_day": "20260708", "rsv_hour": "15"},
        },
        chip_context=None,
        request_slots=request_slots,
        latest_listcar_tmpl=None,
        last_user_text="2026-07-08 15:00",
        existing_slots=ConversationSlots(),
        generic_slot_apply_fn=lambda slots, values: slots.apply_runtime_values(values, source="test"),
        vehicle_slot_apply_fn=lambda slots, values: slots.apply_runtime_values(values, source="test"),
    )

    assert prepared.action_context is not None
    assert prepared.action_context.slot_patch["goods_no"] == "G000000320151"
    assert prepared.action_context.slot_patch["shop_id"] == "F00262"
    assert prepared.action_context.slot_patch["payment_amount"] == 420000
    assert prepared.updated_slots.goods_no == "G000000320151"
    assert prepared.updated_slots.shop_id == "F00262"
    assert prepared.updated_slots.pending_intent == "order"
    assert prepared.updated_slots.goal_type == "place_order"
    assert prepared.trace_metadata["request_slots_applied"] is True
