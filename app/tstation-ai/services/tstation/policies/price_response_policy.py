"""Deterministic response policy for price/coupon-sensitive flows."""

from __future__ import annotations

import re
from typing import Any

from services.tstation.policies.intent_frame import IntentFrame, PolicyDomain
from services.tstation.policies.response_decision import ResponseDecision, ResponseShape, TemplateName, ToolPlan


_COUPON_RE = re.compile(r"쿠폰|할인권|혜택", re.IGNORECASE)
_ISSUE_RE = re.compile(r"발급|받아\s*줘|만들어\s*줘|주세요|링크\s*보내|다운로드", re.IGNORECASE)
_EXTREME_DISCOUNT_RE = re.compile(r"(?:50|70|80|90|99)\s*%|반값|공짜|무료", re.IGNORECASE)
_EXPIRED_RE = re.compile(r"만료|끝난|종료|지난|작년", re.IGNORECASE)
_RESTORE_RE = re.compile(
    r"원복|복구|재사용|다시\s*(?:쓰|쓸|사용)|되살|살려|부활|연장|못\s*쓰.*(?:해줘|할\s*수)",
    re.IGNORECASE,
)
_NONEXISTENT_BENEFIT_RE = re.compile(r"T\s*블랙|블랙\s*멤버십|VIP|브이아이피|블랙\s*카드|50\s*%", re.IGNORECASE)
_STACKING_RE = re.compile(r"중복|같이|동시|함께|둘\s*다|더\s*쓸|추가\s*적용", re.IGNORECASE)
_BIRTHDAY_COUPON_RE = re.compile(r"생일|birthday", re.IGNORECASE)
_FAMILY_COUPON_RE = re.compile(r"패밀리|family", re.IGNORECASE)
_EMPLOYEE_COUPON_RE = re.compile(r"임직원|employee|직원", re.IGNORECASE)
_PERCENT_COUPON_RE = re.compile(r"(\d{1,2})\s*%")
_PRODUCT_RE = re.compile(
    r"키너지\s*EX|kinergy\s*EX|벤투스\s*(?:air\s*S|S2\s*AS)|ventus\s*(?:air\s*S|S2\s*AS)|"
    r"다이나프로\s*HPX|dynapro\s*HPX|아이온|iON",
    re.IGNORECASE,
)
_PROMOTION_RE = re.compile(r"기획전|이벤트|프로모션|행사|딜|deal|멀티브랜드", re.IGNORECASE)


