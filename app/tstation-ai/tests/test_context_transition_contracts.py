from __future__ import annotations

import pytest

from services.tstation.policies.flow_controller import resolve_purchase_order_flow
from services.tstation.policies.flow_state import commit_flow_state, resume_dormant_flow, upsert_dormant_flow
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
