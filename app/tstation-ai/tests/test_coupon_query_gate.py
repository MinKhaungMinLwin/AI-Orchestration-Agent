from services.tstation.policies.coupon_query_gate import (
    CouponQueryGateDecision,
    CouponQueryIntent,
    decide_coupon_query_gate,
    should_consider_coupon_gate,
)


class _FakeGateModel:
    def __init__(self, decision: CouponQueryGateDecision):
        self.decision = decision

    def invoke(self, _prompt: str):
        return self.decision


def test_coupon_gate_is_not_considered_without_coupon_terms() -> None:
    assert should_consider_coupon_gate("타이어 추천") is False


def test_coupon_gate_prefers_product_coupon_when_product_purchase_context_is_present() -> None:
    decision = decide_coupon_query_gate(
        user_text="키너지 EX 구매하고 싶은데 나 할인쿠폰 뭐 갖고 있어?",
        model=_FakeGateModel(
            CouponQueryGateDecision(
                intent=CouponQueryIntent.OWNED_COUPON_LOOKUP,
                confidence=0.93,
                product_name="키너지 EX",
                coupon_hint=None,
                reason="User asks which owned coupons they have.",
            )
        ),
    )

    assert decision.intent == CouponQueryIntent.PRODUCT_COUPON_ELIGIBILITY
    assert decision.product_name is None
    assert decision.coupon_hint == "쿠폰"


def test_coupon_gate_accepts_product_coupon_eligibility() -> None:
    decision = decide_coupon_query_gate(
        user_text="kinergy EX에 쓸 수 있는 쿠폰 뭐 있어?",
        model=_FakeGateModel(
            CouponQueryGateDecision(
                intent=CouponQueryIntent.PRODUCT_COUPON_ELIGIBILITY,
                confidence=0.91,
                product_name="Kinergy EX",
                coupon_hint=None,
                reason="User asks coupons usable for a product.",
            )
        ),
    )

    assert decision.intent == CouponQueryIntent.PRODUCT_COUPON_ELIGIBILITY
    assert decision.product_name is None
    assert decision.coupon_hint == "쿠폰"


def test_coupon_gate_accepts_coupon_applicable_products() -> None:
    decision = decide_coupon_query_gate(
        user_text="16% 할인쿠폰 적용 가능 상품 알려줘",
        model=_FakeGateModel(
            CouponQueryGateDecision(
                intent=CouponQueryIntent.COUPON_APPLICABLE_PRODUCTS,
                confidence=0.9,
                product_name=None,
                coupon_hint="16%",
                reason="User asks products applicable to a discount coupon.",
            )
        ),
    )

    assert decision.intent == CouponQueryIntent.COUPON_APPLICABLE_PRODUCTS
    assert decision.coupon_hint == "16%"


def test_coupon_gate_routes_offline_usage_policy_before_partner_policy() -> None:
    decision = decide_coupon_query_gate(
        user_text="다운받은 쿠폰 현장 결제할 때도 쓸 수 있어?",
        model=_FakeGateModel(
            CouponQueryGateDecision(
                intent=CouponQueryIntent.PARTNER_MEMBER_COUPON_POLICY,
                confidence=0.9,
                product_name=None,
                coupon_hint="partner_member",
                reason="Incorrect partner-only route.",
            )
        ),
    )

    assert decision.intent == CouponQueryIntent.COUPON_USAGE_POLICY
    assert decision.coupon_hint == "쿠폰"


def test_coupon_gate_routes_coupon_registration_policy_deterministically() -> None:
    decision = decide_coupon_query_gate(
        user_text="쿠폰 번호 어디에 등록해?",
        model=_FakeGateModel(
            CouponQueryGateDecision(
                intent=CouponQueryIntent.ISSUE_HOWTO,
                confidence=0.88,
                product_name=None,
                coupon_hint="쿠폰",
                reason="Generic how-to route.",
            )
        ),
    )

    assert decision.intent == CouponQueryIntent.COUPON_REGISTRATION_POLICY
    assert decision.coupon_hint == "쿠폰"
