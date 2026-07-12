import runpy
from pathlib import Path


_APP_ROOT = Path(__file__).resolve().parents[1]
_PERSONA = runpy.run_path(_APP_ROOT / "services/tstation/chat_v3/prompts/persona.py")
SYSTEM_PROMPT = _PERSONA["SYSTEM_PROMPT"]
TRANSACTION_WRITE_GUIDANCE = _PERSONA["TRANSACTION_WRITE_GUIDANCE"]
STORE_SEARCH_FLOW_GUIDANCE = _PERSONA["STORE_SEARCH_FLOW_GUIDANCE"]
VEHICLE_LOOKUP_GUIDANCE = _PERSONA["VEHICLE_LOOKUP_GUIDANCE"]
ORDER_HISTORY_GUIDANCE = _PERSONA["ORDER_HISTORY_GUIDANCE"]
RESERVATION_HISTORY_GUIDANCE = _PERSONA["RESERVATION_HISTORY_GUIDANCE"]


def test_system_prompt_limits_store_recommendations_to_tool_verifiable_conditions():
    assert "도구가 확인할 수 있는 조건" in SYSTEM_PROMPT
    assert "도구 데이터로 확인할 수 없는 매장 속성이나 선호 조건" in SYSTEM_PROMPT
    assert "가능한 것처럼 찾아주겠다고 말하지 마세요" in SYSTEM_PROMPT
    assert "평점순·리뷰 많은 순·후기 좋은 순" in SYSTEM_PROMPT
    assert "방문 예정 매장에 직접 문의" in SYSTEM_PROMPT
    assert "수입차 특화점 검색 의도" in SYSTEM_PROMPT
    assert "실제 BMW 5시리즈 정비 경험이 많다고 단정하지 말고" in SYSTEM_PROMPT


def test_system_prompt_locks_user_facing_price_labels():
    assert "'기본가', '혜택가', '보유쿠폰 적용 혜택가'" in SYSTEM_PROMPT
    assert "cheapest_final_prc가 있으면 이를 최우선으로 사용" in SYSTEM_PROMPT
    assert "cheapest_final_prc가 없고 extra_fvr_sale_prc가 있으면" in SYSTEM_PROMPT
    assert "extra_fvr_sale_prc를 '보유쿠폰 적용 혜택가'라고 설명하지 말고" in SYSTEM_PROMPT
    assert "'안내가', '예시 혜택가', '보유 쿠폰 적용 시 예시 혜택가'" in SYSTEM_PROMPT
    assert "임의 라벨은 사용하지 마세요" in SYSTEM_PROMPT


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


def test_store_flow_prompt_forbids_external_stock_quantity_disclosure():
    assert "정확한 재고 수량" in STORE_SEARCH_FLOW_GUIDANCE
    assert "절대 외부에 말하지 마세요" in STORE_SEARCH_FLOW_GUIDANCE
    assert "요청 수량 기준 장착 가능 여부" in STORE_SEARCH_FLOW_GUIDANCE


def test_store_flow_prompt_uses_unified_install_availability_tool():
    assert "get_store_install_availability_tool" in STORE_SEARCH_FLOW_GUIDANCE
    assert "물류 재고, 매장 재고, T바로배송 가능 여부" in STORE_SEARCH_FLOW_GUIDANCE
    assert "가장 빠른 장착 가능 일정" in STORE_SEARCH_FLOW_GUIDANCE
    assert "일반 매장 방문 스케줄" in STORE_SEARCH_FLOW_GUIDANCE
    assert "get_logistics_inventory_tool" not in STORE_SEARCH_FLOW_GUIDANCE
    assert "get_store_inventory_tool" not in STORE_SEARCH_FLOW_GUIDANCE
    assert "get_store_schedule_tool" not in STORE_SEARCH_FLOW_GUIDANCE


def test_store_flow_prompt_maps_imported_vehicle_experience_to_imported_specialty_search():
    assert "BMW 5시리즈" in STORE_SEARCH_FLOW_GUIDANCE
    assert "수입차 특화점 검색 의도" in STORE_SEARCH_FLOW_GUIDANCE
    assert "차종별 정비 경험 수" in STORE_SEARCH_FLOW_GUIDANCE
    assert "수입차 특화점 기준으로 확인" in STORE_SEARCH_FLOW_GUIDANCE


def test_confirmed_order_recheck_uses_unified_install_availability_tool():
    assert "get_store_install_availability_tool" in TRANSACTION_WRITE_GUIDANCE
    assert "get_logistics_inventory_tool" not in TRANSACTION_WRITE_GUIDANCE


def test_vehicle_lookup_guidance_calls_tool_without_waiting_for_a_request_verb():
    # A bare "차량번호 + 소유주명" message (no request verb) must still trigger
    # get_user_vehicles_tool once DISCOVERY is bound — the model shouldn't just
    # acknowledge the info and wait to be asked.
    assert "get_user_vehicles_tool" in VEHICLE_LOOKUP_GUIDANCE
    assert "car_no" in VEHICLE_LOOKUP_GUIDANCE and "owner_nm" in VEHICLE_LOOKUP_GUIDANCE
    assert "요청 문구가 없어도" in VEHICLE_LOOKUP_GUIDANCE


def test_order_history_guidance_calls_tool_instead_of_refusing_or_redirecting():
    # Issue: bot told a customer order history "isn't connected in this chat" and
    # pointed them to MyPage instead of calling the bound get_orders_of_user_tool.
    assert "get_orders_of_user_tool" in ORDER_HISTORY_GUIDANCE
    assert "조회 기능이 없다고 답하거나 마이페이지로만 안내하지 마세요" in ORDER_HISTORY_GUIDANCE
    assert "get_order_status_tool" in ORDER_HISTORY_GUIDANCE
    assert "주문번호를 먼저 알려 달라고 되묻지 마세요" in ORDER_HISTORY_GUIDANCE


def test_reservation_history_guidance_calls_tool_instead_of_refusing_or_redirecting():
    assert "get_my_reservations_tool" in RESERVATION_HISTORY_GUIDANCE
    assert "조회 기능이 없다고 답하거나 마이페이지로만 안내하지 마세요" in RESERVATION_HISTORY_GUIDANCE
    assert "오늘 오후에 예약한 거 있지?" in RESERVATION_HISTORY_GUIDANCE
    assert "get_store_install_availability_tool" in RESERVATION_HISTORY_GUIDANCE
