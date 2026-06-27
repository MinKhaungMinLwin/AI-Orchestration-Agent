"""Shared purchase/order flow-step resolution for transaction policy layers."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from services.tstation.policies.discovery_intent_policy import normalize_tire_size
from services.tstation.policies.response_decision import TemplateName


current_purchase_flow_state: ContextVar[dict[str, Any] | None] = ContextVar("current_purchase_flow_state", default=None)


@dataclass(frozen=True)
class FlowState:
    flow_id: str
    flow_step: str
    required_slots: tuple[str, ...] = ()
    missing_slots: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    preferred_tool: str | None = None
    template: TemplateName = TemplateName.QUICK_REPLY
    response_shape_key: str = "transaction_fallback"
    action_mode: str = "purchase_continuation"
    slot_patch: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "flow_id": self.flow_id,
            "flow_step": self.flow_step,
            "required_slots": list(self.required_slots),
            "missing_slots": list(self.missing_slots),
            "allowed_tools": list(self.allowed_tools),
            "forbidden_tools": list(self.forbidden_tools),
            "preferred_tool": self.preferred_tool,
            "template": self.template.value,
            "response_shape_key": self.response_shape_key,
            "action_mode": self.action_mode,
            "slot_patch": dict(self.slot_patch),
            "metadata": dict(self.metadata),
        }


_PURCHASE_FLOW_ID = "purchase_order"
_PURCHASE_FORBIDDEN_TOOLS = (
    "get_final_price_tool",
    "get_logistics_inventory_tool",
    "get_store_inventory_tool",
    "transaction_store_preview_tool",
    "get_store_schedule_tool",
    "get_multi_store_schedule_tool",
    "quick_order_tool",
)


def resolve_purchase_order_flow(
    *,
    intent: str,
    known_slots: Mapping[str, Any] | None = None,
) -> FlowState | None:
    if intent not in {"quick_order_reservation", "quick_order_execute"}:
        return None

    slots = dict(known_slots or {})
    goods_no = str(slots.get("goods_no") or "").strip()
    tire_size = normalize_tire_size(str(slots.get("tire_size") or ""))
    quantity = slots.get("ord_qty") or slots.get("quantity")
    shop_id = str(slots.get("shop_id") or "").strip()
    region = str(slots.get("region") or slots.get("place") or "").strip()
    store_name = str(slots.get("store_name") or slots.get("shop_name") or "").strip()
    requested_cal_day = str(slots.get("requested_cal_day") or "").strip()
    rsv_hour = str(slots.get("rsv_hour") or "").strip()

    base_patch = _purchase_slot_patch(slots)
    base_metadata = {
        "flow_id": _PURCHASE_FLOW_ID,
        "flow_slots": base_patch,
    }

    if intent == "quick_order_execute":
        execute_missing: list[str] = []
        if not goods_no:
            execute_missing.append("product")
        if quantity in (None, "", 0, "0"):
            execute_missing.append("quantity")
        if not shop_id:
            execute_missing.append("store")
        if not (requested_cal_day and rsv_hour):
            execute_missing.append("booking_datetime")
        if execute_missing:
            return FlowState(
                flow_id=_PURCHASE_FLOW_ID,
                flow_step="execute_order",
                required_slots=tuple(execute_missing),
                missing_slots=tuple(execute_missing),
                allowed_tools=(),
                forbidden_tools=(
                    "get_final_price_tool",
                    "get_logistics_inventory_tool",
                    "get_store_inventory_tool",
                    "transaction_store_preview_tool",
                    "get_store_schedule_tool",
                    "get_multi_store_schedule_tool",
                    "quick_order_tool",
                ),
                preferred_tool=None,
                template=TemplateName.QUICK_REPLY,
                response_shape_key="missing_order_execution_slots",
                action_mode="purchase_continuation",
                slot_patch=base_patch,
                metadata=base_metadata,
            )

    if not goods_no:
        product_name = str(
            slots.get("product_name") or slots.get("tire_model") or slots.get("pending_product_name") or ""
        ).strip()
        if product_name and not tire_size:
            return FlowState(
                flow_id=_PURCHASE_FLOW_ID,
                flow_step="ask_size",
                required_slots=("tire_size",),
                missing_slots=("tire_size",),
                allowed_tools=(),
                forbidden_tools=_PURCHASE_FORBIDDEN_TOOLS,
                preferred_tool=None,
                template=TemplateName.QUICK_REPLY,
                response_shape_key="missing_order_slots",
                action_mode="purchase_continuation",
                slot_patch=base_patch,
                metadata=base_metadata,
            )
        return FlowState(
            flow_id=_PURCHASE_FLOW_ID,
            flow_step="resolve_product",
            required_slots=("product",),
            missing_slots=("product",) if not product_name else (),
            allowed_tools=("search_product_tool",),
            forbidden_tools=tuple(tool for tool in _PURCHASE_FORBIDDEN_TOOLS if tool != "transaction_store_preview_tool"),
            preferred_tool="search_product_tool",
            template=TemplateName.QUICK_REPLY,
            response_shape_key="missing_order_slots" if product_name else "product_search_summary",
            action_mode="purchase_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    if quantity in (None, "", 0, "0"):
        return FlowState(
            flow_id=_PURCHASE_FLOW_ID,
            flow_step="ask_quantity",
            required_slots=("quantity",),
            missing_slots=("quantity",),
            allowed_tools=(),
            forbidden_tools=_PURCHASE_FORBIDDEN_TOOLS,
            preferred_tool=None,
            template=TemplateName.QUICK_REPLY,
            response_shape_key="missing_order_slots",
            action_mode="purchase_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    if not shop_id and not region and not store_name:
        return FlowState(
            flow_id=_PURCHASE_FLOW_ID,
            flow_step="ask_store",
            required_slots=("store",),
            missing_slots=("store",),
            allowed_tools=(),
            forbidden_tools=_PURCHASE_FORBIDDEN_TOOLS,
            preferred_tool=None,
            template=TemplateName.QUICK_REPLY,
            response_shape_key="missing_order_slots",
            action_mode="purchase_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    if not shop_id and region:
        return FlowState(
            flow_id=_PURCHASE_FLOW_ID,
            flow_step="show_store_candidates",
            required_slots=(),
            missing_slots=(),
            allowed_tools=("transaction_store_preview_tool",),
            forbidden_tools=(
                "get_final_price_tool",
                "get_logistics_inventory_tool",
                "get_store_inventory_tool",
                "get_store_schedule_tool",
                "get_multi_store_schedule_tool",
                "quick_order_tool",
            ),
            preferred_tool="transaction_store_preview_tool",
            template=TemplateName.LOCATION,
            response_shape_key="reservation_store_candidates",
            action_mode="purchase_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    if not shop_id and store_name:
        return FlowState(
            flow_id=_PURCHASE_FLOW_ID,
            flow_step="resolve_store",
            required_slots=(),
            missing_slots=(),
            allowed_tools=("transaction_store_preview_tool",),
            forbidden_tools=(
                "get_final_price_tool",
                "get_logistics_inventory_tool",
                "get_store_inventory_tool",
                "quick_order_tool",
            ),
            preferred_tool="transaction_store_preview_tool",
            template=TemplateName.LOCATION,
            response_shape_key="reservation_store_candidates",
            action_mode="purchase_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    if not (requested_cal_day and rsv_hour):
        return FlowState(
            flow_id=_PURCHASE_FLOW_ID,
            flow_step="show_schedule",
            required_slots=(),
            missing_slots=("booking_datetime",),
            allowed_tools=("get_store_schedule_tool", "get_multi_store_schedule_tool"),
            forbidden_tools=(
                "get_final_price_tool",
                "get_logistics_inventory_tool",
                "get_store_inventory_tool",
                "quick_order_tool",
            ),
            preferred_tool="get_store_schedule_tool",
            template=TemplateName.DATE_PICK,
            response_shape_key="reservation_slots",
            action_mode="booking_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    if intent == "quick_order_execute":
        return FlowState(
            flow_id=_PURCHASE_FLOW_ID,
            flow_step="execute_order",
            required_slots=(),
            missing_slots=(),
            allowed_tools=("quick_order_tool",),
            forbidden_tools=(
                "get_final_price_tool",
                "get_logistics_inventory_tool",
                "get_store_inventory_tool",
                "transaction_store_preview_tool",
                "get_store_schedule_tool",
                "get_multi_store_schedule_tool",
            ),
            preferred_tool="quick_order_tool",
            template=TemplateName.ORDER_COMPLETE,
            response_shape_key="quick_order_execute",
            action_mode="purchase_continuation",
            slot_patch=base_patch,
            metadata=base_metadata,
        )

    return FlowState(
        flow_id=_PURCHASE_FLOW_ID,
        flow_step="build_preorder",
        required_slots=(),
        missing_slots=(),
        allowed_tools=(),
        forbidden_tools=(
            "get_logistics_inventory_tool",
            "get_store_inventory_tool",
            "transaction_store_preview_tool",
            "get_store_schedule_tool",
            "get_multi_store_schedule_tool",
            "quick_order_tool",
        ),
        preferred_tool=None,
        template=TemplateName.PRE_ORDER,
        response_shape_key="reservation_confirmation_ready",
        action_mode="purchase_continuation",
        slot_patch=base_patch,
        metadata=base_metadata,
    )


def build_purchase_flow_fallback_event(
    *,
    flow_state: FlowState | None = None,
    intent: str | None = None,
    known_slots: Mapping[str, Any] | None = None,
    tool_data_list: list[dict] | None = None,
    blocked_tool: str | None = None,
) -> dict[str, Any] | None:
    state = flow_state or resolve_purchase_order_flow(intent=intent or "", known_slots=known_slots)
    if state is None:
        return None

    slots = dict(known_slots or state.slot_patch or {})
    resolved_product = _resolved_purchase_product(slots=slots, tool_data_list=tool_data_list)
    merged_slots = {**slots, **resolved_product}
    metadata = {
        "flowId": state.flow_id,
        "flowStep": state.flow_step,
        "missingSlots": list(state.missing_slots),
        "response_shape_key": state.response_shape_key,
    }
    if blocked_tool:
        metadata["blockedTool"] = blocked_tool
    if merged_slots.get("goods_no"):
        metadata["goodsNo"] = merged_slots["goods_no"]
    if merged_slots.get("product_name"):
        metadata["productName"] = merged_slots["product_name"]
    if merged_slots.get("tire_size"):
        metadata["tireSize"] = merged_slots["tire_size"]
    if merged_slots.get("ord_qty") or merged_slots.get("quantity"):
        metadata["ordQty"] = merged_slots.get("ord_qty") or merged_slots.get("quantity")

    if state.flow_step == "ask_store":
        assistant_response = _purchase_missing_store_text(merged_slots)
    elif state.flow_step == "ask_quantity":
        assistant_response = _purchase_missing_quantity_text(merged_slots)
    else:
        return None

    return {
        "type": "data",
        "template": state.template.value,
        "source_domain": "transaction",
        "assistant_response_source": "code_purchase_flow_fallback",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": _purchase_fallback_quick_replies(state.flow_step),
            "predictedDomains": ["TRANSACTION", "DISCOVERY"],
            "metadata": metadata,
        },
    }


def _purchase_slot_patch(slots: Mapping[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for key in (
        "goods_no",
        "product_name",
        "tire_model",
        "pending_product_name",
        "tire_size",
        "ord_qty",
        "quantity",
        "shop_id",
        "shop_name",
        "store_name",
        "region",
        "place",
        "requested_cal_day",
        "rsv_hour",
        "pending_intent",
        "goal_type",
    ):
        value = slots.get(key)
        if value not in (None, ""):
            patch[key] = value
    if patch.get("pending_intent") in (None, ""):
        patch["pending_intent"] = "order"
    if patch.get("goal_type") in (None, ""):
        patch["goal_type"] = "place_order"
    if patch.get("tire_size"):
        patch["tire_size"] = normalize_tire_size(str(patch["tire_size"]))
    return patch


def _resolved_purchase_product(*, slots: Mapping[str, Any], tool_data_list: list[dict] | None) -> dict[str, Any]:
    if slots.get("goods_no"):
        return {
            "goods_no": str(slots.get("goods_no") or "").strip(),
            "product_name": str(
                slots.get("product_name") or slots.get("tire_model") or slots.get("pending_product_name") or ""
            ).strip(),
            "tire_size": normalize_tire_size(str(slots.get("tire_size") or "")),
        }

    rows = _search_product_rows_from_entries(tool_data_list or [])
    if not rows:
        return {}

    target_name = str(
        slots.get("product_name") or slots.get("tire_model") or slots.get("pending_product_name") or ""
    ).strip()
    target_size = normalize_tire_size(str(slots.get("tire_size") or ""))
    matched_rows = rows
    if target_name:
        normalized_name = _normalize_product_key(target_name)
        name_rows = [
            row for row in matched_rows if normalized_name and normalized_name in _normalize_product_key(str(row.get("goods_nm") or ""))
        ]
        if name_rows:
            matched_rows = name_rows
    if target_size:
        size_rows = [
            row
            for row in matched_rows
            if normalize_tire_size(str(row.get("tire_size_1") or row.get("tire_size") or "")) == target_size
        ]
        if size_rows:
            matched_rows = size_rows
    if len(matched_rows) != 1:
        return {}
    row = matched_rows[0]
    return {
        "goods_no": str(row.get("goods_no") or "").strip(),
        "product_name": str(row.get("goods_nm") or target_name or "").strip(),
        "tire_size": normalize_tire_size(str(row.get("tire_size_1") or row.get("tire_size") or target_size or "")),
    }


def _search_product_rows_from_entries(entries: list[dict]) -> list[dict]:
    for entry in reversed(entries):
        if entry.get("tool") != "search_product_tool":
            continue
        payload = entry.get("data")
        for candidate in _search_payload_candidates(payload):
            if isinstance(candidate, list):
                rows = [row for row in candidate if isinstance(row, dict)]
                if rows:
                    return rows
    return []


def _search_payload_candidates(payload: Any) -> list[Any]:
    candidates: list[Any] = [payload]
    if isinstance(payload, dict):
        data = payload.get("data")
        candidates.append(data)
        if isinstance(data, dict):
            candidates.append(data.get("data"))
    expanded: list[Any] = []
    for candidate in candidates:
        expanded.append(candidate)
        if isinstance(candidate, dict):
            expanded.extend(candidate.get(key) for key in ("items", "products", "data"))
    return expanded


def _normalize_product_key(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def _purchase_product_label(slots: Mapping[str, Any]) -> str:
    product_name = str(slots.get("product_name") or slots.get("tire_model") or slots.get("pending_product_name") or "").strip()
    tire_size = normalize_tire_size(str(slots.get("tire_size") or ""))
    return " ".join(part for part in (product_name, tire_size) if part)


def _purchase_missing_store_text(slots: Mapping[str, Any]) -> str:
    product_label = _purchase_product_label(slots)
    quantity = slots.get("ord_qty") or slots.get("quantity")
    if product_label and quantity not in (None, "", 0, "0"):
        return f"{product_label} {quantity}개 구매를 진행할 매장이나 지역을 알려주세요."
    if product_label:
        return f"{product_label} 구매를 진행할 매장이나 지역을 알려주세요."
    return "구매를 진행할 매장이나 지역을 알려주세요."


def _purchase_missing_quantity_text(slots: Mapping[str, Any]) -> str:
    product_label = _purchase_product_label(slots)
    store_name = str(slots.get("shop_name") or slots.get("store_name") or "").strip()
    if product_label and store_name:
        return f"{product_label} {store_name} 구매를 진행하려면 수량이 필요해요. 구매 수량을 알려주세요."
    if product_label:
        return f"{product_label} 구매를 진행하려면 수량이 필요해요. 구매 수량을 알려주세요."
    return "구매를 진행하려면 수량이 필요해요. 구매 수량을 알려주세요."


def _purchase_fallback_quick_replies(flow_step: str) -> list[dict[str, str]]:
    if flow_step == "ask_store":
        return [
            {"label": "내 주변 매장 찾기", "domain": "TRANSACTION"},
            {"label": "지역/매장 입력", "domain": "TRANSACTION"},
            {"label": "단골매장 보기", "domain": "TRANSACTION"},
        ]
    if flow_step == "ask_quantity":
        return [
            {"label": "2개", "domain": "TRANSACTION"},
            {"label": "4개", "domain": "TRANSACTION"},
            {"label": "수량 직접 입력", "domain": "TRANSACTION"},
        ]
    return []
