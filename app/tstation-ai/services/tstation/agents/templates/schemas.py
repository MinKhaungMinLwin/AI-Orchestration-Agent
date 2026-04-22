"""Pydantic schemas for FE data templates.

Each migrated domain agent should use a structured response schema so the model
returns the final FE payload in a guaranteed shape.
"""

from typing import Annotated, ClassVar, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    stores: list[LocationItem] = Field(..., min_length=1, max_length=5)
    metadata: list[LocationMeta] = Field(..., min_length=1, max_length=5)
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

    carInfo: str = Field(..., min_length=1)
    product: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=0)
    storeName: str = Field(..., min_length=1)
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
    shopId: str = Field(..., min_length=1)
    carNo: str | None = None
    carLncCd: str | None = None


class PreOrderTemplate(TemplatePayload):
    """`preOrder` template — order preview before final confirmation."""

    TEMPLATE_NAME: ClassVar[str] = "preOrder"

    assistantResponse: str = Field(..., min_length=1)
    orderInfo: OrderInfo
    isReadyToOrder: bool
    isReadyToAddToCart: bool
    recommendActions: RecommendActions
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
    shopId: str = Field(..., min_length=1)


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


class ProductMeta(BaseModel):
    """Hidden FE metadata for a product card."""

    model_config = ConfigDict(extra="forbid")

    goodsId: str = Field(..., min_length=1)


class ProductItem(BaseModel):
    """Visible product card content for the FE."""

    model_config = ConfigDict(extra="forbid")

    imageUrl: str
    title: str = Field(..., min_length=1)
    tires: str
    comfort: str
    price: Optional[int] = Field(None, ge=0)
    rate: float = Field(..., ge=0.0, le=5.0)
    totalQuantity: int = Field(..., ge=0)


class ProductTemplate(TemplatePayload):
    """`product` template — product search and recommendation results."""

    TEMPLATE_NAME: ClassVar[str] = "product"

    assistantResponse: str = Field(..., min_length=1)
    products: list[ProductItem] = Field(..., min_length=1, max_length=5)
    metadata: list[ProductMeta] = Field(..., min_length=1, max_length=5)

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
    """Hidden FE metadata for a car selection card."""

    model_config = ConfigDict(extra="forbid")

    carNo: str = Field(..., min_length=1)
    carLncCd: str | None = None


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
