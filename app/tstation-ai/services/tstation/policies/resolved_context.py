"""Canonical turn context resolver for traceable slot source decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from pydantic import BaseModel

from schemas.tstation.slots import ConversationSlots


SOURCE_PRIORITY: tuple[str, ...] = (
    "current_turn",
    "slots",
    "tool",
    "template",
    "preorder",
    "text",
    "missing",
)
CANONICAL_CONTEXT_KEYS: frozenset[str] = frozenset({
    "goods_no",
    "product_name",
    "tire_size",
    "ord_qty",
    "shop_id",
    "shop_name",
    "region",
    "requested_cal_day",
    "rsv_hour",
})
TEMPLATE_ALIAS_KEYS: dict[str, tuple[str, ...]] = {
    "goods_no": ("goods_no", "goodsNo", "goodsId", "goods_id"),
    "product_name": ("product_name", "productName", "titleProductName", "goodsNm", "goods_nm", "goods_name"),
    "tire_size": ("tire_size", "tireSize", "titleTires"),
    "ord_qty": ("ord_qty", "ordQty", "quantity"),
    "shop_id": ("shop_id", "shopId", "storeId", "store_id"),
    "shop_name": ("shop_name", "shopName", "storeName", "store_name"),
    "region": ("region",),
    "requested_cal_day": ("requested_cal_day", "requestedCalDay", "rsvDate"),
    "rsv_hour": ("rsv_hour", "rsvHour"),
}
TOOL_ALIAS_KEYS: dict[str, tuple[str, ...]] = {
    "goods_no": ("goods_no", "goodsNo", "goodsId", "goods_id"),
    "product_name": ("product_name", "productName", "goods_nm", "goodsNm", "goods_name", "titleProductName", "title"),
    "tire_size": ("tire_size", "tire_size_1", "tireSize", "titleTires", "size"),
    "ord_qty": ("ord_qty", "ordQty", "quantity", "qty"),
    "shop_id": ("shop_id", "shopId", "storeId", "store_id", "shop_seq", "shopSeq"),
    "shop_name": ("shop_name", "shopName", "storeName", "shop_nm", "store_nm", "nameAddress", "name"),
    "region": ("region",),
    "requested_cal_day": ("requested_cal_day", "requestedCalDay", "rsvDate", "cal_day"),
    "rsv_hour": ("rsv_hour", "rsvHour", "tm"),
}


@dataclass(frozen=True)
class ResolvedContextValue:
    value: Any = None
    source: str = "missing"

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "source": self.source}


@dataclass(frozen=True)
class ResolvedTurnContext:
    product: dict[str, ResolvedContextValue] = field(default_factory=dict)
    size: dict[str, ResolvedContextValue] = field(default_factory=dict)
    quantity: dict[str, ResolvedContextValue] = field(default_factory=dict)
    store: dict[str, ResolvedContextValue] = field(default_factory=dict)
    booking: dict[str, ResolvedContextValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": _group_to_dict(self.product),
            "size": _group_to_dict(self.size),
            "quantity": _group_to_dict(self.quantity),
            "store": _group_to_dict(self.store),
            "booking": _group_to_dict(self.booking),
        }


def build_resolved_turn_context(
    *,
    user_text: str = "",
    slots: Mapping[str, Any] | None = None,
    tool_values: Mapping[str, Any] | None = None,
    template_values: Mapping[str, Any] | None = None,
    preorder_values: Mapping[str, Any] | None = None,
    text_values: Mapping[str, Any] | None = None,
) -> ResolvedTurnContext:
    """Resolve canonical product/size/order context with explicit source priority.

    This resolver is intentionally trace-only at first. It does not mutate
    ConversationSlots and it does not read alias keys. Alias normalization must
    happen at API/template boundaries before values are passed here.
    """

    current_turn_values = _canonical_current_turn_values(user_text)
    sources = (
        ("current_turn", current_turn_values),
        ("slots", canonical_context_from_slots(slots)),
        ("tool", _canonical_mapping(tool_values)),
        ("template", _canonical_mapping(template_values)),
        ("preorder", _canonical_mapping(preorder_values)),
        ("text", _canonical_mapping(text_values)),
    )

    def resolve(key: str) -> ResolvedContextValue:
        for source, values in sources:
            value = values.get(key)
            if value not in (None, "", [], {}):
                return ResolvedContextValue(value=value, source=source)
        return ResolvedContextValue()

    return ResolvedTurnContext(
        product={
            "goods_no": resolve("goods_no"),
            "product_name": resolve("product_name"),
        },
        size={"tire_size": resolve("tire_size")},
        quantity={"ord_qty": resolve("ord_qty")},
        store={
            "shop_id": resolve("shop_id"),
            "shop_name": resolve("shop_name"),
            "region": resolve("region"),
        },
        booking={
            "requested_cal_day": resolve("requested_cal_day"),
            "rsv_hour": resolve("rsv_hour"),
        },
    )


def canonical_context_from_template_boundary(values: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize FE/template/preOrder aliases before entering policy code."""
    return _canonical_context_from_boundary(values, TEMPLATE_ALIAS_KEYS, include_nested=True)


