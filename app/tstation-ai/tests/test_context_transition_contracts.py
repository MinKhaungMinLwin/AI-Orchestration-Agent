from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.tstation.policies.flow_controller import resolve_purchase_order_flow
from services.tstation.policies.flow_state import commit_flow_state, resume_dormant_flow, upsert_dormant_flow
from services.tstation.policies.intent_frame import IntentFrame, PolicyDomain
from services.tstation.policies.response_decision import ResponseDecision, ResponseShape, TemplateName, ToolPlan
from services.tstation.policies.transaction_intent_policy import plan_transaction_tools
from services.tstation.policies.transaction_response_policy import decide_transaction_response
from services.tstation.policies.turn_contract import (
    TurnContract,
    build_required_slot_clarification_event,
    build_response_policy_guard_event,
    build_turn_contract,
    response_contract_violations,
    violates_response_template_contract,
)
from services.tstation.policies.ui_action_policy import build_pure_inventory_stock_contract, finalize_ui_action_metadata_for_contract


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


def _purchase_flow_contract(
    *,
    intent: str,
    known_slots: dict[str, object],
) -> tuple[TurnContract, ToolPlan, ResponseDecision]:
    flow_state = resolve_purchase_order_flow(intent=intent, known_slots=known_slots)
    assert flow_state is not None
    frame = IntentFrame(
        domain=PolicyDomain.TRANSACTION,
        intent=intent,
        known_slots=known_slots,
        missing_slots=flow_state.missing_slots,
    )
    tool_plan = ToolPlan(
        allowed_tools=flow_state.allowed_tools,
        preferred_tool=flow_state.preferred_tool,
        tool_args_patch=flow_state.slot_patch,
        forbidden_tools=flow_state.forbidden_tools,
        required_slots=flow_state.required_slots,
        metadata={
            "response_intent": intent,
            "flow_id": flow_state.flow_id,
            "flow_step": flow_state.flow_step,
            "flow_response_shape_key": flow_state.response_shape_key,
        },
    )
    response_decision = decide_transaction_response(
        intent=intent,
        user_text="transition table matrix",
        known_slots=known_slots,
    )
    contract = build_turn_contract(
        user_text="transition table matrix",
        intent_frame=frame,
        tool_plan=tool_plan,
        response_decision=response_decision,
    )
    return contract, tool_plan, response_decision


def _transaction_policy_contract(
    *,
    intent: str,
    known_slots: dict[str, object],
    user_text: str = "transition table matrix",
    tool_result: dict[str, object] | None = None,
    action_mode: str = "unspecified",
) -> tuple[TurnContract, ToolPlan, ResponseDecision]:
    frame = IntentFrame(
        domain=PolicyDomain.TRANSACTION,
        intent=intent,
        known_slots=known_slots,
    )
    tool_plan = plan_transaction_tools(frame)
    response_decision = decide_transaction_response(
        intent=intent,
        user_text=user_text,
        known_slots=known_slots,
        tool_result=tool_result,
    )
    contract = build_turn_contract(
        user_text=user_text,
        intent_frame=frame,
        tool_plan=tool_plan,
        response_decision=response_decision,
        action_mode=action_mode,
    )
    return contract, tool_plan, response_decision


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

    assert {violation["type"] for violation in violations} == {
        "order_complete_without_quick_order_tool",
        "forbidden_template",
    }


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


