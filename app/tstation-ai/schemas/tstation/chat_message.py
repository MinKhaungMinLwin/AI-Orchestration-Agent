from typing import List, Optional

from pydantic import BaseModel, Field


class ChipContext(BaseModel):
    """Routing metadata attached by the FE when the user taps a quick reply chip."""

    domain: Optional[str] = Field(
        default=None,
        description="Target domain declared by the chip emitter. One of: DISCOVERY, TRANSACTION, SUPPORT, LEADING.",
    )
    actionId: Optional[str] = Field(default=None, description="Executable quick reply action identifier.")
    action_id: Optional[str] = Field(default=None, description="Executable quick reply action identifier.")
    intentKey: Optional[str] = Field(default=None, description="Conversation intent key declared by the chip emitter.")
    intent_key: Optional[str] = Field(default=None, description="Conversation intent key declared by the chip emitter.")
    cta_id: Optional[str] = Field(default=None, description="Shared CTA registry identifier emitted with the chip.")
    cta_action: Optional[str] = Field(default=None, description="Shared CTA registry action emitted with the chip.")
    expected_behavior: Optional[str] = Field(default=None, description="open_url, conversation_action, or dynamic_choice.")
    source_intent: Optional[str] = Field(default=None, description="Intent that emitted this CTA.")
    expected_contract_intent: Optional[str] = Field(default=None, description="Next-turn contract intent expected by the CTA.")
    ui_action: Optional[dict] = Field(default=None, description="Normalized UI action envelope.")
    slots: Optional[dict] = Field(default=None, description="Current-turn slot patch carried by the UI action.")
    metadata: Optional[dict] = Field(default=None, description="Action-specific metadata emitted with the chip.")

    model_config = {"extra": "allow"}


class ChatMessageRequest(BaseModel):
    """Chat request - auth via Bearer token in header."""
    content: str = Field(..., max_length=3000, description="User message content")
    session_id: str = Field(..., description="Session ID (required)")
    stream: bool = Field(default=False, description="Stream mode")
    user_info: Optional[dict] = Field(default=None, description="Additional user info from UI (overrides JWT fields)")
    tracing_id: Optional[str] = Field(default=None, description="Tracing ID for Langfuse (eval use)")
    chip_context: Optional[ChipContext] = Field(
        default=None,
        description="Set by FE when the user taps a quick reply chip. Allows backend to skip LLM classifier.",
    )
    ui_action: Optional[dict] = Field(default=None, description="Normalized UI action payload sent by the FE.")
    slots: Optional[dict] = Field(default=None, description="Current-turn slot patch sent by the FE.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "content": "타이어 추천해주세요",
                "session_id": "test_session_id_12345",
                "stream": False,
                "user_info": {
                    "tire_size": "225/45R17",
                    "location": {
                        "xpos": None,
                        "ypos": None
                    }
                }
            }
        }
    }


class QuickOrderActionPayload(BaseModel):
    """Canonical payload emitted by a preOrder CTA for deterministic quick-order execution."""

    goodsNo: Optional[str] = Field(default=None, description="Canonical goods number.")
    goodsId: Optional[str] = Field(default=None, description="Legacy goods identifier; mapped to goodsNo.")
    ordQty: Optional[int] = Field(default=None, description="Order quantity.")
    shopId: Optional[str] = Field(default=None, description="Store ID.")
    requestedCalDay: Optional[str] = Field(default=None, description="Reservation day in YYYYMMDD.")
    rsvHour: Optional[str] = Field(default=None, description="Reservation hour in HH or HH:MM.")
    carNo: Optional[str] = Field(default=None, description="Vehicle plate number.")
    carLncCd: Optional[str] = Field(default=None, description="Registered vehicle linkage code.")
    paymentAmount: Optional[int] = Field(default=None, description="Expected payment amount.")
    productName: Optional[str] = Field(default=None, description="Product display name.")
    tireSize: Optional[str] = Field(default=None, description="Tire size.")
    storeName: Optional[str] = Field(default=None, description="Store display name.")
    bookingDateTime: Optional[str] = Field(default=None, description="Korean booking date/time label.")
    mbrCarRegSeq: Optional[str] = Field(default=None, description="Member car registration sequence.")

    model_config = {"extra": "allow"}


class QuickOrderActionRequest(BaseModel):
    """Structured action request for preOrder CTA execution."""

    session_id: str = Field(..., description="Session ID.")
    message_id: Optional[str] = Field(default=None, description="Client-side action/message id for idempotency.")
    action: str = Field(default="quick_order_execute", description="Action name.")
    payload: QuickOrderActionPayload = Field(..., description="Canonical quick-order payload.")
    stream: bool = Field(default=True, description="Stream mode; action endpoint returns SSE by default.")
    tracing_id: Optional[str] = Field(default=None, description="Tracing ID for Langfuse/eval.")


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
    template_data: Optional[dict] = Field(default=None, description="UI template data for assistant messages")


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


class AppendMessageRequest(BaseModel):
    """Request to append a message to chat history."""
    session_id: str = Field(..., description="Session ID")
    content: str = Field(..., description="Message content")
    role: str = Field(default="user", description="Role (user/assistant)")
    template_data: Optional[dict] = Field(default=None, description="Optional template data for assistant messages")


class AppendMessageResponse(BaseModel):
    """Response after appending a message."""
    success: bool = Field(..., description="Append success flag")
    session_id: str = Field(..., description="Session ID")
    msg_id: str = Field(..., description="Created message ID")
    role: str = Field(..., description="Message role")
    created_at: str = Field(..., description="Created timestamp")
