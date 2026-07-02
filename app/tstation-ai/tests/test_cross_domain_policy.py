import pytest

from services.tstation.policies.cross_domain_policy import (
    agent_domain_values_for_initial_route,
    agent_domain_values_for_plan,
    is_safe_service_tire_recommendation_request,
    is_warranty_claim_signal,
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


def test_regional_product_price_policy_routes_to_support() -> None:
    plan = plan_cross_domain_turn("벤투스 에어 S 상품 제주도에서 사는거랑, 서울에서 사는거랑 가격 똑같을까?")

    assert plan.is_cross_domain is False
    assert plan.primary_domain == PolicyDomain.SUPPORT
    assert agent_domain_values_for_plan(plan) == ["support"]
    assert plan.subtasks[0].intent == "price_policy_faq"


@pytest.mark.parametrize(
    "text",
    [
        "ventus air S 5만키로 탈 수 있다더니 벌써 다 닳은거같은데 무료교체해줘",
        "벤투스 에어S 왜 이렇게 빨리 닳아? 보증 대상 아냐?",
        "벤투스 S2 AS 워런티 돼?",
    ],
)
def test_warranty_claim_or_product_warranty_routes_to_support(text: str) -> None:
    plan = plan_cross_domain_turn(text)

    assert is_warranty_claim_signal(text)
    assert plan.is_cross_domain is False
    assert plan.primary_domain == PolicyDomain.SUPPORT
    assert agent_domain_values_for_plan(plan) == ["support"]
    assert plan.subtasks[0].intent == "warranty_claim"


@pytest.mark.parametrize(
    "text",
    [
        "장착하러 매장 왔는데 왜 타이어마다 dot 가 달라? 바꿔줄수 있는거야?",
        "타이어마다 DOT가 다른데 교환 가능한가요?",
        "제조일자가 6개월 전 거야. 새 걸로 바꿔줘",
    ],
)
def test_tire_manufacture_date_policy_preempts_generic_exchange_remedy(text: str) -> None:
    plan = plan_cross_domain_turn(text)

    assert plan.is_cross_domain is False
    assert plan.primary_domain == PolicyDomain.SUPPORT
    assert agent_domain_values_for_plan(plan) == ["support"]
    assert plan.subtasks[0].intent == "tire_manufacture_date_policy"
    assert plan.subtasks[0].intent != "warranty_claim"


def test_tire_quality_warranty_anchor_still_routes_to_warranty_claim() -> None:
    text = "벤투스 에어S 측면이 부풀었는데 품질보증 대상이야?"
    plan = plan_cross_domain_turn(text)

    assert is_warranty_claim_signal(text)
    assert plan.is_cross_domain is False
    assert plan.primary_domain == PolicyDomain.SUPPORT
    assert agent_domain_values_for_plan(plan) == ["support"]
    assert plan.subtasks[0].intent == "warranty_claim"


def test_product_description_does_not_become_warranty_claim() -> None:
    text = "ventus air S 설명해줘"
    plan = plan_cross_domain_turn(text)

    assert not is_warranty_claim_signal(text)
    assert plan.primary_domain == PolicyDomain.DISCOVERY
    assert agent_domain_values_for_plan(plan) == ["discovery"]


def test_mileage_recommendation_does_not_become_warranty_claim() -> None:
    text = "마일리지 좋은 타이어 추천해줘"
    plan = plan_cross_domain_turn(text)

    assert not is_warranty_claim_signal(text)
    assert plan.primary_domain == PolicyDomain.UNKNOWN


def test_safe_service_target_tire_question_routes_to_discovery_recommendation() -> None:
    text = "안심서비스 가능한 타이어는?"
    plan = plan_cross_domain_turn(text)

    assert is_safe_service_tire_recommendation_request(text)
    assert plan.primary_domain == PolicyDomain.DISCOVERY
    assert agent_domain_values_for_plan(plan) == ["discovery"]
    assert plan.subtasks[0].intent == "safe_service_tire_recommendation"


def test_safe_service_owned_or_compensation_questions_stay_support() -> None:
    for text in (
        "나 안심서비스 가입했던것 같은데 확인해줘",
        "안심서비스 보상 조건이 어떻게 돼?",
        "안심서비스 가입 방법 알려줘",
    ):
        plan = plan_cross_domain_turn(text)

        assert not is_safe_service_tire_recommendation_request(text)
        assert plan.primary_domain == PolicyDomain.SUPPORT


def test_sized_regional_product_price_lookup_stays_transaction_flow() -> None:
    plan = plan_cross_domain_turn("벤투스 에어S 245/45R18 제주에서 장착 가격 알려줘")

    assert agent_domain_values_for_plan(plan) == ["discovery", "transaction"]
    assert plan.subtasks[1].intent == "price_or_coupon_check"


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


@pytest.mark.parametrize(
    "text",
    [
        "판교점에서 dynapro hpx 2개 구매하고싶어",
        "판교점에서 오늘서비스로 dynapro hpx 2개 구매하고싶어",
        "서초점에서 키너지 ST AS 4개 예약해줘",
    ],
)
def test_product_store_purchase_without_size_starts_discovery_only(text: str) -> None:
    plan = plan_cross_domain_turn(text)

    assert agent_domain_values_for_plan(plan) == ["discovery", "transaction"]
    assert agent_domain_values_for_initial_route(plan, known_slots={}) == ["discovery"]
    assert [task.intent for task in plan.subtasks] == ["resolve_or_describe_product", "stock_store_or_reservation"]
    assert "goods_no" in plan.subtasks[1].required_slots
    assert "tire_size" in plan.subtasks[1].required_slots


def test_named_store_stock_request_preserves_location_after_product_resolution_first() -> None:
    plan = plan_cross_domain_turn("판교점에 ion evo as 재고 있어?")

    assert agent_domain_values_for_initial_route(plan, known_slots={}) == ["discovery"]
    assert [task.intent for task in plan.subtasks] == ["resolve_or_describe_product", "stock_store_or_reservation"]
    assert "location" not in plan.subtasks[1].required_slots
    assert "tire_size" in plan.subtasks[1].required_slots
    assert "quantity" in plan.subtasks[1].required_slots


def test_plain_store_search_does_not_inherit_stale_product_stock_context() -> None:
    plan = plan_cross_domain_turn(
        "판교지역 매장 찾아줘",
        known_slots={
            "goods_no": "G000000317729",
            "tire_size": "235/35R20",
            "quantity": 4,
            "region": "판교",
        },
    )

    assert plan.is_cross_domain is False
    assert plan.primary_domain == PolicyDomain.TRANSACTION
    assert agent_domain_values_for_plan(plan) == ["transaction"]
    assert plan.subtasks[0].intent == "store_search"


def test_support_question_is_not_promoted_to_transaction_by_stale_product_context() -> None:
    plan = plan_cross_domain_turn(
        "TPMS 경고등 뜨는데 공기압 점검 무료야?",
        known_slots={
            "goods_no": "G000000317729",
            "tire_size": "235/35R20",
            "region": "판교",
        },
    )

    assert plan.primary_domain == PolicyDomain.SUPPORT
    assert agent_domain_values_for_plan(plan) == ["support"]
