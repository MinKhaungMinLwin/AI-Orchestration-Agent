"""Deterministic response policy for Support/FAQ/escalation flows."""

from __future__ import annotations

import re
from typing import Any

from services.tstation.policies.response_decision import ResponseDecision, ResponseShape, TemplateName


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
_CARD_CANCEL_TIMING_POLICY_RE = re.compile(
    r"(?:카드|결제|환불|승인\s*취소|승인취소|취소\s*완료).{0,24}(?:언제|며칠|얼마나|반영|걸려|소요)|"
    r"(?:언제|며칠|얼마나|반영|걸려|소요).{0,24}(?:카드|결제|환불|승인\s*취소|승인취소)|"
    r"카드사.{0,24}(?:환불|승인\s*취소|승인취소|취소|반영|언제|며칠|얼마나|걸려|소요)|"
    r"(?:환불|승인\s*취소|승인취소|취소|반영|언제|며칠|얼마나|걸려|소요).{0,24}카드사|"
    r"승인\s*취소\s*(?:언제|반영|걸려|소요)",
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

    if intent == "personal_contact" or _PERSONAL_CONTACT_RE.search(text):
        return _decision(
            response_shape_key="personal_contact_denied",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("share_personal_contact", "invent_staff_contact"),
            assistant_guidance="개인 연락처는 제공할 수 없으며 공식 고객센터 또는 1:1 문의 경로만 안내한다.",
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
                "보상 조건, 장착비/추가 비용 여부를 검색 근거 범위 안에서 설명한다. 보상 확정이나 자동 접수로 시작하지 않는다."
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
                "타이어 상태를 사진으로 봐달라는 문의는 FAQ hybrid 검색을 먼저 수행하되, 챗봇이 사진 판독이나 안전 여부를 확정할 수 "
                "없다고 분명히 말한다. 매장 점검, 마모도 측정, 필요 시 1:1 문의 첨부 경로를 보조로 안내한다."
            ),
        )

    if intent == "signup_first_purchase_benefit_policy" or _SIGNUP_BENEFIT_RE.search(text):
        return _decision(
            response_shape_key="signup_first_purchase_benefit_policy",
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(
                "generic_marketing_answer_without_faq",
                "promise_signup_coupon_issued",
                "start_owned_coupon_lookup",
                "call_coupon_issue_tool",
            ),
            assistant_guidance=(
                "회원가입/신규회원/첫구매 혜택 문의는 FAQ hybrid 검색을 먼저 수행하고, 검색 근거 범위 안에서 "
                "신규 회원 혜택/서비스와 첫 구매 쿠폰 가능 여부를 요약한다. 계정별 발급 상태를 확인하지 않은 채 "
                "쿠폰이 자동 발급된다고 단정하지 않는다. 보유 쿠폰 조회나 쿠폰 직접 발급으로 시작하지 말고, "
                "쿠폰함/이벤트 페이지 CTA는 보조로 제공한다."
            ),
        )

    if intent == "signup_coupon_guidance" or (
        _COUPON_RE.search(text) and _SIGNUP_COUPON_GUIDANCE_RE.search(text)
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
            ),
            assistant_guidance=(
                "회원가입 전용/신규회원/웰컴 쿠폰 문의는 제휴회원 쿠폰 안내로 보내지 않는다. "
                "이벤트/프로모션 운영 시점에 따라 달라질 수 있음을 안내하고, 현재 진행 중인 혜택 확인 경로를 우선 제공한다. "
                "이미 가입한 회원이라면 쿠폰함에서 발급된 쿠폰이 있는지 확인할 수 있다고만 안내하고, "
                "가입 쿠폰이 반드시 있거나 이미 발급되었다고 단정하지 않는다."
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

    if intent == "general_card_cancel_timing_policy" or _CARD_CANCEL_TIMING_POLICY_RE.search(text):
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
