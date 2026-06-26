"""Structured UI action policy helpers.

Keep chip/card selection handling out of ad hoc chat branches so current-turn
selection metadata can deterministically own slot rewrite, trace fields, and
CTA validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from services.tstation.policies.discovery_intent_policy import normalize_tire_size
from services.tstation.policies.cta_registry import cta_trace_metadata, normalize_quickreply_ctas
from services.tstation.policies.resolved_context import (
    canonical_context_from_template_boundary,
    canonical_context_from_tool_boundary,
)


_VEHICLE_TIRE_SIZE_LOOKUP_INTENT = "vehicle_tire_size_lookup"
_STOCK_STORE_SEARCH_INTENT = "stock_store_search"
_QUICK_ORDER_RESERVATION_INTENT = "quick_order_reservation"
_VEHICLE_SIZE_LOOKUP_ALLOWED_LABELS = frozenset({
    "이 사이즈로 타이어 보기",
    "타이어 추천받기",
    "사이즈 직접 입력",
    "다른 차량 확인",
})
_VEHICLE_SIZE_LOOKUP_ALLOWED_ACTIONS = frozenset({
    "search_products_by_selected_vehicle_size",
})
_VEHICLE_SIZE_LOOKUP_BLOCKED_LABEL_TOKENS = ("매장", "예약", "구매")
_QUANTITY_LABEL_RE = re.compile(r"^\s*([1-4])\s*(?:개|본)\s*$")
_CTA_CLARIFICATION_LABEL_RE = re.compile(r"(?:다른\s*)?(?:지역|장소|날짜|일정)\s*(?:입력|찾기|검색|확인)")
_VEHICLE_PLATE_RE = re.compile(r"\d{2,3}\s*[가-힣]\s*\d{4}")
_VEHICLE_BOUND_REQUEST_RE = re.compile(
    r"내\s*차|내차|내\s*차량|내차량|차량번호|차\s*번호|"
    r"내\s*[0-9a-zA-Z가-힣]+|"
    r"\d{2,3}\s*[가-힣]\s*\d{4}",
    re.IGNORECASE,
)
_VEHICLE_MATCH_STOPWORDS = {
    "내", "차", "차량", "번호", "차량번호", "내차", "내차량", "알지", "맞는", "타이어", "보여줘",
    "보여", "추천", "해줘", "찾아줘", "알려줘", "알려", "규격", "사이즈", "그리고", "그럼", "이건데",
}
_KOREAN_SELECTION_ORDINALS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("첫번째", "첫째", "첫 번", "첫번", "1번째", "1번", "1.", "1)"), 0),
    (("두번째", "둘째", "두 번", "두번", "2번째", "2번", "2.", "2)"), 1),
    (("세번째", "셋째", "세 번", "세번", "3번째", "3번", "3.", "3)"), 2),
    (("네번째", "넷째", "네 번", "네번", "4번째", "4번", "4.", "4)"), 3),
    (("다섯번째", "다섯째", "5번째", "5번", "5.", "5)"), 4),
    (("여섯번째", "여섯째", "6번째", "6번", "6.", "6)"), 5),
    (("일곱번째", "일곱째", "7번째", "7번", "7.", "7)"), 6),
    (("여덟번째", "여덟째", "8번째", "8번", "8.", "8)"), 7),
    (("아홉번째", "아홉째", "9번째", "9번", "9.", "9)"), 8),
    (("열번째", "열째", "10번째", "10번", "10.", "10)"), 9),
)

_UI_ACTION_SLOT_KEYS = (
    "goods_no",
    "tire_size",
    "tire_size_front",
    "tire_size_rear",
    "ord_qty",
    "region",
    "shop_id",
    "shop_name",
    "availability_intent",
    "requested_cal_day",
    "pending_intent",
    "goal_type",
    "stock_check_mode",
    "car_no",
    "car_lnc_cd",
    "mbr_car_reg_seq",
    "mbr_car_unif_no",
    "car_nm",
    "car_model_det",
    "car_type",
    "vehicle_type",
)


@dataclass(frozen=True)
class UIActionContext:
    action_type: str
    action_name: str
    selection_source: str
    contract_intent: str
    source_intent: str
    expected_contract_intent: str
    expected_behavior: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    entity_label: str | None = None
    slots: Mapping[str, Any] = field(default_factory=dict)
    slot_patch: Mapping[str, Any] = field(default_factory=dict)
    trace_metadata: Mapping[str, Any] = field(default_factory=dict)
    raw_metadata: Mapping[str, Any] = field(default_factory=dict)
    payload: Mapping[str, Any] = field(default_factory=dict)


def _vehicle_value(selected_vehicle: Mapping[str, Any], *keys: str) -> str:
    selected_car = selected_vehicle.get("car") if isinstance(selected_vehicle.get("car"), Mapping) else {}
    selected_meta = selected_vehicle.get("meta") if isinstance(selected_vehicle.get("meta"), Mapping) else {}
    for key in keys:
        value = selected_meta.get(key)
        if value not in (None, ""):
            return str(value).strip()
        value = selected_car.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def store_context_from_mapping(data: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        return {}
    context = data.get("currentStoreContext")
    if isinstance(context, Mapping):
        data = context
    canonical_template = canonical_context_from_template_boundary(data)
    canonical_tool = canonical_context_from_tool_boundary(data)
    shop_id = str(canonical_template.get("shop_id") or canonical_tool.get("shop_id") or data.get("store_id") or "").strip()
    shop_name = str(canonical_template.get("shop_name") or canonical_tool.get("shop_name") or "").strip()
    xpos = _float_or_none(
        data.get("xpos")
        or data.get("x_pos")
        or data.get("lng")
        or data.get("longitude")
        or data.get("user_xpos")
    )
    ypos = _float_or_none(
        data.get("ypos")
        or data.get("y_pos")
        or data.get("lat")
        or data.get("latitude")
        or data.get("user_ypos")
    )
    address = str(
        data.get("address")
        or data.get("addr")
        or data.get("roadAddress")
        or data.get("road_address")
        or ""
    ).strip()
    result: dict[str, Any] = {}
    if shop_id:
        result["shop_id"] = shop_id
        result["shopId"] = shop_id
    if shop_name:
        result["shop_name"] = shop_name
        result["shopName"] = shop_name
    if xpos is not None:
        result["xpos"] = xpos
    if ypos is not None:
        result["ypos"] = ypos
    if address:
        result["address"] = address
    return result


def store_name_exact_match_row(store_name: str, stores: list[dict[str, Any]]) -> dict[str, Any] | None:
    target = re.sub(r"\s+", "", str(store_name or "")).lower()
    target = re.sub(r"^(?:티스테이션|더타이어샵|t'?station)", "", target, flags=re.IGNORECASE)
    matches: list[dict[str, Any]] = []
    for store in stores:
        if not isinstance(store, dict):
            continue
        shop_name = re.sub(r"\s+", "", str(store.get("shop_nm") or store.get("shop_name") or "")).lower()
        shop_name = re.sub(r"^(?:티스테이션|더타이어샵|t'?station)", "", shop_name, flags=re.IGNORECASE)
        if shop_name == target:
            matches.append(store)
    if len(matches) == 1:
        return matches[0]
    return None


def build_other_store_context_enrichment_input(
    cta_context: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    store_context = store_context_from_mapping(cta_context)
    if (
        store_context
        and (store_context.get("xpos") is None or store_context.get("ypos") is None)
        and store_context.get("shop_name")
    ):
        return store_context, {"store_nm": str(store_context["shop_name"]), "limit": 10}
    return store_context, None


def apply_other_store_context_enrichment(
    cta_context: Mapping[str, Any] | None,
    *,
    store_rows: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    enriched_cta_context = dict(cta_context or {})
    store_context = store_context_from_mapping(enriched_cta_context)
    if not store_context or not store_context.get("shop_name") or not isinstance(store_rows, list):
        return enriched_cta_context, store_context
    matched_store = store_name_exact_match_row(
        str(store_context["shop_name"]),
        [store for store in store_rows if isinstance(store, dict)],
    )
    if matched_store is None:
        return enriched_cta_context, store_context
    enriched_store_context = store_context_from_mapping({**matched_store, **store_context})
    enriched_cta_context["currentStoreContext"] = enriched_store_context
    return enriched_cta_context, enriched_store_context


def build_other_store_preview_metadata(
    *,
    enriched_cta_context: Mapping[str, Any] | None,
    original_cta_context: Mapping[str, Any] | None,
    preview_input: Mapping[str, Any] | None,
) -> dict[str, Any]:
    store_context = store_context_from_mapping(enriched_cta_context)
    canonical_cta_context = canonical_context_from_template_boundary(original_cta_context)
    previous_store_name = str(
        store_context.get("shop_name") or canonical_cta_context.get("shop_name") or ""
    ).strip()
    excluded_ids = {
        str(shop_id)
        for shop_id in ((preview_input or {}).get("exclude_shop_ids") or [])
        if shop_id
    }
    return {
        "store_context": store_context,
        "previous_store_name": previous_store_name,
        "excluded_ids": excluded_ids,
    }


def build_cta_preview_template_context(
    *,
    user_text: str,
    pending_intent: str,
    goal_type: str,
    excluded_ids: set[str] | None = None,
    action_mode: str | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "user_text": str(user_text or ""),
        "pending_intent": str(pending_intent or ""),
        "goal_type": str(goal_type or ""),
    }
    if excluded_ids:
        context["excluded_ids"] = {str(shop_id) for shop_id in excluded_ids if shop_id}
    if action_mode:
        context["action_mode"] = str(action_mode)
    return context


def _store_area_hint_from_name(store_name: str | None) -> str:
    text = str(store_name or "").strip()
    text = re.sub(r"^(?:티스테이션|더타이어샵)\s*", "", text)
    text = re.sub(r"(?:점|센터|지점)\s*$", "", text)
    return text.strip()


def cta_preview_input_from_slots(
    slots: Any,
    *,
    cta_context: Mapping[str, Any] | None = None,
    other_store_search: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    context = cta_context or {}
    canonical_context = canonical_context_from_template_boundary(context)
    goods_no = getattr(slots, "goods_no", None) or canonical_context.get("goods_no")
    ord_qty_value = getattr(slots, "ord_qty", None) or canonical_context.get("ord_qty")
    if not goods_no:
        return None, "product"
    if not ord_qty_value:
        return None, "quantity"
    store_context = store_context_from_mapping(context)
    has_location = (
        getattr(slots, "region", None)
        or getattr(slots, "shop_name", None)
        or getattr(slots, "shop_id", None)
        or store_context.get("shop_name")
        or (store_context.get("xpos") is not None and store_context.get("ypos") is not None)
    )
    if not has_location:
        return None, "location"
    try:
        ord_qty = int(ord_qty_value)
    except (TypeError, ValueError):
        return None, "quantity"
    preview_input: dict[str, Any] = {
        "goods_no": str(goods_no),
        "ord_qty": ord_qty,
        "include_price": True,
    }
    if other_store_search:
        excluded_shop_ids: list[str] = []
        if store_context.get("shop_id"):
            excluded_shop_ids.append(str(store_context["shop_id"]))
        elif getattr(slots, "shop_id", None):
            excluded_shop_ids.append(str(slots.shop_id))
        if store_context.get("xpos") is not None and store_context.get("ypos") is not None:
            preview_input["user_xpos"] = float(store_context["xpos"])
            preview_input["user_ypos"] = float(store_context["ypos"])
            preview_input["radius_km"] = 20.0
        else:
            area_hint = _store_area_hint_from_name(
                str(store_context.get("shop_name") or getattr(slots, "shop_name", "") or "")
            )
            if area_hint:
                preview_input["region_code"] = area_hint
            elif getattr(slots, "region", None):
                preview_input["region_code"] = slots.region
            else:
                return None, "location"
        if excluded_shop_ids:
            preview_input["exclude_shop_ids"] = excluded_shop_ids
        preview_input["stock_check_mode"] = "inventory_only"
    elif getattr(slots, "region", None):
        preview_input["region_code"] = slots.region
    elif getattr(slots, "shop_name", None):
        preview_input["store_nm"] = slots.shop_name
    elif store_context.get("shop_name"):
        preview_input["store_nm"] = str(store_context["shop_name"])
    if str(context.get("followupMode") or "") == "logistics_earliest_install_date":
        preview_input["stock_check_mode"] = "logistics_only"
    if getattr(slots, "requested_cal_day", None):
        preview_input["requested_cal_day"] = slots.requested_cal_day
    return preview_input, None


def cta_missing_slot_event(missing_slot: str) -> dict[str, Any]:
    if missing_slot == "location":
        response = "확인할 지역명이나 매장명을 입력해 주세요. 이전 상품·수량·날짜 조건을 유지해서 다시 확인할게요."
        chips = [
            {"label": "서울", "domain": "TRANSACTION", "actionId": "change_region", "intentKey": "today_install"},
            {"label": "강남", "domain": "TRANSACTION", "actionId": "change_region", "intentKey": "today_install"},
            {"label": "송파", "domain": "TRANSACTION", "actionId": "change_region", "intentKey": "today_install"},
        ]
    elif missing_slot == "quantity":
        response = "확인할 수량을 알려주세요."
        chips = [
            {"label": "1개", "domain": "TRANSACTION"},
            {"label": "2개", "domain": "TRANSACTION"},
            {"label": "3개", "domain": "TRANSACTION"},
            {"label": "4개", "domain": "TRANSACTION"},
        ]
    else:
        response = "상품 정보를 먼저 확인해야 다음 단계로 진행할 수 있어요."
        chips = [{"label": "조건 다시 입력", "domain": "TRANSACTION"}]
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_cta_action_guard",
        "data": {
            "assistantResponse": response,
            "quickReplies": chips,
            "predictedDomains": ["TRANSACTION"],
        },
    }


def normalize_preview_tool_result(
    raw_preview: Any,
    *,
    parse_tool_output_fn: Callable[[Any], Any],
) -> dict[str, Any]:
    preview_result = raw_preview if isinstance(raw_preview, dict) else parse_tool_output_fn(raw_preview)
    if isinstance(preview_result, dict):
        return preview_result
    return {
        "status": "error",
        "http_status": None,
        "message": "Invalid tool response",
        "data": {},
    }


def build_preview_tool_mapped_event(
    *,
    preview_input: Mapping[str, Any],
    preview_result: Mapping[str, Any],
    template_builder: Callable[[list[dict[str, Any]], str], dict[str, Any] | None],
    intro_text: str,
    assistant_response_source: str,
    fallback_event: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    mapped_event = template_builder(
        [{"tool": "transaction_store_preview_tool", "args": dict(preview_input), "data": dict(preview_result)}],
        intro_text,
    )
    if not isinstance(mapped_event, dict):
        mapped_event = dict(fallback_event or cta_missing_slot_event("location"))
    else:
        mapped_event = dict(mapped_event)
    mapped_event["source_domain"] = "transaction"
    mapped_event["assistant_response_source"] = assistant_response_source
    return mapped_event


def build_cta_preview_contract_gate(
    *,
    user_text: str,
    merged_slots: Any,
    source: str,
    required_tools: tuple[str, ...],
    build_intent_frame_fn: Callable[..., Any],
    plan_tools_fn: Callable[[Any], Any],
    decide_response_fn: Callable[..., Any],
    build_turn_contract_fn: Callable[..., Any],
    contract_gate_fn: Callable[..., tuple[bool, str]],
) -> tuple[Any, bool, str]:
    cta_known_slots = {
        "goods_no": getattr(merged_slots, "goods_no", None),
        "tire_size": getattr(merged_slots, "tire_size", None),
        "quantity": getattr(merged_slots, "ord_qty", None),
        "ord_qty": getattr(merged_slots, "ord_qty", None),
        "shop_id": getattr(merged_slots, "shop_id", None),
        "shop_name": getattr(merged_slots, "shop_name", None),
        "store_name": getattr(merged_slots, "shop_name", None),
        "region": getattr(merged_slots, "region", None),
        "availability_intent": getattr(merged_slots, "availability_intent", None),
        "requested_cal_day": getattr(merged_slots, "requested_cal_day", None),
        "pending_intent": getattr(merged_slots, "pending_intent", None) or "stock",
        "goal_type": getattr(merged_slots, "goal_type", None) or "store_with_stock",
        "stock_check_mode": "preview",
    }
    cta_frame = build_intent_frame_fn(
        user_text,
        known_slots={k: v for k, v in cta_known_slots.items() if v not in (None, "")},
    )
    cta_tool_plan = plan_tools_fn(cta_frame)
    cta_response_decision = decide_response_fn(
        intent=cta_frame.intent,
        user_text=user_text,
        known_slots=dict(cta_frame.known_slots),
    )
    cta_contract = build_turn_contract_fn(
        user_text=user_text,
        intent_frame=cta_frame,
        tool_plan=cta_tool_plan,
        response_decision=cta_response_decision,
        merged_slots=merged_slots,
        action_mode="stock_check",
        context_state="resumed",
        resume_source=f"cta_action:{source}",
    )
    allowed, reason = contract_gate_fn(
        turn_contract=cta_contract,
        intent="stock_store_search",
        template="quickReply",
        source=source,
        required_tools=required_tools,
    )
    return cta_contract, allowed, reason


def _normalize_vehicle_contract_intent(intent: str | None) -> str:
    normalized = str(intent or "").strip()
    if normalized == "vehicle_information":
        return _VEHICLE_TIRE_SIZE_LOOKUP_INTENT
    return normalized


def _normalize_ui_action_mapping(raw_action: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw_action, Mapping):
        return {}
    normalized = dict(raw_action)
    metadata = normalized.get("metadata")
    if isinstance(metadata, Mapping):
        normalized.setdefault("raw_metadata", dict(metadata))
    slots = normalized.get("slots")
    if not isinstance(slots, Mapping):
        slots = normalized.get("slot_patch")
    canonical_slots = canonical_context_from_template_boundary(slots if isinstance(slots, Mapping) else normalized)
    if canonical_slots:
        normalized["slots"] = canonical_slots
    action_type = str(
        normalized.get("action_type")
        or normalized.get("cta_action")
        or normalized.get("action_name")
        or ""
    ).strip()
    normalized["action_type"] = action_type
    if normalized.get("expected_contract_intent") == "vehicle_information":
        normalized["expected_contract_intent"] = _VEHICLE_TIRE_SIZE_LOOKUP_INTENT
    if normalized.get("source_intent") == "vehicle_information":
        normalized["source_intent"] = _VEHICLE_TIRE_SIZE_LOOKUP_INTENT
    return normalized


def _ui_action_slot_patch(raw_action: Mapping[str, Any]) -> dict[str, Any]:
    canonical = canonical_context_from_template_boundary(raw_action.get("slots"))
    if not canonical:
        canonical = canonical_context_from_template_boundary(raw_action)
    patch: dict[str, Any] = {}
    for key in _UI_ACTION_SLOT_KEYS:
        value = canonical.get(key)
        if value in (None, "", []):
            continue
        if key == "ord_qty":
            try:
                patch[key] = int(value)
            except (TypeError, ValueError):
                continue
            continue
        patch[key] = value
    quantity_match = _QUANTITY_LABEL_RE.fullmatch(str(raw_action.get("entity_label") or raw_action.get("dynamic_value") or ""))
    if quantity_match and "ord_qty" not in patch:
        patch["ord_qty"] = int(quantity_match.group(1))
    return patch


def _ui_action_trace_metadata(
    raw_action: Mapping[str, Any],
    *,
    selection_source: str,
    contract_intent: str,
    previous_slots: Mapping[str, Any] | None,
) -> dict[str, Any]:
    slot_patch = _ui_action_slot_patch(raw_action)
    trace_metadata: dict[str, Any] = {
        "ui_action_detected": True,
        "ui_action_type": str(raw_action.get("action_type") or raw_action.get("cta_action") or "").strip() or None,
        "source_intent": str(raw_action.get("source_intent") or "").strip() or None,
        "expected_contract_intent": str(raw_action.get("expected_contract_intent") or "").strip() or None,
        "actual_contract_intent": contract_intent or None,
        "selected_entity_type": str(raw_action.get("entity_type") or "").strip() or None,
        "selected_entity_id": str(raw_action.get("entity_id") or "").strip() or None,
        "selection_source": selection_source,
        "slots_rewritten": False,
        "missing_slots": [],
        "validation_result": "resolved",
        "validation_reason": "ui_action_metadata",
        "fallback_behavior": None,
    }
    if slot_patch:
        trace_metadata["selected_slots"] = dict(slot_patch)
    if previous_slots:
        trace_metadata["previous_slots"] = {
            key: value for key, value in previous_slots.items() if value not in (None, "", [])
        }
    if contract_intent == _VEHICLE_TIRE_SIZE_LOOKUP_INTENT:
        trace_metadata.update({
            "vehicle_selection_detected": True,
            "selected_car_no": str(raw_action.get("entity_id") or slot_patch.get("car_no") or "").strip() or None,
            "selected_tire_size": str(
                slot_patch.get("tire_size")
                or slot_patch.get("tire_size_front")
                or slot_patch.get("tire_size_rear")
                or ""
            ).strip() or None,
            "previous_car_no": str((previous_slots or {}).get("car_no") or ""),
            "previous_tire_size": str((previous_slots or {}).get("tire_size") or ""),
            "contract_intent_before_router": _VEHICLE_TIRE_SIZE_LOOKUP_INTENT,
            "final_contract_intent": _VEHICLE_TIRE_SIZE_LOOKUP_INTENT,
        })
    return trace_metadata


def _build_ui_action_context_from_raw(
    raw_action: Mapping[str, Any],
    *,
    selection_source: str,
    previous_slots: Mapping[str, Any] | None = None,
) -> UIActionContext | None:
    normalized = _normalize_ui_action_mapping(raw_action)
    if not normalized:
        return None
    source_intent = _normalize_vehicle_contract_intent(str(normalized.get("source_intent") or "").strip())
    expected_contract_intent = _normalize_vehicle_contract_intent(
        str(normalized.get("expected_contract_intent") or "").strip()
    )
    contract_intent = expected_contract_intent or source_intent
    if not contract_intent:
        return None
    slot_patch = _ui_action_slot_patch(normalized)
    entity_label = str(
        normalized.get("entity_label")
        or normalized.get("label")
        or normalized.get("entityLabel")
        or normalized.get("dynamic_value")
        or ""
    ).strip()
    entity_id = str(
        normalized.get("entity_id")
        or normalized.get("entityId")
        or slot_patch.get("goods_no")
        or slot_patch.get("car_no")
        or ""
    ).strip()
    entity_type = str(
        normalized.get("entity_type")
        or normalized.get("entityType")
        or ("vehicle" if contract_intent == _VEHICLE_TIRE_SIZE_LOOKUP_INTENT else "product")
    ).strip()
    trace_metadata = _ui_action_trace_metadata(
        normalized,
        selection_source=selection_source,
        contract_intent=contract_intent,
        previous_slots=previous_slots,
    )
    return UIActionContext(
        action_type=str(normalized.get("action_type") or "").strip() or "select_ui_action",
        action_name=str(normalized.get("cta_action") or normalized.get("action_type") or "select_ui_action"),
        selection_source=selection_source,
        contract_intent=contract_intent,
        source_intent=source_intent or contract_intent,
        expected_contract_intent=expected_contract_intent or contract_intent,
        expected_behavior=str(normalized.get("expected_behavior") or "").strip() or None,
        entity_type=entity_type or None,
        entity_id=entity_id or None,
        entity_label=entity_label or None,
        slots=dict(normalized.get("slots") or {}),
        slot_patch=slot_patch,
        trace_metadata=trace_metadata,
        raw_metadata=dict(normalized.get("raw_metadata") or normalized),
        payload=dict(normalized),
    )


def resolve_ui_action_context(
    *,
    raw_action: Mapping[str, Any] | None = None,
    selected_vehicle: Mapping[str, Any] | None,
    selection_source: str,
    previous_slots: Mapping[str, Any] | None = None,
    slot_patch: Mapping[str, Any] | None = None,
) -> UIActionContext | None:
    if raw_action is not None:
        return _build_ui_action_context_from_raw(
            raw_action,
            selection_source=selection_source,
            previous_slots=previous_slots,
        )
    if not isinstance(selected_vehicle, Mapping):
        return None

    selection_context = (
        selected_vehicle.get("selection_context")
        if isinstance(selected_vehicle.get("selection_context"), Mapping)
        else {}
    )
    source_intent = _normalize_vehicle_contract_intent(selection_context.get("source_intent"))
    expected_contract_intent = _normalize_vehicle_contract_intent(
        selection_context.get("expected_contract_intent")
    )
    contract_intent = expected_contract_intent or source_intent
    if contract_intent != _VEHICLE_TIRE_SIZE_LOOKUP_INTENT:
        return None

    slot_patch_dict = {
        key: value for key, value in dict(slot_patch or {}).items() if value not in (None, "")
    }
    selected_size = (
        str(slot_patch_dict.get("tire_size") or "").strip()
        or str(slot_patch_dict.get("tire_size_front") or "").strip()
        or str(slot_patch_dict.get("tire_size_rear") or "").strip()
    )
    trace_metadata = {
        "vehicle_selection_detected": True,
        "selection_source": selection_source,
        "selected_car_no": _vehicle_value(selected_vehicle, "carNo", "car_no", "licensePlate"),
        "selected_tire_size": selected_size or None,
        "previous_car_no": str((previous_slots or {}).get("car_no") or ""),
        "previous_tire_size": str((previous_slots or {}).get("tire_size") or ""),
        "slots_rewritten": False,
        "contract_intent_before_router": _VEHICLE_TIRE_SIZE_LOOKUP_INTENT,
        "final_contract_intent": _VEHICLE_TIRE_SIZE_LOOKUP_INTENT,
    }
    return UIActionContext(
        action_type="select_vehicle",
        action_name="select_vehicle_candidate",
        selection_source=selection_source,
        contract_intent=_VEHICLE_TIRE_SIZE_LOOKUP_INTENT,
        source_intent=source_intent or _VEHICLE_TIRE_SIZE_LOOKUP_INTENT,
        expected_contract_intent=expected_contract_intent or _VEHICLE_TIRE_SIZE_LOOKUP_INTENT,
        expected_behavior="conversation_action",
        entity_type="vehicle",
        entity_id=_vehicle_value(selected_vehicle, "carNo", "car_no", "licensePlate") or None,
        entity_label=_vehicle_value(selected_vehicle, "carNo", "car_no", "licensePlate") or None,
        slots=dict(slot_patch_dict),
        slot_patch=slot_patch_dict,
        trace_metadata=trace_metadata,
        raw_metadata=dict(selection_context),
        payload=selected_vehicle,
    )


def apply_ui_action_slot_patch(
    base_slots: Any,
    action_context: UIActionContext | None,
    *,
    slot_apply_fn: Callable[[Any, dict[str, Any]], Any],
) -> tuple[Any, dict[str, Any]]:
    if action_context is None or not action_context.slot_patch:
        return base_slots, dict(action_context.trace_metadata) if action_context is not None else {}

    updated_slots = slot_apply_fn(base_slots, dict(action_context.slot_patch))
    trace_metadata = dict(action_context.trace_metadata)
    trace_metadata["slots_rewritten"] = True
    if not trace_metadata.get("selected_tire_size"):
        trace_metadata["selected_tire_size"] = str(
            action_context.slot_patch.get("tire_size")
            or action_context.slot_patch.get("tire_size_front")
            or action_context.slot_patch.get("tire_size_rear")
            or ""
        ).strip() or None
    return updated_slots, trace_metadata


def validate_ui_actions_for_contract(
    event: Mapping[str, Any] | None,
    *,
    contract: Any | None = None,
    action_context: UIActionContext | None = None,
) -> bool:
    if not isinstance(event, Mapping) or event.get("template") != "quickReply":
        return False
    data = event.get("data")
    if not isinstance(data, dict):
        return False
    quick_replies = data.get("quickReplies")
    if not isinstance(quick_replies, list):
        return False

    metadata = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}
    contract_intent = (
        action_context.contract_intent
        if action_context is not None
        else _normalize_vehicle_contract_intent(getattr(contract, "sub_intent", None))
        or _normalize_vehicle_contract_intent(getattr(contract, "intent", None))
        or _normalize_vehicle_contract_intent(metadata.get("responseShapeKey") or metadata.get("response_shape_key"))
    )
    if contract_intent != _VEHICLE_TIRE_SIZE_LOOKUP_INTENT:
        return False

    filtered: list[dict[str, Any]] = []
    changed = False
    for chip in quick_replies:
        if not isinstance(chip, dict):
            changed = True
            continue
        label = str(chip.get("label") or "").strip()
        cta_action = str(chip.get("cta_action") or chip.get("ctaAction") or "").strip()
        if any(token in label for token in _VEHICLE_SIZE_LOOKUP_BLOCKED_LABEL_TOKENS):
            changed = True
            continue
        if cta_action:
            if cta_action not in _VEHICLE_SIZE_LOOKUP_ALLOWED_ACTIONS and label not in _VEHICLE_SIZE_LOOKUP_ALLOWED_LABELS:
                changed = True
                continue
        elif label not in _VEHICLE_SIZE_LOOKUP_ALLOWED_LABELS:
            changed = True
            continue
        filtered.append(chip)

    if not changed:
        return False

    data["quickReplies"] = filtered
    if isinstance(metadata, dict):
        metadata["ui_action_validation"] = _VEHICLE_TIRE_SIZE_LOOKUP_INTENT
    return True


def chip_context_dict(chip_context: Any | None) -> dict[str, Any]:
    if isinstance(chip_context, dict):
        return chip_context
    if hasattr(chip_context, "model_dump"):
        dumped = chip_context.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    return {}


def chip_value(chip_context: Mapping[str, Any] | None, *keys: str) -> str:
    normalized_context = chip_context_dict(chip_context)
    if not normalized_context:
        return ""
    for key in keys:
        value = normalized_context.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _normalize_vehicle_match_text(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(value or "")).lower()


def _selection_context_from_vehicle_meta(meta: Mapping[str, Any]) -> dict[str, str]:
    return {
        "source_intent": str(meta.get("source_intent") or meta.get("sourceIntent") or "").strip(),
        "expected_contract_intent": str(
            meta.get("expected_contract_intent") or meta.get("expectedContractIntent") or ""
        ).strip(),
    }


def _strip_vehicle_particle(token: str) -> str:
    stripped = token
    for suffix in ("으로", "에서", "하고", "이랑", "처럼", "이라", "이고", "인데", "으로요"):
        if len(stripped) > len(suffix) + 1 and stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)]
            break
    for suffix in ("은", "는", "이", "가", "을", "를", "에", "도", "와", "과", "로", "요"):
        if len(stripped) > len(suffix) + 1 and stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)]
            break
    return stripped


def _vehicle_match_tokens(user_text: str) -> list[str]:
    tokens: list[str] = []
    for raw in re.findall(r"[0-9a-zA-Z가-힣]+", user_text or ""):
        token = _strip_vehicle_particle(_normalize_vehicle_match_text(raw))
        if len(token) < 2 or token in _VEHICLE_MATCH_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _vehicle_candidate_tokens(car: Mapping[str, Any], meta: Mapping[str, Any]) -> set[str]:
    source_values = [
        car.get("licensePlate"),
        car.get("info"),
        car.get("description"),
        meta.get("carNo"),
        meta.get("carLncCd"),
        meta.get("carMaker"),
        meta.get("carModelDet"),
        meta.get("carName"),
        meta.get("carTrim"),
        meta.get("carEngine"),
    ]
    tokens: set[str] = set()
    for value in source_values:
        for raw in re.findall(r"[0-9a-zA-Z가-힣]+", str(value or "")):
            token = _normalize_vehicle_match_text(raw)
            if len(token) >= 2:
                tokens.add(token)
    return tokens


def _selection_ordinal_index(user_text: str, item_count: int) -> int | None:
    if not user_text or item_count <= 0:
        return None

    text = user_text.strip()
    numeric_match = re.match(r"^\s*(\d+)\s*(?:[\.\)번:]|번째|째)", text)
    if numeric_match:
        idx = int(numeric_match.group(1)) - 1
        return idx if 0 <= idx < item_count else None

    compact = re.sub(r"\s+", "", text)
    if compact.startswith(("마지막", "끝번째", "끝째")):
        return item_count - 1

    for prefixes, idx in _KOREAN_SELECTION_ORDINALS:
        if any(compact.startswith(prefix) for prefix in prefixes):
            return idx if idx < item_count else None
    return None


def resolve_vehicle_ui_selection_from_chip_context(
    chip_context: Mapping[str, Any] | None,
    template_data: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    chip = chip_context_dict(chip_context)
    if not chip or str(chip.get("cta_action") or "").strip() != "select_vehicle_candidate":
        return None
    if not isinstance(template_data, Mapping):
        return None

    latest_listcar: Mapping[str, Any] | None = None
    if template_data.get("template") == "listCar" and isinstance(template_data.get("data"), Mapping):
        latest_listcar = template_data.get("data")
    elif isinstance(template_data.get("listCar"), list):
        latest_listcar = template_data
    if latest_listcar is None:
        return None

    cars = latest_listcar.get("listCar") or []
    metadata = latest_listcar.get("metadata") or []
    if not isinstance(cars, list) or not isinstance(metadata, list) or len(cars) != len(metadata):
        return None

    raw_meta = chip.get("metadata")
    selection_meta = dict(raw_meta) if isinstance(raw_meta, Mapping) else {}
    car_no = _normalize_vehicle_match_text(
        chip.get("car_no") or chip.get("carNo") or selection_meta.get("car_no") or selection_meta.get("carNo")
    )
    mbr_car_reg_seq = str(
        chip.get("mbr_car_reg_seq")
        or chip.get("mbrCarRegSeq")
        or selection_meta.get("mbr_car_reg_seq")
        or selection_meta.get("mbrCarRegSeq")
        or ""
    ).strip()
    car_lnc_cd = str(
        chip.get("car_lnc_cd")
        or chip.get("carLncCd")
        or selection_meta.get("car_lnc_cd")
        or selection_meta.get("carLncCd")
        or ""
    ).strip()
    if not any((car_no, mbr_car_reg_seq, car_lnc_cd)):
        return None

    matches: list[dict[str, Any]] = []
    for car, meta in zip(cars, metadata):
        if not isinstance(car, Mapping) or not isinstance(meta, Mapping):
            continue
        meta_car_no = _normalize_vehicle_match_text(meta.get("carNo") or car.get("licensePlate"))
        meta_reg_seq = str(meta.get("mbrCarRegSeq") or "").strip()
        meta_car_lnc_cd = str(meta.get("carLncCd") or "").strip()
        if car_no and meta_car_no != car_no:
            continue
        if mbr_car_reg_seq and meta_reg_seq != mbr_car_reg_seq:
            continue
        if car_lnc_cd and meta_car_lnc_cd != car_lnc_cd:
            continue
        matches.append(
            {
                "car": dict(car),
                "meta": dict(meta),
                "selection_context": {
                    "source_intent": str(
                        chip.get("source_intent")
                        or selection_meta.get("source_intent")
                        or selection_meta.get("sourceIntent")
                        or ""
                    ).strip(),
                    "expected_contract_intent": str(
                        chip.get("expected_contract_intent")
                        or selection_meta.get("expected_contract_intent")
                        or selection_meta.get("expectedContractIntent")
                        or ""
                    ).strip(),
                },
            }
        )
    return matches[0] if len(matches) == 1 else None


def rewrite_vehicle_selection_user_text(
    last_user_text: str,
    selected_vehicle: Mapping[str, Any] | None,
) -> str:
    if selected_vehicle is None:
        return last_user_text
    selection_context = selected_vehicle.get("selection_context")
    if not isinstance(selection_context, Mapping):
        return last_user_text
    source_intent = str(selection_context.get("source_intent") or "").strip()
    selected_car = selected_vehicle.get("car") if isinstance(selected_vehicle.get("car"), Mapping) else {}
    selected_meta = selected_vehicle.get("meta") if isinstance(selected_vehicle.get("meta"), Mapping) else {}
    car_no = str(selected_meta.get("carNo") or selected_car.get("licensePlate") or last_user_text or "").strip()
    if source_intent == "vehicle_tire_size_lookup":
        return f"{car_no} 차량 타이어 사이즈 알려줘"
    return last_user_text


def resolve_vehicle_selection_from_listcar_event(
    user_text: str,
    event_data: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not _VEHICLE_BOUND_REQUEST_RE.search(user_text or ""):
        return None
    if not isinstance(event_data, Mapping):
        return None
    cars = event_data.get("listCar")
    metadata = event_data.get("metadata")
    if not isinstance(cars, list) or not isinstance(metadata, list) or not cars or len(cars) != len(metadata):
        return None

    plate_match = _VEHICLE_PLATE_RE.search(user_text or "")
    if plate_match:
        target_plate = _normalize_vehicle_match_text(plate_match.group(0))
        plate_matches: list[dict[str, Any]] = []
        for car, meta in zip(cars, metadata):
            if not isinstance(car, Mapping) or not isinstance(meta, Mapping):
                continue
            plate = _normalize_vehicle_match_text(meta.get("carNo") or car.get("licensePlate"))
            if plate == target_plate:
                plate_matches.append(
                    {"car": dict(car), "meta": dict(meta), "selection_context": _selection_context_from_vehicle_meta(meta)}
                )
        return plate_matches[0] if len(plate_matches) == 1 else None

    tokens = _vehicle_match_tokens(user_text)
    if not tokens:
        return None

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for car, meta in zip(cars, metadata):
        if not isinstance(car, Mapping) or not isinstance(meta, Mapping):
            continue
        candidate_tokens = _vehicle_candidate_tokens(car, meta)
        matched_tokens = [token for token in tokens if token in candidate_tokens]
        if not matched_tokens:
            continue
        strong_matches = sum(1 for token in matched_tokens if any(ch.isdigit() for ch in token) or len(token) >= 3)
        scored.append(
            (
                len(matched_tokens),
                strong_matches,
                {"car": dict(car), "meta": dict(meta), "selection_context": _selection_context_from_vehicle_meta(meta)},
            )
        )
    if not scored:
        return None
    max_score = max(score for score, _, _ in scored)
    top = [entry for entry in scored if entry[0] == max_score]
    max_strong = max(strong for _, strong, _ in top)
    top = [match for score, strong, match in top if strong == max_strong]
    if len(top) != 1:
        return None
    if max_score == 1 and max_strong == 0:
        return None
    return top[0]


def resolve_vehicle_from_history_template(
    user_text: str,
    template_data: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not user_text or not isinstance(template_data, Mapping):
        return None

    latest_listcar: Mapping[str, Any] | None = None
    if template_data.get("template") == "listCar" and isinstance(template_data.get("data"), Mapping):
        latest_listcar = template_data.get("data")
    elif isinstance(template_data.get("listCar"), list):
        latest_listcar = template_data
    if latest_listcar is None:
        return None

    cars = latest_listcar.get("listCar") or []
    metadata = latest_listcar.get("metadata") or []
    if not isinstance(cars, list) or not isinstance(metadata, list) or len(cars) != len(metadata):
        return None

    ordinal_idx = _selection_ordinal_index(str(user_text or ""), len(metadata))
    if ordinal_idx is not None:
        car = cars[ordinal_idx]
        meta = metadata[ordinal_idx]
        if isinstance(car, Mapping) and isinstance(meta, Mapping):
            return {"car": dict(car), "meta": dict(meta), "selection_context": _selection_context_from_vehicle_meta(meta)}

    tokens = _vehicle_match_tokens(str(user_text or ""))
    if tokens:
        scored: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
        for car, meta in zip(cars, metadata):
            if not isinstance(car, Mapping) or not isinstance(meta, Mapping):
                continue
            candidate_tokens = _vehicle_candidate_tokens(car, meta)
            matched_tokens = [token for token in tokens if token in candidate_tokens]
            if not matched_tokens:
                continue
            strong_matches = sum(1 for token in matched_tokens if any(ch.isdigit() for ch in token) or len(token) >= 3)
            scored.append((len(matched_tokens), strong_matches, dict(car), dict(meta)))
        if scored:
            max_score = max(score for score, _, _, _ in scored)
            top = [entry for entry in scored if entry[0] == max_score]
            max_strong = max(strong for _, strong, _, _ in top)
            top = [entry for entry in top if entry[1] == max_strong]
            if max_score == 1 and max_strong == 0:
                return None
            if len(top) == 1:
                _, _, car, meta = top[0]
                return {"car": car, "meta": meta, "selection_context": _selection_context_from_vehicle_meta(meta)}

    return resolve_vehicle_selection_from_listcar_event(user_text, latest_listcar)


def resolve_tire_size_from_history_template(
    user_text: str,
    template_data: Mapping[str, Any] | None,
) -> str | None:
    if not user_text or not isinstance(template_data, Mapping):
        return None
    selected_vehicle = resolve_vehicle_from_history_template(user_text, template_data)
    if selected_vehicle is None:
        return None
    selected_meta = selected_vehicle.get("meta")
    if not isinstance(selected_meta, Mapping):
        return None
    front_size = normalize_tire_size(str(selected_meta.get("tireSize") or selected_meta.get("tire_size") or ""))
    rear_size = normalize_tire_size(str(selected_meta.get("tireSizeRe") or selected_meta.get("tire_size_re") or ""))
    if front_size and rear_size and front_size != rear_size:
        return None
    return front_size or rear_size or None


def resolve_store_selection_from_history_template(
    user_text: str,
    template_data: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not user_text or not isinstance(template_data, Mapping):
        return None

    text = user_text.strip()
    target_template: Mapping[str, Any] | None = None
    if template_data.get("template") == "location" and isinstance(template_data.get("data"), Mapping):
        target_template = template_data.get("data")
    elif isinstance(template_data.get("stores"), list):
        target_template = template_data
    if not target_template:
        return None

    stores = target_template.get("stores") or []
    metadata = target_template.get("metadata") or []
    if not isinstance(stores, list) or not isinstance(metadata, list):
        return None
    if not stores or len(stores) != len(metadata):
        return None

    store_select_chips = frozenset({"이 매장 선택", "이 매장으로", "이곳 선택"})
    if text in store_select_chips and len(stores) == 1:
        meta = metadata[0]
        store = stores[0]
        canonical_meta = canonical_context_from_template_boundary(meta) if isinstance(meta, Mapping) else {}
        if isinstance(meta, Mapping) and isinstance(store, Mapping) and canonical_meta.get("shop_id"):
            return {"store": dict(store), "meta": dict(meta)}

    ordinal_idx = _selection_ordinal_index(text, len(metadata))
    if ordinal_idx is not None:
        meta = metadata[ordinal_idx]
        store = stores[ordinal_idx]
        canonical_meta = canonical_context_from_template_boundary(meta) if isinstance(meta, Mapping) else {}
        if isinstance(meta, Mapping) and isinstance(store, Mapping) and canonical_meta.get("shop_id"):
            return {"store": dict(store), "meta": dict(meta)}

    tokens = [t for t in re.findall(r"[A-Za-z가-힣]+", text) if len(t) >= 2]
    if tokens:
        scored: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
        for store, meta in zip(stores, metadata):
            if not isinstance(store, Mapping) or not isinstance(meta, Mapping):
                continue
            name = store.get("nameAddress") or store.get("name") or store.get("title") or ""
            score = sum(1 for tok in tokens if tok in str(name))
            if score > 0:
                scored.append((score, dict(store), dict(meta)))
        if scored:
            max_score = max(s for s, _, _ in scored)
            top = [(store, meta) for s, store, meta in scored if s == max_score]
            if len(top) == 1:
                store, meta = top[0]
                canonical_meta = canonical_context_from_template_boundary(meta)
                if canonical_meta.get("shop_id"):
                    return {"store": store, "meta": meta}
    return None


def resolve_shop_id_from_history_template(
    user_text: str,
    template_data: Mapping[str, Any] | None,
) -> str | None:
    selected = resolve_store_selection_from_history_template(user_text, template_data)
    if selected is None:
        return None
    meta = selected.get("meta")
    canonical_meta = canonical_context_from_template_boundary(meta) if isinstance(meta, Mapping) else {}
    shop_id = canonical_meta.get("shop_id")
    return str(shop_id).strip() or None


def preview_location_slot_values_from_selection(selection: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(selection, Mapping):
        return None
    meta = selection.get("meta")
    if not isinstance(meta, Mapping):
        return None
    if (meta.get("sourceTool") or meta.get("source_tool")) != "transaction_store_preview_tool":
        return None

    values: dict[str, Any] = {}
    canonical_meta = canonical_context_from_template_boundary(meta)
    shop_id = str(canonical_meta.get("shop_id") or "").strip()
    if shop_id:
        values["shop_id"] = shop_id
    shop_name = str(canonical_meta.get("shop_name") or "").strip()
    if shop_name:
        values["shop_name"] = shop_name
    goods_no = str(canonical_meta.get("goods_no") or "").strip()
    if goods_no:
        values["goods_no"] = goods_no
    tire_size = normalize_tire_size(canonical_meta.get("tire_size") or "")
    if tire_size:
        values["tire_size"] = tire_size
    raw_qty = canonical_meta.get("ord_qty")
    if raw_qty is not None:
        try:
            qty = int(raw_qty)
            if qty > 0:
                values["ord_qty"] = qty
        except (TypeError, ValueError):
            pass
    region = str(canonical_meta.get("region") or "").strip()
    if region:
        values["region"] = region
    pending_intent = str(meta.get("pendingIntent") or "").strip()
    if pending_intent in {"stock", "order"}:
        values["pending_intent"] = pending_intent
    goal_type = str(meta.get("goalType") or "").strip()
    if goal_type in {"store_with_stock", "place_order"}:
        values["goal_type"] = goal_type
    if not values.get("pending_intent") and values.get("goods_no") and values.get("ord_qty"):
        values["pending_intent"] = "stock"
    if not values.get("goal_type") and values.get("goods_no") and values.get("ord_qty"):
        values["goal_type"] = "store_with_stock"
    return values or None


def resolve_shop_id_from_selection(user_text: str, prev_tool_data: list[dict[str, Any]]) -> str | None:
    if not user_text or not prev_tool_data:
        return None

    store_tools = {"search_stores_tool", "get_nearby_stores_tool", "get_store_list_tool"}
    items: list[dict[str, Any]] = []
    for entry in prev_tool_data:
        if entry.get("tool") not in store_tools:
            continue
        data = entry.get("data")
        if isinstance(data, list):
            items = [it for it in data if isinstance(it, dict) and not it.get("_truncated")]
            break
        if isinstance(data, Mapping) and isinstance(data.get("stores"), list):
            items = [it for it in data["stores"] if isinstance(it, dict)]
            break
    if not items:
        return None

    text = user_text.strip()
    store_select_chips = frozenset({"이 매장 선택", "이 매장으로", "이곳 선택"})
    if text in store_select_chips and len(items) == 1:
        shop_id = canonical_context_from_tool_boundary(items[0]).get("shop_id")
        if shop_id:
            return str(shop_id)

    ordinal_idx = _selection_ordinal_index(text, len(items))
    if ordinal_idx is not None:
        shop_id = canonical_context_from_tool_boundary(items[ordinal_idx]).get("shop_id")
        if shop_id:
            return str(shop_id)

    tokens = [t for t in re.findall(r"[A-Za-z가-힣]+", text) if len(t) >= 2]
    if tokens:
        scored: list[tuple[int, dict[str, Any]]] = []
        for item in items:
            canonical_item = canonical_context_from_tool_boundary(item)
            shop_nm = str(canonical_item.get("shop_name") or "")
            score = sum(1 for tok in tokens if tok in shop_nm)
            if score > 0:
                scored.append((score, item))
        if scored:
            max_score = max(s for s, _ in scored)
            top = [item for s, item in scored if s == max_score]
            if len(top) == 1:
                shop_id = canonical_context_from_tool_boundary(top[0]).get("shop_id")
                if shop_id:
                    return str(shop_id)
    return None


def resolve_goods_no_from_selection(
    user_text: str,
    prev_tool_data: list[dict[str, Any]],
    current_tire_size: str | None = None,
) -> str | None:
    if not user_text or not prev_tool_data:
        return None

    product_list_tools = {"search_product_tool", "get_products_recommendations_tool"}
    items: list[dict[str, Any]] = []
    for entry in reversed(prev_tool_data):
        if entry.get("tool") not in product_list_tools:
            continue
        data = entry.get("data")
        if isinstance(data, list):
            items = [it for it in data if isinstance(it, dict) and not it.get("_truncated")]
            break
        if isinstance(data, Mapping) and isinstance(data.get("items"), list):
            items = [it for it in data["items"] if isinstance(it, dict)]
            break
    if not items:
        return None

    text = str(user_text).strip()
    ordinal_idx = _selection_ordinal_index(text, len(items))
    if ordinal_idx is not None:
        goods_no = canonical_context_from_tool_boundary(items[ordinal_idx]).get("goods_no")
        if goods_no:
            return str(goods_no)

    target_size_from_text = normalize_tire_size(text)
    target_size = target_size_from_text or normalize_tire_size(current_tire_size or "")
    if not target_size:
        return None

    same_size = [
        item
        for item in items
        if normalize_tire_size(canonical_context_from_tool_boundary(item).get("tire_size")) == target_size
    ]
    if target_size_from_text and len(same_size) == 1:
        goods_no = canonical_context_from_tool_boundary(same_size[0]).get("goods_no")
        if goods_no:
            return str(goods_no)

    tokens = [t.lower() for t in re.findall(r"[A-Za-z가-힣0-9]+", text) if len(t) >= 2]
    best_item: dict[str, Any] | None = None
    best_score = 0
    tied = False
    for item in same_size:
        goods_nm = str(canonical_context_from_tool_boundary(item).get("product_name") or "").lower()
        score = sum(1 for tok in tokens if tok in goods_nm)
        if score > best_score:
            best_score = score
            best_item = item
            tied = False
        elif score == best_score and score > 0:
            tied = True
    if best_item is not None and best_score >= 2 and not tied:
        goods_no = canonical_context_from_tool_boundary(best_item).get("goods_no")
        if goods_no:
            return str(goods_no)
    return None


def build_order_quantity_prompt_event(slots: Any) -> dict[str, Any]:
    selected_size = normalize_tire_size(str(getattr(slots, "tire_size", None) or ""))
    front_size = normalize_tire_size(str(getattr(slots, "tire_size_front", None) or ""))
    rear_size = normalize_tire_size(str(getattr(slots, "tire_size_rear", None) or ""))
    is_staggered = bool(front_size and rear_size and front_size != rear_size)

    if is_staggered:
        axle_label = "앞바퀴" if selected_size == front_size else "뒷바퀴" if selected_size == rear_size else "현재"
        assistant_response = (
            f"{axle_label} **{selected_size}** 기준으로 몇 개 구매하실까요?\n\n"
            "이 차량은 앞/뒤 규격이 달라 현재 규격은 최대 2개까지 선택할 수 있어요."
        )
        quick_replies = [
            {"label": "1개", "domain": "TRANSACTION"},
            {"label": "2개", "domain": "TRANSACTION"},
        ]
    else:
        size_text = f" **{selected_size}** 기준으로" if selected_size else ""
        assistant_response = f"타이어{size_text} 몇 개 구매하실까요?"
        quick_replies = [
            {"label": "1개", "domain": "TRANSACTION"},
            {"label": "2개", "domain": "TRANSACTION"},
            {"label": "3개", "domain": "TRANSACTION"},
            {"label": "4개", "domain": "TRANSACTION"},
        ]

    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_order_quantity_prompt",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": quick_replies,
            "predictedDomains": ["TRANSACTION"],
        },
    }


def resolve_goods_no_from_product_template_selection(user_text: str, template_data: Mapping[str, Any] | None) -> str | None:
    if not user_text or not isinstance(template_data, Mapping):
        return None
    data = template_data.get("data") if isinstance(template_data.get("data"), Mapping) else template_data
    if not isinstance(data, Mapping):
        return None
    products = data.get("products")
    metadata = data.get("metadata")
    if not isinstance(products, list) or not isinstance(metadata, list):
        return None
    if not products or len(products) != len(metadata):
        return None

    text = user_text.strip()
    ordinal_idx = _selection_ordinal_index(text, len(metadata))
    if ordinal_idx is not None and isinstance(metadata[ordinal_idx], Mapping):
        goods_no = str(canonical_context_from_template_boundary(metadata[ordinal_idx]).get("goods_no") or "").strip()
        return goods_no or None

    target_size = normalize_tire_size(text)
    tokens = [t.lower() for t in re.findall(r"[A-Za-z가-힣0-9]+", text) if len(t) >= 2]
    best_goods_no = ""
    best_score = 0
    tied = False
    for product, meta in zip(products, metadata):
        if not isinstance(product, Mapping) or not isinstance(meta, Mapping):
            continue
        canonical_product = canonical_context_from_template_boundary(product)
        canonical_meta = canonical_context_from_template_boundary(meta)
        product_size = normalize_tire_size(str(canonical_product.get("tire_size") or ""))
        if target_size and product_size != target_size:
            continue
        title = " ".join(
            str(part or "")
            for part in (
                canonical_product.get("product_name"),
                product.get("title"),
            )
        ).lower()
        score = sum(1 for token in tokens if token in title)
        goods_no = str(canonical_meta.get("goods_no") or "").strip()
        if score > best_score:
            best_score = score
            best_goods_no = goods_no
            tied = False
        elif score == best_score and score > 0:
            tied = True
    if best_goods_no and best_score >= 2 and not tied:
        return best_goods_no
    return None


def goods_no_from_template_event(event: Mapping[str, Any] | None) -> str:
    if not isinstance(event, Mapping):
        return ""
    data = event.get("data")
    if not isinstance(data, Mapping):
        return ""
    metadata = data.get("metadata")
    if isinstance(metadata, Mapping):
        canonical_metadata = canonical_context_from_template_boundary(metadata)
        goods_no = str(canonical_metadata.get("goods_no") or metadata.get("goodsIdList") or "").strip()
        if goods_no.startswith("G"):
            return goods_no
    for key in ("products", "productList", "items"):
        rows = data.get(key)
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
            continue
        row_goods_no = str(canonical_context_from_template_boundary(rows[0]).get("goods_no") or "").strip()
        if row_goods_no.startswith("G"):
            return row_goods_no
    return ""


def build_store_availability_quantity_prompt_event(
    *,
    product_keyword: str,
    tire_size: str,
    store_name: str | None,
    goods_no: str | None = None,
    requested_day_label: str = "오늘",
) -> dict[str, Any]:
    store_label = str(store_name or "해당 매장").strip()
    day_label = str(requested_day_label or "오늘").strip()
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_store_availability_size_followup_quantity_prompt",
        "data": {
            "assistantResponse": (
                f"{product_keyword} {tire_size} 상품은 확인했어요. "
                f"{store_label} {day_label} 장착 가능 여부를 확인하려면 장착 수량을 알려주세요."
            ),
            "quickReplies": [
                {"label": "1개", "domain": "TRANSACTION"},
                {"label": "2개", "domain": "TRANSACTION"},
                {"label": "3개", "domain": "TRANSACTION"},
                {"label": "4개", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["TRANSACTION"],
            "metadata": {
                "goodsId": goods_no,
                "goodsNo": goods_no,
                "goods_no": goods_no,
                "tireSize": tire_size,
                "tire_size": tire_size,
                "productName": product_keyword,
                "product_name": product_keyword,
                "storeName": store_name,
            },
        },
    }


def quickreply_cta_context_from_template(template_data: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(template_data, Mapping):
        return {}
    data = template_data.get("data") if isinstance(template_data.get("data"), Mapping) else template_data
    metadata = data.get("metadata") if isinstance(data, Mapping) else None
    if not isinstance(metadata, Mapping):
        return {}
    cta_context = metadata.get("ctaContext")
    return dict(cta_context) if isinstance(cta_context, Mapping) else {}


def quickreply_cta_context_from_chip(chip_context: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized_context = chip_context_dict(chip_context)
    if not normalized_context:
        return {}
    metadata = normalized_context.get("metadata")
    context = dict(metadata) if isinstance(metadata, Mapping) else {}
    for key in (
        "cta_id",
        "cta_action",
        "expected_behavior",
        "source_intent",
        "expected_contract_intent",
    ):
        value = normalized_context.get(key)
        if value not in (None, ""):
            context.setdefault(key, value)
    slots = normalized_context.get("slots")
    if isinstance(slots, Mapping) and slots:
        context.setdefault("slots", dict(slots))
    return context


def merged_quickreply_cta_context(
    chip_context: Mapping[str, Any] | None,
    latest_quickreply_tmpl: Mapping[str, Any] | None,
) -> dict[str, Any]:
    context = quickreply_cta_context_from_template(latest_quickreply_tmpl)
    context.update(quickreply_cta_context_from_chip(chip_context))
    intent_key = chip_value(chip_context, "intentKey", "intent_key")
    if intent_key:
        context.setdefault("intentKey", intent_key)
    return context


def apply_cta_context_to_slots(slots: Any, cta_context: Mapping[str, Any] | None, *, source: str = "quickreply_cta") -> Any:
    if not isinstance(cta_context, Mapping):
        return slots
    values: dict[str, Any] = {}
    canonical_context = canonical_context_from_template_boundary(cta_context)
    for key in ("goods_no", "tire_size", "ord_qty", "region", "shop_name", "requested_cal_day"):
        value = canonical_context.get(key)
        if value in (None, "", []):
            continue
        if key == "ord_qty":
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
        values[key] = value
    region_code = cta_context.get("regionCode") or cta_context.get("region_code")
    if region_code not in (None, "", []):
        values["region"] = region_code
    intent_key = cta_context.get("intentKey") or cta_context.get("intent_key")
    if intent_key not in (None, "", []):
        values["availability_intent"] = intent_key
    if values.get("availability_intent") == "today_install":
        values["pending_intent"] = getattr(slots, "pending_intent", None) or "stock"
        values["goal_type"] = getattr(slots, "goal_type", None) or "store_with_stock"
    if not values:
        return slots
    try:
        return slots.apply_runtime_values(values, source=source, fill_only=True)
    except Exception:
        for key, value in values.items():
            if getattr(slots, key, None) in (None, ""):
                setattr(slots, key, value)
        return slots


def build_quickreply_cta_clarification_event(
    user_text: str,
    chip_context: Mapping[str, Any] | None,
    *,
    cta_context: Mapping[str, Any] | None = None,
    allow_label_only: bool = True,
) -> dict[str, Any] | None:
    action_id = chip_value(chip_context, "actionId", "action_id")
    text = str(user_text or "").strip()
    metadata = dict(cta_context or {})
    intent_key = str(metadata.get("intentKey") or chip_value(chip_context, "intentKey", "intent_key") or "today_install")
    metadata.setdefault("intentKey", intent_key)
    if action_id == "enter_region" or (
        allow_label_only and re.fullmatch(r"(?:다른\s*)?(?:지역|장소)\s*(?:입력|찾기|검색)", text)
    ):
        return {
            "type": "data",
            "template": "quickReply",
            "source_domain": "transaction",
            "assistant_response_source": "code_cta_action_guard",
            "data": {
                "assistantResponse": "확인할 지역명을 입력해 주세요. 이전 상품·수량·날짜 조건을 유지해서 다시 확인할게요.",
                "quickReplies": [
                    {"label": "서울", "domain": "TRANSACTION", "actionId": "change_region", "intentKey": intent_key},
                    {"label": "강남", "domain": "TRANSACTION", "actionId": "change_region", "intentKey": intent_key},
                    {"label": "송파", "domain": "TRANSACTION", "actionId": "change_region", "intentKey": intent_key},
                ],
                "predictedDomains": ["TRANSACTION"],
                "metadata": {"ctaContext": metadata},
            },
        }
    if action_id == "enter_date" or (
        allow_label_only and re.fullmatch(r"(?:다른\s*)?(?:날짜|일정)\s*(?:입력|확인|찾기|검색)", text)
    ):
        return {
            "type": "data",
            "template": "quickReply",
            "source_domain": "transaction",
            "assistant_response_source": "code_cta_action_guard",
            "data": {
                "assistantResponse": "확인할 날짜를 입력해 주세요. 예: 오늘, 내일, 6월 20일",
                "quickReplies": [
                    {"label": "오늘", "domain": "TRANSACTION", "actionId": "change_date", "intentKey": intent_key},
                    {"label": "내일", "domain": "TRANSACTION", "actionId": "change_date", "intentKey": intent_key},
                ],
                "predictedDomains": ["TRANSACTION"],
                "metadata": {"ctaContext": metadata},
            },
        }
    return None


def is_logistics_earliest_install_date_followup(
    user_text: str,
    cta_context: Mapping[str, Any] | None,
) -> bool:
    context = cta_context if isinstance(cta_context, Mapping) else {}
    if str(context.get("followupMode") or "") == "logistics_earliest_install_date":
        return True
    if not context.get("logisticsStockAvailable"):
        return False
    return bool(re.search(r"가장\s*빠른\s*(?:예약일|장착일|날짜)|예약일\s*확인|장착일\s*확인", user_text or ""))


def classify_direct_cta_action(
    *,
    chip_action_id: str | None,
    user_text: str,
    cta_context: Mapping[str, Any] | None,
    allow_label_only_clarification: bool = True,
    stock_store_candidate_search_followup: bool = False,
) -> str | None:
    action_id = str(chip_action_id or "").strip()
    text = str(user_text or "").strip()
    if action_id in {"enter_region", "enter_date"}:
        return "clarification"
    if not action_id and allow_label_only_clarification and _CTA_CLARIFICATION_LABEL_RE.fullmatch(text):
        return "clarification"
    if action_id == "search_other_store" or (not action_id and stock_store_candidate_search_followup):
        return "search_other_store"
    if action_id == "logistics_earliest_install_date" or (
        not action_id and is_logistics_earliest_install_date_followup(text, cta_context)
    ):
        return "logistics_earliest_install_date"
    if action_id in {"change_region", "change_date"}:
        return "preview_update"
    return None


def apply_preview_update_cta_action(
    slots: Any,
    *,
    chip_action_id: str | None,
    user_text: str,
    cta_context: Mapping[str, Any] | None,
    regex_region: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    updated_slots = apply_cta_context_to_slots(slots, cta_context)
    action_id = str(chip_action_id or "").strip()
    if action_id == "change_region":
        if regex_region:
            updated_slots.region = regex_region
        elif str(user_text or "").strip():
            updated_slots.region = re.sub(r"(?:은|는|으로|로|에서|에는|\?)\s*$", "", str(user_text).strip())
        updated_slots.shop_id = None
        updated_slots.shop_name = None
    elif action_id == "change_date":
        cleaned_text = str(user_text or "").strip()
        if cleaned_text:
            digits = re.sub(r"[^0-9]", "", cleaned_text)
            if len(digits) == 8:
                updated_slots.requested_cal_day = digits
        if not getattr(updated_slots, "availability_intent", None):
            updated_slots.availability_intent = "today_install"
    if getattr(updated_slots, "availability_intent", None) == "today_install":
        updated_slots.pending_intent = getattr(updated_slots, "pending_intent", None) or "stock"
        updated_slots.goal_type = getattr(updated_slots, "goal_type", None) or "store_with_stock"
    metadata = {
        "chip_action_id": action_id,
        "resolved_region": getattr(updated_slots, "region", None),
        "resolved_requested_cal_day": getattr(updated_slots, "requested_cal_day", None),
        "pending_intent": getattr(updated_slots, "pending_intent", None),
        "goal_type": getattr(updated_slots, "goal_type", None),
    }
    return updated_slots, metadata


def apply_logistics_earliest_install_cta_action(
    slots: Any,
    *,
    cta_context: Mapping[str, Any] | None,
) -> tuple[Any, dict[str, Any]]:
    updated_slots = apply_cta_context_to_slots(slots, cta_context)
    updated_slots.pending_intent = "stock"
    updated_slots.goal_type = "store_with_stock"
    metadata = {
        "stock_check_mode": "logistics_only",
        "pending_intent": getattr(updated_slots, "pending_intent", None),
        "goal_type": getattr(updated_slots, "goal_type", None),
        "requested_cal_day": getattr(updated_slots, "requested_cal_day", None),
        "availability_intent": getattr(updated_slots, "availability_intent", None),
    }
    return updated_slots, metadata


def preview_action_mode_for_slots(slots: Any) -> str:
    pending_intent = str(getattr(slots, "pending_intent", None) or "").strip()
    goal_type = str(getattr(slots, "goal_type", None) or "").strip()
    if pending_intent == "order" or goal_type == "place_order":
        return "purchase_continuation"
    if pending_intent == "stock" or goal_type == "store_with_stock":
        return "stock_check"
    return "booking_continuation"


def _format_yyyymmdd_korean(value: str | None) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if len(digits) != 8:
        return ""
    return f"{int(digits[:4])}년 {int(digits[4:6])}월 {int(digits[6:8])}일"


def build_logistics_earliest_install_fallback_event(
    *,
    cta_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    context = dict(cta_context or {})
    install_date = str(context.get("rsvInstallDate") or "").strip()
    install_date_text = _format_yyyymmdd_korean(install_date) if install_date else ""
    response = (
        f"물류 재고 기준으로는 {install_date_text} 이후 장착 가능 여부를 확인할 수 있어요. "
        "정확한 예약 시간은 매장과 날짜를 확정한 뒤 확인해 주세요."
        if install_date_text
        else "물류 재고는 확인되지만 현재 가장 빠른 예약일은 확정되지 않았어요. 다른 매장이나 상품으로 확인해드릴게요."
    )
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_logistics_earliest_install_date",
        "data": {
            "assistantResponse": response,
            "quickReplies": [
                {"label": "다른 매장 오늘장착 확인", "domain": "TRANSACTION"},
                {"label": "다른 날짜 확인", "domain": "TRANSACTION"},
                {"label": "다른 상품 추천", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["TRANSACTION", "DISCOVERY"],
            "metadata": {
                "response_shape_key": "logistics_earliest_install_date",
                "stock_check_mode": "logistics_only",
                "ctaContext": context,
            },
        },
    }


def _unwrap_tool_data(tool_result: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(tool_result, Mapping):
        return {}
    data = tool_result.get("data")
    return data if isinstance(data, Mapping) else dict(tool_result)


def _preview_today_shop_ids(tool_result: Mapping[str, Any] | None) -> set[str]:
    data = _unwrap_tool_data(tool_result)
    inventory = data.get("inventory") if isinstance(data, Mapping) else None
    if not isinstance(inventory, Mapping):
        return set()
    rows = inventory.get("todayShopArray")
    if not isinstance(rows, list):
        return set()
    result: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        shop_id = str(canonical_context_from_tool_boundary(row).get("shop_id") or "").strip()
        if shop_id:
            result.add(shop_id)
    return result


def build_other_store_stock_unavailable_event(
    *,
    store_name: str,
    searched_by_radius: bool,
) -> dict[str, Any]:
    store_label = store_name or "직전 매장"
    scope = f"{store_label} 기준 반경 20km 내 다른 매장" if searched_by_radius else f"{store_label} 주변 다른 매장"
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_other_store_stock_search",
        "data": {
            "assistantResponse": f"{scope}에서도 오늘 장착 가능한 재고는 확인되지 않아요.",
            "quickReplies": [
                {"label": "다른 지역 입력", "domain": "TRANSACTION", "actionId": "enter_region", "intentKey": "today_install"},
                {"label": "다른 날짜 확인", "domain": "TRANSACTION", "actionId": "enter_date", "intentKey": "today_install"},
                {"label": "대체상품 찾기", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["TRANSACTION", "DISCOVERY"],
            "metadata": {
                "response_shape_key": "other_store_stock_unavailable",
                "stock_check_mode": "inventory_only",
                "radiusKm": 20 if searched_by_radius else None,
            },
        },
    }


def build_other_store_search_result_event(
    *,
    preview_result: Mapping[str, Any] | None,
    preview_input: Mapping[str, Any] | None,
    previous_store_name: str,
    excluded_ids: set[str] | None,
    template_builder: Callable[[list[dict[str, Any]], str], dict[str, Any] | None],
) -> dict[str, Any]:
    input_payload = dict(preview_input or {})
    excluded = {str(shop_id) for shop_id in (excluded_ids or set()) if shop_id}
    searched_by_radius = input_payload.get("user_xpos") is not None and input_payload.get("user_ypos") is not None
    today_shop_ids = _preview_today_shop_ids(preview_result) - excluded
    if not today_shop_ids:
        return build_other_store_stock_unavailable_event(
            store_name=previous_store_name,
            searched_by_radius=searched_by_radius,
        )

    intro_scope = (
        f"{previous_store_name} 기준 반경 20km 내 다른 매장의 오늘 장착 재고를 확인했어요."
        if searched_by_radius and previous_store_name
        else "다른 매장의 오늘 장착 재고를 확인했어요."
    )
    mapped_event = template_builder(
        [{"tool": "transaction_store_preview_tool", "args": input_payload, "data": dict(preview_result or {})}],
        intro_scope,
    )
    if not isinstance(mapped_event, dict):
        return build_other_store_stock_unavailable_event(
            store_name=previous_store_name,
            searched_by_radius=searched_by_radius,
        )
    normalized_event = dict(mapped_event)
    normalized_event["source_domain"] = "transaction"
    normalized_event["assistant_response_source"] = "code_other_store_stock_search"
    return normalized_event


def normalize_ui_action_metadata(
    event: dict[str, Any],
    *,
    contract: Any | None = None,
    source_intent: str | None = None,
) -> bool:
    """Attach a shared UI-action envelope to quickReply and product templates."""

    changed = normalize_quickreply_ctas(event, contract=contract, source_intent=source_intent)
    if not isinstance(event, dict):
        return changed

    template = str(event.get("template") or "")
    data = event.get("data")
    if not isinstance(data, dict):
        return changed

    contract_intent = _normalize_vehicle_contract_intent(
        str(source_intent or getattr(contract, "intent", None) or "").strip()
    ) or _normalize_vehicle_contract_intent(
        str(getattr(contract, "sub_intent", None) or getattr(contract, "intent", None) or "").strip()
    )
    known_slots = dict(getattr(contract, "known_slots", {}) or {})
    contract_domain = str(event.get("source_domain") or getattr(contract, "domain", "") or "").upper()

    if template == "quickReply":
        quick_replies = data.get("quickReplies")
        if not isinstance(quick_replies, list):
            return changed
        for chip in quick_replies:
            if not isinstance(chip, dict):
                continue
            metadata = chip.get("metadata") if isinstance(chip.get("metadata"), Mapping) else {}
            label = str(chip.get("label") or "").strip()
            slot_values = {
                key: value for key, value in known_slots.items()
                if key in _UI_ACTION_SLOT_KEYS and value not in (None, "", [])
            }
            quantity_match = _QUANTITY_LABEL_RE.fullmatch(label)
            action_type = str(chip.get("cta_action") or metadata.get("cta_action") or "").strip()
            if quantity_match:
                slot_values["ord_qty"] = int(quantity_match.group(1))
                action_type = "select_quantity"
            if not action_type:
                continue
            expected_contract_intent = str(
                chip.get("expected_contract_intent")
                or metadata.get("expected_contract_intent")
                or contract_intent
                or ""
            ).strip()
            chip["source_intent"] = str(chip.get("source_intent") or metadata.get("source_intent") or contract_intent or "")
            chip["expected_contract_intent"] = expected_contract_intent
            chip["expected_behavior"] = str(
                chip.get("expected_behavior") or metadata.get("expected_behavior") or "conversation_action"
            )
            chip["ui_action"] = {
                "action_type": action_type,
                "cta_action": action_type,
                "expected_behavior": chip["expected_behavior"],
                "source_intent": chip["source_intent"],
                "expected_contract_intent": expected_contract_intent,
                "entity_type": "quantity" if quantity_match else "quick_reply",
                "entity_label": label,
                "slots": slot_values,
            }
            metadata = dict(metadata)
            metadata["ui_action"] = chip["ui_action"]
            if slot_values:
                metadata["slots"] = slot_values
            chip["metadata"] = metadata
            changed = True
        return changed

    if template == "product" and data.get("isBookingFlow") is True:
        products = data.get("products")
        metadata_list = data.get("metadata")
        if not isinstance(products, list) or not isinstance(metadata_list, list):
            return changed
        if len(products) != len(metadata_list):
            return changed
        expected_contract_intent = contract_intent or _STOCK_STORE_SEARCH_INTENT
        for product, metadata in zip(products, metadata_list):
            if not isinstance(product, dict) or not isinstance(metadata, dict):
                continue
            product_context = canonical_context_from_template_boundary({**product, **metadata})
            slot_values = {
                key: value for key, value in known_slots.items()
                if key in _UI_ACTION_SLOT_KEYS and value not in (None, "", [])
            }
            goods_no = str(product_context.get("goods_no") or "").strip()
            tire_size = str(product_context.get("tire_size") or "").strip()
            if goods_no:
                slot_values["goods_no"] = goods_no
            if tire_size:
                slot_values["tire_size"] = tire_size
            action_type = "select_product"
            metadata["domain"] = metadata.get("domain") or contract_domain or "TRANSACTION"
            metadata["cta_action"] = action_type
            metadata["source_intent"] = metadata.get("source_intent") or expected_contract_intent
            metadata["expected_contract_intent"] = (
                metadata.get("expected_contract_intent") or expected_contract_intent
            )
            metadata["expected_behavior"] = metadata.get("expected_behavior") or "conversation_action"
            metadata["slots"] = slot_values
            metadata["ui_action"] = {
                "action_type": action_type,
                "cta_action": action_type,
                "expected_behavior": metadata["expected_behavior"],
                "source_intent": metadata["source_intent"],
                "expected_contract_intent": metadata["expected_contract_intent"],
                "entity_type": "product",
                "entity_id": goods_no or None,
                "entity_label": str(
                    product_context.get("product_name") or product.get("titleProductName") or product.get("title") or ""
                ).strip() or None,
                "slots": slot_values,
            }
            changed = True
        return changed

    return changed


def ui_action_trace_metadata(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize emitted UI-action metadata for Langfuse trace metadata."""

    trace = cta_trace_metadata(events)
    first_ui_action: dict[str, Any] | None = None
    for event in events:
        data = event.get("data") if isinstance(event, Mapping) else None
        if not isinstance(data, Mapping):
            continue
        if event.get("template") == "quickReply":
            for chip in data.get("quickReplies") or []:
                if not isinstance(chip, Mapping):
                    continue
                ui_action = chip.get("ui_action")
                if isinstance(ui_action, Mapping):
                    first_ui_action = dict(ui_action)
                    break
        elif event.get("template") == "product":
            metadata_list = data.get("metadata")
            if isinstance(metadata_list, list):
                for metadata in metadata_list:
                    if not isinstance(metadata, Mapping):
                        continue
                    ui_action = metadata.get("ui_action")
                    if isinstance(ui_action, Mapping):
                        first_ui_action = dict(ui_action)
                        break
        if first_ui_action is not None:
            break
    if first_ui_action is not None:
        trace.update({
            "ui_action_type": first_ui_action.get("action_type"),
            "expected_contract_intent": first_ui_action.get("expected_contract_intent"),
            "source_intent": first_ui_action.get("source_intent"),
        })
    return trace
