"""Store AF - 매장 정보 및 예약 조회 테스트"""
import pytest

from app.database import get_db
from main import app
from tests.conftest import make_mock_db

BASE_URL = "/api/shops"

# --------------------------------------------------------------------------- #
#  샘플 데이터                                                                  #
# --------------------------------------------------------------------------- #

SHOP_ROWS = [
    {
        "SHOP_ID": "SHOP001",
        "SHOP_SEQ": 1,
        "SHOP_NM": "강남점",
        "ADDR_BASE": "서울시 강남구 역삼동 123",
        "ROAD_ADDR_BASE": "서울시 강남구 테헤란로 123",
        "SHOP_TEL_NO": "02-1234-5678",
        "SHOP_BIZ_STRT_TIME": "0900",
        "SHOP_BIZ_END_TIME": "2100",
        "SHOP_HLDD": "일요일",
        "SHOP_XPOS": 127.028,
        "SHOP_YPOS": 37.498,
        "DISTANCE": 0.030,
    },
    {
        "SHOP_ID": "SHOP002",
        "SHOP_SEQ": 2,
        "SHOP_NM": "서초점",
        "ADDR_BASE": "서울시 서초구 서초동 456",
        "ROAD_ADDR_BASE": "서울시 서초구 강남대로 456",
        "SHOP_TEL_NO": "02-9876-5432",
        "SHOP_BIZ_STRT_TIME": "1000",
        "SHOP_BIZ_END_TIME": "2000",
        "SHOP_HLDD": None,
        "SHOP_XPOS": 127.032,
        "SHOP_YPOS": 37.491,
        "DISTANCE": 0.085,
    },
]

TIME_ROWS = [
    {"SHOP_ID": "SHOP001", "TM": "0900"},
    {"SHOP_ID": "SHOP001", "TM": "1000"},
    {"SHOP_ID": "SHOP001", "TM": "1100"},
    {"SHOP_ID": "SHOP002", "TM": "1000"},
    {"SHOP_ID": "SHOP002", "TM": "1400"},
]

IMG_ROWS = [
    {"SHOP_ID": "SHOP001", "SHOP_IMG_PATH": "/images/shop001_main.jpg"},
    {"SHOP_ID": "SHOP001", "SHOP_IMG_PATH": "/images/shop001_sub.jpg"},
    {"SHOP_ID": "SHOP002", "SHOP_IMG_PATH": "/images/shop002_main.jpg"},
]


def _override(mock_db):
    async def _dep():
        yield mock_db
    app.dependency_overrides[get_db] = _dep


# --------------------------------------------------------------------------- #
#  테스트 케이스                                                                #
# --------------------------------------------------------------------------- #

async def test_nearby_shops_returns_sorted_by_distance(client):
    """거리 순 정렬된 매장 목록을 반환한다."""
    _override(make_mock_db(SHOP_ROWS, TIME_ROWS, IMG_ROWS))

    resp = await client.get(BASE_URL, params={"user_xpos": 127.025, "user_ypos": 37.495})

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["shops"][0]["shop_id"] == "SHOP001"
    assert data["shops"][1]["shop_id"] == "SHOP002"


async def test_nearby_shops_available_times(client):
    """각 매장에 올바른 예약 시간 슬롯이 매핑된다."""
    _override(make_mock_db(SHOP_ROWS, TIME_ROWS, IMG_ROWS))

    resp = await client.get(BASE_URL, params={"user_xpos": 127.025, "user_ypos": 37.495})

    shops = resp.json()["shops"]
    shop1_times = [t["tm"] for t in shops[0]["available_times"]]
    shop2_times = [t["tm"] for t in shops[1]["available_times"]]

    assert shop1_times == ["0900", "1000", "1100"]
    assert shop2_times == ["1000", "1400"]


async def test_nearby_shops_images(client):
    """각 매장에 올바른 이미지 경로가 매핑된다."""
    _override(make_mock_db(SHOP_ROWS, TIME_ROWS, IMG_ROWS))

    resp = await client.get(BASE_URL, params={"user_xpos": 127.025, "user_ypos": 37.495})

    shops = resp.json()["shops"]
    assert shops[0]["images"] == [
        "/images/shop001_main.jpg",
        "/images/shop001_sub.jpg",
    ]
    assert shops[1]["images"] == ["/images/shop002_main.jpg"]


async def test_nearby_shops_no_results(client):
    """DB에 결과가 없으면 total=0, shops=[] 를 반환한다."""
    _override(make_mock_db([]))  # shop 조회 결과 없음

    resp = await client.get(BASE_URL, params={"user_xpos": 0.0, "user_ypos": 0.0})

    assert resp.status_code == 200
    assert resp.json() == pytest.approx({"total": 0, "cal_day": resp.json()["cal_day"], "shops": []})


async def test_nearby_shops_cal_day_passed(client):
    """cal_day 파라미터가 응답에 그대로 반영된다."""
    _override(make_mock_db(SHOP_ROWS, TIME_ROWS, IMG_ROWS))

    resp = await client.get(
        BASE_URL,
        params={"user_xpos": 127.025, "user_ypos": 37.495, "cal_day": "20260301"},
    )

    assert resp.json()["cal_day"] == "20260301"


async def test_nearby_shops_cal_day_invalid_format(client):
    """cal_day가 YYYYMMDD 형식이 아니면 422를 반환한다."""
    # FastAPI가 의존성을 파라미터 검증 전에 resolve할 수 있으므로 dummy override 설정
    _override(make_mock_db([]))

    resp = await client.get(
        BASE_URL,
        params={"user_xpos": 127.025, "user_ypos": 37.495, "cal_day": "2026-03-01"},
    )

    assert resp.status_code == 422


async def test_nearby_shops_missing_required_params(client):
    """필수 파라미터(user_xpos, user_ypos) 누락 시 422를 반환한다."""
    _override(make_mock_db([]))

    resp = await client.get(BASE_URL)
    assert resp.status_code == 422