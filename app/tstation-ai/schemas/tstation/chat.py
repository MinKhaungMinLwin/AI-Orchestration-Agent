import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class TStationChatRequest(BaseModel):
    # Chat information
    messages: list[dict] = Field(..., description="List history messages")
    stream: bool = Field(False, title="Stream mode")

    # User information
    user_id: str = Field(..., description="User ID")
    session_id: str = Field(..., description="Session ID")

    # Access token for tstation-be API (per-request, can be different each time)
    access_token: Optional[str] = Field(default=None, description="Access token for tstation-be API calls")

    # Extra user info from UI (overrides JWT fields if overlap)
    user_info: Optional[dict] = Field(default=None, description="Additional user info from UI")

    # Tracing
    tracing_id: str = Field(default_factory=lambda: uuid.uuid4().hex, description="Tracing ID")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Extra metadata")

    @field_validator("messages")
    def validate_messages_not_empty(cls, v):
        if not v:
            raise ValueError(f"messages cannot be null or empty, current value: {v}")
        return v


    model_config = {
        "json_schema_extra": {
            "example": {
                "messages": [
                    {"role": "user", "content": "Hello!"},
                    {"role": "assistant", "content": "Hi! How can I help you?"},
                    {"role": "user", "content": "At 20 words, 📝 Help me find and buy the right tires for my car."},
                ],
                "stream": False,

                "user_id": "Test-User-123",
                "session_id": "test_session_id_123",
                "access_token": "your-access-token-here",
                "user_info": {"location": {
                        "xpos": 123.456,
                        "ypos": 789.012,
                    }
                },

                "tracing_id": "f3a8d97b9c274c2e9dd648b711e221e5",
                "metadata": {
                    "position": "Swagger APIs"
                },
            }
        }
    }

class TStationChatResponse(BaseModel):
    content: str = Field(..., description="Content response of Chatbot")
