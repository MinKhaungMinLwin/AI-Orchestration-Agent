import runpy
from pathlib import Path


_APP_ROOT = Path(__file__).resolve().parents[1]
_ROUTER = runpy.run_path(_APP_ROOT / "services/tstation/chat_v3/prompts/router.py")
ROUTER_PROMPT = _ROUTER["ROUTER_PROMPT"]


def test_router_prompt_defines_tstation_scope_boundary():
    assert "scope boundary" in ROUTER_PROMPT
    assert "키워드가 아니라 사용자의 주된 목적" in ROUTER_PROMPT
    assert "타이어 판매·장착·차량 관리 서비스" in ROUTER_PROMPT
    assert "타이어/상품/차량/매장/가격/재고/쿠폰/혜택/주문/예약/장착/보증/안심서비스/FAQ" in ROUTER_PROMPT
    assert "최종 행동 목적" in ROUTER_PROMPT
    assert "현재 발화의 목적 기준으로 out_of_scope 여부를 다시 판단" in ROUTER_PROMPT
    assert "현재 발화가 새로운 주된 목적이나 외부 주제로 이동" in ROUTER_PROMPT


def test_router_routes_bare_info_to_the_domain_that_can_use_it():
    # A message with no request verb but enough info to call a tool's required
    # args (e.g. car_no + owner_nm) must not be classified as LEADING — the
    # info itself is the intent.
    assert "요청 문구가 없어도" in ROUTER_PROMPT
    assert "LEADING(잡담)으로 분류해 정보를 흘려보내지" in ROUTER_PROMPT
    assert "09조8765 홍길동" in ROUTER_PROMPT


def test_router_routes_competitor_characteristic_guidance_to_no_tool_discovery():
    assert "금호 마제스티9과 비슷한 한국타이어 제품 뭐 있어?" in ROUTER_PROMPT
    assert 'intents=["competitor_counterpart_guidance"]' in ROUTER_PROMPT
    assert 'guard_id="none", domain=DISCOVERY' in ROUTER_PROMPT
    assert 'tool_profile="discovery_search", needs_selection_card=false' in ROUTER_PROMPT
    assert 'brand_context.desired_brand="한국타이어"' in ROUTER_PROMPT
    assert "unsupported_brand_target을 채우거나 unsupported_brand guard를 선택하지 말고" in ROUTER_PROMPT
    assert "무도구 정보성 턴" in ROUTER_PROMPT
    assert "경쟁사 제품 자체의 검색·가격·재고가 목적이면" in ROUTER_PROMPT


def test_router_prompt_routes_card_interest_free_installments_to_support():
    assert "card_installment_lookup" in ROUTER_PROMPT
    assert "무이자 할부 카드 알려줘" in ROUTER_PROMPT
    assert "12개월 무이자 가능한 카드" in ROUTER_PROMPT
    assert "쿠폰/가격/결제오류 FAQ 로 보내지 마세요" in ROUTER_PROMPT


def test_router_prompt_does_not_absorb_neighboring_payment_intents_as_installments():
    assert "스마트페이 월 납부액" in ROUTER_PROMPT
    assert "카드 결제 실패" in ROUTER_PROMPT
    assert "카드 취소/환불 시점" in ROUTER_PROMPT
    assert "카드 할인/포인트/제휴 혜택" in ROUTER_PROMPT
    assert "쿠폰 적용/최종 혜택가" in ROUTER_PROMPT


def test_router_prompt_routes_imported_vehicle_experience_store_requests_to_transaction():
    assert "store_recommendation_by_vehicle_experience" in ROUTER_PROMPT
    assert "bmw 5시리즈 정비 경험 많은 매장으로 추천해줘" in ROUTER_PROMPT
    assert "TRANSACTION 매장 검색" in ROUTER_PROMPT
    assert "수입차 특화점 조건" in ROUTER_PROMPT
    assert "SUPPORT FAQ가 아니라" in ROUTER_PROMPT


