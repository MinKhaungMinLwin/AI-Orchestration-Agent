"""Pydantic schemas for FE data templates.

Each migrated domain agent should use a structured response schema so the model
returns the final FE payload in a guaranteed shape.
"""

import logging
import re
from typing import Annotated, ClassVar, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

logger = logging.getLogger(__name__)

# Deterministic enforcement for qty-question quickReplies.
# LLM 가 "타이어 수량을 알려주세요" 류 질문을 emit 하면서 chip 에 1개/3개 등을
# 누락하는 휘발성 버그를 막기 위함. c_transaction_agent prompt 룰(L461 / L1310~)
# 이 두 번 보강된 뒤에도 재발해서 schema 측에서 결정적으로 차단.
_QTY_QUESTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"몇\s*개"),
    re.compile(r"(?:타이어\s*)?수량.{0,15}?(?:알려|말씀|선택|골라|어떻게)"),
)
_QTY_CONFIRM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"맞으시"),
)
# Skip qty enforcement when the response asks about OTHER slots (product/size)
# in addition to qty. Pure qty-only questions still trigger chip enforcement.
# Buggy false-positive case: "어떤 상품과 수량인지 알려주세요" — response is asking
# product AND qty together, so forcing qty chips strips the user's chance to
# pick a product first.
_QTY_QUESTION_SKIP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"어떤\s*상품"),
    re.compile(r"상품과\s*(?:수량|사이즈)"),
    re.compile(r"사이즈와\s*수량"),
    re.compile(r"상품(?:명|을)?\s*(?:알려|말씀|선택|입력)"),
)
_REQUIRED_QTY_CHIPS: tuple[str, ...] = ("1개", "2개", "3개", "4개")

# Deterministic enforcement for satisfaction / repurchase / greeting quickReplies.
# LLM 이 사용자 호감/재구매 의도 발화 ("원주점에서 구매해서 너무 만족했어. 다음에도 또…")
# 또는 단순 인사 ("하이", "안녕") 에 대해 `["다시 시도", "상담사 연결", "처음으로"]`
# 같은 failure/fallback chip 을 휘발성으로 emit 하는 버그가 a_leading_agent prompt
# 보강(L577~) 후에도 재발해서 schema 측에서 결정적으로 차단. assistantResponse 가
# 아래 패턴 중 하나 이상 매칭 + chip 에 FORBIDDEN chip 중 하나 이상 포함될 때만
# 발동(false-positive 최소화).
_SATISFACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # 만족 / 재구매 의도
    re.compile(r"만족하"),
    re.compile(r"기쁩니다|기쁘네요|기쁘게"),
    re.compile(r"다음에도\s*(?:이용|구매|찾)"),
    re.compile(r"또\s*(?:이용|찾아|구매)"),
    re.compile(r"잘\s*(?:받으셨|받으신|구매하셨)"),
    # 인사 / 환영 / 일반 도움 안내 (LEADING agent 의 전형 오프닝 멘트)
    re.compile(r"안녕하세요.*도와드릴"),
    re.compile(r"반갑습니다.*도와드릴"),
    re.compile(r"무엇을\s*도와드릴"),
    re.compile(r"어떻게\s*도와드릴"),
    re.compile(r"어떤\s*도움.*드릴"),
    re.compile(r"편하게\s*(?:말씀|도와)"),
    # 답례 / 감사 표현 (LEADING 의 "고마워" 응답)
    re.compile(r"감사드립니다|감사합니다"),
    re.compile(r"별말씀"),
)
_FORBIDDEN_SATISFACTION_CHIPS: frozenset[str] = frozenset({
    "구매하기", "다시 시도", "상담사 연결", "1:1 문의하기",
})
_DEFAULT_SATISFACTION_CHIPS: tuple[tuple[str, str], ...] = (
    ("상품 검색", "DISCOVERY"),
    ("타이어 추천", "DISCOVERY"),
)
_HOME_QUICK_REPLY_LABEL: str = "처음으로"


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
    nextAction: "NextActionPayload | None" = Field(
        default=None,
        description=(
            "Internal coordinator hint for chaining. The backend strips this field "
            "before streaming to FE."
        ),
    )


