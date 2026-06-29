from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Mapping


_EMPTY_VALUES = (None, "", [], {})

_PRODUCT_FIELDS = ("goods_no", "product_name", "tire_model", "pending_product_name", "tire_size", "ord_qty")
_VEHICLE_FIELDS = (
    "selection_required",
    "car_no",
    "car_lnc_cd",
    "mbr_car_reg_seq",
    "tire_size",
    "tire_size_front",
    "tire_size_rear",
    "vehicle_type",
    "car_type",
)
_RECOMMENDATION_FIELDS = (
    "scenario",
    "recommendation_scenario",
    "rcmd_type",
    "season_nm",
    "brand_cd",
    "allow_cross_brand_fill",
    "tool_args_patch",
    "expected_tool_args",
    "source_text",
    "scope",
    "fitment_source",
)
_STORE_FIELDS = ("region", "shop_id", "shop_name")
_SCHEDULE_FIELDS = ("requested_cal_day", "rsv_hour")
_PAYMENT_FIELDS = ("payment_amount", "price_basis", "price_source_tool", "payment_amount_stale")
_INTENT_FIELDS = ("pending_intent", "goal_type", "stock_check_mode", "schedule_mode", "availability_intent")
_ACTIVE_FLOW_TYPES = {"purchase", "recommendation", "stock", "booking"}
_STORE_SELECTION_CHIPS = {"이 매장 선택", "이 매장으로", "이곳 선택"}


