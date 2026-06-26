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
    COUPON_USAGE_POLICY = "coupon_usage_policy"
    COUPON_REGISTRATION_POLICY = "coupon_registration_policy"
    SIGNUP_COUPON_GUIDANCE = "signup_coupon_guidance"
    PARTNER_MEMBER_COUPON_POLICY = "partner_member_coupon_policy"
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
        return self.intent not in {
            CouponQueryIntent.NONE,
            CouponQueryIntent.ISSUE_HOWTO,
            CouponQueryIntent.COUPON_USAGE_POLICY,
            CouponQueryIntent.COUPON_REGISTRATION_POLICY,
            CouponQueryIntent.SIGNUP_COUPON_GUIDANCE,
            CouponQueryIntent.PARTNER_MEMBER_COUPON_POLICY,
            CouponQueryIntent.POLICY_INFO,
            CouponQueryIntent.STACKING,
        } and self.confidence >= 0.55


_COUPON_GATE_TRIGGER_RE = re.compile(r"쿠폰|할인\s*쿠폰|할인권|혜택|할인\s*상품|적용\s*상품", re.IGNORECASE)
_DEFAULT_BENEFIT_RE = re.compile(
    r"지금\s*받을\s*수\s*있는\s*혜택|현재\s*받을\s*수\s*있는\s*혜택|"
    r"진행\s*중인\s*(?:이벤트|기획전|행사|혜택)|이벤트\s*/\s*기획전|이벤트랑\s*기획전",
    re.IGNORECASE,
)
_PRICE_OR_BENEFIT_ALERT_RE = re.compile(
    r"(?:가격|금액|최종가|혜택|쿠폰|이벤트|프로모션|할인|저렴|싸)"
    r".{0,40}(?:알림|알람|문자|SMS|sms|알려|연락|통지)|"
    r"(?:알림|알람|문자|SMS|sms|알려|연락|통지)"
    r".{0,40}(?:가격|금액|최종가|혜택|쿠폰|이벤트|프로모션|할인|저렴|싸)|"
    r"(?:가격|금액|최종가).{0,20}(?:떨어지|내려가|낮아지)|"
    r"(?:저렴해지|싸지).{0,30}(?:알림|알람|알려|문자|SMS|sms)",
    re.IGNORECASE,
)
_COUPON_APPLICABLE_PRODUCT_ANCHOR_RE = re.compile(
    r"적용\s*가능|적용가능|대상\s*상품|적용\s*상품|사용\s*가능|사용가능",
    re.IGNORECASE,
)
_COUPON_ISSUE_HOWTO_RE = re.compile(
    r"쿠폰.{0,24}(?:선물\s*받|발급|다운로드|받는?\s*방법|어디서\s*받|어디\s*서\s*받)|"
    r"(?:선물\s*받|발급|다운로드|받는?\s*방법|어디서\s*받|어디\s*서\s*받).{0,24}쿠폰",
    re.IGNORECASE,
)
_COUPON_REGISTRATION_POLICY_RE = re.compile(
    r"쿠폰.{0,24}(?:번호|등록|입력|코드|등록\s*방법|어디서\s*등록)|"
    r"(?:번호|등록|입력|코드|등록\s*방법|어디서\s*등록).{0,24}쿠폰",
    re.IGNORECASE,
)
_COUPON_USAGE_POLICY_RE = re.compile(
    r"쿠폰.{0,32}(?:현장\s*결제|매장\s*결제|오프라인|온라인\s*주문\s*없이|온라인\s*전용|매장\s*(?:사용|결제)|"
    r"사용처|어디\s*(?:서|에)|쓸\s*수\s*있|사용\s*가능|현장(?:에서도)?|매장에서)|"
    r"(?:현장\s*결제|매장\s*결제|오프라인|온라인\s*주문\s*없이|온라인\s*전용|매장\s*(?:사용|결제)|"
    r"사용처|어디\s*(?:서|에)|쓸\s*수\s*있|사용\s*가능|현장(?:에서도)?|매장에서).{0,32}쿠폰",
    re.IGNORECASE,
)
_COUPON_STACKING_HOWTO_RE = re.compile(r"쿠폰.{0,24}(?:중복|같이|함께|동시)|(?:중복|같이|함께|동시).{0,24}쿠폰", re.IGNORECASE)
_OWNED_COUPON_LOOKUP_RE = re.compile(r"(?:내|나의|보유|가지고\s*있는|있는).{0,16}쿠폰|쿠폰.{0,16}(?:뭐\s*있|보여|조회|확인)", re.IGNORECASE)
_PRODUCT_COUPON_ELIGIBILITY_RE = re.compile(
    r"(?:벤투스|ventus|다이나프로|dynapro|키너지|kinergy|아이온|ion|옵티모|optimo|미쉐린|michelin|cc2)"
    r".{0,30}(?:쿠폰|할인권).{0,24}(?:있|돼|되|쓸|사용|적용)|"
    r"(?:쿠폰|할인권).{0,24}(?:벤투스|ventus|다이나프로|dynapro|키너지|kinergy|아이온|ion|옵티모|optimo|미쉐린|michelin|cc2)",
    re.IGNORECASE,
)
_COUPON_APPLICABLE_PRODUCTS_RE = re.compile(
    r"(?:이|그|해당)?\s*쿠폰.{0,24}(?:적용\s*상품|대상\s*상품|쓸\s*수\s*있는\s*상품|사용\s*가능\s*상품)|"
    r"(?:적용\s*상품|대상\s*상품|쓸\s*수\s*있는\s*상품|사용\s*가능\s*상품).{0,24}쿠폰",
    re.IGNORECASE,
)
_PARTNER_MEMBER_COUPON_POLICY_RE = re.compile(
    r"제휴\s*(?:회원|사|몰|전용)|복지몰|임직원|제휴사|제휴회원|제휴\s*쿠폰|제휴\s*혜택",
    re.IGNORECASE,
)
_SIGNUP_COUPON_GUIDANCE_RE = re.compile(
    r"회원\s*가입|신규\s*회원|가입(?:하면|시)?|웰컴\s*쿠폰|가입\s*쿠폰|신규\s*가입|첫\s*가입",
    re.IGNORECASE,
)


