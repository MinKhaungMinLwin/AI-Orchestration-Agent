from services.tstation.policies.contract_required_tool_candidate import _contract_required_tool_candidate
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
