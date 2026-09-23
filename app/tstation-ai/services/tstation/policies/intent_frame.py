"""Common intent frame contracts for deterministic policy modules.

Integration note:
    Future chat/base-agent/template-mapper wiring should build an ``IntentFrame``
    before domain policies run. This module intentionally does not classify
    Discovery or Transaction intents; it only defines the shared payload shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping


class PolicyDomain(str, Enum):
    """High-level policy domain names shared by domain-specific modules."""

    LEADING = "leading"
    DISCOVERY = "discovery"
    TRANSACTION = "transaction"
    SUPPORT = "support"
    UI_TEMPLATE = "ui_template"
    QC = "qc"
    UNKNOWN = "unknown"


class SlotStatus(str, Enum):
    """Slot confidence state used before a tool plan is decided."""

    KNOWN = "known"
    CANDIDATE = "candidate"
    MISSING = "missing"


@dataclass(frozen=True)
class SlotValue:
    """Normalized slot value with provenance.

    ``source`` is deliberately free-form so callers can record values like
    ``user_text``, ``session_state``, ``template_payload``, or ``tool_result``.
    """

    name: str
    value: Any
    status: SlotStatus = SlotStatus.KNOWN
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "status": self.status.value,
            "source": self.source,
        }


@dataclass(frozen=True)
class IntentFrame:
    """Policy input frame produced before domain-specific tool/response rules."""

    domain: PolicyDomain
    intent: str
    sub_intent: str | None = None
    entities: Mapping[str, Any] = field(default_factory=dict)
    known_slots: Mapping[str, Any] = field(default_factory=dict)
    missing_slots: tuple[str, ...] = ()
    candidate_slots: Mapping[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    source: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def unknown(cls, *, source: str | None = None) -> "IntentFrame":
        return cls(domain=PolicyDomain.UNKNOWN, intent="unknown", source=source)

    def with_slots(
        self,
        *,
        known_slots: Mapping[str, Any] | None = None,
        missing_slots: tuple[str, ...] | list[str] | None = None,
        candidate_slots: Mapping[str, Any] | None = None,
    ) -> "IntentFrame":
        return replace(
            self,
            known_slots={**dict(self.known_slots), **dict(known_slots or {})},
            missing_slots=tuple(missing_slots) if missing_slots is not None else self.missing_slots,
            candidate_slots={**dict(self.candidate_slots), **dict(candidate_slots or {})},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain.value,
            "intent": self.intent,
            "sub_intent": self.sub_intent,
            "entities": dict(self.entities),
            "known_slots": dict(self.known_slots),
            "missing_slots": list(self.missing_slots),
            "candidate_slots": dict(self.candidate_slots),
            "confidence": self.confidence,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


def normalize_domain(value: str | PolicyDomain | None) -> PolicyDomain:
    """Convert classifier/profile domain text into the shared enum."""

    if isinstance(value, PolicyDomain):
        return value
    normalized = str(value or "").strip().lower()
    aliases = {
        "lead": PolicyDomain.LEADING,
        "leading_agent": PolicyDomain.LEADING,
        "discovery_agent": PolicyDomain.DISCOVERY,
        "transaction_agent": PolicyDomain.TRANSACTION,
        "support_agent": PolicyDomain.SUPPORT,
        "template": PolicyDomain.UI_TEMPLATE,
        "ui": PolicyDomain.UI_TEMPLATE,
        "qc_agent": PolicyDomain.QC,
    }
    if normalized in aliases:
        return aliases[normalized]
    for domain in PolicyDomain:
        if normalized == domain.value:
            return domain
    return PolicyDomain.UNKNOWN

