from pathlib import Path


AGENT_PROMPT = Path("app/tstation-ai/services/tstation/agents/c_transaction_agent/agent.py")
TOOLS = Path("app/tstation-ai/services/tstation/agents/c_transaction_agent/tools.py")


def test_smart_pay_prompt_uses_smrt_pay_prc_not_sale_price_or_wage() -> None:
    prompt = AGENT_PROMPT.read_text(encoding="utf-8")

    assert "round(smrt_pay_prc / 12)" in prompt
    assert "round(smrt_pay_prc / 24)" in prompt
    assert "PR_ITEM_PRC_INFO.SMRT_PAY_PRC" in prompt
    assert "Unit price = `extra_fvr_sale_prc + wage_prc`" not in prompt
    assert "total_4ea = unit_price * 4" not in prompt
    assert "4개 기준 스마트페이" not in prompt


def test_price_tool_documents_smart_pay_basis_amount() -> None:
    tools = TOOLS.read_text(encoding="utf-8")

    assert "smrt_pay_prc" in tools
    assert "PR_ITEM_PRC_INFO.SMRT_PAY_PRC" in tools
    assert "extra_fvr_sale_prc, wage_prc" in tools
    assert "스마트페이 계산에 사용하지 마라" in tools
