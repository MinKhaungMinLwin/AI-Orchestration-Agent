import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    """Chat request - auth via Bearer token in header."""
    content: str = Field(..., description="User message content")
    session_id: str = Field(..., description="Session ID (required)")
    stream: bool = Field(default=False, description="Stream mode")
    user_info: Optional[dict] = Field(default=None, description="Additional user info from UI (overrides JWT fields)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "content": "타이어 추천해주세요",
                "session_id": "test_session_id_12345",
                "stream": False,
                "user_info": {"tire_size": "225/45R17"}
            }
        }
    }


class ChatMessageResponse(BaseModel):
    """Response after chat completion (non-stream)."""
    session_id: str = Field(..., description="Session ID")
    message_id: str = Field(..., description="User message ID")
    role: str = Field(default="user", description="Message role")
    content: str = Field(..., description="User message content")
    created_at: str = Field(..., description="Created timestamp")


class ChatStreamResponse(BaseModel):
    """Response for stream mode - returns session_id and user message info."""
    session_id: str = Field(..., description="Session ID")
    message_id: str = Field(..., description="User message ID")
    role: str = Field(default="user", description="Message role")
    content: str = Field(..., description="User message content")
    created_at: str = Field(..., description="Created timestamp")
    stream_started: bool = Field(default=True, description="Stream started flag")


class SessionInfo(BaseModel):
    """Session info for list response."""
    session_id: str = Field(..., description="Session ID")
    last_message: Optional[str] = Field(default=None, description="Last message preview")
    updated_at: Optional[str] = Field(default=None, description="Last update timestamp")


class SessionListResponse(BaseModel):
    """Response for GET /api/messages/sessions."""
    sessions: List[SessionInfo] = Field(default_factory=list, description="List of sessions")
    total: int = Field(default=0, description="Total number of sessions")


class MessageResponse(BaseModel):
    """Single message in history."""
    msg_id: str = Field(..., description="Message ID")
    session_id: str = Field(..., description="Session ID")
    role: str = Field(..., description="Role (user/assistant)")
    content: str = Field(..., description="Message content")
    status: str = Field(default="completed", description="Message status")
    created_at: str = Field(..., description="Created timestamp")


class ChatHistoryResponse(BaseModel):
    """Response for GET /api/messages/history/{session_id}."""
    session_id: str = Field(..., description="Session ID")
    total: int = Field(default=0, description="Total messages")
    messages: List[MessageResponse] = Field(default_factory=list, description="List of messages")


class UserInfoResponse(BaseModel):
    """User info extracted from JWT token."""
    user_id: str = Field(..., description="User ID")
    user_type: Optional[str] = Field(default=None, description="User type (member/non-member)")
    mbr_nm: Optional[str] = Field(default=None, description="Member name")
    affiliate_yn: Optional[str] = Field(default=None, description="Affiliate status (Y/N)")
    issued_at: Optional[str] = Field(default=None, description="Token issued time")
    expire_at: Optional[str] = Field(default=None, description="Token expiration time")


class ValidateTokenResponse(BaseModel):
    """Response for POST /api/messages/validate-token."""
    valid: bool = Field(..., description="Token is valid or not")
    user_id: Optional[str] = Field(default=None, description="User ID if valid")
    reason: Optional[str] = Field(default=None, description="Error reason if invalid")


class DeleteSessionResponse(BaseModel):
    """Response for DELETE /api/messages/{session_id}."""
    success: bool = Field(..., description="Delete success flag")
    session_id: str = Field(..., description="Deleted session ID")
    messages_deleted: int = Field(default=0, description="Number of messages deleted")
