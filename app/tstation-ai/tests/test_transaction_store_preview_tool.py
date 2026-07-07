from __future__ import annotations

from types import SimpleNamespace

from services.tstation.agents.c_transaction_agent import tools


class _Parsed:
    def __init__(self, data: dict):
        self._data = data

    def to_dict(self) -> dict:
        return self._data


class _Response:
    def __init__(self, data: dict, status_code: int = 200):
        self.parsed = _Parsed(data)
        self.status_code = status_code
        self.content = b""


class _GateDecision:
    def __init__(self, allowed: bool):
        self.is_domestic_search_area = allowed

    def model_dump(self) -> dict:
        return {
            "is_domestic_search_area": self.is_domestic_search_area,
            "kind": "domestic_region" if self.is_domestic_search_area else "foreign_region",
            "reason": "test decision",
        }


def test_transaction_store_preview_reuses_authenticated_client_in_worker_threads(monkeypatch):
    clients: list[str] = []
    subcall_clients: dict[str, str] = {}

    def fake_get_client():
        client = f"client-{len(clients) + 1}"
        clients.append(client)
        return client

    def fake_get_store_list(**kwargs):
        assert kwargs["client"] == "client-1"
        return _Response({
            "stores": [
                {"shop_id": "F00518", "shop_nm": "티스테이션 강릉MBC점", "is_installable": True},
                {"shop_id": "T02396", "shop_nm": "티스테이션 강릉강남점", "is_installable": True},
            ]
        })

    def fake_get_logistics_inventory(*, client, body):
        subcall_clients["logistics"] = client
        return _Response({"logistics_qty": 256, "rsv_sale_yn": "N", "rsv_install_date": None})

    def fake_get_store_inventory(*, client, body):
        subcall_clients["store_inventory"] = client
        return _Response({"todayShopArray": [{"shopId": "T02396"}], "tnaShopArray": []})

    def fake_get_price(*, client, goods_no, member_type):
        subcall_clients["price"] = client
        return _Response({"final_price": 120800})

    monkeypatch.setattr(tools, "get_client", fake_get_client)
    monkeypatch.setattr(tools, "get_store_list", fake_get_store_list)
    monkeypatch.setattr(tools, "get_logistics_inventory", fake_get_logistics_inventory)
    monkeypatch.setattr(tools, "get_store_inventory", fake_get_store_inventory)
    monkeypatch.setattr(tools, "get_price", fake_get_price)
    monkeypatch.setattr(
        tools,
        "get_multi_store_schedule_tool",
        SimpleNamespace(func=lambda **kwargs: {"data": {"tier": "today", "stores": ["T02396"]}}),
    )

    result = tools.transaction_store_preview_tool.func(
        goods_no="G000000309780",
        ord_qty=4,
        region_code="강릉",
        include_price=True,
    )

    assert result["status"] == "success"
    assert result["data"]["logistics"]["logistics_qty"] == 256
    assert result["data"]["inventory"]["todayShopArray"] == [{"shopId": "T02396"}]
    assert result["data"]["price"] == {"final_price": 120800}
    assert subcall_clients == {
        "logistics": "client-2",
        "store_inventory": "client-2",
        "price": "client-2",
    }
    assert clients == ["client-1", "client-2"]


