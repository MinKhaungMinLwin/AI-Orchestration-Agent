"""Structured gate for direct-delivery and regional shipping-fee policy turns."""

from __future__ import annotations

from enum import Enum
import re

from pydantic import BaseModel, Field


class DeliveryPolicyIntent(str, Enum):
    NONE = "none"
    DIRECT_HOME_DELIVERY = "direct_home_delivery"
    SHIPPING_FEE_REGION = "shipping_fee_region"
    SHIPPING_FEE_FOLLOWUP = "shipping_fee_followup"
    ONLINE_STORE_PRICE_POLICY = "online_store_price_policy"
    REGIONAL_PRICE_POLICY = "regional_price_policy"


class DeliveryPolicyGateDecision(BaseModel):
    intent: DeliveryPolicyIntent = Field(description="Delivery policy intent enum.")
    confidence: float = Field(ge=0, le=1, description="Confidence from 0 to 1.")
    region_hint: str | None = Field(description="Mentioned region, or null.")
    reason: str = Field(description="Short English reason for trace/debug only.")

    @property
    def is_actionable(self) -> bool:
        return self.intent != DeliveryPolicyIntent.NONE and self.confidence >= 0.65


_DELIVERY_TRIGGER_RE = re.compile(
    r"배송비|추가\s*배송|추가\s*비용|도서산간|제주|서귀포|집으로|집에|자택|택배|"
    r"직접\s*(?:갈아|교체|장착)|자가\s*장착|셀프\s*(?:교체|장착)|"
    r"온라인.{0,12}(?:매장|오프라인)|(?:매장|오프라인).{0,12}온라인|"
    r"(?:지역|서울|부산|대구|인천|광주|대전|울산).{0,24}(?:가격|판매가|최종가)",
    re.IGNORECASE,
)
_DIRECT_HOME_DELIVERY_RE = re.compile(
    r"(?:타이어|상품).{0,20}(?:집|자택|우리\s*집|집으로|집에|배송지|주소지|택배).{0,20}"
    r"(?:배송\s*받|배송받|받고\s*싶|보내|택배|수령)|"
    r"(?:집|자택|우리\s*집|집으로|집에|배송지|주소지|택배).{0,20}(?:타이어|상품).{0,20}"
    r"(?:배송\s*받|배송받|받고\s*싶|보내|택배|수령)|"
    r"(?:집으로|집에|자택으로).{0,12}(?:배송\s*받|배송받|배송\s*해|배송해|받고\s*싶|보내|택배|수령)|"
    r"(?:내가|직접|셀프|자가).{0,12}(?:갈아|교체|장착|끼워)",
    re.IGNORECASE,
)
_SHIPPING_FEE_REGION_RE = re.compile(
    r"(?:제주(?:도|특별자치도)?|서귀포(?:시)?|도서산간).{0,24}(?:배송비|배송\s*비|추가|비용|더\s*들)|"
    r"(?:배송비|배송\s*비|추가\s*배송비|추가\s*비용|더\s*들).{0,24}(?:제주(?:도|특별자치도)?|서귀포(?:시)?|도서산간)",
    re.IGNORECASE,
)
_ONLINE_STORE_PRICE_RE = re.compile(
    r"(?:온라인|닷컴).{0,18}(?:매장|오프라인).{0,18}(?:가격|동일|같|차이)|"
    r"(?:매장|오프라인).{0,18}(?:온라인|닷컴).{0,18}(?:가격|동일|같|차이)",
    re.IGNORECASE,
)
_REGIONAL_PRICE_POLICY_RE = re.compile(
    r"(?=.*(?:가격|판매가|최종가))"
    r"(?=.*(?:똑같|같(?:아|은|나요|을까)?|동일|다르|차이|왜))"
    r"(?=.*(?:제주(?:도|특별자치도)?|서귀포(?:시)?|도서산간|서울|부산|대구|인천|광주|대전|울산|지역|매장|지점))",
    re.IGNORECASE,
)
_REGION_ONLY_FOLLOWUP_RE = re.compile(r"^\s*(제주(?:도)?|서귀포(?:시)?|도서산간)(?:은|는|도|요|呢)?\s*[?.!]*\s*$")
_SHIPPING_CONTEXT_RE = re.compile(
    r"배송비|배송\s*비|추가\s*배송|추가\s*비용|도서산간|제주|서귀포|온라인.{0,12}(?:매장|오프라인)",
    re.IGNORECASE,
)


def should_consider_delivery_policy_gate(user_text: str | None, recent_context: str | None = None) -> bool:
    text = user_text or ""
    context = recent_context or ""
    if _DELIVERY_TRIGGER_RE.search(text):
        return True
    return bool(_REGION_ONLY_FOLLOWUP_RE.search(text) and _SHIPPING_CONTEXT_RE.search(context))


def _region_hint(text: str) -> str | None:
    if re.search(r"서귀포", text):
        return "서귀포"
    if re.search(r"제주", text):
        return "제주"
    if re.search(r"도서산간", text):
        return "도서산간"
    return None


def decide_delivery_policy_gate(
    *,
    user_text: str,
    recent_context: str = "",
) -> DeliveryPolicyGateDecision:
    """Classify direct-delivery and regional shipping-fee policy turns."""
    text = user_text or ""
    context = recent_context or ""
    if not should_consider_delivery_policy_gate(text, context):
        return DeliveryPolicyGateDecision(
            intent=DeliveryPolicyIntent.NONE,
            confidence=1.0,
            region_hint=None,
            reason="No delivery-policy trigger.",
        )

    if _DIRECT_HOME_DELIVERY_RE.search(text) and not _SHIPPING_FEE_REGION_RE.search(text):
        return DeliveryPolicyGateDecision(
            intent=DeliveryPolicyIntent.DIRECT_HOME_DELIVERY,
            confidence=0.95,
            region_hint=None,
            reason="User wants tires delivered home or self-installed.",
        )

    if _SHIPPING_FEE_REGION_RE.search(text):
        return DeliveryPolicyGateDecision(
            intent=DeliveryPolicyIntent.SHIPPING_FEE_REGION,
            confidence=0.95,
            region_hint=_region_hint(text),
            reason="User asks regional additional shipping fee.",
        )

    if _REGION_ONLY_FOLLOWUP_RE.search(text) and _SHIPPING_CONTEXT_RE.search(context):
        return DeliveryPolicyGateDecision(
            intent=DeliveryPolicyIntent.SHIPPING_FEE_FOLLOWUP,
            confidence=0.9,
            region_hint=_region_hint(text),
            reason="Short regional follow-up after shipping-fee context.",
        )

    if _ONLINE_STORE_PRICE_RE.search(text):
        return DeliveryPolicyGateDecision(
            intent=DeliveryPolicyIntent.ONLINE_STORE_PRICE_POLICY,
            confidence=0.85,
            region_hint=_region_hint(text),
            reason="User asks online versus store price policy.",
        )

    if _REGIONAL_PRICE_POLICY_RE.search(text):
        return DeliveryPolicyGateDecision(
            intent=DeliveryPolicyIntent.REGIONAL_PRICE_POLICY,
            confidence=0.85,
            region_hint=_region_hint(text),
            reason="User asks regional product price policy.",
        )

    return DeliveryPolicyGateDecision(
        intent=DeliveryPolicyIntent.NONE,
        confidence=0.5,
        region_hint=_region_hint(text),
        reason="Delivery trigger present but policy intent is unclear.",
    )