def canonical_context_from_tool_boundary(values: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize tool-result aliases before entering policy code."""
    return _canonical_context_from_boundary(values, TOOL_ALIAS_KEYS, include_nested=False)


def _canonical_context_from_boundary(
    values: Mapping[str, Any] | None,
    alias_keys: Mapping[str, tuple[str, ...]],
    *,
    include_nested: bool,
) -> dict[str, Any]:
    if not isinstance(values, Mapping):
        return {}
    normalized: dict[str, Any] = {}
    for canonical_key, aliases in alias_keys.items():
        for alias in aliases:
            value = values.get(alias)
            if value not in (None, "", [], {}):
                normalized[canonical_key] = value
                break
    if include_nested:
        order_info = values.get("orderInfo")
        if isinstance(order_info, Mapping):
            nested = _canonical_context_from_boundary(order_info, alias_keys, include_nested=True)
            for key, value in nested.items():
                normalized.setdefault(key, value)
        metadata = values.get("metadata")
        if isinstance(metadata, Mapping):
            nested = _canonical_context_from_boundary(metadata, alias_keys, include_nested=True)
            for key, value in nested.items():
                normalized.setdefault(key, value)
    return normalized


def canonical_context_from_slots(values: Any | None) -> dict[str, Any]:
    """Normalize ConversationSlots/CanonicalSlotState into internal canonical keys.

    This is not an alias boundary for FE/template payloads. It accepts only
    canonical slot names plus legacy ConversationSlots product labels
    (`pending_product_name`, `tire_model`) and exposes them as `product_name`.
    """
    if values is None:
        return {}
    if isinstance(values, BaseModel):
        data = values.model_dump(exclude_none=True)
    elif isinstance(values, Mapping):
        data = dict(values)
    else:
        data = {
            key: getattr(values, key)
            for key in (
                "goods_no",
                "product_name",
                "pending_product_name",
                "tire_model",
                "tire_size",
                "ord_qty",
                "shop_id",
                "shop_name",
                "region",
                "requested_cal_day",
                "rsv_hour",
            )
            if getattr(values, key, None) not in (None, "", [], {})
        }

    data = _flatten_canonical_slot_state(data)
    normalized = _canonical_mapping(data)
    if not normalized.get("product_name"):
        product_name = data.get("product_name") or data.get("pending_product_name") or data.get("tire_model")
        if product_name not in (None, "", [], {}):
            normalized["product_name"] = product_name
    return normalized


def _flatten_canonical_slot_state(data: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten CanonicalSlotState groups while ignoring FE/template aliases."""
    flattened = dict(data)
    for group_key in ("common", "product", "store", "price"):
        group = data.get(group_key)
        if not isinstance(group, Mapping):
            continue
        for key, value in group.items():
            if key in CANONICAL_CONTEXT_KEYS or key in {"pending_product_name", "tire_model"}:
                flattened.setdefault(key, value)
    return flattened


def _canonical_current_turn_values(user_text: str) -> dict[str, Any]:
    slots = ConversationSlots.extract_from_user_text(user_text or "")
    values: dict[str, Any] = {}
    if slots.goods_no:
        values["goods_no"] = slots.goods_no
    if slots.tire_size:
        values["tire_size"] = slots.tire_size
    if slots.ord_qty:
        values["ord_qty"] = slots.ord_qty
    if slots.shop_name:
        values["shop_name"] = slots.shop_name
    return values


def _canonical_mapping(values: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(values, Mapping):
        return {}
    return {key: values[key] for key in CANONICAL_CONTEXT_KEYS if values.get(key) not in (None, "", [], {})}


def _group_to_dict(group: Mapping[str, ResolvedContextValue]) -> dict[str, dict[str, Any]]:
    return {key: value.to_dict() for key, value in group.items()}
