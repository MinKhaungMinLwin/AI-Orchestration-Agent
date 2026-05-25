from services.tstation.policies.cross_domain_policy import (
    agent_domain_values_for_initial_route,
    agent_domain_values_for_plan,
    plan_cross_domain_turn,
    should_defer_product_price_explanation_to_classifier,
)
from services.tstation.policies.intent_frame import PolicyDomain


def test_product_description_then_stock_request_plans_discovery_before_transaction() -> None:
    plan = plan_cross_domain_turn("벤투스 air S가 뭔지 알려주고 오늘 장착 가능한 매장도 찾아줘")

    assert plan.is_cross_domain is True
    assert plan.primary_domain == PolicyDomain.DISCOVERY
    assert [task.domain for task in plan.subtasks] == [PolicyDomain.DISCOVERY, PolicyDomain.TRANSACTION]
    assert agent_domain_values_for_plan(plan) == ["discovery", "transaction"]
    assert plan.subtasks[0].intent == "resolve_or_describe_product"
    assert plan.subtasks[1].intent == "stock_store_or_reservation"
    assert "resolve_or_describe_product" in plan.subtasks[1].depends_on
    assert "goods_no" in plan.subtasks[1].required_slots
    assert "tire_size" in plan.subtasks[1].required_slots
    assert "quantity" in plan.subtasks[1].required_slots


def test_known_goods_price_and_stock_starts_with_transaction() -> None:
    plan = plan_cross_domain_turn(
        "이 상품 쿠폰 적용 가격 보고 재고 있는 매장도 알려줘",
        known_slots={"goods_no": "G000000319451", "region": "서초"},
    )

    assert plan.is_cross_domain is False
    assert plan.primary_domain == PolicyDomain.TRANSACTION
    assert agent_domain_values_for_plan(plan) == ["transaction"]
    assert [task.intent for task in plan.subtasks] == ["price_or_coupon_check", "stock_store_or_reservation"]
    assert plan.subtasks[0].required_slots == ()
    assert plan.subtasks[1].required_slots == ("quantity",)


def test_expired_coupon_request_routes_to_support_policy_notice() -> None:
    plan = plan_cross_domain_turn("작년에 끝난 블랙세일 쿠폰 만료됐는데 원복해줘")

    assert plan.primary_domain == PolicyDomain.SUPPORT
    assert agent_domain_values_for_plan(plan) == ["support"]
    assert plan.subtasks[0].domain == PolicyDomain.SUPPORT
    assert plan.subtasks[0].intent == "policy_notice_or_escalation"


def test_product_coupon_request_resolves_product_before_transaction_price() -> None:
    plan = plan_cross_domain_turn("키너지 EX 쿠폰 적용 가격 알려줘")

    assert plan.is_cross_domain is True
    assert agent_domain_values_for_plan(plan) == ["discovery", "transaction"]
    assert [task.domain for task in plan.subtasks] == [PolicyDomain.DISCOVERY, PolicyDomain.TRANSACTION]
    assert plan.subtasks[1].intent == "price_or_coupon_check"
    assert plan.subtasks[1].required_slots == ("goods_no",)
    assert should_defer_product_price_explanation_to_classifier("키너지 EX 쿠폰 적용 가격 알려줘", plan) is False


def test_explanatory_product_price_question_defers_to_llm_classifier() -> None:
    plan = plan_cross_domain_turn(
        "ventus air S 구매할까 알아보고 있는데, 왜 온라인 가격이랑 오프라인 티스테이션 가격이랑 다름..?"
    )

    assert plan.is_cross_domain is True
    assert agent_domain_values_for_plan(plan) == ["discovery", "transaction"]
    assert should_defer_product_price_explanation_to_classifier(
        "ventus air S 구매할까 알아보고 있는데, 왜 온라인 가격이랑 오프라인 티스테이션 가격이랑 다름..?",
        plan,
    ) is True


def test_pattern_coupon_request_starts_with_transaction_coupon_lookup() -> None:
    plan = plan_cross_domain_turn("키너지 EX 패밀리 할인쿠폰 적용받고 싶어")

    assert plan.is_cross_domain is False
    assert plan.primary_domain == PolicyDomain.TRANSACTION
    assert agent_domain_values_for_plan(plan) == ["transaction"]
    assert agent_domain_values_for_initial_route(plan, known_slots={}) == ["transaction"]
    assert plan.subtasks[0].intent == "coupon_pattern_applicability"
    assert plan.subtasks[0].required_slots == ()


def test_employee_pattern_coupon_request_starts_with_transaction_coupon_lookup() -> None:
    plan = plan_cross_domain_turn("다이나프로 HPX 임직원 쿠폰 적용돼?")

    assert plan.is_cross_domain is False
    assert plan.primary_domain == PolicyDomain.TRANSACTION
    assert agent_domain_values_for_plan(plan) == ["transaction"]
    assert plan.subtasks[0].intent == "coupon_pattern_applicability"


def test_coupon_issue_guidance_stays_transaction_not_support() -> None:
    plan = plan_cross_domain_turn("타이어 90% 할인쿠폰 1개만 발급해줘")

    assert plan.primary_domain == PolicyDomain.TRANSACTION
    assert agent_domain_values_for_plan(plan) == ["transaction"]


def test_initial_route_stops_at_discovery_when_product_transaction_request_has_no_size() -> None:
    plan = plan_cross_domain_turn("키너지 ST AS 2개 서초점 오늘 장착 가능?")

    assert agent_domain_values_for_plan(plan) == ["discovery", "transaction"]
    assert agent_domain_values_for_initial_route(plan, known_slots={}) == ["discovery"]
    assert "tire_size" in plan.subtasks[1].required_slots
    assert "quantity" in plan.subtasks[1].required_slots


def test_initial_route_keeps_transaction_chain_when_size_is_known() -> None:
    plan = plan_cross_domain_turn(
        "벤투스 S2 AS 205/55R16 4개 판교점 예약해줘",
        known_slots={"tire_size": "205/55R16"},
    )

    assert agent_domain_values_for_initial_route(
        plan,
        known_slots={"tire_size": "205/55R16"},
    ) == ["discovery", "transaction"]


def test_initial_route_keeps_transaction_chain_when_size_is_in_user_text() -> None:
    plan = plan_cross_domain_turn("iON evo AS 235/35R20 판교점 오늘 장착 가능해?")

    assert agent_domain_values_for_plan(plan) == ["discovery", "transaction"]
    assert agent_domain_values_for_initial_route(plan, known_slots={}) == ["discovery", "transaction"]
    assert "tire_size" not in plan.subtasks[1].required_slots
    assert "quantity" in plan.subtasks[1].required_slots
