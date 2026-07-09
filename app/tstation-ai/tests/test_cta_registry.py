from __future__ import annotations

from services.tstation.common.cta_urls import CTAUrls
from services.tstation.common.tstation_be_client import set_tstation_origin_host
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


def test_legacy_policy_url_ctas_are_registered_for_v3_normalization() -> None:
    cases = [
        ("지난 이벤트 보기", CTAUrls.PROMOTION_PAST_EVENT_LIST, "promotion.past_event.open"),
        ("픽업서비스 신청", CTAUrls.SMART_PICKUP, "smart_pickup.open"),
        ("픽업서비스 내역", CTAUrls.SMART_PICKUP_LIST, "smart_pickup.list.open"),
        ("정비이력보기", CTAUrls.STORE_SERVICE_HISTORY, "service_history.open"),
        ("매장서비스 내역", CTAUrls.STORE_SERVICE_HISTORY, "service_history.open"),
        ("상품 리뷰", CTAUrls.GOODS_REVIEW, "goods_review.open"),
        ("보관 서비스 이력", CTAUrls.KEEP_SERVICE_HIST, "keep_service_history.open"),
        ("점검/교체 알림", CTAUrls.REMINDING_ALARM, "maintenance.reminding_alarm.open"),
        ("all my T 점검", CTAUrls.MEMBERSHIP_DASHBOARD, "membership.dashboard.open"),
        ("마모도 측정 결과", CTAUrls.TIRE_CHECK_RESULT_LIST, "tire.check_result.open"),
    ]
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "support",
        "data": {
            "assistantResponse": "확인 경로를 안내드릴게요.",
            "quickReplies": [
                {"label": label, "url": url, "domain": "SUPPORT"}
                for label, url, _cta_id in cases
            ],
        },
    }

    normalize_quickreply_ctas(event)

    for chip, (_label, expected_url, expected_cta_id) in zip(event["data"]["quickReplies"], cases, strict=True):
        assert chip["url"] == expected_url
        assert chip["cta_id"] == expected_cta_id
        assert chip["expected_behavior"] == "open_url"


def test_warranty_cta_uses_verified_pc_and_mobile_paths() -> None:
    assert CTAUrls.WARRANTY_MAIN == "https://www.tstation.com/mypage/tstation/warranty/main"

    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "support",
        "data": {
            "assistantResponse": "나의 워런티에서 확인해 주세요.",
            "quickReplies": [
                {"label": "나의 워런티 확인", "url": CTAUrls.WARRANTY_MAIN, "domain": "SUPPORT"},
            ],
        },
    }

    try:
        set_tstation_origin_host("m.tstation.com")
        normalize_quickreply_ctas(event)
    finally:
        set_tstation_origin_host(None)

    assert event["data"]["quickReplies"][0]["url"] == "https://m.tstation.com/mypage/tstation/warranty"


def test_url_cta_removes_duplicate_markdown_link_from_assistant_response() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "support",
        "data": {
            "assistantResponse": (
                "픽업기사의 실시간 위치나 도착 시간은 챗봇에서 바로 확인하기 어려워요.\n"
                "신청하신 픽업/딜리버리 진행 현황은 아래 픽업서비스 내역에서 확인해 주세요.\n"
                f"[픽업서비스 내역 바로가기]({CTAUrls.SMART_PICKUP_LIST})"
            ),
            "quickReplies": [
                {"label": "픽업서비스 내역", "url": CTAUrls.SMART_PICKUP_LIST, "domain": "SUPPORT"},
            ],
        },
    }

    changed = normalize_quickreply_ctas(event)

    assert changed is True
    assert "https://www.tstation.com" not in event["data"]["assistantResponse"]
    assert "픽업서비스 내역 바로가기" not in event["data"]["assistantResponse"]
    assert event["data"]["quickReplies"][0]["url"] == CTAUrls.SMART_PICKUP_LIST


def test_url_cta_removes_duplicate_bare_url_but_keeps_unrelated_links() -> None:
    other_url = "https://www.tstation.com/promotion/event-list"
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "support",
        "data": {
            "assistantResponse": (
                f"픽업서비스 내역: {CTAUrls.SMART_PICKUP_LIST}\n"
                f"다른 안내 링크는 유지합니다: {other_url}"
            ),
            "quickReplies": [
                {"label": "픽업서비스 내역", "url": CTAUrls.SMART_PICKUP_LIST, "domain": "SUPPORT"},
            ],
        },
    }

    normalize_quickreply_ctas(event)

    assert CTAUrls.SMART_PICKUP_LIST not in event["data"]["assistantResponse"]
    assert other_url in event["data"]["assistantResponse"]


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


