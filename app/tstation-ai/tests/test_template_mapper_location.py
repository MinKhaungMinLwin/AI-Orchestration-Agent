"""Unit tests for `_map_location` `is_shopid_resolution` guard.

The guard suppresses a `location` card when `get_store_list_tool` returns
exactly 1 store in a booking-intent context — because clicking the card
re-sends the store name, looping back through the same resolution turn.

Earlier the guard fired on **any** 1-store result regardless of how the
tool was called. That broke region searches that happened to match only
one store (e.g. dev DB with a single "한남" branch). The fix narrows it to
calls where the user explicitly named a store (`store_nm` arg set).

Run from `app/tstation-ai/`:

    uv run pytest tests/test_template_mapper_location.py -v
"""
from __future__ import annotations

import pytest

from services.tstation.chat import MultiAgentDomain, StreamingMultiAgentCoordinator
from services.tstation.agents.base_agent import BaseAgent, _build_stock_preview_guard_args
from services.tstation.template_mapper import (
    current_discovery_response_decision,
    _product_search_policy_fallback_response,
    _product_result_context_message,
    _map_datepick,
    _map_location,
    current_ev_suitability_comparison,
    current_goal_type,
    current_pending_intent,
    current_store_date_availability,
    current_transaction_response_decision,
    current_user_text,
    current_user_preferences_text,
    try_build_template,
)
from services.tstation.policies.discovery_intent_policy import build_discovery_intent_frame
from services.tstation.policies.discovery_response_policy import decide_discovery_response
from services.tstation.policies.response_decision import ResponseDecision, ResponseShape, TemplateName


# --------------------------------------------------------------------------- #
#  Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_pending_intent():
    """Each test sets pending_intent fresh; reset to avoid bleed across tests."""
    pending_token = current_pending_intent.set(None)
    goal_token = current_goal_type.set(None)
    ev_token = current_ev_suitability_comparison.set(False)
    store_date_token = current_store_date_availability.set(False)
    user_text_token = current_user_text.set("")
    user_preferences_token = current_user_preferences_text.set("")
    discovery_decision_token = current_discovery_response_decision.set(None)
    transaction_decision_token = current_transaction_response_decision.set(None)
    yield
    current_transaction_response_decision.reset(transaction_decision_token)
    current_discovery_response_decision.reset(discovery_decision_token)
    current_user_preferences_text.reset(user_preferences_token)
    current_user_text.reset(user_text_token)
    current_store_date_availability.reset(store_date_token)
    current_ev_suitability_comparison.reset(ev_token)
    current_pending_intent.reset(pending_token)
    current_goal_type.reset(goal_token)


def _store_list_entry(*, args: dict, stores: list[dict]) -> dict:
    """Build a `get_store_list_tool` tool_data entry mimicking BaseAgent's emit shape."""
    return {
        "tool": "get_store_list_tool",
        "args": args,
        "data": {"status": "success", "http_status": 200, "data": {"stores": stores}},
    }


def _stub_store(shop_id: str, shop_nm: str) -> dict:
    return {
        "shop_id": shop_id,
        "shop_nm": shop_nm,
        "is_installable": True,
        "is_all_my_t": False,
        "is_ev_specialty": False,
        "is_ev_charge_available": False,
        "addr_base": "서울특별시 용산구",
        "addr_dtl": "한남대로 80",
        "road_addr_base": None,
        "road_addr_dtl": None,
        "tel_no": "02-790-2921",
        "svc_codes": ["113"],
    }


def test_store_validation_quickreply_carries_confirmation_metadata() -> None:
    event = try_build_template(
        [
            {
                "tool": "transaction_store_preview_tool",
                "args": {"goods_no": "G000000317729", "ord_qty": 4, "store_nm": "강원 고성점"},
                "data": {
                    "status": "success",
                    "http_status": 200,
                    "data": {
                        "user_input": "강원 고성점",
                        "candidates": ["티스테이션 고성점"],
                        "candidate_stores": [{"shop_id": "F00614", "shop_nm": "티스테이션 고성점"}],
                        "stores": [],
                        "validation_message": "고객님, 요청하신 '강원 고성점'으로 검색한 결과 '티스테이션 고성점' 매장이 있는데 이 매장이 맞을까요?",
                        "instruction_to_agent": "STOP",
                    },
                },
            }
        ],
        "",
    )

    assert event is not None
    assert event["template"] == "quickReply"
    assert event["data"]["assistantResponse"].startswith("고객님, 요청하신 '강원 고성점'")
    assert [chip["label"] for chip in event["data"]["quickReplies"]] == ["네, 맞아요", "다른 매장 찾기"]
    assert event["data"]["metadata"]["storeConfirmation"]["candidateStores"] == [
        {"shopName": "티스테이션 고성점", "shopId": "F00614"}
    ]


def test_location_prepends_unverifiable_store_preference_guidance() -> None:
    current_goal_type.set("store_finder")
    current_user_preferences_text.set("내 차 타스만인데 리프트 있어야 되더라고... 하남 지역에 리프트 있는 매장 있어?")

    event = _map_location(
        [
            {
                "tool": "search_stores_tool",
                "args": {"place_query": "하남", "limit": 5},
                "data": {
                    "status": "success",
                    "http_status": 200,
                    "data": {
                        "stores": [_stub_store("F00001", "티스테이션 하남점")],
                    },
                },
            }
        ],
        "주소에 '하남'이 포함된 매장을 검색했어요. 원하시는 매장을 선택해 주세요 😊",
    )

    assert event is not None
    assert event["template"] == "location"
    assert "시스템에서 바로 확인이 어려워요" in event["data"]["assistantResponse"]
    assert "리프트 보유 여부" in event["data"]["assistantResponse"]
    assert "원하시는 매장을 선택해 주세요" in event["data"]["assistantResponse"]


def test_location_prepends_multiple_unverifiable_store_preference_guidance() -> None:
    current_goal_type.set("store_finder")
    current_user_preferences_text.set("하남에 대기실 있고 워셔액 무료로 넣어주고 사은품도 주는 매장 있어?")

    event = _map_location(
        [
            {
                "tool": "search_stores_tool",
                "args": {"place_query": "하남", "limit": 5},
                "data": {
                    "status": "success",
                    "http_status": 200,
                    "data": {
                        "stores": [_stub_store("F00001", "티스테이션 하남점")],
                    },
                },
            }
        ],
        "주소에 '하남'이 포함된 매장을 검색했어요. 원하시는 매장을 선택해 주세요 😊",
    )

    assert event is not None
    assert event["template"] == "location"
    assert "시스템에서 바로 확인이 어려워요" in event["data"]["assistantResponse"]
    assert "대기 공간/워셔액 무료 제공/사은품/추가 무료 서비스" in event["data"]["assistantResponse"]
    assert "원하시는 매장을 선택해 주세요" in event["data"]["assistantResponse"]


def test_location_does_not_duplicate_unverifiable_store_preference_guidance() -> None:
    current_goal_type.set("store_finder")
    current_user_preferences_text.set("하남에 대기실 있고 워셔액 무료로 넣어주는 매장 있어?")

    event = _map_location(
        [
            {
                "tool": "search_stores_tool",
                "args": {"place_query": "하남", "limit": 5},
                "data": {
                    "status": "success",
                    "http_status": 200,
                    "data": {
                        "stores": [_stub_store("F00001", "티스테이션 하남점")],
                    },
                },
            }
        ],
        "하남 매장을 찾았어요. 대기 공간/워셔액 무료 제공 여부는 시스템에서 확인이 어려워 매장에 문의해 주세요.",
    )

    assert event is not None
    response = event["data"]["assistantResponse"]
    assert response.startswith("하남 매장을 찾았어요.")
    assert "매장 목록을 먼저 안내드릴게요" not in response
    assert response.count("시스템에서") == 1


def test_location_description_includes_store_review_count() -> None:
    current_goal_type.set("store_finder")

    event = _map_location(
        [
            {
                "tool": "search_stores_tool",
                "args": {"store_nm": "성남IC점", "limit": 1},
                "data": {
                    "status": "success",
                    "http_status": 200,
                    "data": {
                        "stores": [
                            {
                                **_stub_store("F001", "티스테이션 성남IC점"),
                                "rating_idx": 3.2,
                                "review_count": 14,
                            }
                        ],
                    },
                },
            }
        ],
        "티스테이션 성남IC점 평가를 확인했어요.",
    )

    assert event is not None
    description = event["data"]["stores"][0]["description"]
    assert "⭐ 3.2" in description
    assert "리뷰 14건" in description


def test_store_quality_recommendation_does_not_use_booking_copy_from_stale_context() -> None:
    current_goal_type.set("store_finder")
    current_pending_intent.set("reservation")
    current_user_preferences_text.set("여성 운전자가 방문하기 좋은 친절한 매장 부산지역에서 2개만 추천해봐")

    event = _map_location(
        [
            {
                "tool": "search_stores_tool",
                "args": {"region_code": "부산", "limit": 2, "sort_by": "rating"},
                "data": {
                    "status": "success",
                    "http_status": 200,
                    "data": {
                        "stores": [
                            {**_stub_store("F001", "티스테이션 수영점"), "rating_idx": 4.8},
                            {**_stub_store("F002", "티스테이션 학장점"), "rating_idx": 4.6},
                        ],
                    },
                },
            }
        ],
        "요청하신 조건으로 장착 가능 여부가 확인된 매장 2곳입니다.",
    )

    assert event is not None
    response = event["data"]["assistantResponse"]
    assert "부산 지역에서 평점 기준으로 추천 가능한 매장 2곳" in response
    assert "여성 방문 편의/만족도" in response
    assert "장착 가능 여부" not in response


def test_location_filters_ev_specialty_and_charge_requested_stores() -> None:
    current_goal_type.set("store_finder")
    current_user_preferences_text.set("이번 주 일요일에 문 여는 전기차 전문 매장좀 알려줄래..? 수도권 지역 남산타워 주변에서 가까운 매장 5개 충전도 가능하면 좋겠어")

    stores = [
        {**_stub_store("F001", "티스테이션 한남점"), "is_ev_specialty": True, "is_ev_charge_available": True},
        {**_stub_store("F002", "티스테이션 청량리점"), "is_ev_specialty": True, "is_ev_charge_available": False},
        {**_stub_store("F003", "티스테이션 마장점"), "is_ev_specialty": False, "is_ev_charge_available": True},
    ]
    event = _map_location(
        [
            {
                "tool": "search_stores_tool",
                "args": {"place_query": "남산타워", "limit": 5},
                "data": {"status": "success", "http_status": 200, "data": {"stores": stores}},
            }
        ],
        "남산타워 주변 가까운 매장 5곳을 확인했어요.",
    )

    assert event is not None
    assert event["template"] == "location"
    assert len(event["data"]["stores"]) == 1
    assert event["data"]["metadata"] == [{"shopId": "F001"}]
    assert "전기차 특화점이면서 충전 가능한 매장 1곳" in event["data"]["assistantResponse"]
    assert "전기차 특화점" in event["data"]["stores"][0]["description"]
    assert "충전 가능" in event["data"]["stores"][0]["description"]


