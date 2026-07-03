from dataclasses import replace

from services.tstation.policies.response_decision import TemplateName
from services.tstation.policies.flow_state import purchase_context_vehicle_selection_patch
from services.tstation.policies import transaction_intent_policy as policy
from services.tstation.policies.transaction_intent_policy import (
    build_transaction_intent_frame,
    plan_transaction_tools,
)
from services.tstation.policies.transaction_response_policy import decide_transaction_response


def test_tc003_today_install_nearby_stock_intent_prefers_preview_tool() -> None:
    frame = build_transaction_intent_frame(
        "dynapro HPX 오늘 장착 가능한 근처 매장 알려줘",
        known_slots={
            "product_name": "dynapro HPX",
            "goods_no": "G000000309001",
            "tire_size": "235/55R19",
            "lat": 37.4,
            "lng": 127.1,
        },
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text="dynapro HPX 오늘 장착 가능한 근처 매장 알려줘",
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "stock_store_search"
    assert frame.sub_intent == "today_install"
    assert frame.entities["today_requested"] is True
    assert frame.missing_slots == ("quantity",)
    assert plan.preferred_tool == "transaction_store_preview_tool"
    assert plan.tool_args_patch["today_only"] is True
    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["missing_slots"] == ("quantity",)
    assert decision.required_slots == ()


def test_purchase_flow_with_quantity_and_no_store_resolves_to_ask_store() -> None:
    user_text = "벤투스 S2 AS 245/45R18 2개 구매할래"
    frame = build_transaction_intent_frame(
        user_text,
        known_slots={
            "goods_no": "G000000312679",
            "tire_size": "245/45R18",
            "ord_qty": 2,
            "pending_intent": "order",
            "goal_type": "place_order",
            "tire_model": "벤투스 S2 AS",
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "quick_order_reservation"
    assert plan.metadata["flow_id"] == "purchase_order"
    assert plan.metadata["flow_step"] == "ask_store"
    assert plan.allowed_tools == ()
    assert "get_final_price_tool" in plan.forbidden_tools
    assert "get_logistics_inventory_tool" in plan.forbidden_tools
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert "quick_order_tool" in plan.forbidden_tools


def test_cart_free_text_with_product_context_keeps_cart_sub_intent() -> None:
    frame = build_transaction_intent_frame(
        "장바구니에 넣어줘",
        known_slots={
            "goods_no": "G000000312679",
            "tire_size": "245/45R18",
            "tire_model": "벤투스 S2 AS",
            "pending_intent": "cart",
            "goal_type": "add_to_cart",
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "quick_order_reservation"
    assert frame.sub_intent == "cart"
    assert frame.missing_slots == ("quantity",)
    assert plan.allowed_tools == ()
    assert plan.metadata["flow_step"] == "ask_quantity"


def test_purchase_flow_with_store_and_no_quantity_resolves_to_ask_quantity() -> None:
    user_text = "벤투스 S2 AS 245/45R18 한남점에서 구매할래"
    frame = build_transaction_intent_frame(
        user_text,
        known_slots={
            "goods_no": "G000000312679",
            "tire_size": "245/45R18",
            "store_name": "한남점",
            "pending_intent": "order",
            "goal_type": "place_order",
            "tire_model": "벤투스 S2 AS",
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "quick_order_reservation"
    assert plan.metadata["flow_step"] == "ask_quantity"
    assert plan.allowed_tools == ()
    assert plan.metadata["flow_slots"]["store_name"] == "한남점"


def test_explicit_order_payload_with_labeled_store_and_schedule_stays_in_purchase_flow() -> None:
    user_text = "타이어 사이즈 2454519 / 차종 그랜저 / 수량: 4개 / 상품: 벤투스 air S(흡음재없는거) / 장착점: 티스테이션 분당정자점 / 장착일: 7월 4일 11시 / 이 정보대로 주문서 만들어 줘"
    frame = build_transaction_intent_frame(user_text, known_slots={})
    plan = plan_transaction_tools(frame)

    assert frame.intent == "quick_order_reservation"
    assert frame.sub_intent == "reservation"
    assert frame.known_slots["shop_name"] == "분당정자점"
    assert frame.known_slots["store_name"] == "분당정자점"
    assert frame.known_slots["product_name"] == "Ventus air S"
    assert frame.known_slots["ord_qty"] == 4
    assert plan.metadata["response_intent"] == "quick_order_reservation"
    assert "get_store_list_tool" not in plan.allowed_tools
    assert "get_store_detail_tool" not in plan.allowed_tools


def test_purchase_continuation_after_vehicle_selection_resolves_to_ask_quantity() -> None:
    frame = replace(
        build_transaction_intent_frame(
            "61거1836",
            known_slots={
                "goods_no": "G000000312679",
                "product_name": "Ventus S2 AS",
                "pending_product_name": "Ventus S2 AS",
                "tire_model": "Ventus S2 AS",
                "tire_size": "225/45R17",
                "car_no": "61거1836",
                "car_lnc_cd": "W036269",
                "pending_intent": "order",
                "goal_type": "place_order",
            },
        ),
        intent="quick_order_reservation_continue",
    )
    plan = plan_transaction_tools(frame)

    assert plan.metadata["response_intent"] == "quick_order_reservation_continue"
    assert plan.metadata["flow_id"] == "purchase_order"
    assert plan.metadata["flow_step"] == "ask_quantity"
    assert plan.required_slots == ("quantity",)
    assert plan.allowed_tools == ()


def test_purchase_vehicle_selection_patch_promotes_resolved_goods_no() -> None:
    patch = purchase_context_vehicle_selection_patch(
        parent_context={
            "pending_intent": "order",
            "goal_type": "place_order",
            "pending_product_name": "Ventus S2 AS",
        },
        selected_vehicle_slots={
            "car_no": "61거1836",
            "tire_size": "225/45R17",
        },
        current_slots={
            "goods_no": "G000000312679",
            "product_name": "Ventus S2 AS",
            "tire_model": "Ventus S2 AS",
        },
    )

    assert patch["goods_no"] == "G000000312679"
    assert patch["product_name"] == "Ventus S2 AS"
    assert patch["tire_model"] == "Ventus S2 AS"
    assert patch["tire_size"] == "225/45R17"


def test_purchase_flow_with_region_resolves_to_show_store_candidates() -> None:
    user_text = "벤투스 S2 AS 245/45R18 2개 분당에서 구매할래"
    frame = build_transaction_intent_frame(
        user_text,
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
    plan = plan_transaction_tools(frame)

    assert frame.intent == "quick_order_reservation"
    assert plan.metadata["flow_step"] == "show_store_candidates"
    assert plan.preferred_tool == "transaction_store_preview_tool"
    assert plan.allowed_tools == ("transaction_store_preview_tool",)


def test_purchase_flow_frame_missing_slots_uses_flow_controller_for_schedule_step() -> None:
    frame = build_transaction_intent_frame(
        "티스테이션 판교점",
        known_slots={
            "goods_no": "G000000312679",
            "tire_size": "245/45R18",
            "ord_qty": 2,
            "shop_id": "S001",
            "shop_name": "티스테이션 판교점",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "quick_order_reservation"
    assert frame.missing_slots == ("booking_datetime",)
    assert plan.metadata["flow_step"] == "show_schedule"
    assert plan.required_slots == ()
    assert plan.allowed_tools == ("get_store_schedule_tool", "get_multi_store_schedule_tool")
    assert plan.preferred_tool == "get_store_schedule_tool"


def test_purchase_flow_frame_missing_slots_clears_when_booking_is_ready() -> None:
    frame = build_transaction_intent_frame(
        "2026년 6월 27일 09:00",
        known_slots={
            "goods_no": "G000000312679",
            "tire_size": "245/45R18",
            "ord_qty": 2,
            "shop_id": "S001",
            "shop_name": "티스테이션 판교점",
            "requested_cal_day": "20260627",
            "rsv_hour": "0900",
            "payment_amount": 420000,
            "pending_intent": "order",
            "goal_type": "place_order",
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "quick_order_reservation"
    assert frame.missing_slots == ()
    assert plan.metadata["flow_step"] == "build_preorder"
    assert plan.allowed_tools == ()
    assert "quick_order_tool" in plan.forbidden_tools


def test_store_service_search_policy_uses_service_code_filter() -> None:
    frame = build_transaction_intent_frame("경기권에 타이어 보관해주는 매장 어디 있어?", known_slots={})
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text="경기권에 타이어 보관해주는 매장 어디 있어?",
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "store_service_search"
    assert frame.known_slots["region"] == "경기"
    assert frame.known_slots["service_codes"] == ("119",)
    assert plan.preferred_tool == "search_stores_tool"
    assert plan.tool_args_patch["svc_codes"] == ["119"]
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert decision.template == TemplateName.LOCATION
    assert decision.metadata["response_shape_key"] == "store_service_search"


def test_store_service_search_without_region_requires_region() -> None:
    frame = build_transaction_intent_frame("타이어 보관해주는 매장 어디 있어?", known_slots={})
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text="타이어 보관해주는 매장 어디 있어?",
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "store_service_search"
    assert frame.missing_slots == ("region",)
    assert plan.required_slots == ("region",)
    assert decision.required_slots == ("region",)


def test_router_structured_store_service_search_overrides_generic_store_search_text() -> None:
    user_text = "윈터 타이어 끼고 싶은데, 지금 장착중인 타이어 보관해주는 매장이 경기권에 어디어디 있어?"
    frame = build_transaction_intent_frame(
        user_text,
        known_slots={
            "policy_intent": "store_service_search",
            "service_name": "타이어 보관서비스",
            "service_code": "119",
            "service_codes": ("119",),
            "region": "경기",
            "place_query": "경기권",
        },
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text=user_text,
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "store_service_search"
    assert frame.known_slots["region"] == "경기"
    assert frame.known_slots["service_codes"] == ("119",)
    assert "requested_cal_day" not in frame.known_slots
    assert "availability_intent" not in frame.known_slots
    assert plan.allowed_tools == ("search_stores_tool", "get_store_list_tool")
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert "transaction_store_preview_tool" in plan.forbidden_tools
    assert "quick_order_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "store_service_search"


def test_specific_store_unknown_service_uses_store_attribute_inquiry_contract() -> None:
    user_text = "분당 정자점에서 세차 서비스도 하는 것 같은데 예약은 어디서 해?"
    frame = build_transaction_intent_frame(
        user_text,
        known_slots={
            "store_name": "분당 정자점",
            "place_query": "분당",
        },
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text=user_text,
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "store_attribute_inquiry"
    assert frame.known_slots["store_name"] == "분당 정자점"
    assert frame.known_slots["attribute_text"] == "세차 서비스 운영 여부"
    assert plan.allowed_tools == ("get_store_list_tool", "get_store_detail_tool")
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert "transaction_store_preview_tool" in plan.forbidden_tools
    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "store_attribute_inquiry"


def test_plain_store_info_lookup_allows_store_detail_tools() -> None:
    user_text = "티스테이션 한남점 전화번호 알려줘"
    frame = build_transaction_intent_frame(user_text, known_slots={})
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(intent=frame.intent, user_text=user_text, known_slots=dict(frame.known_slots))

    assert frame.intent == "plain_store_info_lookup"
    assert plan.allowed_tools == ("get_store_list_tool", "get_store_detail_tool")
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert "transaction_store_preview_tool" in plan.forbidden_tools
    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "plain_store_info_lookup"


def test_store_holiday_lookup_uses_store_detail_not_schedule() -> None:
    user_text = "한남점 이번주 일요일 영업해?"
    frame = build_transaction_intent_frame(user_text, known_slots={})
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(intent=frame.intent, user_text=user_text, known_slots=dict(frame.known_slots))

    assert frame.intent == "store_holiday_lookup"
    assert frame.known_slots["store_name"] == "한남점"
    assert plan.allowed_tools == ("get_store_list_tool", "get_store_detail_tool")
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert "transaction_store_preview_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "store_holiday_lookup"


def test_selected_store_hours_followup_uses_store_detail_not_schedule() -> None:
    user_text = "첫 번째 매장 영업시간 알려줘"
    frame = build_transaction_intent_frame(
        user_text,
        known_slots={
            "shop_id": "S001",
            "shop_name": "티스테이션 판교점",
            "store_name": "티스테이션 판교점",
            "pending_intent": "store_search",
            "goal_type": "store_finder",
        },
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(intent=frame.intent, user_text=user_text, known_slots=dict(frame.known_slots))

    assert frame.intent == "store_holiday_lookup"
    assert frame.known_slots["store_name"] == "티스테이션 판교점"
    assert plan.allowed_tools == ("get_store_list_tool", "get_store_detail_tool")
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert "transaction_store_preview_tool" in plan.forbidden_tools
    assert "quick_order_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "store_holiday_lookup"


def test_order_history_reorder_contract_uses_owned_order_tool_only() -> None:
    user_text = "지난번 주문한 타이어 다시 구매할래"
    frame = build_transaction_intent_frame(user_text, known_slots={})
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(intent=frame.intent, user_text=user_text, known_slots=dict(frame.known_slots))

    assert frame.intent == "order_history_reorder"
    assert frame.known_slots["owned_record_target"] == "order"
    assert plan.allowed_tools == ("get_orders_of_user_tool",)
    assert "quick_order_tool" in plan.forbidden_tools
    assert "search_product_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "order_history_reorder"


def test_order_history_lookup_contract_uses_owned_order_list_tool() -> None:
    user_text = "주문내역 보여줘"
    frame = build_transaction_intent_frame(user_text, known_slots={})
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(intent=frame.intent, user_text=user_text, known_slots=dict(frame.known_slots))

    assert frame.intent == "order_history_lookup"
    assert frame.sub_intent == "owned_order_list"
    assert frame.known_slots["pending_intent"] == "order_history_lookup"
    assert frame.known_slots["goal_type"] == "owned_record_lookup"
    assert plan.allowed_tools == ("get_orders_of_user_tool",)
    assert plan.preferred_tool == "get_orders_of_user_tool"
    assert "quick_order_tool" in plan.forbidden_tools
    assert "search_product_tool" in plan.forbidden_tools
    assert "get_final_price_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "order_history_lookup"


def test_order_history_page_navigation_does_not_promote_owned_order_list_lookup() -> None:
    frame = build_transaction_intent_frame("주문내역 페이지로 이동해줘", known_slots={})

    assert frame.intent != "order_history_lookup"


def test_general_cancel_fee_policy_uses_faq_only_contract() -> None:
    user_text = "예약 취소에 따른 위약금이 있는지 알려줘"
    frame = build_transaction_intent_frame(user_text, known_slots={})
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(intent=frame.intent, user_text=user_text, known_slots=dict(frame.known_slots))

    assert frame.intent == "general_cancel_fee_policy"
    assert frame.sub_intent == "cancel_fee_policy"
    assert frame.known_slots["pending_intent"] == "general_cancel_fee_policy"
    assert plan.allowed_tools == ("search_faq_hybrid_tool",)
    assert "get_my_reservations_tool" in plan.forbidden_tools
    assert "get_orders_of_user_tool" in plan.forbidden_tools
    assert "get_order_status_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "general_cancel_fee_policy_summary"


def test_general_cancel_fee_policy_interrupts_active_purchase_without_resuming_order_tools() -> None:
    user_text = "\uc608\uc57d \ucde8\uc18c \uc218\uc218\ub8cc \uc788\uc5b4?"
    frame = build_transaction_intent_frame(
        user_text,
        known_slots={
            "goods_no": "G000000312679",
            "tire_size": "245/45R18",
            "ord_qty": 2,
            "pending_intent": "order",
            "goal_type": "place_order",
            "tire_model": "Ventus S2 AS",
        },
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(intent=frame.intent, user_text=user_text, known_slots=dict(frame.known_slots))

    assert frame.intent == "general_cancel_fee_policy"
    assert frame.sub_intent == "cancel_fee_policy"
    assert frame.known_slots["pending_intent"] == "general_cancel_fee_policy"
    assert plan.allowed_tools == ("search_faq_hybrid_tool",)
    assert plan.preferred_tool == "search_faq_hybrid_tool"
    assert "transaction_store_preview_tool" not in plan.allowed_tools
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert "quick_order_tool" in plan.forbidden_tools
    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "general_cancel_fee_policy_summary"


def test_delivery_delay_reservation_schedule_policy_uses_faq_only_contract() -> None:
    user_text = "주문 다 했는데 배송 지연 되면 예약 일정도 자동으로 변경돼?"
    frame = build_transaction_intent_frame(user_text, known_slots={})
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(intent=frame.intent, user_text=user_text, known_slots=dict(frame.known_slots))

    assert frame.intent == "delivery_delay_reservation_schedule_policy"
    assert frame.sub_intent == "reservation_schedule_policy"
    assert frame.known_slots["pending_intent"] == "delivery_delay_reservation_schedule_policy"
    assert frame.known_slots["goal_type"] == "support_policy_answer"
    assert plan.allowed_tools == ("search_faq_hybrid_tool",)
    assert plan.preferred_tool == "search_faq_hybrid_tool"
    assert "get_my_reservations_tool" in plan.forbidden_tools
    assert "get_orders_of_user_tool" in plan.forbidden_tools
    assert "get_order_status_tool" in plan.forbidden_tools
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert "transaction_store_preview_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "delivery_delay_reservation_schedule_policy"


def test_delivery_delay_reservation_schedule_policy_overrides_owned_reservation_phrase() -> None:
    user_text = "주문하면서 매장, 일정 다 예약했는데, 배송이 지연되고 있다고 문자가 왔어. 내 예약도 자동으로 변경되나?"
    frame = build_transaction_intent_frame(
        user_text,
        known_slots={"comparison_context": {"product_names": ["아이온 에보 AS", "아이온 에보 AS SUV"]}},
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(intent=frame.intent, user_text=user_text, known_slots=dict(frame.known_slots))

    assert frame.intent == "delivery_delay_reservation_schedule_policy"
    assert frame.known_slots["goal_type"] == "support_policy_answer"
    assert plan.allowed_tools == ("search_faq_hybrid_tool",)
    assert "get_my_reservations_tool" in plan.forbidden_tools
    assert "get_orders_of_user_tool" in plan.forbidden_tools
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "delivery_delay_reservation_schedule_policy"


def test_reservation_window_policy_uses_faq_only_contract() -> None:
    user_text = "두달 뒤에도 예약 가능하지?"
    frame = build_transaction_intent_frame(user_text, known_slots={})
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(intent=frame.intent, user_text=user_text, known_slots=dict(frame.known_slots))

    assert frame.intent == "reservation_window_policy"
    assert frame.sub_intent == "reservation_window_policy"
    assert frame.known_slots["pending_intent"] == "reservation_window_policy"
    assert frame.known_slots["goal_type"] == "support_policy_answer"
    assert plan.allowed_tools == ("search_faq_hybrid_tool",)
    assert plan.preferred_tool == "search_faq_hybrid_tool"
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert "get_store_list_tool" in plan.forbidden_tools
    assert "get_my_reservations_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "reservation_window_policy"


def test_reservation_window_policy_overrides_stale_store_context() -> None:
    user_text = "강남점 두 달 뒤 예약 가능한 시간 보여줘"
    frame = build_transaction_intent_frame(
        user_text,
        known_slots={"pending_intent": "store_finder", "shop_name": "티스테이션 강남점"},
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "reservation_window_policy"
    assert frame.known_slots["goal_type"] == "support_policy_answer"
    assert plan.allowed_tools == ("search_faq_hybrid_tool",)
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert plan.required_slots == ()


def test_reservation_change_deadline_uses_window_policy_not_owned_lookup() -> None:
    user_text = "예약 변경은 언제까지 가능해?"
    frame = build_transaction_intent_frame(
        user_text,
        known_slots={
            "pending_intent": "order",
            "goal_type": "place_order",
            "shop_name": "티스테이션 판교점",
        },
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(intent=frame.intent, user_text=user_text, known_slots=dict(frame.known_slots))

    assert frame.intent == "reservation_window_policy"
    assert frame.sub_intent == "reservation_window_policy"
    assert frame.known_slots["goal_type"] == "support_policy_answer"
    assert plan.allowed_tools == ("search_faq_hybrid_tool",)
    assert plan.preferred_tool == "search_faq_hybrid_tool"
    assert "get_orders_of_user_tool" in plan.forbidden_tools
    assert "get_my_reservations_tool" in plan.forbidden_tools
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "reservation_window_policy"


def test_relative_reservation_date_keeps_store_schedule_lookup() -> None:
    user_text = "강남점 내일 예약 가능해?"
    frame = build_transaction_intent_frame(user_text, known_slots={})

    assert frame.intent != "reservation_window_policy"


def test_owned_order_cancel_fee_inquiry_uses_order_lookup_contract() -> None:
    user_text = "내 오늘 예약 취소하면 수수료 있어?"
    frame = build_transaction_intent_frame(user_text, known_slots={})
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(intent=frame.intent, user_text=user_text, known_slots=dict(frame.known_slots))

    assert frame.intent == "owned_order_cancel_fee_inquiry"
    assert frame.sub_intent == "cancel_fee"
    assert frame.known_slots["pending_intent"] == "owned_order_cancel_fee_inquiry"
    assert plan.allowed_tools == ("get_my_reservations_tool", "get_orders_of_user_tool", "get_order_status_tool")
    assert plan.preferred_tool == "get_my_reservations_tool"
    assert "search_faq_hybrid_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "owned_order_cancel_fee_inquiry_summary"


def test_order_number_cancel_fee_inquiry_prefers_order_status_tool() -> None:
    user_text = "O202606220019363 취소하면 위약금 있어?"
    frame = build_transaction_intent_frame(user_text, known_slots={})
    plan = plan_transaction_tools(frame)

    assert frame.intent == "owned_order_cancel_fee_inquiry"
    assert frame.known_slots["order_no"] == "O202606220019363"
    assert plan.preferred_tool == "get_order_status_tool"
    assert plan.tool_args_patch == {"query_no": "O202606220019363"}


def test_owned_reservation_status_lookup_still_wins_for_status_query() -> None:
    user_text = "내 예약 시간이 바뀌었는지 조회해줘"
    frame = build_transaction_intent_frame(user_text, known_slots={})
    plan = plan_transaction_tools(frame)

    assert frame.intent == "reservation_status_lookup"
    assert plan.preferred_tool == "get_my_reservations_tool"


def test_order_suffix_cancel_fee_inquiry_keeps_owned_anchor() -> None:
    user_text = "3708번 주문 취소하면 수수료 있어?"
    frame = build_transaction_intent_frame(user_text, known_slots={})
    plan = plan_transaction_tools(frame)

    assert frame.intent == "owned_order_cancel_fee_inquiry"
    assert frame.known_slots["order_no_suffix"] == "3708"
    assert plan.preferred_tool == "get_orders_of_user_tool"


def test_tomorrow_install_region_request_preserves_requested_cal_day(monkeypatch) -> None:
    monkeypatch.setattr(policy, "_kst_today", lambda: policy.datetime.date(2026, 6, 16))

    frame = build_transaction_intent_frame(
        "내일 장착 가능한 강남지역 매장",
        known_slots={
            "product_name": "다이나프로 HP3",
            "goods_no": "G000000320153",
            "tire_size": "255/50R19",
            "quantity": 2,
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "stock_store_search"
    assert frame.sub_intent == "today_install"
    assert frame.known_slots["region"] == "강남"
    assert frame.entities["requested_cal_day"] == "20260617"
    assert plan.preferred_tool == "transaction_store_preview_tool"
    assert plan.tool_args_patch["requested_cal_day"] == "20260617"


def test_today_install_initial_turn_stores_today_context(monkeypatch) -> None:
    monkeypatch.setattr(policy, "_kst_today", lambda: policy.datetime.date(2026, 6, 18))

    frame = build_transaction_intent_frame(
        "강남역 근처 오늘 장착하고 싶어",
        known_slots={
            "goods_no": "G000000317729",
            "tire_size": "235/55R19",
            "quantity": 4,
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "stock_store_search"
    assert frame.sub_intent == "today_install"
    assert frame.known_slots["availability_intent"] == "today_install"
    assert frame.known_slots["requested_cal_day"] == "20260618"
    assert plan.preferred_tool == "transaction_store_preview_tool"
    assert plan.tool_args_patch["requested_cal_day"] == "20260618"


def test_region_only_today_install_continuation_preserves_requested_cal_day(monkeypatch) -> None:
    monkeypatch.setattr(policy, "_kst_today", lambda: policy.datetime.date(2026, 6, 18))

    frame = build_transaction_intent_frame(
        "서울에는?",
        known_slots={
            "availability_intent": "today_install",
            "requested_cal_day": "20260618",
            "goods_no": "G000000317729",
            "tire_size": "235/55R19",
            "quantity": 4,
            "region": "강남",
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "stock_store_search"
    assert frame.sub_intent == "today_install"
    assert frame.known_slots["region"] == "서울"
    assert frame.known_slots["requested_cal_day"] == "20260618"
    assert plan.preferred_tool == "transaction_store_preview_tool"
    assert plan.tool_args_patch["region"] == "서울"
    assert plan.tool_args_patch["requested_cal_day"] == "20260618"


def test_region_recheck_today_install_continuation_preserves_requested_cal_day() -> None:
    frame = build_transaction_intent_frame(
        "서울 다시 확인",
        known_slots={
            "availability_intent": "today_install",
            "requested_cal_day": "20260618",
            "goods_no": "G000000317729",
            "tire_size": "235/55R19",
            "quantity": 4,
            "region": "서울",
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "stock_store_search"
    assert plan.tool_args_patch["region"] == "서울"
    assert plan.tool_args_patch["requested_cal_day"] == "20260618"


def test_other_store_today_install_continuation_preserves_requested_cal_day() -> None:
    frame = build_transaction_intent_frame(
        "다른 매장 찾기",
        known_slots={
            "availability_intent": "today_install",
            "requested_cal_day": "20260618",
            "goods_no": "G000000317729",
            "tire_size": "235/35R20",
            "quantity": 4,
            "region": "송파",
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "stock_store_search"
    assert frame.sub_intent == "today_install"
    assert frame.known_slots["goods_no"] == "G000000317729"
    assert frame.known_slots["region"] == "송파"
    assert frame.known_slots["requested_cal_day"] == "20260618"
    assert plan.preferred_tool == "transaction_store_preview_tool"
    assert plan.tool_args_patch["goods_no"] == "G000000317729"
    assert plan.tool_args_patch["quantity"] == 4
    assert plan.tool_args_patch["region"] == "송파"
    assert plan.tool_args_patch["requested_cal_day"] == "20260618"


def test_today_install_date_change_replaces_requested_cal_day(monkeypatch) -> None:
    monkeypatch.setattr(policy, "_kst_today", lambda: policy.datetime.date(2026, 6, 18))

    frame = build_transaction_intent_frame(
        "6월 20일에는?",
        known_slots={
            "availability_intent": "today_install",
            "requested_cal_day": "20260618",
            "goods_no": "G000000317729",
            "tire_size": "235/55R19",
            "quantity": 4,
            "region": "서울",
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "stock_store_search"
    assert frame.known_slots["requested_cal_day"] == "20260620"
    assert plan.tool_args_patch["requested_cal_day"] == "20260620"


def test_tc031_product_named_stock_request_requires_only_tire_size() -> None:
    frame = build_transaction_intent_frame(
        "파주 시청 근처 더타이어샵 매장에 iON evo 재고 있을까? 오늘 당장 장착해야 하는데",
        known_slots={"product_name": "iON evo", "region": "파주 시청"},
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text="파주 시청 근처 더타이어샵 매장에 iON evo 재고 있을까? 오늘 당장 장착해야 하는데",
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "stock_store_search"
    assert frame.missing_slots == ("tire_size", "quantity")
    assert plan.required_slots == ("tire_size", "quantity")
    assert plan.preferred_tool is None
    assert "transaction_store_preview_tool" in plan.forbidden_tools
    assert "get_store_inventory_tool" in plan.forbidden_tools
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["missing_slots"] == ("tire_size", "quantity")
    assert decision.required_slots == ()


def test_product_size_store_today_install_can_go_straight_to_preview() -> None:
    frame = build_transaction_intent_frame("iON evo AS 235/35R20 판교점 오늘 장착 가능해?")
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text="iON evo AS 235/35R20 판교점 오늘 장착 가능해?",
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "stock_store_search"
    assert frame.known_slots["product_name"] == "iON evo AS"
    assert frame.known_slots["tire_size"] == "235/35R20"
    assert frame.known_slots["store_name"] == "판교점"
    assert frame.missing_slots == ("quantity",)
    assert plan.preferred_tool == "transaction_store_preview_tool"
    assert plan.tool_args_patch["tire_size"] == "235/35R20"
    assert plan.tool_args_patch["store_name"] == "판교점"
    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["missing_slots"] == ("quantity",)
    assert decision.required_slots == ()


def test_stock_flow_future_schedule_request_promotes_preview_mode() -> None:
    frame = build_transaction_intent_frame(
        "다음주 중 장착 가능해?",
        known_slots={
            "goods_no": "G000000310126",
            "product_name": "다이나프로 HP3",
            "tire_size": "245/45R19",
            "ord_qty": 4,
            "region": "동탄",
            "pending_intent": "stock",
            "goal_type": "store_with_stock",
        },
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text="다음주 중 장착 가능해?",
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "stock_store_search"
    assert frame.sub_intent == "reservation"
    assert frame.known_slots["stock_check_mode"] == "preview"
    assert plan.preferred_tool == "transaction_store_preview_tool"
    assert plan.tool_args_patch["region"] == "동탄"
    assert decision.template == TemplateName.LOCATION
    assert decision.metadata["stock_check_mode"] == "preview"


def test_product_store_purchase_without_size_blocks_store_transaction_tools() -> None:
    frame = build_transaction_intent_frame("판교점에서 dynapro hpx 2개 구매하고싶어")
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text="판교점에서 dynapro hpx 2개 구매하고싶어",
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "quick_order_reservation"
    assert frame.known_slots["product_name"] == "Dynapro HPX"
    assert frame.known_slots["quantity"] == 2
    assert frame.known_slots["store_name"] == "판교점"
    assert frame.missing_slots == ("tire_size",)
    assert plan.preferred_tool is None
    assert "transaction_store_preview_tool" in plan.forbidden_tools
    assert "order_summary_with_null_required_fields" in plan.forbidden_tools
    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["missing_slots"] == ("tire_size",)
    assert decision.required_slots == ("tire_size",)


def test_plain_store_search_masks_stale_stock_slots() -> None:
    frame = build_transaction_intent_frame(
        "판교지역 매장 찾아줘",
        known_slots={
            "goods_no": "G000000317729",
            "product_name": "iON evo AS",
            "tire_size": "235/35R20",
            "quantity": 4,
            "store_name": "판교점",
            "region": "판교",
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "store_search"
    assert frame.known_slots.get("goods_no") is None
    assert frame.known_slots.get("product_name") is None
    assert frame.known_slots.get("store_name") is None
    assert frame.known_slots["region"] == "판교"
    assert plan.preferred_tool == "search_stores_tool"
    assert "transaction_store_preview_tool" in plan.forbidden_tools


def test_plain_store_search_does_not_reuse_unsized_purchase_context() -> None:
    frame = build_transaction_intent_frame(
        "\uac15\ub0a8 \ud2f0\uc2a4\ud14c\uc774\uc158 \ub9e4\uc7a5 \ucc3e\uc544\uc918",
        known_slots={
            "goods_no": "G000000310126",
            "product_name": "Ventus S2 AS",
            "ord_qty": 4,
            "pending_intent": "order",
            "goal_type": "place_order",
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "store_search"
    assert frame.known_slots["region"] == "\uac15\ub0a8"
    assert frame.known_slots.get("goods_no") is None
    assert plan.preferred_tool == "search_stores_tool"
    assert "transaction_store_preview_tool" in plan.forbidden_tools


def test_order_delivery_status_lookup_owns_order_tool_boundary() -> None:
    frame = build_transaction_intent_frame("주문 배송 상태 알려줘")
    plan = plan_transaction_tools(frame)

    assert frame.intent == "order_arrival_status_lookup"
    assert frame.known_slots["owned_record_target"] == "order"
    assert plan.preferred_tool == "get_orders_of_user_tool"
    assert "get_order_status_tool" in plan.allowed_tools
    assert "get_store_schedule_tool" in plan.forbidden_tools


def test_order_delivery_status_lookup_overrides_stale_purchase_context() -> None:
    frame = build_transaction_intent_frame(
        "\uc8fc\ubb38 \ubc30\uc1a1 \uc0c1\ud0dc \uc54c\ub824\uc918",
        known_slots={
            "goods_no": "G000000309780",
            "product_name": "Ventus S2 AS",
            "ord_qty": 4,
            "pending_intent": "order",
            "goal_type": "place_order",
            "availability_context": {"pending_order_context": {"goods_no": "G000000309780"}},
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "order_arrival_status_lookup"
    assert frame.known_slots["pending_intent"] == "order_arrival_status_lookup"
    assert frame.known_slots["goal_type"] == "owned_record_lookup"
    assert frame.known_slots["owned_record_target"] == "order"
    assert frame.missing_slots == ()
    assert plan.preferred_tool == "get_orders_of_user_tool"
    assert "get_order_status_tool" in plan.allowed_tools
    assert "transaction_store_preview_tool" in plan.forbidden_tools


def test_order_cancel_status_lookup_without_stale_purchase_store_slot() -> None:
    frame = build_transaction_intent_frame(
        "취소한 주문 상태 알려줘",
        known_slots={
            "goods_no": "G000000310126",
            "tire_size": "205/55R16",
            "ord_qty": 4,
            "pending_intent": "order",
            "goal_type": "place_order",
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "order_cancel_status_lookup"
    assert frame.known_slots["goal_type"] == "order_cancel_status_lookup"
    assert frame.missing_slots == ()
    assert plan.preferred_tool == "get_orders_of_user_tool"
    assert "transaction_store_preview_tool" in plan.forbidden_tools


def test_tc020_gwanggyo_nearby_store_search_prefers_unified_search() -> None:
    frame = build_transaction_intent_frame("광교 주변 매장 알려줘")
    plan = plan_transaction_tools(frame)

    assert frame.intent == "store_search"
    assert frame.sub_intent == "nearby"
    assert frame.known_slots["region"] == "광교"
    assert frame.entities["nearby"] is True
    assert plan.preferred_tool == "search_stores_tool"
    assert plan.tool_args_patch["region_code"] == "광교"
    assert plan.tool_args_patch["place_query"] == "광교"
    assert "transaction_store_preview_tool" in plan.forbidden_tools


def test_stock_inventory_nearby_store_lookup_prefers_unified_store_search() -> None:
    frame = build_transaction_intent_frame(
        "벤투스 S2 AS 2454519 4개 강남역 근처 재고 있는 매장 찾아줘",
        known_slots={
            "goods_no": "G000000310126",
            "tire_size": "245/45R19",
            "ord_qty": 4,
            "region": "강남",
            "pending_intent": "stock",
            "goal_type": "store_with_stock",
            "stock_check_mode": "inventory_only",
        },
    )
    frame = replace(
        frame,
        sub_intent="stock",
        known_slots={**dict(frame.known_slots), "stock_check_mode": "inventory_only"},
        entities={**dict(frame.entities), "stock_check_mode": "inventory_only"},
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "stock_store_search"
    assert frame.entities["nearby"] is True
    assert "search_stores_tool" in plan.allowed_tools
    assert "get_store_list_tool" in plan.allowed_tools
    assert plan.preferred_tool == "search_stores_tool"
    assert plan.tool_args_patch["place_query"] == "강남"
    assert "quick_order_tool" not in plan.allowed_tools


def test_stock_inventory_region_store_lookup_keeps_store_list_preferred() -> None:
    frame = build_transaction_intent_frame(
        "벤투스 S2 AS 2454519 4개 강남 재고 있는 매장 찾아줘",
        known_slots={
            "goods_no": "G000000310126",
            "tire_size": "245/45R19",
            "ord_qty": 4,
            "region": "강남",
            "pending_intent": "stock",
            "goal_type": "store_with_stock",
            "stock_check_mode": "inventory_only",
        },
    )
    frame = replace(
        frame,
        sub_intent="stock",
        known_slots={**dict(frame.known_slots), "stock_check_mode": "inventory_only"},
        entities={**dict(frame.entities), "stock_check_mode": "inventory_only"},
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "stock_store_search"
    assert frame.entities["nearby"] is False
    assert "search_stores_tool" in plan.allowed_tools
    assert plan.preferred_tool == "get_store_list_tool"
    assert plan.tool_args_patch["region_code"] == "강남"


def test_stock_inventory_mode_overrides_non_stock_sub_intent_preview_boundary() -> None:
    frame = build_transaction_intent_frame(
        "네, 문정 지역으로 검색",
        known_slots={
            "goods_no": "G000000310126",
            "tire_size": "245/45R19",
            "ord_qty": 2,
            "region": "문정",
            "pending_intent": "stock",
            "goal_type": "store_with_stock",
            "stock_check_mode": "inventory_only",
        },
    )
    frame = replace(
        frame,
        sub_intent="store_lookup",
        known_slots={**dict(frame.known_slots), "stock_check_mode": "inventory_only"},
        entities={**dict(frame.entities), "stock_check_mode": "inventory_only"},
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "stock_store_search"
    assert plan.metadata["tool_boundary"] == "stock_inventory_store_lookup"
    assert plan.metadata["stock_check_mode"] == "inventory_only"
    assert plan.preferred_tool == "get_store_list_tool"
    assert "get_store_list_tool" in plan.allowed_tools
    assert "search_stores_tool" in plan.allowed_tools
    assert "transaction_store_preview_tool" in plan.forbidden_tools
    assert "transaction_store_preview_tool" not in plan.allowed_tools
    assert plan.tool_args_patch["region_code"] == "문정"


def test_tc049_store_visit_schedule_for_unverified_store_keeps_store_schedule_intent() -> None:
    frame = build_transaction_intent_frame(
        "강남점에 방문해서 서비스 받고 싶은데, 예약 가능한 시간이 언제야?",
        known_slots={"booking_type": "store_visit"},
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text="강남점에 방문해서 서비스 받고 싶은데, 예약 가능한 시간이 언제야?",
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "store_schedule"
    assert frame.sub_intent == "store_visit"
    assert frame.known_slots["store_name"] == "강남점"
    assert frame.known_slots["store_exact_match"] is False
    assert plan.preferred_tool == "get_store_schedule_tool"
    assert "transaction_store_preview_tool" in plan.forbidden_tools
    assert decision.metadata["response_shape_key"] == "unverified_store_schedule_lookup"
    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.required_slots == ()


def test_tc058_noon_schedule_request_preserves_noon_entity() -> None:
    frame = build_transaction_intent_frame(
        "12시에 작업 가능한 서울 지역 매장 있을까요?",
        known_slots={"region": "서울", "booking_type": "store_visit"},
    )
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text="12시에 작업 가능한 서울 지역 매장 있을까요?",
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "store_schedule"
    assert frame.entities["noon_requested"] is True
    assert decision.template == TemplateName.DATE_PICK
    assert "show_blocked_noon_slot" in decision.forbidden_behaviors


def test_tc076_store_search_preserves_requested_limit() -> None:
    frame = build_transaction_intent_frame("청량리역 주변 가까운 매장 순으로 5개만")
    plan = plan_transaction_tools(frame)

    assert frame.intent == "store_search"
    assert frame.known_slots["region"] == "청량리"
    assert frame.entities["result_limit"] == 5
    assert plan.preferred_tool == "search_stores_tool"
    assert plan.tool_args_patch["limit"] == 5
    assert plan.tool_args_patch["place_query"] == "청량리"


def test_tc231_quick_order_missing_size_does_not_progress_to_null_summary() -> None:
    frame = build_transaction_intent_frame(
        "키너지 ST AS 2개 서초점 오늘 장착 가능?",
        known_slots={"product_name": "키너지 ST AS", "quantity": 2, "store_name": "서초점"},
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent="quick_order_reservation",
        user_text="키너지 ST AS 2개 서초점 오늘 장착 가능?",
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "stock_store_search"
    assert frame.missing_slots == ("tire_size",)
    assert plan.required_slots == ()
    assert plan.preferred_tool == "transaction_store_preview_tool"
    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["missing_slots"] == ("tire_size",)
    assert "order_summary_with_null_required_fields" in decision.forbidden_behaviors


def test_tc233_complete_order_request_prefers_schedule_preview_not_store_hours() -> None:
    frame = build_transaction_intent_frame(
        "dynapro hpx 4개 티스테이션 오목천점 예약해줘",
        known_slots={
            "product_name": "dynapro HPX",
            "goods_no": "G000000309001",
            "tire_size": "235/55R19",
            "quantity": 4,
            "store_name": "티스테이션 오목천점",
            "shop_id": "T01234",
            "payment_amount": 420000,
        },
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text="dynapro hpx 4개 티스테이션 오목천점 예약해줘",
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "quick_order_reservation"
    assert frame.missing_slots == ("booking_datetime",)
    assert plan.preferred_tool == "get_store_schedule_tool"
    assert "store_hours_instead_of_slots" in plan.forbidden_tools
    assert decision.template == TemplateName.DATE_PICK
    assert "store_hours_instead_of_slots" in decision.forbidden_behaviors


def test_datepick_selection_from_stock_preview_parent_order_builds_preorder() -> None:
    """A logistics-preview stock context can still complete the parent purchase flow."""
    frame = build_transaction_intent_frame(
        "2026년 7월 8일 (수)\n15:00",
        known_slots={
            "product_name": "다이나프로 HP3",
            "goods_no": "G000000320151",
            "tire_size": "235/55R19",
            "ord_qty": 4,
            "quantity": 4,
            "shop_id": "F00262",
            "shop_name": "티스테이션 동탄신도시점",
            "store_name": "티스테이션 동탄신도시점",
            "region": "동탄",
            "requested_cal_day": "20260708",
            "rsv_hour": "15",
            "payment_amount": 420000,
            "pending_intent": "stock",
            "goal_type": "store_with_stock",
            "stock_check_mode": "preview",
            "schedule_mode": "logistics_only",
            "inventory_mode": "logistics_only",
            "source_tool": "transaction_store_preview_tool",
            "availability_context": {
                "pending_order_context": {
                    "pending_intent": "order",
                    "goal_type": "place_order",
                },
            },
        },
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text="2026년 7월 8일 (수)\n15:00",
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "quick_order_reservation"
    assert frame.known_slots["pending_intent"] == "order"
    assert frame.known_slots["goal_type"] == "place_order"
    assert frame.missing_slots == ()
    assert plan.preferred_tool is None
    assert plan.metadata["flow_step"] == "build_preorder"
    assert "get_store_schedule_tool" in plan.forbidden_tools
    assert decision.template == TemplateName.PRE_ORDER


def test_inventory_only_context_purchase_followup_promotes_to_order_preview() -> None:
    frame = build_transaction_intent_frame(
        "\uadf8\ub7fc \uc8fc\ubb38\ud560\ub798",
        known_slots={
            "goods_no": "G000000309780",
            "product_name": "\ubca4\ud22c\uc2a4 S2 AS",
            "tire_size": "205/55R16",
            "ord_qty": 4,
            "quantity": 4,
            "region": "\uac15\ub0a8",
            "pending_intent": "stock",
            "goal_type": "store_with_stock",
            "stock_check_mode": "inventory_only",
        },
    )
    plan = plan_transaction_tools(frame)

    assert frame.intent == "quick_order_reservation"
    assert frame.known_slots["pending_intent"] == "order"
    assert frame.known_slots["goal_type"] == "place_order"
    assert frame.known_slots["stock_check_mode"] == "preview"
    assert plan.preferred_tool == "transaction_store_preview_tool"
    assert plan.tool_args_patch["goods_no"] == "G000000309780"
    assert plan.tool_args_patch["region"] == "\uac15\ub0a8"
    assert "get_store_list_tool" not in plan.allowed_tools
