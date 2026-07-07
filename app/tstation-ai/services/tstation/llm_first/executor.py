from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from services.tstation.llm_first.models import AgentFlow, ConversationState, FactBundle, PlannerDecision, ToolCallRecord
from services.tstation.llm_first.planner import normalize_tire_size
from services.tstation.llm_first.persistence.state import apply_state_rules
from services.tstation.llm_first.templates import (
    build_benefit_applicable_products_template,
    build_benefit_event_deal_template,
    build_datepick_template,
    build_event_applicable_products_template,
    build_list_car_template,
    build_location_template,
    build_preorder_template,
    build_product_comparison_template,
    build_product_template,
    build_voucher_template,
)
from services.tstation.llm_first.adapters import legacy
from services.tstation.llm_first.store_schedule_search import normalize_store_place_query, resolve_store_schedule_search
from services.tstation.llm_first.store_search_filters import resolve_store_search_filters
from services.tstation.llm_first.tooling.registry import invoke_tool

logger = logging.getLogger(__name__)

_RECOMMENDATION_SIGNALS = ("추천", "권장", "골라", "고르", "뽑아", "좋은", "베스트", "best")
_COMPARISON_SIGNALS = ("비교", "차이", "다른점", "다른 점", "vs", "대비", "뭐가 더", "어느게 더", "어느 게 더")
_ALTERNATIVE_SIGNALS = ("다른", "다른거", "다른 것", "대안", "말고")


def _append_template(bundle: FactBundle, event: dict[str, Any] | None) -> None:
    if event is not None:
        _normalize_preorder_booking_datetime(event)
        bundle.templates.append(event)


def _is_recommendation_request(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(signal in normalized for signal in _RECOMMENDATION_SIGNALS)


def _is_comparison_request(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(signal in normalized for signal in _COMPARISON_SIGNALS)


def _is_alternative_request(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(signal in normalized for signal in _ALTERNATIVE_SIGNALS)


def _alternative_target(text: str) -> str | None:
    normalized = str(text or "").lower()
    if not _is_alternative_request(normalized):
        return None
    if any(token in normalized for token in ("타이어", "상품", "제품")):
        return "product"
    if any(token in normalized for token in ("매장", "장착점", "지점", "지역")):
        return "store"
    return None


def _normalize_preorder_booking_datetime(event: dict[str, Any]) -> None:
    if event.get("template") != "preOrder":
        return
    data = event.get("data")
    if not isinstance(data, dict):
        return
    order_info = data.get("orderInfo")
    metadata = data.get("metadata")
    if not isinstance(order_info, dict):
        return
    booking_datetime = str(order_info.get("bookingDateTime") or "").strip()
    if not booking_datetime or re.search(r"\d{1,2}:\d{2}\s*$", booking_datetime):
        return
    rsv_hour = ""
    if isinstance(metadata, dict):
        rsv_hour = str(metadata.get("rsvHour") or metadata.get("rsv_hour") or "").strip()
    digits = re.sub(r"\D", "", rsv_hour) or (re.search(r"(\d{1,2})\s*$", booking_datetime).group(1) if re.search(r"(\d{1,2})\s*$", booking_datetime) else "")
    if len(digits) >= 4:
        digits = digits[:2]
    if len(digits) not in {1, 2}:
        return
    try:
        hour = int(digits)
    except ValueError:
        return
    if not 0 <= hour <= 23:
        return
    order_info["bookingDateTime"] = re.sub(r"\d{1,2}\s*$", f"{hour:02d}:00", booking_datetime)


def _escalation_confirmation_event(target: str) -> dict[str, Any]:
    if target == "human":
        assistant_response = "상담사 연결은 사용자 확인 후 진행할 수 있어요. 상담사 연결을 진행할까요?"
        label = "상담사 연결하기"
    else:
        assistant_response = "1:1 문의 연결은 사용자 확인 후 진행할 수 있어요. 1:1 문의 작성 페이지로 이동할까요?"
        label = "1:1 문의하기"
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": [
                {"label": label, "domain": "SUPPORT"},
                {"label": "아니요", "domain": "LEADING"},
            ],
            "predictedDomains": ["SUPPORT", "LEADING"],
            "metadata": {
                "source": "llm_first_escalation_confirmation",
                "escalationTarget": target,
                "requiresConfirmation": True,
            },
        },
    }


def _escalation_completion_event(target: str, result: Any) -> dict[str, Any]:
    if isinstance(result, dict) and result.get("status") == "error":
        message = "죄송해요, 지금은 연결에 실패했어요. 잠시 후 다시 시도해 주세요."
    elif target == "human":
        message = "상담사 연결 요청을 접수했어요. 곧 연결해 드릴게요."
    else:
        message = "1:1 문의가 접수됐어요. 확인 후 답변드릴게요."
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": message,
            "quickReplies": [],
            "predictedDomains": ["SUPPORT"],
            "metadata": {
                "source": "llm_first_escalation_complete",
                "escalationTarget": target,
            },
        },
    }


def _escalation_declined_event() -> dict[str, Any]:
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "알겠습니다. 다른 도움이 필요하시면 말씀해 주세요.",
            "quickReplies": [],
            "predictedDomains": ["LEADING"],
            "metadata": {
                "source": "llm_first_escalation_declined",
            },
        },
    }


def _clear_pending_escalation(state: ConversationState) -> ConversationState:
    """Drop the pending-escalation flag now that it's resolved (confirmed or declined).

    last_facts merges are additive (see _remember_followup_context) — nothing
    else removes a stale key, so leaving it set would wrongly re-trigger the
    confirm/decline shortcuts on a later, unrelated turn.
    """
    cleared_facts = {k: v for k, v in (state.last_facts or {}).items() if k != "pending_escalation_target"}
    return state.model_copy(update={"last_facts": cleared_facts})


def _favorite_store_empty_event() -> dict[str, Any]:
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "등록된 단골매장이 없어요. 매장 검색으로 안내해 드릴까요?",
            "quickReplies": [
                {"label": "매장 검색", "domain": "TRANSACTION"},
                {"label": "아니요", "domain": "LEADING"},
            ],
            "predictedDomains": ["TRANSACTION", "LEADING"],
            "metadata": {
                "source": "llm_first_favorite_store_empty",
                "response_shape_key": "favorite_store_lookup",
            },
        },
    }


