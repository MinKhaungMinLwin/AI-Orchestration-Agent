from abc import ABC
from collections.abc import Callable
from typing import Any, TypeVar
import ast
import json
import logging
import re
import time

from langchain.messages import AIMessageChunk, AIMessage, ToolMessage
from langchain.agents import create_agent
from pydantic import BaseModel, TypeAdapter, ValidationError

from config.tracing import trace_span as _trace_span, truncate_for_trace as _truncate
from services.tstation.common.cta_urls import CTAUrls
from services.tstation.policies.discovery_intent_policy import normalize_tire_size
from services.tstation.policies.schedule_tool_gate import (
    build_blocked_schedule_event,
    decide_schedule_tool_gate,
)
from services.tstation.tool_summaries import summarize_tool


logger = logging.getLogger(__name__)


def _emit_tool_summary_span(
    config: dict | None,
    *,
    tool_name: str,
    tool_input: dict,
    tool_result: Any,
    tool_status: str,
    latency_ms: float | None = None,
) -> None:
    """Open a short-lived child span carrying a one-line summary of a tool call.

    The span is named ``🔧 <tool>: <summary>`` so the Langfuse trace tree shows
    the result inline (e.g. ``🔧 search_product_tool: 3 hits → G123``) without
    needing to expand the raw JSON output captured by the LangChain auto-span.

    Silently no-ops when tracing is disabled or when the trace context is
    missing — never raises into the agent stream.
    """
    cfgable = (config or {}).get("configurable", {}) if isinstance(config, dict) else {}
    trace_id = cfgable.get("tstation_trace_id")
    parent_span_id = cfgable.get("tstation_parent_span_id")
    if not trace_id:
        return
    try:
        summary = summarize_tool(tool_name, tool_result)
    except Exception as exc:  # never let summary formatting break the agent loop
        logger.debug("[TRACE] tool summary failed for %s: %s", tool_name, exc)
        summary = f"status={tool_status}"
    http_status = tool_result.get("http_status") if isinstance(tool_result, dict) else None
    reason = tool_result.get("reason") if isinstance(tool_result, dict) else None
    message = tool_result.get("message") if isinstance(tool_result, dict) else None
    span_name = f"🔧 {tool_name}: {summary}"
    with _trace_span(
        span_name,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        input=tool_input,
    ) as _ts:
        _ts.update(output=_truncate({
            "summary": summary,
            "tool_name": tool_name,
            "tool_status": tool_status,
            "http_status": http_status,
            "reason": reason,
            "message": message,
            "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
        }))

T = TypeVar("T")


# Keys stripped from the SSE `tool` event's `output` payload before it reaches
# the FE / dev tools. These are *internal-only* directives meant for the LLM's
# deterministic guard logic (e.g. `transaction_store_preview_tool` instructing
# the agent to STOP at the location card). The LLM still sees them in the
# original `ToolMessage` content held by LangGraph state; only the SSE-visible
# copy is sanitized so analysts / browser dev tools / log streams never expose
# the raw guard text.
_SSE_TOOL_OUTPUT_STRIPPED_KEYS: frozenset[str] = frozenset({"instruction_to_agent"})
_CAR_NO_RE = re.compile(r"\d{2,3}\s?[가-힣]\s?\d{4}")
_CAR_NO_OWNER_RE = re.compile(
    r"(?P<car_no>\d{2,3}\s?[가-힣]\s?\d{4})(?:\s*[,，、/|]+\s*|\s+)(?P<owner_nm>[가-힣]{2,4})"
)
_REGISTERED_VEHICLE_RECOMMEND_RE = re.compile(r"(타이어|상품).*(추천|맞|보여|찾|알려)|추천.*(타이어|상품)")
_POSSESSIVE_VEHICLE_RE = re.compile(r"(내\s*차|내차|내\s+[0-9A-Za-z가-힣])")
_POSSESSIVE_VEHICLE_MODEL_RE = re.compile(
    r"(?:내\s*차|내차|내\s*차량|내차량|내)\s+"
    r"(?P<model>[0-9A-Za-z가-힣][0-9A-Za-z가-힣\s._-]{1,24}?)(?="
    r"\s*(?:인데|인데요|이야|야|은|는|이|가|에|에는|으로|로|타이어|추천|하중|적재|짐|호환|맞|가능|$)"
    r")",
    re.IGNORECASE,
)
_VEHICLE_LIST_REQUEST_RE = re.compile(
    r"내\s*차\s*목록|내차\s*목록|내차목록|내\s*차량|내차량|보유\s*차량|보유차량|"
    r"보유차량\s*확인|내\s*등록차|등록차량|등록차|내\s*차\s*보여|내차\s*보여|내차보여|"
    r"내\s*차\s*(?:사이즈|규격|로\s*다시)|내차\s*(?:사이즈|규격|로\s*다시)",
    re.IGNORECASE,
)
_POSSESSIVE_VEHICLE_MODEL_STOPWORDS = {
    "내",
    "내차",
    "차",
    "차량",
    "타이어",
    "상품",
    "추천",
    "맞는",
    "하중",
    "적재",
    "짐",
    "호환",
    "가능",
}
_CONTRACT_REQUIRED_LISTCAR_RESPONSE_SHAPE_KEYS = frozenset({
    "vehicle_information",
    "vehicle_based_recommendation_refinement",
    "vehicle_resolved_recommendation",
})


def _normalize_vehicle_key(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def _extract_tool_rows(tool_result: Any) -> list[dict]:
    data = tool_result.get("data") if isinstance(tool_result, dict) else tool_result
    if isinstance(data, dict):
        rows = data.get("items") if "items" in data else [data]
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def _latest_user_text(messages: list[dict]) -> str:
    try:
        from services.tstation.template_mapper import current_user_text

        context_text = current_user_text.get()
        if context_text:
            for line in reversed(context_text.splitlines()):
                stripped = line.strip()
                if stripped:
                    return stripped
    except Exception:
        pass
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = str(msg.get("content") or "")
            if "# Respond in Korean language" in content:
                content = content.split("# Respond in Korean language", 1)[-1]
            return content.strip()
    return ""


def _messages_include_resolved_product_tool_fact(messages: list[dict]) -> bool:
    """True when a prior Discovery handoff already supplied a concrete goods_no."""
    for msg in reversed(messages[-8:]):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = str(msg.get("content") or "")
        if "search_product_tool" in content and re.search(r"\bG\d{9,}\b", content):
            return True
    return False


def _tool_entries_from_previous_agent_facts(messages: list[dict] | None) -> list[dict]:
    if not messages:
        return []
    for msg in reversed(messages[-8:]):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = str(msg.get("content") or "")
        marker = "[Previous agent tool facts]"
        if marker not in content:
            continue
        payload = content.split(marker, 1)[-1].strip()
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except Exception:
            logger.debug("[TOOL_FACTS] failed to parse previous agent tool facts")
            continue
        if isinstance(data, list):
            return [entry for entry in data if isinstance(entry, dict)]
    return []


def _recent_context_text(messages: list[dict], *, limit: int = 8) -> str:
    lines: list[str] = []
    for msg in messages[-limit:]:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        if "# Respond in Korean language" in content:
            content = content.split("# Respond in Korean language", 1)[-1].strip()
        lines.append(f"{role}: {content[:500]}")
    return "\n".join(lines)


def _is_explicit_vehicle_list_request(messages: list[dict]) -> bool:
    return bool(_VEHICLE_LIST_REQUEST_RE.search(_latest_user_text(messages)))


def _should_skip_support_search_product_fast_path(agent_name: str, tool_name: str) -> bool:
    return tool_name == "search_product_tool" and "support" in str(agent_name or "").lower()


def _product_name_for_warranty_result(accumulated_tool_data: list[dict], goods_no: str | None) -> str:
    if not goods_no:
        return "해당 상품"
    for entry in reversed(accumulated_tool_data):
        if entry.get("tool") != "search_product_tool":
            continue
        for row in _extract_tool_rows(entry.get("data")):
            if str(row.get("goods_no") or "").strip() == goods_no:
                name = str(row.get("goods_nm") or "").strip()
                if name:
                    return name
    return "해당 상품"


def _build_product_warranty_quickreply_event(
    tool_result: Any,
    accumulated_tool_data: list[dict],
) -> dict | None:
    if not isinstance(tool_result, dict) or tool_result.get("status") != "success":
        return None
    data = tool_result.get("data")
    if not isinstance(data, dict):
        return None
    goods_no = str(data.get("goods_no") or "").strip() or None
    ptrn_cd = str(data.get("ptrn_cd") or "").strip()
    warranties = data.get("warranties")
    if warranties is None:
        return None
    product_name = _product_name_for_warranty_result(accumulated_tool_data, goods_no)
    lines: list[str] = []
    if isinstance(warranties, list) and warranties:
        names: list[str] = []
        for warranty in warranties:
            if not isinstance(warranty, dict):
                continue
            name = str(warranty.get("wrt_nm") or "").strip()
            if name and name not in names:
                names.append(name)
        if names:
            lines.append(f"{product_name}에 적용 가능한 워런티는 다음과 같아요.")
            lines.append("")
            lines.extend(f"- {name}" for name in names)
            lines.append("")
            lines.append("보유 여부와 가입 상태는 아래 '나의 워런티 확인'에서 확인해 주세요.")
        else:
            return None
    elif ptrn_cd:
        lines.append(f"{product_name}은 현재 워런티 적용 대상이 아닌 것으로 확인돼요.")
        lines.append("정확한 보유 여부는 아래 '나의 워런티 확인'에서 확인해 주세요.")
    else:
        lines.append("해당 상품 정보를 찾지 못했어요. 정확한 상품명으로 다시 확인해 주세요.")

    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": [
                {"label": "나의 워런티 확인", "url": CTAUrls.WARRANTY_MAIN, "domain": "SUPPORT"},
                {"label": "1:1 문의하기", "domain": "SUPPORT"},
            ],
            "predictedDomains": ["SUPPORT"],
        },
    }


def _vehicle_owner_lookup_args_after_registered_mismatch(
    tool_name: str,
    tool_result: Any,
    messages: list[dict],
) -> dict | None:
    if tool_name != "get_my_cars_tool":
        return None
    if not isinstance(tool_result, dict) or tool_result.get("status") != "success":
        return None
    user_text = _latest_user_text(messages)
    match = _CAR_NO_OWNER_RE.search(user_text or "")
    if not match:
        return None
    rows = _extract_tool_rows(tool_result)
    requested_plate = _normalize_vehicle_key(match.group("car_no"))
    if any(_normalize_vehicle_key(row.get("car_no")) == requested_plate for row in rows):
        return None
    return {
        "car_no": re.sub(r"\s+", "", match.group("car_no")),
        "owner_nm": match.group("owner_nm").strip(),
    }


def _recommendation_type_from_vehicle_text(user_text: str) -> str:
    text = user_text or ""
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


def _recommendation_season_from_vehicle_text(user_text: str) -> str | None:
    text = user_text or ""
    if re.search(r"올웨더|전천후|all[-\s]?weather", text, re.IGNORECASE):
        return "올웨더"
    if re.search(r"사계절|올시즌|all[-\s]?season", text, re.IGNORECASE):
        return "사계절"
    if re.search(r"겨울|윈터|눈길", text, re.IGNORECASE):
        return "겨울"
    if re.search(r"여름|썸머", text, re.IGNORECASE):
        return "여름"
    return None


def _owner_lookup_vehicle_recommendation_args(owner_tool_result: Any, messages: list[dict]) -> dict | None:
    if not isinstance(owner_tool_result, dict) or owner_tool_result.get("status") != "success":
        return None
    rows = _extract_tool_rows(owner_tool_result)
    if len(rows) != 1:
        return None
    row = rows[0]
    car_lnc_cd = row.get("car_lnc_cd")
    tire_size = row.get("tire_size_fr") or row.get("tire_size_re")
    if not (car_lnc_cd or tire_size):
        return None
    latest_user_text = _latest_user_text(messages)
    args: dict[str, Any] = {
        "rcmd_type": _recommendation_type_from_vehicle_text(latest_user_text),
        "limit": 3,
        "brand_cd": "HK",
    }
    season_nm = _recommendation_season_from_vehicle_text(latest_user_text)
    if season_nm:
        args["season_nm"] = season_nm
    if car_lnc_cd:
        args["car_lnc_cd"] = car_lnc_cd
    else:
        args["tire_size"] = tire_size
    return args


