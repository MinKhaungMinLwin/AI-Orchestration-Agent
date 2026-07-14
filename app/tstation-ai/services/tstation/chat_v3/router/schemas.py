"""RouteDecision — the single structured output of the router call."""

from enum import Enum

from pydantic import BaseModel, Field

from services.tstation.chat_v3.slots.schemas import SlotsPatch


class BrandContext(BaseModel):
    installed_brand: str | None = Field(
        default=None,
        description="Brand currently mounted on the user's vehicle, if the user states one.",
    )
    desired_brand: str | None = Field(
        default=None,
        description="Brand the user wants to buy, search, or receive recommendations for.",
    )
    excluded_brand: str | None = Field(
        default=None,
        description="Brand the user explicitly wants to exclude from recommendations.",
    )
    unsupported_brand_target: str | None = Field(
        default=None,
        description=(
            "Unsupported brand only when that brand itself is the user's target for search, price, stock, "
            "availability, or recommendation. Leave empty when the unsupported brand is only the installed brand."
        ),
    )

    def has_non_target_brand_context(self) -> bool:
        return any(str(value or "").strip() for value in (self.installed_brand, self.desired_brand, self.excluded_brand))


class GuardId(str, Enum):
    NONE = "none"
    PII = "pii"
    PRIVACY_CONTACT = "privacy_contact"
    REGIONAL_CHEAPEST = "regional_cheapest"
    UNSUPPORTED_BRAND = "unsupported_brand"
    EXTERNAL_PRICE = "external_price"
    PAST_EVENT_PAGE = "past_event_page"
    COUPON_ISSUE_REQUEST = "coupon_issue_request"
    EXPIRED_COUPON_OR_EVENT = "expired_coupon_or_event"
    NONEXISTENT_BENEFIT = "nonexistent_benefit"
    RESERVATION_DATE_RANGE = "reservation_date_range"
    VEHICLE_TYPE_COMPATIBILITY = "vehicle_type_compatibility"
    PICKUP_STATUS = "pickup_status"
    PICKUP_INFO = "pickup_info"
    DIRECT_HOME_DELIVERY = "direct_home_delivery"
    SHIPPING_FEE_REGION = "shipping_fee_region"
    ONLINE_STORE_PRICE_POLICY = "online_store_price_policy"
    REGIONAL_PRICE_POLICY = "regional_price_policy"
    PRODUCT_CODE_REQUEST = "product_code_request"
    OUT_OF_SCOPE = "out_of_scope"


class Domain(str, Enum):
    LEADING = "LEADING"
    DISCOVERY = "DISCOVERY"
    TRANSACTION = "TRANSACTION"
    SUPPORT = "SUPPORT"


class RouteDecision(BaseModel):
    guard_id: GuardId = Field(
        default=GuardId.NONE,
        description="정책 가드에 해당하면 해당 id, 아니면 none",
    )
    domain: Domain = Field(
        default=Domain.LEADING,
        description="이번 턴을 처리할 주 업무 영역",
    )
    extra_domains: list[Domain] = Field(
        default_factory=list,
        description="주 영역 외에 이번 턴 처리에 함께 필요한 보조 영역 (예: 상품 미확정 상태의 주문 → DISCOVERY)",
    )

    def all_domains(self) -> list[str]:
        ordered = [self.domain.value]
        for extra in self.extra_domains:
            if extra.value not in ordered:
                ordered.append(extra.value)
        return ordered
    intents: list[str] = Field(
        default_factory=list,
        description="이번 턴의 세부 의도 키워드 (자유 서술, 1~3개)",
    )
    slots_patch: SlotsPatch = Field(
        default_factory=SlotsPatch,
        description="이번 사용자 발화에서 새로 알 수 있게 된 슬롯 값만",
    )
    brand_context: BrandContext = Field(
        default_factory=BrandContext,
        description=(
            "Role of tire brands mentioned in the current user turn. Distinguish installed/current brand, "
            "desired purchase/recommendation brand, excluded brand, and a truly unsupported target brand."
        ),
    )
    installation_schedule_change: bool = Field(
        default=False,
        description=(
            "True when the user wants to change the selected installation date or time for an active "
            "preOrder/order confirmation. Do not set this for questions about why an order attempt failed."
        ),
    )
    needs_selection_card: bool = Field(
        default=True,
        description=(
            "사용자가 이번 턴에 상품 목록에서 골라야 하거나(모델 선택·가격대별·추천 등) 카드가 꼭 필요하면 true. "
            "특정 상품의 리뷰·스펙·비교·단순 가격 문의 등 정보만 원하면 false. 확실치 않으면 true."
        ),
    )
