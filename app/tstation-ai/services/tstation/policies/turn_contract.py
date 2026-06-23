"""Per-turn execution contract for policy shadow logging and narrow guards."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from services.tstation.policies.cross_domain_policy import CrossDomainPlan
from services.tstation.policies.intent_frame import IntentFrame
from services.tstation.policies.response_decision import ResponseDecision, ToolPlan


_HIGH_RISK_INTENTS = frozenset({
    "price_or_coupon_check",
    "price_coupon_summary",
    "product_coupon_eligibility",
    "coupon_applicable_products",
    "coupon_pattern_applicability",
    "stock_store_search",
    "store_schedule",
    "quick_order_reservation",
    "quick_order_execute",
    "inventory_availability",
    "recent_product_set_size_availability",
})
_HIGH_RISK_DOMAINS = frozenset({"transaction"})
_REQUIRED_SLOT_BLOCK_TEMPLATES = frozenset({
    "datepick",
    "preOrder",
    "orderComplete",
    "billProduct",
    "billService",
})
_FORBIDDEN_BEHAVIOR_TEMPLATE_BLOCKS = {
    "datepick_for_unavailable_stock": frozenset({"datepick", "preOrder"}),
    "datepick_for_pure_inventory_flow": frozenset({"datepick", "preOrder"}),
    "preorder_for_pure_inventory_flow": frozenset({"preOrder", "orderComplete"}),
    "preorder": frozenset({"preOrder", "orderComplete"}),
    "preorder_with_null_required_fields": frozenset({"preOrder", "orderComplete"}),
    "order_summary_with_null_required_fields": frozenset({"preOrder", "orderComplete"}),
    "product_card_without_size": frozenset({"product"}),
    "price_without_size": frozenset({"product", "cheapestProduct", "billProduct"}),
    "answer_without_price_tool": frozenset({"product", "cheapestProduct", "billProduct"}),
    "assert_price_without_tool_result": frozenset({"preOrder", "billProduct", "cheapestProduct"}),
    "assert_coupon_without_tool_result": frozenset({"voucher", "preOrder", "billProduct"}),
    "order_complete_on_tool_error": frozenset({"orderComplete"}),
    "datepick_on_tool_error": frozenset({"datepick", "preOrder"}),
    "assert_success_without_tool_result": frozenset({"datepick", "preOrder", "orderComplete", "billProduct"}),
}
_DISCOVERY_FIRST_LEG_BLOCK_RESPONSE_SHAPES = frozenset({
    "product_attribute_summary",
    "product_search_summary",
    "technology_explanation_then_unsized_recommendation_summary",
    "safe_service_explanation_then_unsized_recommendation_summary",
    "unsized_recommendation_summary",
    "neutral_product_description",
    "discovery_summary",
})
_DISCOVERY_FIRST_LEG_BLOCK_SOURCES = frozenset({
    "code_product_attribute_resolver",
    "code_product_description",
    "discovery_policy",
})
_DISCOVERY_PRODUCT_SOURCE_TOOLS = frozenset({
    "search_product_tool",
    "get_products_recommendations_tool",
    "get_best_selling_products_tool",
})
_WARNING_CONTRACT_VIOLATION_TYPES = frozenset({
    "requested_product_attribute_contract_drift",
    "compare_metric_metadata_drift",
    "compare_metric_contract_drift",
    "compare_metric_row_missing",
    "forbidden_discovery_first_leg_response",
})
_PRICE_OR_COUPON_RE = re.compile(r"가격|얼마|할인가|쿠폰|할인|혜택", re.IGNORECASE)
_REFERENCE_PURCHASE_RE = re.compile(r"(?:그거|그\s*상품|이거|이\s*상품).{0,20}(구매|주문|결제|살래|살게|사고)", re.IGNORECASE)
_DISCOVERY_NO_RESULT_RE = re.compile(r"찾을\s*수\s*없|확인되지\s*않|검색되지\s*않|없어요", re.IGNORECASE)
_REFERENCE_SIGNAL_RE = re.compile(
    r"그거|이거|요거|저거|"
    r"그\s*상품|이\s*상품|해당\s*상품|"
    r"그\s*매장|이\s*매장|해당\s*매장|거기|여기|저기|"
    r"첫\s*번째|1\s*번|두\s*번째|2\s*번|"
    r"방금\s*거|아까\s*거|최근\s*거|해당\s*건",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TurnContract:
    """Stable policy snapshot for one user turn."""

    domain: str
    intent: str
    sub_intent: str | None = None
    known_slots: Mapping[str, Any] = field(default_factory=dict)
    required_slots: tuple[str, ...] = ()
    blocking_required_slots: tuple[str, ...] = ()
    resolvable_required_slots: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    response_decision: Mapping[str, Any] | None = None
    risk_level: str = "low"
    fallback_reason: str | None = None
    planner_intent: str | None = None
    planner_domains: tuple[str, ...] = ()
    execution_plan: tuple[str, ...] = ()
    referred_objects: Mapping[str, Any] = field(default_factory=dict)
    planner_confidence: float | None = None
    has_reference_signal: bool = False
    planner_source: str | None = None
    override_applied: bool = False
    override_reason: str | None = None
    original_router_domains: tuple[str, ...] = ()
    original_router_execution_plan: tuple[str, ...] = ()
    override_blocked: bool = False
    blocked_override_reason: str | None = None
    contract_drift: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "intent": self.intent,
            "sub_intent": self.sub_intent,
            "known_slots": dict(self.known_slots),
            "required_slots": list(self.required_slots),
            "blocking_required_slots": list(self.blocking_required_slots),
            "resolvable_required_slots": list(self.resolvable_required_slots),
            "allowed_tools": list(self.allowed_tools),
            "forbidden_tools": list(self.forbidden_tools),
            "response_decision": dict(self.response_decision or {}),
            "risk_level": self.risk_level,
            "fallback_reason": self.fallback_reason,
            "planner_intent": self.planner_intent,
            "planner_domains": list(self.planner_domains),
            "execution_plan": list(self.execution_plan),
            "referred_objects": dict(self.referred_objects),
            "planner_confidence": self.planner_confidence,
            "has_reference_signal": self.has_reference_signal,
            "planner_source": self.planner_source,
            "override_applied": self.override_applied,
            "override_reason": self.override_reason,
            "original_router_domains": list(self.original_router_domains),
            "original_router_execution_plan": list(self.original_router_execution_plan),
            "override_blocked": self.override_blocked,
            "blocked_override_reason": self.blocked_override_reason,
            "contract_drift": [dict(item) for item in self.contract_drift],
        }


def build_turn_contract(
    *,
    user_text: str = "",
    intent_frame: IntentFrame | None = None,
    tool_plan: ToolPlan | None = None,
    response_decision: ResponseDecision | None = None,
    cross_domain_plan: CrossDomainPlan | None = None,
    routing_result: Any | None = None,
    merged_slots: Any | None = None,
) -> TurnContract:
    """Combine policy objects into a single contract without changing execution."""

    planner_domains = _planner_domains(routing_result, cross_domain_plan)
    execution_plan = _execution_plan(routing_result, cross_domain_plan)
    planner_intent = _planner_intent(routing_result, cross_domain_plan)
    code_domain = _domain_value(intent_frame.domain) if intent_frame is not None else _domain_from_routing(routing_result)
    code_intent = intent_frame.intent if intent_frame is not None else _intent_from_cross_domain(cross_domain_plan)
    domain = planner_domains[0] if planner_domains else code_domain
    intent = planner_intent or code_intent
    sub_intent = intent_frame.sub_intent if intent_frame is not None else None
    known_slots = _compact_slots({
        **(dict(intent_frame.known_slots) if intent_frame is not None else {}),
        **_slots_from_model(merged_slots),
    })
    known_slots = _normalize_quantity_slots(known_slots)
    if intent_frame is not None:
        requested_product_attribute = str(intent_frame.entities.get("requested_product_attribute") or "")
        compare_metric = str(intent_frame.entities.get("compare_metric") or "")
        comparison_followup_intent = str(intent_frame.entities.get("comparison_followup_intent") or "")
        oe_replacement_type = str(intent_frame.entities.get("oe_replacement_type") or "")
        stock_check_mode = str(intent_frame.entities.get("stock_check_mode") or "")
        if requested_product_attribute:
            known_slots["requested_product_attribute"] = requested_product_attribute
        if compare_metric:
            known_slots["compare_metric"] = compare_metric
        if comparison_followup_intent:
            known_slots["comparison_followup_intent"] = comparison_followup_intent
        if oe_replacement_type:
            known_slots["oe_replacement_type"] = oe_replacement_type
        if stock_check_mode:
            known_slots["stock_check_mode"] = stock_check_mode
    policy_intent = str(getattr(routing_result, "policy_intent", "") or "")
    if policy_intent and policy_intent != "none":
        known_slots["policy_intent"] = policy_intent
    response_metadata = response_decision.metadata if response_decision is not None else {}
    if isinstance(response_metadata, Mapping):
        requested_product_attribute = str(response_metadata.get("requested_product_attribute") or "")
        compare_metric = str(response_metadata.get("compare_metric") or "")
        comparison_followup_intent = str(response_metadata.get("comparison_followup_intent") or "")
        oe_replacement_type = str(response_metadata.get("oe_replacement_type") or "")
        stock_check_mode = str(response_metadata.get("stock_check_mode") or "")
        if requested_product_attribute and not known_slots.get("requested_product_attribute"):
            known_slots["requested_product_attribute"] = requested_product_attribute
        if compare_metric and not known_slots.get("compare_metric"):
            known_slots["compare_metric"] = compare_metric
        if comparison_followup_intent and not known_slots.get("comparison_followup_intent"):
            known_slots["comparison_followup_intent"] = comparison_followup_intent
        if oe_replacement_type and not known_slots.get("oe_replacement_type"):
            known_slots["oe_replacement_type"] = oe_replacement_type
        if stock_check_mode and not known_slots.get("stock_check_mode"):
            known_slots["stock_check_mode"] = stock_check_mode

    has_reference_signal = _has_reference_signal(user_text)
    if intent == "transaction_fallback" and _is_recoverable_today_install_stock_contract(known_slots):
        intent = "stock_store_search"
    required_slots = _merge_tuple(
        intent_frame.missing_slots if intent_frame is not None else (),
        tool_plan.required_slots if tool_plan is not None else (),
        response_decision.required_slots if response_decision is not None else (),
        _required_slots_from_cross_domain(cross_domain_plan),
    )
    required_slots = _merge_tuple(
        required_slots,
        _derived_required_slots(
            user_text,
            code_intent,
            known_slots,
            cross_domain_plan=cross_domain_plan,
        ),
    )
    required_slots = _filter_satisfied_required_slots(required_slots, known_slots)
    resolvable_required_slots = _resolvable_required_slots(required_slots, cross_domain_plan)
    blocking_required_slots = _blocking_required_slots(
        user_text,
        required_slots,
        resolvable_required_slots,
        intent=intent,
        routing_result=routing_result,
    )
    allowed_tools = tuple(tool_plan.allowed_tools) if tool_plan is not None else ()
    forbidden_tools = tuple(tool_plan.forbidden_tools) if tool_plan is not None else ()
    if domain == "support" and policy_intent and policy_intent != "none":
        intent = policy_intent
        allowed_tools = _merge_tuple(
            allowed_tools,
            ("search_faq_hybrid_tool",),
        )
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            ("search_product_tool", "get_final_price_tool"),
        )

    drift = _contract_drift(
        code_domain=code_domain,
        code_intent=code_intent,
        planner_domain=domain,
        planner_intent=planner_intent,
    )
    risk_level = _risk_level(
        domain=domain,
        intent=intent,
        required_slots=blocking_required_slots,
        tool_plan=tool_plan,
    )
    if blocking_required_slots and _is_blocking_reference(
        routing_result,
        user_text=user_text,
        intent=intent,
    ):
        risk_level = "high"
    fallback_reason = _fallback_reason(
        intent=intent,
        required_slots=blocking_required_slots,
        response_decision=response_decision,
        cross_domain_plan=cross_domain_plan,
    )

    return TurnContract(
        domain=domain,
        intent=intent,
        sub_intent=sub_intent,
        known_slots=known_slots,
        required_slots=required_slots,
        blocking_required_slots=blocking_required_slots,
        resolvable_required_slots=resolvable_required_slots,
        allowed_tools=allowed_tools,
        forbidden_tools=forbidden_tools,
        response_decision=response_decision.to_dict() if response_decision is not None else None,
        risk_level=risk_level,
        fallback_reason=fallback_reason,
        planner_intent=planner_intent,
        planner_domains=planner_domains,
        execution_plan=execution_plan,
        referred_objects=_referred_objects(routing_result),
        planner_confidence=_planner_confidence(routing_result),
        has_reference_signal=has_reference_signal,
        planner_source=_planner_source(routing_result, cross_domain_plan),
        override_applied=bool(getattr(routing_result, "override_applied", False)),
        override_reason=str(getattr(routing_result, "override_reason", "") or "") or None,
        original_router_domains=tuple(
            _domain_value(domain)
            for domain in tuple(getattr(routing_result, "original_router_domains", ()) or ())
        ),
        original_router_execution_plan=tuple(
            str(item) for item in tuple(getattr(routing_result, "original_router_execution_plan", ()) or ())
        ),
        override_blocked=bool(getattr(routing_result, "override_blocked", False)),
        blocked_override_reason=str(getattr(routing_result, "blocked_override_reason", "") or "") or None,
        contract_drift=drift,
    )


def should_guard_required_slots(contract: TurnContract | None) -> bool:
    """Return true when executing tools/templates would be riskier than clarifying."""

    if contract is None or not contract.blocking_required_slots:
        return False
    if contract.risk_level != "high":
        return False
    if _has_blocking_reference(contract):
        return True
    if contract.domain not in _HIGH_RISK_DOMAINS:
        return False
    return True


def build_required_slot_clarification_event(contract: TurnContract) -> dict[str, Any]:
    """Build the quickReply used when a high-risk turn lacks required slots."""

    message = _clarification_text(contract.blocking_required_slots)
    quick_replies = _clarification_chips(contract.blocking_required_slots)
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_turn_contract_required_slot_guard",
        "data": {
            "assistantResponse": message,
            "quickReplies": quick_replies,
            "predictedDomains": ["TRANSACTION", "DISCOVERY"],
            "metadata": {
                "turnContract": contract.to_dict(),
                "requiredSlots": list(contract.blocking_required_slots),
            },
        },
    }


def build_response_policy_guard_event(contract: TurnContract) -> dict[str, Any]:
    """Build a safe fallback when a template violates response policy, not slots."""

    response_decision = contract.response_decision or {}
    forbidden = response_decision.get("forbidden_behaviors") if isinstance(response_decision, Mapping) else ()
    forbidden_set = {str(item) for item in forbidden} if isinstance(forbidden, list | tuple) else set()
    if _is_discovery_first_leg_transaction_contract(contract):
        intent = str(contract.intent or "")
        if intent == "stock_store_search":
            message = "재고를 확인하려면 어떤 상품 기준인지 먼저 정해야 해요. 확인할 상품명을 알려주시거나 상품을 선택해 주세요."
            quick_replies = [
                {"label": "상품명 입력", "domain": "DISCOVERY"},
                {"label": "재고 확인", "domain": "TRANSACTION"},
                {"label": "상품 추천", "domain": "DISCOVERY"},
            ]
        elif intent == "quick_order_reservation":
            message = "구매를 이어가려면 어떤 상품인지 먼저 정해야 해요. 확인할 상품명을 알려주시거나 상품을 선택해 주세요."
            quick_replies = [
                {"label": "상품명 입력", "domain": "DISCOVERY"},
                {"label": "구매 진행", "domain": "TRANSACTION"},
                {"label": "상품 추천", "domain": "DISCOVERY"},
            ]
        elif intent == "quick_order_execute":
            message = "주문을 이어가려면 상품, 매장, 예약 정보가 모두 확인되어야 해요. 필요한 정보를 다시 확인해 주세요."
            quick_replies = [
                {"label": "상품 다시 선택", "domain": "DISCOVERY"},
                {"label": "매장 다시 선택", "domain": "TRANSACTION"},
                {"label": "예약 시간 다시 선택", "domain": "TRANSACTION"},
            ]
        else:
            message = "가격을 확인하려면 어떤 상품 기준인지 먼저 정해야 해요. 확인할 상품명을 알려주시거나 상품을 선택해 주세요."
            quick_replies = [
                {"label": "상품명 입력", "domain": "DISCOVERY"},
                {"label": "가격 확인", "domain": "TRANSACTION"},
                {"label": "상품 추천", "domain": "DISCOVERY"},
            ]
    elif (
        "datepick_for_unavailable_stock" in forbidden_set
        or "datepick_for_pure_inventory_flow" in forbidden_set
        or "preorder_for_pure_inventory_flow" in forbidden_set
    ):
        message = "요청하신 조건으로 바로 예약 가능한 재고를 확인하지 못했어요. 다른 매장이나 조건으로 다시 확인해드릴게요."
        quick_replies = [
            {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
            {"label": "다른 날짜 확인", "domain": "TRANSACTION"},
            {"label": "다른 상품 추천", "domain": "DISCOVERY"},
        ]
    elif "assert_price_without_tool_result" in forbidden_set:
        message = "가격 정보를 확인하지 못해 금액을 단정할 수 없어요. 상품 조건을 다시 확인한 뒤 조회해드릴게요."
        quick_replies = [
            {"label": "가격 다시 확인", "domain": "TRANSACTION"},
            {"label": "상품 다시 선택", "domain": "DISCOVERY"},
        ]
    elif "assert_coupon_without_tool_result" in forbidden_set:
        message = "쿠폰 정보를 확인하지 못해 적용 여부를 단정할 수 없어요. 보유 쿠폰이나 적용 대상을 다시 확인해드릴게요."
        quick_replies = [
            {"label": "내 쿠폰 확인", "domain": "TRANSACTION"},
            {"label": "적용 상품 확인", "domain": "TRANSACTION"},
        ]
    elif "order_complete_on_tool_error" in forbidden_set:
        message = "주문서 생성 결과를 확인하지 못했어요. 주문 완료로 안내하지 않고 다시 확인해드릴게요."
        quick_replies = [
            {"label": "주문 다시 확인", "domain": "TRANSACTION"},
            {"label": "장바구니 확인", "domain": "TRANSACTION"},
        ]
    elif "datepick_on_tool_error" in forbidden_set:
        message = "예약 가능 시간을 확인하지 못했어요. 매장이나 날짜 조건을 다시 확인해드릴게요."
        quick_replies = [
            {"label": "다른 날짜 확인", "domain": "TRANSACTION"},
            {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
        ]
    else:
        message = "현재 확인된 정보만으로 바로 진행하기 어려워요. 필요한 정보를 먼저 확인한 뒤 이어서 도와드릴게요."
        quick_replies = _clarification_chips(contract.required_slots or ("product",))

    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_turn_contract_response_policy_guard",
        "data": {
            "assistantResponse": message,
            "quickReplies": quick_replies,
            "predictedDomains": ["TRANSACTION", "DISCOVERY"],
            "metadata": {
                "turnContract": contract.to_dict(),
                "forbiddenBehaviors": sorted(forbidden_set),
            },
        },
    }


def violates_response_template_contract(event: Mapping[str, Any], contract: TurnContract | None) -> bool:
    """Block only templates that clearly contradict missing-slot policy."""

    if contract is None:
        return False
    template = str(event.get("template") or "")
    if should_guard_required_slots(contract) and template in _REQUIRED_SLOT_BLOCK_TEMPLATES:
        return True
    if _is_unsupported_discovery_product_template_without_current_source(event, contract):
        return True
    if _is_discovery_first_leg_transaction_violation(event, contract):
        return True
    response_decision = contract.response_decision or {}
    forbidden_behaviors = response_decision.get("forbidden_behaviors") if isinstance(response_decision, Mapping) else ()
    if not isinstance(forbidden_behaviors, list | tuple):
        return False
    return any(template in _FORBIDDEN_BEHAVIOR_TEMPLATE_BLOCKS.get(str(behavior), ()) for behavior in forbidden_behaviors)


def response_contract_violations(
    *,
    template: str | None,
    assistant_response_text: str | None = None,
    assistant_response_source: str | None = None,
    compare_metric: str | None = None,
    response_shape_key: str | None = None,
    called_tools: list[str] | tuple[str, ...] | None = None,
    source_domain: str | None = None,
    contract: TurnContract | None,
) -> list[dict[str, Any]]:
    """Return deterministic contract violations for QC logging."""

    if contract is None:
        return []
    violations: list[dict[str, Any]] = []
    event = {
        "template": template or "",
        "assistant_response_source": assistant_response_source or "",
        "assistant_response_text": assistant_response_text or "",
        "response_shape_key": response_shape_key or "",
        "called_tools": list(called_tools or ()),
        "source_domain": source_domain or ("discovery" if contract.domain == "discovery" else contract.domain),
    }
    if should_guard_required_slots(contract) and template != "quickReply":
        violations.append({
            "type": "required_slots_not_clarified",
            "required_slots": list(contract.blocking_required_slots),
            "template": template,
        })
    unsupported_product_template = _is_unsupported_discovery_product_template_without_current_source(event, contract)
    if unsupported_product_template:
        violations.append({
            "type": "unsupported_product_template_without_current_source",
            "template": template,
            "fallback_reason": contract.fallback_reason,
            "response_shape_key": str(event.get("response_shape_key") or ""),
            "assistant_response_source": str(event.get("assistant_response_source") or ""),
        })
    if violates_response_template_contract(event, contract) and not unsupported_product_template:
        violation_type = (
            "forbidden_discovery_first_leg_response"
            if _is_discovery_first_leg_transaction_violation(event, contract)
            else "forbidden_template"
        )
        violations.append({
            "type": violation_type,
            "template": template,
            "fallback_reason": contract.fallback_reason,
            "response_shape_key": str(event.get("response_shape_key") or ""),
            "assistant_response_source": str(event.get("assistant_response_source") or ""),
        })
    compare_metadata_violation = _comparison_metric_metadata_violation(
        compare_metric=compare_metric,
        assistant_response_source=assistant_response_source,
        contract=contract,
    )
    if compare_metadata_violation is not None:
        violations.append(compare_metadata_violation)
    product_attribute_violation = _product_attribute_contract_violation(
        assistant_response_source=assistant_response_source,
        response_shape_key=response_shape_key,
        contract=contract,
    )
    if product_attribute_violation is not None:
        violations.append(product_attribute_violation)
    tool_contract_violation = _tool_contract_violation(
        called_tools=called_tools,
        contract=contract,
    )
    if tool_contract_violation is not None:
        violations.append(tool_contract_violation)
    compare_violation = _comparison_contract_violation(
        assistant_response_text=assistant_response_text,
        assistant_response_source=assistant_response_source,
        response_shape_key=response_shape_key,
        contract=contract,
    )
    if compare_violation is not None:
        violations.append(compare_violation)
    stock_violation = _stock_contract_violation(
        template=template,
        assistant_response_source=assistant_response_source,
        response_shape_key=response_shape_key,
        called_tools=called_tools,
        contract=contract,
    )
    if stock_violation is not None:
        violations.append(stock_violation)
    quick_order_violation = _quick_order_execute_contract_violation(
        template=template,
        assistant_response_text=assistant_response_text,
        assistant_response_source=assistant_response_source,
        response_shape_key=response_shape_key,
        called_tools=called_tools,
        contract=contract,
    )
    if quick_order_violation is not None:
        violations.append(quick_order_violation)
    return [_with_contract_violation_severity(violation) for violation in violations]


def _with_contract_violation_severity(violation: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(violation)
    if normalized.get("severity") in {"error", "warning"}:
        return normalized
    violation_type = str(normalized.get("type") or "")
    normalized["severity"] = "warning" if violation_type in _WARNING_CONTRACT_VIOLATION_TYPES else "error"
    return normalized


def hard_contract_violations(violations: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    return [violation for violation in violations if str(violation.get("severity") or "error") == "error"]


def warning_contract_violations(violations: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    return [violation for violation in violations if str(violation.get("severity") or "error") == "warning"]


def _comparison_metric_metadata_violation(
    *,
    compare_metric: str | None,
    assistant_response_source: str | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(assistant_response_source or "") != "code_product_compare_resolver":
        return None
    response_metadata = contract.response_decision or {}
    response_metadata = response_metadata.get("metadata") if isinstance(response_metadata, Mapping) else {}
    if not isinstance(response_metadata, Mapping):
        return None
    expected_metric = str(response_metadata.get("compare_metric") or contract.known_slots.get("compare_metric") or "")
    actual_metric = str(compare_metric or "").strip()
    if not expected_metric or not actual_metric or expected_metric == actual_metric:
        return None
    return {
        "type": "compare_metric_metadata_drift",
        "compare_metric": expected_metric,
        "assistant_compare_metric": actual_metric,
    }


def _product_attribute_contract_violation(
    *,
    assistant_response_source: str | None,
    response_shape_key: str | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None:
        return None
    response_metadata = contract.response_decision or {}
    response_metadata = response_metadata.get("metadata") if isinstance(response_metadata, Mapping) else {}
    if not isinstance(response_metadata, Mapping):
        return None
    requested_product_attribute = str(
        response_metadata.get("requested_product_attribute") or contract.known_slots.get("requested_product_attribute") or ""
    )
    if not requested_product_attribute:
        return None
    if str(response_shape_key or "") == "product_attribute_summary":
        return None
    return {
        "type": "requested_product_attribute_contract_drift",
        "requested_product_attribute": requested_product_attribute,
        "response_shape_key": str(response_shape_key or ""),
        "assistant_response_source": str(assistant_response_source or ""),
        "expected_response_shape_key": "product_attribute_summary",
    }


def _tool_contract_violation(
    *,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or not contract.allowed_tools or not called_tools:
        return None
    called_tool_set = {str(tool) for tool in tuple(called_tools or ()) if str(tool).strip()}
    if (
        called_tool_set
        and called_tool_set <= _DISCOVERY_PRODUCT_SOURCE_TOOLS
        and _is_discovery_first_leg_transaction_contract(contract)
    ):
        return None
    disallowed = [
        str(tool)
        for tool in called_tools
        if str(tool)
        and (str(tool) not in contract.allowed_tools or str(tool) in contract.forbidden_tools)
    ]
    if not disallowed:
        return None
    return {
        "type": "unexpected_tool_for_contract",
        "called_tools": disallowed,
        "allowed_tools": list(contract.allowed_tools),
    }


def _comparison_contract_violation(
    *,
    assistant_response_text: str | None,
    assistant_response_source: str | None,
    response_shape_key: str | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None:
        return None
    response_metadata = contract.response_decision or {}
    response_metadata = response_metadata.get("metadata") if isinstance(response_metadata, Mapping) else {}
    if not isinstance(response_metadata, Mapping):
        return None
    comparison_followup_intent = str(response_metadata.get("comparison_followup_intent") or "")
    compare_metric = str(response_metadata.get("compare_metric") or contract.known_slots.get("compare_metric") or "")
    if comparison_followup_intent != "continue_previous_compare_metric":
        return None
    if str(assistant_response_source or "") != "code_product_compare_resolver":
        return {
            "type": "compare_metric_contract_drift",
            "comparison_followup_intent": comparison_followup_intent,
            "compare_metric": compare_metric or "none",
            "assistant_response_source": str(assistant_response_source or ""),
        }
    expected_response_shape_key = (
        "grade_comparison_summary" if compare_metric in {"grade", "price_grade"} else "metric_comparison_summary"
    )
    if str(response_shape_key or "") != expected_response_shape_key:
        return {
            "type": "compare_metric_contract_drift",
            "comparison_followup_intent": comparison_followup_intent,
            "compare_metric": compare_metric or "none",
            "response_shape_key": str(response_shape_key or ""),
            "expected_response_shape_key": expected_response_shape_key,
        }
    expected_row = _comparison_metric_row_label(compare_metric)
    response_text = str(assistant_response_text or "")
    if expected_row and expected_row not in response_text:
        return {
            "type": "compare_metric_row_missing",
            "comparison_followup_intent": comparison_followup_intent,
            "compare_metric": compare_metric or "none",
            "expected_row": expected_row,
        }
    return None


def _stock_contract_violation(
    *,
    template: str | None,
    assistant_response_source: str | None,
    response_shape_key: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(contract.intent or "") != "stock_store_search":
        return None
    stock_check_mode = str(contract.known_slots.get("stock_check_mode") or "")
    called_tools = tuple(str(tool) for tool in tuple(called_tools or ()) if str(tool).strip())
    if stock_check_mode == "inventory_only":
        if str(response_shape_key or "") == "transaction_fallback" and not called_tools:
            return {
                "type": "stock_contract_fell_back_without_resolution",
                "assistant_response_source": str(assistant_response_source or ""),
                "response_shape_key": str(response_shape_key or ""),
                "called_tools": [],
            }
        if not called_tools:
            return {
                "type": "inventory_tool_missing_for_stock_contract",
                "assistant_response_source": str(assistant_response_source or ""),
                "response_shape_key": str(response_shape_key or ""),
            }
        if any(tool == "transaction_store_preview_tool" for tool in called_tools):
            return {
                "type": "unexpected_preview_tool_for_inventory_only_stock",
                "called_tools": list(called_tools),
            }
        if str(template or "") == "datepick":
            return {
                "type": "forbidden_datepick_for_inventory_only_stock",
                "response_shape_key": str(response_shape_key or ""),
            }
    if str(response_shape_key or "") == "transaction_fallback":
        return {
            "type": "stock_contract_fell_back_without_resolution",
            "assistant_response_source": str(assistant_response_source or ""),
        }
    return None


def _quick_order_execute_contract_violation(
    *,
    template: str | None,
    assistant_response_text: str | None,
    assistant_response_source: str | None,
    response_shape_key: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(contract.intent or "") != "quick_order_execute":
        return None
    called_tools = tuple(str(tool) for tool in tuple(called_tools or ()) if str(tool).strip())
    if "quick_order_tool" not in called_tools:
        if str(template or "") == "orderComplete":
            return {
                "type": "order_complete_without_quick_order_tool",
                "assistant_response_source": str(assistant_response_source or ""),
                "response_shape_key": str(response_shape_key or ""),
            }
        return {
            "type": "quick_order_execute_without_tool",
            "assistant_response_source": str(assistant_response_source or ""),
            "response_shape_key": str(response_shape_key or ""),
            "template": str(template or ""),
            "assistant_response_text": str(assistant_response_text or "")[:160],
        }
    if str(response_shape_key or "") == "transaction_fallback":
        return {
            "type": "quick_order_execute_fell_back_without_resolution",
            "assistant_response_source": str(assistant_response_source or ""),
        }
    return None


def _comparison_metric_row_label(metric: str) -> str:
    return {
        "release": "출시 시점",
        "price": "최종 혜택가",
        "grade": "상품 등급",
        "price_grade": "상품 등급",
        "mileage": "마일리지/수명",
        "noise": "정숙성",
        "fuel_efficiency": "연비/회전저항",
        "wet": "빗길 성능",
        "car_type": "차종",
        "detail": "특징",
    }.get(str(metric or ""), "")


def _domain_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "unknown")


def _domain_from_routing(routing_result: Any | None) -> str:
    domains = getattr(routing_result, "domains", None)
    if domains:
        return _domain_value(domains[0])
    return "unknown"


def _planner_domains(routing_result: Any | None, plan: CrossDomainPlan | None) -> tuple[str, ...]:
    domains = getattr(routing_result, "domains", None)
    if domains:
        return tuple(_domain_value(domain) for domain in domains)
    if plan is not None:
        return (_domain_value(plan.primary_domain),)
    return ()


def _is_discovery_first_leg_transaction_contract(contract: TurnContract | None) -> bool:
    if contract is None:
        return False
    if not contract.planner_domains or contract.planner_domains[0] != "discovery":
        return False
    if "transaction" in contract.planner_domains[1:]:
        return True
    return any(str(item).strip().startswith("transaction:") for item in contract.execution_plan)


def _is_discovery_first_leg_transaction_violation(
    event: Mapping[str, Any],
    contract: TurnContract | None,
) -> bool:
    if not _is_discovery_first_leg_transaction_contract(contract):
        return False
    if str(event.get("source_domain") or "").lower() != "discovery":
        return False
    if str(event.get("template") or "") != "quickReply":
        return False
    response_shape_key = str(event.get("response_shape_key") or "")
    assistant_response_source = str(event.get("assistant_response_source") or "")
    assistant_response_text = str(event.get("assistant_response_text") or "")
    if not assistant_response_text:
        data = event.get("data")
        if isinstance(data, Mapping):
            assistant_response_text = str(data.get("assistantResponse") or "")
    if assistant_response_source == "discovery_agent" and _DISCOVERY_NO_RESULT_RE.search(assistant_response_text):
        return False
    if (
        assistant_response_source == "code_product_compare_resolver"
        and response_shape_key in {"metric_comparison_summary", "grade_comparison_summary"}
    ):
        return False
    called_tools = tuple(str(tool) for tool in tuple(event.get("called_tools") or ()))
    if any(tool.startswith("get_final_price_tool") or tool.startswith("get_store") or tool.startswith("quick_order") for tool in called_tools):
        return False
    return (
        response_shape_key in _DISCOVERY_FIRST_LEG_BLOCK_RESPONSE_SHAPES
        or assistant_response_source in _DISCOVERY_FIRST_LEG_BLOCK_SOURCES
    )


def _is_unsupported_discovery_product_template_without_current_source(
    event: Mapping[str, Any],
    contract: TurnContract | None,
) -> bool:
    if contract is None:
        return False
    if str(event.get("template") or "") != "product":
        return False
    if str(event.get("source_domain") or "").lower() != "discovery":
        return False
    response_decision = contract.response_decision or {}
    forbidden_behaviors = response_decision.get("forbidden_behaviors") if isinstance(response_decision, Mapping) else ()
    if not isinstance(forbidden_behaviors, list | tuple) or not forbidden_behaviors:
        return False
    forbidden_set = {str(item) for item in forbidden_behaviors}
    if not any("product" in _FORBIDDEN_BEHAVIOR_TEMPLATE_BLOCKS.get(behavior, ()) for behavior in forbidden_set):
        return False
    called_tools = {str(tool) for tool in tuple(event.get("called_tools") or ()) if str(tool).strip()}
    if called_tools & _DISCOVERY_PRODUCT_SOURCE_TOOLS:
        return False
    return True


def _execution_plan(routing_result: Any | None, plan: CrossDomainPlan | None) -> tuple[str, ...]:
    raw_plan = getattr(routing_result, "execution_plan", None)
    if raw_plan:
        return tuple(str(item) for item in raw_plan if str(item).strip())
    if plan is not None:
        return tuple(f"{task.domain.value}:{task.intent}" for task in plan.subtasks)
    return ()


def _planner_intent(routing_result: Any | None, plan: CrossDomainPlan | None) -> str | None:
    for item in _execution_plan(routing_result, plan):
        token = str(item).strip()
        if not token:
            continue
        if ":" in token:
            _, intent = token.split(":", 1)
            return _normalize_plan_intent(intent)
    return None


def _normalize_plan_intent(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    aliases = {
        "resolve_product": "resolve_or_describe_product",
        "continue_purchase": "quick_order_reservation",
        "quick_order_confirmed": "quick_order_execute",
        "transaction_price_stock": "price_or_coupon_check",
        "discovery_search": "resolve_or_describe_product",
    }
    return aliases.get(normalized, normalized or "unknown")


def _planner_confidence(routing_result: Any | None) -> float | None:
    value = getattr(routing_result, "planner_confidence", None)
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return None


def _planner_source(routing_result: Any | None, plan: CrossDomainPlan | None) -> str:
    if routing_result is not None:
        return "router_llm"
    if plan is not None:
        return "cross_domain_policy"
    return "unknown"


def _referred_objects(routing_result: Any | None) -> dict[str, Any]:
    if routing_result is None:
        return {}
    return {
        "status": str(getattr(routing_result, "referred_object_status", "resolved") or "resolved"),
        "type": str(getattr(routing_result, "referred_object_type", "none") or "none"),
        "needs_clarification": bool(getattr(routing_result, "needs_clarification", False)),
    }


def _contract_drift(
    *,
    code_domain: str,
    code_intent: str,
    planner_domain: str,
    planner_intent: str | None,
) -> tuple[Mapping[str, Any], ...]:
    drift: list[Mapping[str, Any]] = []
    if planner_domain and planner_domain != "unknown" and code_domain != planner_domain:
        drift.append({
            "field": "domain",
            "planner": planner_domain,
            "code_frame": code_domain,
        })
    if planner_intent and planner_intent != "unknown" and code_intent != planner_intent:
        drift.append({
            "field": "intent",
            "planner": planner_intent,
            "code_frame": code_intent,
        })
    return tuple(drift)


def _intent_from_cross_domain(plan: CrossDomainPlan | None) -> str:
    if plan is None or not plan.subtasks:
        return "unknown"
    return plan.subtasks[0].intent


def _required_slots_from_cross_domain(plan: CrossDomainPlan | None) -> tuple[str, ...]:
    if plan is None:
        return ()
    slots: list[str] = []
    for task in plan.subtasks:
        slots.extend(task.required_slots)
    return tuple(slots)


def _resolvable_required_slots(
    required_slots: tuple[str, ...],
    plan: CrossDomainPlan | None,
) -> tuple[str, ...]:
    if not required_slots or not _has_discovery_product_resolution_task(plan):
        return ()
    resolvable = {"product", "goods_no"}
    return tuple(slot for slot in required_slots if slot in resolvable)


def _blocking_required_slots(
    user_text: str,
    required_slots: tuple[str, ...],
    resolvable_required_slots: tuple[str, ...],
    *,
    intent: str,
    routing_result: Any | None,
) -> tuple[str, ...]:
    blocking = [slot for slot in required_slots if slot not in set(resolvable_required_slots)]
    if _should_apply_reference_guard(
        user_text=user_text,
        intent=intent,
        routing_result=routing_result,
    ):
        referred = _referred_objects(routing_result)
        slot = _slot_for_referred_object_type(str(referred.get("type") or "none"))
        if slot not in blocking:
            blocking.append(slot)
    return tuple(blocking)


def _is_blocking_reference(routing_result: Any | None, *, user_text: str = "", intent: str = "") -> bool:
    return _should_apply_reference_guard(
        user_text=user_text,
        intent=intent,
        routing_result=routing_result,
    )


def _has_blocking_reference(contract: TurnContract) -> bool:
    if _reference_guard_exempt_intent(contract.intent):
        return False
    referred_type = str(contract.referred_objects.get("type") or "none")
    if not (
        contract.referred_objects.get("needs_clarification")
        and contract.referred_objects.get("status") in {"missing", "ambiguous"}
    ):
        return False
    if referred_type == "none":
        return contract.has_reference_signal
    if referred_type == "store" and not contract.has_reference_signal:
        return False
    return True


def _should_apply_reference_guard(
    *,
    user_text: str,
    intent: str,
    routing_result: Any | None,
) -> bool:
    if _reference_guard_exempt_intent(intent):
        return False
    referred = _referred_objects(routing_result)
    if not (
        referred.get("needs_clarification")
        and referred.get("status") in {"missing", "ambiguous"}
    ):
        return False
    referred_type = str(referred.get("type") or "none")
    has_reference_signal = _has_reference_signal(user_text)
    if referred_type == "none":
        return has_reference_signal
    if referred_type == "store" and not has_reference_signal:
        return False
    if has_reference_signal:
        return True
    return referred_type in {"product", "product_set", "order", "coupon"}


def _reference_guard_exempt_intent(intent: str) -> bool:
    return str(intent or "") in {"favorite_store_lookup", "oe_re_concept_explanation"}


def _slot_for_referred_object_type(object_type: str) -> str:
    return {
        "product": "product",
        "product_set": "product_set",
        "store": "store",
        "order": "order",
        "coupon": "coupon",
    }.get(object_type, "reference")


def _has_reference_signal(user_text: str) -> bool:
    return bool(_REFERENCE_SIGNAL_RE.search(str(user_text or "")))


def _slots_from_model(model: Any | None) -> dict[str, Any]:
    if model is None:
        return {}
    if hasattr(model, "model_dump"):
        return dict(model.model_dump())
    if isinstance(model, Mapping):
        return dict(model)
    return {
        name: getattr(model, name)
        for name in (
            "goods_no",
            "tire_model",
            "tire_size",
            "ord_qty",
            "shop_id",
            "shop_name",
            "region",
            "pending_intent",
            "goal_type",
        )
        if hasattr(model, name)
    }


def _compact_slots(slots: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in slots.items() if value not in (None, "", [], {})}


def _normalize_quantity_slots(slots: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(slots)
    quantity = normalized.get("quantity") or normalized.get("ord_qty")
    if quantity in (None, "") and normalized.get("pending_intent") in {"stock", "order"}:
        quantity = normalized.get("limit")
    if quantity not in (None, ""):
        normalized["quantity"] = quantity
        normalized["ord_qty"] = quantity
    return normalized


def _has_quantity_slot(known_slots: Mapping[str, Any]) -> bool:
    return bool(known_slots.get("quantity") or known_slots.get("ord_qty"))


def _filter_satisfied_required_slots(
    required_slots: tuple[str, ...],
    known_slots: Mapping[str, Any],
) -> tuple[str, ...]:
    if not required_slots:
        return ()
    filtered: list[str] = []
    for slot in required_slots:
        if slot == "quantity" and _has_quantity_slot(known_slots):
            continue
        if slot == "goods_no" and known_slots.get("goods_no"):
            continue
        if slot == "product" and (
            known_slots.get("goods_no")
            or known_slots.get("product_name")
            or known_slots.get("tire_model")
            or known_slots.get("pattern_name")
        ):
            continue
        if slot == "tire_size" and known_slots.get("tire_size"):
            continue
        if slot in {"store", "location"} and (
            known_slots.get("shop_id")
            or known_slots.get("shop_name")
            or known_slots.get("store_name")
            or known_slots.get("region")
        ):
            continue
        filtered.append(slot)
    return tuple(filtered)


def _is_recoverable_today_install_stock_contract(known_slots: Mapping[str, Any]) -> bool:
    return bool(
        (known_slots.get("pending_intent") == "stock" or known_slots.get("goal_type") == "store_with_stock")
        and known_slots.get("availability_intent") == "today_install"
        and known_slots.get("goods_no")
        and known_slots.get("tire_size")
        and _has_quantity_slot(known_slots)
    )


def _merge_tuple(*values: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    for seq in values:
        for item in seq or ():
            if item and item not in merged:
                merged.append(item)
    return tuple(merged)


def _derived_required_slots(
    user_text: str,
    intent: str,
    known_slots: Mapping[str, Any],
    *,
    cross_domain_plan: CrossDomainPlan | None = None,
) -> tuple[str, ...]:
    has_product = bool(
        known_slots.get("goods_no")
        or known_slots.get("product_name")
        or known_slots.get("tire_model")
        or known_slots.get("pattern_name")
    )
    text = user_text or ""
    required: list[str] = []
    if (
        intent == "price_or_coupon_check"
        and _PRICE_OR_COUPON_RE.search(text)
        and not has_product
        and not _has_discovery_product_resolution_task(cross_domain_plan)
    ):
        required.append("product")
    if _REFERENCE_PURCHASE_RE.search(text) and not has_product:
        required.append("product")
    return tuple(required)


def _has_discovery_product_resolution_task(plan: CrossDomainPlan | None) -> bool:
    if plan is None:
        return False
    return any(task.intent == "resolve_or_describe_product" for task in plan.subtasks)


def _risk_level(
    *,
    domain: str,
    intent: str,
    required_slots: tuple[str, ...],
    tool_plan: ToolPlan | None,
) -> str:
    if required_slots and intent in _HIGH_RISK_INTENTS:
        return "high"
    if domain in _HIGH_RISK_DOMAINS and (intent in _HIGH_RISK_INTENTS or required_slots):
        return "high"
    if tool_plan is not None and tool_plan.forbidden_tools:
        return "medium"
    return "low"


def _fallback_reason(
    *,
    intent: str,
    required_slots: tuple[str, ...],
    response_decision: ResponseDecision | None,
    cross_domain_plan: CrossDomainPlan | None,
) -> str | None:
    if required_slots:
        return f"missing_required_slots:{','.join(required_slots)}"
    if response_decision is not None and response_decision.forbidden_behaviors:
        return "response_policy_forbidden_behaviors"
    if cross_domain_plan is not None and cross_domain_plan.is_cross_domain:
        return "cross_domain_plan"
    if intent in _HIGH_RISK_INTENTS:
        return "high_risk_intent"
    return None


def _clarification_text(required_slots: tuple[str, ...]) -> str:
    if "product" in required_slots or "goods_no" in required_slots or "product_set" in required_slots:
        return "어떤 상품 기준으로 확인해드릴까요?"
    if "tire_size" in required_slots:
        return "확인할 타이어 사이즈를 알려주세요."
    if "quantity" in required_slots:
        return "몇 개 기준으로 확인해드릴까요?"
    if "store" in required_slots or "location" in required_slots:
        return "어느 지역이나 매장 기준으로 확인해드릴까요?"
    return "확인에 필요한 정보를 조금만 더 알려주세요."


def _clarification_chips(required_slots: tuple[str, ...]) -> list[dict[str, str]]:
    chips: list[dict[str, str]] = []
    if "product" in required_slots or "goods_no" in required_slots or "product_set" in required_slots:
        chips.append({"label": "상품명 입력", "domain": "DISCOVERY"})
    if "tire_size" in required_slots:
        chips.append({"label": "사이즈 입력", "domain": "DISCOVERY"})
    if "quantity" in required_slots:
        chips.append({"label": "수량 선택", "domain": "TRANSACTION"})
    if "store" in required_slots or "location" in required_slots:
        chips.append({"label": "지역/매장 입력", "domain": "TRANSACTION"})
    chips.extend([
        {"label": "상품 추천", "domain": "DISCOVERY"},
        {"label": "처음부터 다시", "domain": "LEADING"},
    ])
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for chip in chips:
        label = chip["label"]
        if label not in seen:
            deduped.append(chip)
            seen.add(label)
    return deduped[:4]
