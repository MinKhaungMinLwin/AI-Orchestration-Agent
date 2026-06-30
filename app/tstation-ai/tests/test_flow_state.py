from __future__ import annotations

from services.tstation.policies.flow_state import commit_flow_state, commit_purchase_flow_state


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
    assert "store" not in context
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


def test_active_flow_type_transition_drops_previous_flow_context() -> None:
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
        {"rcmd_type": "comfort", "pending_intent": "product_recommendation", "goal_type": "recommend_tire"},
        source="flow_type_changed",
        flow_type="recommendation",
        flow_step="select_vehicle",
        status="active",
    )

    context = result.state.to_active_flow_context()
    assert context["flow_type"] == "recommendation"
    assert context["flow_step"] == "select_vehicle"
    assert context["recommendation"]["rcmd_type"] == "comfort"
    assert context["intent"]["pending_intent"] == "product_recommendation"
    assert "product" not in context
    assert "store" not in context
    assert "payment" not in context
    assert result.metadata["flow_state_conflicts"]["flow_type"] == {
        "existing": "purchase",
        "incoming": "recommendation",
    }
    assert "product.goods_no" in result.metadata["cleared_fields"]
    assert "store.shop_id" in result.metadata["cleared_fields"]
