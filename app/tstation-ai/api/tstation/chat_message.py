"""
Chat Message API - CRUD operations for conversations via Redis.

Endpoints:
- POST /api/messages/chat - Chat with content only (history managed by service)
- GET /api/messages/sessions - List all sessions for user
- GET /api/messages/history/{session_id} - Get messages for a session
- DELETE /api/messages/{session_id} - Delete a session
- GET /api/messages/user-info - Get user info from JWT
- POST /api/messages/validate-token - Validate JWT token
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.responses import StreamingResponse

from config.sec import get_api_key
from schemas.tstation.chat_message import (
    ChatMessageRequest,
    ChatMessageResponse,
    ChatStreamResponse,
    SessionListResponse,
    SessionInfo,
    ChatHistoryResponse,
    MessageResponse,
    UserInfoResponse,
    ValidateTokenResponse,
    DeleteSessionResponse,
    AppendMessageRequest,
    AppendMessageResponse,
)
from services.tstation.chat_history_service import get_chat_history_service
from services.tstation.chat import TStationChatServiceV2

logger = logging.getLogger(__name__)
router = APIRouter()


def get_current_time() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@router.post("/chat", dependencies=[Depends(get_api_key)])
async def chat(request: ChatMessageRequest, user: dict = Security(get_api_key)):
    """
    Chat endpoint - only content, history managed by service via Redis.

    Parameters:

    - Header:
        - Authorization (str): Bearer JWT token for authentication

    - Request:
        - session_id (str): Session ID (required)
        - content (str): Message content
        - stream (bool): default is False

    - Response:
        - session_id (str): Session ID
        - message_id (str): User message ID
        - role (str): "user"
        - content (str): Echo of user message
        - created_at (str): Timestamp
    """
    # user is already the decoded JWT payload
    user_id = user.get("user_id")

    service = get_chat_history_service()

    # Get or create session
    session_id = service.get_or_create_session_id(request.session_id, user_id)

    # Save user message
    msg_id = service.save_message(session_id, "user", request.content)

    # Build messages list from history (compressed when a rolling summary exists)
    history = service.get_history_for_llm(session_id)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]

    # Add current user message only if not duplicate of last history
    if not (messages and messages[-1].get("role") == "user" and messages[-1].get("content") == request.content):
        messages.append({"role": "user", "content": request.content})

    # Prepare request for chat service
    from schemas.tstation.chat import TStationChatRequest
    from schemas.tstation.chat import TStationChatResponse

    chat_request = TStationChatRequest(
        messages=messages,
        stream=request.stream,
        user_id=user_id,
        session_id=session_id,
        access_token=user["token"],
        user_info=request.user_info,
        chip_context=request.chip_context.model_dump() if request.chip_context else None,
        **({"tracing_id": request.tracing_id} if request.tracing_id else {}),
    )

    # Call chat service
    if request.stream:
        # For stream mode, we need to save assistant message as it comes
        # The streaming response will be handled by chat_2 service
        return StreamingResponse(
            stream_chat_response(chat_request, session_id, msg_id, service),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-stream mode
    response = TStationChatServiceV2.chat(chat_request)

    if isinstance(response, TStationChatResponse):
        # Save assistant response to history
        service.save_message(session_id, "assistant", response.content)

        return ChatMessageResponse(
            session_id=session_id,
            message_id=msg_id,
            role="user",
            content=request.content,
            created_at=get_current_time(),
        )

    raise HTTPException(status_code=500, detail="Unexpected response type")


async def stream_chat_response(chat_request, session_id: str, user_msg_id: str, service):
    """Stream chat response and save assistant messages as they arrive."""
    from services.tstation.chat import TStationChatServiceV2

    full_assistant_content = ""
    assistant_response_ui = None  # Priority: assistantResponse from UI Template Agent
    template_data = None  # Captured from UI Template Agent data events

    # Stream from chat service
    stream_response = TStationChatServiceV2.chat(chat_request)

    # Send initial response with session_id
    initial_response = {
        "session_id": session_id,
        "message_id": user_msg_id,
        "role": "user",
        "content": chat_request.messages[-1]["content"],
        "created_at": get_current_time(),
        "stream_started": True,
    }
    yield f"data: {json.dumps(initial_response, ensure_ascii=False)}\n\n"

    async for chunk in stream_response.body_iterator:
        # Parse the SSE data
        if chunk.strip().startswith("data: "):
            data_str = chunk.strip()[6:]  # Remove "data: " prefix
            if data_str == "[DONE]":
                break

            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            # Priority: Capture assistantResponse from UI Template Agent (JSON data event)
            if event.get("type") == "data":
                event_data = event.get("data", {})
                # assistantResponse may be inside data object or at top level
                if event.get("assistantResponse"):
                    assistant_response_ui = event["assistantResponse"]
                elif event_data.get("assistantResponse"):
                    assistant_response_ui = event_data["assistantResponse"]
                if assistant_response_ui:
                    logger.info(f"[CHAT_MESSAGE] Captured assistantResponse from UI Template: {assistant_response_ui[:50]}...")
                # template_data = full event (KISS)
                template_data = event
                logger.info(f"[CHAT_MESSAGE] Captured template_data: type={template_data.get('type')}, template={template_data.get('template')}")

            # QC parallel mode: override assistantResponse with the verified correction
            if event.get("type") == "qc_correction" and event.get("assistantResponse"):
                assistant_response_ui = event["assistantResponse"]
                logger.info(f"[CHAT_MESSAGE] QC correction applied: {assistant_response_ui[:50]}...")

            # When we receive a message event with assistant content, accumulate it
            if event.get("type") == "message" and event.get("content"):
                content = event.get("content", "")
                if content:
                    full_assistant_content += content

            yield chunk

    # Save assistant message after stream completes
    # Priority: Use assistantResponse from UI Template Agent if available
    message_to_save = assistant_response_ui if assistant_response_ui else full_assistant_content
    if message_to_save:
        service.save_message(session_id, "assistant", message_to_save, template_data=template_data)
        logger.info(f"[CHAT_MESSAGE] Saved assistant message" +
                  (f" with template_data" if template_data else "") + f": {message_to_save[:50]}...")

        # Fire-and-forget: compress old turns into a rolling summary every 4 turns.
        from services.tstation.history_summarizer import maybe_summarize
        asyncio.create_task(maybe_summarize(session_id))

    yield "data: [DONE]\n\n"


@router.get("/sessions", dependencies=[Depends(get_api_key)], response_model=SessionListResponse)
async def list_sessions(user: dict = Security(get_api_key)):
    """
    List all sessions for the current user.

    Parameters:

    - Header:
        - Authorization (str): Bearer JWT token for authentication

    - Response:
        - sessions (list): List of SessionInfo
        - total (int): Total number of sessions
    """
    user_id = user.get("user_id")

    service = get_chat_history_service()
    sessions = service.list_sessions(user_id)

    return SessionListResponse(
        sessions=[SessionInfo(**s) for s in sessions],
        total=len(sessions),
    )


@router.get("/history/{session_id}", dependencies=[Depends(get_api_key)], response_model=ChatHistoryResponse)
async def get_history(
    session_id: str,
    user: dict = Security(get_api_key),
):
    """
    Get chat history for a session.

    Parameters:

    - Path:
        - session_id (str): Session ID

    - Header:
        - Authorization (str): Bearer JWT token for authentication

    - Response:
        - session_id (str): Session ID
        - total (int): Total number of messages
        - messages (list): List of MessageResponse
    """
    user_id = user.get("user_id")

    service = get_chat_history_service()

    # Try to get history - will return empty if session doesn't exist yet
    try:
        messages = service.get_history(session_id)
    except Exception:
        messages = []

    return ChatHistoryResponse(
        session_id=session_id,
        total=len(messages),
        messages=[MessageResponse(**msg) for msg in messages],
    )


@router.post("/append", dependencies=[Depends(get_api_key)], response_model=AppendMessageResponse)
async def append_message(
    request: AppendMessageRequest,
    user: dict = Security(get_api_key),
):
    """
    Append a message to chat history (without AI processing).

    Parameters:

    - Header:
        - Authorization (str): Bearer JWT token for authentication

    - Request:
        - session_id (str): Session ID
        - content (str): Message content
        - role (str): "user" or "assistant" (default "user")
        - template_data (dict): Optional template data for assistant messages

    - Response:
        - success (bool): Append success flag
        - session_id (str): Session ID
        - msg_id (str): Created message ID
        - role (str): Message role
        - created_at (str): Created timestamp
    """
    user_id = user.get("user_id")

    service = get_chat_history_service()

    # Verify session exists for this user
    if not service.session_exists(request.session_id, user_id):
        raise HTTPException(status_code=404, detail="Session not found")

    # Validate role
    if request.role not in ("user", "assistant"):
        raise HTTPException(status_code=400, detail="Role must be 'user' or 'assistant'")

    # Append message (saved at end due to timestamp score)
    msg_id = service.save_message(
        session_id=request.session_id,
        role=request.role,
        content=request.content,
        template_data=request.template_data,
    )

    return AppendMessageResponse(
        success=True,
        session_id=request.session_id,
        msg_id=msg_id,
        role=request.role,
        created_at=get_current_time(),
    )


@router.delete("/{session_id}", dependencies=[Depends(get_api_key)], response_model=DeleteSessionResponse)
async def delete_session(
    session_id: str,
    user: dict = Security(get_api_key),
):
    """
    Delete a session and all its messages.

    Parameters:

    - Path:
        - session_id (str): Session ID to delete

    - Header:
        - Authorization (str): Bearer JWT token for authentication

    - Response:
        - success (bool): True if deleted
        - session_id (str): Deleted session ID
        - messages_deleted (int): Number of messages deleted
    """
    user_id = user.get("user_id")

    service = get_chat_history_service()

    # Verify session belongs to user
    if not service.session_exists(session_id, user_id):
        raise HTTPException(status_code=404, detail="Session not found")

    messages_deleted = service.delete_session(session_id)

    return DeleteSessionResponse(
        success=True,
        session_id=session_id,
        messages_deleted=messages_deleted,
    )

    return DeleteSessionResponse(
        success=True,
        session_id=session_id,
        messages_deleted=messages_deleted,
    )


@router.get("/user-info", dependencies=[Depends(get_api_key)], response_model=UserInfoResponse)
async def get_user_info(user: dict = Security(get_api_key)):
    """
    Get user info from JWT token.

    Parameters:

    - Header:
        - Authorization (str): Bearer JWT token for authentication

    - Response:
        - user_id (str): User ID
        - user_type (str): User type
        - affiliate_yn (str): Affiliate flag
        - issued_at (str): Token issued timestamp
        - expire_at (str): Token expiration timestamp
    """
    # credentials is already the decoded user payload
    # Exclude token from user dict before returning
    user_data = {k: v for k, v in user.items() if k != "token"}
    return UserInfoResponse(**user_data)


@router.post("/validate-token", dependencies=[Depends(get_api_key)], response_model=ValidateTokenResponse)
async def validate_token_endpoint(user: dict = Security(get_api_key)):
    """
    Validate JWT token.

    Parameters:

    - Header:
        - Authorization (str): Bearer JWT token to validate

    - Response:
        - valid (bool): True if token is valid
        - user_id (str): User ID if valid
        - reason (str): Reason if invalid
    """
    # user is already the decoded JWT payload
    user_id = user.get("user_id")
    if user_id:
        return ValidateTokenResponse(valid=True, user_id=user_id)
    else:
        return ValidateTokenResponse(valid=False, reason="Invalid token")
