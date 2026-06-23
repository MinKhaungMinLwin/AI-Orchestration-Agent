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
_STOCK_OR_BOOKING_RE = re.compile(
    r"재고|오늘\s*장착|당일\s*장착|장착\s*가능|예약|오늘\s*서비스|오늘서비스|당일\s*서비스",
    re.IGNORECASE,
)
_PURCHASE_RE = re.compile(r"구매|주문|결제|살래|살게|사고\s*싶|사려고", re.IGNORECASE)
_STORE_SEARCH_RE = re.compile(r"매장|지점|티스테이션|더타이어샵|근처|주변|찾아|알려|보여", re.IGNORECASE)
_FAVORITE_STORE_RE = re.compile(
    r"내\s*단골(?:매장|가게|점)?|단골(?:매장|가게|점)|마이샵|자주\s*가는\s*매장",
    re.IGNORECASE,
)
_STORE_NAME_RE = re.compile(r"([가-힣A-Za-z0-9]+(?:점|매장))")
_REGION_HINT_RE = re.compile(
    r"서울|서초|강남|판교|분당|파주|강릉|부산|광교|성남|오목천|동광주|송파|한남|"
    r"청량리|인천|하남|청주|제주|서귀포",
    re.IGNORECASE,
)
_PRICE_OR_COUPON_RE = re.compile(r"가격|할인가|최대\s*혜택|쿠폰|할인", re.IGNORECASE)
_REGIONAL_PRICE_POLICY_RE = re.compile(
    r"(?=.*(?:가격|판매가|최종가))"
    r"(?=.*(?:똑같|같(?:아|은|나요|을까)?|동일|다르|차이|왜))"
    r"(?=.*(?:제주(?:도|특별자치도)?|서귀포(?:시)?|도서산간|서울|부산|대구|인천|광주|대전|울산|지역|매장|지점))",
    re.IGNORECASE,
)
_PATTERN_COUPON_KEYWORD = r"패밀리|family|생일|birthday|임직원|employee|직원"
_PATTERN_COUPON_RE = re.compile(
    rf"(?:{_PATTERN_COUPON_KEYWORD}).{{0,20}}(?:쿠폰|할인권)|"
    rf"(?:쿠폰|할인권).{{0,20}}(?:{_PATTERN_COUPON_KEYWORD})",
    re.IGNORECASE,
)
_SUPPORT_RE = re.compile(
    r"만료|원복|상담원|고객센터|1:1|문의|불만|클레임|공기압|TPMS|티피엠에스|경고등",
    re.IGNORECASE,
)
_DESCRIPTION_RE = re.compile(r"뭐야|뭔지|설명|차이|장점|왜|등급|연비|소음|마일리지|최신", re.IGNORECASE)
_COMPARISON_SIGNAL_RE = re.compile(r"비교|차이|중(?:에|에서는)|뭐가\s*달라|무슨\s*차이", re.IGNORECASE)
_SIZE_COMPACT_RE = re.compile(r"\b(\d{3})\s*/?\s*(\d{2})\s*R?\s*(\d{2})\b", re.IGNORECASE)
_WARRANTY_CLAIM_WEAR_RE = re.compile(
    r"다\s*닳|빨리\s*닳|벌써\s*닳|조기\s*마모|편마모|마모|수명|하자|문제|이상|불량|품질|"
    r"광고(?:랑|와)?\s*다르|말(?:한|하던)\s*거(?:랑)?\s*다르",
    re.IGNORECASE,
)
_WARRANTY_CLAIM_REMEDY_RE = re.compile(
    r"무료\s*교체|무상\s*교환|무상\s*교체|보상(?:해|받|되|돼|가능)?|교체(?:해|받|되|돼)?|"
    r"바꿔|바꾸|책임(?:져|지)|환불|클레임",
    re.IGNORECASE,
)
_WARRANTY_CLAIM_REFERENCE_RE = re.compile(
    r"보증|워런티|warranty|품질\s*보증|품질보증|안심\s*서비스|안심서비스|안심\s*플러스|"
    r"\d+\s*만\s*(?:키로|km|킬로)|몇\s*만\s*(?:키로|km|킬로)",
    re.IGNORECASE,
)
_WARRANTY_CLAIM_STRONG_RE = re.compile(
    r"무료\s*교체|무상\s*교환|무상\s*교체|보상\s*해\s*줘|보상해줘|책임\s*져|책임져|"
    r"하자\s*아니|클레임|품질\s*보증|품질보증",
    re.IGNORECASE,
)


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


def is_warranty_claim_signal(user_text: str, *, known_slots: dict[str, Any] | None = None) -> bool:
    """Return true for product warranty/claim complaints, not general product info.

    The signal is intentionally conjunctive so ordinary description/recommendation
    turns such as "마일리지 좋은 타이어 추천" stay in Discovery. A strong claim
    phrase can stand on its own; otherwise require product context plus at least
    two claim dimensions.
    """
    text = user_text or ""
    slots = known_slots or {}
    has_product_hint = bool(_PRODUCT_HINT_RE.search(text) or slots.get("product_name") or slots.get("goods_no"))
    if not text:
        return False
    if has_product_hint and _WARRANTY_CLAIM_REFERENCE_RE.search(text):
        return True
    if has_product_hint and _WARRANTY_CLAIM_STRONG_RE.search(text):
        return True

    score = 0
    if _WARRANTY_CLAIM_WEAR_RE.search(text):
        score += 1
    if _WARRANTY_CLAIM_REMEDY_RE.search(text):
        score += 1
    if _WARRANTY_CLAIM_REFERENCE_RE.search(text):
        score += 1
    return has_product_hint and score >= 2