def test_router_prompt_moves_fixed_policy_faqs_out_of_guard_routing():
    guard_section = ROUTER_PROMPT.split("## 2. domain", maxsplit=1)[0]
    static_faq_section = ROUTER_PROMPT.split("### 고정 FAQ 정책 key 라우팅", maxsplit=1)[1]

    assert "guard_id=\"none\", domain=SUPPORT" in static_faq_section
    for policy_key in (
        "vehicle_type_compatibility",
        "runflat_mixed_install_policy",
        "late_night_store_hours_policy",
        "direct_home_delivery",
        "shipping_fee_region",
        "online_store_price_policy",
        "regional_price_policy",
        "past_event_page",
        "maintenance_history_access_policy",
        "maintenance_reminding_alarm",
        "my_goods_review_lookup",
        "store_service_review_write",
        "keep_service_history_lookup",
        "tire_check_result_lookup",
    ):
        assert policy_key not in guard_section
        assert policy_key in static_faq_section


def test_router_prompt_separates_maintenance_history_lookup_from_access_policy():
    static_faq_section = ROUTER_PROMPT.split("### 고정 FAQ 정책 key 라우팅", maxsplit=1)[1]

    assert "maintenance_history_lookup" in static_faq_section
    assert "domain=TRANSACTION" in static_faq_section
    assert "maintenance_history_access_policy" in static_faq_section
    assert "어느 메뉴/페이지/매장에서 확인할 수 있는지" in static_faq_section
    assert "needs_selection_card=false" in static_faq_section
    assert "제가 지금 바로 최근 정비이력도 조회해드릴게요" in static_faq_section
    assert "정비이력은 어디서 확인해?" in static_faq_section
    assert "내 정비이력 보여줘" in static_faq_section


def test_router_prompt_separates_tire_self_check_guidance_from_measurement_result_lookup():
    static_faq_section = ROUTER_PROMPT.split("### 고정 FAQ 정책 key 라우팅", maxsplit=1)[1]

    assert "tire_check_result_lookup" in static_faq_section
    assert "이미 측정한 타이어 마모도 결과·측정 이력" in static_faq_section
    assert '"타이어 마모도 확인 방법"' in static_faq_section
    assert "이 key를 사용하지 마세요" in static_faq_section
    assert 'intents=["tire_tread_self_check_guidance"]' in static_faq_section
    assert "SUPPORT FAQ/RAG에서 답변" in static_faq_section


def test_router_prompt_routes_pickup_questions_to_faq_not_static_policy():
    pickup_section = ROUTER_PROMPT.split("### 스마트픽업 FAQ 라우팅", maxsplit=1)[1].split(
        "### 고정 FAQ 정책 key 라우팅",
        maxsplit=1,
    )[0]
    static_faq_section = ROUTER_PROMPT.split("### 고정 FAQ 정책 key 라우팅", maxsplit=1)[1]

    assert "SUPPORT FAQ/RAG" in pickup_section
    assert "pickup_status" in pickup_section
    assert "pickup_info" in pickup_section
    assert "고정 FAQ 정책 key가 아닙니다" in pickup_section
    assert "내 차 지금 작업 중이야?" in pickup_section
    assert "reservation_status_lookup" in pickup_section
    assert "pickup_status" not in static_faq_section
    assert "pickup_info" not in static_faq_section


def test_router_prompt_blocks_internal_product_code_requests_as_guard():
    guard_section = ROUTER_PROMPT.split("## 2. domain", maxsplit=1)[0]

    assert "product_code_request" in guard_section
    assert "상품 코드" in guard_section
    assert "goods_no" in guard_section
    assert "상품명·규격·가격·재고·장착 가능 여부" in guard_section


def test_router_prompt_requires_brand_role_context_for_unsupported_brand():
    assert "brand_context" in ROUTER_PROMPT
    assert "installed_brand" in ROUTER_PROMPT
    assert "desired_brand" in ROUTER_PROMPT
    assert "excluded_brand" in ROUTER_PROMPT
    assert "unsupported_brand_target" in ROUTER_PROMPT
    assert "switch_to_supported_alternative" in ROUTER_PROMPT
    assert 'Use guard_id="unsupported_brand" only when unsupported_brand_target is filled' in ROUTER_PROMPT
    assert "ignore an unsupported target carried only by conversation history" in ROUTER_PROMPT