def test_location_returns_quickreply_when_no_store_matches_ev_specialty_filters() -> None:
    current_goal_type.set("store_finder")
    current_user_preferences_text.set("남산타워 주변 전기차 전문 매장 찾아줘")

    event = _map_location(
        [
            {
                "tool": "search_stores_tool",
                "args": {"place_query": "남산타워", "limit": 5},
                "data": {
                    "status": "success",
                    "http_status": 200,
                    "data": {"stores": [{**_stub_store("F002", "티스테이션 청량리점"), "is_ev_specialty": False}]},
                },
            }
        ],
        "남산타워 주변 가까운 매장 1곳을 확인했어요.",
    )

    assert event is not None
    assert event["template"] == "quickReply"
    assert "전기차 특화 조건에 맞는 매장은 현재 확인되지 않았어요" in event["data"]["assistantResponse"]


def _preview_entry(*, args: dict, stores: list[dict], inventory: dict) -> dict:
    """Build a `transaction_store_preview_tool` entry with store candidates and inventory."""
    return {
        "tool": "transaction_store_preview_tool",
        "args": args,
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "stores": stores,
                "inventory": inventory,
                "schedule": {"tier": "today_only", "stores": [{"shop_id": "T02396"}]},
            },
        },
    }


def _recommendation_entry(*, args: dict, data: dict) -> dict:
    return {
        "tool": "get_products_recommendations_tool",
        "args": args,
        "data": {"status": "success", "http_status": 200, "data": data},
    }


def _sound_absorber_recommendation_entry() -> dict:
    return _recommendation_entry(
        args={"rcmd_type": "sound_absorber", "limit": 5, "brand_cd": "HK"},
        data={
            "items": [
                {"goods_no": "G1", "goods_nm": "아이온 ST AS SUV", "goods_pfm_nm": "COMFORT", "car_knd_nm": "SUV"},
                {"goods_no": "G2", "goods_nm": "벤투스 에어S", "goods_pfm_nm": "COMFORT", "car_knd_nm": "승용차"},
                {"goods_no": "G3", "goods_nm": "아이온 에보 AS", "goods_pfm_nm": "SPORT", "car_knd_nm": "전기차"},
            ]
        },
    )


def _best_selling_entry(*, period: str, items: list[dict]) -> dict:
    return {
        "tool": "get_best_selling_products_tool",
        "args": {"period": period, "limit": len(items) or 5},
        "data": {"status": "success", "http_status": 200, "data": {"items": items}},
    }


def _search_product_entry(*, keyword: str, size: str | None, items: list[dict]) -> dict:
    return {
        "tool": "search_product_tool",
        "args": {"keyword": keyword, "limit": 10, "size": size, "brand_cd": "HK"},
        "data": {"status": "success", "http_status": 200, "data": {"items": items}},
    }


def _inventory_entry(*, today_ids: list[str] | None = None, tna_ids: list[str] | None = None) -> dict:
    return {
        "tool": "get_store_inventory_tool",
        "args": {
            "goods_list": [{"goodsNo": "G000000319451", "qty": 4}],
            "shop_id_list": [{"shopId": "F001"}, {"shopId": "F002"}],
        },
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "todayShopArray": [{"shopId": shop_id} for shop_id in (today_ids or [])],
                "tnaShopArray": [{"shopId": shop_id} for shop_id in (tna_ids or [])],
            },
        },
    }


def test_product_result_context_message_prefers_winter_fallback_notice() -> None:
    message = _product_result_context_message(
        [
            _recommendation_entry(
                args={"rcmd_type": "snow", "season_nm": "겨울", "tire_size": "225/55R17"},
                data={
                    "items": [{"goods_no": "G1", "goods_nm": "키너지 4S2"}],
                    "recommendation_fallback": {
                        "requested_season_nm": "겨울",
                        "applied_season_nm": "올웨더",
                    },
                },
            )
        ],
        1,
    )

    assert message == "겨울 상품은 현재 확인되지 않아 올웨더 대안 상품 1개를 찾았어요. 원하시는 상품을 선택해 주세요."


def test_product_result_context_message_describes_best_seller_period_and_top_product() -> None:
    message = _product_result_context_message(
        [
            _best_selling_entry(
                period="week",
                items=[
                    {"goods_no": "G1", "goods_nm": "벤투스 에어S", "sale_qty": 120},
                    {"goods_no": "G2", "goods_nm": "다이나프로 HPX", "sale_qty": 90},
                ],
            )
        ],
        2,
    )

    assert message == "이번 주 베스트셀러는 벤투스 에어S예요. 인기 상품 2개를 안내드립니다."


def test_product_result_context_message_hides_exact_best_seller_sales_count() -> None:
    token = current_user_text.set("오늘 베스트셀러는 어떤 타이어야? 몇개팔렸어?")
    try:
        message = _product_result_context_message(
            [
                _best_selling_entry(
                    period="day",
                    items=[
                        {"goods_no": "G1", "goods_nm": "벤투스 에어S", "sale_qty": 12},
                        {"goods_no": "G2", "goods_nm": "다이나프로 HPX", "sale_qty": 8},
                    ],
                )
            ],
            2,
        )
    finally:
        current_user_text.reset(token)

    assert message == (
        "오늘 베스트셀러는 벤투스 에어S예요. "
        "정확한 판매 개수는 바로 안내드리기 어렵지만, 인기 상품 2개를 안내드립니다."
    )


def test_product_result_context_message_uses_only_current_turn_for_best_seller_count_query() -> None:
    token = current_user_text.set("오늘 베스트셀러는 어떤 타이어야? 몇개팔렸어?\n이번주 베스트셀러는?")
    try:
        message = _product_result_context_message(
            [
                _best_selling_entry(
                    period="week",
                    items=[
                        {"goods_no": "G1", "goods_nm": "다이나프로 HPX", "sale_qty": 12},
                        {"goods_no": "G2", "goods_nm": "벤투스 에어S", "sale_qty": 8},
                    ],
                )
            ],
            2,
        )
    finally:
        current_user_text.reset(token)

    assert message == "이번 주 베스트셀러는 다이나프로 HPX예요. 인기 상품 2개를 안내드립니다."


def test_product_search_policy_fallback_does_not_ask_for_size_when_keyword_and_size_were_already_provided() -> None:
    token = current_user_text.set("지금 kinergy EX 2055516 사이즈 주문하면 동광주 매장에 도착하는 날짜가 언제야?")
    try:
        message = _product_search_policy_fallback_response(
            [
                _search_product_entry(keyword="키너지 EX", size="205/55R16", items=[]),
            ]
        )
    finally:
        current_user_text.reset(token)

    assert message == (
        "입력하신 키너지 EX 205/55R16 상품은 현재 확인되지 않아요.\n"
        "다른 사이즈를 다시 찾거나, 대체 가능한 상품 기준으로 매장 도착 일정을 확인해 드릴게요."
    )


def test_map_product_deduplicates_same_recommendation_goods_from_guard_and_tool() -> None:
    tool_data = [
        _recommendation_entry(
            args={"rcmd_type": "tstation", "tire_size": "225/55R17", "car_lnc_cd": "W011338"},
            data={
                "items": [
                    {"goods_no": "G1", "goods_nm": "키너지 4S2", "tire_size_1": "225/55R17", "price": 134500},
                    {"goods_no": "G2", "goods_nm": "크로스클라이밋 2", "tire_size_1": "225/55R17", "price": 251800},
                ],
                "recommendation_fallback": {
                    "requested_season_nm": "겨울",
                    "applied_season_nm": "올웨더",
                },
            },
        ),
        _recommendation_entry(
            args={"rcmd_type": "snow", "tire_size": "225/55R17", "season_nm": "겨울"},
            data={
                "items": [
                    {"goods_no": "G1", "goods_nm": "키너지 4S2", "tire_size_1": "225/55R17", "price": 134500},
                    {"goods_no": "G2", "goods_nm": "크로스클라이밋 2", "tire_size_1": "225/55R17", "price": 251800},
                ],
                "recommendation_fallback": {
                    "requested_season_nm": "겨울",
                    "applied_season_nm": "올웨더",
                },
            },
        ),
    ]

    event = try_build_template(tool_data, "")

    assert event is not None
    assert event["template"] == "product"
    assert len(event["data"]["products"]) == 2
    assert [item["goodsId"] for item in event["data"]["metadata"]] == ["G1", "G2"]
    assert "올웨더 대안 상품 2개" in event["data"]["assistantResponse"]


def test_empty_recommendation_result_maps_to_no_result_quickreply() -> None:
    event = try_build_template(
        [
            _recommendation_entry(
                args={"rcmd_type": "value", "limit": 3, "brand_cd": "HK", "tire_size": "255/45R20"},
                data={"items": []},
            )
        ],
        "타이어 연비 관련 정보는 보통 회전저항(RR) 등급으로 확인합니다.",
    )

    assert event is not None
    assert event["template"] == "quickReply"
    assert "255/45R20" in event["data"]["assistantResponse"]
    assert "추천 가능한 상품을 찾지 못했어요" in event["data"]["assistantResponse"]
    assert [chip["label"] for chip in event["data"]["quickReplies"]] == [
        "다시 검색",
        "다른 조건으로 찾기",
        "사이즈 직접 입력",
    ]


def _preview_entry_with_schedule(*, args: dict, stores: list[dict], schedule_stores: list[dict]) -> dict:
    """Build a preview entry where the preview tool already resolved bookable slots."""
    return {
        "tool": "transaction_store_preview_tool",
        "args": args,
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "stores": stores,
                "inventory": {"todayShopArray": [{"shopId": "T02396"}], "tnaShopArray": []},
                "schedule": {"tier": "today_only", "stores": schedule_stores},
            },
        },
    }


def _schedule_entry(*, mode: str, is_installable: bool, slots: list[dict]) -> dict:
    """Build a `get_store_schedule_tool` entry mimicking the StoreScheduleResponse."""
    return {
        "tool": "get_store_schedule_tool",
        "args": {"shop_id": "F00405", "mode": mode},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "shop_id": "F00405",
                "mode": mode,
                "shop_nm": "티스테이션 경포점",
                "is_installable": is_installable,
                "is_tna_delivery": False,
                "slots": slots,
            },
        },
    }


def _store_detail_entry(*, cal_day: str, available_slots: list[str]) -> dict:
    """Build a `get_store_detail_tool` entry for a single-date store lookup."""
    return {
        "tool": "get_store_detail_tool",
        "args": {"shop_id": "C01312", "cal_day": cal_day},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "shop_seq": "F202053575",
                "shop_nm": "티스테이션 송파오금점",
                "tel_no": "02-403-0666",
                "is_all_my_t": True,
                "is_installable": True,
                "is_tna_delivery": True,
                "is_imported_car": True,
                "svc_codes": ["113", "116"],
                "holiday": "토요일 17:00/일요일휴무 ",
                "shop_biz_strt_time": "09",
                "shop_biz_end_time": "18",
                "shop_biz_strt_wday": "월요일",
                "shop_biz_end_wday": "토요일",
                "shop_sat_strt_time": "09:00",
                "shop_sat_end_time": "17:00",
                "available_slots": available_slots,
            },
        },
    }


def _product_entry() -> dict:
    """Build a `search_product_tool` entry with EV tire search results."""
    return {
        "tool": "search_product_tool",
        "args": {"keyword": "아이온 evo", "limit": 10, "brand_cd": "HK"},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "items": [
                    {
                        "goods_no": "G000000319448",
                        "goods_nm": "아이온 에보",
                        "tire_size_1": "235/35R20",
                        "car_knd_nm": "전기차",
                        "brand_nm": "HANKOOK",
                        "extra_fvr_sale_prc": 410500,
                        "sale_prc": 533500,
                    }
                ]
            },
        },
    }