class NextActionPayload(BaseModel):
    """Agent-declared next action for coordinator chaining (B1)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["stop", "continue"] = Field(
        ...,
        description="Whether coordinator should stop or continue chaining.",
    )
    domain: Literal["discovery", "transaction", "support"] | None = Field(
        default=None,
        description="Required when type='continue'; ignored for stop.",
    )

    @model_validator(mode="after")
    def validate_type_domain_pair(self):
        if self.type == "continue" and self.domain is None:
            raise ValueError("nextAction.domain is required when nextAction.type='continue'")
        if self.type == "stop" and self.domain is not None:
            raise ValueError("nextAction.domain must be null when nextAction.type='stop'")
        return self


class QuickReplyChip(BaseModel):
    """A single quick reply chip with optional routing metadata for classifier skip."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., min_length=1)
    domain: Optional[str] = Field(
        default=None,
        description="Target domain for this chip. One of: DISCOVERY, TRANSACTION, SUPPORT, LEADING. "
                    "Set by the emitting agent so the backend can skip the LLM classifier on the next turn.",
    )
    url: Optional[str] = Field(
        default=None,
        description="Optional external URL. When set, the FE opens this URL in a new tab on click "
                    "instead of sending a chat message. Used for store-detail-page redirects and "
                    "similar out-of-conversation navigation.",
    )


class QuickReplyTemplate(TemplatePayload):
    """`quickReply` template — text response with routing hints."""

    TEMPLATE_NAME: ClassVar[str] = "quickReply"

    _MAX_QUICK_REPLIES: ClassVar[int] = 4

    assistantResponse: str = Field(..., min_length=1)
    quickReplies: list[QuickReplyChip] = Field(default_factory=list)
    predictedDomains: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("quickReplies")
    @classmethod
    def truncate_quick_replies(cls, v: list[QuickReplyChip]) -> list[QuickReplyChip]:
        if len(v) > cls._MAX_QUICK_REPLIES:
            logger.warning("quickReplies has %d chips, truncating to %d", len(v), cls._MAX_QUICK_REPLIES)
            return v[: cls._MAX_QUICK_REPLIES]
        return v

    @model_validator(mode="after")
    def enforce_quantity_chips(self) -> "QuickReplyTemplate":
        text = self.assistantResponse or ""
        if any(p.search(text) for p in _QTY_CONFIRM_PATTERNS):
            return self
        if not any(p.search(text) for p in _QTY_QUESTION_PATTERNS):
            return self
        # Skip if the response asks about other slots (product/size) too —
        # forcing qty chips would strip the user's chance to pick those first.
        if any(p.search(text) for p in _QTY_QUESTION_SKIP_PATTERNS):
            return self
        chip_labels = {c.label for c in self.quickReplies}
        if all(req in chip_labels for req in _REQUIRED_QTY_CHIPS):
            return self
        missing = [r for r in _REQUIRED_QTY_CHIPS if r not in chip_labels]
        logger.warning(
            "QuickReplyTemplate qty-question auto-fix: original=%s missing=%s; replacing with %s",
            [c.label for c in self.quickReplies],
            missing,
            list(_REQUIRED_QTY_CHIPS),
        )
        self.quickReplies = [
            QuickReplyChip(label=label, domain="TRANSACTION") for label in _REQUIRED_QTY_CHIPS
        ]
        return self

    @model_validator(mode="after")
    def enforce_satisfaction_chips(self) -> "QuickReplyTemplate":
        """Replace failure/fallback chips with progress chips on satisfaction messages.

        Trigger: assistantResponse 가 만족·기쁨·재구매 응답 패턴 매칭 AND quickReplies 에
        FORBIDDEN chip(구매하기/다시 시도/상담사 연결/1:1 문의하기) 중 하나 이상 포함.
        그 경우에만 전체 chip 셋을 `[상품 검색, 타이어 추천, 처음으로]` 디폴트로 교체.
        FORBIDDEN chip 이 하나도 없으면 그대로 통과(prompt 가 이미 잘 emit 한 경우).
        """
        text = self.assistantResponse or ""
        if not any(p.search(text) for p in _SATISFACTION_PATTERNS):
            return self
        existing_labels = {c.label for c in self.quickReplies}
        if not (existing_labels & _FORBIDDEN_SATISFACTION_CHIPS):
            return self
        logger.warning(
            "QuickReplyTemplate satisfaction auto-fix: original=%s; replacing with %s",
            [c.label for c in self.quickReplies],
            [label for label, _ in _DEFAULT_SATISFACTION_CHIPS],
        )
        self.quickReplies = [
            QuickReplyChip(label=label, domain=domain)
            for label, domain in _DEFAULT_SATISFACTION_CHIPS
        ]
        return self

    @model_validator(mode="after")
    def remove_home_chip(self) -> "QuickReplyTemplate":
        """Do not expose the global "처음으로" quick button."""
        if not self.quickReplies:
            return self
        filtered = [
            chip for chip in self.quickReplies
            if chip.label.strip() != _HOME_QUICK_REPLY_LABEL
        ]
        if len(filtered) == len(self.quickReplies):
            return self
        logger.info(
            "QuickReplyTemplate removed home chip: original=%s",
            [chip.label for chip in self.quickReplies],
        )
        self.quickReplies = filtered
        if not any((chip.domain or "").upper() == "LEADING" for chip in self.quickReplies):
            self.predictedDomains = [
                domain for domain in self.predictedDomains
                if str(domain).upper() != "LEADING"
            ]
        return self


