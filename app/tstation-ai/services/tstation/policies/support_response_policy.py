"""Deterministic response policy for Support/FAQ/escalation flows."""

from __future__ import annotations

import re
from typing import Any, Mapping

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
    "payment_error_troubleshooting",
    "tire_manufacture_date_policy",
    "tire_quality_warranty_policy",
    "assurance_service_policy",
    "reservation_policy_guidance",
    "installation_work_policy",
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
    r"작업\s*시작|작업\s*중|기존\s*타이어|다\s*뺐|탈거|분리|장착\s*하려고|공임비",
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
    if normalized_intent == "payment_error_troubleshooting" or _PAYMENT_ERROR_RE.search(text):
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
    return facts


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
                        f"{condition_text} 취소 수수료가 발생할 수 있고, FAQ 기준으로는 {amount_text} 안내돼요."
                    )
                else:
                    lines.append(
                        "다만 온라인몰에서 결제까지 완료된 주문이라면 "
                        f"{condition_text} 취소 수수료가 발생할 수 있다고 안내돼요."
                    )
            if has_card:
                lines.append(
                    f"결제 취소가 완료된 뒤 카드 환불 반영은 보통 {facts.get('card_refund_timing')} 정도 걸릴 수 있어요."
                )
            response = "\n\n".join(lines)
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
    elif policy_group == _PURCHASE_ORDER_POLICY and fact_type == "online_order_cancel_fee":
        amount_text = facts.get("fee_amount") or "취소 시점과 주문 상태에 따라 비용이 달라질 수 있어요."
        response = (
            "결제 완료 주문 취소 기준으로는 배송/처리 진행 상태에 따라 취소 비용이 달라질 수 있어요.\n"
            f"현재 FAQ 근거로는 {amount_text} 기준 안내가 우선이에요.\n"
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
    facts = _extract_support_faq_policy_facts(policy_group, fact_type, filtered)
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
            "generalizedAnswerUsed": bool(
                policy_group == _RESERVATION_INSTALLATION_POLICY and fact_type == "mixed_cancel_fee_generalized"
            ),
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
_DELIVERY_DELAY_RESERVATION_SCHEDULE_POLICY_RE = re.compile(
    r"(?=.*(?:배송\s*지연|상품\s*미도착|미도착|입고\s*지연|배송\s*늦))"
    r"(?=.*(?:예약\s*(?:일정|시간)?.{0,8}자동\s*(?:변경|바뀌|밀리)|"
    r"자동\s*(?:변경|바뀌|밀리).{0,20}예약|예약\s*(?:일정|시간)?.{0,12}(?:변경되|바뀌|밀리)))",
    re.IGNORECASE,
)
_INSTALLATION_WORK_POLICY_RE = re.compile(
    r"작업\s*중\s*취소|공임(?:비)?|장착비|폐타이어|얼라인먼트.{0,16}(현장\s*결제|추가|따로)|"
    r"공임만\s*받고\s*장착|추가\s*작업",
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

    if intent == "payment_error_troubleshooting":
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
