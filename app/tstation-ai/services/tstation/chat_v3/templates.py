"""Rich FE templates: product cards, store lists, car picker, cheapest price.

The mini model maps raw tool output into the Pydantic template models from
`agents/templates/schemas.py` (single source of truth) — same approach V2
uses via RESPONSE_FORMAT, but as one dedicated call. Any failure returns
None and the turn falls back to the plain quickReply event.
"""

import json
import logging
from typing import Any

from pydantic import BaseModel

from services.tstation.agents.templates.schemas import (
    CheapestProductTemplate,
    DatepickTemplate,
    ListCarTemplate,
    LocationTemplate,
    OrderCompleteTemplate,
    PreOrderTemplate,
    ProductTemplate,
    QnaCompleteTemplate,
)
from services.tstation.chat_v3.llm import get_router_llm
from services.tstation.chat_v3.prompts.templates import TEMPLATE_BUILDER_PROMPT

logger = logging.getLogger(__name__)

_MAX_TOOL_OUTPUT_CHARS = 12000

_SERVICE_LABELS = {
    "113": "타이어",
    "119": "타이어 보관서비스",
    "120": "수입타이어 취급",
    "121": "경정비",
    "122": "경정비",
    "124": "휠얼라이먼트",
    "125": "휠얼라이먼트",
    "126": "무상점검",
}

_QUANTITY_CHIPS = [
    {"label": "1개", "domain": "TRANSACTION"},
    {"label": "2개", "domain": "TRANSACTION"},
    {"label": "3개", "domain": "TRANSACTION"},
    {"label": "4개", "domain": "TRANSACTION"},
]

_CNSL_TYPE_MAP = {
    "10002": "\uc0c1\ud488\ubb38\uc758",
    "10006": "\uc8fc\ubb38/\uacb0\uc81c/\ubc30\uc1a1",
    "10010": "\ubc18\ud488/\uad50\ud658/\ud658\ubd88",
    "10013": "\uc81c\uacf5\uc11c\ube44\uc2a4/\uc774\ubca4\ud2b8/\ud61c\ud0dd",
    "10017": "\ud68c\uc6d0",
    "10019": "\uae30\ud0c0",
    "10025": "\uac00\ub9f9\uc810\uc81c\ud734\ubb38\uc758",
    "10034": "\uc774\ub825\uc11c\uc811\uc218",
}

# Which template a tool's output can feed — data availability, not routing.
_TOOL_TEMPLATES: dict[str, tuple[str, type[BaseModel]]] = {
    "search_product_tool": ("product", ProductTemplate),
    "search_product_summary_tool": ("product", ProductTemplate),
    "get_products_recommendations_tool": ("product", ProductTemplate),
    "get_best_selling_products_tool": ("product", ProductTemplate),
    "get_newest_products_tool": ("product", ProductTemplate),
    "search_benefit_applicable_products_tool": ("product", ProductTemplate),
    "get_event_applicable_products_tool": ("product", ProductTemplate),
    "get_coupon_applicable_products_tool": ("product", ProductTemplate),
    "search_stores_tool": ("location", LocationTemplate),
    "search_stores_complex_tool": ("location", LocationTemplate),
    "get_nearby_stores_tool": ("location", LocationTemplate),
    "get_store_list_tool": ("location", LocationTemplate),
    "get_stores_with_time_filter_tool": ("location", LocationTemplate),
    "get_user_vehicles_tool": ("listCar", ListCarTemplate),
    "get_my_cars_tool": ("listCar", ListCarTemplate),
    "get_cheapest_price_tool": ("cheapestProduct", CheapestProductTemplate),
    "get_store_schedule_tool": ("datepick", DatepickTemplate),
    "get_multi_store_schedule_tool": ("datepick", DatepickTemplate),
    "transaction_store_preview_tool": ("preOrder", PreOrderTemplate),
    "quick_order_tool": ("orderComplete", OrderCompleteTemplate),
    "save_to_cart_tool": ("orderComplete", OrderCompleteTemplate),
}


def _has_rows(output: str) -> bool:
    """True when the tool output parses to non-empty JSON data."""
    try:
        parsed = json.loads(output)
    except (TypeError, ValueError):
        return bool(output and len(output) > 50)
    if isinstance(parsed, dict):
        return any(bool(v) for v in parsed.values())
    return bool(parsed)


