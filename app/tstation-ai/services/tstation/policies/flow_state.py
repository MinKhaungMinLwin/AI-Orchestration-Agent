from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


_EMPTY_VALUES = (None, "", [], {})

_PRODUCT_FIELDS = ("goods_no", "product_name", "tire_model", "pending_product_name", "tire_size", "ord_qty")
_STORE_FIELDS = ("region", "shop_id", "shop_name")
_SCHEDULE_FIELDS = ("requested_cal_day", "rsv_hour")
_PAYMENT_FIELDS = ("payment_amount", "price_basis", "price_source_tool", "payment_amount_stale")
_INTENT_FIELDS = ("pending_intent", "goal_type", "stock_check_mode", "schedule_mode", "availability_intent")


def _non_empty_mapping(values: Mapping[str, Any] | None) -> dict[str, Any]:
    return {key: value for key, value in dict(values or {}).items() if value not in _EMPTY_VALUES}


def _normalize_product_aliases(values: dict[str, Any]) -> None:
    product_name = values.get("product_name") or values.get("tire_model") or values.get("pending_product_name")
    if product_name in _EMPTY_VALUES:
        return
    values.setdefault("product_name", product_name)
    values.setdefault("tire_model", product_name)
    values.setdefault("pending_product_name", product_name)


@dataclass(slots=True)
class FlowStateMergeResult:
    state: "FlowState"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FlowState:
    flow_type: str
    status: str = "active"
    product: dict[str, Any] = field(default_factory=dict)
    store: dict[str, Any] = field(default_factory=dict)
    schedule: dict[str, Any] = field(default_factory=dict)
    payment: dict[str, Any] = field(default_factory=dict)
    intent: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def purchase(cls, status: str = "active") -> "FlowState":
        return cls(flow_type="purchase", status=status)

    @classmethod
    def from_pending_order_context(cls, context: Mapping[str, Any] | None) -> "FlowState":
        flat = _non_empty_mapping(context)
        state = cls.purchase(status=str(flat.get("context_state") or flat.get("status") or "active"))
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
    def from_flat_delta(cls, values: Mapping[str, Any] | None, *, source: str) -> "FlowState":
        flat = _non_empty_mapping(values)
        state = cls.purchase()
        state.product = {key: flat[key] for key in _PRODUCT_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        _normalize_product_aliases(state.product)
        state.store = {key: flat[key] for key in _STORE_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.schedule = {key: flat[key] for key in _SCHEDULE_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.payment = {key: flat[key] for key in _PAYMENT_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.intent = {key: flat[key] for key in _INTENT_FIELDS if flat.get(key) not in _EMPTY_VALUES}
        state.meta = {
            key: flat[key]
            for key in ("awaiting_store_region", "pending_step")
            if flat.get(key) not in _EMPTY_VALUES
        }
        state.meta["source"] = source
        return state

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

        for section_name in ("product", "store", "schedule", "payment", "intent"):
            target = getattr(merged, section_name)
            incoming = getattr(delta, section_name)
            for key, value in incoming.items():
                if value in _EMPTY_VALUES:
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
        merged.meta["source"] = source
        merged.meta["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        merged.status = delta.status if delta.status in {"active", "dormant", "resumed"} else merged.status
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