class QuickReplyDataEvent(BaseModel):
    """Structured response for `quickReply` data events."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["quickReply"] = "quickReply"
    data: QuickReplyTemplate
    nextAction: "NextActionPayload | None" = None


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


SupportDataEvent = Annotated[
    QuickReplyDataEvent | QnaCompleteDataEvent,
    Field(discriminator="template"),
]


class VoucherMeta(BaseModel):
    """Hidden FE metadata for a voucher card."""

    model_config = ConfigDict(extra="forbid")

    couponId: str = Field(..., min_length=1)


class VoucherItem(BaseModel):
    """Visible coupon card content for the FE."""

    model_config = ConfigDict(extra="forbid")

    nameVoucher: str = Field(..., min_length=1)
    discount: str = Field(..., min_length=1)
    dateVoucher: str = Field(..., min_length=1)
    downloadLink: str
    myCouponLink: RedictLink


class VoucherTemplate(TemplatePayload):
    """`voucher` template — coupon list results."""

    TEMPLATE_NAME: ClassVar[str] = "voucher"

    assistantResponse: str = Field(..., min_length=1)
    vouchers: list[VoucherItem] = Field(..., min_length=1, max_length=5)
    metadata: list[VoucherMeta] = Field(..., min_length=1, max_length=5)

    @model_validator(mode="after")
    def validate_metadata_alignment(self):
        if len(self.vouchers) != len(self.metadata):
            raise ValueError("metadata length must match vouchers length")
        return self


class VoucherDataEvent(BaseModel):
    """Structured response for `voucher` data events."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["voucher"] = "voucher"
    data: VoucherTemplate


class LocationMeta(BaseModel):
    """Hidden FE metadata for a store result card."""

    model_config = ConfigDict(extra="forbid")

    shopId: str = Field(..., min_length=1)


class LocationItem(BaseModel):
    """Visible store card content for the FE."""

    model_config = ConfigDict(extra="ignore")

    nameAddress: str = Field(..., min_length=1)
    distance: str
    detailAddress: str
    isAllMyT: bool
    todayInstall: bool
    tnaDelivery: bool
    description: str


class LocationTemplate(TemplatePayload):
    """`location` template — store list results."""

    TEMPLATE_NAME: ClassVar[str] = "location"

    assistantResponse: str = Field(..., min_length=1)
    stores: list[LocationItem] = Field(..., min_length=1, max_length=10)
    metadata: list[LocationMeta] = Field(..., min_length=1, max_length=10)
    # Routing hint for the FE click handler. When True, the FE should treat a
    # store-card click as a flow-advancement signal and call /chat so the
    # agent can return the next step (typically datepick). When False
    # (default), the FE keeps the legacy /append shortcut that just shows the
    # store's description bubble — appropriate for pure info lookups.
    # Set True from booking/order/stock contexts (Flow 6 STEP 5A, Flow 3,
    # Flow 3.5). Leave False for standalone store-info queries (Flow 5
    # General, Flow 4 nearby-stores info).
    isBookingFlow: bool = False

    @model_validator(mode="after")
    def validate_metadata_alignment(self):
        if len(self.stores) != len(self.metadata):
            raise ValueError("metadata length must match stores length")
        return self


