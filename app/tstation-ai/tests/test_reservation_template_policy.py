from __future__ import annotations

from types import SimpleNamespace

from services.tstation.policies.reservation_template_policy import (
    build_datepick_from_preview_payload,
    build_datepick_from_schedule_payload,
    coerce_order_preview_quickreply_to_datepick,
    coerce_reservation_quickreply_to_datepick,
    coerce_schedule_confirmation_quickreply_to_datepick,
    filter_datepick_to_requested_date,
    filter_datepick_to_requested_weekday,
    is_other_store_request,
    latest_template_data_from_messages,
)


def _preview_source() -> tuple[str, dict]:
    return (
        "transaction_store_preview_tool",
        {
            "status": "success",
            "data": {
                "schedule": {
                    "tier": "today_only",
                    "stores": [{
                        "shop_id": "T02396",
                        "shop_nm": "티스테이션 강릉강남점",
                        "slots": [
                            {"cal_day": "20260521", "tm": "09"},
                            {"cal_day": "20260521", "tm": "10"},
                            {"cal_day": "20260521", "tm": "12"},
                            {"cal_day": "20260521", "tm": "13"},
                        ],
                    }],
                },
            },
        },
    )


def _datepick_event() -> dict:
    return {
        "type": "data",
        "template": "datepick",
        "data": {
            "assistantResponse": "예약 가능한 날짜와 시간을 선택해 주세요.",
            "selectedDate": 0,
            "dates": [
                {"date": "2026년 5월 23일 (토)", "available": True, "availableTimes": [9], "index": 0},
                {"date": "2026년 5월 24일 (일)", "available": True, "availableTimes": [10], "index": 1},
                {"date": "2026년 5월 29일 (금)", "available": True, "availableTimes": [11], "index": 2},
            ],
        },
    }


def test_reservation_time_quickreply_is_coerced_to_datepick() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "data": {
            "assistantResponse": "강릉에서 장착 예약 가능한 시간을 확인했어요.",
            "quickReplies": [
                {"label": "09시 예약", "domain": "TRANSACTION"},
                {"label": "13시 예약", "domain": "TRANSACTION"},
                {"label": "다른 시간 선택", "domain": "TRANSACTION"},
            ],
        },
    }

    result = coerce_reservation_quickreply_to_datepick(
        event,
        [_preview_source()],
        SimpleNamespace(pending_intent="order", goal_type="place_order"),
    )

    assert result is not None
    assert result["template"] == "datepick"
    assert result["data"]["metadata"] == {
        "shopId": "T02396",
        "shopName": "티스테이션 강릉강남점",
    }
    assert result["data"]["dates"] == [{
        "date": "2026년 5월 21일 (목)",
        "available": True,
        "availableTimes": [9, 10, 13],
        "index": 0,
    }]


def test_tc058_preview_datepick_excludes_blocked_noon_slot() -> None:
    result = build_datepick_from_preview_payload(
        _preview_source()[1]["data"],
        assistant_text="12시에 작업 가능한 서울 지역 매장을 확인했어요.",
        assistant_response_source="test",
        require_single_store=True,
    )

    assert result is not None
    assert result["template"] == "datepick"
    assert result["data"]["dates"] == [{
        "date": "2026년 5월 21일 (목)",
        "available": True,
        "availableTimes": [9, 10, 13],
        "index": 0,
    }]


def test_tc233_preview_with_single_confirmed_store_builds_datepick() -> None:
    result = build_datepick_from_preview_payload(
        {
            "schedule": {
                "tier": "in_store_only",
                "stores": [{
                    "shop_id": "T01234",
                    "shop_nm": "티스테이션 오목천점",
                    "slots": [
                        {"cal_day": "20260523", "tm": "0900"},
                        {"cal_day": "20260523", "tm": "1000"},
                    ],
                }],
            },
        },
        assistant_text="티스테이션 오목천점 예약 가능한 시간을 확인했어요.",
        source_domain="transaction",
        assistant_response_source="test",
        require_single_store=True,
    )

    assert result is not None
    assert result["source_domain"] == "transaction"
    assert result["data"]["metadata"] == {
        "shopId": "T01234",
        "shopName": "티스테이션 오목천점",
    }
    assert result["data"]["dates"] == [{
        "date": "2026년 5월 23일 (토)",
        "available": True,
        "availableTimes": [9, 10],
        "index": 0,
    }]


