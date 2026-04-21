"""Pydantic schemas for FE data templates.

Each migrated domain agent should use a structured response schema so the model
returns the final FE payload in a guaranteed shape.
"""

from typing import Annotated, ClassVar, Literal

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


class SupportDataEvent(BaseModel):
    """Structured response for Support Agent — accepts quickReply and qnaComplete templates."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["data"] = "data"
    template: Literal["quickReply", "qnaComplete"]
    data: dict


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
    price: int = Field(..., ge=0)
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