def test_router_prompt_routes_tire_purchase_channels_in_scope_without_price_comparison():
    guard_section = ROUTER_PROMPT.split("## 2. domain", maxsplit=1)[0]

    assert "other_brand_purchase_channel" in guard_section
    assert "금호타이어는 어디서 살 수 있어?" in guard_section
    assert "넥센 타이어 구매 사이트 알려줘" in guard_section
    assert "hankook_alternative_purchase_channel" in guard_section
    assert "한국타이어는 티스테이션 말고 어디서 사?" in guard_section
    assert "한국타이어 파는 다른 온라인몰 있어?" in guard_section
    assert "가격 비교·최저가 확인을 요구하지 않으면 external_price가 아닙니다" in guard_section
    assert "타이어 구매 채널은 T-Station 고객 업무 범위입니다" in guard_section
    assert "out_of_scope로 분류하지 말고" in guard_section


def test_router_prompt_requires_current_turn_evidence_for_nonexistent_benefit():
    assert "benefit_context.unverified_benefit_target" in ROUTER_PROMPT
    assert "benefit_context.unverified_access_request" in ROUTER_PROMPT
    assert "현재 사용자 발화에서 그대로 인용한 문구" in ROUTER_PROMPT
    assert "이전 대화에만 있는 VIP/50%/링크 문구라면 이 guard를 선택하지 마세요" in ROUTER_PROMPT
    assert "일반 N% 쿠폰의 존재·위치·수령 경로 질문" in ROUTER_PROMPT


def test_router_prompt_routes_owned_coupon_exclusion_to_benefit_discovery():
    assert "benefit_context.owned_coupon_exclusion" in ROUTER_PROMPT
    assert "내 쿠폰 말고 20% 할인되는 쿠폰은 어디 있어?" in ROUTER_PROMPT
    assert "이전의 my_coupons_lookup 문맥을 이어가지 마세요" in ROUTER_PROMPT
    assert 'intents=["benefit_event_lookup"]' in ROUTER_PROMPT
    assert 'tool_profile="discovery_event_content"' in ROUTER_PROMPT


def test_router_prompt_routes_external_prediction_or_advice_as_out_of_scope():
    guard_section = ROUTER_PROMPT.split("## 2. domain", maxsplit=1)[0]

    assert "out_of_scope" in guard_section
    assert "외부 분야의 판단·예측·추천·결정" in guard_section
    assert "불확실하거나 무작위인 결과에 대한 예측" in guard_section
    assert "타이어 말고" in guard_section


def test_router_prompt_blocks_tire_themed_artifact_generation_as_out_of_scope():
    guard_section = ROUTER_PROMPT.split("## 2. domain", maxsplit=1)[0]

    assert "외부 산출물을 만들어 달라고 하면" in guard_section
    assert "최종 목적은 산출물 생성" in guard_section
    assert "타이어를 주제로 단편 소설을 써줘" in guard_section
    assert "타이어를 활용한 팩맨게임을 코드로 짜줘" in guard_section
    assert "타이어 재고 및 매출 관리를 위한 엑셀 VBA 코드 짜줘" in guard_section
    assert "타이어 재고 있어?" in guard_section


def test_router_prompt_blocks_tire_themed_general_history_as_out_of_scope():
    guard_section = ROUTER_PROMPT.split("## 2. domain", maxsplit=1)[0]

    assert "일반 지식·역사·에세이·산업/유통 흐름 설명" in guard_section
    assert "T-Station 고객 업무와 직접 연결되지 않는 해설" in guard_section
    assert "타이어 재고에 대한 역사는?" in guard_section
    assert "타이어 산업의 발전 과정을 설명해줘" in guard_section
    assert "타이어 관리·차량 안전·보증/장착/구매 방법" in guard_section


