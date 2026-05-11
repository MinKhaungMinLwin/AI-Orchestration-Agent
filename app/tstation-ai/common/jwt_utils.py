import logging
from typing import Optional

import jwt

from config.env import settings

logger = logging.getLogger(__name__)


def decode_jwt(token: str, secret: Optional[str] = None) -> Optional[dict]:
    """Verify JWT token and extract payload."""
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            secret or settings.API_SECRET_KEY,
            algorithms=["HS256"],
            options={"require": ["exp"]},
        )
        logger.debug(f"JWT verified successfully, payload keys: {payload.keys()}")
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Failed to verify JWT: {e}")
        return None


def decode_jwt_unverified(token: str) -> Optional[dict]:
    """Decode JWT payload without verification. Do not use for authentication."""
    if not token:
        return None

    try:
        return jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError as e:
        logger.warning(f"Failed to decode JWT payload: {e}")
        return None


def get_user_info_from_token(token: str, secret: Optional[str] = None) -> Optional[dict]:
    """
    Extract user info from JWT token.

    JWT fields:
    - user_id: Member number
    - user_type: Member type (10: member, 20: non-member)
    - mbr_nm: Member name (only if exists)
    - affiliate_yn: Affiliate status (Y, N)
    - entr_no: Affiliate company number (only if affiliated)
    - issued_at: Token issued time
    - expire_at: Token expiration time
    """
    payload = decode_jwt(token, secret)
    if not payload:
        return None

    # Map user_type to readable format
    user_type = payload.get("user_type")
    user_type_display = "member" if user_type == "10" else "non-member" if user_type == "20" else user_type

    # Extract user info fields
    # car_no excluded — vehicle info should come from get_my_cars_tool
    # to avoid auto-selecting one car when multiple are registered
    user_info = {
        "user_id": payload.get("user_id"),
        "user_type": user_type_display,
        "mbr_nm": payload.get("mbr_nm"),
        "affiliate_yn": payload.get("affiliate_yn"),
        "entr_no": payload.get("entr_no"),
        "issued_at": payload.get("issued_at"),
        "expire_at": payload.get("expire_at"),
    }

    # Filter out None values
    return {k: v for k, v in user_info.items() if v is not None}