def _preview_entry_with_guard(*, args: dict, stores: list[dict]) -> dict:
    """Build a preview entry where schedule is unavailable but store candidates exist."""
    return {
        "tool": "transaction_store_preview_tool",
        "args": args,
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "stores": stores,
                "inventory": {"todayShopArray": [], "tnaShopArray": []},
                "schedule": {
                    "tier": "none",
                    "stores": [],
                    "candidate_shop_ids": [store["shop_id"] for store in stores],
                },
                "candidate_shop_ids": [store["shop_id"] for store in stores],
                "instruction_to_agent": "DETERMINISTIC GUARD: render location with store candidates.",
            },
        },
    }


def _unsized_recommendation_entry() -> dict:
    """Build recommendation results with repeated tire names across sizes."""
    return {
        "tool": "get_products_recommendations_tool",
        "args": {"rcmd_type": "ev", "limit": 5},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "items": [
                    {
                        "goods_no": "G000000317729",
                        "goods_nm": "아이온 에보 AS",
                        "tire_size_1": "235/35R20",
                        "car_knd_nm": "전기차",
                        "season_nm": "사계절",
                        "goods_pfm_nm": "SPORT",
                    },
                    {
                        "goods_no": "G000000317730",
                        "goods_nm": "아이온 에보 AS",
                        "tire_size_1": "265/35R21",
                        "car_knd_nm": "전기차",
                        "season_nm": "사계절",
                        "goods_pfm_nm": "SPORT",
                    },
                    {
                        "goods_no": "G000000317664",
                        "goods_nm": "다이나프로 HPX",
                        "tire_size_1": "265/50R20",
                        "car_knd_nm": "SUV",
                        "season_nm": "사계절",
                        "goods_pfm_nm": "COMFORT",
                        "t_life_span": "5",
                    },
                ]
            },
        },
    }


def _registered_vehicle_entry() -> dict:
    return {
        "tool": "get_my_cars_tool",
        "args": {"mbr_no": "M200012890"},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "items": [
                    {
                        "car_no": "205소4214",
                        "mbr_car_reg_seq": "2000002944",
                        "car_lnc_cd": "W049847",
                        "car_nm": "GV70 2.5T 가솔린 AWD A/T",
                        "car_model_det": "GV70 (1세대) (2021 - 2024)",
                        "tire_size_fr": "2355519",
                        "tire_size_re": "2355519",
                    }
                ]
            },
        },
    }


def _errored_sized_recommendation_entry() -> dict:
    return {
        "tool": "get_products_recommendations_tool",
        "args": {
            "rcmd_type": "tstation",
            "limit": 3,
            "brand_cd": "HK",
            "tire_size": "2355519",
            "car_lnc_cd": "W049847",
        },
        "data": {"status": "error", "http_status": 200, "reason": "no_results", "message": "0 hits"},
    }


def _mileage_search_entry() -> dict:
    return {
        "tool": "search_product_tool",
        "args": {"keyword": "마일리지", "brand_cd": "HK", "limit": 10},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "items": [
                    {
                        "goods_no": "G000000309815",
                        "goods_nm": "마일리지 플러스2",
                        "tire_size_1": "195/65R15",
                        "car_knd_nm": "승용차",
                        "season_nm": "사계절",
                        "goods_pfm_nm": "COMFORT",
                    },
                    {
                        "goods_no": "G000000310545",
                        "goods_nm": "마일리지 플러스3",
                        "tire_size_1": "205/70R15",
                        "car_knd_nm": "승용차",
                        "season_nm": "사계절",
                        "goods_pfm_nm": "COMFORT",
                    },
                    {
                        "goods_no": "G000000310546",
                        "goods_nm": "마일리지 플러스3",
                        "tire_size_1": "215/60R16",
                        "car_knd_nm": "승용차",
                        "season_nm": "사계절",
                        "goods_pfm_nm": "COMFORT",
                    },
                ]
            },
        },
    }


def _dynapro_hpx_search_entry() -> dict:
    return {
        "tool": "search_product_tool",
        "args": {"keyword": "Dynapro HPX", "brand_cd": "HK", "limit": 10},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "items": [
                    {
                        "goods_no": "G000000317664",
                        "goods_nm": "다이나프로 HPX",
                        "tire_size_1": "265/50R20",
                        "car_knd_nm": "SUV",
                        "season_nm": "사계절",
                        "goods_pfm_nm": "COMFORT",
                        "t_life_span": "5",
                    },
                    {
                        "goods_no": "G000000317665",
                        "goods_nm": "다이나프로 HPX",
                        "tire_size_1": "255/55R18",
                        "car_knd_nm": "SUV",
                        "season_nm": "사계절",
                        "goods_pfm_nm": "COMFORT",
                        "t_life_span": "5",
                    },
                ]
            },
        },
    }


def _kinergy_ex_search_entry() -> dict:
    return {
        "tool": "search_product_tool",
        "args": {"keyword": "Kinergy EX", "brand_cd": "HK", "limit": 5},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "items": [
                    {
                        "goods_nm": "키너지 EX",
                        "tire_size_1": "165/60R14",
                        "label_pnwave": "A",
                        "label_pnwave_nm": "저소음",
                        "label_pndb": "71",
                        "rr": "3",
                        "wet": "3",
                        "prc_grd_nm": "스탠다드",
                        "t_rls_yearmon": "2013년 4월",
                        "orpl_nm": "한국",
                        "t_wgt_idx": "79",
                        "t_wgt_idx_kg": "437KG",
                        "t_wgt_spd": "79H",
                        "season_nm": "사계절",
                        "car_knd_nm": "승용차",
                    },
                    {
                        "goods_nm": "키너지 EX",
                        "tire_size_1": "185/65R14",
                        "rr": "3",
                        "wet": "3",
                        "prc_grd_nm": "스탠다드",
                        "t_rls_yearmon": "2013년 4월",
                        "orpl_nm": "한국",
                        "t_wgt_idx": "90",
                        "t_wgt_idx_kg": "600KG",
                        "t_wgt_spd": "90H",
                        "season_nm": "사계절",
                        "car_knd_nm": "승용차",
                    },
                ]
            },
        },
    }


def _attribute_compare_search_entries() -> list[dict]:
    return [
        {
            "tool": "search_product_tool",
            "args": {"keyword": "벤투스 에어S", "brand_cd": "HK", "limit": 10},
            "data": {
                "status": "success",
                "http_status": 200,
                "data": {
                    "items": [
                        {
                            "goods_nm": "벤투스 에어S",
                            "tire_size_1": "245/45R18",
                            "t_life_span": "4.0",
                            "rr": "3",
                            "sys_reg_dtime": "2024-06-13 15:50:56",
                            "t_rls_yearmon": "2024년 7월",
                        }
                    ]
                },
            },
        },
        {
            "tool": "search_product_tool",
            "args": {"keyword": "다이나프로 HPX", "brand_cd": "HK", "limit": 10},
            "data": {
                "status": "success",
                "http_status": 200,
                "data": {
                    "items": [
                        {
                            "goods_nm": "다이나프로 HPX",
                            "tire_size_1": "235/55R19",
                            "t_life_span": "5.0",
                            "rr": "4",
                            "sys_reg_dtime": "2022-11-10 10:00:00",
                            "t_rls_yearmon": "2023년 1월",
                        }
                    ]
                },
            },
        },
        {
            "tool": "search_product_tool",
            "args": {"keyword": "다이나프로 HP3", "brand_cd": "HK", "limit": 10},
            "data": {
                "status": "success",
                "http_status": 200,
                "data": {
                    "items": [
                        {
                            "goods_nm": "다이나프로 HP3",
                            "tire_size_1": "235/55R19",
                            "t_life_span": "4.2",
                            "rr": "3",
                            "sys_reg_dtime": "2025-01-20 09:30:00",
                            "t_rls_yearmon": "2025년 2월",
                        }
                    ]
                },
            },
        },
        {
            "tool": "search_product_tool",
            "args": {"keyword": "옵티모", "brand_cd": "HK", "limit": 10},
            "data": {
                "status": "success",
                "http_status": 200,
                "data": {
                    "items": [
                        {
                            "goods_nm": "옵티모 H426",
                            "tire_size_1": "245/50R18",
                            "t_life_span": "2.5",
                            "rr": "3",
                            "sys_reg_dtime": "2019-03-12 09:15:37",
                            "t_rls_yearmon": "2005년 1월",
                        },
                        {
                            "goods_nm": "옵티모 H108",
                            "tire_size_1": "245/45R19",
                            "t_life_span": "2.5",
                            "rr": "4",
                            "sys_reg_dtime": "2019-03-12 09:15:38",
                            "t_rls_yearmon": "2008년 1월",
                        },
                    ]
                },
            },
        },
        {
            "tool": "search_product_tool",
            "args": {"keyword": "cc2", "brand_cd": "MC", "limit": 10},
            "data": {
                "status": "success",
                "http_status": 200,
                "data": {
                    "items": [
                        {
                            "goods_nm": "크로스클라이밋 2",
                            "tire_size_1": "245/40R19",
                            "t_life_span": "0",
                            "rr": None,
                            "sys_reg_dtime": "2024-02-20 16:19:50",
                            "t_rls_yearmon": "2021년 10월",
                        }
                    ]
                },
            },
        },
    ]


def _mileage_value_recommendation_entry() -> dict:
    return {
        "tool": "get_products_recommendations_tool",
        "args": {"rcmd_type": "value", "limit": 3, "brand_cd": "HK"},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "items": [
                    {
                        "goods_no": "G000000318219",
                        "goods_nm": "아이온 ST AS SUV",
                        "tire_size_1": "235/55R19",
                        "t_life_span": 5.0,
                    },
                    {
                        "goods_no": "G000000317671",
                        "goods_nm": "다이나프로 HPX",
                        "tire_size_1": "255/55R18",
                        "t_life_span": 5.0,
                    },
                ]
            },
        },
    }


def test_unsized_recommendation_maps_to_text_summary_not_product_cards() -> None:
    result = try_build_template([_unsized_recommendation_entry()], "전기차용 타이어를 추천해 드릴게요.")

    assert result is not None
    assert result["template"] == "quickReply"
    assistant_response = result["data"]["assistantResponse"]
    assert "- 아이온 에보 AS: 전기차용 사계절 스포츠 타이어입니다." in assistant_response
    assert "정숙성과 승차감 중심의 타이어입니다." in assistant_response
    assert "- 다이나프로 HPX: SUV용 사계절 컴포트 타이어입니다." in assistant_response
    assert "승차감과 마일리지 중심의 타이어입니다." in assistant_response
    assert assistant_response.count("아이온 에보 AS") == 1
    assert "235/35R20" not in assistant_response
    assert "265/35R21" not in assistant_response
    assert "패턴" not in assistant_response
    assert "products" not in result["data"]


def test_product_search_size_question_answers_sizes_instead_of_generic_unsized_summary() -> None:
    current_user_text.set("마일리지 타이어 사이즈가 뭐야?\n아니 추천 말고 마일리지 타이어 말야")

    result = try_build_template([_mileage_search_entry()], "마일리지 타이어를 확인했어요.")

    assert result is not None
    assert result["template"] == "quickReply"
    assistant_response = result["data"]["assistantResponse"]
    assert "검색된 상품은 현재 아래 사이즈로 확인돼요." in assistant_response
    assert "- 마일리지 플러스2: 195/65R15" in assistant_response
    assert "- 마일리지 플러스3: 205/70R15, 215/60R16" in assistant_response
    assert "사이즈가 아직 확인되지 않아" not in assistant_response