def test_preview_datepick_keeps_today_inventory_slots_before_reservation_install_date() -> None:
    result = build_datepick_from_preview_payload(
        {
            "logistics": {
                "logistics_qty": 0,
                "rsv_sale_yn": "Y",
                "rsv_install_date": "2026-06-25",
            },
            "inventory": {
                "todayShopArray": [{"shopId": "F00721"}],
                "tnaShopArray": [],
            },
            "schedule": {
                "tier": "in_store_only",
                "stores": [{
                    "shop_id": "F00721",
                    "shop_nm": "티스테이션 판교점",
                    "slots": [
                        {"cal_day": "20260605", "tm": "1700"},
                        {"cal_day": "20260625", "tm": "0900"},
                    ],
                }],
            },
        },
        assistant_text="예약 가능한 날짜와 시간을 선택해 주세요.",
        assistant_response_source="test",
        require_single_store=True,
    )

    assert result is not None
    assert result["data"]["dates"][0] == {
        "date": "2026년 6월 5일 (금)",
        "available": True,
        "availableTimes": [17],
        "index": 0,
    }


def test_preview_datepick_filters_before_reservation_install_date_only_for_reservation_sale_fallback() -> None:
    result = build_datepick_from_preview_payload(
        {
            "logistics": {
                "logistics_qty": 0,
                "rsv_sale_yn": "Y",
                "rsv_install_date": "2026-06-25",
            },
            "inventory": {
                "todayShopArray": [],
                "tnaShopArray": [],
            },
            "schedule": {
                "tier": "reservation_sale",
                "stores": [{
                    "shop_id": "F00721",
                    "shop_nm": "티스테이션 판교점",
                    "slots": [
                        {"cal_day": "20260605", "tm": "1700"},
                        {"cal_day": "20260624", "tm": "1700"},
                        {"cal_day": "20260625", "tm": "0900"},
                        {"cal_day": "20260626", "tm": "1000"},
                    ],
                }],
            },
        },
        assistant_text="예약 가능한 날짜와 시간을 선택해 주세요.",
        assistant_response_source="test",
        require_single_store=True,
    )

    assert result is not None
    assert result["data"]["dates"] == [
        {
            "date": "2026년 6월 25일 (목)",
            "available": True,
            "availableTimes": [9],
            "index": 0,
        },
        {
            "date": "2026년 6월 26일 (금)",
            "available": True,
            "availableTimes": [10],
            "index": 1,
        },
    ]


def test_reservation_time_quickreply_stock_context_is_not_coerced() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "강릉에서 재고가 확인된 매장입니다.",
            "quickReplies": [{"label": "09시 예약", "domain": "TRANSACTION"}],
        },
    }

    result = coerce_reservation_quickreply_to_datepick(
        event,
        [_preview_source()],
        SimpleNamespace(pending_intent="stock", goal_type="store_with_stock"),
    )

    assert result is None


def test_non_time_quickreply_is_not_coerced() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "주문을 진행할까요?",
            "quickReplies": [{"label": "주문하기", "domain": "TRANSACTION"}],
        },
    }

    result = coerce_reservation_quickreply_to_datepick(
        event,
        [_preview_source()],
        SimpleNamespace(pending_intent="order", goal_type="place_order"),
    )

    assert result is None


def test_order_preview_generic_quickreply_is_coerced_to_datepick() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "data": {
            "assistantResponse": "검색된 상품 정보를 기준으로 안내드릴게요.",
            "quickReplies": [
                {"label": "보유차량 중 선택", "domain": "DISCOVERY"},
                {"label": "차번+이름으로 검색", "domain": "DISCOVERY"},
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
            ],
        },
    }
    preview_source = (
        "transaction_store_preview_tool",
        {
            "status": "success",
            "data": {
                "schedule": {
                    "tier": "in_store_only",
                    "stores": [{
                        "shop_id": "F07782",
                        "shop_nm": "티스테이션 한남점",
                        "is_installable": True,
                        "slots": [
                            {"cal_day": "20260609", "tm": "16"},
                            {"cal_day": "20260609", "tm": "17"},
                            {"cal_day": "20260610", "tm": "09"},
                        ],
                    }],
                },
                "stores": [{"shop_id": "F07782", "shop_nm": "티스테이션 한남점"}],
                "candidate_shop_ids": ["F07782"],
            },
        },
    )

    result = coerce_order_preview_quickreply_to_datepick(
        event,
        [preview_source],
        SimpleNamespace(pending_intent="order", goal_type="place_order"),
    )

    assert result is not None
    assert result["template"] == "datepick"
    assert result["source_domain"] == "transaction"
    assert result["assistant_response_source"] == "code_mapper_order_preview_quickreply"
    assert result["data"]["metadata"] == {
        "shopId": "F07782",
        "shopName": "티스테이션 한남점",
    }
    assert result["data"]["dates"] == [
        {
            "date": "2026년 6월 9일 (화)",
            "available": True,
            "availableTimes": [16, 17],
            "index": 0,
        },
        {
            "date": "2026년 6월 10일 (수)",
            "available": True,
            "availableTimes": [9],
            "index": 1,
        },
    ]


