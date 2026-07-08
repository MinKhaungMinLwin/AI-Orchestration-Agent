import runpy
from pathlib import Path


_PERSONA = runpy.run_path(Path("services/tstation/chat_v3/prompts/persona.py"))
SYSTEM_PROMPT = _PERSONA["SYSTEM_PROMPT"]
TRANSACTION_WRITE_GUIDANCE = _PERSONA["TRANSACTION_WRITE_GUIDANCE"]
STORE_SEARCH_FLOW_GUIDANCE = _PERSONA["STORE_SEARCH_FLOW_GUIDANCE"]
VEHICLE_LOOKUP_GUIDANCE = _PERSONA["VEHICLE_LOOKUP_GUIDANCE"]


def test_system_prompt_limits_store_recommendations_to_tool_verifiable_conditions():
    assert "도구가 확인할 수 있는 조건" in SYSTEM_PROMPT
    assert "도구 데이터로 확인할 수 없는 매장 속성이나 선호 조건" in SYSTEM_PROMPT
    assert "가능한 것처럼 찾아주겠다고 말하지 마세요" in SYSTEM_PROMPT
    assert "평점순·리뷰 많은 순·후기 좋은 순" in SYSTEM_PROMPT
    assert "방문 예정 매장에 직접 문의" in SYSTEM_PROMPT


def test_transaction_prompt_resolves_goods_no_without_asking_customer_for_internal_id():
    assert "상품번호나 상품 링크를 알려 달라고 하지 마세요" in TRANSACTION_WRITE_GUIDANCE
    assert "search_product_tool" in TRANSACTION_WRITE_GUIDANCE
    assert "goods_no는 내부 식별자" in TRANSACTION_WRITE_GUIDANCE


def test_store_flow_resolves_shown_branch_selection_from_memory():
    # Issue 6: naming a branch already shown ("한남점" ↔ "티스테이션 한남점") must resolve
    # against PREVIOUS TOOL RESULTS, not trigger a failing store_nm branch-name search.
    assert "PREVIOUS TOOL RESULTS" in STORE_SEARCH_FLOW_GUIDANCE
    assert "한남점" in STORE_SEARCH_FLOW_GUIDANCE
    assert "새로 매장을 검색하지 말고" in STORE_SEARCH_FLOW_GUIDANCE
    assert "shop_id" in STORE_SEARCH_FLOW_GUIDANCE
    assert "지점명" in STORE_SEARCH_FLOW_GUIDANCE and "store_nm" in STORE_SEARCH_FLOW_GUIDANCE


def test_vehicle_lookup_guidance_calls_tool_without_waiting_for_a_request_verb():
    # A bare "차량번호 + 소유주명" message (no request verb) must still trigger
    # get_user_vehicles_tool once DISCOVERY is bound — the model shouldn't just
    # acknowledge the info and wait to be asked.
    assert "get_user_vehicles_tool" in VEHICLE_LOOKUP_GUIDANCE
    assert "car_no" in VEHICLE_LOOKUP_GUIDANCE and "owner_nm" in VEHICLE_LOOKUP_GUIDANCE
    assert "요청 문구가 없어도" in VEHICLE_LOOKUP_GUIDANCE
