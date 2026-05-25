from services.tstation.policies.response_decision import TemplateName
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
    assert decision.required_slots == ("quantity",)


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
    assert plan.preferred_tool == "transaction_store_preview_tool"
    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.required_slots == ("tire_size", "quantity")


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
    assert decision.required_slots == ("quantity",)


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
    assert decision.metadata["response_shape_key"] == "invalid_store_confirmation"
    assert decision.template == TemplateName.QUICK_REPLY


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
    assert plan.required_slots == ("tire_size",)
    assert decision.template == TemplateName.QUICK_REPLY
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
