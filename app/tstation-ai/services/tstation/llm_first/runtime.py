from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from fastapi.responses import StreamingResponse
from langchain_litellm import ChatLiteLLM

from config.env import settings
from config.tracing import set_trace_name
from schemas.tstation.chat import TStationChatRequest, TStationChatResponse
from services.tstation.llm_first.adapters import legacy
from services.tstation.llm_first.composer import Composer
from services.tstation.llm_first.executor import AFExecutor
from services.tstation.llm_first.models import AgentFlow, PlannerDecision, SelectedAF
from services.tstation.llm_first.planner import LeadingAgentPlanner
from services.tstation.llm_first.qc import verify_response
from services.tstation.llm_first.schedule_validation import build_past_schedule_selection_event
from services.tstation.llm_first.persistence.state import LLMFirstStateStore, apply_state_rules

logger = logging.getLogger(__name__)

_QUESTION_TEXT_RE = re.compile(
    r"\?|뭐|무엇|어떤|어떻게|왜|언제|얼마|알려|설명|궁금|되나|돼|가능|차이|비교|"
    r"할인|쿠폰|혜택|이벤트|프로모션|FAQ|faq",
    re.IGNORECASE,
)
_PURCHASE_CONTINUATION_TEXT_RE = re.compile(
    r"선택|예약|주문|구매|담아|장바구니|결제|장착|스케줄|일정|"
    r"\d+\s*개|(?:\d{1,2}\s*월\s*)?\d{1,2}\s*일|\d{1,2}\s*시|^\s*\d{1,2}\s*:\s*\d{2}",
    re.IGNORECASE,
)


def _make_llm(model_setting: str, *, streaming: bool = False, timeout: int = 60) -> ChatLiteLLM:
    return ChatLiteLLM(
        api_base=settings.AI_GATEWAY_BASE_URL,
        api_key=settings.AI_GATEWAY_API_KEY,
        model=f"{settings.AI_DEFAULT_PROVIDER}/{model_setting}",
        streaming=streaming,
        request_timeout=timeout,
    )


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def _text_response_event(text: str) -> dict[str, Any]:
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": text,
            "quickReplies": [],
            "predictedDomains": [],
            "metadata": {"source": "llm_first_text_response"},
        },
    }


