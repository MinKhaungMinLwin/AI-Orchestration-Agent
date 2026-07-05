from __future__ import annotations

from services.tstation.policies.flow_controller import resolve_purchase_order_flow
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