def _unsupported_region_event(query: Any) -> dict[str, Any]:
    region = str(query or "").strip() or "입력하신 지역"
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": (
                f"{region}은 티스테이션 매장 검색 서비스 지역으로 확인되지 않아요. "
                "국내 지역명이나 현재 위치 기준으로 다시 검색해 주세요."
            ),
            "quickReplies": [
                {"label": "현재 위치로 검색", "domain": "TRANSACTION"},
                {"label": "지역 다시 입력", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["TRANSACTION"],
            "metadata": {
                "source": "llm_first_unsupported_region",
                "response_shape_key": "unsupported_region_search",
                "region": region,
            },
        },
    }


def _store_search_query(value: Any) -> str | None:
    return normalize_store_place_query(value)


def _quantity_quickreply_event() -> dict[str, Any]:
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "수량 정보를 알려주시면 이어서 확인해 드릴게요.",
            "quickReplies": [
                {"label": "1개", "domain": "TRANSACTION"},
                {"label": "2개", "domain": "TRANSACTION"},
                {"label": "3개", "domain": "TRANSACTION"},
                {"label": "4개", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["TRANSACTION"],
            "metadata": {
                "source": "llm_first_quantity_missing",
                "response_shape_key": "quantity_selection",
                "fillsSlot": "ord_qty",
                "fills_slot": "ord_qty",
            },
        },
    }


def _success_payload(result: Any) -> Any:
    if isinstance(result, dict) and result.get("status") == "error":
        return None
    return result


