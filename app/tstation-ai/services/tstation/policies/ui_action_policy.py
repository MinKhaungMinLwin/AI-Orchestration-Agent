"""Structured UI action policy helpers.

Keep chip/card selection handling out of ad hoc chat branches so current-turn
selection metadata can deterministically own slot rewrite, trace fields, and
CTA validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


_VEHICLE_TIRE_SIZE_LOOKUP_INTENT = "vehicle_tire_size_lookup"
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


@dataclass(frozen=True)
class UIActionContext:
    action_name: str
    selection_source: str
    contract_intent: str
    source_intent: str
    expected_contract_intent: str
    slot_patch: Mapping[str, Any] = field(default_factory=dict)
    trace_metadata: Mapping[str, Any] = field(default_factory=dict)
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


def _normalize_vehicle_contract_intent(intent: str | None) -> str:
    normalized = str(intent or "").strip()
    if normalized == "vehicle_information":
        return _VEHICLE_TIRE_SIZE_LOOKUP_INTENT
    return normalized


def resolve_ui_action_context(
    *,
    selected_vehicle: Mapping[str, Any] | None,
    selection_source: str,
    previous_slots: Mapping[str, Any] | None = None,
    slot_patch: Mapping[str, Any] | None = None,
) -> UIActionContext | None:
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
        action_name="select_vehicle_candidate",
        selection_source=selection_source,
        contract_intent=_VEHICLE_TIRE_SIZE_LOOKUP_INTENT,
        source_intent=source_intent or _VEHICLE_TIRE_SIZE_LOOKUP_INTENT,
        expected_contract_intent=expected_contract_intent or _VEHICLE_TIRE_SIZE_LOOKUP_INTENT,
        slot_patch=slot_patch_dict,
        trace_metadata=trace_metadata,
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
