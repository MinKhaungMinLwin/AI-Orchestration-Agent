from services.tstation.policies.response_decision import ResponseShape, TemplateName
from services.tstation.policies.support_response_policy import decide_support_response


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
