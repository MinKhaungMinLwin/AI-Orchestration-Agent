from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

_VALID_CHIP_DOMAINS: frozenset[str] = frozenset({"DISCOVERY", "TRANSACTION", "SUPPORT", "LEADING"})


def _dedupe_domain_values(values: list[str]) -> list[str]:
    deduped = []
    for value in values:
        domain = str(value).upper()
        if domain in _VALID_CHIP_DOMAINS and domain not in deduped:
            deduped.append(domain)
    return deduped


_ORDER_CANCEL_REFUND_QUERY_RE = re.compile(
    r"환불|환급|입금|취소\s*승인|취소\s*완료|취소\s*처리|카드\s*취소|결제\s*취소|결제수단|"
    r"카드사|취소.{0,20}(?:언제|됐|되|처리|승인|환불)|(?:언제|얼마나).{0,20}환불|"
    r"주문\s*취소|예약\s*취소|반품|교환",
    re.IGNORECASE,
)
_DIRECT_RESERVATION_CHANGE_QUERY_RE = re.compile(
    r"(?:예약|방문|일정|시간|예약\s*시간|방문\s*시간).{0,20}(?:변경|바꾸|바꿔|미루|당기)|"
    r"(?:\d{1,2}\s*시|\d{1,2}\s*:\s*\d{2}|오늘|내일|모레).{0,12}(?:로|으로)?.{0,12}"
    r"(?:변경|바꾸|바꿔|미루|당기)",
    re.IGNORECASE,
)

_BOOKING_PREVIEW_CHIPS = [
    {
        "label": "다른 지역 입력",
        "domain": "TRANSACTION",
        "actionId": "enter_region",
        "intentKey": "today_install",
        "metadata": {"intentKey": "today_install"},
    },
    {
        "label": "다른 날짜 입력",
        "domain": "TRANSACTION",
        "actionId": "enter_date",
        "intentKey": "today_install",
        "metadata": {"intentKey": "today_install"},
    },
]
_AFFIRMATIVE_REPLY_RE = re.compile(r"^\s*(?:응|네|예|좋아|ㅇㅇ|그래|진행해|검색해줘)\s*$", re.IGNORECASE)
_CURRENT_LOCATION_STORE_SEARCH_PROMPT_RE = re.compile(
    r"현재\s*위치\s*기반.*(?:가까운|주변)\s*매장\s*검색.*(?:진행|해드릴까요|할까요)|"
    r"(?:가까운|주변)\s*매장\s*검색.*현재\s*위치\s*기반",
    re.IGNORECASE,
)


def _is_current_location_store_search_confirmation(user_text: str, latest_quickreply_tmpl: dict | None) -> bool:
    if not _AFFIRMATIVE_REPLY_RE.match(user_text or ""):
        return False
    if not isinstance(latest_quickreply_tmpl, dict):
        return False
    assistant_text = str(latest_quickreply_tmpl.get("assistantResponse") or "")
    return bool(_CURRENT_LOCATION_STORE_SEARCH_PROMPT_RE.search(assistant_text))


_ORDER_HISTORY_CTA_LABEL_RE = re.compile(r"주문\s*내역|주문내역", re.IGNORECASE)
_PURCHASE_CTA_LABELS = {"구매하기", "주문하기", "바로 주문", "바로 구매"}
_CART_CTA_LABELS = {
    "장바구니담기",
    "장바구니 담기",
    "장바구니에 담아줘",
    "장바구니에 넣어줘",
    "카트에 넣어",
    "이거 카트에 넣어",
}
_ORDER_HISTORY_CTA_ALLOWED_INTENTS = frozenset({
    "order_history_lookup",
    "order_document_guidance",
    "owned_order_cancel_fee_inquiry",
    "order_cancel_request",
    "order_cancel_status_lookup",
    "order_arrival_status_lookup",
    "payment_method_change_guidance",
    "payment_error_troubleshooting",
    "general_cancel_fee_policy",
    "general_card_cancel_timing_policy",
})


def _contract_intent_value(turn_contract: Any | None) -> str:
    return str(
        getattr(turn_contract, "sub_intent", None)
        or getattr(turn_contract, "intent", None)
        or ""
    ).strip()