def _last_user_text(request: TStationChatRequest) -> str:
    for message in reversed(request.messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _request_location_coords(request: TStationChatRequest) -> tuple[float | None, float | None]:
    sources: list[dict[str, Any]] = []
    for source in (request.user_info, request.metadata, request.slots):
        if isinstance(source, dict):
            sources.append(source)
            location = source.get("location")
            if isinstance(location, dict):
                sources.append(location)
    for source in sources:
        xpos = _to_float(source.get("xpos") or source.get("user_xpos") or source.get("longitude") or source.get("lng"))
        ypos = _to_float(source.get("ypos") or source.get("user_ypos") or source.get("latitude") or source.get("lat"))
        if xpos is not None and ypos is not None:
            return xpos, ypos
    return None, None


def _request_slot_patch(request: TStationChatRequest) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for source in (request.slots, request.ui_action, request.chip_context):
        if isinstance(source, dict):
            patch.update(source)
            nested_slots = source.get("slots")
            if isinstance(nested_slots, dict):
                patch.update(nested_slots)
            metadata = source.get("metadata")
            if isinstance(metadata, dict):
                patch.update(metadata)
    return patch


def _ui_action_values(request: TStationChatRequest, patch: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for source in (request.ui_action, request.chip_context, request.metadata, patch):
        if not isinstance(source, dict):
            continue
        values.update(source)
        ui_action = source.get("ui_action")
        if isinstance(ui_action, dict):
            values.update(ui_action)
            slots = ui_action.get("slots")
            if isinstance(slots, dict):
                values.update(slots)
        slots = source.get("slots")
        if isinstance(slots, dict):
            values.update(slots)
        metadata = source.get("metadata")
        if isinstance(metadata, dict):
            values.update(metadata)
    return values


def _looks_like_side_question(user_text: str) -> bool:
    text = str(user_text or "").strip()
    if not text:
        return False
    return bool(_QUESTION_TEXT_RE.search(text))


def _allows_deterministic_purchase_resume(user_text: str, values: dict[str, Any], *, text_selection_resolved: bool = False) -> bool:
    text = str(user_text or "").strip()
    if text_selection_resolved:
        return True
    if not text:
        return True
    if _looks_like_side_question(text) and not _PURCHASE_CONTINUATION_TEXT_RE.search(text):
        return False
    action_type = str(values.get("action_type") or values.get("cta_action") or values.get("ctaAction") or values.get("actionId") or "").strip()
    fills_slot = str(values.get("fills_slot") or values.get("fillsSlot") or "").strip()
    if action_type or fills_slot:
        return bool(_PURCHASE_CONTINUATION_TEXT_RE.search(text))
    return True


def _should_apply_request_patch(request: TStationChatRequest, user_text: str) -> bool:
    patch = _request_slot_patch(request)
    if not patch:
        return False
    values = _ui_action_values(request, patch)
    purchase_patch_keys = {
        "ord_qty",
        "ordQty",
        "quantity",
        "shop_id",
        "shopId",
        "shop_name",
        "shopName",
        "storeName",
        "requested_cal_day",
        "requestedCalDay",
        "rsv_hour",
        "rsvHour",
        "date",
        "time",
        "booking_datetime",
        "bookingDateTime",
    }
    purchase_like_patch = (
        _is_store_selection_request(request, patch)
        or _has_purchase_progress_patch(request)
        or _confirmed_purchase_action(request, patch) is not None
        or any(values.get(key) not in (None, "") for key in purchase_patch_keys)
    )
    if purchase_like_patch and not _allows_deterministic_purchase_resume(user_text, values):
        return False
    return True


def _is_store_selection_request(request: TStationChatRequest, patch: dict[str, Any]) -> bool:
    values = _ui_action_values(request, patch)
    action_type = str(values.get("action_type") or values.get("cta_action") or values.get("actionId") or "").strip()
    fills_slot = str(values.get("fills_slot") or values.get("fillsSlot") or "").strip()
    shop_id = values.get("shop_id") or values.get("shopId")
    explicit_action_payload = request.ui_action if isinstance(request.ui_action, dict) else request.chip_context
    return bool(shop_id) and (
        action_type == "select_store"
        or fills_slot == "shop_id"
        or isinstance(explicit_action_payload, dict)
    )


def _selection_key(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def _normalize_schedule_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 8:
        return f"{digits[:4]}년 {digits[4:6]}월 {digits[6:8]}일"
    return text


def _normalize_action_token(value: Any) -> str:
    return re.sub(r"[^0-9a-z_가-힣]", "", str(value or "").strip().lower())


def _confirmed_purchase_action(request: TStationChatRequest, patch: dict[str, Any]) -> str | None:
    explicit_action_payload = request.ui_action if isinstance(request.ui_action, dict) else request.chip_context
    if not isinstance(explicit_action_payload, dict):
        return None
    values = _ui_action_values(request, patch)
    tokens = {
        _normalize_action_token(values.get("action")),
        _normalize_action_token(values.get("action_type")),
        _normalize_action_token(values.get("cta_action")),
        _normalize_action_token(values.get("ctaAction")),
        _normalize_action_token(values.get("actionId")),
        _normalize_action_token(values.get("confirmed_action")),
        _normalize_action_token(values.get("confirmedAction")),
        _normalize_action_token(values.get("source")),
        _normalize_action_token(values.get("template")),
    }
    if tokens & {
        "quick_order_execute",
        "quick_order_reservation",
        "quickorderexecute",
        "quickorderreservation",
        "confirm_order",
        "order_confirm",
        "orderconfirmed",
        "order_confirmed",
        "place_order",
        "preorder_action",
    }:
        return "order"
    if tokens & {
        "save_to_cart",
        "savetocart",
        "add_to_cart",
        "addtocart",
        "cart_confirm",
        "cart_confirmed",
    }:
        return "cart"
    return None


def _resolve_text_store_selection(request: TStationChatRequest, state: Any, user_text: str) -> Any:
    commerce = state.commerce_state
    if commerce.store.shop_id or commerce.schedule.date or commerce.schedule.time:
        return state
    if not (commerce.product.goods_no and commerce.quantity):
        return state
    user_key = _selection_key(user_text)
    if not user_key:
        return state
    try:
        latest_location = legacy.latest_template_data(request.session_id, "location")
    except Exception:
        logger.warning("[LLM_FIRST_RUNTIME] failed to load latest location template", exc_info=True)
        return state
    if not isinstance(latest_location, dict) or latest_location.get("isBookingFlow") is not True:
        return state
    stores = latest_location.get("stores")
    metadata = latest_location.get("metadata")
    if not isinstance(stores, list) or not isinstance(metadata, list):
        return state
    for store, meta in zip(stores, metadata):
        if not isinstance(store, dict) or not isinstance(meta, dict):
            continue
        shop_id = str(meta.get("shopId") or meta.get("shop_id") or "").strip()
        name = str(store.get("nameAddress") or store.get("shopName") or store.get("name") or "").strip()
        if not shop_id or not name:
            continue
        name_key = _selection_key(name)
        if user_key == name_key or user_key in name_key or name_key in user_key:
            return apply_state_rules(state, store_patch={"shop_id": shop_id, "shop_name": name})
    return state


def _store_selection_schedule_plan(
    request: TStationChatRequest,
    state: Any,
    user_text: str,
    *,
    text_selection_resolved: bool = False,
) -> PlannerDecision | None:
    patch = _request_slot_patch(request)
    direct_selection = _is_store_selection_request(request, patch)
    if not (direct_selection or text_selection_resolved):
        return None
    values = _ui_action_values(request, patch)
    if direct_selection and not _allows_deterministic_purchase_resume(user_text, values, text_selection_resolved=text_selection_resolved):
        return None
    commerce = state.commerce_state
    if commerce.schedule.date or commerce.schedule.time:
        return None
    if not (commerce.product.goods_no and commerce.quantity and commerce.store.shop_id):
        return None
    known_inputs = {
        "goods_no": commerce.product.goods_no,
        "product_name": commerce.product.product_name,
        "tire_size": commerce.product.tire_size,
        "ord_qty": commerce.quantity,
        "shop_id": commerce.store.shop_id,
        "store_name": commerce.store.shop_name,
        "region": commerce.store.region,
    }
    schedule_mode = values.get("schedule_mode") or values.get("scheduleMode") or values.get("inventory_mode") or values.get("inventoryMode")
    if schedule_mode not in (None, ""):
        known_inputs["schedule_mode"] = schedule_mode
    return PlannerDecision(
        selected_afs=[
            SelectedAF(
                af=AgentFlow.QUICK_SHOPPING,
                reason="store selected for an active purchase or inventory flow; show schedule choices",
                required_inputs=["goods_no", "ord_qty", "shop_id"],
                known_inputs={k: v for k, v in known_inputs.items() if v not in (None, "")},
                missing_inputs=[],
            )
        ],
        conversation_goal="show_store_schedule_after_store_selection",
        answer_mode="tool_grounded_answer",
        requires_user_confirmation=False,
        resume_previous_flow=True,
    )


def _has_purchase_progress_patch(request: TStationChatRequest) -> bool:
    patch = _request_slot_patch(request)
    values = _ui_action_values(request, patch)
    action_type = str(values.get("action_type") or values.get("cta_action") or values.get("actionId") or "").strip()
    fills_slot = str(values.get("fills_slot") or values.get("fillsSlot") or "").strip()
    purchase_action_types = {
        "select_quantity",
        "select_store",
        "select_schedule",
        "select_date",
        "select_time",
        "quick_order_reservation",
    }
    purchase_slots = {
        "ord_qty",
        "ordQty",
        "quantity",
        "shop_id",
        "shopId",
        "requested_cal_day",
        "requestedCalDay",
        "rsv_hour",
        "rsvHour",
        "date",
        "time",
        "booking_datetime",
        "bookingDateTime",
    }
    if action_type and action_type not in purchase_action_types:
        return False
    if fills_slot and fills_slot not in purchase_slots:
        return False
    if not (action_type or fills_slot):
        return False
    purchase_keys = {
        "ord_qty",
        "ordQty",
        "quantity",
        "shop_id",
        "shopId",
        "shop_name",
        "shopName",
        "storeName",
        "region",
        "region_code",
        "regionCode",
        "requested_cal_day",
        "requestedCalDay",
        "rsv_hour",
        "rsvHour",
        "date",
        "time",
    }
    return any(values.get(key) not in (None, "") for key in purchase_keys)


def _commerce_known_inputs(state: Any) -> dict[str, Any]:
    commerce = state.commerce_state
    known_inputs = {
        "goods_no": commerce.product.goods_no,
        "product_name": commerce.product.product_name,
        "tire_size": commerce.product.tire_size,
        "ord_qty": commerce.quantity,
        "shop_id": commerce.store.shop_id,
        "store_name": commerce.store.shop_name,
        "region": commerce.store.region,
        "date": commerce.schedule.date,
        "time": commerce.schedule.time,
    }
    return {k: v for k, v in known_inputs.items() if v not in (None, "")}


def _alternative_request_target(user_text: str) -> str | None:
    text = str(user_text or "").lower()
    if not any(token in text for token in ("다른", "다른거", "다른 것", "대안", "말고")):
        return None
    if any(token in text for token in ("타이어", "상품", "제품")):
        return "product"
    if any(token in text for token in ("매장", "장착점", "지점", "지역")):
        return "store"
    return None


def _alternative_request_plan(user_text: str, state: Any) -> PlannerDecision | None:
    target = _alternative_request_target(user_text)
    if target is None:
        return None
    commerce = state.commerce_state
    known_inputs = _commerce_known_inputs(state)
    if target == "product" and commerce.product.goods_no:
        known_inputs["alternative_target"] = "product"
        known_inputs["exclude_goods_no"] = commerce.product.goods_no
        if commerce.product.product_name:
            known_inputs["exclude_product_name"] = commerce.product.product_name
        known_inputs.setdefault("recommendation_type", "tstation")
        return PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_RECOMMENDATION,
                    reason="user asked for alternative tire; recommend excluding current product",
                    required_inputs=[],
                    known_inputs=known_inputs,
                    missing_inputs=[],
                )
            ],
            conversation_goal="show_alternative_products",
            answer_mode="tool_grounded_answer",
            requires_user_confirmation=False,
            resume_previous_flow=True,
        )
    if target == "store" and commerce.product.goods_no and commerce.quantity:
        known_inputs["alternative_target"] = "store"
        if commerce.store.shop_id:
            known_inputs["exclude_shop_id"] = commerce.store.shop_id
        if commerce.store.shop_name:
            known_inputs["exclude_store_name"] = commerce.store.shop_name
        return PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.QUICK_SHOPPING,
                    reason="user asked for alternative store or region; search purchase store candidates excluding current store",
                    required_inputs=["goods_no", "ord_qty", "store"],
                    known_inputs=known_inputs,
                    missing_inputs=[],
                )
            ],
            conversation_goal="show_alternative_stores",
            answer_mode="tool_grounded_answer",
            requires_user_confirmation=False,
            resume_previous_flow=True,
        )
    return None


