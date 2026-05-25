"""Deterministic response policy for Support/FAQ/escalation flows."""

from __future__ import annotations

import re
from typing import Any

from services.tstation.policies.response_decision import ResponseDecision, ResponseShape, TemplateName


_EXTREME_COUPON_RE = re.compile(r"90\s*%|99\s*%|파격\s*할인|발급해\s*줘|만들어\s*줘", re.IGNORECASE)
_EXPIRED_COUPON_RE = re.compile(r"만료|끝난|종료|원복|복구|다시\s*쓰", re.IGNORECASE)
_COUPON_RE = re.compile(r"쿠폰|할인권|혜택", re.IGNORECASE)
_NONEXISTENT_BENEFIT_RE = re.compile(r"T\s*블랙|블랙\s*멤버십|VIP|브이아이피|블랙\s*카드|50\s*%", re.IGNORECASE)
_HUMAN_RE = re.compile(r"상담원|사람\s*상담|고객센터|전화번호|연결", re.IGNORECASE)
_PERSONAL_CONTACT_RE = re.compile(r"개인\s*(?:핸드폰|전화|연락처)|담당자\s*연락처|관리자\s*번호", re.IGNORECASE)


def decide_support_response(
    *,
    intent: str,
    user_text: str = "",
    known_slots: dict[str, Any] | None = None,
) -> ResponseDecision:
    """Return Support response contracts for policy-sensitive cases."""
    text = user_text or ""
    slots = known_slots or {}

    if intent == "coupon_issue" or (_COUPON_RE.search(text) and _EXTREME_COUPON_RE.search(text)):
        return _decision(
            response_shape_key="coupon_issue_not_supported",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("promise_coupon_issue", "invent_discount", "show_all_coupons_without_context"),
            assistant_guidance="임의 쿠폰 발급은 불가하다고 안내하고, 받을 수 있는 쿠폰은 쿠폰함에서 확인 가능하다고 안내한다.",
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

    if intent == "human_escalation" or _HUMAN_RE.search(text):
        return _decision(
            response_shape_key="human_escalation",
            response_shape=ResponseShape.ACTION_CONFIRM,
            template=TemplateName.QNA_COMPLETE,
            forbidden_behaviors=("overpromise_live_agent", "hide_official_contact"),
            assistant_guidance="챗봇 처리 한계를 인정하고 1:1 문의 또는 공식 고객센터 번호 안내로 연결한다.",
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
