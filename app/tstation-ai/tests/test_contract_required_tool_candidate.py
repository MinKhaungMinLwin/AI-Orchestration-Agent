from schemas.tstation.slots import ConversationSlots
from services.tstation.policies.contract_required_tool_candidate import (
    _contract_required_tool_candidate,
    _is_contract_required_selected_store_schedule,
)
from services.tstation.policies.turn_contract import TurnContract


def test_discovery_candidate_preserves_preferred_tool_and_args_patch() -> None:
    contract = TurnContract(
        domain="discovery",
        intent="product_search",
        allowed_tools=("search_product_tool",),
        preferred_tool="search_product_tool",
        tool_args_patch={"keyword": "Kinergy EX", "limit": 3},
        context_state="active",
    )

    candidate = _contract_required_tool_candidate(
        turn_contract=contract,
        user_text="Kinergy EX",
        merged_slots=None,
    )

    assert candidate is not None
    assert candidate.tool_name == "search_product_tool"
    assert candidate.tool_input == {"keyword": "Kinergy EX", "limit": 3}
    assert candidate.tool_input_source == "turn_contract_tool_args_patch"


def test_forbidden_tool_suppresses_candidate_creation() -> None:
    contract = TurnContract(
        domain="discovery",
        intent="product_search",
        allowed_tools=("search_product_tool",),
        forbidden_tools=("search_product_tool",),
        preferred_tool="search_product_tool",
        tool_args_patch={"keyword": "Kinergy EX"},
        context_state="active",
    )

    candidate = _contract_required_tool_candidate(
        turn_contract=contract,
        user_text="Kinergy EX",
        merged_slots=None,
    )

    assert candidate is None


def test_product_resolve_candidate_uses_known_goods_no() -> None:
    contract = TurnContract(
        domain="discovery",
        intent="product_detail",
        known_slots={"goods_no": "G000000309780"},
        allowed_tools=("get_product_description_tool",),
        preferred_tool="get_product_description_tool",
        context_state="active",
    )

    candidate = _contract_required_tool_candidate(
        turn_contract=contract,
        user_text="이 상품 자세히 알려줘",
        merged_slots=None,
    )

    assert candidate is not None
    assert candidate.tool_name == "get_product_description_tool"
    assert candidate.tool_input == {"goods_no": "G000000309780"}
    assert candidate.tool_input_source == "known_slots"


def test_stock_store_lookup_candidate_uses_contract_boundary() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="stock_store_search",
        known_slots={
            "goods_no": "G000000309780",
            "tire_size": "225/45R17",
            "ord_qty": 4,
            "region": "강남",
            "stock_check_mode": "inventory_only",
        },
        allowed_tools=("get_store_list_tool",),
        preferred_tool="get_store_list_tool",
        response_decision={
            "template": "location",
            "metadata": {"response_shape_key": "stock_inventory_lookup"},
        },
        context_state="active",
    )

    candidate = _contract_required_tool_candidate(
        turn_contract=contract,
        user_text="강남 재고 매장 찾아줘",
        merged_slots=None,
    )

    assert candidate is not None
    assert candidate.tool_name == "get_store_list_tool"
    assert candidate.tool_input_source == "turn_contract_required_stock_inventory_store_lookup"
    assert candidate.tool_input["region_code"] == "강남"


def test_plain_store_search_candidate_uses_contract_tool_args_patch() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="store_search",
        known_slots={"pending_intent": "order", "goal_type": "store_finder"},
        allowed_tools=("search_stores_tool", "get_store_list_tool"),
        forbidden_tools=("transaction_store_preview_tool", "get_store_schedule_tool"),
        preferred_tool="search_stores_tool",
        tool_args_patch={"region_code": "Gangnam"},
        response_decision={"template": "quickReply", "metadata": {"response_shape_key": "transaction_fallback"}},
        context_state="dormant",
    )

    candidate = _contract_required_tool_candidate(
        turn_contract=contract,
        user_text="find T-Station stores in Gangnam",
        merged_slots=None,
    )

    assert candidate is not None
    assert candidate.tool_name == "search_stores_tool"
    assert candidate.tool_input_source == "turn_contract_required_store_search"
    assert candidate.tool_input == {"region_code": "Gangnam"}


def test_order_status_lookup_candidate_uses_owned_record_boundary() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="order_arrival_status_lookup",
        known_slots={"pending_intent": "order_arrival_status_lookup", "owned_record_target": "order"},
        allowed_tools=("get_orders_of_user_tool", "get_order_status_tool"),
        forbidden_tools=("transaction_store_preview_tool", "get_store_schedule_tool"),
        preferred_tool="get_orders_of_user_tool",
        response_decision={"template": "quickReply", "metadata": {"response_shape_key": "order_arrival_status_lookup"}},
        context_state="dormant",
    )

    candidate = _contract_required_tool_candidate(
        turn_contract=contract,
        user_text="order delivery status",
        merged_slots=None,
    )

    assert candidate is not None
    assert candidate.tool_name == "get_orders_of_user_tool"
    assert candidate.tool_input == {}
    assert candidate.tool_input_source == "turn_contract_required_owned_record_lookup"