def test_product_search_without_size_question_keeps_generic_unsized_summary() -> None:
    current_user_text.set("마일리지 타이어")

    result = try_build_template([_mileage_search_entry()], "마일리지 타이어를 확인했어요.")

    assert result is not None
    assert result["template"] == "quickReply"
    assistant_response = result["data"]["assistantResponse"]
    assert "사이즈가 아직 확인되지 않아" in assistant_response
    assert "검색된 상품은 현재 아래 사이즈로 확인돼요." not in assistant_response


def test_discovery_policy_product_search_summary_prevents_generic_unsized_summary() -> None:
    current_user_text.set("마일리지 타이어 이거는 택시기사들이 쓰는거 아냐? 별로지?")
    decision = decide_discovery_response(
        build_discovery_intent_frame("마일리지 타이어 이거는 택시기사들이 쓰는거 아냐? 별로지?")
    )
    current_discovery_response_decision.set(decision)

    result = try_build_template([_mileage_search_entry()], "직업군과 무관하게 상품 특성 기준으로 안내드릴게요.")

    assert result is not None
    assert result["template"] == "quickReply"
    assistant_response = result["data"]["assistantResponse"]
    assert "직업군과 무관하게" in assistant_response
    assert "사이즈가 아직 확인되지 않아" not in assistant_response
    assert result["assistant_response_source"] == "discovery_policy"


def test_discovery_policy_product_search_summary_does_not_reference_missing_cards() -> None:
    current_user_text.set("마일리지 타이어 추천")
    decision = decide_discovery_response(build_discovery_intent_frame("마일리지 타이어 추천"))
    current_discovery_response_decision.set(decision)

    result = try_build_template([_mileage_search_entry()], "마일리지 플러스 상품을 찾았어요. 카드에서 선택해 주세요.")

    assert result is not None
    assert result["template"] == "quickReply"
    assistant_response = result["data"]["assistantResponse"]
    assert "검색된 상품 기준으로 안내드릴게요." in assistant_response
    assert "- 마일리지 플러스2:" in assistant_response
    assert "- 마일리지 플러스3:" in assistant_response
    assert "카드" not in assistant_response
    assert "차량에 맞는 규격 확인" in assistant_response
    assert result["assistant_response_source"] == "discovery_policy"


def test_product_attribute_price_grade_uses_direct_grade_answer() -> None:
    current_user_text.set("키너지 EX 등급이 뭐야?")
    current_pending_intent.set(None)
    current_goal_type.set(None)
    current_discovery_response_decision.set(
        decide_discovery_response(build_discovery_intent_frame("키너지 EX 등급이 뭐야?"))
    )

    result = try_build_template(
        [
            {
                "tool": "search_product_tool",
                "args": {"keyword": "키너지 EX", "limit": 10},
                "data": {
                    "status": "success",
                    "http_status": 200,
                    "data": {
                        "items": [
                            {
                                "goods_nm": "키너지 EX",
                                "prc_grd_nm": "스탠다드",
                                "tire_size_1": "205/55R16",
                            }
                        ]
                    },
                },
            }
        ],
        "조회된 상품의 상세 정보는 아래처럼 확인돼요.",
    )

    assert result is not None
    assert result["template"] == "quickReply"
    assistant_response = result["data"]["assistantResponse"]
    assert "키너지 EX의 상품 등급은 스탠다드입니다." in assistant_response
    assert "프리미엄 > 스탠다드 > 이코노미" in assistant_response


def test_product_name_stock_request_asks_size_instead_of_product_cards() -> None:
    text = "dynapro HPX 오늘 장착 가능한 근처 매장 알려줘"
    current_user_text.set(text)
    current_pending_intent.set("stock")
    decision = decide_discovery_response(build_discovery_intent_frame(text))
    current_discovery_response_decision.set(decision)

    result = try_build_template([_dynapro_hpx_search_entry()], "추천 상품 10개를 안내드립니다.")

    assert result is not None
    assert result["template"] == "quickReply"
    assistant_response = result["data"]["assistantResponse"]
    assert "상품은 확인했어요. 장착 가능 여부 확인을 위해 먼저 규격을 확인할게요." in assistant_response
    assert "- 다이나프로 HPX:" in assistant_response
    assert "265/50R20" in assistant_response
    assert "255/55R18" in assistant_response
    assert "차량에 맞는 규격 확인" in assistant_response
    assert "추천 상품 10개" not in assistant_response
    assert "products" not in result["data"]
    assert result["assistant_response_source"] == "discovery_policy"
    assert [reply["label"] for reply in result["data"]["quickReplies"]] == [
        "보유차량 중 선택",
        "차번+이름으로 검색",
        "사이즈 직접 입력",
    ]


def test_tc015_restock_question_maps_to_quickreply_not_product_card() -> None:
    text = "미쉐린 CC2 235/5519 품절인데 재입고 언제 되나요?"
    current_user_text.set(text)
    decision = decide_discovery_response(build_discovery_intent_frame(text))
    current_discovery_response_decision.set(decision)

    entry = {
        "tool": "search_product_tool",
        "args": {"keyword": "Michelin CC2", "size": "235/55R19", "brand_cd": "MC", "limit": 10},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "items": [
                    {
                        "goods_no": "G000000399999",
                        "goods_nm": "미쉐린 CC2",
                        "tire_size_1": "235/55R19",
                        "car_knd_nm": "SUV",
                        "season_nm": "사계절",
                        "goods_pfm_nm": "COMFORT",
                    }
                ]
            },
        },
    }

    result = try_build_template([entry], "고객님, 추천 상품 1개를 안내드립니다. 원하시는 상품을 선택해 주세요.")

    assert result is not None
    assert result["template"] == "quickReply"
    assert "미쉐린 CC2 235/55R19 재입고 일정은 현재 바로 확인하기 어려워요." in result["data"]["assistantResponse"]
    assert "지역이나 매장을 알려주시면 매장 재고가 있는지 먼저 확인" in result["data"]["assistantResponse"]
    assert [reply["label"] for reply in result["data"]["quickReplies"]] == ["지역 입력", "매장명 입력", "대체상품 찾기"]


def test_tc044_unsized_sound_absorber_uses_deterministic_summary_when_results_exist() -> None:
    text = "흡음재가 뭐야? 그거들어간 타이어 종류추천해줘 구매할래."
    current_user_text.set(text)
    current_discovery_response_decision.set(decide_discovery_response(build_discovery_intent_frame(text)))

    result = try_build_template(
        [_sound_absorber_recommendation_entry()],
        "현재 흡음재 적용 조건으로 바로 추천 가능한 한국타이어 상품은 확인되지 않았어요.",
    )

    assert result is not None
    assert result["template"] == "quickReply"
    assistant_response = result["data"]["assistantResponse"]
    assert "흡음재는 타이어 내부에 부착해 주행 중 노면 소음을 줄여주는 소재예요." in assistant_response
    assert "현재 확인되는 흡음재 적용 상품으로는 아이온 ST AS SUV, 벤투스 에어S, 아이온 에보 AS가 있어요." in assistant_response
    assert "현재 흡음재 적용 조건으로 바로 추천 가능한" not in assistant_response
    assert [reply["label"] for reply in result["data"]["quickReplies"]] == [
        "보유차량 중 선택",
        "차번+이름으로 검색",
        "사이즈 직접 입력",
    ]


def test_product_card_uses_search_context_not_generic_intro() -> None:
    entry = _unsized_recommendation_entry()
    entry["args"] = {"rcmd_type": "performance", "limit": 3, "brand_cd": "HK", "car_lnc_cd": "W011338"}
    result = try_build_template([entry], "추천 상품을 확인했어요.")

    assert result is not None
    assert result["template"] == "product"
    assert result["data"]["assistantResponse"] == "퍼포먼스 조건으로 찾은 상품 3개입니다. 원하시는 상품을 선택해 주세요."


def test_similar_price_recommendation_with_items_prefers_product_cards() -> None:
    text = "비슷한 가격대의 타이어 더 추천해줘"
    current_user_text.set(text)
    current_discovery_response_decision.set(decide_discovery_response(build_discovery_intent_frame(text)))

    entry = _recommendation_entry(
        args={"rcmd_type": "tstation", "limit": 3, "min_price": 40000, "max_price": 100000},
        data={
            "rcmd_type": "tstation",
            "total": 3,
            "items": [
                {
                    "goods_no": "G1",
                    "goods_nm": "키너지 ST AS",
                    "tire_size_1": "195/65R15",
                    "brand_nm": "HANKOOK",
                    "goods_pfm_nm": "COMFORT",
                    "car_knd_nm": "승용차",
                    "season_nm": "사계절",
                    "prc_grd_nm": "스탠다드",
                    "sale_prc": 129800,
                    "cheapest_final_prc": 97400,
                    "image_url": "https://example.com/1.png",
                },
                {
                    "goods_no": "G2",
                    "goods_nm": "키너지 GT",
                    "tire_size_1": "205/60R16",
                    "brand_nm": "HANKOOK",
                    "goods_pfm_nm": "COMFORT",
                    "car_knd_nm": "승용차",
                    "season_nm": "사계절",
                    "prc_grd_nm": "스탠다드",
                    "sale_prc": 112500,
                    "cheapest_final_prc": 84500,
                    "image_url": "https://example.com/2.png",
                },
            ],
        },
    )

    result = try_build_template(
        [entry],
        "정가 기준 가격대 range로 유사 상품을 추천하고, 최종 구매 가격은 규격 확인 후 안내한다.",
    )

    assert result is not None
    assert result["template"] == "product"
    assert len(result["data"]["products"]) == 2


def test_product_search_policy_never_exposes_internal_guidance_without_tool_rows() -> None:
    text = "dynapro HPX 오늘 장착 가능한 근처 매장 알려줘"
    current_user_text.set(text)
    decision = decide_discovery_response(build_discovery_intent_frame(text))
    current_discovery_response_decision.set(decision)

    result = try_build_template(
        [{
            "tool": "search_product_tool",
            "args": {"keyword": "Dynapro HPX", "brand_cd": "HK", "limit": 10},
            "data": {"status": "success", "http_status": 200, "data": {"items": []}},
        }],
        "",
    )

    assert result is not None
    assistant_response = result["data"]["assistantResponse"]
    assert "상품은 확인했어요. 장착 가능 여부를 확인하려면 타이어 사이즈와 지역 정보가 필요해요." in assistant_response
    assert "보유차량 중 선택하거나, 차량번호+소유주명으로 찾거나" in assistant_response
    assert "상품명 검색 결과 기준으로 답하고" not in assistant_response
    assert "이전 추천 결과로 대체" not in assistant_response


def test_product_attribute_policy_answers_noise_label_from_search_results() -> None:
    current_user_text.set("키너지 EX 소음등급은 어떤거고?")
    decision = decide_discovery_response(build_discovery_intent_frame("키너지 EX 소음등급은 어떤거고?"))
    current_discovery_response_decision.set(decision)

    result = try_build_template([_kinergy_ex_search_entry()], "사이즈가 아직 확인되지 않아 타이어 기준으로 안내드릴게요.")

    assert result is not None
    assert result["template"] == "quickReply"
    assistant_response = result["data"]["assistantResponse"]
    assert "조회된 상품의 상세 정보" in assistant_response
    assert "- 키너지 EX: 소음 등급 A(저소음), 71dB" in assistant_response
    assert "일부 규격은 요청하신 상세 정보 표시가 없을 수 있어요." in assistant_response
    assert "사이즈가 아직 확인되지 않아" not in assistant_response
    assert result["assistant_response_source"] == "discovery_policy"


