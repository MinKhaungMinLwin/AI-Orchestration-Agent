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


def test_router_prompt_moves_fixed_policy_faqs_out_of_guard_routing():
    guard_section = ROUTER_PROMPT.split("## 2. domain", maxsplit=1)[0]
    static_faq_section = ROUTER_PROMPT.split("### 고정 FAQ 정책 key 라우팅", maxsplit=1)[1]

    assert "guard_id=\"none\", domain=SUPPORT" in static_faq_section
    for policy_key in (
        "vehicle_type_compatibility",
        "runflat_mixed_install_policy",
        "pickup_status",
        "pickup_info",
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


def test_router_prompt_blocks_internal_product_code_requests_as_guard():
    guard_section = ROUTER_PROMPT.split("## 2. domain", maxsplit=1)[0]

    assert "product_code_request" in guard_section
    assert "상품 코드" in guard_section
    assert "goods_no" in guard_section
    assert "상품명·규격·가격·재고·장착 가능 여부" in guard_section


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
