from __future__ import annotations

from services.tstation.policies.flow_state import commit_flow_state
from services.tstation.policies.intent_frame import IntentFrame, PolicyDomain
from services.tstation.policies.response_decision import ResponseDecision, ResponseShape, TemplateName, ToolPlan
from services.tstation.policies.transaction_intent_policy import plan_transaction_tools
from services.tstation.policies.transaction_response_policy import decide_transaction_response
from services.tstation.policies.turn_contract import (
    TurnContract,
    build_turn_contract,
    response_contract_violations,
    violates_response_template_contract,
)
from services.tstation.policies.ui_action_policy import build_pure_inventory_stock_contract


def _purchase_slots(**overrides: object) -> dict[str, object]:
    slots: dict[str, object] = {
        "goods_no": "G000000309783",
        "product_name": "Ventus S2 AS",
        "tire_size": "225/45R17",
        "ord_qty": 4,
        "shop_id": "F00721",
        "shop_name": "T-Station Pangyo",
        "requested_cal_day": "20260705",
        "rsv_hour": "17",
        "pending_intent": "order",
        "goal_type": "place_order",
    }
    slots.update(overrides)
    return slots


def test_purchase_new_product_transition_invalidates_stale_store_schedule_and_price() -> None:
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "show_schedule",
            "product": _purchase_slots(),
            "store": {"shop_id": "F00721", "shop_name": "T-Station Pangyo"},
            "schedule": {"requested_cal_day": "20260705", "rsv_hour": "17"},
            "payment": {"payment_amount": 420000, "price_basis": "cheapest_final_prc"},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
        {"product_name": "Kinergy ST AS", "pending_intent": "order", "goal_type": "place_order"},
        source="transition_table:new_product_intent",
        flow_type="purchase",
        status="active",
    )

    context = result.state.to_active_flow_context()

    assert "goods_no" not in context["product"]
    assert context["product"]["product_name"] == "Kinergy ST AS"
    assert "store" not in context
    assert "schedule" not in context
    assert "payment" not in context
    assert context["current_step"] == "resolve_product"
    assert context["next_tool"] == "search_product_tool"


def test_purchase_store_change_does_not_recommit_stale_schedule_or_price_from_delta() -> None:
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "build_preorder",
            "product": _purchase_slots(),
            "store": {"shop_id": "F00721", "shop_name": "T-Station Pangyo"},
            "schedule": {"requested_cal_day": "20260705", "rsv_hour": "17"},
            "payment": {"payment_amount": 420000, "price_basis": "cheapest_final_prc"},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
        {
            "goods_no": "G000000309783",
            "product_name": "Ventus S2 AS",
            "tire_size": "225/45R17",
            "ord_qty": 4,
            "shop_id": "F00999",
            "shop_name": "T-Station Gangnam",
            "requested_cal_day": "20260705",
            "rsv_hour": "17",
            "payment_amount": 420000,
            "price_basis": "cheapest_final_prc",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
        source="transition_table:store_change",
        flow_type="purchase",
        status="active",
    )

    context = result.state.to_active_flow_context()

    assert context["store"]["shop_id"] == "F00999"
    assert context["current_step"] == "resolve_schedule"
    assert "schedule" not in context
    assert "payment" not in context
    assert "shop_id" in result.metadata["flow_state_conflicts"]


