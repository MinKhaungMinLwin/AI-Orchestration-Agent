from __future__ import annotations

from types import SimpleNamespace

from schemas.tstation.slots import ConversationSlots
from services.tstation.policies.slot_fill_controller import (
    _flow_state_reconciliation,
    apply_router_location_slot_fill,
    build_router_slot_fill_context,
    can_promote_existing_store_for_expected_slot_fill,
)
from services.tstation.policies.pending_clarification_policy import (
    resolve_pending_clarification_answer,
    stage_pending_clarification,
)
from services.tstation.policies.slot_fill_policy import expected_slot_fill_precheck
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


def test_router_location_slot_fill_replaces_stale_region_and_resets_store_schedule() -> None:
    slots = ConversationSlots(
        goods_no="G000000320151",
        tire_size="235/55R19",
        ord_qty=4,
        region="분당",
        shop_id="F00262",
        shop_name="티스테이션 분당점",
        requested_cal_day="20260708",
        rsv_hour="16",
        pending_intent="order",
        goal_type="place_order",
        availability_context={
            "pending_order_context": {
                "goods_no": "G000000320151",
                "product_name": "Dynapro HP3",
                "tire_size": "235/55R19",
                "ord_qty": 4,
                "region": "분당",
                "shop_id": "F00262",
                "shop_name": "티스테이션 분당점",
                "requested_cal_day": "20260708",
                "rsv_hour": "16",
                "payment_amount": 420000,
                "pending_intent": "order",
                "goal_type": "place_order",
            },
            "active_flow_context": {
                "flow_type": "commerce",
                "flow_step": "product_selected",
                "product": {
                    "goods_no": "G000000320151",
                    "product_name": "Dynapro HP3",
                    "tire_size": "235/55R19",
                    "ord_qty": 4,
                },
                "intent": {"sub_flow_type": "purchase", "pending_intent": "order", "goal_type": "place_order"},
                "current_step": "ask_store",
                "missing_slots": ["shop_id"],
                "last_candidates": [{"shop_id": "F00262"}],
                "tool_args_patch": {"limit": 10, "region_code": "분당"},
            },
        },
    )
    routing_result = SimpleNamespace(
        needs_clarification=False,
        primary_action="store_search",
        intent="quick_order_reservation",
        execution_plan=["transaction:quick_order_reservation"],
        entity_candidates={
            "location": {
                "mentioned": True,
                "name": "고양시",
                "type": "region",
                "reference_text": "고양시",
                "confidence": 0.96,
            }
        },
    )

    decision = apply_router_location_slot_fill(
        slots=slots,
        routing_result=routing_result,
        router_context={"current_flow": "quick_order_reservation", "flow_step": "show_store_candidates"},
    )

    assert decision.matched is True
    assert decision.slot_patch == {"region": "고양시"}
    assert decision.resume_source == "router_slot_fill:region"
    assert decision.slots.region == "고양시"
    assert decision.slots.shop_id is None
    assert decision.slots.shop_name is None
    assert decision.slots.requested_cal_day is None
    assert decision.slots.rsv_hour is None
    assert decision.slots.goods_no == "G000000320151"
    assert decision.slots.ord_qty == 4
    pending_context = decision.slots.availability_context["pending_order_context"]
    active_context = decision.slots.availability_context["active_flow_context"]
    assert pending_context["region"] == "고양시"
    assert pending_context["payment_amount"] == 420000
    assert "shop_id" not in pending_context
    assert "shop_name" not in pending_context
    assert "requested_cal_day" not in pending_context
    assert "rsv_hour" not in pending_context
    assert active_context["region"] == "고양시"
    assert active_context["flow_step"] == "show_store_candidates"
    assert active_context["current_step"] == "ask_store"
    assert active_context["missing_slots"] == ["shop_id"]
    assert active_context["tool_args_patch"]["region_code"] == "고양시"
    assert active_context["product"]["goods_no"] == "G000000320151"
    assert "last_candidates" not in active_context


def test_current_turn_region_fill_blocks_stale_store_slot_promotion() -> None:
    assert not can_promote_existing_store_for_expected_slot_fill(
        location_slot_fill_matched=True,
        location_selection_resume_source="expected_slot_fill:store",
        existing_shop_id="F00071",
    )
    assert can_promote_existing_store_for_expected_slot_fill(
        location_slot_fill_matched=False,
        location_selection_resume_source="expected_slot_fill:store",
        existing_shop_id="F00071",
    )