def _purchase_progress_plan(request: TStationChatRequest, state: Any) -> PlannerDecision | None:
    if not _has_purchase_progress_patch(request):
        return None
    patch = _request_slot_patch(request)
    if not _allows_deterministic_purchase_resume(_last_user_text(request), _ui_action_values(request, patch)):
        return None
    if not state.commerce_state.product.goods_no:
        return None
    return PlannerDecision(
        selected_afs=[
            SelectedAF(
                af=AgentFlow.QUICK_SHOPPING,
                reason="purchase slot value supplied for an active purchase flow; continue to the next required step",
                required_inputs=["goods_no", "ord_qty", "shop_id", "schedule"],
                known_inputs=_commerce_known_inputs(state),
                missing_inputs=[],
            )
        ],
        conversation_goal="continue_purchase_flow",
        answer_mode="tool_grounded_answer",
        requires_user_confirmation=False,
        resume_previous_flow=True,
    )


def _confirmed_purchase_plan(request: TStationChatRequest, state: Any) -> PlannerDecision | None:
    patch = _request_slot_patch(request)
    values = _ui_action_values(request, patch)
    confirmed_action = _confirmed_purchase_action(request, patch)
    if confirmed_action is None:
        return None
    if not _allows_deterministic_purchase_resume(_last_user_text(request), values):
        return None
    if not state.commerce_state.product.goods_no:
        return None
    known_inputs = _commerce_known_inputs(state)
    known_inputs["confirmed_action"] = confirmed_action
    for target, aliases in {
        "car_lnc_cd": ("car_lnc_cd", "carLncCd"),
        "date": ("requested_cal_day", "requestedCalDay", "date"),
        "time": ("rsv_hour", "rsvHour", "time"),
    }.items():
        for alias in aliases:
            if values.get(alias) not in (None, ""):
                known_inputs[target] = values[alias]
                break
    return PlannerDecision(
        selected_afs=[
            SelectedAF(
                af=AgentFlow.QUICK_SHOPPING,
                reason="confirmed purchase side-effect action from an explicit UI action",
                required_inputs=["goods_no", "ord_qty"] if confirmed_action == "cart" else ["goods_no", "ord_qty", "shop_id", "schedule"],
                known_inputs=known_inputs,
                missing_inputs=[],
            )
        ],
        conversation_goal=f"execute_confirmed_{confirmed_action}",
        answer_mode="tool_grounded_answer",
        requires_user_confirmation=False,
        resume_previous_flow=True,
    )