def test_transaction_store_preview_falls_back_to_place_coordinates_for_landmark_region(monkeypatch):
    store_calls: list[dict] = []

    def fake_get_client():
        return "client"

    def fake_get_store_list(**kwargs):
        store_calls.append(kwargs)
        if kwargs.get("region_code") == "강남구청":
            return _Response({"stores": []})
        assert kwargs["xpos"] == 127.0473
        assert kwargs["ypos"] == 37.5172
        return _Response({
            "stores": [
                {"shop_id": "F10001", "shop_nm": "티스테이션 강남구청점", "is_installable": True, "distance_km": 0.8},
            ]
        })

    def fake_search_place(**kwargs):
        assert kwargs["query"] == "강남구청"
        return _Response({
            "items": [{
                "place_name": "강남구청",
                "address_name": "서울 강남구 학동로",
                "x": "127.0473",
                "y": "37.5172",
            }]
        })

    monkeypatch.setattr(tools, "get_client", fake_get_client)
    monkeypatch.setattr(tools, "get_store_list", fake_get_store_list)
    monkeypatch.setattr(tools, "search_place", fake_search_place)
    monkeypatch.setattr(tools, "decide_domestic_search_area", lambda query: _GateDecision(True))
    monkeypatch.setattr(tools, "get_logistics_inventory", lambda **kwargs: _Response({"logistics_qty": 0}))
    monkeypatch.setattr(
        tools,
        "get_store_inventory",
        lambda **kwargs: _Response({"todayShopArray": [{"shopId": "F10001"}], "tnaShopArray": []}),
    )
    monkeypatch.setattr(tools, "get_price", lambda **kwargs: _Response({"final_price": 120800}))
    monkeypatch.setattr(
        tools,
        "get_multi_store_schedule_tool",
        SimpleNamespace(func=lambda **kwargs: {"data": {"tier": "today", "stores": ["F10001"]}}),
    )

    result = tools.transaction_store_preview_tool.func(
        goods_no="G000000309780",
        ord_qty=4,
        region_code="강남구청",
        include_price=True,
    )

    assert result["status"] == "success"
    assert result["data"]["stores"][0]["shop_id"] == "F10001"
    assert result["data"]["search"]["source"] == "place_fallback"
    assert [call.get("region_code") for call in store_calls] == ["강남구청", None]


def test_transaction_store_preview_filters_schedule_by_requested_cal_day(monkeypatch):
    def fake_get_client():
        return "client"

    def fake_get_store_list(**kwargs):
        return _Response({
            "stores": [
                {"shop_id": "T10001", "shop_nm": "티스테이션 강남점", "is_installable": True},
                {"shop_id": "T10002", "shop_nm": "티스테이션 역삼점", "is_installable": True},
            ]
        })

    monkeypatch.setattr(tools, "get_client", fake_get_client)
    monkeypatch.setattr(tools, "get_store_list", fake_get_store_list)
    monkeypatch.setattr(tools, "get_logistics_inventory", lambda **kwargs: _Response({"logistics_qty": 20}))
    monkeypatch.setattr(tools, "get_store_inventory", lambda **kwargs: _Response({"todayShopArray": [], "tnaShopArray": []}))
    monkeypatch.setattr(tools, "get_price", lambda **kwargs: _Response({"final_price": 120800}))
    monkeypatch.setattr(
        tools,
        "get_multi_store_schedule_tool",
        SimpleNamespace(func=lambda **kwargs: {
            "data": {
                "tier": "logistics_only",
                "stores": [
                    {
                        "shop_id": "T10001",
                        "slots": [
                            {"cal_day": "20260617", "tm": "1000"},
                            {"cal_day": "20260618", "tm": "1100"},
                        ],
                    },
                    {"shop_id": "T10002", "slots": [{"cal_day": "20260618", "tm": "0900"}]},
                ],
                "candidate_shop_ids": ["T10001", "T10002"],
            }
        }),
    )

    result = tools.transaction_store_preview_tool.func(
        goods_no="G000000320153",
        ord_qty=2,
        region_code="강남",
        requested_cal_day="20260617",
    )

    assert result["status"] == "success"
    assert result["data"]["requested_cal_day"] == "20260617"
    assert [store["shop_id"] for store in result["data"]["stores"]] == ["T10001"]
    assert result["data"]["candidate_shop_ids"] == ["T10001"]
    assert result["data"]["schedule"]["requested_cal_day"] == "20260617"
    assert result["data"]["schedule"]["stores"] == [{
        "shop_id": "T10001",
        "slots": [{"cal_day": "20260617", "tm": "1000"}],
    }]


