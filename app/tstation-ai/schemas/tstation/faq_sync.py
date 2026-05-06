from typing import Optional

from pydantic import BaseModel, Field, model_validator


class FAQMetadata(BaseModel):
    category_lv1: Optional[str] = None
    category_lv2: Optional[str] = None
    intent: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    source: Optional[str] = None
    lang: Optional[str] = None
    document_type: Optional[str] = None

    model_config = {"extra": "allow"}


class FAQItem(BaseModel):
    """
    Accepts two input formats:

    Type 1 (FAQ):  representative_question / representative_answer / similar_questions
    Type 2 (CS):   question / answer / intent / keywords / ...

    Both formats are normalised to a unified dict by the ingestion worker
    via DocumentProcessor._normalize_document before embedding.
    """
    id: str | int = Field(..., description="Unique FAQ identifier (used for idempotent upsert)")
    content: str = ""

    # Type 1 fields
    representative_question: Optional[str] = None
    representative_answer: Optional[str] = None
    similar_questions: list[str] = Field(default_factory=list)

    # Type 2 fields
    question: Optional[str] = None
    answer: Optional[str] = None

    metadata: FAQMetadata = Field(default_factory=FAQMetadata)

    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def check_question_and_answer(self) -> "FAQItem":
        has_question = bool(self.representative_question or self.question)
        has_answer = bool(self.representative_answer or self.answer)
        if not has_question:
            raise ValueError("Provide 'representative_question' (Type 1) or 'question' (Type 2)")
        if not has_answer:
            raise ValueError("Provide 'representative_answer' (Type 1) or 'answer' (Type 2)")
        return self


class FAQSyncRequest(BaseModel):
    items: list[FAQItem] = Field(..., min_length=1, description="List of FAQ items to sync (max 500 per request)")
    collection_name: Optional[str] = Field(None, description="Target Qdrant collection (defaults to env QDRANT_COLLECTION_FAQ)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "id": "FAQ-001",
                        "question": "타이어 교체 주기는 얼마나 되나요?",
                        "answer": "일반적으로 4~5년 또는 주행거리 4~5만km 마다 교체를 권장합니다.",
                        "metadata": {
                            "intent": "product_inquiry",
                            "category_lv1": "상품/타이어 관련",
                            "category_lv2": "타이어 상품정보/수명",
                            "keywords": ["타이어", "교체", "주기", "수명"]
                        }
                    }
                ]
            }
        }
    }


class FAQSyncResponse(BaseModel):
    task_id: str = Field(..., description="Task ID to poll status via GET /queue/{task_id}")
    status: str = Field(default="PENDING")
    total_items: int = Field(..., description="Number of FAQ items queued for sync")
    message: str = Field(default="FAQ sync task queued successfully")