def build_price_intent_frame(
    user_text: str,
    *,
    known_slots: dict[str, Any] | None = None,
) -> IntentFrame:
    """Classify policy-sensitive price/coupon turns into a shared IntentFrame."""
    text = user_text or ""
    slots = known_slots or {}
    entities: dict[str, Any] = {
        "has_coupon_keyword": bool(_COUPON_RE.search(text)),
        "has_promotion_keyword": bool(_PROMOTION_RE.search(text)),
    }
    product_match = _PRODUCT_RE.search(text)
    if product_match:
        entities["product_name"] = _normalize_product_name(product_match.group(0))
    elif slots.get("product_name"):
        entities["product_name"] = slots["product_name"]

    percent_match = _PERCENT_COUPON_RE.search(text)
    if percent_match:
        entities["discount_rate"] = int(percent_match.group(1))
    if _BIRTHDAY_COUPON_RE.search(text):
        entities["coupon_keyword"] = "birthday"
        entities["coupon_scope"] = "pattern"
    elif _FAMILY_COUPON_RE.search(text):
        entities["coupon_keyword"] = "family"
        entities["coupon_scope"] = "pattern"
    elif _EMPLOYEE_COUPON_RE.search(text):
        entities["coupon_keyword"] = "employee"
        entities["coupon_scope"] = "pattern"

    if _NONEXISTENT_BENEFIT_RE.search(text) and (_ISSUE_RE.search(text) or _COUPON_RE.search(text)):
        intent = "nonexistent_benefit"
        sub_intent = "deny_unverified_benefit"
    elif (
        _EXPIRED_RE.search(text)
        and _RESTORE_RE.search(text)
        and (_COUPON_RE.search(text) or _PROMOTION_RE.search(text))
    ):
        intent = "expired_coupon_or_event"
        sub_intent = "restore_not_supported"
    elif _COUPON_RE.search(text) and _ISSUE_RE.search(text) and _EXTREME_DISCOUNT_RE.search(text):
        intent = "coupon_issue_request"
        sub_intent = "arbitrary_coupon_issue"
    elif (_COUPON_RE.search(text) or _PROMOTION_RE.search(text)) and _STACKING_RE.search(text):
        intent = "coupon_stacking_check"
        sub_intent = "coupon_or_promotion_stacking"
    elif _COUPON_RE.search(text) and percent_match and re.search(r"적용\s*가능|대상|상품", text):
        intent = "coupon_applicable_products"
        sub_intent = "discount_rate_coupon_targets"
    elif _COUPON_RE.search(text) and (entities.get("product_name") or slots.get("goods_no")):
        intent = "product_coupon_eligibility"
        sub_intent = "product_or_pattern_coupon"
    else:
        intent = "price_coupon_summary"
        sub_intent = None

    return IntentFrame(
        domain=PolicyDomain.TRANSACTION,
        intent=intent,
        sub_intent=sub_intent,
        entities=entities,
        known_slots=slots,
        confidence=0.9,
        source="price_response_policy",
    )


def plan_price_tools(frame: IntentFrame) -> ToolPlan:
    """Return the tool contract implied by a price/coupon intent frame."""
    if frame.intent == "coupon_issue_request":
        return ToolPlan(
            allowed_tools=(),
            preferred_tool=None,
            forbidden_tools=("issue_coupon_tool",),
            metadata={"policy": "coupon_issue_denied"},
        )
    if frame.intent in {"expired_coupon_or_event", "nonexistent_benefit"}:
        return ToolPlan(
            allowed_tools=(),
            preferred_tool=None,
            forbidden_tools=("issue_coupon_tool", "get_coupon_applicable_products_tool"),
            metadata={"policy": frame.intent},
        )
    if frame.intent == "coupon_stacking_check":
        return ToolPlan(
            allowed_tools=("get_my_coupons_tool", "check_coupon_stacking_tool"),
            preferred_tool="get_my_coupons_tool",
            required_slots=("coupon_identifiers",),
            forbidden_tools=("faq_answer_without_coupon_condition_check", "issue_coupon_tool"),
            metadata={"requires_stacking_check": True},
        )
    if frame.intent == "coupon_applicable_products":
        return ToolPlan(
            allowed_tools=("get_my_coupons_tool", "get_coupon_applicable_products_tool"),
            preferred_tool="get_my_coupons_tool",
            required_slots=("coupon_identifier",),
            forbidden_tools=("get_events_tool", "issue_coupon_tool"),
            metadata={"resolve_coupon_before_targets": True},
        )
    if frame.intent == "product_coupon_eligibility":
        return ToolPlan(
            allowed_tools=("get_my_coupons_tool", "get_product_promotions_tool", "get_coupon_applicable_products_tool"),
            preferred_tool="get_my_coupons_tool",
            forbidden_tools=("issue_coupon_tool",),
            metadata={"separate_owned_and_downloadable": True, "do_not_require_size_first": True},
        )
    return ToolPlan(
        allowed_tools=("get_my_coupons_tool", "get_product_promotions_tool"),
        preferred_tool="get_my_coupons_tool",
        forbidden_tools=("issue_coupon_tool",),
    )