class LocationDataEvent(BaseModel):
    """Structured response for `location` data events."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["location"] = "location"
    data: LocationTemplate


class ScheduleItem(BaseModel):
    """Visible schedule item for the FE date picker."""

    model_config = ConfigDict(extra="allow")

    date: str = Field(..., min_length=1)
    available: bool
    availableTimes: list[int] = Field(default_factory=list)
    index: int

    @field_validator("availableTimes")
    @classmethod
    def exclude_noon(cls, v: list[int]) -> list[int]:
        return [t for t in v if t != 12]


class DatepickTemplate(TemplatePayload):
    """`datepick` template — schedule and slot results."""

    TEMPLATE_NAME: ClassVar[str] = "datepick"

    assistantResponse: str = Field(..., min_length=1)
    dates: list[ScheduleItem] = Field(..., min_length=1)
    selectedDate: Optional[int] = None
    metadata: dict = Field(default_factory=dict)


class DatepickDataEvent(BaseModel):
    """Structured response for `datepick` data events."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["datepick"] = "datepick"
    data: DatepickTemplate


class OrderInfo(BaseModel):
    """Shared order summary displayed in pre-order and completion states."""

    model_config = ConfigDict(extra="forbid")

    # carInfo / storeName: 사용자가 차량 미등록 상태로 주문/예약을 진행하거나
    # cart-save 흐름(매장 선택 전 단계)에 들어올 수 있어 optional. FE는 빈 값을
    # "—"로 그래스풀 처리(chatbox-order-summary.js valOrDash). required로 두면
    # LLM이 cart-save 단계에서 null을 emit해 schema validation 실패 → silent
    # terminator(\n\n) + fallback chips만 사용자에게 보여 cart 진행이 막힌다.
    carInfo: str | None = None
    product: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=0)
    storeName: str | None = None
    bookingDateTime: str | None = None
    paymentAmount: int | None = Field(default=None, ge=0)


class RecommendActions(BaseModel):
    """Suggested next actions for the FE pre-order card."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1)
    listActions: list[str] = Field(..., min_length=1, max_length=5)


class PreOrderMeta(BaseModel):
    """Hidden FE metadata for order preview."""

    model_config = ConfigDict(extra="forbid")

    goodsId: str = Field(..., min_length=1)
    # shopId: optional during cart-save flow (before store selection). Same
    # rationale as OrderInfo.storeName / carInfo — required would fail
    # validation and show fallback chips to the user instead of the cart card.
    shopId: str | None = None
    carNo: str | None = None
    carLncCd: str | None = None


class PreOrderTemplate(TemplatePayload):
    """`preOrder` template — order preview before final confirmation."""

    TEMPLATE_NAME: ClassVar[str] = "preOrder"

    assistantResponse: str = Field(..., min_length=1)
    orderInfo: OrderInfo
    isReadyToOrder: bool
    isReadyToAddToCart: bool
    # Optional: the FE renders pay/cart buttons inside the orderInfo card itself,
    # so a separate recommendActions follow-up bubble duplicates the same intent.
    # New emissions should omit this field; legacy emitters that still set it
    # remain compatible.
    recommendActions: RecommendActions | None = None
    metadata: PreOrderMeta


class PreOrderDataEvent(BaseModel):
    """Structured response for `preOrder` data events."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["preOrder"] = "preOrder"
    data: PreOrderTemplate


class OrderCompleteResult(BaseModel):
    """Compact tool result included inside the orderComplete payload."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., min_length=1)


class OrderCompleteMeta(BaseModel):
    """Hidden FE metadata for order completion."""

    model_config = ConfigDict(extra="forbid")

    ordNo: str | None = None
    goodsId: str = Field(..., min_length=1)
    # shopId: optional during cart-save flow (no store selected). PreOrderMeta
    # already treats shopId as optional for the same reason. Keeping it required
    # here caused TransactionDataEvent validation to fail on cart success →
    # base_agent fell back to quickReply + ["다시 시도", "상담사 연결", "처음으로"]
    # chips. Aligning the two metas eliminates that silent fallback path.
    shopId: str | None = None


class OrderCompleteTemplate(TemplatePayload):
    """`orderComplete` template — quick order or cart save result."""

    TEMPLATE_NAME: ClassVar[str] = "orderComplete"

    assistantResponse: str = Field(..., min_length=1)
    orderInfo: OrderInfo
    isSuccess: bool
    type: Literal["order", "cart"]
    message: str | None = None
    data: OrderCompleteResult
    metadata: OrderCompleteMeta


class OrderCompleteDataEvent(BaseModel):
    """Structured response for `orderComplete` data events."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["orderComplete"] = "orderComplete"
    data: OrderCompleteTemplate


