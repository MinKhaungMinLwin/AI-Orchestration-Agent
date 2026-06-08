from common.jwt_utils import TOKEN_EXPIRED_CODE, TOKEN_EXPIRED_MESSAGE, decode_jwt, is_jwt_payload_expired
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)


def get_api_key(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """Validate JWT token and return user info + token."""
    if not credentials:
        raise HTTPException(status_code=403, detail="Forbidden")

    token = credentials.credentials

    # Decode JWT token
    payload = decode_jwt(token)
    if not payload or not payload.get("user_id"):
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        expired = is_jwt_payload_expired(payload)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token expiration")
    if expired:
        raise HTTPException(
            status_code=401,
            detail={"code": TOKEN_EXPIRED_CODE, "message": TOKEN_EXPIRED_MESSAGE},
        )

    # Return user payload with token for further use
    payload["token"] = token
    return payload
