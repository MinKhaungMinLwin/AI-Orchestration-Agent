"""Cross-domain task decomposition policy.

This module does not execute tools. It converts a single user request into a
stable ordered contract that the coordinator can consume when a turn requires
more than one domain, such as product resolution followed by stock lookup.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from services.tstation.policies.intent_frame import PolicyDomain


_PRODUCT_HINT_RE = re.compile(
    r"벤투스|ventus|다이나프로|dynapro|키너지|kinergy|아이온|ion|옵티모|optimo|미쉐린|michelin|cc2",
    re.IGNORECASE,
)
_STOCK_OR_BOOKING_RE = re.compile(r"재고|오늘\s*장착|장착\s*가능|예약|매장|근처|주변", re.IGNORECASE)
_PRICE_OR_COUPON_RE = re.compile(r"가격|할인가|최대\s*혜택|쿠폰|할인", re.IGNORECASE)
_PATTERN_COUPON_KEYWORD = r"패밀리|family|생일|birthday|임직원|employee|직원"
_PATTERN_COUPON_RE = re.compile(
    rf"(?:{_PATTERN_COUPON_KEYWORD}).{{0,20}}(?:쿠폰|할인권)|"
    rf"(?:쿠폰|할인권).{{0,20}}(?:{_PATTERN_COUPON_KEYWORD})",
    re.IGNORECASE,
)
_SUPPORT_RE = re.compile(r"만료|원복|상담원|고객센터|1:1|문의|불만|클레임", re.IGNORECASE)
_DESCRIPTION_RE = re.compile(r"뭐야|뭔지|설명|차이|장점|왜|등급|연비|소음|마일리지|최신", re.IGNORECASE)
_SIZE_COMPACT_RE = re.compile(r"\b(\d{3})\s*/?\s*(\d{2})\s*R?\s*(\d{2})\b", re.IGNORECASE)


@dataclass(frozen=True)
class DomainSubtask:
    domain: PolicyDomain
    intent: str
    reason: str
    required_slots: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain.value,
            "intent": self.intent,
            "reason": self.reason,
            "required_slots": list(self.required_slots),
            "depends_on": list(self.depends_on),
        }


@dataclass(frozen=True)
class CrossDomainPlan:
    primary_domain: PolicyDomain
    subtasks: tuple[DomainSubtask, ...]
    response_strategy: str

    @property
    def is_cross_domain(self) -> bool:
        return len({task.domain for task in self.subtasks}) > 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_domain": self.primary_domain.value,
            "subtasks": [task.to_dict() for task in self.subtasks],
            "response_strategy": self.response_strategy,
            "is_cross_domain": self.is_cross_domain,
        }


def agent_domain_values_for_plan(plan: CrossDomainPlan) -> list[str]:
    """Return ordered agent domain values for a coordinator route."""
    domains: list[str] = []
    for task in plan.subtasks:
        if task.domain == PolicyDomain.UNKNOWN:
            continue
        value = task.domain.value
        if value not in domains:
            domains.append(value)
    return domains


def agent_domain_values_for_initial_route(
    plan: CrossDomainPlan,
    *,
    known_slots: dict[str, Any] | None = None,
) -> list[str]:
    """Return a safe initial route for the coordinator.

    Product-name + transaction turns need Discovery first. When neither goods_no
    nor tire_size is known, Discovery must stop at product/size selection instead
    of pre-running Transaction with insufficient slots.
    """
    domains = agent_domain_values_for_plan(plan)
    transaction_task = next((task for task in plan.subtasks if task.domain == PolicyDomain.TRANSACTION), None)
    if (
        domains == [PolicyDomain.DISCOVERY.value, PolicyDomain.TRANSACTION.value]
        and transaction_task is not None
        and "tire_size" in transaction_task.required_slots
    ):
        return [PolicyDomain.DISCOVERY.value]
    return domains


def should_defer_product_price_explanation_to_classifier(user_text: str, plan: CrossDomainPlan) -> bool:
    """Let the LLM classifier handle explanatory product-price questions.

    The deterministic cross-domain route is intended for executable tasks
    (resolve product → price/stock/order). For "why/difference" questions, the
    user is asking for an explanation or policy, so forcing product resolution
    first can surface a product list and pressure the user to choose a size.
    """
    text = user_text or ""
    intents = {task.intent for task in plan.subtasks}
    return (
        "resolve_or_describe_product" in intents
        and "price_or_coupon_check" in intents
        and "stock_store_or_reservation" not in intents
        and bool(_DESCRIPTION_RE.search(text))
    )


def plan_cross_domain_turn(user_text: str, *, known_slots: dict[str, Any] | None = None) -> CrossDomainPlan:
    """Plan ordered domain subtasks for a multi-intent user turn."""
    text = user_text or ""
    slots = known_slots or {}
    subtasks: list[DomainSubtask] = []

    has_product_hint = bool(_PRODUCT_HINT_RE.search(text) or slots.get("product_name") or slots.get("goods_no"))
    tire_size = slots.get("tire_size") or _normalize_tire_size(text)
    needs_stock_or_booking = bool(_STOCK_OR_BOOKING_RE.search(text))
    needs_price = bool(_PRICE_OR_COUPON_RE.search(text))
    needs_support = bool(_SUPPORT_RE.search(text))
    needs_description = bool(_DESCRIPTION_RE.search(text))
    needs_pattern_coupon_lookup = bool(has_product_hint and _PATTERN_COUPON_RE.search(text))

    if needs_support and not has_product_hint:
        return CrossDomainPlan(
            primary_domain=PolicyDomain.SUPPORT,
            subtasks=(
                DomainSubtask(
                    domain=PolicyDomain.SUPPORT,
                    intent="policy_notice_or_escalation",
                    reason="정책 안내 또는 1:1 문의 연결이 필요함",
                ),
            ),
            response_strategy="single_domain_response",
        )

    if has_product_hint and not needs_pattern_coupon_lookup and (needs_description or not slots.get("goods_no")):
        subtasks.append(
            DomainSubtask(
                domain=PolicyDomain.DISCOVERY,
                intent="resolve_or_describe_product",
                reason="상품명/상품 속성 확인이 먼저 필요함",
                required_slots=() if slots.get("goods_no") else ("product",),
            )
        )

    if needs_pattern_coupon_lookup:
        subtasks.append(
            DomainSubtask(
                domain=PolicyDomain.TRANSACTION,
                intent="coupon_pattern_applicability",
                reason="패턴 기준 쿠폰은 규격 상품 검색보다 보유 쿠폰과 적용 패턴 확인이 우선임",
            )
        )
    elif needs_price:
        depends_on = ("resolve_or_describe_product",) if not slots.get("goods_no") and has_product_hint else ()
        subtasks.append(
            DomainSubtask(
                domain=PolicyDomain.TRANSACTION,
                intent="price_or_coupon_check",
                reason="가격/쿠폰은 Transaction tool 결과가 필요함",
                required_slots=("goods_no",) if not slots.get("goods_no") and has_product_hint else (),
                depends_on=depends_on,
            )
        )

    if needs_stock_or_booking:
        depends_on = ("resolve_or_describe_product",) if not slots.get("goods_no") and has_product_hint else ()
        required_slots: list[str] = []
        if has_product_hint and not slots.get("goods_no"):
            required_slots.append("goods_no")
        if has_product_hint and not slots.get("goods_no") and not tire_size:
            required_slots.append("tire_size")
        if has_product_hint and not (slots.get("quantity") or slots.get("ord_qty")):
            required_slots.append("quantity")
        if needs_stock_or_booking and not (slots.get("region") or slots.get("shop_id") or slots.get("lat")):
            required_slots.append("location")
        subtasks.append(
            DomainSubtask(
                domain=PolicyDomain.TRANSACTION,
                intent="stock_store_or_reservation",
                reason="재고/매장/예약은 Transaction tool 결과가 필요함",
                required_slots=tuple(required_slots),
                depends_on=depends_on,
            )
        )

    if needs_support:
        subtasks.append(
            DomainSubtask(
                domain=PolicyDomain.SUPPORT,
                intent="policy_notice_or_escalation",
                reason="정책 안내 또는 1:1 문의 연결이 필요함",
            )
        )

    if not subtasks:
        domain = PolicyDomain.DISCOVERY if has_product_hint else PolicyDomain.UNKNOWN
        subtasks.append(DomainSubtask(domain=domain, intent="single_domain", reason="단일 도메인 처리 가능"))

    primary = subtasks[0].domain
    if any(task.domain == PolicyDomain.SUPPORT for task in subtasks) and not has_product_hint:
        primary = PolicyDomain.SUPPORT
    elif any(task.domain == PolicyDomain.TRANSACTION for task in subtasks) and not needs_description:
        primary = PolicyDomain.TRANSACTION

    strategy = "ordered_tool_chain_then_single_response" if len(subtasks) > 1 else "single_domain_response"
    return CrossDomainPlan(primary_domain=primary, subtasks=tuple(subtasks), response_strategy=strategy)


def _normalize_tire_size(text: str) -> str | None:
    match = _SIZE_COMPACT_RE.search(text or "")
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}R{match.group(3)}"