def test_purchase_product_change_does_not_recommit_stale_store_schedule_or_price_from_delta() -> None:
    result = commit_flow_state(
        {
            "flow_type": "purchase",
            "status": "active",
            "flow_step": "build_preorder",
            "product": _purchase_slots(),
            "store": {"shop_id": "F00721", "shop_name": "T-Station Pangyo"},
            "schedule": {"requested_cal_day": "20260705", "rsv_hour": "17"},
            "payment": {"payment_amount": 420000, "price_basis": "cheapest_final_prc"},
            "intent": {"pending_intent": "order", "goal_type": "place_order"},
        },
        {
            "goods_no": "G000000999999",
            "product_name": "Kinergy ST AS",
            "tire_size": "225/45R17",
            "ord_qty": 4,
            "shop_id": "F00721",
            "shop_name": "T-Station Pangyo",
            "requested_cal_day": "20260705",
            "rsv_hour": "17",
            "payment_amount": 420000,
            "price_basis": "cheapest_final_prc",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
        source="transition_table:product_change",
        flow_type="purchase",
        status="active",
    )

    context = result.state.to_active_flow_context()

    assert context["product"]["goods_no"] == "G000000999999"
    assert context["current_step"] == "ask_store"
    assert "store" not in context
    assert "schedule" not in context
    assert "payment" not in context
    assert "goods_no" in result.metadata["flow_state_conflicts"]


def test_purchase_preorder_requires_price_basis_before_template_action() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="quick_order_reservation",
        known_slots=_purchase_slots(),
        response_decision={
            "template": "preOrder",
            "metadata": {"response_shape_key": "reservation_confirmation_ready"},
        },
        action_mode="purchase_continuation",
        flow_id="purchase_order",
        flow_step="build_preorder",
        context_state="active",
    )

    violations = response_contract_violations(
        template="preOrder",
        assistant_response_source="code_reservation_confirmation_ready",
        response_shape_key="reservation_confirmation_ready",
        called_tools=(),
        contract=contract,
    )

    assert {violation["type"] for violation in violations} == {"preorder_without_price_basis"}


def test_purchase_preorder_allows_complete_slots_with_price_basis() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="quick_order_reservation",
        known_slots=_purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
        response_decision={
            "template": "preOrder",
            "metadata": {"response_shape_key": "reservation_confirmation_ready"},
        },
        action_mode="purchase_continuation",
        flow_id="purchase_order",
        flow_step="build_preorder",
        context_state="active",
    )

    violations = response_contract_violations(
        template="preOrder",
        assistant_response_source="code_reservation_confirmation_ready",
        response_shape_key="reservation_confirmation_ready",
        called_tools=(),
        contract=contract,
    )

    assert violations == []


def test_purchase_order_complete_requires_successful_quick_order_tool_boundary() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="quick_order_execute",
        known_slots=_purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
        allowed_tools=("quick_order_tool",),
        response_decision={
            "template": "orderComplete",
            "metadata": {"response_shape_key": "quick_order_execute"},
        },
        action_mode="purchase_continuation",
        context_state="active",
    )

    violations = response_contract_violations(
        template="orderComplete",
        assistant_response_source="llm",
        response_shape_key="quick_order_execute",
        called_tools=(),
        contract=contract,
    )

    assert {violation["type"] for violation in violations} == {"order_complete_without_quick_order_tool"}


def test_purchase_order_complete_blocks_failed_quick_order_tool_result() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="quick_order_execute",
        known_slots=_purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
        allowed_tools=("quick_order_tool",),
        response_decision={
            "template": "orderComplete",
            "metadata": {"response_shape_key": "quick_order_execute"},
        },
        action_mode="purchase_continuation",
        context_state="active",
    )

    violations = response_contract_violations(
        template="orderComplete",
        assistant_response_source="transaction_agent",
        response_shape_key="quick_order_execute",
        called_tools=("quick_order_tool",),
        structured_sources=(("quick_order_tool", {"status": "error", "data": {}}),),
        contract=contract,
    )

    assert "order_complete_without_successful_quick_order_tool" in {violation["type"] for violation in violations}


def test_purchase_order_complete_allows_successful_quick_order_tool_result() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="quick_order_execute",
        known_slots=_purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
        allowed_tools=("quick_order_tool",),
        response_decision={
            "template": "orderComplete",
            "metadata": {"response_shape_key": "quick_order_execute"},
        },
        action_mode="purchase_continuation",
        context_state="active",
    )

    violations = response_contract_violations(
        template="orderComplete",
        assistant_response_source="transaction_agent",
        response_shape_key="quick_order_execute",
        called_tools=("quick_order_tool",),
        structured_sources=(("quick_order_tool", {"status": "success", "data": {}}),),
        contract=contract,
    )

    assert violations == []


def test_support_policy_turn_blocks_stale_purchase_templates_and_tools() -> None:
    contract = TurnContract(
        domain="support",
        intent="general_cancel_fee_policy",
        known_slots={"active_parent_flow": "purchase"},
        forbidden_tools=("quick_order_tool", "get_store_schedule_tool", "get_final_price_tool"),
        response_decision={
            "template": "quickReply",
            "metadata": {"response_shape_key": "general_cancel_fee_policy_summary"},
        },
        action_mode="support_policy_answer",
        context_state="dormant",
        dormant_context_reason="support_turn",
    )

    assert violates_response_template_contract({"template": "preOrder"}, contract) is True
    assert violates_response_template_contract({"template": "datepick"}, contract) is True
    assert violates_response_template_contract({"template": "quickReply"}, contract) is False

    violations = response_contract_violations(
        template="quickReply",
        called_tools=("quick_order_tool",),
        contract=contract,
    )

    assert "action_mode_tool_violation" in {violation["type"] for violation in violations}


