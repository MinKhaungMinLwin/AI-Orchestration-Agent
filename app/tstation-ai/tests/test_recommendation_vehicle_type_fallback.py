"""Zero-result relax fallback for the vehicle_type recommendation filter (Step 4).

Exercises get_products_recommendations_tool through its underlying .func with the
BE client mocked, so the fallback ordering (winter first → vehicle_type relax) and
the price-filter guard are verified without a live backend.
"""

import services.tstation.agents.b_discovery_agent.tools as t

VehicleType = t.VehicleType


class _Resp:
    def __init__(self, items, status=200):
        self.parsed = {"items": list(items)}
        self.status_code = status
        self.content = b""


class _FakeBE:
    """Return canned responses in order and record each call's kwargs."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def _patch(monkeypatch, responses):
    be = _FakeBE(responses)
    monkeypatch.setattr(t, "get_products_recommendations", be)
    monkeypatch.setattr(t, "get_client", lambda: None)
    monkeypatch.setattr(t, "detect_car_no_mismatch", lambda: None)
    monkeypatch.setattr(t, "_enrich_items_with_descriptions", lambda items: items)
    monkeypatch.setattr(t, "_enrich_items_with_price_fields", lambda items: items)
    monkeypatch.setattr(t, "_sort_items", lambda items, sort_by: items)
    return be


def _call(**kwargs):
    kwargs.setdefault("ignore_policy_patch", True)
    return t.get_products_recommendations_tool.func(**kwargs)


ITEM = {"goods_no": "G1", "goods_nm": "Ventus", "tire_size_1": "235/60R18"}


def test_empty_vehicle_type_result_relaxes_filter(monkeypatch):
    be = _patch(monkeypatch, [_Resp([]), _Resp([ITEM])])

    result = _call(rcmd_type="tstation", vehicle_type="suv")

    assert result["status"] == "success"
    assert result["data"]["items"] == [ITEM]
    fb = result["data"]["recommendation_fallback"]
    assert fb["requested_vehicle_type"] == "suv"
    assert fb["applied_vehicle_type"] is None
    assert "차량 타입" in fb["assistant_response_hint"]
    # exactly two BE calls: filtered (SUV) then relaxed (None)
    assert len(be.calls) == 2
    assert be.calls[0]["vehicle_type"] == VehicleType.SUV
    assert be.calls[1]["vehicle_type"] is None


def test_relax_retry_also_empty_returns_original_without_loop(monkeypatch):
    be = _patch(monkeypatch, [_Resp([]), _Resp([])])

    result = _call(rcmd_type="tstation", vehicle_type="suv")

    assert result["status"] == "success"
    assert result["data"]["items"] == []
    assert "recommendation_fallback" not in result["data"]
    assert len(be.calls) == 2  # one relax retry only, no loop


def test_non_empty_vehicle_type_result_does_not_retry(monkeypatch):
    be = _patch(monkeypatch, [_Resp([ITEM])])

    result = _call(rcmd_type="tstation", vehicle_type="suv")

    assert result["status"] == "success"
    assert result["data"]["items"] == [ITEM]
    assert "recommendation_fallback" not in result["data"]
    assert len(be.calls) == 1


def test_price_filter_empty_does_not_relax_vehicle_type(monkeypatch):
    be = _patch(monkeypatch, [_Resp([])])

    result = _call(rcmd_type="value", vehicle_type="suv", min_price=200_000, max_price=300_000)

    # price-empty keeps its own no_results messaging; must not be masked by relax
    assert result["status"] == "no_results"
    assert result["reason"] == "no_products_in_price_range"
    assert len(be.calls) == 1
    assert be.calls[0]["vehicle_type"] == VehicleType.SUV


def test_winter_fallback_keeps_vehicle_type_filter(monkeypatch):
    be = _patch(monkeypatch, [_Resp([]), _Resp([ITEM])])

    result = _call(rcmd_type="snow", season_nm="겨울", vehicle_type="suv")

    assert result["status"] == "success"
    assert result["data"]["items"] == [ITEM]
    # winter fallback annotation, not the vehicle_type relax one
    fb = result["data"]["recommendation_fallback"]
    assert "applied_rcmd_type" in fb
    assert "applied_vehicle_type" not in fb
    # both the original and the winter-fallback call keep the SUV filter
    assert len(be.calls) == 2
    assert be.calls[0]["vehicle_type"] == VehicleType.SUV
    assert be.calls[1]["vehicle_type"] == VehicleType.SUV


def test_invalid_vehicle_type_returns_422(monkeypatch):
    be = _patch(monkeypatch, [_Resp([ITEM])])

    result = _call(rcmd_type="tstation", vehicle_type="spaceship")

    assert result["status"] == "error"
    assert result["http_status"] == 422
    assert result["reason"] == "INVALID_VEHICLE_TYPE"
    assert len(be.calls) == 0  # rejected before any BE call


def test_three_pmsf_description_is_added_for_certified_product():
    result = t._append_three_pmsf_description({
        "goods_nm": "웨더플렉스 GT",
        "three_pmsf_yn": "Y",
        "pc_prod_remark_desc": "프리미엄 올웨더 타이어입니다.",
    })

    assert "3PMSF 인증" in result["pc_prod_remark_desc"]
    assert result["three_pmsf_description"].startswith("3PMSF 인증")


def test_three_pmsf_description_is_not_duplicated():
    result = t._append_three_pmsf_description({
        "goods_nm": "웨더플렉스 GT",
        "three_pmsf_yn": "Y",
        "pc_prod_remark_desc": "3PMSF 인증으로 눈길 성능 기준을 충족합니다.",
    })

    assert result["pc_prod_remark_desc"].count("3PMSF") == 1
    assert result["three_pmsf_description"].startswith("3PMSF 인증")


def test_search_product_budget_passes_max_price_to_be_and_ignores_min_price(monkeypatch):
    be = _FakeBE([_Resp([{"goods_no": "G1", "goods_nm": "Budget tire", "extra_fvr_sale_prc": 299_000}])])
    monkeypatch.setattr(t, "search_product", be)
    monkeypatch.setattr(t, "get_client", lambda: None)
    monkeypatch.setattr(t, "_enrich_items_with_descriptions", lambda items: items)

    result = t.search_product_tool.func(
        keyword=None,
        limit=5,
        min_price=200_000,
        max_price=299_999,
        sort_by="price_asc",
    )

    assert result["status"] == "success"
    assert be.calls[0]["limit"] == 5
    assert be.calls[0]["min_price"] is None
    assert be.calls[0]["max_price"] == 299_999
    assert be.calls[0]["sort_by"] == "price_desc"
