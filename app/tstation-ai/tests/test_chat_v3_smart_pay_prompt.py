"""V3 lost V2's Flow 1.5 smart-pay rules on migration, so the model echoed the raw
per-tire basis amount ("타이어 1개당 166,500원") instead of the 4-tire basis. These
guard the V3 replacement: `SMART_PAY_GUIDANCE`, injected on TRANSACTION turns.

Read as text (not imported): importing chat_v3 pulls in config.env, which needs a
populated environment.
"""

from pathlib import Path

_V3 = Path(__file__).resolve().parents[1] / "services/tstation/chat_v3"
PERSONA = _V3 / "prompts/persona.py"
SERVICE = _V3 / "service.py"


def _guidance() -> str:
    source = PERSONA.read_text(encoding="utf-8")
    return source.split("SMART_PAY_GUIDANCE = (", 1)[1].split("\n)\n", 1)[0]


def test_smart_pay_basis_is_always_four_tires() -> None:
    guidance = _guidance()
    assert "smart_pay_total_4ea = smrt_pay_prc * 4" in guidance
    assert "round(smart_pay_total_4ea / 12)" in guidance
    assert "round(smart_pay_total_4ea / 24)" in guidance


def test_smart_pay_never_divides_the_per_tire_basis() -> None:
    guidance = _guidance()
    assert "round(smrt_pay_prc / 12)" not in guidance
    assert "round(smrt_pay_prc / 24)" not in guidance


def test_per_tire_basis_is_not_exposed_under_any_label() -> None:
    """The real bug: the model computed 4x correctly but still printed smrt_pay_prc
    and called it 기준금액. Banning only the label leaves '1개당 …원' as an escape."""
    guidance = _guidance()
    assert "어떤 라벨로도 사용자에게 노출하지 마세요" in guidance
    assert "숫자 자체를 적지 마세요" in guidance
    assert "언제나 타이어 4개 기준" in guidance


def test_ordinary_per_tire_prices_stay_visible() -> None:
    """sale_prc / extra_fvr_sale_prc are also per-tire but are normal catalogue prices."""
    guidance = _guidance()
    assert "노출이 금지된 것은 smrt_pay_prc 뿐입니다" in guidance


def test_quantity_slots_never_drive_the_smart_pay_calculation() -> None:
    guidance = _guidance()
    assert "ord_qty" in guidance
    assert "payment_amount" in guidance
    assert "cheapest_final_prc" not in guidance


def test_only_twelve_and_twenty_four_month_plans() -> None:
    assert "36/48/60개월은 언급하지 마세요" in _guidance()


def test_unsupported_product_stops_before_calculating() -> None:
    assert "해당 상품은 스마트페이 할부서비스를 지원하지 않는 상품입니다." in _guidance()


def test_plain_price_query_does_not_volunteer_smart_pay() -> None:
    assert "명시하지 않은 단순 가격 문의" in _guidance()


def test_output_format_forces_the_four_tire_basis_line() -> None:
    """Post-deploy the model printed only the monthly figures and dropped the basis
    line, leaving the user unable to check where 52,400원/month came from."""
    guidance = _guidance()
    assert "스마트페이 기준금액(4개): {smart_pay_total_4ea}원" in guidance
    assert "12개월 할부: 월 {monthly_12}원" in guidance
    assert "24개월 할부: 월 {monthly_24}원" in guidance
    assert "기준금액 줄을 절대 생략하지 마세요" in guidance
    assert "상품마다 세 줄을 반복하세요" in guidance


def test_prompt_never_contains_a_real_per_tire_basis_amount() -> None:
    """A worked example quoting smrt_pay_prc would hand the model the exact number it
    is forbidden to print. Observed values: 157,200 (V12 에보2), 161,700 (S2 AS)."""
    guidance = _guidance()
    for leaked in ("157,200", "161,700"):
        assert leaked not in guidance


def test_guidance_is_injected_on_transaction_turns() -> None:
    source = SERVICE.read_text(encoding="utf-8")
    transaction_block = source.split('if "TRANSACTION" in domains:', 1)[1].split('if "DISCOVERY"', 1)[0]
    assert "extra_context.append(SMART_PAY_GUIDANCE)" in transaction_block
