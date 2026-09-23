from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Mapping

from schemas.tstation.slots import ConversationSlots

_EMPTY_VALUES = (None, "", [], {})

_CANCEL_RE = re.compile(r"^(아니|아니야|취소|처음부터|다른\s*거|됐어|괜찮아)\.?$", re.IGNORECASE)
_PRICE_ANSWER_RE = re.compile(r"가격|할인|쿠폰|혜택|견적|얼마|프로모션|이벤트|행사|적립|멤버십", re.IGNORECASE)
_STOCK_ANSWER_RE = re.compile(r"재고|있는\s*곳|장착점|장착\s*가능|오늘\s*장착|당일\s*장착|매장", re.IGNORECASE)
_DESCRIPTION_ANSWER_RE = re.compile(r"성능|스펙|특징|설명|어때|괜찮|소음|승차감|마일리지|제동", re.IGNORECASE)
_PURCHASE_ANSWER_RE = re.compile(r"구매|주문|예약|진행|계속|결제", re.IGNORECASE)

_INTENT_ALIASES: dict[str, tuple[re.Pattern[str], ...]] = {
    "price_or_coupon_check": (_PRICE_ANSWER_RE,),
    "stock_store_search": (_STOCK_ANSWER_RE,),
    "store_service_search": (_STOCK_ANSWER_RE,),
    "product_description": (_DESCRIPTION_ANSWER_RE,),
    "quick_order_reservation": (_PURCHASE_ANSWER_RE,),
}

_INTENT_DOMAINS = {
    "price_or_coupon_check": "transaction",
    "stock_store_search": "transaction",
    "store_service_search": "transaction",
    "quick_order_reservation": "transaction",
    "product_description": "discovery",
}

_BASE_SLOT_KEYS = (
    "goods_no",
    "product_name",
    "tire_model",
    "pending_product_name",
    "tire_size",
    "ord_qty",
    "quantity",
    "region",
    "shop_id",
    "shop_name",
    "store_name",
    "payment_amount",
    "price_basis",
    "price_source_tool",
)


@dataclass(frozen=True)
class PendingClarificationResolution:
    status: str
    intent: str = ""
    domain: str = ""
    execution_plan: tuple[str, ...] = ()
    base_slots: dict[str, Any] = field(default_factory=dict)
    candidate: dict[str, Any] = field(default_factory=dict)
    pending_clarification: dict[str, Any] = field(default_factory=dict)
    slots: ConversationSlots | None = None
    reason: str = "none"

    @property
    def resolved(self) -> bool:
        return self.status == "resolved" and bool(self.intent)


def stage_pending_clarification(
    slots: ConversationSlots,
    *,
    user_text: str,
    routing_result: Any | None = None,
    candidates: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None = None,
    question: str | None = None,
    source_turn_id: str | None = None,
    source: str = "router_clarification",
) -> ConversationSlots:
    normalized_candidates = _normalise_candidates(candidates) or _candidates_from_router(routing_result, slots)
    if not normalized_candidates:
        return slots
    pending = {
        "status": "pending",
        "source": source,
        "source_turn_id": source_turn_id or "",
        "source_user_text": str(user_text or "").strip(),
        "question": question or _default_question(normalized_candidates),
        "candidates": normalized_candidates,
        "base_slots": _base_slots_from_slots(slots),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "remaining_turns": 1,
    }
    context = dict(slots.availability_context or {})
    context["pending_clarification"] = pending
    return slots.apply_runtime_values({"availability_context": context}, source=source)


def resolve_pending_clarification_answer(
    slots: ConversationSlots,
    *,
    user_text: str,
) -> PendingClarificationResolution:
    context = dict(slots.availability_context or {})
    pending = context.get("pending_clarification")
    if not isinstance(pending, Mapping) or pending.get("status") != "pending":
        return PendingClarificationResolution(status="not_found", slots=slots)

    if _CANCEL_RE.search(str(user_text or "").strip()):
        return PendingClarificationResolution(
            status="cleared",
            slots=_clear_pending_clarification(slots, reason="cancelled"),
            reason="cancelled",
            pending_clarification=dict(pending),
        )

    base_slots = _mapping(pending.get("base_slots"))
    if _base_context_changed(slots, base_slots):
        return PendingClarificationResolution(
            status="cleared",
            slots=_clear_pending_clarification(slots, reason="base_context_changed"),
            reason="base_context_changed",
            pending_clarification=dict(pending),
        )

    candidate = _match_candidate(str(user_text or ""), pending.get("candidates"))
    if not candidate:
        return PendingClarificationResolution(
            status="cleared",
            slots=_clear_pending_clarification(slots, reason="unrelated_answer"),
            reason="unrelated_answer",
            pending_clarification=dict(pending),
        )

    intent = str(candidate.get("intent") or "").strip()
    domain = str(candidate.get("domain") or _INTENT_DOMAINS.get(intent) or "").strip()
    execution_plan = tuple(candidate.get("execution_plan") or (f"{domain}:{intent}",))
    resolved_slots = _clear_pending_clarification(slots, reason="resolved")
    if base_slots:
        resolved_slots = resolved_slots.apply_runtime_values(base_slots, source="pending_clarification:base_slots")
    return PendingClarificationResolution(
        status="resolved",
        intent=intent,
        domain=domain,
        execution_plan=execution_plan,
        base_slots=base_slots,
        candidate=candidate,
        pending_clarification=dict(pending),
        slots=resolved_slots,
        reason="matched_candidate",
    )