def _order_history_cta_allowed_for_contract(turn_contract: Any | None, action_mode: str | None) -> bool:
    intent = _contract_intent_value(turn_contract)
    if intent in _ORDER_HISTORY_CTA_ALLOWED_INTENTS:
        return True
    if intent.startswith("order_") and intent != "quick_order_reservation":
        return True
    if "owned_order" in intent or "order_document" in intent:
        return True
    if intent == "quick_order_reservation":
        return not tuple(getattr(turn_contract, "missing_slots", ()) or ())
    return str(action_mode or getattr(turn_contract, "action_mode", "") or "") in {
        "owned_record_lookup",
        "support_policy_answer",
    } and bool(intent and "order" in intent)


def _event_or_contract_product_context(event_data: Mapping[str, Any], turn_contract: Any | None) -> dict[str, Any]:
    metadata = event_data.get("metadata") if isinstance(event_data.get("metadata"), Mapping) else {}
    known_slots = getattr(turn_contract, "known_slots", None)
    known_slots = known_slots if isinstance(known_slots, Mapping) else {}
    context: dict[str, Any] = {}
    for field, aliases in {
        "goods_no": ("goods_no", "goodsNo"),
        "tire_size": ("tire_size", "tireSize"),
        "product_name": ("product_name", "productName", "goods_nm", "goodsNm"),
        "ord_qty": ("ord_qty", "ordQty", "quantity"),
    }.items():
        for source in (known_slots, metadata):
            for alias in aliases:
                value = source.get(alias) if isinstance(source, Mapping) else None
                if value not in (None, "", [], {}):
                    context[field] = value
                    break
            if field in context:
                break
    return context


def _sanitize_transaction_cta_contracts(
    event_data: dict[str, Any],
    *,
    source_domain: str,
    turn_contract: Any | None = None,
    action_mode: str | None = None,
) -> bool:
    chips = event_data.get("quickReplies")
    if not isinstance(chips, list):
        return False
    changed = False
    normalized: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    blocked_ctas: list[dict[str, str]] = []
    product_context = _event_or_contract_product_context(event_data, turn_contract)
    current_action_mode = str(action_mode or getattr(turn_contract, "action_mode", "") or "")
    current_intent = _contract_intent_value(turn_contract)
    for chip in chips:
        if not isinstance(chip, dict):
            continue
        label = str(chip.get("label") or "").strip()
        if not label:
            continue
        action_id = str(chip.get("actionId") or chip.get("action_id") or "").strip()
        has_url = bool(chip.get("url"))
        if _ORDER_HISTORY_CTA_LABEL_RE.search(label) and not _order_history_cta_allowed_for_contract(
            turn_contract,
            current_action_mode,
        ):
            blocked_ctas.append({
                "label": label,
                "reason": f"order_history_forbidden:{current_intent or current_action_mode or 'unknown'}",
            })
            changed = True
            continue
        if label in _PURCHASE_CTA_LABELS and product_context:
            chip = dict(chip)
            metadata = chip.get("metadata") if isinstance(chip.get("metadata"), dict) else {}
            slots = {key: value for key, value in product_context.items() if value not in (None, "", [], {})}
            metadata = {
                **metadata,
                "cta_action": "start_purchase",
                "source_intent": current_intent or "quick_order_reservation",
                "expected_contract_intent": "quick_order_reservation",
                "expected_behavior": "conversation_action",
                "slots": {
                    **slots,
                    "pending_intent": "order",
                    "goal_type": "place_order",
                },
            }
            chip.update({
                "domain": "TRANSACTION",
                "cta_action": "start_purchase",
                "expected_behavior": "conversation_action",
                "expected_contract_intent": "quick_order_reservation",
                "metadata": metadata,
            })
            changed = True
        if label in _CART_CTA_LABELS and product_context:
            chip = dict(chip)
            metadata = chip.get("metadata") if isinstance(chip.get("metadata"), dict) else {}
            slots = {key: value for key, value in product_context.items() if value not in (None, "", [], {})}
            metadata = {
                **metadata,
                "cta_action": "add_to_cart",
                "source_intent": current_intent or "quick_order_reservation",
                "expected_contract_intent": "quick_order_reservation",
                "expected_behavior": "conversation_action",
                "slots": {
                    **slots,
                    "pending_intent": "cart",
                    "goal_type": "add_to_cart",
                },
            }
            chip.update({
                "domain": "TRANSACTION",
                "cta_action": "add_to_cart",
                "expected_behavior": "conversation_action",
                "expected_contract_intent": "quick_order_reservation",
                "metadata": metadata,
            })
            changed = True
        if (
            source_domain == "transaction"
            and label in {"다른 매장 찾기", "다른 지역 찾기"}
            and not action_id
            and not has_url
        ):
            chip = {
                "label": "다른 지역 입력",
                "domain": "TRANSACTION",
                "actionId": "enter_region",
                "intentKey": "today_install",
                "metadata": {"intentKey": "today_install"},
            }
            label = "다른 지역 입력"
            changed = True
        elif source_domain == "transaction" and label == "예약하기" and not action_id and not has_url:
            blocked_ctas.append({"label": label, "reason": "label_only_reservation"})
            changed = True
            continue
        if label in seen_labels:
            changed = True
            continue
        seen_labels.add(label)
        normalized.append(chip)
    if normalized != chips:
        event_data["quickReplies"] = normalized
        changed = True
    if changed and normalized:
        event_data["predictedDomains"] = _dedupe_domain_values([
            *(event_data.get("predictedDomains") or []),
            *[
                str(chip.get("domain") or "")
                for chip in normalized
                if isinstance(chip, dict) and chip.get("domain")
            ],
        ])
    if changed:
        metadata = event_data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            event_data["metadata"] = metadata
        metadata["cta_validation_result"] = "blocked" if blocked_ctas else "normalized"
        if blocked_ctas:
            metadata["blocked_ctas"] = blocked_ctas
    return changed