def test_transaction_store_preview_requested_cal_day_removes_all_non_matching_candidates(monkeypatch):
    monkeypatch.setattr(tools, "get_client", lambda: "client")
    monkeypatch.setattr(
        tools,
        "get_store_list",
        lambda **kwargs: _Response({
            "stores": [{"shop_id": "T10001", "shop_nm": "티스테이션 강남점", "is_installable": True}]
        }),
    )
    monkeypatch.setattr(tools, "get_logistics_inventory", lambda **kwargs: _Response({"logistics_qty": 20}))
    monkeypatch.setattr(tools, "get_store_inventory", lambda **kwargs: _Response({"todayShopArray": [], "tnaShopArray": []}))
    monkeypatch.setattr(tools, "get_price", lambda **kwargs: _Response({"final_price": 120800}))
    monkeypatch.setattr(
        tools,
        "get_multi_store_schedule_tool",
        SimpleNamespace(func=lambda **kwargs: {
            "data": {
                "tier": "logistics_only",
                "stores": [{"shop_id": "T10001", "slots": [{"cal_day": "20260618", "tm": "1000"}]}],
                "candidate_shop_ids": ["T10001"],
            }
        }),
    )

    result = tools.transaction_store_preview_tool.func(
        goods_no="G000000320153",
        ord_qty=2,
        region_code="강남",
        requested_cal_day="20260617",
    )

    assert result["status"] == "success"
    assert result["data"]["stores"] == []
    assert result["data"]["candidate_shop_ids"] == []
    assert result["data"]["schedule"]["tier"] == "none"
    assert result["data"]["schedule"]["stores"] == []


def test_transaction_store_preview_keeps_tna_candidates_for_today_request(monkeypatch):
    monkeypatch.setattr(tools, "get_client", lambda: "client")
    monkeypatch.setattr(
        tools,
        "get_store_list",
        lambda **kwargs: _Response({
            "stores": [
                {"shop_id": "C01317", "shop_nm": "티스테이션 송파삼전점", "is_installable": True},
                {"shop_id": "F00469", "shop_nm": "티스테이션 구로구청점", "is_installable": True},
            ]
        }),
    )
    monkeypatch.setattr(tools, "get_logistics_inventory", lambda **kwargs: _Response({"logistics_qty": 0}))
    monkeypatch.setattr(
        tools,
        "get_store_inventory",
        lambda **kwargs: _Response({
            "todayShopArray": [],
            "tnaShopArray": [{"shopId": "C01317"}, {"shopId": "F00469"}],
        }),
    )
    monkeypatch.setattr(
        tools,
        "get_multi_store_schedule_tool",
        SimpleNamespace(func=lambda **kwargs: {
            "data": {
                "tier": "tna_only",
                "stores": [
                    {"shop_id": "C01317", "slots": [{"cal_day": "20260620", "tm": "1000"}]},
                    {"shop_id": "F00469", "slots": [{"cal_day": "20260620", "tm": "1100"}]},
                ],
                "candidate_shop_ids": ["C01317", "F00469"],
            }
        }),
    )

    result = tools.transaction_store_preview_tool.func(
        goods_no="G000000317729",
        ord_qty=4,
        region_code="송파",
        requested_cal_day="20260618",
        include_price=False,
    )

    assert result["status"] == "success"
    assert result["data"]["requested_cal_day"] == "20260618"
    assert [store["shop_id"] for store in result["data"]["stores"]] == ["C01317", "F00469"]
    assert result["data"]["candidate_shop_ids"] == ["C01317", "F00469"]
    assert result["data"]["schedule"]["tier"] == "tna_only"