def clear_pending_clarification(slots: ConversationSlots, *, reason: str) -> ConversationSlots:
    return _clear_pending_clarification(slots, reason=reason)


def _clear_pending_clarification(slots: ConversationSlots, *, reason: str) -> ConversationSlots:
    context = dict(slots.availability_context or {})
    if "pending_clarification" not in context:
        return slots
    previous = context.pop("pending_clarification", None)
    if isinstance(previous, Mapping):
        context["last_cleared_clarification"] = {
            "reason": reason,
            "intent_candidates": [
                candidate.get("intent")
                for candidate in previous.get("candidates", [])
                if isinstance(candidate, Mapping) and candidate.get("intent")
            ],
            "cleared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    return slots.apply_runtime_values({"availability_context": context}, source=f"pending_clarification:{reason}")


def _normalise_candidates(
    candidates: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for candidate in candidates or ():
        if not isinstance(candidate, Mapping):
            continue
        intent = str(candidate.get("intent") or "").strip()
        if not intent:
            continue
        domain = str(candidate.get("domain") or _INTENT_DOMAINS.get(intent) or "").strip()
        if not domain:
            continue
        label = str(candidate.get("label") or _label_for_intent(intent)).strip()
        normalized.append({
            "label": label,
            "intent": intent,
            "domain": domain,
            "execution_plan": list(candidate.get("execution_plan") or (f"{domain}:{intent}",)),
        })
    return normalized


def _candidates_from_router(routing_result: Any | None, slots: ConversationSlots) -> list[dict[str, Any]]:
    if not bool(getattr(routing_result, "needs_clarification", False)):
        return []
    base_slots = _base_slots_from_slots(slots)
    has_product_context = bool(
        base_slots.get("goods_no")
        or base_slots.get("product_name")
        or base_slots.get("tire_model")
        or base_slots.get("pending_product_name")
        or base_slots.get("tire_size")
    )
    if not has_product_context:
        return []
    candidates = [
        {"label": "가격/할인", "intent": "price_or_coupon_check", "domain": "transaction"},
        {"label": "재고", "intent": "stock_store_search", "domain": "transaction"},
        {"label": "성능", "intent": "product_description", "domain": "discovery"},
    ]
    if _has_dormant_purchase_context(slots):
        candidates.append({"label": "구매 계속", "intent": "quick_order_reservation", "domain": "transaction"})
    return _normalise_candidates(candidates)


def _match_candidate(user_text: str, raw_candidates: Any) -> dict[str, Any]:
    text = str(user_text or "").strip()
    if not text:
        return {}
    candidates = _normalise_candidates(raw_candidates if isinstance(raw_candidates, (list, tuple)) else [])
    for candidate in candidates:
        label = str(candidate.get("label") or "").strip()
        intent = str(candidate.get("intent") or "").strip()
        if label and (text == label or text in label or label in text):
            return candidate
        for pattern in _INTENT_ALIASES.get(intent, ()):
            if pattern.search(text):
                return candidate
    return {}


def _base_context_changed(slots: ConversationSlots, base_slots: Mapping[str, Any]) -> bool:
    for key in ("goods_no", "tire_size", "shop_id"):
        base_value = base_slots.get(key)
        current_value = getattr(slots, key, None)
        if base_value not in _EMPTY_VALUES and current_value not in _EMPTY_VALUES and str(base_value) != str(current_value):
            return True
    return False


def _base_slots_from_slots(slots: ConversationSlots) -> dict[str, Any]:
    values = {key: getattr(slots, key, None) for key in _BASE_SLOT_KEYS if hasattr(slots, key)}
    if values.get("product_name") in _EMPTY_VALUES and values.get("tire_model") not in _EMPTY_VALUES:
        values["product_name"] = values["tire_model"]
    if values.get("ord_qty") in _EMPTY_VALUES and values.get("quantity") not in _EMPTY_VALUES:
        values["ord_qty"] = values["quantity"]
    return {key: value for key, value in values.items() if value not in _EMPTY_VALUES}


def _has_dormant_purchase_context(slots: ConversationSlots) -> bool:
    context = slots.availability_context if isinstance(slots.availability_context, Mapping) else {}
    dormant = context.get("dormant_purchase_context")
    if isinstance(dormant, Mapping):
        return True
    dormant_flows = context.get("dormant_flows")
    return isinstance(dormant_flows, list) and bool(dormant_flows)


def _default_question(candidates: list[Mapping[str, Any]]) -> str:
    labels = [str(candidate.get("label") or "").strip() for candidate in candidates if candidate.get("label")]
    if not labels:
        return "어떤 내용을 확인할까요?"
    return f"{', '.join(labels)} 중 어떤 걸 확인할까요?"


def _label_for_intent(intent: str) -> str:
    return {
        "price_or_coupon_check": "가격/할인",
        "stock_store_search": "재고",
        "store_service_search": "매장",
        "product_description": "성능",
        "quick_order_reservation": "구매 계속",
    }.get(intent, intent)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