def decide_price_response(frame: IntentFrame) -> ResponseDecision:
    """Return response contracts for price/coupon-sensitive cases."""
    if frame.intent == "coupon_issue_request":
        return _decision(
            response_shape_key="coupon_issue_not_supported",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("promise_coupon_issue", "invent_discount", "show_coupon_download_cta"),
            assistant_guidance=(
                "임의 쿠폰 발급은 불가하다고 명확히 안내하고, 보유 쿠폰/받을 수 있는 쿠폰 확인 CTA로만 유도한다."
            ),
            metadata={"cta_policy": "coupon_box_only"},
        )
    if frame.intent == "expired_coupon_or_event":
        return _decision(
            response_shape_key="expired_coupon_not_restorable_qna",
            response_shape=ResponseShape.ACTION_CONFIRM,
            template=TemplateName.QNA_COMPLETE,
            forbidden_behaviors=("promise_coupon_restore", "promise_ended_event_reuse", "omit_non_restorable_policy"),
            assistant_guidance="만료 쿠폰/종료 이벤트는 원칙적으로 원복/재사용 불가를 안내하고 클레임은 1:1 문의로 연결한다.",
            metadata={"qna_category_hint": "제공서비스/이벤트/혜택"},
        )
    if frame.intent == "nonexistent_benefit":
        return _decision(
            response_shape_key="unverified_benefit_denied",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("acknowledge_fake_vip_benefit", "invent_discount", "provide_fake_benefit_link"),
            assistant_guidance="확인되지 않은 VIP/블랙카드/50% 혜택은 인정하지 않고 공식 쿠폰/이벤트 확인 경로만 안내한다.",
        )
    if frame.intent == "coupon_stacking_check":
        return _decision(
            response_shape_key="coupon_stacking_condition_check",
            response_shape=ResponseShape.CLARIFY,
            template=TemplateName.QUICK_REPLY,
            required_slots=("coupon_identifiers",),
            forbidden_behaviors=("generic_faq_answer", "infer_stacking_without_tool", "promise_coupon_application"),
            assistant_guidance="FAQ 일반론으로 답하지 말고 쿠폰 조건/중복 가능 여부 조회 흐름으로 안내한다.",
        )
    if frame.intent == "coupon_applicable_products":
        return _decision(
            response_shape_key="coupon_applicable_products_by_owned_coupon",
            response_shape=ResponseShape.CLARIFY,
            template=TemplateName.QUICK_REPLY,
            required_slots=("coupon_identifier",),
            forbidden_behaviors=("treat_discount_rate_as_event", "list_all_events", "promise_coupon_application"),
            assistant_guidance="보유 쿠폰 중 해당 할인율 쿠폰을 먼저 특정하고, 그 쿠폰의 대상 상품 조건을 확인한다.",
        )
    if frame.intent == "product_coupon_eligibility":
        return _decision(
            response_shape_key="product_coupon_eligibility",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=("product_or_pattern",),
            forbidden_behaviors=("require_size_first", "mix_owned_and_downloadable_coupons", "promise_coupon_application"),
            assistant_guidance="특정 상품/패턴 쿠폰 문의는 규격 요구보다 쿠폰 적용 대상, 보유 여부, 다운 가능 여부를 분리해 안내한다.",
        )
    return _decision(
        response_shape_key="price_coupon_summary",
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        forbidden_behaviors=("promise_coupon_application", "invent_discount"),
        assistant_guidance="가격/쿠폰 데이터 근거가 확인된 범위에서만 안내한다.",
    )


def _normalize_product_name(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip())
    aliases = {
        "kinergy ex": "Kinergy EX",
        "키너지 ex": "Kinergy EX",
        "dynapro hpx": "Dynapro HPX",
        "다이나프로 hpx": "Dynapro HPX",
        "ventus air s": "Ventus air S",
        "벤투스 air s": "Ventus air S",
        "ventus s2 as": "Ventus S2 AS",
        "벤투스 s2 as": "Ventus S2 AS",
    }
    return aliases.get(normalized.casefold(), normalized)


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