def _normalize_booking_preview_quickreply(event_data: dict, called_tool_names: set[str]) -> bool:
    """Add booking-oriented CTAs after a stock/booking preview quickReply.

    `transaction_store_preview_tool` is the ground-truth tool for "this tire,
    this store, this qty" installability. When it returns a text quickReply
    (for example "today is unavailable, earliest is next Tuesday"), generic
    discovery chips are a dead end. Keep this scoped to turns where that tool
    actually ran so ordinary product/search quickReplies are untouched.
    """
    if "transaction_store_preview_tool" not in called_tool_names:
        return False
    assistant_text = str(event_data.get("assistantResponse") or "")
    if not re.search(r"예약|장착", assistant_text):
        return False
    chips = event_data.get("quickReplies")
    if isinstance(chips, list) and chips:
        return False
    event_data["quickReplies"] = [dict(chip) for chip in _BOOKING_PREVIEW_CHIPS]
    event_data["predictedDomains"] = ["TRANSACTION"]
    event_data.setdefault("metadata", {"ctaContext": {"intentKey": "today_install"}})
    return True


_RESERVATION_CHANGE_POSSIBLE_COPY_RE = re.compile(
    r"예약\s*시간\s*변경이\s*가능한\s*상태로\s*보여요\.?"
    r"|[^\n.。]*변경\s*가능\s*여부[^\n.。]*[.。]?"
    r"|주문\s*내역\s*상세에서\s*예약\s*시간\s*변경\s*가능\s*여부[^\n.。]*[.。]?"
    r"|예약\s*시간\s*변경\s*가능\s*여부[^\n.。]*[.。]?"
    r"|(?:정확한\s*)?변경\s*가능\s*여부는\s*[^\n.。]*확인[^\n.。]*필요해요\.?"
    r"|(?:오늘|내일|모레|\d{1,2}\s*시|\d{1,2}\s*:\s*\d{2}|[^\n.。]{0,12})로\s*변경\s*가능\s*여부는\s*"
    r"예약\s*확인\s*후\s*진행이\s*필요해요\.?",
    re.IGNORECASE,
)


