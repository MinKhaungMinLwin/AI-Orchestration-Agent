from services.tstation.policies.response_decision import TemplateName
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
    assert plan.preferred_tool == "transaction_store_preview_tool"
    assert "order_summary_with_null_required_fields" in plan.forbidden_tools
    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["missing_slots"] == ("tire_size",)
    assert decision.required_slots == ()


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
        },
    )
    plan = plan_transaction_tools(frame)
    decision = decide_transaction_response(
        intent=frame.intent,
        user_text="dynapro hpx 4개 티스테이션 오목천점 예약해줘",
        known_slots=dict(frame.known_slots),
    )

    assert frame.intent == "quick_order_reservation"
    assert frame.missing_slots == ()
    assert plan.preferred_tool == "transaction_store_preview_tool"
    assert "store_hours_instead_of_slots" in plan.forbidden_tools
    assert decision.template == TemplateName.DATE_PICK
    assert "store_hours_instead_of_slots" in decision.forbidden_behaviors