def test_transaction_store_preview_blocks_foreign_region_business_place_fallback(monkeypatch):
    store_calls: list[dict] = []

    def fake_get_client():
        return "client"

    def fake_get_store_list(**kwargs):
        store_calls.append(kwargs)
        if kwargs.get("region_code") == "평양":
            return _Response({"stores": []})
        raise AssertionError("Blocked region fallback must not search nearby stores by POI coordinates")

    def fake_search_place(**kwargs):
        assert kwargs["query"] == "평양"
        return _Response({
            "items": [{
                "title": "평양주유소",
                "road_addr": "충북 청주시 서원구 사운로 69",
                "x": "127.47909877093",
                "y": "36.6351814518454",
            }]
        })

    monkeypatch.setattr(tools, "get_client", fake_get_client)
    monkeypatch.setattr(tools, "get_store_list", fake_get_store_list)
    monkeypatch.setattr(tools, "search_place", fake_search_place)
    monkeypatch.setattr(tools, "decide_domestic_search_area", lambda query: _GateDecision(False))

    result = tools.transaction_store_preview_tool.func(
        goods_no="G000000319448",
        ord_qty=2,
        region_code="평양",
        include_price=True,
    )

    assert result["status"] == "success"
    assert result["data"]["stores"] == []
    assert result["data"]["search"]["source"] == "place_fallback_blocked"
    assert result["data"]["search"]["reason"] == "not_domestic_search_area"
    assert [call.get("region_code") for call in store_calls] == ["평양"]


def test_search_stores_region_zero_result_falls_back_to_place_coordinates(monkeypatch):
    store_calls: list[dict] = []

    def fake_get_client():
        return "client"

    def fake_get_store_list(**kwargs):
        store_calls.append(kwargs)
        if kwargs.get("region_code") == "광교":
            return _Response({"stores": []})
        assert kwargs["xpos"] == 127.0610
        assert kwargs["ypos"] == 37.2910
        return _Response({
            "stores": [
                {"shop_id": "F02020", "shop_nm": "티스테이션 광교중앙점", "is_installable": True},
            ]
        })

    def fake_search_place(**kwargs):
        assert kwargs["query"] == "광교"
        return _Response({
            "items": [{
                "place_name": "광교",
                "address_name": "경기 수원시 영통구",
                "x": "127.0610",
                "y": "37.2910",
            }]
        })

    monkeypatch.setattr(tools, "get_client", fake_get_client)
    monkeypatch.setattr(tools, "get_store_list", fake_get_store_list)
    monkeypatch.setattr(tools, "search_place", fake_search_place)
    monkeypatch.setattr(tools, "decide_domestic_search_area", lambda query: _GateDecision(True))

    result = tools.search_stores_tool.func(region_code="광교", limit=5)

    assert result["status"] == "success"
    assert result["data"]["stores"][0]["shop_id"] == "F02020"
    assert result["data"]["search"]["source"] == "region_place_fallback"
    assert result["data"]["search"]["returned_count"] == 1
    assert [call.get("region_code") for call in store_calls] == ["광교", None]


def test_search_stores_blocks_foreign_region_business_place_fallback(monkeypatch):
    store_calls: list[dict] = []

    def fake_get_client():
        return "client"

    def fake_get_store_list(**kwargs):
        store_calls.append(kwargs)
        if kwargs.get("region_code") == "베이징":
            return _Response({"stores": []})
        raise AssertionError("Blocked region fallback must not search nearby stores by POI coordinates")

    def fake_search_place(**kwargs):
        assert kwargs["query"] == "베이징"
        return _Response({
            "items": [{
                "title": "베이징반점",
                "road_addr": "서울 중구 세종대로",
                "x": "126.9769",
                "y": "37.5665",
            }]
        })

    monkeypatch.setattr(tools, "get_client", fake_get_client)
    monkeypatch.setattr(tools, "get_store_list", fake_get_store_list)
    monkeypatch.setattr(tools, "search_place", fake_search_place)
    monkeypatch.setattr(tools, "decide_domestic_search_area", lambda query: _GateDecision(False))

    result = tools.search_stores_tool.func(region_code="베이징", limit=5)

    assert result["status"] == "success"
    assert result["data"]["stores"] == []
    assert result["data"]["search"]["source"] == "region_place_fallback_blocked"
    assert result["data"]["search"]["reason"] == "not_domestic_search_area"
    assert [call.get("region_code") for call in store_calls] == ["베이징"]