_ESCALATION_CONFIRM_LABELS = frozenset({"1:1 문의하기", "상담사 연결하기"})
_ESCALATION_AFFIRMATIVE_RE = re.compile(r"^(?:네|응|어|예|좋아요?|진행(?:할게요?|해\s*주세요|해줘)?|해\s*주세요|해줘|콜)[.!~♥️😊]*$")


def _confirmed_escalation_plan(state: Any, user_text: str) -> PlannerDecision | None:
    """Detect confirmation of a just-shown escalation prompt from plain chat text.

    Unlike the purchase confirm→execute flow, the escalation confirmation
    quickReply carries no structured ui_action/cta metadata for the FE to echo
    back — it is a plain label/domain chip, so a click just resubmits the
    label text like any other typed message. The only signal available is:
    a pending escalation target was recorded last turn, and this turn's text
    matches the button label (or a plain "yes").
    """
    last_facts = state.last_facts if isinstance(state.last_facts, dict) else {}
    pending_target = str(last_facts.get("pending_escalation_target") or "").strip()
    if not pending_target:
        return None
    text = str(user_text or "").strip()
    if text not in _ESCALATION_CONFIRM_LABELS and not _ESCALATION_AFFIRMATIVE_RE.match(text):
        return None
    return PlannerDecision(
        selected_afs=[
            SelectedAF(
                af=AgentFlow.FALLBACK_ESCALATION,
                reason="confirmed escalation from a prior confirmation prompt",
                required_inputs=[],
                known_inputs={"escalation_target": pending_target, "confirmed_action": "escalation"},
                missing_inputs=[],
            )
        ],
        conversation_goal="execute_confirmed_escalation",
        answer_mode="tool_grounded_answer",
        requires_user_confirmation=False,
        resume_previous_flow=True,
    )


