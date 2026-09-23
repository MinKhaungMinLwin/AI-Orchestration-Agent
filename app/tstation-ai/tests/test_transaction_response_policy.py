from services.tstation.policies.transaction_response_policy import decide_transaction_response
from services.tstation.policies.response_decision import ResponseShape, TemplateName


def test_tc003_today_install_nearby_stock_renders_location_candidates() -> None:
    decision = decide_transaction_response(
        intent="stock_store_search",
        user_text="dynapro HPX 오늘 장착 가능한 근처 매장 알려줘",
        known_slots={
            "product_name": "dynapro HPX",
            "goods_no": "1029384",
            "tire_size": "235/55R19",
            "lat": 37.4,
            "lng": 127.1,
        },
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.CLARIFY
    assert decision.metadata["response_shape_key"] == "missing_stock_search_slots"
    assert decision.metadata["missing_slots"] == ("quantity",)
    assert decision.required_slots == ()


def test_purchase_response_with_quantity_and_no_store_asks_store() -> None:
    decision = decide_transaction_response(
        intent="quick_order_reservation",
        user_text="벤투스 S2 AS 245/45R18 2개 구매할래",
        known_slots={
            "goods_no": "G000000312679",
            "tire_size": "245/45R18",
            "ord_qty": 2,
            "pending_intent": "order",
            "goal_type": "place_order",
            "tire_model": "벤투스 S2 AS",
        },
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.CLARIFY
    assert decision.metadata["flow_id"] == "purchase_order"
    assert decision.metadata["flow_step"] == "ask_store"
    assert decision.metadata["missing_slots"] == ("store",)
    assert "get_final_price_tool" in decision.forbidden_behaviors
    assert "get_logistics_inventory_tool" in decision.forbidden_behaviors


def test_price_or_coupon_response_blocks_schedule_reprompt() -> None:
    decision = decide_transaction_response(
        intent="price_or_coupon_check",
        user_text="할인은 어떻게 적용된거야?",
        known_slots={
            "goods_no": "G000000309856",
            "tire_size": "275/35R20",
            "ord_qty": 4,
            "shop_id": "F00721",
            "requested_cal_day": "20260707",
            "rsv_hour": "16",
        },
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "price_or_coupon_check"
    assert "datepick_for_price_or_coupon_check" in decision.forbidden_behaviors

def test_purchase_response_with_product_family_only_prefers_product_card_clarify() -> None:
    decision = decide_transaction_response(
        intent="quick_order_reservation",
        user_text="벤투스 에어S 245/45R19 4개 분당정자점에서 주문할래",
        known_slots={
            "product_name": "벤투스 에어S",
            "tire_size": "245/45R19",
            "ord_qty": 4,
            "store_name": "분당정자점",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
    )

    assert decision.template == TemplateName.PRODUCT
    assert decision.response_shape == ResponseShape.CARD
    assert decision.metadata["flow_step"] == "resolve_product"
    assert decision.metadata["clarify_template"] == "product"


def test_purchase_response_without_product_name_keeps_quickreply_fallback() -> None:
    decision = decide_transaction_response(
        intent="quick_order_reservation",
        user_text="245/45R19 4개 분당정자점에서 주문할래",
        known_slots={
            "tire_size": "245/45R19",
            "ord_qty": 4,
            "store_name": "분당정자점",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.CLARIFY
    assert decision.metadata["flow_step"] == "resolve_product"
    assert decision.metadata["missing_slots"] == ("product",)
    assert "clarify_template" not in decision.metadata


def test_purchase_response_with_store_and_no_quantity_asks_quantity() -> None:
    decision = decide_transaction_response(
        intent="quick_order_reservation",
        user_text="벤투스 S2 AS 245/45R18 한남점에서 구매할래",
        known_slots={
            "goods_no": "G000000312679",
            "tire_size": "245/45R18",
            "store_name": "한남점",
            "pending_intent": "order",
            "goal_type": "place_order",
            "tire_model": "벤투스 S2 AS",
        },
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["flow_step"] == "ask_quantity"
    assert decision.metadata["missing_slots"] == ("quantity",)


def test_purchase_response_with_region_shows_store_candidates() -> None:
    decision = decide_transaction_response(
        intent="quick_order_reservation",
        user_text="벤투스 S2 AS 245/45R18 2개 분당에서 구매할래",
        known_slots={
            "goods_no": "G000000312679",
            "tire_size": "245/45R18",
            "ord_qty": 2,
            "region": "분당",
            "pending_intent": "order",
            "goal_type": "place_order",
            "tire_model": "벤투스 S2 AS",
        },
    )

    assert decision.template == TemplateName.LOCATION
    assert decision.response_shape == ResponseShape.LOCATION
    assert decision.metadata["flow_step"] == "show_store_candidates"
    assert decision.metadata["response_shape_key"] == "reservation_store_candidates"


def test_tc031_product_named_stock_request_asks_for_all_missing_slots() -> None:
    decision = decide_transaction_response(
        intent="stock_store_search",
        user_text="파주 시청 근처 더타이어샵 매장에 iON evo 재고 있을까? 오늘 당장 장착해야 하는데",
        known_slots={"product_name": "iON evo", "place": "파주 시청"},
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.CLARIFY
    assert decision.metadata["response_shape_key"] == "missing_stock_search_slots"
    assert decision.metadata["missing_slots"] == ("tire_size", "quantity")
    assert decision.required_slots == ()


def test_tc049_invalid_gangnam_store_does_not_show_datepick() -> None:
    decision = decide_transaction_response(
        intent="store_schedule",
        user_text="강남점에 방문해서 서비스 받고 싶은데, 예약 가능한 시간이 언제야?",
        known_slots={"store_name": "강남점", "store_exact_match": False, "booking_type": "store_visit"},
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.CLARIFY
    assert decision.metadata["response_shape_key"] == "unverified_store_schedule_lookup"
    assert decision.required_slots == ()
    assert "datepick_for_unverified_store" in decision.forbidden_behaviors
    assert "pretend_store_exists" in decision.forbidden_behaviors


def test_tc058_noon_request_keeps_datepick_but_blocks_noon_slot() -> None:
    decision = decide_transaction_response(
        intent="store_schedule",
        user_text="12시에 작업 가능한 서울 지역 매장 있을까요?",
        known_slots={"region": "서울", "booking_type": "store_visit"},
    )

    assert decision.template == TemplateName.DATE_PICK
    assert decision.response_shape == ResponseShape.DATE_PICK
    assert decision.metadata["response_shape_key"] == "time_filtered_schedule"
    assert decision.forbidden_behaviors == ("show_blocked_noon_slot",)


def test_tc219_unavailable_inventory_must_not_progress_to_schedule() -> None:
    decision = decide_transaction_response(
        intent="inventory_availability",
        user_text="이거 판교점에 지금 재고 있어?",
        known_slots={
            "product_name": "iON evo AS",
            "tire_size": "235/35R20",
            "quantity": 4,
            "store_name": "판교점",
        },
        tool_result={
            "available_qty": 0,
            "today_installable": False,
            "tna_available": False,
        },
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.NO_RESULT
    assert decision.metadata["response_shape_key"] == "stock_unavailable"
    assert "say_available_when_stock_zero" in decision.forbidden_behaviors
    assert "datepick_for_unavailable_stock" in decision.forbidden_behaviors


def test_inventory_tool_arrays_with_stock_are_available() -> None:
    decision = decide_transaction_response(
        intent="inventory_availability",
        user_text="이거 역삼점에 지금 재고 있어?",
        known_slots={
            "product_name": "iON evo",
            "quantity": 2,
            "store_name": "역삼점",
        },
        tool_result={
            "todayShopArray": [{"shopId": "F00098"}],
            "tnaShopArray": [],
        },
    )

    assert decision.template == TemplateName.LOCATION
    assert decision.response_shape == ResponseShape.LOCATION
    assert decision.metadata["response_shape_key"] == "stock_available"


def test_store_specific_stock_request_requires_quantity_before_location() -> None:
    decision = decide_transaction_response(
        intent="stock_store_search",
        user_text="이거 판교점에 재고 있어?",
        known_slots={
            "product_name": "iON evo",
            "goods_no": "G000000319451",
            "tire_size": "235/35R20",
            "store_name": "판교점",
        },
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.CLARIFY
    assert decision.metadata["response_shape_key"] == "missing_stock_search_slots"
    assert decision.metadata["missing_slots"] == ("quantity",)
    assert decision.required_slots == ()


def test_general_cancel_fee_policy_response_contract_prefers_summary() -> None:
    decision = decide_transaction_response(
        intent="general_cancel_fee_policy",
        user_text="예약 취소하면 비용이 발생하나요?",
        known_slots={"general_cancel_fee_policy": True},
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "general_cancel_fee_policy_summary"
    assert "personal_order_lookup" in decision.forbidden_behaviors
    assert "cancel_detail_only_guidance" in decision.forbidden_behaviors


def test_owned_order_cancel_fee_inquiry_response_contract_stays_order_specific() -> None:
    decision = decide_transaction_response(
        intent="owned_order_cancel_fee_inquiry",
        user_text="내 오늘 예약 취소하면 수수료 있어?",
        known_slots={"owned_order_cancel_fee_inquiry": True},
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "owned_order_cancel_fee_inquiry_summary"
    assert "normalize_as_cancel_request" in decision.forbidden_behaviors
    assert "arbitrary_past_order_fee_answer" in decision.forbidden_behaviors


def test_tc231_missing_size_does_not_build_null_order_summary() -> None:
    decision = decide_transaction_response(
        intent="quick_order_reservation",
        user_text="키너지 ST AS 2개 서초점 오늘 장착 가능?",
        known_slots={"product_name": "키너지 ST AS", "quantity": 2, "store_name": "서초점"},
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.CLARIFY
    assert decision.metadata["response_shape_key"] == "missing_order_slots"
    assert decision.metadata["missing_slots"] == ("tire_size",)
    assert decision.required_slots == ("tire_size",)
    assert "quick_order_tool" in decision.forbidden_behaviors
    assert "get_store_schedule_tool" in decision.forbidden_behaviors


def test_reservation_request_requires_quantity_when_product_size_store_are_known() -> None:
    decision = decide_transaction_response(
        intent="quick_order_reservation",
        user_text="키너지 ST AS 서초점 예약해줘",
        known_slots={
            "product_name": "키너지 ST AS",
            "goods_no": "G000000319451",
            "tire_size": "205/55R17",
            "store_name": "서초점",
            "shop_id": "T00077",
        },
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.CLARIFY
    assert decision.metadata["response_shape_key"] == "missing_order_slots"
    assert decision.metadata["missing_slots"] == ("quantity",)
    assert decision.required_slots == ("quantity",)


def test_tc233_complete_product_quantity_store_request_shows_reservation_slots() -> None:
    decision = decide_transaction_response(
        intent="quick_order_reservation",
        user_text="dynapro hpx 4개 티스테이션 오목천점 예약해줘",
        known_slots={
            "product_name": "dynapro HPX",
            "goods_no": "1029384",
            "tire_size": "235/55R19",
            "quantity": 4,
            "shop_id": "T01234",
            "store_name": "티스테이션 오목천점",
        },
    )

    assert decision.template == TemplateName.DATE_PICK
    assert decision.response_shape == ResponseShape.DATE_PICK
    assert decision.metadata["response_shape_key"] == "reservation_slots"
    assert decision.required_slots == ("booking_datetime",)
    assert "quick_order_tool" in decision.forbidden_behaviors
    assert "get_final_price_tool" in decision.forbidden_behaviors
