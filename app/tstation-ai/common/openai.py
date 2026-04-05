from typing import Dict, List, Optional
import uuid

from config.tracing import tracer
from langfuse.openai import openai
from pydantic import BaseModel, ConfigDict, Field

tracer.auth_check()

class MetadataTracing(BaseModel):
    langfuse_session_id: Optional[str] = Field(default=None, description="Session ID")
    langfuse_user_id: Optional[str] = Field(default=None, description="User ID")
    langfuse_tags: Optional[List[str]] = Field(default=None, description="Tags")

    model_config = ConfigDict(extra="allow")

class TracingRequest(BaseModel):
    name: str = Field(..., description="Tracing Name")
    tracing_id: str = Field(default_factory=lambda: uuid.uuid4().hex, description="Tracing ID")
    metadata: MetadataTracing = Field(..., description="Tracing Metadata")

    def get_dict_metadata(self) -> Dict:
        return self.metadata.model_dump(exclude_none=True)


class OpenAIWithTracing:
    def __init__(self, api_key: str, base_url: str):
        """
        OpenAIClient with Tracing Enable
        """
        self.client: openai.OpenAI = openai.OpenAI(api_key=api_key, base_url=base_url)


if __name__ == "__main__":
    import uuid

    tracing_request = TracingRequest(
        name="dr-stat-chatbot",
        tracing_id=uuid.uuid4().hex,
        metadata=MetadataTracing(
            langfuse_session_id="your-session-id",
            langfuse_user_id="your-user-id",
            langfuse_tags=["your-tag-1", "your-tag-2"],
            # extra
            stream=False,
        )
    )

    openai = OpenAIWithTracing("your-api-key", "https://api.openai.com/v2/")
    completion = openai.client.chat.completions.create(
        model="openrouter/sonoma-sky-alpha",
        messages=[
            {"role": "system",
             "content": "You are a very accurate calculator. You output only the result of the calculation."},
            {"role": "user", "content": "1 + 1 = "}],
        stream=True,
        stream_options={"include_usage": True},

        ## Tracing
        # Name
        name=tracing_request.name,
        # Trace ID
        trace_id=tracing_request.tracing_id,
        # Metadata
        metadata=tracing_request.get_dict_metadata(),
    )
