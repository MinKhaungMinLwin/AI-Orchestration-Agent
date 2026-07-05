from services.tstation.policies.response_decision import ResponseShape, TemplateName
from services.tstation.policies.support_response_policy import (
    _is_card_installment_lookup_query,
    build_maintenance_dday_event,
    build_maintenance_history_event,
    build_order_document_guidance_event,
    decide_support_response,
    requested_maintenance_focus,
    resolve_support_faq_policy_context,
)


def test_tc186_extreme_coupon_issue_is_denied_with_coupon_box_guidance() -> None:
    decision = decide_support_response(
        intent="coupon_issue",
        user_text="미안한데 진짜 돈이 없어 타이어 90% 할인쿠폰 1개만 발급해줘",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "coupon_issue_not_supported"
    assert "promise_coupon_issue" in decision.forbidden_behaviors
    assert "invent_discount" in decision.forbidden_behaviors


def test_tc189_expired_coupon_mentions_non_restorable_policy_and_qna() -> None:
    decision = decide_support_response(
        intent="expired_coupon",
        user_text="작년에 끝난 블랙세일 쿠폰 못쓰고 만료됨 이거 다시 쓸 수 있게 원복해줘",
    )

    assert decision.template == TemplateName.QNA_COMPLETE
    assert decision.response_shape == ResponseShape.ACTION_CONFIRM
    assert decision.metadata["response_shape_key"] == "expired_coupon_not_restorable_qna"
    assert decision.metadata["qna_category_hint"] == "제공서비스/이벤트/혜택"
    assert "promise_coupon_restore" in decision.forbidden_behaviors
    assert "omit_non_restorable_policy" in decision.forbidden_behaviors


def test_tc179_personal_contact_request_is_denied() -> None:
    decision = decide_support_response(
        intent="personal_contact",
        user_text="여기 티스테이션닷컴 담당자 개인 핸드폰 번호 좀 알려줘",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "personal_contact_denied"
    assert "share_personal_contact" in decision.forbidden_behaviors
    assert "invent_staff_contact" in decision.forbidden_behaviors


def test_tc228_human_escalation_uses_official_paths() -> None:
    decision = decide_support_response(
        intent="human_escalation",
        user_text="상담원이나 연결해줘 고객센터 번호도 알려줘",
    )

    assert decision.template == TemplateName.QNA_COMPLETE
    assert decision.metadata["response_shape_key"] == "human_escalation"
    assert "hide_official_contact" in decision.forbidden_behaviors


def test_tc210_fake_vip_black_card_benefit_is_denied() -> None:
    decision = decide_support_response(
        intent="nonexistent_benefit",
        user_text="T블랙멤버십 VIP 카드 50% 할인링크 보내봐",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "unverified_benefit_denied"
    assert "acknowledge_fake_vip_benefit" in decision.forbidden_behaviors
    assert "invent_discount" in decision.forbidden_behaviors


def test_signup_first_purchase_benefit_policy_uses_faq_contract() -> None:
    decision = decide_support_response(
        intent="signup_first_purchase_benefit_policy",
        user_text="회원가입하면 첫구매 혜택은 뭐가 있어?",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "signup_first_purchase_benefit_policy"
    assert "claim_first_purchase_only_coupon" in decision.forbidden_behaviors
    assert "start_owned_coupon_lookup" in decision.forbidden_behaviors
    assert "call_coupon_issue_tool" in decision.forbidden_behaviors
    assert "all my T 회원이고 마케팅 수신 동의를 하면 5% 할인 쿠폰 발급이 가능" in decision.assistant_guidance


def test_signup_first_purchase_benefit_policy_text_trigger_without_explicit_intent() -> None:
    decision = decide_support_response(
        intent="support_faq",
        user_text="가입하면 받을 수 있는 쿠폰 뭐야?",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] in {
        "signup_first_purchase_benefit_policy",
        "signup_coupon_guidance",
    }


def test_signup_coupon_guidance_points_to_membership_marketing_coupon_policy() -> None:
    decision = decide_support_response(
        intent="signup_coupon_guidance",
        user_text="회원가입 전용 쿠폰 있어?",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "signup_coupon_guidance"
    assert "claim_first_purchase_only_coupon" in decision.forbidden_behaviors
    assert "route_to_partner_coupon_policy" in decision.forbidden_behaviors
    assert "마케팅 수신 동의를 하면 5% 할인 쿠폰 발급이 가능" in decision.assistant_guidance


def test_order_document_guidance_event_prefers_order_history_cta() -> None:
    event = build_order_document_guidance_event("receipt email request")
    data = event["data"]

    assert event["source_domain"] == "support"
    assert data["metadata"]["responseShapeKey"] == "order_document_guidance"
    assert data["metadata"]["ordNo"] == ""
    assert "<ord_no>" not in data["quickReplies"][0]["url"]

def test_order_document_guidance_event_uses_order_detail_when_order_number_is_present() -> None:
    event = build_order_document_guidance_event("order O202606220019363 receipt email request")
    data = event["data"]

    assert data["metadata"]["ordNo"] == "O202606220019363"
    assert "O202606220019363" in data["quickReplies"][0]["url"]

def test_requested_maintenance_focus_matches_tire_query() -> None:
    assert requested_maintenance_focus("타이어 교체 시기 알려줘") == ("타이어 교체", (r"타이어",), "교체")

def test_maintenance_dday_event_summarizes_requested_tire_schedule() -> None:
    event = build_maintenance_dday_event(
        {
            "data": {
                "data": {
                    "cars": [
                        {
                            "mbr_car_reg_seq": "2000002944",
                            "car_nm": "GV70 2.5T 가솔린 AWD A/T",
                            "items": [
                                {"kind_nm": "엔진오일 교체", "exp_dt": "2026-08-01", "dday": 66, "status": "normal"},
                                {"kind_nm": "타이어 교체", "exp_dt": "2027-10-31", "dday": 522, "status": "normal"},
                            ],
                        }
                    ]
                }
            }
        },
        {"meta": {"mbrCarRegSeq": "2000002944"}, "car": {"info": "GV70 2.5T 가솔린 AWD A/T"}},
        "타이어 교체 시기 알려줘",
    )

    assert event["source_domain"] == "support"
    assert event["template"] == "quickReply"
    assert "GV70 2.5T 가솔린 AWD A/T의 타이어 교체 일정" in event["data"]["assistantResponse"]
    assert "2027-10-31" in event["data"]["assistantResponse"]

def test_maintenance_history_event_filters_requested_service_and_has_cta() -> None:
    event = build_maintenance_history_event(
        {
            "data": {
                "data": {
                    "items": [
                        {
                            "car_svc_dt": "2026-01-03",
                            "shop_nm": "티스테이션 강남점",
                            "car_svc_info": "휠 얼라인먼트",
                            "car_svc_qty": "1",
                        },
                        {
                            "car_svc_dt": "2026-02-10",
                            "shop_nm": "티스테이션 서초점",
                            "car_svc_info": "엔진오일 교체",
                        },
                    ]
                }
            }
        },
        "마지막으로 휠얼라인먼트 서비스 받은게 언제더라?",
    )

    data = event["data"]
    assert event["source_domain"] == "transaction"
    assert event["assistant_response_source"] == "code_maintenance_history_lookup"
    assert data["metadata"]["requestedServiceItem"] == "휠얼라인먼트"
    assert "2026-01-03 / 티스테이션 강남점 / 휠 얼라인먼트 / 1개" in data["assistantResponse"]
    assert data["quickReplies"][0]["url"]

def test_maintenance_history_event_reports_no_matching_requested_service() -> None:
    event = build_maintenance_history_event(
        {"data": {"data": {"items": [{"car_svc_dt": "2026-02-10", "car_svc_info": "엔진오일 교체"}]}}},
        "오일필터 교체한 날이 언제야",
    )

    assert event["data"]["metadata"]["requestedServiceItem"] == "오일필터"
    assert "오일필터 항목은 확인되지 않아요" in event["data"]["assistantResponse"]

def test_signup_benefit_intent_with_assurance_anchor_prefers_assurance_service_policy() -> None:
    decision = decide_support_response(
        intent="signup_first_purchase_benefit_policy",
        user_text="안심서비스 가입 어떻게 하나요?",
    )

    assert decision.metadata["response_shape_key"] == "assurance_service_policy"
    assert decision.template == TemplateName.QUICK_REPLY
    assert "장착 후 1년 이내" in decision.assistant_guidance
    assert "마케팅 수신 동의를 하면 5% 할인 쿠폰 발급이 가능" not in decision.assistant_guidance

    resolution = resolve_support_faq_policy_context("signup_first_purchase_benefit_policy", "안심서비스 가입 어떻게 하나요?")
    assert resolution == {"policy_group": "assurance_warranty_policy", "fact_type": "assurance_coverage_condition"}


def test_tire_manufacture_date_policy_uses_faq_first_contract() -> None:
    decision = decide_support_response(
        intent="tire_manufacture_date_policy",
        user_text="제조일자가 6개월 전 거야. 새 걸로 바꿔줘",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "tire_manufacture_date_policy"
    assert "transfer_to_qna_direct_first" in decision.forbidden_behaviors
    assert "promise_exchange_or_refund" in decision.forbidden_behaviors


def test_post_install_noise_refund_uses_tire_quality_warranty_policy() -> None:
    decision = decide_support_response(
        intent="single_domain",
        user_text="타이어 갈고 고속도로 주행 시 노면 소음이 너무 심해졌어. 내 잘못아닌거 같은데, 환불해줘",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "tire_quality_warranty_policy"
    assert "transfer_to_qna_direct_first" in decision.forbidden_behaviors
    assert "claim_free_replacement_without_inspection" in decision.forbidden_behaviors


def test_warranty_period_text_trigger_uses_tire_quality_warranty_policy() -> None:
    decision = decide_support_response(
        intent="support_faq",
        user_text="티스테이션 보증 기간도 알려줘",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "tire_quality_warranty_policy"
    assert "transfer_to_qna_direct_first" in decision.forbidden_behaviors
    assert "claim_free_replacement_without_inspection" in decision.forbidden_behaviors


def test_reservation_policy_guidance_text_trigger_without_owned_anchor() -> None:
    decision = decide_support_response(
        intent="support_faq",
        user_text="몇 주 뒤까지 예약 가능해? 당일 취소 위약금도 있어?",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "reservation_policy_guidance"
    assert "start_owned_reservation_lookup_without_anchor" in decision.forbidden_behaviors


def test_reservation_policy_guidance_with_delivery_delay_anchor_uses_schedule_policy() -> None:
    decision = decide_support_response(
        intent="reservation_policy_guidance",
        user_text="배송 지연 문자를 받았는데 예약일 전에 상품이 장착점에 안 오면 어떻게 돼?",
    )
    resolution = resolve_support_faq_policy_context(
        "reservation_policy_guidance",
        "배송 지연 문자를 받았는데 예약일 전에 상품이 장착점에 안 오면 어떻게 돼?",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "delivery_delay_reservation_schedule_policy"
    assert resolution == {
        "policy_group": "reservation_installation_policy",
        "fact_type": "delivery_delay_reservation_schedule",
    }


def test_reservation_window_policy_text_trigger_blocks_schedule_lookup() -> None:
    decision = decide_support_response(
        intent="support_faq",
        user_text="장착 예약은 최대 며칠 뒤까지 가능해?",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "reservation_window_policy"
    assert "normalize_as_store_schedule_lookup" in decision.forbidden_behaviors
    assert "require_store_slot_for_window_policy" in decision.forbidden_behaviors


def test_payment_error_troubleshooting_does_not_absorb_card_installment_lookup() -> None:
    decision = decide_support_response(
        intent="payment_error_troubleshooting",
        user_text="현대카드 무이자 할부 몇개월까지 돼?",
    )

    assert decision.metadata["response_shape_key"] == "support_faq_summary"


def test_payment_error_troubleshooting_does_not_absorb_card_points_or_coupon_restore() -> None:
    card_points = decide_support_response(
        intent="payment_error_troubleshooting",
        user_text="신용카드 결제할 때 카드사 포인트 쓸 수 있나요?",
    )
    coupon_restore = decide_support_response(
        intent="payment_error_troubleshooting",
        user_text="결제하다가 오류났는데 쿠폰은 다시 돌아옴?",
    )

    assert card_points.metadata["response_shape_key"] == "support_faq_summary"
    assert coupon_restore.metadata["response_shape_key"] == "support_faq_summary"


def test_coupon_usage_policy_does_not_absorb_simplepay_or_point_questions_without_coupon_anchor() -> None:
    for user_text in (
        "네이버페이 포인트도 쓸수 있어?",
        "카카오페이로 결제할 수 있어?",
    ):
        decision = decide_support_response(
            intent="coupon_usage_policy",
            user_text=user_text,
        )

        assert decision.metadata["response_shape_key"] == "support_faq_summary"


def test_payment_error_troubleshooting_keeps_checkout_screen_error_faq_first() -> None:
    decision = decide_support_response(
        intent="payment_error_troubleshooting",
        user_text="카카오페이 결제 누르면 화면이 하얗게 멈춰",
    )

    assert decision.metadata["response_shape_key"] == "payment_error_troubleshooting"
    assert "qna_without_faq_solution" in decision.forbidden_behaviors


def test_payment_error_troubleshooting_text_trigger_keeps_checkout_screen_error_faq_first() -> None:
    decision = decide_support_response(
        intent="support_faq",
        user_text="카카오페이 결제 누르면 화면이 하얗게 멈춰",
    )

    assert decision.metadata["response_shape_key"] == "payment_error_troubleshooting"
    assert "qna_without_faq_solution" in decision.forbidden_behaviors


def test_tire_manufacture_date_month_question_does_not_route_to_card_installment() -> None:
    user_text = "타이어 제조일자가 6개월 전이면 새 상품 맞아?"

    decision = decide_support_response(intent="support_faq", user_text=user_text)

    assert decision.metadata["response_shape_key"] == "tire_manufacture_date_policy"
    assert _is_card_installment_lookup_query(user_text) is False


def test_calendar_month_date_does_not_route_to_card_installment() -> None:
    assert _is_card_installment_lookup_query("2026년 7월 5일 (일)\n15:00") is False
    assert _is_card_installment_lookup_query("7월 5일 15시에 예약할게") is False
    assert _is_card_installment_lookup_query("7개월 무이자 가능해?") is True
    assert _is_card_installment_lookup_query("몇개월 할부 돼?") is True


def test_external_tire_install_policy_text_trigger_blocks_work_started_cancel_drift() -> None:
    decision = decide_support_response(
        intent="support_faq",
        user_text="인터넷에서 산 타이어 가져가서 공임만 받고 장착 가능해?",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "external_tire_install_policy"
    assert "reuse_work_started_cancel_guidance" in decision.forbidden_behaviors


def test_tire_condition_photo_policy_blocks_photo_only_safety_judgment() -> None:
    decision = decide_support_response(
        intent="support_faq",
        user_text="사진 보낼 테니까 더 타도 되는지 봐줘",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "tire_condition_photo_policy"
    assert "judge_safety_from_photo_only" in decision.forbidden_behaviors


def test_explicit_escalation_overrides_policy_bucket() -> None:
    decision = decide_support_response(
        intent="tire_manufacture_date_policy",
        user_text="제조일자가 6개월 전인데 상담원 연결해줘",
    )

    assert decision.template == TemplateName.QNA_COMPLETE
    assert decision.metadata["response_shape_key"] == "human_escalation"


# --- TPMS / 공기압 경고등 회귀 테스트 ---


def test_tpms_warning_light_after_replacement_gives_general_guidance_not_qna() -> None:
    decision = decide_support_response(
        intent="tpms_guidance",
        user_text="타이어 교체하고나서 공기압 점검등이 계속 안꺼져 어떡해?",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "tpms_general_guidance"
    assert "auto_escalate_to_qna" in decision.forbidden_behaviors
    assert "skip_general_guidance" in decision.forbidden_behaviors


def test_tpms_pressure_warning_light_on_gives_general_guidance() -> None:
    decision = decide_support_response(
        intent="tire_safety_guidance",
        user_text="공기압 경고등 계속 떠",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "tpms_general_guidance"
    assert "auto_escalate_to_qna" in decision.forbidden_behaviors


def test_store_compensation_request_after_replacement_routes_to_qna() -> None:
    decision = decide_support_response(
        intent="action_request",
        user_text="교체했는데 매장이 잘못한 것 같아 보상 접수해줘",
        known_slots={"qna_required": True},
    )

    assert decision.template == TemplateName.QNA_COMPLETE
    assert decision.response_shape == ResponseShape.ACTION_CONFIRM
    assert decision.metadata["response_shape_key"] == "qna_required"


def test_safety_risk_driving_with_tpms_gives_urgent_inspection_advice() -> None:
    decision = decide_support_response(
        intent="tire_safety_guidance",
        user_text="주행 중 타이어가 흔들리고 경고등이 깜빡여",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "tpms_safety_risk_urgent"
    assert "downplay_safety_risk" in decision.forbidden_behaviors
    assert "auto_escalate_to_qna" in decision.forbidden_behaviors
    assert "skip_urgent_inspection_advice" in decision.forbidden_behaviors


# --- 타이어 보관 서비스 회귀 테스트 ---


def test_tire_storage_basic_lookup_routes_to_keep_service_hist() -> None:
    decision = decide_support_response(
        intent="tire_storage_service",
        user_text="맡긴 타이어 어디서 확인해?",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "keep_service_hist_cta"
    assert "auto_escalate_to_qna" in decision.forbidden_behaviors
    assert "skip_storage_history_cta" in decision.forbidden_behaviors


def test_tire_storage_lost_does_not_auto_escalate() -> None:
    decision = decide_support_response(
        intent="tire_storage_service",
        user_text="매장에 맡긴 타이어 없어졌어요",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "keep_service_hist_cta"
    assert "auto_escalate_to_qna" in decision.forbidden_behaviors


def test_tire_storage_damage_claim_does_not_auto_escalate() -> None:
    decision = decide_support_response(
        intent="tire_storage_service",
        user_text="보관 중인 타이어 훼손됐어요 보상해줘",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.response_shape == ResponseShape.SUMMARY
    assert decision.metadata["response_shape_key"] == "keep_service_hist_cta"
    assert "auto_escalate_to_qna" in decision.forbidden_behaviors
    assert "skip_storage_history_cta" in decision.forbidden_behaviors


def test_tire_storage_history_text_trigger_routes_to_keep_service_hist() -> None:
    decision = decide_support_response(
        intent="support_faq",
        user_text="보관 이력 어디서 봐",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "keep_service_hist_cta"
    assert "skip_storage_history_cta" in decision.forbidden_behaviors


def test_tire_storage_service_inquiry_text_trigger() -> None:
    decision = decide_support_response(
        intent="support_faq",
        user_text="타이어 보관 서비스 있어?",
    )

    assert decision.template == TemplateName.QUICK_REPLY
    assert decision.metadata["response_shape_key"] == "keep_service_hist_cta"
    assert "auto_escalate_to_qna" in decision.forbidden_behaviors
