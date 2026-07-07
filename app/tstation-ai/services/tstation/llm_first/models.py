from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class StructuredKnownInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goods_no: str | None
    tire_size: str | None
    ord_qty: int | None
    product_name: str | None
    shop_id: str | None
    store_name: str | None
    region: str | None
    store_attribute: str | None
    date: str | None
    time: str | None
    mbr_no: str | None
    car_no: str | None
    owner_nm: str | None
    car_model: str | None
    car_lnc_cd: str | None
    vehicle_type: Literal["none", "ev", "suv", "passenger", "truck_van"] | None
    recommendation_type: Literal[
        "none",
        "tstation",
        "discount",
        "value",
        "wet",
        "snow",
        "high_speed",
        "performance",
        "low_vibration",
        "commute",
        "long_distance",
        "urban",
        "family",
        "ev",
        "heavy_load",
        "weekend",
        "safe_kids",
        "all_weather",
        "warranty",
        "summer",
        "sound_absorber",
    ] | None
    recommendation_source: Literal["none", "recommendation", "best_seller"] | None
    season_nm: Literal["none", "사계절", "올웨더", "여름", "겨울"] | None
    sort_by: Literal["none", "price_asc", "price_desc", "rating_desc", "review_desc"] | None
    min_price: int | None
    max_price: int | None
    limit: int | None
    vehicle_query: str | None
    months: int | None
    from_date: str | None
    to_date: str | None
    escalation_target: Literal["none", "qna", "human"] | None
    account_lookup: Literal[
        "none",
        "coupons",
        "reservations",
        "orders",
        "maintenance_history",
        "warranties",
    ] | None


class StructuredSelectedAF(BaseModel):
    model_config = ConfigDict(extra="forbid")

    af: AgentFlow
    reason: str
    required_inputs: list[str]
    known_inputs: StructuredKnownInputs
    missing_inputs: list[str]


class StructuredPlannerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