def _normalize_existing_reservation_change_quickreply(
    event_data: dict[str, Any],
    *,
    last_user_text: str | None = None,
    called_tool_names: set[str] | None = None,
) -> bool:
    user_text = last_user_text or ""
    if called_tool_names and "get_orders_of_user_tool" in called_tool_names:
        return False
    if user_text and _ORDER_CANCEL_REFUND_QUERY_RE.search(user_text):
        return False
    if user_text and not _DIRECT_RESERVATION_CHANGE_QUERY_RE.search(user_text):
        return False

    assistant_text = str(event_data.get("assistantResponse") or "")
    if not assistant_text:
        return False

    guidance = (
        "예약 시간은 제가 직접 변경해 드릴 수는 없어요. "
        "예약 내역 또는 주문 상세에서 직접 처리하거나, 필요하면 취소 후 재예약 또는 1:1 문의로 확인해 주세요."
    )
    normalized = _RESERVATION_CHANGE_POSSIBLE_COPY_RE.sub(guidance, assistant_text)
    if normalized == assistant_text and "직접 변경" in assistant_text:
        return False
    if normalized == assistant_text:
        normalized = f"{assistant_text.rstrip()}\n\n{guidance}"
    direct_sentence = "예약 시간은 제가 직접 변경해 드릴 수는 없어요."
    if normalized.count(direct_sentence) > 1:
        first_idx = normalized.find(direct_sentence)
        head = normalized[: first_idx + len(direct_sentence)]
        tail = normalized[first_idx + len(direct_sentence):].replace(direct_sentence, "").strip()
        normalized = f"{head}\n\n{tail}" if tail else head

    event_data["assistantResponse"] = normalized
    chips = event_data.get("quickReplies")
    if not isinstance(chips, list) or not chips:
        event_data["quickReplies"] = [
            {"label": "내 예약 조회", "domain": "TRANSACTION"},
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ]
    event_data["predictedDomains"] = _dedupe_domain_values(
        [
            *(event_data.get("predictedDomains") or []),
            "TRANSACTION",
            "SUPPORT",
        ]
    )
    return True


_VAGUE_STORE_DETAIL_TEXT_RE = re.compile(
    r"(?:매장|지점)?.{0,12}(?:정보|상세(?:정보)?).{0,12}확인(?:했|됐|되었)",
    re.IGNORECASE,
)
_STORE_DETAIL_REPLACEMENT_ALLOWED_INTENTS: frozenset[str] = frozenset({
    "plain_store_info_lookup",
    "store_detail",
    "store_holiday_lookup",
    "store_holiday",
    "reservation_store_info_lookup",
    "reservation_store_reference",
})


def _store_detail_quickreply_from_sources(
    structured_sources: list[tuple[str, dict]],
    assistant_text: str,
) -> dict | None:
    if not structured_sources:
        return None
    tool_data = [
        {"tool": tool_name, "data": data}
        for tool_name, data in structured_sources
        if tool_name == "get_store_detail_tool" and isinstance(data, dict)
    ]
    if not tool_data:
        return None
    try:
        from services.tstation.template_mapper import try_build_template

        mapped = try_build_template(tool_data, assistant_text)
    except Exception:
        logger.exception("[STORE_DETAIL] failed to rebuild vague quickReply from tool sources")
        return None
    if isinstance(mapped, dict) and mapped.get("template") == "quickReply":
        return mapped
    return None


def _should_replace_vague_store_detail_quickreply(event_data: dict[str, Any]) -> bool:
    assistant_text = str(event_data.get("assistantResponse") or "")
    if not assistant_text:
        return False
    if "• 매장명:" in assistant_text or "전화번호" in assistant_text or "영업시간" in assistant_text:
        return False
    return bool(_VAGUE_STORE_DETAIL_TEXT_RE.search(assistant_text))


def _store_detail_quickreply_replacement_allowed(
    event_data: dict[str, Any],
    *,
    called_tool_names: set[str],
    turn_contract: Any | None,
) -> bool:
    if "get_store_detail_tool" not in called_tool_names:
        return False
    if _contract_intent_value(turn_contract) not in _STORE_DETAIL_REPLACEMENT_ALLOWED_INTENTS:
        return False
    return _should_replace_vague_store_detail_quickreply(event_data)


_LISTCAR_SELECTION_NEEDLES: tuple[str, ...] = (
    "선택",
    "골라",
    "어떤 차량",
    "이 차량으로 진행",
    "차량을 확인해",
    "등록된 차량",
    "차량 목록",
)


def _looks_like_vehicle_selection_prompt(text: str | None) -> bool:
    normalized = (text or "").strip()
    return bool(normalized) and any(needle in normalized for needle in _LISTCAR_SELECTION_NEEDLES)