def test_product_attribute_policy_answers_multiple_requested_fields() -> None:
    current_user_text.set("키너지 EX 연비랑 원산지는 어떻게 돼?")
    decision = decide_discovery_response(build_discovery_intent_frame("키너지 EX 연비랑 원산지는 어떻게 돼?"))
    current_discovery_response_decision.set(decision)

    result = try_build_template([_kinergy_ex_search_entry()], "상품 정보를 확인했어요.")

    assert result is not None
    assistant_response = result["data"]["assistantResponse"]
    assert "- 키너지 EX: 회전저항/RR 3등급 / 원산지 한국" in assistant_response
    assert "소음 등급" not in assistant_response


def test_product_attribute_policy_explains_general_noise_label_without_product() -> None:
    current_user_text.set("소음 등급은 어떻게 돼?")
    decision = decide_discovery_response(build_discovery_intent_frame("소음 등급은 어떻게 돼?"))
    current_discovery_response_decision.set(decision)

    result = try_build_template(
        [_unsized_recommendation_entry()],
        "사이즈가 아직 확인되지 않아 타이어 기준으로 안내드릴게요.",
    )

    assert result is not None
    assistant_response = result["data"]["assistantResponse"]
    assert "타이어 소음 등급은" in assistant_response
    assert "상품명이나 사이즈" in assistant_response
    assert "사이즈가 아직 확인되지 않아" not in assistant_response


def test_metric_comparison_policy_ranks_mileage_from_search_results() -> None:
    text = "ventus air S, dynapro HPX 어떤거 가장 오래 탈 수 있어?"
    current_user_text.set(text)
    current_discovery_response_decision.set(decide_discovery_response(build_discovery_intent_frame(text)))

    result = try_build_template(_attribute_compare_search_entries()[:2], "상품 카드로 안내드릴게요.")

    assert result is not None
    assert result["template"] == "quickReply"
    assistant_response = result["data"]["assistantResponse"]
    assert "DB 수명/마일리지 지표 기준으로는 다이나프로 HPX" in assistant_response
    assert "- 다이나프로 HPX: 수명/마일리지 점수 5/5" in assistant_response
    assert "- 벤투스 에어S: 수명/마일리지 점수 4/5" in assistant_response
    assert "상품 카드" not in assistant_response


def test_metric_comparison_policy_groups_generic_keyword_results_by_request() -> None:
    text = "ventus air S, dynapro HPX, optimo, 미쉐린 CC2 어떤거 가장 오래 탈 수 있어?"
    current_user_text.set(text)
    current_discovery_response_decision.set(decide_discovery_response(build_discovery_intent_frame(text)))

    result = try_build_template(_attribute_compare_search_entries(), "상품 카드로 안내드릴게요.")

    assert result is not None
    assistant_response = result["data"]["assistantResponse"]
    assert "- 옵티모: 수명/마일리지 점수 2.5/5" in assistant_response
    assert "- 미쉐린 CC2: 수명/마일리지 정보 확인되지 않음" in assistant_response
    assert "옵티모 H426" not in assistant_response
    assert "옵티모 H108" not in assistant_response


def test_metric_comparison_policy_ranks_fuel_efficiency_from_rr() -> None:
    text = "키너지 EX랑 벤투스 air S 연비 기준으로 비교해줘"
    current_user_text.set(text)
    current_discovery_response_decision.set(decide_discovery_response(build_discovery_intent_frame(text)))

    result = try_build_template([_kinergy_ex_search_entry(), _attribute_compare_search_entries()[0]], "비교해드릴게요.")

    assert result is not None
    assistant_response = result["data"]["assistantResponse"]
    assert "회전저항/RR 기준으로는 벤투스 에어S, 키너지 EX이 같은 수준" in assistant_response
    assert "- 벤투스 에어S: 회전저항/RR 3등급" in assistant_response
    assert "- 키너지 EX: 회전저항/RR 3등급" in assistant_response
    assert "등급 숫자가 낮을수록" in assistant_response


def test_metric_comparison_policy_answers_latest_product_confidently() -> None:
    text = "dynapro HPX, dynapro HP3 중에 최신상품이 뭐야? 헷갈리넹"
    current_user_text.set(text)
    current_discovery_response_decision.set(decide_discovery_response(build_discovery_intent_frame(text)))

    result = try_build_template(_attribute_compare_search_entries()[1:], "보통 HPX 쪽으로 보시면 돼요.")

    assert result is not None
    assistant_response = result["data"]["assistantResponse"]
    assert "최신 상품은 다이나프로 HP3입니다." in assistant_response
    assert "- 다이나프로 HP3: 등록일 2025-01-20, 출시 2025년 2월" in assistant_response
    assert "- 다이나프로 HPX: 등록일 2022-11-10, 출시 2023년 1월" in assistant_response
    assert "보통" not in assistant_response


def test_mileage_value_recommendation_uses_life_score_when_catalog_fields_are_missing() -> None:
    current_user_text.set("마일리지 좋은 타이어")

    result = try_build_template([_mileage_value_recommendation_entry()], "마일리지 좋은 타이어를 추천드릴게요.")

    assert result is not None
    assert result["template"] == "quickReply"
    assistant_response = result["data"]["assistantResponse"]
    assert "마일리지/수명 성능이 확인된 타이어입니다." in assistant_response
    assert "수명/마일리지 성능이 강점인 타이어입니다." in assistant_response
    assert "상품 정보가 확인된 타이어입니다." not in assistant_response


def test_unsized_transaction_flow_still_maps_to_product_cards() -> None:
    current_pending_intent.set("stock")
    current_goal_type.set("store_with_stock")

    result = try_build_template([_unsized_recommendation_entry()], "상품을 검색했습니다.")

    assert result is not None
    assert result["template"] == "product"


def test_recommendation_with_car_lnc_cd_maps_to_product_cards() -> None:
    entry = _unsized_recommendation_entry()
    entry["args"] = {"rcmd_type": "performance", "limit": 3, "brand_cd": "HK", "car_lnc_cd": "W011338"}

    result = try_build_template([entry], "추천 상품을 확인했어요.")

    assert result is not None
    assert result["template"] == "product"


def test_listcar_metadata_includes_member_car_reg_seq_for_auto_selection() -> None:
    result = try_build_template([_registered_vehicle_entry()], "고객님, 등록된 차량 1대입니다. 차량을 선택해 주세요.")

    assert result is not None
    assert result["template"] == "listCar"
    assert result["data"]["metadata"][0]["mbrCarRegSeq"] == "2000002944"


def test_ev_suitability_maps_to_quickreply_for_explanation_turn() -> None:
    current_ev_suitability_comparison.set(True)

    result = try_build_template([_product_entry()], "전기차에는 전기차 전용 타이어가 유리합니다.")

    assert result is not None
    assert result["template"] == "quickReply"
    assistant_response = result["data"]["assistantResponse"]
    assert "차량 카테고리만으로는 특정 상품이나 규격을 바로 추천드리기 어렵습니다" in assistant_response
    assert "보유차량을 확인하거나 차종을 알려주시면" in assistant_response
    assert result["data"]["quickReplies"][0] == {"label": "보유차량 확인", "domain": "DISCOVERY"}
    assert "235/35R20" not in assistant_response
    assert "현재 조회된 상품 기준" not in assistant_response


def test_force_keyword_routing_sends_owned_vehicle_check_to_discovery() -> None:
    result = StreamingMultiAgentCoordinator._force_keyword_routing("보유차량 확인")

    assert result is not None
    assert result.domains == [MultiAgentDomain.Domain.DISCOVERY]


def test_ev_suitability_does_not_override_stock_product_flow() -> None:
    current_ev_suitability_comparison.set(True)
    current_pending_intent.set("stock")
    current_goal_type.set("store_with_stock")

    result = try_build_template([_product_entry()], "상품을 검색했습니다.")

    assert result is not None
    assert result["template"] == "product"


# --------------------------------------------------------------------------- #
#  Bug fix: region_code search with 1 store → location card emitted
# --------------------------------------------------------------------------- #


def test_region_code_with_single_store_emits_location() -> None:
    """User typed only 지역 ("한남"); BE returned 1 store. Card MUST render
    so user can pick — they have not named a store yet, so the infinite-loop
    pattern does not apply."""
    current_pending_intent.set("order")
    entry = _store_list_entry(
        args={"region_code": "한남", "limit": 10},
        stores=[_stub_store("F07782", "티스테이션 한남점")],
    )
    result = _map_location([entry], "고객님, 주소에 '한남'이 포함된 매장을 검색했어요.")

    assert result is not None
    assert result["template"] == "location"
    assert len(result["data"]["stores"]) == 1
    assert result["data"]["stores"][0]["nameAddress"] == "티스테이션 한남점"


def test_region_code_with_multiple_stores_emits_location() -> None:
    """Regression: multi-store region search must keep working."""
    current_pending_intent.set("order")
    entry = _store_list_entry(
        args={"region_code": "강남", "limit": 10},
        stores=[
            _stub_store("F00001", "티스테이션 강남점"),
            _stub_store("F00002", "티스테이션 역삼점"),
        ],
    )
    result = _map_location([entry], "고객님, 주소에 '강남'이 포함된 매장을 검색했어요.")

    assert result is not None
    assert result["template"] == "location"
    assert len(result["data"]["stores"]) == 2


def test_preview_location_filters_to_inventory_positive_stores() -> None:
    """Composite preview returns candidate stores plus inventory arrays. The
    location card must show only stores that actually have stock."""
    current_pending_intent.set("stock")
    entry = _preview_entry(
        args={"region_code": "강릉"},
        stores=[
            _stub_store("F00518", "티스테이션 강릉MBC점"),
            _stub_store("T02396", "티스테이션 강릉강남점"),
            _stub_store("F00405", "티스테이션 경포점"),
        ],
        inventory={"todayShopArray": [{"shopId": "T02396"}], "tnaShopArray": []},
    )

    result = _map_location([entry], "강릉에서 재고와 예약 가능 시간을 확인했어요.")

    assert result is not None
    assert result["template"] == "location"
    assert result["data"]["assistantResponse"] == "강릉에서 오늘 장착 가능한 매장입니다. 원하시는 매장을 선택해 주세요."
    assert len(result["data"]["stores"]) == 1
    assert result["data"]["stores"][0]["nameAddress"] == "티스테이션 강릉강남점"
    assert result["data"]["stores"][0]["todayInstall"] is True
    assert "[매장재고]" in result["data"]["stores"][0]["description"]
    assert result["data"]["metadata"] == [{"shopId": "T02396"}]


def test_preview_location_does_not_filter_order_preview_candidates() -> None:
    """Order/reservation previews may intentionally show fulfillment candidates.
    Inventory filtering is limited to stock-check contexts."""
    current_pending_intent.set("order")
    entry = _preview_entry(
        args={"region_code": "강릉"},
        stores=[
            _stub_store("F00518", "티스테이션 강릉MBC점"),
            _stub_store("T02396", "티스테이션 강릉강남점"),
            _stub_store("F00405", "티스테이션 경포점"),
        ],
        inventory={"todayShopArray": [{"shopId": "T02396"}], "tnaShopArray": []},
    )

    result = _map_location([entry], "강릉에서 주문 가능한 매장을 확인했어요.")

    assert result is not None
    assert result["template"] == "location"
    assert len(result["data"]["stores"]) == 3
    assert result["data"]["metadata"] == [{"shopId": "F00518"}, {"shopId": "T02396"}, {"shopId": "F00405"}]