def test_forbidden_tool_cta_is_removed_and_quickreplies_may_be_empty() -> None:
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

    assert event["data"]["quickReplies"] == []
    assert event["data"]["metadata"]["cta_validation"][0]["result"] == "blocked"
    assert "tool_forbidden:transfer_to_qna_tool" == event["data"]["metadata"]["cta_validation"][0]["reason"]


def test_product_description_purchase_cta_is_next_turn_action_even_when_purchase_tools_forbidden() -> None:
    contract = TurnContract(
        domain="discovery",
        intent="product_description",
        sub_intent="product_name_search",
        forbidden_tools=("transaction_store_preview_tool", "quick_order_tool"),
        known_slots={"goods_no": "G000000320152", "tire_size": "245/45R19", "product_name": "다이나프로 HP3"},
    )
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "data": {
            "assistantResponse": "상품 정보를 확인했어요.",
            "quickReplies": [{"label": "구매하기", "domain": "TRANSACTION"}],
            "metadata": {
                "goods_no": "G000000320152",
                "tire_size": "245/45R19",
                "product_name": "다이나프로 HP3",
            },
        },
    }

    normalize_quickreply_ctas(event, contract=contract)

    chip = event["data"]["quickReplies"][0]
    assert chip["label"] == "구매하기"
    assert chip["cta_id"] == "purchase.start"
    assert chip["metadata"]["expected_contract_intent"] == "quick_order_reservation"
    assert event["data"]["metadata"]["cta_validation"][0]["result"] == "allowed"


def test_unregistered_label_only_chip_is_dropped() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "data": {
            "assistantResponse": "추천 기준으로 사용할 차량을 선택해 주세요.",
            "quickReplies": [
                {"label": "다시 검색", "domain": "DISCOVERY"},
                {"label": "처음으로", "domain": "LEADING"},
                {"label": "보유차량 중 선택", "domain": "DISCOVERY"},
            ],
        },
    }

    normalize_quickreply_ctas(event, contract=TurnContract(domain="discovery", intent="product_recommendation"))
    chips = event["data"]["quickReplies"]

    assert [chip["label"] for chip in chips] == ["보유차량 중 선택"]
    audit = event["data"]["metadata"]["cta_validation"]
    dropped = [item for item in audit if item["result"] == "dropped"]
    assert {item["label"] for item in dropped} == {"다시 검색", "처음으로"}
    assert all(item["reason"] == "no_executable_action" for item in dropped)


def test_entry_point_ctas_are_registered_with_contract_intents() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "leading",
        "data": {
            "assistantResponse": "무엇을 도와드릴까요?",
            "quickReplies": [
                {"label": "상품 검색", "domain": "DISCOVERY"},
                {"label": "타이어 추천", "domain": "DISCOVERY"},
                {"label": "내 차 검색", "domain": "DISCOVERY"},
                {"label": "내 예약 조회", "domain": "TRANSACTION"},
            ],
        },
    }

    normalize_quickreply_ctas(event)
    chips = event["data"]["quickReplies"]

    assert [chip["cta_id"] for chip in chips] == [
        "discovery.product_search.start",
        "discovery.recommendation.start",
        "owned_vehicle.select",
        "order.reservation.lookup",
    ]
    assert chips[2]["expected_contract_intent"] == "vehicle_lookup"
    assert chips[3]["expected_contract_intent"] == "order_history_lookup"


def test_unregistered_chip_with_url_is_kept_as_open_url_action() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "support",
        "data": {
            "assistantResponse": "자세한 내용은 안내 페이지에서 확인해 주세요.",
            "quickReplies": [
                {"label": "장착 가이드 보기", "domain": "SUPPORT", "url": "https://www.tstation.com/guide/install"},
            ],
        },
    }

    normalize_quickreply_ctas(event)
    chips = event["data"]["quickReplies"]

    assert [chip["label"] for chip in chips] == ["장착 가이드 보기"]
    audit = event["data"]["metadata"]["cta_validation"]
    assert audit[0]["result"] == "allowed"
    assert audit[0]["reason"] == "unregistered_url_action"


