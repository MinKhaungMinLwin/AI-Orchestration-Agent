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
