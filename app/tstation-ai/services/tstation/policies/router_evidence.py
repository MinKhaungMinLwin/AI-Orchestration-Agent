"""Normalize router action/entity candidates into stable policy evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


_ENTITY_CONFIDENCE_THRESHOLD = 0.5


def build_router_evidence(
    routing_result: Any | None,
    *,
    domains: tuple[Any, ...] | list[Any] | None = None,
    source: str = "llm_router",
    regex_candidates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact snapshot that downstream policy can prefer over regex.

    Priority encoded here:
    router entity candidates are preserved as authoritative candidate evidence;
    regex candidates are supplemental and only fill empty entity fields.
    """

    if routing_result is None:
        return {}
    execution_plan = _execution_plan(routing_result)
    primary_action = _primary_action(routing_result, execution_plan)
    router_domain = _router_domain(routing_result, domains, execution_plan)
    router_intent = _router_intent(routing_result, execution_plan)
    entities = _normalized_entities(getattr(routing_result, "entity_candidates", None))
    entities = _merge_regex_supplemental(entities, regex_candidates or {})
    confidence = getattr(routing_result, "planner_confidence", None)

    evidence: dict[str, Any] = {
        "domain": router_domain,
        "intent": router_intent,
        "primary_action": primary_action,
        "policy_intent": str(getattr(routing_result, "policy_intent", "") or "").strip(),
        "execution_plan": list(execution_plan),
        "entities": entities,
        "flow": str(getattr(routing_result, "flow", "") or "").strip(),
        "source": source,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if confidence not in (None, ""):
        evidence["confidence"] = confidence
    return _drop_empty(evidence)


def router_entities_for_trace(routing_result: Any | None) -> dict[str, dict[str, Any]]:
    entities = _normalized_entities(getattr(routing_result, "entity_candidates", None) if routing_result else None)
    trace_entities: dict[str, dict[str, Any]] = {}
    for entity_name, entity in entities.items():
        compact = {
            "anchor": entity.get("anchor") or entity.get("name"),
            "name": entity.get("name"),
            "type": entity.get("type"),
            "confidence": entity.get("confidence"),
        }
        trace_entities[entity_name] = _drop_empty(compact)
    return trace_entities


def _execution_plan(routing_result: Any) -> tuple[str, ...]:
    return tuple(
        str(item or "").strip()
        for item in tuple(getattr(routing_result, "execution_plan", ()) or ())
        if str(item or "").strip()
    )


def _primary_action(routing_result: Any, execution_plan: tuple[str, ...]) -> str:
    action = str(getattr(routing_result, "primary_action", "") or "").strip()
    if action and action != "none":
        return action
    joined = " ".join(execution_plan).lower()
    profile = str(getattr(routing_result, "agent_prompt_profile", "") or "").lower()
    if "recommend" in joined or "recommendation" in profile:
        return "recommend"
    if any(token in joined for token in ("reservation", "schedule", "booking")):
        return "reserve"
    if any(token in joined for token in ("order", "buy", "purchase", "cart")):
        return "buy"
    if "compare" in joined or str(getattr(routing_result, "comparison_metric", "") or "") not in {"", "none"}:
        return "compare"
    if "coupon" in joined or "coupon" in profile:
        return "coupon_lookup"
    if any(token in joined for token in ("search", "lookup", "info", "detail")):
        return "lookup"
    return "none"


def _router_intent(routing_result: Any, execution_plan: tuple[str, ...]) -> str:
    for attr in ("intent", "slot_fill_intent", "policy_intent"):
        value = str(getattr(routing_result, attr, "") or "").strip()
        if value and value != "none":
            return value
    for item in execution_plan:
        if ":" in item:
            _, _, intent = item.partition(":")
            if intent.strip():
                return intent.strip()
    return ""


def _router_domain(
    routing_result: Any,
    domains: tuple[Any, ...] | list[Any] | None,
    execution_plan: tuple[str, ...],
) -> str:
    for item in tuple(domains or ()):
        value = getattr(item, "value", item)
        if str(value or "").strip():
            return str(value).strip()
    result_domains = getattr(routing_result, "domains", None)
    if result_domains:
        first = result_domains[0]
        return str(getattr(first, "value", first) or "").strip()
    for item in execution_plan:
        if ":" in item:
            domain, _, _ = item.partition(":")
            return domain.strip()
    return ""


def _normalized_entities(entity_candidates: Any) -> dict[str, dict[str, Any]]:
    raw = _mapping(entity_candidates)
    entities: dict[str, dict[str, Any]] = {}
    for entity_name in ("registered_vehicle", "store", "coupon", "location"):
        entity = _mapping(raw.get(entity_name))
        if not entity:
            continue
        confidence = _confidence(entity.get("confidence"))
        if confidence < _ENTITY_CONFIDENCE_THRESHOLD:
            continue
        normalized = {
            "mentioned": bool(entity.get("mentioned")),
            "anchor": _text(entity.get("anchor")),
            "name": _text(entity.get("name")),
            "type": _text(entity.get("type")),
            "reference_text": _text(entity.get("reference_text")),
            "confidence": confidence,
            "source": "router",
        }
        if entity_name == "registered_vehicle" and not normalized["anchor"]:
            normalized["anchor"] = normalized["name"]
        if entity_name in {"store", "coupon", "location"} and not normalized["name"]:
            normalized["name"] = normalized["anchor"]
        entities[entity_name] = _drop_empty(normalized)
    return entities


def _merge_regex_supplemental(
    entities: dict[str, dict[str, Any]],
    regex_candidates: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    merged = {key: dict(value) for key, value in entities.items()}
    for entity_name, raw_candidate in regex_candidates.items():
        candidate = _mapping(raw_candidate)
        if not candidate:
            continue
        existing = merged.get(entity_name, {})
        if existing:
            continue
        value = _text(candidate.get("anchor") or candidate.get("name") or candidate.get("value"))
        if not value:
            continue
        merged[entity_name] = _drop_empty({
            "anchor": value if entity_name == "registered_vehicle" else "",
            "name": "" if entity_name == "registered_vehicle" else value,
            "type": _text(candidate.get("type")),
            "reference_text": _text(candidate.get("reference_text")),
            "confidence": _confidence(candidate.get("confidence"), default=0.4),
            "source": "regex_supplemental",
        })
    return merged


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(exclude_none=True)
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    return {}


def _confidence(value: Any, *, default: float = 0.0) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return max(0.0, min(confidence, 1.0))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _drop_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _drop_empty(item)) not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _drop_empty(item)) not in (None, "", [], {})]
    return value
