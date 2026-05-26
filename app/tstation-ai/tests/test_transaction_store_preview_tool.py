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
