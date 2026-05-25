from services.tstation.policies.schedule_tool_gate import deterministic_schedule_gate_decision


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