def test_purchase_store_preview_candidate_uses_contract_patch() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="quick_order_reservation",
        known_slots={
            "goods_no": "G000000309780",
            "tire_size": "225/45R17",
            "ord_qty": 4,
            "region": "강남",
        },
        allowed_tools=("transaction_store_preview_tool",),
        preferred_tool="transaction_store_preview_tool",
        tool_args_patch={"region": "분당", "include_price": True},
        response_decision={
            "template": "location",
            "metadata": {"response_shape_key": "reservation_store_candidates"},
        },
        action_mode="purchase_continuation",
        context_state="active",
    )

    candidate = _contract_required_tool_candidate(
        turn_contract=contract,
        user_text="분당으로 보여줘",
        merged_slots=None,
    )

    assert candidate is not None
    assert candidate.tool_name == "transaction_store_preview_tool"
    assert candidate.tool_input_source == "turn_contract_required_transaction_store_preview"
    assert candidate.tool_input["region"] == "분당"
    assert candidate.tool_input["include_price"] is True
    assert candidate.tool_input["quantity"] == 4


def test_purchase_store_preview_slot_fill_candidate_uses_contract_patch() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="quick_order_reservation_slot_fill_region",
        known_slots={
            "goods_no": "G000000309780",
            "product_name": "Ventus S2 AS",
            "tire_size": "205/55R16",
            "ord_qty": 4,
            "region": "Gangnam",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
        allowed_tools=("transaction_store_preview_tool",),
        preferred_tool="transaction_store_preview_tool",
        tool_args_patch={"region": "Gangnam", "pending_intent": "order", "goal_type": "place_order"},
        response_decision={
            "template": "location",
            "metadata": {"response_shape_key": "reservation_store_candidates"},
        },
        action_mode="purchase_continuation",
        context_state="resumed",
        resume_source="expected_slot_fill:region",
    )

    candidate = _contract_required_tool_candidate(
        turn_contract=contract,
        user_text="then order it",
        merged_slots=None,
    )

    assert candidate is not None
    assert candidate.tool_name == "transaction_store_preview_tool"
    assert candidate.tool_input_source == "turn_contract_required_transaction_store_preview"
    assert candidate.tool_input["goods_no"] == "G000000309780"
    assert candidate.tool_input["tire_size"] == "205/55R16"
    assert candidate.tool_input["quantity"] == 4
    assert candidate.tool_input["pending_intent"] == "order"
    assert candidate.tool_input["goal_type"] == "place_order"
    assert candidate.tool_input["sub_flow_type"] == "purchase"
    assert candidate.tool_input["stock_check_mode"] == "preview"


def test_purchase_price_progress_candidate_allows_final_price_tool() -> None:
    active_flow_context = {
        "flow_type": "commerce",
        "status": "active",
        "flow_step": "show_schedule",
        "product": {
            "goods_no": "G000000309780",
            "product_name": "Ventus S2 AS",
            "tire_size": "225/45R17",
            "ord_qty": 4,
        },
        "store": {"shop_id": "F00721", "shop_name": "T-Station Pangyo"},
        "schedule": {"requested_cal_day": "20260705", "rsv_hour": "17"},
        "intent": {"sub_flow_type": "purchase", "pending_intent": "order", "goal_type": "place_order"},
    }
    contract = TurnContract(
        domain="transaction",
        intent="quick_order_reservation",
        allowed_tools=("get_final_price_tool",),
        forbidden_tools=("quick_order_tool", "get_store_schedule_tool"),
        preferred_tool="get_final_price_tool",
        response_decision={
            "template": "quickReply",
            "metadata": {"response_shape_key": "reservation_price_lookup"},
        },
        action_mode="purchase_continuation",
        context_state="active",
    )

    candidate = _contract_required_tool_candidate(
        turn_contract=contract,
        user_text="ì´ ì¼ì •ìœ¼ë¡œ ì˜ˆì•½í•´ì¤˜",
        merged_slots=ConversationSlots(availability_context={"active_flow_context": active_flow_context}),
    )

    assert candidate is not None
    assert candidate.tool_name == "get_final_price_tool"
    assert candidate.tool_input == {"goods_no": "G000000309780"}
    assert candidate.tool_input_source == "flow_state_progress"


def test_selected_store_schedule_requires_datepick_contract_boundary() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="selected_store_schedule",
        allowed_tools=("get_store_schedule_tool",),
        response_decision={
            "template": "location",
            "metadata": {"response_shape_key": "reservation_store_candidates"},
        },
        context_state="active",
    )

    assert _is_contract_required_selected_store_schedule(contract, merged_slots=None) is False


def test_selected_store_schedule_rejects_forbidden_schedule_tool() -> None:
    contract = TurnContract(
        domain="transaction",
        intent="selected_store_schedule",
        allowed_tools=("get_store_schedule_tool",),
        forbidden_tools=("get_store_schedule_tool",),
        response_decision={
            "template": "datepick",
            "metadata": {"response_shape_key": "reservation_slots"},
        },
        context_state="active",
    )

    assert _is_contract_required_selected_store_schedule(contract, merged_slots=None) is False
