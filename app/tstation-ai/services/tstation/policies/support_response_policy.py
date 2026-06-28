"""Deterministic response policy for Support/FAQ/escalation flows."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from langchain_core.messages import HumanMessage

from services.tstation.common.cta_urls import CTAUrls
from services.tstation.policies.policy_text_matchers import is_general_card_cancel_timing_policy_query
from services.tstation.policies.response_decision import ResponseDecision, ResponseShape, TemplateName


_RESERVATION_INSTALLATION_POLICY = "reservation_installation_policy"
_PAYMENT_REFUND_POLICY = "payment_refund_policy"
_ASSURANCE_WARRANTY_POLICY = "assurance_warranty_policy"
_BENEFIT_PROMOTION_POLICY = "benefit_promotion_policy"
_PRODUCT_CONDITION_POLICY = "product_condition_policy"
_PURCHASE_ORDER_POLICY = "purchase_order_policy"
_SUPPORT_FAQ_POLICY_GROUP_INTENTS = frozenset({
    "general_cancel_fee_policy",
    "general_card_cancel_timing_policy",
    "reservation_window_policy",
    "payment_error_troubleshooting",
    "tire_manufacture_date_policy",
    "tire_quality_warranty_policy",
    "assurance_service_policy",
    "reservation_policy_guidance",
    "installation_work_policy",
    "external_tire_install_policy",
    "promotion_gift_policy",
    "tire_condition_photo_policy",
})
_RESERVATION_RE = re.compile(r"예약|방문|장착(?:\s*예약)?|오후\s*\d+시|당일", re.IGNORECASE)
_ORDER_RE = re.compile(r"주문|결제|카드|승인|배송|온라인", re.IGNORECASE)
_CANCEL_RE = re.compile(r"취소|환불|철회", re.IGNORECASE)
_FEE_RE = re.compile(r"위약금|수수료|공임비|비용|차감", re.IGNORECASE)
_STORE_CHANGE_RE = re.compile(r"장착점|지점|매장|방문\s*지점", re.IGNORECASE)
_CHANGE_RE = re.compile(r"변경|바꿀|바꾸|옮길|이동", re.IGNORECASE)
_WORK_STARTED_RE = re.compile(
    r"작업\s*시작|작업\s*중|이미\s*장착|장착\s*중|기존\s*타이어.{0,8}(?:다\s*뺐|탈거|분리)|탈거|분리|장착\s*작업",
    re.IGNORECASE,
)
_EXTERNAL_TIRE_INSTALL_POLICY_RE = re.compile(
    r"인터넷(?:에서)?\s*(?:산|구매한)|외부\s*구매|사제\s*타이어|"
    r"가져가(?:서)?\s*장착|반입\s*장착|들고\s*가(?:서)?\s*장착|"
    r"공임만\s*받고\s*장착|타이어만\s*장착|타이어만\s*(?:가져가|들고가)",
    re.IGNORECASE,
)
_ONLINE_ORDER_CANCEL_RE = re.compile(
    r"결제\s*완료\s*주문|온라인몰|주문\s*취소|취소\s*수수료|타이어\s*(?:개당|1개당)|개당\s*1만\s*원|배송\s*(?:현황|상태|진행)",
    re.IGNORECASE,
)
_PAYMENT_ERROR_RE = re.compile(
    r"결제\s*(?:오류|에러|실패|안\s*돼|안\s*되|안\s*열)|결제창|결제\s*화면|승인\s*실패|장착일\s*선택란",
    re.IGNORECASE,
)
_CARD_INSTALLMENT_LOOKUP_RE = re.compile(
    r"무이자|할부|몇\s*개?월|[0-9]{1,2}\s*개?월|개월수|카드사별|현대카드|신한카드|삼성카드|국민카드|"
    r"롯데카드|하나카드|농협카드|우리카드|비씨카드|BC카드|스마트\s*페이|smart\s*pay|smartpay",
    re.IGNORECASE,
)
_ASSURANCE_DOCUMENT_LOST_RE = re.compile(r"보증서.{0,12}(분실|잃어버|없어)|종이\s*보증서", re.IGNORECASE)
_PROMOTION_PARTIAL_CANCEL_RE = re.compile(
    r"부분\s*취소|[0-9]+\s*(?:짝|개)\s*취소|반납|차감|돌려줘야",
    re.IGNORECASE,
)
_WRONG_ITEM_RE = re.compile(
    r"다른\s*(?:타이어|상품).{0,12}(왔|도착)|오배송|잘못\s*온|규격.{0,8}(안\s*맞|다르)|맞지\s*않",
    re.IGNORECASE,
)
_SUPPORT_FACT_TYPE_TO_BUCKET: dict[tuple[str, str], str] = {
    (_RESERVATION_INSTALLATION_POLICY, "visit_reservation_cancel"): "visit_reservation_cancel_policy",
    (_RESERVATION_INSTALLATION_POLICY, "store_change"): "reservation_store_change_policy",
    (_RESERVATION_INSTALLATION_POLICY, "work_started_cancel"): "work_started_cancel_fee_policy",
    (_PURCHASE_ORDER_POLICY, "online_order_cancel_fee"): "online_order_cancel_fee_policy",
    (_PAYMENT_REFUND_POLICY, "card_cancel_timing"): "card_cancel_timing_policy",
}
_SUPPORT_FAQ_SOURCE_MIN_SCORE_BY_INTENT: dict[str, float] = {
    "tire_manufacture_date_policy": 0.2,
    "tire_quality_warranty_policy": 0.2,
    "general_card_cancel_timing_policy": 0.18,
    "reservation_policy_guidance": 0.18,
    "reservation_window_policy": 0.18,
    "external_tire_install_policy": 0.18,
    "general_cancel_fee_policy": 0.18,
}
_SUPPORT_FAQ_SOURCE_SCORE_GAP_BY_INTENT: dict[str, float] = {
    "tire_manufacture_date_policy": 0.04,
    "tire_quality_warranty_policy": 0.04,
    "general_card_cancel_timing_policy": 0.03,
    "reservation_policy_guidance": 0.03,
    "reservation_window_policy": 0.03,
    "external_tire_install_policy": 0.03,
    "general_cancel_fee_policy": 0.03,
}
_SUPPORT_FAQ_SOURCE_GROUNDED_ALLOWLIST = frozenset({
    "general_cancel_fee_policy",
    "general_card_cancel_timing_policy",
    "reservation_window_policy",
    "external_tire_install_policy",
    "reservation_policy_guidance",
    "tire_manufacture_date_policy",
    "tire_quality_warranty_policy",
})
_SUPPORT_FAQ_LLM_GROUNDED_ALLOWLIST = frozenset(_SUPPORT_FAQ_SOURCE_GROUNDED_ALLOWLIST | {
    "assurance_service_policy",
    "payment_error_troubleshooting",
})
_SUPPORT_FAQ_RETRIEVAL_TOP_K = 8
_SUPPORT_FAQ_MAX_LLM_EVIDENCE = 4
_SUPPORT_FAQ_LLM_RETRY_LIMIT = 1
_SUPPORT_FAQ_SCOPE_TO_EVIDENCE_TYPES: dict[str, tuple[str, ...]] = {
    "fee_or_penalty": (
        "reservation_cancel_method",
        "online_order_cancel_fee",
        "delivered_item_return_fee",
        "installation_work_fee",
        "promotion_gift_partial_cancel",
    ),
    "cancel_method": ("reservation_cancel_method",),
    "refund_timing": ("card_refund_timing",),
    "delivery_stage": ("online_order_cancel_fee", "delivered_item_return_fee"),
    "work_started": ("installation_work_fee",),
    "store_change": ("store_change_policy",),
    "reservation_window": (
        "reservation_window_limit",
        "advance_booking_not_supported",
        "reservation_required_with_purchase",
    ),
    "external_tire_install": (
        "external_tire_install_restriction",
        "online_purchase_install_flow",
        "store_specific_install_fee",
    ),
    "warranty_condition": ("warranty_condition",),
    "manufacture_date_policy": ("manufacture_date_policy",),
    "payment_error": ("payment_error_troubleshooting",),
    "promotion_condition": ("promotion_gift_partial_cancel", "promotion_gift_policy_general"),
    "document_status": ("assurance_document_lost",),
}
_ALLOWED_CATEGORY_NAMES_BY_POLICY_GROUP: dict[str, tuple[tuple[str, str], ...]] = {
    _RESERVATION_INSTALLATION_POLICY: (("배송/장착", "장착"), ("상품/서비스", "서비스")),
    _PAYMENT_REFUND_POLICY: (("주문/결제", "결제"),),
    _ASSURANCE_WARRANTY_POLICY: (("상품/서비스", "서비스"), ("상품/서비스", "상품")),
    _BENEFIT_PROMOTION_POLICY: (("혜택/프로모션", "프로모션"), ("혜택/프로모션", "쿠폰"), ("회원", "회원가입")),
    _PRODUCT_CONDITION_POLICY: (("상품/서비스", "상품"), ("상품/서비스", "서비스")),
    _PURCHASE_ORDER_POLICY: (("주문/결제", "주문"), ("주문/결제", "결제")),
}
_ALLOWED_CATEGORY_CODES_BY_POLICY_GROUP: dict[str, tuple[tuple[str, str], ...]] = {
    _RESERVATION_INSTALLATION_POLICY: (("C01", "C0106"), ("C03", "C0302")),
    _PAYMENT_REFUND_POLICY: (("C01", "C0105"),),
    _ASSURANCE_WARRANTY_POLICY: (("C03", "C0302"), ("C03", "C0301")),
    _BENEFIT_PROMOTION_POLICY: (("C04", "C0401"), ("C04", "C0402"), ("C05", "C0501")),
    _PRODUCT_CONDITION_POLICY: (("C03", "C0301"), ("C03", "C0302")),
    _PURCHASE_ORDER_POLICY: (("C01", "C0104"), ("C01", "C0105")),
}


def _normalize_support_faq_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _support_faq_candidate_text(candidate: Mapping[str, Any]) -> str:
    parts = [
        _normalize_support_faq_text(candidate.get("question") or ""),
        _normalize_support_faq_text(
            candidate.get("answer")
            or candidate.get("pc_ans_cont")
            or candidate.get("content")
            or candidate.get("body")
            or ""
        ),
    ]
    return "\n".join(part for part in parts if part)


def _support_faq_candidates(tool_result: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(tool_result, Mapping):
        return []
    data = tool_result.get("data", tool_result)
    if isinstance(data, Mapping):
        items = data.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, Mapping)]
    return []


def _is_card_installment_lookup_query(text: str) -> bool:
    return bool(_CARD_INSTALLMENT_LOOKUP_RE.search(str(text or "")))


def _support_faq_candidate_score(candidate: Mapping[str, Any]) -> float | None:
    raw_score = candidate.get("score")
    if raw_score is None:
        return None
    try:
        return float(raw_score)
    except (TypeError, ValueError):
        return None


def _support_faq_candidate_categories(candidate: Mapping[str, Any]) -> tuple[str, str, str, str]:
    metadata = candidate.get("metadata")
    meta = metadata if isinstance(metadata, Mapping) else {}
    lv1 = _normalize_support_faq_text(
        meta.get("category_lv1")
        or meta.get("lrcl_nm")
        or meta.get("categoryLv1")
        or meta.get("large_category")
        or ""
    )
    lv2 = _normalize_support_faq_text(
        meta.get("category_lv2")
        or meta.get("mdcl_nm")
        or meta.get("categoryLv2")
        or meta.get("medium_category")
        or ""
    )
    code1 = _normalize_support_faq_text(meta.get("lrcl_cd") or meta.get("category_lv1_cd") or "")
    code2 = _normalize_support_faq_text(meta.get("mdcl_cd") or meta.get("category_lv2_cd") or "")
    return lv1, lv2, code1, code2


def _support_faq_candidate_topic(
    *,
    intent: str,
    policy_group: str,
    fact_type: str,
    candidate: Mapping[str, Any],
) -> str:
    lv1, lv2, _, _ = _support_faq_candidate_categories(candidate)
    category_topic = f"{lv1}>{lv2}".strip(">")
    if category_topic:
        return category_topic.lower()
    text = _support_faq_candidate_text(candidate).lower()
    if intent == "tire_manufacture_date_policy":
        if any(token in text for token in ("측면", "사이드월", "품질보증", "워런티")):
            return "warranty"
        if any(token in text for token in ("제조일자", "dot", "신품", "6개월", "12개월")):
            return "manufacture"
    if intent == "tire_quality_warranty_policy":
        if any(token in text for token in ("측면", "사이드월", "품질보증", "워런티")):
            return "warranty"
        if any(token in text for token in ("제조일자", "dot", "신품", "6개월", "12개월")):
            return "manufacture"
    if policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "mixed_cancel_fee_generalized":
        if re.search(r"카드|환불|승인\s*취소|영업일", text, re.IGNORECASE):
            return "card_refund"
        if _ONLINE_ORDER_CANCEL_RE.search(text):
            return "online_order_cancel"
        if _RESERVATION_RE.search(text):
            return "visit_reservation_cancel"
    return category_topic.lower() if category_topic else ""


def _support_faq_question_anchor_allowed(intent: str, text: str) -> bool:
    return bool(re.search(r"카드|환불|승인취소|승인\s*취소|반영|영업일|언제", text, re.IGNORECASE))


def _support_faq_split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return []
    parts = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+|(?<=요)\s+|(?<=다)\s+", normalized)
        if part.strip()
    ]
    return parts[:3]


def _support_faq_sentence_allowed(
    *,
    intent: str,
    user_text: str,
    policy_group: str,
    fact_type: str,
    sentence: str,
) -> bool:
    normalized_sentence = str(sentence or "").strip()
    if not normalized_sentence:
        return False
    if intent == "general_card_cancel_timing_policy":
        return bool(re.search(r"카드|환불|승인\s*취소|반영|영업일", normalized_sentence, re.IGNORECASE))
    if intent == "tire_manufacture_date_policy":
        return bool(re.search(r"제조일자|DOT|신품|개월|주차", normalized_sentence, re.IGNORECASE))
    if intent == "tire_quality_warranty_policy":
        return bool(re.search(r"측면|사이드월|부풀|보증|워런티|점검", normalized_sentence, re.IGNORECASE))
    if policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "mixed_cancel_fee_generalized":
        allow_reservation = bool(
            _RESERVATION_RE.search(normalized_sentence) and re.search(r"예약|방문|장착|매장", user_text, re.IGNORECASE)
        )
        allow_order = bool(
            _ONLINE_ORDER_CANCEL_RE.search(normalized_sentence) and re.search(r"결제|주문|온라인|배송", user_text, re.IGNORECASE)
        )
        allow_card = bool(
            re.search(r"카드|환불|승인\s*취소|반영|영업일", normalized_sentence, re.IGNORECASE)
            and _support_faq_question_anchor_allowed(intent, user_text)
        )
        return allow_reservation or allow_order or allow_card
    if policy_group == _PURCHASE_ORDER_POLICY and fact_type == "online_order_cancel_fee":
        return bool(_ONLINE_ORDER_CANCEL_RE.search(normalized_sentence) or re.search(r"취소|반품|수수료", normalized_sentence, re.IGNORECASE))
    if policy_group == _PAYMENT_REFUND_POLICY and fact_type == "payment_error_troubleshooting":
        return bool(_PAYMENT_ERROR_RE.search(normalized_sentence))
    return True


def _compact_support_faq_answer(
    *,
    intent: str,
    user_text: str,
    policy_group: str,
    fact_type: str,
    candidate: Mapping[str, Any],
) -> str:
    answer = _normalize_support_faq_text(
        candidate.get("answer")
        or candidate.get("pc_ans_cont")
        or candidate.get("content")
        or candidate.get("body")
        or ""
    )
    if not answer:
        return ""
    sentences = _support_faq_split_sentences(answer)
    kept = [
        sentence
        for sentence in sentences
        if _support_faq_sentence_allowed(
            intent=intent,
            user_text=user_text,
            policy_group=policy_group,
            fact_type=fact_type,
            sentence=sentence,
        )
    ]
    return "\n".join(kept[:3]).strip()


def _support_faq_ranked_candidates(candidates: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        candidate
        for _, candidate in sorted(
            enumerate(candidates),
            key=lambda item: (_support_faq_candidate_score(item[1]) is not None, _support_faq_candidate_score(item[1]) or 0.0, -item[0]),
            reverse=True,
        )
    ]


def _support_faq_grounded_competing_candidate(
    *,
    intent: str,
    user_text: str,
    top_candidate: Mapping[str, Any],
    candidates: list[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    for candidate in _support_faq_ranked_candidates(candidates):
        if candidate is top_candidate:
            continue
        if not _support_faq_question_anchor_allowed(intent, user_text) and _support_faq_candidate_matches_fact_type(
            "card_cancel_timing", candidate
        ):
            continue
        return candidate
    return None


def _support_faq_strip_card_refund_facts_for_non_anchor(
    *,
    intent: str,
    user_text: str,
    facts: dict[str, Any],
) -> dict[str, Any]:
    if _support_faq_question_anchor_allowed(intent, user_text):
        return facts
    stripped = dict(facts)
    stripped.pop("card_refund_timing", None)
    stripped.pop("cardRefundTiming", None)
    return stripped


def _classify_faq_evidence(
    candidate: Mapping[str, Any],
    *,
    policy_group: str,
    fact_type: str,
) -> str | None:
    text = _support_faq_candidate_text(candidate)
    if not text:
        return None
    if policy_group == _RESERVATION_INSTALLATION_POLICY:
        if _support_faq_candidate_matches_fact_type("external_tire_install", candidate):
            lowered_text = text.lower()
            if any(token in lowered_text for token in ("별도 수령", "직접 장착", "반입", "타이어만", "불가")):
                return "external_tire_install_restriction"
            if any(token in lowered_text for token in ("온라인몰", "지정 장착점", "발송")):
                return "online_purchase_install_flow"
            return "store_specific_install_fee"
        if _support_faq_candidate_matches_fact_type("work_started_cancel", candidate):
            return "installation_work_fee"
        if _support_faq_candidate_matches_fact_type("store_change", candidate):
            return "store_change_policy"
        if _support_faq_candidate_matches_fact_type("reservation_window", candidate):
            lowered_text = text.lower()
            if any(token in lowered_text for token in ("30일", "1개월", "한달", "한 달", "최대")):
                return "reservation_window_limit"
            if any(token in lowered_text for token in ("사전 구매", "사전구매", "지원하지 않", "불가")):
                return "advance_booking_not_supported"
            return "reservation_required_with_purchase"
        if _support_faq_candidate_matches_fact_type("online_order_cancel_fee", candidate):
            return "online_order_cancel_fee"
        if _support_faq_candidate_matches_fact_type("card_cancel_timing", candidate):
            return "card_refund_timing"
        if _support_faq_candidate_matches_fact_type("visit_reservation_cancel", candidate):
            return "reservation_cancel_method"
    if policy_group == _PURCHASE_ORDER_POLICY:
        if fact_type == "wrong_item_or_fitment_issue":
            return "delivered_item_return_fee"
        if _support_faq_candidate_matches_fact_type("online_order_cancel_fee", candidate):
            return "online_order_cancel_fee"
    if policy_group == _PAYMENT_REFUND_POLICY:
        if fact_type == "payment_error_troubleshooting":
            return "payment_error_troubleshooting"
        if _support_faq_candidate_matches_fact_type("card_cancel_timing", candidate):
            return "card_refund_timing"
    if policy_group == _ASSURANCE_WARRANTY_POLICY:
        if fact_type == "assurance_document_lost":
            return "assurance_document_lost"
        return "warranty_condition"
    if policy_group == _BENEFIT_PROMOTION_POLICY:
        if fact_type == "promotion_gift_partial_cancel":
            return "promotion_gift_partial_cancel"
        return "promotion_gift_policy_general"
    if policy_group == _PRODUCT_CONDITION_POLICY:
        if fact_type == "manufacture_date":
            return "manufacture_date_policy"
        return "warranty_condition"
    return None


def _infer_user_faq_scope(
    *,
    intent: str,
    user_text: str,
    policy_group: str,
    fact_type: str,
) -> dict[str, Any]:
    scopes: list[str] = []
    primary_evidence_types: list[str] = []
    supporting_evidence_types: list[str] = []
    text = str(user_text or "")
    has_refund_anchor = _support_faq_question_anchor_allowed(intent, text)

    if policy_group == _PAYMENT_REFUND_POLICY and fact_type == "card_cancel_timing":
        scopes.append("refund_timing")
        primary_evidence_types.append("card_refund_timing")
    elif policy_group == _PAYMENT_REFUND_POLICY and fact_type == "payment_error_troubleshooting":
        scopes.append("payment_error")
        primary_evidence_types.append("payment_error_troubleshooting")
    elif policy_group == _PRODUCT_CONDITION_POLICY and fact_type == "manufacture_date":
        scopes.append("manufacture_date_policy")
        primary_evidence_types.append("manufacture_date_policy")
    elif policy_group == _ASSURANCE_WARRANTY_POLICY and fact_type == "assurance_document_lost":
        scopes.append("document_status")
        primary_evidence_types.append("assurance_document_lost")
    elif policy_group == _ASSURANCE_WARRANTY_POLICY:
        scopes.append("warranty_condition")
        primary_evidence_types.append("warranty_condition")
    elif policy_group == _BENEFIT_PROMOTION_POLICY:
        scopes.append("promotion_condition")
        primary_evidence_types.append(
            "promotion_gift_partial_cancel" if fact_type == "promotion_gift_partial_cancel" else "promotion_gift_policy_general"
        )
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "reservation_window":
        scopes.append("reservation_window")
        primary_evidence_types.append("reservation_window_limit")
        supporting_evidence_types.extend(["advance_booking_not_supported", "reservation_required_with_purchase"])
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "external_tire_install":
        scopes.append("external_tire_install")
        primary_evidence_types.append("external_tire_install_restriction")
        supporting_evidence_types.extend(["online_purchase_install_flow", "store_specific_install_fee"])
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "store_change":
        scopes.append("store_change")
        primary_evidence_types.append("store_change_policy")
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "work_started_cancel":
        scopes.extend(["work_started", "fee_or_penalty"])
        primary_evidence_types.append("installation_work_fee")
    elif policy_group == _PURCHASE_ORDER_POLICY and fact_type == "online_order_cancel_fee":
        scopes.extend(["fee_or_penalty", "delivery_stage"])
        primary_evidence_types.append("online_order_cancel_fee")
    elif policy_group == _PURCHASE_ORDER_POLICY and fact_type == "wrong_item_or_fitment_issue":
        scopes.append("delivery_stage")
        primary_evidence_types.append("delivered_item_return_fee")
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "mixed_cancel_fee_generalized":
        scopes.append("fee_or_penalty")
        if _RESERVATION_RE.search(text):
            scopes.append("cancel_method")
            primary_evidence_types.append("reservation_cancel_method")
        if _ORDER_RE.search(text):
            scopes.append("delivery_stage")
            if "reservation_cancel_method" in primary_evidence_types:
                supporting_evidence_types.append("online_order_cancel_fee")
            else:
                primary_evidence_types.append("online_order_cancel_fee")
        if has_refund_anchor:
            scopes.append("refund_timing")
            supporting_evidence_types.append("card_refund_timing")
        if not primary_evidence_types:
            primary_evidence_types.append("reservation_cancel_method")
    else:
        default_primary_by_fact_type = {
            "visit_reservation_cancel": "reservation_cancel_method",
            "online_order_cancel_fee": "online_order_cancel_fee",
            "card_cancel_timing": "card_refund_timing",
            "work_started_cancel": "installation_work_fee",
            "reservation_window": "reservation_window_limit",
            "external_tire_install": "external_tire_install_restriction",
            "store_change": "store_change_policy",
            "quality_warranty_condition": "warranty_condition",
            "manufacture_date": "manufacture_date_policy",
            "payment_error_troubleshooting": "payment_error_troubleshooting",
            "promotion_gift_partial_cancel": "promotion_gift_partial_cancel",
            "promotion_gift_policy_general": "promotion_gift_policy_general",
            "assurance_coverage_condition": "warranty_condition",
            "assurance_document_lost": "assurance_document_lost",
        }
        default_primary = default_primary_by_fact_type.get(fact_type)
        if default_primary:
            primary_evidence_types.append(default_primary)

    allowed_evidence_types: list[str] = []
    for scope in scopes:
        allowed_evidence_types.extend(_SUPPORT_FAQ_SCOPE_TO_EVIDENCE_TYPES.get(scope, ()))
    allowed_evidence_types.extend(primary_evidence_types)
    allowed_evidence_types.extend(supporting_evidence_types)
    if not has_refund_anchor:
        allowed_evidence_types = [evidence_type for evidence_type in allowed_evidence_types if evidence_type != "card_refund_timing"]
        supporting_evidence_types = [evidence_type for evidence_type in supporting_evidence_types if evidence_type != "card_refund_timing"]

    return {
        "scopes": list(dict.fromkeys(scopes)),
        "primary_evidence_types": list(dict.fromkeys(primary_evidence_types)),
        "supporting_evidence_types": list(dict.fromkeys(supporting_evidence_types)),
        "allowed_evidence_types": list(dict.fromkeys(allowed_evidence_types)),
        "refund_timing_allowed": has_refund_anchor,
    }


def _select_evidence_for_scope(
    *,
    intent: str,
    user_text: str,
    policy_group: str,
    fact_type: str,
    candidates: list[Mapping[str, Any]],
    scope_info: Mapping[str, Any],
) -> dict[str, Any]:
    primary_types = set(scope_info.get("primary_evidence_types") or [])
    supporting_types = set(scope_info.get("supporting_evidence_types") or [])
    allowed_types = set(scope_info.get("allowed_evidence_types") or [])

    primary: list[dict[str, Any]] = []
    supporting: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for candidate in _support_faq_ranked_candidates(candidates):
        evidence_type = _classify_faq_evidence(candidate, policy_group=policy_group, fact_type=fact_type)
        entry = {
            "candidate": candidate,
            "evidence_type": evidence_type,
        }
        if not evidence_type or evidence_type not in allowed_types:
            excluded.append(entry)
            continue
        if evidence_type in primary_types:
            primary.append(entry)
        elif evidence_type in supporting_types:
            supporting.append(entry)
        else:
            excluded.append(entry)

    selected = primary + supporting
    return {
        "primary": primary,
        "supporting": supporting,
        "selected": selected,
        "excluded": excluded,
        "selected_candidates": [entry["candidate"] for entry in selected],
        "selected_evidence_types": [str(entry["evidence_type"]) for entry in selected if entry.get("evidence_type")],
    }


def _truncate_selected_evidence(
    selected_evidence: Mapping[str, Any],
    *,
    max_items: int = _SUPPORT_FAQ_MAX_LLM_EVIDENCE,
) -> dict[str, Any]:
    primary = list(selected_evidence.get("primary") or [])
    supporting = list(selected_evidence.get("supporting") or [])
    limited_primary = primary[:max_items]
    remaining = max(0, max_items - len(limited_primary))
    limited_supporting = supporting[:remaining]
    selected = [*limited_primary, *limited_supporting]
    return {
        "primary": limited_primary,
        "supporting": limited_supporting,
        "selected": selected,
        "selected_candidates": [entry["candidate"] for entry in selected if isinstance(entry, Mapping) and entry.get("candidate")],
        "selected_evidence_types": [
            str(entry["evidence_type"])
            for entry in selected
            if isinstance(entry, Mapping) and entry.get("evidence_type")
        ],
    }


def _support_faq_grounded_prompt(
    *,
    intent: str,
    user_text: str,
    policy_group: str,
    fact_type: str,
    candidates: list[Mapping[str, Any]],
) -> str:
    candidate_blocks: list[str] = []
    for rank, candidate in enumerate(candidates, start=1):
        lv1, lv2, _, _ = _support_faq_candidate_categories(candidate)
        payload = {
            "rank": rank,
            "score": _support_faq_candidate_score(candidate),
            "category_lv1": lv1 or None,
            "category_lv2": lv2 or None,
            "question": _normalize_support_faq_text(candidate.get("question") or ""),
            "answer": _normalize_support_faq_text(
                candidate.get("answer")
                or candidate.get("pc_ans_cont")
                or candidate.get("content")
                or candidate.get("body")
                or ""
            ),
        }
        candidate_blocks.append(json.dumps(payload, ensure_ascii=False))
    candidates_text = "\n".join(candidate_blocks)
    return (
        "당신은 T'Station FAQ 답변 보조기입니다.\n"
        "사용자 질문과 FAQ 후보만 보고 2~3문장 한국어 답변을 작성하세요.\n"
        "규칙:\n"
        "- FAQ 후보 question/answer에 없는 사실, 숫자, 기간, 금액은 절대 추가하지 마세요.\n"
        "- 사용자 질문과 직접 관련 없는 후보 내용은 제외하세요.\n"
        "- 카드 승인취소/환불 반영 기간은 사용자가 카드/환불/승인취소/반영 시점을 직접 물은 경우에만 포함하세요.\n"
        "- 취소 수수료 질문에는 환불 반영 기간을 넣지 마세요.\n"
        "- 제조일자/DOT 내용은 제조일자 질문에만 사용하세요.\n"
        "- 답변 안에 'FAQ 기준', 'RAG 기준', '후보', 'rank', 'score' 같은 표현을 쓰지 마세요.\n"
        "- 근거가 부족하면 확인이 필요하다고 짧게 말하세요.\n"
        f"- policy_group={policy_group}, fact_type={fact_type}, intent={intent}\n\n"
        f"사용자 질문:\n{_normalize_support_faq_text(user_text)}\n\n"
        f"FAQ 후보:\n{candidates_text}\n\n"
        "출력은 답변 본문만 작성하세요."
    )


def _support_faq_evidence_grounded_prompt(
    *,
    intent: str,
    user_text: str,
    policy_group: str,
    fact_type: str,
    scope_info: Mapping[str, Any],
    selected_evidence: Mapping[str, Any],
) -> str:
    evidence_blocks: list[str] = []
    for rank, entry in enumerate(selected_evidence.get("primary") or [], start=1):
        candidate = entry["candidate"]
        lv1, lv2, _, _ = _support_faq_candidate_categories(candidate)
        evidence_blocks.append(
            json.dumps(
                {
                    "role": "primary",
                    "rank": rank,
                    "evidence_type": entry.get("evidence_type"),
                    "category_lv1": lv1 or None,
                    "category_lv2": lv2 or None,
                    "question": _normalize_support_faq_text(candidate.get("question") or ""),
                    "answer": _normalize_support_faq_text(candidate.get("answer") or candidate.get("pc_ans_cont") or ""),
                },
                ensure_ascii=False,
            )
        )
    supporting_offset = len(evidence_blocks)
    for rank, entry in enumerate(selected_evidence.get("supporting") or [], start=1):
        candidate = entry["candidate"]
        lv1, lv2, _, _ = _support_faq_candidate_categories(candidate)
        evidence_blocks.append(
            json.dumps(
                {
                    "role": "supporting",
                    "rank": supporting_offset + rank,
                    "evidence_type": entry.get("evidence_type"),
                    "category_lv1": lv1 or None,
                    "category_lv2": lv2 or None,
                    "question": _normalize_support_faq_text(candidate.get("question") or ""),
                    "answer": _normalize_support_faq_text(candidate.get("answer") or candidate.get("pc_ans_cont") or ""),
                },
                ensure_ascii=False,
            )
        )
    return (
        "당신은 T'Station FAQ 답변 보조기입니다.\n"
        "사용자 질문 범위에 맞는 근거만 사용해 2~3문장 한국어 답변을 작성하세요.\n"
        "규칙:\n"
        "- 아래 evidence에 없는 사실, 숫자, 기간, 금액을 추가하지 마세요.\n"
        "- 질문 scope 밖 내용은 쓰지 마세요.\n"
        "- 서로 다른 조건은 섞지 말고 구분해서 설명하세요.\n"
        "- 직접 근거가 부족하면 '확인이 필요해요'처럼 단정하지 말고 답하세요.\n"
        "- 답변 안에 FAQ, RAG, 후보, rank, score 같은 표현을 쓰지 마세요.\n"
        f"- intent={intent}, policy_group={policy_group}, fact_type={fact_type}\n"
        f"- question_scopes={json.dumps(list(scope_info.get('scopes') or []), ensure_ascii=False)}\n"
        f"- allowed_evidence_types={json.dumps(list(scope_info.get('allowed_evidence_types') or []), ensure_ascii=False)}\n\n"
        f"사용자 질문:\n{_normalize_support_faq_text(user_text)}\n\n"
        f"evidence:\n" + "\n".join(evidence_blocks) + "\n\n"
        "출력은 답변 본문만 작성하세요."
    )


def _support_faq_retry_prompt(prompt: str, failure_reason: str) -> str:
    retry_note = (
        "\n\n이전 답변 초안은 정책 post-check를 통과하지 못했습니다.\n"
        f"실패 이유: {failure_reason}\n"
        "이번에는 실패 이유에 해당하는 내용은 제거하고, evidence에 직접 있는 내용만 사용해 다시 답변하세요."
    )
    return f"{prompt}{retry_note}"


def _invoke_support_faq_grounded_llm(prompt: str) -> str:
    from services.tstation.agents.router import DECISION_LLM

    result = DECISION_LLM.invoke([HumanMessage(content=prompt)])
    content = result.content if hasattr(result, "content") else result
    return _normalize_support_faq_text(content)


def _support_faq_numeric_facts(text: str) -> set[str]:
    normalized = re.sub(r"\s+", "", str(text or "")).lower().replace(",", "")
    patterns = [
        r"\d+(?:[~-]\d+)?영업일",
        r"\d+(?:[~-]\d+)?일",
        r"\d+(?:[~-]\d+)?개월",
        r"\d+년",
        r"\d+km",
        r"\d+만?원",
        r"\d+개",
        r"\d+짝",
        r"\d+본",
        r"\d+(?:[~-]\d+)?",
    ]
    found: set[str] = set()
    for pattern in patterns:
        found.update(re.findall(pattern, normalized, re.IGNORECASE))
    return found


def _support_faq_post_check_failure(
    *,
    intent: str,
    user_text: str,
    answer: str,
    source_candidates: list[Mapping[str, Any]],
    scope_info: Mapping[str, Any] | None = None,
    selected_evidence_types: list[str] | None = None,
) -> str | None:
    normalized_answer = _normalize_support_faq_text(answer)
    if not normalized_answer:
        return "empty_answer"
    if re.search(r"faq\s*기준|rag\s*기준|후보|rank|score", normalized_answer, re.IGNORECASE):
        return "source_reference_exposed"
    scope_set = set(scope_info.get("scopes") or []) if isinstance(scope_info, Mapping) else set()
    evidence_type_set = set(selected_evidence_types or [])
    refund_allowed = (
        "refund_timing" in scope_set
        or "card_refund_timing" in evidence_type_set
        or _support_faq_question_anchor_allowed(intent, user_text)
    )
    if re.search(r"카드|환불|승인\s*취소|반영|영업일", normalized_answer, re.IGNORECASE) and not refund_allowed:
        return "card_refund_anchor_missing"
    if "manufacture_date_policy" not in evidence_type_set and intent == "tire_quality_warranty_policy" and re.search(
        r"제조일자|dot", normalized_answer, re.IGNORECASE
    ):
        return "manufacture_drift"
    if "external_tire_install" in scope_set and re.search(r"무조건|항상|확실히", normalized_answer, re.IGNORECASE):
        return "unsupported_absolute_claim"

    source_text = "\n".join(_support_faq_candidate_text(candidate) for candidate in source_candidates)
    allowed_numeric_facts = _support_faq_numeric_facts(source_text)
    answer_numeric_facts = _support_faq_numeric_facts(normalized_answer)
    if any(fact not in allowed_numeric_facts for fact in answer_numeric_facts):
        return "unsupported_numeric_fact"
    return None


def _build_support_faq_safe_fallback_reply(
    *,
    policy_group: str,
    fact_type: str,
    filtered_candidates: list[Mapping[str, Any]],
    excluded_candidates: list[Mapping[str, Any]],
    fallback_reason: str,
) -> dict[str, Any]:
    response, quick_replies = _build_support_faq_policy_reply(
        policy_group,
        fact_type,
        {},
        safe_fallback_used=True,
    )
    return {
        "assistant_response": response,
        "quick_replies": quick_replies,
        "metadata": {
            "policyGroup": policy_group,
            "factType": fact_type,
            "clarificationNeeded": False,
            "safeFallbackUsed": True,
            "sourceGroundedReplyUsed": False,
            "evidenceGroundedReplyUsed": False,
            "faqLlmGroundedReplyUsed": False,
            "fallbackReason": fallback_reason,
            "filteredFaqCount": len(filtered_candidates),
            "excludedFaqCount": len(excluded_candidates),
            "factExtractionApplied": False,
        },
    }


def resolve_support_faq_policy_context(intent: str, user_text: str) -> dict[str, Any] | None:
    normalized_intent = str(intent or "").strip()
    text = str(user_text or "")
    if normalized_intent not in _SUPPORT_FAQ_POLICY_GROUP_INTENTS and not _WRONG_ITEM_RE.search(text):
        return None

    has_cancel = bool(_CANCEL_RE.search(text) or _FEE_RE.search(text))
    has_reservation = bool(_RESERVATION_RE.search(text))
    has_order = bool(_ORDER_RE.search(text))
    has_work_started = bool(_WORK_STARTED_RE.search(text) and has_cancel)
    has_store_change = bool(_STORE_CHANGE_RE.search(text) and _CHANGE_RE.search(text))

    if normalized_intent == "general_card_cancel_timing_policy" or is_general_card_cancel_timing_policy_query(text):
        return {"policy_group": _PAYMENT_REFUND_POLICY, "fact_type": "card_cancel_timing"}
    if normalized_intent == "reservation_window_policy":
        return {"policy_group": _RESERVATION_INSTALLATION_POLICY, "fact_type": "reservation_window"}
    if normalized_intent == "external_tire_install_policy":
        return {"policy_group": _RESERVATION_INSTALLATION_POLICY, "fact_type": "external_tire_install"}
    if normalized_intent == "payment_error_troubleshooting" and _is_card_installment_lookup_query(text):
        return None
    if (normalized_intent == "payment_error_troubleshooting" or _PAYMENT_ERROR_RE.search(text)) and not _is_card_installment_lookup_query(text):
        return {"policy_group": _PAYMENT_REFUND_POLICY, "fact_type": "payment_error_troubleshooting"}
    if normalized_intent == "tire_manufacture_date_policy":
        return {"policy_group": _PRODUCT_CONDITION_POLICY, "fact_type": "manufacture_date"}
    if normalized_intent == "tire_condition_photo_policy":
        return {"policy_group": _PRODUCT_CONDITION_POLICY, "fact_type": "photo_condition_check"}
    if normalized_intent == "tire_quality_warranty_policy":
        return {"policy_group": _ASSURANCE_WARRANTY_POLICY, "fact_type": "quality_warranty_condition"}
    if normalized_intent == "assurance_service_policy":
        strong_fact_types = []
        if _ASSURANCE_DOCUMENT_LOST_RE.search(text):
            strong_fact_types.append("assurance_document_lost")
        if re.search(r"조건|보상|가입|워런티|안심\s*서비스|안심플러스", text, re.IGNORECASE):
            strong_fact_types.append("assurance_coverage_condition")
        if len(strong_fact_types) > 1:
            return {
                "policy_group": _ASSURANCE_WARRANTY_POLICY,
                "fact_type": None,
                "needs_clarification": True,
                "clarification_reason": "assurance_scope_ambiguous",
                "assistant_response": "안심서비스 보상 조건을 묻는 건지, 보증서 분실 후 확인 방법을 묻는 건지 알려주시면 정확히 안내드릴게요.",
                "quick_replies": [
                    {"label": "보상 조건", "url": CTAUrls.WARRANTY_MAIN, "domain": "SUPPORT"},
                    {"label": "보증서 분실", "url": CTAUrls.WARRANTY_MAIN, "domain": "SUPPORT"},
                ],
            }
        fact_type = strong_fact_types[0] if strong_fact_types else None
        if fact_type is None:
            return {
                "policy_group": _ASSURANCE_WARRANTY_POLICY,
                "fact_type": None,
                "needs_clarification": True,
                "clarification_reason": "assurance_fact_type_missing",
                "assistant_response": "안심서비스 보상 조건인지, 보증서 분실인지처럼 확인하려는 항목을 알려주시면 정확히 안내드릴게요.",
                "quick_replies": [{"label": "나의 워런티 확인", "url": CTAUrls.WARRANTY_MAIN, "domain": "SUPPORT"}],
            }
        return {"policy_group": _ASSURANCE_WARRANTY_POLICY, "fact_type": fact_type}
    if normalized_intent == "promotion_gift_policy":
        return {
            "policy_group": _BENEFIT_PROMOTION_POLICY,
            "fact_type": "promotion_gift_partial_cancel" if _PROMOTION_PARTIAL_CANCEL_RE.search(text) else "promotion_gift_policy_general",
        }
    if normalized_intent == "installation_work_policy" and has_work_started:
        return {"policy_group": _RESERVATION_INSTALLATION_POLICY, "fact_type": "work_started_cancel"}
    if normalized_intent in {"general_cancel_fee_policy", "reservation_policy_guidance", "installation_work_policy"}:
        if has_work_started:
            return {"policy_group": _RESERVATION_INSTALLATION_POLICY, "fact_type": "work_started_cancel"}
        if has_store_change:
            return {"policy_group": _RESERVATION_INSTALLATION_POLICY, "fact_type": "store_change"}
        if has_cancel and has_reservation and has_order:
            return {"policy_group": _RESERVATION_INSTALLATION_POLICY, "fact_type": "mixed_cancel_fee_generalized"}
        if has_cancel and has_reservation and not has_order:
            return {"policy_group": _RESERVATION_INSTALLATION_POLICY, "fact_type": "mixed_cancel_fee_generalized"}
        if has_cancel and has_order and not has_reservation:
            return {"policy_group": _PURCHASE_ORDER_POLICY, "fact_type": "online_order_cancel_fee"}
    if _WRONG_ITEM_RE.search(text):
        return {"policy_group": _PURCHASE_ORDER_POLICY, "fact_type": "wrong_item_or_fitment_issue"}
    return None


def _support_faq_candidate_matches_fact_type(fact_type: str, candidate: Mapping[str, Any]) -> bool:
    text = _support_faq_candidate_text(candidate)
    if fact_type == "visit_reservation_cancel":
        return bool(_RESERVATION_RE.search(text) and (_CANCEL_RE.search(text) or _FEE_RE.search(text)))
    if fact_type == "mixed_cancel_fee_generalized":
        return bool(
            (_RESERVATION_RE.search(text) and (_CANCEL_RE.search(text) or _FEE_RE.search(text)))
            or (_ORDER_RE.search(text) and (_CANCEL_RE.search(text) or _FEE_RE.search(text)))
            or re.search(r"카드|승인\s*취소|환불\s*반영|영업일", text, re.IGNORECASE)
        )
    if fact_type == "store_change":
        return bool(_STORE_CHANGE_RE.search(text) and _CHANGE_RE.search(text))
    if fact_type == "work_started_cancel":
        return bool(_WORK_STARTED_RE.search(text) and (_CANCEL_RE.search(text) or _FEE_RE.search(text)))
    if fact_type == "reservation_window":
        return bool(
            re.search(r"30일|1개월|한\s*달|두\s*달|2\s*달|최대|예약\s*가능\s*기간|사전\s*구매", text, re.IGNORECASE)
            and _RESERVATION_RE.search(text)
        )
    if fact_type == "external_tire_install":
        return bool(
            _EXTERNAL_TIRE_INSTALL_POLICY_RE.search(text)
            or re.search(
                r"타이어만.{0,16}(?:직접\s*장착|장착\s*불가|별도\s*수령)|"
                r"온라인몰.{0,24}(?:지정\s*장착점|발송|장착)|"
                r"오프라인\s*매장.{0,24}(?:구매|장착)|"
                r"장착비.{0,16}(?:매장별|상이)",
                text,
                re.IGNORECASE,
            )
        )
    if fact_type == "online_order_cancel_fee":
        return bool(_ONLINE_ORDER_CANCEL_RE.search(text))
    if fact_type == "card_cancel_timing":
        return bool(re.search(r"카드|승인\s*취소|환불\s*반영|영업일", text, re.IGNORECASE))
    if fact_type == "payment_error_troubleshooting":
        return bool(_PAYMENT_ERROR_RE.search(text))
    if fact_type == "assurance_coverage_condition":
        return bool(re.search(r"안심\s*서비스|안심플러스|보상|가입|워런티|16,?000km|1년", text, re.IGNORECASE))
    if fact_type == "assurance_document_lost":
        return bool(_ASSURANCE_DOCUMENT_LOST_RE.search(text))
    if fact_type == "quality_warranty_condition":
        return bool(_TIRE_QUALITY_WARRANTY_POLICY_RE.search(text))
    if fact_type == "promotion_gift_partial_cancel":
        return bool(re.search(r"사은품|이벤트|프로모션", text, re.IGNORECASE) and _PROMOTION_PARTIAL_CANCEL_RE.search(text))
    if fact_type == "promotion_gift_policy_general":
        return bool(re.search(r"사은품|이벤트|프로모션|선착순", text, re.IGNORECASE))
    if fact_type == "manufacture_date":
        return bool(_TIRE_MANUFACTURE_DATE_POLICY_RE.search(text))
    if fact_type == "photo_condition_check":
        return bool(_TIRE_CONDITION_PHOTO_POLICY_RE.search(text) or re.search(r"사진|마모|손상|더\s*타", text, re.IGNORECASE))
    if fact_type == "wrong_item_or_fitment_issue":
        return bool(_WRONG_ITEM_RE.search(text))
    return False


def _filter_support_faq_candidates(
    policy_group: str,
    fact_type: str,
    tool_result: Mapping[str, Any] | None,
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    if policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "mixed_cancel_fee_generalized":
        allowed_names = (("배송/장착", "장착"), ("주문/결제", "주문"), ("주문/결제", "결제"))
        allowed_codes = (("C01", "C0106"), ("C01", "C0104"), ("C01", "C0105"))
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "external_tire_install":
        allowed_names = (("배송/장착", "장착"), ("상품/서비스", "서비스"), ("주문/결제", "주문"))
        allowed_codes = (("C01", "C0106"), ("C03", "C0302"), ("C01", "C0104"))
    else:
        allowed_names = _ALLOWED_CATEGORY_NAMES_BY_POLICY_GROUP.get(policy_group, ())
        allowed_codes = _ALLOWED_CATEGORY_CODES_BY_POLICY_GROUP.get(policy_group, ())
    included: list[Mapping[str, Any]] = []
    excluded: list[Mapping[str, Any]] = []
    for candidate in _support_faq_candidates(tool_result):
        lv1, lv2, code1, code2 = _support_faq_candidate_categories(candidate)
        has_category = bool((lv1 and lv2) or (code1 and code2))
        if has_category:
            category_allowed = any(lv1 == name1 and lv2 == name2 for name1, name2 in allowed_names if lv1 and lv2)
            code_allowed = any(code1 == name1 and code2 == name2 for name1, name2 in allowed_codes if code1 and code2)
            if not category_allowed and not code_allowed:
                excluded.append(candidate)
                continue
        if _support_faq_candidate_matches_fact_type(fact_type, candidate):
            included.append(candidate)
        else:
            excluded.append(candidate)
    return included, excluded


def _extract_support_faq_policy_facts(
    intent: str,
    user_text: str,
    policy_group: str,
    fact_type: str,
    candidates: list[Mapping[str, Any]],
) -> dict[str, Any]:
    combined = "\n".join(_support_faq_candidate_text(candidate) for candidate in candidates)
    facts: dict[str, Any] = {}
    if policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "visit_reservation_cancel":
        facts["fee_condition"] = (
            "none"
            if re.search(r"별도(?:의)?\s*(?:취소\s*)?(?:수수료|위약금).{0,8}(없|않)", combined, re.IGNORECASE)
            else "depends"
        )
        facts["cancel_method"] = "reservation_only"
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "mixed_cancel_fee_generalized":
        reservation_text = "\n".join(
            _support_faq_candidate_text(candidate)
            for candidate in candidates
            if _support_faq_candidate_matches_fact_type("visit_reservation_cancel", candidate)
        )
        order_text = "\n".join(
            _support_faq_candidate_text(candidate)
            for candidate in candidates
            if _support_faq_candidate_matches_fact_type("online_order_cancel_fee", candidate)
        )
        card_text = "\n".join(
            _support_faq_candidate_text(candidate)
            for candidate in candidates
            if _support_faq_candidate_matches_fact_type("card_cancel_timing", candidate)
        )
        facts["visitReservationCancel"] = bool(reservation_text)
        facts["visit_reservation_fee_condition"] = (
            "none"
            if re.search(r"별도(?:의)?\s*(?:취소\s*)?(?:수수료|위약금).{0,8}(없|않)", reservation_text, re.IGNORECASE)
            else "depends"
        )
        if re.search(r"고객센터|전화", reservation_text, re.IGNORECASE):
            facts["visit_reservation_cancel_method"] = "고객센터 전화"
        if re.search(r"바로\s*취소\s*처리|즉시\s*취소", reservation_text, re.IGNORECASE):
            facts["visit_reservation_cancel_effect"] = "요청 시 바로 취소 처리"
        order_amount_match = re.search(r"(?:타이어\s*(?:개당|1개당)|개당)\s*1만\s*원", order_text, re.IGNORECASE)
        if order_amount_match:
            facts["online_order_cancel_fee_amount"] = "타이어 개당 1만 원"
            facts["onlineOrderCancelFee"] = "타이어 개당 1만 원 가능"
        if re.search(r"배송\s*(?:현황|상태)|배송\s*진행", order_text, re.IGNORECASE):
            facts["online_order_cancel_fee_condition"] = "배송 현황에 따라"
        card_timing_match = re.search(r"([0-9]+(?:\s*[~-]\s*[0-9]+)?\s*영업일)", card_text, re.IGNORECASE)
        if card_timing_match:
            facts["card_refund_timing"] = card_timing_match.group(1).replace(" ", "")
            facts["cardRefundTiming"] = facts["card_refund_timing"]
    elif policy_group == _PURCHASE_ORDER_POLICY and fact_type == "online_order_cancel_fee":
        amount_match = re.search(r"(?:타이어\s*1개당|1본당|개당)\s*1만\s*원", combined, re.IGNORECASE)
        facts["fee_condition"] = "per_item_fee" if amount_match else "depends"
        facts["fee_amount"] = "타이어 1개당 1만 원" if amount_match else None
    elif policy_group == _PAYMENT_REFUND_POLICY and fact_type == "card_cancel_timing":
        timing_match = re.search(r"영업일\s*기준\s*([0-9]+(?:\s*[~-]\s*[0-9]+)?일?)", combined, re.IGNORECASE)
        facts["refund_timing"] = timing_match.group(1).replace(" ", "") if timing_match else None
        facts["refund_timing_source"] = "card_company"
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "work_started_cancel":
        facts["fee_condition"] = "work_started_check_required"
        if re.search(r"공임(?:비)?", combined, re.IGNORECASE):
            facts["work_fee"] = "possible"
        if re.search(r"폐타이어", combined, re.IGNORECASE):
            facts["disposal_fee"] = "possible"
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "reservation_window":
        if re.search(r"30일\s*이내|최대\s*30일", combined, re.IGNORECASE):
            facts["reservation_window_limit"] = "30일 이내"
        elif re.search(r"1개월\s*이내|한\s*달\s*이내|구매일로부터\s*1개월", combined, re.IGNORECASE):
            facts["reservation_window_limit"] = "구매일로부터 1개월 이내"
        if re.search(r"사전\s*구매|사전구매", combined, re.IGNORECASE) and re.search(r"불가|지원하지\s*않", combined, re.IGNORECASE):
            facts["advance_booking_not_supported"] = True
        if re.search(r"구매일로부터|주문\s*후|결제\s*후", combined, re.IGNORECASE):
            facts["reservation_required_with_purchase"] = True
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "external_tire_install":
        if re.search(r"별도\s*수령|직접\s*장착|반입", combined, re.IGNORECASE) and re.search(r"불가|지원하지\s*않", combined, re.IGNORECASE):
            facts["external_tire_install_restriction"] = "direct_install_not_supported"
        if re.search(r"온라인몰|지정\s*장착점|발송", combined, re.IGNORECASE):
            facts["online_purchase_install_flow"] = True
        if re.search(r"오프라인\s*매장|매장\s*구매", combined, re.IGNORECASE):
            facts["offline_store_purchase_install"] = True
        if re.search(r"장착비|공임|매장별\s*상이|가격\s*상이", combined, re.IGNORECASE):
            facts["store_specific_install_fee"] = True
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "store_change":
        facts["store_change_allowed"] = (
            "allowed"
            if re.search(r"변경(?:이)?\s*(?:가능|할\s*수\s*있|가능한\s*경우)", combined, re.IGNORECASE)
            else "depends"
        )
    elif policy_group == _ASSURANCE_WARRANTY_POLICY and fact_type == "assurance_coverage_condition":
        facts["year_limit"] = "1년" if re.search(r"1년\s*이내", combined, re.IGNORECASE) else None
        facts["mileage_limit"] = "16,000km" if re.search(r"16[, ]?000\s*km", combined, re.IGNORECASE) else None
        facts["assurance_min_qty"] = "2개" if re.search(r"2개\s*이상", combined, re.IGNORECASE) else None
        facts["plus_min_qty"] = "4개" if re.search(r"4개\s*(?:구매|이상)", combined, re.IGNORECASE) else None
    elif policy_group == _ASSURANCE_WARRANTY_POLICY and fact_type == "assurance_document_lost":
        facts["digital_or_history_check"] = bool(re.search(r"디지털|구매\s*이력|장착\s*이력|워런티", combined, re.IGNORECASE))
    elif policy_group == _ASSURANCE_WARRANTY_POLICY and fact_type == "quality_warranty_condition":
        facts["inspection_required"] = True
    elif policy_group == _BENEFIT_PROMOTION_POLICY and fact_type == "promotion_gift_partial_cancel":
        facts["gift_return_required"] = bool(re.search(r"반납", combined, re.IGNORECASE))
        facts["refund_deduction_possible"] = bool(re.search(r"차감", combined, re.IGNORECASE))
    elif policy_group == _PRODUCT_CONDITION_POLICY and fact_type == "manufacture_date":
        freshness_match = re.search(r"([0-9]+(?:\s*[~-]\s*[0-9]+)?\s*개월)\s*이내", combined, re.IGNORECASE)
        facts["freshness_window"] = freshness_match.group(1).replace(" ", "") + " 이내" if freshness_match else None
    elif policy_group == _PAYMENT_REFUND_POLICY and fact_type == "payment_error_troubleshooting":
        issue_match = re.search(r"결제창|결제\s*화면|장착일\s*선택란|승인\s*실패|결제\s*오류", combined, re.IGNORECASE)
        facts["issue_scope"] = issue_match.group(0) if issue_match else None
    return _support_faq_strip_card_refund_facts_for_non_anchor(intent=intent, user_text=user_text, facts=facts)


def _support_faq_reply_ctas(policy_group: str, fact_type: str) -> list[dict[str, Any]]:
    if policy_group == _ASSURANCE_WARRANTY_POLICY:
        return [{"label": "나의 워런티 확인", "url": CTAUrls.WARRANTY_MAIN, "domain": "SUPPORT"}]
    if policy_group == _BENEFIT_PROMOTION_POLICY:
        return [{"label": "진행 중인 이벤트 보기", "url": CTAUrls.PROMOTION_EVENT_LIST, "domain": "DISCOVERY"}]
    if policy_group == _PRODUCT_CONDITION_POLICY and fact_type == "photo_condition_check":
        return [
            {"label": "마모도 측정 서비스", "url": CTAUrls.TIRE_CHECK, "domain": "TRANSACTION"},
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ]
    if policy_group == _PURCHASE_ORDER_POLICY:
        return [
            {"label": "주문내역 확인", "domain": "TRANSACTION"},
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ]
    if policy_group == _PAYMENT_REFUND_POLICY and fact_type == "payment_error_troubleshooting":
        return [
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
            {"label": "고객센터 안내", "domain": "SUPPORT"},
        ]
    if policy_group == _PAYMENT_REFUND_POLICY:
        return [
            {"label": "주문내역 확인", "domain": "TRANSACTION"},
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ]
    if policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "work_started_cancel":
        return [
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
            {"label": "고객센터 안내", "domain": "SUPPORT"},
        ]
    if policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "external_tire_install":
        return [
            {"label": "가까운 매장 찾기", "domain": "TRANSACTION"},
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ]
    if policy_group == _RESERVATION_INSTALLATION_POLICY:
        return [
            {
                "label": "주문/예약 내역 보기",
                "domain": "TRANSACTION",
                "cta_action": "open_order_history",
                "expected_contract_intent": "get_my_reservations",
            },
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ]
    return [
        {"label": "주문/예약 내역 보기", "domain": "TRANSACTION"},
        {"label": "1:1 문의하기", "domain": "SUPPORT"},
    ]


def _build_support_faq_policy_reply(
    policy_group: str,
    fact_type: str,
    facts: Mapping[str, Any],
    *,
    safe_fallback_used: bool,
) -> tuple[str, list[dict[str, Any]]]:
    if policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "visit_reservation_cancel":
        if safe_fallback_used:
            response = (
                "예약/장착 관련 비용은 예약 유형과 진행 상태에 따라 달라질 수 있어요.\n"
                "방문 예약만 취소하는 건인지, 주문이나 배송이 함께 진행된 건인지에 따라 결론이 달라질 수 있어요.\n"
                "실제 취소 전 예약 상세 또는 고객센터 안내를 확인해 주세요."
            )
        elif facts.get("fee_condition") == "none":
            response = (
                "방문 예약만 취소하는 건이라면 별도의 취소 수수료가 없다고 안내드릴 수 있어요.\n"
                "다만 실제 주문이나 배송이 함께 걸린 건이면 비용 조건이 달라질 수 있어요.\n"
                "실제 취소 전에는 예약 상세나 고객센터 안내를 함께 확인해 주세요."
            )
        else:
            response = (
                "방문 예약 취소 비용은 예약만 취소하는 경우인지, 주문이나 배송이 함께 진행된 건인지에 따라 달라질 수 있어요.\n"
                "예약 취소만으로 끝나는 건인지부터 먼저 확인하시는 게 안전해요.\n"
                "실제 취소 전에는 예약 상세 안내를 먼저 확인해 주세요."
            )
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "mixed_cancel_fee_generalized":
        has_visit = bool(
            facts.get("visit_reservation_cancel_method")
            or facts.get("visit_reservation_cancel_effect")
            or facts.get("visitReservationCancel")
        )
        has_order = bool(
            facts.get("online_order_cancel_fee_amount")
            or facts.get("online_order_cancel_fee_condition")
            or facts.get("onlineOrderCancelFee")
        )
        has_card = bool(facts.get("card_refund_timing") or facts.get("cardRefundTiming"))
        if not (has_visit or has_order or has_card):
            response = (
                "예약/장착 관련 비용은 예약 유형과 진행 상태에 따라 달라질 수 있어요.\n"
                "방문 예약만 취소하는 건인지, 온라인몰에서 결제까지 완료된 주문인지에 따라 결론이 달라질 수 있어요.\n"
                "실제 취소 전에는 주문/예약 내역이나 고객센터 안내를 먼저 확인해 주세요."
            )
        elif has_visit and has_order:
            response = (
                "예약 취소 비용은 방문 예약만 취소하는 건인지, 온라인몰 결제 주문까지 함께 취소하는 건인지에 따라 달라질 수 있어요.\n"
                "예약 상태와 주문 진행 상태를 함께 확인해야 해서 여기서 한 가지 조건으로 단정하기는 어려워요.\n"
                "실제 취소 전에는 주문/예약 내역이나 고객센터 안내를 먼저 확인해 주세요."
            )
        else:
            lines: list[str] = []
            if has_visit:
                if facts.get("visit_reservation_fee_condition") == "none" and facts.get("visit_reservation_cancel_method") != "고객센터 전화":
                    sentence = "예약만 잡아둔 상태라면 별도의 취소 수수료가 없다고 안내돼요."
                else:
                    sentence = "예약만 잡아둔 상태라면 취소는"
                if facts.get("visit_reservation_cancel_method") == "고객센터 전화":
                    sentence += " 고객센터를 통해 처리할 수 있고,"
                elif not sentence.endswith("안내돼요."):
                    sentence += " 고객센터 안내 기준으로 처리 여부를 확인할 수 있고,"
                if facts.get("visit_reservation_cancel_effect") == "요청 시 바로 취소 처리":
                    sentence += " 요청 시 바로 취소 처리되는 것으로 안내돼요."
                elif facts.get("visit_reservation_fee_condition") == "none" and not has_order and not has_card:
                    sentence = "방문 예약만 취소하는 건이라면 별도의 취소 수수료가 없다고 안내드릴 수 있어요."
                elif not sentence.endswith("안내돼요."):
                    sentence += " 요청 즉시 처리 여부는 안내 기준에 따라 달라질 수 있어요."
                lines.append(sentence)
            if has_order:
                condition_text = str(facts.get("online_order_cancel_fee_condition") or "배송 진행 상태에 따라").strip()
                amount_text = str(facts.get("online_order_cancel_fee_amount") or "").strip()
                if amount_text:
                    lines.append(
                        "다만 온라인몰에서 결제까지 완료된 주문이라면 "
                        f"{condition_text} 취소 수수료가 발생할 수 있고, {amount_text} 안내가 있어요."
                    )
                else:
                    lines.append(
                        "다만 온라인몰에서 결제까지 완료된 주문이라면 "
                        f"{condition_text} 취소 수수료가 발생할 수 있다고 안내돼요."
                    )
            response = "\n\n".join(lines)
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "reservation_window":
        limit_text = str(facts.get("reservation_window_limit") or "최대 30일 이내").strip()
        response = (
            f"장착 예약일은 보통 {limit_text}로 안내돼요.\n"
            "두 달 뒤처럼 범위를 넘는 예약은 지원되지 않거나 진행이 어려울 수 있어요.\n"
            "실제 일정 확인은 이 범위 안에서만 추가로 진행해 주세요."
        )
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "store_change":
        allowed_text = "방문 지점 변경 가능 여부는 예약 정책과 현재 예약 상태에 따라 달라질 수 있어요."
        if facts.get("store_change_allowed") == "allowed":
            allowed_text = "방문 날짜를 유지한 채 지점 변경이 가능한 경우도 있지만, 예약 정책과 현재 예약 상태를 함께 확인해야 해요."
        response = (
            f"{allowed_text}\n"
            "지점만 바꾸는 건인지, 일정도 함께 바꾸는 건인지에 따라 안내 기준이 달라질 수 있어요.\n"
            "실제 변경 전에는 예약 상세나 고객센터 안내 기준으로 변경 가능 여부를 먼저 확인해 주세요."
        )
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "work_started_cancel":
        response = (
            "이미 작업이 시작된 뒤 취소하는 건은 공임비나 부대 비용이 발생할 수 있어서 작업 진행 범위를 먼저 확인해야 해요.\n"
            "기존 타이어 탈거나 장착 작업이 진행됐다면 현장 작업 범위 기준으로 비용 여부가 달라질 수 있어요.\n"
            "실제 취소 전에는 작업 범위와 비용 기준을 매장이나 고객센터 안내로 확인해 주세요."
        )
    elif policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "external_tire_install":
        if safe_fallback_used:
            response = (
                "외부 구매 타이어를 매장에 반입해 장착하는 건은 FAQ만으로 일괄 가능하다고 단정하기 어려워요.\n"
                "구매 경로와 매장 운영 기준에 따라 장착 가능 여부나 비용 기준이 달라질 수 있어요.\n"
                "방문 전에는 해당 매장 운영 기준이나 고객센터 안내를 먼저 확인해 주세요."
            )
        else:
            response = (
                "외부 구매 타이어 반입 장착은 구매 경로와 장착 방식에 따라 기준이 달라질 수 있어요.\n"
                "온라인몰 주문은 지정 장착점 발송/장착 기준으로 안내되고, 별도 수령 후 직접 반입 장착은 지원되지 않거나 제한될 수 있어요.\n"
                "오프라인 매장 구매 후 장착이나 장착비 기준은 매장별 운영에 따라 달라질 수 있으니 방문 전 확인해 주세요."
            )
    elif policy_group == _PURCHASE_ORDER_POLICY and fact_type == "online_order_cancel_fee":
        amount_text = facts.get("fee_amount") or "취소 시점과 주문 상태에 따라 비용이 달라질 수 있어요."
        response = (
            "결제 완료 주문 취소 기준으로는 배송/처리 진행 상태에 따라 취소 비용이 달라질 수 있어요.\n"
            f"{amount_text} 기준 안내가 확인돼요.\n"
            "실제 차감 여부는 주문 상태와 취소 시점을 함께 확인해 주세요."
        )
    elif policy_group == _PURCHASE_ORDER_POLICY and fact_type == "wrong_item_or_fitment_issue":
        response = (
            "주문한 상품과 다른 타이어가 도착했거나 장착 규격이 맞지 않다면 바로 장착 진행을 단정하면 안 돼요.\n"
            "주문 상품명, 사이즈, 실제 도착 상품, 차량 적합 여부를 함께 확인해야 해요.\n"
            "주문내역과 현장 확인 결과를 기준으로 매장이나 고객센터 안내를 받아 주세요."
        )
    elif policy_group == _PAYMENT_REFUND_POLICY and fact_type == "card_cancel_timing":
        timing_text = facts.get("refund_timing") or "영업일 기준 수일"
        response = (
            f"카드 승인 취소 반영은 카드사와 결제수단에 따라 달라지고, 보통 {timing_text} 정도 걸릴 수 있어요.\n"
            "실제 반영 시점은 카드사 처리와 주문 취소 완료 시점에 따라 달라질 수 있어요.\n"
            "정확한 반영 여부는 카드사 승인내역과 주문내역을 함께 확인해 주세요."
        )
    elif policy_group == _PAYMENT_REFUND_POLICY and fact_type == "payment_error_troubleshooting":
        response = (
            "결제 오류는 결제수단, 결제창 상태, 장착일 선택 단계 같은 현재 진행 화면에 따라 원인이 달라질 수 있어요.\n"
            "오류 문구, 결제수단, 어느 화면에서 멈췄는지를 확인해야 정확한 안내가 가능해요.\n"
            "같은 문제가 계속되면 1:1 문의나 고객센터로 오류 화면 정보를 함께 남겨 주세요."
        )
    elif policy_group == _ASSURANCE_WARRANTY_POLICY and fact_type == "assurance_coverage_condition":
        response = (
            "안심서비스/안심플러스 보상 조건은 장착 후 1년 이내, 주행거리 16,000km 이내 같은 기본 조건을 먼저 확인해야 해요.\n"
            "안심서비스는 2개 이상, 안심플러스는 4개 구매 기준과 대상 상품·약관에 따라 적용 범위가 달라질 수 있어요.\n"
            "보상 여부는 실제 구매 수량, 대상 상품, 손상 상태를 함께 확인해 주세요."
        )
    elif policy_group == _ASSURANCE_WARRANTY_POLICY and fact_type == "assurance_document_lost":
        response = (
            "종이 보증서를 분실했더라도 디지털 워런티나 구매·장착 이력 기준으로 먼저 확인이 필요해요.\n"
            "보증서 원본만으로 처리 여부를 단정하기보다는 워런티 등록 여부와 구매 이력을 함께 봐야 해요.\n"
            "워런티 정보 확인이 필요하면 나의 워런티 화면이나 고객센터 안내를 함께 확인해 주세요."
        )
    elif policy_group == _ASSURANCE_WARRANTY_POLICY and fact_type == "quality_warranty_condition":
        response = (
            "사이드월 부풀음은 안전 관련 손상일 수 있어서 먼저 점검이 필요해요.\n"
            "무상 수리나 교체 여부는 현장 점검 결과와 구매·장착 이력, 보증 또는 워런티 적용 여부에 따라 결정돼요.\n"
            "워런티 서비스 적용 대상이면 상태 확인 후 안내받을 수 있어요."
        )
    elif policy_group == _BENEFIT_PROMOTION_POLICY and fact_type == "promotion_gift_partial_cancel":
        response = (
            "부분 취소로 이벤트나 프로모션 지급 기준 수량에 미달할 수 있어요.\n"
            "기준 미달 시에는 사은품 반납이 필요할 수 있고, 반납이 어렵거나 조건에 따라 사은품 상당 금액을 차감한 뒤 환불될 수 있어요.\n"
            "최종 적용은 이벤트 상세 조건과 실제 주문/취소 처리 기준에 따라 달라져요."
        )
    elif policy_group == _BENEFIT_PROMOTION_POLICY:
        response = (
            "사은품이나 프로모션 적용 여부는 이벤트 조건과 참여 시점에 따라 달라질 수 있어요.\n"
            "선착순 마감 여부나 지급 기준 충족 여부를 함께 확인해야 결론이 달라질 수 있어요.\n"
            "실제 적용 전에는 이벤트 상세 조건을 먼저 확인해 주세요."
        )
    elif policy_group == _PRODUCT_CONDITION_POLICY and fact_type == "manufacture_date":
        freshness_text = facts.get("freshness_window") or "6~12개월 이내"
        response = (
            f"제조일자 {freshness_text} 제품은 정상 신품 범주로 안내되는 경우가 있어요.\n"
            "다만 제조일자만으로 불량이나 교환·환불 가능 여부를 바로 단정할 수는 없어요.\n"
            "실제 판단 전에는 제품 상태와 구매 이력도 함께 확인해 주세요."
        )
    else:
        response = (
            "현재 챗봇에서는 사진이나 파일을 업로드해 확인받을 수 없어요.\n"
            "사진만으로는 타이어 마모 상태, 교체 필요 여부, 주행 안전을 확정할 수 없어요. 사진이나 파일 첨부가 필요한 경우 1:1 문의를 통해 등록해 주세요.\n"
            "실제 마모도, 균열, 편마모, 손상 여부는 마모도 측정 서비스 또는 가까운 티스테이션 매장 점검으로 확인해 주세요."
        )
    return response, _support_faq_reply_ctas(policy_group, fact_type)


def build_support_faq_source_grounded_reply(
    *,
    intent: str,
    user_text: str,
    tool_result: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if intent not in _SUPPORT_FAQ_SOURCE_GROUNDED_ALLOWLIST:
        return None
    resolution = resolve_support_faq_policy_context(intent, user_text)
    if not resolution or resolution.get("needs_clarification"):
        return None

    policy_group = str(resolution.get("policy_group") or "").strip()
    fact_type = str(resolution.get("fact_type") or "").strip()
    if not policy_group or not fact_type:
        return None

    filtered, excluded_candidates = _filter_support_faq_candidates(policy_group, fact_type, tool_result)
    if not filtered:
        return None

    ranked = sorted(
        enumerate(filtered),
        key=lambda item: (_support_faq_candidate_score(item[1]) is not None, _support_faq_candidate_score(item[1]) or 0.0, -item[0]),
        reverse=True,
    )
    top_candidate = ranked[0][1]
    top_score = _support_faq_candidate_score(top_candidate)
    min_score = _SUPPORT_FAQ_SOURCE_MIN_SCORE_BY_INTENT.get(intent)
    if min_score is not None and top_score is not None and top_score < min_score:
        return None

    competing_candidate = _support_faq_grounded_competing_candidate(
        intent=intent,
        user_text=user_text,
        top_candidate=top_candidate,
        candidates=filtered,
    )
    if competing_candidate is not None:
        second_candidate = competing_candidate
        second_score = _support_faq_candidate_score(second_candidate) or 0.0
        top_topic = _support_faq_candidate_topic(
            intent=intent,
            policy_group=policy_group,
            fact_type=fact_type,
            candidate=top_candidate,
        )
        second_topic = _support_faq_candidate_topic(
            intent=intent,
            policy_group=policy_group,
            fact_type=fact_type,
            candidate=second_candidate,
        )
        required_gap = _SUPPORT_FAQ_SOURCE_SCORE_GAP_BY_INTENT.get(intent, 0.0)
        if top_topic and second_topic and top_topic != second_topic and (top_score or 0.0) - second_score < required_gap:
            return None

    compact_answer = _compact_support_faq_answer(
        intent=intent,
        user_text=user_text,
        policy_group=policy_group,
        fact_type=fact_type,
        candidate=top_candidate,
    )
    if not compact_answer:
        return None

    return {
        "assistant_response": compact_answer,
        "quick_replies": _support_faq_reply_ctas(policy_group, fact_type),
        "metadata": {
            "policyGroup": policy_group,
            "factType": fact_type,
            "clarificationNeeded": False,
            "safeFallbackUsed": False,
            "sourceGroundedReplyUsed": True,
            "filteredFaqCount": len(filtered),
            "excludedFaqCount": len(excluded_candidates),
            "factExtractionApplied": False,
            "topFaqScore": top_score,
            "topFaqCategory": {
                "categoryLv1": _support_faq_candidate_categories(top_candidate)[0] or None,
                "categoryLv2": _support_faq_candidate_categories(top_candidate)[1] or None,
            },
        },
    }


def build_support_faq_evidence_grounded_reply(
    *,
    intent: str,
    user_text: str,
    tool_result: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if intent not in _SUPPORT_FAQ_LLM_GROUNDED_ALLOWLIST:
        return None
    resolution = resolve_support_faq_policy_context(intent, user_text)
    if not resolution:
        return None
    if resolution.get("needs_clarification"):
        return {
            "assistant_response": str(resolution.get("assistant_response") or ""),
            "quick_replies": list(resolution.get("quick_replies") or []),
            "metadata": {
                "policyGroup": resolution.get("policy_group"),
                "factType": resolution.get("fact_type"),
                "clarificationNeeded": True,
                "clarificationReason": resolution.get("clarification_reason"),
                "safeFallbackUsed": False,
                "sourceGroundedReplyUsed": False,
                "evidenceGroundedReplyUsed": False,
                "faqLlmGroundedReplyUsed": False,
                "filteredFaqCount": 0,
                "excludedFaqCount": 0,
                "factExtractionApplied": False,
            },
        }

    policy_group = str(resolution.get("policy_group") or "").strip()
    fact_type = str(resolution.get("fact_type") or "").strip()
    if not policy_group or not fact_type:
        return None

    filtered, excluded_candidates = _filter_support_faq_candidates(policy_group, fact_type, tool_result)
    if not filtered:
        return _build_support_faq_safe_fallback_reply(
            policy_group=policy_group,
            fact_type=fact_type,
            filtered_candidates=[],
            excluded_candidates=excluded_candidates,
            fallback_reason="no_filtered_candidates",
        )

    scope_info = _infer_user_faq_scope(
        intent=intent,
        user_text=user_text,
        policy_group=policy_group,
        fact_type=fact_type,
    )
    selected_evidence = _select_evidence_for_scope(
        intent=intent,
        user_text=user_text,
        policy_group=policy_group,
        fact_type=fact_type,
        candidates=filtered,
        scope_info=scope_info,
    )
    selected_evidence = {
        **selected_evidence,
        **_truncate_selected_evidence(selected_evidence, max_items=_SUPPORT_FAQ_MAX_LLM_EVIDENCE),
    }
    selected_candidates = list(selected_evidence.get("selected_candidates") or [])
    if not selected_candidates:
        return _build_support_faq_safe_fallback_reply(
            policy_group=policy_group,
            fact_type=fact_type,
            filtered_candidates=filtered,
            excluded_candidates=excluded_candidates,
            fallback_reason="no_selected_evidence",
        )

    ranked = _support_faq_ranked_candidates(selected_candidates)
    top_candidate = ranked[0]
    top_score = _support_faq_candidate_score(top_candidate)
    min_score = _SUPPORT_FAQ_SOURCE_MIN_SCORE_BY_INTENT.get(intent)
    if min_score is not None and top_score is not None and top_score < min_score:
        return _build_support_faq_safe_fallback_reply(
            policy_group=policy_group,
            fact_type=fact_type,
            filtered_candidates=selected_candidates,
            excluded_candidates=excluded_candidates,
            fallback_reason="top_score_below_min",
        )

    prompt = _support_faq_evidence_grounded_prompt(
        intent=intent,
        user_text=user_text,
        policy_group=policy_group,
        fact_type=fact_type,
        scope_info=scope_info,
        selected_evidence={
            "primary": list(selected_evidence.get("primary") or []),
            "supporting": list(selected_evidence.get("supporting") or []),
        },
    )
    assistant_response = ""
    failure_reason: str | None = None
    source_candidates = ranked[:_SUPPORT_FAQ_MAX_LLM_EVIDENCE]
    for attempt in range(_SUPPORT_FAQ_LLM_RETRY_LIMIT + 1):
        current_prompt = prompt if attempt == 0 or failure_reason is None else _support_faq_retry_prompt(prompt, failure_reason)
        try:
            assistant_response = _invoke_support_faq_grounded_llm(current_prompt)
        except Exception:
            assistant_response = ""
            failure_reason = "llm_invoke_failed"
            continue
        if not assistant_response:
            failure_reason = "empty_answer"
            continue
        failure_reason = _support_faq_post_check_failure(
            intent=intent,
            user_text=user_text,
            answer=assistant_response,
            source_candidates=source_candidates,
            scope_info=scope_info,
            selected_evidence_types=list(selected_evidence.get("selected_evidence_types") or []),
        )
        if failure_reason is None:
            break
    if not assistant_response or failure_reason is not None:
        return _build_support_faq_safe_fallback_reply(
            policy_group=policy_group,
            fact_type=fact_type,
            filtered_candidates=selected_candidates,
            excluded_candidates=excluded_candidates,
            fallback_reason=str(failure_reason or "llm_answer_missing"),
        )

    return {
        "assistant_response": assistant_response,
        "quick_replies": _support_faq_reply_ctas(policy_group, fact_type),
        "metadata": {
            "policyGroup": policy_group,
            "factType": fact_type,
            "clarificationNeeded": False,
            "safeFallbackUsed": False,
            "evidenceGroundedReplyUsed": True,
            "faqLlmGroundedReplyUsed": True,
            "sourceGroundedReplyUsed": False,
            "filteredFaqCount": len(selected_candidates),
            "excludedFaqCount": len(excluded_candidates),
            "factExtractionApplied": False,
            "topFaqScore": top_score,
            "llmGroundedCandidateCount": len(source_candidates),
            "faqScopes": list(scope_info.get("scopes") or []),
            "selectedEvidenceTypes": list(selected_evidence.get("selected_evidence_types") or []),
            "topFaqCategory": {
                "categoryLv1": _support_faq_candidate_categories(top_candidate)[0] or None,
                "categoryLv2": _support_faq_candidate_categories(top_candidate)[1] or None,
            },
        },
    }


def build_support_faq_llm_grounded_reply(
    *,
    intent: str,
    user_text: str,
    tool_result: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    return build_support_faq_evidence_grounded_reply(intent=intent, user_text=user_text, tool_result=tool_result)


def build_support_faq_policy_reply(
    *,
    intent: str,
    user_text: str,
    tool_result: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    resolution = resolve_support_faq_policy_context(intent, user_text)
    if not resolution:
        return None
    if resolution.get("needs_clarification"):
        return {
            "assistant_response": resolution["assistant_response"],
            "quick_replies": list(resolution.get("quick_replies") or []),
            "metadata": {
                "policyGroup": resolution.get("policy_group"),
                "factType": resolution.get("fact_type"),
                "clarificationNeeded": True,
                "clarificationReason": resolution.get("clarification_reason"),
                "safeFallbackUsed": False,
                "filteredFaqCount": 0,
                "excludedFaqCount": 0,
                "factExtractionApplied": False,
            },
        }

    policy_group = str(resolution.get("policy_group") or "").strip()
    fact_type = str(resolution.get("fact_type") or "").strip()
    if not policy_group or not fact_type:
        return None
    filtered, excluded_candidates = _filter_support_faq_candidates(policy_group, fact_type, tool_result)
    safe_fallback_used = not filtered
    facts = _extract_support_faq_policy_facts(intent, user_text, policy_group, fact_type, filtered)
    response, quick_replies = _build_support_faq_policy_reply(
        policy_group,
        fact_type,
        facts,
        safe_fallback_used=safe_fallback_used,
    )

    allowed_categories = [
        {
            "categoryLv1": _support_faq_candidate_categories(candidate)[0] or None,
            "categoryLv2": _support_faq_candidate_categories(candidate)[1] or None,
        }
        for candidate in filtered
    ]
    bucket = _SUPPORT_FACT_TYPE_TO_BUCKET.get((policy_group, fact_type))
    return {
        "assistant_response": response,
        "quick_replies": quick_replies,
        "metadata": {
            "policyGroup": policy_group,
            "factType": fact_type,
            "clarificationNeeded": False,
            "generalizedAnswerUsed": False,
            "safeFallbackUsed": safe_fallback_used,
            "filteredFaqCount": len(filtered),
            "excludedFaqCount": len(excluded_candidates),
            "allowedCategories": allowed_categories,
            "factExtractionApplied": True,
            "facts": facts,
            "supportFaqBucket": bucket,
        },
    }


def resolve_support_faq_policy_bucket(intent: str, user_text: str) -> dict[str, Any] | None:
    resolution = resolve_support_faq_policy_context(intent, user_text)
    if resolution is None:
        return None
    if resolution.get("needs_clarification"):
        return {
            "bucket": None,
            "needs_clarification": True,
            "clarification_reason": resolution.get("clarification_reason"),
            "assistant_response": resolution.get("assistant_response"),
            "quick_replies": list(resolution.get("quick_replies") or []),
        }
    bucket = _SUPPORT_FACT_TYPE_TO_BUCKET.get(
        (str(resolution.get("policy_group") or ""), str(resolution.get("fact_type") or ""))
    )
    return {"bucket": bucket} if bucket else None


def build_support_faq_policy_bucket_reply(
    *,
    intent: str,
    user_text: str,
    tool_result: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    return build_support_faq_policy_reply(intent=intent, user_text=user_text, tool_result=tool_result)


_EXTREME_COUPON_RE = re.compile(r"90\s*%|99\s*%|파격\s*할인|발급해\s*줘|만들어\s*줘", re.IGNORECASE)
_EXPIRED_COUPON_RE = re.compile(r"만료|끝난|종료|원복|복구|다시\s*쓰", re.IGNORECASE)
_COUPON_RE = re.compile(r"쿠폰|할인권|혜택", re.IGNORECASE)
_SIGNUP_BENEFIT_RE = re.compile(
    r"(회원\s*가입|신규\s*회원|첫\s*구매|처음\s*구매|가입하면).{0,24}(혜택|쿠폰|할인|서비스)|"
    r"(혜택|쿠폰|할인|서비스).{0,24}(회원\s*가입|신규\s*회원|첫\s*구매|처음\s*구매|가입하면)",
    re.IGNORECASE,
)
_PARTNER_MEMBER_COUPON_POLICY_RE = re.compile(
    r"제휴\s*(?:회원|사|몰|전용)|복지몰|임직원|제휴사|제휴회원|제휴\s*쿠폰|제휴\s*혜택",
    re.IGNORECASE,
)
_COUPON_USAGE_POLICY_RE = re.compile(
    r"쿠폰.{0,32}(?:현장\s*결제|매장\s*결제|오프라인|온라인\s*주문\s*없이|온라인\s*전용|매장\s*(?:사용|결제)|"
    r"사용처|어디\s*(?:서|에)|쓸\s*수\s*있|사용\s*가능|현장(?:에서도)?|매장에서)|"
    r"(?:현장\s*결제|매장\s*결제|오프라인|온라인\s*주문\s*없이|온라인\s*전용|매장\s*(?:사용|결제)|"
    r"사용처|어디\s*(?:서|에)|쓸\s*수\s*있|사용\s*가능|현장(?:에서도)?|매장에서).{0,32}쿠폰",
    re.IGNORECASE,
)
_COUPON_REGISTRATION_POLICY_RE = re.compile(
    r"쿠폰.{0,24}(?:번호|등록|입력|코드|등록\s*방법|어디서\s*등록)|"
    r"(?:번호|등록|입력|코드|등록\s*방법|어디서\s*등록).{0,24}쿠폰",
    re.IGNORECASE,
)
_ORDER_DOCUMENT_GUIDANCE_RE = re.compile(
    r"거래\s*명세서|거래명세서|영수증|구매\s*증빙|증빙\s*서류|제출용\s*서류|"
    r"세금\s*계산서|이메일.{0,24}(?:보내|발송)|(?:보내|발송).{0,24}이메일",
    re.IGNORECASE,
)
_TIRE_MANUFACTURE_DATE_POLICY_RE = re.compile(
    r"제조\s*일자|제조일자|제조\s*주차|DOT|최신\s*제조|언제\s*만든|오래된\s*거\s*아냐|신상품\s*맞",
    re.IGNORECASE,
)
_TIRE_QUALITY_WARRANTY_POLICY_RE = re.compile(
    r"측면.{0,12}부풀|사이드월.{0,12}부풀|품질\s*보증|품질보증|무상\s*(?:A/?S|as|교환)|제조상\s*과실|"
    r"보증\s*기준|불량.{0,12}(무상|교환|보상)",
    re.IGNORECASE,
)
_ASSURANCE_SERVICE_POLICY_RE = re.compile(
    r"안심\s*서비스|안심서비스|안심\s*플러스|안심플러스|디지털\s*워런티|종이\s*보증서|"
    r"보증서.{0,12}(분실|잃어버)|가입\s*가능\s*기간|장착비.{0,12}(따로|별도)",
    re.IGNORECASE,
)
_RESERVATION_POLICY_GUIDANCE_RE = re.compile(
    r"예약.{0,16}(취소|변경|장착점|매장\s*변경|몇\s*주|며칠\s*뒤|가능)|당일\s*취소|위약금|"
    r"장착점\s*변경|몇\s*주\s*뒤까지\s*예약|예약\s*가능",
    re.IGNORECASE,
)
_RESERVATION_WINDOW_POLICY_RE = re.compile(
    r"두\s*달\s*뒤|2\s*달\s*뒤|한\s*달\s*넘|1\s*달\s*넘|30일\s*(?:이후|뒤)|"
    r"최대\s*(?:며칠|몇\s*일|몇\s*주)\s*뒤까지|예약\s*가능\s*기간|언제까지\s*장착\s*예약|"
    r"장착\s*예약(?:은)?\s*최대\s*(?:며칠|몇\s*일|몇\s*주)|"
    r"(?:두\s*달|2\s*달).{0,12}예약\s*가능|예약.{0,12}(?:30일|1개월|한\s*달).{0,8}(?:이내|까지)",
    re.IGNORECASE,
)
_DELIVERY_DELAY_RESERVATION_SCHEDULE_POLICY_RE = re.compile(
    r"(?=.*(?:배송\s*지연|상품\s*미도착|미도착|입고\s*지연|배송\s*늦))"
    r"(?=.*(?:예약\s*(?:일정|시간)?.{0,8}자동\s*(?:변경|바뀌|밀리)|"
    r"자동\s*(?:변경|바뀌|밀리).{0,20}예약|예약\s*(?:일정|시간)?.{0,12}(?:변경되|바뀌|밀리)))",
    re.IGNORECASE,
)
_INSTALLATION_WORK_POLICY_RE = re.compile(
    r"작업\s*중\s*취소|장착비|폐타이어|얼라인먼트.{0,16}(현장\s*결제|추가|따로)|"
    r"추가\s*작업|공임(?:비)?.{0,12}(?:취소|작업\s*시작|탈거|분리|이미\s*장착|장착\s*중)",
    re.IGNORECASE,
)
_EXTERNAL_TIRE_INSTALL_SUPPORT_POLICY_RE = re.compile(
    r"인터넷(?:에서)?\s*(?:산|구매한)|외부\s*구매|사제\s*타이어|"
    r"가져가(?:서)?\s*장착|반입\s*장착|들고\s*가(?:서)?\s*장착|"
    r"공임만\s*받고\s*장착|타이어만\s*장착",
    re.IGNORECASE,
)
_PROMOTION_GIFT_POLICY_RE = re.compile(
    r"사은품|선착순|프로모션.{0,12}(취소|반납|차감)|이벤트\s*조건|증정품|4짝.{0,16}2짝\s*취소",
    re.IGNORECASE,
)
_TIRE_CONDITION_PHOTO_POLICY_RE = re.compile(
    r"사진.{0,16}(더\s*타|타도\s*되|봐줘|판독|확인)|마모.{0,12}사진|타이어.{0,12}사진",
    re.IGNORECASE,
)
_SIGNUP_COUPON_GUIDANCE_RE = re.compile(
    r"회원\s*가입|신규\s*회원|가입(?:하면|시)?|웰컴\s*쿠폰|가입\s*쿠폰|신규\s*가입|첫\s*가입",
    re.IGNORECASE,
)
_NONEXISTENT_BENEFIT_RE = re.compile(r"T\s*블랙|블랙\s*멤버십|VIP|브이아이피|블랙\s*카드|50\s*%", re.IGNORECASE)
_HUMAN_RE = re.compile(r"상담원|사람\s*상담|고객센터|전화번호|연결", re.IGNORECASE)
_EXPLICIT_ESCALATION_RE = re.compile(
    r"1:1\s*문의|일대일\s*문의|상담원|상담사|사람\s*상담|문의\s*접수|접수해\s*줘|"
    r"담당자.{0,8}(연결|문의)|상담\s*연결",
    re.IGNORECASE,
)
_PERSONAL_CONTACT_RE = re.compile(
    r"개인\s*(?:핸드폰|휴대폰|전화|번호|연락처)"
    r"|(?:담당자|관리자|직원|사장님|매니저|점장).{0,16}(?:개인\s*)?(?:연락처|번호|전화번호|휴대폰|핸드폰)",
    re.IGNORECASE,
)
_TPMS_RE = re.compile(
    r"TPMS|공기압\s*경고등|공기압\s*점검등|타이어압력모니터링"
    r"|경고등.*안\s*꺼|안\s*꺼.*경고등|경고등.*꺼지지|경고등.*계속",
    re.IGNORECASE,
)
_TIRE_STORAGE_RE = re.compile(
    r"보관\s*서비스|맡긴\s*타이어|타이어\s*보관|보관\s*이력"
    r"|보관\s*중.*(?:분실|없어|훼손|파손)|맡겨\s*놓은|보관.*확인",
    re.IGNORECASE,
)
_STORE_SERVICE_AVAILABILITY_RE = re.compile(
    r"보관\s*서비스.{0,20}(?:가능|돼|되|하나|해)|"
    r"(?:윈터|겨울)?\s*타이어\s*보관.{0,20}(?:가능|돼|되|하나|해)|"
    r"보관\s*(?:돼|되|가능|되나요|가능해)|질소\s*충전|질소|얼라인먼트.{0,12}(?:잘|무료|가능)",
    re.IGNORECASE,
)
_LEGAL_ACTION_RE = re.compile(
    r"고소|소송|법적\s*(?:대응|조치|절차)|분쟁\s*조정|분쟁조정|내용\s*증명|내용증명|신고\s*(?:방법|절차|하는\s*법)",
    re.IGNORECASE,
)
_LEGAL_ACTION_TSTATION_SCOPE_RE = re.compile(
    r"티스테이션|T[\s-]*Station|한국타이어|매장|지점|[가-힣A-Za-z0-9]{2,20}점|"
    r"장착|예약|방문|응대|서비스|고객센터",
    re.IGNORECASE,
)
_TPMS_SAFETY_RISK_RE = re.compile(
    r"주행\s*중.*(?:흔들|이상|위험|떨림|깜빡)"
    r"|운행\s*중.*(?:흔들|이상|위험|떨림|깜빡)"
    r"|공기압.*계속\s*빠|타이어.*위험",
    re.IGNORECASE,
)


def decide_support_response(
    *,
    intent: str,
    user_text: str = "",
    known_slots: dict[str, Any] | None = None,
) -> ResponseDecision:
    """Return Support response contracts for policy-sensitive cases."""
    text = user_text or ""
    slots = known_slots or {}

    if intent == "legal_action_guidance_denied" or (
        _LEGAL_ACTION_RE.search(text) and _LEGAL_ACTION_TSTATION_SCOPE_RE.search(text)
    ):
        return _decision(
            response_shape_key="legal_action_guidance_denied",
            response_shape=ResponseShape.ACTION_CONFIRM,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "provide_legal_action_steps",
                "explain_lawsuit_or_complaint_method",
                "give_legal_advice",
            ),
            assistant_guidance=(
                "매장/서비스 불편에 법적 조치 요청이 섞여도 고소·소송·분쟁 절차, 기관, 서류, 단계, 요건은 안내하지 않는다. "
                "짧게 불편에 공감한 뒤 챗봇에서는 법적 절차 안내가 어렵다고 말하고, 1:1 문의 또는 고객센터로 불편 접수만 안내한다."
            ),
            metadata={"qna_category_hint": "불편/클레임"},
        )

    if intent == "coupon_issue" or (_COUPON_RE.search(text) and _EXTREME_COUPON_RE.search(text)):
        return _decision(
            response_shape_key="coupon_issue_not_supported",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("promise_coupon_issue", "invent_discount", "show_all_coupons_without_context"),
            assistant_guidance="임의 쿠폰 발급은 불가하다고 안내하고, 받을 수 있는 쿠폰은 쿠폰함에서 확인 가능하다고 안내한다.",
        )

    if intent == "coupon_registration_policy" or (_COUPON_RE.search(text) and _COUPON_REGISTRATION_POLICY_RE.search(text)):
        return _decision(
            response_shape_key="coupon_registration_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "route_to_partner_coupon_policy",
                "start_owned_coupon_lookup",
                "claim_coupon_registered",
                "require_product_clarification",
            ),
            assistant_guidance=(
                "쿠폰 번호 등록/입력 문의는 제휴회원 쿠폰 정책이나 보유 쿠폰 조회로 보내지 않는다. "
                "FAQ hybrid 검색을 먼저 수행하고, 쿠폰 등록 위치·입력 방법·쿠폰함 확인 경로를 정책 범위 안에서 안내한다. "
                "상품명이나 특정 상품 적용 여부를 되묻지 않는다."
            ),
        )

    if intent == "coupon_usage_policy" or (
        _COUPON_RE.search(text)
        and _COUPON_USAGE_POLICY_RE.search(text)
        and not _PARTNER_MEMBER_COUPON_POLICY_RE.search(text)
    ):
        return _decision(
            response_shape_key="coupon_usage_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "route_to_partner_coupon_policy",
                "start_owned_coupon_lookup",
                "call_coupon_applicability_tools",
                "require_product_clarification",
                "claim_coupon_usage_confirmed",
            ),
            assistant_guidance=(
                "일반 쿠폰 사용 정책 문의는 제휴회원/복지몰/임직원 전용 쿠폰 안내로 보내지 않는다. "
                "FAQ hybrid 검색을 먼저 수행하고, 쿠폰별 사용처와 유의사항에 따라 온라인 전용인지 매장 사용 가능인지 다를 수 있다고 설명한다. "
                "티스테이션닷컴에서 받은 쿠폰은 쿠폰 상세/유의사항의 사용처 확인이 필요하고, 온라인 주문 전용 쿠폰이면 현장 결제에는 적용되지 않을 수 있다고 안내한다. "
                "보유 쿠폰 목록 조회나 상품별 적용 가능 여부 조회를 시작하지 말고, 현재 매장에서 결제 중이면 매장 직원에게 사용 가능 여부를 확인하도록 보조 안내한다."
            ),
        )

    if intent == "personal_contact" or _PERSONAL_CONTACT_RE.search(text):
        return _decision(
            response_shape_key="personal_contact_denied",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("share_personal_contact", "invent_staff_contact"),
            assistant_guidance="개인 연락처는 제공할 수 없으며 공식 고객센터 또는 1:1 문의 경로만 안내한다.",
        )

    if slots.get("qna_required"):
        return _decision(
            response_shape_key="qna_required",
            response_shape=ResponseShape.ACTION_CONFIRM,
            template=TemplateName.QNA_COMPLETE,
            forbidden_behaviors=("answer_without_required_evidence",),
            assistant_guidance="정책/주문 근거 확인이 필요한 건은 요약 후 1:1 문의로 연결한다.",
        )

    if intent == "human_escalation" or _EXPLICIT_ESCALATION_RE.search(text):
        return _decision(
            response_shape_key="human_escalation",
            response_shape=ResponseShape.ACTION_CONFIRM,
            template=TemplateName.QNA_COMPLETE,
            forbidden_behaviors=("overpromise_live_agent", "hide_official_contact"),
            assistant_guidance="챗봇 처리 한계를 인정하고 1:1 문의 또는 공식 고객센터 번호 안내로 연결한다.",
        )

    if intent == "tire_manufacture_date_policy" or _TIRE_MANUFACTURE_DATE_POLICY_RE.search(text):
        return _decision(
            response_shape_key="tire_manufacture_date_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "transfer_to_qna_direct_first",
                "claim_defect_from_manufacture_date_only",
                "promise_exchange_or_refund",
            ),
            assistant_guidance=(
                "타이어 제조일자/DOT/신품 여부 문의는 FAQ hybrid 검색을 먼저 수행하고, 검색 근거 범위 안에서 "
                "6~12개월 이내 제품은 정상 신품 범주로 안내한다. 제조일자만으로 불량, 교환, 환불을 단정하지 말고 "
                "정책 안내를 먼저 제공한다."
            ),
        )

    if intent == "delivery_delay_reservation_schedule_policy" or _DELIVERY_DELAY_RESERVATION_SCHEDULE_POLICY_RE.search(text):
        return _decision(
            response_shape_key="delivery_delay_reservation_schedule_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "start_owned_reservation_lookup",
                "normalize_as_store_schedule_lookup",
                "claim_personal_reservation_changed",
            ),
            assistant_guidance=(
                "배송 지연 때문에 예약 일정이 자동 변경되는지 묻는 경우는 일반 정책 안내다. "
                "내 예약/주문 조회나 매장 예약 가능 시간 조회를 먼저 시작하지 말고, 배송 지연으로 예약 일정이 자동 변경되지는 않으며 "
                "상품이 예약 일정에 맞춰 도착하지 않으면 매장 해피콜 등으로 안내받을 수 있다고 설명한다."
            ),
        )

    if intent == "tire_quality_warranty_policy" or _TIRE_QUALITY_WARRANTY_POLICY_RE.search(text):
        return _decision(
            response_shape_key="tire_quality_warranty_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "transfer_to_qna_direct_first",
                "claim_free_replacement_without_inspection",
                "normalize_as_store_attribute_inquiry",
            ),
            assistant_guidance=(
                "측면 부풀음, 품질보증, 무상 A/S 기준 문의는 FAQ hybrid 검색을 먼저 수행하고, 제조상 과실 보증 기간, "
                "잔여 홈 깊이, 현장 점검 필요 여부를 근거 기반으로 요약한다. 현재 매장명이나 과거 구매 맥락만으로 "
                "특정 매장 속성 문의로 바꾸지 않는다."
            ),
        )

    if intent == "assurance_service_policy" or _ASSURANCE_SERVICE_POLICY_RE.search(text):
        return _decision(
            response_shape_key="assurance_service_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "transfer_to_qna_direct_first",
                "claim_compensation_confirmed",
                "skip_assurance_policy_summary",
            ),
            assistant_guidance=(
                "안심서비스/안심플러스/디지털워런티/보증서 문의는 FAQ hybrid 검색을 먼저 수행하고, 가입 가능 기간, "
                "보상 조건, 장착비/추가 비용 여부를 검색 근거 범위 안에서 설명한다. 장착 후 1년 이내와 주행거리 "
                "16,000km 이내 기준을 포함하되, 보상 확정이나 자동 접수처럼 말하지 않는다."
            ),
        )

    if intent == "reservation_window_policy" or _RESERVATION_WINDOW_POLICY_RE.search(text):
        return _decision(
            response_shape_key="reservation_window_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "transfer_to_qna_direct_first",
                "normalize_as_store_schedule_lookup",
                "require_store_slot_for_window_policy",
            ),
            assistant_guidance=(
                "예약 가능 기간 제한 문의는 FAQ hybrid 검색을 먼저 수행하고, 장착 예약일 최대 기간과 범위 밖 예약 제한을 "
                "정책 기준으로 quickReply에 요약한다. 두 달 뒤처럼 범위를 넘는 요청은 매장 슬롯 조회로 바꾸지 말고 "
                "정책 제한을 먼저 설명한다."
            ),
        )

    if intent == "reservation_policy_guidance" or _RESERVATION_POLICY_GUIDANCE_RE.search(text):
        return _decision(
            response_shape_key="reservation_policy_guidance",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "transfer_to_qna_direct_first",
                "start_owned_reservation_lookup_without_anchor",
                "skip_reservation_policy_summary",
            ),
            assistant_guidance=(
                "예약 가능 기간, 취소, 변경, 장착점 변경 같은 일반 예약 정책 문의는 FAQ hybrid 검색을 먼저 수행하고 "
                "정책 안내를 quickReply로 요약한다. 주문번호, 내 예약, 오늘 예약 같은 owned anchor 없이 "
                "개인 예약/주문 조회를 시작하지 않는다."
            ),
        )

    if intent == "external_tire_install_policy" or _EXTERNAL_TIRE_INSTALL_SUPPORT_POLICY_RE.search(text):
        return _decision(
            response_shape_key="external_tire_install_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "transfer_to_qna_direct_first",
                "claim_external_tire_install_supported",
                "reuse_work_started_cancel_guidance",
            ),
            assistant_guidance=(
                "외부 구매 타이어 반입 장착 문의는 FAQ hybrid 검색을 먼저 수행하고, 온라인몰 지정 장착점 발송/장착 기준, "
                "별도 수령 후 직접 반입 장착 제한 여부, 오프라인 매장 구매 후 장착 및 매장별 비용 차이만 근거 범위에서 요약한다. "
                "작업 시작 후 취소/위약금 안내로 바꾸지 말고, 매장별 운영 확인이 필요하다는 점을 함께 안내한다."
            ),
        )

    if intent == "installation_work_policy" or _INSTALLATION_WORK_POLICY_RE.search(text):
        return _decision(
            response_shape_key="installation_work_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "transfer_to_qna_direct_first",
                "claim_store_specific_work_supported",
                "skip_installation_policy_summary",
            ),
            assistant_guidance=(
                "공임, 장착비, 추가 작업, 폐타이어 비용, 현장 결제 여부 같은 작업 정책 문의는 FAQ hybrid 검색을 먼저 수행하고 "
                "일반 정책 범위만 요약한다. 매장별 가능 여부나 현장 운영을 확인 없이 단정하지 않는다."
            ),
        )

    if intent == "promotion_gift_policy" or _PROMOTION_GIFT_POLICY_RE.search(text):
        return _decision(
            response_shape_key="promotion_gift_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "transfer_to_qna_direct_first",
                "claim_gift_kept_or_revoked",
                "skip_promotion_condition_summary",
            ),
            assistant_guidance=(
                "사은품/선착순/이벤트 조건 문의는 FAQ hybrid 검색을 먼저 수행하고, 조건 미달 시 반납 또는 차감 가능성과 "
                "실시간 마감 확인 필요를 근거 범위 안에서 설명한다. 지급/미지급을 확정하지 않는다."
            ),
        )

    if intent == "tire_condition_photo_policy" or _TIRE_CONDITION_PHOTO_POLICY_RE.search(text):
        return _decision(
            response_shape_key="tire_condition_photo_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "transfer_to_qna_direct_first",
                "judge_safety_from_photo_only",
                "claim_safe_to_drive_without_inspection",
            ),
            assistant_guidance=(
                "타이어 상태를 사진으로 봐달라는 문의는 FAQ/RAG 요약보다 고정 정책 안내를 우선한다. "
                "현재 챗봇에서는 사진/파일 업로드 확인이 불가능하다고 먼저 안내하고, 사진만으로 마모 상태, 교체 필요 여부, "
                "주행 안전을 확정할 수 없다고 분명히 말한다. 사진/파일 첨부가 필요하면 1:1 문의를 통해 등록하도록 안내하고, "
                "실제 확인은 마모도 측정 서비스 또는 가까운 매장/전문 점검으로 유도한다."
            ),
        )

    if intent == "signup_coupon_guidance" or (
        intent != "signup_first_purchase_benefit_policy"
        and intent != "signup_coupon_guidance"
        and _COUPON_RE.search(text)
        and _SIGNUP_COUPON_GUIDANCE_RE.search(text)
    ):
        return _decision(
            response_shape_key="signup_coupon_guidance",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "start_owned_coupon_lookup",
                "route_to_partner_coupon_policy",
                "claim_signup_coupon_already_issued",
                "claim_signup_coupon_always_available",
                "claim_first_purchase_only_coupon",
                "direct_qna_complete_first",
            ),
            assistant_guidance=(
                "회원가입 전용/신규회원/웰컴/첫구매 쿠폰 문의는 제휴회원 쿠폰 안내로 보내지 않는다. "
                "확인된 정책 기준으로 all my T 회원이고 마케팅 수신 동의를 하면 5% 할인 쿠폰 발급이 가능하다고 안내한다. "
                "첫구매 여부를 핵심 조건으로 말하지 말고, 계정의 실제 회원 상태, 마케팅 수신 동의 상태, 발급 여부는 "
                "챗봇이 직접 확정하지 않는다고 설명한다."
            ),
        )

    if intent == "signup_first_purchase_benefit_policy" or (
        intent != "signup_coupon_guidance" and _SIGNUP_BENEFIT_RE.search(text)
    ):
        return _decision(
            response_shape_key="signup_first_purchase_benefit_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "claim_first_purchase_only_coupon",
                "promise_signup_coupon_issued",
                "start_owned_coupon_lookup",
                "call_coupon_issue_tool",
                "direct_qna_complete_first",
            ),
            assistant_guidance=(
                "회원가입/신규회원/첫구매 쿠폰 문의는 첫구매 전용 쿠폰으로 단정하지 않는다. 확인된 정책 기준으로 "
                "all my T 회원이고 마케팅 수신 동의를 하면 5% 할인 쿠폰 발급이 가능하다고만 안내한다. "
                "계정의 실제 회원 상태, 마케팅 수신 동의 상태, 발급 여부는 챗봇이 직접 확정하지 않으며, "
                "조건 충족 시 발급 가능하다고만 표현한다. 보유 쿠폰 조회, 직접 발급, qnaComplete 직행으로 시작하지 않는다."
            ),
        )

    if intent == "order_document_guidance" or _ORDER_DOCUMENT_GUIDANCE_RE.search(text):
        return _decision(
            response_shape_key="order_document_guidance",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "direct_email_document_send",
                "direct_qna_complete_first",
                "skip_order_history_guidance",
            ),
            assistant_guidance=(
                "거래명세서/영수증/구매 증빙/회사 제출용 서류 문의는 챗봇이 이메일 직접 발송을 처리할 수 없다고 먼저 안내한다. "
                "그 다음 주문 내역에서 해당 주문의 증빙/거래명세서 정보를 확인하는 경로를 우선 제시하고, "
                "별도 양식이나 이메일 발송 요청이 더 필요할 때만 1:1 문의를 보조 CTA로 둔다. "
                "사용자가 명시적으로 접수/문의 생성을 요청하지 않는 한 qnaComplete를 바로 시작하지 않는다."
            ),
        )

    if intent == "partner_member_coupon_policy" or (
        _COUPON_RE.search(text) and _PARTNER_MEMBER_COUPON_POLICY_RE.search(text)
    ):
        return _decision(
            response_shape_key="partner_member_coupon_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "start_owned_coupon_lookup",
                "claim_partner_member_verified",
                "claim_coupon_already_issued",
                "show_owned_coupon_voucher",
                "route_to_signup_coupon_guidance",
            ),
            assistant_guidance=(
                "제휴회원/제휴사/복지몰/임직원 전용 쿠폰 문의는 보유 쿠폰 조회가 아니라 접근 권한/접속 경로 정책으로 안내한다. "
                "현재 회원이 제휴회원인지 챗봇에서 직접 확인하지 못하면 그 한계를 명시하고, "
                "제휴사 전용 URL 또는 제휴몰 경로에서 확인이 필요하며 제휴 기간과 제휴사별 조건이 다를 수 있다고 설명한다."
            ),
        )

    if intent == "expired_coupon" or (_COUPON_RE.search(text) and _EXPIRED_COUPON_RE.search(text)):
        return _decision(
            response_shape_key="expired_coupon_not_restorable_qna",
            response_shape=ResponseShape.ACTION_CONFIRM,
            template=TemplateName.QNA_COMPLETE,
            forbidden_behaviors=("promise_coupon_restore", "omit_non_restorable_policy"),
            assistant_guidance="만료된 쿠폰은 원칙적으로 원복/재사용이 어렵다고 먼저 안내한 뒤 1:1 문의 CTA를 연결한다.",
            metadata={"qna_category_hint": "제공서비스/이벤트/혜택"},
        )

    if intent == "nonexistent_benefit" or _NONEXISTENT_BENEFIT_RE.search(text):
        return _decision(
            response_shape_key="unverified_benefit_denied",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("acknowledge_fake_vip_benefit", "invent_discount", "provide_fake_benefit_link"),
            assistant_guidance="확인되지 않은 VIP/블랙카드/50% 혜택은 인정하지 않고 공식 쿠폰/이벤트 확인 경로만 안내한다.",
        )

    if intent in ("tpms_guidance", "tire_safety_guidance") or _TPMS_RE.search(text):
        if _TPMS_SAFETY_RISK_RE.search(text):
            return _decision(
                response_shape_key="tpms_safety_risk_urgent",
                response_shape=ResponseShape.SUMMARY,
                template=TemplateName.QUICK_REPLY,
                forbidden_behaviors=("auto_escalate_to_qna", "downplay_safety_risk", "skip_urgent_inspection_advice"),
                assistant_guidance=(
                    "주행 중 흔들림·경고등 동시 발생은 즉시 안전한 곳에 정차해 공기압 확인 및 매장 점검을 강하게 권장한다. "
                    "1:1 문의 자동 전환은 금지하고 매장 찾기 CTA를 우선 제공한다."
                ),
            )
        return _decision(
            response_shape_key="tpms_general_guidance",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("auto_escalate_to_qna", "skip_general_guidance"),
            assistant_guidance=(
                "교체 후 TPMS/공기압 경고등이 안 꺼지는 것은 일반 정비 안내로 처리한다: "
                "(1) 안전한 곳 정차 후 실제 공기압 확인, "
                "(2) TPMS 초기화/리셋 필요 가능, "
                "(3) 주행 후 일정 시간 지나면 꺼지는 경우 있음, "
                "(4) 리셋 방법은 차량 매뉴얼/정비사 확인, "
                "(5) 계속 경고 시 매장 점검 권장. 자동 1:1 연결 금지."
            ),
        )

    if intent == "tire_storage_service" or _TIRE_STORAGE_RE.search(text):
        return _decision(
            response_shape_key="keep_service_hist_cta",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("auto_escalate_to_qna", "skip_storage_history_cta"),
            assistant_guidance=(
                "매장에 보관한 타이어는 보관 서비스 이력에서 확인할 수 있음을 안내하고 "
                "keepservice-hist CTA를 첫 번째 chip으로 제공한다. "
                "분실·훼손 언급이 있어도 1:1 문의 자동 연결 금지 — 보관 이력 확인을 우선."
            ),
        )

    if intent == "store_service_availability" or _STORE_SERVICE_AVAILABILITY_RE.search(text):
        return _decision(
            response_shape_key="store_service_availability",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("claim_unverified_store_service_available", "show_datepick_for_store_service"),
            assistant_guidance=(
                "매장별 서비스 운영 여부는 확정 단정하지 말고 매장별로 다를 수 있음을 안내한다. "
                "매장명이 있으면 그 매장 기준 직접 확인을 권장하고, 매장명이 없으면 어느 매장 기준인지 확인한다."
            ),
        )

    if intent == "payment_error_troubleshooting" and not _is_card_installment_lookup_query(text):
        return _decision(
            response_shape_key="payment_error_troubleshooting",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "qna_without_faq_solution",
                "infer_payment_provider_or_browser_cause_without_faq",
            ),
            assistant_guidance=(
                "결제 오류/결제창/결제 진행 불가 문의는 FAQ hybrid 검색을 먼저 수행하고, FAQ 근거로 시도 가능한 해결 방법을 안내한다. "
                "1:1 문의는 해결 방법 안내 후에도 문제가 지속될 때 fallback CTA로만 제공한다."
            ),
        )

    if intent == "general_card_cancel_timing_policy" or is_general_card_cancel_timing_policy_query(text):
        return _decision(
            response_shape_key="general_card_cancel_timing_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "start_owned_order_lookup",
                "claim_specific_refund_completed",
                "normalize_as_order_status_lookup",
            ),
            assistant_guidance=(
                "카드 승인취소/환불 반영 기간 문의는 일반 정책 안내로 처리한다. 주문번호, 내 주문/상태 조회 같은 owned-order anchor 없이 "
                "주문 조회를 시작하지 말고, 카드사/결제수단별 반영 기간과 확인 경로를 설명한다."
            ),
        )

    if intent == "my_goods_review_lookup":
        return _decision(
            response_shape_key="my_goods_review_lookup",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("omit_goods_review_cta", "route_goods_review_to_store_service_history"),
            assistant_guidance=(
                "내가 쓴 상품 리뷰/구매후기/베스트리뷰 선정 여부 확인 경로는 마이페이지 > 리뷰관리만 안내한다. "
                "GOODS_REVIEW CTA가 첫 번째 quickReply가 아니면 보정 대상이다."
            ),
        )

    if intent in {"store_service_review_write", "store_review_write"}:
        return _decision(
            response_shape_key="store_service_review_write",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("omit_store_service_history_cta", "invent_external_review_path"),
            assistant_guidance=(
                "매장 리뷰/후기/칭찬/별점 작성 경로는 마이페이지 > 매장서비스 내역만 안내한다. "
                "STORE_SERVICE_HISTORY CTA가 첫 번째 quickReply가 아니면 보정 대상이다."
            ),
        )

    if _HUMAN_RE.search(text):
        return _decision(
            response_shape_key="human_escalation",
            response_shape=ResponseShape.ACTION_CONFIRM,
            template=TemplateName.QNA_COMPLETE,
            forbidden_behaviors=("overpromise_live_agent", "hide_official_contact"),
            assistant_guidance="챗봇 처리 한계를 인정하고 1:1 문의 또는 공식 고객센터 번호 안내로 연결한다.",
        )

    return _decision(
        response_shape_key="support_faq_summary",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        assistant_guidance="FAQ 근거 범위 안에서 간결히 답하고 필요한 경우 관련 CTA를 제공한다.",
    )


def _decision(
    *,
    response_shape_key: str,
    response_shape: ResponseShape,
    template: TemplateName,
    required_slots: tuple[str, ...] = (),
    forbidden_behaviors: tuple[str, ...] = (),
    assistant_guidance: str = "",
    metadata: dict[str, Any] | None = None,
) -> ResponseDecision:
    return ResponseDecision(
        response_shape=response_shape,
        template=template,
        required_slots=required_slots,
        forbidden_behaviors=forbidden_behaviors,
        assistant_guidance=assistant_guidance,
        metadata={"response_shape_key": response_shape_key, **dict(metadata or {})},
    )
