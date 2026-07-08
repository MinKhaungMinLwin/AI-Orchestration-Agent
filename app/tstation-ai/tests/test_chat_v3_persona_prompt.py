import runpy
from pathlib import Path


SYSTEM_PROMPT = runpy.run_path(Path("services/tstation/chat_v3/prompts/persona.py"))["SYSTEM_PROMPT"]


def test_system_prompt_limits_store_recommendations_to_tool_verifiable_conditions():
    assert "도구가 확인할 수 있는 조건" in SYSTEM_PROMPT
    assert "도구 데이터로 확인할 수 없는 매장 속성이나 선호 조건" in SYSTEM_PROMPT
    assert "가능한 것처럼 찾아주겠다고 말하지 마세요" in SYSTEM_PROMPT
    assert "평점순·리뷰 많은 순·후기 좋은 순" in SYSTEM_PROMPT
    assert "방문 예정 매장에 직접 문의" in SYSTEM_PROMPT
