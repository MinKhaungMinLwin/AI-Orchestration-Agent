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
    current_pending_intent,
)


# --------------------------------------------------------------------------- #
#  Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_pending_intent():
    """Each test sets pending_intent fresh; reset to avoid bleed across tests."""
    token = current_pending_intent.set(None)
    yield
    current_pending_intent.reset(token)


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
