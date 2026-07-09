"""Shared quickReply CTA registry and final-emission normalizer."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping
from urllib.parse import urlparse

from services.tstation.common.cta_urls import CTAUrls, rebase_tstation_url_to_origin


@dataclass(frozen=True)
class CTADefinition:
    cta_id: str
    label: str
    domain: str
    cta_action: str
    expected_behavior: str
    url: str | None = None
    source_intent: str | None = None
    expected_contract_intent: str | None = None
    allowed_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    forbidden_templates: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    fallback_behavior: str | None = None
    # Entry/navigation CTAs are off-context while the contract is waiting on a
    # required slot (e.g. vehicle selection) — the only valid chips on such a
    # turn are the pending answer itself (dynamic value chips) or none.
    blocked_during_slot_fill: bool = False


@dataclass(frozen=True)
class CTAValidationResult:
    result: str
    reason: str
    cta_id: str = ""
    cta_action: str = ""
    expected_behavior: str = ""
    expected_contract_intent: str = ""


_URL_CTA_DEFINITIONS: tuple[CTADefinition, ...] = (
    CTADefinition(
        cta_id="member.benefit.open",
        label="회원 혜택 확인",
        domain="SUPPORT",
        cta_action="open_membership_benefit",
        expected_behavior="open_url",
        url=CTAUrls.MEMBERSHIP_BENEFIT,
    ),
    CTADefinition(
        cta_id="coupon.my_list.open",
        label="쿠폰함 바로가기",
        domain="TRANSACTION",
        cta_action="open_my_coupon_list",
        expected_behavior="open_url",
        url=CTAUrls.MY_COUPON_LIST_PC,
    ),
    CTADefinition(
        cta_id="coupon.my_list.open",
        label="내 쿠폰 확인",
        domain="TRANSACTION",
        cta_action="open_my_coupon_list",
        expected_behavior="open_url",
        url=CTAUrls.MY_COUPON_LIST_PC,
    ),
    CTADefinition(
        cta_id="order.history.open",
        label="주문 내역 확인",
        domain="TRANSACTION",
        cta_action="open_order_history",
        expected_behavior="open_url",
        url=CTAUrls.ORDER_HISTORY,
    ),
    CTADefinition(
        cta_id="order.history.open",
        label="주문 내역 보기",
        domain="TRANSACTION",
        cta_action="open_order_history",
        expected_behavior="open_url",
        url=CTAUrls.ORDER_HISTORY,
    ),
    CTADefinition(
        cta_id="cart.open",
        label="장바구니 확인",
        domain="TRANSACTION",
        cta_action="open_cart",
        expected_behavior="open_url",
        url=CTAUrls.CART,
    ),
    CTADefinition(
        cta_id="warranty.main.open",
        label="나의 워런티 확인",
        domain="SUPPORT",
        cta_action="open_warranty_main",
        expected_behavior="open_url",
        url=CTAUrls.WARRANTY_MAIN,
    ),
    CTADefinition(
        cta_id="warranty.ease_detail.open",
        label="안심서비스 상세",
        domain="SUPPORT",
        cta_action="open_warranty_ease_detail",
        expected_behavior="open_url",
        url=CTAUrls.WARRANTY_EASE_DETAIL,
    ),
    CTADefinition(
        cta_id="promotion.event.open",
        label="진행 중인 이벤트 보기",
        domain="DISCOVERY",
        cta_action="open_promotion_event_list",
        expected_behavior="open_url",
        url=CTAUrls.PROMOTION_EVENT_LIST,
    ),
    CTADefinition(
        cta_id="promotion.event.open",
        label="진행 중인 이벤트",
        domain="DISCOVERY",
        cta_action="open_promotion_event_list",
        expected_behavior="open_url",
        url=CTAUrls.PROMOTION_EVENT_LIST,
    ),
    CTADefinition(
        cta_id="promotion.deal.open",
        label="진행 중인 기획전",
        domain="DISCOVERY",
        cta_action="open_promotion_deal_list",
        expected_behavior="open_url",
        url=CTAUrls.PROMOTION_DEAL_LIST,
    ),
    CTADefinition(
        cta_id="promotion.past_event.open",
        label="지난 이벤트 보기",
        domain="DISCOVERY",
        cta_action="open_promotion_past_event_list",
        expected_behavior="open_url",
        url=CTAUrls.PROMOTION_PAST_EVENT_LIST,
    ),
    CTADefinition(
        cta_id="promotion.past_event.open",
        label="종료된 이벤트 보기",
        domain="DISCOVERY",
        cta_action="open_promotion_past_event_list",
        expected_behavior="open_url",
        url=CTAUrls.PROMOTION_PAST_EVENT_LIST,
    ),
    CTADefinition(
        cta_id="tire.check.open",
        label="마모도 측정 서비스",
        domain="TRANSACTION",
        cta_action="open_tire_check",
        expected_behavior="open_url",
        url=CTAUrls.TIRE_CHECK,
    ),
    CTADefinition(
        cta_id="tire.check_result.open",
        label="마모도 측정 결과",
        domain="TRANSACTION",
        cta_action="open_tire_check_result_list",
        expected_behavior="open_url",
        url=CTAUrls.TIRE_CHECK_RESULT_LIST,
    ),
    CTADefinition(
        cta_id="smart_pickup.open",
        label="픽업서비스 신청",
        domain="SUPPORT",
        cta_action="open_smart_pickup",
        expected_behavior="open_url",
        url=CTAUrls.SMART_PICKUP,
    ),
    CTADefinition(
        cta_id="smart_pickup.list.open",
        label="픽업서비스 내역",
        domain="SUPPORT",
        cta_action="open_smart_pickup_list",
        expected_behavior="open_url",
        url=CTAUrls.SMART_PICKUP_LIST,
    ),
    CTADefinition(
        cta_id="service_history.open",
        label="정비이력보기",
        domain="SUPPORT",
        cta_action="open_store_service_history",
        expected_behavior="open_url",
        url=CTAUrls.STORE_SERVICE_HISTORY,
    ),
    CTADefinition(
        cta_id="service_history.open",
        label="매장서비스 내역",
        domain="SUPPORT",
        cta_action="open_store_service_history",
        expected_behavior="open_url",
        url=CTAUrls.STORE_SERVICE_HISTORY,
    ),
    CTADefinition(
        cta_id="goods_review.open",
        label="상품 리뷰",
        domain="SUPPORT",
        cta_action="open_goods_review",
        expected_behavior="open_url",
        url=CTAUrls.GOODS_REVIEW,
    ),
    CTADefinition(
        cta_id="goods_review.open",
        label="리뷰관리 보기",
        domain="SUPPORT",
        cta_action="open_goods_review",
        expected_behavior="open_url",
        url=CTAUrls.GOODS_REVIEW,
    ),
    CTADefinition(
        cta_id="keep_service_history.open",
        label="보관 서비스 이력",
        domain="SUPPORT",
        cta_action="open_keep_service_history",
        expected_behavior="open_url",
        url=CTAUrls.KEEP_SERVICE_HIST,
    ),
    CTADefinition(
        cta_id="maintenance.reminding_alarm.open",
        label="점검/교체 알림",
        domain="SUPPORT",
        cta_action="open_reminding_alarm",
        expected_behavior="open_url",
        url=CTAUrls.REMINDING_ALARM,
    ),
    CTADefinition(
        cta_id="membership.dashboard.open",
        label="all my T 점검",
        domain="SUPPORT",
        cta_action="open_membership_dashboard",
        expected_behavior="open_url",
        url=CTAUrls.MEMBERSHIP_DASHBOARD,
    ),
    CTADefinition(
        cta_id="support.qna.open",
        label="1:1 문의하기",
        domain="SUPPORT",
        cta_action="open_qna",
        expected_behavior="conversation_action",
        expected_contract_intent="human_escalation",
        allowed_tools=("transfer_to_qna_tool",),
        fallback_behavior="ask_escalation_confirmation",
    ),
    CTADefinition(
        cta_id="support.qna.open",
        label="상담사 연결",
        domain="SUPPORT",
        cta_action="open_qna",
        expected_behavior="conversation_action",
        expected_contract_intent="human_escalation",
        allowed_tools=("transfer_to_qna_tool",),
        fallback_behavior="ask_escalation_confirmation",
    ),
)

_OWNED_VEHICLE_SELECT_LABELS: tuple[str, ...] = (
    "내 차량으로 확인",
    "내 차량 보기",
    "보유차량 중 선택",
    "내 차로 찾기",
    "내 차 검색",
    "내차검색",
)

_CONVERSATION_CTA_DEFINITIONS: tuple[CTADefinition, ...] = (
    *(
        CTADefinition(
            cta_id="owned_vehicle.select",
            label=label,
            domain="DISCOVERY",
            cta_action="select_owned_vehicle",
            expected_behavior="conversation_action",
            expected_contract_intent="vehicle_lookup",
            allowed_tools=("get_my_cars_tool", "get_user_vehicles_tool"),
            fallback_behavior="ask_vehicle_or_size_again",
        )
        for label in _OWNED_VEHICLE_SELECT_LABELS
    ),
    CTADefinition(
        cta_id="discovery.recommendation.start",
        label="타이어 추천",
        domain="DISCOVERY",
        cta_action="start_tire_recommendation",
        blocked_during_slot_fill=True,
        expected_behavior="conversation_action",
        expected_contract_intent="product_recommendation",
        allowed_tools=("get_products_recommendations_tool",),
        fallback_behavior="ask_vehicle_or_size_again",
    ),
    CTADefinition(
        cta_id="discovery.recommendation.start",
        label="타이어 추천 받기",
        domain="DISCOVERY",
        cta_action="start_tire_recommendation",
        blocked_during_slot_fill=True,
        expected_behavior="conversation_action",
        expected_contract_intent="product_recommendation",
        allowed_tools=("get_products_recommendations_tool",),
        fallback_behavior="ask_vehicle_or_size_again",
    ),
    CTADefinition(
        cta_id="discovery.recommendation.start",
        label="다른 추천 받기",
        domain="DISCOVERY",
        cta_action="start_tire_recommendation",
        blocked_during_slot_fill=True,
        expected_behavior="conversation_action",
        expected_contract_intent="product_recommendation",
        allowed_tools=("get_products_recommendations_tool",),
        fallback_behavior="ask_vehicle_or_size_again",
    ),
    CTADefinition(
        cta_id="discovery.product_search.start",
        label="상품 검색",
        domain="DISCOVERY",
        cta_action="start_product_search",
        blocked_during_slot_fill=True,
        expected_behavior="conversation_action",
        expected_contract_intent="product_search",
        allowed_tools=("search_product_tool",),
        fallback_behavior="ask_product_keyword",
    ),
    CTADefinition(
        cta_id="order.reservation.lookup",
        label="내 예약 조회",
        domain="TRANSACTION",
        cta_action="lookup_my_reservations",
        expected_behavior="conversation_action",
        expected_contract_intent="reservation_status_lookup",
        allowed_tools=("get_my_reservations_tool",),
        fallback_behavior="ask_reservation_identifier",
    ),
    CTADefinition(
        cta_id="store.search.start",
        label="매장 찾기",
        domain="TRANSACTION",
        cta_action="start_store_search",
        blocked_during_slot_fill=True,
        expected_behavior="conversation_action",
        expected_contract_intent="store_search",
        allowed_tools=("search_stores_tool", "get_store_list_tool", "get_nearby_stores_tool"),
        fallback_behavior="ask_region_again",
    ),
    CTADefinition(
        cta_id="store.search.other",
        label="다른 매장 찾기",
        domain="TRANSACTION",
        cta_action="search_other_store",
        expected_behavior="conversation_action",
        expected_contract_intent="stock_store_search",
        allowed_tools=("search_stores_tool", "get_store_list_tool", "transaction_store_preview_tool"),
        fallback_behavior="ask_region_again",
    ),
    CTADefinition(
        cta_id="store.search.other",
        label="다른 매장 보기",
        domain="TRANSACTION",
        cta_action="search_other_store",
        expected_behavior="conversation_action",
        expected_contract_intent="stock_store_search",
        allowed_tools=("search_stores_tool", "get_store_list_tool", "transaction_store_preview_tool"),
        fallback_behavior="ask_region_again",
    ),
    CTADefinition(
        cta_id="reservation.date.change",
        label="다른 날짜 확인",
        domain="TRANSACTION",
        cta_action="enter_date",
        expected_behavior="conversation_action",
        expected_contract_intent="store_schedule",
        allowed_tools=("get_store_schedule_tool", "get_multi_store_schedule_tool"),
        fallback_behavior="ask_date_again",
    ),
    CTADefinition(
        cta_id="purchase.start",
        label="구매하기",
        domain="TRANSACTION",
        cta_action="start_purchase",
        expected_behavior="conversation_action",
        expected_contract_intent="quick_order_reservation",
        allowed_tools=("transaction_store_preview_tool", "quick_order_tool"),
        fallback_behavior="ask_missing_purchase_slots",
    ),
    CTADefinition(
        cta_id="purchase.start",
        label="주문하기",
        domain="TRANSACTION",
        cta_action="start_purchase",
        expected_behavior="conversation_action",
        expected_contract_intent="quick_order_reservation",
        allowed_tools=("transaction_store_preview_tool", "quick_order_tool"),
        fallback_behavior="ask_missing_purchase_slots",
    ),
    CTADefinition(
        cta_id="cart.add",
        label="장바구니에 담기",
        domain="TRANSACTION",
        cta_action="add_to_cart",
        expected_behavior="conversation_action",
        expected_contract_intent="quick_order_reservation",
        allowed_tools=("save_to_cart_tool",),
        fallback_behavior="ask_missing_cart_slots",
    ),
    CTADefinition(
        cta_id="cart.add",
        label="장바구니담기",
        domain="TRANSACTION",
        cta_action="add_to_cart",
        expected_behavior="conversation_action",
        expected_contract_intent="quick_order_reservation",
        allowed_tools=("save_to_cart_tool",),
        fallback_behavior="ask_missing_cart_slots",
    ),
    CTADefinition(
        cta_id="cart.add",
        label="장바구니 담기",
        domain="TRANSACTION",
        cta_action="add_to_cart",
        expected_behavior="conversation_action",
        expected_contract_intent="quick_order_reservation",
        allowed_tools=("save_to_cart_tool",),
        fallback_behavior="ask_missing_cart_slots",
    ),
    CTADefinition(
        cta_id="cart.check",
        label="장바구니 확인",
        domain="TRANSACTION",
        cta_action="open_cart",
        expected_behavior="open_url",
        url=CTAUrls.CART,
    ),
)

_DEFINITIONS_BY_LABEL: dict[str, CTADefinition] = {
    definition.label: definition
    for definition in (*_URL_CTA_DEFINITIONS, *_CONVERSATION_CTA_DEFINITIONS)
}

_DYNAMIC_SIZE_RE = re.compile(r"^\s*\d{3}\s*/\s*\d{2}\s*R\s*\d{2}\s*$", re.IGNORECASE)
_DYNAMIC_QTY_RE = re.compile(r"^\s*[1-4]\s*(?:개|본)\s*$")
_DYNAMIC_ORDER_RE = re.compile(r"(?:주문|예약)?\s*[0-9]{4,}\s*(?:번|건)?")
_DYNAMIC_CAR_NO_RE = re.compile(r"^\s*\d{2,3}[가-힣]\s*\d{4}\s*$")


def _url_path(url: str | None) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    return urlparse(raw).path.rstrip("/")


_DEFINITIONS_BY_URL_PATH: dict[str, CTADefinition] = {
    _url_path(definition.url): definition
    for definition in _URL_CTA_DEFINITIONS
    if definition.url
}


def _context_value(context: Mapping[str, Any], key: str) -> Any:
    value = context.get(key)
    if value not in (None, ""):
        return value
    snake = re.sub(r"(?<!^)([A-Z])", r"_\1", key).lower()
    return context.get(snake)


def _definition_for_chip(chip: Mapping[str, Any]) -> CTADefinition | None:
    label = str(chip.get("label") or "").strip()
    definition = _DEFINITIONS_BY_LABEL.get(label)
    if definition is not None:
        return definition
    url_path = _url_path(str(chip.get("url") or ""))
    if url_path:
        return _DEFINITIONS_BY_URL_PATH.get(url_path)
    return None


def _dynamic_definition_for_chip(chip: Mapping[str, Any]) -> CTADefinition | None:
    label = str(chip.get("label") or "").strip()
    metadata = chip.get("metadata") if isinstance(chip.get("metadata"), Mapping) else {}
    dynamic_type = str(metadata.get("dynamic_type") or metadata.get("cta_type") or "").strip()
    if dynamic_type:
        cta_type = dynamic_type
    elif _DYNAMIC_SIZE_RE.fullmatch(label):
        cta_type = "dynamic_tire_size"
    elif _DYNAMIC_QTY_RE.fullmatch(label):
        cta_type = "dynamic_quantity"
    elif _DYNAMIC_ORDER_RE.fullmatch(label):
        cta_type = "dynamic_order_candidate"
    elif _DYNAMIC_CAR_NO_RE.fullmatch(label):
        cta_type = "dynamic_vehicle_candidate"
    elif str(chip.get("domain") or "").upper() == "TRANSACTION" and label.endswith(("점", "센터")):
        cta_type = "dynamic_store_candidate"
    else:
        return None
    return CTADefinition(
        cta_id=f"dynamic.{cta_type}",
        label=label,
        domain=str(chip.get("domain") or "").upper(),
        cta_action="select_dynamic_choice",
        expected_behavior="dynamic_choice",
        expected_contract_intent=str(metadata.get("expected_contract_intent") or ""),
    )


def _definition_payload(definition: CTADefinition, *, source_intent: str) -> dict[str, Any]:
    payload = {
        "cta_id": definition.cta_id,
        "cta_action": definition.cta_action,
        "expected_behavior": definition.expected_behavior,
        "source_intent": definition.source_intent or source_intent,
        "expected_contract_intent": definition.expected_contract_intent or "",
        "expected_behavior_version": "cta_registry_v1",
    }
    if definition.allowed_tools:
        payload["allowed_tools"] = list(definition.allowed_tools)
    if definition.forbidden_tools:
        payload["forbidden_tools"] = list(definition.forbidden_tools)
    if definition.required_context:
        payload["required_context"] = list(definition.required_context)
    if definition.fallback_behavior:
        payload["fallback_behavior"] = definition.fallback_behavior
    return payload


def _validate_definition(
    chip: Mapping[str, Any],
    definition: CTADefinition,
    *,
    current_template: str,
    contract: Any | None,
    context: Mapping[str, Any],
) -> CTAValidationResult:
    if definition.expected_behavior == "open_url" and not str(chip.get("url") or definition.url or "").strip():
        return CTAValidationResult("blocked", "open_url_missing_url", definition.cta_id, definition.cta_action)
    if (
        definition.expected_behavior == "conversation_action"
        and not definition.expected_contract_intent
        and definition.cta_id != "support.qna.open"
    ):
        return CTAValidationResult("blocked", "conversation_cta_missing_expected_contract", definition.cta_id)
    if current_template in definition.forbidden_templates:
        return CTAValidationResult("blocked", f"template_forbidden:{current_template}", definition.cta_id)
    if definition.blocked_during_slot_fill and contract is not None:
        blocking_slots = tuple(getattr(contract, "blocking_required_slots", ()) or ())
        contract_intent = str(getattr(contract, "intent", "") or "")
        if blocking_slots or contract_intent == "vehicle_lookup":
            return CTAValidationResult(
                "blocked",
                "blocked_during_slot_fill",
                definition.cta_id,
                definition.cta_action,
                definition.expected_behavior,
                definition.expected_contract_intent or "",
            )
    missing_context = [
        key for key in definition.required_context
        if _context_value(context, key) in (None, "")
    ]
    if missing_context:
        return CTAValidationResult(
            "blocked",
            f"missing_context:{','.join(missing_context)}",
            definition.cta_id,
            definition.cta_action,
            definition.expected_behavior,
            definition.expected_contract_intent or "",
        )
    if contract is not None:
        forbidden_tools = set(str(tool) for tool in getattr(contract, "forbidden_tools", ()) or ())
        current_intents = {
            str(getattr(contract, "intent", "") or "").strip(),
            str(getattr(contract, "sub_intent", "") or "").strip(),
        }
        next_turn_purchase_from_product_description = (
            definition.cta_id == "purchase.start"
            and definition.expected_contract_intent == "quick_order_reservation"
            and bool(current_intents & {"product_description", "product_detail_lookup", "product_name_search"})
        )
        blocked_tools = [
            tool
            for tool in definition.allowed_tools
            if tool in forbidden_tools and not next_turn_purchase_from_product_description
        ]
        if blocked_tools:
            return CTAValidationResult(
                "blocked",
                f"tool_forbidden:{','.join(blocked_tools)}",
                definition.cta_id,
                definition.cta_action,
                definition.expected_behavior,
                definition.expected_contract_intent or "",
            )
    return CTAValidationResult(
        "allowed",
        "cta_contract_validated",
        definition.cta_id,
        definition.cta_action,
        definition.expected_behavior,
        definition.expected_contract_intent or "",
    )


_PREANNOTATED_ACTION_KEYS: tuple[str, ...] = ("actionId", "action_id", "intentKey", "intent_key", "cta_action")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]{1,120})\]\((https?://[^)\s]+)\)")
_BARE_URL_RE = re.compile(r"https?://[^\s)>\]]+")


def _has_preannotated_action(chip: Mapping[str, Any]) -> bool:
    metadata = chip.get("metadata") if isinstance(chip.get("metadata"), Mapping) else {}
    return any(
        str(chip.get(key) or "").strip() or str(metadata.get(key) or "").strip()
        for key in _PREANNOTATED_ACTION_KEYS
    )


def _strip_duplicate_cta_links_from_answer(answer: str, chips: list[Any]) -> str:
    cta_url_paths: set[str] = set()
    for chip in chips:
        if not isinstance(chip, Mapping):
            continue
        url_path = _url_path(str(chip.get("url") or ""))
        if not url_path:
            continue
        cta_url_paths.add(url_path)
    cta_url_paths.discard("")
    if not answer or not cta_url_paths:
        return answer

    def markdown_repl(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        url_path = _url_path(match.group(2))
        return label if url_path not in cta_url_paths else ""

    sanitized = _MARKDOWN_LINK_RE.sub(markdown_repl, answer)
    sanitized = _BARE_URL_RE.sub(
        lambda match: "" if _url_path(match.group(0)) in cta_url_paths else match.group(0),
        sanitized,
    )
    lines = [line.rstrip() for line in sanitized.splitlines()]
    return "\n".join(line for line in lines if line.strip())


def normalize_quickreply_ctas(
    event: dict[str, Any],
    *,
    contract: Any | None = None,
    source_intent: str | None = None,
) -> bool:
    """Attach CTA action contracts to quickReply chips and drop non-executable chips.

    A chip survives only when it resolves to a validated registry/dynamic CTA,
    carries a direct URL, or is pre-annotated with action metadata by a code
    builder. Label-only chips with no executable action are dropped; an empty
    quickReplies list is a valid outcome.
    """

    if not isinstance(event, dict) or event.get("template") != "quickReply":
        return False
    data = event.get("data")
    if not isinstance(data, dict):
        return False
    chips = data.get("quickReplies")
    if not isinstance(chips, list):
        return False
    current_template = str(event.get("template") or "")
    current_intent = str(source_intent or getattr(contract, "intent", "") or "")
    event_metadata = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}

    changed = False
    normalized: list[Any] = []
    audit: list[dict[str, Any]] = []
    for raw_chip in chips:
        if not isinstance(raw_chip, dict):
            changed = True
            continue
        chip = dict(raw_chip)
        definition = _definition_for_chip(chip) or _dynamic_definition_for_chip(chip)
        if definition is None:
            if str(chip.get("url") or "").strip():
                keep_reason = "unregistered_url_action"
            elif _has_preannotated_action(chip):
                keep_reason = "preannotated_action_metadata"
            else:
                keep_reason = None
            audit.append({
                "label": chip.get("label"),
                "cta_id": "",
                "cta_action": str(chip.get("cta_action") or "").strip(),
                "expected_behavior": "open_url" if keep_reason == "unregistered_url_action" else "",
                "expected_contract_intent": "",
                "result": "allowed" if keep_reason else "dropped",
                "reason": keep_reason or "no_executable_action",
            })
            if keep_reason:
                normalized.append(chip)
            else:
                changed = True
            continue
        if not chip.get("domain") and definition.domain:
            chip["domain"] = definition.domain
        if definition.expected_behavior == "open_url" and not chip.get("url") and definition.url:
            chip["url"] = definition.url
        chip_metadata = chip.get("metadata") if isinstance(chip.get("metadata"), Mapping) else {}
        merged_context = {**dict(event_metadata), **dict(chip_metadata)}
        validation = _validate_definition(
            chip,
            definition,
            current_template=current_template,
            contract=contract,
            context=merged_context,
        )
        audit.append({
            "label": chip.get("label"),
            "cta_id": validation.cta_id or definition.cta_id,
            "cta_action": validation.cta_action or definition.cta_action,
            "expected_behavior": validation.expected_behavior or definition.expected_behavior,
            "expected_contract_intent": (
                validation.expected_contract_intent or definition.expected_contract_intent or ""
            ),
            "result": validation.result,
            "reason": validation.reason,
        })
        if validation.result != "allowed":
            changed = True
            continue
        next_metadata = {
            **dict(chip_metadata),
            **_definition_payload(definition, source_intent=current_intent),
            "actual_contract_intent": current_intent,
            "cta_validation_result": validation.result,
            "cta_validation_reason": validation.reason,
        }
        if definition.expected_behavior == "dynamic_choice":
            next_metadata.setdefault("dynamic_value", chip.get("label"))
        chip["metadata"] = next_metadata
        chip["cta_id"] = definition.cta_id
        chip["cta_action"] = definition.cta_action
        chip["expected_behavior"] = definition.expected_behavior
        if definition.expected_contract_intent:
            chip["expected_contract_intent"] = definition.expected_contract_intent
        normalized.append(chip)
        changed = changed or chip != raw_chip

    if changed:
        data["quickReplies"] = normalized
    assistant_response = data.get("assistantResponse")
    if isinstance(assistant_response, str):
        sanitized_response = _strip_duplicate_cta_links_from_answer(assistant_response, normalized)
        if sanitized_response != assistant_response:
            data["assistantResponse"] = sanitized_response
            changed = True
    rebased_normalized: list[Any] = []
    rebased_changed = False
    for chip in normalized:
        if not isinstance(chip, dict):
            rebased_normalized.append(chip)
            continue
        next_chip = dict(chip)
        url = str(next_chip.get("url") or "").strip()
        rebased_url = rebase_tstation_url_to_origin(url)
        if url and rebased_url != url:
            next_chip["url"] = rebased_url
            rebased_changed = True
        rebased_normalized.append(next_chip)
    if rebased_changed:
        normalized = rebased_normalized
        changed = True
    if changed:
        data["quickReplies"] = normalized
    if audit:
        metadata = data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            data["metadata"] = metadata
        metadata["cta_validation_result"] = "allowed" if all(item["result"] == "allowed" for item in audit) else "mixed"
        metadata["cta_validation"] = audit
        metadata["cta_registry_version"] = "cta_registry_v1"
        metadata["actual_contract_intent"] = current_intent
    return changed or bool(audit)


def cta_trace_metadata(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize emitted CTA metadata for Langfuse trace metadata."""

    ctas: list[dict[str, Any]] = []
    for event in events:
        data = event.get("data") if isinstance(event, Mapping) else None
        if not isinstance(data, Mapping):
            continue
        for chip in data.get("quickReplies") or []:
            if not isinstance(chip, Mapping):
                continue
            metadata = chip.get("metadata") if isinstance(chip.get("metadata"), Mapping) else {}
            cta_id = str(chip.get("cta_id") or metadata.get("cta_id") or "").strip()
            if not cta_id:
                continue
            ctas.append({
                "label": chip.get("label"),
                "cta_id": cta_id,
                "cta_action": chip.get("cta_action") or metadata.get("cta_action"),
                "expected_behavior": chip.get("expected_behavior") or metadata.get("expected_behavior"),
                "source_intent": metadata.get("source_intent"),
                "expected_contract_intent": (
                    chip.get("expected_contract_intent") or metadata.get("expected_contract_intent")
                ),
                "actual_contract_intent": metadata.get("actual_contract_intent"),
                "validation_result": metadata.get("cta_validation_result"),
                "validation_reason": metadata.get("cta_validation_reason"),
            })
    if not ctas:
        return {}
    return {
        "ctas": ctas[:10],
        "cta_id": ctas[0].get("cta_id"),
        "cta_action": ctas[0].get("cta_action"),
        "expected_behavior": ctas[0].get("expected_behavior"),
        "expected_contract_intent": ctas[0].get("expected_contract_intent"),
        "actual_contract_intent": ctas[0].get("actual_contract_intent"),
        "cta_validation_result": ctas[0].get("validation_result"),
        "cta_validation_reason": ctas[0].get("validation_reason"),
    }
