"""RouteDecision — the single structured output of the router call."""

from enum import Enum

from pydantic import BaseModel, Field

from services.tstation.chat_v3.slots.schemas import SlotsPatch


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
