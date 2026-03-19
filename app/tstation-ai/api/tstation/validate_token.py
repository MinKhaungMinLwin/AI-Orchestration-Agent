import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from common.tstation_be_api_client.hkt_api_client.api.faq_af_일반_문의.get_faq_api_faq_get import sync as get_faq
from common.tstation_be_api_client.hkt_api_client.models import FaqListResponse
from services.tstation.common.tstation_be_client import set_tstation_be_token, get_tstation_be_client

logger = logging.getLogger(__name__)
router = APIRouter()


class ValidateTokenRequest(BaseModel):
    access_token: str


@router.post("/validate-token")
def validate_token(request: ValidateTokenRequest):
    """
    Validate access token by calling FAQ API with limit=1
    """
    try:
        set_tstation_be_token(request.access_token)

        result = get_faq(
            client=get_tstation_be_client(),
            limit=1,
        )

        if result:
            return {"status": "success", "valid": True}
        return {"status": "success", "valid": False}

    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        return {"status": "error", "valid": False, "reason": str(e)}
