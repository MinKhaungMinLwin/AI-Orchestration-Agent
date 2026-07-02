from services.tstation.policies.schedule_tool_gate import decide_schedule_tool_gate, deterministic_schedule_gate_decision


def test_blocks_arrival_visit_status_question():
    decision = deterministic_schedule_gate_decision("매장에서 타이어 도착했다고 전화왔어. 지금 가도 돼?")

    assert decision is not None
    assert decision.allow is False
    assert decision.action == "check_order"


def test_allows_explicit_schedule_request():
    decision = deterministic_schedule_gate_decision("내일 12시 예약 가능해?")

    assert decision is not None
    assert decision.allow is True
    assert decision.action == "allow"


def test_blocks_reservation_status_confirmation():
    decision = deterministic_schedule_gate_decision("예약 잘 된거 맞지? 방문만 하면 돼?")

    assert decision is not None
    assert decision.allow is False
    assert decision.action == "check_order"


def test_allows_store_selection_after_candidate_list():
    decision = deterministic_schedule_gate_decision(
        "티스테이션 센텀점",
        tool_args={"shop_id": "F00035", "mode": "general"},
        recent_context="요청하신 조건으로 장착 가능 여부가 확인된 매장 2곳입니다. 원하시는 매장을 선택해 주세요.",
    )

    assert decision is not None
    assert decision.allow is True
    assert decision.action == "allow"


def test_allows_store_reservation_time_check_not_arrival_status():
    decision = deterministic_schedule_gate_decision("판교점 예약 가능 시간 확인")

    assert decision is not None
    assert decision.allow is True
    assert decision.action == "allow"


def test_allows_store_selection_after_which_store_question():
    decision = deterministic_schedule_gate_decision(
        "티스테이션 분당정자점",
        tool_args={"shop_id": "F00413", "mode": "general"},
        recent_context="요청하신 '정자점'으로 검색한 결과 다음 매장들이 있는데, 원하시는 매장이 있나요?",
    )

    assert decision is not None
    assert decision.allow is True
    assert decision.action == "allow"


def test_allows_less_busy_reservation_time_request():
    decision = deterministic_schedule_gate_decision(
        "토요일 오전에 정자점에 세차하는 차량들이 너무 많아서 들어갈 수가 없던데 언제 예약해야 좀 한가할까?"
    )

    assert decision is not None
    assert decision.allow is True
    assert decision.action == "allow"


def test_tool_plan_allow_makes_llm_schedule_gate_advisory():
    decision = decide_schedule_tool_gate(
        user_text="주문하기",
        tool_args={"shop_id": "F00035", "mode": "general"},
        recent_context="",
        allowed_by_tool_plan=True,
    )

    assert decision.allow is True
    assert decision.action == "allow"
    assert "ToolPlan allows" in decision.reason
