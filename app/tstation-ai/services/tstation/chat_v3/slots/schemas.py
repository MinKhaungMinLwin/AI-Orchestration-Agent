"""Slot patch extracted by the router LLM from the current user turn.

A deliberate SUBSET of `ConversationSlots` — only what a user can state
in a message. Merging/dependency-resets stay in `ConversationSlots.merge`.
"""

from pydantic import BaseModel, Field


class SlotsPatch(BaseModel):
    tire_size: str | None = Field(default=None, description="타이어 사이즈, 예: 245/45R18")
    tire_size_front: str | None = Field(default=None, description="전륜 타이어 사이즈")
    tire_size_rear: str | None = Field(default=None, description="후륜 타이어 사이즈")
    tire_model: str | None = Field(
        default=None, description="타이어 모델/패턴명, 예: 벤투스 S2 AS. 상품코드 등 내부 식별자는 모델명이 아니다"
    )
    car_model: str | None = Field(default=None, description="차종명, 예: 그랜저 IG")
    car_no: str | None = Field(
        default=None,
        description="차량 번호판, 예: 12가3456. 상품코드·주문번호 등 차량과 무관한 식별자는 절대 넣지 말 것",
    )
    region: str | None = Field(default=None, description="지역명, 예: 강남구, 수원")
    shop_name: str | None = Field(default=None, description="언급된 매장 이름")
    ord_qty: int | None = Field(default=None, description="구매/장착 수량")
    requested_cal_day: str | None = Field(default=None, description="희망 예약 날짜 YYYYMMDD")
    rsv_hour: str | None = Field(default=None, description="희망 예약 시간 HH")
    goal_type: str | None = Field(
        default=None,
        description=(
            "이번 턴의 목표: product_recommend | product_search | store_with_stock | store_finder | "
            "price_inquiry | coupon_discount_amount | place_order | add_to_cart"
        ),
    )
    pending_intent: str | None = Field(
        default=None,
        description="진행 중 거래 의도: price | stock | order | reservation | cart",
    )
    user_preferences_text: str | None = Field(default=None, description="주행/선호 조건 원문, 예: 승차감 위주, 고속주행 많음")

    def non_empty(self) -> dict:
        return {k: v for k, v in self.model_dump().items() if v is not None}
