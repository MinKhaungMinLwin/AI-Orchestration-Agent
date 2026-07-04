from services.tstation.policies.flow_controller import (
    build_purchase_flow_fallback_event,
    resolve_purchase_order_flow,
)
from services.tstation.policies.transaction_intent_policy import build_transaction_intent_frame, plan_transaction_tools


def _comparison_slots() -> dict:
    return {
        "comparison_context": {
            "product_candidates": [
                {
                    "goods_no": "G-CMP-1",
                    "product_name": "Dynapro HPX",
                    "tire_size": "235/55R19",
                },
                {
                    "goods_no": "G-CMP-2",
                    "product_name": "Dynapro HP3",
                    "tire_size": "235/55R19",
                },
            ],
            "compare_metric": "detail",
            "source": "code_product_compare_resolver",
        }
    }


def test_purchase_after_comparison_requires_scoped_product_selection() -> None:
    state = resolve_purchase_order_flow(intent="quick_order_reservation", known_slots=_comparison_slots())

    assert state is not None
    assert state.flow_step == "select_compared_product"
    assert state.allowed_tools == ()
    assert state.preferred_tool is None
    assert "search_product_tool" in state.forbidden_tools
    assert state.response_shape_key == "comparison_purchase_product_selection"


def test_purchase_after_comparison_uses_explicit_compared_candidate() -> None:
    slots = {**_comparison_slots(), "tire_model": "Dynapro HPX"}

    state = resolve_purchase_order_flow(intent="quick_order_reservation", known_slots=slots)

    assert state is not None
    assert state.flow_step == "ask_quantity"
    assert state.slot_patch["goods_no"] == "G-CMP-1"
    assert state.slot_patch["tire_size"] == "235/55R19"


def test_transaction_plan_blocks_broad_product_search_after_comparison_purchase() -> None:
    frame = build_transaction_intent_frame("구매", known_slots=_comparison_slots())
    plan = plan_transaction_tools(frame)

    assert frame.intent == "quick_order_reservation"
    assert plan.allowed_tools == ()
    assert plan.preferred_tool is None
    assert "search_product_tool" in plan.forbidden_tools
    assert plan.metadata["flow_step"] == "select_compared_product"
    assert plan.metadata["flow_response_shape_key"] == "comparison_purchase_product_selection"


def test_comparison_purchase_fallback_returns_only_compared_candidates() -> None:
    event = build_purchase_flow_fallback_event(intent="quick_order_reservation", known_slots=_comparison_slots())

    assert event is not None
    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "code_purchase_comparison_boundary"
    assert event["data"]["metadata"]["flowStep"] == "select_compared_product"

    quick_replies = event["data"]["quickReplies"]
    assert [reply["label"] for reply in quick_replies] == ["Dynapro HPX 235/55R19", "Dynapro HP3 235/55R19"]
    assert [reply["metadata"]["ui_action"]["slots"]["goods_no"] for reply in quick_replies] == [
        "G-CMP-1",
        "G-CMP-2",
    ]