def test_order_preview_generic_quickreply_stock_context_is_not_coerced() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "재고가 확인된 매장입니다.",
            "quickReplies": [{"label": "주문하기", "domain": "TRANSACTION"}],
        },
    }

    result = coerce_order_preview_quickreply_to_datepick(
        event,
        [_preview_source()],
        SimpleNamespace(pending_intent="stock", goal_type="store_with_stock"),
    )

    assert result is None


def test_weekend_request_keeps_first_weekend_block() -> None:
    result = filter_datepick_to_requested_weekday(_datepick_event(), "이번주말 예약 가능해?")

    assert result is not None
    assert [item["date"] for item in result["data"]["dates"]] == [
        "2026년 5월 23일 (토)",
        "2026년 5월 24일 (일)",
    ]
    assert [item["index"] for item in result["data"]["dates"]] == [0, 1]


def test_explicit_weekday_request_keeps_first_matching_day() -> None:
    result = filter_datepick_to_requested_weekday(_datepick_event(), "금요일 예약할래")

    assert result is not None
    assert result["data"]["dates"] == [{
        "date": "2026년 5월 29일 (금)",
        "available": True,
        "availableTimes": [11],
        "index": 0,
    }]


def test_incidental_weekday_character_does_not_filter_datepick() -> None:
    assert filter_datepick_to_requested_weekday(_datepick_event(), "금액도 같이 알려줘") is None


def test_explicit_slash_date_request_keeps_matching_day() -> None:
    result = filter_datepick_to_requested_date(_datepick_event(), "5/29은?")

    assert result is not None
    assert result["data"]["dates"] == [{
        "date": "2026년 5월 29일 (금)",
        "available": True,
        "availableTimes": [11],
        "index": 0,
    }]


def test_non_date_question_does_not_filter_datepick_by_date() -> None:
    assert filter_datepick_to_requested_date(_datepick_event(), "예약 가능해?") is None


def test_other_store_request_detection() -> None:
    assert is_other_store_request("다른 매장은 없어?") is True
    assert is_other_store_request("지점 더 있어?") is True
    assert is_other_store_request("이 매장 예약 가능해?") is False


def test_schedule_confirmation_quickreply_reuses_latest_datepick() -> None:
    latest_datepick = {
        "assistantResponse": "티스테이션 방배점 예약 가능한 시간을 확인했어요.",
        "dates": [
            {
                "date": "2026년 5월 23일 (토)",
                "available": True,
                "availableTimes": [9, 10, 11, 13],
                "index": 0,
            }
        ],
        "selectedDate": 0,
        "metadata": {"shopId": "F07779", "shopName": "티스테이션 방배점"},
    }
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "data": {
            "assistantResponse": "네, 선택 가능한 장착 일정이에요. 원하시는 날짜와 시간을 선택해 주세요.",
            "quickReplies": [],
        },
    }

    result = coerce_schedule_confirmation_quickreply_to_datepick(
        event,
        user_text="장착 가능일정이야?",
        latest_datepick_data=latest_datepick,
    )

    assert result is not None
    assert result["template"] == "datepick"
    assert result["data"]["metadata"] == {"shopId": "F07779", "shopName": "티스테이션 방배점"}
    assert result["data"]["dates"] == latest_datepick["dates"]
    assert "quickReplies" not in result["data"]


