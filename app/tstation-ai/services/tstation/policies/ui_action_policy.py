"""Structured UI action policy helpers.

Keep chip/card selection handling out of ad hoc chat branches so current-turn
selection metadata can deterministically own slot rewrite, trace fields, and
CTA validation.
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from schemas.tstation.slots import ConversationSlots
from services.tstation.policies.intent_frame import IntentFrame, PolicyDomain
from services.tstation.policies.transaction_intent_policy import build_transaction_intent_frame, plan_transaction_tools
from services.tstation.policies.transaction_response_policy import decide_transaction_response
from services.tstation.policies.turn_contract import build_turn_contract
from services.tstation.policies.discovery_intent_policy import build_discovery_intent_frame, normalize_tire_size
from services.tstation.policies.cta_registry import cta_trace_metadata, normalize_quickreply_ctas
from services.tstation.policies.resolved_context import (
    canonical_context_from_slots,
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
_FRONT_TIRE_CHIP_LABEL = "앞바퀴사이즈"
_REAR_TIRE_CHIP_LABEL = "뒷바퀴사이즈"
_CUSTOM_TIRE_CHIP_LABEL = "다른 사이즈 입력"
_FRONT_TIRE_SELECTION_RE = re.compile(r"앞\s*바퀴|전륜|앞\s*타이어", re.IGNORECASE)
_REAR_TIRE_SELECTION_RE = re.compile(r"뒤\s*바퀴|뒷\s*바퀴|후륜|뒤\s*타이어|뒷\s*타이어", re.IGNORECASE)
_TIRE_POSITION_FOLLOWUP_ACTION_RE = re.compile(
    r"추천|찾|검색|골라|보여|알려|가격|재고|구매|예약|장착|비교",
    re.IGNORECASE,
)
_QUANTITY_LABEL_RE = re.compile(r"^\s*([1-4])\s*(?:개|본)\s*$")
_CTA_CLARIFICATION_LABEL_RE = re.compile(r"(?:다른\s*)?(?:지역|장소|날짜|일정)\s*(?:입력|찾기|검색|확인)")
_SIZE_ONLY_RE = re.compile(r"^\s*\d{3}\s*[/\s]?\s*\d{2}\s*(?:R|\s|/)?\s*\d{2}\s*$", re.IGNORECASE)
_VEHICLE_PLATE_RE = re.compile(r"\d{2,3}\s*[가-힣]\s*\d{4}")
_NON_SELF_CAR_RE = re.compile(
    r"(내\s*차|저장\s*차|등록\s*차|보유\s*차|보유한\s*차|내가\s*가진\s*차)"
    r"\s*(말고|말구|말로|아닌|아니라|아니고|빼고|이외|제외)"
    r"|다른\s*차(?:종)?",
    re.IGNORECASE,
)
_OE_REPLACEMENT_EQUIVALENT_RE = re.compile(
    r"순정|출고|처음\s*끼|살\s*때\s*끼|끼워져\s*있|똑같|동일(?:한)?\s*상품|같은\s*상품|"
    r"(?<![A-Za-z])(?:OE|RE)(?![A-Za-z])",
    re.IGNORECASE,
)
_OWNED_VEHICLE_SELECTION_CTA_RE = re.compile(
    r"^\s*(보유\s*차량\s*중\s*선택|내\s*차량\s*보기|내\s*차\s*보기|내\s*차(?:량)?로\s*찾기|"
    r"차량\s*(?:정보로\s*)?찾기|차량\s*선택해서\s*찾기)\s*$",
    re.IGNORECASE,
)
_OE_REPLACEMENT_FOLLOWUP_RE = re.compile(
    r"교체용\s*상품\s*추천|호환\s*사이즈\s*추천|동일(?:한)?\s*상품\s*찾기|같은\s*상품\s*찾기",
    re.IGNORECASE,
)
_VEHICLE_BOUND_REQUEST_RE = re.compile(
    r"내\s*차|내차|내\s*차량|내차량|차량번호|차\s*번호|"
    r"내\s*[0-9a-zA-Z가-힣]+|"
    r"\d{2,3}\s*[가-힣]\s*\d{4}",
    re.IGNORECASE,
)
_VEHICLE_LIST_REQUEST_RE = re.compile(
    r"내\s*차\s*목록|내차\s*목록|내차목록|내\s*차량|내차량|보유\s*차량|보유차량|"
    r"보유차량\s*확인|내\s*등록차|등록차량|등록차|내\s*차\s*보여|내차\s*보여|내차보여|"
    r"내\s*차\s*(?:사이즈|규격|로\s*다시)|내차\s*(?:사이즈|규격|로\s*다시)",
    re.IGNORECASE,
)
_VEHICLE_MATCH_STOPWORDS = {
    "내", "차", "차량", "번호", "차량번호", "내차", "내차량", "알지", "맞는", "타이어", "보여줘",
    "보여", "추천", "해줘", "찾아줘", "알려줘", "알려", "규격", "사이즈", "그리고", "그럼", "이건데",
}
_STORE_AVAILABILITY_CONTINUATION_RE = re.compile(
    r"장착\s*가능|오늘|내일|예약|매장|지점|재고|스케줄|시간|방문",
    re.IGNORECASE,
)
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


def normalize_vehicle_tire_size_pair(selected_meta: Mapping[str, Any]) -> tuple[str | None, str | None]:
    front_size = normalize_tire_size(str(selected_meta.get("tireSize") or selected_meta.get("tire_size") or ""))
    rear_size = normalize_tire_size(str(selected_meta.get("tireSizeRe") or selected_meta.get("tire_size_re") or ""))
    return front_size, rear_size


def normalize_vehicle_type_from_car_type(raw_car_type: Any, *, fallback_text: str | None = None) -> str | None:
    """Normalize registered car type into recommendation vehicle_type."""
    combined = " ".join(
        part
        for part in (
            str(raw_car_type or "").strip(),
            str(fallback_text or "").strip(),
        )
        if part
    )
    if not combined:
        return None

    normalized = re.sub(r"[\s_\-/]+", "", combined).lower()
    if re.search(r"전기차|electric|아이오닉|ioniq|electrified|gv70ev|\bev\b", combined, re.IGNORECASE):
        return "ev"
    if "스포츠유틸리티" in normalized or "suv" in normalized:
        return "suv"
    if any(token in normalized for token in ("승용차", "승용", "세단", "sedan", "스포츠카", "passenger")):
        return "passenger"
    if any(token in normalized for token in ("경트럭", "트럭", "truck", "밴", "van", "화물")):
        return "truck_van"
    return None


def vehicle_selection_slot_values(selected_vehicle: Mapping[str, Any] | None) -> dict[str, Any]:
    selected_car = (selected_vehicle or {}).get("car") if isinstance((selected_vehicle or {}).get("car"), Mapping) else {}
    selected_meta = (selected_vehicle or {}).get("meta") if isinstance((selected_vehicle or {}).get("meta"), Mapping) else {}
    front_size, rear_size = normalize_vehicle_tire_size_pair(selected_meta)

    slot_values: dict[str, Any] = {}
    if front_size:
        slot_values["tire_size_front"] = front_size
    if rear_size:
        slot_values["tire_size_rear"] = rear_size
    if front_size and (not rear_size or front_size == rear_size):
        slot_values["tire_size"] = front_size
    elif rear_size and not front_size:
        slot_values["tire_size"] = rear_size

    raw_car_model = (
        selected_meta.get("carModel")
        or selected_meta.get("carNm")
        or selected_car.get("model")
        or selected_car.get("name")
    )
    car_model = str(raw_car_model or "").strip()
    if car_model:
        slot_values["car_model"] = car_model
    car_no = str(selected_meta.get("carNo") or selected_car.get("licensePlate") or "").strip()
    if car_no:
        slot_values["car_no"] = car_no
    car_lnc_cd = str(selected_meta.get("carLncCd") or "").strip()
    if car_lnc_cd:
        slot_values["car_lnc_cd"] = car_lnc_cd
    raw_car_type = (
        selected_meta.get("carType")
        or selected_meta.get("car_type")
        or selected_meta.get("carTypeNm")
        or selected_meta.get("car_type_nm")
        or selected_car.get("carType")
        or selected_car.get("car_type")
        or selected_car.get("type")
        or selected_car.get("vehicleType")
    )
    car_type = str(raw_car_type or "").strip()
    vehicle_type = normalize_vehicle_type_from_car_type(
        car_type,
        fallback_text=" ".join(
            part
            for part in (
                car_model,
                str(selected_car.get("info") or selected_car.get("description") or "").strip(),
            )
            if part
        ),
    )
    if car_type:
        slot_values["car_type"] = car_type
    if vehicle_type:
        slot_values["vehicle_type"] = vehicle_type
    mbr_car_reg_seq = str(selected_meta.get("mbrCarRegSeq") or "").strip()
    if mbr_car_reg_seq:
        slot_values["mbr_car_reg_seq"] = mbr_car_reg_seq

    return slot_values


def apply_vehicle_selection_slot_values(base_slots: Any, slot_values: Mapping[str, Any]) -> Any:
    """Apply selected-vehicle slots as one atomic replacement."""
    updated = base_slots.model_copy()

    vehicle_fields = {
        "car_model",
        "car_no",
        "car_lnc_cd",
        "car_type",
        "vehicle_type",
        "mbr_car_reg_seq",
        "tire_size",
        "tire_size_front",
        "tire_size_rear",
    }
    for slot_key in vehicle_fields:
        setattr(updated, slot_key, slot_values.get(slot_key))

    if getattr(updated, "tire_size", None) != getattr(base_slots, "tire_size", None):
        updated.goods_no = None
        updated.payment_amount = None

    if (
        getattr(updated, "car_no", None) != getattr(base_slots, "car_no", None)
        or getattr(updated, "car_lnc_cd", None) != getattr(base_slots, "car_lnc_cd", None)
        or getattr(updated, "car_model", None) != getattr(base_slots, "car_model", None)
    ):
        updated.goods_no = None
        updated.payment_amount = None

    return updated


def has_staggered_vehicle_tire_sizes(front_size: str | None, rear_size: str | None) -> bool:
    return bool(front_size and rear_size and front_size != rear_size)


def is_staggered_selected_tire_size_context(slots: Any) -> bool:
    front_size = normalize_tire_size(str(getattr(slots, "tire_size_front", None) or ""))
    rear_size = normalize_tire_size(str(getattr(slots, "tire_size_rear", None) or ""))
    selected_size = normalize_tire_size(str(getattr(slots, "tire_size", None) or ""))
    return has_staggered_vehicle_tire_sizes(front_size, rear_size) and selected_size in {front_size, rear_size}


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


def build_pure_inventory_stock_cta_payload(
    *,
    quick_replies: list[dict[str, Any]],
    store_context: Mapping[str, Any] | None,
    ord_qty: int,
    tire_size: str,
    goods_no: str | None = None,
    response_shape_key: str,
    stock_check_mode: str,
    logistics_stock_available: bool | None = None,
    reservation_sale_available: bool | None = None,
    rsv_install_date: str | None = None,
    previous_stock_result: str | None = None,
    followup_mode: str | None = None,
    reservation_ui_emitted: bool | None = None,
    include_pending_stock_context: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    current_store_context = store_context_from_mapping(store_context)
    metadata: dict[str, Any] = {
        "response_shape_key": response_shape_key,
        "stock_check_mode": stock_check_mode,
    }
    if logistics_stock_available is not None:
        metadata["logisticsStockAvailable"] = logistics_stock_available
    if reservation_sale_available is not None:
        metadata["reservationSaleAvailable"] = reservation_sale_available
    if rsv_install_date is not None:
        metadata["rsvInstallDate"] = rsv_install_date
    if reservation_ui_emitted is not None:
        metadata["reservationUiEmitted"] = reservation_ui_emitted

    cta_context: dict[str, Any] = {
        "ordQty": ord_qty,
        "tireSize": tire_size,
        "intentKey": "today_install",
        "currentStoreContext": current_store_context,
    }
    if include_pending_stock_context:
        cta_context["pendingIntent"] = "stock"
        cta_context["goalType"] = "store_with_stock"
    if previous_stock_result:
        cta_context["previousStockResult"] = previous_stock_result
    if followup_mode:
        cta_context["followupMode"] = followup_mode
    if goods_no:
        cta_context["goodsNo"] = goods_no
    if logistics_stock_available is not None:
        cta_context["logisticsStockAvailable"] = logistics_stock_available
    if reservation_sale_available is not None:
        cta_context["reservationSaleAvailable"] = reservation_sale_available
    if rsv_install_date is not None:
        cta_context["rsvInstallDate"] = rsv_install_date
    if stock_check_mode:
        cta_context["stock_check_mode"] = stock_check_mode

    enriched_replies: list[dict[str, Any]] = []
    for reply in quick_replies:
        if not isinstance(reply, Mapping):
            continue
        enriched_reply = dict(reply)
        label = str(enriched_reply.get("label") or "")
        action_id = str(enriched_reply.get("actionId") or "")
        if label == "가장 빠른 예약일 확인":
            enriched_reply["actionId"] = "logistics_earliest_install_date"
            enriched_reply["intentKey"] = "today_install"
            enriched_reply["metadata"] = dict(cta_context)
        elif action_id == "search_other_store":
            enriched_reply["metadata"] = dict(cta_context)
        elif label == "예약 가능 시간 확인":
            enriched_reply["metadata"] = dict(cta_context)
        enriched_replies.append(enriched_reply)

    if current_store_context:
        metadata["currentStoreContext"] = current_store_context
    metadata["ctaContext"] = cta_context
    return enriched_replies, metadata


def build_staggered_tire_quantity_limit_event(slots: Any) -> dict[str, Any] | None:
    if not is_staggered_selected_tire_size_context(slots):
        return None

    selected_size = normalize_tire_size(str(getattr(slots, "tire_size", None) or ""))
    front_size = normalize_tire_size(str(getattr(slots, "tire_size_front", None) or ""))
    rear_size = normalize_tire_size(str(getattr(slots, "tire_size_rear", None) or ""))
    axle_label = "앞바퀴" if selected_size == front_size else "뒷바퀴" if selected_size == rear_size else "선택한"
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_staggered_tire_quantity_limit",
        "data": {
            "assistantResponse": (
                f"앞/뒤 사이즈가 다른 차량은 {axle_label} 규격 **{selected_size}** 기준으로 "
                "최대 2개까지 선택할 수 있어요.\n\n수량을 다시 선택해 주세요."
            ),
            "quickReplies": [
                {"label": "1개", "domain": "TRANSACTION"},
                {"label": "2개", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["TRANSACTION"],
        },
    }


def build_staggered_vehicle_tire_selection_event(selected_vehicle: Mapping[str, Any]) -> dict[str, Any] | None:
    selected_car = selected_vehicle.get("car") if isinstance(selected_vehicle.get("car"), Mapping) else {}
    selected_meta = selected_vehicle.get("meta") if isinstance(selected_vehicle.get("meta"), Mapping) else {}
    front_size, rear_size = normalize_vehicle_tire_size_pair(selected_meta)
    if not has_staggered_vehicle_tire_sizes(front_size, rear_size):
        return None

    car_info = str(selected_car.get("info") or selected_car.get("description") or "선택하신 차량").strip()
    car_no = str(selected_meta.get("carNo") or selected_car.get("licensePlate") or "").strip()
    vehicle_label = f"**{car_info} ({car_no})**" if car_no else f"**{car_info}**"
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "assistant_response_source": "code_vehicle_staggered_tire_prompt",
        "data": {
            "assistantResponse": (
                f"{vehicle_label}의 규격은 전륜 **{front_size}**, 후륜 **{rear_size}**예요.\n\n"
                "앞/뒤 사이즈가 다릅니다. 어떤 사이즈 기준으로 검색할까요?"
            ),
            "quickReplies": [
                {"label": _FRONT_TIRE_CHIP_LABEL, "domain": "DISCOVERY"},
                {"label": _REAR_TIRE_CHIP_LABEL, "domain": "DISCOVERY"},
                {"label": _CUSTOM_TIRE_CHIP_LABEL, "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
        },
    }


def build_manual_tire_size_input_event() -> dict[str, Any]:
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "assistant_response_source": "code_vehicle_manual_tire_size_prompt",
        "data": {
            "assistantResponse": "검색할 타이어 사이즈를 직접 입력해 주세요. 예: 225/50R18",
            "quickReplies": [
                {"label": _FRONT_TIRE_CHIP_LABEL, "domain": "DISCOVERY"},
                {"label": _REAR_TIRE_CHIP_LABEL, "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
        },
    }


def listcar_allows_staggered_tire_prompt(template_data: Mapping[str, Any] | None) -> bool:
    if not isinstance(template_data, Mapping):
        return True
    source_domain = str(template_data.get("source_domain") or "").strip().lower()
    return source_domain in {"", "discovery"}


def quickreply_labels(template_data: Mapping[str, Any] | None) -> set[str]:
    labels: set[str] = set()
    if not isinstance(template_data, Mapping):
        return labels
    data = template_data.get("data")
    if not isinstance(data, Mapping):
        return labels
    for quick_reply in data.get("quickReplies") or []:
        if isinstance(quick_reply, Mapping):
            label = str(quick_reply.get("label") or "").strip()
            if label:
                labels.add(label)
    return labels


def is_manual_tire_size_input_selection(user_text: str | None, latest_quickreply_tmpl: Mapping[str, Any] | None) -> bool:
    return (
        str(user_text or "").strip() == _CUSTOM_TIRE_CHIP_LABEL
        and _CUSTOM_TIRE_CHIP_LABEL in quickreply_labels(latest_quickreply_tmpl)
    )


def resolve_vehicle_tire_position_selection(
    user_text: str | None,
    slots: Any,
    latest_quickreply_tmpl: Mapping[str, Any] | None = None,
) -> str | None:
    text = str(user_text or "").strip()
    if not text or normalize_tire_size(text):
        return None

    front_size = normalize_tire_size(str(getattr(slots, "tire_size_front", None) or ""))
    rear_size = normalize_tire_size(str(getattr(slots, "tire_size_rear", None) or ""))
    if not has_staggered_vehicle_tire_sizes(front_size, rear_size):
        return None

    latest_labels = quickreply_labels(latest_quickreply_tmpl)
    if text == _FRONT_TIRE_CHIP_LABEL and _FRONT_TIRE_CHIP_LABEL in latest_labels:
        return front_size
    if text == _REAR_TIRE_CHIP_LABEL and _REAR_TIRE_CHIP_LABEL in latest_labels:
        return rear_size
    if text == _CUSTOM_TIRE_CHIP_LABEL and _CUSTOM_TIRE_CHIP_LABEL in latest_labels:
        return None
    if (
        _FRONT_TIRE_SELECTION_RE.search(text)
        and not _REAR_TIRE_SELECTION_RE.search(text)
        and _TIRE_POSITION_FOLLOWUP_ACTION_RE.search(text)
    ):
        return _FRONT_TIRE_SELECTION_RE.sub(front_size, text, count=1)
    if _REAR_TIRE_SELECTION_RE.search(text) and _TIRE_POSITION_FOLLOWUP_ACTION_RE.search(text):
        return _REAR_TIRE_SELECTION_RE.sub(rear_size, text, count=1)
    return None


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


def confirmed_product_slot_values_from_event(event: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(event, Mapping):
        return None
    template = event.get("template")
    if template not in {"product", "quickReply"}:
        return None
    event_data = event.get("data")
    if not isinstance(event_data, Mapping):
        return None

    if template == "quickReply":
        metadata = event_data.get("metadata")
        if not isinstance(metadata, Mapping):
            return None
        canonical_values = canonical_context_from_template_boundary(metadata)
        goods_no = str(canonical_values.get("goods_no") or "").strip()
        if not goods_no:
            return None
        tire_size = normalize_tire_size(str(canonical_values.get("tire_size") or ""))
        tire_model = str(canonical_values.get("product_name") or "").strip()
        slot_values: dict[str, Any] = {"goods_no": goods_no}
        if tire_size:
            slot_values["tire_size"] = tire_size
        if tire_model:
            slot_values["tire_model"] = tire_model
        raw_qty = canonical_values.get("ord_qty")
        if raw_qty is not None:
            try:
                qty = int(raw_qty)
                if qty > 0:
                    slot_values["ord_qty"] = qty
            except (TypeError, ValueError):
                pass
        return slot_values

    products = event_data.get("products")
    metadata = event_data.get("metadata")
    if not (
        isinstance(products, list)
        and len(products) == 1
        and isinstance(metadata, list)
        and len(metadata) == 1
    ):
        return None
    product = products[0]
    meta = metadata[0]
    if not isinstance(product, Mapping) or not isinstance(meta, Mapping):
        return None

    canonical_values = canonical_context_from_template_boundary({**product, **meta})
    goods_no = str(canonical_values.get("goods_no") or "").strip()
    if not goods_no:
        return None

    tire_size = normalize_tire_size(str(canonical_values.get("tire_size") or product.get("size") or ""))
    tire_model = str(canonical_values.get("product_name") or "").strip()
    slot_values: dict[str, Any] = {"goods_no": goods_no}
    if tire_size:
        slot_values["tire_size"] = tire_size
    if tire_model:
        slot_values["tire_model"] = tire_model
    return slot_values


def confirmed_product_slot_values_for_purchase_cta(
    *,
    latest_quickreply_tmpl: Mapping[str, Any] | None = None,
    latest_product_tmpl: Mapping[str, Any] | None = None,
    prev_tool_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    for template, data in (
        ("quickReply", latest_quickreply_tmpl),
        ("product", latest_product_tmpl),
    ):
        slots = confirmed_product_slot_values_from_event({
            "template": template,
            "data": data,
        })
        if slots:
            return slots

    for entry in reversed(prev_tool_data or []):
        if not isinstance(entry, Mapping):
            continue
        tool = str(entry.get("tool") or "")
        tool_input = entry.get("input") if isinstance(entry.get("input"), Mapping) else entry.get("args")
        tool_input = tool_input if isinstance(tool_input, Mapping) else {}

        if tool == "get_final_price_tool":
            goods_no = str(tool_input.get("goods_no") or "").strip()
            if goods_no:
                slot_values: dict[str, Any] = {"goods_no": goods_no}
                tire_size = normalize_tire_size(str(tool_input.get("tire_size") or tool_input.get("size") or ""))
                if tire_size:
                    slot_values["tire_size"] = tire_size
                product_name = str(tool_input.get("product_name") or tool_input.get("goods_nm") or "").strip()
                if product_name:
                    slot_values["tire_model"] = product_name
                return slot_values

        if tool == "get_product_description_tool":
            slot_values: dict[str, Any] = {}
            goods_no = str(tool_input.get("goods_no") or "").strip()
            data = entry.get("data")
            payload = data.get("data") if isinstance(data, Mapping) and isinstance(data.get("data"), Mapping) else data
            payload = payload if isinstance(payload, Mapping) else {}
            canonical_payload = canonical_context_from_tool_boundary(payload)
            if not goods_no:
                goods_no = str(canonical_payload.get("goods_no") or "").strip()
            if goods_no:
                slot_values["goods_no"] = goods_no
            tire_size = normalize_tire_size(
                str(tool_input.get("tire_size") or tool_input.get("size") or canonical_payload.get("tire_size") or "")
            )
            if tire_size:
                slot_values["tire_size"] = tire_size
            product_name = str(canonical_payload.get("product_name") or "").strip()
            if product_name:
                slot_values["tire_model"] = product_name
            if slot_values.get("goods_no"):
                return slot_values

    return None


def _cal_day_from_korean_date_text(value: str | None) -> str | None:
    text = str(value or "")
    match = re.search(r"(?P<year>20\d{2})년\s*(?P<month>\d{1,2})월\s*(?P<day>\d{1,2})일", text)
    if not match:
        return None
    return f"{int(match.group('year')):04d}{int(match.group('month')):02d}{int(match.group('day')):02d}"


def _reservation_hour_from_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    hour_match = re.search(r"(?<!\d)([01]?\d|2[0-3])\s*(?::\s*00|시)(?:\s*예약)?", text)
    if not hour_match:
        return None
    return f"{int(hour_match.group(1)):02d}"


def preorder_slot_values_from_data(template_data: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(template_data, Mapping):
        return None
    if template_data.get("template") == "preOrder" and isinstance(template_data.get("data"), Mapping):
        template_data = template_data["data"]
    if not template_data.get("isReadyToOrder"):
        return None

    metadata = template_data.get("metadata")
    order_info = template_data.get("orderInfo")
    if not isinstance(metadata, Mapping) or not isinstance(order_info, Mapping):
        return None

    slot_values: dict[str, Any] = {}
    canonical_values = canonical_context_from_template_boundary(template_data)
    goods_no = str(canonical_values.get("goods_no") or "").strip()
    if goods_no:
        slot_values["goods_no"] = goods_no

    shop_id = str(canonical_values.get("shop_id") or "").strip()
    if shop_id:
        slot_values["shop_id"] = shop_id

    store_name = str(canonical_values.get("shop_name") or "").strip()
    if store_name:
        slot_values["shop_name"] = store_name

    raw_qty = canonical_values.get("ord_qty")
    if raw_qty is not None:
        try:
            qty = int(raw_qty)
            if qty > 0:
                slot_values["ord_qty"] = qty
        except (TypeError, ValueError):
            pass

    raw_amount = order_info.get("paymentAmount") or metadata.get("paymentAmount") or metadata.get("payment_amount")
    if raw_amount is not None:
        try:
            amount = int(raw_amount)
            if amount > 0:
                slot_values["payment_amount"] = amount
        except (TypeError, ValueError):
            pass

    product_text = str(order_info.get("product") or "").strip()
    product_name = str(canonical_values.get("product_name") or "").strip() or product_text
    if product_name:
        slot_values["tire_model"] = re.sub(
            r"\s*\d{3}\s*/?\s*\d{2}\s*R?\s*\d{2}\s*$",
            "",
            product_name,
            flags=re.IGNORECASE,
        ).strip() or product_name
    tire_size = normalize_tire_size(canonical_values.get("tire_size") or product_text)
    if tire_size:
        slot_values["tire_size"] = tire_size

    booking_datetime = str(order_info.get("bookingDateTime") or metadata.get("bookingDateTime") or "").strip()
    requested_cal_day = _cal_day_from_korean_date_text(booking_datetime)
    requested_cal_day = requested_cal_day or str(canonical_values.get("requested_cal_day") or "").strip()
    if requested_cal_day:
        slot_values["requested_cal_day"] = requested_cal_day
    rsv_hour = _reservation_hour_from_text(booking_datetime)
    rsv_hour = rsv_hour or str(canonical_values.get("rsv_hour") or "").strip()
    if rsv_hour:
        slot_values["rsv_hour"] = rsv_hour

    return slot_values or None


def _datepick_requested_cal_day_from_text(
    user_text: str,
    datepick_data: Mapping[str, Any],
    *,
    allow_selected_fallback: bool = False,
) -> str | None:
    direct = _cal_day_from_korean_date_text(user_text)
    if direct:
        return direct

    dates = datepick_data.get("dates")
    if not isinstance(dates, list) or not dates:
        return None
    for date_item in dates:
        if not isinstance(date_item, Mapping):
            continue
        label = str(date_item.get("date") or "")
        cal_day = _cal_day_from_korean_date_text(label)
        if cal_day and label and label in user_text:
            return cal_day

    if not allow_selected_fallback:
        return None
    selected_idx = datepick_data.get("selectedDate")
    if isinstance(selected_idx, int) and 0 <= selected_idx < len(dates):
        selected = dates[selected_idx]
        if isinstance(selected, Mapping):
            return _cal_day_from_korean_date_text(str(selected.get("date") or ""))
    return None


def datepick_slot_values_from_data(
    template_data: Mapping[str, Any] | None,
    *,
    user_text: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(template_data, Mapping):
        return None
    if template_data.get("template") == "datepick" and isinstance(template_data.get("data"), Mapping):
        template_data = template_data["data"]

    metadata = template_data.get("metadata")
    if not isinstance(metadata, Mapping):
        return None

    slot_values: dict[str, Any] = {}
    canonical_values = canonical_context_from_template_boundary(metadata)
    shop_id = str(canonical_values.get("shop_id") or "").strip()
    if shop_id:
        slot_values["shop_id"] = shop_id
    shop_name = str(canonical_values.get("shop_name") or "").strip()
    if shop_name:
        slot_values["shop_name"] = shop_name
    goods_no = str(canonical_values.get("goods_no") or "").strip()
    if goods_no:
        slot_values["goods_no"] = goods_no
    product_name = str(canonical_values.get("product_name") or "").strip()
    if product_name:
        slot_values["tire_model"] = product_name
    tire_size = normalize_tire_size(canonical_values.get("tire_size") or "")
    if tire_size:
        slot_values["tire_size"] = tire_size
    raw_qty = canonical_values.get("ord_qty")
    if raw_qty is not None:
        try:
            qty = int(raw_qty)
            if qty > 0:
                slot_values["ord_qty"] = qty
        except (TypeError, ValueError):
            pass
    raw_amount = metadata.get("paymentAmount") or metadata.get("payment_amount")
    if raw_amount is not None:
        try:
            amount = int(raw_amount)
            if amount > 0:
                slot_values["payment_amount"] = amount
        except (TypeError, ValueError):
            pass

    text = str(user_text or "").strip()
    rsv_hour = _reservation_hour_from_text(text)
    rsv_hour = rsv_hour or str(canonical_values.get("rsv_hour") or "").strip()
    if rsv_hour:
        slot_values["rsv_hour"] = rsv_hour

    requested_cal_day = _datepick_requested_cal_day_from_text(
        text,
        template_data,
        allow_selected_fallback=bool(text),
    )
    requested_cal_day = requested_cal_day or str(canonical_values.get("requested_cal_day") or "").strip()
    if requested_cal_day:
        slot_values["requested_cal_day"] = requested_cal_day

    return slot_values or None


def selected_order_context_from_preview_values(preview_values: Mapping[str, Any]) -> dict[str, Any]:
    if not preview_values.get("goods_no"):
        return {}
    context: dict[str, Any] = {}
    for key_name in ("goods_no", "tire_size", "ord_qty", "region", "shop_id", "shop_name"):
        value = preview_values.get(key_name)
        if value not in (None, "", [], {}):
            context[key_name] = value
    for key_name in ("schedule_mode", "stock_check_mode"):
        value = preview_values.get(key_name)
        if value not in (None, "", [], {}):
            context[key_name] = value
    context["pending_intent"] = "order"
    context["goal_type"] = "place_order"
    context["source"] = "preview_location_template_selection"
    return context


def apply_selected_order_context_for_purchase_cta(slots: Any) -> tuple[Any, dict[str, Any]]:
    context_root = slots.order_context if isinstance(getattr(slots, "order_context", None), dict) else {}
    selected_context = context_root.get("selected_order_context")
    if not isinstance(selected_context, dict):
        return slots, {}
    values = {
        key: value
        for key, value in selected_context.items()
        if key
        in {
            "goods_no",
            "tire_size",
            "ord_qty",
            "region",
            "shop_id",
            "shop_name",
            "pending_intent",
            "goal_type",
            "requested_cal_day",
            "rsv_hour",
        }
        and value not in (None, "", [], {})
    }
    if not values.get("goods_no"):
        return slots, {}
    values["pending_intent"] = "order"
    values["goal_type"] = "place_order"
    updated = slots.apply_runtime_values(values, source="selected_order_context", fill_only=False)
    return updated, values


def resolve_recent_product_search_keyword(prev_tool_data: list[dict[str, Any]]) -> str | None:
    if not prev_tool_data:
        return None
    for entry in prev_tool_data:
        if entry.get("tool") != "search_product_tool":
            continue
        tool_input = entry.get("input")
        if not isinstance(tool_input, Mapping):
            continue
        keyword = str(tool_input.get("keyword") or "").strip()
        if keyword:
            return keyword
    return None


def resolve_goods_no_from_recent_product_context(
    prev_tool_data: list[dict[str, Any]],
    tire_size: str | None,
) -> str | None:
    target_size = normalize_tire_size(tire_size)
    if not target_size or not prev_tool_data:
        return None

    items: list[dict[str, Any]] = []
    product_list_tools = {"search_product_tool", "get_products_recommendations_tool"}
    for entry in prev_tool_data:
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

    same_size = [
        item
        for item in items
        if normalize_tire_size(canonical_context_from_tool_boundary(item).get("tire_size")) == target_size
    ]
    if len(same_size) != 1:
        return None
    goods_no = canonical_context_from_tool_boundary(same_size[0]).get("goods_no")
    return str(goods_no).strip() if goods_no else None


def oe_replacement_cta_context() -> dict[str, str]:
    return {
        "intentKey": "oe_replacement",
        "source_intent": "oe_replacement_guidance",
        "expected_contract_intent": "oe_re_product_filter_summary",
    }


def is_oe_replacement_cta_context(value: Mapping[str, Any] | None) -> bool:
    if not isinstance(value, Mapping):
        return False
    source_intent = str(value.get("source_intent") or "").strip()
    expected_contract_intent = str(value.get("expected_contract_intent") or "").strip()
    return source_intent == "oe_replacement_guidance" or expected_contract_intent in {
        "oe_re_product_filter_summary",
        "oe_re_concept_explanation",
    }


def build_oe_replacement_guidance_event(
    selected_vehicle: Mapping[str, Any] | None,
    user_text: str,
    *,
    include_vehicle_selection: bool = False,
) -> dict[str, Any]:
    selected_car = (selected_vehicle or {}).get("car") if isinstance((selected_vehicle or {}).get("car"), Mapping) else {}
    selected_meta = (selected_vehicle or {}).get("meta") if isinstance((selected_vehicle or {}).get("meta"), Mapping) else {}
    car_info = str(selected_car.get("info") or selected_car.get("description") or "").strip()
    car_no = str(selected_meta.get("carNo") or selected_car.get("licensePlate") or "").strip()
    front_size = str(selected_meta.get("tireSize") or "").strip()
    rear_size = str(selected_meta.get("tireSizeRe") or "").strip()

    lines = [
        "OE는 차량 출고 시 장착된 순정 타이어이고, RE는 교체용으로 판매되는 타이어예요.",
        "출고 타이어와 완전히 같은 상품은 차종, 연식, 트림, 당시 출고 브랜드에 따라 달라서 차량 정보만으로는 바로 확정하기 어려워요.",
    ]
    if car_info:
        vehicle_label = f"{car_info} ({car_no})" if car_no else car_info
        lines.append(f"\n{vehicle_label} 기준으로 확인을 이어가려면 현재 장착된 타이어의 브랜드와 사이즈를 함께 봐야 해요.")
        if front_size and rear_size and front_size != rear_size:
            lines.append(f"현재 등록 정보의 규격은 전륜 {front_size}, 후륜 {rear_size}로 확인돼요.")
        elif front_size or rear_size:
            lines.append(f"현재 등록 정보의 규격은 {front_size or rear_size}로 확인돼요.")
    else:
        lines.append("\n차량을 선택해 주시면 등록된 규격 기준으로 동일 상품 또는 가까운 교체용 상품을 찾아드릴게요.")

    if re.search(r"미쉐린|michelin", user_text or "", re.IGNORECASE):
        lines.append("미쉐린으로 기억하고 계시면, 해당 브랜드 상품부터 확인하고 없으면 호환되는 교체용 상품을 함께 안내할게요.")
    else:
        lines.append("동일 OE 상품 확인이 어려운 경우에는 같은 규격의 주력 교체용 상품을 대안으로 안내드릴게요.")

    cta_context = oe_replacement_cta_context()
    quick_replies = [
        {"label": "차량 선택해서 찾기", "domain": "DISCOVERY", "intentKey": "oe_replacement", "metadata": cta_context},
        {"label": "사이즈 직접 입력", "domain": "DISCOVERY", "intentKey": "oe_replacement", "metadata": cta_context},
        {"label": "교체용 상품 추천", "domain": "DISCOVERY", "intentKey": "oe_replacement", "metadata": cta_context},
    ]
    if selected_vehicle is not None:
        quick_replies = [
            {"label": "동일 상품 찾기", "domain": "DISCOVERY", "intentKey": "oe_replacement", "metadata": cta_context},
            {"label": "교체용 상품 추천", "domain": "DISCOVERY", "intentKey": "oe_replacement", "metadata": cta_context},
            {"label": "사이즈 직접 입력", "domain": "DISCOVERY", "intentKey": "oe_replacement", "metadata": cta_context},
        ]
    elif include_vehicle_selection:
        quick_replies = [
            {"label": "보유차량 중 선택", "domain": "DISCOVERY", "intentKey": "oe_replacement", "metadata": cta_context},
            {"label": "차번+이름으로 검색", "domain": "DISCOVERY", "intentKey": "oe_replacement", "metadata": cta_context},
            {"label": "사이즈 직접 입력", "domain": "DISCOVERY", "intentKey": "oe_replacement", "metadata": cta_context},
        ]

    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "assistant_response_source": "code_oe_replacement_guidance",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": quick_replies,
            "predictedDomains": ["DISCOVERY"],
            "metadata": {"ctaContext": cta_context, "response_shape_key": "oe_re_concept_explanation"},
        },
    }


def build_oe_replacement_same_product_brand_prompt_event(
    tire_size: str | None,
) -> dict[str, Any]:
    size_text = f"{tire_size} 기준으로 " if tire_size else ""
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "assistant_response_source": "code_oe_replacement_same_product_brand_prompt",
        "data": {
            "assistantResponse": (
                f"{size_text}동일 상품은 기존 장착 브랜드를 알아야 더 정확하게 찾을 수 있어요.\n\n"
                "브랜드를 알려주시면 그 기준으로 동일 상품을 찾아드릴게요. "
                "브랜드가 기억나지 않으시면 한국타이어 교체용 상품으로 바로 추천해 드릴 수 있어요."
            ),
            "quickReplies": [
                {"label": "미쉐린으로 동일 상품 찾기", "domain": "DISCOVERY"},
                {"label": "한국타이어 교체용 추천", "domain": "DISCOVERY"},
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
        },
    }


def extract_vehicle_plate_from_text(user_text: str | None) -> str | None:
    match = _VEHICLE_PLATE_RE.search(user_text or "")
    if not match:
        return None
    return re.sub(r"[^0-9가-힣]", "", match.group(0))


def is_oe_replacement_equivalent_query(user_text: str | None) -> bool:
    return bool(_OE_REPLACEMENT_EQUIVALENT_RE.search(user_text or ""))


def is_owned_vehicle_selection_cta(user_text: str | None) -> bool:
    return bool(_OWNED_VEHICLE_SELECTION_CTA_RE.match(user_text or ""))


def is_oe_replacement_followup_query(user_text: str | None) -> bool:
    return bool(_OE_REPLACEMENT_FOLLOWUP_RE.search(user_text or ""))


def is_oe_replacement_context(
    context_text: str | None,
    current_text: str | None,
    latest_quickreply_tmpl: Mapping[str, Any] | None = None,
) -> bool:
    if is_oe_replacement_equivalent_query(current_text):
        return True
    if is_owned_vehicle_selection_cta(current_text):
        return False
    if not is_oe_replacement_equivalent_query(context_text):
        return False
    cta_context = quickreply_cta_context_from_template(latest_quickreply_tmpl)
    if not is_oe_replacement_cta_context(cta_context):
        return False
    return is_oe_replacement_followup_query(current_text) or bool(extract_vehicle_plate_from_text(current_text))


def recommendation_type_for_vehicle_auto_continue(user_text: str) -> str:
    text = user_text or ""
    if re.search(r"연비|회전\s*저항|rr\b", text, re.IGNORECASE):
        return "fuel_efficiency"
    if re.search(r"세일|할인|할인율", text, re.IGNORECASE):
        return "discount"
    if re.search(r"가성비|저렴|싼|최저", text, re.IGNORECASE):
        return "value"
    if re.search(r"가족|패밀리|승차감|컴포트", text, re.IGNORECASE):
        return "family"
    if re.search(r"전기차|EV|ev|아이온|iON", text, re.IGNORECASE):
        return "ev"
    if re.search(r"겨울|윈터|눈길", text, re.IGNORECASE):
        return "snow"
    if re.search(r"여름|썸머", text, re.IGNORECASE):
        return "summer"
    if re.search(r"사계절|올시즌|all[-\s]?season|올웨더|전천후|all[-\s]?weather", text, re.IGNORECASE):
        return "all_weather"
    if re.search(r"빗길|젖은", text, re.IGNORECASE):
        return "wet"
    if re.search(r"정숙|조용|소음|진동", text, re.IGNORECASE):
        return "low_vibration"
    if re.search(r"퍼포먼스|스포츠|성능", text, re.IGNORECASE):
        return "performance"
    return "tstation"


def should_reuse_vehicle_slots_for_oe_followup(
    recent_context_text: str | None,
    current_text: str | None,
    tire_size: str | None,
    latest_quickreply_tmpl: Mapping[str, Any] | None = None,
) -> bool:
    text = current_text or ""
    if not tire_size:
        return False
    if not is_oe_replacement_context(recent_context_text, current_text, latest_quickreply_tmpl):
        return False
    if not is_oe_replacement_followup_query(text):
        return False
    if _NON_SELF_CAR_RE.search(text):
        return False
    if _VEHICLE_BOUND_REQUEST_RE.search(text) or _VEHICLE_LIST_REQUEST_RE.search(text):
        return False
    return True


def build_oe_replacement_followup_recommendation_args(
    current_text: str,
    recent_context_text: str,
    tire_size: str | None,
    latest_quickreply_tmpl: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not should_reuse_vehicle_slots_for_oe_followup(
        recent_context_text,
        current_text,
        tire_size,
        latest_quickreply_tmpl,
    ):
        return None
    return {
        "rcmd_type": recommendation_type_for_vehicle_auto_continue(current_text),
        "limit": 3,
        "tire_size": str(tire_size),
        "brand_cd": "HK",
    }


def oe_replacement_followup_brand_cd(current_text: str, recent_context_text: str) -> str | None:
    current_frame = build_discovery_intent_frame(current_text)
    current_brand_cd = str(current_frame.entities.get("brand_cd") or "").strip()
    if current_brand_cd:
        return current_brand_cd

    context_frame = build_discovery_intent_frame(recent_context_text)
    context_brand_cd = str(context_frame.entities.get("brand_cd") or "").strip()
    if context_brand_cd:
        return context_brand_cd

    return None


def build_oe_replacement_same_product_search_args(
    current_text: str,
    recent_context_text: str,
    tire_size: str | None,
    latest_quickreply_tmpl: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not should_reuse_vehicle_slots_for_oe_followup(
        recent_context_text,
        current_text,
        tire_size,
        latest_quickreply_tmpl,
    ):
        return None
    if not re.search(r"동일(?:한)?\s*상품|같은\s*상품", current_text, re.IGNORECASE):
        return None
    brand_cd = oe_replacement_followup_brand_cd(current_text, recent_context_text)
    if not brand_cd:
        return None
    return {
        "size": str(tire_size),
        "brand_cd": brand_cd,
        "limit": 10,
    }


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


def is_size_only_store_availability_continuation(
    user_text: str,
    *,
    build_size_only_product_search_tool_input: Callable[..., dict[str, Any] | None],
    prev_tool_data: list[dict] | None = None,
    recent_context: str = "",
    messages: list[dict] | None = None,
    slots: Any | None = None,
) -> bool:
    if not _SIZE_ONLY_RE.match(str(user_text or "")):
        return False
    if not build_size_only_product_search_tool_input(
        user_text,
        prev_tool_data=prev_tool_data,
        recent_context=recent_context,
        slots=slots,
    ):
        return False
    context_parts = [recent_context]
    for message in reversed((messages or [])[-8:]):
        content = str(message.get("content") or "")
        template_data = message.get("template_data")
        if isinstance(template_data, dict):
            content += " " + json.dumps(template_data, ensure_ascii=False)
        context_parts.append(content)
    context_blob = "\n".join(part for part in context_parts if part)
    return bool(_STORE_AVAILABILITY_CONTINUATION_RE.search(context_blob))


def is_resolved_size_store_availability_transaction_continuation(
    user_text: str,
    *,
    slots: Any | None,
    routing_result: Any | None = None,
    size_only_store_availability_continuation: bool = False,
) -> bool:
    if not size_only_store_availability_continuation:
        return False
    if not _SIZE_ONLY_RE.match(str(user_text or "")):
        return False

    canonical_slots = canonical_context_from_slots(slots)
    if not (canonical_slots.get("goods_no") and canonical_slots.get("tire_size")):
        return False
    pending_intent = str(canonical_slots.get("pending_intent") or "").strip()
    goal_type = str(canonical_slots.get("goal_type") or "").strip()
    if pending_intent != "stock" and goal_type != "store_with_stock":
        return False
    has_scope = bool(
        canonical_slots.get("region")
        or canonical_slots.get("shop_id")
        or canonical_slots.get("shop_name")
        or canonical_slots.get("store_name")
    )
    availability_context = canonical_slots.get("availability_context")
    if isinstance(availability_context, Mapping):
        pending_context = availability_context.get("pending_order_context")
        if isinstance(pending_context, Mapping):
            has_scope = has_scope or bool(
                pending_context.get("region") or pending_context.get("shop_id") or pending_context.get("shop_name")
            )
    if not has_scope:
        return False
    routing_topic = str(getattr(routing_result, "pending_check_topic", "") or "").strip()
    followup_intent = str(getattr(routing_result, "discovery_followup_intent", "") or "").strip()
    execution_plan = " ".join(str(item) for item in (getattr(routing_result, "execution_plan", []) or []))
    return bool(
        routing_topic in {"store_inventory", "today_install", "none", ""}
        or followup_intent == "recent_product_set_size_availability"
        or re.search(r"stock|inventory|재고|장착|store", execution_plan, re.IGNORECASE)
    )


def is_quantity_only_stock_followup_text(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    parsed = ConversationSlots.extract_from_user_text(normalized)
    return bool(
        parsed.ord_qty is not None
        and normalize_tire_size(normalized) is None
        and parsed.shop_name is None
        and parsed.region is None
        and not ConversationSlots.has_product_keyword(normalized)
        and not re.search(r"예약|장착|오늘\s*서비스|오늘서비스|당일|방문|가능\s*시간|스케줄", normalized, re.IGNORECASE)
    )


def is_pure_inventory_stock_ready(slots: Any | None) -> bool:
    canonical_slots = canonical_context_from_slots(slots)
    if slots is None and not canonical_slots:
        return False
    slot_values = slots.model_dump() if hasattr(slots, "model_dump") else dict(slots or {})

    def _slot_value(name: str) -> Any:
        if isinstance(slots, Mapping):
            return slots.get(name, canonical_slots.get(name))
        if slots is not None and hasattr(slots, name):
            return getattr(slots, name, canonical_slots.get(name))
        return slot_values.get(name, canonical_slots.get(name))

    try:
        qty = int(_slot_value("ord_qty") or _slot_value("quantity") or 0)
    except (TypeError, ValueError):
        qty = 0
    return bool(
        (_slot_value("pending_intent") == "stock" or _slot_value("goal_type") == "store_with_stock")
        and _slot_value("goods_no")
        and _slot_value("tire_size")
        and qty > 0
        and (_slot_value("shop_id") or _slot_value("shop_name") or _slot_value("store_name"))
    )


def build_pure_inventory_stock_contract(
    user_text: str,
    slots: Any,
    *,
    action_mode: str = "stock_check",
    context_state: str = "resumed",
    resume_source: str = "pure_inventory_stock_fast_path",
) -> Any | None:
    canonical_slots = canonical_context_from_slots(slots)
    slot_values = slots.model_dump() if hasattr(slots, "model_dump") else dict(slots or {})

    def _slot_value(name: str) -> Any:
        if isinstance(slots, Mapping):
            return slots.get(name, canonical_slots.get(name))
        if slots is not None and hasattr(slots, name):
            return getattr(slots, name, canonical_slots.get(name))
        return slot_values.get(name, canonical_slots.get(name))

    if str(_slot_value("stock_check_mode") or "") != "inventory_only":
        return None
    known_slots = {
        "goods_no": _slot_value("goods_no"),
        "tire_size": _slot_value("tire_size"),
        "quantity": _slot_value("ord_qty") or _slot_value("quantity"),
        "ord_qty": _slot_value("ord_qty") or _slot_value("quantity"),
        "shop_id": _slot_value("shop_id"),
        "shop_name": _slot_value("shop_name"),
        "store_name": _slot_value("shop_name") or _slot_value("store_name"),
        "pending_intent": _slot_value("pending_intent"),
        "goal_type": _slot_value("goal_type"),
        "stock_check_mode": "inventory_only",
    }
    filtered_known_slots = {k: v for k, v in known_slots.items() if v not in (None, "")}
    frame = build_transaction_intent_frame(user_text, known_slots=filtered_known_slots)
    if (
        (frame.intent != "stock_store_search" or frame.sub_intent != "stock")
        or str(frame.known_slots.get("stock_check_mode") or "") != "inventory_only"
    ):
        if not is_quantity_only_stock_followup_text(user_text):
            return None
        frame = IntentFrame(
            domain=PolicyDomain.TRANSACTION,
            intent="stock_store_search",
            sub_intent="stock",
            known_slots={
                **filtered_known_slots,
                "quantity": filtered_known_slots.get("quantity") or filtered_known_slots.get("ord_qty"),
                "ord_qty": filtered_known_slots.get("ord_qty") or filtered_known_slots.get("quantity"),
                "stock_check_mode": "inventory_only",
            },
            missing_slots=(),
            entities={"stock_check_mode": "inventory_only"},
        )
    if (
        frame.intent != "stock_store_search"
        or frame.sub_intent != "stock"
        or str(frame.known_slots.get("stock_check_mode") or "") != "inventory_only"
    ):
        return None
    tool_plan = plan_transaction_tools(frame)
    response_decision = decide_transaction_response(
        intent=frame.intent,
        user_text="재고 있어?" if is_quantity_only_stock_followup_text(user_text) else user_text,
        known_slots=dict(frame.known_slots),
    )
    return build_turn_contract(
        user_text=user_text,
        intent_frame=frame,
        tool_plan=tool_plan,
        response_decision=response_decision,
        merged_slots=slots,
        action_mode=action_mode,
        context_state=context_state,
        resume_source=resume_source,
    )


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