def _is_domestic_region_gate_blocked(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    data = result.get("data")
    if not isinstance(data, dict):
        return False
    search = data.get("search")
    if not isinstance(search, dict):
        return False
    return search.get("source") == "place_fallback_blocked" and search.get("reason") == "not_domestic_search_area"


def _first_item(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    for key in ("items", "products", "goods", "stores"):
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, list):
            return next((item for item in value if isinstance(item, dict)), None)
    return data if isinstance(data, dict) else None


def _items(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    if isinstance(data, dict):
        for key in ("items", "cars", "vehicles"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [data]
    return []


def _digits_date(value: Any) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) >= 8:
        return digits[:8]
    return None


def _hour(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 4:
        digits = digits[:2]
    if len(digits) in {1, 2}:
        hour = int(digits)
        if 0 <= hour <= 23:
            return f"{hour:02d}"
    match = re.search(r"(\d{1,2})\s*시", text)
    if match:
        hour = int(match.group(1))
        if 0 <= hour <= 23:
            return f"{hour:02d}"
    return None


def _tool_data_list(bundle: FactBundle) -> list[dict[str, Any]]:
    return [
        {"tool": call.tool_name, "args": call.args, "data": call.result}
        for call in bundle.tool_calls
        if not call.blocked
    ]


def _mark_completion_event(event: dict[str, Any] | None, *, source: str, called_tool: str) -> dict[str, Any] | None:
    if event is None:
        return None
    data = event.get("data")
    if isinstance(data, dict):
        metadata = data.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata.setdefault("source", source)
            metadata.setdefault("called_tools", [called_tool])
    event.setdefault("assistant_response_source", source)
    return event


def _vehicle_key(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def _vehicle_aliases(row: dict[str, Any]) -> set[str]:
    aliases = {
        row.get("car_no"),
        row.get("car_nm"),
        row.get("carName"),
        row.get("car_model_det"),
        row.get("carModelDet"),
        row.get("ver_opt_choc"),
        row.get("carTrim"),
    }
    normalized = {_vehicle_key(alias) for alias in aliases if alias}
    return {alias for alias in normalized if alias}


def _match_registered_vehicle(rows: list[dict[str, Any]], anchor: str) -> dict[str, Any] | None:
    key = _vehicle_key(anchor)
    if not key:
        return None
    matches = [row for row in rows if any(alias and (alias in key or key in alias) for alias in _vehicle_aliases(row))]
    return matches[0] if len(matches) == 1 else None


def _vehicle_recommendation_args(row: dict[str, Any], known: dict[str, Any]) -> dict[str, Any] | None:
    car_lnc_cd = str(row.get("car_lnc_cd") or row.get("carLncCd") or "").strip()
    tire_size = normalize_tire_size(str(row.get("tire_size_fr") or row.get("tireSize") or "")) or normalize_tire_size(
        str(row.get("tire_size_re") or row.get("tireSizeRe") or "")
    )
    if not (car_lnc_cd or tire_size):
        return None
    recommendation_type = known.get("recommendation_type")
    if recommendation_type in (None, "", "none"):
        recommendation_type = "tstation"
    args: dict[str, Any] = {
        "rcmd_type": recommendation_type,
        "limit": min(max(int(known.get("limit") or 3), 1), 10),
    }
    if car_lnc_cd:
        args["car_lnc_cd"] = car_lnc_cd
    elif tire_size:
        args["tire_size"] = tire_size
    vehicle_type = _vehicle_type_from_row(row, known)
    if vehicle_type:
        args["vehicle_type"] = vehicle_type
    for key in ("season_nm", "sort_by", "min_price", "max_price"):
        value = known.get(key)
        if value not in (None, "", "none"):
            args[key] = value
    return args


def _vehicle_first_nonempty(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _vehicle_type_from_row(row: dict[str, Any], known: dict[str, Any] | None = None) -> str | None:
    explicit = str((known or {}).get("vehicle_type") or row.get("vehicle_type") or row.get("vehicleType") or "").strip()
    if explicit and explicit != "none":
        return explicit
    fallback_text = " ".join(
        part
        for part in (
            _vehicle_first_nonempty(row, "car_model_det", "carModelDet"),
            _vehicle_first_nonempty(row, "car_nm", "carName"),
            _vehicle_first_nonempty(row, "car_model", "carModel"),
        )
        if part
    )
    return (
        legacy.normalize_vehicle_type_from_car_type(
            _vehicle_first_nonempty(row, "car_knd_nm", "carKndNm", "car_type", "carType", "car_type_nm", "carTypeNm"),
            fallback_text=fallback_text,
        )
        or _infer_vehicle_type_from_text(fallback_text)
    )


def _infer_vehicle_type_from_text(text: str) -> str | None:
    match = legacy.match_vehicle_model_category(text)
    return match.category if match is not None else None


def _infer_vehicle_type_from_known(known: dict[str, Any], user_text: str) -> str | None:
    explicit = str(known.get("vehicle_type") or "").strip()
    if explicit and explicit != "none":
        return explicit
    fallback_text = " ".join(
        str(known.get(key) or "").strip()
        for key in ("vehicle_query", "car_model", "product_name")
        if str(known.get(key) or "").strip()
    )
    car_type = str(known.get("car_type") or "").strip()
    return (
        legacy.normalize_vehicle_type_from_car_type(car_type, fallback_text=fallback_text or user_text)
        or _infer_vehicle_type_from_text(fallback_text or user_text)
    )


def _current_product_exclusions(state: ConversationState, known: dict[str, Any]) -> dict[str, set[str]]:
    goods_ids = {
        str(value).strip()
        for value in (state.commerce_state.product.goods_no, known.get("exclude_goods_no"), known.get("goods_no") if known.get("alternative_target") == "product" else None)
        if str(value or "").strip()
    }
    names = {
        str(value).strip()
        for value in (state.commerce_state.product.product_name, known.get("exclude_product_name"), known.get("product_name") if known.get("alternative_target") == "product" else None)
        if str(value or "").strip()
    }
    return {"goods_ids": goods_ids, "names": names}


def _current_store_exclusions(state: ConversationState, known: dict[str, Any]) -> dict[str, set[str]]:
    shop_ids = {
        str(value).strip()
        for value in (state.commerce_state.store.shop_id, known.get("exclude_shop_id"), known.get("shop_id") if known.get("alternative_target") == "store" else None)
        if str(value or "").strip()
    }
    names = {
        str(value).strip()
        for value in (state.commerce_state.store.shop_name, known.get("exclude_store_name"), known.get("store_name") if known.get("alternative_target") == "store" else None)
        if str(value or "").strip()
    }
    return {"shop_ids": shop_ids, "names": names}


def _vehicle_type_recommendation_args(known: dict[str, Any], user_text: str) -> dict[str, Any] | None:
    vehicle_type = _infer_vehicle_type_from_known(known, user_text)
    if not vehicle_type:
        return None
    recommendation_type = known.get("recommendation_type")
    if recommendation_type in (None, "", "none"):
        recommendation_type = "tstation"
    args: dict[str, Any] = {
        "rcmd_type": recommendation_type,
        "limit": min(max(int(known.get("limit") or 3), 1), 10),
        "vehicle_type": vehicle_type,
    }
    for key in ("season_nm", "sort_by", "min_price", "max_price"):
        value = known.get(key)
        if value not in (None, "", "none"):
            args[key] = value
    return args


def _remember_followup_context(
    state: ConversationState,
    *,
    conversation_summary: str | None = None,
    last_facts_patch: dict[str, Any] | None = None,
) -> ConversationState:
    updated = state.model_copy(deep=True)
    if conversation_summary:
        updated.conversation_summary = conversation_summary
    if last_facts_patch:
        updated.last_facts = {
            **(updated.last_facts or {}),
            **{key: value for key, value in last_facts_patch.items() if value not in (None, "", [], {})},
        }
    return updated


def _preview_text(value: Any, *, limit: int = 140) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _template_followup_context(event: dict[str, Any] | None, state: ConversationState, bundle: FactBundle) -> tuple[str | None, dict[str, Any] | None]:
    if not isinstance(event, dict):
        return None, None
    template = str(event.get("template") or "").strip()
    data = event.get("data")
    if not isinstance(data, dict):
        return None, None
    assistant_response = _preview_text(data.get("assistantResponse"))
    response_shape_key = ""
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        response_shape_key = str(metadata.get("response_shape_key") or "").strip()
    followup: dict[str, Any] = {
        "template": template,
        "assistant_response_preview": assistant_response,
        "tool_names": [call.tool_name for call in bundle.tool_calls],
    }
    if response_shape_key:
        followup["response_shape_key"] = response_shape_key

    if template == "product":
        products = data.get("products") if isinstance(data.get("products"), list) else []
        meta_list = metadata if isinstance(metadata, list) else []
        product_names = [str(item.get("titleProductName") or item.get("title") or "").strip() for item in products if isinstance(item, dict)]
        resolved_products: list[dict[str, Any]] = []
        for index, item in enumerate(products):
            if not isinstance(item, dict):
                continue
            goods_no = ""
            if index < len(meta_list) and isinstance(meta_list[index], dict):
                goods_no = str(meta_list[index].get("goodsId") or "").strip()
            resolved_products.append({
                key: value
                for key, value in {
                    "goodsNo": goods_no,
                    "productName": str(item.get("titleProductName") or item.get("title") or "").strip(),
                    "tireSize": str(item.get("titleTires") or "").strip(),
                }.items()
                if value
            })
        summary = f"최근 상품 후보: {', '.join(product_names[:2])}" if product_names else assistant_response
        followup.update({
            "followup_type": "product_list",
            "product_names": product_names[:5],
            "resolved_products": resolved_products[:5],
            "is_booking_flow": data.get("isBookingFlow") is True,
        })
        if len(product_names) == 1:
            followup["product_name"] = product_names[0]
        if resolved_products and resolved_products[0].get("goodsNo"):
            followup["goods_no"] = resolved_products[0]["goodsNo"]
        return summary, followup

    if template == "location":
        stores = data.get("stores") if isinstance(data.get("stores"), list) else []
        meta_list = metadata if isinstance(metadata, list) else []
        store_names = [str(item.get("nameAddress") or "").strip() for item in stores if isinstance(item, dict)]
        shop_ids = [
            str(item.get("shopId") or "").strip()
            for item in meta_list
            if isinstance(item, dict) and str(item.get("shopId") or "").strip()
        ]
        summary = f"최근 매장 후보: {', '.join(store_names[:2])}" if store_names else assistant_response
        followup.update({
            "followup_type": "store_list",
            "store_names": store_names[:5],
            "shop_ids": shop_ids[:5],
            "is_booking_flow": data.get("isBookingFlow") is True,
        })
        if len(store_names) == 1:
            followup["store_name"] = store_names[0]
        if len(shop_ids) == 1:
            followup["shop_id"] = shop_ids[0]
        return summary, followup

    if template == "datepick":
        dates = data.get("dates") if isinstance(data.get("dates"), list) else []
        date_candidates = [str(item.get("date") or "").strip() for item in dates if isinstance(item, dict) and str(item.get("date") or "").strip()]
        first_times: list[int] = []
        if dates and isinstance(dates[0], dict) and isinstance(dates[0].get("availableTimes"), list):
            first_times = [int(t) for t in dates[0]["availableTimes"] if str(t).isdigit()]
        summary = (
            f"최근 일정 후보: {date_candidates[0]} 포함 {len(date_candidates)}일"
            if date_candidates else assistant_response
        )
        followup.update({
            "followup_type": "schedule_options",
            "date_candidates": date_candidates[:10],
            "first_available_times": first_times[:10],
            "shop_id": state.commerce_state.store.shop_id,
            "store_name": state.commerce_state.store.shop_name,
            "goods_no": state.commerce_state.product.goods_no,
            "product_name": state.commerce_state.product.product_name,
        })
        return summary, followup

    if template == "voucher":
        vouchers = data.get("vouchers") if isinstance(data.get("vouchers"), list) else []
        meta_list = metadata if isinstance(metadata, list) else []
        voucher_names = [str(item.get("nameVoucher") or "").strip() for item in vouchers if isinstance(item, dict)]
        coupon_ids = [
            str(item.get("couponId") or "").strip()
            for item in meta_list
            if isinstance(item, dict) and str(item.get("couponId") or "").strip()
        ]
        summary = f"최근 쿠폰 조회: {', '.join(voucher_names[:2])}" if voucher_names else assistant_response
        followup.update({
            "followup_type": "coupon_list",
            "voucher_names": voucher_names[:5],
            "coupon_ids": coupon_ids[:5],
        })
        return summary, followup

    if template == "listCar":
        cars = data.get("listCar") if isinstance(data.get("listCar"), list) else []
        meta_list = metadata if isinstance(metadata, list) else []
        car_numbers = [str(item.get("licensePlate") or "").strip() for item in cars if isinstance(item, dict)]
        car_infos = [str(item.get("info") or item.get("description") or "").strip() for item in cars if isinstance(item, dict)]
        first_meta = meta_list[0] if meta_list and isinstance(meta_list[0], dict) else {}
        summary = f"최근 차량 조회: {', '.join(car_numbers[:2])}" if car_numbers else assistant_response
        followup.update({
            "followup_type": "vehicle_list",
            "car_numbers": car_numbers[:5],
            "car_infos": car_infos[:5],
            "car_no": first_meta.get("carNo") or first_meta.get("car_no"),
            "car_model": first_meta.get("carModelDet") or first_meta.get("car_model_det") or first_meta.get("carName"),
            "tire_size": first_meta.get("tireSize") or first_meta.get("tire_size_fr"),
        })
        return summary, followup

    if template == "preOrder":
        order_info = data.get("orderInfo") if isinstance(data.get("orderInfo"), dict) else {}
        meta_dict = metadata if isinstance(metadata, dict) else {}
        product = str(order_info.get("product") or "").strip()
        quantity = order_info.get("quantity")
        store_name = str(order_info.get("storeName") or "").strip()
        booking = str(order_info.get("bookingDateTime") or "").strip()
        summary_parts = [part for part in [product, f"{quantity}개" if quantity else "", store_name, booking] if part]
        summary = f"최근 주문 초안: {' / '.join(summary_parts)}" if summary_parts else assistant_response
        followup.update({
            "followup_type": "preorder",
            "product_name": product,
            "ord_qty": quantity,
            "store_name": store_name,
            "shop_id": meta_dict.get("shopId"),
            "goods_no": meta_dict.get("goodsId"),
            "booking_datetime": booking,
            "payment_amount": order_info.get("paymentAmount"),
        })
        return summary, followup

    if template == "quickReply" and isinstance(metadata, dict):
        if metadata.get("source") == "llm_first_escalation_confirmation":
            target = str(metadata.get("escalationTarget") or "qna").strip()
            followup.update({
                "followup_type": "escalation_confirmation",
                "pending_escalation_target": target,
            })
            return assistant_response, followup
        if response_shape_key == "metric_comparison_summary":
            compared_names = metadata.get("productNames") or []
            compare_metric = str(metadata.get("compareMetric") or metadata.get("compare_metric") or "detail")
            summary = (
                f"최근 비교 상품: {', '.join(compared_names[:2])} / 비교 기준: {compare_metric}"
                if compared_names else assistant_response
            )
            followup.update({
                "followup_type": "product_comparison",
                "product_names": compared_names[:5],
                "requested_product_names": metadata.get("requestedProductNames"),
                "resolved_products": metadata.get("resolvedProducts"),
                "compare_metric": compare_metric,
            })
            return summary, followup
        summary = assistant_response
        followup.update({
            "followup_type": "quick_reply",
        })
        return summary, followup

    if assistant_response:
        followup["followup_type"] = "generic_response"
        return assistant_response, followup
    return None, None


def _finalize_followup_state(state: ConversationState, bundle: FactBundle) -> ConversationState:
    event = bundle.templates[-1] if bundle.templates else None
    summary, last_facts_patch = _template_followup_context(event, state, bundle)
    if summary or last_facts_patch:
        return _remember_followup_context(
            state,
            conversation_summary=summary,
            last_facts_patch=last_facts_patch,
        )
    if bundle.tool_calls:
        return _remember_followup_context(
            state,
            conversation_summary=f"최근 처리 흐름: {', '.join(call.tool_name for call in bundle.tool_calls[:3])}",
            last_facts_patch={
                "followup_type": "tool_only",
                "tool_names": [call.tool_name for call in bundle.tool_calls],
            },
        )
    return state


class AFExecutor:
    async def execute(self, *, user_text: str, state: ConversationState, planner: PlannerDecision) -> FactBundle:
        bundle = FactBundle(planner=planner, state=state)
        working_state = state
        for selected in planner.selected_afs:
            if selected.af == AgentFlow.PRODUCT_RECOMMENDATION:
                working_state = await self._recommend(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.PRODUCT_DESCRIPTION:
                working_state = await self._description(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.PRICE:
                if selected.known_inputs.get("account_lookup") == "coupons":
                    working_state = await self._coupons(user_text, working_state, selected.known_inputs, bundle)
                else:
                    working_state = await self._price(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.STORE:
                working_state = await self._store(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.INVENTORY:
                working_state = await self._inventory(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.QUICK_SHOPPING:
                working_state = await self._quick_shopping(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.FAQ:
                if selected.known_inputs.get("account_lookup") == "warranties":
                    working_state = await self._warranties(user_text, working_state, selected.known_inputs, bundle)
                else:
                    working_state = await self._faq(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.ORDER_DELIVERY:
                working_state = await self._account_order_delivery(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.PRODUCT_COMPATIBILITY:
                working_state = await self._compatibility(user_text, working_state, selected.known_inputs, bundle)
            elif selected.af == AgentFlow.FALLBACK_ESCALATION:
                working_state = await self._fallback_escalation(user_text, working_state, selected.known_inputs, bundle)
        working_state = _finalize_followup_state(working_state, bundle)
        bundle.state = working_state
        bundle.facts["commerce_state"] = working_state.commerce_state.model_dump(exclude_none=True)
        return bundle

    async def _call(
        self,
        bundle: FactBundle,
        af: AgentFlow,
        tool_name: str,
        args: dict[str, Any],
        *,
        allow_side_effect: bool = False,
    ) -> Any:
        try:
            result = await asyncio.to_thread(invoke_tool, tool_name, args, af=af, allow_side_effect=allow_side_effect)
            bundle.tool_calls.append(ToolCallRecord(af=af, tool_name=tool_name, args=args, result=result))
            bundle.facts[tool_name] = result
            return result
        except PermissionError as exc:
            bundle.tool_calls.append(ToolCallRecord(af=af, tool_name=tool_name, args=args, blocked=True, reason=str(exc)))
            return None
        except Exception as exc:
            logger.warning("[LLM_FIRST_EXECUTOR] tool failed: %s", tool_name, exc_info=True)
            result = {"status": "error", "message": str(exc)}
            bundle.tool_calls.append(ToolCallRecord(af=af, tool_name=tool_name, args=args, result=result))
            return result

    async def _resolve_product(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> tuple[ConversationState, str | None]:
        goods_no = known.get("goods_no") or state.commerce_state.product.goods_no
        if goods_no:
            return state, str(goods_no)
        keyword = known.get("product_name")
        if not keyword and not known.get("tire_size"):
            bundle.missing_inputs.append("product")
            return state, None
        result = await self._call(bundle, AgentFlow.PRODUCT_DESCRIPTION, "search_product_tool", {
            "keyword": keyword,
            "size": known.get("tire_size"),
            "limit": 5,
        })
        item = _first_item(_success_payload(result))
        if not item:
            bundle.missing_inputs.append("product_selection")
            return state, None
        goods_no = item.get("goods_no") or item.get("goodsNo")
        product_name = item.get("goods_nm") or item.get("goodsNm") or item.get("title")
        next_state = apply_state_rules(
            state,
            product_patch={
                "goods_no": goods_no,
                "product_name": product_name,
                "tire_size": known.get("tire_size"),
            },
        )
        return next_state, str(goods_no) if goods_no else None

    async def _recommend(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        if (
            len([name for name in known.get("product_names") or [] if str(name).strip()]) >= 2
            and _is_comparison_request(user_text)
            and not _is_recommendation_request(user_text)
        ):
            return await self._description(user_text, state, known, bundle)

        if known.get("recommendation_source") == "best_seller":
            args: dict[str, Any] = {"limit": int(known.get("limit") or 5)}
            if known.get("vehicle_query") or known.get("car_model"):
                args["vehicle_query"] = known.get("vehicle_query") or known.get("car_model")
            if known.get("months"):
                args["months"] = int(known["months"])
            if known.get("from_date") and known.get("to_date"):
                args["from_date"] = known["from_date"]
                args["to_date"] = known["to_date"]
            result = await self._call(bundle, AgentFlow.PRODUCT_RECOMMENDATION, "get_best_selling_products_tool", args)
            exclusions = _current_product_exclusions(state, known) if known.get("alternative_target") == "product" else {"goods_ids": set(), "names": set()}
            _append_template(
                bundle,
                build_product_template(
                    result,
                    "인기 상품을 확인해 주세요.",
                    is_booking_flow=True,
                    exclude_goods_ids=exclusions["goods_ids"],
                    exclude_product_names=exclusions["names"],
                ),
            )
            return state

        tire_size = known.get("tire_size") or state.commerce_state.product.tire_size
        recommendation_type = known.get("recommendation_type")
        if recommendation_type in (None, "", "none"):
            recommendation_type = "tstation"
        args = {
            "rcmd_type": recommendation_type,
            "limit": min(max(int(known.get("limit") or 3), 1), 10),
        }
        optional_keys = (
            "brand_cd",
            "car_lnc_cd",
            "vehicle_type",
            "season_nm",
            "sort_by",
            "min_price",
            "max_price",
        )
        if tire_size:
            args["tire_size"] = tire_size
        for key in optional_keys:
            value = known.get(key)
            if value not in (None, "", "none"):
                args[key] = value
        if "vehicle_type" not in args:
            inferred_vehicle_type = _infer_vehicle_type_from_known(known, user_text)
            if inferred_vehicle_type:
                args["vehicle_type"] = inferred_vehicle_type
        result = await self._call(bundle, AgentFlow.PRODUCT_RECOMMENDATION, "get_products_recommendations_tool", args)
        exclusions = _current_product_exclusions(state, known) if known.get("alternative_target") == "product" else {"goods_ids": set(), "names": set()}
        _append_template(
            bundle,
            build_product_template(
                result,
                "추천 상품을 확인해 주세요.",
                is_booking_flow=True,
                exclude_goods_ids=exclusions["goods_ids"],
                exclude_product_names=exclusions["names"],
            ),
        )
        return apply_state_rules(state, product_patch={"tire_size": tire_size} if tire_size else None)

    async def _description(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        if known.get("benefit_lookup") not in (None, "", "none"):
            return await self._benefit_lookup(user_text, state, known, bundle)
        if _is_recommendation_request(user_text) and not _is_comparison_request(user_text):
            recommendation_known = {
                key: value
                for key, value in known.items()
                if key not in {"product_names", "compare_metric"}
            }
            recommendation_known.setdefault("recommendation_type", "tstation")
            return await self._recommend(user_text, state, recommendation_known, bundle)

        product_names = [str(name).strip() for name in known.get("product_names") or [] if str(name).strip()]
        if len(product_names) >= 2:
            rows_by_name: dict[str, dict[str, Any] | None] = {}
            for name in product_names[:4]:
                result = await self._call(bundle, AgentFlow.PRODUCT_DESCRIPTION, "search_product_summary_tool", {
                    "keyword": name,
                    "limit": 5,
                })
                rows_by_name[name] = _first_item(_success_payload(result))
            event = build_product_comparison_template(
                rows_by_name,
                compare_metric=str(known.get("compare_metric") or "detail"),
            )
            _append_template(bundle, event)
            if event is None:
                bundle.missing_inputs.append("product_selection")
                return state
            return state
        next_state, goods_no = await self._resolve_product(user_text, state, known, bundle)
        if not goods_no:
            return next_state
        await self._call(bundle, AgentFlow.PRODUCT_DESCRIPTION, "get_product_description_tool", {"goods_no": goods_no})
        return next_state

    async def _benefit_lookup(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        lookup = str(known.get("benefit_lookup") or "").strip()
        query = str(known.get("benefit_query") or known.get("product_name") or user_text).strip()
        if lookup == "event_deal_list":
            result = await self._call(bundle, AgentFlow.PRODUCT_DESCRIPTION, "get_benefit_event_deal_list_tool", {"lang_cd": "ko"})
            _append_template(bundle, build_benefit_event_deal_template(result))
            return state
        if lookup == "event_applicable_products" and known.get("evt_no_list"):
            result = await self._call(bundle, AgentFlow.PRODUCT_DESCRIPTION, "get_event_applicable_products_tool", {
                "evt_no_list": known["evt_no_list"],
            })
            _append_template(bundle, build_event_applicable_products_template(result))
            return state
        if not query:
            bundle.missing_inputs.append("benefit_query")
            return state
        result = await self._call(bundle, AgentFlow.PRODUCT_DESCRIPTION, "search_benefit_applicable_products_tool", {
            "query": query,
            "lang_cd": "ko",
        })
        _append_template(bundle, build_benefit_applicable_products_template(result))
        return state

    async def _price(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        next_state, goods_no = await self._resolve_product(user_text, state, known, bundle)
        if not goods_no:
            return next_state
        result = await self._call(bundle, AgentFlow.PRICE, "get_final_price_tool", {"goods_no": goods_no})
        data = result.get("data", {}) if isinstance(result, dict) else {}
        final_price = data.get("cheapest_final_prc") or data.get("final_prc") or data.get("extra_fvr_sale_prc") or data.get("sale_prc")
        return apply_state_rules(next_state, price_patch={"final_price": final_price, "source": "get_final_price_tool"})

    async def _coupons(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        result = await self._call(bundle, AgentFlow.PRICE, "get_my_coupons_tool", {"lang_cd": "ko"})
        _append_template(bundle, build_voucher_template(result, "보유 쿠폰 목록을 확인해 주세요."))
        return state

    async def _account_order_delivery(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        lookup = known.get("account_lookup")
        if lookup == "orders":
            await self._call(bundle, AgentFlow.ORDER_DELIVERY, "get_orders_of_user_tool", {})
        elif lookup == "maintenance_history":
            await self._call(bundle, AgentFlow.ORDER_DELIVERY, "get_maintenance_history_tool", {"limit": 5})
        else:
            await self._call(bundle, AgentFlow.ORDER_DELIVERY, "get_my_reservations_tool", {"sct_cd": "all"})
        return state

    async def _store(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        if known.get("store_lookup") == "favorite_stores":
            result = await self._call(bundle, AgentFlow.STORE, "get_favorite_stores_tool", {})
            event = build_location_template(
                result,
                "단골매장이에요. 원하시는 매장을 선택해 주세요.",
                is_booking_flow=bool(state.commerce_state.product.goods_no and state.commerce_state.quantity),
            )
            _append_template(bundle, event or _favorite_store_empty_event())
            return state

        user_xpos = known.get("user_xpos")
        user_ypos = known.get("user_ypos")
        has_coords = user_xpos not in (None, "") and user_ypos not in (None, "")
        raw_query = known.get("region") or known.get("store_name") or (None if has_coords else state.commerce_state.store.region)
        query = _store_search_query(raw_query)
        if not query and not has_coords:
            bundle.missing_inputs.append("region_or_store")
            return state
        search_args: dict[str, Any] = {"limit": 10}
        store_attribute = str(known.get("store_attribute") or "").strip()
        resolved_store_filters = resolve_store_search_filters(store_attribute)
        schedule_search_filters = resolve_store_schedule_search(user_text, known)
        if resolved_store_filters is not None:
            search_args.update(resolved_store_filters.to_tool_args())
        if schedule_search_filters is not None:
            search_args.update(schedule_search_filters)
        if query:
            search_args["place_query"] = str(query)
        else:
            search_args["xpos"] = float(user_xpos)
            search_args["ypos"] = float(user_ypos)
        tool_name = "search_stores_complex_tool" if schedule_search_filters is not None else "search_stores_tool"
        result = await self._call(bundle, AgentFlow.STORE, tool_name, search_args)
        if query and _is_domestic_region_gate_blocked(result):
            _append_template(bundle, _unsupported_region_event(query))
            return state
        assistant_response = "매장 후보를 확인해 주세요."
        if store_attribute and resolved_store_filters is None:
            assistant_response = (
                f"조회된 매장 기본정보에는 {store_attribute} 여부가 포함되어 있지 않아요. "
                "아래 매장은 지역 기준 후보이며, 방문 전 매장에 직접 확인해 주세요."
            )
        elif store_attribute:
            assistant_response = f"{store_attribute} 조건에 맞는 매장 후보를 확인해 주세요."
        is_booking_flow = bool(
            (known.get("goods_no") or state.commerce_state.product.goods_no)
            and (known.get("ord_qty") or state.commerce_state.quantity)
        )
        exclusions = _current_store_exclusions(state, known) if known.get("alternative_target") == "store" else {"shop_ids": set(), "names": set()}
        _append_template(bundle, build_location_template(
            result,
            assistant_response,
            is_booking_flow=is_booking_flow,
            exclude_shop_ids=exclusions["shop_ids"],
            exclude_store_names=exclusions["names"],
        ))
        return apply_state_rules(state, store_patch={"region": str(raw_query)} if raw_query else None)

    async def _inventory(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        next_state, goods_no = await self._resolve_product(user_text, state, known, bundle)
        qty = known.get("ord_qty") or next_state.commerce_state.quantity
        user_xpos = known.get("user_xpos")
        user_ypos = known.get("user_ypos")
        has_coords = user_xpos not in (None, "") and user_ypos not in (None, "")
        region = known.get("region") or (None if has_coords else next_state.commerce_state.store.region)
        shop_id = known.get("shop_id") or next_state.commerce_state.store.shop_id
        if not goods_no:
            bundle.missing_inputs.append("goods_no")
            return next_state
        if not qty:
            bundle.missing_inputs.append("ord_qty")
            _append_template(bundle, _quantity_quickreply_event())
            return next_state
        if not (region or shop_id or has_coords):
            bundle.missing_inputs.append("region_or_store")
            return apply_state_rules(next_state, quantity=int(qty))
        args = {"goods_no": goods_no, "ord_qty": int(qty), "region_code": region, "store_nm": known.get("store_name")}
        if has_coords and not (region or shop_id):
            args["user_xpos"] = float(user_xpos)
            args["user_ypos"] = float(user_ypos)
        result = await self._call(bundle, AgentFlow.INVENTORY, "transaction_store_preview_tool", args)
        if region and _is_domestic_region_gate_blocked(result):
            _append_template(bundle, _unsupported_region_event(region))
            return apply_state_rules(next_state, quantity=int(qty))
        exclusions = _current_store_exclusions(state, known) if known.get("alternative_target") == "store" else {"shop_ids": set(), "names": set()}
        _append_template(
            bundle,
            build_location_template(
                result,
                "장착 가능한 후보 매장을 확인해 주세요.",
                is_booking_flow=True,
                exclude_shop_ids=exclusions["shop_ids"],
                exclude_store_names=exclusions["names"],
            ),
        )
        return apply_state_rules(next_state, quantity=int(qty), store_patch={"region": region})

    async def _quick_shopping(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        next_state, goods_no = await self._resolve_product(user_text, state, known, bundle)
        qty = known.get("ord_qty") or next_state.commerce_state.quantity
        if not goods_no:
            bundle.missing_inputs.append("product")
            return next_state
        if not qty:
            bundle.missing_inputs.append("quantity")
            _append_template(bundle, _quantity_quickreply_event())
            return next_state
        next_state = apply_state_rules(next_state, quantity=int(qty))
        confirmed_action = str(known.get("confirmed_action") or "").strip()
        if confirmed_action == "cart":
            cart_args: dict[str, Any] = {
                "goods_no": goods_no,
                "ord_qty": int(qty),
            }
            if known.get("car_lnc_cd"):
                cart_args["car_lnc_cd"] = str(known["car_lnc_cd"])
            await self._call(
                bundle,
                AgentFlow.QUICK_SHOPPING,
                "save_to_cart_tool",
                cart_args,
                allow_side_effect=True,
            )
            event = _mark_completion_event(
                legacy.build_template_from_tool_data(_tool_data_list(bundle), ""),
                source="llm_first_cart_complete",
                called_tool="save_to_cart_tool",
            )
            _append_template(bundle, event)
            if event is None:
                bundle.missing_inputs.append("cart_complete_template")
            return next_state
        store_patch = {
            "shop_id": known.get("shop_id"),
            "shop_name": known.get("store_name"),
            "region": known.get("region"),
        }
        schedule_patch = {
            "date": known.get("date"),
            "time": known.get("time"),
        }
        next_state = apply_state_rules(
            next_state,
            store_patch={k: v for k, v in store_patch.items() if v not in (None, "")},
            schedule_patch={k: v for k, v in schedule_patch.items() if v not in (None, "")},
        )
        commerce = next_state.commerce_state
        alternative_store_requested = known.get("alternative_target") == "store" or _alternative_target(user_text) == "store"
        user_xpos = known.get("user_xpos")
        user_ypos = known.get("user_ypos")
        has_coords = user_xpos not in (None, "") and user_ypos not in (None, "")
        effective_region = commerce.store.region
        effective_store_name = commerce.store.shop_name
        if alternative_store_requested:
            effective_store_name = None
        if has_coords:
            if not known.get("region"):
                effective_region = None
            if not known.get("store_name"):
                effective_store_name = None
        if not ((commerce.store.shop_id and not alternative_store_requested) or effective_region or effective_store_name or has_coords):
            bundle.missing_inputs.append("store_or_region")
            return next_state
        if alternative_store_requested or not commerce.store.shop_id:
            preview_args: dict[str, Any] = {
                "goods_no": goods_no,
                "ord_qty": int(qty),
                "region_code": effective_region,
                "store_nm": effective_store_name,
            }
            if has_coords and not (effective_region or effective_store_name):
                preview_args["user_xpos"] = float(user_xpos)
                preview_args["user_ypos"] = float(user_ypos)
            result = await self._call(bundle, AgentFlow.INVENTORY, "transaction_store_preview_tool", preview_args)
            if effective_region and _is_domestic_region_gate_blocked(result):
                _append_template(bundle, _unsupported_region_event(effective_region))
                return next_state
            exclusions = _current_store_exclusions(state, known) if alternative_store_requested else {"shop_ids": set(), "names": set()}
            _append_template(
                bundle,
                build_location_template(
                    result,
                    "현재 선택된 매장을 제외한 후보 매장을 확인해 주세요." if alternative_store_requested else "장착 가능한 후보 매장을 확인해 주세요.",
                    is_booking_flow=True,
                    exclude_shop_ids=exclusions["shop_ids"],
                    exclude_store_names=exclusions["names"],
                ),
            )
            bundle.missing_inputs.append("store")
            return next_state
        if not (commerce.schedule.date and commerce.schedule.time):
            schedule_mode = str(known.get("schedule_mode") or known.get("inventory_mode") or "general").strip() or "general"
            result = await self._call(bundle, AgentFlow.QUICK_SHOPPING, "get_store_schedule_tool", {
                "shop_id": commerce.store.shop_id,
                "mode": schedule_mode,
            })
            _append_template(bundle, build_datepick_template(result, "가능한 일정을 선택해 주세요."))
            bundle.missing_inputs.append("schedule")
            return next_state
        if not next_state.commerce_state.price.final_price:
            next_state = await self._price(user_text, next_state, {"goods_no": goods_no}, bundle)
        if confirmed_action == "order":
            rsv_date = _digits_date(known.get("requested_cal_day") or known.get("date") or commerce.schedule.date)
            rsv_hour = _hour(known.get("rsv_hour") or known.get("time") or commerce.schedule.time)
            if not (rsv_date and rsv_hour):
                bundle.missing_inputs.append("schedule")
                return next_state
            order_args: dict[str, Any] = {
                "goods_no": goods_no,
                "ord_qty": int(qty),
                "shop_id": commerce.store.shop_id,
                "rsv_date": rsv_date,
                "rsv_hour": rsv_hour,
            }
            if known.get("car_lnc_cd"):
                order_args["car_lnc_cd"] = str(known["car_lnc_cd"])
            await self._call(
                bundle,
                AgentFlow.QUICK_SHOPPING,
                "quick_order_tool",
                order_args,
                allow_side_effect=True,
            )
            event = _mark_completion_event(
                legacy.build_template_from_tool_data(_tool_data_list(bundle), ""),
                source="llm_first_order_complete",
                called_tool="quick_order_tool",
            )
            _append_template(bundle, event)
            if event is None:
                bundle.missing_inputs.append("order_complete_template")
            return next_state
        preorder = build_preorder_template(next_state, "주문 초안을 확인해 주세요. 실제 주문 실행은 아직 하지 않았습니다.")
        if preorder:
            bundle.templates.append(preorder)
        else:
            bundle.missing_inputs.append("preorder_required_inputs")
        return next_state

    async def _faq(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        await self._call(bundle, AgentFlow.FAQ, "search_faq_hybrid_tool", {"query": user_text, "top_k": 5})
        return state

    async def _warranties(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        await self._call(bundle, AgentFlow.FAQ, "get_my_warranties_tool", {})
        return state

    async def _compatibility(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        car_no = str(known.get("car_no") or "").strip()
        owner_nm = str(known.get("owner_nm") or "").strip()
        car_model = str(known.get("car_model") or known.get("product_name") or "").strip()
        mbr_no = str(known.get("mbr_no") or "").strip()
        if car_no and owner_nm:
            result = await self._call(bundle, AgentFlow.PRODUCT_COMPATIBILITY, "get_user_vehicles_tool", {
                "car_no": car_no,
                "owner_nm": owner_nm,
            })
            _append_template(bundle, build_list_car_template(result, "차량 정보를 확인해 주세요."))
            return state
        if car_model and not (mbr_no and known.get("vehicle_recommendation")):
            await self._call(bundle, AgentFlow.PRODUCT_COMPATIBILITY, "search_car_model_groups_tool", {
                "keyword": car_model,
            })
            return state
        if mbr_no:
            result = await self._call(bundle, AgentFlow.PRODUCT_COMPATIBILITY, "get_my_cars_tool", {"mbr_no": mbr_no})
            if known.get("vehicle_recommendation"):
                rows = _items(_success_payload(result))
                selected = _match_registered_vehicle(rows, car_model) if car_model else None
                if selected is not None:
                    args = _vehicle_recommendation_args(selected, known)
                    if args is not None:
                        recommendation = await self._call(
                            bundle,
                            AgentFlow.PRODUCT_RECOMMENDATION,
                            "get_products_recommendations_tool",
                            args,
                        )
                        _append_template(
                            bundle,
                            build_product_template(
                                recommendation,
                                "내 차에 맞는 추천 상품을 확인해 주세요.",
                                is_booking_flow=True,
                            ),
                        )
                        tire_size = args.get("tire_size") or normalize_tire_size(str(selected.get("tire_size_fr") or ""))
                        return apply_state_rules(state, product_patch={"tire_size": tire_size} if tire_size else None)
                if car_model:
                    args = _vehicle_type_recommendation_args(known, user_text)
                    if args is not None:
                        recommendation = await self._call(
                            bundle,
                            AgentFlow.PRODUCT_RECOMMENDATION,
                            "get_products_recommendations_tool",
                            args,
                        )
                        _append_template(
                            bundle,
                            build_product_template(
                                recommendation,
                                "차량 유형 기준 추천 상품을 확인해 주세요.",
                                is_booking_flow=True,
                            ),
                        )
                        return state
                _append_template(
                    bundle,
                    build_list_car_template(
                        result,
                        "내 차에 맞는 타이어를 추천하려면 차량을 먼저 선택해 주세요.",
                        source_intent="vehicle_resolved_recommendation",
                    ),
                )
                return state
            _append_template(bundle, build_list_car_template(result, "등록된 차량을 확인해 주세요."))
            return state
        bundle.missing_inputs.append("vehicle")
        return state

    async def _fallback_escalation(self, user_text: str, state: ConversationState, known: dict[str, Any], bundle: FactBundle) -> ConversationState:
        target = str(known.get("escalation_target") or "qna").strip()
        confirmed_action = str(known.get("confirmed_action") or "").strip()
        if confirmed_action == "declined":
            _append_template(bundle, _escalation_declined_event())
            return _clear_pending_escalation(state)
        if confirmed_action != "escalation":
            _append_template(bundle, _escalation_confirmation_event(target))
            return state
        if target == "human":
            result = await self._call(
                bundle,
                AgentFlow.FALLBACK_ESCALATION,
                "escalate_tool",
                {
                    "mbr_no": known.get("mbr_no"),
                    "inq_type_cd": known.get("inq_type_cd"),
                    "msg_count": known.get("msg_count") or 0,
                    "summary": known.get("summary") or user_text,
                },
                allow_side_effect=True,
            )
            # escalate_tool has no dedicated FE card in the legacy contract —
            # a plain confirmation message is the correct, complete answer.
            _append_template(bundle, _escalation_completion_event(target, result))
        else:
            result = await self._call(
                bundle,
                AgentFlow.FALLBACK_ESCALATION,
                "transfer_to_qna_tool",
                {
                    "cnsl_clss_seq": known.get("cnsl_clss_seq") or "10019",
                    "inq_tit_nm": known.get("inq_tit_nm") or user_text[:100],
                    "ai_summary": known.get("ai_summary") or user_text[:400],
                    "is_mobile": bool(known.get("is_mobile")),
                },
                allow_side_effect=True,
            )
            # transfer_to_qna_tool has a dedicated qnaComplete FE card (inquiry
            # link + category + summary) in the legacy template contract —
            # reuse it instead of a bare text confirmation, same as order/cart.
            event = None
            if isinstance(result, dict) and result.get("status") != "error":
                event = _mark_completion_event(
                    legacy.build_template_from_tool_data(_tool_data_list(bundle), ""),
                    source="llm_first_qna_complete",
                    called_tool="transfer_to_qna_tool",
                )
            _append_template(bundle, event or _escalation_completion_event(target, result))
        return _clear_pending_escalation(state)
