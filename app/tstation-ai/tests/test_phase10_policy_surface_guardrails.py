import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read_repo_file(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_phase9_failed_cases_are_not_hardcoded_in_chat_or_policy_code() -> None:
    production_sources = "\n".join(
        _read_repo_file(path)
        for path in (
            "app/tstation-ai/services/tstation/chat.py",
            "app/tstation-ai/services/tstation/policies/flow_controller.py",
            "app/tstation-ai/services/tstation/policies/turn_contract.py",
            "app/tstation-ai/services/tstation/policies/support_response_policy.py",
        )
    )

    assert re.search(r'["\']주문 취소하면 수수료 있어\?["\']', production_sources) is None
    assert re.search(r'["\']타이어 제조일자가 6개월 전이면 새 상품 맞아\?["\']', production_sources) is None
    assert re.search(r'["\']카카오페이 결제 누르면 화면이 하얗게 멈춰["\']', production_sources) is None


def test_flow_controller_uses_support_policy_matchers_instead_of_local_card_regex() -> None:
    flow_controller_source = _read_repo_file("app/tstation-ai/services/tstation/policies/flow_controller.py")

    assert "_CARD_INSTALLMENT_SUPPORT_CURRENT_TURN_RE" not in flow_controller_source
    assert "_is_card_installment_lookup_query" in flow_controller_source
    assert "_is_payment_error_troubleshooting_query" in flow_controller_source
    assert "_is_tire_manufacture_date_question" in flow_controller_source


def test_chat_reservation_legacy_helpers_delegate_to_owner_policy() -> None:
    chat_source = _read_repo_file("app/tstation-ai/services/tstation/chat.py")

    assert "from services.tstation.policies.reservation_history_policy import" in chat_source
    assert "build_reservation_status_lookup_event" in chat_source
    assert "build_reservation_store_info_event" in chat_source
    assert "build_reservation_store_not_found_event" in chat_source
    assert "select_reservation_store_row" in chat_source
    assert "def _reservation_rows_from_result" not in chat_source
    assert "def _reservation_row_value" not in chat_source
    assert "def _reservation_sort_key" not in chat_source
    assert "return select_reservation_store_row(user_text, reservations_result)" in chat_source
    assert "return build_reservation_store_not_found_event(reason)" in chat_source
    assert "return build_reservation_store_info_event(reservation_row, match_reason=match_reason)" in chat_source
    assert "return build_reservation_status_lookup_event(reservations_result)" in chat_source


def test_router_override_inventory_documents_remaining_phase9_deterministic_overrides() -> None:
    inventory = _read_repo_file("docs/router-override-inventory.md")

    assert "Current-turn support policy normalization" in inventory
    assert "Cancel-fee transaction boundary" in inventory
    assert "general_cancel_fee_policy" in inventory
    assert "payment_error_troubleshooting" in inventory
    assert "tire_manufacture_date_policy" in inventory