def plan_cross_domain_turn(user_text: str, *, known_slots: dict[str, Any] | None = None) -> CrossDomainPlan:
    """Plan ordered domain subtasks for a multi-intent user turn."""
    text = user_text or ""
    slots = known_slots or {}
    subtasks: list[DomainSubtask] = []

    has_current_product_hint = bool(_PRODUCT_HINT_RE.search(text))
    has_product_hint = bool(has_current_product_hint or slots.get("product_name") or slots.get("goods_no"))
    tire_size = slots.get("tire_size") or _normalize_tire_size(text)
    needs_store_search = bool(_STORE_SEARCH_RE.search(text))
    needs_favorite_store_lookup = bool(_FAVORITE_STORE_RE.search(text))
    needs_price = bool(_PRICE_OR_COUPON_RE.search(text))
    needs_support = bool(_SUPPORT_RE.search(text))
    needs_description = bool(_DESCRIPTION_RE.search(text))
    needs_pattern_coupon_lookup = bool(has_product_hint and _PATTERN_COUPON_RE.search(text))
    needs_regional_price_policy = bool(_REGIONAL_PRICE_POLICY_RE.search(text))
    has_current_store = bool(_STORE_NAME_RE.search(text) or _REGION_HINT_RE.search(text))
    needs_stock_or_booking = bool(_STOCK_OR_BOOKING_RE.search(text) or (_PURCHASE_RE.search(text) and has_current_store))
    has_warranty_claim_signal = is_warranty_claim_signal(text, known_slots=slots)
    has_product_comparison_signal = (
        len(tuple(_PRODUCT_HINT_RE.finditer(text))) >= 2
        and bool(_COMPARISON_SIGNAL_RE.search(text))
        and not needs_stock_or_booking
    )

    if has_product_comparison_signal:
        return CrossDomainPlan(
            primary_domain=PolicyDomain.DISCOVERY,
            subtasks=(
                DomainSubtask(
                    domain=PolicyDomain.DISCOVERY,
                    intent="product_comparison",
                    reason="두 개 이상 상품명과 비교/차이 신호가 있어 단일 상품 설명으로 축소하지 않음",
                ),
            ),
            response_strategy="single_domain_response",
        )

    if needs_regional_price_policy:
        return CrossDomainPlan(
            primary_domain=PolicyDomain.SUPPORT,
            subtasks=(
                DomainSubtask(
                    domain=PolicyDomain.SUPPORT,
                    intent="price_policy_faq",
                    reason="지역/매장별 가격 동일 여부는 실제 가격 조회가 아닌 가격 정책 FAQ임",
                ),
            ),
            response_strategy="single_domain_response",
        )

    if has_warranty_claim_signal:
        return CrossDomainPlan(
            primary_domain=PolicyDomain.SUPPORT,
            subtasks=(
                DomainSubtask(
                    domain=PolicyDomain.SUPPORT,
                    intent="warranty_claim",
                    reason="상품명과 조기 마모/품질 불만/보상 요구가 결합된 워런티 클레임임",
                ),
            ),
            response_strategy="single_domain_response",
        )

    current_turn_is_plain_store_search = (
        needs_store_search and not needs_favorite_store_lookup and not needs_stock_or_booking and not needs_price
    )

    if needs_support and not has_current_product_hint and not needs_stock_or_booking:
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

    if needs_favorite_store_lookup and not has_current_product_hint and not needs_stock_or_booking and not needs_price:
        return CrossDomainPlan(
            primary_domain=PolicyDomain.TRANSACTION,
            subtasks=(
                DomainSubtask(
                    domain=PolicyDomain.TRANSACTION,
                    intent="favorite_store_lookup",
                    reason="현재 발화는 지역 검색이 아니라 사용자의 단골매장 조회임",
                    required_slots=(),
                ),
            ),
            response_strategy="single_domain_response",
        )

    if current_turn_is_plain_store_search and not has_current_product_hint:
        return CrossDomainPlan(
            primary_domain=PolicyDomain.TRANSACTION,
            subtasks=(
                DomainSubtask(
                    domain=PolicyDomain.TRANSACTION,
                    intent="store_search",
                    reason="현재 발화는 상품 재고/예약이 아닌 일반 매장 검색임",
                    required_slots=() if (slots.get("region") or slots.get("store_name") or slots.get("shop_id")) else ("location",),
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
        if needs_stock_or_booking and not (
            has_current_store
            or slots.get("region")
            or slots.get("store_name")
            or slots.get("shop_id")
            or slots.get("lat")
        ):
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