def should_consider_coupon_gate(user_text: str | None) -> bool:
    text = user_text or ""
    if _DEFAULT_BENEFIT_RE.search(text):
        return False
    if (
        _COUPON_ISSUE_HOWTO_RE.search(text)
        or _COUPON_REGISTRATION_POLICY_RE.search(text)
        or _COUPON_USAGE_POLICY_RE.search(text)
        or _COUPON_STACKING_HOWTO_RE.search(text)
    ):
        return True
    if _PRICE_OR_BENEFIT_ALERT_RE.search(text) and not _COUPON_APPLICABLE_PRODUCT_ANCHOR_RE.search(text):
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
    text = user_text or ""
    if _COUPON_STACKING_HOWTO_RE.search(text):
        return CouponQueryGateDecision(
            intent=CouponQueryIntent.STACKING,
            confidence=0.9,
            product_name=None,
            coupon_hint=None,
            reason="Deterministic coupon stacking policy/how-to query.",
        )
    if _COUPON_REGISTRATION_POLICY_RE.search(text):
        return CouponQueryGateDecision(
            intent=CouponQueryIntent.COUPON_REGISTRATION_POLICY,
            confidence=0.92,
            product_name=None,
            coupon_hint="쿠폰",
            reason="Deterministic coupon registration/input policy query.",
        )
    if _COUPON_USAGE_POLICY_RE.search(text) and not _PARTNER_MEMBER_COUPON_POLICY_RE.search(text):
        return CouponQueryGateDecision(
            intent=CouponQueryIntent.COUPON_USAGE_POLICY,
            confidence=0.92,
            product_name=None,
            coupon_hint="쿠폰",
            reason="Deterministic offline/online coupon usage policy query.",
        )
    if _COUPON_ISSUE_HOWTO_RE.search(text):
        return CouponQueryGateDecision(
            intent=CouponQueryIntent.ISSUE_HOWTO,
            confidence=0.92,
            product_name=None,
            coupon_hint="쿠폰",
            reason="Deterministic coupon issue/register/use how-to query.",
        )
    if _COUPON_APPLICABLE_PRODUCTS_RE.search(text):
        return CouponQueryGateDecision(
            intent=CouponQueryIntent.COUPON_APPLICABLE_PRODUCTS,
            confidence=0.88,
            product_name=None,
            coupon_hint="쿠폰",
            reason="Deterministic coupon applicable products query.",
        )
    if _PRODUCT_COUPON_ELIGIBILITY_RE.search(text):
        return CouponQueryGateDecision(
            intent=CouponQueryIntent.PRODUCT_COUPON_ELIGIBILITY,
            confidence=0.88,
            product_name=None,
            coupon_hint="쿠폰",
            reason="Deterministic product coupon eligibility query.",
        )
    if _SIGNUP_COUPON_GUIDANCE_RE.search(text) and _COUPON_GATE_TRIGGER_RE.search(text):
        return CouponQueryGateDecision(
            intent=CouponQueryIntent.SIGNUP_COUPON_GUIDANCE,
            confidence=0.92,
            product_name=None,
            coupon_hint="signup_coupon",
            reason="Deterministic signup coupon guidance query.",
        )
    if _PARTNER_MEMBER_COUPON_POLICY_RE.search(text):
        return CouponQueryGateDecision(
            intent=CouponQueryIntent.PARTNER_MEMBER_COUPON_POLICY,
            confidence=0.92,
            product_name=None,
            coupon_hint="partner_member",
            reason="Deterministic partner-member coupon policy query.",
        )
    if _OWNED_COUPON_LOOKUP_RE.search(text):
        return CouponQueryGateDecision(
            intent=CouponQueryIntent.OWNED_COUPON_LOOKUP,
            confidence=0.88,
            product_name=None,
            coupon_hint=None,
            reason="Deterministic owned coupon lookup query.",
        )

    prompt = dedent(f"""
    You are a coupon intent gate for a Korean tire-commerce chatbot.
    Classify the CURRENT user message into exactly one enum.

    Important:
    - Decide intent only. Do not answer the user.
    - Product mentions such as "키너지 EX", "Kinergy EX", "다이나프로 HPX" are product/pattern names.
    - Coupon mentions such as "30%", "16% 할인", "패밀리 쿠폰", "생일 쿠폰" are coupon hints.
    - If the user asks what coupons they have, choose owned_coupon_lookup even if a product is mentioned.
    - If the user asks which owned coupons expire this month/soon or asks owned coupon validity period,
      choose owned_coupon_lookup, not policy_info.
    - If the user asks which owned coupon gives the biggest discount among all owned coupons (no specific product mentioned), choose best_discount.
    - If the user asks what coupons can be used for a product/pattern, or asks how to buy a specific product most cheaply using coupons, choose product_coupon_eligibility.
    - If a product/pattern name is mentioned alongside a coupon cheapest/biggest-discount request, choose product_coupon_eligibility, not best_discount.
    - If the user asks what products a specific coupon/discount coupon applies to, choose coupon_applicable_products.
    - If the user asks how to get/download/issue a coupon, choose issue_howto.
    - If the user asks where to register/input a coupon number/code, choose coupon_registration_policy.
    - If the user asks whether a downloaded/online coupon can be used for store payment, offline payment, or without an online order, choose coupon_usage_policy.
    - If the user asks whether multiple coupons/deals/card benefits can be used together, choose stacking.
    - If the user asks about signup-only / new-member / welcome coupon guidance, choose signup_coupon_guidance.
    - If the user asks about partner-member-only / affiliate-only / welfare-mall / employee-only coupons or benefits, choose partner_member_coupon_policy.
    - coupon_usage_policy is general coupon usage/channel policy, not partner_member_coupon_policy, not owned_coupon_lookup, and not product_coupon_eligibility.
    - signup_coupon_guidance is general signup/new-member coupon guidance, not partner_member_coupon_policy and not owned_coupon_lookup.
    - partner_member_coupon_policy is policy/access guidance, not owned_coupon_lookup, and must not assume the user already has the coupon.
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