def test_router_prompt_blocks_new_external_purposes_during_scope_drift():
    guard_section = ROUTER_PROMPT.split("## 2. domain", maxsplit=1)[0]

    assert "외부 기관·서비스·전문 영역" in guard_section
    assert "조언, 실행 방법, 연락처/접수 경로, 판단·의사결정" in guard_section
    assert "글/문서 작성이면 out_of_scope" in guard_section
    assert "예시일 뿐" in guard_section
    assert "의료·건강 판단" in guard_section
    assert "병원/응급 서비스" in guard_section
    assert "교통사고 현장 조치" in guard_section
    assert "경찰/보험사 연락" in guard_section
    assert "보험 사고 접수·진술·청구 문서" in guard_section
    assert "대화가 전기차·차량·타이어에서 시작되었더라도" in guard_section
    assert "T-Station 차량 관리 FAQ로 확장하지 마세요" in guard_section


def test_router_prompt_defines_support_grounding_clarification_contract():
    assert "support_needs_clarification" in ROUTER_PROMPT
    assert "SUPPORT 답변은 공식 도구 결과 또는 고정 정책에 근거" in ROUTER_PROMPT
    assert "필수 정보가 부족하여" in ROUTER_PROMPT
    assert "사용자에게 짧게 되물어야 하는 경우에만" in ROUTER_PROMPT
    assert "외부 기관·서비스·전문 영역의 새 목적" in ROUTER_PROMPT
    assert 'guard_id="out_of_scope"' in ROUTER_PROMPT


def test_router_prompt_keeps_runflat_mixed_install_out_of_vehicle_type_policy():
    static_faq_section = ROUTER_PROMPT.split("### 고정 FAQ 정책 key 라우팅", maxsplit=1)[1]

    assert "런플랫" in static_faq_section
    assert "vehicle_type_compatibility가 아니라 runflat_mixed_install_policy" in static_faq_section
    assert "앞바퀴/뒷바퀴 2짝만 일반 타이어" in static_faq_section


def test_router_prompt_routes_late_night_store_hours_to_static_policy():
    static_faq_section = ROUTER_PROMPT.split("### 고정 FAQ 정책 key 라우팅", maxsplit=1)[1]

    assert "late_night_store_hours_policy" in static_faq_section
    assert "09:00 ~ 19:00" in static_faq_section
    assert "매장별 영업시간은 상이" in static_faq_section
    assert "예약/장착 표현이 있어도" in static_faq_section
    assert "get_stores_with_time_filter_tool 로 매장 목록을 확정하지 마세요" in static_faq_section


def test_router_prompt_requires_explicit_cart_request():
    assert "add_to_cart" in ROUTER_PROMPT
    assert "pending_intent=\"cart\"" in ROUTER_PROMPT
    # 고객 요구사항: 짧은 동의/수량 선택은 장바구니 요청이 아니며,
    # cart_confirmation 자동 실행 규칙은 존재하지 않아야 한다.
    assert "cart_confirmation" not in ROUTER_PROMPT
    assert "명시적으로 장바구니 담기를 요청한 경우" in ROUTER_PROMPT
    assert "짧은 동의 발화는 장바구니 담기 요청이" in ROUTER_PROMPT
    assert "짧은 승인/동의 발화만으로 장바구니 담기를 실행 의도로 분류하지 마세요" in ROUTER_PROMPT


def test_router_prompt_extracts_direct_staggered_tire_sizes_into_separate_slots() -> None:
    assert "slots_patch.tire_size_front" in ROUTER_PROMPT
    assert "slots_patch.tire_size_rear" in ROUTER_PROMPT
    assert "slots_patch.tire_size 를 채우지 마세요" in ROUTER_PROMPT
    assert "ask the user to choose" in ROUTER_PROMPT
    assert "before searching products, stores, stock, or installation availability" in ROUTER_PROMPT


def test_router_prompt_does_not_treat_system_time_as_a_requested_date() -> None:
    normalized_prompt = " ".join(ROUTER_PROMPT.split())
    assert '"오늘 날짜/시간: Current Time" line is system reference context' in ROUTER_PROMPT
    assert "Never copy that system date into slots_patch.requested_cal_day" in normalized_prompt