def _owner_lookup_vehicle_display_name(row: dict) -> str:
    car_maker = str(row.get("car_maker") or "").strip()
    car_name = str(row.get("car_nm") or row.get("ver_opt_choc") or row.get("car_model_det") or "").strip()
    if car_maker and car_name and _normalize_vehicle_key(car_maker) not in _normalize_vehicle_key(car_name):
        return f"{car_maker} {car_name}"
    return car_name or car_maker or "조회된 차량"


def _build_owner_vehicle_lookup_event(tool_name: str, tool_result: Any, messages: list[dict]) -> dict | None:
    if tool_name != "get_user_vehicles_tool":
        return None
    if not isinstance(tool_result, dict) or tool_result.get("status") != "success":
        return None
    user_text = _latest_user_text(messages)
    if not _CAR_NO_OWNER_RE.search(user_text or ""):
        return None
    if _REGISTERED_VEHICLE_RECOMMEND_RE.search(user_text or ""):
        return None
    rows = _extract_tool_rows(tool_result)
    if len(rows) != 1:
        return None

    row = rows[0]
    vehicle_name = _owner_lookup_vehicle_display_name(row)
    front_size, rear_size = _registered_vehicle_tire_sizes(row)
    if front_size and rear_size and front_size != rear_size:
        size_text = f"전륜 {front_size}, 후륜 {rear_size}"
    else:
        size_text = front_size or rear_size
    if size_text:
        assistant_response = f"조회되었습니다. {vehicle_name} 차량의 타이어 사이즈는 {size_text}입니다."
    else:
        assistant_response = f"조회되었습니다. {vehicle_name} 차량 정보는 확인했지만 타이어 사이즈는 확인되지 않았어요."

    return {
        "type": "data",
        "template": "quickReply",
        "assistant_response_source": "code_owner_vehicle_lookup",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": [
                {"label": "다시 검색", "domain": "DISCOVERY"},
                {"label": "타이어 추천", "domain": "DISCOVERY"},
                {"label": "구매하기", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["DISCOVERY", "TRANSACTION"],
            "metadata": {
                "carNo": row.get("car_no"),
                "carLncCd": row.get("car_lnc_cd"),
                "carMaker": row.get("car_maker"),
                "carName": row.get("car_nm"),
                "carModelDet": row.get("car_model_det"),
                "tireSize": front_size,
                "tireSizeRe": rear_size,
            },
        },
    }


def _vehicle_aliases(row: dict) -> set[str]:
    aliases: set[str] = set()
    for key in ("car_nm", "car_model_det", "car_engine", "ver_opt_choc", "car_maker"):
        normalized = _normalize_vehicle_key(row.get(key))
        if len(normalized) >= 2:
            aliases.add(normalized)
    # Short model identifiers like GV70 / EV3 / K7 are often embedded at the
    # beginning of the full model/trim string. Add them as aliases so
    # "내 GV70" can resolve without requiring the full trim name.
    for key in ("car_nm", "car_model_det", "car_engine"):
        value = str(row.get(key) or "")
        for token in re.findall(r"[A-Za-z가-힣]*\d+[A-Za-z가-힣]*|[A-Za-z]{2,}|[가-힣]{2,}", value):
            normalized = _normalize_vehicle_key(token)
            if len(normalized) >= 2:
                aliases.add(normalized)
    maker = _normalize_vehicle_key(row.get("car_maker"))
    model = _normalize_vehicle_key(row.get("car_model_det") or row.get("car_nm"))
    if maker and model:
        aliases.add(f"{maker}{model}")
    return aliases


def _possessive_vehicle_model_mentions(user_text: str) -> list[str]:
    mentions: list[str] = []
    for match in _POSSESSIVE_VEHICLE_MODEL_RE.finditer(user_text or ""):
        raw = re.sub(r"\s+", " ", match.group("model") or "").strip(" ._-")
        normalized = _normalize_vehicle_key(raw)
        if len(normalized) < 2 or normalized in _POSSESSIVE_VEHICLE_MODEL_STOPWORDS:
            continue
        mentions.append(normalized)
    return mentions


def _has_registered_vehicle_model_match(rows: list[dict], requested_models: list[str]) -> bool:
    if not requested_models:
        return False
    for row in rows:
        aliases = _vehicle_aliases(row)
        for requested in requested_models:
            if any(alias and (requested in alias or alias in requested) for alias in aliases):
                return True
    return False


def _should_defer_listcar_for_possessive_model_mismatch(
    tool_name: str,
    tool_result: Any,
    messages: list[dict],
) -> bool:
    """Let the LLM answer using the named vehicle when it is not registered.

    For turns like "내 차 다마스인데 하중..." the registered-car lookup is only a
    first attempt to resolve a size. If none of the user's registered cars match
    the named model, stopping at listCar makes the user pick an unrelated car.
    """
    if tool_name not in {"get_my_cars_tool", "get_user_vehicles_tool"}:
        return False
    if not isinstance(tool_result, dict) or tool_result.get("status") != "success":
        return False
    rows = _extract_tool_rows(tool_result)
    if not rows:
        return False
    try:
        from services.tstation.template_mapper import current_discovery_response_decision

        decision = current_discovery_response_decision.get()
    except Exception:
        decision = None
    if decision is not None:
        decision_metadata = getattr(decision, "metadata", None) or {}
        template = getattr(decision, "template", None)
        template_value = getattr(template, "value", template)
        response_shape_key = str(decision_metadata.get("response_shape_key") or "").strip()
        flow_step = str(decision_metadata.get("flow_step") or "").strip()
        if (
            response_shape_key == "vehicle_resolved_recommendation"
            and str(template_value or "").strip() == "listCar"
            and flow_step == "select_vehicle"
        ):
            return False
        if (
            response_shape_key == "vehicle_based_recommendation_refinement"
            and len(rows) >= 2
            and str(template_value or "").strip() in {"", "listCar", "product"}
        ):
            return False
    if _is_explicit_vehicle_list_request(messages):
        return False
    user_text = _latest_user_text(messages)
    requested_models = _possessive_vehicle_model_mentions(user_text)
    if not requested_models:
        return False
    return not _has_registered_vehicle_model_match(rows, requested_models)


def _contract_requires_listcar_fast_path(tool_name: str, tool_result: Any) -> bool:
    if tool_name not in {"get_my_cars_tool", "get_user_vehicles_tool"}:
        return False
    if not isinstance(tool_result, dict) or tool_result.get("status") != "success":
        return False
    rows = _extract_tool_rows(tool_result)
    if not rows:
        return False
    try:
        from services.tstation.template_mapper import current_discovery_response_decision

        decision = current_discovery_response_decision.get()
    except Exception:
        decision = None
    if decision is None:
        return False
    decision_metadata = getattr(decision, "metadata", None) or {}
    template = getattr(decision, "template", None)
    template_value = str(getattr(template, "value", template) or "").strip()
    response_shape_key = str(decision_metadata.get("response_shape_key") or "").strip()
    return template_value == "listCar" or response_shape_key in _CONTRACT_REQUIRED_LISTCAR_RESPONSE_SHAPE_KEYS


def _resolve_registered_vehicle_match(tool_name: str, tool_result: Any, messages: list[dict]) -> dict | None:
    """Resolve a user-named registered vehicle to a unique registered-car row.

    Auto-selection is intentionally narrow:
      1. the current message contains an explicit license plate, or
      2. the current message uses a possessive vehicle expression ("내 GV70",
         "내차 GV70") and exactly one registered vehicle name matches.

    Plain model mentions like "GV70 타이어" must not auto-select a registered
    car, because they can be generic model inquiries.
    """
    if tool_name not in {"get_my_cars_tool", "get_user_vehicles_tool"}:
        return None
    if not isinstance(tool_result, dict) or tool_result.get("status") != "success":
        return None
    user_text = _latest_user_text(messages)
    if not user_text or not _REGISTERED_VEHICLE_RECOMMEND_RE.search(user_text):
        return None
    rows = _extract_tool_rows(tool_result)
    if not rows:
        return None

    normalized_user = _normalize_vehicle_key(user_text)
    requested_plates = {_normalize_vehicle_key(match) for match in _CAR_NO_RE.findall(user_text)}
    matched: list[dict] = []
    if requested_plates:
        matched = [row for row in rows if _normalize_vehicle_key(row.get("car_no")) in requested_plates]
    elif _POSSESSIVE_VEHICLE_RE.search(user_text):
        for row in rows:
            if any(alias and alias in normalized_user for alias in _vehicle_aliases(row)):
                matched.append(row)
    else:
        return None

    if len(matched) != 1:
        return None
    row = matched[0]
    tire_size = row.get("tire_size_fr") or row.get("tire_size_re")
    return row if tire_size else None


def _registered_vehicle_tire_sizes(row: dict) -> tuple[str | None, str | None]:
    front_size = normalize_tire_size(str(row.get("tire_size_fr") or ""))
    rear_size = normalize_tire_size(str(row.get("tire_size_re") or ""))
    return front_size, rear_size


def _is_staggered_registered_vehicle(row: dict) -> bool:
    front_size, rear_size = _registered_vehicle_tire_sizes(row)
    return bool(front_size and rear_size and front_size != rear_size)


def _registered_vehicle_slot_values(row: dict) -> dict[str, Any]:
    front_size, rear_size = _registered_vehicle_tire_sizes(row)
    slot_values: dict[str, Any] = {
        "car_model": row.get("car_nm") or row.get("ver_opt_choc") or row.get("car_model_det"),
        "car_no": row.get("car_no"),
        "car_lnc_cd": row.get("car_lnc_cd"),
        "mbr_car_reg_seq": row.get("mbr_car_unif_no"),
        "tire_size_front": front_size,
        "tire_size_rear": rear_size,
    }
    if front_size and (not rear_size or front_size == rear_size):
        slot_values["tire_size"] = front_size
    elif rear_size and not front_size:
        slot_values["tire_size"] = rear_size
    else:
        slot_values["tire_size"] = None
    return {key: value for key, value in slot_values.items() if value is not None or key == "tire_size"}