def test_support_policy_contract_overrides_stale_purchase_tool_plan() -> None:
    frame = IntentFrame(
        domain=PolicyDomain.SUPPORT,
        intent="general_cancel_fee_policy",
        known_slots={
            **_purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
            "active_parent_flow": "purchase",
        },
    )
    stale_tool_plan = ToolPlan(
        allowed_tools=("quick_order_tool", "get_store_schedule_tool", "search_faq_hybrid_tool"),
        preferred_tool="quick_order_tool",
        forbidden_tools=(),
        metadata={"response_intent": "quick_order_execute"},
    )
    response_decision = ResponseDecision(
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=("personal_order_lookup", "normalize_as_cancel_request"),
        metadata={"response_shape_key": "general_cancel_fee_policy_summary"},
    )
    contract = build_turn_contract(
        user_text="cancel fee policy",
        intent_frame=frame,
        tool_plan=stale_tool_plan,
        response_decision=response_decision,
    )

    assert contract.domain == "support"
    assert contract.intent == "general_cancel_fee_policy"
    assert "search_faq_hybrid_tool" in contract.allowed_tools
    assert "quick_order_tool" not in contract.allowed_tools
    assert "get_store_schedule_tool" not in contract.allowed_tools
    assert "quick_order_tool" in contract.forbidden_tools
    assert "get_store_schedule_tool" in contract.forbidden_tools
    assert violates_response_template_contract({"template": "preOrder"}, contract) is True
    assert violates_response_template_contract({"template": "datepick"}, contract) is True
    assert violates_response_template_contract({"template": "orderComplete"}, contract) is True
    assert violates_response_template_contract({"template": "quickReply"}, contract) is False


def test_stock_pure_inventory_transition_blocks_schedule_and_preorder_templates() -> None:
    decision = decide_transaction_response(
        intent="stock_store_search",
        user_text="Pangyo store inventory only",
        known_slots={
            "goods_no": "G000000309783",
            "tire_size": "225/45R17",
            "ord_qty": 4,
            "shop_id": "F00721",
            "stock_check_mode": "inventory_only",
        },
    )
    contract = TurnContract(
        domain="transaction",
        intent="stock_store_search",
        known_slots={"stock_check_mode": "inventory_only"},
        response_decision=decision.to_dict(),
        action_mode="stock_check",
        context_state="active",
    )

    assert decision.template == TemplateName.LOCATION
    assert decision.metadata["reservation_ui_allowed"] is False
    assert violates_response_template_contract({"template": "datepick"}, contract) is True
    assert violates_response_template_contract({"template": "preOrder"}, contract) is True
    assert violates_response_template_contract({"template": "orderComplete"}, contract) is True
    assert violates_response_template_contract({"template": "location"}, contract) is False


def test_pure_inventory_stock_contract_uses_inventory_boundary_not_datepick() -> None:
    contract = build_pure_inventory_stock_contract(
        "4개",
        {
            "goods_no": "G000000309783",
            "tire_size": "225/45R17",
            "ord_qty": 4,
            "shop_id": "F00721",
            "shop_name": "T-Station Pangyo",
            "pending_intent": "stock",
            "goal_type": "store_with_stock",
            "stock_check_mode": "inventory_only",
        },
    )

    assert contract is not None
    assert contract.preferred_tool == "get_store_inventory_tool"
    assert "get_store_schedule_tool" not in contract.allowed_tools
    assert "get_store_schedule_tool" in contract.forbidden_tools
    assert contract.response_decision["template"] == "location"
    assert contract.response_decision["metadata"]["response_shape_key"] == "stock_inventory_lookup"
    assert violates_response_template_contract({"template": "datepick"}, contract) is True