def test_search_stores_region_gangnam_uses_gangnam_station_coordinates(monkeypatch):
    store_calls: list[dict] = []

    def fake_get_client():
        return "client"

    def fake_search_place(**kwargs):
        assert kwargs["query"] == "강남역"
        return _Response({
            "items": [{
                "place_name": "강남역",
                "address_name": "서울 강남구 강남대로",
                "x": "127.0276",
                "y": "37.4979",
            }]
        })

    def fake_get_store_list(**kwargs):
        store_calls.append(kwargs)
        assert kwargs["xpos"] == 127.0276
        assert kwargs["ypos"] == 37.4979
        return _Response({
            "stores": [
                {
                    "shop_id": "F00012",
                    "shop_nm": "티스테이션 역삼점",
                    "addr_base": "서울특별시 강남구 테헤란로",
                    "road_addr_base": "서울특별시 강남구 테헤란로",
                    "rating_idx": 4.9,
                },
                {
                    "shop_id": "F00013",
                    "shop_nm": "티스테이션 삼성점",
                    "addr_base": "서울특별시 강남구 삼성로",
                    "road_addr_base": "서울특별시 강남구 삼성로",
                    "rating_idx": 4.7,
                },
            ]
        })

    monkeypatch.setattr(tools, "get_client", fake_get_client)
    monkeypatch.setattr(tools, "search_place", fake_search_place)
    monkeypatch.setattr(tools, "get_store_list", fake_get_store_list)
    monkeypatch.setattr(
        tools,
        "_get_store_list_cached",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("강남 region search should bypass list search")),
    )

    result = tools.search_stores_tool.func(region_code="강남", sort_by="rating", limit=2)

    assert result["status"] == "success"
    assert [store["shop_id"] for store in result["data"]["stores"]] == ["F00012", "F00013"]
    assert result["data"]["search"]["source"] == "region_place_override"
    assert result["data"]["search"]["place_query"] == "강남역"
    assert result["data"]["search"]["candidate_count"] == 2
    assert result["data"]["search"]["returned_count"] == 2
    assert len(store_calls) == 1


def test_search_stores_region_rating_keeps_specific_store_name_disambiguation(monkeypatch):
    monkeypatch.setattr(
        tools,
        "_get_store_list_cached",
        lambda **kwargs: {
            "status": "success",
            "http_status": 200,
            "data": {
                "stores": [
                    {
                        "shop_id": "F00001",
                        "shop_nm": "티스테이션 강남점",
                        "addr_base": "서울특별시 강남구 도곡로",
                    },
                    {
                        "shop_id": "F90001",
                        "shop_nm": "티스테이션 강릉강남점",
                        "addr_base": "강원특별자치도 강릉시 경강로",
                    },
                ]
            },
        },
    )

    result = tools.search_stores_tool.func(store_nm="강남점", sort_by="rating", limit=5)

    assert result["status"] == "success"
    assert [store["shop_id"] for store in result["data"]["stores"]] == ["F00001", "F90001"]


def test_search_stores_region_keeps_original_results_when_no_preferred_address_match(monkeypatch):
    monkeypatch.setattr(
        tools,
        "_get_store_list_cached",
        lambda **kwargs: {
            "status": "success",
            "http_status": 200,
            "data": {
                "stores": [
                    {
                        "shop_id": "T02396",
                        "shop_nm": "티스테이션 강릉강남점",
                        "addr_base": "강원특별자치도 강릉시 경강로",
                        "road_addr_base": "강원특별자치도 강릉시 경강로",
                        "rating_idx": 4.8,
                    }
                ]
            },
        },
    )

    result = tools.search_stores_tool.func(region_code="강릉", sort_by="rating", limit=5)

    assert result["status"] == "success"
    assert [store["shop_id"] for store in result["data"]["stores"]] == ["T02396"]


