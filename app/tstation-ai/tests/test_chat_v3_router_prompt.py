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


def test_router_routes_bare_info_to_the_domain_that_can_use_it():
    # A message with no request verb but enough info to call a tool's required
    # args (e.g. car_no + owner_nm) must not be classified as LEADING — the
    # info itself is the intent.
    assert "요청 문구가 없어도" in ROUTER_PROMPT
    assert "LEADING(잡담)으로 분류해 정보를 흘려보내지" in ROUTER_PROMPT
    assert "09조8765 홍길동" in ROUTER_PROMPT


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


def test_router_prompt_routes_external_prediction_or_advice_as_out_of_scope():
    guard_section = ROUTER_PROMPT.split("## 2. domain", maxsplit=1)[0]

    assert "out_of_scope" in guard_section
    assert "외부 분야의 판단·예측·추천·결정" in guard_section
    assert "불확실하거나 무작위인 결과에 대한 예측" in guard_section
    assert "타이어 말고" in guard_section


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
    assert 'intent "staggered_install_availability"' in ROUTER_PROMPT
    assert 'slots_patch.goal_type="store_with_stock"' in ROUTER_PROMPT
    assert 'slots_patch.pending_intent="stock"' in ROUTER_PROMPT
