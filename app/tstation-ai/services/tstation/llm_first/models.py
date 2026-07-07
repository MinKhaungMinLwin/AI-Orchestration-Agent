from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentFlow(str, Enum):
    STORE = "StoreAF"
    PRICE = "PriceAF"
    INVENTORY = "InventoryAF"
    QUICK_SHOPPING = "QuickShoppingAF"
    PRODUCT_RECOMMENDATION = "ProductRecommendationAF"
    PRODUCT_DESCRIPTION = "ProductDescriptionAF"
    FAQ = "FAQAF"
    ORDER_DELIVERY = "OrderDeliveryAF"
    PRODUCT_COMPATIBILITY = "ProductCompatibilityAF"
    FALLBACK_ESCALATION = "FallbackEscalationAF"


class SelectedAF(BaseModel):
    af: AgentFlow
    reason: str = ""
    required_inputs: list[str] = Field(default_factory=list)
    known_inputs: dict[str, Any] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)


class PlannerDecision(BaseModel):
    selected_afs: list[SelectedAF] = Field(default_factory=list)
    conversation_goal: str = "answer_user"
    answer_mode: Literal["clarification", "tool_grounded_answer", "blocked"] = "tool_grounded_answer"
    requires_user_confirmation: bool = False
    resume_previous_flow: bool = False


class StructuredSelectedAF(BaseModel):
    af: AgentFlow
    reason: str
    required_inputs: list[str]
    known_inputs: dict[str, Any]
    missing_inputs: list[str]


class StructuredPlannerDecision(BaseModel):
    selected_afs: list[StructuredSelectedAF]
    conversation_goal: str
    answer_mode: Literal["clarification", "tool_grounded_answer", "blocked"]
    requires_user_confirmation: bool
    resume_previous_flow: bool


class ProductState(BaseModel):
    goods_no: str | None = None
    product_name: str | None = None
    tire_size: str | None = None


class StoreState(BaseModel):
    shop_id: str | None = None
    shop_name: str | None = None
    region: str | None = None


class ScheduleState(BaseModel):
    date: str | None = None
    time: str | None = None


class PriceState(BaseModel):
    final_price: int | None = None
    source: str | None = None


class CommerceState(BaseModel):
    product: ProductState = Field(default_factory=ProductState)
    quantity: int | None = None
    store: StoreState = Field(default_factory=StoreState)
    schedule: ScheduleState = Field(default_factory=ScheduleState)
    price: PriceState = Field(default_factory=PriceState)
    status: str = "collecting_info"


class ConversationState(BaseModel):
    conversation_summary: str = ""
    commerce_state: CommerceState = Field(default_factory=CommerceState)
    last_facts: dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    af: AgentFlow
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    blocked: bool = False
    reason: str | None = None


class FactBundle(BaseModel):
    planner: PlannerDecision
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)
    templates: list[dict[str, Any]] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    state: ConversationState = Field(default_factory=ConversationState)
