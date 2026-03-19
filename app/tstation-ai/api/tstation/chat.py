
import asyncio
import logging

from fastapi import APIRouter, HTTPException
from schemas.tstation.chat import TStationChatRequest
from services.tstation.chat import TStationChatService

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/chat")
async def chat(request: TStationChatRequest):
    """
    Function Agent chat for T-station, with and without streaming

    Parameters:

    - User Info:
        - session_id (str): Session ID - Conversation ID
        - user_id (str): UserSeq - UserId

    - Chat Info:

        - messages (list): List history messages
        - stream (bool): default is False

    - When you want tracing:

        - tracing_id (str): Optional, default is uuid.uuid4().hex
        - metadata (dict): Optional, default is {}, is extra metadata when tracing

    """
    try:
        # Set token in thread-local storage before running in thread
        from services.tstation.common.tstation_be_client import set_tstation_be_token
        set_tstation_be_token(request.access_token)

        return await asyncio.to_thread(TStationChatService.chat, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Error while /chat")
        raise HTTPException(status_code=500, detail="Internal server error")