def test_order_preview_logistics_only_location_explains_today_unavailable() -> None:
    """When preview tier is logistics_only, the location copy must not imply today install."""
    current_pending_intent.set("order")
    current_user_text.set("dynapro HPX 오늘 장착 가능한 근처 매장 알려줘")
    entry = {
        "tool": "transaction_store_preview_tool",
        "args": {"goods_no": "G000000317682", "ord_qty": 4, "region_code": "강남", "include_price": True},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "stores": [_stub_store("F00002", "티스테이션 역삼점")],
                "inventory": {"todayShopArray": [], "tnaShopArray": []},
                "schedule": {
                    "tier": "logistics_only",
                    "stores": [{
                        "shop_id": "F00002",
                        "mode": "logistics_only",
                        "shop_nm": "티스테이션 역삼점",
                        "slots": [{"cal_day": "20260529", "tm": "09"}],
                    }],
                },
            },
        },
    }

    result = _map_location([entry], "고객님, 매장 1곳을 안내드립니다. 원하시는 매장을 선택해 주세요.")

    assert result is not None
    assert result["template"] == "location"
    assert result["assistant_response_source"] == "code_mapper"
    assert result["data"]["assistantResponse"] == (
        "강남에서 오늘 바로 장착 가능한 매장은 없어요. "
        "물류 배송 후 장착 가능한 매장 1곳입니다. 원하시는 매장을 선택해 주세요."
    )
    assert result["data"]["stores"][0]["nameAddress"] == "티스테이션 역삼점"
    assert result["data"]["stores"][0]["todayInstall"] is False


def test_guarded_preview_forces_location_even_when_llm_emits_quickreply() -> None:
    """Regression: preview tools store their raw result under `data`, not `output`.

    When the LLM also emits fenced quickReply JSON, BaseAgent must still honor
    the tool's deterministic guard and use the code mapper so the store list is
    rendered.
    """
    current_pending_intent.set("order")
    entry = _preview_entry_with_guard(
        args={"goods_no": "G000000309778", "ord_qty": 4, "region_code": "분당", "include_price": True},
        stores=[
            _stub_store("F00071", "티스테이션 분당정자점"),
            _stub_store("F00721", "티스테이션 판교점"),
        ],
    )
    accumulated_text = (
        '```json\n'
        '{"type":"data","template":"quickReply",'
        '"data":{"assistantResponse":"주소에 분당이 포함된 매장을 검색했어요.","quickReplies":[]}}\n'
        '```'
    )

    result = BaseAgent._try_code_template([entry], None, accumulated_text)

    assert result is not None
    assert result["template"] == "location"
    assert result["data"]["assistantResponse"] == "분당 근처 주문 가능한 매장입니다. 원하시는 매장을 선택해 주세요."
    assert [store["nameAddress"] for store in result["data"]["stores"]] == [
        "티스테이션 분당정자점",
        "티스테이션 판교점",
    ]


def test_preview_single_scheduled_store_maps_to_datepick_for_booking() -> None:
    """When preview already found one bookable store, reservation flow should
    show datepick directly instead of all candidate stores."""
    current_pending_intent.set("order")
    entry = _preview_entry_with_schedule(
        args={"region_code": "강릉"},
        stores=[
            _stub_store("F00518", "티스테이션 강릉MBC점"),
            _stub_store("T02396", "티스테이션 강릉강남점"),
            _stub_store("F00405", "티스테이션 경포점"),
        ],
        schedule_stores=[{
            "shop_id": "T02396",
            "shop_nm": "티스테이션 강릉강남점",
            "slots": [
                {"cal_day": "20260521", "tm": "09"},
                {"cal_day": "20260521", "tm": "12"},
                {"cal_day": "20260521", "tm": "13"},
                {"cal_day": "20260522", "tm": "10"},
            ],
        }],
    )

    result = try_build_template([entry], "원하시는 날짜와 시간을 선택해 주세요.")

    assert result is not None
    assert result["template"] == "datepick"
    assert result["data"]["metadata"] == {"shopId": "T02396", "shopName": "티스테이션 강릉강남점"}
    assert result["data"]["dates"] == [
        {
            "date": "2026년 5월 21일 (목)",
            "available": True,
            "availableTimes": [9, 13],
            "index": 0,
        },
        {
            "date": "2026년 5월 22일 (금)",
            "available": True,
            "availableTimes": [10],
            "index": 1,
        },
    ]


def test_today_service_question_dates_pick_answers_with_earliest_available_date() -> None:
    current_pending_intent.set("stock")
    current_goal_type.set("store_with_stock")
    current_user_text.set(
        "키너지 EX 분당판교점에서 오늘서비스로 4개 구매 가능해?\n키너지 EX 205/65R16\n판교 지역 검색"
    )
    entry = _schedule_entry(
        mode="general",
        is_installable=True,
        slots=[
            {"cal_day": "20260529", "tm": "08"},
            {"cal_day": "20260529", "tm": "09"},
        ],
    )

    result = _map_datepick([entry], "예약 가능한 날짜와 시간을 선택해 주세요.")

    assert result is not None
    assert result["template"] == "datepick"
    assert result["assistant_response_source"] == "code_mapper_today_service"
    assert (
        result["data"]["assistantResponse"]
        == "오늘서비스는 어렵고, 가장 빠른 예약 가능 일정은 2026년 5월 29일 (금)부터예요. 가능한 날짜와 시간을 선택해 주세요."
    )


def test_other_store_request_after_preview_schedule_does_not_emit_datepick() -> None:
    """User asked for alternative stores, not another schedule picker for the same store."""
    current_pending_intent.set("order")
    current_user_text.set("다른 매장은 없어?")
    entry = _preview_entry_with_schedule(
        args={"goods_no": "G000000317732", "ord_qty": 4, "region_code": "분당", "include_price": True},
        stores=[_stub_store("F00721", "티스테이션 판교점")],
        schedule_stores=[{
            "shop_id": "F00721",
            "mode": "tna_only",
            "shop_nm": "티스테이션 판교점",
            "is_installable": True,
            "is_tna_delivery": True,
            "slots": [
                {"cal_day": "20260526", "tm": "09"},
                {"cal_day": "20260526", "tm": "10"},
            ],
        }],
    )

    result = try_build_template([entry], "현재 조건으로는 티스테이션 판교점만 예약 가능해요.")

    assert result is not None
    assert result["template"] == "quickReply"
    assert result["data"]["assistantResponse"] == "현재 조건으로는 티스테이션 판교점만 예약 가능해요. 다른 지역으로도 찾아드릴까요?"
    assert [chip["label"] for chip in result["data"]["quickReplies"]] == ["다른 지역 찾기", "다른 상품 보기"]


def test_preview_single_scheduled_store_keeps_stock_location_flow() -> None:
    """Stock-store checks must still render the stock-positive location card."""
    current_pending_intent.set("stock")
    entry = _preview_entry_with_schedule(
        args={"region_code": "강릉"},
        stores=[
            _stub_store("F00518", "티스테이션 강릉MBC점"),
            _stub_store("T02396", "티스테이션 강릉강남점"),
            _stub_store("F00405", "티스테이션 경포점"),
        ],
        schedule_stores=[{
            "shop_id": "T02396",
            "shop_nm": "티스테이션 강릉강남점",
            "slots": [{"cal_day": "20260521", "tm": "09"}],
        }],
    )

    result = try_build_template([entry], "강릉에서 재고가 확인된 매장입니다.")

    assert result is not None
    assert result["template"] == "location"
    assert len(result["data"]["stores"]) == 1
    assert result["data"]["metadata"] == [{"shopId": "T02396"}]


def test_exact_order_preview_maps_to_datepick_even_if_pending_stock_context_lingers() -> None:
    """A named-store order preview already has price, qty, and schedule slots.
    It must render datepick even when a previous stock intent lingers in slots."""
    current_pending_intent.set("stock")
    entry = _preview_entry_with_schedule(
        args={
            "goods_no": "G000000309780",
            "ord_qty": 4,
            "store_nm": "티스테이션 강릉MBC점",
            "include_price": True,
        },
        stores=[_stub_store("F00518", "티스테이션 강릉MBC점")],
        schedule_stores=[{
            "shop_id": "F00518",
            "mode": "logistics_only",
            "shop_nm": "티스테이션 강릉MBC점",
            "is_installable": True,
            "is_tna_delivery": True,
            "slots": [
                {"cal_day": "20260527", "tm": "09"},
                {"cal_day": "20260527", "tm": "12"},
                {"cal_day": "20260527", "tm": "13"},
                {"cal_day": "20260528", "tm": "10"},
            ],
        }],
    )

    result = try_build_template([entry], "티스테이션 강릉MBC점의 예약 가능한 일정을 확인했어요.")

    assert result is not None
    assert result["template"] == "datepick"
    assert result["data"]["metadata"] == {"shopId": "F00518", "shopName": "티스테이션 강릉MBC점"}
    assert result["data"]["dates"] == [
        {
            "date": "2026년 5월 27일 (수)",
            "available": True,
            "availableTimes": [9, 13],
            "index": 0,
        },
        {
            "date": "2026년 5월 28일 (목)",
            "available": True,
            "availableTimes": [10],
            "index": 1,
        },
    ]


def test_general_schedule_maps_to_datepick_even_when_online_install_unavailable() -> None:
    """`is_installable=false` means online tire installation is unavailable,
    not that a general store-visit schedule should be hidden."""
    entry = _schedule_entry(
        mode="general",
        is_installable=False,
        slots=[
            {"cal_day": "20260521", "tm": "09"},
            {"cal_day": "20260521", "tm": "12"},
            {"cal_day": "20260521", "tm": "13"},
            {"cal_day": "20260522", "tm": "10"},
        ],
    )

    result = try_build_template([entry], "티스테이션 경포점의 예약 가능한 일정을 확인했어요.")

    assert result is not None
    assert result["template"] == "datepick"
    assert result["data"]["metadata"] == {"shopId": "F00405", "shopName": "티스테이션 경포점"}
    assert result["data"]["dates"] == [
        {
            "date": "2026년 5월 21일 (목)",
            "available": True,
            "availableTimes": [9, 13],
            "index": 0,
        },
        {
            "date": "2026년 5월 22일 (금)",
            "available": True,
            "availableTimes": [10],
            "index": 1,
        },
    ]


def test_order_schedule_still_blocks_datepick_when_online_install_unavailable() -> None:
    """Non-general schedule modes still require an installable store."""
    entry = _schedule_entry(
        mode="in_store_only",
        is_installable=False,
        slots=[{"cal_day": "20260521", "tm": "09"}],
    )

    result = try_build_template([entry], "예약 가능한 일정을 확인했어요.")

    assert result is None


