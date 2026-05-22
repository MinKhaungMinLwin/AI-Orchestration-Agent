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

from services.tstation.template_mapper import (
    _map_location,
    current_ev_suitability_comparison,
    current_goal_type,
    current_pending_intent,
    current_store_date_availability,
    try_build_template,
)


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
    yield
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
        "addr_base": "서울특별시 용산구",
        "addr_dtl": "한남대로 80",
        "road_addr_base": None,
        "road_addr_dtl": None,
        "tel_no": "02-790-2921",
        "svc_codes": ["113"],
    }


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


def test_ev_suitability_maps_to_quickreply_for_explanation_turn() -> None:
    current_ev_suitability_comparison.set(True)

    result = try_build_template([_product_entry()], "전기차에는 전기차 전용 타이어가 유리합니다.")

    assert result is not None
    assert result["template"] == "quickReply"
    assistant_response = result["data"]["assistantResponse"]
    assert "차량 카테고리만으로는 특정 상품이나 규격을 바로 추천드리기 어렵습니다" in assistant_response
    assert "보유차량을 확인하거나 차종을 알려주시면" in assistant_response
    assert "235/35R20" not in assistant_response
    assert "현재 조회된 상품 기준" not in assistant_response


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
    assert result["data"]["assistantResponse"] == "강릉에서 재고가 확인된 매장입니다. 원하시는 매장을 선택해 주세요."
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
