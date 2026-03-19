import logging
from typing import Optional
import jwt

logger = logging.getLogger(__name__)


def decode_jwt(token: str, secret: Optional[str] = None) -> Optional[dict]:
    """
    Decode JWT token and extract payload.
    If secret is None, decoding is done without verification (for reading payload only).
    """
    if not token:
        return None

    try:
        if secret:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
        else:
            # Decode without verification - useful for extracting claims
            payload = jwt.decode(token, options={"verify_signature": False})
        logger.debug(f"JWT decoded successfully, payload keys: {payload.keys()}")
        return payload
    except jwt.InvalidTokenError as e:
        logger.warning(f"Failed to decode JWT: {e}")
        return None
    except Exception as e:
        logger.exception(f"Error decoding JWT: {e}")
        return None


def get_user_info_from_token(token: str, secret: Optional[str] = None) -> Optional[dict]:
    """
    Extract user info from JWT token.

    JWT fields:
    - user_id: Member number
    - user_type: Member type (10: member, 20: non-member)
    - car_no: Vehicle number (only if exists)
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
    user_info = {
        "user_id": payload.get("user_id"),
        "user_type": user_type_display,
        "car_no": payload.get("car_no"),
        "affiliate_yn": payload.get("affiliate_yn"),
        "entr_no": payload.get("entr_no"),
        "issued_at": payload.get("issued_at"),
        "expire_at": payload.get("expire_at"),
    }

    # Filter out None values
    return {k: v for k, v in user_info.items() if v is not None}