def test_specific_date_store_availability_maps_detail_slots_to_datepick() -> None:
    """A single-date open/holiday question should show the concrete slots,
    even when no product/order booking tool ran in the same turn."""
    current_store_date_availability.set(True)
    entry = _store_detail_entry(cal_day="20260606", available_slots=["09", "10", "11", "13", "14", "15", "16", "17"])

    result = try_build_template([entry], "고객님, 티스테이션 송파오금점 매장 정보를 안내드릴게요.")

    assert result is not None
    assert result["template"] == "datepick"
    assert result["data"]["assistantResponse"] == "2026년 6월 6일 (토) 티스테이션 송파오금점은 영업하며 예약 가능한 시간이 있습니다."
    assert result["data"]["metadata"] == {"shopId": "C01312", "shopName": "티스테이션 송파오금점"}
    assert result["data"]["dates"] == [{
        "date": "2026년 6월 6일 (토)",
        "available": True,
        "availableTimes": [9, 10, 11, 13, 14, 15, 16, 17],
        "index": 0,
    }]


def test_plain_store_detail_with_slots_still_maps_to_info_quickreply() -> None:
    """Plain store-info lookups should not turn into a reservation picker just
    because `get_store_detail_tool` always returns today's available slots."""
    entry = _store_detail_entry(cal_day="20260606", available_slots=["09", "10"])

    result = try_build_template([entry], "고객님, 티스테이션 송파오금점 매장 정보를 안내드릴게요.")

    assert result is not None
    assert result["template"] == "quickReply"
    assert "매장명: 티스테이션 송파오금점" in result["data"]["assistantResponse"]
    assert "예약 가능한 시간이 있습니다" not in result["data"]["assistantResponse"]


def test_date_only_followup_after_reservation_query_maps_detail_slots_to_datepick() -> None:
    current_user_text.set("티스테이션 성남IC점 5/29 오후 16시 예약 돼?\n5/30은?")
    entry = _store_detail_entry(cal_day="20260530", available_slots=["09", "10", "11", "13", "14", "15", "16", "17"])

    result = try_build_template([entry], "고객님, 티스테이션 성남IC점 매장 정보를 안내드릴게요.")

    assert result is not None
    assert result["template"] == "datepick"
    assert result["data"]["assistantResponse"] == "2026년 5월 30일 (토) 티스테이션 송파오금점은 영업하며 예약 가능한 시간이 있습니다."
    assert result["data"]["metadata"] == {"shopId": "C01312", "shopName": "티스테이션 송파오금점"}


# --------------------------------------------------------------------------- #
#  Preserved guard: store_nm search with 1 store → None (infinite-loop block)
# --------------------------------------------------------------------------- #


def test_store_nm_with_single_store_returns_none() -> None:
    """User explicitly typed a branch name ("강남점") → 1-store result is a
    shop_id resolution turn. Card emit would re-send the store name on FE
    click → infinite loop. Guard must still fire."""
    current_pending_intent.set("order")
    entry = _store_list_entry(
        args={"store_nm": "강남점"},
        stores=[_stub_store("F00001", "티스테이션 강남점")],
    )
    result = _map_location([entry], "")
    assert result is None


def test_store_nm_with_multiple_stores_emits_location() -> None:
    """`store_nm="강남점"` matching multiple branches (e.g. "강릉강남점") still
    needs the card so user can disambiguate."""
    current_pending_intent.set("order")
    entry = _store_list_entry(
        args={"store_nm": "강남점"},
        stores=[
            _stub_store("F00001", "티스테이션 강남점"),
            _stub_store("F90001", "티스테이션 강릉강남점"),
        ],
    )
    result = _map_location([entry], "")
    assert result is not None
    assert result["template"] == "location"
    assert len(result["data"]["stores"]) == 2


# --------------------------------------------------------------------------- #
#  No booking intent → mapper defers regardless of arg shape
# --------------------------------------------------------------------------- #


def test_no_booking_intent_defers_to_llm() -> None:
    """Without booking intent / goal / list-browsing, mapper returns None so
    Flow 5 info-only lookups keep their text answer."""
    # pending_intent stays None via autouse fixture
    entry = _store_list_entry(
        args={"region_code": "한남"},
        stores=[_stub_store("F07782", "티스테이션 한남점")],
    )
    result = _map_location([entry], "")
    assert result is None


# --------------------------------------------------------------------------- #
#  Favorite stores: always render, even without booking intent
# --------------------------------------------------------------------------- #


def _favorite_stores_entry(stores: list[dict]) -> dict:
    """Build a `get_favorite_stores_tool` tool_data entry."""
    return {
        "tool": "get_favorite_stores_tool",
        "args": {},
        "data": {"status": "success", "http_status": 200, "data": {"stores": stores}},
    }


def test_favorite_stores_renders_without_booking_intent() -> None:
    """Pure 단골매장 조회 ("내 단골매장 보여줘") has no booking intent / goal,
    but the user explicitly asked for the list — the card MUST render so
    they can click to select."""
    # pending_intent stays None via autouse fixture — confirms bypass works
    entry = _favorite_stores_entry([
        _stub_store("F07782", "티스테이션 한남점"),
        _stub_store("F00721", "티스테이션 판교점"),
    ])
    result = _map_location([entry], "단골매장이에요. 원하시는 매장을 선택해 주세요 😊")

    assert result is not None
    assert result["template"] == "location"
    assert len(result["data"]["stores"]) == 2
    # No booking signal/intent — card stays in info mode (FE just shows
    # description on click, doesn't advance flow).
    assert result["data"]["isBookingFlow"] is False


def test_favorite_stores_single_result_still_renders_card() -> None:
    """단골 1개 보유 회원도 자동 선택하지 않고 카드를 보여줘 사용자 클릭을 기다린다."""
    entry = _favorite_stores_entry([_stub_store("F03077", "티스테이션 모란점")])
    result = _map_location([entry], "단골매장이에요. 매장을 선택해 주세요 😊")

    assert result is not None
    assert result["template"] == "location"
    assert len(result["data"]["stores"]) == 1
    assert result["data"]["stores"][0]["nameAddress"] == "티스테이션 모란점"


def test_favorite_stores_with_booking_intent_sets_booking_flow() -> None:
    """주문 의도 컨텍스트에서 사용자가 단골을 골랐을 때는 isBookingFlow=True 로
    카드 클릭이 /chat 라우팅 (다음 단계로 진행)."""
    current_pending_intent.set("order")
    entry = _favorite_stores_entry([_stub_store("F03077", "티스테이션 모란점")])
    result = _map_location([entry], "단골 매장으로 주문 진행할게요 😊")

    assert result is not None
    assert result["template"] == "location"
    assert result["data"]["isBookingFlow"] is True


def test_favorite_stores_dispatched_via_try_build_template() -> None:
    """Dispatch regression test — `try_build_template` (called by chat.py)
    must route `get_favorite_stores_tool` to `_map_location` via the
    `_MAPPERS` / `_PRIORITY` tables. Earlier the tool was wired into the
    info-only guard bypass and `_TOOL_TEMPLATE_MAP` but not into the
    dispatch tables, so live chat fell through to the LLM and emitted a
    dead-end quickReply instead of the location card."""
    entry = _favorite_stores_entry([_stub_store("F00721", "티스테이션 판교점")])
    result = try_build_template([entry], "등록된 단골매장을 확인했어요.")

    assert result is not None, (
        "try_build_template returned None — favorite-stores tool is not "
        "registered in _MAPPERS / _PRIORITY dispatch tables"
    )
    assert result["template"] == "location"
    assert len(result["data"]["stores"]) == 1
    assert result["data"]["stores"][0]["nameAddress"] == "티스테이션 판교점"


def test_stock_channel_followup_builds_preview_guard_args() -> None:
    """A channel-only follow-up in stock flow must re-run inventory preview,
    not render the generic store-search result."""
    messages = [
        {
            "role": "assistant",
            "content": (
                "[확인된 고객 정보]\n"
                "- 상품번호: G000000319448\n"
                "- 수량: 2\n"
                "[사용자의 진행 중인 요청: 재고 확인]"
            ),
        },
        {"role": "user", "content": "티스테이션으로"},
    ]
    store_search = {
        "tool": "search_stores_tool",
        "args": {"place_query": "강남구청", "chl_sct_cd": "F", "limit": 10},
        "data": {"status": "success", "data": {"stores": [_stub_store("F00098", "티스테이션 역삼점")]}},
    }

    result = _build_stock_preview_guard_args([store_search], messages)

    assert result == {
        "goods_no": "G000000319448",
        "ord_qty": 2,
        "region_code": "강남구청",
        "include_price": True,
        "all_my_t_only": False,
        "imported_car_only": False,
        "chl_sct_cd": "F",
    }


def test_stock_preview_guard_skips_info_only_store_followup() -> None:
    messages = [
        {
            "role": "assistant",
            "content": (
                "[확인된 고객 정보]\n"
                "- 상품번호: G000000319448\n"
                "- 수량: 2\n"
                "[사용자의 진행 중인 요청: 재고 확인]"
            ),
        },
        {"role": "user", "content": "티스테이션 역삼점 영업시간 알려줘"},
    ]
    store_search = {
        "tool": "search_stores_tool",
        "args": {"store_nm": "티스테이션 역삼점", "chl_sct_cd": "F", "limit": 10},
        "data": {"status": "success", "data": {"stores": [_stub_store("F00098", "티스테이션 역삼점")]}},
    }

    assert _build_stock_preview_guard_args([store_search], messages) is None


def test_stock_context_empty_inventory_blocks_schedule_datepick() -> None:
    """If store inventory already proved no stock, a same-turn schedule call
    must not be rendered as an installable datepick."""
    current_pending_intent.set("stock")
    current_goal_type.set("store_with_stock")
    inventory_entry = {
        "tool": "get_store_inventory_tool",
        "args": {
            "goods_list": [{"goodsNo": "G000000319448", "qty": "2"}],
            "shop_id_list": [{"shopId": "F00098"}],
        },
        "data": {"status": "success", "http_status": 200, "data": {"todayShopArray": [], "tnaShopArray": []}},
    }
    schedule_entry = {
        "tool": "get_store_schedule_tool",
        "args": {"shop_id": "F00098", "mode": "general"},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "shop_id": "F00098",
                "shop_nm": "티스테이션 역삼점",
                "mode": "general",
                "is_installable": True,
                "slots": [{"cal_day": "20260523", "tm": "09"}],
            },
        },
    }

    assert _map_datepick([inventory_entry, schedule_entry], "예약 가능한 일정을 확인했어요.") is None


def test_logistics_only_schedule_with_slots_survives_empty_inventory() -> None:
    current_pending_intent.set("stock")
    current_goal_type.set("store_with_stock")
    inventory_entry = {
        "tool": "get_store_inventory_tool",
        "args": {
            "goods_list": [{"goodsNo": "G000000319448", "qty": "2"}],
            "shop_id_list": [{"shopId": "F00098"}],
        },
        "data": {"status": "success", "http_status": 200, "data": {"todayShopArray": [], "tnaShopArray": []}},
    }
    schedule_entry = {
        "tool": "get_store_schedule_tool",
        "args": {"shop_id": "F00098", "mode": "logistics_only"},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "shop_id": "F00098",
                "shop_nm": "티스테이션 역삼점",
                "mode": "logistics_only",
                "is_installable": False,
                "is_tna_delivery": False,
                "slots": [{"cal_day": "20260529", "tm": "13"}],
            },
        },
    }

    result = _map_datepick([inventory_entry, schedule_entry], "예약 가능한 일정을 확인했어요.")

    assert result is not None
    assert result["template"] == "datepick"
    assert result["data"]["dates"][0]["availableTimes"] == [13]


