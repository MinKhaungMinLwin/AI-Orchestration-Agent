from pathlib import Path


AGENT_PROMPT = Path("app/tstation-ai/services/tstation/agents/c_transaction_agent/agent.py")
TOOLS = Path("app/tstation-ai/services/tstation/agents/c_transaction_agent/tools.py")


def test_smart_pay_prompt_uses_smrt_pay_prc_not_sale_price_or_wage() -> None:
    prompt = AGENT_PROMPT.read_text(encoding="utf-8")

    assert "smart_pay_total_4ea = smrt_pay_prc * 4" in prompt
    assert "round(smart_pay_total_4ea / 12)" in prompt
    assert "round(smart_pay_total_4ea / 24)" in prompt
    assert "스마트페이 기준금액(4개)" in prompt
    assert "round(smrt_pay_prc / 12)" not in prompt
    assert "round(smrt_pay_prc / 24)" not in prompt
    assert "PR_ITEM_PRC_INFO.SMRT_PAY_PRC" in prompt
    assert "Unit price = `extra_fvr_sale_prc + wage_prc`" not in prompt
    assert "total_4ea = unit_price * 4" not in prompt
    assert "4개 기준 스마트페이" not in prompt


def test_price_tool_documents_smart_pay_basis_amount() -> None:
    tools = TOOLS.read_text(encoding="utf-8")

    assert "smrt_pay_prc" in tools
    assert "PR_ITEM_PRC_INFO.SMRT_PAY_PRC" in tools
    assert "이 값에 4를 곱한 뒤 12/24로 나누고" in tools
    assert "extra_fvr_sale_prc, wage_prc" in tools
    assert "스마트페이 계산에 사용하지 마라" in tools


def test_front_rear_order_guidance_does_not_force_smart_pay() -> None:
    prompt = AGENT_PROMPT.read_text(encoding="utf-8")
    flow = prompt.split("### Flow 1.7 — Different Front/Rear Tire Order Guidance", 1)[1]
    flow = flow.split("### Flow 2 — Inventory Check", 1)[0]

    assert "Do NOT mention Smart Pay" in flow
    assert "unless the user explicitly asks about Smart Pay/payment/installments" in flow
    assert "Include Smart Pay guidance" not in flow
    assert "12/24-month interest-free installments" not in flow


def test_smart_pay_trigger_requires_explicit_smart_pay_wording() -> None:
    prompt = AGENT_PROMPT.read_text(encoding="utf-8")
    flow = prompt.split("### Flow 1.5 — Smart Pay Installment Calculation", 1)[1]
    flow = flow.split("### Flow 1.6 — Card Installment Lookup", 1)[0]
    profile = prompt.split("## Smart Pay 12/24개월 무이자 할부", 1)[1]
    profile = profile.split("## Output Policy", 1)[0]

    assert "with explicit Smart Pay wording" in flow
    assert "Generic payment wording without explicit Smart Pay" in flow
    assert "Generic payment wording without explicit Smart Pay" in profile
    assert "is NOT Smart Pay" in profile


def test_card_installment_flow_owns_generic_installment_wording() -> None:
    prompt = AGENT_PROMPT.read_text(encoding="utf-8")
    flow = prompt.split("### Flow 1.6 — Card Installment Lookup", 1)[1]
    flow = flow.split("### Flow 1.7 — Different Front/Rear Tire Order Guidance", 1)[0]

    assert '"무이자", "할부", "월 납부", "월 결제", "월 얼마"' in flow
    assert '"스마트페이/smart pay/smartpay" 가 없으면 Flow 1.5 로 보내지 말고 Flow 1.6 으로 처리' in flow


def test_tire_installation_with_maintenance_request_has_dedicated_guidance() -> None:
    prompt = AGENT_PROMPT.read_text(encoding="utf-8")
    flow = prompt.split("### 타이어 교체 + 경정비 동시 요청 안내", 1)[1]
    flow = flow.split("### 절대 위반 금지", 1)[0]

    assert "여주점에서 타이어 교체하면서 엔진오일, 실내필터 같이 교체하고 싶어" in flow
    assert "매장 일정/휴무일/예약 오픈 시점을 먼저 설명하지 마라" in flow
    assert "svc_codes` 에 `121` 또는 `122`" in flow
    assert "온라인으로 타이어를 주문할 때 엔진오일/실내필터 같은 경정비 상품을 함께 담아 주문" in flow
    assert "방문예약 또는 매장 방문 전 전화로 요청 가능 여부를 확인" in flow
    assert "사용자가 묻지 않은 예약 오픈 일정 안내로 끝내지 마라" in flow
