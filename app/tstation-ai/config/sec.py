from common.jwt_utils import decode_jwt
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

    # Return user payload with token for further use
    payload["token"] = token
    return payload
