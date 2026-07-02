import asyncio

import pytest
import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api.tstation.chat_message import validate_token_endpoint
from config.sec import get_api_key


def _jwt(payload: dict) -> str:
    return jwt.encode(payload, "test-secret", algorithm="HS256")


def _credentials(payload: dict) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=_jwt(payload))


def test_get_api_key_rejects_expired_expire_at_token() -> None:
    credentials = _credentials({
        "user_id": "M200012931",
        "user_type": "10",
        "affiliate_yn": "N",
        "issued_at": "2000-01-01T00:00:00.000Z",
        "expire_at": "2000-01-01T00:00:01.000Z",
    })

    with pytest.raises(HTTPException) as exc:
        get_api_key(credentials)

    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "TOKEN_EXPIRED"


def test_validate_token_returns_token_expired_reason() -> None:
    credentials = _credentials({
        "user_id": "M200012931",
        "user_type": "10",
        "affiliate_yn": "N",
        "issued_at": "2000-01-01T00:00:00.000Z",
        "expire_at": "2000-01-01T00:00:01.000Z",
    })

    response = asyncio.run(validate_token_endpoint(credentials))

    assert response.valid is False
    assert response.user_id == "M200012931"
    assert response.reason == "TOKEN_EXPIRED"


def test_get_api_key_accepts_future_expire_at_token() -> None:
    credentials = _credentials({
        "user_id": "M200012931",
        "user_type": "10",
        "affiliate_yn": "N",
        "issued_at": "2026-01-01T00:00:00.000Z",
        "expire_at": "2999-01-01T00:00:00.000Z",
    })

    payload = get_api_key(credentials)

    assert payload["user_id"] == "M200012931"
    assert payload["token"] == credentials.credentials
