"""Price AF - 가격 및 할인 조회 테스트"""
from app.database import get_db
from main import app
from tests.conftest import make_mock_db

BASE_URL = "/api/prices"

# --------------------------------------------------------------------------- #
#  샘플 데이터                                                                  #
# --------------------------------------------------------------------------- #

PRICE_ROW = {
    "SALE_PRC": 150000,
    "EXTRA_FVR_SALE_PRC": 120000,
    "EXTRA_FVR_SALE_PER": 20.0,
    "WAGE_PRC": 30000,
    "WAGE_TODAY_PRC": 25000,
}

PRICE_ROW_PARTIAL = {
    "SALE_PRC": 80000,
    "EXTRA_FVR_SALE_PRC": None,   # 혜택가 없음
    "EXTRA_FVR_SALE_PER": None,
    "WAGE_PRC": 15000,
    "WAGE_TODAY_PRC": None,       # 오늘의 공임비 없음
}


def _override(mock_db):
    async def _dep():
        yield mock_db
    app.dependency_overrides[get_db] = _dep


# --------------------------------------------------------------------------- #
#  테스트 케이스                                                                #
# --------------------------------------------------------------------------- #

async def test_get_price_full_data(client):
    """모든 가격 필드가 있는 상품을 정상 반환한다."""
    _override(make_mock_db([PRICE_ROW]))

    resp = await client.get(f"{BASE_URL}/GOODS001")

    assert resp.status_code == 200
    data = resp.json()
    assert data["goods_id"] == "GOODS001"
    assert data["sale_prc"] == 150000
    assert data["extra_fvr_sale_prc"] == 120000
    assert data["extra_fvr_sale_per"] == 20.0
    assert data["wage_prc"] == 30000
    assert data["wage_today_prc"] == 25000


async def test_get_price_partial_data(client):
    """일부 필드가 null인 상품도 정상 반환한다."""
    _override(make_mock_db([PRICE_ROW_PARTIAL]))

    resp = await client.get(f"{BASE_URL}/GOODS002")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sale_prc"] == 80000
    assert data["extra_fvr_sale_prc"] is None
    assert data["extra_fvr_sale_per"] is None
    assert data["wage_today_prc"] is None


async def test_get_price_not_found(client):
    """존재하지 않는 상품 ID는 404를 반환한다."""
    _override(make_mock_db([]))  # DB 결과 없음

    resp = await client.get(f"{BASE_URL}/UNKNOWN")

    assert resp.status_code == 404
    assert "UNKNOWN" in resp.json()["detail"]


async def test_get_price_goods_id_in_response(client):
    """응답에 요청한 goods_id가 그대로 포함된다."""
    _override(make_mock_db([PRICE_ROW]))

    resp = await client.get(f"{BASE_URL}/GOODS-XYZ-999")

    assert resp.json()["goods_id"] == "GOODS-XYZ-999"