def _non_empty_mapping(values: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(values, Mapping):
        return {}
    return {key: value for key, value in dict(values or {}).items() if value not in _EMPTY_VALUES}


def _normalize_product_aliases(values: dict[str, Any]) -> None:
    product_name = values.get("product_name") or values.get("tire_model") or values.get("pending_product_name")
    if product_name in _EMPTY_VALUES:
        return
    values.setdefault("product_name", product_name)
    values.setdefault("tire_model", product_name)
    values.setdefault("pending_product_name", product_name)


def _is_purchase_intent_group(values: Mapping[str, Any]) -> bool:
    return (
        str(values.get("pending_intent") or "").strip() == "order"
        or str(values.get("goal_type") or "").strip() == "place_order"
    )


def _is_stock_intent_group(values: Mapping[str, Any]) -> bool:
    return (
        str(values.get("pending_intent") or "").strip() == "stock"
        or str(values.get("goal_type") or "").strip() == "store_with_stock"
    )


@dataclass(slots=True)
class FlowStateMergeResult:
    state: "FlowState"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FlowState:
    flow_type: str
    status: str = "active"
    flow_step: str | None = None
    product: dict[str, Any] = field(default_factory=dict)
    vehicle: dict[str, Any] = field(default_factory=dict)
    recommendation: dict[str, Any] = field(default_factory=dict)
    store: dict[str, Any] = field(default_factory=dict)
    schedule: dict[str, Any] = field(default_factory=dict)
    payment: dict[str, Any] = field(default_factory=dict)
    intent: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def purchase(cls, status: str = "active") -> "FlowState":
        return cls(flow_type="purchase", status=status)

    @classmethod
    def from_active_flow_context(cls, context: Mapping[str, Any] | None) -> "FlowState":
        flat = _non_empty_mapping(context)
        flow_type = str(flat.get("flow_type") or "").strip()
        if flow_type not in _ACTIVE_FLOW_TYPES:
            flow_type = "purchase"
        state = cls(
            flow_type=flow_type,
            status=str(flat.get("status") or "active"),
            flow_step=str(flat.get("flow_step") or "") or None,
        )
        state.product = _section_values(flat, "product", _PRODUCT_FIELDS)
        _normalize_product_aliases(state.product)
        state.vehicle = _section_values(flat, "vehicle", _VEHICLE_FIELDS)
        state.recommendation = _section_values(flat, "recommendation", _RECOMMENDATION_FIELDS)
        state.store = _section_values(flat, "store", _STORE_FIELDS)
        state.schedule = _section_values(flat, "schedule", _SCHEDULE_FIELDS)
        state.payment = _section_values(flat, "payment", _PAYMENT_FIELDS)
        state.intent = _section_values(flat, "intent", _INTENT_FIELDS)
        state.meta = {
            key: flat[key]
            for key in ("source", "updated_at", "awaiting_store_region", "pending_step")
            if flat.get(key) not in _EMPTY_VALUES
        }
        state.candidates = _candidate_values(flat.get("last_candidates"))
        return state

    @classmethod
    def from_pending_order_context(cls, context: Mapping[str, Any] | None) -> "FlowState":
        flat = _non_empty_mapping(context)
        state = cls.purchase(status=str(flat.get("context_state") or flat.get("status") or "active"))
        state.flow_step = str(flat.get("flow_step") or flat.get("pending_step") or "") or None
        state.product = {key: flat[key] for key in _PRODUCT_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        _normalize_product_aliases(state.product)
        state.store = {key: flat[key] for key in _STORE_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.schedule = {key: flat[key] for key in _SCHEDULE_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.payment = {key: flat[key] for key in _PAYMENT_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.intent = {key: flat[key] for key in _INTENT_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.meta = {
            key: flat[key]
            for key in ("source", "updated_at", "awaiting_store_region", "pending_step")
            if flat.get(key) not in _EMPTY_VALUES
        }
        return state

    @classmethod
    def from_flat_delta(
        cls,
        values: Mapping[str, Any] | None,
        *,
        source: str,
        flow_type: str = "purchase",
        flow_step: str | None = None,
    ) -> "FlowState":
        flat = _non_empty_mapping(values)
        state = cls(flow_type=flow_type if flow_type in _ACTIVE_FLOW_TYPES else "purchase", flow_step=flow_step)
        state.product = {key: flat[key] for key in _PRODUCT_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        _normalize_product_aliases(state.product)
        state.vehicle = {key: flat[key] for key in _VEHICLE_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.recommendation = {
            key: flat[key] for key in _RECOMMENDATION_FIELDS if flat.get(key) not in _EMPTY_VALUES
        }
        state.store = {key: flat[key] for key in _STORE_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.schedule = {key: flat[key] for key in _SCHEDULE_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.payment = {key: flat[key] for key in _PAYMENT_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.intent = {key: flat[key] for key in _INTENT_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.meta = {
            key: flat[key]
            for key in ("awaiting_store_region", "pending_step")
            if flat.get(key) not in _EMPTY_VALUES
        }
        state.candidates = _candidate_values(flat.get("last_candidates"))
        state.meta["source"] = source
        return state

    def to_active_flow_context(self) -> dict[str, Any]:
        context: dict[str, Any] = {
            "flow_type": self.flow_type,
            "status": self.status,
            "updated_at": str(
                self.meta.get("updated_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
            ),
        }
        if self.flow_step:
            context["flow_step"] = self.flow_step
        for section_name in (
            "product",
            "vehicle",
            "recommendation",
            "store",
            "schedule",
            "payment",
            "intent",
        ):
            values = _non_empty_mapping(getattr(self, section_name))
            if values:
                context[section_name] = values
        if self.meta.get("source") not in _EMPTY_VALUES:
            context["source"] = self.meta["source"]
        if self.candidates:
            context["last_candidates"] = [dict(candidate) for candidate in self.candidates]
        return _non_empty_mapping(context)

    def to_pending_order_context(self) -> dict[str, Any]:
        flat: dict[str, Any] = {}
        for section in (self.product, self.store, self.schedule, self.payment, self.intent, self.meta):
            flat.update(_non_empty_mapping(section))
        flat["source"] = str(self.meta.get("source") or flat.get("source") or "")
        flat["status"] = self.status
        flat["flow_type"] = self.flow_type
        flat["updated_at"] = str(
            self.meta.get("updated_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
        )
        return _non_empty_mapping(flat)

    def merge(self, delta: "FlowState", *, source: str) -> FlowStateMergeResult:
        if self.flow_type != "purchase" or delta.flow_type != "purchase":
            return self._merge_active(delta, source=source)
        before = self.to_pending_order_context()
        merged = FlowState.from_pending_order_context(before)
        committed_fields: list[str] = []
        preserved_fields: list[str] = []
        cleared_fields: list[str] = []
        conflicts: dict[str, dict[str, Any]] = {}

        existing_goods_no = str(merged.product.get("goods_no") or "").strip()
        incoming_goods_no = str(delta.product.get("goods_no") or "").strip()
        product_changed = bool(existing_goods_no and incoming_goods_no and existing_goods_no != incoming_goods_no)
        if product_changed:
            conflicts["goods_no"] = {"existing": existing_goods_no, "incoming": incoming_goods_no}
            cleared_fields.extend(_clear_section(merged.store))
            cleared_fields.extend(_clear_section(merged.schedule))
            cleared_fields.extend(_clear_section(merged.payment))

        existing_shop_id = str(merged.store.get("shop_id") or "").strip()
        incoming_shop_id = str(delta.store.get("shop_id") or "").strip()
        if existing_shop_id and incoming_shop_id and existing_shop_id != incoming_shop_id:
            conflicts["shop_id"] = {"existing": existing_shop_id, "incoming": incoming_shop_id}
            cleared_fields.extend(_clear_section(merged.schedule))
            cleared_fields.extend(_clear_section(merged.payment))

        existing_region = str(merged.store.get("region") or "").strip()
        incoming_region = str(delta.store.get("region") or "").strip()
        if existing_region and incoming_region and existing_region != incoming_region and not delta.store.get("shop_id"):
            cleared_fields.extend(_clear_section(merged.schedule))
            cleared_fields.extend(_clear_section(merged.payment))
            for field_name in ("shop_id", "shop_name"):
                if merged.store.pop(field_name, None) not in _EMPTY_VALUES:
                    cleared_fields.append(field_name)

        qty_changed = _quantity_changed(merged.product.get("ord_qty"), delta.product.get("ord_qty"))
        if qty_changed and delta.payment.get("payment_amount") in _EMPTY_VALUES:
            cleared_fields.extend(_clear_section(merged.payment))
            merged.payment["payment_amount_stale"] = True
            committed_fields.append("payment_amount_stale")

        preserve_purchase_intent = _is_purchase_intent_group(merged.intent) and _is_stock_intent_group(delta.intent)

        for section_name in ("product", "store", "schedule", "payment", "intent"):
            target = getattr(merged, section_name)
            incoming = getattr(delta, section_name)
            for key, value in incoming.items():
                if value in _EMPTY_VALUES:
                    continue
                if preserve_purchase_intent and section_name == "intent" and key in {
                    "pending_intent",
                    "goal_type",
                    "stock_check_mode",
                }:
                    preserved_fields.append(key)
                    continue
                if target.get(key) not in _EMPTY_VALUES and target.get(key) == value:
                    preserved_fields.append(key)
                    continue
                target[key] = value
                committed_fields.append(key)

        if merged.payment.get("payment_amount") not in _EMPTY_VALUES:
            merged.payment.pop("payment_amount_stale", None)
        _normalize_product_aliases(merged.product)
        merged.meta.update(_non_empty_mapping(delta.meta))
        if delta.candidates:
            merged.candidates = [dict(candidate) for candidate in delta.candidates]
            committed_fields.append("last_candidates")
        merged.meta["source"] = source
        merged.meta["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        merged.status = (
            delta.status if delta.status in {"active", "dormant", "resumed", "completed"} else merged.status
        )
        after = merged.to_pending_order_context()

        return FlowStateMergeResult(
            state=merged,
            metadata={
                "slot_commit_event": source,
                "committed_fields": sorted(dict.fromkeys(committed_fields)),
                "preserved_fields": sorted(dict.fromkeys(preserved_fields)),
                "cleared_fields": sorted(dict.fromkeys(cleared_fields)),
                "flow_state_before": before,
                "flow_state_delta": delta.to_pending_order_context(),
                "flow_state_after": after,
                "flow_state_commit_source": source,
                "flow_state_conflicts": conflicts,
                "payment_amount_stale": bool(after.get("payment_amount_stale")),
            },
        )

    def _merge_active(self, delta: "FlowState", *, source: str) -> FlowStateMergeResult:
        before = self.to_active_flow_context()
        merged = FlowState.from_active_flow_context(before)
        committed_fields: list[str] = []
        preserved_fields: list[str] = []
        conflicts: dict[str, dict[str, Any]] = {}

        if delta.flow_type and merged.flow_type != delta.flow_type:
            conflicts["flow_type"] = {"existing": merged.flow_type, "incoming": delta.flow_type}
            merged = FlowState(flow_type=delta.flow_type, status=delta.status, flow_step=delta.flow_step)
            committed_fields.append("flow_type")
        elif delta.flow_step:
            merged.flow_step = delta.flow_step
            committed_fields.append("flow_step")

        for section_name in (
            "product",
            "vehicle",
            "recommendation",
            "store",
            "schedule",
            "payment",
            "intent",
        ):
            target = getattr(merged, section_name)
            incoming = getattr(delta, section_name)
            for key, value in incoming.items():
                if value in _EMPTY_VALUES:
                    continue
                if target.get(key) == value:
                    preserved_fields.append(key)
                    continue
                target[key] = value
                committed_fields.append(key)

        if delta.candidates:
            merged.candidates = [dict(candidate) for candidate in delta.candidates]
            committed_fields.append("last_candidates")
        merged.meta.update(_non_empty_mapping(delta.meta))
        merged.meta["source"] = source
        merged.meta["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        merged.status = (
            delta.status if delta.status in {"active", "dormant", "resumed", "completed"} else merged.status
        )
        after = merged.to_active_flow_context()
        return FlowStateMergeResult(
            state=merged,
            metadata={
                "slot_commit_event": source,
                "committed_fields": sorted(dict.fromkeys(committed_fields)),
                "preserved_fields": sorted(dict.fromkeys(preserved_fields)),
                "cleared_fields": [],
                "flow_state_before": before,
                "flow_state_delta": delta.to_active_flow_context(),
                "flow_state_after": after,
                "flow_state_commit_source": source,
                "flow_state_conflicts": conflicts,
                "payment_amount_stale": False,
            },
        )


def is_purchase_flow_context(*contexts: Mapping[str, Any] | None) -> bool:
    for context in contexts:
        values = _non_empty_mapping(context)
        if values.get("flow_type") == "purchase":
            return True
        if values.get("pending_intent") == "order" or values.get("goal_type") == "place_order":
            return True
    return False


def commit_purchase_flow_state(
    existing_context: Mapping[str, Any] | None,
    delta: Mapping[str, Any] | None,
    *,
    source: str,
    status: str = "active",
) -> FlowStateMergeResult:
    existing_state = FlowState.from_pending_order_context(existing_context)
    delta_state = FlowState.from_flat_delta(delta, source=source)
    delta_state.status = status
    return existing_state.merge(delta_state, source=source)


def commit_flow_state(
    existing_context: Mapping[str, Any] | None,
    delta: Mapping[str, Any] | None,
    *,
    source: str,
    flow_type: str,
    flow_step: str | None = None,
    status: str = "active",
) -> FlowStateMergeResult:
    existing_state = FlowState.from_active_flow_context(existing_context)
    delta_state = FlowState.from_flat_delta(delta, source=source, flow_type=flow_type, flow_step=flow_step)
    delta_state.status = status
    return existing_state.merge(delta_state, source=source)


def latest_router_evidence(
    routing_result: Any | None,
    *,
    domains: tuple[Any, ...] | list[Any] | None = None,
    source: str = "llm_router",
) -> dict[str, Any]:
    if routing_result is None:
        return {}
    execution_plan = tuple(
        str(item or "").strip()
        for item in tuple(getattr(routing_result, "execution_plan", ()) or ())
        if str(item or "").strip()
    )
    router_intent = _router_current_turn_intent(routing_result, execution_plan)
    router_domain = _router_current_turn_domain(routing_result, domains, execution_plan)
    if not router_intent and not router_domain:
        return {}
    confidence = getattr(routing_result, "planner_confidence", None)
    evidence: dict[str, Any] = {
        "domain": router_domain,
        "intent": router_intent,
        "policy_intent": str(getattr(routing_result, "policy_intent", "") or "").strip(),
        "execution_plan": list(execution_plan),
        "flow": str(getattr(routing_result, "flow", "") or "").strip(),
        "source": source,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if confidence not in _EMPTY_VALUES:
        evidence["confidence"] = confidence
    return _non_empty_mapping(evidence)


def apply_latest_router_evidence(
    slots: Any,
    routing_result: Any | None,
    *,
    domains: tuple[Any, ...] | list[Any] | None = None,
    source: str = "llm_router",
) -> tuple[Any, dict[str, Any]]:
    evidence = latest_router_evidence(routing_result, domains=domains, source=source)
    return apply_router_evidence_snapshot(slots, evidence, source=source)


def apply_router_evidence_snapshot(
    slots: Any,
    evidence: Mapping[str, Any] | None,
    *,
    source: str = "llm_router",
) -> tuple[Any, dict[str, Any]]:
    evidence = _non_empty_mapping(evidence)
    if not evidence:
        return slots, {}
    availability_context = (
        dict(slots.availability_context)
        if isinstance(getattr(slots, "availability_context", None), Mapping)
        else {}
    )
    previous_evidence = availability_context.get("latest_router_evidence")
    availability_context["latest_router_evidence"] = evidence
    if hasattr(slots, "availability_context"):
        slots.availability_context = availability_context
    return slots, {
        "latest_router_evidence_saved": True,
        "latest_router_evidence_source": source,
        "latest_router_evidence_before": (
            dict(previous_evidence) if isinstance(previous_evidence, Mapping) else {}
        ),
        "latest_router_evidence_after": evidence,
    }


def _router_current_turn_intent(routing_result: Any, execution_plan: tuple[str, ...]) -> str:
    for attr in ("intent", "slot_fill_intent", "policy_intent"):
        value = str(getattr(routing_result, attr, "") or "").strip()
        if value and value != "none":
            return value
    for item in execution_plan:
        if ":" in item:
            intent = item.split(":", 1)[1].strip()
            if intent:
                return intent
    return ""


def _router_current_turn_domain(
    routing_result: Any,
    domains: tuple[Any, ...] | list[Any] | None,
    execution_plan: tuple[str, ...],
) -> str:
    for domain in tuple(domains or ()):
        value = _domain_value(domain)
        if value:
            return value
    for domain in tuple(getattr(routing_result, "domains", ()) or ()):
        value = _domain_value(domain)
        if value:
            return value
    for item in execution_plan:
        if ":" in item:
            return item.split(":", 1)[0].strip()
    return ""


def _domain_value(domain: Any) -> str:
    value = getattr(domain, "value", domain)
    return str(value or "").strip().lower()


def stock_store_candidates_flow_delta(
    *,
    event: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        return {}
    if event.get("template") == "location":
        event_data = event.get("data") if isinstance(event.get("data"), Mapping) else {}
    elif isinstance(event.get("stores"), list):
        event_data = event
    else:
        return {}
    stores = event_data.get("stores") if isinstance(event_data, Mapping) else None
    metadata = event_data.get("metadata") if isinstance(event_data, Mapping) else None
    if not isinstance(stores, list) or not isinstance(metadata, list):
        return {}

    candidates: list[dict[str, Any]] = []
    known_slots: dict[str, Any] = {}
    for idx, meta in enumerate(metadata):
        if not isinstance(meta, Mapping):
            continue
        source_tool = str(meta.get("sourceTool") or meta.get("source_tool") or "").strip()
        if source_tool != "transaction_store_preview_tool":
            continue
        shop_id = str(meta.get("shopId") or meta.get("shop_id") or "").strip()
        if not shop_id:
            continue
        store = stores[idx] if idx < len(stores) and isinstance(stores[idx], Mapping) else {}
        candidate = _stock_store_candidate_from_metadata(store, meta)
        if not candidate:
            continue
        candidates.append(candidate)
        for key in ("goods_no", "tire_size", "ord_qty", "region", "pending_intent", "goal_type"):
            if known_slots.get(key) in _EMPTY_VALUES and candidate.get(key) not in _EMPTY_VALUES:
                known_slots[key] = candidate[key]
    if not candidates:
        return {}
    pending_intent = str(known_slots.get("pending_intent") or "").strip()
    goal_type = str(known_slots.get("goal_type") or "").strip()
    if pending_intent not in {"stock", ""} and goal_type != "store_with_stock":
        return {}
    return {
        "flow_type": "stock",
        "status": "active",
        "flow_step": "show_store_candidates",
        "stock_check_mode": "preview",
        "pending_intent": "stock",
        "goal_type": "store_with_stock",
        "last_candidates": candidates,
        **known_slots,
    }


def stock_store_candidate_selection_patch(
    *,
    active_flow_context: Mapping[str, Any] | None,
    user_text: str,
    selection_hint: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    active_flow = FlowState.from_active_flow_context(active_flow_context)
    if active_flow.flow_type != "stock" or active_flow.flow_step != "show_store_candidates":
        return {}
    if active_flow.status not in {"active", "resumed"}:
        return {}
    candidates = [candidate for candidate in active_flow.candidates if isinstance(candidate, Mapping)]
    if not candidates:
        return {}

    selected, ambiguous = _select_stock_store_candidate(
        candidates,
        user_text=user_text,
        selection_hint=_non_empty_mapping(selection_hint),
    )
    if not selected:
        return {"_stock_store_candidate_ambiguous": True} if ambiguous else {}

    patch = {
        key: selected[key]
        for key in (
            "shop_id",
            "shop_name",
            "schedule_mode",
            "schedule_tier",
            "inventory_mode",
            "source_tool",
            "goods_no",
            "tire_size",
            "ord_qty",
            "region",
            "payment_amount",
        )
        if selected.get(key) not in _EMPTY_VALUES
    }
    patch.update({
        "pending_intent": "stock",
        "goal_type": "store_with_stock",
        "stock_check_mode": "preview",
        "flow_step": "selected_store_schedule",
    })
    return patch


def recommendation_listcar_flow_delta(
    *,
    event: Mapping[str, Any] | None,
    recommendation_context: Mapping[str, Any] | None,
    recommendation_scenario: str | None = None,
    contract_intent: str | None = None,
    response_shape_key: str | None = None,
) -> dict[str, Any]:
    if not isinstance(event, Mapping) or event.get("template") != "listCar":
        return {}
    event_data = event.get("data") if isinstance(event.get("data"), Mapping) else {}
    contract_metadata = _event_contract_metadata(event_data)
    effective_response_shape_key = str(
        response_shape_key
        or contract_metadata.get("response_shape_key")
        or contract_metadata.get("responseShapeKey")
        or ""
    ).strip()
    effective_contract_intent = str(contract_intent or contract_metadata.get("contract_intent") or "").strip()
    if (
        effective_response_shape_key != "vehicle_resolved_recommendation"
        and effective_contract_intent != "vehicle_resolved_recommendation"
    ):
        return {}
    metadata = event_data.get("metadata") if isinstance(event_data, Mapping) else None
    listcar_metadata = metadata if isinstance(metadata, list) else []
    if not listcar_metadata:
        return {}
    expected_intents = {
        str(item.get("expected_contract_intent") or item.get("expectedContractIntent") or "").strip()
        for item in listcar_metadata
        if isinstance(item, Mapping)
    }
    if expected_intents and "vehicle_resolved_recommendation" not in expected_intents:
        return {}
    normalized_context = _recommendation_context_dict(recommendation_context)
    scenario = str(
        recommendation_scenario
        or normalized_context.get("recommendation_scenario")
        or normalized_context.get("scenario")
        or ""
    ).strip()
    tool_args_patch = _non_empty_mapping(normalized_context.get("tool_args_patch"))
    expected_tool_args = _non_empty_mapping(normalized_context.get("expected_tool_args"))
    if not normalized_context and not scenario and not tool_args_patch and not expected_tool_args:
        return {}

    recommendation = {
        key: value
        for key, value in {
            "scenario": scenario or None,
            "recommendation_scenario": scenario or None,
            "tool_args_patch": tool_args_patch or None,
            "expected_tool_args": expected_tool_args or None,
            "rcmd_type": tool_args_patch.get("rcmd_type") or expected_tool_args.get("rcmd_type"),
            "season_nm": tool_args_patch.get("season_nm") or expected_tool_args.get("season_nm"),
            "brand_cd": tool_args_patch.get("brand_cd") or expected_tool_args.get("brand_cd"),
            "allow_cross_brand_fill": tool_args_patch.get("allow_cross_brand_fill")
            if "allow_cross_brand_fill" in tool_args_patch
            else expected_tool_args.get("allow_cross_brand_fill"),
            "source_text": normalized_context.get("source_text"),
            "scope": normalized_context.get("scope"),
            "fitment_source": normalized_context.get("fitment_source"),
        }.items()
        if value not in _EMPTY_VALUES
    }
    return {
        "flow_type": "recommendation",
        "status": "active",
        "flow_step": "select_vehicle",
        "pending_intent": "product_recommendation",
        "goal_type": "recommend_tire",
        "selection_required": True,
        **recommendation,
    }


def recommendation_vehicle_selection_patch(
    *,
    active_flow_context: Mapping[str, Any] | None,
    selected_vehicle_slots: Mapping[str, Any] | None,
) -> dict[str, Any]:
    active_flow = FlowState.from_active_flow_context(active_flow_context)
    if active_flow.flow_type != "recommendation" or active_flow.flow_step != "select_vehicle":
        return {}
    if active_flow.status not in {"active", "resumed"}:
        return {}
    vehicle_slots = _non_empty_mapping(selected_vehicle_slots)
    tire_size = str(vehicle_slots.get("tire_size") or "").strip()
    tire_size_front = str(vehicle_slots.get("tire_size_front") or "").strip()
    tire_size_rear = str(vehicle_slots.get("tire_size_rear") or "").strip()
    if not tire_size and tire_size_front and tire_size_rear and tire_size_front != tire_size_rear:
        return {}
    car_lnc_cd = str(vehicle_slots.get("car_lnc_cd") or "").strip()
    if not tire_size and not car_lnc_cd:
        return {}

    recommendation_context = dict(active_flow.recommendation)
    tool_args_patch = _non_empty_mapping(recommendation_context.get("tool_args_patch"))
    expected_tool_args = _non_empty_mapping(recommendation_context.get("expected_tool_args"))
    scenario = str(
        recommendation_context.get("recommendation_scenario")
        or recommendation_context.get("scenario")
        or ""
    ).strip()
    if not scenario and not tool_args_patch and not expected_tool_args:
        return {}

    if tire_size:
        recommendation_context["tire_size"] = tire_size
    if car_lnc_cd:
        recommendation_context["car_lnc_cd"] = car_lnc_cd
    recommendation_context["fitment_source"] = "selected_vehicle"

    patch: dict[str, Any] = {
        "discovery_followup_action": "vehicle_based_recommendation_refinement",
        "recommendation_context": recommendation_context,
    }
    if scenario:
        patch["recommendation_scenario"] = scenario
    for key in ("tire_size", "car_lnc_cd", "vehicle_type", "car_type", "mbr_car_reg_seq", "car_no"):
        if vehicle_slots.get(key) not in _EMPTY_VALUES:
            patch[key] = vehicle_slots[key]
    for source_patch in (expected_tool_args, tool_args_patch, recommendation_context):
        for key in ("rcmd_type", "season_nm", "brand_cd", "allow_cross_brand_fill"):
            if source_patch.get(key) not in _EMPTY_VALUES:
                patch.setdefault(key, source_patch[key])
    return patch


def _candidate_values(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_non_empty_mapping(item) for item in value if isinstance(item, Mapping)]


def _stock_store_candidate_from_metadata(store: Mapping[str, Any], meta: Mapping[str, Any]) -> dict[str, Any]:
    shop_id = str(meta.get("shopId") or meta.get("shop_id") or "").strip()
    shop_name = str(
        meta.get("shopName")
        or meta.get("shop_name")
        or store.get("nameAddress")
        or store.get("name")
        or store.get("title")
        or ""
    ).strip()
    schedule_mode = str(meta.get("scheduleMode") or meta.get("schedule_mode") or "").strip()
    inventory_mode = str(meta.get("inventoryMode") or meta.get("inventory_mode") or schedule_mode or "").strip()
    if not shop_id or not schedule_mode:
        return {}
    stable_id = str(meta.get("stableId") or meta.get("stable_id") or shop_id).strip()
    candidate = {
        "type": "store",
        "stable_id": stable_id,
        "label": shop_name or shop_id,
        "shop_id": shop_id,
        "shop_name": shop_name,
        "schedule_mode": schedule_mode,
        "schedule_tier": str(meta.get("scheduleTier") or meta.get("schedule_tier") or schedule_mode).strip(),
        "inventory_mode": inventory_mode,
        "source_tool": "transaction_store_preview_tool",
        "goods_no": str(meta.get("goodsNo") or meta.get("goods_no") or "").strip(),
        "tire_size": str(meta.get("tireSize") or meta.get("tire_size") or "").strip(),
        "region": str(meta.get("region") or "").strip(),
        "pending_intent": str(meta.get("pendingIntent") or meta.get("pending_intent") or "stock").strip(),
        "goal_type": str(meta.get("goalType") or meta.get("goal_type") or "store_with_stock").strip(),
    }
    raw_qty = meta.get("ordQty") if meta.get("ordQty") not in _EMPTY_VALUES else meta.get("ord_qty")
    try:
        qty = int(raw_qty)
    except (TypeError, ValueError):
        qty = 0
    if qty > 0:
        candidate["ord_qty"] = qty
    payment_amount = meta.get("paymentAmount") if meta.get("paymentAmount") not in _EMPTY_VALUES else meta.get(
        "payment_amount"
    )
    if payment_amount not in _EMPTY_VALUES:
        candidate["payment_amount"] = payment_amount
    return _non_empty_mapping(candidate)


def _select_stock_store_candidate(
    candidates: list[Mapping[str, Any]],
    *,
    user_text: str,
    selection_hint: Mapping[str, Any],
) -> tuple[Mapping[str, Any] | None, bool]:
    hinted_id = str(
        selection_hint.get("stable_id")
        or selection_hint.get("stableId")
        or selection_hint.get("shop_id")
        or selection_hint.get("shopId")
        or selection_hint.get("entity_id")
        or ""
    ).strip()
    if hinted_id:
        exact = [
            candidate
            for candidate in candidates
            if hinted_id
            in {
                str(candidate.get("stable_id") or "").strip(),
                str(candidate.get("shop_id") or "").strip(),
            }
        ]
        if len(exact) == 1:
            return exact[0], False
        if len(exact) > 1:
            return None, True

    hinted_label = str(
        selection_hint.get("label")
        or selection_hint.get("entity_label")
        or selection_hint.get("shop_name")
        or selection_hint.get("shopName")
        or ""
    ).strip()
    text = hinted_label or str(user_text or "").strip()
    if text in _STORE_SELECTION_CHIPS and len(candidates) == 1:
        return candidates[0], False
    normalized_text = _normalize_store_label(text)
    if not normalized_text:
        return None, False

    exact_matches = [
        candidate
        for candidate in candidates
        if any(
            _normalize_store_label(value) == normalized_text
            for value in (candidate.get("label"), candidate.get("shop_name"))
            if value not in _EMPTY_VALUES
        )
    ]
    if len(exact_matches) == 1:
        return exact_matches[0], False
    if len(exact_matches) > 1:
        return None, True

    partial_matches = [
        candidate
        for candidate in candidates
        if any(
            normalized_text in _normalize_store_label(value) or _normalize_store_label(value) in normalized_text
            for value in (candidate.get("label"), candidate.get("shop_name"))
            if value not in _EMPTY_VALUES
        )
    ]
    if len(partial_matches) == 1:
        return partial_matches[0], False
    return None, len(partial_matches) > 1


def _normalize_store_label(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[\s\-_()]+", "", text)
    return text.replace("티스테이션", "").replace("tstation", "")


def _clear_section(section: dict[str, Any]) -> list[str]:
    cleared = [key for key, value in section.items() if value not in _EMPTY_VALUES]
    section.clear()
    return cleared


def _quantity_changed(existing: Any, incoming: Any) -> bool:
    if existing in _EMPTY_VALUES or incoming in _EMPTY_VALUES:
        return False
    try:
        return int(existing) != int(incoming)
    except (TypeError, ValueError):
        return False


def _section_values(flat: Mapping[str, Any], section_name: str, fields: tuple[str, ...]) -> dict[str, Any]:
    section = flat.get(section_name)
    if isinstance(section, Mapping):
        return _non_empty_mapping(section)
    return {key: flat[key] for key in fields if flat.get(key) not in _EMPTY_VALUES}


def _event_contract_metadata(event_data: Any) -> dict[str, Any]:
    if not isinstance(event_data, Mapping):
        return {}
    metadata = event_data.get("metadata")
    if isinstance(metadata, Mapping):
        return dict(metadata)
    contract_metadata = event_data.get("contractMetadata")
    if isinstance(contract_metadata, Mapping):
        return dict(contract_metadata)
    return {}


def _recommendation_context_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return _non_empty_mapping(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
        except TypeError:
            return {}
        if isinstance(dumped, Mapping):
            return _non_empty_mapping(dumped)
    return {}