TransactionDataEvent = Annotated[
    QuickReplyDataEvent
    | VoucherDataEvent
    | LocationDataEvent
    | DatepickDataEvent
    | PreOrderDataEvent
    | OrderCompleteDataEvent,
    Field(discriminator="template"),
]


class TransactionAgentOutput(BaseModel):
    """Transaction agent output with optional internal chain hint."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: str
    data: dict
    nextAction: NextActionPayload | None = None

    @model_validator(mode="after")
    def validate_transaction_payload(self):
        event = TypeAdapter(TransactionDataEvent).validate_python({
            "type": self.type,
            "template": self.template,
            "data": self.data,
        })
        # validator 가 mutate 한 결과 (예: QuickReplyTemplate.enforce_quantity_chips
        # 의 수량 chip 자동 보정) 를 self.data 에 반영. 단순 validate_python 만 호출하면
        # 보정 결과가 throw away 되어 LLM 휘발성 누락이 wire 로 그대로 새어 나간다.
        self.data = event.data.model_dump()
        return self


class ProductMeta(BaseModel):
    """Hidden FE metadata for a product card."""

    model_config = ConfigDict(extra="forbid")

    goodsId: str = Field(..., min_length=1)


class ProductTag(BaseModel):
    """Tag chip rendered on a product card.

    primary=True → 강조 스타일 (chatbox-product-tag-primary, prc_grd_nm 매핑)
    primary=False → 일반 스타일 (chatbox-product-tag-secondary, goods_pfm_nm 매핑)
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    primary: bool = False


class ProductItem(BaseModel):
    """Visible product card content for the FE.

    extra="ignore" — LLM 이 종종 BE row 의 필드명(comfort, review_count 등)을
    그대로 emit 하는 hallucination 이 발생한다. forbid 로 두면 validation 이
    실패해 카드 자체가 안 나오므로(quickReply fallback 발생), ignore 로 풀어
    검증을 통과시키고 model_dump 시점에 자동 strip 한다.
    `inject_product_tags_and_sanitize` 가 한 번 더 schema-키 화이트리스트로
    sanitize 하므로 wire 에는 정의된 필드만 노출된다.
    """

    model_config = ConfigDict(extra="ignore")

    imageUrl: str
    title: str = Field(..., min_length=1)
    tires: str
    titleProductName: str = ""
    titleTires: str = ""
    price: Optional[int] = Field(None, ge=0)
    originalPrice: Optional[int] = Field(None, ge=0)
    discountRate: Optional[float] = Field(None, ge=0)
    discountAmount: Optional[int] = Field(None, ge=0)
    rate: float = Field(..., ge=0.0, le=5.0)
    totalQuantity: int = Field(..., ge=0)
    tags: list[ProductTag] = Field(default_factory=list)


class ProductTemplate(TemplatePayload):
    """`product` template — product search and recommendation results."""

    TEMPLATE_NAME: ClassVar[str] = "product"

    assistantResponse: str = Field(..., min_length=1)
    products: list[ProductItem] = Field(..., min_length=1, max_length=10)
    metadata: list[ProductMeta] = Field(..., min_length=1, max_length=10)
    # Routing hint mirroring LocationTemplate.isBookingFlow. When True, the FE
    # should treat a product-card click as a flow-advancement signal and call
    # /chat (so the next checklist step — qty / shop / inventory / order —
    # runs). When False (default), the FE keeps the legacy /append shortcut
    # that just shows the product description bubble — appropriate for
    # product_recommend goal where the user is browsing.
    # Set True from store_with_stock / place_order / price_inquiry contexts.
    isBookingFlow: bool = False

    @model_validator(mode="after")
    def validate_metadata_alignment(self):
        if len(self.products) != len(self.metadata):
            raise ValueError("metadata length must match products length")
        return self