def test_search_stores_complex_tool_passes_specialty_and_schedule_filters(monkeypatch):
    calls: list[dict] = []

    def fake_get_client():
        return "client"

    def fake_search_stores_complex(**kwargs):
        calls.append(kwargs)
        return _Response({
            "stores": [{
                "shop_id": "T00001",
                "shop_nm": "티스테이션 분당점",
                "is_ev_specialty": True,
                "is_open": True,
                "slots": [{"cal_day": "20260531", "tm": "1500"}],
            }]
        })

    monkeypatch.setattr(tools, "get_client", fake_get_client)
    monkeypatch.setattr(tools, "search_stores_complex", fake_search_stores_complex)

    result = tools.search_stores_complex_tool.func(
        region_code="분당",
        ev_specialty_only=True,
        cal_days=["20260531"],
        open_only=True,
        time_after_hour=15,
        limit=5,
    )

    assert result["status"] == "success"
    assert result["data"]["stores"][0]["shop_id"] == "T00001"
    assert result["data"]["search"]["filters"]["cal_days"] == ["20260531"]
    assert calls == [{
        "client": "client",
        "region_code": "분당",
        "store_nm": None,
        "xpos": None,
        "ypos": None,
        "radius_km": 20.0,
        "svc_codes": None,
        "all_my_t_only": False,
        "imported_car_only": False,
        "ev_specialty_only": True,
        "ev_charge_available_only": False,
        "installable_only": False,
        "chl_sct_cd": None,
        "cal_days": ["20260531"],
        "open_only": True,
        "time_after_hour": 15,
        "sort_by": None,
        "limit": 5,
    }]


def test_search_stores_tool_delegates_ev_filters_to_complex_search(monkeypatch):
    calls: list[dict] = []

    def fake_complex_search(**kwargs):
        calls.append(kwargs)
        return {
            "status": "success",
            "http_status": 200,
            "data": {
                "stores": [{"shop_id": "T00009", "shop_nm": "티스테이션 강남EV점"}],
                "search": {"source": "complex"},
            },
        }

    monkeypatch.setattr(tools.search_stores_complex_tool, "func", fake_complex_search)

    result = tools.search_stores_tool.func(
        place_query="강남역",
        ev_specialty_only=True,
        limit=4,
    )

    assert result["status"] == "success"
    assert result["data"]["stores"][0]["shop_id"] == "T00009"
    assert calls == [{
        "place_query": "강남역",
        "region_code": None,
        "store_nm": None,
        "xpos": None,
        "ypos": None,
        "radius_km": 20.0,
        "svc_codes": None,
        "all_my_t_only": False,
        "imported_car_only": False,
        "ev_specialty_only": True,
        "ev_charge_available_only": False,
        "chl_sct_cd": None,
        "sort_by": None,
        "limit": 4,
    }]


def test_time_filter_tool_uses_complex_search_for_today_plus_two(monkeypatch):
    calls: list[dict] = []

    class FixedDatetime:
        @staticmethod
        def now():
            from datetime import datetime

            return datetime(2026, 5, 28)

    def fake_get_client():
        return "client"

    def fake_search_stores_complex(**kwargs):
        calls.append(kwargs)
        return _Response({
            "stores": [{
                "shop_id": "T00002",
                "shop_nm": "티스테이션 판교점",
                "road_addr_base": "경기 성남시 분당구",
                "tel_no": "031-000-0000",
                "is_all_my_t": True,
                "rating_idx": 4.7,
                "slots": [
                    {"cal_day": "20260528", "tm": "1400"},
                    {"cal_day": "20260529", "tm": "1600"},
                ],
            }]
        })

    monkeypatch.setattr(tools, "datetime", FixedDatetime)
    monkeypatch.setattr(tools, "get_client", fake_get_client)
    monkeypatch.setattr(tools, "search_stores_complex", fake_search_stores_complex)

    result = tools.get_stores_with_time_filter_tool.func(region_code="분당", time_threshold_hour=15)

    assert result["status"] == "success"
    assert calls == [{
        "client": "client",
        "region_code": "분당",
        "cal_days": ["20260528", "20260529", "20260530"],
        "open_only": True,
        "time_after_hour": 15,
        "limit": 50,
    }]
    available = result["data"]["stores_available"]
    assert available == [{
        "shop_id": "T00002",
        "shop_nm": "티스테이션 판교점",
        "address": "경기 성남시 분당구",
        "tel": "031-000-0000",
        "cal_day": "20260529",
        "qualifying_slots": ["1600"],
        "is_all_my_t": True,
        "is_tna_delivery": False,
        "rating_idx": 4.7,
    }]


