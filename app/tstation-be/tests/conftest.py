"""공통 테스트 픽스처

DB 없이 FastAPI dependency override로 Oracle 세션을 mock합니다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from main import app


def make_db_result(rows: list) -> MagicMock:
    """db.execute() 반환값을 흉내내는 mock 객체를 생성합니다.

    사용 예::

        result = make_db_result([{"COL": "val"}])
        result.mappings().all()   # → [{"COL": "val"}]
        result.mappings().first() # → {"COL": "val"}
    """
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    result.mappings.return_value.first.return_value = rows[0] if rows else None
    return result


def make_mock_db(*rows_per_call: list) -> AsyncMock:
    """execute() 호출 순서마다 다른 row 목록을 반환하는 mock DB 세션을 생성합니다.

    Args:
        *rows_per_call: 각 execute() 호출에 대응하는 row 목록

    사용 예::

        mock_db = make_mock_db(
            [{"SHOP_ID": "S1", ...}],   # 1번째 execute()
            [{"TM": "0900"}, ...],       # 2번째 execute()
            [],                          # 3번째 execute()
        )
    """
    mock = AsyncMock()
    mock.execute = AsyncMock(
        side_effect=[make_db_result(rows) for rows in rows_per_call]
    )
    return mock


@pytest.fixture
async def client():
    """테스트용 비동기 HTTP 클라이언트"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    """각 테스트 후 dependency override를 자동으로 초기화합니다."""
    yield
    app.dependency_overrides.clear()