@pytest.mark.parametrize(
    ("case_name", "intent", "known_slots", "expected"),
    (
        (
            "store_resolved_schedule_request",
            "quick_order_reservation",
            _purchase_slots(requested_cal_day=None, rsv_hour=None),
            {
                "flow_step": "show_schedule",
                "preferred_tool": "get_store_schedule_tool",
                "allowed_tools": {"get_store_schedule_tool", "get_multi_store_schedule_tool"},
                "forbidden_tools": {"quick_order_tool", "store_hours_instead_of_slots"},
                "template": TemplateName.DATE_PICK,
                "allowed_templates": {"datepick", "quickReply"},
                "forbidden_templates": {"preOrder", "orderComplete"},
            },
        ),
        (
            "datepick_slot_fill_requires_price_basis",
            "quick_order_reservation",
            _purchase_slots(),
            {
                "flow_step": "resolve_price",
                "preferred_tool": "get_final_price_tool",
                "allowed_tools": {"get_final_price_tool"},
                "forbidden_tools": {"quick_order_tool", "get_store_schedule_tool"},
                "template": TemplateName.QUICK_REPLY,
                "allowed_templates": {"quickReply"},
                "forbidden_templates": {"preOrder", "orderComplete"},
            },
        ),
        (
            "order_slots_complete_builds_preorder",
            "quick_order_reservation",
            _purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
            {
                "flow_step": "build_preorder",
                "preferred_tool": None,
                "allowed_tools": set(),
                "forbidden_tools": {"quick_order_tool", "get_store_schedule_tool"},
                "template": TemplateName.PRE_ORDER,
                "allowed_templates": {"preOrder"},
                "forbidden_templates": {"datepick", "orderComplete"},
            },
        ),
        (
            "preorder_confirm_executes_order_tool",
            "quick_order_execute",
            _purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
            {
                "flow_step": "execute_order",
                "preferred_tool": "quick_order_tool",
                "allowed_tools": {"quick_order_tool"},
                "forbidden_tools": {"get_store_schedule_tool", "transaction_store_preview_tool"},
                "template": TemplateName.ORDER_COMPLETE,
                "allowed_templates": {"orderComplete"},
                "forbidden_templates": {"datepick", "preOrder"},
                "required_violation": "order_complete_without_quick_order_tool",
            },
        ),
    ),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_purchase_reservation_preorder_transition_matrix(
    case_name: str,
    intent: str,
    known_slots: dict[str, object],
    expected: dict[str, object],
) -> None:
    contract, tool_plan, response_decision = _purchase_flow_contract(intent=intent, known_slots=known_slots)

    assert case_name
    assert contract.flow_step == expected["flow_step"]
    assert tool_plan.preferred_tool == expected["preferred_tool"]
    assert set(tool_plan.allowed_tools) == expected["allowed_tools"]
    assert set(expected["forbidden_tools"]).issubset(set(tool_plan.forbidden_tools))
    assert response_decision.template == expected["template"]

    for template in expected["allowed_templates"]:
        if template == "orderComplete":
            violations = response_contract_violations(
                template=template,
                response_shape_key=response_decision.metadata.get("response_shape_key"),
                called_tools=("quick_order_tool",),
                structured_sources=(("quick_order_tool", {"status": "success", "data": {}}),),
                contract=contract,
            )
            assert violations == []
        elif template == "preOrder":
            violations = response_contract_violations(
                template=template,
                assistant_response_source="code_reservation_confirmation_ready",
                response_shape_key=response_decision.metadata.get("response_shape_key"),
                called_tools=(),
                contract=contract,
            )
            assert violations == []
        else:
            assert violates_response_template_contract({"template": template}, contract) is False

    for template in expected["forbidden_templates"]:
        if template == "preOrder":
            violations = response_contract_violations(
                template=template,
                assistant_response_source="code_reservation_confirmation_ready",
                response_shape_key=response_decision.metadata.get("response_shape_key"),
                called_tools=(),
                contract=contract,
            )
            assert violations or violates_response_template_contract({"template": template}, contract)
        elif template == "orderComplete":
            violations = response_contract_violations(
                template=template,
                response_shape_key=response_decision.metadata.get("response_shape_key"),
                called_tools=(),
                contract=contract,
            )
            assert violations or violates_response_template_contract({"template": template}, contract)
        else:
            assert violates_response_template_contract({"template": template}, contract) is True

    required_violation = expected.get("required_violation")
    if required_violation:
        violation_template = "preOrder" if str(required_violation).startswith("preorder_") else "orderComplete"
        violations = response_contract_violations(
            template=violation_template,
            assistant_response_source="code_reservation_confirmation_ready",
            response_shape_key=response_decision.metadata.get("response_shape_key"),
            called_tools=(),
            contract=contract,
        )
        assert required_violation in {violation["type"] for violation in violations}


def test_reservation_policy_transition_matrix_blocks_preorder_and_owned_lookup_drift() -> None:
    frame = IntentFrame(
        domain=PolicyDomain.TRANSACTION,
        intent="reservation_window_policy",
        known_slots={
            **_purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
            "active_parent_flow": "reservation_preorder",
        },
    )
    tool_plan = plan_transaction_tools(frame)
    response_decision = decide_transaction_response(
        intent=frame.intent,
        user_text="How far out can I reserve installation?",
        known_slots=frame.known_slots,
    )
    contract = build_turn_contract(
        user_text="How far out can I reserve installation?",
        intent_frame=frame,
        tool_plan=tool_plan,
        response_decision=response_decision,
    )

    assert tool_plan.preferred_tool == "search_faq_hybrid_tool"
    assert "quick_order_tool" in contract.forbidden_tools
    assert "get_order_status_tool" in contract.forbidden_tools
    assert "get_store_schedule_tool" in contract.forbidden_tools
    assert response_decision.template == TemplateName.QUICK_REPLY
    assert violates_response_template_contract({"template": "datepick"}, contract) is True
    assert violates_response_template_contract({"template": "preOrder"}, contract) is True
    assert violates_response_template_contract({"template": "orderComplete"}, contract) is True
    assert violates_response_template_contract({"template": "quickReply"}, contract) is False


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


@pytest.mark.parametrize(
    ("case_name", "intent", "known_slots", "tool_result", "expected"),
    (
        (
            "pure_inventory_available",
            "inventory_availability",
            {
                "goods_no": "G000000309783",
                "tire_size": "225/45R17",
                "ord_qty": 4,
                "shop_id": "F00721",
                "stock_check_mode": "inventory_only",
            },
            {"available_qty": 8},
            {
                "template": TemplateName.LOCATION,
                "allowed_templates": {"location", "quickReply"},
                "forbidden_templates": {"datepick", "preOrder", "orderComplete"},
                "forbidden_behaviors": {"datepick_for_pure_inventory_flow", "preorder_for_pure_inventory_flow"},
            },
        ),
        (
            "preview_schedule_available",
            "inventory_availability",
            {
                "goods_no": "G000000309783",
                "tire_size": "225/45R17",
                "ord_qty": 4,
                "shop_id": "F00721",
                "stock_check_mode": "preview",
            },
            {"stores": [{"slots": [{"cal_day": "20260705", "tm": "1700"}]}]},
            {
                "template": TemplateName.DATE_PICK,
                "allowed_templates": {"datepick", "quickReply"},
                "forbidden_templates": {"preOrder", "orderComplete"},
                "forbidden_behaviors": {"hide_available_stock"},
            },
        ),
        (
            "unavailable_inventory",
            "inventory_availability",
            {
                "goods_no": "G000000309783",
                "tire_size": "225/45R17",
                "ord_qty": 4,
                "shop_id": "F00721",
                "stock_check_mode": "inventory_only",
            },
            {"available_qty": 0, "today_installable": False, "tna_available": False},
            {
                "template": TemplateName.QUICK_REPLY,
                "allowed_templates": {"quickReply"},
                "forbidden_templates": {"datepick", "preOrder", "orderComplete"},
                "forbidden_behaviors": {"datepick_for_unavailable_stock", "preorder_for_pure_inventory_flow"},
            },
        ),
    ),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_stock_transition_matrix(
    case_name: str,
    intent: str,
    known_slots: dict[str, object],
    tool_result: dict[str, object],
    expected: dict[str, object],
) -> None:
    contract, _, response_decision = _transaction_policy_contract(
        intent=intent,
        known_slots=known_slots,
        tool_result=tool_result,
        action_mode="stock_check",
    )

    assert case_name
    assert response_decision.template == expected["template"]
    assert set(expected["forbidden_behaviors"]).issubset(set(response_decision.forbidden_behaviors))

    for template in expected["allowed_templates"]:
        assert violates_response_template_contract({"template": template}, contract) is False
    for template in expected["forbidden_templates"]:
        assert violates_response_template_contract({"template": template}, contract) is True


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


def test_inventory_only_stock_blocks_booking_location_and_schedule_actions() -> None:
    contract, tool_plan, response_decision = _transaction_policy_contract(
        intent="stock_store_search",
        known_slots={
            "goods_no": "G000000309783",
            "tire_size": "205/55R16",
            "ord_qty": 4,
            "shop_id": "F00721",
            "shop_name": "T-Station Pangyo",
            "stock_check_mode": "inventory_only",
        },
        tool_result={"available_qty": 4, "today_installable": False, "tna_available": False},
        action_mode="stock_check",
    )

    assert tool_plan.preferred_tool == "get_store_inventory_tool"
    assert response_decision.metadata["stock_check_mode"] == "inventory_only"
    assert "transaction_store_preview_tool" in contract.forbidden_tools
    assert "get_store_schedule_tool" in contract.forbidden_tools
    assert "quick_order_tool" in contract.forbidden_tools
    assert violates_response_template_contract(
        {"template": "location", "data": {"isBookingFlow": True}},
        contract,
    ) is True
    assert violates_response_template_contract(
        {"template": "location", "data": {"isBookingFlow": False}},
        contract,
    ) is False
    assert violates_response_template_contract(
        {"template": "datepick", "called_tools": ["transaction_store_preview_tool"]},
        contract,
    ) is True
    violations = response_contract_violations(
        template="quickReply",
        called_tools=("transaction_store_preview_tool",),
        contract=contract,
    )
    violation_types = {violation["type"] for violation in violations}
    assert "forbidden_tool_for_contract" in violation_types
    assert "inventory_only_stock_action_tool_violation" in violation_types

def test_stock_product_resolution_contract_keeps_stock_owner_boundary() -> None:
    frame = IntentFrame(
        domain=PolicyDomain.DISCOVERY,
        intent="resolve_or_describe_product",
        known_slots={
            "product_name": "Ventus S2 AS",
            "tire_size": "205/55R16",
            "ord_qty": 4,
            "region": "Gangnam",
            "stock_check_mode": "inventory_only",
        },
    )
    contract = build_turn_contract(
        user_text="stock lookup after product resolution",
        intent_frame=frame,
        tool_plan=ToolPlan(
            allowed_tools=("search_product_tool", "get_store_list_tool"),
            preferred_tool="search_product_tool",
            metadata={"response_intent": "resolve_or_describe_product", "stock_check_mode": "inventory_only"},
        ),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.LIST,
            template=TemplateName.LOCATION,
            metadata={"response_shape_key": "stock_store_candidates", "stock_check_mode": "inventory_only"},
        ),
        action_mode="stock_check",
    )

    assert contract.domain == "transaction"
    assert contract.intent == "stock_store_search"
    assert contract.known_slots["stock_check_mode"] == "inventory_only"
    assert "transaction_store_preview_tool" in contract.forbidden_tools
    assert violates_response_template_contract(
        {"template": "location", "data": {"isBookingFlow": True}},
        contract,
    ) is True
    assert violates_response_template_contract(
        {"template": "location", "data": {"isBookingFlow": False}},
        contract,
    ) is False

def test_reservation_lookup_owns_response_over_stale_purchase_context() -> None:
    contract = build_turn_contract(
        user_text="reservation lookup",
        intent_frame=IntentFrame(
            domain=PolicyDomain.TRANSACTION,
            intent="reservation_status_lookup",
            known_slots={
                **_purchase_slots(goods_no=None, tire_size=None, shop_id=None),
                "pending_intent": "order",
                "goal_type": "place_order",
            },
        ),
        tool_plan=ToolPlan(
            allowed_tools=("quick_order_tool", "get_my_reservations_tool"),
            preferred_tool="quick_order_tool",
            required_slots=("product",),
            metadata={"response_intent": "quick_order_reservation"},
        ),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            metadata={"response_shape_key": "reservation_status_lookup"},
        ),
    )

    assert contract.intent == "reservation_status_lookup"
    assert contract.action_mode == "owned_record_lookup"
    assert contract.blocking_required_slots == ()
    assert contract.preferred_tool == "get_my_reservations_tool"
    assert "get_my_reservations_tool" in contract.allowed_tools
    assert "quick_order_tool" in contract.forbidden_tools
    assert "search_product_tool" in contract.forbidden_tools
    assert violates_response_template_contract({"template": "quickReply"}, contract) is False
    assert violates_response_template_contract({"template": "datepick"}, contract) is True

    guard_event = build_response_policy_guard_event(contract)

    assert guard_event["template"] == "quickReply"
    assert guard_event["assistant_response_source"] == "code_turn_contract_owned_record_guard"
    assert guard_event["contract_intent"] == "reservation_status_lookup"
    assert "상품" not in guard_event["data"]["assistantResponse"]

