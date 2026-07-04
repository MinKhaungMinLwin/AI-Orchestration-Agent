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

def test_chat_support_coupon_history_legacy_helpers_delegate_to_owner_policy() -> None:
    chat_source = _read_repo_file("app/tstation-ai/services/tstation/chat.py")
    helper_region = chat_source[
        chat_source.index("def _build_maintenance_dday_event") : chat_source.index(
            "def _compact_policy_source_summary"
        )
    ]

    assert "from services.tstation.policies.support_response_policy import" in chat_source
    assert "build_maintenance_dday_event" in chat_source
    assert "build_maintenance_history_event" in chat_source
    assert "build_maintenance_history_access_policy_event" in chat_source
    assert "is_maintenance_history_access_policy_query as _is_maintenance_history_access_policy_query" in chat_source
    assert "is_maintenance_history_lookup_query as _is_maintenance_history_lookup_query" in chat_source
    assert "requested_maintenance_focus" in chat_source
    assert "build_partner_member_coupon_policy_event" in chat_source
    assert "build_signup_member_coupon_guidance_event" in chat_source
    assert "build_signup_coupon_guidance_event" in chat_source
    assert "build_signup_first_purchase_benefit_event" in chat_source
    assert "return requested_maintenance_focus(user_query)" in chat_source
    assert "return build_maintenance_dday_event(tool_result, selected_vehicle, user_query)" in chat_source
    assert "return build_maintenance_history_event(tool_result, user_query)" in chat_source
    assert "return build_maintenance_history_access_policy_event(user_query)" in chat_source
    assert "return build_partner_member_coupon_policy_event(user_query)" in chat_source
    assert "return build_signup_member_coupon_guidance_event(user_query, response_shape_key=response_shape_key)" in chat_source
    assert "return build_signup_coupon_guidance_event(user_query)" in chat_source
    assert "return build_signup_first_purchase_benefit_event(user_query)" in chat_source
    assert "def _format_maintenance_dday_item" not in chat_source
    assert "_MAINTENANCE_HISTORY_LOOKUP_RE" not in chat_source
    assert "_MAINTENANCE_HISTORY_ACCESS_POLICY_RE" not in chat_source
    assert "code_vehicle_auto_select" not in helper_region
    assert "code_maintenance_history_lookup" not in helper_region
    assert "code_maintenance_history_access_policy" not in helper_region
    assert "code_partner_member_coupon_policy" not in helper_region
    assert "signupMemberCouponGuidance" not in helper_region

def test_chat_order_document_legacy_helper_delegates_to_owner_policy() -> None:
    chat_source = _read_repo_file("app/tstation-ai/services/tstation/chat.py")
    helper_region = chat_source[
        chat_source.index("def _build_order_document_guidance_event") : chat_source.index(
            "_QUANTITYLESS_CART_ORDER_CTA_RE"
        )
    ]

    assert "from services.tstation.policies.support_response_policy import" in chat_source
    assert "build_order_document_guidance_event" in chat_source
    assert "return build_order_document_guidance_event(user_query)" in chat_source
    assert "code_order_document_guidance" not in helper_region
    assert "orderDocumentGuidance" not in helper_region
    assert "ORDER_HISTORY_DETAIL" not in helper_region


def test_chat_leading_guard_legacy_helpers_delegate_to_owner_policy() -> None:
    chat_source = _read_repo_file("app/tstation-ai/services/tstation/chat.py")
    helper_region = chat_source[
        chat_source.index("def _is_private_contact_request") : chat_source.index("_FALLBACK_DISPATCH")
    ]

    assert "from services.tstation.policies.leading_response_policy import" in chat_source
    assert "build_privacy_contact_request_event" in chat_source
    assert "build_complaint_scope_guard_event" in chat_source
    assert "complaint_scope_for_turn" in chat_source
    assert "infer_complaint_scope" in chat_source
    assert "is_private_contact_request" in chat_source
    assert "is_tstation_legal_action_request" in chat_source
    assert "return is_private_contact_request(text)" in chat_source
    assert "return build_privacy_contact_request_event(text)" in chat_source
    assert "return infer_complaint_scope(text)" in chat_source
    assert "return complaint_scope_for_turn(text, routing_result)" in chat_source
    assert "return build_complaint_scope_guard_event(scope)" in chat_source
    assert "if is_tstation_legal_action_request(text):" in chat_source
    assert "_PRIVATE_CONTACT_REQUEST_RE" not in chat_source
    assert "_COMPLAINT_TONE_RE" not in chat_source
    assert "_OUT_OF_SCOPE_COMPLAINT_RE" not in chat_source
    assert "code_privacy_contact_request_guard" not in helper_region
    assert "code_complaint_scope_guard" not in helper_region

