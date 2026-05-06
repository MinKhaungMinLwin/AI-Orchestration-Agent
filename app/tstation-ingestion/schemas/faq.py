from typing import Optional

from pydantic import BaseModel, Field


class FaqMetadata(BaseModel):
    category_lv1: str = ""
    category_lv2: str = ""
    intent: str = ""
    keywords: list[str] = Field(default_factory=list)
    source: str = ""
    lang: str = "ko"
    document_type: str = "faq_qa"

    model_config = {"extra": "allow"}


class FaqDocument(BaseModel):
    id: str
    content: str = ""
    question: str
    answer: str
    metadata: FaqMetadata = Field(default_factory=FaqMetadata)


class IngestRequest(BaseModel):
    documents: list[FaqDocument] = Field(..., min_length=1)


class IngestResponse(BaseModel):
    status: str
    upserted_count: int
    message: str