def _vehicle_selection_recommendation_plan(request: TStationChatRequest) -> PlannerDecision | None:
    patch = _request_slot_patch(request)
    values = _ui_action_values(request, patch)
    source_intent = str(
        values.get("sourceIntent")
        or values.get("source_intent")
        or values.get("expectedContractIntent")
        or values.get("expected_contract_intent")
        or ""
    ).strip()
    action_type = str(values.get("action_type") or values.get("cta_action") or values.get("ctaAction") or "").strip()
    if source_intent != "vehicle_resolved_recommendation" and action_type != "select_vehicle_candidate":
        return None
    car_lnc_cd = values.get("car_lnc_cd") or values.get("carLncCd")
    tire_size = (
        values.get("tire_size")
        or values.get("tireSize")
        or values.get("tire_size_fr")
        or values.get("tireSizeFr")
        or values.get("tire_size_re")
        or values.get("tireSizeRe")
    )
    if not (car_lnc_cd or tire_size):
        return None
    vehicle_type = str(values.get("vehicle_type") or values.get("vehicleType") or "").strip()
    if not vehicle_type:
        fallback_text = " ".join(
            str(values.get(key) or "").strip()
            for key in ("car_model_det", "carModelDet", "car_nm", "carName", "car_model", "carModel")
            if str(values.get(key) or "").strip()
        )
        vehicle_type = legacy.normalize_vehicle_type_from_car_type(
            values.get("car_type") or values.get("carType") or values.get("car_type_nm") or values.get("carTypeNm"),
            fallback_text=fallback_text,
        ) or ""
    known_inputs = {
        "car_lnc_cd": car_lnc_cd,
        "tire_size": tire_size,
        "vehicle_type": vehicle_type,
        "recommendation_type": values.get("recommendation_type") or values.get("rcmd_type") or "tstation",
        "season_nm": values.get("season_nm"),
        "sort_by": values.get("sort_by"),
        "min_price": values.get("min_price"),
        "max_price": values.get("max_price"),
        "limit": values.get("limit") or 3,
    }
    return PlannerDecision(
        selected_afs=[
            SelectedAF(
                af=AgentFlow.PRODUCT_RECOMMENDATION,
                reason="registered vehicle selected; continue vehicle-based tire recommendation",
                required_inputs=[],
                known_inputs={k: v for k, v in known_inputs.items() if v not in (None, "")},
                missing_inputs=[],
            )
        ],
        conversation_goal="recommend_tires_for_selected_vehicle",
        answer_mode="tool_grounded_answer",
        requires_user_confirmation=False,
        resume_previous_flow=True,
    )