class ProductDataEvent(BaseModel):
    """Structured response for `product` data events."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["product"] = "product"
    data: ProductTemplate


class CarMeta(BaseModel):
    """Hidden FE metadata for a car selection card.

    `tireSize` / `tireSizeRe` are populated from the BE vehicle response
    (`tire_size_fr` / `tire_size_re`) so that when the user picks a car the
    coordinator can resolve the correct tire size into slots — without
    needing the LLM to re-issue a recommendation tool call. Front rear
    asymmetry is preserved (a few performance/SUV trims have different
    sizes per axle).
    """

    model_config = ConfigDict(extra="forbid")

    carNo: str = Field(..., min_length=1)
    carLncCd: str | None = None
    tireSize: str | None = None
    tireSizeRe: str | None = None


class CarItem(BaseModel):
    """Visible car card content for the FE."""

    model_config = ConfigDict(extra="forbid")

    licensePlate: str = Field(..., min_length=1)
    info: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    imageUrl: str


class ListCarTemplate(TemplatePayload):
    """`listCar` template — choose one car from multiple matches."""

    TEMPLATE_NAME: ClassVar[str] = "listCar"

    assistantResponse: str = Field(..., min_length=1)
    listCar: list[CarItem] = Field(..., min_length=1, max_length=5)
    metadata: list[CarMeta] = Field(..., min_length=1, max_length=5)

    @model_validator(mode="after")
    def validate_metadata_alignment(self):
        if len(self.listCar) != len(self.metadata):
            raise ValueError("metadata length must match listCar length")
        return self


class ListCarDataEvent(BaseModel):
    """Structured response for `listCar` data events."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["listCar"] = "listCar"
    data: ListCarTemplate


class CheapestItem(BaseModel):
    """Visible cheapest-product comparison payload."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1)
    originalPrice: int = Field(..., ge=0)
    quantity: int = Field(..., ge=0)
    totalDiscount: int = Field(..., ge=0)
    productDiscount: int = Field(..., ge=0)
    couponDiscount: int = Field(..., ge=0)
    finalPrice: int = Field(..., ge=0)


class CheapestProductTemplate(TemplatePayload):
    """`cheapestProduct` template — best discount option."""

    TEMPLATE_NAME: ClassVar[str] = "cheapestProduct"

    assistantResponse: str = Field(..., min_length=1)
    cheapestProduct: list[CheapestItem] = Field(..., min_length=1, max_length=1)
    metadata: list[ProductMeta] = Field(..., min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_metadata_alignment(self):
        if len(self.cheapestProduct) != len(self.metadata):
            raise ValueError("metadata length must match cheapestProduct length")
        return self


class CheapestProductDataEvent(BaseModel):
    """Structured response for `cheapestProduct` data events."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["cheapestProduct"] = "cheapestProduct"
    data: CheapestProductTemplate


class YoutubeItem(BaseModel):
    """Visible YouTube preview card content for the FE."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1)
    thumbnailUrl: str
    youtubeUrl: str
    videoId: str


class PreviewYoutubeTemplate(TemplatePayload):
    """`previewYoutube` template — related video previews."""

    TEMPLATE_NAME: ClassVar[str] = "previewYoutube"

    assistantResponse: str = Field(..., min_length=1)
    items: list[YoutubeItem] = Field(..., min_length=1, max_length=5)


class PreviewYoutubeDataEvent(BaseModel):
    """Structured response for `previewYoutube` data events."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["previewYoutube"] = "previewYoutube"
    data: PreviewYoutubeTemplate


DiscoveryDataEvent = Annotated[
    QuickReplyDataEvent | ProductDataEvent | ListCarDataEvent | CheapestProductDataEvent | PreviewYoutubeDataEvent,
    Field(discriminator="template"),
]


class DiscoveryAgentOutput(BaseModel):
    """Discovery agent output with optional internal chain hint."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: str
    data: dict
    nextAction: NextActionPayload | None = None

    @model_validator(mode="after")
    def validate_discovery_payload(self):
        event = TypeAdapter(DiscoveryDataEvent).validate_python({
            "type": self.type,
            "template": self.template,
            "data": self.data,
        })
        # validator 가 mutate 한 결과 (예: QuickReplyTemplate.enforce_quantity_chips
        # 의 수량 chip 자동 보정) 를 self.data 에 반영. validate_python 만 호출하면
        # 보정 결과가 throw away 되어 LLM 휘발성 누락이 wire 로 그대로 새어 나간다.
        self.data = event.data.model_dump()
        return self