def test_schedule_slot_fill_requires_current_turn_schedule_signal() -> None:
    precheck = expected_slot_fill_precheck(
        user_text="1개 가격이 얼마야?",
        regex_slots=ConversationSlots(),
        merged_slots=ConversationSlots(
            goods_no="G000000320151",
            tire_size="235/55R19",
            ord_qty=4,
            shop_id="F00262",
            requested_cal_day="20260708",
            rsv_hour="16",
            pending_intent="order",
            goal_type="place_order",
        ),
        router_context={
            "current_flow": "quick_order_reservation",
            "flow_step": "show_schedule",
            "missing_slots": ["schedule"],
            "last_requested_slot": "schedule",
        },
    )

    assert precheck["matched"] is False
    assert precheck["reason"] == "input_does_not_fill_expected_slot"


def test_router_location_slot_fill_requires_transaction_context() -> None:
    routing_result = SimpleNamespace(
        needs_clarification=False,
        primary_action="store_search",
        intent="store_search",
        execution_plan=["transaction:store_search"],
        entity_candidates={
            "location": {
                "mentioned": True,
                "name": "고양시",
                "type": "region",
                "reference_text": "고양시",
                "confidence": 0.96,
            }
        },
    )

    decision = apply_router_location_slot_fill(
        slots=ConversationSlots(),
        routing_result=routing_result,
        router_context={"current_flow": "none", "flow_step": "none"},
    )

    assert decision.matched is False
    assert decision.slots.region is None


def test_dormant_purchase_context_does_not_turn_general_store_search_into_slot_fill() -> None:
    slots = ConversationSlots(
        availability_context={
            "dormant_purchase_context": {
                "goods_no": "G000000320151",
                "product_name": "Dynapro HP3",
                "tire_size": "235/55R19",
                "ord_qty": 4,
                "region": "분당",
                "pending_intent": "order",
                "goal_type": "place_order",
                "context_state": "dormant",
            }
        },
    )
    routing_result = SimpleNamespace(
        needs_clarification=False,
        primary_action="store_search",
        intent="store_service_search",
        execution_plan=["transaction:store_service_search"],
        entity_candidates={
            "location": {
                "mentioned": True,
                "name": "고양시청",
                "type": "place",
                "reference_text": "고양시청 근처",
                "confidence": 0.96,
            }
        },
    )
    router_context = build_router_slot_fill_context(
        slots=slots,
        user_text="고양시청 근처는?",
        latest_product_tmpl=None,
        latest_location_tmpl=None,
        latest_datepick_tmpl=None,
        has_purchase_anchor=False,
    )

    decision = apply_router_location_slot_fill(
        slots=slots,
        routing_result=routing_result,
        router_context=router_context,
    )

    assert router_context["current_flow"] == "none"
    assert decision.matched is False
    assert decision.slots.availability_context["dormant_purchase_context"]["region"] == "분당"
    assert decision.slots.region is None


def test_router_location_slot_fill_does_not_patch_dormant_purchase_context() -> None:
    slots = ConversationSlots(
        goods_no="G000000320151",
        tire_model="Dynapro HP3",
        tire_size="235/55R19",
        ord_qty=4,
        pending_intent="order",
        goal_type="place_order",
        availability_context={
            "active_flow_context": {
                "flow_type": "purchase",
                "flow_step": "ask_store",
                "status": "active",
                "ord_qty": 4,
                "product": {
                    "goods_no": "G000000320151",
                    "product_name": "Dynapro HP3",
                    "tire_size": "235/55R19",
                    "ord_qty": 4,
                },
                "quantity": {"ord_qty": 4},
                "intent": {"pending_intent": "order", "goal_type": "place_order"},
            },
            "dormant_purchase_context": {
                "goods_no": "G000000111111",
                "tire_size": "225/45R17",
                "ord_qty": 2,
                "region": "분당",
                "shop_id": "F12345",
                "shop_name": "티스테이션 분당점",
                "pending_intent": "order",
                "goal_type": "place_order",
                "context_state": "dormant",
            },
        },
    )
    routing_result = SimpleNamespace(
        needs_clarification=False,
        primary_action="store_selection",
        intent="quick_order_reservation",
        execution_plan=["transaction:quick_order_reservation"],
        entity_candidates={
            "location": {
                "mentioned": True,
                "name": "강남",
                "type": "region",
                "reference_text": "강남",
                "confidence": 0.95,
            }
        },
    )
    router_context = build_router_slot_fill_context(
        slots=slots,
        user_text="강남",
        latest_product_tmpl=None,
        latest_location_tmpl=None,
        latest_datepick_tmpl=None,
        has_purchase_anchor=True,
    )

    decision = apply_router_location_slot_fill(
        slots=slots,
        routing_result=routing_result,
        router_context=router_context,
    )

    dormant = decision.slots.availability_context["dormant_purchase_context"]
    assert decision.matched is True
    assert decision.slots.region == "강남"
    assert dormant["region"] == "분당"
    assert dormant["shop_id"] == "F12345"
    assert dormant["shop_name"] == "티스테이션 분당점"