def test_inventory_only_stock_contract_rejects_schedule_tool_datepick() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="stock_store_search",
        known_slots={"stock_check_mode": "inventory_only"},
        allowed_tools=("get_store_schedule_tool",),
        preferred_tool="get_store_schedule_tool",
        response_decision={
            "template": "datepick",
            "forbidden_behaviors": ("datepick_for_pure_inventory_flow",),
            "metadata": {"response_shape_key": "reservation_slots", "stock_check_mode": "inventory_only"},
        },
        action_mode="stock_check",
        context_state="active",
    )

    violations = response_contract_violations(
        template="datepick",
        response_shape_key="reservation_slots",
        called_tools=("get_store_schedule_tool",),
        contract=contract,
    )

    assert "forbidden_datepick_for_inventory_only_stock" in {violation["type"] for violation in violations}


def test_stock_unavailable_inventory_blocks_schedule_and_preorder_templates() -> None:
    decision = decide_transaction_response(
        intent="inventory_availability",
        user_text="Is this available at Pangyo now?",
        known_slots={
            "goods_no": "G000000309783",
            "tire_size": "225/45R17",
            "ord_qty": 4,
            "shop_id": "F00721",
        },
        tool_result={
            "available_qty": 0,
            "today_installable": False,
            "tna_available": False,
        },
    )
    contract = TurnContract(
        domain="transaction",
        intent="inventory_availability",
        known_slots={"stock_check_mode": "inventory_only"},
        response_decision=decision.to_dict(),
        action_mode="stock_check",
        context_state="active",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert "datepick_for_unavailable_stock" in decision.forbidden_behaviors
    assert violates_response_template_contract({"template": "datepick"}, contract) is True
    assert violates_response_template_contract({"template": "preOrder"}, contract) is True
    assert violates_response_template_contract({"template": "quickReply"}, contract) is False


def test_stock_schedule_selection_does_not_create_preorder_without_purchase_anchor() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="stock_store_search",
        known_slots={
            "goods_no": "G000000309783",
            "tire_size": "225/45R17",
            "ord_qty": 4,
            "shop_id": "F00721",
            "stock_check_mode": "preview",
        },
        response_decision={
            "template": "datepick",
            "forbidden_behaviors": ("preorder",),
            "metadata": {"response_shape_key": "reservation_slots"},
        },
        action_mode="stock_check",
        context_state="active",
    )

    assert violates_response_template_contract({"template": "datepick"}, contract) is False
    assert violates_response_template_contract({"template": "preOrder"}, contract) is True


def test_store_search_location_booking_flow_requires_booking_context() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="open_store_search",
        known_slots={"region": "Pangyo"},
        response_decision={
            "template": "location",
            "metadata": {"response_shape_key": "open_store_filter"},
        },
        action_mode="store_search",
        context_state="active",
    )

    assert violates_response_template_contract(
        {"template": "location", "data": {"isBookingFlow": True}},
        contract,
    ) is True
    assert violates_response_template_contract(
        {"template": "location", "data": {"isBookingFlow": False}},
        contract,
    ) is False


def test_open_store_search_forbids_schedule_boundary() -> None:
    frame = IntentFrame(
        domain=PolicyDomain.TRANSACTION,
        intent="open_store_search",
        sub_intent="open_store_filter",
        known_slots={"region": "Pangyo", "open_only": True},
    )
    tool_plan = plan_transaction_tools(frame)
    response_decision = decide_transaction_response(
        intent=frame.intent,
        user_text="find open stores near Pangyo",
        known_slots=frame.known_slots,
    )
    contract = build_turn_contract(
        user_text="find open stores near Pangyo",
        intent_frame=frame,
        tool_plan=tool_plan,
        response_decision=response_decision,
    )

    assert "search_stores_complex_tool" in tool_plan.allowed_tools
    assert "get_store_schedule_tool" not in tool_plan.allowed_tools
    assert "get_store_schedule_tool" in tool_plan.forbidden_tools
    assert "datepick_for_store_search_flow" in response_decision.forbidden_behaviors
    assert "search_stores_complex_tool" in contract.allowed_tools
    assert "get_store_schedule_tool" not in contract.allowed_tools
    assert "get_store_schedule_tool" in contract.forbidden_tools
    assert violates_response_template_contract({"template": "datepick"}, contract) is True
    violations = response_contract_violations(
        template="location",
        called_tools=("get_store_schedule_tool",),
        contract=contract,
    )
    assert "forbidden_tool_for_contract" in {violation["type"] for violation in violations}
