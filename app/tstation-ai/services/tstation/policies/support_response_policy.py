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

    if intent == "personal_contact" or _PERSONAL_CONTACT_RE.search(text):
        return _decision(
            response_shape_key="personal_contact_denied",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("share_personal_contact", "invent_staff_contact"),
            assistant_guidance="개인 연락처는 제공할 수 없으며 공식 고객센터 또는 1:1 문의 경로만 안내한다.",
        )

    if intent == "human_escalation" or _HUMAN_RE.search(text):
        return _decision(
            response_shape_key="human_escalation",
            response_shape=ResponseShape.ACTION_CONFIRM,
            template=TemplateName.QNA_COMPLETE,
            forbidden_behaviors=("overpromise_live_agent", "hide_official_contact"),
            assistant_guidance="챗봇 처리 한계를 인정하고 1:1 문의 또는 공식 고객센터 번호 안내로 연결한다.",
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