def test_chat_product_coupon_price_legacy_helpers_delegate_to_price_policy() -> None:
    chat_source = _read_repo_file("app/tstation-ai/services/tstation/chat.py")
    helper_region = chat_source[
        chat_source.index("def _is_product_coupon_price_amount_query") : chat_source.index(
            "def _coupon_target_product_name_for_query"
        )
    ]

    assert "from services.tstation.policies.price_response_policy import" in chat_source
    assert "build_product_coupon_price_amount_event" in chat_source
    assert "build_product_coupon_price_no_product_event" in chat_source
    assert "is_product_coupon_price_amount_query" in chat_source
    assert "price_row_from_final_price_result" in chat_source
    assert "return is_product_coupon_price_amount_query(user_text)" in chat_source
    assert "return price_row_from_final_price_result(price_result)" in chat_source
    assert "return build_product_coupon_price_amount_event(" in chat_source
    assert "return build_product_coupon_price_no_product_event(product_name, tire_size, quantity=quantity)" in chat_source
    assert "_COUPON_PRICE_AMOUNT_QUERY_RE" not in chat_source
    assert "code_product_coupon_price_resolver" not in helper_region
    assert "code_product_coupon_price_no_product" not in helper_region

def test_chat_owned_coupon_legacy_helpers_delegate_to_coupon_policy() -> None:
    chat_source = _read_repo_file("app/tstation-ai/services/tstation/chat.py")
    helper_region = chat_source[
        chat_source.index("def _normalize_coupon_match_text") : chat_source.index(
            "def _is_specific_coupon_usage_query"
        )
    ]
    applicability_region = chat_source[
        chat_source.index("def _build_coupon_applicability_event") : chat_source.index(
            "_COUPON_WORD_RE"
        )
    ]

    assert "from services.tstation.policies.coupon_response_policy import" in chat_source
    assert "return build_owned_coupon_expiry_lookup_event(user_text, tool_result)" in chat_source
    assert "return build_owned_coupon_best_discount_event(tool_result)" in chat_source
    assert "return build_coupon_channel_policy_event(" in chat_source
    assert "return build_coupon_applicability_event(" in chat_source
    assert "return build_product_coupon_eligibility_event(" in chat_source
    assert "return merge_coupon_applicable_products_results(results)" in chat_source
    assert "return find_coupon_from_owned_coupons(user_text, tool_result)" in chat_source
    assert "return find_single_confident_coupon_from_owned_coupons(user_text, tool_result)" in chat_source
    assert "_OWNED_COUPON_EXPIRY_LOOKUP_RE" not in chat_source
    assert "_PRODUCT_MATCH_ALIAS_GROUPS" not in chat_source
    assert "code_owned_coupon_expiry_lookup" not in helper_region
    assert "code_owned_coupon_best_discount" not in helper_region
    assert "code_coupon_channel_policy" not in helper_region
    assert "code_coupon_resolver" not in applicability_region
    assert "code_product_coupon_resolver" not in applicability_region

def test_router_override_inventory_documents_remaining_phase9_deterministic_overrides() -> None:
    inventory = _read_repo_file("docs/router-override-inventory.md")

    assert "Current-turn support policy normalization" in inventory
    assert "Cancel-fee transaction boundary" in inventory
    assert "general_cancel_fee_policy" in inventory
    assert "payment_error_troubleshooting" in inventory
    assert "tire_manufacture_date_policy" in inventory
