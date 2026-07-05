"""Normalize router action/entity candidates into stable policy evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from services.tstation.policies.router_intent_schema import canonical_router_intent


_ENTITY_CONFIDENCE_THRESHOLD = 0.5
_ROUTER_SLOT_SOURCE = "router_evidence"


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
    raw_router_intent = _router_intent(routing_result, execution_plan)
    router_intent = canonical_router_intent(raw_router_intent)
    raw_policy_intent = str(getattr(routing_result, "policy_intent", "") or "").strip()
    policy_intent = canonical_router_intent(raw_policy_intent)
    entities = _normalized_entities(getattr(routing_result, "entity_candidates", None))
    entities = _merge_regex_supplemental(entities, regex_candidates or {})
    confidence = getattr(routing_result, "planner_confidence", None)

    evidence: dict[str, Any] = {
        "domain": router_domain,
        "intent": router_intent,
        "raw_intent": raw_router_intent,
        "primary_action": primary_action,
        "policy_intent": policy_intent,
        "raw_policy_intent": raw_policy_intent,
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


def router_evidence_known_slots(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    """Flatten RouterEvidence into policy slot names without choosing a tool.

    Confirmed flow state and UI actions should be merged before this helper is
    applied. Callers can then let router-derived candidates fill only empty
    policy slots while preserving the source map for trace/debugging.
    """

    raw = _mapping(evidence)
    if not raw:
        return {}
    entities = _mapping(raw.get("entities"))
    primary_action = _text(raw.get("primary_action"))
    slot_sources: dict[str, str] = {}
    slots: dict[str, Any] = {}

    def put(key: str, value: Any) -> None:
        if value in (None, "", [], {}):
            return
        slots[key] = value
        slot_sources[key] = _ROUTER_SLOT_SOURCE

    registered_vehicle = _mapping(entities.get("registered_vehicle"))
    registered_anchor = _text(registered_vehicle.get("anchor") or registered_vehicle.get("name"))
    if registered_anchor:
        put("named_registered_vehicle_anchor", registered_anchor)
        if primary_action in {"recommend", "compare"}:
            put("discovery_followup_action", "vehicle_resolved_recommendation")

    store = _mapping(entities.get("store"))
    store_name = _text(store.get("name") or store.get("anchor"))
    if store_name:
        put("store_name_candidate", store_name)
        put("store_name", store_name)
        put("shop_name", store_name)

    coupon = _mapping(entities.get("coupon"))
    coupon_name = _text(coupon.get("name") or coupon.get("anchor"))
    if coupon_name:
        put("coupon_name_candidate", coupon_name)
        put("coupon_name", coupon_name)

    benefit = _mapping(entities.get("benefit"))
    benefit_name = _text(benefit.get("name") or benefit.get("anchor"))
    benefit_type = _text(benefit.get("type"))
    if benefit_name:
        put("benefit_applicable_products_query", benefit_name)
        put("benefit_name_candidate", benefit_name)
    if benefit_type:
        put("benefit_type_candidate", benefit_type)

    location = _mapping(entities.get("location"))
    location_name = _text(location.get("name") or location.get("anchor"))
    location_type = _text(location.get("type"))
    if location_name:
        put("location_name", location_name)
        put("place_query", location_name)
    if location_type:
        put("location_type", location_type)

    if primary_action and primary_action != "none":
        put("router_primary_action", primary_action)
    if slot_sources:
        slots["slot_sources"] = slot_sources
    return slots


def router_place_slot_patch(
    evidence: Mapping[str, Any] | None,
    *,
    expected_slot: str | None = None,
) -> dict[str, Any]:
    """Return current-turn place slot patch from router entities only.

    This intentionally ignores regex/free-text fallback. During store or region
    slot-fill, the router's current-turn location/store entity is the authority
    unless a structured UI action already supplied a slot patch.
    """

    raw = _mapping(evidence)
    entities = _mapping(raw.get("entities"))
    expected = _text(expected_slot)
    store = _mapping(entities.get("store"))
    location = _mapping(entities.get("location"))
    store_name = _entity_name_if_confident(store)
    location_name = _entity_name_if_confident(location)
    if expected == "store" and store_name:
        return {"shop_name": store_name}
    if expected in {"region", "place"} and location_name:
        return {"region": location_name, "place_query": location_name}
    if store_name:
        return {"shop_name": store_name}
    if location_name:
        return {"region": location_name, "place_query": location_name}
    return {}


def merge_router_evidence_known_slots(
    known_slots: Mapping[str, Any] | None,
    evidence: Mapping[str, Any] | None,
    *,
    preserve_existing: bool = True,
) -> dict[str, Any]:
    """Merge RouterEvidence slots under the fixed priority order.

    Existing slots represent UI action/confirmed flow state or older confirmed
    session slots, so router candidates fill gaps by default. Regex candidates
    should run after this merge and therefore must not overwrite these keys.
    """

    merged = dict(known_slots or {})
    router_slots = router_evidence_known_slots(evidence)
    if not router_slots:
        return _drop_empty(merged)
    merged_sources = _mapping(merged.get("slot_sources"))
    router_sources = _mapping(router_slots.get("slot_sources"))
    for key, value in router_slots.items():
        if key == "slot_sources":
            continue
        if preserve_existing and merged.get(key) not in (None, "", [], {}):
            continue
        merged[key] = value
        source = router_sources.get(key)
        if source:
            merged_sources[key] = source
    if merged_sources:
        merged["slot_sources"] = merged_sources
    return _drop_empty(merged)


def _entity_name_if_confident(entity: Mapping[str, Any] | None) -> str:
    data = _mapping(entity)
    try:
        confidence = float(data.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < _ENTITY_CONFIDENCE_THRESHOLD:
        return ""
    return _text(data.get("name") or data.get("anchor"))


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
    for entity_name in ("registered_vehicle", "store", "coupon", "benefit", "location"):
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
        if entity_name in {"store", "coupon", "benefit", "location"} and not normalized["name"]:
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