def test_dormant_purchase_context_does_not_resume_for_unanchored_quantity_question() -> None:
    slots = ConversationSlots(
        availability_context={
            "dormant_purchase_context": {
                "goods_no": "G000000320151",
                "tire_size": "235/55R19",
                "ord_qty": 4,
                "region": "분당",
                "pending_intent": "order",
                "goal_type": "place_order",
                "context_state": "dormant",
            }
        },
    )

    router_context = build_router_slot_fill_context(
        slots=slots,
        user_text="2개 할인은?",
        latest_product_tmpl=None,
        latest_location_tmpl=None,
        latest_datepick_tmpl=None,
        has_purchase_anchor=False,
    )

    assert router_context["current_flow"] == "none"


def test_pending_clarification_stores_candidates_and_resolves_discount_answer() -> None:
    slots = ConversationSlots(
        goods_no="G000000319584",
        tire_model="벤투스 에어S",
        tire_size="245/45R19",
        ord_qty=2,
    )
    routing_result = SimpleNamespace(
        needs_clarification=True,
        referred_object_status="ambiguous",
        referred_object_type="product",
    )

    staged = stage_pending_clarification(
        slots,
        user_text="이거 괜찮아?",
        routing_result=routing_result,
        source_turn_id="turn-1",
    )
    pending = staged.availability_context["pending_clarification"]

    assert pending["status"] == "pending"
    assert [candidate["intent"] for candidate in pending["candidates"]] == [
        "price_or_coupon_check",
        "stock_store_search",
        "product_description",
    ]
    assert pending["base_slots"]["goods_no"] == "G000000319584"

    resolved = resolve_pending_clarification_answer(staged, user_text="할인")

    assert resolved.resolved is True
    assert resolved.intent == "price_or_coupon_check"
    assert resolved.domain == "transaction"
    assert resolved.execution_plan == ("transaction:price_or_coupon_check",)
    assert resolved.slots.goods_no == "G000000319584"
    assert "pending_clarification" not in resolved.slots.availability_context


def test_pending_clarification_resolves_stock_and_description_only_from_candidates() -> None:
    slots = ConversationSlots(
        goods_no="G000000319584",
        tire_model="벤투스 에어S",
        availability_context={
            "pending_clarification": {
                "status": "pending",
                "candidates": [
                    {"label": "재고", "intent": "stock_store_search", "domain": "transaction"},
                    {"label": "성능", "intent": "product_description", "domain": "discovery"},
                ],
                "base_slots": {"goods_no": "G000000319584", "product_name": "벤투스 에어S"},
            }
        },
    )

    stock = resolve_pending_clarification_answer(slots, user_text="재고")
    description = resolve_pending_clarification_answer(slots, user_text="성능")

    assert stock.intent == "stock_store_search"
    assert stock.execution_plan == ("transaction:stock_store_search",)
    assert description.intent == "product_description"
    assert description.execution_plan == ("discovery:product_description",)


def test_pending_clarification_unrelated_answer_clears_and_falls_back_to_router() -> None:
    slots = ConversationSlots(
        goods_no="G000000319584",
        tire_model="벤투스 에어S",
        availability_context={
            "pending_clarification": {
                "status": "pending",
                "candidates": [
                    {"label": "가격/할인", "intent": "price_or_coupon_check", "domain": "transaction"},
                ],
                "base_slots": {"goods_no": "G000000319584"},
            }
        },
    )

    resolved = resolve_pending_clarification_answer(slots, user_text="고양시청 근처는?")

    assert resolved.status == "cleared"
    assert resolved.reason == "unrelated_answer"
    assert "pending_clarification" not in resolved.slots.availability_context


def test_pending_clarification_base_context_change_clears_without_resolution() -> None:
    slots = ConversationSlots(
        goods_no="G000000000002",
        tire_model="다른 상품",
        availability_context={
            "pending_clarification": {
                "status": "pending",
                "candidates": [
                    {"label": "가격/할인", "intent": "price_or_coupon_check", "domain": "transaction"},
                ],
                "base_slots": {"goods_no": "G000000000001"},
            }
        },
    )

    resolved = resolve_pending_clarification_answer(slots, user_text="할인")

    assert resolved.status == "cleared"
    assert resolved.reason == "base_context_changed"