def test_purchase_region_slot_fill_requires_size_before_store_preview() -> None:
    contract, tool_plan, response_decision = _purchase_flow_contract(
        intent="quick_order_reservation",
        known_slots={
            "goods_no": "G000000309783",
            "product_name": "Ventus S2 AS",
            "ord_qty": 4,
            "region": "Gangnam",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
    )

    assert contract.flow_step == "ask_size"
    assert contract.blocking_required_slots == ("tire_size",)
    assert tool_plan.allowed_tools == ()
    assert "transaction_store_preview_tool" in tool_plan.forbidden_tools
    assert "get_store_schedule_tool" in tool_plan.forbidden_tools
    assert response_decision.template == TemplateName.QUICK_REPLY
    assert violates_response_template_contract(
        {"template": "location", "called_tools": ["transaction_store_preview_tool"]},
        contract,
    ) is True
    assert violates_response_template_contract({"template": "datepick"}, contract) is True

def test_store_search_contract_does_not_inherit_purchase_preview_boundary() -> None:
    contract, tool_plan, response_decision = _transaction_policy_contract(
        intent="store_search",
        known_slots={
            "goods_no": "G000000309783",
            "product_name": "Ventus S2 AS",
            "ord_qty": 4,
            "region": "Gangnam",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
        action_mode="store_search",
    )

    assert contract.intent == "store_search"
    assert contract.action_mode == "store_search"
    assert "transaction_store_preview_tool" not in contract.allowed_tools
    assert "transaction_store_preview_tool" in contract.forbidden_tools
    assert tool_plan.preferred_tool in {"search_stores_tool", "get_store_list_tool"}
    assert response_decision.template == TemplateName.QUICK_REPLY
    assert violates_response_template_contract({"template": "datepick"}, contract) is True
    assert violates_response_template_contract(
        {"template": "location", "data": {"isBookingFlow": False}},
        contract,
    ) is False
    assert violates_response_template_contract(
        {"template": "location", "data": {"isBookingFlow": True}},
        contract,
    ) is True

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


@pytest.mark.parametrize(
    ("case_name", "intent", "known_slots", "expected"),
    (
        (
            "open_store_search",
            "open_store_search",
            {"region": "Pangyo", "open_only": True},
            {
                "preferred_tool": "search_stores_complex_tool",
                "allowed_tools": {"search_stores_complex_tool", "search_stores_tool", "get_store_list_tool", "get_store_detail_tool"},
                "forbidden_tools": {"get_store_schedule_tool", "transaction_store_preview_tool"},
                "template": TemplateName.LOCATION,
            },
        ),
        (
            "store_service_search",
            "store_service_search",
            {"region": "Pangyo", "service_name": "tire storage", "service_codes": ("119",)},
            {
                "preferred_tool": "search_stores_tool",
                "allowed_tools": {"search_stores_tool", "get_store_list_tool"},
                "forbidden_tools": {"get_store_schedule_tool", "transaction_store_preview_tool", "quick_order_tool"},
                "template": TemplateName.LOCATION,
            },
        ),
    ),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_store_transition_matrix(
    case_name: str,
    intent: str,
    known_slots: dict[str, object],
    expected: dict[str, object],
) -> None:
    contract, tool_plan, response_decision = _transaction_policy_contract(
        intent=intent,
        known_slots=known_slots,
        action_mode="store_search",
    )

    assert case_name
    assert tool_plan.preferred_tool == expected["preferred_tool"]
    assert set(tool_plan.allowed_tools) == expected["allowed_tools"]
    assert set(expected["forbidden_tools"]).issubset(set(tool_plan.forbidden_tools))
    assert response_decision.template == expected["template"]
    assert violates_response_template_contract({"template": "location", "data": {"isBookingFlow": False}}, contract) is False
    assert violates_response_template_contract({"template": "location", "data": {"isBookingFlow": True}}, contract) is True
    assert violates_response_template_contract({"template": "datepick"}, contract) is True
    assert violates_response_template_contract({"template": "preOrder"}, contract) is True
    assert violates_response_template_contract({"template": "orderComplete"}, contract) is True


@pytest.mark.parametrize(
    ("parent_flow", "known_slots"),
    (
        ("purchase", _purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc")),
        (
            "stock",
            {
                "goods_no": "G000000309783",
                "tire_size": "225/45R17",
                "ord_qty": 4,
                "shop_id": "F00721",
                "stock_check_mode": "inventory_only",
            },
        ),
        ("store", {"region": "Pangyo", "store_name": "Pangyo Store"}),
    ),
)
def test_support_policy_matrix_keeps_parent_flow_dormant(parent_flow: str, known_slots: dict[str, object]) -> None:
    frame = IntentFrame(
        domain=PolicyDomain.SUPPORT,
        intent="general_cancel_fee_policy",
        known_slots={**known_slots, "active_parent_flow": parent_flow},
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
    assert contract.action_mode == "support_policy_answer"
    assert "search_faq_hybrid_tool" in contract.allowed_tools
    assert "quick_order_tool" in contract.forbidden_tools
    assert "get_store_schedule_tool" in contract.forbidden_tools
    assert violates_response_template_contract({"template": "quickReply"}, contract) is False
    assert violates_response_template_contract({"template": "location"}, contract) is True
    assert violates_response_template_contract({"template": "datepick"}, contract) is True
    assert violates_response_template_contract({"template": "preOrder"}, contract) is True
    assert violates_response_template_contract({"template": "orderComplete"}, contract) is True


def test_support_turn_dormants_purchase_until_explicit_resume_anchor() -> None:
    active_purchase = commit_flow_state(
        None,
        _purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
        source="transition_matrix:purchase_active",
        flow_type="purchase",
        flow_step="build_preorder",
        status="active",
    ).state.to_active_flow_context()
    dormant_flows = upsert_dormant_flow([], active_purchase)

    support_contract = build_turn_contract(
        user_text="cancel fee policy",
        intent_frame=IntentFrame(
            domain=PolicyDomain.SUPPORT,
            intent="general_cancel_fee_policy",
            known_slots={**_purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"), "active_parent_flow": "purchase"},
        ),
        tool_plan=ToolPlan(
            allowed_tools=("quick_order_tool", "search_faq_hybrid_tool"),
            preferred_tool="quick_order_tool",
        ),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("personal_order_lookup",),
            metadata={"response_shape_key": "general_cancel_fee_policy_summary"},
        ),
    )

    assert dormant_flows
    assert dormant_flows[0]["context"]["status"] == "dormant"
    assert violates_response_template_contract({"template": "preOrder"}, support_contract) is True
    assert violates_response_template_contract({"template": "orderComplete"}, support_contract) is True

    weak_resume = resume_dormant_flow(
        None,
        dormant_flows,
        resume_anchor={"pending_intent": "order", "goal_type": "place_order"},
        source="transition_matrix:weak_metadata",
    )
    assert weak_resume.status == "not_found"

    explicit_resume = resume_dormant_flow(
        None,
        dormant_flows,
        resume_anchor={"flow_type": "purchase", "goods_no": "G000000309783"},
        source="transition_matrix:explicit_purchase_resume",
    )
    assert explicit_resume.status == "resumed"
    assert explicit_resume.active_flow_context["status"] == "resumed"
    assert explicit_resume.active_flow_context["product"]["goods_no"] == "G000000309783"


def _policy_interrupt_contract(
    *,
    resume_source: str,
    known_slot_patch: dict[str, object],
    tool_args_patch: dict[str, object],
) -> TurnContract:
    return build_turn_contract(
        user_text="cancel fee policy",
        intent_frame=IntentFrame(
            domain=PolicyDomain.TRANSACTION,
            intent="quick_order_reservation_slot_fill",
            known_slots={
                **_purchase_slots(shop_id=None, shop_name=None, requested_cal_day=None, rsv_hour=None),
                **known_slot_patch,
                "active_parent_flow": "purchase",
            },
        ),
        routing_result=SimpleNamespace(
            domains=(PolicyDomain.TRANSACTION,),
            policy_intent="general_cancel_fee_policy",
            execution_plan=("transaction:quick_order_reservation_continue",),
            planner_confidence=0.95,
        ),
        tool_plan=ToolPlan(
            allowed_tools=("transaction_store_preview_tool", "quick_order_tool"),
            preferred_tool="transaction_store_preview_tool",
            tool_args_patch=tool_args_patch,
        ),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.LOCATION,
            template=TemplateName.LOCATION,
            metadata={"response_shape_key": "reservation_store_candidates"},
        ),
        action_mode="purchase_continuation",
        context_state="resumed",
        resume_source=resume_source,
        previous_pending_intent="order",
        previous_goal_type="place_order",
    )

def test_policy_interrupt_overrides_purchase_region_slot_fill_context() -> None:
    contract = _policy_interrupt_contract(
        resume_source="expected_slot_fill:region",
        known_slot_patch={"region": "cancel fee policy"},
        tool_args_patch={"region": "cancel fee policy"},
    )

    assert contract.domain == "support"
    assert contract.intent == "general_cancel_fee_policy"
    assert contract.action_mode == "support_policy_answer"
    assert contract.context_state == "dormant"
    assert contract.resume_source == "none"
    assert contract.dormant_context_reason == "support_turn"
    assert contract.known_slots["goods_no"] == "G000000309783"
    assert "region" not in contract.known_slots
    assert contract.resolved_context["store"]["region"]["source"] == "missing"
    assert "search_faq_hybrid_tool" in contract.allowed_tools
    assert "quick_order_tool" in contract.forbidden_tools
    assert violates_response_template_contract({"template": "location"}, contract) is True
    assert violates_response_template_contract({"template": "quickReply"}, contract) is False

def test_policy_interrupt_uses_code_frame_policy_intent_when_router_policy_is_none() -> None:
    contract = build_turn_contract(
        user_text="cancel fee policy",
        intent_frame=IntentFrame(
            domain=PolicyDomain.TRANSACTION,
            intent="general_cancel_fee_policy",
            sub_intent="cancel_fee_policy",
            known_slots={
                **_purchase_slots(shop_id=None, shop_name=None, requested_cal_day=None, rsv_hour=None),
                "region": "cancel fee policy",
                "active_parent_flow": "purchase",
            },
        ),
        routing_result=SimpleNamespace(
            domains=(PolicyDomain.TRANSACTION,),
            policy_intent="none",
            execution_plan=("transaction:quick_order_reservation:slot_fill:region",),
            planner_confidence=1.0,
        ),
        tool_plan=ToolPlan(
            allowed_tools=("transaction_store_preview_tool",),
            preferred_tool="transaction_store_preview_tool",
            tool_args_patch={"region": "cancel fee policy"},
        ),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.LOCATION,
            template=TemplateName.LOCATION,
            metadata={"response_shape_key": "reservation_store_candidates"},
        ),
        action_mode="purchase_continuation",
        context_state="resumed",
        resume_source="expected_slot_fill:region",
        previous_pending_intent="order",
        previous_goal_type="place_order",
    )

    assert contract.domain == "support"
    assert contract.intent == "general_cancel_fee_policy"
    assert contract.action_mode == "support_policy_answer"
    assert contract.context_state == "dormant"
    assert contract.resume_source == "none"
    assert contract.router_wins_applied is True
    assert contract.known_slots["goods_no"] == "G000000309783"
    assert "region" not in contract.known_slots
    assert "search_faq_hybrid_tool" in contract.allowed_tools
    assert "transaction_store_preview_tool" not in contract.allowed_tools
    assert "quick_order_tool" in contract.forbidden_tools
    assert violates_response_template_contract({"template": "location"}, contract) is True
    assert violates_response_template_contract({"template": "quickReply"}, contract) is False

def test_policy_interrupt_overrides_purchase_store_slot_fill_context() -> None:
    contract = _policy_interrupt_contract(
        resume_source="expected_slot_fill:store",
        known_slot_patch={"shop_name": "cancel fee policy", "store_name": "cancel fee policy"},
        tool_args_patch={"shop_name": "cancel fee policy", "store_name": "cancel fee policy"},
    )

    assert contract.domain == "support"
    assert contract.intent == "general_cancel_fee_policy"
    assert contract.action_mode == "support_policy_answer"
    assert contract.context_state == "dormant"
    assert contract.resume_source == "none"
    assert "shop_name" not in contract.known_slots
    assert "store_name" not in contract.known_slots
    assert contract.resolved_context["store"]["shop_name"]["source"] == "missing"
    assert "transaction_store_preview_tool" not in contract.allowed_tools
    assert "quick_order_tool" in contract.forbidden_tools
    assert violates_response_template_contract({"template": "location"}, contract) is True
    assert violates_response_template_contract({"template": "quickReply"}, contract) is False

def test_policy_interrupt_overrides_purchase_schedule_slot_fill_context() -> None:
    contract = _policy_interrupt_contract(
        resume_source="expected_slot_fill:schedule",
        known_slot_patch={"requested_cal_day": "20260705", "rsv_hour": "17"},
        tool_args_patch={"requested_cal_day": "20260705", "rsv_hour": "17"},
    )

    assert contract.domain == "support"
    assert contract.intent == "general_cancel_fee_policy"
    assert contract.action_mode == "support_policy_answer"
    assert contract.context_state == "dormant"
    assert contract.resume_source == "none"
    assert "requested_cal_day" not in contract.known_slots
    assert "rsv_hour" not in contract.known_slots
    assert contract.resolved_context["booking"]["requested_cal_day"]["source"] == "missing"
    assert "get_store_schedule_tool" in contract.forbidden_tools
    assert "quick_order_tool" in contract.forbidden_tools
    assert violates_response_template_contract({"template": "datepick"}, contract) is True
    assert violates_response_template_contract({"template": "quickReply"}, contract) is False

def test_policy_interrupt_dormant_purchase_requires_explicit_resume() -> None:
    active_purchase = commit_flow_state(
        None,
        _purchase_slots(shop_id=None, shop_name=None, requested_cal_day=None, rsv_hour=None),
        source="transition_matrix:purchase_awaiting_store",
        flow_type="purchase",
        flow_step="ask_store",
        status="active",
    ).state.to_active_flow_context()
    dormant_flows = upsert_dormant_flow([], active_purchase)

    support_followup = resume_dormant_flow(
        None,
        dormant_flows,
        resume_anchor={"pending_intent": "general_cancel_fee_policy"},
        source="transition_matrix:support_interrupt_followup",
    )
    assert support_followup.status == "not_found"

    explicit_resume = resume_dormant_flow(
        None,
        dormant_flows,
        resume_anchor={"flow_type": "purchase", "goods_no": "G000000309783"},
        source="transition_matrix:explicit_purchase_resume_after_interrupt",
    )
    assert explicit_resume.status == "resumed"
    assert explicit_resume.active_flow_context["status"] == "resumed"
    assert explicit_resume.active_flow_context["intent"]["sub_flow_type"] == "purchase"
    assert explicit_resume.active_flow_context["product"]["goods_no"] == "G000000309783"

def test_explicit_purchase_resume_after_interrupt_stops_at_missing_store_boundary() -> None:
    active_purchase = commit_flow_state(
        None,
        _purchase_slots(shop_id=None, shop_name=None, requested_cal_day=None, rsv_hour=None),
        source="transition_matrix:purchase_awaiting_store",
        flow_type="purchase",
        flow_step="ask_store",
        status="active",
    ).state.to_active_flow_context()
    dormant_flows = upsert_dormant_flow([], active_purchase)

    explicit_resume = resume_dormant_flow(
        None,
        dormant_flows,
        resume_anchor={"flow_type": "purchase", "goods_no": "G000000309783"},
        source="transition_matrix:explicit_purchase_resume_after_interrupt",
    )
    resumed_product = explicit_resume.active_flow_context["product"]
    contract, tool_plan, response_decision = _purchase_flow_contract(
        intent="quick_order_reservation_continue",
        known_slots={
            "goods_no": resumed_product["goods_no"],
            "product_name": resumed_product["product_name"],
            "tire_size": resumed_product["tire_size"],
            "ord_qty": resumed_product["ord_qty"],
            "pending_intent": "order",
            "goal_type": "place_order",
        },
    )

    assert explicit_resume.status == "resumed"
    assert tool_plan.preferred_tool is None
    assert tool_plan.metadata["flow_step"] == "ask_store"
    assert response_decision.template == TemplateName.QUICK_REPLY
    assert "quick_order_tool" in contract.forbidden_tools
    assert violates_response_template_contract({"template": "quickReply"}, contract) is False
    assert violates_response_template_contract({"template": "datepick"}, contract) is True
    assert violates_response_template_contract({"template": "preOrder"}, contract) is True
    assert violates_response_template_contract({"template": "orderComplete"}, contract) is True

def test_explicit_purchase_resume_after_interrupt_stops_at_missing_schedule_boundary() -> None:
    active_purchase = commit_flow_state(
        None,
        _purchase_slots(requested_cal_day=None, rsv_hour=None),
        source="transition_matrix:purchase_awaiting_schedule",
        flow_type="purchase",
        flow_step="show_schedule",
        status="active",
    ).state.to_active_flow_context()
    dormant_flows = upsert_dormant_flow([], active_purchase)

    explicit_resume = resume_dormant_flow(
        None,
        dormant_flows,
        resume_anchor={"flow_type": "purchase", "goods_no": "G000000309783"},
        source="transition_matrix:explicit_purchase_resume_after_interrupt",
    )
    resumed_product = explicit_resume.active_flow_context["product"]
    resumed_store = explicit_resume.active_flow_context["store"]
    contract, tool_plan, response_decision = _purchase_flow_contract(
        intent="quick_order_reservation_continue",
        known_slots={
            "goods_no": resumed_product["goods_no"],
            "product_name": resumed_product["product_name"],
            "tire_size": resumed_product["tire_size"],
            "ord_qty": resumed_product["ord_qty"],
            "shop_id": resumed_store["shop_id"],
            "shop_name": resumed_store["shop_name"],
            "pending_intent": "order",
            "goal_type": "place_order",
        },
    )

    assert explicit_resume.status == "resumed"
    assert tool_plan.preferred_tool == "get_store_schedule_tool"
    assert tool_plan.metadata["flow_step"] == "show_schedule"
    assert response_decision.template == TemplateName.DATE_PICK
    assert "get_store_schedule_tool" in contract.allowed_tools
    assert "quick_order_tool" in contract.forbidden_tools
    assert violates_response_template_contract({"template": "datepick"}, contract) is False
    assert violates_response_template_contract({"template": "preOrder"}, contract) is True
    assert violates_response_template_contract({"template": "orderComplete"}, contract) is True

def test_next_turn_new_product_clears_persisted_preorder_context() -> None:
    persisted_preorder = commit_flow_state(
        None,
        _purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
        source="transition_matrix:persist_preorder",
        flow_type="purchase",
        flow_step="build_preorder",
        status="active",
    ).state.to_active_flow_context()

    result = commit_flow_state(
        persisted_preorder,
        {
            "product_name": "Kinergy ST AS",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
        source="transition_matrix:next_turn_new_product",
        flow_type="purchase",
        status="active",
    )
    context = result.state.to_active_flow_context()

    assert context["product"]["product_name"] == "Kinergy ST AS"
    assert "goods_no" not in context["product"]
    assert "store" not in context
    assert "schedule" not in context
    assert "payment" not in context
    assert context["current_step"] == "resolve_product"
    assert context["next_tool"] == "search_product_tool"

    contract, _, _ = _purchase_flow_contract(
        intent="quick_order_reservation",
        known_slots={"product_name": "Kinergy ST AS", "pending_intent": "order", "goal_type": "place_order"},
    )
    assert violates_response_template_contract({"template": "preOrder"}, contract) is True
    assert violates_response_template_contract({"template": "orderComplete"}, contract) is True


def test_next_turn_support_context_does_not_promote_stale_preorder_template_metadata() -> None:
    result = commit_flow_state(
        {
            "pending_intent": "order",
            "goal_type": "place_order",
            "template_data": {
                "template": "preOrder",
                "metadata": {
                    "goodsNo": "G000000309783",
                    "pendingIntent": "order",
                    "goalType": "place_order",
                },
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
        source="transition_matrix:next_turn_support_policy",
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

    support_contract = build_turn_contract(
        user_text="cancel fee policy",
        intent_frame=IntentFrame(
            domain=PolicyDomain.SUPPORT,
            intent="general_cancel_fee_policy",
            known_slots={"pending_intent": "order", "goal_type": "place_order"},
        ),
        tool_plan=ToolPlan(
            allowed_tools=("quick_order_tool", "search_faq_hybrid_tool"),
            preferred_tool="quick_order_tool",
        ),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("personal_order_lookup",),
            metadata={"response_shape_key": "general_cancel_fee_policy_summary"},
        ),
    )

    assert "quick_order_tool" in support_contract.forbidden_tools
    assert violates_response_template_contract({"template": "preOrder"}, support_contract) is True
    assert violates_response_template_contract({"template": "orderComplete"}, support_contract) is True


def test_next_turn_stock_context_moves_to_purchase_only_with_explicit_purchase_intent() -> None:
    persisted_stock = commit_flow_state(
        None,
        {
            "goods_no": "G000000309783",
            "product_name": "Ventus S2 AS",
            "tire_size": "225/45R17",
            "ord_qty": 4,
            "shop_id": "F00721",
            "shop_name": "T-Station Pangyo",
            "pending_intent": "stock",
            "goal_type": "store_with_stock",
            "stock_check_mode": "inventory_only",
        },
        source="transition_matrix:persist_stock",
        flow_type="stock",
        flow_step="check_inventory",
        status="active",
    ).state.to_active_flow_context()

    stock_followup = commit_flow_state(
        persisted_stock,
        {"region": "Gangnam", "pending_intent": "stock", "goal_type": "store_with_stock"},
        source="transition_matrix:next_turn_stock_followup",
        flow_type="stock",
        status="active",
    ).state.to_active_flow_context()
    assert stock_followup["intent"]["sub_flow_type"] == "stock"
    assert stock_followup["intent"]["pending_intent"] == "stock"
    assert stock_followup["current_step"] == "check_inventory"

    purchase_resume = commit_flow_state(
        persisted_stock,
        {"pending_intent": "order", "goal_type": "place_order"},
        source="transition_matrix:next_turn_explicit_purchase",
        flow_type="purchase",
        status="active",
    ).state.to_active_flow_context()
    assert purchase_resume["intent"]["sub_flow_type"] == "purchase"
    assert purchase_resume["intent"]["pending_intent"] == "order"
    assert purchase_resume["product"]["goods_no"] == "G000000309783"
    assert purchase_resume["store"]["shop_id"] == "F00721"
    assert purchase_resume["current_step"] == "resolve_schedule"


@pytest.mark.parametrize(
    ("template", "allowed_event", "allowed_contract", "forbidden_event", "forbidden_contract"),
    (
        (
            "datepick",
            {"template": "datepick"},
            TurnContract(
                domain="transaction",
                intent="stock_store_search",
                known_slots={"stock_check_mode": "preview"},
                response_decision={"template": "datepick", "metadata": {"response_shape_key": "reservation_slots"}},
                action_mode="stock_check",
            ),
            {"template": "datepick"},
            TurnContract(
                domain="support",
                intent="general_cancel_fee_policy",
                response_decision={"template": "quickReply"},
                action_mode="support_policy_answer",
            ),
        ),
        (
            "preOrder",
            {"template": "preOrder"},
            TurnContract(
                domain="transaction",
                intent="quick_order_reservation",
                known_slots=_purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
                response_decision={"template": "preOrder"},
                action_mode="purchase_continuation",
                flow_step="build_preorder",
            ),
            {"template": "preOrder"},
            TurnContract(
                domain="transaction",
                intent="quick_order_reservation",
                known_slots=_purchase_slots(),
                response_decision={"template": "quickReply"},
                action_mode="purchase_continuation",
                flow_step="resolve_price",
            ),
        ),
        (
            "orderComplete",
            {"template": "orderComplete", "called_tools": ["quick_order_tool"]},
            TurnContract(
                domain="transaction",
                intent="quick_order_execute",
                known_slots=_purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
                response_decision={"template": "orderComplete"},
                action_mode="purchase_continuation",
                flow_step="execute_order",
            ),
            {"template": "orderComplete"},
            TurnContract(
                domain="transaction",
                intent="quick_order_reservation",
                known_slots=_purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
                response_decision={"template": "preOrder"},
                action_mode="purchase_continuation",
                flow_step="build_preorder",
            ),
        ),
        (
            "product",
            {
                "template": "product",
                "source_domain": "discovery",
                "called_tools": ["search_product_tool"],
                "data": {"products": [{"titleProductName": "Ventus S2 AS", "titleTires": "225/45R17"}]},
            },
            TurnContract(
                domain="discovery",
                intent="product_search",
                response_decision={
                    "template": "product",
                    "forbidden_behaviors": ["product_card_without_size", "price_without_size"],
                },
            ),
            {"template": "product"},
            TurnContract(
                domain="transaction",
                intent="price_or_coupon_check",
                response_decision={"template": "quickReply", "forbidden_behaviors": ["price_without_size"]},
            ),
        ),
        (
            "location",
            {"template": "location", "data": {"isBookingFlow": False}},
            TurnContract(
                domain="transaction",
                intent="open_store_search",
                response_decision={"template": "location"},
                action_mode="store_search",
            ),
            {"template": "location", "data": {"isBookingFlow": True}},
            TurnContract(
                domain="transaction",
                intent="open_store_search",
                response_decision={"template": "location"},
                action_mode="store_search",
            ),
        ),
        (
            "voucher",
            {"template": "voucher"},
            TurnContract(
                domain="transaction",
                intent="owned_coupon_lookup",
                response_decision={"template": "voucher"},
                action_mode="owned_record_lookup",
            ),
            {"template": "voucher"},
            TurnContract(
                domain="transaction",
                intent="price_or_coupon_check",
                response_decision={"template": "quickReply", "forbidden_behaviors": ["assert_coupon_without_tool_result"]},
            ),
        ),
    ),
)
def test_risky_template_contract_matrix_allows_and_blocks_by_contract_fields(
    template: str,
    allowed_event: dict[str, object],
    allowed_contract: TurnContract,
    forbidden_event: dict[str, object],
    forbidden_contract: TurnContract,
) -> None:
    assert template
    assert violates_response_template_contract(allowed_event, allowed_contract) is False
    assert violates_response_template_contract(forbidden_event, forbidden_contract) is True


def test_mapper_priority_event_is_subordinate_to_current_contract() -> None:
    mapper_event = {
        "template": "datepick",
        "assistant_response_source": "code_mapper",
        "called_tools": ["get_store_schedule_tool"],
        "data": {"assistantResponse": "Select a date."},
    }
    schedule_contract = TurnContract(
        domain="transaction",
        intent="quick_order_reservation",
        known_slots=_purchase_slots(),
        allowed_tools=("get_store_schedule_tool",),
        forbidden_tools=("quick_order_tool",),
        response_decision={"template": "datepick", "metadata": {"response_shape_key": "reservation_slots"}},
        action_mode="purchase_continuation",
        flow_step="show_schedule",
    )
    support_contract = TurnContract(
        domain="support",
        intent="general_cancel_fee_policy",
        allowed_tools=("search_faq_hybrid_tool",),
        forbidden_tools=("get_store_schedule_tool", "quick_order_tool"),
        response_decision={"template": "quickReply", "metadata": {"response_shape_key": "general_cancel_fee_policy"}},
        action_mode="support_policy_answer",
    )
    inventory_only_contract = TurnContract(
        domain="transaction",
        intent="stock_store_search",
        known_slots={
            "tire_size": "225/45R17",
            "goods_no": "G000000309783",
            "ord_qty": 4,
            "shop_id": "F00721",
            "pending_intent": "stock",
            "goal_type": "store_with_stock",
            "stock_check_mode": "inventory_only",
        },
        allowed_tools=("get_store_inventory_tool",),
        forbidden_tools=("get_store_schedule_tool", "quick_order_tool"),
        response_decision={
            "template": "location",
            "forbidden_behaviors": ("datepick_for_pure_inventory_flow", "preorder_for_pure_inventory_flow"),
            "metadata": {"response_shape_key": "stock_inventory_lookup"},
        },
        action_mode="stock_check",
    )

    assert violates_response_template_contract(mapper_event, schedule_contract) is False
    assert violates_response_template_contract(mapper_event, support_contract) is True
    assert violates_response_template_contract(mapper_event, inventory_only_contract) is True


def _assert_guard_event_does_not_carry_stale_template_context(event: dict[str, object]) -> None:
    assert event["template"] == "quickReply"
    assert event.get("contract_gate_result") == "blocked"

    data = event["data"]
    assert isinstance(data, dict)
    metadata = data["metadata"]
    assert isinstance(metadata, dict)
    turn_contract = metadata["turnContract"]
    assert isinstance(turn_contract, dict)
    known_slots = turn_contract["known_slots"]
    assert isinstance(known_slots, dict)

    stale_keys = {"template_data", "ui_action", "pending_intent", "goal_type", "pendingIntent", "goalType"}
    assert stale_keys.isdisjoint(known_slots)


def test_response_policy_guard_fallback_does_not_persist_stale_preorder_context() -> None:
    contract = TurnContract(
        domain="support",
        intent="general_cancel_fee_policy",
        known_slots={
            "pending_intent": "order",
            "goal_type": "place_order",
            "template_data": {
                "template": "preOrder",
                "data": {"metadata": {"pendingIntent": "order", "goalType": "place_order"}},
            },
            "ui_action": {
                "action_type": "select_schedule",
                "expected_contract_intent": "quick_order_reservation",
            },
        },
        response_decision={"template": "quickReply", "forbidden_behaviors": ["personal_order_lookup"]},
        action_mode="support_policy_answer",
    )

    event = build_response_policy_guard_event(contract)

    _assert_guard_event_does_not_carry_stale_template_context(event)
    assert event["source_domain"] == "support"
    assert event["data"]["metadata"]["contract_intent"] == "general_cancel_fee_policy"


def test_support_policy_guard_owns_response_over_stale_purchase_flow() -> None:
    contract = TurnContract(
        domain="support",
        intent="general_cancel_fee_policy",
        known_slots={
            **_purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
            "pending_intent": "order",
            "goal_type": "place_order",
            "region": "예약 취소 수수료 있어",
        },
        response_decision={
            "template": "quickReply",
            "forbidden_behaviors": [
                "resume_stale_transaction_flow",
                "start_owned_record_lookup",
                "normalize_as_purchase_or_schedule",
            ],
            "metadata": {"response_shape_key": "general_cancel_fee_policy"},
        },
        action_mode="support_policy_answer",
        context_state="dormant",
        dormant_context_reason="support_turn",
    )

    event = build_response_policy_guard_event(contract)

    assert event["template"] == "quickReply"
    assert event["source_domain"] == "support"
    assert event["assistant_response_source"] == "code_turn_contract_support_response_guard"
    assert event["data"]["metadata"]["contract_intent"] == "general_cancel_fee_policy"
    assert event["data"]["metadata"]["response_shape_key"] == "general_cancel_fee_policy"
    assert event["data"]["metadata"].get("flowId") is None
    assert "매장이나 지역" not in event["data"]["assistantResponse"]
    assert "구매를 진행" not in event["data"]["assistantResponse"]


def test_required_slot_clarification_fallback_does_not_persist_stale_order_complete_context() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="quick_order_execute",
        known_slots={
            "pending_intent": "order",
            "goal_type": "place_order",
            "template_data": {"template": "orderComplete"},
            "ui_action": {"action_type": "submit_order"},
        },
        required_slots=("order",),
        blocking_required_slots=("order",),
        response_decision={"template": "quickReply"},
        action_mode="purchase_continuation",
    )

    event = build_required_slot_clarification_event(contract)

    _assert_guard_event_does_not_carry_stale_template_context(event)
    assert event["source_domain"] == "transaction"
    assert event["data"]["metadata"]["requiredSlots"] == ["order"]


def test_order_complete_template_gate_requires_quick_order_tool_before_final_emit() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="quick_order_execute",
        known_slots=_purchase_slots(payment_amount=420000, price_basis="cheapest_final_prc"),
        allowed_tools=("quick_order_tool",),
        response_decision={"template": "orderComplete", "metadata": {"response_shape_key": "quick_order_execute"}},
        action_mode="purchase_continuation",
        flow_step="execute_order",
    )

    assert violates_response_template_contract({"template": "orderComplete"}, contract) is True
    assert violates_response_template_contract(
        {"template": "orderComplete", "called_tools": ["quick_order_tool"]},
        contract,
    ) is False

    violations = response_contract_violations(
        template="orderComplete",
        response_shape_key="quick_order_execute",
        called_tools=(),
        contract=contract,
    )

    assert "forbidden_template" in {violation["type"] for violation in violations}


def test_final_ui_action_metadata_normalizes_and_validates_before_persistence_boundary() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "data": {
            "assistantResponse": "Select a valid vehicle lookup action.",
            "quickReplies": [
                {"label": "4개", "domain": "TRANSACTION"},
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY", "cta_action": "enter_size"},
            ],
            "metadata": {"response_shape_key": "vehicle_tire_size_lookup"},
        },
    }
    contract = TurnContract(
        domain="discovery",
        intent="vehicle_tire_size_lookup",
        response_decision={"template": "quickReply", "metadata": {"response_shape_key": "vehicle_tire_size_lookup"}},
        action_mode="product_description",
    )

    changed = finalize_ui_action_metadata_for_contract(event, contract=contract)

    assert changed is True
    quick_replies = event["data"]["quickReplies"]
    assert [chip["label"] for chip in quick_replies] == ["사이즈 직접 입력"]
    assert quick_replies[0]["ui_action"]["action_type"] == "enter_size"
    assert quick_replies[0]["ui_action"]["expected_contract_intent"] == "vehicle_tire_size_lookup"
    assert event["data"]["metadata"]["ui_action_validation"] == "vehicle_tire_size_lookup"
