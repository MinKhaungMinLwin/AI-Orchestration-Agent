import runpy
from pathlib import Path


_APP_ROOT = Path(__file__).resolve().parents[1]
_ROUTER = runpy.run_path(_APP_ROOT / "services/tstation/chat_v3/prompts/router.py")
ROUTER_PROMPT = _ROUTER["ROUTER_PROMPT"]


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