def test_discovery_policy_quickreply_does_not_reuse_latest_datepick() -> None:
    latest_datepick = {
        "assistantResponse": "2026년 5월 31일 (일) 티스테이션 한남점은 영업하며 예약 가능한 시간이 있습니다.",
        "dates": [{
            "date": "2026년 5월 31일 (일)",
            "available": True,
            "availableTimes": [9, 10, 11, 13],
            "index": 0,
        }],
        "selectedDate": 0,
        "metadata": {"shopId": "F07782", "shopName": "티스테이션 한남점"},
    }
    event = {
        "type": "data",
        "template": "quickReply",
        "assistant_response_source": "discovery_policy",
        "data": {
            "assistantResponse": "입력하신 벤투스 에어S 235/55R19 상품은 현재 확인되지 않아요.\n상품명이나 규격을 다시 확인해 주세요.",
            "quickReplies": [
                {"label": "보유차량 중 선택", "domain": "DISCOVERY"},
                {"label": "차번+이름으로 검색", "domain": "DISCOVERY"},
            ],
        },
    }

    result = coerce_schedule_confirmation_quickreply_to_datepick(
        event,
        user_text="이번 주 토요일 13시에 ventus air s 2355519 2개 장착 가능할까?",
        latest_datepick_data=latest_datepick,
        structured_sources=[],
    )

    assert result is None


def test_schedule_confirmation_does_not_depend_on_assistant_copy() -> None:
    latest_datepick = {
        "dates": [{
            "date": "2026년 5월 23일 (토)",
            "available": True,
            "availableTimes": [9],
            "index": 0,
        }],
        "selectedDate": 0,
        "metadata": {"shopId": "F07779"},
    }
    event = {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "원하시는 날짜와 시간을 선택해 주세요.",
            "quickReplies": [],
        },
    }

    assert (
        coerce_schedule_confirmation_quickreply_to_datepick(
            event,
            user_text="이건 다른 질문이야",
            latest_datepick_data=latest_datepick,
        )
        is None
    )


def test_schedule_payload_builds_datepick_from_tool_result() -> None:
    result = build_datepick_from_schedule_payload(
        {
            "status": "success",
            "data": {
                "shop_id": "F07782",
                "shop_nm": "티스테이션 한남점",
                "mode": "general",
                "slots": [
                    {"cal_day": "20260530", "tm": "09"},
                    {"cal_day": "20260530", "tm": "10"},
                    {"cal_day": "20260530", "tm": "13"},
                ],
            },
        },
        assistant_text="예약 가능한 날짜와 시간을 선택해 주세요.",
        assistant_response_source="test",
    )

    assert result is not None
    assert result["template"] == "datepick"
    assert result["data"]["metadata"] == {"shopId": "F07782", "shopName": "티스테이션 한남점"}
    assert result["data"]["dates"] == [{
        "date": "2026년 5월 30일 (토)",
        "available": True,
        "availableTimes": [9, 10, 13],
        "index": 0,
    }]


def test_schedule_request_quickreply_uses_schedule_tool_context_when_latest_datepick_missing() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "data": {
            "assistantResponse": "이번 주 토요일 13시 예약 가능 시간도 확인됐어요.",
            "quickReplies": [
                {"label": "보유차량 중 선택", "domain": "DISCOVERY"},
                {"label": "차번+이름으로 검색", "domain": "DISCOVERY"},
            ],
        },
    }

    result = coerce_schedule_confirmation_quickreply_to_datepick(
        event,
        user_text="이번 주 토요일 13시에 ventus air s 2553519 2개 장착 가능할까?",
        latest_datepick_data=None,
        structured_sources=[(
            "get_store_schedule_tool",
            {
                "status": "success",
                "data": {
                    "shop_id": "F07782",
                    "shop_nm": "티스테이션 한남점",
                    "mode": "general",
                    "slots": [
                        {"cal_day": "20260530", "tm": "09"},
                        {"cal_day": "20260530", "tm": "10"},
                        {"cal_day": "20260530", "tm": "13"},
                    ],
                },
            },
        )],
    )

    assert result is not None
    assert result["template"] == "datepick"
    assert result["data"]["metadata"] == {"shopId": "F07782", "shopName": "티스테이션 한남점"}
    assert result["data"]["assistantResponse"] == "이번 주 토요일 13시 예약 가능 시간도 확인됐어요."


def test_latest_template_data_from_messages_returns_newest_matching_template() -> None:
    messages = [
        {
            "role": "assistant",
            "template_data": {
                "template": "datepick",
                "data": {"metadata": {"shopId": "F07779"}, "dates": [{"date": "new"}]},
            },
        },
        {
            "role": "assistant",
            "template_data": {
                "template": "datepick",
                "data": {"metadata": {"shopId": "OLD"}, "dates": [{"date": "old"}]},
            },
        },
    ]

    assert latest_template_data_from_messages(messages, "datepick") == {
        "metadata": {"shopId": "F07779"},
        "dates": [{"date": "new"}],
    }