def _pick_source(tool_calls: list[dict]) -> tuple[str, type[BaseModel], dict] | None:
    """Most recent tool call whose output can feed a rich template."""
    for call in reversed(tool_calls):
        entry = _TOOL_TEMPLATES.get(call.get("name") or "")
        output = str(call.get("output") or "")
        if entry and not output.startswith("Tool error") and _has_rows(output):
            return entry[0], entry[1], call
    return None


def _parse_tool_output(output: object) -> dict[str, Any]:
    if isinstance(output, dict):
        return output
    try:
        parsed = json.loads(str(output or ""))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _latest_tool_output(tool_calls: list[dict], tool_name: str) -> dict[str, Any]:
    for call in reversed(tool_calls):
        if call.get("name") == tool_name:
            return _parse_tool_output(call.get("output"))
    return {}


def _answer_without_urls(answer: str) -> str:
    lines = []
    for line in str(answer or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if "http://" in line or "https://" in line:
            continue
        cleaned = line.strip()
        if cleaned:
            lines.append(cleaned)
    return compact_answer_spacing("\n".join(lines))


def _cnsl_type_label(cnsl_clss_seq: object) -> str:
    seq = str(cnsl_clss_seq or "").strip()
    return _CNSL_TYPE_MAP.get(seq, seq or "1:1")


def build_qna_complete_event(answer: str, tool_calls: list[dict]) -> dict | None:
    """Build qnaComplete directly from transfer_to_qna_tool output."""
    raw = _latest_tool_output(tool_calls, "transfer_to_qna_tool")
    if not raw or raw.get("status") != "success":
        return None
    redict_link = raw.get("redictLink") or raw.get("redict_link")
    if not isinstance(redict_link, dict) or not redict_link.get("pc") or not redict_link.get("mobile"):
        return None

    title = str(raw.get("inq_tit_nm") or "1:1 문의").strip()
    summary = str(raw.get("ai_summary") or title).strip()
    assistant_response = _answer_without_urls(answer) or summary
    payload = QnaCompleteTemplate(
        assistantResponse=assistant_response,
        redictLink=redict_link,
        cnslType=_cnsl_type_label(raw.get("cnsl_clss_seq")),
        title=title,
        summary=summary,
    )
    return {
        "type": "data",
        "template": "qnaComplete",
        "data": payload.model_dump(mode="json", exclude_none=True),
        "source_tool": "transfer_to_qna_tool",
    }


def _store_rows_from_output(output: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(output)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, dict):
        return []
    data = parsed.get("data")
    if isinstance(data, dict) and isinstance(data.get("stores"), list):
        return [row for row in data["stores"] if isinstance(row, dict)]
    stores = parsed.get("stores")
    if isinstance(stores, list):
        return [row for row in stores if isinstance(row, dict)]
    return []


def _join_address(*parts: object) -> str:
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def _format_hour(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if ":" in text:
        return text
    if text.isdigit() and len(text) <= 2:
        return f"{int(text):02d}:00"
    return text


def _format_time_range(start: object, end: object) -> str:
    start_text = _format_hour(start)
    end_text = _format_hour(end)
    if start_text and end_text:
        return f"{start_text}~{end_text}"
    return start_text or end_text or "-"


def _closed_days(row: dict[str, Any]) -> str:
    end_day = str(row.get("shop_biz_end_wday") or "").strip()
    if end_day == "일요일":
        return "없음"
    if end_day == "토요일":
        return "일요일"
    if end_day == "금요일":
        return "토요일, 일요일"
    return "-"


def _feature_labels(row: dict[str, Any]) -> list[str]:
    labels = []
    if row.get("is_all_my_t"):
        labels.append("all my T")
    if row.get("is_installable"):
        labels.append("온라인 장착 가능")
    if row.get("is_imported_car"):
        labels.append("수입차 특화점")
    if row.get("is_ev_specialty"):
        labels.append("전기차 특화점")
    if row.get("is_ev_charge_available"):
        labels.append("전기차 충전 가능")
    return labels


def _service_labels(row: dict[str, Any]) -> list[str]:
    raw_codes = row.get("svc_codes") or []
    if isinstance(raw_codes, str):
        raw_codes = [raw_codes]
    labels = []
    seen = set()
    for code in raw_codes if isinstance(raw_codes, list) else []:
        label = _SERVICE_LABELS.get(str(code))
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    return labels


def _store_info_lines(row: dict[str, Any]) -> list[str]:
    return [
        f"주소: {_join_address(row.get('addr_base'), row.get('addr_dtl')) or '-'}",
        f"연락처: {str(row.get('tel_no') or '').strip() or '-'}",
        f"평일: {_format_time_range(row.get('shop_biz_strt_time'), row.get('shop_biz_end_time'))}",
        f"토요일: {_format_time_range(row.get('shop_sat_strt_time'), row.get('shop_sat_end_time'))}",
        f"휴무일: {_closed_days(row)}",
        f"특징: {', '.join(_feature_labels(row)) or '-'}",
        f"서비스: {', '.join(_service_labels(row)) or '-'}",
    ]


def _intro_from_answer(answer: str) -> str:
    intro = (answer or "").split("\n\n", 1)[0].strip()
    return intro if intro and not intro.startswith("1.") else "확인된 매장 정보입니다."


def compact_answer_spacing(answer: str) -> str:
    text = str(answer or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    while "\n\n" in text:
        text = text.replace("\n\n", "\n")
    return text.strip()


def quantity_quick_replies(answer: str, ord_qty: int | None = None) -> list[dict]:
    if ord_qty is not None:
        return []
    text = str(answer or "")
    asks_quantity = (
        "몇 개" in text
        or "몇 본" in text
        or "수량" in text
        or "4개로 진행" in text
        or "4개 기준" in text
    )
    asks_confirmation = "진행할까요" in text or "선택" in text or "알려" in text or "말씀" in text
    if asks_quantity and asks_confirmation:
        return [dict(chip) for chip in _QUANTITY_CHIPS]
    return []


def format_location_answer(answer: str, tool_calls: list[dict]) -> str:
    source = _pick_source(tool_calls)
    if source is None or source[0] != "location":
        return answer
    raw_stores = _store_rows_from_output(str(source[2].get("output") or ""))
    if not raw_stores:
        return answer

    sections = [_intro_from_answer(answer)]
    for index, row in enumerate(raw_stores[:5], start=1):
        shop_name = str(row.get("shop_nm") or "").strip() or f"매장 {index}"
        lines = "\n   ".join(_store_info_lines(row))
        sections.append(f"{index}. **{shop_name}**\n   {lines}")
    return "\n\n".join(sections)


def _normalize_location_payload(payload: BaseModel, tool_output: str) -> None:
    raw_stores = _store_rows_from_output(tool_output)
    stores = getattr(payload, "stores", None)
    metadata = getattr(payload, "metadata", None)
    if not raw_stores or not isinstance(stores, list):
        return

    for index, (item, raw) in enumerate(zip(stores, raw_stores)):
        shop_name = str(raw.get("shop_nm") or "").strip()
        if shop_name:
            item.nameAddress = shop_name
        detail_address = _join_address(raw.get("addr_base"), raw.get("addr_dtl"))
        if detail_address:
            item.detailAddress = detail_address
        item.description = "\n".join(_store_info_lines(raw))
        if isinstance(metadata, list) and index < len(metadata):
            meta = metadata[index]
            shop_id = str(raw.get("shop_id") or "").strip()
            if shop_id:
                meta.shopId = shop_id
            if shop_name:
                meta.shopName = shop_name


async def build_rich_data_event(answer: str, tool_calls: list[dict], trace_config: dict | None = None) -> dict | None:
    """Return a validated FE data event dict, or None to fall back to quickReply."""
    source = _pick_source(tool_calls)
    if source is None:
        return None
    template_name, template_model, call = source
    try:
        llm = get_router_llm().with_structured_output(template_model, method="function_calling")
        messages = [
            ("system", TEMPLATE_BUILDER_PROMPT),
            (
                "user",
                f"## 도구: {call['name']}\n## 도구 결과\n{str(call['output'])[:_MAX_TOOL_OUTPUT_CHARS]}\n\n"
                f"## 챗봇 답변\n{answer[:2000]}",
            ),
        ]
        payload = await llm.ainvoke(messages, config=trace_config) if trace_config else await llm.ainvoke(messages)
        if not getattr(payload, "assistantResponse", ""):
            payload.assistantResponse = answer
        if template_name == "location":
            _normalize_location_payload(payload, str(call["output"]))
        return {
            "type": "data",
            "template": template_name,
            "data": payload.model_dump(mode="json", exclude_none=True),
            "source_tool": call["name"],
        }
    except Exception:
        logger.exception("[CHAT_V3] rich template build failed (%s) — falling back to quickReply", template_name)
        return None