def test_multi_store_schedule_uses_broader_mode_for_today_shop_without_logistics(monkeypatch):
    calls: list[tuple[list[str], str]] = []

    def fake_fetch_schedule(shop_ids, mode):
        calls.append((shop_ids, mode.value))
        return {
            shop_ids[0]: {
                "shop_nm": "티스테이션 판교점",
                "slots": [
                    {"cal_day": "20260523", "tm": "09"},
                    {"cal_day": "20260524", "tm": "10"},
                ],
            }
        }

    monkeypatch.setattr(tools, "_fetch_schedule_for_shops", fake_fetch_schedule)

    result = tools.get_multi_store_schedule_tool.func(
        shop_id_list=["F00721"],
        today_shop_ids=["F00721"],
        tna_shop_ids=[],
        has_logistics=False,
    )

    assert result["status"] == "success"
    assert result["data"]["tier"] == "in_store_only"
    assert calls == [(["F00721"], "in_store_only")]
    assert [slot["cal_day"] for slot in result["data"]["stores"][0]["slots"]] == ["20260523", "20260524"]


def test_multi_store_schedule_uses_combined_mode_for_today_shop_with_logistics(monkeypatch):
    calls: list[tuple[list[str], str]] = []

    def fake_fetch_schedule(shop_ids, mode):
        calls.append((shop_ids, mode.value))
        return {
            shop_ids[0]: {
                "shop_nm": "티스테이션 판교점",
                "slots": [
                    {"cal_day": "20260523", "tm": "09"},
                    {"cal_day": "20260525", "tm": "10"},
                ],
            }
        }

    monkeypatch.setattr(tools, "_fetch_schedule_for_shops", fake_fetch_schedule)

    result = tools.get_multi_store_schedule_tool.func(
        shop_id_list=["F00721"],
        today_shop_ids=["F00721"],
        tna_shop_ids=["F00721"],
        has_logistics=True,
    )

    assert result["status"] == "success"
    assert result["data"]["tier"] == "in_store_logistics_combined"
    assert calls == [(["F00721"], "in_store_logistics_combined")]
    assert [slot["cal_day"] for slot in result["data"]["stores"][0]["slots"]] == ["20260523", "20260525"]


def test_reservation_sale_schedule_filter_keeps_tna_store_slots_before_rsv_install_date() -> None:
    payload = {
        "logistics": {
            "logistics_qty": 0,
            "rsv_sale_yn": "Y",
            "rsv_install_date": "2026-06-25",
        },
        "inventory": {
            "todayShopArray": [],
            "tnaShopArray": [{"shopId": "F00721"}],
        },
    }
    schedule = {
        "tier": "tna_only",
        "stores": [{
            "shop_id": "F00721",
            "slots": [
                {"cal_day": "20260605", "tm": "17"},
                {"cal_day": "20260625", "tm": "09"},
            ],
        }],
    }

    result = tools._filter_reservation_sale_schedule(schedule, payload)

    assert result == schedule


def test_reservation_sale_schedule_filter_applies_only_when_no_store_or_logistics_inventory() -> None:
    payload = {
        "logistics": {
            "logistics_qty": 0,
            "rsv_sale_yn": "Y",
            "rsv_install_date": "2026-06-25",
        },
        "inventory": {
            "todayShopArray": [],
            "tnaShopArray": [],
        },
    }
    schedule = {
        "tier": "reservation_sale",
        "stores": [{
            "shop_id": "F00721",
            "slots": [
                {"cal_day": "20260605", "tm": "17"},
                {"cal_day": "20260624", "tm": "17"},
                {"cal_day": "20260625", "tm": "09"},
            ],
        }],
    }

    result = tools._filter_reservation_sale_schedule(schedule, payload)

    assert result["tier"] == "reservation_sale"
    assert result["stores"][0]["slots"] == [{"cal_day": "20260625", "tm": "09"}]
