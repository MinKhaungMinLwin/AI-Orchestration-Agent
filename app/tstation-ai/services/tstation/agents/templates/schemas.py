"""Pydantic schemas for FE data templates.

Each migrated domain agent should use a structured response schema so the model
returns the final FE payload in a guaranteed shape.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field


class TemplatePayload(BaseModel):
    """Base class for all FE template payloads."""

    model_config = ConfigDict(extra="forbid")

    TEMPLATE_NAME: ClassVar[str] = ""


class DataEvent(BaseModel):
    """Top-level SSE `data` event shape expected by FE."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: str
    data: dict


class QuickReplyTemplate(TemplatePayload):
    """`quickReply` template — used for text-only responses with suggestion chips."""

    TEMPLATE_NAME: ClassVar[str] = "quickReply"

    assistantResponse: str = Field(..., min_length=1)
    quickReplies: list[str] = Field(default_factory=list, max_length=4)


class QuickReplyDataEvent(BaseModel):
    """Structured response for `quickReply` data events."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["quickReply"] = "quickReply"
    data: QuickReplyTemplate


class RedictLink(BaseModel):
    """PC and mobile URLs for 1:1 inquiry redirect."""

    model_config = ConfigDict(extra="allow")

    pc: str
    mobile: str


class QnaCompleteTemplate(TemplatePayload):
    """`qnaComplete` template — used after transfer_to_qna_tool to show the inquiry link."""

    TEMPLATE_NAME: ClassVar[str] = "qnaComplete"

    assistantResponse: str = Field(..., min_length=1)
    redictLink: RedictLink
    cnslType: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)


class QnaCompleteDataEvent(BaseModel):
    """Structured response for `qnaComplete` data events."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["qnaComplete"] = "qnaComplete"
    data: QnaCompleteTemplate


class SupportDataEvent(BaseModel):
    """Structured response for Support Agent — accepts quickReply and qnaComplete templates."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["quickReply", "qnaComplete"]
    data: dict
