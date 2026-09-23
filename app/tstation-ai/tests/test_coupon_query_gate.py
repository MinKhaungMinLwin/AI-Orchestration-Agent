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


def test_coupon_gate_does_not_turn_applied_order_coupon_question_into_owned_lookup() -> None:
    for user_text in (
        "적용된 쿠폰이 뭐야?",
        "어떤 쿠폰이 적용됐어?",
        "할인 적용 내역 알려줘",
    ):
        decision = decide_coupon_query_gate(
            user_text=user_text,
            model=_FakeGateModel(
                CouponQueryGateDecision(
                    intent=CouponQueryIntent.OWNED_COUPON_LOOKUP,
                    confidence=0.92,
                    product_name=None,
                    coupon_hint=None,
                    reason="Incorrect owned coupon lookup route.",
                )
            ),
        )

        assert decision.intent == CouponQueryIntent.NONE


def test_coupon_gate_still_allows_plain_owned_coupon_lookup() -> None:
    decision = decide_coupon_query_gate(
        user_text="내 보유 쿠폰 뭐 있어?",
        model=_FakeGateModel(
            CouponQueryGateDecision(
                intent=CouponQueryIntent.PRODUCT_COUPON_ELIGIBILITY,
                confidence=0.9,
                product_name=None,
                coupon_hint="쿠폰",
                reason="Incorrect product route.",
            )
        ),
    )

    assert decision.intent == CouponQueryIntent.OWNED_COUPON_LOOKUP


def test_coupon_gate_routes_product_name_usable_coupon_before_usage_policy() -> None:
    for user_text in (
        "키너지 ex에 쓸 수 있는 쿠폰은?",
        "키너지 EX에 사용 가능한 쿠폰 있어?",
        "벤투스 S2 AS에 적용 가능한 쿠폰 알려줘",
    ):
        decision = decide_coupon_query_gate(
            user_text=user_text,
            model=_FakeGateModel(
                CouponQueryGateDecision(
                    intent=CouponQueryIntent.COUPON_USAGE_POLICY,
                    confidence=0.92,
                    product_name=None,
                    coupon_hint="쿠폰",
                    reason="Incorrect generic usage policy route.",
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
