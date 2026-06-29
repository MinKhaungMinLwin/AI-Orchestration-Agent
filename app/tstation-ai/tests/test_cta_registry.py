from __future__ import annotations

from services.tstation.common.cta_urls import CTAUrls
from services.tstation.policies.cta_registry import cta_trace_metadata, normalize_quickreply_ctas
from services.tstation.policies.turn_contract import TurnContract


def test_url_cta_preserves_destination_and_gets_open_url_contract() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "support",
        "data": {
            "assistantResponse": "회원 혜택은 혜택 페이지에서 확인해 주세요.",
            "quickReplies": [
                {"label": "회원 혜택 확인", "url": CTAUrls.MEMBERSHIP_BENEFIT, "domain": "SUPPORT"},
            ],
        },
    }

    changed = normalize_quickreply_ctas(event)
    chip = event["data"]["quickReplies"][0]

    assert changed is True
    assert chip["url"] == CTAUrls.MEMBERSHIP_BENEFIT
    assert chip["cta_id"] == "member.benefit.open"
    assert chip["expected_behavior"] == "open_url"
    assert chip["metadata"]["cta_action"] == "open_membership_benefit"


def test_coupon_url_cta_preserves_coupon_list_destination() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "data": {
            "assistantResponse": "쿠폰함에서 확인해 주세요.",
            "quickReplies": [
                {"label": "쿠폰함 바로가기", "url": CTAUrls.MY_COUPON_LIST_PC, "domain": "TRANSACTION"},
            ],
        },
    }

    normalize_quickreply_ctas(event)
    chip = event["data"]["quickReplies"][0]

    assert chip["url"] == CTAUrls.MY_COUPON_LIST_PC
    assert chip["cta_id"] == "coupon.my_list.open"
    assert chip["expected_behavior"] == "open_url"


def test_conversation_cta_gets_next_turn_contract_seed() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "data": {
            "assistantResponse": "차량 또는 사이즈를 선택해 주세요.",
            "quickReplies": [{"label": "보유차량 중 선택", "domain": "DISCOVERY"}],
        },
    }

    normalize_quickreply_ctas(event, contract=TurnContract(domain="discovery", intent="product_recommendation"))
    chip = event["data"]["quickReplies"][0]

    assert chip["cta_id"] == "owned_vehicle.select"
    assert chip["cta_action"] == "select_owned_vehicle"
    assert chip["expected_behavior"] == "conversation_action"
    assert chip["expected_contract_intent"] == "vehicle_lookup"
    assert chip["metadata"]["source_intent"] == "product_recommendation"
    assert chip["metadata"]["actual_contract_intent"] == "product_recommendation"


def test_store_and_reservation_ctas_get_conversation_contracts() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "data": {
            "assistantResponse": "다른 조건으로 확인할 수 있어요.",
            "quickReplies": [
                {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
                {"label": "다른 날짜 확인", "domain": "TRANSACTION"},
            ],
        },
    }

    normalize_quickreply_ctas(event, contract=TurnContract(domain="transaction", intent="stock_store_search"))
    store_chip, date_chip = event["data"]["quickReplies"]

    assert store_chip["cta_id"] == "store.search.other"
    assert store_chip["expected_contract_intent"] == "stock_store_search"
    assert date_chip["cta_id"] == "reservation.date.change"
    assert date_chip["expected_contract_intent"] == "store_schedule"


def test_forbidden_tool_cta_is_removed_and_safe_fallback_is_inserted() -> None:
    contract = TurnContract(
        domain="support",
        intent="order_document_guidance",
        forbidden_tools=("transfer_to_qna_tool",),
    )
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "support",
        "data": {
            "assistantResponse": "주문 내역에서 먼저 확인해 주세요.",
            "quickReplies": [{"label": "1:1 문의하기", "domain": "SUPPORT"}],
        },
    }

    normalize_quickreply_ctas(event, contract=contract)

    chip = event["data"]["quickReplies"][0]
    assert chip["label"] == "문의 내용 다시 입력"
    assert chip["metadata"]["cta_validation_result"] == "fallback"
    assert event["data"]["metadata"]["cta_validation"][0]["result"] == "blocked"
    assert "tool_forbidden:transfer_to_qna_tool" == event["data"]["metadata"]["cta_validation"][0]["reason"]


def test_dynamic_size_chip_is_typed_without_fixed_label_registry() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "data": {
            "assistantResponse": "사이즈를 선택해 주세요.",
            "quickReplies": [{"label": "225/45R17", "domain": "DISCOVERY"}],
        },
    }

    normalize_quickreply_ctas(event, contract=TurnContract(domain="discovery", intent="product_recommendation"))
    chip = event["data"]["quickReplies"][0]

    assert chip["cta_id"] == "dynamic.dynamic_tire_size"
    assert chip["expected_behavior"] == "dynamic_choice"
    assert chip["metadata"]["dynamic_value"] == "225/45R17"


def test_cta_trace_metadata_summarizes_emitted_ctas() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "data": {
            "quickReplies": [
                {
                    "label": "주문 내역 확인",
                    "cta_id": "order.history.open",
                    "cta_action": "open_order_history",
                    "expected_behavior": "open_url",
                    "metadata": {
                        "cta_id": "order.history.open",
                        "cta_action": "open_order_history",
                        "expected_behavior": "open_url",
                        "expected_contract_intent": "",
                        "actual_contract_intent": "order_document_guidance",
                        "cta_validation_result": "allowed",
                        "cta_validation_reason": "cta_contract_validated",
                    },
                }
            ]
        },
    }

    metadata = cta_trace_metadata([event])

    assert metadata["cta_id"] == "order.history.open"
    assert metadata["cta_action"] == "open_order_history"
    assert metadata["expected_behavior"] == "open_url"
    assert metadata["actual_contract_intent"] == "order_document_guidance"
    assert metadata["cta_validation_result"] == "allowed"
