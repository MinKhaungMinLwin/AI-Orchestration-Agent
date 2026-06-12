"""Structured LLM gate for coupon query routing.

The gate classifies only the user's coupon intent. It must not answer the user
or infer factual coupon eligibility; existing tool-backed resolvers do that.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
import logging
import re
from textwrap import dedent

from langchain_litellm import ChatLiteLLM
from pydantic import BaseModel, Field

from config.env import settings

logger = logging.getLogger(__name__)


class CouponQueryIntent(str, Enum):
    NONE = "none"
    ISSUE_HOWTO = "issue_howto"
    OWNED_COUPON_LOOKUP = "owned_coupon_lookup"
    BEST_DISCOUNT = "best_discount"
    PRODUCT_COUPON_ELIGIBILITY = "product_coupon_eligibility"
    COUPON_APPLICABLE_PRODUCTS = "coupon_applicable_products"
    STACKING = "stacking"
    POLICY_INFO = "policy_info"


class CouponQueryGateDecision(BaseModel):
    intent: CouponQueryIntent = Field(description="Coupon query intent enum.")
    confidence: float = Field(ge=0, le=1, description="Confidence from 0 to 1.")
    product_name: str | None = Field(description="Mentioned product or pattern name, or null.")
    coupon_hint: str | None = Field(description="Mentioned coupon name, discount rate, or hint, or null.")
    reason: str = Field(description="Short English reason for trace/debug only.")

    @property
    def is_actionable(self) -> bool:
        return self.intent not in {CouponQueryIntent.NONE, CouponQueryIntent.POLICY_INFO} and self.confidence >= 0.55


_COUPON_GATE_TRIGGER_RE = re.compile(r"쿠폰|할인권|혜택|할인\s*상품|적용\s*상품", re.IGNORECASE)
_DEFAULT_BENEFIT_RE = re.compile(
    r"지금\s*받을\s*수\s*있는\s*혜택|현재\s*받을\s*수\s*있는\s*혜택|"
    r"진행\s*중인\s*(?:이벤트|기획전|행사|혜택)|이벤트\s*/\s*기획전|이벤트랑\s*기획전",
    re.IGNORECASE,
)


def should_consider_coupon_gate(user_text: str | None) -> bool:
    text = user_text or ""
    if _DEFAULT_BENEFIT_RE.search(text):
        return False
    return bool(_COUPON_GATE_TRIGGER_RE.search(text))


@lru_cache(maxsize=1)
def _coupon_gate_model():
    llm = ChatLiteLLM(
        api_base=settings.AI_GATEWAY_BASE_URL,
        api_key=settings.AI_GATEWAY_API_KEY,
        model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL_MINI}",
        streaming=False,
        request_timeout=8,
    )
    return llm.with_structured_output(CouponQueryGateDecision)


def decide_coupon_query_gate(
    *,
    user_text: str,
    recent_context: str = "",
    model=None,
) -> CouponQueryGateDecision:
    """Classify a coupon-related user turn into a structured intent."""
    if not should_consider_coupon_gate(user_text):
        return CouponQueryGateDecision(
            intent=CouponQueryIntent.NONE,
            confidence=1.0,
            product_name=None,
            coupon_hint=None,
            reason="No coupon-related trigger.",
        )

    prompt = dedent(f"""
    You are a coupon intent gate for a Korean tire-commerce chatbot.
    Classify the CURRENT user message into exactly one enum.

    Important:
    - Decide intent only. Do not answer the user.
    - Product mentions such as "키너지 EX", "Kinergy EX", "다이나프로 HPX" are product/pattern names.
    - Coupon mentions such as "30%", "16% 할인", "패밀리 쿠폰", "생일 쿠폰" are coupon hints.
    - If the user asks what coupons they have, choose owned_coupon_lookup even if a product is mentioned.
    - If the user asks which owned coupon gives the biggest discount among all owned coupons (no specific product mentioned), choose best_discount.
    - If the user asks what coupons can be used for a product/pattern, or asks how to buy a specific product most cheaply using coupons, choose product_coupon_eligibility.
    - If a product/pattern name is mentioned alongside a coupon cheapest/biggest-discount request, choose product_coupon_eligibility, not best_discount.
    - If the user asks what products a specific coupon/discount coupon applies to, choose coupon_applicable_products.
    - If the user asks how to get/download/issue a coupon, choose issue_howto.
    - If the user asks whether multiple coupons/deals/card benefits can be used together, choose stacking.
    - If it is a general policy/explanation question, choose policy_info.
    - If not coupon-related, choose none.

    Current user message:
    {user_text}

    Recent context:
    {recent_context[-1200:]}
    """).strip()

    try:
        gate_model = model or _coupon_gate_model()
        decision = gate_model.invoke(prompt)
        if isinstance(decision, CouponQueryGateDecision):
            return decision
        return CouponQueryGateDecision.model_validate(decision)
    except Exception as exc:
        logger.warning("[COUPON_QUERY_GATE] LLM decision failed: %s", exc)
        return CouponQueryGateDecision(
            intent=CouponQueryIntent.NONE,
            confidence=0.0,
            product_name=None,
            coupon_hint=None,
            reason="LLM gate failed; falling back to existing policy.",
        )