def test_logistics_only_schedule_with_slots_outranks_no_stock_quickreply() -> None:
    current_pending_intent.set("stock")
    current_goal_type.set("store_with_stock")
    inventory_entry = {
        "tool": "get_store_inventory_tool",
        "args": {
            "goods_list": [{"goodsNo": "G000000319448", "qty": "2"}],
            "shop_id_list": [{"shopId": "F00098"}],
        },
        "data": {"status": "success", "http_status": 200, "data": {"todayShopArray": [], "tnaShopArray": []}},
    }
    schedule_entry = {
        "tool": "get_store_schedule_tool",
        "args": {"shop_id": "F00098", "mode": "logistics_only"},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "shop_id": "F00098",
                "shop_nm": "티스테이션 역삼점",
                "mode": "logistics_only",
                "is_installable": False,
                "is_tna_delivery": False,
                "slots": [{"cal_day": "20260529", "tm": "13"}],
            },
        },
    }

    result = try_build_template([inventory_entry, schedule_entry], "예약 가능한 날짜와 시간을 확인했어요.")

    assert result is not None
    assert result["template"] == "datepick"


def test_stock_inventory_no_stock_maps_quickreply() -> None:
    """A no-stock inventory result must be an explicit fallback, not a datepick/location."""
    current_pending_intent.set("stock")
    current_goal_type.set("store_with_stock")

    result = try_build_template([_inventory_entry()], "재고를 확인했어요.")

    assert result is not None
    assert result["template"] == "quickReply"
    assert result["assistant_response_source"] == "code_mapper"
    assert "재고가 확인되지 않았어요" in result["data"]["assistantResponse"]
    assert [chip["label"] for chip in result["data"]["quickReplies"]] == [
        "다른 매장 찾기",
        "다른 날짜 확인",
        "대체상품 찾기",
    ]


def test_stock_inventory_filters_location_to_available_shops() -> None:
    """Same-turn inventory + store list renders only stores with eligible stock."""
    current_pending_intent.set("stock")
    current_goal_type.set("store_with_stock")
    stores = [
        _stub_store("F001", "티스테이션 재고점"),
        _stub_store("F002", "티스테이션 품절점"),
    ]

    result = try_build_template(
        [
            _store_list_entry(args={"region_code": "서초"}, stores=stores),
            _inventory_entry(today_ids=["F001"]),
        ],
        "재고 있는 매장을 확인했어요.",
    )

    assert result is not None
    assert result["template"] == "location"
    assert result["assistant_response_source"] == "code_mapper"
    assert result["data"]["assistantResponse"] == "서초에서 오늘 장착 가능한 매장입니다. 원하시는 매장을 선택해 주세요."
    assert result["data"]["isBookingFlow"] is True
    assert len(result["data"]["stores"]) == 1
    assert result["data"]["stores"][0]["nameAddress"] == "티스테이션 재고점"
    assert result["data"]["stores"][0]["todayInstall"] is True


def test_preview_location_tna_stock_uses_today_install_copy() -> None:
    """TNA-only preview stock should still be phrased as today-installable."""
    current_pending_intent.set("stock")
    entry = _preview_entry(
        args={"region_code": "한남동"},
        stores=[_stub_store("F07782", "티스테이션 한남점")],
        inventory={"todayShopArray": [], "tnaShopArray": [{"shopId": "F07782"}]},
    )

    result = _map_location([entry], "한남동에서 재고와 예약 가능 시간을 확인했어요.")

    assert result is not None
    assert result["template"] == "location"
    assert result["data"]["assistantResponse"] == "한남동에서 오늘 장착 가능한 매장입니다. 원하시는 매장을 선택해 주세요."
    assert result["data"]["stores"][0]["todayInstall"] is False
    assert result["data"]["stores"][0]["tnaDelivery"] is True


def test_transaction_policy_missing_slot_blocks_location_card() -> None:
    current_pending_intent.set("stock")
    current_transaction_response_decision.set(ResponseDecision(
        response_shape=ResponseShape.CLARIFY,
        template=TemplateName.QUICK_REPLY,
        required_slots=("tire_size",),
        forbidden_behaviors=("ask_product_again",),
    ))
    entry = _store_list_entry(
        args={"region_code": "파주"},
        stores=[_stub_store("F001", "티스테이션 파주점")],
    )

    assert _map_location([entry], "매장을 확인했어요.") is None


def test_preview_instruction_allows_location_even_with_missing_store_policy() -> None:
    current_pending_intent.set("order")
    current_transaction_response_decision.set(ResponseDecision(
        response_shape=ResponseShape.CLARIFY,
        template=TemplateName.QUICK_REPLY,
        required_slots=("store",),
    ))
    entry = {
        "tool": "transaction_store_preview_tool",
        "args": {"goods_no": "G000000309977", "ord_qty": 2, "region_code": "해운대", "include_price": True},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "stores": [
                    _stub_store("F00035", "티스테이션 센텀점"),
                    _stub_store("F00124", "티스테이션 부산중동점"),
                ],
                "inventory": {"todayShopArray": [], "tnaShopArray": []},
                "schedule": {
                    "tier": "none",
                    "stores": [],
                    "candidate_shop_ids": ["F00035", "F00124"],
                },
                "candidate_shop_ids": ["F00035", "F00124"],
            },
        },
    }

    result = _map_location([entry], "주소에 '해운대'가 포함된 매장을 검색했어요. 원하시는 매장을 선택해 주세요 😊")

    assert result is not None
    assert result["template"] == "location"
    assert len(result["data"]["stores"]) == 2
    assert result["data"]["stores"][0]["nameAddress"] == "티스테이션 센텀점"


def test_named_store_preview_single_candidate_defers_to_schedule_followup() -> None:
    current_pending_intent.set("order")
    entry = {
        "tool": "transaction_store_preview_tool",
        "args": {"goods_no": "G000000309977", "ord_qty": 2, "store_nm": "티스테이션 센텀점", "include_price": True},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "stores": [_stub_store("F00035", "티스테이션 센텀점")],
                "inventory": {"todayShopArray": [], "tnaShopArray": []},
                "schedule": {
                    "tier": "none",
                    "stores": [],
                    "candidate_shop_ids": ["F00035"],
                },
                "candidate_shop_ids": ["F00035"],
            },
        },
    }

    result = _map_location([entry], "티스테이션 센텀점을 확인했어요.")

    assert result is None


def test_transaction_policy_invalid_store_blocks_datepick() -> None:
    current_transaction_response_decision.set(ResponseDecision(
        response_shape=ResponseShape.CLARIFY,
        template=TemplateName.QUICK_REPLY,
        required_slots=("store",),
        forbidden_behaviors=("datepick_for_unverified_store",),
    ))
    schedule_entry = _schedule_entry(
        mode="general",
        is_installable=True,
        slots=[{"cal_day": "20260523", "tm": "09"}],
    )

    assert _map_datepick([schedule_entry], "예약 가능한 시간을 확인했어요.") is None


def test_tc058_time_filter_location_excludes_blocked_noon_slot() -> None:
    entry = {
        "tool": "get_stores_with_time_filter_tool",
        "args": {"region_code": "서울", "time_threshold_hour": 12},
        "data": {
            "status": "success",
            "data": {
                "region_code": "서울",
                "time_threshold_hour": 12,
                "stores_available": [
                    {
                        "shop_id": "T00001",
                        "shop_nm": "티스테이션 서울점",
                        "cal_day": "20260523",
                        "qualifying_slots": [12, 13, "1400"],
                        "address": "서울특별시 강남구",
                    },
                    {
                        "shop_id": "T00002",
                        "shop_nm": "티스테이션 점심점",
                        "cal_day": "20260523",
                        "qualifying_slots": [12],
                        "address": "서울특별시 서초구",
                    },
                ],
            },
        },
    }

    result = try_build_template([entry], "12시에 작업 가능한 서울 지역 매장을 확인했어요.")

    assert result is not None
    assert result["template"] == "location"
    assert len(result["data"]["stores"]) == 1
    description = result["data"]["stores"][0]["description"]
    assert "12:00" not in description
    assert "13:00, 14:00" in description


def test_tc076_location_mapper_respects_requested_store_limit_from_user_text() -> None:
    current_goal_type.set("store_finder")
    current_user_text.set("청량리역 주변 가까운 매장 순으로 5개만")
    stores = [
        _stub_store(f"F0000{i}", f"티스테이션 청량리{i}점")
        for i in range(1, 8)
    ]
    entry = _store_list_entry(args={"region_code": "청량리"}, stores=stores)

    result = _map_location([entry], "청량리역 주변 가까운 매장을 확인했어요.")

    assert result is not None
    assert result["template"] == "location"
    assert len(result["data"]["stores"]) == 5
    assert len(result["data"]["metadata"]) == 5
    assert result["data"]["stores"][-1]["nameAddress"] == "티스테이션 청량리5점"


def test_registered_vehicle_recommendation_error_does_not_render_listcar() -> None:
    result = try_build_template(
        [_registered_vehicle_entry(), _errored_sized_recommendation_entry()],
        "고객님, 등록된 차량 7대입니다. 차량을 선택해 주세요.",
    )

    assert result is not None
    assert result["template"] == "quickReply"
    assert "235/55R19" in result["data"]["assistantResponse"]
    assert "등록된 차량" not in result["data"]["assistantResponse"]


def test_unregistered_plate_only_prompts_owner_name_instead_of_listcar() -> None:
    current_user_text.set("26저7922 에 맞는 타이어")

    result = try_build_template(
        [_registered_vehicle_entry()],
        "등록된 차량 1대를 확인했어요. 안내받으실 차량을 선택해 주세요.",
    )

    assert result is not None
    assert result["template"] == "quickReply"
    assert "26저7922" in result["data"]["assistantResponse"]
    assert "차량번호 + 소유주명" in result["data"]["assistantResponse"]


def test_owner_lookup_result_with_recommendation_renders_product_not_listcar() -> None:
    current_user_text.set("26저7922 황지훈")
    user_vehicle_entry = {
        "tool": "get_user_vehicles_tool",
        "args": {"car_no": "26저7922", "owner_nm": "황지훈"},
        "data": {
            "status": "success",
            "http_status": 200,
            "data": {
                "items": [
                    {
                        "car_no": "26저7922",
                        "car_lnc_cd": "W011338",
                        "car_nm": "올 뉴 K7 하이브리드 2.4 노블레스 A/T",
                        "car_model_det": "올 뉴 K7 하이브리드(YG) (2017 - 2019)",
                        "tire_size_fr": "225/55R17",
                        "tire_size_re": "225/55R17",
                    }
                ]
            },
        },
    }
    recommendation_entry = _recommendation_entry(
        args={"rcmd_type": "tstation", "limit": 3, "brand_cd": "HK", "car_lnc_cd": "W011338"},
        data={
            "items": [
                {
                    "goods_no": "G000000312684",
                    "goods_nm": "키너지 4S2",
                    "title": "키너지 4S2",
                    "tire_size_1": "225/55R17",
                    "brand_nm": "HANKOOK",
                    "sale_prc": 179300,
                    "price": 134500,
                    "extra_fvr_sale_prc": 134500,
                    "rating_avg": 4.4,
                    "image_url": "https://example.com/tire.png",
                    "prc_grd_nm": "스탠다드",
                    "goods_pfm_nm": "COMFORT",
                }
            ],
        },
    )

    result = try_build_template(
        [_registered_vehicle_entry(), user_vehicle_entry, recommendation_entry],
        "차량 코드 기준으로 추천해 드릴게요.",
    )

    assert result is not None
    assert result["template"] == "product"
    assert result["data"]["metadata"][0]["goodsId"] == "G000000312684"