def _build_registered_vehicle_staggered_tire_event(row: dict) -> dict | None:
    front_size, rear_size = _registered_vehicle_tire_sizes(row)
    if not (front_size and rear_size and front_size != rear_size):
        return None

    car_name = str(row.get("car_nm") or row.get("ver_opt_choc") or row.get("car_model_det") or "선택하신 차량").strip()
    car_no = str(row.get("car_no") or "").strip()
    vehicle_label = f"**{car_name} ({car_no})**" if car_no else f"**{car_name}**"
    return {
        "type": "data",
        "template": "quickReply",
        "assistant_response_source": "code_registered_vehicle_staggered_tire_prompt",
        "data": {
            "assistantResponse": (
                f"{vehicle_label}의 규격은 전륜 **{front_size}**, 후륜 **{rear_size}**예요.\n\n"
                "앞/뒤 사이즈가 다릅니다. 어떤 사이즈 기준으로 검색할까요?"
            ),
            "quickReplies": [
                {"label": "앞바퀴사이즈", "domain": "DISCOVERY"},
                {"label": "뒷바퀴사이즈", "domain": "DISCOVERY"},
                {"label": "다른 사이즈 입력", "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
        },
    }


def _strip_keys_in_place(node: Any, keys: frozenset[str]) -> None:
    if isinstance(node, dict):
        for k in list(node.keys()):
            if k in keys:
                del node[k]
            else:
                _strip_keys_in_place(node[k], keys)
    elif isinstance(node, list):
        for item in node:
            _strip_keys_in_place(item, keys)


def _stock_preview_guard_context(messages: list[dict]) -> tuple[str, int] | None:
    """Return (goods_no, qty) when the current turn is an active stock flow."""
    joined = "\n".join(str(m.get("content") or "") for m in messages if isinstance(m, dict))
    last_user_text = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            last_user_text = str(msg.get("content") or "")
            break
    if re.search(r"영업|운영|전화|주소|휴무|서비스|몇\s*시", last_user_text):
        return None

    has_stock_context = (
        "진행 중인 요청: 재고 확인" in joined
        or "pending_intent=stock" in joined
        or "goal_type=store_with_stock" in joined
        or ("재고 확인" in joined and "상품번호" in joined)
    )
    has_stock_followup_text = (
        bool(re.search(r"재고|장착|당장|오늘|근처|주변|으로", last_user_text))
        or len(last_user_text.strip()) <= 20
    )
    if not has_stock_context or not has_stock_followup_text:
        return None

    goods_match = re.search(r"G\d{12}", joined)
    qty_match = re.search(r"(?:수량|ord_qty|quantity)\D{0,20}(\d+)", joined, re.IGNORECASE)
    if not goods_match or not qty_match:
        return None

    try:
        qty = int(qty_match.group(1))
    except ValueError:
        return None
    if qty < 1:
        return None
    return goods_match.group(0), qty


def _build_stock_preview_guard_args(
    accumulated_tool_data: list[dict],
    messages: list[dict],
) -> dict | None:
    if any(e.get("tool") == "transaction_store_preview_tool" for e in accumulated_tool_data):
        return None

    context = _stock_preview_guard_context(messages)
    if context is None:
        return None
    goods_no, qty = context

    store_entries = [
        e for e in accumulated_tool_data
        if e.get("tool") in {"search_stores_tool", "get_store_list_tool", "get_nearby_stores_tool"}
    ]
    if not store_entries:
        return None
    args = store_entries[-1].get("args")
    if not isinstance(args, dict):
        return None

    region_code = args.get("region_code") or args.get("place_query")
    store_nm = args.get("store_nm")
    xpos = args.get("xpos") or args.get("user_xpos")
    ypos = args.get("ypos") or args.get("user_ypos")
    if not (region_code or store_nm or (xpos is not None and ypos is not None)):
        return None

    preview_args = {
        "goods_no": goods_no,
        "ord_qty": qty,
        "region_code": region_code,
        "store_nm": store_nm,
        "user_xpos": xpos,
        "user_ypos": ypos,
        "include_price": True,
        "svc_codes": args.get("svc_codes"),
        "all_my_t_only": bool(args.get("all_my_t_only", False)),
        "imported_car_only": bool(args.get("imported_car_only", False)),
        "chl_sct_cd": args.get("chl_sct_cd"),
    }
    return {k: v for k, v in preview_args.items() if v is not None}


def _sanitize_tool_output_for_sse(content: Any) -> Any:
    """Return the tool result as a JSON string with internal-only keys removed.

    Accepts either a raw JSON string (parses it) or an already-parsed dict
    (skips redundant json.loads). Falls back to the original value on error.
    """
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return content
    elif isinstance(content, dict):
        parsed = content  # instruction_to_agent is internal-only; safe to strip from accumulated dict
    else:
        return content
    _strip_keys_in_place(parsed, _SSE_TOOL_OUTPUT_STRIPPED_KEYS)
    try:
        return json.dumps(parsed, ensure_ascii=False)
    except (TypeError, ValueError):
        return content


def _slot_data_for_tool_event(tool_name: str, tool_result: Any) -> dict | None:
    """Return minimal raw data needed by the coordinator to update slots.

    The SSE-visible `output` is sanitized. Slot extraction needs fields such as
    goods_no from the raw tool result, but exposing the full raw payload would be
    noisy. Keep this payload intentionally small.
    """
    if tool_name != "search_product_tool" or not isinstance(tool_result, dict):
        return None
    data = tool_result.get("data")
    if not isinstance(data, dict):
        return None
    items = data.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        return None
    item = items[0]
    goods_no = item.get("goods_no")
    if not goods_no:
        return None
    slot_item = {"goods_no": goods_no}
    tire_size = item.get("tire_size") or item.get("tire_size_1") or item.get("tireSize")
    if tire_size:
        slot_item["tire_size_1"] = tire_size
    return {"status": tool_result.get("status", "success"), "data": {"items": [slot_item]}}


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
# Matches trailing `quickReplies: [...]` that the model sometimes appends when it fails
# to emit a proper fenced JSON block (plain-text fallback path in stream()).
_INLINE_QUICK_REPLIES_RE = re.compile(r"\n\s*quickReplies:\s*(\[.*?\])\s*$", re.DOTALL | re.IGNORECASE)
_UNQUOTED_JSON_KEY_RE = re.compile(r"(?<=[{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")


# Validation 실패 시 사용자에게 빈 화면(silent dead-end) 대신 보여줄 안내.
# OUTPUT_TEMPLATE을 emit하려다 schema 검증이 깨진 경우, FE는 stream 종료
# 토큰(\n\n)만 받아 "응답 없음"으로 보였다. quickReply로 fallback하면
# 최소한 사용자가 다음 행동을 선택할 수 있다.
_VALIDATION_FALLBACK_MESSAGE = (
    "죄송합니다, 답변을 정리하던 중 일시적인 문제가 발생했어요.\n\n"
    "잠시 후 다시 시도해 주시거나 아래 버튼으로 다른 도움을 받아보세요."
)
_VALIDATION_FALLBACK_QUICK_REPLIES = [
    {"label": "다시 시도", "domain": "LEADING"},
    {"label": "상담사 연결", "domain": "SUPPORT"},
]


def _build_validated_quickreply_data(assistant_response: str, chips: list[dict]) -> dict:
    """Build a quickReply `data` payload through QuickReplyTemplate validation.

    Fallback emit paths (validation failure, prose mode, validation_fallback) bypass
    pydantic instantiation and yield dicts directly, which means QuickReplyTemplate
    validators (qty enforcement, satisfaction-chip enforcement) never fire. This
    helper runs the payload through QuickReplyTemplate so the same deterministic
    guards apply on the fallback paths.

    Returns the validated `data` dict (assistantResponse + quickReplies). Schema
    failures fall back to the raw input so we never harden an emit path into a
    crash — but validators that mutate (e.g., satisfaction auto-fix) take effect.
    """
    from services.tstation.agents.templates.schemas import QuickReplyChip, QuickReplyTemplate

    try:
        chip_objs = [QuickReplyChip(**c) if isinstance(c, dict) else c for c in chips]
        tpl = QuickReplyTemplate(assistantResponse=assistant_response, quickReplies=chip_objs)
        return tpl.model_dump()
    except ValidationError as exc:
        logger.warning(
            "[_build_validated_quickreply_data] schema validation failed, falling back to raw: %s",
            exc.errors(include_url=False),
        )
        return {"assistantResponse": assistant_response, "quickReplies": chips}

# 주문 수량을 묻는 quickReply 는 항상 1/2/3/4 4개 chip 을 노출해야 한다.
# LLM 이 가끔 일부 chip 을 누락 (예: ["4개","2개"]) 하거나 중복 (["2개","2개"]) 시켜
# UX 가 깨지므로 결정적 후처리로 정규화한다.
_CANONICAL_QTY_CHIPS = ("1개", "2개", "3개", "4개")
_STAGGERED_QTY_CHIPS = ("1개", "2개")
_QTY_CHIP_LABEL_RE = re.compile(r"^\s*\d+\s*(?:개|본)\s*$")
_QTY_PROMPT_RE = re.compile(
    r"주문\s*수량"
    r"|몇\s*개\s*(?:주문|구매|확인|예약|받|살|쓸|장바구니|결제|보내|들여|선택)"
    r"|몇\s*본\s*(?:주문|구매|확인|예약|받|살|쓸|장바구니|결제|보내|들여|선택)"
    r"|수량(?:을\s*(?:알려|선택|입력|말씀)|이\s*어떻|은\s*\d+\s*개)"
    r"|수량(?:을\s*)?몇\s*(?:개|본)"
    r"|수량\s*[:：]"
)
_STAGGERED_MAX_TWO_QTY_PROMPT_RE = re.compile(
    r"(?:앞/뒤|전/후륜|전륜.*후륜|앞.*뒤|규격.*달라|사이즈.*달라).{0,80}최대\s*2\s*개"
    r"|최대\s*2\s*개.{0,80}(?:앞/뒤|전/후륜|전륜.*후륜|앞.*뒤|규격.*달라|사이즈.*달라)",
    re.DOTALL,
)


def _normalize_qty_quick_replies(payload: dict) -> None:
    """주문 수량 질문 시 chip 을 결정적으로 ["1개","2개","3개","4개"] 로 강제.

    Trigger 조건 (모두 만족):
    - template == "quickReply"
    - assistantResponse 가 qty-asking 패턴 (`_QTY_PROMPT_RE`) 매칭
    - 기존 chip 이 모두 "N개" 모양 (혼합/비 qty chip 이면 보호하기 위해 skip)
    """
    if payload.get("template") != "quickReply":
        return
    data = payload.get("data")
    if not isinstance(data, dict):
        return
    assistant_response = data.get("assistantResponse") or ""
    if not _QTY_PROMPT_RE.search(assistant_response):
        return
    chips = data.get("quickReplies")
    chip_list = chips if isinstance(chips, list) else []
    labels = [c.get("label") if isinstance(c, dict) else c for c in chip_list]
    qty_shaped = [
        isinstance(label, str) and bool(_QTY_CHIP_LABEL_RE.match(label))
        for label in labels
    ]
    # 빈 배열이거나 chip 이 모두 qty 모양일 때만 정규화 — 다른 라벨이 섞이면 보존.
    if labels and not all(qty_shaped):
        return
    canonical_chips = (
        _STAGGERED_QTY_CHIPS
        if _STAGGERED_MAX_TWO_QTY_PROMPT_RE.search(assistant_response)
        else _CANONICAL_QTY_CHIPS
    )
    if tuple(labels) == canonical_chips:
        return  # 이미 정상
    domains = {
        c.get("domain")
        for c in chip_list
        if isinstance(c, dict) and c.get("domain")
    }
    domain = next(iter(domains)) if len(domains) == 1 else "TRANSACTION"
    data["quickReplies"] = [
        {"label": label, "domain": domain} for label in canonical_chips
    ]
    logger.info(
        "[base_agent] Normalized qty quickReply chips: was %s, now %s",
        labels,
        list(canonical_chips),
    )


class _AssistantResponseStreamer:
    """OUTPUT_TEMPLATE 응답에서 `assistantResponse` 값만 토큰 단위로 흘려보내는
    state machine. 이게 없으면 LeadingAgent처럼 fenced JSON을 출력하는 agent는
    JSON이 닫힐 때까지 모든 토큰을 버퍼링하므로, 사용자는 답이 다 만들어질 때까지
    스피너만 본다 (체감 latency의 핵심 원인).
    """

    _KEY = '"assistantResponse"'
    _ESCAPE_MAP = {'"': '"', "\\": "\\", "/": "/", "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}

    def __init__(self):
        self._buf = ""
        self._state = "SEARCHING"
        self._streamed_text = ""

    @property
    def streamed_any(self) -> bool:
        return bool(self._streamed_text)

    @property
    def streamed_text(self) -> str:
        return self._streamed_text

    @property
    def finished(self) -> bool:
        return self._state == "DONE"

    def feed(self, chunk: str) -> str:
        out: list[str] = []
        self._buf += chunk
        while True:
            if self._state == "SEARCHING":
                idx = self._buf.find(self._KEY)
                if idx < 0:
                    # key가 청크 경계에 걸칠 수 있으니 끝부분만 남긴다.
                    keep = len(self._KEY) - 1
                    if len(self._buf) > keep:
                        self._buf = self._buf[-keep:]
                    break
                self._buf = self._buf[idx + len(self._KEY):]
                self._state = "AWAIT_COLON"
            elif self._state == "AWAIT_COLON":
                idx = self._buf.find(":")
                if idx < 0:
                    break
                self._buf = self._buf[idx + 1:]
                self._state = "AWAIT_QUOTE"
            elif self._state == "AWAIT_QUOTE":
                idx = self._buf.find('"')
                if idx < 0:
                    break
                self._buf = self._buf[idx + 1:]
                self._state = "INSIDE"
            elif self._state == "INSIDE":
                emitted, consumed, finished = self._decode_inside(self._buf)
                if emitted:
                    out.append(emitted)
                self._buf = self._buf[consumed:]
                if finished:
                    self._state = "DONE"
                break
            else:
                self._buf = ""
                break
        result = "".join(out)
        if result:
            self._streamed_text += result
        return result

    @classmethod
    def _decode_inside(cls, s: str) -> tuple[str, int, bool]:
        out: list[str] = []
        i = 0
        n = len(s)
        while i < n:
            ch = s[i]
            if ch == '"':
                return ("".join(out), i + 1, True)
            if ch == "\\":
                if i + 1 >= n:
                    break
                esc = s[i + 1]
                if esc == "u":
                    if i + 6 > n:
                        break
                    try:
                        out.append(chr(int(s[i + 2:i + 6], 16)))
                    except ValueError:
                        out.append(s[i:i + 6])
                    i += 6
                    continue
                out.append(cls._ESCAPE_MAP.get(esc, esc))
                i += 2
                continue
            out.append(ch)
            i += 1
        return ("".join(out), i, False)


TOOL_DISPLAY_NAMES: dict[str, str] = {
    # Discovery
    "check_compatibility_tool": "차량-타이어 호환 확인 중...",
    "search_product_tool": "상품 검색 중...",
    "get_user_vehicles_tool": "차량 정보 조회 중...",
    "get_my_cars_tool": "내 차량 조회 중...",
    "search_car_model_tool": "차량 모델 검색 중...",
    "search_car_model_groups_tool": "차종 모델 검색 중...",
    "get_car_trims_tool": "차량 트림 조회 중...",
    "get_product_description_tool": "상품 상세 정보 조회 중...",
    "get_products_recommendations_tool": "상품 추천 조회 중...",
    "get_events_tool": "이벤트 목록 조회 중...",
    "get_deals_tool": "기획전 목록 조회 중...",
    "get_event_applicable_products_tool": "이벤트 적용 상품 조회 중...",
    "get_product_applicable_events_tool": "상품 적용 이벤트 조회 중...",
    "compare_discount_tool": "할인 가격 비교 중...",
    "get_cheapest_price_tool": "최저 혜택가 계산 중...",
    "search_youtube_video_tool": "유튜브 영상 검색 중...",
    # Transaction
    "get_final_price_tool": "가격 정보 조회 중...",
    "get_my_coupons_tool": "내 쿠폰 조회 중...",
    "get_logistics_inventory_tool": "재고 확인 중...",
    "get_store_inventory_tool": "매장 재고 확인 중...",
    "search_stores_tool": "매장 검색 중...",
    "search_stores_complex_tool": "매장 복합 검색 중...",
    "search_place_tool": "위치 검색 중...",
    "get_nearby_stores_tool": "주변 매장 검색 중...",
    "get_store_list_tool": "매장 목록 조회 중...",
    "get_store_detail_tool": "매장 상세 정보 조회 중...",
    "get_favorite_stores_tool": "단골매장 조회 중...",
    "save_to_cart_tool": "장바구니에 담는 중...",
    "quick_order_tool": "주문서 작성 중...",
    "get_order_status_tool": "주문 현황 조회 중...",
    "get_orders_of_user_tool": "주문 내역 조회 중...",
    # Support
    "get_faq_tool": "자주 묻는 질문 검색 중...",
    "search_faq_rag_tool": "질문 검색 중...",
    "escalate_tool": "상담사 연결 중...",
    "transfer_to_qna_tool": "1:1 문의 페이지 준비 중...",
    "get_product_warranties_tool": "상품 워런티 조회 중...",
    "get_my_warranties_tool": "내 워런티 조회 중...",
    "get_card_installments_tool": "무이자 할부 카드 조회 중...",
    "check_coupon_stacking_tool": "쿠폰 중복 적용 여부 확인 중...",
}


class BaseAgent(ABC):
    """Base agent class with streaming support for agent name and AF (Agent Function) mapping."""

    TOOL_TO_AF_MAP: dict[str, str] = {}
    TOOL_TO_TEMPLATE_MAP: dict[str, str] = {}
    OUTPUT_TEMPLATE: Any = None
    _FAST_PATH_CODE_MAPPER_TOOLS: frozenset[str] = frozenset({
        "get_my_cars_tool",
        "get_user_vehicles_tool",
        "get_store_inventory_tool",
        "get_store_schedule_tool",
        "get_stores_with_time_filter_tool",
        "search_stores_complex_tool",
        "search_product_tool",
        "get_products_recommendations_tool",
        "get_newest_products_tool",
        "get_best_selling_products_tool",
        "transaction_store_preview_tool",
    })

    def __init__(self, model, tools: list | None = None, system_prompt: str | Callable[[], str] = "", name: str = ""):
        self.name = name
        self._model = model
        self._tools = tools
        self._system_prompt = system_prompt
        self._agent = self._build_agent()

    def _build_agent(self):
        prompt = self._system_prompt() if callable(self._system_prompt) else self._system_prompt
        self._system_prompt_chars = len(prompt or "")
        logger.info("[AGENT] %s system_prompt_chars=%d", self.__class__.__name__, self._system_prompt_chars)
        return create_agent(
            model=self._model,
            tools=self._tools,
            # Keep LangGraph debug stream off in runtime to avoid noisy
            # `[values]` / `[updates]` payload dumps in container logs.
            debug=False,
            system_prompt=prompt,
            name=self.name,
        )

    @property
    def system_prompt_chars(self) -> int:
        return getattr(self, "_system_prompt_chars", 0)

    def invoke(self, messages: list[dict], config: dict | None = None) -> str:
        agent = self._agent
        result = agent.invoke({"messages": messages}, config=config)
        return result["messages"][-1].content

    def stream(self, messages: list[dict], config: dict | None = None):
        """
        Supported Stream modes:
        - status: Lifecycle markers — thinking (start), answering (before first token)
        - agent_flow: Agent name or AF when active (for UI display)
        - tokens: AI response tokens
        - message: Agent messages with agent name
        - tool_start: Emitted before a tool runs, with display_name for UI typing indicator
        - tool: Tool execution results with tool name, input, and output
        - data: Final UI template payload from structured response
        """
        agent = self._agent
        tool_calls_map: dict[str, dict] = {}
        answering_emitted = False
        prompt_template = self.OUTPUT_TEMPLATE
        suppress_tokens = prompt_template is not None
        accumulated_text = ""
        accumulated_tool_data: list[dict] = []
        response_streamer = _AssistantResponseStreamer() if suppress_tokens else None

        yield {"type": "status", "status": "생각 중..."}

        speculative_guard = (config or {}).get("configurable", {}).get("speculative_tool_guard", {})
        confirm_event = speculative_guard.get("confirm_event")
        wait_for_confirmation = speculative_guard.get("wait_for_confirmation")
        mutating_tools = set(speculative_guard.get("mutating_tools") or [])

        for mode, chunk in agent.stream(
            {"messages": messages},
            stream_mode=["messages", "updates"],
            config=config,
        ):
            if mode == "messages":
                token, _ = chunk
                if isinstance(token, AIMessageChunk) and token.text:
                    if suppress_tokens:
                        accumulated_text += token.text
                        streamed = response_streamer.feed(token.text)
                        if streamed:
                            if not answering_emitted:
                                yield {"type": "status", "status": "답변 중..."}
                                answering_emitted = True
                            yield {"type": "token", "content": streamed}
                        continue
                    if not answering_emitted:
                        yield {"type": "status", "status": "답변 중..."}
                        answering_emitted = True
                    yield {"type": "token", "content": token.text}

            elif mode == "updates":
                for node, update in chunk.items():
                    update_messages = update.get("messages")
                    if not isinstance(update_messages, list):
                        continue
                    for message in update_messages:
                        if isinstance(message, AIMessage):
                            if hasattr(message, "tool_calls") and message.tool_calls:
                                for tc in message.tool_calls:
                                    tool_name = tc["name"]
                                    tool_calls_map[tc["id"]] = {
                                        "name": tool_name,
                                        "args": tc.get("args", {}),
                                        "started_at": time.perf_counter(),
                                    }
                                    if tool_name == "get_store_schedule_tool":
                                        tool_plan = None
                                        tool_plan_allowed = False
                                        try:
                                            from services.tstation.template_mapper import current_transaction_tool_plan

                                            tool_plan = current_transaction_tool_plan.get()
                                        except Exception:
                                            tool_plan = None
                                        if tool_plan is not None:
                                            allowed_tools = tuple(getattr(tool_plan, "allowed_tools", ()) or ())
                                            forbidden_tools = tuple(getattr(tool_plan, "forbidden_tools", ()) or ())
                                            required_slots = tuple(getattr(tool_plan, "required_slots", ()) or ())
                                            tool_plan_allowed = (
                                                tool_name in allowed_tools
                                                and tool_name not in forbidden_tools
                                                and not required_slots
                                            )
                                        gate_decision = decide_schedule_tool_gate(
                                            user_text=_latest_user_text(messages),
                                            tool_args=tc.get("args", {}),
                                            recent_context=_recent_context_text(messages),
                                            allowed_by_tool_plan=tool_plan_allowed,
                                        )
                                        cfgable = (
                                            (config or {}).get("configurable", {})
                                            if isinstance(config, dict)
                                            else {}
                                        )
                                        trace_id = cfgable.get("tstation_trace_id")
                                        parent_span_id = cfgable.get("tstation_parent_span_id")
                                        if trace_id:
                                            with _trace_span(
                                                "🛡️ schedule_tool_gate",
                                                trace_id=trace_id,
                                                parent_span_id=parent_span_id,
                                                input={
                                                    "user_text": _latest_user_text(messages),
                                                    "tool_args": tc.get("args", {}),
                                                },
                                            ) as _ts:
                                                _ts.update(output=gate_decision.model_dump())
                                        logger.info(
                                            "[SCHEDULE_TOOL_GATE] allow=%s action=%s reason=%s",
                                            gate_decision.allow,
                                            gate_decision.action,
                                            gate_decision.reason,
                                        )
                                        if not gate_decision.allow:
                                            blocked_event = build_blocked_schedule_event(
                                                decision=gate_decision,
                                                user_text=_latest_user_text(messages),
                                            )
                                            for event in self._code_template_events(
                                                blocked_event,
                                                response_streamer,
                                                answering_emitted,
                                            ):
                                                yield event
                                            return
                                    guard_events = self._contract_sensitive_tool_guard_events(
                                        tool_name,
                                        messages,
                                        config=config,
                                        response_streamer=response_streamer,
                                        answering_emitted=answering_emitted,
                                    )
                                    if guard_events is not None:
                                        for event in guard_events:
                                            yield event
                                        return
                                    blocked_event = self._transaction_policy_blocked_event(tool_name, messages)
                                    if blocked_event is not None:
                                        logger.info(
                                            "[%s] Transaction policy blocked tool=%s required_slots=%s",
                                            self.name,
                                            tool_name,
                                            blocked_event.get("data", {}).get("requiredSlots"),
                                        )
                                        for event in self._code_template_events(
                                            blocked_event,
                                            response_streamer,
                                            answering_emitted,
                                        ):
                                            yield event
                                        return
                                    if (
                                        confirm_event is not None
                                        and tool_name in mutating_tools
                                        and not confirm_event.is_set()
                                    ):
                                        logger.info(
                                            "[%s] Waiting for speculative confirmation before %s",
                                            self.name,
                                            tool_name,
                                        )
                                        if wait_for_confirmation is not None and not wait_for_confirmation():
                                            logger.info("[%s] Speculative route rejected before %s", self.name, tool_name)
                                            return
                                        if wait_for_confirmation is None:
                                            confirm_event.wait()
                                    display_name = TOOL_DISPLAY_NAMES.get(tool_name, "답변 중...")
                                    yield {
                                        "type": "status",
                                        "status": "tool_start",
                                        "tool": tool_name,
                                        "display_name": display_name,
                                    }
                            if suppress_tokens:
                                continue
                            yield {
                                "type": "message",
                                "content": message.content,
                                "node": node,
                                "agent": self.name,
                            }
                        elif isinstance(message, ToolMessage):
                            af = self.TOOL_TO_AF_MAP.get(message.name, "Unknown")
                            tool_status = "success"
                            tool_result: Any = None
                            try:
                                tool_result = (
                                    json.loads(message.content) if isinstance(message.content, str) else message.content
                                )
                                if isinstance(tool_result, dict):
                                    tool_status = tool_result.get("status", "success")
                            except (json.JSONDecodeError, TypeError):
                                pass
                            tool_input = tool_calls_map.get(message.tool_call_id, {})
                            tool_started_at = tool_input.get("started_at")
                            tool_latency_ms = (
                                (time.perf_counter() - tool_started_at) * 1000
                                if isinstance(tool_started_at, (int, float))
                                else None
                            )
                            if tool_result is not None:
                                # Capture input args alongside the result so the
                                # template mapper can correlate same-turn tool calls
                                # by shop_id / cal_day (e.g., merge get_store_detail
                                # data into a get_store_list location card).
                                accumulated_tool_data.append({
                                    "tool": message.name,
                                    "data": tool_result,
                                    "args": tool_input.get("args", {}),
                                })
                            # Manual Langfuse span with a one-line summary so the
                            # trace tree shows what the tool returned at a glance.
                            # Raw output is still captured by LangChain's auto-span;
                            # this layer is purely for analyst readability.
                            _emit_tool_summary_span(
                                config,
                                tool_name=message.name,
                                tool_input=tool_input.get("args", {}),
                                tool_result=tool_result,
                                tool_status=tool_status,
                                latency_ms=tool_latency_ms,
                            )
                            yield {
                                "type": "agent_flow",
                                "agent": f"[{af} AF]",
                                "agent_class": self.name,
                                "status": tool_status,
                            }
                            yield {
                                "type": "tool",
                                "input": tool_input.get("args", {}),
                                "output": _sanitize_tool_output_for_sse(
                                    tool_result if tool_result is not None else message.content
                                ),
                                "slot_data": _slot_data_for_tool_event(message.name, tool_result),
                                "node": node,
                                "tool": message.name,
                            }
                            if "support" in self.name.lower() and message.name == "get_product_warranties_tool":
                                warranty_event = _build_product_warranty_quickreply_event(
                                    tool_result,
                                    accumulated_tool_data,
                                )
                                if warranty_event is not None:
                                    logger.info("[%s] Product warranty resolved via deterministic quickReply", self.name)
                                    for event in self._code_template_events(
                                        warranty_event,
                                        response_streamer,
                                        answering_emitted,
                                    ):
                                        yield event
                                    return
                            owner_lookup_event = _build_owner_vehicle_lookup_event(
                                message.name,
                                tool_result,
                                messages,
                            )
                            if owner_lookup_event is not None:
                                logger.info("[%s] Owner vehicle lookup resolved via deterministic quickReply", self.name)
                                for event in self._code_template_events(
                                    owner_lookup_event,
                                    response_streamer,
                                    answering_emitted,
                                ):
                                    yield event
                                return
                            owner_lookup_args = _vehicle_owner_lookup_args_after_registered_mismatch(
                                message.name,
                                tool_result,
                                messages,
                            )
                            if owner_lookup_args is not None:
                                try:
                                    from services.tstation.agents.b_discovery_agent.tools import get_user_vehicles_tool

                                    owner_tool_name = "get_user_vehicles_tool"
                                    owner_started_at = time.perf_counter()
                                    owner_tool_result = get_user_vehicles_tool.func(**owner_lookup_args)
                                    owner_latency_ms = (time.perf_counter() - owner_started_at) * 1000
                                    accumulated_tool_data.append({
                                        "tool": owner_tool_name,
                                        "data": owner_tool_result,
                                        "args": owner_lookup_args,
                                    })
                                    _emit_tool_summary_span(
                                        config,
                                        tool_name=owner_tool_name,
                                        tool_input=owner_lookup_args,
                                        tool_result=owner_tool_result,
                                        tool_status=(
                                            owner_tool_result.get("status", "success")
                                            if isinstance(owner_tool_result, dict)
                                            else "success"
                                        ),
                                        latency_ms=owner_latency_ms,
                                    )
                                    yield {
                                        "type": "status",
                                        "status": "tool_start",
                                        "tool": owner_tool_name,
                                        "display_name": TOOL_DISPLAY_NAMES.get(owner_tool_name, "차량 정보 조회 중..."),
                                    }
                                    yield {
                                        "type": "agent_flow",
                                        "agent": f"[{self.TOOL_TO_AF_MAP.get(owner_tool_name, 'Product Compatibility')} AF]",
                                        "agent_class": self.name,
                                        "status": (
                                            owner_tool_result.get("status", "success")
                                            if isinstance(owner_tool_result, dict)
                                            else "success"
                                        ),
                                    }
                                    yield {
                                        "type": "tool",
                                        "input": owner_lookup_args,
                                        "output": _sanitize_tool_output_for_sse(owner_tool_result),
                                        "node": "vehicle_owner_lookup_guard",
                                        "tool": owner_tool_name,
                                    }
                                    logger.info(
                                        "[%s] Ran owner vehicle lookup after registered-plate mismatch car_no=%s",
                                        self.name,
                                        owner_lookup_args.get("car_no"),
                                    )
                                    recommendation_args = _owner_lookup_vehicle_recommendation_args(
                                        owner_tool_result,
                                        messages,
                                    )
                                    if recommendation_args is not None:
                                        from services.tstation.agents.b_discovery_agent.tools import (
                                            get_products_recommendations_tool,
                                        )

                                        recommendation_tool_name = "get_products_recommendations_tool"
                                        yield {
                                            "type": "status",
                                            "status": "tool_start",
                                            "tool": recommendation_tool_name,
                                            "display_name": TOOL_DISPLAY_NAMES.get(
                                                recommendation_tool_name,
                                                "상품 추천 조회 중...",
                                            ),
                                        }
                                        recommendation_started_at = time.perf_counter()
                                        recommendation_result = get_products_recommendations_tool.invoke(
                                            recommendation_args,
                                        )
                                        recommendation_latency_ms = (
                                            time.perf_counter() - recommendation_started_at
                                        ) * 1000
                                        accumulated_tool_data.append({
                                            "tool": recommendation_tool_name,
                                            "data": recommendation_result,
                                            "args": recommendation_args,
                                        })
                                        _emit_tool_summary_span(
                                            config,
                                            tool_name=recommendation_tool_name,
                                            tool_input=recommendation_args,
                                            tool_result=recommendation_result,
                                            tool_status=(
                                                recommendation_result.get("status", "success")
                                                if isinstance(recommendation_result, dict)
                                                else "success"
                                            ),
                                            latency_ms=recommendation_latency_ms,
                                        )
                                        yield {
                                            "type": "agent_flow",
                                            "agent": (
                                                f"[{self.TOOL_TO_AF_MAP.get(recommendation_tool_name, 'Product Recommendation')} AF]"
                                            ),
                                            "agent_class": self.name,
                                            "status": (
                                                recommendation_result.get("status", "success")
                                                if isinstance(recommendation_result, dict)
                                                else "success"
                                            ),
                                        }
                                        yield {
                                            "type": "tool",
                                            "input": recommendation_args,
                                            "output": _sanitize_tool_output_for_sse(recommendation_result),
                                            "node": "vehicle_owner_lookup_guard",
                                            "tool": recommendation_tool_name,
                                        }
                                        code_event = self._try_code_template(
                                            accumulated_tool_data,
                                            response_streamer,
                                            accumulated_text,
                                        )
                                        if self._is_fast_path_code_event(recommendation_tool_name, code_event):
                                            logger.info(
                                                "[%s] Owner vehicle lookup recommendation resolved via code fast-path",
                                                self.name,
                                            )
                                            for event in self._code_template_events(
                                                code_event,
                                                response_streamer,
                                                answering_emitted,
                                            ):
                                                yield event
                                            return
                                except Exception:
                                    logger.exception("[%s] owner vehicle lookup guard failed", self.name)
                            if (
                                message.name in {"get_my_cars_tool", "get_user_vehicles_tool"}
                                and _is_explicit_vehicle_list_request(messages)
                            ):
                                code_event = self._try_code_template(
                                    accumulated_tool_data,
                                    response_streamer,
                                    accumulated_text,
                                )
                                if self._is_fast_path_code_event(message.name, code_event):
                                    logger.info(
                                        "[%s] Force listCar fast-path for explicit vehicle-list request",
                                        self.name,
                                    )
                                    for event in self._code_template_events(
                                        code_event,
                                        response_streamer,
                                        answering_emitted,
                                    ):
                                        yield event
                                    return
                            registered_vehicle_match = _resolve_registered_vehicle_match(
                                message.name,
                                tool_result,
                                messages,
                            )
                            if (
                                registered_vehicle_match is not None
                                and _is_staggered_registered_vehicle(registered_vehicle_match)
                            ):
                                staggered_event = _build_registered_vehicle_staggered_tire_event(
                                    registered_vehicle_match
                                )
                                if staggered_event is not None:
                                    logger.info(
                                        "[%s] Stop registered-vehicle auto recommendation for staggered fitment car_no=%s",
                                        self.name,
                                        registered_vehicle_match.get("car_no"),
                                    )
                                    yield {
                                        "type": "vehicle_selection_slots",
                                        "slot_values": _registered_vehicle_slot_values(registered_vehicle_match),
                                    }
                                    yield staggered_event
                                    return
                            if (
                                message.name in {"get_my_cars_tool", "get_user_vehicles_tool"}
                                and _contract_requires_listcar_fast_path(message.name, tool_result)
                            ):
                                if _should_defer_listcar_for_possessive_model_mismatch(
                                    message.name,
                                    tool_result,
                                    messages,
                                ):
                                    logger.info(
                                        "[%s] Skip contract-required listCar fast-path after possessive vehicle model mismatch",
                                        self.name,
                                    )
                                    continue
                                if registered_vehicle_match is not None:
                                    logger.info(
                                        "[%s] Skip contract-required listCar fast-path after unique registered-vehicle match car_no=%s",
                                        self.name,
                                        registered_vehicle_match.get("car_no"),
                                    )
                                    continue
                                code_event = self._try_code_template(
                                    accumulated_tool_data,
                                    response_streamer,
                                    accumulated_text,
                                )
                                if self._is_fast_path_code_event(message.name, code_event):
                                    logger.info(
                                        "[%s] Force contract-required listCar fast-path after tool=%s",
                                        self.name,
                                        message.name,
                                    )
                                    for event in self._code_template_events(
                                        code_event,
                                        response_streamer,
                                        answering_emitted,
                                    ):
                                        yield event
                                    return
                            if suppress_tokens and message.name in self._FAST_PATH_CODE_MAPPER_TOOLS:
                                if _should_skip_support_search_product_fast_path(self.name, message.name):
                                    logger.info(
                                        "[%s] Skip search_product_tool fast-path for support follow-up",
                                        self.name,
                                    )
                                    continue
                                if _should_defer_listcar_for_possessive_model_mismatch(
                                    message.name,
                                    tool_result,
                                    messages,
                                ):
                                    logger.info(
                                        "[%s] Skip listCar fast-path after possessive vehicle model mismatch",
                                        self.name,
                                    )
                                    continue
                                # When the user already named a unique registered vehicle in a
                                # recommendation turn, do not terminate at listCar here. Let the
                                # main Discovery loop continue and issue exactly one
                                # scenario-aware recommendation call.
                                if (
                                    registered_vehicle_match is not None
                                    and message.name in {"get_my_cars_tool", "get_user_vehicles_tool"}
                                ):
                                    logger.info(
                                        "[%s] Skip listCar fast-path after unique registered-vehicle match car_no=%s",
                                        self.name,
                                        registered_vehicle_match.get("car_no"),
                                    )
                                    continue
                                code_event = self._try_code_template(
                                    accumulated_tool_data,
                                    response_streamer,
                                    accumulated_text,
                                )
                                if self._is_fast_path_code_event(message.name, code_event):
                                    logger.info(
                                        "[%s] Deterministic template fast-path after tool=%s template=%s",
                                        self.name,
                                        message.name,
                                        code_event.get("template"),
                                    )
                                    for event in self._code_template_events(
                                        code_event,
                                        response_streamer,
                                        answering_emitted,
                                    ):
                                        yield event
                                    return

        stock_preview_args = _build_stock_preview_guard_args(accumulated_tool_data, messages)
        if stock_preview_args is not None:
            try:
                from services.tstation.agents.c_transaction_agent.tools import transaction_store_preview_tool

                tool_name = "transaction_store_preview_tool"
                tool_result = transaction_store_preview_tool.func(**stock_preview_args)
                accumulated_tool_data.append({
                    "tool": tool_name,
                    "data": tool_result,
                    "args": stock_preview_args,
                })
                _emit_tool_summary_span(
                    config,
                    tool_name=tool_name,
                    tool_input=stock_preview_args,
                    tool_result=tool_result,
                    tool_status=tool_result.get("status", "success") if isinstance(tool_result, dict) else "success",
                )
                yield {
                    "type": "agent_flow",
                    "agent": f"[{self.TOOL_TO_AF_MAP.get(tool_name, 'Unknown')} AF]",
                    "agent_class": self.name,
                    "status": tool_result.get("status", "success") if isinstance(tool_result, dict) else "success",
                }
                yield {
                    "type": "tool",
                    "input": stock_preview_args,
                    "output": _sanitize_tool_output_for_sse(tool_result),
                    "node": "stock_preview_guard",
                    "tool": tool_name,
                }
                logger.warning(
                    "[STOCK_PREVIEW_GUARD] Re-ran generic store search as inventory preview: %s",
                    stock_preview_args,
                )
            except Exception:
                logger.exception("[STOCK_PREVIEW_GUARD] Failed to run transaction_store_preview_tool")

        # Phase 2B: prefer code-based template mapping over LLM fenced JSON.
        # When a deterministically-mappable tool was used, build the data event
        # in code from accumulated_tool_data — saves the LLM from emitting the
        # full FE JSON payload (the dominant 2nd-call output token cost).
        code_event = self._try_code_template(accumulated_tool_data, response_streamer, accumulated_text)
        if code_event is not None:
            for event in self._code_template_events(code_event, response_streamer, answering_emitted):
                yield event
            return

        if prompt_template is not None and accumulated_text:
            data_event = self._build_data_event_from_text(accumulated_text, prompt_template)
            already_streamed = response_streamer is not None and response_streamer.streamed_any
            if data_event is not None:
                # LLM 이 product 템플릿을 직접 emit 한 경우, tags 결정형 주입 +
                # 스키마 외 hallucinated 필드 (comfort 등) 제거. 다른 템플릿은 no-op.
                from services.tstation.template_mapper import inject_product_tags_and_sanitize, sanitize_user_facing_response
                inject_product_tags_and_sanitize(data_event, accumulated_tool_data)
                assistant_response = self._get_assistant_response(data_event)
                if assistant_response:
                    assistant_response = sanitize_user_facing_response(assistant_response)
                    data_event["data"]["assistantResponse"] = assistant_response
                if assistant_response:
                    if not answering_emitted:
                        yield {"type": "status", "status": "답변 중..."}
                        answering_emitted = True
                    # 점진적 streaming으로 이미 prose를 보낸 경우 token 재전송은
                    # 화면에 응답이 두 번 쌓이게 만든다.
                    if not already_streamed:
                        yield {"type": "token", "content": assistant_response}
                    yield {
                        "type": "message",
                        "content": assistant_response,
                        "agent": self.name,
                    }
                yield data_event
            else:
                # If any tool returned a pre-built output_payload, use it directly
                # rather than falling through to generic fallback. This handles
                # reasoning models that consistently emit plain text instead of
                # the required fenced JSON block.
                _tool_payload_used = False
                for _td in reversed(accumulated_tool_data):
                    _tool_data = _td.get("data") or {}
                    _payload_str = (_tool_data.get("data") or {}).get("output_payload")
                    if _payload_str:
                        try:
                            _payload = json.loads(_payload_str)
                            if not answering_emitted:
                                yield {"type": "status", "status": "답변 중..."}
                                answering_emitted = True
                            yield _payload
                            _tool_payload_used = True
                        except Exception:
                            pass
                        break
                if not _tool_payload_used:
                    # _build_data_event_from_text가 이미 error 로그를 남겼다.
                    # 여기서는 빈 \n\n만 보내는 대신 사용자에게 fallback quickReply를
                    # 노출해 silent dead-end UX를 방지한다.
                    if not answering_emitted:
                        yield {"type": "status", "status": "답변 중..."}
                        answering_emitted = True
                    if already_streamed:
                        # prose는 이미 흘러갔으므로 fallback 메시지 중복 송출은 피하고
                        # 마무리용 quickReply chips만 추가한다.
                        yield {
                            "type": "data",
                            "template": "quickReply",
                            "data": _build_validated_quickreply_data(
                                response_streamer.streamed_text,
                                list(_VALIDATION_FALLBACK_QUICK_REPLIES),
                            ),
                            "nextAction": {"type": "stop", "domain": None},
                        }
                    else:
                        # Phase 2B: LLM may have emitted plain prose (PROSE MODE) when
                        # template_mapper couldn't build a card — e.g., zero-result
                        # search where the model honored the "prose mode" rule but
                        # the mapper found no items to render. Treat the raw text
                        # as the assistant's prose answer rather than showing the
                        # generic validation-failure apology.
                        prose_only = accumulated_text.strip()
                        if prose_only and self._extract_fenced_json(accumulated_text) is None:
                            # Model emitted plain text instead of fenced JSON. Strip any
                            # trailing `quickReplies: [...]` annotation and parse chips.
                            chips: list[dict] = []
                            m = _INLINE_QUICK_REPLIES_RE.search(prose_only)
                            if m:
                                prose_only = prose_only[:m.start()].strip()
                                try:
                                    raw = json.loads(m.group(1))
                                    chips = [
                                        {"label": c, "domain": None} if isinstance(c, str) else c
                                        for c in raw if c
                                    ]
                                except (json.JSONDecodeError, TypeError):
                                    pass
                            yield {"type": "token", "content": prose_only}
                            yield {
                                "type": "message",
                                "content": prose_only,
                                "agent": self.name,
                            }
                            yield {
                                "type": "data",
                                "template": "quickReply",
                                "data": _build_validated_quickreply_data(prose_only, chips),
                                "nextAction": {"type": "stop", "domain": None},
                            }
                        else:
                            yield from self._yield_validation_fallback()

        yield {"type": "token", "content": "\n\n"}

    def _yield_validation_fallback(self):
        """OUTPUT_TEMPLATE 검증 실패 시 사용자 가시 fallback 이벤트 시퀀스.

        성공 경로(token → message → data)와 같은 형태로 emit하여
        FE/coordinator가 일관되게 처리할 수 있게 한다.
        """
        message = _VALIDATION_FALLBACK_MESSAGE
        yield {"type": "token", "content": message}
        yield {
            "type": "message",
            "content": message,
            "agent": self.name,
        }
        yield {
            "type": "data",
            "template": "quickReply",
            "assistant_response_source": "validation_fallback",
            "data": _build_validated_quickreply_data(
                message, list(_VALIDATION_FALLBACK_QUICK_REPLIES)
            ),
            "nextAction": {"type": "stop", "domain": None},
        }

    def _code_template_events(
        self,
        code_event: dict,
        response_streamer: "_AssistantResponseStreamer | None",
        answering_emitted: bool,
    ) -> list[dict]:
        """Return the standard SSE sequence for a deterministic template event."""
        code_event["template_source"] = "code_mapper"
        assistant_response = self._get_assistant_response(code_event)
        if assistant_response:
            from services.tstation.template_mapper import sanitize_user_facing_response

            assistant_response = sanitize_user_facing_response(assistant_response)
            code_event["data"]["assistantResponse"] = assistant_response
        already_streamed = response_streamer is not None and response_streamer.streamed_any
        events: list[dict] = []
        if assistant_response:
            if not answering_emitted:
                events.append({"type": "status", "status": "답변 중..."})
            if not already_streamed:
                events.append({"type": "token", "content": assistant_response})
            events.append({
                "type": "message",
                "content": assistant_response,
                "agent": self.name,
            })
        events.append(code_event)
        events.append({"type": "token", "content": "\n\n"})
        return events

    def _build_data_event(self, structured_response: BaseModel | dict | None) -> dict | None:
        """Convert structured response into the FE `data` event shape."""
        if structured_response is None:
            return None

        payload = (
            structured_response.model_dump() if isinstance(structured_response, BaseModel) else structured_response
        )
        if not isinstance(payload, dict):
            logger.warning("[%s] Structured response is not a dict — skipping data event", self.name)
            return None

        if payload.get("type") != "data":
            logger.warning("[%s] Structured response missing type='data' — skipping", self.name)
            return None

        if not isinstance(payload.get("template"), str):
            logger.warning("[%s] Structured response missing template — skipping", self.name)
            return None

        if not isinstance(payload.get("data"), dict):
            logger.warning("[%s] Structured response missing data object — skipping", self.name)
            return None

        _normalize_qty_quick_replies(payload)
        return payload

    @staticmethod
    def _get_assistant_response(data_event: dict) -> str:
        data = data_event.get("data", {})
        if not isinstance(data, dict):
            return ""
        assistant_response = data.get("assistantResponse")
        return assistant_response if isinstance(assistant_response, str) else ""

    def _build_data_event_from_text(self, text: str, template_cls: Any) -> dict | None:
        """Extract a fenced JSON object from `text`, validate it against `template_cls`,
        and return a `data` event ready to yield. Returns None on any failure.

        On failure, logs at error level so missed structured-output turns are observable
        (the coordinator will fall back to the legacy UI Template Agent path).
        """
        raw = self._extract_fenced_json(text)
        if raw is None:
            logger.error(
                "[%s] No fenced JSON block found in agent response — falling back to legacy UI path",
                self.name,
            )
            return None
        parsed = self._parse_agent_json(raw)
        if parsed is None:
            logger.error("[%s] Invalid JSON in agent response", self.name)
            return None
        try:
            validated = TypeAdapter(template_cls).validate_python(parsed)
        except ValidationError as exc:
            logger.error(
                "[%s] Output JSON failed schema validation (template=%s): %s",
                self.name,
                parsed.get("template") if isinstance(parsed, dict) else None,
                exc.errors(include_url=False),
            )
            return None
        return self._build_data_event(validated)

    @staticmethod
    def _parse_agent_json(raw: str) -> Any | None:
        """Parse LLM JSON, accepting common JSON-like slips without hiding real failures."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError as strict_exc:
            # Models sometimes emit JS/Python-ish dicts: {type: 'data'}.
            normalized = _UNQUOTED_JSON_KEY_RE.sub(r' "\1":', raw)
            try:
                return json.loads(normalized)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(normalized)
                except (SyntaxError, ValueError, TypeError) as loose_exc:
                    logger.debug("Agent JSON parse failed: strict=%s loose=%s", strict_exc, loose_exc)
                    return None
                return parsed

    @staticmethod
    def _extract_fenced_json(text: str) -> str | None:
        matches = _FENCED_JSON_RE.findall(text)
        return matches[-1] if matches else None

    @staticmethod
    def _try_code_template(
        accumulated_tool_data: list[dict],
        response_streamer: "_AssistantResponseStreamer | None",
        accumulated_text: str,
    ) -> dict | None:
        """Attempt deterministic FE-template construction from tool outputs.

        Returns a `data` event dict if any tool in accumulated_tool_data has a
        registered code mapper AND the mapper produced a valid event.
        Returns None to signal "fall through to fenced-JSON path".

        If the LLM emitted an explicit fenced JSON block, defer to it — the
        agent has chosen its own template (e.g. comparison intent → quickReply
        instead of the default cheapestProduct mapper).

        listCar exception: when get_my_cars_tool / get_user_vehicles_tool ran,
        always use the deterministic mapper even if the LLM emitted fenced JSON.
        The mapper enriches info with car_maker prefix and keeps info/description
        consistent; LLM-authored JSON drifts in format between turns.

        Store-detail exception: when get_store_detail_tool ran, the LLM's
        quickReply often slips into PROSE-MODE ("매장 상세정보를 확인했어요.")
        and the rich detail fields never reach the user — only QC catches it.
        _map_store_detail_info's own guards defer back to the LLM for Flow 5.1
        (date-specific datepick / no-slot apology).
        """
        if not accumulated_tool_data:
            return None
        _FORCE_CODE_MAPPER_TOOLS = (
            "get_my_cars_tool",
            "get_user_vehicles_tool",
            "get_store_detail_tool",
            "get_store_schedule_tool",
            "get_nearby_stores_tool",
            "get_stores_with_time_filter_tool",
            # Product list tools — items 있으면 product 카드 강제. LLM 이
            # "비슷한 가격대 더 추천" 같은 follow-up 발화에서 fenced JSON 으로
            # quickReply 만 emit 하고 product 카드를 건너뛰는 회귀 차단.
            # items 0 (검색 0건) 케이스는 mapper 가 None 반환 → LLM prose fallback.
            "search_product_tool",
            "get_products_recommendations_tool",
            "get_newest_products_tool",
            "get_best_selling_products_tool",
        )
        has_force_code_mapper_tool = any(
            e.get("tool") in _FORCE_CODE_MAPPER_TOOLS for e in accumulated_tool_data
        )
        # Deterministic guard override: when a tool response carries
        # `instruction_to_agent` (e.g. transaction_store_preview_tool tier=none
        # region/multi-candidate case), the LLM's own template choice may slip
        # into a generic `quickReply` and bury the candidate list. Force the
        # code mapper so the structured card (`location`) reaches the FE.
        if not has_force_code_mapper_tool:
            for entry in accumulated_tool_data:
                for output in (entry.get("output"), entry.get("data")):
                    if isinstance(output, str) and '"instruction_to_agent"' in output:
                        has_force_code_mapper_tool = True
                        break
                    if not isinstance(output, dict):
                        continue
                    data = output.get("data") if isinstance(output.get("data"), dict) else output
                    if isinstance(data, dict) and data.get("instruction_to_agent"):
                        has_force_code_mapper_tool = True
                        break
                if has_force_code_mapper_tool:
                    break
        if not has_force_code_mapper_tool and BaseAgent._extract_fenced_json(accumulated_text) is not None:
            return None
        from services.tstation.template_mapper import _MAPPERS, try_build_template
        if not any(e.get("tool") in _MAPPERS for e in accumulated_tool_data):
            return None
        prose = (
            response_streamer.streamed_text
            if response_streamer is not None and response_streamer.streamed_any
            else accumulated_text
        )
        return try_build_template(accumulated_tool_data, prose)

    @classmethod
    def _is_fast_path_code_event(cls, tool_name: str, code_event: dict | None) -> bool:
        """Return true when a tool result can terminate the turn without post-tool LLM."""
        if tool_name not in cls._FAST_PATH_CODE_MAPPER_TOOLS:
            return False
        if not isinstance(code_event, dict) or code_event.get("type") != "data":
            return False
        template = code_event.get("template")
        if not isinstance(template, str):
            return False

        terminal_templates_by_tool = {
            "get_my_cars_tool": {"listCar"},
            "get_user_vehicles_tool": {"listCar"},
            "get_store_inventory_tool": {"location", "quickReply"},
            "get_store_schedule_tool": {"datepick"},
            "get_stores_with_time_filter_tool": {"location", "quickReply"},
            "search_stores_complex_tool": {"location", "quickReply"},
            "search_product_tool": {"product", "quickReply"},
            "get_products_recommendations_tool": {"product", "quickReply"},
            "get_newest_products_tool": {"product", "quickReply"},
            "get_best_selling_products_tool": {"product", "quickReply"},
            "transaction_store_preview_tool": {"location", "datepick", "quickReply"},
        }
        return template in terminal_templates_by_tool.get(tool_name, set())

    @staticmethod
    def _annotate_contract_tool_block(
        event: dict[str, Any],
        *,
        blocked_tool: str,
        replacement_tool: str | None,
        contract_intent: str,
        allowed_tools: tuple[str, ...],
        forbidden_tools: tuple[str, ...],
        block_reason: str,
    ) -> dict[str, Any]:
        event["contract_tool_blocked"] = True
        event["blocked_tool"] = blocked_tool
        event["replacement_tool"] = replacement_tool or ""
        event["contract_intent"] = contract_intent
        event["block_reason"] = block_reason
        event["allowed_tools"] = list(allowed_tools)
        event["forbidden_tools"] = list(forbidden_tools)
        event_data = event.get("data")
        if isinstance(event_data, dict):
            metadata = event_data.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
                event_data["metadata"] = metadata
            metadata["contract_tool_blocked"] = True
            metadata["blocked_tool"] = blocked_tool
            metadata["replacement_tool"] = replacement_tool or ""
            metadata["contract_intent"] = contract_intent
            metadata["block_reason"] = block_reason
            metadata["allowed_tools"] = list(allowed_tools)
            metadata["forbidden_tools"] = list(forbidden_tools)
        return event

    def _blocked_contract_tool_guard_events(
        self,
        *,
        tool_name: str,
        contract_intent: str,
        allowed_tools: tuple[str, ...],
        forbidden_tools: tuple[str, ...],
        required_slots: tuple[str, ...],
        response_decision: Any,
        block_reason: str,
        response_streamer: "_AssistantResponseStreamer | None",
        answering_emitted: bool,
    ) -> list[dict] | None:
        try:
            from services.tstation.policies.turn_contract import (
                TurnContract,
                build_required_slot_clarification_event,
                build_response_policy_guard_event,
            )
        except Exception:
            return None

        domain = "support" if "support" in str(self.name or "").lower() else "transaction"
        known_slots: dict[str, Any] = {}
        if required_slots:
            if "product" in required_slots or "goods_no" in required_slots or "product_set" in required_slots:
                known_slots["pending_intent"] = "price"
                known_slots["goal_type"] = "price_inquiry"
            elif "order" in required_slots:
                known_slots["pending_intent"] = "order"
                known_slots["goal_type"] = "place_order"
            elif "store" in required_slots or "location" in required_slots:
                known_slots["pending_intent"] = "stock"
                known_slots["goal_type"] = "store_with_stock"

        contract = TurnContract(
            domain=domain,
            intent=contract_intent or "contract_tool_guard",
            known_slots=known_slots,
            required_slots=required_slots,
            allowed_tools=allowed_tools,
            forbidden_tools=forbidden_tools,
            response_decision=response_decision.to_dict() if hasattr(response_decision, "to_dict") else {},
            action_mode="support_policy_answer" if domain == "support" else "unspecified",
            context_state="dormant",
        )
        guard_event = (
            build_required_slot_clarification_event(contract)
            if required_slots
            else build_response_policy_guard_event(contract)
        )
        guard_event = self._annotate_contract_tool_block(
            guard_event,
            blocked_tool=tool_name,
            replacement_tool=None,
            contract_intent=contract_intent or "contract_tool_guard",
            allowed_tools=allowed_tools,
            forbidden_tools=forbidden_tools,
            block_reason=block_reason,
        )
        guard_event["assistant_response_source"] = "code_contract_tool_guard"
        return [*self._code_template_events(guard_event, response_streamer, answering_emitted)]

    def _contract_sensitive_tool_guard_events(
        self,
        tool_name: str,
        messages: list[dict] | None,
        *,
        config: dict | None,
        response_streamer: "_AssistantResponseStreamer | None",
        answering_emitted: bool,
    ) -> list[dict] | None:
        try:
            from services.tstation.policies.flow_controller import build_purchase_flow_fallback_event
            from services.tstation.policies.response_decision import TemplateName
            from services.tstation.template_mapper import (
                current_transaction_response_decision,
                current_transaction_tool_plan,
            )
        except Exception:
            return None

        decision = current_transaction_response_decision.get()
        tool_plan = current_transaction_tool_plan.get()
        if decision is None or tool_plan is None:
            return None

        allowed_tools = tuple(getattr(tool_plan, "allowed_tools", ()) or ())
        forbidden_tools = tuple(getattr(tool_plan, "forbidden_tools", ()) or ())
        preferred_tool = str(getattr(tool_plan, "preferred_tool", None) or "")
        metadata = getattr(tool_plan, "metadata", None) or {}
        flow_id = str(metadata.get("flow_id") or "")
        if decision.template != TemplateName.QUICK_REPLY and flow_id != "purchase_order":
            return None
        contract_intent = str(metadata.get("response_intent") or "")
        required_slots = tuple(getattr(tool_plan, "required_slots", ()) or getattr(decision, "required_slots", ()) or ())
        if not forbidden_tools and not allowed_tools:
            return None

        block_reason = ""
        if tool_name in forbidden_tools:
            block_reason = "forbidden_tool_for_contract"
        elif allowed_tools and tool_name not in allowed_tools:
            block_reason = "tool_not_allowed_for_contract"
        if not block_reason:
            return None

        if flow_id == "purchase_order":
            replacement_events = self._preferred_contract_tool_replacement_events(
                blocked_tool=tool_name,
                preferred_tool=preferred_tool,
                tool_plan=tool_plan,
                metadata=metadata,
                contract_intent=contract_intent,
                allowed_tools=allowed_tools,
                forbidden_tools=forbidden_tools,
                required_slots=required_slots,
                block_reason=block_reason,
                config=config,
                response_streamer=response_streamer,
                answering_emitted=answering_emitted,
            )
            if replacement_events is not None:
                return replacement_events
            flow_event = build_purchase_flow_fallback_event(
                intent=contract_intent,
                known_slots=metadata.get("flow_slots") if isinstance(metadata.get("flow_slots"), dict) else {},
                tool_data_list=_tool_entries_from_previous_agent_facts(messages),
                blocked_tool=tool_name,
            )
            if flow_event is not None:
                flow_event = self._annotate_contract_tool_block(
                    flow_event,
                    blocked_tool=tool_name,
                    replacement_tool=None,
                    contract_intent=contract_intent or "contract_tool_guard",
                    allowed_tools=allowed_tools,
                    forbidden_tools=forbidden_tools,
                    block_reason=block_reason,
                )
                flow_event["assistant_response_source"] = "code_contract_tool_guard"
                return [*self._code_template_events(flow_event, response_streamer, answering_emitted)]

        if preferred_tool != "search_faq_hybrid_tool":
            return self._blocked_contract_tool_guard_events(
                tool_name=tool_name,
                contract_intent=contract_intent,
                allowed_tools=allowed_tools,
                forbidden_tools=forbidden_tools,
                required_slots=required_slots,
                response_decision=decision,
                block_reason=block_reason,
                response_streamer=response_streamer,
                answering_emitted=answering_emitted,
            )

        user_query = _latest_user_text(messages or [])
        logger.info(
            "[%s] Contract tool guard blocked tool=%s replacement=%s intent=%s reason=%s",
            self.name,
            tool_name,
            preferred_tool,
            contract_intent,
            block_reason,
        )

        try:
            from services.tstation.agents.e_support_agent.tools import search_faq_hybrid_tool as _search_faq_hybrid_tool
            from services.tstation.chat import (
                _DIRECT_SUPPORT_FAQ_POLICY_INTENTS,
                _build_general_cancel_fee_policy_event,
                _build_general_card_cancel_timing_policy_event,
                _build_support_faq_policy_event,
            )
        except Exception:
            return None

        tool_input = {"query": user_query, "top_k": 8}
        try:
            raw_tool_result = _search_faq_hybrid_tool.invoke(tool_input)
        except Exception as exc:
            logger.exception("[%s] Replacement FAQ tool failed intent=%s", self.name, contract_intent)
            raw_tool_result = {"status": "error", "http_status": None, "message": str(exc), "data": {}}
        tool_result = raw_tool_result if isinstance(raw_tool_result, dict) else {"status": "success", "data": raw_tool_result}
        tool_status = str(tool_result.get("status") or "success")
        _emit_tool_summary_span(
            config,
            tool_name=preferred_tool,
            tool_input=tool_input,
            tool_result=tool_result,
            tool_status=tool_status,
            latency_ms=None,
        )

        if contract_intent == "general_cancel_fee_policy":
            code_event = _build_general_cancel_fee_policy_event(user_query, tool_result=tool_result)
        elif contract_intent == "general_card_cancel_timing_policy":
            code_event = _build_general_card_cancel_timing_policy_event(user_query, tool_result=tool_result)
        elif contract_intent in _DIRECT_SUPPORT_FAQ_POLICY_INTENTS:
            code_event = _build_support_faq_policy_event(
                contract_intent,
                user_query,
                tool_result=tool_result,
            )
        else:
            return self._blocked_contract_tool_guard_events(
                tool_name=tool_name,
                contract_intent=contract_intent,
                allowed_tools=allowed_tools,
                forbidden_tools=forbidden_tools,
                required_slots=required_slots,
                response_decision=decision,
                block_reason=block_reason,
                response_streamer=response_streamer,
                answering_emitted=answering_emitted,
            )
        if not isinstance(code_event, dict):
            return self._blocked_contract_tool_guard_events(
                tool_name=tool_name,
                contract_intent=contract_intent,
                allowed_tools=allowed_tools,
                forbidden_tools=forbidden_tools,
                required_slots=required_slots,
                response_decision=decision,
                block_reason=block_reason,
                response_streamer=response_streamer,
                answering_emitted=answering_emitted,
            )
        code_event = self._annotate_contract_tool_block(
            code_event,
            blocked_tool=tool_name,
            replacement_tool=preferred_tool,
            contract_intent=contract_intent,
            allowed_tools=allowed_tools,
            forbidden_tools=forbidden_tools,
            block_reason=block_reason,
        )
        return [
            {
                "type": "status",
                "status": "tool_start",
                "tool": preferred_tool,
                "display_name": "FAQ 확인 중...",
            },
            {
                "type": "agent_flow",
                "agent": "[FAQ AF]",
                "agent_class": self.name,
                "status": tool_status,
            },
            {
                "type": "tool",
                "input": tool_input,
                "output": _sanitize_tool_output_for_sse(tool_result),
                "slot_data": _slot_data_for_tool_event(preferred_tool, tool_result),
                "node": "tools",
                "tool": preferred_tool,
            },
            *self._code_template_events(code_event, response_streamer, answering_emitted),
        ]

    def _preferred_contract_tool_replacement_events(
        self,
        *,
        blocked_tool: str,
        preferred_tool: str,
        tool_plan: Any,
        metadata: dict[str, Any],
        contract_intent: str,
        allowed_tools: tuple[str, ...],
        forbidden_tools: tuple[str, ...],
        required_slots: tuple[str, ...],
        block_reason: str,
        config: dict | None,
        response_streamer: "_AssistantResponseStreamer | None",
        answering_emitted: bool,
    ) -> list[dict] | None:
        if (
            not preferred_tool
            or required_slots
            or preferred_tool in forbidden_tools
            or (allowed_tools and preferred_tool not in allowed_tools)
        ):
            return None

        try:
            from services.tstation.agents.c_transaction_agent import tools as transaction_tools
            from services.tstation.template_mapper import try_build_template
        except Exception:
            return None

        replacement_tool = getattr(transaction_tools, preferred_tool, None)
        if replacement_tool is None or not hasattr(replacement_tool, "invoke"):
            return None

        tool_input = {
            key: value
            for key, value in dict(getattr(tool_plan, "tool_args_patch", {}) or {}).items()
            if value not in (None, "", [], {})
        }
        if not tool_input:
            return None

        logger.info(
            "[%s] Contract tool guard blocked tool=%s replacement=%s intent=%s reason=%s",
            self.name,
            blocked_tool,
            preferred_tool,
            contract_intent,
            block_reason,
        )

        started_at = time.perf_counter()
        try:
            raw_tool_result = replacement_tool.invoke(tool_input)
        except Exception as exc:
            logger.exception("[%s] Replacement transaction tool failed intent=%s", self.name, contract_intent)
            raw_tool_result = {"status": "error", "http_status": None, "message": str(exc), "data": {}}
        latency_ms = (time.perf_counter() - started_at) * 1000
        tool_result = raw_tool_result if isinstance(raw_tool_result, dict) else {"status": "success", "data": raw_tool_result}
        tool_status = str(tool_result.get("status") or "success")
        _emit_tool_summary_span(
            config,
            tool_name=preferred_tool,
            tool_input=tool_input,
            tool_result=tool_result,
            tool_status=tool_status,
            latency_ms=latency_ms,
        )

        code_event = try_build_template(
            [{"tool": preferred_tool, "args": tool_input, "data": tool_result}],
            "",
        )
        if not isinstance(code_event, dict):
            return None

        code_event = self._annotate_contract_tool_block(
            code_event,
            blocked_tool=blocked_tool,
            replacement_tool=preferred_tool,
            contract_intent=contract_intent,
            allowed_tools=allowed_tools,
            forbidden_tools=forbidden_tools,
            block_reason=block_reason,
        )
        code_event["assistant_response_source"] = "code_contract_tool_guard"
        display_name = str(metadata.get("preferred_tool_display_name") or metadata.get("display_name") or "정보 확인 중...")
        return [
            {
                "type": "status",
                "status": "tool_start",
                "tool": preferred_tool,
                "display_name": display_name,
            },
            {
                "type": "agent_flow",
                "agent": "[Transaction AF]",
                "agent_class": self.name,
                "status": tool_status,
            },
            {
                "type": "tool",
                "input": tool_input,
                "output": _sanitize_tool_output_for_sse(tool_result),
                "slot_data": _slot_data_for_tool_event(preferred_tool, tool_result),
                "node": "tools",
                "tool": preferred_tool,
            },
            *self._code_template_events(code_event, response_streamer, answering_emitted),
        ]

    @staticmethod
    def _transaction_policy_blocked_event(tool_name: str, messages: list[dict] | None = None) -> dict | None:
        """Return a deterministic clarification when Transaction lacks required slots."""
        transaction_tools_requiring_slots = {
            "search_stores_tool",
            "search_stores_complex_tool",
            "get_store_list_tool",
            "get_nearby_stores_tool",
            "get_store_inventory_tool",
            "get_store_schedule_tool",
            "get_multi_store_schedule_tool",
            "transaction_store_preview_tool",
            "save_to_cart_tool",
            "quick_order_tool",
        }
        if tool_name not in transaction_tools_requiring_slots:
            return None
        try:
            from services.tstation.policies.response_decision import TemplateName
            from services.tstation.template_mapper import (
                current_transaction_response_decision,
                current_transaction_tool_plan,
            )
        except Exception:
            return None

        decision = current_transaction_response_decision.get()
        tool_plan = current_transaction_tool_plan.get()
        safe_lookup_intents = {
            "store_search",
            "favorite_store_lookup",
            "product_coupon_eligibility",
            "coupon_applicable_products",
            "coupon_pattern_applicability",
            "order_history_lookup",
            "reservation_lookup",
        }
        tool_plan_intent = ""
        if tool_plan is not None:
            metadata = getattr(tool_plan, "metadata", None) or {}
            tool_plan_intent = str(metadata.get("response_intent") or "")
        if (
            tool_plan is not None
            and tool_name in getattr(tool_plan, "allowed_tools", ())
            and not getattr(tool_plan, "required_slots", ())
            and tool_plan_intent in safe_lookup_intents
        ):
            return None
        if (
            decision is None
            or decision.template != TemplateName.QUICK_REPLY
            or not decision.required_slots
        ):
            return None
        if "product" in decision.required_slots and _messages_include_resolved_product_tool_fact(messages or []):
            return None

        slot_labels = {
            "product": "상품",
            "tire_size": "타이어 사이즈",
            "quantity": "수량",
            "store": "매장",
            "location": "지역",
        }
        labels = [slot_labels.get(slot, slot) for slot in decision.required_slots]
        if decision.required_slots == ("tire_size",):
            assistant_response = "재고와 장착 가능 여부를 확인하려면 타이어 사이즈가 필요해요."
        else:
            assistant_response = f"{', '.join(labels)} 정보를 먼저 확인해야 다음 단계로 진행할 수 있어요."
        quick_replies = []
        if "tire_size" in decision.required_slots:
            quick_replies.extend([
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
                {"label": "차량번호로 확인", "domain": "DISCOVERY"},
            ])
        if "store" in decision.required_slots or "location" in decision.required_slots:
            quick_replies.append({"label": "근처 매장 찾기", "domain": "TRANSACTION"})
        if "quantity" in decision.required_slots:
            quick_replies.extend([
                {"label": "1개", "domain": "TRANSACTION"},
                {"label": "2개", "domain": "TRANSACTION"},
                {"label": "3개", "domain": "TRANSACTION"},
                {"label": "4개", "domain": "TRANSACTION"},
            ])
        if not quick_replies:
            quick_replies = [{"label": "조건 다시 입력", "domain": "TRANSACTION"}]

        return {
            "type": "data",
            "template": "quickReply",
            "assistant_response_source": "transaction_policy_guard",
            "data": {
                "assistantResponse": assistant_response,
                "quickReplies": quick_replies,
                "predictedDomains": ["DISCOVERY", "TRANSACTION"],
                "requiredSlots": list(decision.required_slots),
            },
        }

    def stream_template(self, messages: list[dict], config: dict | None = None):
        """
        Stream that transforms tool calls into data template events.
        Yields ONLY data events (no token or agent_flow events).

        Use this when you want to format tool outputs as UI templates directly.
        """
        import json
        import logging

        logger = logging.getLogger(__name__)
        agent = self._agent

        tool_called = False

        for mode, chunk in agent.stream(
            {"messages": messages},
            stream_mode=["messages", "updates"],
            config=config,
        ):
            if mode == "updates":
                for node, update in chunk.items():
                    message = update["messages"][-1]
                    if isinstance(message, ToolMessage):
                        tool_called = True
                        template_name = self.TOOL_TO_TEMPLATE_MAP.get(message.name)
                        if not template_name:
                            logger.warning(f"[UI_TEMPLATE] Tool {message.name} has no template mapping")
                            continue
                        # Parse tool output (message.content is JSON string)
                        try:
                            tool_output = json.loads(message.content)
                            tool_data = tool_output.get("data", {})
                        except (json.JSONDecodeError, TypeError):
                            logger.warning(f"[UI_TEMPLATE] Failed to parse tool output for {message.name}")
                            tool_data = {}

                        # Skip if tool_data is null or empty
                        if not tool_data:
                            logger.warning(f"[UI_TEMPLATE] Empty tool_data for {message.name}, skipping")
                            continue

                        # Yield data event with tool's actual output data
                        yield {
                            "type": "data",
                            "template": template_name,
                            "data": tool_data,
                        }

        if not tool_called:
            logger.warning("[UI_TEMPLATE] Agent generated no tool calls — templates not rendered")
