from types import SimpleNamespace

from services.tstation.policies.leading_response_policy import (
    build_complaint_scope_guard_event,
    build_privacy_contact_request_event,
    complaint_scope_for_turn,
    infer_complaint_scope,
    is_private_contact_request,
    is_tstation_legal_action_request,
)


def test_privacy_contact_request_blocks_personal_phone_number() -> None:
    event = build_privacy_contact_request_event("서초점 사장님 휴대폰 번호 알려줘")

    assert event is not None
    assert event["source_domain"] == "support"
    assert event["assistant_response_source"] == "code_privacy_contact_request_guard"
    assert event["data"]["metadata"]["policy_intent"] == "privacy_contact_request"
    assert event["data"]["metadata"]["storeOfficialContactAllowed"] is True
    assert event["data"]["quickReplies"][-1]["label"] == "매장 공식 연락처"


def test_store_official_contact_request_is_allowed() -> None:
    text = "서초점 매장 공식 전화번호 알려줘"

    assert is_private_contact_request(text) is False
    assert build_privacy_contact_request_event(text) is None


def test_out_of_scope_complaint_uses_leading_guard() -> None:
    scope = infer_complaint_scope("한국타이어 주식 떨어져서 짜증나")
    event = build_complaint_scope_guard_event(scope)

    assert scope == "out_of_scope_complaint"
    assert event is not None
    assert event["source_domain"] == "leading"
    assert event["assistant_response_source"] == "code_complaint_scope_guard"
    assert event["data"]["predictedDomains"] == ["DISCOVERY", "TRANSACTION"]


def test_unclear_complaint_asks_for_tstation_context() -> None:
    scope = complaint_scope_for_turn("되는 일이 없어 짜증나", None)
    event = build_complaint_scope_guard_event(scope)

    assert scope == "unclear_complaint"
    assert event is None


def test_router_complaint_scope_overrides_inferred_scope() -> None:
    routing_result = SimpleNamespace(complaint_scope="out_of_scope_complaint")

    assert complaint_scope_for_turn("타이어 주문했는데 계속 오류나", routing_result) == "out_of_scope_complaint"


def test_tstation_legal_action_request_is_owned_by_leading_policy() -> None:
    assert is_tstation_legal_action_request("장착 매장 응대 때문에 법적 조치하고 싶어") is True
    assert is_tstation_legal_action_request("전세 계약 때문에 법적 조치하고 싶어") is False


def test_tstation_complaint_does_not_build_leading_guard() -> None:
    scope = infer_complaint_scope("타이어 주문했는데 계속 오류나고 짜증나")

    assert scope == "tstation_service_complaint"
    assert build_complaint_scope_guard_event(scope) is None