def _attach_runtime_known_inputs(planner: PlannerDecision, request: TStationChatRequest) -> PlannerDecision:
    xpos, ypos = _request_location_coords(request)
    for selected in planner.selected_afs:
        if request.user_id:
            selected.known_inputs.setdefault("mbr_no", request.user_id)
        if xpos is not None and ypos is not None:
            selected.known_inputs.setdefault("user_xpos", xpos)
            selected.known_inputs.setdefault("user_ypos", ypos)
    return planner


def _apply_request_patch(state: Any, request: TStationChatRequest) -> Any:
    patch = _request_slot_patch(request)
    if not patch:
        return state
    product_patch = {
        "goods_no": patch.get("goods_no") or patch.get("goodsNo") or patch.get("goodsId"),
        "product_name": patch.get("product_name") or patch.get("productName") or patch.get("product"),
        "tire_size": patch.get("tire_size") or patch.get("tireSize"),
    }
    raw_qty = patch.get("ord_qty") or patch.get("ordQty") or patch.get("quantity")
    quantity = None
    try:
        quantity = int(raw_qty) if raw_qty not in (None, "") else None
    except (TypeError, ValueError):
        quantity = None
    store_patch = {
        "shop_id": patch.get("shop_id") or patch.get("shopId"),
        "shop_name": patch.get("shop_name") or patch.get("shopName") or patch.get("storeName"),
        "region": patch.get("region") or patch.get("region_code") or patch.get("regionCode"),
    }
    schedule_patch = {
        "date": _normalize_schedule_date(
            patch.get("requested_cal_day") or patch.get("requestedCalDay") or patch.get("date")
        ),
        "time": patch.get("rsv_hour") or patch.get("rsvHour") or patch.get("time"),
    }
    raw_price = patch.get("final_price") or patch.get("paymentAmount") or patch.get("payment_amount")
    price = None
    try:
        price = int(raw_price) if raw_price not in (None, "") else None
    except (TypeError, ValueError):
        price = None
    return apply_state_rules(
        state,
        product_patch={k: v for k, v in product_patch.items() if v not in (None, "")},
        quantity=quantity,
        store_patch={k: v for k, v in store_patch.items() if v not in (None, "")},
        schedule_patch={k: v for k, v in schedule_patch.items() if v not in (None, "")},
        price_patch={"final_price": price, "source": "request_slots"} if price is not None else None,
    )


def _schedule_selection_guard_event(request: TStationChatRequest) -> dict[str, Any] | None:
    patch = _request_slot_patch(request)
    if not patch:
        return None
    values = _ui_action_values(request, patch)
    action_type = str(values.get("action_type") or values.get("cta_action") or values.get("ctaAction") or "").strip()
    fills_slot = str(values.get("fills_slot") or values.get("fillsSlot") or "").strip()
    date_value = values.get("requested_cal_day") or values.get("requestedCalDay") or values.get("date")
    time_value = values.get("rsv_hour") or values.get("rsvHour") or values.get("time")
    if not (date_value and time_value):
        return None
    if action_type != "select_schedule" and "requested_cal_day" not in fills_slot and "rsv_hour" not in fills_slot:
        return None
    return build_past_schedule_selection_event(date_value, time_value)