def test_preannotated_action_chip_is_kept() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "data": {
            "assistantResponse": "확인할 지역명을 입력해 주세요.",
            "quickReplies": [
                {"label": "서울", "domain": "TRANSACTION", "actionId": "change_region", "intentKey": "today_install"},
                {"label": "그냥 텍스트 칩", "domain": "TRANSACTION"},
            ],
        },
    }

    normalize_quickreply_ctas(event)
    chips = event["data"]["quickReplies"]

    assert [chip["label"] for chip in chips] == ["서울"]
    audit = event["data"]["metadata"]["cta_validation"]
    kept = next(item for item in audit if item["label"] == "서울")
    assert kept["result"] == "allowed"
    assert kept["reason"] == "preannotated_action_metadata"


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


def test_entry_ctas_blocked_while_contract_waits_on_required_slot() -> None:
    # Maintenance D-day flow: bot asked "which car?" — the contract is waiting on
    # vehicle selection, so navigation/entry chips are off-context and must drop.
    contract = TurnContract(
        domain="support",
        intent="maintenance_timing_guidance",
        blocking_required_slots=("mbr_car_reg_seq",),
    )
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "support",
        "data": {
            "assistantResponse": "어느 차량의 정비 일정을 확인해 드릴까요?",
            "quickReplies": [
                {"label": "매장 찾기", "domain": "TRANSACTION"},
                {"label": "타이어 추천", "domain": "DISCOVERY"},
                {"label": "12가3456", "domain": "DISCOVERY"},
            ],
        },
    }

    normalize_quickreply_ctas(event, contract=contract)
    chips = event["data"]["quickReplies"]

    # Only the plate-number chip (the pending answer itself) survives.
    assert [chip["label"] for chip in chips] == ["12가3456"]
    audit = event["data"]["metadata"]["cta_validation"]
    blocked = {item["label"]: item["reason"] for item in audit if item["result"] == "blocked"}
    assert blocked == {"매장 찾기": "blocked_during_slot_fill", "타이어 추천": "blocked_during_slot_fill"}


def test_entry_ctas_blocked_for_vehicle_lookup_intent() -> None:
    contract = TurnContract(domain="discovery", intent="vehicle_lookup")
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "data": {
            "assistantResponse": "추천 기준으로 사용할 차량을 선택해 주세요.",
            "quickReplies": [{"label": "상품 검색", "domain": "DISCOVERY"}],
        },
    }

    normalize_quickreply_ctas(event, contract=contract)

    assert event["data"]["quickReplies"] == []
    assert event["data"]["metadata"]["cta_validation"][0]["reason"] == "blocked_during_slot_fill"


def test_entry_ctas_still_allowed_without_pending_slot_fill() -> None:
    # Same chips, normal contract (greeting-style turn, nothing blocking) → must pass,
    # so the slot-fill rule cannot silently remove entry buttons elsewhere.
    contract = TurnContract(domain="leading", intent="greeting")
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "leading",
        "data": {
            "assistantResponse": "무엇을 도와드릴까요?",
            "quickReplies": [
                {"label": "매장 찾기", "domain": "TRANSACTION"},
                {"label": "타이어 추천", "domain": "DISCOVERY"},
            ],
        },
    }

    normalize_quickreply_ctas(event, contract=contract)
    chips = event["data"]["quickReplies"]

    assert [chip["label"] for chip in chips] == ["매장 찾기", "타이어 추천"]
    assert all(chip["cta_id"] for chip in chips)


def test_dynamic_vehicle_candidate_chip_is_typed_by_plate_pattern() -> None:
    event = {
        "type": "data",
        "template": "quickReply",
        "source_domain": "discovery",
        "data": {
            "assistantResponse": "205소4214 은(는) 등록된 차량 목록에 없어요. 등록된 차량 중에서 골라주세요.",
            "quickReplies": [
                {"label": "12가3456", "domain": "DISCOVERY"},
                {"label": "205소4214", "domain": "DISCOVERY"},
            ],
        },
    }

    normalize_quickreply_ctas(event, contract=TurnContract(domain="discovery", intent="vehicle_lookup"))
    chips = event["data"]["quickReplies"]

    assert [chip["label"] for chip in chips] == ["12가3456", "205소4214"]
    assert all(chip["cta_id"] == "dynamic.dynamic_vehicle_candidate" for chip in chips)
    assert all(chip["expected_behavior"] == "dynamic_choice" for chip in chips)
    assert chips[0]["metadata"]["dynamic_value"] == "12가3456"


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
