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
    "preorder": frozenset({"preOrder", "orderComplete"}),
    "preorder_with_null_required_fields": frozenset({"preOrder", "orderComplete"}),
    "order_summary_with_null_required_fields": frozenset({"preOrder", "orderComplete"}),
    "assert_price_without_tool_result": frozenset({"preOrder", "billProduct", "cheapestProduct"}),
    "assert_coupon_without_tool_result": frozenset({"voucher", "preOrder", "billProduct"}),
    "order_complete_on_tool_error": frozenset({"orderComplete"}),
    "datepick_on_tool_error": frozenset({"datepick", "preOrder"}),
    "assert_success_without_tool_result": frozenset({"datepick", "preOrder", "orderComplete", "billProduct"}),
}
_PRICE_OR_COUPON_RE = re.compile(r"가격|얼마|할인가|쿠폰|할인|혜택", re.IGNORECASE)
_REFERENCE_PURCHASE_RE = re.compile(r"(?:그거|그\s*상품|이거|이\s*상품).{0,20}(구매|주문|결제|살래|살게|사고)", re.IGNORECASE)


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
    planner_source: str | None = None
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
            "planner_source": self.planner_source,
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
    resolvable_required_slots = _resolvable_required_slots(required_slots, cross_domain_plan)
    blocking_required_slots = _blocking_required_slots(
        required_slots,
        resolvable_required_slots,
        routing_result=routing_result,
    )
    allowed_tools = tuple(tool_plan.allowed_tools) if tool_plan is not None else ()
    forbidden_tools = tuple(tool_plan.forbidden_tools) if tool_plan is not None else ()

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
    if blocking_required_slots and _is_blocking_reference(routing_result):
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
        planner_source=_planner_source(routing_result, cross_domain_plan),
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
    if "datepick_for_unavailable_stock" in forbidden_set:
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
    response_decision = contract.response_decision or {}
    forbidden_behaviors = response_decision.get("forbidden_behaviors") if isinstance(response_decision, Mapping) else ()
    if not isinstance(forbidden_behaviors, list | tuple):
        return False
    return any(template in _FORBIDDEN_BEHAVIOR_TEMPLATE_BLOCKS.get(str(behavior), ()) for behavior in forbidden_behaviors)


def response_contract_violations(
    *,
    template: str | None,
    contract: TurnContract | None,
) -> list[dict[str, Any]]:
    """Return deterministic contract violations for QC logging."""

    if contract is None:
        return []
    violations: list[dict[str, Any]] = []
    event = {"template": template or ""}
    if should_guard_required_slots(contract) and template != "quickReply":
        violations.append({
            "type": "required_slots_not_clarified",
            "required_slots": list(contract.blocking_required_slots),
            "template": template,
        })
    if violates_response_template_contract(event, contract):
        violations.append({
            "type": "forbidden_template",
            "template": template,
            "fallback_reason": contract.fallback_reason,
        })
    return violations


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
    required_slots: tuple[str, ...],
    resolvable_required_slots: tuple[str, ...],
    *,
    routing_result: Any | None,
) -> tuple[str, ...]:
    blocking = [slot for slot in required_slots if slot not in set(resolvable_required_slots)]
    referred = _referred_objects(routing_result)
    if referred.get("needs_clarification") and referred.get("status") in {"missing", "ambiguous"}:
        slot = _slot_for_referred_object_type(str(referred.get("type") or "none"))
        if slot not in blocking:
            blocking.append(slot)
    return tuple(blocking)


def _is_blocking_reference(routing_result: Any | None) -> bool:
    referred = _referred_objects(routing_result)
    return bool(
        referred.get("needs_clarification")
        and referred.get("status") in {"missing", "ambiguous"}
    )


def _has_blocking_reference(contract: TurnContract) -> bool:
    return bool(
        contract.referred_objects.get("needs_clarification")
        and contract.referred_objects.get("status") in {"missing", "ambiguous"}
    )


def _slot_for_referred_object_type(object_type: str) -> str:
    return {
        "product": "product",
        "product_set": "product_set",
        "store": "store",
        "order": "order",
        "coupon": "coupon",
    }.get(object_type, "reference")


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