class LLMFirstRuntime:
    def __init__(
        self,
        *,
        planner: LeadingAgentPlanner | None = None,
        executor: AFExecutor | None = None,
        composer: Composer | None = None,
        state_store: LLMFirstStateStore | None = None,
    ):
        self.planner = planner or LeadingAgentPlanner(_make_llm(settings.AI_MODEL_QC_AGENT))
        self.executor = executor or AFExecutor()
        self.composer = composer or Composer(_make_llm(settings.AI_MODEL, streaming=False, timeout=120))
        self.state_store = state_store or LLMFirstStateStore()

    async def run(self, request: TStationChatRequest) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        user_text = _last_user_text(request)
        set_trace_name(user_text[:60] if user_text else "llm_first_chat")
        state = self.state_store.load(request.session_id)
        if guard_event := _schedule_selection_guard_event(request):
            self.state_store.save(request.session_id, state)
            text = str(guard_event.get("data", {}).get("assistantResponse") or "")
            metadata = {
                "runtime": "llm_first",
                "planner": PlannerDecision(
                    selected_afs=[],
                    conversation_goal="reject_past_schedule_selection",
                    answer_mode="tool_grounded_answer",
                    requires_user_confirmation=False,
                    resume_previous_flow=True,
                ).model_dump(mode="json"),
                "qc_status": "ok",
                "tool_calls": [],
                "missing_inputs": [],
            }
            return text, [guard_event], metadata
        if _should_apply_request_patch(request, user_text):
            state = _apply_request_patch(state, request)
        store_shop_id_before_text_resolution = state.commerce_state.store.shop_id
        state = _resolve_text_store_selection(request, state, user_text)
        text_selection_resolved = (
            not store_shop_id_before_text_resolution
            and bool(state.commerce_state.store.shop_id)
            and bool(state.commerce_state.product.goods_no and state.commerce_state.quantity)
        )
        planner = _store_selection_schedule_plan(
            request,
            state,
            user_text,
            text_selection_resolved=text_selection_resolved,
        )
        if planner is None:
            planner = _vehicle_selection_recommendation_plan(request)
        if planner is None:
            planner = _confirmed_purchase_plan(request, state)
        if planner is None:
            planner = _alternative_request_plan(user_text, state)
        if planner is None:
            planner = _purchase_progress_plan(request, state)
        if planner is None:
            planner = _confirmed_escalation_plan(state, user_text)
        if planner is None:
            planner = await self.planner.plan(
                user_text=user_text,
                state=state,
                session_id=request.session_id,
                user_id=request.user_id,
                trace_id=request.tracing_id,
            )
        planner = _attach_runtime_known_inputs(planner, request)
        bundle = await self.executor.execute(user_text=user_text, state=state, planner=planner)
        text = await self.composer.compose(
            user_text=user_text,
            bundle=bundle,
            session_id=request.session_id,
            user_id=request.user_id,
            trace_id=request.tracing_id,
        )
        qc_status, qc_event = verify_response(text, bundle)
        events = list(bundle.templates)
        if qc_event is not None:
            events = [qc_event]
            text = str(qc_event.get("data", {}).get("assistantResponse") or text)
        self.state_store.save(request.session_id, bundle.state)
        metadata = {
            "runtime": "llm_first",
            "planner": planner.model_dump(mode="json"),
            "qc_status": qc_status,
            "tool_calls": [
                call.model_dump(mode="json", exclude={"result"})
                for call in bundle.tool_calls
            ],
            "missing_inputs": bundle.missing_inputs,
        }
        return text, events, metadata

    async def stream(self, request: TStationChatRequest) -> AsyncIterator[str]:
        yield _sse({"type": "agent_flow", "agent": "[LEADING AGENT]", "status": "start"})
        try:
            text, events, metadata = await self.run(request)
            yield _sse({"type": "agent_flow", "agent": "[LEADING AGENT]", "status": "done", "metadata": metadata})
            for event in events:
                yield _sse(event)
            if text and not events:
                yield _sse(_text_response_event(text))
            if text:
                yield _sse({"type": "token", "content": text})
                yield _sse({"type": "message", "content": text, "agent": "[COMPOSER]"})
            yield _sse({"type": "DONE"})
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.exception("[LLM_FIRST_RUNTIME] stream failed")
            message = "요청을 처리하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            yield _sse({
                "type": "data",
                "template": "quickReply",
                "data": {
                    "assistantResponse": message,
                    "quickReplies": [{"label": "다시 시도", "domain": "LEADING"}],
                    "metadata": {"source": "llm_first_runtime_error", "error": str(exc)},
                },
            })
            yield _sse({"type": "token", "content": message})
            yield _sse({"type": "message", "content": message, "agent": "[COMPOSER]"})
            yield "data: [DONE]\n\n"


async def chat(request: TStationChatRequest):
    runtime = LLMFirstRuntime()
    if request.stream:
        return StreamingResponse(
            runtime.stream(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    text, _, _ = await runtime.run(request)
    return TStationChatResponse(content=text)


def enabled() -> bool:
    return bool(getattr(settings, "AI_LLM_FIRST_RUNTIME_ENABLED", False))
