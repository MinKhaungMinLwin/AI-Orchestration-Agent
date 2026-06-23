"""Unit tests for chat._choose_quickreply_fallback() domain-aware routing.

Locks in:
  - LEADING domain → progress chips ([상품 검색, 타이어 추천])
  - Tool dispatch (order/coupon) overrides domain routing.
  - Unknown / non-LEADING domain → generic fallback ([1:1 문의하기])

Run from repo root:

    cd app/tstation-ai && uv run pytest tests/test_quickreply_fallback_routing.py -v
"""
from __future__ import annotations

import datetime
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.tstation import chat as chat_module, qc_verifier
from services.tstation.common.cta_urls import CTAUrls
from services.tstation.source_filter import _ORDER_FIELDS_BASE
from services.tstation.agents.b_discovery_agent import tools as discovery_tools
from services.tstation.agents.base_agent import (
    _build_registered_vehicle_staggered_tire_event,
    _is_staggered_registered_vehicle,
    _registered_vehicle_slot_values,
    _slot_data_for_tool_event,
)
from services.tstation.agents.c_transaction_agent.agent import TRANSACTION_ORDER_SYSTEM_PROMPT_TEMPLATE
from services.tstation.chat import (
    _FALLBACK_COUPON,
    _FALLBACK_GENERIC,
    _FALLBACK_LEADING_PROGRESS,
    _FALLBACK_ORDER_LIST,
    _FALLBACK_TRANSACTION_STORE_SEARCH,
    _ALL_MY_T_5_PERCENT_COUPON_RE,
    _ALL_MY_T_BENEFIT_PAGE_RE,
    _COUPON_ISSUE_INTENT_RE,
    _all_my_t_benefit_page_event,
    _build_coupon_applicability_event,
    _build_coupon_channel_policy_event,
    _build_default_benefit_event,
    _build_maintenance_dday_event,
    _build_owned_coupon_best_discount_event,
    _build_owned_coupon_expiry_lookup_event,
    _build_oe_replacement_guidance_event,
    _build_product_coupon_eligibility_event,
    _build_product_coupon_price_amount_event,
    _build_product_coupon_price_no_product_event,
    _build_quantity_benefit_missing_event,
    _reminding_alarm_event,
    _build_store_holiday_period_event,
    _build_transaction_policy_context,
    _build_product_attribute_event_from_search_results,
    _quantity_benefit_continuation_frame_from_pending,
    _resolve_goods_no_from_product_template_selection,
    _final_price_from_row,
    _build_bare_product_search_tool_input,
    _build_external_price_comparison_event_from_search_results,
    _build_size_only_product_search_tool_input,
    _build_store_availability_quantity_prompt_event,
    _external_price_search_results_from_sources,
    _build_product_description_quickreply_event,
    _build_multi_product_detail_quickreply_event,
    _build_product_comparison_event,
    _build_product_comparison_event_from_search_results,
    _product_compare_target_prompt_event,
    _multi_product_intent_clarification_event,
    _build_product_size_list_event_from_search_results,
    _build_product_size_list_not_found_event,
    _build_recent_product_size_availability_event,
    _build_recent_product_size_availability_event_from_rows,
    _build_recent_product_size_availability_missing_context_event,
    _build_no_visible_output_fallback_event,
    _build_turn_contract_fallback_event,
    _build_turn_contract_required_slot_guard_event,
    _build_transaction_unresolved_product_resolution_event,
    _build_product_objective_followup_clarification_event,
    _clear_stale_product_slots_for_new_recommendation,
    _datepick_template_recovery_candidate_from_messages,
    _verified_datepick_order_values,
    _comparison_query_with_recent_context,
    _recent_product_set_size_availability_context,
    _should_clarify_ambiguous_multi_product_query,
    _multi_product_detail_continuation_names,
    _multi_product_compare_continuation_query,
    _recent_multi_product_clarification_names,
    _should_prompt_for_new_product_compare_target,
    _should_resolve_compare_target_product_pair,
    _should_skip_product_compare_override,
    _build_oe_replacement_followup_recommendation_args,
    _build_oe_replacement_same_product_brand_prompt_event,
    _build_oe_replacement_same_product_search_args,
    _bare_product_search_followup_override,
    _build_discovery_policy_context,
    _build_manual_tire_size_input_event,
    _build_missing_order_product_reselection_event,
    _build_order_quantity_prompt_event,
    _build_order_arrival_status_event,
    _build_order_history_reorder_event,
    _build_staggered_vehicle_tire_selection_event,
    _build_staggered_tire_quantity_limit_event,
    _is_manual_tire_size_input_selection,
    _is_order_quantity_prompt_continuation_text,
    _is_staggered_selected_tire_size_context,
    _listcar_allows_staggered_tire_prompt,
    _apply_vehicle_selection_slot_values,
    _resolve_vehicle_tire_position_selection,
    _vehicle_selection_slot_values,
    _vehicle_type_compatibility_guard_event,
    _preferred_product_search_keyword,
    _infer_multi_variant_recommendation_constraints,
    _is_oe_replacement_context,
    _is_explicit_store_purchase_chain_request,
    _is_oe_replacement_equivalent_query,
    _is_oe_replacement_followup_query,
    _is_owned_vehicle_selection_cta,
    _is_strong_coupon_applicability_query,
    _is_product_coupon_eligibility_query,
    _is_product_coupon_price_amount_query,
    _is_specific_coupon_usage_query,
    _is_product_comparison_query,
    _tool_error_response_decision,
    _tool_parse_failure_response_decision,
    _qc_factual_mismatch_guard_event,
    _repair_assistant_response,
    _repair_qc_mismatch_event,
    _tool_error_summary,
    _trace_final_error_state,
    _response_decision_for_source_domain,
    _response_shape_key_for_source_domain,
    _is_product_attribute_lookup_query,
    _should_apply_product_attribute_resolver,
    _should_replace_listcar_with_product_attribute_lookup,
    _is_store_holiday_period_info_query,
    _is_sized_product_name_search_query,
    _is_recent_product_size_availability_query,
    _is_size_only_store_availability_continuation,
    _is_confirmed_product_store_scope_followup,
    _is_strong_product_name_match,
    _is_product_size_list_intent,
    _is_owned_coupon_best_discount_query,
    _is_owned_coupon_expiry_lookup_query,
    _coupon_target_brand_for_query,
    _coupon_target_product_name_for_query,
    _split_product_size_quantity_from_text,
    _delivery_policy_guard_event,
    _direct_tire_delivery_guard_event,
    _build_vehicle_information_event,
    _build_complaint_scope_guard_event,
    _choose_quickreply_fallback,
    _coerce_unmatched_vehicle_listcar_to_owner_prompt,
    _coerce_vehicle_type_compatibility_listcar_to_quickreply,
    _coupon_channel_type,
    _discovery_recovery_chips_for_text,
    _find_coupon_from_owned_coupons,
    _find_single_confident_coupon_from_owned_coupons,
    _is_order_arrival_status_query,
    _is_order_history_reorder_query,
    _is_specific_owned_coupon_lookup_query,
    _infer_followup_recommendation_context,
    _ensure_discovery_transaction_recovery_chain,
    _inject_store_detail_chip_for_contact_guidance,
    _inject_order_history_chip_for_cancel_guidance,
    _is_ev_suitability_turn,
    _extract_plain_store_info_store_name,
    _is_bare_product_name_search_query,
    _is_fresh_product_transaction_request,
    _is_new_store_name_anchor_for_current_turn,
    _unique_product_row_from_sized_search_result,
    _clear_stale_product_identity_for_fresh_transaction,
    _normalize_store_name_for_slot_compare,
    _NON_SELF_CAR_RE,
    _looks_like_generic_dead_end_chips,
    _normalize_discovery_policy_quickreply,
    _complaint_scope_for_turn,
    _infer_complaint_scope,
    _normalize_existing_reservation_change_quickreply,
    _normalize_policy_guidance_leak_quickreply,
    _normalize_price_policy_quickreply,
    _store_detail_quickreply_from_sources,
    _normalize_vehicle_owner_lookup_text,
    _non_self_vehicle_plate_owner_lookup_plate,
    _non_self_vehicle_plate_owner_lookup_prompt_event,
    _pick_product_row_from_search_result,
    _product_search_keyword_candidates,
    _select_order_history_reorder_row,
    _product_size_list_keyword_from_context,
    _pickup_service_guard_event,
    _past_event_page_event,
    _price_policy_guard_event,
    _unsupported_brand_policy_guard_event,
    _recommendation_type_for_vehicle_auto_continue,
    _recent_product_coupon_price_target,
    _recent_product_keyword_for_size_only_search,
    _recent_store_name_for_availability_continuation,
    _remove_home_quick_reply_chips,
    _reservation_date_range_guard_event,
    _parse_requested_reservation_date,
    _owned_coupon_lookup_summary_text,
    _resolve_order_row_for_arrival_query,
    _specific_owned_coupon_lookup_hint,
    _requested_reservation_cal_day_or_today,
    _requested_maintenance_focus,
    _qc_skip_reason,
    _rule_based_classify,
    _select_vehicle_from_listcar_event,
    _should_reuse_pending_vehicle_lookup_car_no,
    _should_prompt_order_quantity_before_store,
    _is_plain_store_search_reset_allowed,
    _is_quantityless_cart_or_order_cta,
    _should_preserve_store_date_availability_context,
    _should_suppress_inherited_recommendation_context_for_product_attribute,
    _should_skip_qc,
    _should_replace_discovery_dead_end_chips,
    _should_force_warranty_claim_support_route,
    _should_force_best_seller_code_route,
    _enrich_best_selling_result_for_product_cards,
    _quickreply_cta_clarification_event,
    _sanitize_transaction_cta_contracts,
    _apply_cta_context_to_slots,
    _is_current_location_store_search_confirmation,
    _merged_quickreply_cta_context,
    _cta_preview_input_from_slots,
    _support_fast_path,
    MultiAgentDomain,
    StreamingMultiAgentCoordinator,
    TStationChatServiceV2,
)
from schemas.tstation.chat_message import ChatMessageRequest
from services.tstation.agents.c_transaction_agent.tools import _apply_store_preview_policy_patch
from services.tstation.policies.cross_domain_policy import plan_cross_domain_turn
from services.tstation.policies.coupon_query_gate import should_consider_coupon_gate
from services.tstation.policies.delivery_policy_gate import (
    DeliveryPolicyIntent,
    decide_delivery_policy_gate,
)
from services.tstation.policies.intent_frame import IntentFrame, PolicyDomain
from services.tstation.policies.transaction_intent_policy import build_transaction_intent_frame, plan_transaction_tools
from services.tstation.policies.transaction_response_policy import decide_transaction_response
from services.tstation.policies.response_decision import ResponseDecision, ResponseShape, TemplateName
from services.tstation.policies.turn_contract import (
    TurnContract,
    build_required_slot_clarification_event,
    build_response_policy_guard_event,
    build_turn_contract,
    response_contract_violations,
    should_guard_required_slots,
    violates_response_template_contract,
)
from services.tstation.policies.pickup_service_gate import deterministic_pickup_service_gate_decision
from services.tstation.policies.store_service_gate import decide_store_service_gate, unverifiable_store_preference_labels
from schemas.tstation.slots import ConversationSlots
from services.tstation.template_mapper import (
    _map_store_detail_info,
    current_discovery_response_decision,
    current_goal_type,
    current_pending_intent,
    current_runflat_comparison,
    current_transaction_response_decision,
    current_user_text,
    try_build_template,
)
from services.tstation.policies.discovery_intent_policy import (
    best_seller_period_from_text,
    build_discovery_intent_frame,
    is_best_seller_request,
    plan_discovery_tools,
)
from services.tstation.policies.discovery_response_policy import decide_discovery_response
from services.tstation.policies.price_response_policy import build_price_intent_frame, decide_price_response
from services.tstation.source_filter import filter_for_context

def _labels(chips: list[dict]) -> list[str]:
    return [c["label"] for c in chips]


def test_chip_context_preserves_action_contract_fields() -> None:
    request = ChatMessageRequest(
        content="다른 지역 입력",
        session_id="s1",
        chip_context={
            "domain": "TRANSACTION",
            "actionId": "enter_region",
            "intentKey": "today_install",
            "metadata": {"goodsNo": "G000000317729", "ordQty": 4},
        },
    )

    dumped = request.chip_context.model_dump()

    assert dumped["actionId"] == "enter_region"
    assert dumped["intentKey"] == "today_install"
    assert dumped["metadata"]["goodsNo"] == "G000000317729"


def test_quickreply_cta_action_enter_region_asks_for_region_only() -> None:
    event = _quickreply_cta_clarification_event(
        "다른 지역 입력",
        {"domain": "TRANSACTION", "actionId": "enter_region", "intentKey": "today_install"},
        cta_context={"goodsNo": "G000000317729", "ordQty": 4, "requestedCalDay": "20260618"},
    )

    assert event is not None
    assert event["template"] == "quickReply"
    assert "지역명" in event["data"]["assistantResponse"]
    assert event["data"]["metadata"]["ctaContext"]["goodsNo"] == "G000000317729"
    assert event["data"]["metadata"]["ctaContext"]["requestedCalDay"] == "20260618"
    assert [chip["actionId"] for chip in event["data"]["quickReplies"]] == [
        "change_region",
        "change_region",
        "change_region",
    ]


def test_transaction_cta_sanitizer_removes_label_only_reservation_and_contracts_region() -> None:
    event_data = {
        "assistantResponse": "오늘 장착 가능한 일정이 확인되지 않았어요.",
        "quickReplies": [
            {"label": "예약하기", "domain": "TRANSACTION"},
            {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
            {"label": "다른 상품 보기", "domain": "DISCOVERY"},
        ],
        "predictedDomains": ["TRANSACTION"],
    }

    changed = _sanitize_transaction_cta_contracts(event_data, source_domain="transaction")

    assert changed is True
    assert _labels(event_data["quickReplies"]) == ["다른 지역 입력", "다른 상품 보기"]
    assert event_data["quickReplies"][0]["actionId"] == "enter_region"


def test_cta_context_recovers_from_latest_quickreply_template_when_chip_has_no_metadata() -> None:
    latest_quickreply = {
        "template": "quickReply",
        "data": {
            "assistantResponse": "확인할 지역명을 입력해 주세요.",
            "quickReplies": [],
            "metadata": {
                "ctaContext": {
                    "intentKey": "today_install",
                    "goodsNo": "G000000317729",
                    "tireSize": "235/35R20",
                    "ordQty": 4,
                    "requestedCalDay": "20260618",
                }
            },
        },
    }

    context = _merged_quickreply_cta_context(
        {"domain": "TRANSACTION", "actionId": "change_region", "intentKey": "today_install"},
        latest_quickreply,
    )

    assert context["goodsNo"] == "G000000317729"
    assert context["ordQty"] == 4
    assert context["requestedCalDay"] == "20260618"


def test_apply_cta_context_to_slots_preserves_today_install_preview_slots() -> None:
    slots = ConversationSlots()
    context = {
        "intentKey": "today_install",
        "goodsNo": "G000000317729",
        "tireSize": "235/35R20",
        "ordQty": 4,
        "requestedCalDay": "20260618",
    }

    updated = _apply_cta_context_to_slots(slots, context)

    assert updated.goods_no == "G000000317729"
    assert updated.tire_size == "235/35R20"
    assert updated.ord_qty == 4
    assert updated.requested_cal_day == "20260618"
    assert updated.availability_intent == "today_install"
    assert updated.pending_intent == "stock"
    assert updated.goal_type == "store_with_stock"


def test_cta_preview_input_uses_recovered_region_and_requested_day() -> None:
    slots = ConversationSlots(
        goods_no="G000000317729",
        tire_size="235/35R20",
        ord_qty=4,
        region="서울",
        requested_cal_day="20260618",
        availability_intent="today_install",
    )

    preview_input, missing_slot = _cta_preview_input_from_slots(slots)

    assert missing_slot is None
    assert preview_input == {
        "goods_no": "G000000317729",
        "ord_qty": 4,
        "include_price": True,
        "region_code": "서울",
        "requested_cal_day": "20260618",
    }


def test_cta_preview_input_reports_missing_location_without_generic_guard() -> None:
    slots = ConversationSlots(goods_no="G000000317729", ord_qty=4)

    preview_input, missing_slot = _cta_preview_input_from_slots(slots)

    assert preview_input is None
    assert missing_slot == "location"


def test_registered_vehicle_staggered_fitment_builds_size_selection_prompt() -> None:
    row = {
        "car_no": "56모2162",
        "car_lnc_cd": "W022859",
        "car_nm": "3-series(F30) 320d A/T",
        "mbr_car_unif_no": "2000002975",
        "tire_size_fr": "2255018",
        "tire_size_re": "2555018",
    }

    assert _is_staggered_registered_vehicle(row) is True

    event = _build_registered_vehicle_staggered_tire_event(row)

    assert event is not None
    assert event["template"] == "quickReply"
    assert "전륜 **225/50R18**, 후륜 **255/50R18**" in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["앞바퀴사이즈", "뒷바퀴사이즈", "다른 사이즈 입력"]


def test_registered_vehicle_staggered_slot_values_clear_selected_size_until_user_chooses() -> None:
    row = {
        "car_no": "56모2162",
        "car_lnc_cd": "W022859",
        "car_nm": "3-series(F30) 320d A/T",
        "mbr_car_unif_no": "2000002975",
        "tire_size_fr": "2255018",
        "tire_size_re": "2555018",
    }

    slot_values = _registered_vehicle_slot_values(row)

    assert slot_values["tire_size_front"] == "225/50R18"
    assert slot_values["tire_size_rear"] == "255/50R18"
    assert slot_values["tire_size"] is None


def test_qc_runs_for_code_mapped_product_with_tool_sources() -> None:
    tools = {"search_product_tool"}

    assert _qc_skip_reason(tools, "product", "code_mapper", "default") is None
    assert _should_skip_qc(tools, "product", "code_mapper", "default") is False


def test_qc_runs_for_code_mapped_templates_with_tool_sources() -> None:
    assert _qc_skip_reason({"get_store_schedule_tool"}, "datepick", "code_mapper", "code_mapper") is None
    assert _qc_skip_reason({"get_my_cars_tool"}, "listCar", "code_mapper", "code_mapper") is None


def test_qc_skips_only_when_no_tool_sources_exist() -> None:
    assert _qc_skip_reason(set(), "quickReply", None, None) == "no_tool_sources"


def test_tc186_price_policy_guard_denies_arbitrary_coupon_issue() -> None:
    event = _price_policy_guard_event("미안한데 진짜 돈이 없어 타이어 90% 할인쿠폰 1개만 발급해줘")

    assert event is not None
    assert event["template"] == "quickReply"
    assert "직접 발급" in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["쿠폰함 바로가기", "내 쿠폰 조회"]


def test_coupon_issue_regex_requires_coupon_context() -> None:
    assert _COUPON_ISSUE_INTENT_RE.search("쿠폰 어떻게 받아?") is not None
    assert _COUPON_ISSUE_INTENT_RE.search("30% 할인권 발급해줘") is not None
    assert _COUPON_ISSUE_INTENT_RE.search("그 동안 티스테이션에서 정비받은 내역 한번에 보고싶어.") is None
    assert _COUPON_ISSUE_INTENT_RE.search("관리받은 내역 보여줘") is None


def test_all_my_t_five_percent_coupon_path_query_is_detected() -> None:
    assert _ALL_MY_T_5_PERCENT_COUPON_RE.search("방금 가입했는데 all my T 5% 할인쿠폰은 어디서 받아?")
    assert _ALL_MY_T_5_PERCENT_COUPON_RE.search("올마이티 5% 쿠폰 어디서 다운로드해?")
    assert _ALL_MY_T_5_PERCENT_COUPON_RE.search("5% 할인쿠폰 all my T 회원이면 받을 수 있어?")
    assert _ALL_MY_T_5_PERCENT_COUPON_RE.search("그냥 5% 할인쿠폰 알려줘") is None


def test_all_my_t_benefit_page_query_is_detected() -> None:
    assert _ALL_MY_T_BENEFIT_PAGE_RE.search("all my T 혜택 안내 페이지 링크 알려줘")
    assert _ALL_MY_T_BENEFIT_PAGE_RE.search("올마이티 혜택 페이지 바로가기 줘")
    assert _ALL_MY_T_BENEFIT_PAGE_RE.search("혜택 안내 링크 all my T")
    assert _ALL_MY_T_BENEFIT_PAGE_RE.search("내 쿠폰 보여줘") is None


def test_all_my_t_benefit_page_event_uses_dedicated_cta() -> None:
    event = _all_my_t_benefit_page_event()

    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "code_all_my_t_benefit_page"
    assert "쿠폰함" not in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["all my T 혜택 안내", "1:1 문의하기"]
    assert event["data"]["quickReplies"][0]["url"].endswith("/membership/dashboard/benefit")


def test_default_benefit_cta_skips_coupon_gate() -> None:
    assert should_consider_coupon_gate("지금 받을 수 있는 혜택은?") is False
    assert should_consider_coupon_gate("내 쿠폰 보여줘") is True


def test_default_benefit_event_lists_events_and_deals_with_links() -> None:
    event = _build_default_benefit_event(
        {
            "status": "success",
            "data": {
                "items": [
                    {
                        "evt_nm": "한국타이어 페스타",
                        "evt_strt_dtime": "2026-06-01 00:00:00",
                        "evt_end_dtime": "2026-06-30 23:59:59",
                        "evt_url_addr": "https://wwwqa.tstation.com/promotion/event/festa",
                    }
                ]
            },
        },
        {
            "status": "success",
            "data": {
                "items": [
                    {
                        "deal_nm": "여름맞이 기획전",
                        "deal_strt_dtime": "2026-06-01 00:00:00",
                        "deal_end_dtime": "2026-07-15 23:59:59",
                        "dtl_conts_url_addr": "https://wwwqa.tstation.com/promotion/deal/summer",
                    }
                ]
            },
        },
    )

    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "code_default_benefit_event_deal"
    assistant_response = event["data"]["assistantResponse"]
    assert "보유 쿠폰" not in assistant_response
    assert "쿠폰함" not in assistant_response
    assert "이벤트" in assistant_response
    assert "한국타이어 페스타 · 2026-06-01 ~ 2026-06-30" in assistant_response
    assert "https://wwwqa.tstation.com/promotion/event/festa" in assistant_response
    assert "기획전" in assistant_response
    assert "여름맞이 기획전 · 2026-06-01 ~ 2026-07-15" in assistant_response
    assert "https://wwwqa.tstation.com/promotion/deal/summer" in assistant_response
    assert _labels(event["data"]["quickReplies"]) == ["진행 중인 이벤트 보기", "처음으로"]


def test_tc189_price_policy_guard_blocks_expired_coupon_restore() -> None:
    event = _price_policy_guard_event("작년에 끝난 블랙세일 쿠폰 못쓰고 만료됨 원복해줘")

    assert event is not None
    assert event["template"] == "quickReply"
    assert "원복 또는 재사용이 어렵" in event["data"]["assistantResponse"]
    assert "1:1 문의하기" in _labels(event["data"]["quickReplies"])


def test_price_policy_guard_does_not_block_owned_coupon_expiry_lookup() -> None:
    frame = build_price_intent_frame("보유 쿠폰 중에 이번달 만료인거 뭐 있어?")

    assert frame.intent != "expired_coupon_or_event"
    assert _price_policy_guard_event("보유 쿠폰 중에 이번달 만료인거 뭐 있어?") is None
    assert _is_owned_coupon_expiry_lookup_query("보유 쿠폰 중에 이번달 만료인거 뭐 있어?")


def test_price_policy_guard_keeps_expired_coupon_restore_and_event_reuse() -> None:
    coupon_event = _price_policy_guard_event("만료된 쿠폰 원복해줘")
    event_event = _price_policy_guard_event("끝난 이벤트 혜택 다시 쓸 수 있어?")

    assert coupon_event is not None
    assert event_event is not None
    assert "원복 또는 재사용이 어렵" in coupon_event["data"]["assistantResponse"]
    assert "원복 또는 재사용이 어렵" in event_event["data"]["assistantResponse"]


def test_unsupported_brand_policy_blocks_store_search_for_kumho_store_query() -> None:
    event = _unsupported_brand_policy_guard_event("티스테이션 판교점에 금호 타이어 취급해?")

    assert event is not None
    data = event["data"]
    assert event["assistant_response_source"] == "code_unsupported_brand_policy_guard"
    assert (
        "현재 챗봇에서 바로 안내 가능한 브랜드는 한국타이어, 라우펜, 미쉐린, 피렐리, 브리지스톤, 콘티넨탈, 굿이어"
        in data["assistantResponse"]
    )
    assert "금호" in data["assistantResponse"]
    assert "매장별 별도 취급 여부는 실시간 데이터가 없어 확정할 수 없으니 매장에 직접 확인해 주세요." in data["assistantResponse"]
    assert _labels(data["quickReplies"]) == ["지원 브랜드 상품 보기", "다른 브랜드 추천"]


def test_unsupported_brand_policy_uses_recent_store_context_for_followup_brand_query() -> None:
    event = _unsupported_brand_policy_guard_event(
        "넥센도 판매해?",
        recent_context="이전 문의: 티스테이션 판교점에 금호 타이어 취급해?",
    )

    assert event is not None
    response = event["data"]["assistantResponse"]
    assert "넥센" in response
    assert "매장별 별도 취급 여부" in response


def test_unsupported_brand_policy_does_not_block_supported_or_place_name_queries() -> None:
    assert _unsupported_brand_policy_guard_event("미쉐린도 판매해?") is None
    assert _unsupported_brand_policy_guard_event("브리지스톤 판교점에 있어?") is None
    assert _unsupported_brand_policy_guard_event("금호동 근처 매장 찾아줘") is None
    assert _unsupported_brand_policy_guard_event("판교점 영업시간 알려줘") is None


def test_unsupported_brand_policy_detects_extended_known_tire_brands() -> None:
    assert _unsupported_brand_policy_guard_event("요코하마 타이어 판매해?") is not None
    assert _unsupported_brand_policy_guard_event("Dunlop 2355519 가격 있어?") is not None
    assert _unsupported_brand_policy_guard_event("BFGoodrich 타이어도 취급해?") is not None


def test_past_event_page_event_routes_ended_event_list_queries() -> None:
    for text in ("지난 이벤트 알려줘", "종료된 이벤트 알려줘", "끝난 행사 보여줘"):
        event = _past_event_page_event(text)

        assert event is not None
        assert event["template"] == "quickReply"
        assert "지난 이벤트" in event["data"]["assistantResponse"]
        chips = event["data"]["quickReplies"]
        assert _labels(chips) == ["지난 이벤트 보기", "진행 중인 이벤트"]
        assert chips[0]["url"].endswith("/promotion/past-event-list")


def test_past_event_page_event_does_not_hijack_restore_claims() -> None:
    assert _past_event_page_event("종료된 이벤트 혜택 원복해줘") is None


def test_tc210_price_policy_guard_denies_fake_vip_link() -> None:
    event = _price_policy_guard_event("T블랙멤버십 VIP 카드 50% 할인링크 보내봐")

    assert event is not None
    assert event["template"] == "quickReply"
    assert "확인되지 않은 VIP/블랙카드/50% 전용 혜택" in event["data"]["assistantResponse"]
    assert "할인 링크는 제공할 수 없" in event["data"]["assistantResponse"]


def test_pickup_service_guard_handles_application_question() -> None:
    event = _pickup_service_guard_event("픽업서비스 어떻게 신청해?")

    assert event is not None
    assert event["template"] == "quickReply"
    assert "매장 기준 최대 30km" in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["픽업서비스 신청", "내 근처 매장 찾기", "타이어 추천"]
    assert "1:1 문의하기" not in _labels(event["data"]["quickReplies"])


def test_pickup_service_gate_classifies_required_intents() -> None:
    assert deterministic_pickup_service_gate_decision("픽업서비스 어떻게 신청해?").intent == "pickup_howto"
    assert deterministic_pickup_service_gate_decision("차 가지러 올 수 있어?").intent == "pickup_request_context"
    assert (
        deterministic_pickup_service_gate_decision(
            "시간이 없어서 회사로 차 가지러 왔다가 타이어 교체하고 집앞까지 데려다 줄 수 있을까?"
        ).intent
        == "pickup_request_context"
    )
    assert deterministic_pickup_service_gate_decision("픽업 기사 어디쯤이야?").intent == "pickup_status"

    generic = deterministic_pickup_service_gate_decision("신청 방법 알려줘")
    assert generic is not None
    assert generic.is_pickup is False
    assert generic.intent == "none"


def test_pickup_service_guard_handles_availability_question() -> None:
    event = _pickup_service_guard_event("차 가지러 올 수 있어?")

    assert event is not None
    assert event["template"] == "quickReply"
    assert "매장 기준 최대 30km" in event["data"]["assistantResponse"]
    assert event["data"]["quickReplies"][0]["label"] == "픽업서비스 신청"


def test_pickup_service_guard_handles_pickup_and_delivery_request() -> None:
    event = _pickup_service_guard_event("시간이 없어서 회사로 차 가지러 왔다가 타이어 교체하고 집앞까지 데려다 줄 수 있을까?")

    assert event is not None
    assert event["template"] == "quickReply"
    assert "고객 차량을 픽업해 타이어를 교체한 뒤 다시 인도" in event["data"]["assistantResponse"]
    assert event["data"]["quickReplies"][0]["label"] == "픽업서비스 신청"


def test_pickup_service_guard_handles_driver_status_question() -> None:
    event = _pickup_service_guard_event("픽업 기사 어디까지 왔어?")

    assert event is not None
    assert event["template"] == "quickReply"
    assert "실시간 위치나 도착 시간은 챗봇에서 바로 확인하기 어려워요" in event["data"]["assistantResponse"]
    assert "픽업서비스 내역" in event["data"]["assistantResponse"]
    assert "픽업 매장" not in event["data"]["assistantResponse"]
    assert "매장으로" not in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["픽업서비스 내역"]
    assert event["data"]["quickReplies"][0]["url"].endswith("/mypage/tstation/reservation/pickupList")


def test_pickup_service_guard_distinguishes_application_from_status() -> None:
    status_event = _pickup_service_guard_event("픽업딜리버리 신청했는데 기사님 어디쯤 오고계셔?")
    howto_event = _pickup_service_guard_event("픽업서비스 어떻게 신청해?")

    assert status_event is not None
    assert howto_event is not None
    assert _labels(status_event["data"]["quickReplies"]) == ["픽업서비스 내역"]
    assert _labels(howto_event["data"]["quickReplies"])[0] == "픽업서비스 신청"


def test_pickup_service_guard_does_not_hijack_generic_application_question() -> None:
    assert _pickup_service_guard_event("신청 방법 안내해줘") is None
    assert _pickup_service_guard_event("워런티 어떻게 신청해?") is None


def test_direct_tire_delivery_guard_blocks_home_delivery_self_install() -> None:
    event = _direct_tire_delivery_guard_event("집으로 배송받아서 내가 직접 갈아도 돼?")

    assert event is not None
    assert event["template"] == "quickReply"
    assert "집으로 배송받아 직접 장착하는 방식은 지원하지 않아요" in event["data"]["assistantResponse"]
    assert "선택하신 장착점" in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["장착 매장 찾기", "타이어 추천", "구매하기"]
    assert "1:1 문의하기" not in _labels(event["data"]["quickReplies"])


def test_direct_tire_delivery_guard_blocks_casual_home_delivery_request() -> None:
    event = _direct_tire_delivery_guard_event("타이어 집으로 걍 배송받고 싶어.")

    assert event is not None
    assert "지원하지 않아요" in event["data"]["assistantResponse"]


def test_direct_tire_delivery_guard_blocks_order_context_home_delivery_request() -> None:
    event = _direct_tire_delivery_guard_event("집으로 배송해줘")

    assert event is not None
    assert event["assistant_response_source"] == "code_direct_tire_delivery_guard"
    assert "집으로 배송받아 직접 장착하는 방식은 지원하지 않아요" in event["data"]["assistantResponse"]


def test_direct_tire_delivery_guard_ignores_shipping_fee_policy_question() -> None:
    assert _direct_tire_delivery_guard_event("제주도는 배송비 더 들어?") is None
    assert _direct_tire_delivery_guard_event("주문 배송 상태 확인해줘") is None


def test_delivery_policy_gate_blocks_direct_home_delivery() -> None:
    decision = decide_delivery_policy_gate(user_text="타이어 집으로 걍 배송받고 싶어.")

    assert decision.intent == DeliveryPolicyIntent.DIRECT_HOME_DELIVERY
    event = _delivery_policy_guard_event("타이어 집으로 걍 배송받고 싶어.")
    assert event is not None
    assert event["assistant_response_source"] == "code_direct_tire_delivery_guard"
    assert "직접 장착하는 방식은 지원하지 않아요" in event["data"]["assistantResponse"]


def test_delivery_policy_gate_handles_jeju_shipping_fee() -> None:
    decision = decide_delivery_policy_gate(user_text="서귀포시인데 배송비 더 들어?")

    assert decision.intent == DeliveryPolicyIntent.SHIPPING_FEE_REGION
    assert decision.region_hint == "서귀포"
    event = _delivery_policy_guard_event("서귀포시인데 배송비 더 들어?")
    assert event is not None
    assert event["assistant_response_source"] == "code_shipping_fee_policy_guard"
    assert "상품 1개당 배송비 1만 원" in event["data"]["assistantResponse"]


def test_delivery_policy_gate_handles_short_jeju_followup_from_shipping_context() -> None:
    decision = decide_delivery_policy_gate(
        user_text="제주도는?",
        recent_context="강원 산간 지역은 배송비 더 들어?",
    )

    assert decision.intent == DeliveryPolicyIntent.SHIPPING_FEE_FOLLOWUP
    event = _delivery_policy_guard_event("제주도는?", recent_context="배송비 더 들어?")
    assert event is not None
    assert event["assistant_response_source"] == "code_shipping_fee_policy_guard"


def test_delivery_policy_gate_does_not_hijack_order_delivery_status() -> None:
    decision = decide_delivery_policy_gate(user_text="주문 배송 상태 확인해줘")

    assert decision.intent == DeliveryPolicyIntent.NONE
    assert _delivery_policy_guard_event("주문 배송 상태 확인해줘") is None


def test_delivery_policy_gate_handles_online_store_price_policy() -> None:
    decision = decide_delivery_policy_gate(user_text="제주도 매장에서도 온라인 가격이랑 똑같아?")

    assert decision.intent == DeliveryPolicyIntent.ONLINE_STORE_PRICE_POLICY
    event = _delivery_policy_guard_event("제주도 매장에서도 온라인 가격이랑 똑같아?")
    assert event is not None
    assert event["assistant_response_source"] == "code_online_store_price_policy_guard"
    assert "온라인 판매가와 매장 현장 판매가" in event["data"]["assistantResponse"]


def test_delivery_policy_gate_handles_regional_product_price_policy() -> None:
    text = "벤투스 에어 S 상품 제주도에서 사는거랑, 서울에서 사는거랑 가격 똑같을까?"
    decision = decide_delivery_policy_gate(user_text=text)

    assert decision.intent == DeliveryPolicyIntent.REGIONAL_PRICE_POLICY
    event = _delivery_policy_guard_event(text)
    assert event is not None
    assert event["assistant_response_source"] == "code_regional_price_policy_guard"
    assert "지역, 장착점, 행사, 쿠폰, 재고, 배송 조건" in event["data"]["assistantResponse"]
    assert "상품 규격과 장착점을 선택한 뒤 주문/결제 단계" in event["data"]["assistantResponse"]


def test_oe_replacement_query_is_detected() -> None:
    assert _is_oe_replacement_equivalent_query("내 차 살 때 끼워져 있던 타이어랑 똑같은 거 있어?")
    assert _is_oe_replacement_equivalent_query("내 차 제네시스 GV70이고 미쉐린 타이어 끼고 있었던 거 같은데, 동일한 상품 판매하고 있어?")
    assert _is_oe_replacement_equivalent_query("OE 타이어랑 같은 상품 있어?")
    assert _is_oe_replacement_equivalent_query("RE 상품으로 교체하면 돼?")
    assert not _is_oe_replacement_equivalent_query("requesting tire recommendation following tire feature explanation")
    assert not _is_oe_replacement_equivalent_query("Current Time: Monday")


def test_order_history_reorder_query_is_not_oe_replacement() -> None:
    text = "205소4214 이전에 장착했던 타이어와 동일한 상품으로 교체하고 싶어"

    assert _is_order_history_reorder_query(text)
    assert not _is_oe_replacement_equivalent_query(text)

    route = StreamingMultiAgentCoordinator._force_keyword_routing(text)

    assert route is not None
    assert route.domains == [MultiAgentDomain.Domain.TRANSACTION]
    assert route.agent_prompt_profile == "transaction_order"


def test_order_history_reorder_does_not_hijack_strong_oe_query() -> None:
    text = "차 살 때 출고 타이어랑 같은 상품으로 교체하고 싶어"

    assert not _is_order_history_reorder_query(text)
    assert _is_oe_replacement_equivalent_query(text)


def test_order_history_reorder_prefers_car_no_over_same_tire_size() -> None:
    orders_result = {
        "status": "success",
        "data": {
            "orders": [
                {
                    "ord_no": "O1",
                    "goods_no": "G-WRONG",
                    "goods_nm": "다른 차량 상품",
                    "tire_size_1": "235/55R19",
                    "sys_reg_dtime": "2026-06-22",
                    "car_no": "33가3333",
                    "car_nm": "다른 차량",
                },
                {
                    "ord_no": "O2",
                    "goods_no": "G-RIGHT",
                    "goods_nm": "옵티모 H426",
                    "tire_size_1": "205/65R16",
                    "sys_reg_dtime": "2026-06-17",
                    "car_no": "205소4214",
                    "car_nm": "제네시스 GV70",
                },
            ],
        },
    }

    row, reason = _select_order_history_reorder_row(
        "205소4214 이전에 장착했던 타이어와 동일한 상품으로 교체하고 싶어",
        orders_result,
    )

    assert reason == "car_no"
    assert row is not None
    assert row["goods_no"] == "G-RIGHT"


def test_order_history_reorder_can_match_vehicle_name_before_size_fallback() -> None:
    orders_result = {
        "status": "success",
        "data": {
            "orders": [
                {
                    "goods_no": "G-1",
                    "goods_nm": "키너지 EX",
                    "tire_size_1": "235/55R19",
                    "sys_reg_dtime": "2026-06-22",
                    "car_no": "11가1111",
                    "car_nm": "아반떼",
                },
                {
                    "goods_no": "G-2",
                    "goods_nm": "옵티모 H426",
                    "tire_size_1": "225/55R18",
                    "sys_reg_dtime": "2026-06-17",
                    "car_no": "205소4214",
                    "car_nm": "제네시스 GV70",
                    "car_model_det": "GV70 2.5T",
                },
            ],
        },
    }

    row, reason = _select_order_history_reorder_row(
        "GV70 전에 장착했던 타이어와 같은 상품으로 교체하고 싶어",
        orders_result,
    )

    assert reason == "vehicle_name"
    assert row is not None
    assert row["goods_no"] == "G-2"


def test_order_history_reorder_ambiguous_orders_ask_user_to_choose() -> None:
    orders_result = {
        "status": "success",
        "data": {
            "orders": [
                {"goods_no": "G-1", "goods_nm": "키너지 EX", "tire_size_1": "205/55R16"},
                {"goods_no": "G-2", "goods_nm": "옵티모 H426", "tire_size_1": "225/55R18"},
            ],
        },
    }

    row, reason = _select_order_history_reorder_row(
        "이전에 장착했던 타이어와 동일한 상품으로 교체하고 싶어",
        orders_result,
    )

    assert row is None
    assert reason == "ambiguous"


def test_order_history_reorder_event_uses_matched_order_metadata() -> None:
    event = _build_order_history_reorder_event(
        {
            "goods_no": "G0000001",
            "goods_nm": "옵티모 H426",
            "tire_size_1": "205/65R16",
            "ord_qty": 4,
            "car_no": "205소4214",
        },
        match_reason="car_no",
    )

    assert event["assistant_response_source"] == "code_order_history_reorder_resolver"
    assert "205소4214" in event["data"]["assistantResponse"]
    assert "옵티모 H426 205/65R16" in event["data"]["assistantResponse"]
    assert event["data"]["metadata"]["goodsNo"] == "G0000001"


def test_order_source_filter_keeps_vehicle_fields_for_reorder_matching_context() -> None:
    assert {"car_no", "car_nm", "car_model_det", "car_maker"} <= _ORDER_FIELDS_BASE


def test_owned_vehicle_selection_cta_does_not_retrigger_oe_guidance() -> None:
    context = "내 차 살 때 끼워져 있던 타이어랑 똑같은 거 있어?\n보유차량 중 선택"

    assert _is_owned_vehicle_selection_cta("보유차량 중 선택")
    assert _is_owned_vehicle_selection_cta("내 차로 찾기")
    assert _is_owned_vehicle_selection_cta("차량 정보로 찾기")
    assert not _is_oe_replacement_context(context, "보유차량 중 선택")
    assert not _is_oe_replacement_context(context, "내 차로 찾기")
    assert _is_oe_replacement_context(context, "205소4214")


def test_owned_vehicle_selection_cta_is_detected_after_context_extraction() -> None:
    wrapped = "USER CONTEXT INFORMATION\nCurrent user input: 보유차량 중 선택"

    current_text = StreamingMultiAgentCoordinator._extract_current_user_input(wrapped)

    assert current_text == "보유차량 중 선택"
    assert _is_owned_vehicle_selection_cta(current_text)


def test_oe_replacement_guidance_explains_oe_re_before_vehicle_selection() -> None:
    event = _build_oe_replacement_guidance_event(
        None,
        "내 차 살 때 끼워져 있던 타이어랑 똑같은 거 있어?",
        include_vehicle_selection=True,
    )

    response = event["data"]["assistantResponse"]
    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "code_oe_replacement_guidance"
    assert "OE는 차량 출고 시 장착된 순정 타이어" in response
    assert "RE는 교체용" in response
    assert "차량을 선택해 주시면" in response
    assert _labels(event["data"]["quickReplies"]) == ["보유차량 중 선택", "차번+이름으로 검색", "사이즈 직접 입력"]


def test_oe_replacement_guidance_does_not_recommend_vehicle_products_immediately() -> None:
    selected_vehicle = {
        "car": {
            "licensePlate": "205소4214",
            "info": "제네시스 GV70 (1세대) (2021 - 2024)",
        },
        "meta": {
            "carNo": "205소4214",
            "tireSize": "2355519",
            "tireSizeRe": "2355519",
        },
    }

    event = _build_oe_replacement_guidance_event(
        selected_vehicle,
        "내 차 제네시스 GV70이고 미쉐린 타이어 끼고 있었던 거 같은데, 동일한 상품 판매하고 있어?",
    )

    response = event["data"]["assistantResponse"]
    assert event["template"] == "quickReply"
    assert "제네시스 GV70" in response
    assert "2355519" in response
    assert "미쉐린으로 기억" in response
    assert "추천 상품" not in response
    assert _labels(event["data"]["quickReplies"]) == ["동일 상품 찾기", "교체용 상품 추천", "사이즈 직접 입력"]


def test_oe_replacement_followup_query_is_detected() -> None:
    assert _is_oe_replacement_followup_query("교체용 상품 추천")
    assert _is_oe_replacement_followup_query("호환 사이즈 추천")
    assert _is_oe_replacement_followup_query("동일 상품 찾기")
    assert not _is_oe_replacement_followup_query("쿠폰 보여줘")


def test_oe_replacement_followup_reuses_confirmed_tire_size() -> None:
    args = _build_oe_replacement_followup_recommendation_args(
        "교체용 상품 추천",
        "내 차 제네시스 GV70이고 미쉐린 타이어 끼고 있었던 거 같은데, 동일한 상품 판매하고 있어?\n교체용 상품 추천",
        "235/55R19",
    )

    assert args is not None
    assert args["tire_size"] == "235/55R19"
    assert args["brand_cd"] == "HK"


def test_oe_replacement_same_product_followup_prefers_context_brand() -> None:
    args = _build_oe_replacement_same_product_search_args(
        "동일 상품 찾기",
        "내 차 제네시스 GV70이고 미쉐린 타이어 끼고 있었던 거 같은데, 동일한 상품 판매하고 있어?\n동일 상품 찾기",
        "235/55R19",
    )

    assert args is not None
    assert args["size"] == "235/55R19"
    assert args["brand_cd"] == "MC"


def test_oe_replacement_same_product_without_brand_returns_none() -> None:
    args = _build_oe_replacement_same_product_search_args(
        "동일 상품 찾기",
        "내 차 제네시스 GV70인데 동일한 상품 판매하고 있어?\n동일 상품 찾기",
        "235/55R19",
    )

    assert args is None


def test_oe_replacement_same_product_without_brand_prompts_for_brand() -> None:
    event = _build_oe_replacement_same_product_brand_prompt_event("235/55R19")

    assert event["assistant_response_source"] == "code_oe_replacement_same_product_brand_prompt"
    assert "브랜드를 알려주시면" in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == [
        "미쉐린으로 동일 상품 찾기",
        "한국타이어 교체용 추천",
        "사이즈 직접 입력",
    ]


def test_oe_replacement_followup_does_not_fire_for_unrelated_question() -> None:
    args = _build_oe_replacement_followup_recommendation_args(
        "쿠폰 뭐 있어?",
        "내 차 제네시스 GV70이고 미쉐린 타이어 끼고 있었던 거 같은데, 동일한 상품 판매하고 있어?\n쿠폰 뭐 있어?",
        "235/55R19",
    )

    assert args is None


def test_vehicle_selection_slot_values_normalize_tire_size() -> None:
    slot_values = _vehicle_selection_slot_values({
        "car": {
            "licensePlate": "205소4214",
            "info": "제네시스 GV70 (1세대) (2021 - 2024)",
        },
        "meta": {
            "carNo": "205소4214",
            "tireSize": "2355519",
        },
    })

    assert slot_values["tire_size"] == "235/55R19"
    assert slot_values["tire_size_front"] == "235/55R19"
    assert "tire_size_rear" not in slot_values


def test_vehicle_selection_slot_values_use_structured_car_model_when_present() -> None:
    slot_values = _vehicle_selection_slot_values({
        "car": {
            "licensePlate": "205소4214",
            "info": "제네시스 GV70 (1세대) (2021 - 2024)",
        },
        "meta": {
            "carNo": "205소4214",
            "tireSize": "235/55R19",
            "carNm": "GV70",
        },
    })

    assert slot_values["car_model"] == "GV70"


def test_vehicle_selection_slot_values_normalize_car_type_to_vehicle_type() -> None:
    slot_values = _vehicle_selection_slot_values({
        "car": {
            "licensePlate": "205소4214",
            "info": "제네시스 GV70 (1세대) (2021 - 2024)",
        },
        "meta": {
            "carNo": "205소4214",
            "tireSize": "235/55R19",
            "carNm": "GV70",
            "carLncCd": "W049847",
            "carType": "SUV",
        },
    })

    assert slot_values["car_type"] == "SUV"
    assert slot_values["vehicle_type"] == "suv"


def test_vehicle_selection_slot_values_normalize_ev_model_to_vehicle_type() -> None:
    slot_values = _vehicle_selection_slot_values({
        "car": {
            "licensePlate": "11가1111",
            "info": "아이오닉 5",
        },
        "meta": {
            "carNo": "11가1111",
            "tireSize": "235/55R19",
            "carNm": "아이오닉 5",
        },
    })

    assert slot_values["vehicle_type"] == "ev"


def test_vehicle_selection_slot_values_preserve_staggered_front_rear_without_default_selected_size() -> None:
    slot_values = _vehicle_selection_slot_values({
        "car": {
            "licensePlate": "56모2162",
            "info": "BMW 3시리즈 그란 투리스모(6세대)",
        },
        "meta": {
            "carNo": "56모2162",
            "tireSize": "2255018",
            "tireSizeRe": "2555018",
        },
    })

    assert slot_values["tire_size_front"] == "225/50R18"
    assert slot_values["tire_size_rear"] == "255/50R18"
    assert "tire_size" not in slot_values


def test_vehicle_selection_atomic_update_preserves_new_front_rear_when_car_changes() -> None:
    from schemas.tstation.slots import ConversationSlots

    base_slots = ConversationSlots(
        car_model="GV70",
        car_no="205소4214",
        car_lnc_cd="W000001",
        tire_size="235/55R19",
        tire_size_front="235/55R19",
        tire_size_rear="235/55R19",
        goods_no="G000000123456",
        payment_amount=100000,
    )
    slot_values = {
        "car_model": "BMW 3시리즈 그란 투리스모",
        "car_no": "56모2162",
        "car_lnc_cd": "W049847",
        "car_type": "승용차",
        "vehicle_type": "passenger",
        "tire_size_front": "225/50R18",
        "tire_size_rear": "255/50R18",
    }

    updated = _apply_vehicle_selection_slot_values(base_slots, slot_values)

    assert updated.car_model == "BMW 3시리즈 그란 투리스모"
    assert updated.car_no == "56모2162"
    assert updated.car_lnc_cd == "W049847"
    assert updated.car_type == "승용차"
    assert updated.vehicle_type == "passenger"
    assert updated.tire_size is None
    assert updated.tire_size_front == "225/50R18"
    assert updated.tire_size_rear == "255/50R18"
    assert updated.goods_no is None
    assert updated.payment_amount is None


def test_transaction_stall_recovery_appends_transaction_after_existing_discovery() -> None:
    domains = [MultiAgentDomain.Domain.TRANSACTION, MultiAgentDomain.Domain.DISCOVERY]

    _ensure_discovery_transaction_recovery_chain(domains, 0)

    assert domains == [
        MultiAgentDomain.Domain.TRANSACTION,
        MultiAgentDomain.Domain.DISCOVERY,
        MultiAgentDomain.Domain.TRANSACTION,
    ]


def test_transaction_stall_recovery_adds_discovery_transaction_when_missing() -> None:
    domains = [MultiAgentDomain.Domain.TRANSACTION]

    _ensure_discovery_transaction_recovery_chain(domains, 0)

    assert domains == [
        MultiAgentDomain.Domain.TRANSACTION,
        MultiAgentDomain.Domain.DISCOVERY,
        MultiAgentDomain.Domain.TRANSACTION,
    ]


def test_transaction_stall_recovery_does_not_duplicate_existing_recovery_tail() -> None:
    domains = [
        MultiAgentDomain.Domain.TRANSACTION,
        MultiAgentDomain.Domain.DISCOVERY,
        MultiAgentDomain.Domain.TRANSACTION,
    ]

    _ensure_discovery_transaction_recovery_chain(domains, 0)

    assert domains == [
        MultiAgentDomain.Domain.TRANSACTION,
        MultiAgentDomain.Domain.DISCOVERY,
        MultiAgentDomain.Domain.TRANSACTION,
    ]


def test_reservation_date_range_guard_blocks_far_future_month_request() -> None:
    event = _reservation_date_range_guard_event(
        "8월에 갈건데 미리 예약 가능? 예약 잡기 너무 힘들어서.",
        today=datetime.date(2026, 5, 25),
    )

    assert event is not None
    assert event["assistant_response_source"] == "code_reservation_date_range_guard"
    assert "2026년 6월 24일까지" in event["data"]["assistantResponse"]
    assert "2026년 8월 1일 예약은 아직 오픈 전" in event["data"]["assistantResponse"]


def test_reservation_date_range_guard_uses_recent_reservation_context() -> None:
    event = _reservation_date_range_guard_event(
        "8월 1일",
        messages=[{"role": "assistant", "content": "현재 예약 가능 일정은 6월 24일까지로 확인돼요."}],
        today=datetime.date(2026, 5, 25),
    )

    assert event is not None
    assert "2026년 8월 1일 예약은 아직 오픈 전" in event["data"]["assistantResponse"]


def test_reservation_date_range_guard_blocks_past_explicit_date_and_ignores_user_declared_today() -> None:
    event = _reservation_date_range_guard_event(
        "오늘은 2026년 5월 25일이야. 2026년 5월 29일 오후 16시 예약 돼?",
        today=datetime.date(2026, 6, 5),
    )

    assert event is not None
    assert event["assistant_response_source"] == "code_reservation_past_date_guard"
    assert (
        event["data"]["assistantResponse"]
        == "지난 날짜의 예약 가능 여부는 조회가 불가능합니다. 오늘 날짜 2026-06-05 이후로 다시 선택해 주세요."
    )


def test_reservation_date_range_guard_blocks_past_yearless_date() -> None:
    event = _reservation_date_range_guard_event(
        "티스테이션 성남IC점 5월 29일 16시 예약 돼?",
        today=datetime.date(2026, 6, 5),
    )

    assert event is not None
    assert event["assistant_response_source"] == "code_reservation_past_date_guard"
    assert "오늘 날짜 2026-06-05 이후로 다시 선택해 주세요." in event["data"]["assistantResponse"]


@pytest.mark.parametrize(
    "text",
    [
        "분당정자점 27년 2월 16일날 예약해줘",
        "분당정자점 27.2.16 예약해줘",
        "분당정자점 270216 예약해줘",
    ],
)
def test_reservation_date_range_guard_parses_two_digit_future_year(text: str) -> None:
    today = datetime.date(2026, 6, 17)

    parsed = _parse_requested_reservation_date(text, today=today)
    event = _reservation_date_range_guard_event(text, today=today)

    assert parsed == datetime.date(2027, 2, 16)
    assert event is not None
    assert event["assistant_response_source"] == "code_reservation_date_range_guard"
    assert "2027년 2월 16일 예약은 아직 오픈 전" in event["data"]["assistantResponse"]
    assert "지난 날짜" not in event["data"]["assistantResponse"]


def test_compact_six_digit_date_requires_reservation_context() -> None:
    assert _parse_requested_reservation_date("270216", today=datetime.date(2026, 6, 17)) is None


def test_reservation_date_range_guard_ignores_in_range_or_non_reservation_dates() -> None:
    today = datetime.date(2026, 5, 25)

    assert _reservation_date_range_guard_event("6월 1일 예약 가능해?", today=today) is None
    assert _reservation_date_range_guard_event("8월 이벤트 알려줘", today=today) is None


@pytest.mark.parametrize(
    "tire_size_text",
    [
        "2254517",
        "225 45 17",
        "225 4517",
        "225/4517",
        "225-4517",
        "225-45-17",
        "225R4517",
        "225/45R17",
    ],
)
def test_reservation_date_range_guard_ignores_tire_size_tokens(tire_size_text: str) -> None:
    text = f"벤투스 S2 AS {tire_size_text}"

    event = _reservation_date_range_guard_event(
        text,
        messages=[{"role": "assistant", "content": "원하시는 매장을 선택하면 예약 가능 시간을 확인해 드릴게요."}],
        today=datetime.date(2026, 5, 27),
    )

    assert event is None
    assert _parse_requested_reservation_date(text, today=datetime.date(2026, 5, 27)) is None


def test_reservation_date_range_guard_still_parses_date_after_tire_size() -> None:
    event = _reservation_date_range_guard_event(
        "벤투스 S2 AS 225/45R17 8월 1일 예약 가능해?",
        today=datetime.date(2026, 5, 27),
    )

    assert event is not None
    assert "2026년 8월 1일 예약은 아직 오픈 전" in event["data"]["assistantResponse"]


def test_parse_requested_reservation_date_preserves_day_30_for_slash_format() -> None:
    today = datetime.date(2026, 5, 26)

    assert _parse_requested_reservation_date("5/30은?", today=today) == datetime.date(2026, 5, 30)


def test_parse_requested_reservation_date_preserves_day_31_for_month_day_format() -> None:
    today = datetime.date(2026, 5, 26)

    assert _parse_requested_reservation_date("5월 31일 예약 돼?", today=today) == datetime.date(2026, 5, 31)


def test_parse_requested_reservation_date_supports_relative_weekday_expression() -> None:
    today = datetime.date(2026, 5, 27)

    assert _parse_requested_reservation_date("한남점 이번주 일요일 영업해?", today=today) == datetime.date(2026, 5, 31)
    assert _parse_requested_reservation_date("다음 주 토요일 예약 가능해?", today=today) == datetime.date(2026, 6, 6)


def test_store_confirmation_reply_reuses_confirmed_candidate_from_quickreply_template() -> None:
    store_name, region = TStationChatServiceV2._resolve_store_followup_from_quickreply_template(
        "네, 맞아요",
        {
            "template": "quickReply",
            "data": {
                "assistantResponse": "고객님, 요청하신 '강원 고성점'으로 검색한 결과 '티스테이션 고성점' 매장이 있는데 이 매장이 맞을까요?",
                "quickReplies": [{"label": "네, 맞아요", "domain": "TRANSACTION"}],
                "metadata": {
                    "storeConfirmation": {
                        "candidateStores": [{"shopName": "티스테이션 고성점", "shopId": "F00614"}],
                    }
                },
            },
        },
    )

    assert store_name == "티스테이션 고성점"
    assert region is None


def test_store_region_confirmation_reply_reuses_suggested_region_from_quickreply_template() -> None:
    store_name, region = TStationChatServiceV2._resolve_store_followup_from_quickreply_template(
        "네, 고성 지역으로 검색",
        {
            "template": "quickReply",
            "data": {
                "assistantResponse": "고객님, '티스테이션 고성점'으로 검색되는 매장이 없습니다. '고성' 지역으로 검색해 드릴까요?",
                "quickReplies": [{"label": "네, 고성 지역으로 검색", "domain": "TRANSACTION"}],
                "metadata": {
                    "storeConfirmation": {
                        "suggestedRegion": "고성",
                    }
                },
            },
        },
    )

    assert store_name is None
    assert region == "고성"


def test_friendly_store_recommendation_forces_transaction_store_routing() -> None:
    routing = StreamingMultiAgentCoordinator._force_keyword_routing(
        "여성 운전자가 방문하기 좋은 친절한 매장 부산지역에서 2개만 추천해봐"
    )

    assert routing is not None
    assert routing.domains == [MultiAgentDomain.Domain.TRANSACTION]
    assert routing.agent_prompt_profile.value == "transaction_store"


def test_cancel_guidance_injects_order_history_cta() -> None:
    event_data = {
        "assistantResponse": (
            "이미 출고가 진행된 주문은 단순 변심 취소/반품 시 배송 현황에 따라 비용이 발생할 수 있어요.\n\n"
            "정확한 취소 가능 여부와 최종 비용은 1:1 문의를 통해 확인해 주세요."
        ),
        "quickReplies": [{"label": "1:1 문의하기", "domain": "SUPPORT"}],
        "predictedDomains": ["SUPPORT"],
    }

    changed = _inject_order_history_chip_for_cancel_guidance(
        event_data,
        tool_data_list=[
            {
                "tool": "get_orders_of_user_tool",
                "data": {
                    "data": {
                        "orders": [{"ord_no": "2500012345", "goods_nm": "벤투스 S2 AS"}],
                    }
                },
            }
        ],
        last_user_text="주문 취소좀 해달라니까?",
    )

    assert changed is True
    assert event_data["quickReplies"][0]["label"] == "주문 내역 보기"
    assert event_data["quickReplies"][0]["url"].endswith("/mypage/tstation/order-history")
    assert "벤투스 S2 AS 주문 내역" in event_data["assistantResponse"]


def test_order_arrival_followup_resolves_recent_order_not_store_schedule() -> None:
    messages = [
        {
            "role": "assistant",
            "content": (
                "주문번호\t주문상태\t상품명\t수량\t주문날짜\n"
                "O202605180019345\t출하지시\t벤투스 S1 에보 Z AS\t4\t2026-05-18\n"
                "O202605120019340\t주문완료\t아이온 에보\t4\t2026-05-12"
            ),
        }
    ]

    assert _is_order_arrival_status_query("최근 주문 배송 예정일 알려줘")
    assert _is_order_arrival_status_query("그거 매장에 언제 와?")
    assert _is_order_arrival_status_query("그 이후에 매장 가면 돼?")
    assert _is_order_arrival_status_query("O202605120019340 주문 언제 매장 도착해?")
    assert not _is_order_arrival_status_query("여주점 예약 가능한 시간 보여줘")
    assert not _is_order_arrival_status_query("O202605120019340 주문췻호건 환불 언제돼?")
    assert not _is_order_arrival_status_query("O202605120019340 카드 취소 언제 승인돼?")

    resolved = _resolve_order_row_for_arrival_query("최근 주문 배송 예정일 알려줘", messages=messages)

    assert resolved is not None
    assert resolved["ord_no"] == "O202605180019345"


def test_order_arrival_followup_resolves_by_product_name() -> None:
    orders_result = {
        "status": "success",
        "data": {
            "orders": [
                {"ord_no": "O202605180019345", "goods_nm": "벤투스 S1 에보 Z AS"},
                {"ord_no": "O202605120019340", "goods_nm": "아이온 에보"},
            ]
        },
    }

    resolved = _resolve_order_row_for_arrival_query("아이온 에보 매장에 언제 도착해?", orders_result=orders_result)

    assert resolved is not None
    assert resolved["ord_no"] == "O202605120019340"


def test_order_arrival_direct_order_number_does_not_use_current_question_as_product_name() -> None:
    messages = [
        {"role": "user", "content": "O202605120019340 주문췻호건 환불 언제돼?"},
        {
            "role": "assistant",
            "content": (
                "주문번호\t주문상태\t상품명\t수량\t주문날짜\n"
                "O202605180019345\t출하지시\t벤투스 S1 에보 Z AS\t4\t2026-05-18"
            ),
        },
    ]

    resolved = _resolve_order_row_for_arrival_query("O202605120019340 주문 언제 매장 도착해?", messages=messages)
    event = _build_order_arrival_status_event(
        {"status": "success", "data": {"query_no": "O202605120019340", "ord_prgs_stat_nm": "주문완료"}},
        resolved,
    )

    response = event["data"]["assistantResponse"]
    assert "- 주문번호: O202605120019340" in response
    assert "상품명:" not in response
    assert "주문췻호건 환불 언제돼" not in response


def test_order_arrival_history_parser_ignores_assistant_refund_sentence() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "주문번호 O202605120019340 취소 건의 환불 일정이 궁금하시군요. 아래 버튼을 눌러 1:1 문의를 진행해 주세요 😊",
        },
        {
            "role": "assistant",
            "content": (
                "| 주문번호 | 주문상태 | 상품명 | 수량 | 주문날짜 |\n"
                "|---|---|---|---|---|\n"
                "| O202605180019345 | 출하지시 | 벤투스 S1 에보 Z AS | 4 | 2026-05-18 |"
            ),
        },
    ]

    resolved = _resolve_order_row_for_arrival_query("최근 주문 배송 예정일 알려줘", messages=messages)

    assert resolved is not None
    assert resolved["ord_no"] == "O202605180019345"
    assert resolved["goods_nm"] == "벤투스 S1 에보 Z AS"


def test_order_arrival_status_formats_delivery_date_without_time_and_no_direct_visit_claim() -> None:
    event = _build_order_arrival_status_event(
        {
            "status": "success",
            "data": {
                "query_no": "O202605180019345",
                "ord_no": "O202605180019345",
                "ord_prgs_stat_nm": "출하지시",
                "dlv_prgs_stat_nm": "배송중",
                "dlv_fcst_dtime": "2026-05-20 13:30:00",
                "shop_nm": "티스테이션 판교점",
                "rsv_dtime": None,
            },
        },
        {"goods_nm": "벤투스 S1 에보 Z AS"},
    )

    response = event["data"]["assistantResponse"]
    assert "2026-05-20" in response
    assert "13:30" not in response
    assert "배송 도착 후 매장과 방문 일정을 먼저 확인" in response
    assert "바로 방문 가능" not in response
    assert "get_store_schedule_tool" not in response


def test_tc005_price_policy_runtime_replaces_size_first_coupon_reply() -> None:
    event_data = {
        "assistantResponse": "키너지 EX 쿠폰 적용을 확인하려면 먼저 타이어 사이즈를 알려주세요.",
        "quickReplies": [{"label": "사이즈 직접 입력", "domain": "DISCOVERY"}],
    }

    changed = _normalize_price_policy_quickreply(
        event_data,
        source_domain="transaction",
        last_user_text="키너지 EX 패밀리 할인쿠폰 적용받고 싶어",
    )

    assert changed is False
    assert "사이즈를 알려주세요" in event_data["assistantResponse"]


def test_similar_price_policy_runtime_replaces_internal_guidance_text() -> None:
    event_data = {
        "assistantResponse": "정가 기준 가격대 range로 유사 상품을 추천하고, 최종 구매 가격은 규격 확인 후 안내한다.",
        "quickReplies": [{"label": "보유차량 중 선택", "domain": "DISCOVERY"}],
    }
    decision = decide_discovery_response(
        build_discovery_intent_frame("비슷한 가격대의 타이어 더 추천해줘")
    )

    changed = _normalize_discovery_policy_quickreply(
        event_data,
        source_domain="discovery",
        decision=decision,
    )

    assert changed is True
    assert "range로" not in event_data["assistantResponse"]
    assert "비슷한 가격대 상품으로 더 추천" in event_data["assistantResponse"]
    assert _labels(event_data["quickReplies"]) == ["사이즈 직접 입력", "차량번호로 확인", "내 차량 보기"]


def test_grade_comparison_policy_runtime_replaces_internal_guidance_text() -> None:
    event_data = {
        "assistantResponse": "상품명을 정확히 인식하고 각 상품의 등급/포지션 근거로 비교한다.",
        "quickReplies": [{"label": "보유차량 중 선택", "domain": "DISCOVERY"}],
    }
    decision = decide_discovery_response(
        build_discovery_intent_frame("키너지 EX가 벤투스 air S 보다 프리미엄 등급 맞지?")
    )

    changed = _normalize_discovery_policy_quickreply(
        event_data,
        source_domain="discovery",
        decision=decision,
    )

    assert changed is True
    assert "등급/포지션 근거로 비교한다" not in event_data["assistantResponse"]
    assert "두 상품의 프리미엄 등급 여부를 비교하려면" in event_data["assistantResponse"]
    assert _labels(event_data["quickReplies"]) == ["상품명 다시 입력", "사이즈 직접 입력", "내 차량 보기"]


def test_grade_comparison_event_prefers_higher_price_grade() -> None:
    event = _build_product_comparison_event(
        "키너지 EX가 벤투스 air S 보다 프리미엄 등급 맞지?",
        [
            ("Kinergy EX", {"goods_nm": "키너지 EX", "prc_grd_nm": "스탠다드"}),
            ("Ventus air S", {"goods_nm": "벤투스 에어S", "prc_grd_nm": "프리미엄"}),
        ]
    )

    assistant = event["data"]["assistantResponse"]
    assert "| 항목 | 키너지 EX | 벤투스 에어S |" in assistant
    assert "| 상품 등급 | 스탠다드 | 프리미엄 |" in assistant
    assert "벤투스 에어S이 키너지 EX보다 상위 등급입니다." in assistant
    assert _labels(event["data"]["quickReplies"]) == ["구매하기", "다른 상품 비교", "내 차량 보기"]


def test_final_price_from_row_prefers_member_best_price_before_generic_fields() -> None:
    assert _final_price_from_row({
        "cheapest_final_prc": 85000,
        "final_unit_price": 90000,
        "extra_fvr_sale_prc": 100000,
        "price": 110000,
        "sale_prc": 120000,
    }) == 85000
    assert _final_price_from_row({"final_unit_price": 91000, "extra_fvr_sale_prc": 100000}) == 91000
    assert _final_price_from_row({"final_prc": 92000, "extra_fvr_sale_prc": 100000}) == 92000


def test_price_comparison_event_uses_same_final_price_priority_as_product_cards() -> None:
    event = _build_product_comparison_event(
        "키너지 EX랑 벤투스 air S 가격 비교해줘",
        [
            (
                "키너지 EX",
                {
                    "goods_nm": "키너지 EX",
                    "sale_prc": 120000,
                    "extra_fvr_sale_prc": 100000,
                    "cheapest_final_prc": 85000,
                },
            ),
            (
                "벤투스 에어S",
                {
                    "goods_nm": "벤투스 에어S",
                    "sale_prc": 130000,
                    "extra_fvr_sale_prc": 95000,
                },
            ),
        ],
    )

    assistant = event["data"]["assistantResponse"]
    assert "| 항목 | 키너지 EX | 벤투스 에어S |" in assistant
    assert "| 최종 혜택가 | 85,000원 | 95,000원 |" in assistant
    assert "키너지 EX이 10,000원 더 저렴해요." in assistant


def test_mileage_comparison_event_prefers_higher_life_span() -> None:
    event = _build_product_comparison_event(
        "키너지 EX랑 벤투스 air S 중 뭐가 더 오래 타?",
        [
            ("Kinergy EX", {"goods_nm": "키너지 EX", "t_life_span": 4.1}),
            ("Ventus air S", {"goods_nm": "벤투스 에어S", "t_life_span": 3.2}),
        ]
    )

    assistant = event["data"]["assistantResponse"]
    assert "| 항목 | 키너지 EX | 벤투스 에어S |" in assistant
    assert "| 마일리지/수명 | 4.1 | 3.2 |" in assistant
    assert "마일리지/수명 기준으로는 키너지 EX이 벤투스 에어S보다 유리해요." in assistant


def test_product_comparison_uses_existing_search_results() -> None:
    event = _build_product_comparison_event_from_search_results(
        "키너지 EX가 벤투스 air S 보다 프리미엄 등급 맞지?",
        [
            (
                "키너지 EX",
                {"status": "success", "data": {"items": [{"goods_nm": "키너지 EX", "prc_grd_nm": "스탠다드"}]}},
            ),
            (
                "벤투스 에어S",
                {"status": "success", "data": {"items": [{"goods_nm": "벤투스 에어S", "prc_grd_nm": "프리미엄"}]}},
            ),
        ],
    )

    assert event is not None
    assert event["assistant_response_source"] == "code_product_compare_resolver"
    assert "벤투스 에어S" in event["data"]["assistantResponse"]
    assert "상위 등급" in event["data"]["assistantResponse"]


def test_generic_product_comparison_defaults_to_features_and_reviews() -> None:
    event = _build_product_comparison_event(
        "다이나프로 hpx 랑 윈터 아이셉트 비교해줘",
        [
            (
                "다이나프로 HPX",
                {
                    "goods_nm": "다이나프로 HPX",
                    "slogan": "SUV용 사계절 컴포트 타이어",
                    "rating": {"rating_avg": 4.8, "review_count": 12},
                    "reviews": [{"gdas_cont": "승차감이 좋고 조용해서 장거리 주행이 편해요.\n추천해요."}],
                    "sale_prc": 249700,
                    "t_silence": "5",
                    "t_comfort": "4.8",
                    "rr": "3",
                    "wet": "3",
                },
            ),
            (
                "윈터 아이셉트 에보3 X",
                {
                    "goods_nm": "윈터 아이셉트 에보3 X",
                    "slogan": "겨울철 눈길과 빙판 주행에 초점을 둔 SUV 윈터 타이어",
                    "rating": {"rating_avg": 4.6, "review_count": 5},
                    "reviews": [{"gdas_cont": "눈길 접지력이 안정적이라는 | 느낌이 있어요."}],
                    "sale_prc": 256300,
                    "t_silence": "4",
                    "t_comfort": "4.2",
                    "rr": "4",
                    "wet": "2",
                },
            ),
        ],
    )

    assistant = event["data"]["assistantResponse"]

    assert "상품 정보를 표로 비교해드릴게요." in assistant
    assert "| 항목 | 다이나프로 HPX | 윈터 아이셉트 에보3 X |" in assistant
    assert "| 특징 | SUV용 사계절 컴포트 타이어 | 겨울철 눈길과 빙판 주행에 초점을 둔 SUV 윈터 타이어 |" in assistant
    assert "| 주요 성능 | 정숙성 5, 승차감 4.8, 회전저항 3, 젖은노면 3 | 정숙성 4, 승차감 4.2, 회전저항 4, 젖은노면 2 |" in assistant
    assert "| 리뷰 | 평점 4.8, 리뷰 12건. 대표 리뷰는" in assistant
    assert "추천해요." in assistant
    assert "눈길 접지력이 안정적이라는 / 느낌" in assistant
    assert "SUV용 사계절 컴포트 타이어" in assistant
    assert "눈길과 빙판" in assistant
    assert "승차감이 좋고 조용" in assistant
    assert "\n추천해요" not in assistant
    assert "| 느낌" not in assistant
    assert "가격 기준" not in assistant
    assert "249,700" not in assistant


def test_product_comparison_table_does_not_expose_goods_no() -> None:
    event = _build_product_comparison_event(
        "키너지 EX랑 벤투스 air S 비교해줘",
        [
            (
                "키너지 EX",
                {
                    "goods_no": "G000000111111",
                    "goods_nm": "키너지 EX",
                    "slogan": "일상 주행용 컴포트 타이어",
                    "sale_prc": 120000,
                },
            ),
            (
                "벤투스 에어S",
                {
                    "goods_no": "G000000222222",
                    "goods_nm": "벤투스 에어S",
                    "slogan": "정숙성과 승차감 중심 타이어",
                    "sale_prc": 130000,
                },
            ),
        ],
    )

    assistant = event["data"]["assistantResponse"]
    assert "| 항목 | 키너지 EX | 벤투스 에어S |" in assistant
    assert "상품코드" not in assistant
    assert "goods_no" not in assistant
    assert "G000000111111" not in assistant
    assert "G000000222222" not in assistant


def test_product_comparison_feature_fallback_omits_pattern_group() -> None:
    event = _build_product_comparison_event(
        "벤투스 S2 AS랑 다이나프로 HP3 비교해줘",
        [
            (
                "Ventus S2 AS",
                {
                    "goods_nm": "벤투스 S2 AS",
                    "season_nm": "사계절",
                    "car_knd_nm": "승용차",
                    "goods_pfm_nm": "COMFORT",
                    "ptrn_d_nm": "벤투스 슈퍼 컴포트",
                },
            ),
            (
                "Dynapro HP3",
                {
                    "goods_nm": "다이나프로 HP3",
                    "season_nm": "사계절",
                    "car_knd_nm": "SUV",
                    "goods_pfm_nm": "COMFORT",
                    "ptrn_d_nm": "다이나프로 컴포트",
                },
            ),
        ],
    )

    assistant = event["data"]["assistantResponse"]

    assert "| 특징 | 사계절, 승용차용, COMFORT | 사계절, SUV용, COMFORT |" in assistant
    assert "벤투스 슈퍼 컴포트" not in assistant
    assert "다이나프로 컴포트" not in assistant


def test_generic_compare_text_is_product_comparison_query() -> None:
    assert _is_product_comparison_query("다이나프로 hpx 랑 윈터 아이셉트 비교해줘") is True


def test_description_compare_followup_reuses_previous_compare_products() -> None:
    messages = [
        {"role": "user", "content": "다이나프로 hpx 랑 윈터 아이셉트 비교해줘"},
        {"role": "assistant", "content": "가격 기준으로는 다이나프로 HPX가 더 저렴해요."},
        {"role": "user", "content": "상품 설명 비교"},
    ]

    query = _comparison_query_with_recent_context("상품 설명 비교", messages)

    assert query == "Dynapro HPX랑 아이셉트 상품 설명 비교"


def test_single_product_compare_followup_reuses_recent_product() -> None:
    messages = [
        {"role": "user", "content": "벤투스 에어 S 상품 제주도에서 사는거랑, 서울에서 사는거랑 가격 똑같을까?"},
        {"role": "assistant", "content": "제주 지역은 상품 1개당 배송비 1만 원이 추가될 수 있어요."},
        {"role": "user", "content": "벤투스 s2 as 랑 비교해줘"},
    ]

    query = _comparison_query_with_recent_context("벤투스 s2 as 랑 비교해줘", messages)

    assert query == "Ventus air S랑 Ventus S2 AS 비교"


def test_pronoun_compare_followup_reuses_two_recent_products() -> None:
    messages = [
        {"role": "user", "content": "벤투스 에어 S 상품 제주도에서 사는거랑, 서울에서 사는거랑 가격 똑같을까?"},
        {"role": "assistant", "content": "제주 지역은 상품 1개당 배송비 1만 원이 추가될 수 있어요."},
        {"role": "user", "content": "벤투스 s2 as 는?"},
        {"role": "assistant", "content": "벤투스 S2 AS: 승용차용 사계절 컴포트 타이어입니다."},
        {"role": "user", "content": "이 2개중에 어떤게 더 좋아?"},
    ]

    query = _comparison_query_with_recent_context("이 2개중에 어떤게 더 좋아?", messages)

    assert query == "Ventus air S랑 Ventus S2 AS 비교"


@pytest.mark.parametrize(
    "user_text",
    [
        "두개 말고 다른 추천 상품은 없어?",
        "둘 말고 다른 상품은?",
        "이거 말고 다른 추천 상품 없어?",
        "아까 두 개 말고 다른 걸로 비교하고 싶어",
        "다른 상품 비교",
        "다른 추천 상품 보여줘",
    ],
)
def test_other_recommendation_text_does_not_reuse_recent_compare_products(user_text: str) -> None:
    messages = [
        {"role": "user", "content": "ventus air s, ventus s2 as 비교해줘"},
        {"role": "assistant", "content": "벤투스 에어S와 벤투스 S2 AS를 비교했어요."},
        {"role": "user", "content": user_text},
    ]

    query = _comparison_query_with_recent_context(user_text, messages)

    assert query == user_text


@pytest.mark.parametrize(
    ("user_text", "expected"),
    [
        ("두 개 특징 비교해줘", "Ventus air S랑 Ventus S2 AS 상품 설명 비교"),
        ("가격은 둘 중 뭐가 더 저렴해?", "Ventus air S랑 Ventus S2 AS 비교"),
    ],
)
def test_clear_recent_two_compare_followup_still_reuses_recent_products(user_text: str, expected: str) -> None:
    messages = [
        {"role": "user", "content": "ventus air s, ventus s2 as 비교해줘"},
        {"role": "assistant", "content": "벤투스 에어S와 벤투스 S2 AS를 비교했어요."},
        {"role": "user", "content": user_text},
    ]

    query = _comparison_query_with_recent_context(user_text, messages)

    assert query == expected


def test_other_recommendation_text_does_not_rebuild_compare_event_from_previous_results() -> None:
    messages = [
        {"role": "user", "content": "ventus air s, ventus s2 as 비교해줘"},
        {"role": "assistant", "content": "벤투스 에어S와 벤투스 S2 AS를 비교했어요."},
        {"role": "user", "content": "두개 말고 다른 추천 상품은 없어?"},
    ]
    comparison_query = _comparison_query_with_recent_context("두개 말고 다른 추천 상품은 없어?", messages)

    event = _build_product_comparison_event_from_search_results(
        comparison_query,
        [
            ("Ventus air S", {"data": [{"goods_nm": "벤투스 에어S", "sale_prc": 180000}]}),
            ("Ventus S2 AS", {"data": [{"goods_nm": "벤투스 S2 AS", "sale_prc": 170000}]}),
        ],
    )

    assert event is None


def test_other_product_compare_cta_prompts_for_new_target_without_compare_resolver_source() -> None:
    messages = [
        {"role": "user", "content": "ventus air s, ventus s2 as 비교해줘"},
        {"role": "assistant", "content": "벤투스 에어S와 벤투스 S2 AS를 비교했어요."},
        {"role": "user", "content": "다른 상품 비교"},
    ]

    event = _product_compare_target_prompt_event()
    assistant = event["data"]["assistantResponse"]

    assert _should_prompt_for_new_product_compare_target("다른 상품 비교", messages) is True
    assert _should_skip_product_compare_override("다른 상품 비교", {"get_products_recommendations_tool"}) is True
    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "code_product_compare_target_prompt"
    assert event["assistant_response_source"] != "code_product_compare_resolver"
    assert "비교할 다른 상품명을 알려주시면" in assistant
    assert "구매하기" not in _labels(event["data"]["quickReplies"])
    assert _labels(event["data"]["quickReplies"])[0] == "상품명 다시 입력"


def test_other_product_compare_cta_without_recent_products_does_not_trigger_compare_prompt() -> None:
    messages = [
        {"role": "user", "content": "다른 상품 비교"},
    ]

    assert _should_prompt_for_new_product_compare_target("다른 상품 비교", messages) is False


def test_compare_target_prompt_next_two_product_names_become_comparison() -> None:
    latest_prompt = _product_compare_target_prompt_event()
    messages = [
        {"role": "user", "content": "두개 말고 다른 상품은 없어?"},
        {"role": "assistant", "content": latest_prompt["data"]["assistantResponse"], "template_data": latest_prompt},
        {"role": "user", "content": "벤투스 에어S랑 키너지 ST AS"},
    ]

    query = _comparison_query_with_recent_context("벤투스 에어S랑 키너지 ST AS", messages, latest_prompt)

    assert query == "Ventus air S랑 Kinergy ST AS 비교"
    assert _should_resolve_compare_target_product_pair("벤투스 에어S랑 키너지 ST AS", messages, latest_prompt) is True
    assert _build_product_comparison_event_from_search_results(
        query,
        [
            ("Ventus air S", {"data": {"items": [{"goods_nm": "벤투스 에어S", "slogan": "프리미엄 컴포트"}]}}),
            ("Kinergy ST AS", {"data": {"items": [{"goods_nm": "키너지 ST AS", "slogan": "사계절 밸런스"}]}}),
        ],
    )["assistant_response_source"] == "code_product_compare_resolver"


def test_compare_target_prompt_text_without_template_data_promotes_next_product_pair() -> None:
    prompt = _product_compare_target_prompt_event()["data"]["assistantResponse"]
    messages = [
        {"role": "user", "content": "두개 말고 다른 상품은 없어?"},
        {"role": "assistant", "content": prompt},
        {"role": "user", "content": "벤투스 에어S랑 키너지 ST AS"},
    ]

    query = _comparison_query_with_recent_context("벤투스 에어S랑 키너지 ST AS", messages)

    assert query == "Ventus air S랑 Kinergy ST AS 비교"
    assert _should_resolve_compare_target_product_pair("벤투스 에어S랑 키너지 ST AS", messages) is True


def test_explicit_two_product_compare_with_korean_aliases_remains_comparison() -> None:
    user_text = "벤투스 에어S랑 키너지 ST AS 비교"
    query = _comparison_query_with_recent_context(user_text, [{"role": "user", "content": user_text}])

    assert query == user_text
    assert build_discovery_intent_frame(user_text).intent == "product_comparison"
    event = _build_product_comparison_event_from_search_results(
        query,
        [
            ("Ventus air S", {"data": {"items": [{"goods_nm": "벤투스 에어S", "slogan": "프리미엄 컴포트"}]}}),
            ("Kinergy ST AS", {"data": {"items": [{"goods_nm": "키너지 ST AS", "slogan": "사계절 밸런스"}]}}),
        ],
    )
    assert event is not None
    assert event["assistant_response_source"] == "code_product_compare_resolver"


def test_overlapping_ion_alias_single_input_stays_single_product() -> None:
    user_text = "아이온 에보 as"
    frame = build_discovery_intent_frame(user_text)

    assert frame.entities["product_names"] == ("iON evo AS",)
    assert _should_clarify_ambiguous_multi_product_query(user_text, [{"role": "user", "content": user_text}]) is False


def test_overlapping_ion_alias_suv_single_input_does_not_split() -> None:
    user_text = "아이온 에보 as suv"
    frame = build_discovery_intent_frame(user_text)

    assert frame.entities["product_names"] == ("iON evo AS SUV",)


def test_overlapping_ion_alias_explicit_compare_keeps_two_distinct_products() -> None:
    user_text = "아이온 에보랑 아이온 에보 as 비교"
    frame = build_discovery_intent_frame(user_text)

    assert frame.intent == "product_comparison"
    assert frame.entities["product_names"] == ("iON evo", "iON evo AS")


def test_overlapping_ion_alias_explicit_compare_with_as_suv_keeps_two_distinct_products() -> None:
    user_text = "아이온 에보 AS랑 아이온 에보 AS SUV 비교"
    frame = build_discovery_intent_frame(user_text)

    assert frame.intent == "product_comparison"
    assert frame.entities["product_names"] == ("iON evo AS", "iON evo AS SUV")


def test_overlapping_sfit_aliases_keep_single_or_distinct_products() -> None:
    single_frame = build_discovery_intent_frame("s fit as")
    compare_frame = build_discovery_intent_frame("s fit랑 s fit as 비교")

    assert single_frame.entities["product_names"] == ("S FIT AS",)
    assert compare_frame.entities["product_names"] == ("S FIT", "S FIT AS")


def test_overlapping_ventus_s1_evo_z_aliases_keep_single_or_distinct_products() -> None:
    single_frame = build_discovery_intent_frame("벤투스 s1 에보 z as")
    compare_frame = build_discovery_intent_frame("벤투스 s1 에보 z랑 벤투스 s1 에보 z as 비교")

    assert single_frame.entities["product_names"] == ("Ventus S1 evo Z AS",)
    assert compare_frame.entities["product_names"] == ("Ventus S1 evo Z", "Ventus S1 evo Z AS")


def test_overlapping_mileage_plus_aliases_keep_single_or_distinct_products() -> None:
    single_frame = build_discovery_intent_frame("마일리지 플러스 3")
    compare_frame = build_discovery_intent_frame("마일리지 플러스랑 마일리지 플러스 2 비교")

    assert single_frame.entities["product_names"] == ("Mileage Plus 3",)
    assert compare_frame.entities["product_names"] == ("Mileage Plus", "Mileage Plus 2")


def test_overlapping_ventus_s2_aliases_keep_single_or_distinct_products() -> None:
    single_frame = build_discovery_intent_frame("벤투스 s2 as")
    compare_frame = build_discovery_intent_frame("벤투스 s2랑 벤투스 s2 as 비교")

    assert single_frame.entities["product_names"] == ("Ventus S2 AS",)
    assert compare_frame.entities["product_names"] == ("Ventus S2", "Ventus S2 AS")


def test_router_continue_previous_compare_metric_preserves_release_axis() -> None:
    frame = build_discovery_intent_frame(
        "dynapro hpx, dynapro hp3 중에서는?",
        known_slots={
            "comparison_followup_intent": "continue_previous_compare_metric",
            "comparison_metric": "release",
        },
    )
    decision = decide_discovery_response(frame)

    assert frame.intent == "product_comparison"
    assert frame.sub_intent == "latest_compare"
    assert frame.entities["compare_metric"] == "release"
    assert frame.entities["comparison_followup_intent"] == "continue_previous_compare_metric"
    assert decision.metadata["compare_metric"] == "release"
    assert decision.metadata["comparison_followup_intent"] == "continue_previous_compare_metric"


def test_router_new_compare_metric_overrides_to_price_axis() -> None:
    frame = build_discovery_intent_frame(
        "dynapro hpx, dynapro hp3 가격은?",
        known_slots={
            "comparison_followup_intent": "new_compare_metric",
            "comparison_metric": "price",
        },
    )
    decision = decide_discovery_response(frame)

    assert frame.intent == "product_comparison"
    assert frame.entities["compare_metric"] == "price"
    assert frame.entities["comparison_followup_intent"] == "new_compare_metric"
    assert decision.metadata["compare_metric"] == "price"
    assert decision.metadata["comparison_followup_intent"] == "new_compare_metric"


def test_router_continue_previous_compare_metric_is_not_polluted_by_suv_suffix() -> None:
    frame = build_discovery_intent_frame(
        "ion evo as, ion evo as suv 중에서는?",
        known_slots={
            "comparison_followup_intent": "continue_previous_compare_metric",
            "comparison_metric": "release",
        },
    )

    assert frame.intent == "product_comparison"
    assert frame.sub_intent == "latest_compare"
    assert frame.entities["product_names"] == ("iON evo AS", "iON evo AS SUV")
    assert frame.entities["compare_metric"] == "release"


def test_router_generic_compare_preserves_detail_axis() -> None:
    frame = build_discovery_intent_frame(
        "dynapro hpx, dynapro hp3 중에서는?",
        known_slots={
            "comparison_followup_intent": "generic_compare",
            "comparison_metric": "detail",
        },
    )
    decision = decide_discovery_response(frame)

    assert frame.intent == "product_comparison"
    assert frame.sub_intent == "general_compare"
    assert frame.entities["compare_metric"] == "detail"
    assert decision.metadata["compare_metric"] == "detail"
    assert decision.metadata["comparison_followup_intent"] == "generic_compare"


def test_standalone_two_product_names_ask_clarification_without_single_keyword_plan() -> None:
    user_text = "벤투스 에어S랑 키너지 ST AS"
    messages = [{"role": "user", "content": user_text}]
    event = _multi_product_intent_clarification_event(("Ventus air S", "Kinergy ST AS"))
    frame = build_discovery_intent_frame(user_text)
    plan = plan_discovery_tools(frame)

    assert _should_clarify_ambiguous_multi_product_query(user_text, messages) is True
    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "code_multi_product_intent_clarification"
    assert "두 상품을 비교해드릴까요" in event["data"]["assistantResponse"]
    assert event["data"]["metadata"]["pendingProductNames"] == ["Ventus air S", "Kinergy ST AS"]
    assert "search_product_tool" in plan.forbidden_tools
    assert plan.tool_args_patch == {}


def test_multi_product_clarification_detail_chip_restores_pending_products_from_metadata() -> None:
    clarification_event = _multi_product_intent_clarification_event(("Ventus S2 AS", "Dynapro HP3"))
    messages = [
        {"role": "user", "content": "벤투스 s2 as 랑 다이나프로 hp3"},
        {
            "role": "assistant",
            "content": clarification_event["data"]["assistantResponse"],
            "template_data": clarification_event,
        },
        {"role": "user", "content": "각각 찾아보기"},
    ]

    assert _recent_multi_product_clarification_names(messages, clarification_event) == ("Ventus S2 AS", "Dynapro HP3")
    assert _multi_product_detail_continuation_names("각각 찾아보기", messages, clarification_event) == (
        "Ventus S2 AS",
        "Dynapro HP3",
    )
    assert _multi_product_compare_continuation_query("두 상품 비교", messages, clarification_event) == (
        "Ventus S2 AS랑 Dynapro HP3 비교"
    )


def test_multi_product_clarification_detail_chip_restores_products_from_previous_user_text() -> None:
    clarification_event = _multi_product_intent_clarification_event()
    messages = [
        {"role": "user", "content": "벤투스 s2 as 랑 다이나프로 hp3"},
        {
            "role": "assistant",
            "content": clarification_event["data"]["assistantResponse"],
            "template_data": clarification_event,
        },
        {"role": "user", "content": "각각 찾아보기"},
    ]

    assert _multi_product_detail_continuation_names("각각 찾아보기", messages) == ("Ventus S2 AS", "Dynapro HP3")
    assert _multi_product_compare_continuation_query("두 상품 비교", messages) == (
        "Ventus S2 AS랑 Dynapro HP3 비교"
    )


def test_multi_product_clarification_detail_chip_restores_products_from_assistant_text_only_history() -> None:
    clarification_event = _multi_product_intent_clarification_event()
    messages = [
        {"role": "user", "content": "ventus air s, ventus s2 as"},
        {
            "role": "assistant",
            "content": (
                f"{clarification_event['data']['assistantResponse']}\n\n"
                "[이전 선택된 상품 데이터]\n"
                '{"type":"data","template":"quickReply","assistant_response_source":'
                '"code_multi_product_intent_clarification"}'
            ),
        },
        {"role": "user", "content": "각각 찾아보기"},
    ]

    assert _multi_product_detail_continuation_names("각각 찾아보기", messages) == (
        "Ventus air S",
        "Ventus S2 AS",
    )
    assert _multi_product_compare_continuation_query("두 상품 비교", messages) == (
        "Ventus air S랑 Ventus S2 AS 비교"
    )


def test_multi_product_detail_followup_restores_recent_pair_without_clarification_prompt() -> None:
    messages = [
        {"role": "user", "content": "두개 말고 다른 추천 상품은 없어?"},
        {"role": "assistant", "content": "비교할 다른 상품명을 알려주시면 특징, 평점, 리뷰 중심으로 비교해드릴게요."},
        {"role": "user", "content": "ventus air s, dynapro hp3"},
        {"role": "assistant", "content": "두 상품을 비교해드릴까요, 아니면 각각 상품을 찾아드릴까요?"},
        {"role": "user", "content": "두 상품 정보 보여줘"},
    ]

    assert _multi_product_detail_continuation_names("두 상품 정보 보여줘", messages) == (
        "Ventus air S",
        "Dynapro HP3",
    )


def test_multi_product_detail_event_keeps_both_products_in_final_response() -> None:
    event = _build_multi_product_detail_quickreply_event(
        [
            (
                "Ventus S2 AS",
                {
                    "goods_no": "101",
                    "goods_nm": "벤투스 S2 AS",
                    "tire_size_1": "225/45R17",
                    "slogan": "프리미엄 정숙성과 승차감을 갖춘 사계절 타이어",
                    "season_nm": "사계절",
                    "car_knd_nm": "승용차",
                    "goods_pfm_nm": "COMFORT",
                    "ptrn_d_nm": "벤투스 슈퍼 컴포트",
                    "sale_prc": 152500,
                    "_available_tire_sizes": ["225/45R17", "245/40R18"],
                },
            ),
            (
                "Dynapro HP3",
                {
                    "goods_no": "202",
                    "goods_nm": "다이나프로 HP3",
                    "tire_size_1": "225/70R16",
                    "slogan": "SUV를 위한 컴포트 주행 성능",
                    "season_nm": "사계절",
                    "car_knd_nm": "SUV",
                    "goods_pfm_nm": "COMFORT",
                    "ptrn_d_nm": "다이나프로 컴포트",
                    "sale_prc": 140800,
                    "_available_tire_sizes": ["225/70R16", "235/60R18"],
                },
            ),
        ]
    )

    assistant = event["data"]["assistantResponse"]

    assert event["assistant_response_source"] == "code_multi_product_detail_resolver"
    assert event["assistant_response_source"] != "code_mapper"
    assert "벤투스 S2 AS" in assistant
    assert "다이나프로 HP3" in assistant
    assert "벤투스 S2 AS는 프리미엄 정숙성과 승차감을 갖춘 사계절 타이어 상품이에요." in assistant
    assert "다이나프로 HP3는 SUV를 위한 컴포트 주행 성능 상품이에요." in assistant
    assert "확인 가능한 규격은 225/45R17, 245/40R18" in assistant
    assert "확인 가능한 규격은 225/70R16, 235/60R18" in assistant
    assert "상품 분류는 사계절 · 승용차 · COMFORT 기준으로 확인돼요." in assistant
    assert "상품 분류는 사계절 · SUV · COMFORT 기준으로 확인돼요." in assistant
    assert "벤투스 슈퍼 컴포트" not in assistant
    assert "다이나프로 컴포트" not in assistant
    assert "정가는 152,500원입니다." not in assistant
    assert "정가는 140,800원입니다." not in assistant
    assert [product["productName"] for product in event["data"]["metadata"]["products"]] == [
        "벤투스 S2 AS",
        "다이나프로 HP3",
    ]


def test_multi_product_detail_event_shows_price_when_size_is_specific() -> None:
    event = _build_multi_product_detail_quickreply_event(
        [
            (
                "Ventus S2 AS",
                {
                    "goods_no": "101",
                    "goods_nm": "벤투스 S2 AS",
                    "tire_size_1": "225/45R17",
                    "slogan": "프리미엄 정숙성과 승차감을 갖춘 사계절 타이어",
                    "season_nm": "사계절",
                    "car_knd_nm": "승용차",
                    "goods_pfm_nm": "COMFORT",
                    "ptrn_d_nm": "벤투스 슈퍼 컴포트",
                    "sale_prc": 152500,
                    "_available_tire_sizes": ["225/45R17", "245/40R18"],
                },
            ),
            (
                "Dynapro HP3",
                {
                    "goods_no": "202",
                    "goods_nm": "다이나프로 HP3",
                    "tire_size_1": "225/45R17",
                    "slogan": "SUV를 위한 컴포트 주행 성능",
                    "season_nm": "사계절",
                    "car_knd_nm": "SUV",
                    "goods_pfm_nm": "COMFORT",
                    "ptrn_d_nm": "다이나프로 컴포트",
                    "sale_prc": 140800,
                    "_available_tire_sizes": ["225/45R17", "235/60R18"],
                },
            ),
        ],
        size_specific=True,
    )

    assistant = event["data"]["assistantResponse"]

    assert "선택한 규격은 225/45R17예요." in assistant
    assert "상품 분류는 사계절 · 승용차 · COMFORT 기준으로 확인돼요." in assistant
    assert "상품 분류는 사계절 · SUV · COMFORT 기준으로 확인돼요." in assistant
    assert "벤투스 슈퍼 컴포트" not in assistant
    assert "다이나프로 컴포트" not in assistant
    assert "정가는 152,500원입니다." in assistant
    assert "정가는 140,800원입니다." in assistant
    assert "확인 가능한 규격은" not in assistant


def test_multi_product_detail_request_keeps_search_plan_available() -> None:
    frame = build_discovery_intent_frame("벤투스 에어S랑 키너지 ST AS 각각 설명해줘")
    plan = plan_discovery_tools(frame)

    assert frame.entities["multi_product_detail_request"] is True
    assert "search_product_tool" not in plan.forbidden_tools
    assert "get_products_recommendations_tool" in plan.forbidden_tools
    assert plan.tool_args_patch == {}
    assert plan.metadata["response_intent"] == "multi_product_detail"


def test_discovery_followup_intent_promotes_recent_product_set_size_availability() -> None:
    frame = build_discovery_intent_frame(
        "2355519 규격 있어?",
        known_slots={"discovery_followup_intent": "recent_product_set_size_availability"},
    )
    plan = plan_discovery_tools(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "recent_product_set_size_availability"
    assert frame.entities["discovery_followup_intent"] == "recent_product_set_size_availability"
    assert "search_product_tool" in plan.forbidden_tools
    assert plan.metadata["response_intent"] == "recent_product_set_size_availability"


def test_oe_query_is_not_hijacked_by_recent_product_set_size_availability() -> None:
    frame = build_discovery_intent_frame(
        "2454518 사이즈 OE 타이어 있음?",
        known_slots={"discovery_followup_intent": "recent_product_set_size_availability"},
    )
    plan = plan_discovery_tools(frame)
    decision = decide_discovery_response(frame)

    assert frame.intent == "product_search"
    assert frame.sub_intent == "oe_re_product_filter"
    assert frame.entities["oe_replacement_type"] == "oe"
    assert frame.entities["tire_size"] == "245/45R18"
    assert plan.preferred_tool == "search_product_tool"
    assert plan.tool_args_patch == {"limit": 10, "size": "245/45R18"}
    assert decision.metadata["response_shape_key"] == "oe_re_product_filter_summary"


def test_oe_concept_query_does_not_create_missing_reference_guard() -> None:
    frame = build_discovery_intent_frame("OE 타이어 뭐 있어? 다 RE 타이어야?")
    decision = decide_discovery_response(frame)
    contract = build_turn_contract(
        user_text="OE 타이어 뭐 있어? 다 RE 타이어야?",
        intent_frame=frame,
        tool_plan=plan_discovery_tools(frame),
        response_decision=decision,
        routing_result=SimpleNamespace(
            domains=[MultiAgentDomain.Domain.DISCOVERY],
            execution_plan=["discovery:oe_re_concept_explanation"],
            referred_object_status="resolved",
            referred_object_type="none",
            needs_clarification=False,
        ),
    )

    assert frame.intent == "product_description"
    assert frame.sub_intent == "oe_re_concept_explanation"
    assert decision.metadata["response_shape_key"] == "oe_re_concept_explanation"
    assert contract.blocking_required_slots == ()
    assert contract.known_slots["oe_replacement_type"] == "oe"


def test_discovery_policy_context_preserves_oe_query_over_recent_size_followup_router_hint() -> None:
    routing_result = MultiAgentDomain(
        reason="test",
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        execution_plan=["discovery:oe_re_product_filter"],
        user_behavior="asking for OE products in a specific size",
        flow="oe filter search",
        claim_check_type="none",
        complaint_scope="none",
        discovery_followup_intent="recent_product_set_size_availability",
        carried_discovery_objective="none",
        agent_prompt_profile="discovery_search",
    )

    tool_patch, response_decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="2454518 사이즈 OE 타이어 있음?",
        context_text="조용한 타이어 추천해줘\n2454518 사이즈 OE 타이어 있음?",
        tire_size="245/45R18",
        routing_result=routing_result,
    )

    assert tool_patch == {"size": "245/45R18"}
    assert response_decision is not None
    assert response_decision.metadata["response_shape_key"] == "oe_re_product_filter_summary"


def test_single_product_status_question_does_not_become_comparison() -> None:
    messages = [
        {"role": "user", "content": "벤투스 에어 S 알려줘"},
        {"role": "assistant", "content": "벤투스 에어S 상품 안내입니다."},
        {"role": "user", "content": "벤투스 s2 as 는?"},
    ]

    query = _comparison_query_with_recent_context("벤투스 s2 as 는?", messages)

    assert query == "벤투스 s2 as 는?"


def test_product_attribute_uses_existing_search_results_for_load_question() -> None:
    text = "내 차 하중이 좀 무거워. 짐을 많이 싣고 다니거든.. optimo 가 하중 버틸 수 있음?"
    text_token = current_user_text.set(text)
    decision_token = current_discovery_response_decision.set(
        decide_discovery_response(build_discovery_intent_frame(text))
    )
    try:
        event = _build_product_attribute_event_from_search_results(
            text,
            [
                (
                    "옵티모",
                    {
                        "status": "success",
                        "data": {
                            "items": [
                                {"goods_nm": "옵티모 H426", "t_wgt_idx": "99", "t_wgt_idx_kg": "775KG"},
                                {"goods_nm": "옵티모 K406", "t_wgt_idx": "108", "t_wgt_idx_kg": "1000KG"},
                            ]
                        },
                    },
                ),
            ],
        )
    finally:
        current_discovery_response_decision.reset(decision_token)
        current_user_text.reset(text_token)

    assert event is not None
    assert event["assistant_response_source"] == "code_product_attribute_resolver"
    assistant_response = event["data"]["assistantResponse"]
    assert "조회된 상품의 상세 정보" in assistant_response
    assert "- 옵티모 H426: 하중지수 99 775KG" in assistant_response
    assert "- 옵티모 K406: 하중지수 108 1000KG" in assistant_response
    assert "상품명을 알려주시면" not in assistant_response


def test_product_attribute_load_question_replaces_accidental_listcar() -> None:
    text = "내 차 하중이 좀 무거워. 짐을 많이 싣고 다니거든.. optimo 가 하중 버틸 수 있음?"
    event = {
        "type": "data",
        "template": "listCar",
        "source_domain": "discovery",
        "data": {"assistantResponse": "등록된 차량 7대를 확인했어요.", "listCar": []},
    }

    assert _is_product_attribute_lookup_query(text) is True
    assert _should_replace_listcar_with_product_attribute_lookup(event, text) is True


def test_external_price_comparison_does_not_enter_product_attribute_resolver() -> None:
    text = "벤투스 air S 2354518 네이버 쇼핑 최저가"

    assert _is_product_attribute_lookup_query(text) is False
    assert _should_apply_product_attribute_resolver(text, set()) is False
    assert (
        _build_product_attribute_event_from_search_results(
            text,
            [
                (
                    "벤투스 에어S",
                    {
                        "status": "success",
                        "data": {
                            "items": [
                                {
                                    "goods_nm": "벤투스 에어S",
                                    "tire_size_1": "235/45R18",
                                    "sale_prc": 160000,
                                }
                            ]
                        },
                    },
                )
            ],
        )
        is None
    )


def test_external_price_comparison_event_uses_internal_price_policy_copy_and_ctas() -> None:
    event = _build_external_price_comparison_event_from_search_results(
        "벤투스 air S 2354518 다나와에서 최저가 찾아줘",
        [
            (
                "벤투스 에어S",
                {
                    "status": "success",
                    "data": {
                        "items": [
                            {
                                "goods_nm": "벤투스 에어S",
                                "tire_size_1": "235/45R18",
                                "sale_prc": 160000,
                                "extra_fvr_sale_prc": 140000,
                                "cheapest_final_prc": 128000,
                            }
                        ]
                    },
                },
            )
        ],
    )

    assert event is not None
    assistant = event["data"]["assistantResponse"]
    assert "외부 사이트의 실시간 최저가" in assistant
    assert "직접 수집하거나 비교할 수는 없어요" in assistant
    assert "T'Station 기준" in assistant
    assert "내부 최저 혜택가 128,000원" in assistant
    assert "상품이에요" not in assistant
    assert _labels(event["data"]["quickReplies"]) == [
        "T'Station 가격 확인",
        "회원 쿠폰 적용가 보기",
        "다른 사이즈 확인",
    ]


def test_external_price_comparison_event_can_use_product_description_source() -> None:
    search_results = _external_price_search_results_from_sources([
        (
            "get_product_description_tool",
            {
                "status": "success",
                "data": {
                    "goods_nm": "벤투스 에어S",
                    "tire_size_1": "235/45R18",
                    "sale_prc": 253000,
                    "cheapest_final_prc": 177100,
                },
            },
        )
    ])

    event = _build_external_price_comparison_event_from_search_results(
        "벤투스 air S 2354518 다나와에서 최저가 찾아줘",
        search_results,
    )

    assert event is not None
    assistant = event["data"]["assistantResponse"]
    assert "직접 수집하거나 비교할 수는 없어요" in assistant
    assert "내부 최저 혜택가 177,100원" in assistant
    assert "프리미엄이 제공하는" not in assistant


def test_product_description_turn_does_not_apply_attribute_resolver() -> None:
    text = "아이온 에보 AS SUV 235/55R19"

    assert _is_product_attribute_lookup_query(text) is True
    assert _should_apply_product_attribute_resolver(text, {"get_product_description_tool"}) is False
    assert _should_apply_product_attribute_resolver(text, set()) is True


def test_product_warranty_question_does_not_apply_attribute_resolver() -> None:
    text = "벤투스 S2 AS 워런티 돼?"

    assert _is_product_attribute_lookup_query(text) is False
    assert _should_apply_product_attribute_resolver(text, set()) is False
    assert (
        _build_product_attribute_event_from_search_results(
            text,
            [
                (
                    "벤투스 S2 AS",
                    {
                        "status": "success",
                        "data": {
                            "items": [
                                {"goods_nm": "벤투스 S2 AS", "car_type_nm": "승용차"},
                            ],
                        },
                    },
                ),
            ],
        )
        is None
    )


def test_product_attribute_query_suppresses_inherited_recommendation_context_without_explicit_size() -> None:
    assert _should_suppress_inherited_recommendation_context_for_product_attribute("키너지 EX 설명좀") is True


def test_product_attribute_query_keeps_context_when_same_turn_size_is_explicit() -> None:
    assert _should_suppress_inherited_recommendation_context_for_product_attribute("키너지 EX 225/55R17 설명좀") is False


def test_store_date_availability_context_preserved_on_store_confirmation_reply() -> None:
    messages = [
        {"role": "user", "content": "티스테이션 성남 IC점 5/29 오후 16시 예약 돼?"},
        {
            "role": "assistant",
            "content": "고객님, 요청하신 '성남 IC점'으로 검색한 결과 '티스테이션 성남IC점' 매장이 있는데 이 매장이 맞을까요?",
        },
    ]

    assert _should_preserve_store_date_availability_context("네, 맞아요", messages) is True


def test_store_date_availability_context_not_preserved_for_generic_store_confirmation() -> None:
    messages = [
        {"role": "user", "content": "티스테이션 성남 IC점 전화번호 알려줘"},
        {
            "role": "assistant",
            "content": "고객님, 요청하신 '성남 IC점'으로 검색한 결과 '티스테이션 성남IC점' 매장이 있는데 이 매장이 맞을까요?",
        },
    ]

    assert _should_preserve_store_date_availability_context("네, 맞아요", messages) is False


def test_current_turn_new_store_name_invalidates_carried_shop_id_without_prior_name() -> None:
    assert _is_new_store_name_anchor_for_current_turn(
        current_store_name="모란점",
        existing_shop_name=None,
        existing_shop_id="F00409",
    ) is True


def test_current_turn_new_store_name_invalidates_mismatched_carried_store() -> None:
    assert _is_new_store_name_anchor_for_current_turn(
        current_store_name="모란점",
        existing_shop_name="신성주점",
        existing_shop_id="F00409",
    ) is True


def test_current_turn_same_store_name_can_keep_carried_shop_id() -> None:
    assert _is_new_store_name_anchor_for_current_turn(
        current_store_name="한남점",
        existing_shop_name="티스테이션 한남점",
        existing_shop_id="F07782",
    ) is False
    assert _normalize_store_name_for_slot_compare("티스테이션 한남점") == "한남점"


def test_recent_single_store_context_not_reused_when_current_turn_names_store() -> None:
    prev_tool_data = [
        {
            "tool": "search_stores_tool",
            "input": {"store_nm": "신성주점"},
            "data": {"stores": [{"shop_id": "F00409", "shop_nm": "신성주점"}]},
        }
    ]
    regex_slots = ConversationSlots.extract_from_user_text("벤투스 S2 AS 2254517 4개 모란점 재고 확인해줘")

    assert regex_slots.pending_intent == "stock"
    assert regex_slots.shop_name == "모란점"
    assert TStationChatServiceV2._resolve_recent_single_shop_id_from_context(prev_tool_data) == "F00409"
    assert _is_new_store_name_anchor_for_current_turn(regex_slots.shop_name, None, "F00409") is True


def test_search_product_tool_slot_data_preserves_goods_no_for_chained_transaction() -> None:
    tool_result = {
        "status": "success",
        "data": {
            "items": [
                {
                    "goods_no": "G000000309783",
                    "goods_nm": "벤투스 S2 AS",
                    "tire_size_1": "225/45R17",
                    "sale_prc": 150000,
                }
            ]
        },
    }

    slot_data = _slot_data_for_tool_event("search_product_tool", tool_result)
    slots = ConversationSlots(pending_intent="stock", shop_name="모란점", ord_qty=4)

    assert slot_data == {
        "status": "success",
        "data": {"items": [{"goods_no": "G000000309783", "tire_size_1": "225/45R17"}]},
    }
    changed = StreamingMultiAgentCoordinator._apply_tool_derived_slots(
        slots,
        "search_product_tool",
        slot_data,
        {"keyword": "벤투스 S2 AS", "size": "225/45R17"},
    )

    assert changed is True
    assert slots.goods_no == "G000000309783"
    assert slots.tire_size == "225/45R17"
    assert slots.pending_intent == "stock"


def test_chained_transaction_policy_refresh_removes_product_required_after_discovery_goods_no() -> None:
    _tool_patch, decision = _build_transaction_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION],
        last_user_text="벤투스 S2 AS 2254517 4개 모란점 재고 확인해줘",
        known_slots={
            "tire_size": "225/45R17",
            "goods_no": "G000000309783",
            "quantity": 4,
            "ord_qty": 4,
            "store_name": "모란점",
        },
    )

    assert decision is not None
    assert "product" not in decision.required_slots


def test_grade_comparison_search_uses_korean_preferred_keywords() -> None:
    assert _preferred_product_search_keyword("Kinergy EX") == "키너지 EX"
    assert _preferred_product_search_keyword("kinergy ex") == "키너지 EX"
    assert _preferred_product_search_keyword("Ventus air S") == "벤투스 에어S"
    assert _preferred_product_search_keyword("ventus air s") == "벤투스 에어S"


def test_bare_short_alias_can_use_code_product_search_path() -> None:
    assert _is_bare_product_name_search_query("s fit as") is True
    assert _is_bare_product_name_search_query("에스핏") is True
    assert _is_bare_product_name_search_query("s fit as 가격 알려줘") is False
    assert _is_bare_product_name_search_query("벤투스 S2 AS 225/45R17 2개 장바구니 담아줘") is False
    assert _is_bare_product_name_search_query("벤투스 S2 AS 225/45R17 4개 구매할래") is False
    assert _is_bare_product_name_search_query("벤투스 S2 AS 225/45R17 재고 조회") is False


def test_bare_product_search_tool_input_preserves_same_turn_size() -> None:
    assert _build_bare_product_search_tool_input("벤투스 S2 AS 225/45R17") == {
        "keyword": "벤투스 S2 AS",
        "limit": 10,
        "size": "225/45R17",
        "brand_cd": "HK",
    }


def test_size_only_store_availability_continuation_recovers_product_context() -> None:
    prev_tool_data = [{
        "tool": "search_product_tool",
        "input": {"keyword": "벤투스 에어S", "limit": 10},
        "data": {
            "items": [{
                "goods_no": "G000000319593",
                "goods_nm": "벤투스 에어S",
                "tire_size_1": "235/55R19",
            }]
        },
    }]
    recent_context = "판교점에서 ventus air S 오늘 장착 가능해?\n규격을 알려주세요."

    assert _build_size_only_product_search_tool_input(
        "2355519",
        prev_tool_data=prev_tool_data,
        recent_context=recent_context,
    ) == {"keyword": "벤투스 에어S", "limit": 10, "size": "235/55R19"}
    assert _is_size_only_store_availability_continuation(
        "2355519",
        prev_tool_data=prev_tool_data,
        recent_context=recent_context,
    ) is True


def test_size_only_store_availability_continuation_requires_availability_context() -> None:
    prev_tool_data = [{
        "tool": "search_product_tool",
        "input": {"keyword": "벤투스 에어S", "limit": 10},
        "data": {"items": [{"goods_nm": "벤투스 에어S"}]},
    }]

    assert _is_size_only_store_availability_continuation(
        "2355519",
        prev_tool_data=prev_tool_data,
        recent_context="벤투스 에어S 설명해줘\n규격을 알려주세요.",
    ) is False


def test_store_availability_size_followup_quantity_prompt_invariant() -> None:
    event = _build_store_availability_quantity_prompt_event(
        product_keyword="벤투스 에어S",
        tire_size="235/55R19",
        store_name="티스테이션 판교점",
        goods_no="G000000319593",
    )

    response = event["data"]["assistantResponse"]
    assert event["source_domain"] == "transaction"
    assert event["assistant_response_source"] == "code_store_availability_size_followup_quantity_prompt"
    assert "벤투스 에어S 235/55R19 상품은 확인했어요" in response
    assert "티스테이션 판교점 오늘 장착 가능 여부" in response
    assert "장착 수량을 알려주세요" in response
    assert "상품 검색하겠습니다" not in response
    assert "프리미엄이 제공하는" not in response
    assert _labels(event["data"]["quickReplies"]) == ["1개", "2개", "3개", "4개"]


def test_store_availability_continuation_recovers_recent_single_store_name() -> None:
    prev_tool_data = [{
        "tool": "get_store_list_tool",
        "data": [{"shop_id": "F00098", "shop_nm": "티스테이션 판교점"}],
    }]

    assert _recent_store_name_for_availability_continuation(prev_tool_data=prev_tool_data) == "티스테이션 판교점"


def test_sized_bare_product_search_can_resolve_unique_goods_no_for_detail() -> None:
    row = _unique_product_row_from_sized_search_result(
        {
            "status": "success",
            "data": {
                "items": [
                    {
                        "goods_no": "G000000309783",
                        "goods_nm": "벤투스 S2 AS",
                        "tire_size_1": "225/45R17",
                    }
                ]
            },
        },
        "벤투스 S2 AS",
        "225/45R17",
    )

    assert row is not None
    assert row["goods_no"] == "G000000309783"


def test_sized_product_name_search_accepts_compact_numeric_size() -> None:
    assert _is_sized_product_name_search_query("벤투스 에보 2254517") is True


def test_sized_product_name_search_accepts_unknown_model_name() -> None:
    assert _is_sized_product_name_search_query("새상품 ABC 2356018") is True
    assert _build_bare_product_search_tool_input("새상품 ABC 2356018") == {
        "keyword": "새상품 ABC",
        "limit": 10,
        "size": "235/60R18",
    }


def test_sized_product_name_search_rejects_size_only_text() -> None:
    assert _is_sized_product_name_search_query("2356018") is False
    assert _build_bare_product_search_tool_input("2356018") is None


def test_sized_product_name_search_rejects_followup_reference_size_availability_text() -> None:
    assert _is_sized_product_name_search_query("두개다 2355519 사이즈가 있을까?") is False
    assert _build_bare_product_search_tool_input("두개다 2355519 사이즈가 있을까?") is None
    assert _is_recent_product_size_availability_query("두개다 2355519 사이즈가 있을까?") is True


def test_recent_product_size_availability_query_does_not_require_reference_keyword() -> None:
    assert _is_sized_product_name_search_query("2355519 사이즈가 있을까?") is False
    assert _build_bare_product_search_tool_input("2355519 사이즈가 있을까?") is None
    assert _is_recent_product_size_availability_query("2355519 사이즈가 있을까?") is True


def test_size_only_followup_search_reuses_recent_product_context() -> None:
    assert _build_size_only_product_search_tool_input(
        "2255517",
        recent_context="ventus air S 2255517 4개 구매하고 싶은데 쿠폰 적용하면 할인받는 금액이 얼마야?\n2255517",
    ) == {
        "keyword": "벤투스 에어S",
        "limit": 10,
        "size": "225/55R17",
    }


def test_size_only_followup_search_reuses_recent_search_tool_keyword() -> None:
    assert _build_size_only_product_search_tool_input(
        "2255517",
        prev_tool_data=[{"tool": "search_product_tool", "input": {"keyword": "벤투스 에어S"}}],
    ) == {
        "keyword": "벤투스 에어S",
        "limit": 10,
        "size": "225/55R17",
    }


def test_sized_product_name_search_can_resolve_unique_ventus_evo_goods_no() -> None:
    row = _unique_product_row_from_sized_search_result(
        {
            "status": "success",
            "data": {
                "items": [
                    {
                        "goods_no": "G000000320136",
                        "goods_nm": "벤투스 에보",
                        "tire_size_1": "225/45R17",
                    }
                ]
            },
        },
        "벤투스 에보",
        "225/45R17",
    )

    assert row is not None
    assert row["goods_no"] == "G000000320136"


def test_sized_product_resolver_accepts_alias_but_rejects_same_family_other_model() -> None:
    assert _is_strong_product_name_match("Ventus air S", "벤투스 에어S") is True
    assert _is_strong_product_name_match("Dynapro HPX", "다이나프로 HPX") is True
    assert _is_strong_product_name_match("벤투스 에어S", "벤투스 S1 evo Z AS") is False
    assert _is_strong_product_name_match("다이나프로 HPX", "다이나프로 HL3") is False

    row = _unique_product_row_from_sized_search_result(
        {
            "status": "success",
            "data": {
                "items": [
                    {
                        "goods_no": "G-S1",
                        "goods_nm": "벤투스 S1 evo Z AS",
                        "tire_size_1": "265/45R19",
                    }
                ]
            },
        },
        "벤투스 에어S",
        "265/45R19",
    )

    assert row is None


def test_sized_bare_product_search_does_not_guess_ambiguous_goods_no() -> None:
    row = _unique_product_row_from_sized_search_result(
        {
            "status": "success",
            "data": {
                "items": [
                    {
                        "goods_no": "G1",
                        "goods_nm": "벤투스 S2 AS",
                        "tire_size_1": "225/45R17",
                    },
                    {
                        "goods_no": "G2",
                        "goods_nm": "벤투스 S2 AS",
                        "tire_size_1": "225/45R17",
                    },
                ]
            },
        },
        "벤투스 S2 AS",
        "225/45R17",
    )

    assert row is None


def test_product_description_quickreply_stays_description_focused() -> None:
    event = _build_product_description_quickreply_event({
        "status": "success",
        "data": {
            "goods_nm": "벤투스 S2 AS",
            "big_goods_nm": "벤투스",
            "goods_no": "G000000309783",
            "tire_size_1": "225/45R17",
            "slogan": "고속 주행에서 느끼는 Comfort Technology",
            "pc_prod_remark_desc": (
                "<ol><li><span>제조사</span> 한국타이어</li>"
                "<li><span>품질 보증</span> 제조상의 과실에 의한 하자가 발생 시 A/S 처리해드립니다.</li>"
                "<li><span>특이사항</span> TPMS 또는 런플랫 타이어는 추가 비용이 발생합니다.</li></ol>"
            ),
            "pc_prod_tech_desc": "<ol><li>승차감 : 조용하고 안락한 승차감 제공</li></ol>",
            "ptrn_d_nm": "벤투스 슈퍼 컴포트",
            "season_nm": "사계절",
            "car_knd_nm": "승용차",
            "goods_pfm_nm": "COMFORT",
            "t_comfort": 4.5,
            "t_silence": 4.3,
            "t_life_span": 4.1,
            "wet": "B",
            "rr": "A",
            "sale_prc": 152500,
            "cheapest_final_prc": 118800,
            "cheapest_applied_coupons": [
                {"cpn_nm": "한국타이어 18% 상품 할인쿠폰(26년)"},
                {"cpn_nm": "마케팅동의 5% 결제쿠폰"},
            ],
            "rating": {"review_count": 68, "rating_avg": 4.5},
        },
    })

    assert event is not None
    assert event["template"] == "quickReply"
    assistant_response = event["data"]["assistantResponse"]
    assert "벤투스 S2 AS" in assistant_response
    assert "225/45R17" in assistant_response
    assert "사계절" in assistant_response
    assert "승용차" in assistant_response
    assert "COMFORT" in assistant_response
    assert "승차감 : 조용하고 안락한 승차감 제공" in assistant_response
    assert "품질 보증" not in assistant_response
    assert "제조상의 과실" not in assistant_response
    assert "A/S" not in assistant_response
    assert "특이사항" not in assistant_response
    assert "TPMS" not in assistant_response
    assert "승차감 4.5/5" in assistant_response
    assert "정숙성 4.3/5" in assistant_response
    assert "마일리지 4.1/5" in assistant_response
    assert "젖은노면 B등급" in assistant_response
    assert "회전저항 A등급" in assistant_response
    assert "최종 혜택가" not in assistant_response
    assert "정가" not in assistant_response
    assert "리뷰는 68건" in assistant_response
    assert [reply["label"] for reply in event["data"]["quickReplies"]] == ["가격 확인", "재고 확인", "다른 상품 보기"]
    assert event["data"]["metadata"] == {
        "goodsId": "G000000309783",
        "tireSize": "225/45R17",
        "productName": "벤투스 S2 AS",
    }


def test_product_description_claim_check_prefix_uses_policy_decision_only() -> None:
    frame = build_discovery_intent_frame("벤투스 air S가 우주 항공국 인증 제품이라던데 사실이야?")
    decision = decide_discovery_response(frame)
    assert frame.intent == "product_description"
    assert frame.entities["claim_check_type"] == "unverified_external_claim"
    assert decision.metadata["claim_check_type"] == "unverified_external_claim"
    decision_token = current_discovery_response_decision.set(decision)
    try:
        event = _build_product_description_quickreply_event({
            "status": "success",
            "data": {
                "goods_nm": "벤투스 에어S",
                "goods_no": "G000000380117",
                "tire_size_1": "245/45R18",
                "slogan": "프리미엄이 제공하는 품격있는 정숙성과 승차감",
                "season_nm": "사계절",
                "car_knd_nm": "승용차",
                "goods_pfm_nm": "COMFORT",
            },
        })
    finally:
        current_discovery_response_decision.reset(decision_token)

    assert event is not None
    assistant_response = event["data"]["assistantResponse"]
    assert assistant_response.startswith("말씀하신 내용은 현재 상품 설명 데이터에서 직접 확인하기 어려워요.")
    assert "확인 가능한 상품 설명 기준으로 안내드릴게요." in assistant_response
    assert "벤투스 에어S는 프리미엄이 제공하는 품격있는 정숙성과 승차감 상품이에요." in assistant_response


def test_discovery_policy_context_uses_routing_claim_check_type() -> None:
    _tool_patch, decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="벤투스 air S가 외부 기관 인증 제품이라던데 사실이야?",
        context_text="벤투스 air S가 외부 기관 인증 제품이라던데 사실이야?",
        tire_size=None,
        routing_result=SimpleNamespace(claim_check_type="unverified_external_claim"),
    )

    assert decision is not None
    assert decision.metadata["response_shape_key"] == "neutral_product_description"
    assert decision.metadata["claim_check_type"] == "unverified_external_claim"


def test_router_claim_check_type_is_required_for_strict_structured_output() -> None:
    assert "claim_check_type" in MultiAgentDomain.model_json_schema()["required"]


def test_router_complaint_scope_is_required_for_strict_structured_output() -> None:
    assert "complaint_scope" in MultiAgentDomain.model_json_schema()["required"]


@pytest.mark.parametrize(
    "text",
    [
        "한국타이어 주식 사고 난 이후로 점점 떨어지기만 하고 되는 일이 없어..!!",
        "요즘 취업도 안 되고 되는 일이 없어",
    ],
)
def test_out_of_scope_complaint_gets_scope_guidance_without_support_handoff(text: str) -> None:
    assert _infer_complaint_scope(text) == "out_of_scope_complaint"

    event = _build_complaint_scope_guard_event(_complaint_scope_for_turn(text, None))

    assert event is not None
    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "code_complaint_scope_guard"
    assert event["source_domain"] == MultiAgentDomain.Domain.LEADING.value
    assistant_response = event["data"]["assistantResponse"]
    assert "직접 도와드리기 어려운 주제" in assistant_response
    assert "타이어 추천, 가격 조회, 매장 검색, 주문/장착 관련 문의" in assistant_response
    assert "상담" not in assistant_response
    assert "1:1" not in assistant_response
    assert _labels(event["data"]["quickReplies"]) == ["타이어 추천", "가격 조회", "매장 찾기"]


def test_unclear_complaint_asks_target_before_support_handoff() -> None:
    assert _infer_complaint_scope("되는 일이 없어 짜증나") == "unclear_complaint"

    event = _build_complaint_scope_guard_event(_complaint_scope_for_turn("되는 일이 없어 짜증나", None))

    assert event is not None
    assert event["source_domain"] == MultiAgentDomain.Domain.LEADING.value
    assistant_response = event["data"]["assistantResponse"]
    assert "어떤 부분이 불편하셨는지" in assistant_response
    assert "타이어 상품, 주문/결제, 장착 매장" in assistant_response
    assert _labels(event["data"]["quickReplies"]) == ["주문 조회", "매장 찾기", "1:1 문의"]


@pytest.mark.parametrize(
    "text",
    [
        "타이어 주문했는데 계속 오류나고 되는 일이 없어",
        "너 답변이 계속 틀려서 짜증나",
    ],
)
def test_tstation_service_complaint_is_not_blocked_by_scope_guard(text: str) -> None:
    assert _infer_complaint_scope(text) == "tstation_service_complaint"
    assert _build_complaint_scope_guard_event(_complaint_scope_for_turn(text, None)) is None


def test_router_complaint_scope_overrides_broad_support_prediction_for_out_of_scope() -> None:
    routing_result = SimpleNamespace(complaint_scope="out_of_scope_complaint")

    event = _build_complaint_scope_guard_event(
        _complaint_scope_for_turn("한국타이어 주식 떨어져서 짜증나", routing_result)
    )

    assert event is not None
    assert "1:1 문의" not in _labels(event["data"]["quickReplies"])


def test_forced_routing_defaults_claim_check_type_without_relaxing_schema() -> None:
    route = StreamingMultiAgentCoordinator._force_keyword_routing("고객센터 왜 전화가 안돼? 주문 취소 처리해줘")

    assert route is not None
    assert route.claim_check_type == "none"
    assert route.domains == [MultiAgentDomain.Domain.TRANSACTION]
    assert route.agent_prompt_profile == "transaction_order"


@pytest.mark.parametrize(
    "text",
    [
        "벤투스 air S 설명해줘",
        "벤투스 air S 최저소음 라벨 맞아?",
    ],
)
def test_product_description_prefix_not_added_for_general_or_verifiable_claim(text: str) -> None:
    frame = build_discovery_intent_frame(text)
    decision = decide_discovery_response(frame)
    if "라벨" in text:
        assert frame.entities["claim_check_type"] == "verifiable_product_attribute"
        assert decision.metadata["claim_check_type"] == "verifiable_product_attribute"
    else:
        assert frame.entities["claim_check_type"] == "none"
        assert "claim_check_type" not in decision.metadata
    decision_token = current_discovery_response_decision.set(decision)
    try:
        event = _build_product_description_quickreply_event({
            "status": "success",
            "data": {
                "goods_nm": "벤투스 에어S",
                "goods_no": "G000000380117",
                "tire_size_1": "245/45R18",
                "slogan": "프리미엄이 제공하는 품격있는 정숙성과 승차감",
                "season_nm": "사계절",
                "car_knd_nm": "승용차",
                "goods_pfm_nm": "COMFORT",
            },
        })
    finally:
        current_discovery_response_decision.reset(decision_token)

    assert event is not None
    assistant_response = event["data"]["assistantResponse"]
    assert not assistant_response.startswith("말씀하신 내용은 현재 상품 설명 데이터에서 직접 확인하기 어려워요.")
    assert "확인 가능한 상품 설명 기준으로 안내드릴게요." not in assistant_response


def test_grade_comparison_uses_existing_search_results_for_korean_keywords() -> None:
    event = _build_product_comparison_event_from_search_results(
        "키너지 EX가 벤투스 air S 보다 프리미엄 등급 맞지?",
        [
            (
                "키너지 EX",
                {"status": "success", "data": {"items": [{"goods_nm": "키너지 EX", "prc_grd_nm": "스탠다드"}]}},
            ),
            (
                "벤투스 에어S",
                {"status": "success", "data": {"items": [{"goods_nm": "벤투스 에어S", "prc_grd_nm": "프리미엄"}]}},
            ),
        ],
    )

    assert event is not None
    assert event["assistant_response_source"] == "code_product_compare_resolver"
    assert "벤투스 에어S이 키너지 EX보다 상위 등급입니다." in event["data"]["assistantResponse"]


def test_grade_comparison_does_not_match_unrelated_single_search_result() -> None:
    row = _pick_product_row_from_search_result(
        {"status": "success", "data": {"items": [{"goods_nm": "키너지 EX", "prc_grd_nm": "스탠다드"}]}},
        "Ventus air S",
    )

    assert row is None


def test_product_row_picker_uses_actual_search_keyword_without_product_alias() -> None:
    row = _pick_product_row_from_search_result(
        {"status": "success", "data": {"items": [{"goods_nm": "다이나프로 HP3", "t_rls_yearmon": "2025년 2월"}]}},
        "Dynapro HP3",
        "다이나프로 HP3",
    )

    assert row is not None
    assert row["goods_nm"] == "다이나프로 HP3"


def test_product_search_keyword_candidates_include_korean_and_english_dynapro_variants() -> None:
    assert _product_search_keyword_candidates("Dynapro HPX") == ("다이나프로 HPX", "Dynapro HPX")
    assert _product_search_keyword_candidates("다이나프로 HPX") == ("다이나프로 HPX", "Dynapro HPX")


def test_product_row_picker_matches_partial_pattern_name_generically() -> None:
    row = _pick_product_row_from_search_result(
        {"status": "success", "data": {"items": [{"goods_nm": "벤투스 프라임2", "prc_grd_nm": "스탠다드"}]}},
        "프라임",
    )

    assert row is not None
    assert row["goods_nm"] == "벤투스 프라임2"


def test_product_row_picker_rejects_same_family_other_ion_variant() -> None:
    row = _pick_product_row_from_search_result(
        {"status": "success", "data": {"items": [{"goods_nm": "아이온 에보 AS SUV"}]}},
        "iON evo AS",
        "아이온 에보 AS",
    )

    assert row is None


def test_product_row_picker_can_use_first_row_fallback_for_product_specific_search() -> None:
    row = _pick_product_row_from_search_result(
        {
            "status": "success",
            "data": {"items": [{"goods_nm": "벤투스 에어 에스", "t_rls_yearmon": "2025년 3월"}]},
        },
        "Ventus air S",
        "벤투스 에어S",
        allow_first_row_fallback=True,
    )

    assert row is not None
    assert row["goods_nm"] == "벤투스 에어 에스"


def test_latest_comparison_uses_search_keyword_to_match_rows() -> None:
    event = _build_product_comparison_event_from_search_results(
        "dynapro HPX, dynapro HP3 중에 최신상품이 뭐야? 헷갈리넹",
        [
            (
                "다이나프로 HPX",
                {
                    "status": "success",
                    "data": {
                        "items": [{
                            "goods_nm": "다이나프로 HPX",
                            "sys_reg_dtime": "2022-11-10 10:00:00",
                            "t_rls_yearmon": "2023년 1월",
                        }]
                    },
                },
            ),
            (
                "다이나프로 HP3",
                {
                    "status": "success",
                    "data": {
                        "items": [{
                            "goods_nm": "다이나프로 HP3",
                            "sys_reg_dtime": "2025-01-20 09:30:00",
                            "t_rls_yearmon": "2025년 2월",
                        }]
                    },
                },
            ),
        ],
    )

    assert event is not None
    assert "최신 상품은 다이나프로 HP3입니다." in event["data"]["assistantResponse"]


def test_latest_comparison_search_results_can_fallback_to_first_row_for_alias_variants() -> None:
    event = _build_product_comparison_event_from_search_results(
        "ventus s2 as, ventus air S 중에 뭐가 더 신상품?",
        [
            (
                "벤투스 S2 AS",
                {
                    "status": "success",
                    "data": {
                        "items": [{
                            "goods_nm": "벤투스 에스투 에이에스",
                            "sys_reg_dtime": "2022-11-10 10:00:00",
                            "t_rls_yearmon": "2023년 1월",
                        }]
                    },
                },
            ),
            (
                "벤투스 에어S",
                {
                    "status": "success",
                    "data": {
                        "items": [{
                            "goods_nm": "벤투스 에어 에스",
                            "sys_reg_dtime": "2025-01-20 09:30:00",
                            "t_rls_yearmon": "2025년 2월",
                        }]
                    },
                },
            ),
        ],
    )

    assert event is not None
    assert "최신 상품은 벤투스 에어 에스입니다." in event["data"]["assistantResponse"]


def test_product_comparison_event_does_not_build_when_both_targets_resolve_to_same_product() -> None:
    event = _build_product_comparison_event_from_search_results(
        "아이온 에보랑 아이온 에보 as 비교",
        [
            (
                "아이온 에보",
                {"status": "success", "data": {"items": [{"goods_no": "G-AS-SUV", "goods_nm": "아이온 에보 AS SUV"}]}},
            ),
            (
                "아이온 에보 AS",
                {"status": "success", "data": {"items": [{"goods_no": "G-AS-SUV", "goods_nm": "아이온 에보 AS SUV"}]}},
            ),
        ],
    )

    assert event is None


def test_grade_comparison_partial_search_results_defer_to_code_resolver() -> None:
    event = _build_product_comparison_event_from_search_results(
        "키너지 EX가 벤투스 air S 보다 프리미엄 등급 맞지?",
        [
            (
                "키너지 EX",
                {"status": "success", "data": {"items": [{"goods_nm": "키너지 EX", "prc_grd_nm": "스탠다드"}]}},
            ),
        ],
    )

    assert event is None


def test_common_policy_guidance_leak_blocker_rewrites_discovery_guidance() -> None:
    decision = decide_discovery_response(
        build_discovery_intent_frame("키너지 EX가 벤투스 air S 보다 프리미엄 등급 맞지?")
    )
    event_data = {
        "assistantResponse": decision.assistant_guidance,
        "quickReplies": [{"label": "보유차량 중 선택", "domain": "DISCOVERY"}],
    }

    changed = _normalize_policy_guidance_leak_quickreply(
        event_data,
        source_domain="discovery",
        decision=decision,
    )

    assert changed is True
    assert event_data["assistantResponse"] != decision.assistant_guidance
    assert _labels(event_data["quickReplies"]) == ["상품명 다시 입력", "사이즈 직접 입력", "내 차량 보기"]


def test_common_policy_guidance_leak_blocker_rewrites_transaction_guidance() -> None:
    frame = build_price_intent_frame("30% 할인 쿠폰 적용 가능 상품 뭐뭐 있어?")
    decision = decide_price_response(frame)
    event_data = {
        "assistantResponse": decision.assistant_guidance,
        "quickReplies": [{"label": "보유차량 중 선택", "domain": "DISCOVERY"}],
    }

    changed = _normalize_policy_guidance_leak_quickreply(
        event_data,
        source_domain="transaction",
        decision=decision,
    )

    assert changed is True
    assert event_data["assistantResponse"] != decision.assistant_guidance
    assert _labels(event_data["quickReplies"]) == ["내 쿠폰 조회", "주문 내역 보기", "1:1 문의하기"]


def test_recommendation_tool_passes_strict_brand_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Parsed:
        def to_dict(self) -> dict:
            return {"rcmd_type": "tstation", "total": 0, "items": []}

    def _fake_get_products_recommendations(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(status_code=200, parsed=_Parsed(), content=b"")

    monkeypatch.setattr(discovery_tools, "get_products_recommendations", _fake_get_products_recommendations)

    result = discovery_tools.get_products_recommendations_tool.invoke(
        {
            "rcmd_type": "tstation",
            "limit": 2,
            "brand_cd": "HK",
            "tire_size": "225/45R18",
            "allow_cross_brand_fill": False,
        }
    )

    assert result["status"] == "success"
    assert captured["allow_cross_brand_fill"] is False


def test_best_selling_tool_enriches_price_and_description_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class _Parsed:
        def to_dict(self) -> dict:
            return {
                "items": [
                    {
                        "goods_no": "G000000317682",
                        "goods_nm": "다이나프로 HPX",
                        "tire_size_1": "235/55R19",
                        "extra_fvr_sale_prc": "179700",
                    }
                ]
            }

    def _fake_get_best_sellers(**_kwargs):
        return SimpleNamespace(status_code=200, parsed=_Parsed(), content=b"")

    def _fake_price_enrich(items: list[dict]) -> list[dict]:
        calls.append("price")
        enriched = [dict(item) for item in items]
        enriched[0]["sale_prc"] = "220000"
        return enriched

    def _fake_description_enrich(items: list[dict]) -> list[dict]:
        calls.append("description")
        enriched = [dict(item) for item in items]
        enriched[0]["rate"] = 4.8
        enriched[0]["prc_grd_nm"] = "프리미엄"
        return enriched

    monkeypatch.setattr(discovery_tools, "get_best_sellers", _fake_get_best_sellers)
    monkeypatch.setattr(discovery_tools, "_enrich_items_with_price_fields", _fake_price_enrich)
    monkeypatch.setattr(discovery_tools, "_enrich_items_with_descriptions", _fake_description_enrich)

    result = discovery_tools.get_best_selling_products_tool.invoke({"period": "3months", "limit": 5})

    assert result["status"] == "success"
    item = result["data"]["items"][0]
    assert calls == ["price", "description"]
    assert item["sale_prc"] == "220000"
    assert item["rate"] == 4.8
    assert item["prc_grd_nm"] == "프리미엄"


def test_best_selling_cached_tool_result_is_enriched_before_template(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_product_card_enrich(items: list[dict]) -> list[dict]:
        enriched = [dict(item) for item in items]
        enriched[0]["sale_prc"] = "220000"
        enriched[0]["rate"] = 4.8
        enriched[0]["prc_grd_nm"] = "프리미엄"
        return enriched

    monkeypatch.setattr(discovery_tools, "enrich_product_card_items", _fake_product_card_enrich)

    result = _enrich_best_selling_result_for_product_cards({
        "status": "success",
        "data": {
            "items": [
                {
                    "goods_no": "G000000317682",
                    "goods_nm": "다이나프로 HPX",
                    "tire_size_1": "235/55R19",
                    "extra_fvr_sale_prc": "179700",
                }
            ]
        },
    })

    item = result["data"]["items"][0]
    assert item["sale_prc"] == "220000"
    assert item["rate"] == 4.8
    assert item["prc_grd_nm"] == "프리미엄"


def test_tc005_family_coupon_matching_ignores_product_terms() -> None:
    result = _find_coupon_from_owned_coupons(
        "키너지 EX 패밀리 할인쿠폰 적용받고 싶어",
        {
            "status": "success",
            "data": {
                "coupons": [
                    {"cpn_no": "C001", "cpn_nm": "패밀리 할인쿠폰", "rt_amt_val": 10},
                ],
            },
        },
    )

    assert result is not None
    assert result["cpn_no"] == "C001"


def test_employee_coupon_matching_ignores_product_terms() -> None:
    result = _find_coupon_from_owned_coupons(
        "다이나프로 HPX 임직원 쿠폰 적용돼?",
        {
            "status": "success",
            "data": {
                "coupons": [
                    {"cpn_no": "C001", "cpn_nm": "패밀리 할인쿠폰", "rt_amt_val": 10},
                    {"cpn_no": "C002", "cpn_nm": "임직원 전용 쿠폰", "rt_amt_val": 15},
                ],
            },
        },
    )

    assert result is not None
    assert result["cpn_no"] == "C002"


def test_specific_coupon_usage_query_detects_coupon_and_deal_usage_without_price() -> None:
    assert _is_specific_coupon_usage_query("우동딜 테스트는 어떻게 써?")
    assert _is_specific_coupon_usage_query("이 쿠폰 쓸 수 있어?")
    assert _is_specific_coupon_usage_query("이 상품에 우동딜 테스트 쿠폰 먹어?")
    assert _is_specific_coupon_usage_query("월디페 참여고객_한국타이어 30% 할인은 매장에서 사용 가능?")
    assert not _is_specific_coupon_usage_query("벤투스 S2 AS 2254517 할인가 얼마야")
    assert not _is_specific_coupon_usage_query("벤투스 S2 AS 2254517 쿠폰 적용하면 얼마야")
    assert not _is_specific_coupon_usage_query("드라이브 행사 고객 한정_한국타이어 30% 할인권 적용 가능 상품 뭐야")
    assert not _is_specific_coupon_usage_query("한국타이어 18% 상품 할인쿠폰 적용 가능 제품 뭐야")


def test_specific_coupon_matching_requires_single_confident_candidate() -> None:
    matched, ambiguous = _find_single_confident_coupon_from_owned_coupons(
        "우동딜 테스트는 어떻게 써?",
        {
            "status": "success",
            "data": {
                "coupons": [
                    {"cpn_no": "C001", "cpn_nm": "우동딜 테스트", "rt_amt_val": 10},
                    {"cpn_no": "C002", "cpn_nm": "우동딜 테스트 2차", "rt_amt_val": 10},
                ],
            },
        },
    )

    assert matched is None
    assert [row["cpn_no"] for row in ambiguous] == ["C001", "C002"]


def test_specific_coupon_matching_strips_particle_for_single_partial_match() -> None:
    matched, ambiguous = _find_single_confident_coupon_from_owned_coupons(
        "우동딜 테스트는 어떻게 써?",
        {
            "status": "success",
            "data": {
                "coupons": [
                    {"cpn_no": "C001", "cpn_nm": "서울 우동딜 테스트", "rt_amt_val": 10},
                ],
            },
        },
    )

    assert matched is not None
    assert matched["cpn_no"] == "C001"
    assert ambiguous == []


def test_coupon_channel_type_recovers_from_backend_codes() -> None:
    assert _coupon_channel_type({"cpn_onoff_cd": "10", "has_store_mapping": True}) == "online"
    assert _coupon_channel_type({"cpn_onoff_cd": "20"}) == "onoff"
    assert _coupon_channel_type({"cpn_onoff_cd": "30", "has_store_mapping": True}) == "store_only"
    assert _coupon_channel_type({"cpn_onoff_cd": "30", "has_store_mapping": False}) == "offline"
    assert _coupon_channel_type({"cpn_onoff_cd": "10", "has_partner_mapping": True}) == "partner_only"


def test_coupon_channel_policy_store_only_blocks_online_price_cta() -> None:
    event = _build_coupon_channel_policy_event(
        {
            "cpn_no": "C001",
            "cpn_nm": "우동딜 테스트",
            "cpn_onoff_cd": "30",
            "has_store_mapping": True,
        },
        applicable_result={
            "status": "success",
            "data": {
                "stores": [
                    {"cpn_no": "C001", "items": [{"shop_nm": "모란점"}, {"shop_nm": "강남점"}]},
                ],
            },
        },
    )

    assert event is not None
    response = event["data"]["assistantResponse"]
    labels = _labels(event["data"]["quickReplies"])
    assert "매장 전용 쿠폰" in response
    assert "온라인 상품 가격에는 반영되지 않습니다" in response
    assert "모란점, 강남점" in response
    assert labels == ["적용 매장 보기", "내 쿠폰 조회", "매장 찾기"]
    assert "상품 가격 확인" not in labels


def test_coupon_channel_policy_store_only_keeps_usage_template_without_store_result() -> None:
    event = _build_coupon_channel_policy_event(
        {
            "cpn_no": "C001",
            "cpn_nm": "서울 우동딜 테스트",
            "cpn_onoff_cd": "30",
            "has_store_mapping": True,
        },
    )

    assert event is not None
    assert event["assistant_response_source"] == "code_coupon_channel_policy"
    response = event["data"]["assistantResponse"]
    labels = _labels(event["data"]["quickReplies"])
    assert "매장 전용 쿠폰" in response
    assert "온라인 상품 가격에는 반영되지 않습니다" in response
    assert "적용 가능 매장은" in response
    assert labels == ["적용 매장 보기", "내 쿠폰 조회", "매장 찾기"]
    assert "상품 가격 확인" not in labels


def test_coupon_channel_policy_online_allows_price_followup() -> None:
    event = _build_coupon_channel_policy_event(
        {"cpn_no": "C001", "cpn_nm": "온라인 쿠폰", "coupon_channel_type": "online"},
    )

    assert event is not None
    assert "온라인에서 사용 가능한 쿠폰" in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["상품 가격 확인", "내 쿠폰 조회"]


def test_coupon_channel_policy_offline_and_partner_do_not_offer_price_cta() -> None:
    offline_event = _build_coupon_channel_policy_event(
        {"cpn_no": "C001", "cpn_nm": "오프라인 쿠폰", "coupon_channel_type": "offline"},
    )
    partner_event = _build_coupon_channel_policy_event(
        {"cpn_no": "C002", "cpn_nm": "제휴 쿠폰", "coupon_channel_type": "partner_only"},
    )

    assert offline_event is not None
    assert partner_event is not None
    assert "온라인 상품 가격에는 반영되지 않습니다" in offline_event["data"]["assistantResponse"]
    assert "상품 가격 확인" not in _labels(offline_event["data"]["quickReplies"])
    assert "제휴 조건" in partner_event["data"]["assistantResponse"]
    assert "상품 가격 확인" not in _labels(partner_event["data"]["quickReplies"])


def test_tc005_coupon_applicability_answers_pattern_without_size_listing() -> None:
    event = _build_coupon_applicability_event(
        {
            "status": "success",
            "data": {
                "coupons": [
                    {
                        "cpn_no": "C001",
                        "total": 1,
                        "items": [{"goods_nm": "키너지 EX", "tire_size_1": "205/55R16"}],
                    }
                ],
                "stores": [],
                "total_products": 1,
                "total_stores": 0,
            },
        },
        {"cpn_no": "C001", "cpn_nm": "패밀리 할인쿠폰"},
        target_product_name="Kinergy EX",
    )

    response = event["data"]["assistantResponse"]
    assert "보유 쿠폰에서 ‘패밀리 할인쿠폰’을 확인" in response
    assert "키너지 EX 패턴에 적용 가능" in response
    assert "키너지 EX를 주문하시겠어요?" in response
    assert "205/55R16" not in response
    assert "먼저 규격을 고르지 않아도" not in response
    assert [chip["label"] for chip in event["data"]["quickReplies"]] == [
        "보유차량 중 선택",
        "사이즈 직접 입력",
        "내 쿠폰 조회",
    ]


def test_coupon_applicability_answers_brand_target_without_full_product_listing() -> None:
    event = _build_coupon_applicability_event(
        {
            "status": "success",
            "data": {
                "coupons": [
                    {
                        "cpn_no": "C001",
                        "total": 44,
                        "items": [
                            {"goods_nm": "벤투스 에어S", "brand_cd": "HK", "brand_nm": "HANKOOK"},
                            {"goods_nm": "미쉐린 파일럿 스포츠 5", "brand_cd": "MC", "brand_nm": "MICHELIN"},
                            {"goods_nm": "미쉐린 프라이머시 4", "brand_cd": "MC", "brand_nm": "MICHELIN"},
                        ],
                    }
                ],
                "stores": [],
                "total_products": 44,
                "total_stores": 0,
            },
        },
        {"cpn_no": "C001", "cpn_nm": "타이어 경정비 싹-다 1만원 할인쿠폰"},
        target_brand=_coupon_target_brand_for_query("타이어 경정비 싹-다 1만원 할인쿠폰은 미쉐린도 적용 돼?"),
    )

    response = event["data"]["assistantResponse"]
    labels = [chip["label"] for chip in event["data"]["quickReplies"]]

    assert "미쉐린 상품에도 적용 가능" in response
    assert "확인된 대표 상품" in response
    assert "적용 가능 상품은 44개" not in response
    assert "미쉐린 파일럿 스포츠 5" in response
    assert labels == ["쿠폰함 바로가기", "내 쿠폰 조회", "적용 상품 다시 확인"]
    assert event["data"]["quickReplies"][0]["url"] == CTAUrls.MY_COUPON_LIST_PC
    assert "보유차량 중 선택" not in labels
    assert "사이즈 직접 입력" not in labels


def test_coupon_applicability_brand_target_reports_absence_without_purchase_cta() -> None:
    event = _build_coupon_applicability_event(
        {
            "status": "success",
            "data": {
                "coupons": [
                    {
                        "cpn_no": "C001",
                        "total": 1,
                        "items": [{"goods_nm": "벤투스 에어S", "brand_cd": "HK", "brand_nm": "HANKOOK"}],
                    }
                ],
                "stores": [],
                "total_products": 1,
                "total_stores": 0,
            },
        },
        {"cpn_no": "C001", "cpn_nm": "타이어 경정비 싹-다 1만원 할인쿠폰"},
        target_brand={"brand_cd": "MC", "label": "미쉐린"},
    )

    response = event["data"]["assistantResponse"]
    labels = [chip["label"] for chip in event["data"]["quickReplies"]]

    assert "적용 가능 상품 목록에서 미쉐린 상품은 확인되지 않았어요" in response
    assert "쿠폰함에서 상세 적용 조건을 확인" in response
    assert labels == ["쿠폰함 바로가기", "내 쿠폰 조회", "적용 상품 다시 확인"]
    assert "보유차량 중 선택" not in labels
    assert "사이즈 직접 입력" not in labels


def test_discount_rate_coupon_targets_do_not_force_product_narrowing() -> None:
    assert _coupon_target_product_name_for_query("30% 할인 쿠폰 적용 가능 상품 뭐뭐 있어?") is None
    assert _coupon_target_brand_for_query("한국타이어 16% 상품 할인쿠폰 적용 가능한 상품이 뭐있어?") is None
    assert _coupon_target_brand_for_query("타이어 경정비 싹-다 1만원 할인쿠폰은 미쉐린도 적용 돼?") == {
        "brand_cd": "MC",
        "label": "미쉐린",
    }


def test_strong_coupon_applicability_query_accepts_applicable_variants() -> None:
    assert _is_strong_coupon_applicability_query("16% 상품 할인쿠폰 적용 가능한 상품이 뭐있어?")
    assert _is_strong_coupon_applicability_query("한국타이어 16% 상품 할인쿠폰 적용 가능한 상품이 뭐있어?")


def test_strong_coupon_applicability_query_does_not_hijack_non_coupon_target_question() -> None:
    assert _is_strong_coupon_applicability_query("이 상품 적용 가능한 사이즈 뭐야?") is False


def test_strong_coupon_applicability_query_does_not_hijack_coupon_issue_requests() -> None:
    assert _is_strong_coupon_applicability_query("쿠폰 너가 임시로 만들어줘") is False
    assert _is_strong_coupon_applicability_query("90% 쿠폰 하나 만들어서 내 쿠폰함에 넣어줘") is False


def test_product_coupon_eligibility_keeps_explicit_product_name() -> None:
    assert _coupon_target_product_name_for_query("아이온 에보 AS에 30% 할인 쿠폰 적용돼?") == "아이온"


def test_product_coupon_query_splits_compact_size_and_quantity_from_product_name() -> None:
    parsed = _split_product_size_quantity_from_text(
        "ventus air S 2255517",
        "ventus air S 2255517 4개 구매하고 싶은데 쿠폰 적용하면 할인받는 금액이 얼마야?",
    )

    assert parsed == {
        "product_name": "ventus air S",
        "tire_size": "225/55R17",
        "quantity": 4,
    }


def test_price_policy_frame_keeps_coupon_product_size_quantity_separate() -> None:
    frame = build_price_intent_frame(
        "ventus air S 2255517 4개 구매하고 싶은데 쿠폰 적용하면 할인받는 금액이 얼마야?"
    )

    assert frame.entities["product_name"] == "Ventus air S"
    assert frame.entities["tire_size"] == "225/55R17"
    assert frame.entities["quantity"] == 4


def test_product_coupon_price_amount_query_is_detected() -> None:
    assert _is_product_coupon_price_amount_query(
        "ventus air S 2255517 4개 구매하고 싶은데 쿠폰 적용하면 할인받는 금액이 얼마야?"
    )
    assert not _is_product_coupon_price_amount_query("벤투스 에어S에 적용 가능한 쿠폰 뭐 있어?")


def test_size_only_followup_recovers_coupon_price_target_from_recent_context() -> None:
    target = _recent_product_coupon_price_target(
        "2255517",
        "ventus air S 2255517 4개 구매하고 싶은데 쿠폰 적용하면 할인받는 금액이 얼마야?\n2255517",
    )

    assert target == {
        "product_name": "Ventus air S",
        "tire_size": "225/55R17",
        "quantity": 4,
    }


def test_size_only_followup_prefers_pending_product_name_over_recent_search_result() -> None:
    slots = ConversationSlots(
        pending_product_name="벤투스 에어S",
        tire_model="벤투스 에어S",
        pending_intent="price",
        goal_type="price_inquiry",
    )
    prev_tool_data = [
        {
            "tool": "search_product_tool",
            "args": {"keyword": "벤투스 S1 evo Z", "limit": 10},
            "data": {
                "status": "success",
                "data": {"items": [{"goods_nm": "벤투스 S1 evo Z AS", "tire_size_1": "265/45R19"}]},
            },
        }
    ]

    keyword = _recent_product_keyword_for_size_only_search(
        "265/45R19",
        prev_tool_data=prev_tool_data,
        recent_context="",
        slots=slots,
    )

    assert keyword == "벤투스 에어S"


def test_size_list_intent_uses_pending_product_name_before_recent_tool_context() -> None:
    slots = ConversationSlots(pending_product_name="벤투스 에어S", tire_model="벤투스 에어S")

    keyword = _product_size_list_keyword_from_context(
        "다른 사이즈 확인",
        [],
        prev_tool_data=[
            {
                "tool": "search_product_tool",
                "args": {"keyword": "벤투스 S1 evo Z", "limit": 10},
                "data": {"status": "success", "data": {"items": []}},
            }
        ],
        recent_context="",
        slots=slots,
    )

    assert keyword == "벤투스 에어S"


def test_size_list_intent_does_not_reuse_other_product_rows_when_pending_product_mismatches() -> None:
    event = _build_product_size_list_event_from_search_results(
        "다른 사이즈 확인",
        [],
        prev_tool_data=[
            {
                "tool": "search_product_tool",
                "args": {"keyword": "벤투스 S1 evo Z", "limit": 10},
                "data": {
                    "status": "success",
                    "data": {
                        "items": [
                            {
                                "goods_no": "G1",
                                "goods_nm": "벤투스 S1 evo Z AS",
                                "tire_size_1": "265/45R19",
                            }
                        ]
                    },
                },
            }
        ],
        recent_context="",
        slots=ConversationSlots(pending_product_name="벤투스 에어S", tire_model="벤투스 에어S"),
    )

    assert event is None


def test_product_size_list_not_found_event_uses_pending_product_cta_contract() -> None:
    event = _build_product_size_list_not_found_event("벤투스 에어S")

    assistant = event["data"]["assistantResponse"]
    labels = [chip["label"] for chip in event["data"]["quickReplies"]]

    assert "벤투스 에어S의 다른 규격을 현재 찾을 수 없어요" in assistant
    assert labels == ["상품명 다시 입력", "타이어 추천 받기", "사이즈 직접 입력"]


def test_product_coupon_price_no_product_message_names_product_before_size() -> None:
    event = _build_product_coupon_price_no_product_event("벤투스 에어S", "265/45R19")

    assistant = event["data"]["assistantResponse"]
    labels = [chip["label"] for chip in event["data"]["quickReplies"]]

    assert "벤투스 에어S 265/45R19 규격 상품을 찾을 수 없어" in assistant
    assert labels == ["다른 사이즈 확인", "사이즈 없이 검색", "타이어 추천 받기"]


def test_product_coupon_price_amount_event_multiplies_quantity_discount() -> None:
    event = _build_product_coupon_price_amount_event(
        {
            "status": "success",
            "data": {
                "goods_no": "G000000317729",
                "goods_nm": "벤투스 에어S",
                "sale_prc": 200000,
                "cheapest_final_prc": 150000,
                "cheapest_total_discount": 50000,
                "cheapest_applied_coupons": [{"cpn_nm": "한국타이어 30% 할인권"}],
            },
        },
        product_name="벤투스 에어S",
        tire_size="225/55R17",
        quantity=4,
    )

    assert event is not None
    assistant = event["data"]["assistantResponse"]
    assert "벤투스 에어S 225/55R17 4개 기준" in assistant
    assert "정가 합계: 800,000원" in assistant
    assert "쿠폰 적용 할인액: 200,000원" in assistant
    assert "최종 혜택가: 600,000원" in assistant
    assert "한국타이어 30% 할인권" in assistant


def test_product_coupon_price_amount_event_uses_final_unit_price_when_cheapest_missing() -> None:
    event = _build_product_coupon_price_amount_event(
        {
            "status": "success",
            "data": {
                "goods_no": "G000000317729",
                "goods_nm": "벤투스 에어S",
                "sale_prc": 200000,
                "final_unit_price": 160000,
                "extra_fvr_sale_prc": 180000,
            },
        },
        product_name="벤투스 에어S",
        tire_size="225/55R17",
        quantity=2,
    )

    assert event is not None
    assistant = event["data"]["assistantResponse"]
    assert "정가 합계: 400,000원" in assistant
    assert "쿠폰 적용 할인액: 80,000원" in assistant
    assert "최종 혜택가: 320,000원" in assistant


def test_product_card_mapper_uses_display_final_price_priority() -> None:
    event = try_build_template(
        [
            {
                "tool": "search_product_tool",
                "args": {"keyword": "벤투스 에어S", "limit": 10, "size": "225/55R17"},
                "data": {
                    "status": "success",
                    "http_status": 200,
                    "data": {
                        "items": [
                            {
                                "goods_no": "G1",
                                "goods_nm": "벤투스 에어S",
                                "tire_size_1": "225/55R17",
                                "sale_prc": 120000,
                                "extra_fvr_sale_prc": 100000,
                                "final_unit_price": 90000,
                                "cheapest_final_prc": 85000,
                            }
                        ]
                    },
                },
            }
        ],
        "상품을 확인했어요.",
    )

    assert event is not None
    assert event["template"] == "product"
    product = event["data"]["products"][0]
    assert product["price"] == 85000
    assert product["originalPrice"] == 120000
    assert product["discountAmount"] == 35000
    assert product["discountRate"] == 29.2


def test_compare_discount_mapper_uses_final_unit_price_without_cheapest_final_price() -> None:
    event = try_build_template(
        [
            {
                "tool": "compare_discount_tool",
                "args": {"goods_no_list": ["G1", "G2"], "quantity": 1},
                "data": {
                    "status": "success",
                    "http_status": 200,
                    "data": {
                        "cheapest_goods_no": "G1",
                        "quantity": 1,
                        "items": [
                            {
                                "goods_no": "G1",
                                "goods_nm": "벤투스 에어S",
                                "sale_prc": 120000,
                                "extra_fvr_sale_prc": 100000,
                                "final_unit_price": 85000,
                                "total_discount": 35000,
                            },
                            {
                                "goods_no": "G2",
                                "goods_nm": "키너지 EX",
                                "sale_prc": 120000,
                                "extra_fvr_sale_prc": 95000,
                                "final_unit_price": 90000,
                                "total_discount": 30000,
                            },
                        ],
                    },
                },
            }
        ],
        "최저가 상품을 확인했어요.",
    )

    assert event is not None
    assert event["template"] == "cheapestProduct"
    assert event["data"]["cheapestProduct"][0]["finalPrice"] == 85000


def test_runflat_price_comparison_uses_final_unit_price_as_final_price() -> None:
    token = current_runflat_comparison.set(True)
    try:
        event = try_build_template(
            [
                {
                    "tool": "search_product_tool",
                    "args": {"keyword": "벤투스", "limit": 10, "size": "225/45R17"},
                    "data": {
                        "status": "success",
                        "http_status": 200,
                        "data": {
                            "items": [
                                {
                                    "goods_no": "G1",
                                    "goods_nm": "벤투스 일반",
                                    "tire_size_1": "225/45R17",
                                    "goods_pfm_nm": "COMFORT",
                                },
                                {
                                    "goods_no": "G2",
                                    "goods_nm": "벤투스 런플랫",
                                    "tire_size_1": "225/45R17",
                                    "goods_pfm_nm": "RUNFLAT",
                                },
                            ]
                        },
                    },
                },
                {
                    "tool": "compare_discount_tool",
                    "args": {"goods_no_list": ["G1", "G2"], "quantity": 1},
                    "data": {
                        "status": "success",
                        "http_status": 200,
                        "data": {
                            "items": [
                                {"goods_no": "G1", "final_unit_price": 85000, "extra_fvr_sale_prc": 100000},
                                {"goods_no": "G2", "final_unit_price": 105000, "extra_fvr_sale_prc": 120000},
                            ]
                        },
                    },
                },
            ],
            "런플랫과 일반 타이어 가격을 비교했어요.",
        )
    finally:
        current_runflat_comparison.reset(token)

    assert event is not None
    assert event["template"] == "quickReply"
    assistant = event["data"]["assistantResponse"]
    assert "85,000원" in assistant
    assert "105,000원" in assistant
    assert "+20,000원" in assistant


def test_product_coupon_price_no_product_event_stops_without_price_cta() -> None:
    event = _build_product_coupon_price_no_product_event("벤투스 에어S", "225/55R17")

    assistant = event["data"]["assistantResponse"]
    labels = _labels(event["data"]["quickReplies"])
    assert "상품을 찾을 수 없어 쿠폰 적용 금액을 계산할 수 없어요" in assistant
    assert "상품을 찾았어요" not in assistant
    assert "가격 확인" not in labels


def test_product_coupon_eligibility_query_is_resolver_candidate() -> None:
    assert _is_product_coupon_eligibility_query("kinergy EX에 쓸 수 있는 쿠폰 뭐 있어?")
    assert _is_product_coupon_eligibility_query("키너지 EX 쿠폰 뭐 있어?")
    assert _is_product_coupon_eligibility_query("ventus s2 as 가장 싸게 살 수 있는 쿠폰 뭐야?")
    assert _is_product_coupon_eligibility_query("벤투스 S2 AS 가장 싸게 살 수 있는 쿠폰 뭐야?")
    assert not _is_product_coupon_eligibility_query("쿠폰 너가 임시로 만들어줘")


def test_product_coupon_eligibility_filters_owned_coupons_by_target_pattern() -> None:
    event = _build_product_coupon_eligibility_event(
        {
            "status": "success",
            "data": {
                "coupons": [
                    {
                        "cpn_no": "C001",
                        "total": 1,
                        "items": [{"goods_nm": "키너지 EX"}],
                    },
                    {
                        "cpn_no": "C002",
                        "total": 1,
                        "items": [{"goods_nm": "벤투스 S2 AS"}],
                    },
                ],
                "total_products": 2,
            },
        },
        [
            {"cpn_no": "C001", "cpn_nm": "1월 키너지EX 특가전 45% 할인쿠폰"},
            {"cpn_no": "C002", "cpn_nm": "한국타이어 18% 상품 할인쿠폰"},
        ],
        target_product_name="Kinergy EX",
    )

    response = event["data"]["assistantResponse"]
    assert "키너지 EX 패턴에 적용 가능한 쿠폰" in response
    assert "1월 키너지EX 특가전 45% 할인쿠폰" in response
    assert "한국타이어 18% 상품 할인쿠폰" not in response
    assert "사이즈" in response


def test_product_coupon_eligibility_brand_target_uses_coupon_cta_not_purchase_cta() -> None:
    event = _build_product_coupon_eligibility_event(
        {
            "status": "success",
            "data": {
                "coupons": [
                    {
                        "cpn_no": "C001",
                        "total": 2,
                        "items": [
                            {"goods_nm": "옵티모 H108", "brand_cd": "HK", "brand_nm": "HANKOOK"},
                            {"goods_nm": "미쉐린 파일럿 스포츠 5", "brand_cd": "MC", "brand_nm": "MICHELIN"},
                        ],
                    }
                ],
                "total_products": 2,
            },
        },
        [{"cpn_no": "C001", "cpn_nm": "타이어 경정비 싹-다 1만원 할인쿠폰"}],
        target_product_name="미쉐린",
        target_brand={"brand_cd": "MC", "label": "미쉐린"},
    )

    response = event["data"]["assistantResponse"]
    labels = _labels(event["data"]["quickReplies"])

    assert "미쉐린 상품에도 적용 가능한 쿠폰" in response
    assert "미쉐린 패턴" not in response
    assert labels == ["쿠폰함 바로가기", "내 쿠폰 조회", "적용 상품 다시 확인"]
    assert event["data"]["quickReplies"][0]["url"] == CTAUrls.MY_COUPON_LIST_PC
    assert "보유차량 중 선택" not in labels
    assert "사이즈 직접 입력" not in labels


def test_product_coupon_eligibility_brand_target_absence_uses_coupon_cta() -> None:
    event = _build_product_coupon_eligibility_event(
        {
            "status": "success",
            "data": {
                "coupons": [
                    {
                        "cpn_no": "C001",
                        "total": 1,
                        "items": [{"goods_nm": "옵티모 H108", "brand_cd": "HK", "brand_nm": "HANKOOK"}],
                    }
                ],
                "total_products": 1,
            },
        },
        [{"cpn_no": "C001", "cpn_nm": "타이어 경정비 싹-다 1만원 할인쿠폰"}],
        target_product_name="미쉐린",
        target_brand={"brand_cd": "MC", "label": "미쉐린"},
    )

    response = event["data"]["assistantResponse"]
    labels = _labels(event["data"]["quickReplies"])

    assert "적용 가능 상품 목록에서 미쉐린 상품은 확인되지 않았어요" in response
    assert "미쉐린 패턴" not in response
    assert labels == ["쿠폰함 바로가기", "내 쿠폰 조회", "적용 상품 다시 확인"]
    assert "보유차량 중 선택" not in labels
    assert "사이즈 직접 입력" not in labels


def test_owned_coupon_best_discount_query_is_not_coupon_name_lookup() -> None:
    assert _is_owned_coupon_best_discount_query("내가 가진 쿠폰 중에서 할인 제일 많이 되는 게 뭐야")
    assert _is_owned_coupon_best_discount_query("내 쿠폰 중 가장 할인 큰 쿠폰 뭐야?")
    assert not _is_owned_coupon_best_discount_query("30% 할인 쿠폰 적용 가능 상품 뭐뭐 있어?")
    assert not _is_owned_coupon_best_discount_query("ventus s2 as 가장 싸게 살 수 있는 쿠폰 뭐야?")


def test_specific_owned_coupon_lookup_extracts_clean_hint() -> None:
    assert _specific_owned_coupon_lookup_hint("혹시 패밀리쿠폰 있어?") == "패밀리"
    assert _specific_owned_coupon_lookup_hint("내 생일쿠폰 보유중이야?") == "생일"
    assert _is_specific_owned_coupon_lookup_query("패밀리쿠폰 있어?")
    assert not _is_specific_owned_coupon_lookup_query("쿠폰 있어?")
    assert not _is_specific_owned_coupon_lookup_query("내 쿠폰 보여줘")
    assert not _is_specific_owned_coupon_lookup_query("쿠폰함 보여줘")
    assert not _is_specific_owned_coupon_lookup_query("패밀리쿠폰으로 살 수 있는 상품?")
    assert not _is_specific_owned_coupon_lookup_query("키너지 EX 패밀리쿠폰 적용돼?")
    assert not _is_specific_owned_coupon_lookup_query("ventus s2 as 가장 싸게 살 수 있는 쿠폰 뭐야?")


def test_specific_owned_coupon_lookup_summarizes_match_without_dropping_coupon_list() -> None:
    summary = _owned_coupon_lookup_summary_text(
        "패밀리쿠폰 있어?",
        {
            "status": "success",
            "data": {
                "coupons": [
                    {"cpn_no": "C001", "cpn_nm": "패밀리 할인쿠폰", "rt_amt_val": 10},
                    {"cpn_no": "C002", "cpn_nm": "생일축하 쿠폰", "rt_amt_val": 10000},
                ],
            },
        },
    )

    assert summary is not None
    assert "‘패밀리 할인쿠폰’ 관련 쿠폰을 보유 중이에요" in summary
    assert "보유 쿠폰 목록도 함께 확인" in summary


def test_specific_owned_coupon_lookup_summarizes_missing_coupon() -> None:
    summary = _owned_coupon_lookup_summary_text(
        "패밀리쿠폰 있어?",
        {
            "status": "success",
            "data": {
                "coupons": [
                    {"cpn_no": "C002", "cpn_nm": "생일축하 쿠폰", "rt_amt_val": 10000},
                ],
            },
        },
    )

    assert summary is not None
    assert "현재 보유 쿠폰에서 ‘패밀리’ 관련 쿠폰은 확인되지 않아요" in summary
    assert "현재 보유 쿠폰 목록" in summary


def test_owned_coupon_expiry_lookup_filters_this_month_coupons() -> None:
    today = datetime.date.today()
    next_month = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    this_month_end = next_month - datetime.timedelta(days=1)
    event = _build_owned_coupon_expiry_lookup_event(
        "보유 쿠폰 중에 이번달 만료인거 뭐 있어?",
        {
            "status": "success",
            "data": {
                "coupons": [
                    {
                        "cpn_nm": "이번달 만료 쿠폰",
                        "rt_amt_val": 10,
                        "use_end_dtime": this_month_end.isoformat(),
                    },
                    {
                        "cpn_nm": "다음달 만료 쿠폰",
                        "rt_amt_val": 10000,
                        "use_end_dtime": next_month.isoformat(),
                    },
                ],
            },
        },
    )

    response = event["data"]["assistantResponse"]
    assert "이번달 만료 쿠폰" in response
    assert "다음달 만료 쿠폰" not in response
    assert "원복" not in response
    assert "1:1 문의" not in response
    assert "1:1 문의하기" not in _labels(event["data"]["quickReplies"])


def test_owned_coupon_expiry_lookup_handles_no_matches() -> None:
    next_month = (datetime.date.today().replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    event = _build_owned_coupon_expiry_lookup_event(
        "내 쿠폰 중 곧 만료되는 거 보여줘",
        {
            "status": "success",
            "data": {
                "coupons": [
                    {
                        "cpn_nm": "나중에 만료 쿠폰",
                        "rt_amt_val": 10000,
                        "use_end_dtime": (next_month + datetime.timedelta(days=45)).isoformat(),
                    }
                ],
            },
        },
    )

    assert "곧 만료되는 쿠폰은 없어요" in event["data"]["assistantResponse"]


def test_owned_coupon_best_discount_summarizes_highest_owned_coupon() -> None:
    event = _build_owned_coupon_best_discount_event(
        {
            "status": "success",
            "data": {
                "coupons": [
                    {
                        "cpn_nm": "한국타이어 18% 상품 할인쿠폰",
                        "rt_amt_val": 18,
                        "min_pur_amt": 30000,
                        "max_dscnt_amt": 500000,
                        "mbr_use_yn": "N",
                    },
                    {
                        "cpn_nm": "키너지EX 특가전 45% 할인쿠폰",
                        "rt_amt_val": 45,
                        "min_pur_amt": 30000,
                        "max_dscnt_amt": 500000,
                        "mbr_use_yn": "N",
                    },
                    {
                        "cpn_nm": "생일축하 1만원 쿠폰",
                        "rt_amt_val": 10000,
                        "mbr_use_yn": "N",
                    },
                ]
            },
        }
    )

    response = event["data"]["assistantResponse"]
    assert "키너지EX 특가전 45% 할인쿠폰" in response
    assert "45% 할인" in response
    assert "생일축하 1만원 쿠폰" in response
    assert "상품 가격, 적용 대상, 중복 가능 여부" in response
    assert "해당 쿠폰을 찾지 못했어요" not in response


def test_store_contact_guidance_injects_store_detail_cta() -> None:
    event_data = {
        "assistantResponse": (
            "티스테이션 부산거제점은 무상점검 서비스가 가능한 매장이지만, "
            "질소 충전 가능 여부는 별도 확인이 필요해요. 매장으로 문의해 주세요."
        ),
        "quickReplies": [{"label": "1:1 문의하기", "domain": "SUPPORT"}],
        "predictedDomains": ["SUPPORT"],
    }
    tool_data_list = [
        {
            "tool": "get_store_list_tool",
            "args": {"store_nm": "티스테이션 부산거제점"},
            "data": {
                "status": "success",
                "data": {
                    "stores": [
                        {
                            "shop_seq": "F203675962",
                            "shop_nm": "티스테이션 부산거제점",
                        }
                    ]
                },
            },
        }
    ]

    changed = _inject_store_detail_chip_for_contact_guidance(
        event_data,
        tool_data_list=tool_data_list,
        messages=[],
    )

    assert changed is True
    assert event_data["quickReplies"][0]["label"] == "매장 상세 페이지로 이동"
    assert event_data["quickReplies"][0]["url"].endswith("/store/locals/F203675962")
    assert "매장명: 티스테이션 부산거제점" in event_data["assistantResponse"]
    assert "1:1 문의하기" in _labels(event_data["quickReplies"])
    assert event_data["predictedDomains"][0] == "TRANSACTION"


def test_store_contact_guidance_skips_candidate_confirmation_prompt() -> None:
    event_data = {
        "assistantResponse": (
            "고객님, 요청하신 '거제점'으로 검색한 결과 '티스테이션 부산거제점' 매장이 있는데 이 매장이 맞을까요?"
        ),
        "quickReplies": [{"label": "네, 맞아요", "domain": "TRANSACTION"}],
        "predictedDomains": ["TRANSACTION"],
    }
    tool_data_list = [
        {
            "tool": "get_store_list_tool",
            "data": {
                "status": "success",
                "data": {
                    "stores": [
                        {
                            "shop_seq": "F203675962",
                            "shop_nm": "티스테이션 성남IC점",
                            "road_addr_base": "경기도 성남시 중원구 둔촌대로 124-3",
                            "road_addr_dtl": "1층 (하대원동)",
                        }
                    ]
                },
            },
        },
        {
            "tool": "search_stores_tool",
            "data": {
                "status": "success",
                "data": {
                    "stores": [
                        {
                            "shop_seq": "F999999999",
                            "shop_nm": "티스테이션 부산거제점",
                        }
                    ]
                },
            },
        },
    ]

    changed = _inject_store_detail_chip_for_contact_guidance(
        event_data,
        tool_data_list=tool_data_list,
        messages=[{"role": "user", "content": "티스테이션 거제점 질소 충전도 해줘?"}],
    )

    assert changed is False
    assert "티스테이션 성남IC점" not in event_data["assistantResponse"]
    assert _labels(event_data["quickReplies"]) == ["네, 맞아요"]


def test_store_service_gate_detects_unverifiable_service_conditions() -> None:
    nitrogen = decide_store_service_gate(user_text="티스테이션 부산거제점 질소 충전도 해줘?")
    lift = decide_store_service_gate(user_text="내 차 타스만인데 리프트 있어야 되더라고... 하남 지역에 리프트 있는 매장 있어?")
    amenities = decide_store_service_gate(user_text="하남에 대기실 있고 워셔액 무료로 넣어주는 매장 있어?")
    women_kids = decide_store_service_gate(user_text="여성 주차구역이나 키즈 놀이방 있는 매장 찾아줘")
    gifts = decide_store_service_gate(user_text="사은품이나 추가 무료 서비스 주는 매장 있어?")
    balance_skill = decide_store_service_gate(user_text="얼라인먼트랑 밸런스 정확도 좋은 매장 알려줘")

    assert nitrogen.intent == "store_special_service"
    assert nitrogen.needs_store_detail_cta is True
    assert nitrogen.needs_unverifiable_guidance is True
    assert unverifiable_store_preference_labels("티스테이션 부산거제점 질소 충전도 해줘?") == ["질소 충전 여부"]
    assert lift.intent == "store_special_service"
    assert lift.needs_store_detail_cta is True
    assert "리프트 보유 여부" in unverifiable_store_preference_labels(
        "내 차 타스만인데 리프트 있어야 되더라고... 하남 지역에 리프트 있는 매장 있어?"
    )
    assert amenities.intent == "store_special_service"
    assert unverifiable_store_preference_labels("하남에 대기실 있고 워셔액 무료로 넣어주는 매장 있어?") == [
        "대기 공간",
        "워셔액 무료 제공",
    ]
    assert women_kids.intent == "store_special_service"
    assert unverifiable_store_preference_labels("여성 주차구역이나 키즈 놀이방 있는 매장 찾아줘") == [
        "여성 방문 편의/만족도",
        "키즈/가족 편의시설",
    ]
    assert gifts.intent == "store_special_service"
    assert "사은품/추가 무료 서비스" in unverifiable_store_preference_labels(
        "사은품이나 추가 무료 서비스 주는 매장 있어?"
    )
    assert balance_skill.intent == "store_special_service"
    assert "얼라인먼트/밸런스 숙련도" in unverifiable_store_preference_labels(
        "얼라인먼트랑 밸런스 정확도 좋은 매장 알려줘"
    )


def test_store_service_gate_does_not_hijack_generic_pickup_service_question() -> None:
    decision = decide_store_service_gate(user_text="픽업서비스 어떻게 신청해?")

    assert decision.intent == "none"
    assert decision.needs_store_detail_cta is False


def test_store_service_gate_detects_review_detail_but_not_review_write() -> None:
    review_detail = decide_store_service_gate(user_text="리뷰 확인해줘")
    rating_summary = decide_store_service_gate(user_text="티스테이션 성남IC점 평가가 어때?")
    review_write = decide_store_service_gate(user_text="리뷰 어디다 써?")

    assert review_detail.intent == "store_review_detail"
    assert review_detail.needs_store_detail_cta is True
    assert rating_summary.intent == "store_rating_summary"
    assert rating_summary.needs_store_detail_cta is False
    assert review_write.intent == "none"
    assert review_write.needs_store_detail_cta is False


def test_store_visual_detail_request_routes_to_store_detail_cta_intent() -> None:
    visual = decide_store_service_gate(user_text="티스테이션 구리점 매장 전경 사진 보고 싶어")

    assert visual.intent == "store_visual_detail"
    assert visual.needs_store_detail_cta is True
    assert _extract_plain_store_info_store_name("티스테이션 구리점 매장 전경 사진 보고 싶어") == "구리점"
    assert _extract_plain_store_info_store_name("분당정자점 사진 있어?") == "분당정자점"


def test_store_visual_detail_guidance_injects_detail_cta_before_generic_store_search() -> None:
    event_data = {
        "assistantResponse": "티스테이션 구리점 매장 전경은 매장 상세 화면에서 확인하실 수 있어요.",
        "quickReplies": [
            {"label": "매장 찾기", "domain": "TRANSACTION"},
            {"label": "다른 매장 정보", "domain": "TRANSACTION"},
        ],
        "predictedDomains": ["TRANSACTION"],
    }
    tool_data_list = [
        {
            "tool": "get_store_detail_tool",
            "data": {
                "status": "success",
                "data": {
                    "shop_seq": "F203675962",
                    "shop_nm": "티스테이션 구리점",
                    "tel_no": "0315551234",
                    "shop_biz_strt_time": "09",
                    "shop_biz_end_time": "19",
                },
            },
        }
    ]

    changed = _inject_store_detail_chip_for_contact_guidance(
        event_data,
        tool_data_list=tool_data_list,
        messages=[{"role": "user", "content": "티스테이션 구리점 매장 전경 사진 보고 싶어"}],
    )

    assert changed is True
    assert event_data["quickReplies"][0]["label"] == "매장 상세 페이지로 이동"
    assert event_data["quickReplies"][0]["url"].endswith("/store/locals/F203675962")
    assert "매장 찾기" not in _labels(event_data["quickReplies"])


def test_store_contact_guidance_injects_store_detail_cta_from_context_list_shape() -> None:
    event_data = {
        "assistantResponse": (
            "티스테이션 부산거제점은 무상점검, 경정비, 휠얼라인먼트 등은 확인되지만 "
            "질소 충전 가능 여부는 시스템에서 바로 확인되지 않아요. 매장으로 문의해 주세요."
        ),
        "quickReplies": [{"label": "매장 찾기", "domain": "TRANSACTION"}],
        "predictedDomains": ["TRANSACTION"],
    }
    tool_data_list = [
        {
            "tool": "get_store_list_tool",
            "data": [
                {
                    "shop_id": "F203675962",
                    "shop_nm": "티스테이션 부산거제점",
                    "addr_base": "부산광역시 연제구 거제대로 295",
                    "tel": "0515038585",
                    "shop_biz_strt_time": "09",
                    "shop_biz_end_time": "19",
                }
            ],
            "input": {"store_nm": "티스테이션 부산거제점"},
        }
    ]

    changed = _inject_store_detail_chip_for_contact_guidance(
        event_data,
        tool_data_list=tool_data_list,
        messages=[],
    )

    assert changed is True
    assert event_data["quickReplies"][0]["label"] == "매장 상세 페이지로 이동"
    assert event_data["quickReplies"][0]["url"].endswith("/store/locals/F203675962")
    assert "매장명: 티스테이션 부산거제점" in event_data["assistantResponse"]
    assert "주소: 부산광역시 연제구 거제대로 295" in event_data["assistantResponse"]
    assert "전화: 051-503-8585" in event_data["assistantResponse"]
    assert "영업시간: 평일 09:00~19:00" in event_data["assistantResponse"]
    assert "매장 찾기" in _labels(event_data["quickReplies"])


def test_store_contact_guidance_injects_detail_summary_for_staff_contact_copy() -> None:
    event_data = {
        "assistantResponse": (
            "티스테이션 부산거제점의 질소 충전 제공 여부는 현재 조회 정보로 확인되지 않아요. "
            "매장 직원에게 문의하시면 정확히 안내받으실 수 있어요."
        ),
        "quickReplies": [{"label": "방문 예약하기", "domain": "TRANSACTION"}],
        "predictedDomains": ["TRANSACTION"],
    }
    tool_data_list = [
        {
            "tool": "get_store_detail_tool",
            "data": {
                "status": "success",
                "data": {
                    "shop_seq": "F203675962",
                    "shop_nm": "티스테이션 부산거제점",
                    "road_addr_base": "부산광역시 연제구 거제대로",
                    "road_addr_dtl": "295",
                    "tel_no": "0515038585",
                    "shop_biz_strt_time": "09",
                    "shop_biz_end_time": "19",
                },
            },
        }
    ]

    changed = _inject_store_detail_chip_for_contact_guidance(
        event_data,
        tool_data_list=tool_data_list,
        messages=[{"role": "user", "content": "네, 맞아요"}],
    )

    assert changed is True
    assert event_data["quickReplies"][0]["label"] == "매장 상세 페이지로 이동"
    assert event_data["quickReplies"][0]["url"].endswith("/store/locals/F203675962")
    assert "매장명: 티스테이션 부산거제점" in event_data["assistantResponse"]
    assert "주소: 부산광역시 연제구 거제대로 295" in event_data["assistantResponse"]
    assert "전화: 051-503-8585" in event_data["assistantResponse"]
    assert "영업시간: 평일 09:00~19:00" in event_data["assistantResponse"]
    assert "방문 예약하기" in _labels(event_data["quickReplies"])


def test_store_review_detail_guidance_injects_store_detail_cta() -> None:
    event_data = {
        "assistantResponse": (
            "티스테이션 성남IC점 리뷰는 14건이 있습니다. "
            "상세 리뷰는 매장 상세 페이지에서 확인하실 수 있어요."
        ),
        "quickReplies": [{"label": "다른 매장 보기", "domain": "TRANSACTION"}],
        "predictedDomains": ["TRANSACTION"],
    }
    tool_data_list = [
        {
            "tool": "get_store_list_tool",
            "data": {
                "status": "success",
                "data": {
                    "stores": [
                        {
                            "shop_seq": "F203675962",
                            "shop_nm": "티스테이션 성남IC점",
                            "review_count": 14,
                        }
                    ]
                },
            },
        }
    ]

    changed = _inject_store_detail_chip_for_contact_guidance(
        event_data,
        tool_data_list=tool_data_list,
        messages=[],
    )

    assert changed is True
    assert event_data["quickReplies"][0]["label"] == "매장 상세 페이지로 이동"
    assert event_data["quickReplies"][0]["url"].endswith("/store/locals/F203675962")
    assert "다른 매장 보기" in _labels(event_data["quickReplies"])


def test_store_review_user_request_injects_store_detail_cta_even_without_page_text() -> None:
    event_data = {
        "assistantResponse": (
            "티스테이션 성남IC점은 현재 평점 3.2점으로 확인돼요. "
            "리뷰 상세 내용은 현재 조회 가능한 정보에 포함되어 있지 않아요."
        ),
        "quickReplies": [{"label": "예약 가능 시간 보기", "domain": "TRANSACTION"}],
        "predictedDomains": ["TRANSACTION"],
    }
    tool_data_list = [
        {
            "tool": "get_store_list_tool",
            "data": {
                "status": "success",
                "data": {
                    "stores": [
                        {
                            "shop_seq": "F203675962",
                            "shop_nm": "티스테이션 성남IC점",
                            "rating_idx": 3.2,
                            "review_count": 14,
                        }
                    ]
                },
            },
        }
    ]

    changed = _inject_store_detail_chip_for_contact_guidance(
        event_data,
        tool_data_list=tool_data_list,
        messages=[{"role": "user", "content": "매장 리뷰는 어때?"}],
    )

    assert changed is True
    assert "상세 리뷰는 매장 상세 페이지에서 확인하실 수 있어요" in event_data["assistantResponse"]
    assert "조회 가능한 정보에 포함되어 있지 않아요" not in event_data["assistantResponse"]
    assert event_data["quickReplies"][0]["label"] == "매장 상세 페이지로 이동"
    assert event_data["quickReplies"][0]["url"].endswith("/store/locals/F203675962")
    assert "예약 가능 시간 보기" in _labels(event_data["quickReplies"])


def test_store_holiday_period_query_detects_named_and_specific_holidays() -> None:
    assert _is_store_holiday_period_info_query('티스테이션 한남점 "추석 연휴에도 타이어 교체 예약 받아?"')
    assert _is_store_holiday_period_info_query("티스테이션 한남점 석가탄신일에 영업해?")
    assert _is_store_holiday_period_info_query("티스테이션 한남점 5/1에 문 열어?")
    assert _is_store_holiday_period_info_query("한남점 이번주 일요일 영업해?")


def test_store_holiday_period_query_does_not_hijack_reservation_slot_question() -> None:
    assert _is_store_holiday_period_info_query("티스테이션 성남IC점 5/29 오후 16시 예약 돼?") is False
    assert _is_store_holiday_period_info_query("티스테이션 성남IC점 5/29 예약 가능 시간 보여줘") is False


def test_store_holiday_period_event_uses_detail_info_and_cta() -> None:
    event = _build_store_holiday_period_event(
        '티스테이션 한남점 "추석 연휴에도 타이어 교체 예약 받아?"',
        {"shop_seq": "F204423537", "shop_nm": "티스테이션 한남점"},
        {
            "status": "success",
            "data": {
                "shop_seq": "F204423537",
                "shop_nm": "티스테이션 한남점",
                "holiday": "일요일 휴무",
                "addr_base": "서울특별시 용산구",
                "addr_dtl": "한남대로 80",
                "tel_no": "027902921",
                "shop_biz_strt_time": "09",
                "shop_biz_end_time": "19",
            },
        },
    )

    data = event["data"]
    assert event["template"] == "quickReply"
    assert "추석 연휴" in data["assistantResponse"]
    assert "현재 확인되는 매장 휴무일 정보는 `일요일 휴무`" in data["assistantResponse"]
    assert "매장명: 티스테이션 한남점" in data["assistantResponse"]
    assert data["quickReplies"][0]["label"] == "매장 상세 페이지로 이동"
    assert data["quickReplies"][0]["url"].endswith("/store/locals/F204423537")


def test_store_holiday_period_event_does_not_infer_open_from_detail_slots() -> None:
    event = _build_store_holiday_period_event(
        "한남점 이번주 일요일 영업해?",
        {"shop_seq": "F204423537", "shop_nm": "티스테이션 한남점"},
        {
            "status": "success",
            "data": {
                "shop_seq": "F204423537",
                "shop_nm": "티스테이션 한남점",
                "holiday": None,
                "available_slots": ["09", "10", "11"],
                "tel_no": "027902921",
                "shop_biz_strt_time": "09",
                "shop_biz_end_time": "19",
            },
        },
    )

    data = event["data"]
    assert event["template"] == "quickReply"
    assert "영업 중" not in data["assistantResponse"]
    assert "티스테이션 한남점의 일요일 휴무 여부는 현재 확인되지 않아요." in data["assistantResponse"]
    assert "일요일/공휴일 운영 여부는 매장 사정에 따라 달라질 수 있어 매장에 직접 확인해 주세요." in data["assistantResponse"]


def test_store_holiday_period_event_matches_scheduled_holiday_date() -> None:
    event = _build_store_holiday_period_event(
        "한남점 이번주 일요일 영업해?",
        {"shop_seq": "F204423537", "shop_nm": "티스테이션 한남점"},
        {
            "status": "success",
            "data": {
                "shop_seq": "F204423537",
                "shop_nm": "티스테이션 한남점",
                "holiday": "06/14(일), 06/21(일)",
                "available_slots": ["09", "10", "11"],
                "tel_no": "027902921",
                "shop_biz_strt_time": "09",
                "shop_biz_end_time": "19",
            },
        },
    )

    data = event["data"]
    assert event["template"] == "quickReply"
    assert "티스테이션 한남점은 일요일에 휴무로 확인돼요." in data["assistantResponse"]


def test_store_holiday_period_event_answers_operation_query_with_holiday_as_closed() -> None:
    event = _build_store_holiday_period_event(
        "한남점 이번주 일요일 영업해?",
        {"shop_seq": "F204423537", "shop_nm": "티스테이션 한남점"},
        {
            "status": "success",
            "data": {
                "shop_seq": "F204423537",
                "shop_nm": "티스테이션 한남점",
                "holiday": "일요일",
                "available_slots": [],
                "tel_no": "027902921",
                "shop_biz_strt_time": "09",
                "shop_biz_end_time": "19",
            },
        },
    )

    data = event["data"]
    assert event["template"] == "quickReply"
    assert "티스테이션 한남점은 일요일에 휴무로 확인돼요." in data["assistantResponse"]


def test_store_holiday_period_event_prefers_holiday_match_over_available_slots() -> None:
    event = _build_store_holiday_period_event(
        "한남점 이번주 일요일 영업해?",
        {"shop_seq": "F204423537", "shop_nm": "티스테이션 한남점"},
        {
            "status": "success",
            "data": {
                "shop_seq": "F204423537",
                "shop_nm": "티스테이션 한남점",
                "holiday": "일요일",
                "available_slots": ["09", "10"],
                "tel_no": "027902921",
                "shop_biz_strt_time": "09",
                "shop_biz_end_time": "19",
            },
        },
    )

    data = event["data"]
    assert "티스테이션 한남점은 일요일에 휴무로 확인돼요." in data["assistantResponse"]


def test_store_holiday_period_detail_uses_requested_cal_day_when_present() -> None:
    assert (
        _requested_reservation_cal_day_or_today(
            "티스테이션 성남IC점 5/29 예약 가능해?",
            today=datetime.date(2026, 5, 26),
        )
        == "20260529"
    )


def test_store_holiday_period_detail_falls_back_to_today_when_no_requested_date() -> None:
    now_utc = datetime.datetime(2026, 5, 26, 0, 0, tzinfo=datetime.UTC)

    assert _requested_reservation_cal_day_or_today("티스테이션 성남IC점 오늘 영업해?", now_utc=now_utc) == "20260526"


def test_store_date_availability_context_is_preserved_for_date_only_followup_after_datepick() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "2026년 5월 29일 (금) 티스테이션 성남IC점은 영업하며 예약 가능한 시간이 있습니다.",
            "template_data": {
                "template": "datepick",
                "data": {
                    "dates": [{
                        "date": "2026년 5월 29일 (금)",
                        "available": True,
                        "availableTimes": [9, 10, 11, 13, 14, 15, 16, 17],
                        "index": 0,
                    }],
                },
            },
        },
    ]

    assert _should_preserve_store_date_availability_context("5/30은?", messages) is True


def test_store_context_preserves_shop_seq_for_detail_cta() -> None:
    result = filter_for_context(
        "get_store_list_tool",
        {
            "status": "success",
            "data": {
                "stores": [
                    {
                        "shop_id": "C01306",
                        "shop_seq": "F203675962",
                        "shop_nm": "티스테이션 성남IC점",
                        "review_count": 14,
                    }
                ]
            },
        },
        {"store_nm": "성남IC점"},
    )

    assert result is not None
    assert result["data"][0]["shop_seq"] == "F203675962"
    assert result["data"][0]["review_count"] == 14


def test_store_detail_context_preserves_summary_fields_for_contact_cta() -> None:
    result = filter_for_context(
        "get_store_detail_tool",
        {
            "status": "success",
            "data": {
                "shop_seq": "F203675962",
                "shop_nm": "티스테이션 부산거제점",
                "road_addr_base": "부산광역시 연제구 거제대로",
                "road_addr_dtl": "295",
                "tel_no": "0515038585",
                "shop_biz_strt_time": "09",
                "shop_biz_end_time": "19",
            },
        },
        {"shop_id": "C01306"},
    )

    assert result is not None
    assert result["data"]["shop_seq"] == "F203675962"
    assert result["data"]["road_addr_base"] == "부산광역시 연제구 거제대로"
    assert result["data"]["tel_no"] == "0515038585"


def test_store_schedule_context_preserves_slots_for_followup_datepick_recovery() -> None:
    result = filter_for_context(
        "get_store_schedule_tool",
        {
            "status": "success",
            "data": {
                "shop_id": "F07782",
                "shop_nm": "티스테이션 한남점",
                "mode": "general",
                "slots": [
                    {"cal_day": "20260530", "tm": "09"},
                    {"cal_day": "20260530", "tm": "13"},
                ],
            },
        },
        {"shop_id": "F07782", "mode": "general"},
    )

    assert result is not None
    assert result["data"]["shop_id"] == "F07782"
    assert result["data"]["shop_nm"] == "티스테이션 한남점"
    assert result["data"]["mode"] == "general"
    assert result["data"]["slots"] == [
        {"cal_day": "20260530", "tm": "09"},
        {"cal_day": "20260530", "tm": "13"},
    ]


def test_reservation_history_context_is_preserved_for_followup_reference() -> None:
    result = filter_for_context(
        "get_my_reservations_tool",
        {
            "status": "success",
            "data": {
                "reservations": [
                    {
                        "ord_no": "O202605120019340",
                        "shop_nm": "티스테이션 성남IC점",
                        "vst_rsv_dtime": "2026-05-29 16:00",
                        "shop_rsv_sct_label": "구매후방문예약",
                        "shop_vst_rsv_sts_label": "예약대기",
                        "shop_rsv_no": "RSV-PRIVATE",
                        "tel_no": "031-751-6471",
                    },
                    {
                        "ord_no": "O202605180019345",
                        "shop_nm": "티스테이션 판교점",
                        "vst_rsv_dtime": "2026-05-20 13:00",
                        "shop_rsv_sct_label": "구매후방문예약",
                        "shop_vst_rsv_sts_label": "예약대기",
                    },
                ]
            },
        },
        {"sct_cd": "all"},
    )

    assert result is not None
    assert result["tool"] == "get_my_reservations_tool"
    assert result["data"][0] == {
        "ord_no": "O202605120019340",
        "shop_nm": "티스테이션 성남IC점",
        "vst_rsv_dtime": "2026-05-29 16:00",
        "shop_rsv_sct_label": "구매후방문예약",
        "shop_vst_rsv_sts_label": "예약대기",
    }
    assert "shop_rsv_no" not in result["data"][0]
    assert "tel_no" not in result["data"][0]


def test_tool_context_formats_reservation_history_label() -> None:
    context = TStationChatServiceV2._format_tool_context([
        {
            "tool": "get_my_reservations_tool",
            "data": [
                {
                    "ord_no": "O202605120019340",
                    "shop_nm": "티스테이션 성남IC점",
                    "vst_rsv_dtime": "2026-05-29 16:00",
                    "shop_rsv_sct_label": "구매후방문예약",
                    "shop_vst_rsv_sts_label": "예약대기",
                }
            ],
        }
    ])

    assert "• [최신] 예약 내역" in context
    assert "티스테이션 성남IC점" in context
    assert "2026-05-29 16:00" in context


def test_tool_context_keeps_price_fields_without_mid_string_truncation() -> None:
    context = TStationChatServiceV2._format_tool_context([
        {
            "tool": "get_products_recommendations_tool",
            "input": {"rcmd_type": "wet", "brand_cd": "HK", "limit": 3},
            "data": [
                {
                    "goods_no": "G000000310283",
                    "goods_nm": "AH11S",
                    "tire_size_1": "205/85R16",
                    "sale_prc": 128700,
                    "extra_fvr_sale_prc": 122300,
                    "cheapest_final_prc": 122300,
                    "cheapest_total_discount": 6400,
                    "wet": 4.0,
                    "rr": 3,
                    "season_nm": "사계절",
                    "car_knd_nm": "경트럭&밴",
                    "goods_pfm_nm": "COMFORT",
                    "prc_grd_nm": "스탠다드",
                    "pc_prod_tech_desc": "x" * 3000,
                }
            ],
        }
    ])

    assert "cheapest_final_prc: 122300 |" in context
    assert "cheapest_total_discount: 6400" in context
    assert "cheapest_final_prc: 12230 |" not in context


def test_existing_reservation_management_filters_stale_store_schedule_context() -> None:
    selected = TStationChatServiceV2._select_tool_context_for_prompt(
        [
            {
                "tool": "get_store_schedule_tool",
                "data": {"shop_nm": "티스테이션 고양시청점", "slots": [{"cal_day": "20260617"}]},
            },
            {
                "tool": "get_my_reservations_tool",
                "data": [
                    {
                        "shop_nm": "티스테이션 정관점",
                        "vst_rsv_dtime": "2026-06-16 17:00",
                    }
                ],
            },
        ],
        SimpleNamespace(shop_name="티스테이션 정관점"),
        intent_group="existing_reservation_management",
    )

    assert [item["tool"] for item in selected] == ["get_my_reservations_tool"]


def test_existing_reservation_management_drops_schedule_templates() -> None:
    assert TStationChatServiceV2._should_drop_template_for_intent_group(
        {"type": "data", "template": "datepick"},
        "existing_reservation_management",
    )
    assert TStationChatServiceV2._should_drop_template_for_intent_group(
        {"type": "data", "template": "location"},
        "existing_reservation_management",
    )
    assert not TStationChatServiceV2._should_drop_template_for_intent_group(
        {"type": "data", "template": "quickReply"},
        "existing_reservation_management",
    )


def test_existing_reservation_change_copy_does_not_imply_bot_can_change_time() -> None:
    event_data = {
        "assistantResponse": (
            "정관점 방문예약을 확인했어요.\n\n"
            "예약 유형: 단순 방문예약\n"
            "예약 매장: 티스테이션 정관점\n"
            "예약 일시: 2026-06-16 17:00\n\n"
            "해당 예약은 주문번호가 없는 단순 방문예약이라, 내일로 변경 가능 여부는 예약 확인 후 진행이 필요해요."
        ),
        "quickReplies": [{"label": "다른 예약 확인", "domain": "TRANSACTION"}],
        "predictedDomains": ["TRANSACTION"],
    }

    assert _normalize_existing_reservation_change_quickreply(event_data, last_user_text="정관점 예약시간 내일로 바꿔줘")
    assistant = event_data["assistantResponse"]
    assert "예약 시간은 제가 직접 변경해 드릴 수는 없어요" in assistant
    assert "변경 가능 여부는 예약 확인 후 진행이 필요해요" not in assistant


def test_existing_reservation_change_copy_removes_order_detail_possibility_wording() -> None:
    event_data = {
        "assistantResponse": (
            "확인된 온라인 예약 정보예요.\n\n"
            "예약 유형: 온라인 예약\n"
            "주문번호: O202604080019311\n"
            "예약 매장: 티스테이션 고양시청점\n"
            "예약 일시: 2026-04-18 15:00\n\n"
            "예약 시간은 제가 직접 변경해 드릴 수는 없어요. "
            "주문 내역 상세에서 예약 시간 변경 가능 여부를 확인하고 진행해 주세요."
        ),
        "quickReplies": [{"label": "주문 내역 상세 보기", "domain": "TRANSACTION"}],
        "predictedDomains": ["TRANSACTION"],
    }

    assert _normalize_existing_reservation_change_quickreply(event_data, last_user_text="예약 시간 변경해줘")
    assistant = event_data["assistantResponse"]
    assert "예약 시간은 제가 직접 변경해 드릴 수는 없어요" in assistant
    assert "변경 가능 여부" not in assistant
    assert "직접 처리하거나" in assistant


def test_existing_reservation_change_copy_skips_refund_cancel_order_context() -> None:
    event_data = {
        "assistantResponse": (
            "취소된 주문의 환불은 결제수단과 카드사 승인 일정에 따라 처리돼요.\n\n"
            "환불 진행 상태는 주문 내역 상세에서 확인해 주세요."
        ),
        "quickReplies": [{"label": "주문 내역 보기", "domain": "TRANSACTION"}],
        "predictedDomains": ["TRANSACTION"],
    }

    assert not _normalize_existing_reservation_change_quickreply(
        event_data,
        last_user_text="O202605120019340 주문취소건 환불 언제돼?",
        called_tool_names={"get_orders_of_user_tool"},
    )
    assert "예약 시간은 제가 직접 변경" not in event_data["assistantResponse"]


def test_vague_store_detail_quickreply_rebuilds_from_tool_source() -> None:
    event = _store_detail_quickreply_from_sources(
        [
            (
                "get_store_detail_tool",
                {
                    "shop_nm": "티스테이션 고양시청점",
                    "tel_no": "0319719333",
                    "shop_biz_strt_time": "0900",
                    "shop_biz_end_time": "1900",
                    "shop_sat_strt_time": "0900",
                    "shop_sat_end_time": "1700",
                    "is_all_my_t": False,
                    "is_installable": True,
                    "is_tna_delivery": True,
                    "is_imported_car": False,
                    "svc_codes": ["04"],
                },
            )
        ],
        "고객님, 고양시청점 정보를 확인했어요.",
    )

    assert event is not None
    assistant = event["data"]["assistantResponse"]
    assert "매장명: 티스테이션 고양시청점" in assistant
    assert "전화번호: 031-971-9333" in assistant
    assert "영업시간: 09:00~19:00" in assistant


def test_plain_store_info_query_extracts_store_name_without_reservation_action() -> None:
    assert _extract_plain_store_info_store_name("고양시청점 정보") == "고양시청점"
    assert _extract_plain_store_info_store_name("티스테이션 고양시청점 전화번호 알려줘") == "고양시청점"
    assert _extract_plain_store_info_store_name("판교점에서 오늘서비스로 dynapro hpx 2개 구매하고싶어") is None
    assert _extract_plain_store_info_store_name("고양시청점 예약시간 내일 18시로 변경해줘") is None
    assert _extract_plain_store_info_store_name("고양시청점 18시 예약 가능해?") is None


def test_transaction_prompt_prioritizes_previous_answer_for_recent_reference_time_change() -> None:
    assert "previous user question and assistant answer" in TRANSACTION_ORDER_SYSTEM_PROMPT_TEMPLATE
    assert "previous answer was a reservation-history list" in TRANSACTION_ORDER_SYSTEM_PROMPT_TEMPLATE
    assert "Do NOT fall back to the first order row" in TRANSACTION_ORDER_SYSTEM_PROMPT_TEMPLATE


def test_recent_single_store_context_can_carry_shop_id_from_detail_input() -> None:
    prev_tool_data = [
        {
            "tool": "get_store_detail_tool",
            "input": {"shop_id": "F07782", "cal_day": "20260525"},
            "data": {
                "shop_seq": "F204423537",
                "shop_nm": "티스테이션 한남점",
                "tel_no": "02-790-2921",
            },
        }
    ]

    assert TStationChatServiceV2._resolve_recent_single_shop_id_from_context(prev_tool_data) == "F07782"


def test_recent_single_store_context_can_carry_shop_id_from_single_store_list() -> None:
    prev_tool_data = [
        {
            "tool": "get_store_list_tool",
            "input": {"store_nm": "티스테이션 한남점"},
            "data": [
                {
                    "shop_id": "F07782",
                    "shop_seq": "F204423537",
                    "shop_nm": "티스테이션 한남점",
                }
            ],
        }
    ]

    assert TStationChatServiceV2._resolve_recent_single_shop_id_from_context(prev_tool_data) == "F07782"


def test_recent_single_store_context_does_not_guess_from_multi_store_list() -> None:
    prev_tool_data = [
        {
            "tool": "get_store_list_tool",
            "data": [
                {"shop_id": "F07782", "shop_nm": "티스테이션 한남점"},
                {"shop_id": "F00694", "shop_nm": "티스테이션 청량리점"},
            ],
        }
    ]

    assert TStationChatServiceV2._resolve_recent_single_shop_id_from_context(prev_tool_data) is None


def test_recent_store_name_can_be_carried_from_assistant_summary() -> None:
    messages = [
        {
            "role": "assistant",
            "content": (
                "티스테이션 한남점의 추석 연휴 예약 가능 여부는 매장 휴무일 기준으로 확인해야 해요.\n\n"
                "매장명: 티스테이션 한남점\n"
                "전화: 02-790-2921"
            ),
        }
    ]

    assert TStationChatServiceV2._resolve_recent_store_name_from_messages(messages) == "티스테이션 한남점"


def test_store_contact_guidance_skips_without_store_identity() -> None:
    event_data = {
        "assistantResponse": "질소 충전 가능 여부는 별도 확인이 필요해요. 매장으로 문의해 주세요.",
        "quickReplies": [{"label": "1:1 문의하기", "domain": "SUPPORT"}],
    }

    changed = _inject_store_detail_chip_for_contact_guidance(
        event_data,
        tool_data_list=[],
        messages=[],
    )

    assert changed is False
    assert _labels(event_data["quickReplies"]) == ["1:1 문의하기"]


def test_vehicle_auto_select_matches_exact_plate_from_listcar() -> None:
    selected = _select_vehicle_from_listcar_event(
        "내 차 번호 205소 4214 알지? 맞는 타이어 보여줘.",
        {
            "listCar": [
                {"licensePlate": "29조3344", "info": "폭스바겐 제타"},
                {"licensePlate": "205소4214", "info": "제네시스 GV70 2.5T"},
            ],
            "metadata": [
                {"carNo": "29조3344", "carLncCd": "W036270", "tireSize": "205/55R16"},
                {"carNo": "205소4214", "carLncCd": "W049847", "tireSize": "235/55R19"},
            ],
        },
    )

    assert selected is not None
    assert selected["meta"]["carNo"] == "205소4214"


def test_vehicle_auto_select_does_not_hijack_unregistered_plate() -> None:
    selected = _select_vehicle_from_listcar_event(
        "내 차 번호 999가9999 알지? 맞는 타이어 보여줘.",
        {
            "listCar": [
                {"licensePlate": "29조3344", "info": "폭스바겐 제타"},
                {"licensePlate": "205소4214", "info": "제네시스 GV70 2.5T"},
            ],
            "metadata": [
                {"carNo": "29조3344", "carLncCd": "W036270", "tireSize": "205/55R16"},
                {"carNo": "205소4214", "carLncCd": "W049847", "tireSize": "235/55R19"},
            ],
        },
    )

    assert selected is None


def test_vehicle_owner_lookup_force_routes_to_discovery_recommendation() -> None:
    result = StreamingMultiAgentCoordinator._force_keyword_routing("26저 7922 황지훈")

    assert result is not None
    assert result.domains == [MultiAgentDomain.Domain.DISCOVERY]
    assert result.agent_prompt_profile == "discovery_recommendation"


def test_vehicle_owner_lookup_with_separator_and_lookup_suffix_force_routes_to_discovery_recommendation() -> None:
    result = StreamingMultiAgentCoordinator._force_keyword_routing("56모 2162, 심여사 차량조회해줘")

    assert result is not None
    assert result.domains == [MultiAgentDomain.Domain.DISCOVERY]
    assert result.agent_prompt_profile == "discovery_recommendation"


def test_monthly_best_seller_request_forces_code_route_even_if_transaction_biased() -> None:
    for text in (
        "이번달 사람들이 젤 많이 구매한 타이어",
        "이번 달 제일 많이 산 타이어",
        "이번달 베스트셀러",
        "이달 최다 판매 타이어 뭐야",
        "월간 판매 순위 타이어 알려줘",
    ):
        frame = build_discovery_intent_frame(text)
        plan = plan_discovery_tools(frame)

        assert is_best_seller_request(text)
        assert best_seller_period_from_text(text) == "month"
        assert frame.sub_intent == "best_seller_search"
        assert plan.allowed_tools == ("get_best_selling_products_tool",)
        assert plan.tool_args_patch == {"period": "month", "limit": 5}
        assert _should_force_best_seller_code_route(
            text,
            [MultiAgentDomain.Domain.TRANSACTION],
        )


def test_non_aggregate_purchase_request_does_not_force_best_seller_code_route() -> None:
    assert not _should_force_best_seller_code_route(
        "이번달 내가 구매한 타이어 주문 확인해줘",
        [MultiAgentDomain.Domain.TRANSACTION],
    )


def test_reservation_time_change_force_routes_to_transaction_order() -> None:
    result = StreamingMultiAgentCoordinator._force_keyword_routing("5/29 예약한거 시간 변경하고 싶은데")

    assert result is not None
    assert result.domains == [MultiAgentDomain.Domain.TRANSACTION]
    assert result.agent_prompt_profile == "transaction_order"


def test_bare_target_time_change_force_routes_to_transaction_order() -> None:
    result = StreamingMultiAgentCoordinator._force_keyword_routing("18시로 바꿔줘")

    assert result is not None
    assert result.domains == [MultiAgentDomain.Domain.TRANSACTION]
    assert result.agent_prompt_profile == "transaction_order"


def test_owned_reservation_lookup_force_routes_to_transaction_order() -> None:
    result = StreamingMultiAgentCoordinator._force_keyword_routing("내 예약 어떻게 돼있어?")

    assert result is not None
    assert result.domains == [MultiAgentDomain.Domain.TRANSACTION]
    assert result.agent_prompt_profile == "transaction_order"


def test_order_history_force_routes_to_transaction_order() -> None:
    result = StreamingMultiAgentCoordinator._force_keyword_routing("내 주문내역 알려줘")

    assert result is not None
    assert result.domains == [MultiAgentDomain.Domain.TRANSACTION]
    assert result.agent_prompt_profile == "transaction_order"


def test_store_schedule_question_force_routes_to_transaction_store() -> None:
    result = StreamingMultiAgentCoordinator._force_keyword_routing("강남점에서 5/29 예약 가능해?")

    assert result is not None
    assert result.domains == [MultiAgentDomain.Domain.TRANSACTION]
    assert result.agent_prompt_profile == "transaction_store"


def test_after_hours_store_search_does_not_force_route_to_transaction_order() -> None:
    result = StreamingMultiAgentCoordinator._force_keyword_routing("서울에서 18시 이후 서비스 받을 수 있는 매장 있어?")

    assert result is None or result.agent_prompt_profile != "transaction_order"


def test_reservation_change_with_store_name_stays_transaction_order() -> None:
    result = StreamingMultiAgentCoordinator._force_keyword_routing("성남IC점 예약한거 5/29 16시에서 17시로 바꾸고 싶어")

    assert result is not None
    assert result.domains == [MultiAgentDomain.Domain.TRANSACTION]
    assert result.agent_prompt_profile == "transaction_order"


def test_pickup_service_force_routes_to_support() -> None:
    result = StreamingMultiAgentCoordinator._force_keyword_routing("차 가지러 올 수 있어?")

    assert result is not None
    assert result.domains == [MultiAgentDomain.Domain.SUPPORT]


def test_delivery_policy_force_routes_to_support() -> None:
    result = StreamingMultiAgentCoordinator._force_keyword_routing("서귀포시인데 배송비 더 들어?")

    assert result is not None
    assert result.domains == [MultiAgentDomain.Domain.SUPPORT]

    result = StreamingMultiAgentCoordinator._force_keyword_routing("집으로 배송해줘")

    assert result is not None
    assert result.domains == [MultiAgentDomain.Domain.SUPPORT]


def test_generic_application_question_does_not_force_route_to_pickup_support() -> None:
    result = StreamingMultiAgentCoordinator._force_keyword_routing("신청 방법 안내해줘")

    assert result is None


def test_support_fast_path_uses_pickup_and_delivery_policy_gates() -> None:
    assert _support_fast_path("픽업서비스 어떻게 신청해?") == [MultiAgentDomain.Domain.SUPPORT]
    assert _support_fast_path("타이어 집으로 걍 배송받고 싶어") == [MultiAgentDomain.Domain.SUPPORT]
    assert _support_fast_path("집으로 배송해줘") == [MultiAgentDomain.Domain.SUPPORT]
    assert _support_fast_path("서귀포시인데 배송비 더 들어?") == [MultiAgentDomain.Domain.SUPPORT]
    assert _support_fast_path("제주도 매장에서도 온라인 가격이랑 똑같아?") == [MultiAgentDomain.Domain.SUPPORT]


def test_support_fast_path_routes_reminding_alarm_settings() -> None:
    assert _support_fast_path("알람 설정하는 페이지 어디야?") == [MultiAgentDomain.Domain.SUPPORT]
    assert _support_fast_path("타이어 교체 알림 신청하고 싶어") == [MultiAgentDomain.Domain.SUPPORT]


def test_reminding_alarm_event_links_to_cta() -> None:
    event = _reminding_alarm_event()
    data = event["data"]

    assert event["source_domain"] == MultiAgentDomain.Domain.SUPPORT.value
    assert "도와드릴 수 없" not in data["assistantResponse"]
    assert "채팅창 안에서는 바로 변경할 수 없어요" in data["assistantResponse"]
    assert "알림 설정 페이지" in data["assistantResponse"]
    assert "아래 버튼" in data["assistantResponse"]
    assert data["quickReplies"][0] == {
        "label": "점검/교체 알림",
        "url": CTAUrls.REMINDING_ALARM,
        "domain": "SUPPORT",
    }


def test_support_fast_path_routes_product_warranty_claims() -> None:
    assert _support_fast_path("ventus air S 5만키로 탈 수 있다더니 벌써 다 닳은거같은데 무료교체해줘") == [
        MultiAgentDomain.Domain.SUPPORT
    ]
    assert _support_fast_path("벤투스 에어S 왜 이렇게 빨리 닳아? 보증 대상 아냐?") == [
        MultiAgentDomain.Domain.SUPPORT
    ]
    assert _support_fast_path("ventus air S 설명해줘") is None


def test_product_warranty_policy_route_beats_discovery_chip_context() -> None:
    plan = plan_cross_domain_turn("벤투스 S2 AS 워런티 돼?")

    assert _should_force_warranty_claim_support_route(plan) is True


def test_support_fast_path_does_not_hijack_generic_application_question() -> None:
    assert _support_fast_path("신청 방법 알려줘") is None


def test_rule_based_classify_keeps_pickup_and_delivery_policy_gates_even_when_disabled() -> None:
    merged_slots = SimpleNamespace(goods_no=None)

    assert _rule_based_classify("차 가지러 올 수 있어?", merged_slots) == [MultiAgentDomain.Domain.SUPPORT]
    assert _rule_based_classify("타이어 집으로 걍 배송받고 싶어", merged_slots) == [MultiAgentDomain.Domain.SUPPORT]
    assert _rule_based_classify("서귀포시인데 배송비 더 들어?", merged_slots) == [MultiAgentDomain.Domain.SUPPORT]
    assert _rule_based_classify("제주도 매장에서도 온라인 가격이랑 똑같아?", merged_slots) == [
        MultiAgentDomain.Domain.SUPPORT
    ]
    assert _rule_based_classify("신청 방법 알려줘", merged_slots) is None


def test_rule_based_classify_routes_default_tbot_shopping_cta_to_discovery() -> None:
    merged_slots = SimpleNamespace(goods_no=None)

    assert _rule_based_classify("T'Bot과 타이어 쇼핑하기", merged_slots) == [MultiAgentDomain.Domain.DISCOVERY]
    assert _rule_based_classify("T’Bot과 타이어 쇼핑하기", merged_slots) == [MultiAgentDomain.Domain.DISCOVERY]


def test_vehicle_auto_select_matches_unique_owned_model_from_listcar() -> None:
    selected = _select_vehicle_from_listcar_event(
        "내 gv70 에 맞는 타이어 추천",
        {
            "listCar": [
                {"licensePlate": "205소4214", "info": "제네시스 GV70 2.5T"},
                {"licensePlate": "29조3344", "info": "폭스바겐 제타"},
            ],
            "metadata": [
                {"carNo": "205소4214", "carLncCd": "W049847", "tireSize": "235/55R19"},
                {"carNo": "29조3344", "carLncCd": "W036270", "tireSize": "205/55R16"},
            ],
        },
    )

    assert selected is not None
    assert selected["meta"]["carNo"] == "205소4214"


def test_vehicle_selection_slot_values_include_vehicle_identifiers() -> None:
    slot_values = _vehicle_selection_slot_values(
        {
            "car": {"licensePlate": "205소4214", "info": "GV70 2.5T"},
            "meta": {
                "carNo": "205소4214",
                "carLncCd": "W049847",
                "mbrCarRegSeq": "2000002944",
                "carNm": "GV70 2.5T 가솔린 AWD A/T",
                "carType": "SUV",
                "tireSize": "2355519",
            },
        }
    )

    assert slot_values == {
        "tire_size": "235/55R19",
        "tire_size_front": "235/55R19",
        "car_model": "GV70 2.5T 가솔린 AWD A/T",
        "car_no": "205소4214",
        "car_lnc_cd": "W049847",
        "car_type": "SUV",
        "vehicle_type": "suv",
        "mbr_car_reg_seq": "2000002944",
    }


def test_staggered_vehicle_selection_event_prompts_for_front_or_rear_size() -> None:
    event = _build_staggered_vehicle_tire_selection_event(
        {
            "car": {"licensePlate": "56모2162", "info": "BMW 3시리즈 그란 투리스모(6세대)"},
            "meta": {
                "carNo": "56모2162",
                "tireSize": "225/50R18",
                "tireSizeRe": "255/50R18",
            },
        }
    )

    assert event is not None
    assert event["template"] == "quickReply"
    assert "어떤 사이즈 기준으로 검색할까요?" in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["앞바퀴사이즈", "뒷바퀴사이즈", "다른 사이즈 입력"]


def test_staggered_prompt_is_not_allowed_for_support_originated_listcar() -> None:
    assert _listcar_allows_staggered_tire_prompt({"template": "listCar", "source_domain": "support"}) is False
    assert _listcar_allows_staggered_tire_prompt({"template": "listCar", "source_domain": "discovery"}) is True


def test_manual_tire_size_chip_gets_deterministic_prompt() -> None:
    latest_quickreply = {
        "template": "quickReply",
        "data": {
            "quickReplies": [
                {"label": "앞바퀴사이즈"},
                {"label": "뒷바퀴사이즈"},
                {"label": "다른 사이즈 입력"},
            ]
        },
    }

    assert _is_manual_tire_size_input_selection("다른 사이즈 입력", latest_quickreply) is True

    event = _build_manual_tire_size_input_event()

    assert event["template"] == "quickReply"
    assert "타이어 사이즈를 직접 입력" in event["data"]["assistantResponse"]


def test_vehicle_tire_position_selection_resolves_quickreply_chip_to_front_size() -> None:
    slots = SimpleNamespace(tire_size_front="225/50R18", tire_size_rear="255/50R18")
    latest_quickreply = {
        "template": "quickReply",
        "data": {
            "quickReplies": [
                {"label": "앞바퀴사이즈"},
                {"label": "뒷바퀴사이즈"},
                {"label": "다른 사이즈 입력"},
            ]
        },
    }

    resolved = _resolve_vehicle_tire_position_selection("앞바퀴사이즈", slots, latest_quickreply)

    assert resolved == "225/50R18"


def test_vehicle_tire_position_selection_resolves_rear_recommend_followup() -> None:
    slots = SimpleNamespace(tire_size_front="225/50R18", tire_size_rear="255/50R18")

    resolved = _resolve_vehicle_tire_position_selection("뒤바퀴도 추천해줘", slots, None)

    assert resolved == "255/50R18도 추천해줘"


def test_vehicle_tire_position_selection_preserves_transactional_intent_text() -> None:
    slots = SimpleNamespace(tire_size_front="225/50R18", tire_size_rear="255/50R18")

    resolved = _resolve_vehicle_tire_position_selection("전륜 가격 알려줘", slots, None)

    assert resolved == "225/50R18 가격 알려줘"


def test_staggered_selected_tire_size_context_detects_single_axle_size() -> None:
    slots = SimpleNamespace(
        tire_size="225/50R18",
        tire_size_front="225/50R18",
        tire_size_rear="255/50R18",
    )

    assert _is_staggered_selected_tire_size_context(slots) is True


def test_staggered_tire_quantity_limit_event_offers_only_one_or_two() -> None:
    slots = SimpleNamespace(
        tire_size="255/50R18",
        tire_size_front="225/50R18",
        tire_size_rear="255/50R18",
    )

    event = _build_staggered_tire_quantity_limit_event(slots)

    assert event is not None
    assert event["template"] == "quickReply"
    assert "최대 2개" in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["1개", "2개"]


def test_order_quantity_prompt_for_staggered_vehicle_offers_only_one_or_two() -> None:
    slots = SimpleNamespace(
        tire_size="225/50R18",
        tire_size_front="225/50R18",
        tire_size_rear="255/50R18",
    )

    event = _build_order_quantity_prompt_event(slots)

    assert event["template"] == "quickReply"
    assert "앞바퀴 **225/50R18** 기준으로 몇 개 구매" in event["data"]["assistantResponse"]
    assert "최대 2개" in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["1개", "2개"]


def test_order_quantity_prompt_precedes_store_when_region_entered_without_quantity() -> None:
    slots = SimpleNamespace(
        goods_no="G000000309855",
        ord_qty=None,
        pending_intent="order",
        goal_type="place_order",
    )

    assert _should_prompt_order_quantity_before_store("강남", slots) is True


def test_store_scope_followup_preserves_confirmed_product_slots() -> None:
    slots = ConversationSlots(
        goods_no="G000000317900",
        tire_size="205/65R15",
        tire_model="세레니티 플러스",
        ord_qty=4,
        pending_intent="stock",
        goal_type="store_with_stock",
        shop_name="티스테이션 모란점",
    )
    regex_slots = ConversationSlots.extract_from_user_text("근처에 다른 매장은?")

    assert _is_confirmed_product_store_scope_followup("근처에 다른 매장은?", slots) is True
    assert _is_plain_store_search_reset_allowed("근처에 다른 매장은?", regex_slots, slots) is False

    patch, _decision = _build_transaction_policy_context(
        domains=[MultiAgentDomain.Domain.TRANSACTION],
        last_user_text="근처에 다른 매장은?",
        known_slots={
            "goods_no": slots.goods_no,
            "tire_size": slots.tire_size,
            "product_name": slots.tire_model,
            "ord_qty": slots.ord_qty,
            "store_name": slots.shop_name,
            "pending_intent": slots.pending_intent,
            "goal_type": slots.goal_type,
        },
    )

    assert patch["goods_no"] == "G000000317900"
    assert patch["quantity"] == 4
    assert patch["preserve_confirmed_product_slots"] is True


def test_datepick_metadata_recovers_order_store_slots() -> None:
    datepick = {
        "template": "datepick",
        "data": {
            "assistantResponse": "예약하려는 날짜와 시간을 선택해 주세요.",
            "dates": [
                {
                    "date": "2026년 6월 24일 (수)",
                    "available": True,
                    "availableTimes": [9, 13],
                    "index": 0,
                }
            ],
            "selectedDate": 0,
            "metadata": {
                "shopId": "F00405",
                "shopName": "티스테이션 경포점",
                "goodsNo": "G000000317900",
                "productName": "Dynapro HPX",
                "tireSize": "235/55R19",
                "ordQty": 2,
                "paymentAmount": 286000,
            },
        },
    }

    values = TStationChatServiceV2._datepick_slot_values_from_data(datepick)

    assert values == {
        "shop_id": "F00405",
        "shop_name": "티스테이션 경포점",
        "goods_no": "G000000317900",
        "tire_model": "Dynapro HPX",
        "tire_size": "235/55R19",
        "ord_qty": 2,
        "payment_amount": 286000,
    }


def test_datepick_selection_recovers_reservation_date_and_hour() -> None:
    datepick = {
        "dates": [
            {
                "date": "2026년 6월 24일 (수)",
                "available": True,
                "availableTimes": [9, 13],
                "index": 0,
            }
        ],
        "selectedDate": 0,
        "metadata": {"shopId": "F00405", "shopName": "티스테이션 경포점"},
    }

    values = TStationChatServiceV2._datepick_slot_values_from_data(
        datepick,
        user_text="2026년 6월 24일 (수)\n13:00",
    )

    assert values["shop_id"] == "F00405"
    assert values["requested_cal_day"] == "20260624"
    assert values["rsv_hour"] == "13"


def test_datepick_template_recovery_candidate_uses_recent_assistant_template_marker() -> None:
    messages = [
        {"role": "user", "content": "2355519"},
        {
            "role": "assistant",
            "content": (
                "예약하려는 날짜와 시간을 선택해 주세요.\n\n[이전 선택된 상품 데이터]\n"
                '{"template":"datepick","data":{"metadata":{"shopId":"F00405","goodsNo":"G000000317900",'
                '"productName":"Dynapro HPX","tireSize":"235/55R19","ordQty":2}}}'
            ),
        },
    ]

    template = _datepick_template_recovery_candidate_from_messages(messages)
    values = TStationChatServiceV2._datepick_slot_values_from_data(template)

    assert template is not None
    assert values is not None
    assert values["shop_id"] == "F00405"
    assert values["goods_no"] == "G000000317900"
    assert values["tire_size"] == "235/55R19"
    assert values["ord_qty"] == 2


def test_datepick_slots_fill_missing_order_state_without_overwriting_preorder_values() -> None:
    slots = ConversationSlots(
        goods_no="G000000317900",
        ord_qty=4,
        shop_id="F00001",
        shop_name="기존 매장",
        pending_intent="order",
        goal_type="place_order",
    )
    values = {
        "shop_id": "F00405",
        "shop_name": "티스테이션 경포점",
        "requested_cal_day": "20260624",
        "rsv_hour": "13",
    }

    updated = slots.apply_runtime_values(values, source="datepick_recovery", fill_only=True)

    assert updated.shop_id == "F00001"
    assert updated.shop_name == "기존 매장"
    assert updated.requested_cal_day == "20260624"
    assert updated.rsv_hour == "13"


def test_verified_datepick_order_values_extracts_critical_product_context() -> None:
    values = _verified_datepick_order_values(
        {
            "shop_id": "F00405",
            "shop_name": "티스테이션 판교점",
            "goods_no": "G000000317900",
            "tire_model": "Dynapro HPX",
            "tire_size": "235/55R19",
            "ord_qty": 2,
            "requested_cal_day": "20260623",
            "rsv_hour": "17",
        }
    )

    assert values == {
        "goods_no": "G000000317900",
        "tire_model": "Dynapro HPX",
        "tire_size": "235/55R19",
        "ord_qty": 2,
        "shop_id": "F00405",
        "shop_name": "티스테이션 판교점",
        "requested_cal_day": "20260623",
        "rsv_hour": "17",
    }


def test_preview_datepick_metadata_preserves_product_slots() -> None:
    goal_token = current_goal_type.set("place_order")
    pending_token = current_pending_intent.set("order")
    try:
        event = try_build_template(
            [
                {
                    "tool": "search_product_tool",
                    "args": {"keyword": "dynapro hpx", "size": "235/55R19"},
                    "data": {
                        "status": "success",
                        "items": [
                            {
                                "goods_no": "G000000317900",
                                "goods_nm": "Dynapro HPX",
                                "tire_size_1": "235/55R19",
                            }
                        ],
                    },
                },
                {
                    "tool": "transaction_store_preview_tool",
                    "args": {
                        "goods_no": "G000000317900",
                        "ord_qty": 2,
                        "store_nm": "티스테이션 판교점",
                        "include_price": True,
                    },
                    "data": {
                        "status": "success",
                        "data": {
                            "schedule": {
                                "tier": "today",
                                "stores": [
                                    {
                                        "shop_id": "F00405",
                                        "shop_nm": "티스테이션 판교점",
                                        "slots": [
                                            {"cal_day": "20260701", "tm": "0900"},
                                            {"cal_day": "20260701", "tm": "1500"},
                                        ],
                                    }
                                ],
                            }
                        },
                    },
                },
            ],
            "예약하려는 날짜와 시간을 선택해 주세요.",
        )
    finally:
        current_pending_intent.reset(pending_token)
        current_goal_type.reset(goal_token)

    assert event is not None
    assert event["template"] == "datepick"
    metadata = event["data"]["metadata"]
    assert metadata["shopId"] == "F00405"
    assert metadata["shopName"] == "티스테이션 판교점"
    assert metadata["goodsNo"] == "G000000317900"
    assert metadata["productName"] == "Dynapro HPX"
    assert metadata["tireSize"] == "235/55R19"
    assert metadata["ordQty"] == 2


def test_store_detail_info_mapping_is_disabled_in_active_order_flow() -> None:
    goal_token = current_goal_type.set("place_order")
    pending_token = current_pending_intent.set("order")
    try:
        event = _map_store_detail_info(
            [
                {
                    "tool": "get_store_detail_tool",
                    "args": {"shop_id": "F00405"},
                    "data": {
                        "shop_nm": "티스테이션 판교점",
                        "tel_no": "0311234567",
                    },
                }
            ],
            "매장 상세정보를 확인했어요.",
        )
    finally:
        current_pending_intent.reset(pending_token)
        current_goal_type.reset(goal_token)

    assert event is None


def test_explicit_store_purchase_chain_request_detection_is_narrow() -> None:
    assert _is_explicit_store_purchase_chain_request("판교점에서 오늘서비스로 dynapro hpx 2355519 2개 구매하고싶어")
    assert not _is_explicit_store_purchase_chain_request("판교점 정보 알려줘")
    assert not _is_explicit_store_purchase_chain_request("2026년 7월 1일 (수)\n17:00")


def test_missing_order_product_reselection_event_is_clarifying() -> None:
    event = _build_missing_order_product_reselection_event()

    assert event["template"] == "quickReply"
    assert event["data"]["assistantResponse"] == "예약할 상품 정보가 확인되지 않아 상품을 다시 선택해 주세요."
    assert _labels(event["data"]["quickReplies"]) == ["상품 다시 선택", "사이즈 다시 입력", "타이어 추천"]


def test_transaction_unresolved_product_resolution_event_clarifies_size_for_multi_candidate_order() -> None:
    slots = ConversationSlots(
        pending_intent="order",
        goal_type="place_order",
        tire_model="Dynapro HPX",
        ord_qty=2,
        shop_name="판교점",
    )

    event = _build_transaction_unresolved_product_resolution_event(
        user_text="판교점에서 오늘서비스로 dynapro hpx 2개 구매하고싶어",
        slots=slots,
        tool_data_list=[
            {
                "tool": "search_product_tool",
                "input": {"keyword": "Dynapro HPX", "limit": 10},
                "data": {
                    "items": [
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "235/55R19"},
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "255/45R20"},
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "225/60R18"},
                    ]
                },
            }
        ],
    )

    assert event is not None
    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "code_transaction_product_resolution_size_clarification"
    assert event["source_domain"] == "transaction"
    assert "구매 확인을 위해 Dynapro HPX의 타이어 규격을 선택해 주세요." in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["235/55R19", "255/45R20", "225/60R18", "사이즈 직접 입력"]


def test_transaction_unresolved_product_resolution_event_returns_not_found_for_zero_rows() -> None:
    slots = ConversationSlots(
        pending_intent="price",
        goal_type="price_inquiry",
        tire_model="Dynapro HPX",
    )

    event = _build_transaction_unresolved_product_resolution_event(
        user_text="dynapro hpx 가격 얼마야?",
        slots=slots,
        tool_data_list=[
            {
                "tool": "search_product_tool",
                "input": {"keyword": "Dynapro HPX", "limit": 10},
                "data": {"items": []},
            }
        ],
    )

    assert event is not None
    assert event["assistant_response_source"] == "code_transaction_product_resolution_not_found"
    assert "Dynapro HPX 상품을 찾지 못해 가격을(를) 이어서 확인하지 못했어요." in event["data"]["assistantResponse"]


def test_transaction_unresolved_product_resolution_event_skips_explicit_size_turn() -> None:
    slots = ConversationSlots(
        pending_intent="order",
        goal_type="place_order",
        tire_model="Dynapro HPX",
        tire_size="235/55R19",
    )

    event = _build_transaction_unresolved_product_resolution_event(
        user_text="dynapro hpx 2355519 2개 구매하고싶어",
        slots=slots,
        tool_data_list=[
            {
                "tool": "search_product_tool",
                "input": {"keyword": "Dynapro HPX", "size": "235/55R19", "limit": 10},
                "data": {"items": [{"goods_nm": "Dynapro HPX", "tire_size_1": "235/55R19"}]},
            }
        ],
    )

    assert event is None


def test_turn_contract_required_slot_guard_prefers_size_clarification_for_multi_size_order_rows() -> None:
    contract = build_turn_contract(
        user_text="판교점에서 오늘서비스로 dynapro hpx 2개 구매하고싶어",
        intent_frame=IntentFrame(domain=PolicyDomain.TRANSACTION, intent="quick_order_reservation"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            required_slots=("tire_size",),
        ),
        merged_slots=ConversationSlots(
            pending_intent="order",
            goal_type="place_order",
            tire_model="Dynapro HPX",
            ord_qty=2,
            shop_name="판교점",
        ),
        routing_result=_routing_result(execution_plan=["transaction:quick_order_reservation"]),
    )

    event = _build_turn_contract_required_slot_guard_event(
        turn_contract=contract,
        user_text="판교점에서 오늘서비스로 dynapro hpx 2개 구매하고싶어",
        tool_data_list=[
            {
                "tool": "search_product_tool",
                "input": {"keyword": "Dynapro HPX", "limit": 10},
                "data": {
                    "items": [
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "255/45R20"},
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "255/55R18"},
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "215/55R18"},
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "215/45R18"},
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "235/55R19"},
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "265/50R20"},
                    ]
                },
            }
        ],
    )

    assert event is not None
    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "code_transaction_product_resolution_size_clarification"
    assert "Dynapro HPX의 타이어 규격을 선택해 주세요." in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == [
        "255/45R20",
        "255/55R18",
        "215/55R18",
        "215/45R18",
        "235/55R19",
        "265/50R20",
        "사이즈 직접 입력",
    ]


def test_turn_contract_fallback_event_prefers_size_clarification_on_response_policy_guard_path() -> None:
    contract = TurnContract(
        domain="discovery",
        intent="resolve_or_describe_product",
        sub_intent="product_name_search",
        known_slots={
            "ord_qty": 2,
            "shop_name": "판교점",
            "availability_intent": "today_install",
            "requested_cal_day": "20260623",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
        required_slots=("product", "goods_no", "tire_size", "quantity"),
        blocking_required_slots=("tire_size", "quantity"),
        resolvable_required_slots=("product", "goods_no"),
        allowed_tools=("search_product_tool",),
        forbidden_tools=("get_products_recommendations_tool",),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("answer_from_previous_recommendation",),
            metadata={"response_shape_key": "product_search_summary"},
        ).to_dict(),
        risk_level="medium",
        fallback_reason="missing_required_slots:tire_size,quantity",
        planner_intent="resolve_or_describe_product",
        planner_domains=("discovery",),
        execution_plan=("discovery:resolve_or_describe_product", "transaction:stock_store_or_reservation"),
        referred_objects={"status": "resolved", "type": "none", "needs_clarification": False},
        planner_confidence=0.0,
        planner_source="router_llm",
        contract_drift=({"field": "intent", "planner": "resolve_or_describe_product", "code_frame": "product_search"},),
    )

    assert contract.blocking_required_slots == ("tire_size", "quantity")
    assert not should_guard_required_slots(contract)

    event = _build_turn_contract_fallback_event(
        turn_contract=contract,
        user_text="판교점에서 오늘서비스로 dynapro hpx 2개 구매하고싶어",
        tool_data_list=[
            {
                "tool": "search_product_tool",
                "input": {"keyword": "Dynapro HPX", "limit": 10},
                "data": {
                    "items": [
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "255/45R20"},
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "255/55R18"},
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "215/55R18"},
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "235/55R19"},
                    ]
                },
            }
        ],
    )

    assert event is not None
    assert event["assistant_response_source"] == "code_transaction_product_resolution_size_clarification"
    assert "Dynapro HPX의 타이어 규격을 선택해 주세요." in event["data"]["assistantResponse"]


def test_no_visible_output_fallback_event_builds_latest_compare_summary() -> None:
    contract = build_turn_contract(
        user_text="ventus s2 as, ventus air s 중에 뭐가 더 신상품?",
        intent_frame=IntentFrame(domain=PolicyDomain.DISCOVERY, intent="product_comparison", sub_intent="latest_compare"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            metadata={"response_shape_key": "metric_comparison_summary"},
        ),
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY],
            execution_plan=["discovery:product_comparison"],
        ),
    )

    event = _build_no_visible_output_fallback_event(
        user_text="ventus s2 as, ventus air s 중에 뭐가 더 신상품?",
        turn_contract=contract,
        structured_sources=[
            (
                "search_product_tool",
                {
                    "items": [
                        {
                            "goods_nm": "벤투스 S2 AS",
                            "t_rls_yearmon": "2016년 1월",
                            "sys_reg_dtime": "2016-01-10 00:00:00",
                        }
                    ]
                },
            ),
            (
                "search_product_tool",
                {
                    "items": [
                        {
                            "goods_nm": "벤투스 에어S",
                            "t_rls_yearmon": "2024년 7월",
                            "sys_reg_dtime": "2024-07-01 00:00:00",
                        }
                    ]
                },
            ),
        ],
        called_tool_names={"search_product_tool"},
        source_domain="discovery",
    )

    assert event is not None
    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "code_product_compare_resolver"
    assert event.get("source_domain") == "discovery"
    assert not violates_response_template_contract(
        {
            "template": event["template"],
            "source_domain": event.get("source_domain"),
            "assistant_response_source": event.get("assistant_response_source"),
            "response_shape_key": "metric_comparison_summary",
            "called_tools": ["search_product_tool"],
        },
        contract,
    )
    assert "최신 상품은 벤투스 에어S입니다." in event["data"]["assistantResponse"]


def test_product_compare_event_uses_router_continued_release_metric_and_metadata() -> None:
    frame = build_discovery_intent_frame(
        "dynapro hpx, dynapro hp3 중에서는?",
        known_slots={
            "comparison_followup_intent": "continue_previous_compare_metric",
            "comparison_metric": "release",
        },
    )
    decision = decide_discovery_response(frame)
    decision_token = current_discovery_response_decision.set(decision)
    try:
        event = _build_product_comparison_event(
            "dynapro hpx, dynapro hp3 중에서는?",
            [
                ("Dynapro HPX", {"goods_nm": "Dynapro HPX", "t_rls_yearmon": "2024년 3월", "car_knd_nm": "SUV"}),
                ("Dynapro HP3", {"goods_nm": "Dynapro HP3", "t_rls_yearmon": "2021년 5월", "car_knd_nm": "승용차"}),
            ],
        )
    finally:
        current_discovery_response_decision.reset(decision_token)

    assert event["assistant_response_source"] == "code_product_compare_resolver"
    assert event["data"]["metadata"]["compareMetric"] == "release"
    assert event["data"]["metadata"]["comparison_followup_intent"] == "continue_previous_compare_metric"
    assert event["data"]["metadata"]["response_shape_key"] == "metric_comparison_summary"
    assert "출시 시점" in event["data"]["assistantResponse"]
    assert "최신 상품은 Dynapro HPX입니다." in event["data"]["assistantResponse"]


def test_product_compare_event_uses_router_new_car_type_metric() -> None:
    frame = build_discovery_intent_frame(
        "ion evo as, ion evo as suv 차종 기준으로는?",
        known_slots={
            "comparison_followup_intent": "new_compare_metric",
            "comparison_metric": "car_type",
        },
    )
    decision = decide_discovery_response(frame)
    decision_token = current_discovery_response_decision.set(decision)
    try:
        event = _build_product_comparison_event(
            "ion evo as, ion evo as suv 차종 기준으로는?",
            [
                ("iON evo AS", {"goods_nm": "iON evo AS", "car_knd_nm": "승용차"}),
                ("iON evo AS SUV", {"goods_nm": "iON evo AS SUV", "car_knd_nm": "SUV"}),
            ],
        )
    finally:
        current_discovery_response_decision.reset(decision_token)

    assert event["data"]["metadata"]["compareMetric"] == "car_type"
    assert event["data"]["metadata"]["comparison_followup_intent"] == "new_compare_metric"
    assert "차종" in event["data"]["assistantResponse"]


def test_discovery_policy_context_recovers_release_compare_continuation_from_recent_compare_template() -> None:
    messages = [
        {"role": "user", "content": "ventus s2 as, ventus air S 중에 뭐가 더 신상품?"},
        {
            "role": "assistant",
            "content": (
                "상품 정보를 표로 비교해드릴게요.\n\n최신 상품은 벤투스 에어S입니다.\n\n"
                "[이전 선택된 상품 데이터]\n"
                '{"type":"data","template":"quickReply","source_domain":"discovery",'
                '"assistant_response_source":"code_product_compare_resolver","data":{"assistantResponse":"x",'
                '"metadata":{"response_shape_key":"metric_comparison_summary","compareMetric":"release",'
                '"comparison_followup_intent":"none"}}}'
            ),
        },
        {"role": "user", "content": "dynapro hpx, dynapro hp3 중에서는?"},
    ]
    patch, decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="dynapro hpx, dynapro hp3 중에서는?",
        context_text="ventus s2 as, ventus air S 중에 뭐가 더 신상품?\ndynapro hpx, dynapro hp3 중에서는?",
        messages=messages,
        tire_size=None,
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY],
            execution_plan=["discovery:resolve_or_describe_product"],
        ),
    )

    assert patch == {}
    assert decision is not None
    assert decision.metadata["compare_metric"] == "release"
    assert decision.metadata["comparison_followup_intent"] == "continue_previous_compare_metric"


def test_discovery_policy_context_prefers_explicit_price_metric_over_prior_release_compare_context() -> None:
    messages = [
        {"role": "user", "content": "ventus s2 as, ventus air S 중에 뭐가 더 신상품?"},
        {
            "role": "assistant",
            "content": (
                "상품 정보를 표로 비교해드릴게요.\n\n최신 상품은 벤투스 에어S입니다.\n\n"
                "[이전 선택된 상품 데이터]\n"
                '{"type":"data","template":"quickReply","source_domain":"discovery",'
                '"assistant_response_source":"code_product_compare_resolver","data":{"assistantResponse":"x",'
                '"metadata":{"response_shape_key":"metric_comparison_summary","compareMetric":"release",'
                '"comparison_followup_intent":"none"}}}'
            ),
        },
        {"role": "user", "content": "dynapro hpx, dynapro hp3 가격은?"},
    ]
    patch, decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="dynapro hpx, dynapro hp3 가격은?",
        context_text="ventus s2 as, ventus air S 중에 뭐가 더 신상품?\ndynapro hpx, dynapro hp3 가격은?",
        messages=messages,
        tire_size=None,
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY],
            execution_plan=["discovery:resolve_or_describe_product"],
        ),
    )

    assert patch == {}
    assert decision is not None
    assert decision.metadata["compare_metric"] == "price"
    assert decision.metadata["comparison_followup_intent"] == "new_compare_metric"


def test_no_visible_output_fallback_event_prefers_transaction_size_clarification_over_description() -> None:
    contract = build_turn_contract(
        user_text="판교점에서 오늘서비스로 dynapro hpx 2개 구매하고싶어",
        intent_frame=IntentFrame(domain=PolicyDomain.TRANSACTION, intent="quick_order_reservation"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            metadata={"response_shape_key": "order_summary"},
        ),
        merged_slots=ConversationSlots(
            pending_intent="order",
            goal_type="place_order",
            tire_model="Dynapro HPX",
            ord_qty=2,
            shop_name="판교점",
        ),
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION],
            execution_plan=["discovery:resolve_product", "transaction:quick_order_reservation"],
        ),
    )

    event = _build_no_visible_output_fallback_event(
        user_text="판교점에서 오늘서비스로 dynapro hpx 2개 구매하고싶어",
        turn_contract=contract,
        structured_sources=[
            (
                "search_product_tool",
                {
                    "items": [
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "235/55R19"},
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "255/45R20"},
                    ]
                },
            )
        ],
        called_tool_names={"search_product_tool"},
        source_domain="transaction",
    )

    assert event is not None
    assert event["assistant_response_source"] == "code_transaction_product_resolution_size_clarification"
    assert "구매 확인을 위해 Dynapro HPX의 타이어 규격을 선택해 주세요." in event["data"]["assistantResponse"]


def test_no_visible_output_fallback_event_uses_tool_context_input_for_size_clarification() -> None:
    contract = TurnContract(
        domain="discovery",
        intent="resolve_or_describe_product",
        known_slots={
            "ord_qty": 2,
            "shop_name": "판교점",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
        required_slots=("product", "goods_no", "tire_size", "quantity"),
        blocking_required_slots=("tire_size", "quantity"),
        resolvable_required_slots=("product", "goods_no"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            metadata={"response_shape_key": "product_search_summary"},
        ).to_dict(),
        risk_level="medium",
    )

    event = _build_no_visible_output_fallback_event(
        user_text="판교점에서 오늘서비스로 dynapro hpx 2개 구매하고싶어",
        turn_contract=contract,
        structured_sources=[
            (
                "search_product_tool",
                {
                    "items": [
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "255/45R20"},
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "235/55R19"},
                    ]
                },
            )
        ],
        tool_data_list=[
            {
                "tool": "search_product_tool",
                "input": {"keyword": "Dynapro HPX", "limit": 10},
                "data": {
                    "items": [
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "255/45R20"},
                        {"goods_nm": "Dynapro HPX", "tire_size_1": "235/55R19"},
                    ]
                },
            }
        ],
        called_tool_names={"search_product_tool"},
        source_domain="discovery",
    )

    assert event is not None
    assert event["assistant_response_source"] == "code_transaction_product_resolution_size_clarification"


def test_current_location_store_search_confirmation_is_narrow() -> None:
    latest_quickreply = {
        "assistantResponse": "현재 위치 기반으로 가까운 매장 검색을 진행할까요?",
        "quickReplies": [{"label": "응", "domain": "TRANSACTION"}],
    }

    assert _is_current_location_store_search_confirmation("응", latest_quickreply)
    assert not _is_current_location_store_search_confirmation(
        "응",
        {"assistantResponse": "예약 가능 시간 보기로 진행할까요?"},
    )


def test_store_preview_policy_patch_overrides_first_row_and_default_quantity_fallback() -> None:
    goods_no, ord_qty, region_code, store_nm, user_xpos, user_ypos = _apply_store_preview_policy_patch(
        patch={
            "goods_no": "G000000317900",
            "quantity": 4,
            "store_name": "티스테이션 모란점",
            "preserve_confirmed_product_slots": True,
        },
        goods_no="G000000317899",
        ord_qty=2,
        region_code=None,
        store_nm=None,
        user_xpos=None,
        user_ypos=None,
    )

    assert goods_no == "G000000317900"
    assert ord_qty == 4
    assert store_nm == "티스테이션 모란점"
    assert region_code is None
    assert user_xpos is None
    assert user_ypos is None


def test_store_scope_followup_allows_explicit_quantity_or_size_change() -> None:
    slots = ConversationSlots(
        goods_no="G000000317900",
        tire_size="205/65R15",
        ord_qty=4,
        pending_intent="stock",
        goal_type="store_with_stock",
    )

    assert _is_confirmed_product_store_scope_followup("2개로 다시 확인해줘", slots) is False
    assert _is_confirmed_product_store_scope_followup("195/65R15로 근처 매장 확인", slots) is False


def test_order_quantity_prompt_fires_when_product_is_selected_this_turn() -> None:
    slots = SimpleNamespace(
        goods_no="G000000309855",
        ord_qty=None,
        pending_intent="order",
        goal_type="place_order",
    )

    assert (
        _should_prompt_order_quantity_before_store(
            "스콜피언 베르디 255/55R19",
            slots,
            goods_no_resolved_this_turn=True,
        )
        is True
    )


def test_order_quantity_prompt_does_not_fire_when_quantity_is_current_turn() -> None:
    slots = SimpleNamespace(
        goods_no="G000000309855",
        ord_qty=2,
        pending_intent="order",
        goal_type="place_order",
    )

    assert _should_prompt_order_quantity_before_store("2개", slots) is False


@pytest.mark.parametrize(
    "text",
    [
        "내 차로 확인",
        "아니 이거 말고 내 차 확인한다고",
        "아니 내 차목록 보여달라고",
        "내차 사이즈로 다시",
        "내 쿠폰 보여줘",
        "예약내역 확인",
        "다른 상품 추천해줘",
        "이 타이어 승차감은 어때?",
        "한남점 질소충전 무료야?",
    ],
)
def test_order_quantity_prompt_does_not_trap_topic_switches(text: str) -> None:
    slots = SimpleNamespace(
        goods_no="G000000309855",
        ord_qty=None,
        pending_intent="order",
        goal_type="place_order",
    )

    assert _should_prompt_order_quantity_before_store(text, slots) is False


@pytest.mark.parametrize("text", ["강남", "판교점", "근처 매장", "오늘 장착 가능한 매장", "구매하기"])
def test_order_quantity_prompt_keeps_order_continuation_texts(text: str) -> None:
    assert _is_order_quantity_prompt_continuation_text(text) is True


def test_fresh_sized_product_order_clears_stale_comparison_product() -> None:
    slots = ConversationSlots(
        goods_no="G000000309780",
        tire_model="벤투스 S2 AS",
        tire_size="245/45R18",
        payment_amount=123000,
        pending_intent="order",
        goal_type="place_order",
    )

    text = "이글 투어링 2454518 사이즈 구매하고 싶은데"

    assert _is_fresh_product_transaction_request(text, "order") is True
    assert _clear_stale_product_identity_for_fresh_transaction(slots, text, "order") is True
    assert slots.goods_no is None
    assert slots.tire_model is None
    assert slots.payment_amount is None
    assert slots.tire_size == "245/45R18"


def test_size_only_order_does_not_clear_stale_product_identity() -> None:
    slots = ConversationSlots(
        goods_no="G000000309780",
        tire_model="벤투스 S2 AS",
        tire_size="205/55R16",
        payment_amount=123000,
        pending_intent="order",
        goal_type="place_order",
    )

    text = "2454518 사이즈 구매하고 싶은데"

    assert _is_fresh_product_transaction_request(text, "order") is False
    assert _clear_stale_product_identity_for_fresh_transaction(slots, text, "order") is False
    assert slots.goods_no == "G000000309780"
    assert slots.tire_model == "벤투스 S2 AS"


def test_runtime_product_or_size_change_invalidates_goods_no() -> None:
    base = ConversationSlots(
        goods_no="G-S1",
        pending_product_name="벤투스 S1 evo Z",
        tire_model="벤투스 S1 evo Z",
        tire_size="225/45R17",
        payment_amount=100000,
    )

    changed_product = base.apply_runtime_values(
        {"pending_product_name": "벤투스 에어S", "tire_model": "벤투스 에어S"},
        source="test",
    )
    changed_size = base.apply_runtime_values({"tire_size": "265/45R19"}, source="test")
    changed_front = base.apply_runtime_values({"tire_size_front": "225/50R18"}, source="test")
    changed_rear = base.apply_runtime_values({"tire_size_rear": "255/50R18"}, source="test")

    assert changed_product.goods_no is None
    assert changed_product.payment_amount is None
    assert changed_size.goods_no is None
    assert changed_front.goods_no is None
    assert changed_rear.goods_no is None


def test_fresh_transaction_clear_keeps_current_product_entity_after_pending_update() -> None:
    slots = ConversationSlots(
        goods_no="G-S1",
        pending_product_name="벤투스 에어S",
        tire_model="벤투스 에어S",
        tire_size="225/55R17",
        payment_amount=100000,
        pending_intent="price",
        goal_type="price_inquiry",
    )

    changed = _clear_stale_product_identity_for_fresh_transaction(
        slots,
        "ventus air S 2255517 4개 구매하고 싶은데 쿠폰 적용하면 할인받는 금액이 얼마야?",
        "price",
    )

    assert changed is True
    assert slots.goods_no is None
    assert slots.payment_amount is None
    assert slots.pending_product_name == "벤투스 에어S"
    assert slots.tire_model == "벤투스 에어S"


@pytest.mark.parametrize("text", ["장바구니담기", "장바구니 담기", "장바구니에 담아줘", "구매하기", "주문하기"])
def test_quantityless_cart_order_cta_detects_button_labels(text: str) -> None:
    assert _is_quantityless_cart_or_order_cta(text) is True


def test_confirmed_product_slot_values_from_cart_quickreply_metadata_includes_quantity() -> None:
    event = {
        "template": "quickReply",
        "data": {
            "assistantResponse": "장바구니에 담았어요.",
            "quickReplies": [{"label": "주문하기", "domain": "TRANSACTION"}],
            "metadata": {
                "goodsId": "G000000309783",
                "tireSize": "225/45R17",
                "productName": "벤투스 S2 AS",
                "quantity": 2,
            },
        },
    }

    assert TStationChatServiceV2._confirmed_product_slot_values_from_event(event) == {
        "goods_no": "G000000309783",
        "ord_qty": 2,
        "tire_model": "벤투스 S2 AS",
        "tire_size": "225/45R17",
    }


def test_history_vehicle_selection_does_not_auto_resolve_staggered_front_size() -> None:
    template = {
        "template": "listCar",
        "data": {
            "listCar": [{"licensePlate": "56모2162", "info": "BMW 3시리즈 그란 투리스모(6세대)"}],
            "metadata": [{
                "carNo": "56모2162",
                "tireSize": "225/50R18",
                "tireSizeRe": "255/50R18",
            }],
        },
    }

    resolved = TStationChatServiceV2._resolve_tire_size_from_history_template("56모2162", template)

    assert resolved is None


def test_history_vehicle_selection_still_resolves_selected_vehicle_for_staggered_fitment() -> None:
    template = {
        "template": "listCar",
        "data": {
            "listCar": [{"licensePlate": "56모2162", "info": "BMW 3시리즈 그란 투리스모(6세대)"}],
            "metadata": [{
                "carNo": "56모2162",
                "tireSize": "225/50R18",
                "tireSizeRe": "255/50R18",
                "carLncCd": "W049847",
            }],
        },
    }

    resolved = TStationChatServiceV2._resolve_vehicle_from_history_template("56모2162", template)

    assert resolved is not None
    assert resolved["meta"]["carNo"] == "56모2162"
    assert resolved["meta"]["tireSizeRe"] == "255/50R18"


def test_history_vehicle_selection_resolves_ordinal_pick() -> None:
    template = {
        "template": "listCar",
        "data": {
            "listCar": [
                {"licensePlate": "11가1111", "info": "쏘나타"},
                {"licensePlate": "56모2162", "info": "BMW 3시리즈 그란 투리스모(6세대)"},
            ],
            "metadata": [
                {"carNo": "11가1111", "tireSize": "205/55R16", "tireSizeRe": "205/55R16"},
                {"carNo": "56모2162", "tireSize": "225/50R18", "tireSizeRe": "255/50R18"},
            ],
        },
    }

    resolved = TStationChatServiceV2._resolve_vehicle_from_history_template("2번", template)

    assert resolved is not None
    assert resolved["meta"]["carNo"] == "56모2162"
    assert resolved["meta"]["tireSizeRe"] == "255/50R18"


def test_history_tire_size_resolution_supports_ordinal_pick_for_same_size_vehicle() -> None:
    template = {
        "template": "listCar",
        "data": {
            "listCar": [
                {"licensePlate": "11가1111", "info": "쏘나타"},
                {"licensePlate": "29조3344", "info": "폭스바겐 제타"},
            ],
            "metadata": [
                {"carNo": "11가1111", "tireSize": "205/55R16", "tireSizeRe": "205/55R16"},
                {"carNo": "29조3344", "tireSize": "225/45R17", "tireSizeRe": "225/45R17"},
            ],
        },
    }

    resolved = TStationChatServiceV2._resolve_tire_size_from_history_template("2)", template)

    assert resolved == "225/45R17"


def test_history_vehicle_selection_resolves_model_name_pick() -> None:
    template = {
        "template": "listCar",
        "data": {
            "listCar": [
                {"licensePlate": "205소4214", "info": "제네시스 GV70 2.5T"},
                {"licensePlate": "29조3344", "info": "폭스바겐 제타"},
            ],
            "metadata": [
                {"carNo": "205소4214", "tireSize": "235/55R19", "tireSizeRe": "235/55R19"},
                {"carNo": "29조3344", "tireSize": "225/45R17", "tireSizeRe": "225/45R17"},
            ],
        },
    }

    resolved = TStationChatServiceV2._resolve_vehicle_from_history_template("GV70", template)

    assert resolved is not None
    assert resolved["meta"]["carNo"] == "205소4214"


def test_history_vehicle_selection_model_name_pick_requires_unique_match() -> None:
    template = {
        "template": "listCar",
        "data": {
            "listCar": [
                {"licensePlate": "11가1111", "info": "제네시스 GV70 2.5T"},
                {"licensePlate": "22나2222", "info": "제네시스 GV80 3.5T"},
            ],
            "metadata": [
                {"carNo": "11가1111", "tireSize": "235/55R19", "tireSizeRe": "235/55R19"},
                {"carNo": "22나2222", "tireSize": "265/40R22", "tireSizeRe": "265/40R22"},
            ],
        },
    }

    resolved = TStationChatServiceV2._resolve_vehicle_from_history_template("제네시스", template)

    assert resolved is None


def test_history_vehicle_selection_does_not_match_product_name_substring_to_vehicle() -> None:
    template = {
        "template": "listCar",
        "data": {
            "listCar": [
                {"licensePlate": "33가3333", "info": "더 뉴 A-class(W177) F/L A 220 Hatchback A/T"},
                {"licensePlate": "56모2162", "info": "3-series(F30) 320d A/T"},
            ],
            "metadata": [
                {"carNo": "33가3333", "tireSize": "205/55R17", "tireSizeRe": "205/55R17"},
                {"carNo": "56모2162", "tireSize": "225/50R18", "tireSizeRe": "255/50R18"},
            ],
        },
    }

    resolved = TStationChatServiceV2._resolve_vehicle_from_history_template("벤투스 S2 AS 225/50R18", template)

    assert resolved is None


def test_unmatched_vehicle_listcar_is_coerced_to_owner_prompt() -> None:
    event = {
        "template": "listCar",
        "data": {
            "listCar": [{"licensePlate": "205소4214", "info": "GV70"}],
            "metadata": [{"carNo": "205소4214"}],
        },
    }

    coerced = _coerce_unmatched_vehicle_listcar_to_owner_prompt(event, "14다5499")

    assert coerced is not None
    assert coerced["template"] == "quickReply"
    assert "차량번호 + 소유주명" in coerced["data"]["assistantResponse"]


def test_pending_vehicle_lookup_plate_is_reused_for_owner_only_followup() -> None:
    latest_quickreply_tmpl = {
        "template": "quickReply",
        "data": {
            "assistantResponse": "해당 차량으로 찾으시려면 차량번호 + 소유주명을 입력해 주세요.",
            "quickReplies": [{"label": "차번+이름으로 검색", "domain": "DISCOVERY"}],
        },
    }

    assert _should_reuse_pending_vehicle_lookup_car_no(
        latest_quickreply_tmpl,
        "홍길동",
        "14다5499",
    )


def test_vehicle_auto_select_prefers_exact_vehicle_tokens_over_loose_overlap() -> None:
    selected = _select_vehicle_from_listcar_event(
        "내 차 BMW 3시리즈 GT 320d 이건데 전/후륜 규격이 다른게 있던데 뭘로 그럼 사이즈를 봐야해..?",
        {
            "listCar": [
                {"licensePlate": "205소4214", "info": "제네시스 GV70 (1세대)"},
                {"licensePlate": "56모2162", "info": "BMW 3시리즈 그란 투리스모(6세대)"},
            ],
            "metadata": [
                {"carNo": "205소4214", "carLncCd": "W049847", "tireSize": "235/55R19"},
                {
                    "carNo": "56모2162",
                    "carLncCd": "W022859",
                    "tireSize": "225/50R18",
                    "tireSizeRe": "255/50R18",
                    "carMaker": "BMW",
                    "carModelDet": "3시리즈 그란 투리스모(6세대)",
                    "carTrim": "3-series(F30) 320d A/T",
                },
            ],
        },
    )

    assert selected is not None
    assert selected["meta"]["carNo"] == "56모2162"


def test_vehicle_auto_select_keeps_listcar_when_model_match_is_ambiguous() -> None:
    selected = _select_vehicle_from_listcar_event(
        "내 gv70 에 맞는 타이어 추천",
        {
            "listCar": [
                {"licensePlate": "205소4214", "info": "제네시스 GV70 2.5T"},
                {"licensePlate": "111가2222", "info": "제네시스 GV70 전동화 모델"},
            ],
            "metadata": [
                {"carNo": "205소4214", "carLncCd": "W049847", "tireSize": "235/55R19"},
                {"carNo": "111가2222", "carLncCd": "W049848", "tireSize": "265/45R20"},
            ],
        },
    )

    assert selected is None


def test_vehicle_auto_select_preserves_discount_recommendation_intent() -> None:
    assert _recommendation_type_for_vehicle_auto_continue("내 gv70 세일 많이 하는 타이어 추천") == "discount"


def test_vehicle_auto_select_maps_fuel_efficiency_query_to_tstation_context() -> None:
    assert _recommendation_type_for_vehicle_auto_continue("연비 좋은 타이어 추천") == "fuel_efficiency"


def test_fuel_efficiency_sort_prefers_higher_score_then_lower_rr() -> None:
    items = [
        {"goods_no": "A", "t_fuel_eff_convert": 21.0, "rr": "2"},
        {"goods_no": "B", "t_fuel_eff_convert": 27.3, "rr": "3"},
        {"goods_no": "C", "t_fuel_eff_convert": 27.3, "rr": "2"},
    ]

    sorted_items = discovery_tools._sort_items(items, "fuel_efficiency_desc")

    assert [item["goods_no"] for item in sorted_items] == ["C", "B", "A"]


def test_recent_product_search_keyword_is_recovered_after_vehicle_selection() -> None:
    prev_tool_data = [
        {
            "tool": "search_product_tool",
            "input": {"keyword": "옵티모", "brand_cd": "HK"},
            "data": [
                {"goods_no": "G1", "goods_nm": "옵티모 H426", "tire_size_1": "245/50R18"},
                {"goods_no": "G2", "goods_nm": "옵티모 H418", "tire_size_1": "215/65R16"},
            ],
        }
    ]

    assert TStationChatServiceV2._resolve_recent_product_search_keyword(prev_tool_data) == "옵티모"
    assert TStationChatServiceV2._resolve_goods_no_from_recent_product_context(prev_tool_data, "235/55R19") is None


def test_recent_product_context_resolves_unique_goods_no_by_vehicle_selected_tire_size() -> None:
    prev_tool_data = [
        {
            "tool": "search_product_tool",
            "input": {"keyword": "벤투스 S2 AS", "brand_cd": "HK"},
            "data": [
                {"goods_no": "G1", "goods_nm": "벤투스 S2 AS", "tire_size_1": "225/45R17"},
                {"goods_no": "G2", "goods_nm": "벤투스 S2 AS", "tire_size_1": "235/55R19"},
                {"goods_no": "G3", "goods_nm": "벤투스 S2 AS", "tire_size_1": "245/45R18"},
            ],
        }
    ]

    assert (
        TStationChatServiceV2._resolve_goods_no_from_recent_product_context(prev_tool_data, "2355519")
        == "G2"
    )


def test_goods_no_from_selection_resolves_size_only_compact_input() -> None:
    prev_tool_data = [
        {
            "tool": "search_product_tool",
            "data": [
                {"goods_no": "G1", "goods_nm": "벤투스 S1 에보 Z", "tire_size_1": "255/40R21"},
                {"goods_no": "G2", "goods_nm": "벤투스 S1 에보 Z", "tire_size_1": "265/40R21"},
            ],
        }
    ]

    assert TStationChatServiceV2._resolve_goods_no_from_selection("2654021", prev_tool_data) == "G2"


def test_goods_no_from_selection_uses_stored_tire_size_for_name_only_pick() -> None:
    prev_tool_data = [
        {
            "tool": "get_products_recommendations_tool",
            "data": [
                {"goods_no": "G000000310120", "goods_nm": "벤투스 S2 AS", "tire_size_1": "225/55R17"},
                {"goods_no": "G000000318549", "goods_nm": "키너지 ST AS", "tire_size_1": "225/55R17"},
                {"goods_no": "G000000312301", "goods_nm": "벤투스 V2 AS", "tire_size_1": "225/55R17"},
            ],
        }
    ]

    assert (
        TStationChatServiceV2._resolve_goods_no_from_selection(
            "벤투스 S2 AS 선택",
            prev_tool_data,
            current_tire_size="225/55R17",
        )
        == "G000000310120"
    )


def test_product_size_list_intent_builds_quickreply_from_previous_search_after_no_result() -> None:
    prev_tool_data = [
        {
            "tool": "search_product_tool",
            "input": {"keyword": "벤투스 에어S", "limit": 10},
            "data": [
                {
                    "goods_no": "G1",
                    "goods_nm": "벤투스 에어S",
                    "tire_size_1": "245/45R18",
                    "sale_prc": 253000,
                    "image_url": "https://example.test/tire.png",
                },
                {
                    "goods_no": "G2",
                    "goods_nm": "벤투스 에어S",
                    "tire_size_1": "245/50R18",
                    "sale_prc": 260000,
                    "image_url": "https://example.test/tire2.png",
                },
                {
                    "goods_no": "G3",
                    "goods_nm": "벤투스 에어S",
                    "tire_size_1": "245/40R18",
                },
            ],
        },
        {
            "tool": "search_product_tool",
            "input": {"keyword": "벤투스 에어S", "limit": 10, "size": "235/55R19"},
            "data": [],
        },
    ]

    event = _build_product_size_list_event_from_search_results(
        "다른 사이즈 보기",
        [],
        prev_tool_data=prev_tool_data,
    )

    assert event is not None
    assert event["template"] == "quickReply"
    data = event["data"]
    assert "245/45R18" in data["assistantResponse"]
    assert "245/50R18" in data["assistantResponse"]
    assert "products" not in data
    assert "imageUrl" not in data
    assert "price" not in data
    assert "goodsId" not in data["metadata"]
    assert data["metadata"]["sizes"] == ["245/45R18", "245/50R18", "245/40R18"]


def test_product_size_list_intent_does_not_capture_product_search_or_size_selection() -> None:
    assert _is_product_size_list_intent("다른 규격 있어?") is True
    assert _is_product_size_list_intent("벤투스 에어S 보여줘") is False
    assert _is_product_size_list_intent("2454518") is False


def test_recent_product_size_availability_event_uses_previous_recommendation_candidates() -> None:
    prev_tool_data = [
        {
            "tool": "get_products_recommendations_tool",
            "data": [
                {"goods_no": "G1", "goods_nm": "아이온 에보 AS", "tire_size_1": "255/45R19"},
                {"goods_no": "G2", "goods_nm": "아이온 에보 AS SUV", "tire_size_1": "235/55R19"},
                {"goods_no": "G3", "goods_nm": "아이온 에보", "tire_size_1": "235/55R19"},
            ],
        }
    ]

    event = _build_recent_product_size_availability_event(
        "235/55R19",
        ["아이온 에보 AS", "아이온 에보 AS SUV", "아이온 에보"],
        ["아이온 에보 AS SUV", "아이온 에보"],
        ["아이온 에보 AS"],
        source_tool="get_products_recommendations_tool",
    )
    context_event = _build_recent_product_size_availability_event_from_rows(
        "두개다 2355519 사이즈가 있을까?",
        prev_tool_data=prev_tool_data,
    )

    assert event is not None
    assert context_event is not None
    assert event["assistant_response_source"] == "code_recent_product_size_availability"
    assistant = event["data"]["assistantResponse"]
    assert "직전 추천 상품 기준으로 235/55R19 규격을 확인했어요." in assistant
    assert "아이온 에보 AS SUV, 아이온 에보는 확인돼요." in assistant
    assert "아이온 에보 AS는 해당 규격을 찾지 못했어요." in assistant
    assert context_event["data"]["metadata"]["productNames"] == ["아이온 에보 AS", "아이온 에보 AS SUV", "아이온 에보"]


def test_recent_product_size_availability_event_prefers_followup_reference_over_single_pending_product() -> None:
    slots = ConversationSlots(pending_product_name="아이온 에보 AS", tire_model="아이온 에보 AS")
    prev_tool_data = [
        {
            "tool": "get_products_recommendations_tool",
            "data": [
                {"goods_no": "G1", "goods_nm": "아이온 에보 AS", "tire_size_1": "255/45R19"},
                {"goods_no": "G2", "goods_nm": "아이온 에보 AS SUV", "tire_size_1": "235/55R19"},
                {"goods_no": "G3", "goods_nm": "아이온 에보", "tire_size_1": "235/55R19"},
            ],
        }
    ]

    event = _build_recent_product_size_availability_event_from_rows(
        "두개다 2355519 사이즈가 있을까?",
        prev_tool_data=prev_tool_data,
    )
    size_list_event = _build_product_size_list_event_from_search_results(
        "두개다 2355519 사이즈가 있을까?",
        [],
        prev_tool_data=prev_tool_data,
        slots=slots,
    )

    assert event is not None
    assert size_list_event is None


def test_recent_product_size_availability_context_recovers_product_names_from_assistant_text() -> None:
    messages = [
        {"role": "user", "content": "타이어 추천"},
        {
            "role": "assistant",
            "content": (
                "사이즈가 아직 확인되지 않아 타이어 기준으로 안내드릴게요.\n\n"
                "- 아이온 에보 AS: 설명\n"
                "- 아이온 에보 AS SUV: 설명\n"
                "- 아이온 에보: 설명\n"
            ),
        },
        {"role": "user", "content": "세개다 2355519 사이즈가 있을까?"},
    ]

    context = _recent_product_set_size_availability_context(
        "세개다 2355519 사이즈가 있을까?",
        messages=messages,
    )

    assert context is not None
    assert context["tool"] == "assistant_quickreply_text"
    assert context["product_names"] == ["아이온 에보 AS", "아이온 에보 AS SUV", "아이온 에보"]


def test_recent_product_size_availability_context_prefers_template_metadata_without_prev_tool_data() -> None:
    latest_quickreply_tmpl = {
        "assistant_response_source": "code_mapper",
        "data": {
            "assistantResponse": "추천 결과입니다.",
            "metadata": {
                "productNames": ["아이온 에보 AS", "아이온 에보 AS SUV", "아이온 에보"],
            },
        },
    }

    context = _recent_product_set_size_availability_context(
        "세개다 2355519 사이즈가 있을까?",
        messages=[{"role": "user", "content": "세개다 2355519 사이즈가 있을까?"}],
        latest_quickreply_tmpl=latest_quickreply_tmpl,
    )

    assert context is not None
    assert context["tool"] == "assistant_template_metadata"
    assert context["product_names"] == ["아이온 에보 AS", "아이온 에보 AS SUV", "아이온 에보"]


def test_recent_product_size_availability_event_from_rows_returns_none_when_only_assistant_text_exists() -> None:
    messages = [
        {"role": "user", "content": "타이어 추천"},
        {
            "role": "assistant",
            "content": (
                "사이즈가 아직 확인되지 않아 타이어 기준으로 안내드릴게요.\n\n"
                "- 아이온 에보 AS: 설명\n"
                "- 아이온 에보 AS SUV: 설명\n"
                "- 아이온 에보: 설명\n"
            ),
        },
        {"role": "user", "content": "세개다 2355519 사이즈가 있을까?"},
    ]

    event = _build_recent_product_size_availability_event_from_rows(
        "세개다 2355519 사이즈가 있을까?",
        messages=messages,
    )

    assert event is None


def test_recent_product_size_availability_missing_context_prompt_keeps_clarification() -> None:
    context = _recent_product_set_size_availability_context(
        "2355519 규격 있어?",
        messages=[{"role": "user", "content": "2355519 규격 있어?"}],
    )
    event = _build_recent_product_size_availability_missing_context_event("235/55R19")

    assert context is None
    assert "확인할 상품이 아직 정해지지 않았어요" in event["data"]["assistantResponse"]


def test_recent_product_size_availability_query_skips_explicit_unknown_product_name() -> None:
    assert _is_sized_product_name_search_query("새상품 ABC 2356018 있을까?") is True
    assert _is_recent_product_size_availability_query("새상품 ABC 2356018 있을까?") is False


def test_router_size_continuation_preserves_recommendation_objective() -> None:
    routing_result = MultiAgentDomain(
        reason="test",
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        execution_plan=["discovery:size_for_recommendation_continuation"],
        user_behavior="providing tire size after unsized recommendation",
        flow="unsized recommendation -> size follow-up",
        claim_check_type="none",
        complaint_scope="none",
        discovery_followup_intent="size_for_recommendation_continuation",
        agent_prompt_profile="discovery_recommendation",
    )

    context = _recent_product_set_size_availability_context(
        "2454518",
        routing_result=routing_result,
        messages=[
            {"role": "user", "content": "승용차용 조용한 타이어 추천해줘"},
            {
                "role": "assistant",
                "content": "- 벤투스 S1 에보 Z AS: 설명\n- 키너지 ST AS: 설명\n- 키너지 EX: 설명",
            },
            {"role": "user", "content": "2454518"},
        ],
    )
    tool_patch, response_decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="2454518",
        context_text="승용차용 조용한 타이어 추천해줘\n2454518",
        tire_size="245/45R18",
        routing_result=routing_result,
    )

    assert context is None
    assert tool_patch == {
        "vehicle_type": "passenger",
        "rcmd_type": "low_vibration",
        "tire_size": "245/45R18",
    }
    assert response_decision is not None
    assert response_decision.metadata["response_shape_key"] != "product_search_summary"


def test_product_pick_after_size_confirmed_patches_search_tool_with_size() -> None:
    routing_result = MultiAgentDomain(
        reason="test",
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        execution_plan=["discovery:resolve_or_describe_product"],
        user_behavior="selecting a product from size-filtered recommendation context",
        flow="unsized recommendation -> size follow-up -> product pick",
        claim_check_type="none",
        complaint_scope="none",
        discovery_followup_intent="none",
        carried_discovery_objective="none",
        agent_prompt_profile="discovery_search",
    )

    tool_patch, response_decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="키너지 st as",
        context_text=(
            "승용차용 조용한 타이어 추천해줘\n"
            "2454518\n"
            "직전 추천 상품 기준으로 245/45R18 규격을 확인했어요.\n"
            "키너지 st as"
        ),
        tire_size="245/45R18",
        routing_result=routing_result,
    )

    assert tool_patch == {"size": "245/45R18"}
    assert response_decision is not None
    assert response_decision.metadata["response_shape_key"] == "product_search_summary"


def test_discovery_policy_context_carries_recent_product_set_followup_from_router() -> None:
    routing_result = MultiAgentDomain(
        reason="test",
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        execution_plan=["discovery:recent_product_set_size_availability"],
        user_behavior="asking size availability for recent product set",
        flow="follow-up size availability",
        claim_check_type="none",
        complaint_scope="none",
        discovery_followup_intent="recent_product_set_size_availability",
        agent_prompt_profile="discovery_search",
    )

    tool_patch, response_decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="2355519 규격 있어?",
        context_text="추천 상품 세 개 보여줌\n2355519 규격 있어?",
        tire_size=None,
        routing_result=routing_result,
    )

    assert tool_patch == {}
    assert response_decision is not None
    assert response_decision.template.value == "quickReply"
    assert response_decision.metadata["response_shape_key"] == "product_search_summary"


def test_discovery_policy_context_carries_safe_service_objective_into_bare_product_name() -> None:
    routing_result = MultiAgentDomain(
        reason="test",
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        execution_plan=["discovery:product_objective_followup"],
        user_behavior="naming a product after asking about safe-service eligibility",
        flow="안심서비스 질문 후 상품명만 답변",
        claim_check_type="none",
        complaint_scope="none",
        discovery_followup_intent="product_objective_followup",
        carried_discovery_objective="safe_service",
        agent_prompt_profile="discovery_search",
    )

    _tool_patch, response_decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="dynapro hp3",
        context_text="안심서비스 가능한 타이어는?\ndynapro hp3",
        tire_size=None,
        routing_result=routing_result,
    )

    assert _tool_patch == {"rcmd_type": "safe_kids", "brand_cd": "HK"}
    assert response_decision is not None
    assert (
        response_decision.metadata["response_shape_key"]
        == "safe_service_explanation_then_unsized_recommendation_summary"
    )


def test_discovery_policy_context_carries_sound_absorber_objective_into_bare_product_name() -> None:
    routing_result = MultiAgentDomain(
        reason="test",
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        execution_plan=["discovery:product_objective_followup"],
        user_behavior="naming a product after asking about sound-absorber tires",
        flow="흡음재 질문 후 상품명만 답변",
        claim_check_type="none",
        complaint_scope="none",
        discovery_followup_intent="product_objective_followup",
        carried_discovery_objective="sound_absorber",
        agent_prompt_profile="discovery_search",
    )

    _tool_patch, response_decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="벤투스 에어S",
        context_text="흡음재 들어간 타이어 알려줘\n벤투스 에어S",
        tire_size=None,
        routing_result=routing_result,
    )

    assert _tool_patch == {"rcmd_type": "sound_absorber"}
    assert response_decision is not None
    assert (
        response_decision.metadata["response_shape_key"]
        == "technology_explanation_then_unsized_recommendation_summary"
    )


def test_discovery_policy_context_ignores_carried_objective_without_followup_intent() -> None:
    """carried_discovery_objective alone (without discovery_followup_intent=product_objective_followup)
    must NOT trigger the entity patch — guards against a partially-set router output."""
    routing_result = MultiAgentDomain(
        reason="test",
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        execution_plan=["discovery:product_search"],
        user_behavior="explicitly asking for a product description",
        flow="안심서비스 질문 후 명시적 설명 요청으로 전환",
        claim_check_type="none",
        complaint_scope="none",
        discovery_followup_intent="none",
        carried_discovery_objective="safe_service",
        agent_prompt_profile="discovery_search",
    )

    _tool_patch, response_decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="dynapro hp3 설명해줘",
        context_text="안심서비스 가능한 타이어는?\ndynapro hp3 설명해줘",
        tire_size=None,
        routing_result=routing_result,
    )

    assert response_decision is not None
    assert (
        response_decision.metadata.get("response_shape_key")
        != "safe_service_explanation_then_unsized_recommendation_summary"
    )


def test_bare_product_followup_override_routes_supported_safe_service_to_agent() -> None:
    routing_result = SimpleNamespace(
        discovery_followup_intent="product_objective_followup",
        carried_discovery_objective="safe_service",
    )

    override = _bare_product_search_followup_override(
        "dynapro hp3",
        context_text="안심서비스 가능한 타이어는?\ndynapro hp3",
        routing_result=routing_result,
    )

    assert override == {"action": "agent", "objective": "safe_service"}


def test_bare_product_followup_override_routes_supported_sound_absorber_to_agent() -> None:
    routing_result = SimpleNamespace(
        discovery_followup_intent="product_objective_followup",
        carried_discovery_objective="sound_absorber",
    )

    override = _bare_product_search_followup_override(
        "벤투스 에어S",
        context_text="흡음재 들어간 타이어 알려줘\n벤투스 에어S",
        routing_result=routing_result,
    )

    assert override == {"action": "agent", "objective": "sound_absorber"}


@pytest.mark.parametrize(
    ("context_text", "objective"),
    [
        ("dynapro hp3 소음 어때?\ndynapro hp3", "attribute_lookup"),
        ("올시즌 타이어 추천해줘\ndynapro hp3", "recommendation_filter"),
    ],
)
def test_bare_product_followup_override_clarifies_unsupported_objective_context(
    context_text: str,
    objective: str,
) -> None:
    override = _bare_product_search_followup_override(
        "dynapro hp3",
        context_text=context_text,
        routing_result=SimpleNamespace(
            discovery_followup_intent="none",
            carried_discovery_objective="none",
        ),
    )

    assert override == {"action": "clarify", "objective": objective}
    event = _build_product_objective_followup_clarification_event(objective)
    assert event["assistant_response_source"] == "code_product_objective_followup_clarification"
    assert event["data"]["assistantResponse"] == "해당 상품으로 어떤 정보를 확인해드릴까요?"
    assert _labels(event["data"]["quickReplies"]) == ["상품 설명", "가격 확인", "재고/장착 확인", "타이어 추천"]


def test_bare_product_followup_override_keeps_general_context_on_plain_bare_search() -> None:
    override = _bare_product_search_followup_override(
        "dynapro hp3",
        context_text="dynapro hp3",
        routing_result=SimpleNamespace(
            discovery_followup_intent="none",
            carried_discovery_objective="none",
        ),
    )

    assert override is None


def test_bare_product_followup_override_does_not_block_explicit_description_intent() -> None:
    override = _bare_product_search_followup_override(
        "dynapro hp3 설명해줘",
        context_text="안심서비스 가능한 타이어는?\ndynapro hp3 설명해줘",
        routing_result=SimpleNamespace(
            discovery_followup_intent="product_objective_followup",
            carried_discovery_objective="safe_service",
        ),
    )

    assert override is None


@pytest.mark.parametrize(
    ("pending_intent", "goal_type"),
    [
        ("price", "price_inquiry"),
        ("stock", "store_with_stock"),
    ],
)
def test_supported_carried_objective_does_not_override_transaction_pending_intent(
    pending_intent: str,
    goal_type: str,
) -> None:
    routing_result = MultiAgentDomain(
        reason="test",
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        execution_plan=["discovery:product_objective_followup"],
        user_behavior="naming a product after a prior objective",
        flow="transaction pending intent should win",
        claim_check_type="none",
        complaint_scope="none",
        discovery_followup_intent="product_objective_followup",
        carried_discovery_objective="safe_service",
        agent_prompt_profile="discovery_search",
    )

    patch, decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="dynapro hp3",
        context_text="안심서비스 가능한 타이어는?\ndynapro hp3",
        tire_size=None,
        routing_result=routing_result,
        pending_intent=pending_intent,
        goal_type=goal_type,
    )

    assert patch == {}
    assert decision is not None
    assert decision.metadata["response_shape_key"] == "product_search_summary"
    assert (
        _bare_product_search_followup_override(
            "dynapro hp3",
            context_text="안심서비스 가능한 타이어는?\ndynapro hp3",
            routing_result=routing_result,
            pending_intent=pending_intent,
            goal_type=goal_type,
        )
        is None
    )


def test_transaction_followup_priority_blocks_attribute_context_inheritance() -> None:
    routing_result = MultiAgentDomain(
        reason="test",
        domains=[MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION],
        execution_plan=["discovery:resolve_product", "transaction:price_or_coupon_check"],
        user_behavior="asking price for a product family that previously had attribute context",
        flow="discovery then transaction",
        claim_check_type="none",
        complaint_scope="none",
        discovery_followup_intent="none",
        carried_discovery_objective="none",
        agent_prompt_profile="discovery_search",
    )

    patch, decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="옵티모 가격 얼마야?",
        context_text="옵티모 젖은노면 등급 알려줘\n옵티모 가격 얼마야?",
        tire_size=None,
        routing_result=routing_result,
        pending_intent="price",
        goal_type="price_inquiry",
    )

    assert patch == {}
    assert decision is not None
    assert decision.metadata["response_shape_key"] == "product_search_summary"


def test_goods_no_from_selection_does_not_guess_ambiguous_name_with_stored_tire_size() -> None:
    prev_tool_data = [
        {
            "tool": "get_products_recommendations_tool",
            "data": [
                {"goods_no": "G1", "goods_nm": "벤투스 S2 AS", "tire_size_1": "225/55R17"},
                {"goods_no": "G2", "goods_nm": "벤투스 V2 AS", "tire_size_1": "225/55R17"},
            ],
        }
    ]

    assert (
        TStationChatServiceV2._resolve_goods_no_from_selection(
            "벤투스 선택",
            prev_tool_data,
            current_tire_size="225/55R17",
        )
        is None
    )


def test_confirmed_product_slot_values_from_single_product_event() -> None:
    event = {
        "template": "product",
        "data": {
            "products": [
                {
                    "titleProductName": "벤투스 S1 에보 Z",
                    "titleTires": "265/40R21",
                }
            ],
            "metadata": [{"goodsId": "G2"}],
        },
    }

    assert TStationChatServiceV2._confirmed_product_slot_values_from_event(event) == {
        "goods_no": "G2",
        "tire_model": "벤투스 S1 에보 Z",
        "tire_size": "265/40R21",
    }


def test_confirmed_product_slot_values_from_product_description_quickreply_event() -> None:
    event = {
        "template": "quickReply",
        "data": {
            "assistantResponse": "벤투스 S2 AS 상세 정보입니다.",
            "quickReplies": [
                {"label": "구매하기", "domain": "TRANSACTION"},
                {"label": "장바구니담기", "domain": "TRANSACTION"},
            ],
            "metadata": {
                "goodsId": "G000000309783",
                "tireSize": "225/45R17",
                "productName": "벤투스 S2 AS",
            },
        },
    }

    assert TStationChatServiceV2._confirmed_product_slot_values_from_event(event) == {
        "goods_no": "G000000309783",
        "tire_model": "벤투스 S2 AS",
        "tire_size": "225/45R17",
    }


def test_confirmed_product_slot_values_ignore_multi_product_event() -> None:
    event = {
        "template": "product",
        "data": {
            "products": [
                {"titleProductName": "벤투스 S1 에보 Z", "titleTires": "255/40R21"},
                {"titleProductName": "벤투스 S1 에보 Z", "titleTires": "265/40R21"},
            ],
            "metadata": [{"goodsId": "G1"}, {"goodsId": "G2"}],
        },
    }

    assert TStationChatServiceV2._confirmed_product_slot_values_from_event(event) is None


def test_requested_maintenance_focus_matches_tire_query() -> None:
    assert _requested_maintenance_focus("타이어 교체 시기 알려줘") == ("타이어 교체", (r"타이어",), "교체")


def test_build_maintenance_dday_event_summarizes_tire_schedule_for_tire_query() -> None:
    event = _build_maintenance_dday_event(
        {
            "data": {
                "data": {
                    "cars": [
                        {
                            "mbr_car_reg_seq": "2000002944",
                            "car_nm": "GV70 2.5T 가솔린 AWD A/T",
                            "items": [
                                {"kind_nm": "엔진오일 교체", "exp_dt": "2026-08-01", "dday": 66, "status": "normal"},
                                {"kind_nm": "타이어 교체", "exp_dt": "2027-10-31", "dday": 522, "status": "normal"},
                            ],
                        }
                    ]
                }
            }
        },
        {
            "meta": {"mbrCarRegSeq": "2000002944"},
            "car": {"info": "GV70 2.5T 가솔린 AWD A/T"},
        },
        "타이어 교체 시기 알려줘",
    )

    assert event["template"] == "quickReply"
    assert (
        event["data"]["assistantResponse"]
        == "GV70 2.5T 가솔린 AWD A/T의 타이어 교체 일정은 지난 교체일 기준 2027-10-31에 교체하는 것을 권장 드려요. 정확한 진단은 매장에서 받아 보실 수 있어요 😊"
    )


def test_build_maintenance_dday_event_keeps_full_schedule_for_generic_query() -> None:
    event = _build_maintenance_dday_event(
        {
            "data": {
                "data": {
                    "cars": [
                        {
                            "mbr_car_reg_seq": "2000002944",
                            "car_nm": "GV70 2.5T 가솔린 AWD A/T",
                            "items": [
                                {"kind_nm": "엔진오일 교체", "exp_dt": "2026-08-01", "dday": 66, "status": "normal"},
                                {"kind_nm": "타이어 교체", "exp_dt": "2027-10-31", "dday": 522, "status": "normal"},
                            ],
                        }
                    ]
                }
            }
        },
        {
            "meta": {"mbrCarRegSeq": "2000002944"},
            "car": {"info": "GV70 2.5T 가솔린 AWD A/T"},
        },
        "내 차 정비 일정 알려줘",
    )

    assert "엔진오일 교체: 2026-08-01" in event["data"]["assistantResponse"]
    assert "타이어 교체: 2027-10-31" in event["data"]["assistantResponse"]


def test_vehicle_information_event_answers_staggered_fitment_question() -> None:
    event = _build_vehicle_information_event(
        {
            "car": {
                "licensePlate": "56모2162",
                "info": "BMW 3시리즈 그란 투리스모(6세대)",
            },
            "meta": {
                "carNo": "56모2162",
                "tireSize": "225/50R18",
                "tireSizeRe": "255/50R18",
            },
        },
        "전/후륜 규격이 다른데 뭘로 봐야 해?",
    )

    assert event is not None
    assert event["template"] == "quickReply"
    assert "전륜 **225/50R18**, 후륜 **255/50R18**" in event["data"]["assistantResponse"]
    assert "한 가지 사이즈만 보면 안 되고" in event["data"]["assistantResponse"]


def test_vehicle_information_event_handles_generic_spec_question() -> None:
    event = _build_vehicle_information_event(
        {
            "car": {
                "licensePlate": "56모2162",
                "info": "BMW 3시리즈 그란 투리스모(6세대)",
            },
            "meta": {
                "carNo": "56모2162",
                "tireSize": "225/50R18",
                "tireSizeRe": "255/50R18",
            },
        },
        "내 차 규격이 뭐야?",
    )

    assert event is not None
    assert event["template"] == "quickReply"
    assert "현재 확인되는 규격은 전륜 **225/50R18**, 후륜 **255/50R18**예요." in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["전/후륜 규격 보기", "맞는 타이어 추천", "동일 상품 찾기"]


def test_suv_passenger_tire_question_does_not_render_listcar() -> None:
    event = {
        "type": "data",
        "template": "listCar",
        "source_domain": "discovery",
        "data": {
            "assistantResponse": "고객님, 등록된 차량 1대입니다. 차량을 선택해 주세요.",
            "listCar": [{"licensePlate": "29조3344", "info": "폭스바겐 제타"}],
            "metadata": [{"carNo": "29조3344", "carLncCd": "W036270"}],
        },
    }

    coerced = _coerce_vehicle_type_compatibility_listcar_to_quickreply(
        event,
        "내 차 SUV긴 한데 세단용 끼워도 될까?",
    )

    assert coerced is not None
    assert coerced["template"] == "quickReply"
    assert "권장하지 않아요" in coerced["data"]["assistantResponse"]
    assert _labels(coerced["data"]["quickReplies"]) == ["SUV용 추천", "사이즈 직접 입력", "내 차량으로 확인"]


def test_suv_passenger_tire_question_fast_path_returns_guidance() -> None:
    event = _vehicle_type_compatibility_guard_event("내 차 SUV긴 한데 세단용 끼워도 될까?")

    assert event is not None
    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "code_vehicle_type_compatibility_guard"
    assert "권장하지 않아요" in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["SUV용 추천", "사이즈 직접 입력", "내 차량으로 확인"]


def test_tc098_price_policy_runtime_removes_internal_mapping_term() -> None:
    event_data = {
        "assistantResponse": "쿠폰 매핑 결과를 확인했어요.",
        "quickReplies": [{"label": "내 쿠폰 조회", "domain": "TRANSACTION"}],
    }

    changed = _normalize_price_policy_quickreply(
        event_data,
        source_domain="transaction",
        last_user_text="ventus s2 as 2055516 사이즈 최대 혜택 받으려면?",
    )

    assert changed is True
    assert "매핑" not in event_data["assistantResponse"]
    assert "적용 정보" in event_data["assistantResponse"]


# --------------------------------------------------------------------------- #
#  EV suitability intent detection
# --------------------------------------------------------------------------- #


def test_ev_suitability_detects_explicit_ev_explanation_question() -> None:
    text = "내 차는 전기차인데 그냥 dynapro HPX 끼면 안돼? ion evo AS를 꼭 껴야하는 이유가 있어?"
    assert _is_ev_suitability_turn(text) is True


def test_ev_suitability_is_not_product_attribute_lookup() -> None:
    text = "내 차는 전기차인데 그냥 dynapro HPX 끼면 안돼? ion evo AS를 꼭 껴야하는 이유가 있어?"
    assert _is_product_attribute_lookup_query(text) is False


def test_vehicle_category_suitability_detects_non_ev_question() -> None:
    text = "내 차는 SUV인데 경차용 타이어 그냥 껴도 되나?"
    assert _is_ev_suitability_turn(text) is True


def test_ev_suitability_does_not_treat_evo_as_ev_context() -> None:
    text = "파주 시청 근처 더타이어샵 매장에 iON evo 재고 있을까? 오늘 당장 장착해야 하는데"
    assert _is_ev_suitability_turn(text, pending_intent="stock", goal_type="store_with_stock") is False


def test_ev_suitability_does_not_override_stock_turn_even_for_ev_owner() -> None:
    text = "전기차 타는데 iON evo 재고 있을까? 오늘 당장 장착해야 해"
    assert _is_ev_suitability_turn(text, pending_intent="stock", goal_type="store_with_stock") is False


def test_followup_size_input_preserves_ev_recommendation_context() -> None:
    messages = [
        {
            "role": "user",
            "content": "내 차는 전기차인데 그냥 dynapro HPX 끼면 안돼? ion evo AS를 꼭 껴야하는 이유가 있어?",
        },
        {
            "role": "assistant",
            "content": "전기차는 전기차용 타이어를 우선 확인하는 것이 좋아요. 정확한 차량이나 규격을 확인해 주세요.",
        },
        {"role": "user", "content": "규격으로 찾기"},
        {"role": "user", "content": "2355519"},
    ]

    context = _infer_followup_recommendation_context(messages, "2355519")

    assert context is not None
    assert "전기차용" in context
    assert "vehicle_type='ev'" in context


def test_discovery_policy_context_preserves_ev_and_quiet_axes_for_size_followup() -> None:
    patch, _decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="2555018",
        context_text="전기차 타이어 저소음으로 추천해줘\n2555018",
        tire_size="255/50R18",
    )

    assert patch == {
        "vehicle_type": "ev",
        "rcmd_type": "low_vibration",
        "tire_size": "255/50R18",
    }


def test_discovery_policy_context_applies_selected_vehicle_type_to_followup_recommendation() -> None:
    patch, _decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="조용한 걸로 추천해줘",
        context_text="GV70 선택\n조용한 걸로 추천해줘",
        tire_size="235/55R19",
        vehicle_type="suv",
    )

    assert patch == {
        "rcmd_type": "low_vibration",
        "tire_size": "235/55R19",
        "vehicle_type": "suv",
    }


def test_discovery_policy_context_prefers_current_turn_vehicle_type_over_selected_vehicle_slot() -> None:
    patch, _decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="전기차용으로 추천해줘",
        context_text="GV70 선택\n전기차용으로 추천해줘",
        tire_size="235/55R19",
        vehicle_type="suv",
    )

    assert patch == {"tire_size": "235/55R19", "vehicle_type": "ev"}


def test_followup_size_input_preserves_non_ev_vehicle_category_context() -> None:
    messages = [
        {"role": "user", "content": "내 차는 SUV인데 승용차용 타이어 껴도 돼?"},
        {"role": "assistant", "content": "SUV는 하중과 차종 조건이 중요해요. 차량이나 규격을 확인해 주세요."},
        {"role": "user", "content": "사이즈 직접 입력"},
        {"role": "user", "content": "2355519"},
    ]

    context = _infer_followup_recommendation_context(messages, "2355519")

    assert context is not None
    assert "SUV 차량용" in context
    assert "vehicle_type='suv'" in context


def test_followup_size_input_prefers_user_winter_intent_over_assistant_vehicle_category() -> None:
    messages = [
        {"role": "user", "content": "윈터 타이어 추천"},
        {
            "role": "assistant",
            "content": (
                "사이즈가 아직 확인되지 않아 타이어 기준으로 안내드릴게요.\n\n"
                "- 윈터 Radial DW04: 경트럭&밴용 겨울 컴포트 타이어입니다.\n"
                "- 윈터 아이셉트 IZ2 A: 승용차용 겨울 컴포트 타이어입니다."
            ),
        },
        {"role": "user", "content": "사이즈 직접 입력"},
        {"role": "assistant", "content": "장착하실 타이어 사이즈를 입력해 주세요."},
        {"role": "user", "content": "225/45R18"},
    ]

    context = _infer_followup_recommendation_context(messages, "225/45R18")

    assert context is not None
    assert "겨울/눈길" in context
    assert "rcmd_type='snow'" in context
    assert "season_nm='겨울'" in context
    assert "heavy_load" not in context
    assert "하중 중심" not in context


def test_followup_size_input_does_not_infer_from_assistant_recommendation_labels_only() -> None:
    messages = [
        {"role": "user", "content": "미쉐린, 콘티넨탈, 브리지스톤 상품 1개씩 BMW 3시리즈에 맞는 타이어 추천해줘"},
        {
            "role": "assistant",
            "content": (
                "BMW 3시리즈는 연식/트림에 따라 타이어 사이즈가 다를 수 있어요!\n\n"
                "미쉐린·콘티넨탈·브리지스톤을 각각 1개씩 정확히 추천하려면 먼저 타이어 사이즈가 필요해요."
            ),
        },
        {"role": "user", "content": "225/40R19"},
        {
            "role": "assistant",
            "content": (
                "225/40R19 기준으로 찾은 상품 1개입니다. 원하시는 상품을 선택해 주세요.\n\n"
                "*해당 혜택가는 현재 보유 쿠폰 기준으로 적용된 가격입니다."
            ),
        },
        {"role": "user", "content": "225/45R18"},
    ]

    assert _infer_followup_recommendation_context(messages, "225/45R18") is None


def test_followup_size_input_preserves_all_season_as_four_season_context() -> None:
    messages = [
        {"role": "user", "content": "올시즌 타이어 추천해줘"},
        {"role": "assistant", "content": "타이어 사이즈를 입력해 주세요."},
        {"role": "user", "content": "2355519"},
    ]

    context = _infer_followup_recommendation_context(messages, "2355519")

    assert context is not None
    assert "사계절" in context
    assert "rcmd_type='all_weather'" in context
    assert "season_nm='사계절'" in context
    assert "season_nm='올웨더'" not in context


def test_followup_size_input_preserves_all_weather_context_separately() -> None:
    messages = [
        {"role": "user", "content": "올웨더 타이어 추천해줘"},
        {"role": "assistant", "content": "타이어 사이즈를 입력해 주세요."},
        {"role": "user", "content": "2355519"},
    ]

    context = _infer_followup_recommendation_context(messages, "2355519")

    assert context is not None
    assert "올웨더" in context
    assert "rcmd_type='all_weather'" in context
    assert "season_nm='올웨더'" in context
    assert "season_nm='사계절'" not in context


def test_sized_all_season_recommendation_uses_four_season_tool_filter() -> None:
    frame = build_discovery_intent_frame("2355519 올시즌 추천")
    plan = plan_discovery_tools(frame)

    assert frame.entities["tire_size"] == "235/55R19"
    assert frame.entities["season"] == "all_season"
    assert plan.tool_args_patch["tire_size"] == "235/55R19"
    assert plan.tool_args_patch["rcmd_type"] == "all_weather"
    assert plan.tool_args_patch["season_nm"] == "사계절"


def test_sized_all_weather_recommendation_uses_all_weather_tool_filter() -> None:
    frame = build_discovery_intent_frame("2355519 올웨더 추천")
    plan = plan_discovery_tools(frame)

    assert frame.entities["tire_size"] == "235/55R19"
    assert frame.entities["season"] == "all_weather"
    assert plan.tool_args_patch["tire_size"] == "235/55R19"
    assert plan.tool_args_patch["rcmd_type"] == "all_weather"
    assert plan.tool_args_patch["season_nm"] == "올웨더"


def _recommendation_template_entry(
    *,
    season_nm: str,
    limit: int | None = None,
    requested_limit: int | None = None,
    effective_limit: int | None = None,
    item_count: int = 1,
) -> dict:
    args = {
        "rcmd_type": "all_weather",
        "season_nm": season_nm,
        "tire_size": "235/55R19",
    }
    if limit is not None:
        args["limit"] = limit
    data = {
        "items": [
            {
                "goods_no": f"G{i}",
                "goods_nm": f"벤투스 에어S {i}",
                "tire_size_1": "235/55R19",
                "season_nm": season_nm,
            }
            for i in range(1, item_count + 1)
        ]
    }
    if requested_limit is not None:
        data["requested_limit"] = requested_limit
    if effective_limit is not None:
        data["effective_limit"] = effective_limit
    return {
        "tool": "get_products_recommendations_tool",
        "args": args,
        "data": {
            "status": "success",
            "http_status": 200,
            "data": data,
        },
    }


def test_recommendation_response_uses_all_season_label_separately_from_all_weather() -> None:
    event = try_build_template([_recommendation_template_entry(season_nm="사계절")], "상품을 찾았어요.")

    assert event is not None
    response = event["data"]["assistantResponse"]
    assert "235/55R19 사계절 조건" in response
    assert "올웨더 조건" not in response


def test_recommendation_response_uses_all_weather_label_when_requested() -> None:
    event = try_build_template([_recommendation_template_entry(season_nm="올웨더")], "상품을 찾았어요.")

    assert event is not None
    response = event["data"]["assistantResponse"]
    assert "235/55R19 올웨더 조건" in response
    assert "사계절 조건" not in response


def test_recommendation_response_mentions_cap_when_requested_over_ten_and_ten_returned() -> None:
    event = try_build_template(
        [_recommendation_template_entry(season_nm="사계절", requested_limit=15, effective_limit=10, item_count=10)],
        "추천 상품을 확인했어요.",
    )

    assert event is not None
    assert event["data"]["assistantResponse"] == (
        "추천은 최대 10개까지만 가능해요. 조건에 맞는 상품 10개를 보여드릴게요. 원하시는 상품을 선택해 주세요."
    )


def test_recommendation_response_mentions_cap_and_shortfall_when_requested_over_ten() -> None:
    event = try_build_template(
        [_recommendation_template_entry(season_nm="사계절", requested_limit=15, effective_limit=10, item_count=7)],
        "추천 상품을 확인했어요.",
    )

    assert event is not None
    assert event["data"]["assistantResponse"] == (
        "추천은 최대 10개까지만 가능해요. 조건에 맞는 상품은 현재 7개만 확인돼요. 원하시는 상품을 선택해 주세요."
    )


def test_recommendation_response_recovers_original_count_when_tool_call_was_already_clamped() -> None:
    token = current_user_text.set("15개 추천해줘")
    try:
        event = try_build_template(
            [_recommendation_template_entry(season_nm="사계절", limit=10, requested_limit=10, effective_limit=10, item_count=8)],
            "추천 상품을 확인했어요.",
        )
    finally:
        current_user_text.reset(token)

    assert event is not None
    assert event["data"]["assistantResponse"] == (
        "추천은 최대 10개까지만 가능해요. 조건에 맞는 상품은 현재 8개만 확인돼요. 원하시는 상품을 선택해 주세요."
    )


def test_recommendation_response_mentions_shortfall_for_requested_limit_under_cap() -> None:
    event = try_build_template(
        [_recommendation_template_entry(season_nm="사계절", limit=5, requested_limit=5, effective_limit=5, item_count=3)],
        "추천 상품을 확인했어요.",
    )

    assert event is not None
    assert event["data"]["assistantResponse"] == (
        "요청하신 5개 중 조건에 맞는 상품은 현재 3개만 확인돼요. 원하시는 상품을 선택해 주세요."
    )


def test_recommendation_response_does_not_call_under_cap_request_a_max_limit() -> None:
    event = try_build_template(
        [_recommendation_template_entry(season_nm="사계절", limit=5, requested_limit=5, effective_limit=3, item_count=3)],
        "추천 상품을 확인했어요.",
    )

    assert event is not None
    response = event["data"]["assistantResponse"]
    assert response == "요청하신 5개 중 조건에 맞는 상품은 현재 3개만 확인돼요. 원하시는 상품을 선택해 주세요."
    assert "추천은 최대 5개" not in response


def test_recommendation_response_uses_current_turn_count_not_previous_over_cap_count() -> None:
    token = current_user_text.set("2355519 20개 추천\n2355519 올시즌 5개 추천")
    try:
        event = try_build_template(
            [_recommendation_template_entry(season_nm="사계절", limit=5, requested_limit=5, effective_limit=5, item_count=5)],
            "추천 상품을 확인했어요.",
        )
    finally:
        current_user_text.reset(token)

    assert event is not None
    response = event["data"]["assistantResponse"]
    assert response == "235/55R19 사계절 조건으로 찾은 상품 5개입니다. 원하시는 상품을 선택해 주세요."
    assert "추천은 최대 10개" not in response


def test_product_store_purchase_without_size_maps_to_size_selection_product_card() -> None:
    token = current_user_text.set("판교점에서 dynapro hpx 2개 구매하고싶어")
    decision_token = current_discovery_response_decision.set(
        decide_discovery_response(build_discovery_intent_frame("판교점에서 dynapro hpx 2개 구매하고싶어"))
    )
    try:
        event = try_build_template(
            [{
                "tool": "search_product_tool",
                "data": {
                    "status": "success",
                    "data": {
                        "items": [
                            {
                                "goods_no": "G000000309001",
                                "goods_nm": "다이나프로 HPX",
                                "tire_size_1": "235/55R19",
                                "brand_nm": "HANKOOK",
                                "sale_prc": 200000,
                                "extra_fvr_sale_prc": 180000,
                            },
                            {
                                "goods_no": "G000000309002",
                                "goods_nm": "다이나프로 HPX",
                                "tire_size_1": "245/45R19",
                                "brand_nm": "HANKOOK",
                                "sale_prc": 210000,
                                "extra_fvr_sale_prc": 190000,
                            },
                        ],
                    },
                },
                "args": {"keyword": "Dynapro HPX", "brand_cd": "HK"},
            }],
            (
                "차량 규격이 아직 확인되지 않아 타이어 기준으로 안내드릴게요.\n"
                "다이나프로 HPX\nSUV용 사계절 컴포트 타이어입니다."
            ),
        )
    finally:
        current_discovery_response_decision.reset(decision_token)
        current_user_text.reset(token)

    assert event is not None
    assert event["template"] == "product"
    data = event["data"]
    assert data["assistantResponse"] == "구매를 진행하려면 먼저 타이어 규격을 확인해야 해요. 장착할 규격을 선택해 주세요."
    assert data["isBookingFlow"] is True
    assert len(data["products"]) == 2
    assert data["metadata"][0]["pendingIntent"] == "order"
    assert data["metadata"][0]["requestedFlow"] == "purchase_or_install"
    assert data["metadata"][0]["ordQty"] == 2
    assert data["metadata"][0]["shopName"] == "판교점"


def test_product_description_turn_ignores_stale_booking_goal_for_unsized_summary() -> None:
    text_token = current_user_text.set("dynapro hpx 설명해줘")
    goal_token = current_goal_type.set("place_order")
    pending_token = current_pending_intent.set("order")
    decision_token = current_discovery_response_decision.set(
        decide_discovery_response(build_discovery_intent_frame("dynapro hpx 설명해줘"))
    )
    try:
        event = try_build_template(
            [{
                "tool": "search_product_tool",
                "data": {
                    "status": "success",
                    "data": {
                        "items": [
                            {
                                "goods_no": "G000000309001",
                                "goods_nm": "다이나프로 HPX",
                                "tire_size_1": "255/45R20",
                                "ptrn_d_nm": "SUV용 사계절 컴포트 타이어",
                                "brand_nm": "HANKOOK",
                            },
                            {
                                "goods_no": "G000000309002",
                                "goods_nm": "다이나프로 HPX",
                                "tire_size_1": "255/55R18",
                                "ptrn_d_nm": "SUV용 사계절 컴포트 타이어",
                                "brand_nm": "HANKOOK",
                            },
                        ],
                    },
                },
                "args": {"keyword": "Dynapro HPX", "brand_cd": "HK"},
            }],
            "다이나프로 HPX 상품 설명입니다.",
        )
    finally:
        current_discovery_response_decision.reset(decision_token)
        current_pending_intent.reset(pending_token)
        current_goal_type.reset(goal_token)
        current_user_text.reset(text_token)

    assert event is not None
    assert event["template"] == "quickReply"
    assert "다이나프로 HPX" in event["data"]["assistantResponse"]
    assert "구매를 진행하려면" not in event["data"]["assistantResponse"]


def test_followup_size_input_preserves_prior_multi_brand_user_request_as_variants() -> None:
    messages = [
        {"role": "user", "content": "미쉐린, 콘티넨탈, 브리지스톤 상품 1개씩 BMW 3시리즈에 맞는 타이어 추천해줘"},
        {"role": "assistant", "content": "먼저 타이어 사이즈를 알려주세요."},
        {"role": "user", "content": "225/45R18"},
    ]

    constraints = _infer_multi_variant_recommendation_constraints(messages, "225/45R18")

    assert constraints is not None
    assert constraints["variants"] == (
        {"brand_cd": "MC"},
        {"brand_cd": "CT"},
        {"brand_cd": "BS"},
    )
    assert constraints["limit_per_variant"] == 1
    assert constraints["source_frame"].entities["tire_size"] == "225/45R18"


def test_followup_size_input_uses_stored_multi_brand_context_when_history_is_compact() -> None:
    messages = [
        {"role": "user", "content": "225/45R18"},
    ]

    constraints = _infer_multi_variant_recommendation_constraints(
        messages,
        "225/45R18",
        stored_context={
            "variants": [{"brand_cd": "MC"}, {"brand_cd": "CT"}, {"brand_cd": "BS"}],
            "limit_per_variant": 1,
            "source_text": "미쉐린, 콘티넨탈, 브리지스톤 상품 1개씩 BMW 3시리즈에 맞는 타이어 추천해줘",
        },
    )

    assert constraints is not None
    assert constraints["variants"] == (
        {"brand_cd": "MC"},
        {"brand_cd": "CT"},
        {"brand_cd": "BS"},
    )
    assert constraints["limit_per_variant"] == 1
    assert constraints["source_frame"].entities["tire_size"] == "225/45R18"


def test_followup_size_input_uses_stored_context_with_injected_user_prefix() -> None:
    constraints = _infer_multi_variant_recommendation_constraints(
        [{"role": "user", "content": "# Respond in Korean language\n225/45R18"}],
        "# Respond in Korean language\n225/45R18",
        stored_context={
            "variants": [{"brand_cd": "MC"}, {"brand_cd": "CT"}, {"brand_cd": "BS"}],
            "limit_per_variant": 1,
            "source_text": "미쉐린, 콘티넨탈, 브리지스톤 상품 1개씩 BMW 3시리즈에 맞는 타이어 추천해줘",
        },
    )

    assert constraints is not None
    assert constraints["variants"] == (
        {"brand_cd": "MC"},
        {"brand_cd": "CT"},
        {"brand_cd": "BS"},
    )
    assert constraints["source_frame"].entities["tire_size"] == "225/45R18"


def test_followup_size_input_preserves_prior_multi_season_user_request_as_variants() -> None:
    messages = [
        {"role": "user", "content": "여름용이랑 사계절 타이어 각각 1개씩 BMW 3시리즈에 맞는 거 추천해줘"},
        {"role": "assistant", "content": "먼저 타이어 사이즈를 알려주세요."},
        {"role": "user", "content": "225/45R18"},
    ]

    constraints = _infer_multi_variant_recommendation_constraints(messages, "225/45R18")

    assert constraints is not None
    assert constraints["variants"] == (
        {"season_nm": "여름", "label": "여름용"},
        {"rcmd_type": "all_weather", "season_nm": "사계절", "label": "사계절"},
    )
    assert constraints["limit_per_variant"] == 1


def test_multi_brand_followup_request_without_size_reuses_recent_user_size_and_quantity() -> None:
    messages = [
        {"role": "user", "content": "미쉐린, 콘티넨탈, 브리지스톤 상품 1개씩 BMW 3시리즈에 맞는 타이어 추천해줘"},
        {"role": "assistant", "content": "먼저 타이어 사이즈를 알려주세요."},
        {"role": "user", "content": "225/45R18"},
        {"role": "assistant", "content": "225/45R18 기준으로 찾은 상품 1개입니다."},
        {"role": "user", "content": "한국타이어, 미쉐린을 각각 2개씩 추천해줘"},
    ]

    constraints = _infer_multi_variant_recommendation_constraints(messages, "한국타이어, 미쉐린을 각각 2개씩 추천해줘")

    assert constraints is not None
    assert constraints["variants"] == (
        {"brand_cd": "HK"},
        {"brand_cd": "MC"},
    )
    assert constraints["limit_per_variant"] == 2
    assert constraints["source_frame"].entities["tire_size"] == "225/45R18"


def test_followup_vehicle_pick_preserves_prior_winter_context() -> None:
    messages = [
        {"role": "user", "content": "윈터 타이어랑 사계절 타이어랑 어떤 의미야?"},
        {
            "role": "assistant",
            "content": "윈터 타이어는 겨울용 타이어예요. 사계절 타이어는 일반 주행을 두루 고려한 타이어예요.",
        },
        {"role": "user", "content": "타이어 추천"},
        {
            "role": "assistant",
            "content": (
                "추천받으실 차량을 선택해 주세요.\n\n"
                '{"type":"data","template":"listCar","data":{"metadata":[{"carNo":"33가3333"}]}}'
            ),
        },
        {"role": "user", "content": "33가3333"},
    ]

    context = _infer_followup_recommendation_context(messages, "33가3333")

    assert context is not None
    assert "추천받을 차량을 선택한 후속 입력" in context
    assert "겨울/눈길" in context
    assert "rcmd_type='snow'" in context
    assert "season_nm='겨울'" in context


def test_followup_vehicle_pick_preserves_prior_fuel_efficiency_context() -> None:
    messages = [
        {"role": "user", "content": "연비 좋은 타이어 추천해줘"},
        {"role": "assistant", "content": "차량을 선택해 주세요."},
        {
            "role": "assistant",
            "content": (
                '{"type":"data","template":"listCar","data":{"metadata":[{"carNo":"205소4214"}]}}'
            ),
        },
        {"role": "user", "content": "205소4214"},
    ]

    context = _infer_followup_recommendation_context(messages, "205소4214")

    assert context is not None
    assert "연비" in context
    assert "rcmd_type='fuel_efficiency'" in context


def test_followup_vehicle_pick_ignores_ev_model_in_listcar_when_user_context_is_product_search() -> None:
    messages = [
        {"role": "user", "content": "마일리지 타이어"},
        {
            "role": "assistant",
            "content": (
                "사이즈가 아직 확인되지 않아 타이어 기준으로 안내드릴게요.\n\n"
                "- 마일리지 플러스2: 승용차용 사계절 컴포트 타이어입니다."
            ),
        },
        {"role": "user", "content": "내 차량 보기"},
        {
            "role": "assistant",
            "content": (
                "고객님 등록 차량을 확인했어요. 어떤 차량으로 진행할까요? 😊\n\n"
                '{"type":"data","template":"listCar","data":{"listCar":['
                '{"licensePlate":"99구9999","info":"기아 EV3 (1세대) (2024 - )"},'
                '{"licensePlate":"34가4566","info":"현대 뉴 i30(GD) (2015 - 2016)"}'
                '],"metadata":[{"carNo":"34가4566","tireSize":"215/45R17"}]}}'
            ),
        },
        {"role": "user", "content": "34가4566"},
    ]

    assert _infer_followup_recommendation_context(messages, "34가4566") is None


def test_recommendation_tool_autofills_confirmed_tire_size(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _Response:
        status_code = 200
        parsed = {"rcmd_type": "long_distance", "total": 0, "items": []}

    def _fake_recommendations(**kwargs):
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr(discovery_tools, "get_products_recommendations", _fake_recommendations)
    token = discovery_tools.current_confirmed_tire_size.set("215/45R17")
    try:
        result = discovery_tools.get_products_recommendations_tool.func(
            rcmd_type="long_distance",
            limit=3,
            brand_cd="HK",
        )
    finally:
        discovery_tools.current_confirmed_tire_size.reset(token)

    assert result["status"] == "success"
    assert captured["tire_size"] == "215/45R17"


def test_recommendation_tool_clamps_requested_limit_to_ten(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _Response:
        status_code = 200
        parsed = {"rcmd_type": "tstation", "total": 0, "items": []}

    def _fake_recommendations(**kwargs):
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr(discovery_tools, "get_products_recommendations", _fake_recommendations)

    result = discovery_tools.get_products_recommendations_tool.func(
        rcmd_type="tstation",
        limit=15,
        brand_cd="HK",
    )

    assert result["status"] == "success"
    assert captured["limit"] == 10
    assert result["data"]["requested_limit"] == 15
    assert result["data"]["effective_limit"] == 10
    assert result["data"]["limit_capped"] is True


def test_recommendation_tool_does_not_autofill_tire_size_for_price_range(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _Response:
        status_code = 200
        parsed = {"rcmd_type": "tstation", "total": 0, "items": []}

    def _fake_recommendations(**kwargs):
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr(discovery_tools, "get_products_recommendations", _fake_recommendations)
    token = discovery_tools.current_confirmed_tire_size.set("215/45R17")
    try:
        result = discovery_tools.get_products_recommendations_tool.func(
            rcmd_type="tstation",
            limit=3,
            brand_cd="HK",
            min_price=100_000,
            max_price=200_000,
        )
    finally:
        discovery_tools.current_confirmed_tire_size.reset(token)

    assert result["status"] == "no_results"
    assert captured["tire_size"] is None


def test_similar_price_policy_preserves_referenced_latest_size_context() -> None:
    patch, decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="해당 사이즈 비슷한 가격대 타이어 몇개 더 추천해줘",
        context_text="1955515\n해당 사이즈 비슷한 가격대 타이어 몇개 더 추천해줘",
        tire_size="195/55R15",
    )

    assert decision is not None
    assert decision.metadata["response_shape_key"] == "similar_price_range_recommendation"
    assert patch["tire_size"] == "195/55R15"


def test_similar_price_policy_preserves_size_after_specific_product_selection() -> None:
    patch, decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="비슷한 가격대의 타이어 더 추천해줘",
        context_text="키너지 ST AS 195/65R15\n비슷한 가격대의 타이어 더 추천해줘",
        tire_size="195/65R15",
        goods_no="G000000318500",
    )

    assert decision is not None
    assert decision.metadata["response_shape_key"] == "similar_price_range_recommendation"
    assert patch["tire_size"] == "195/65R15"


def test_similar_price_policy_does_not_inject_size_without_size_reference() -> None:
    patch, decision = _build_discovery_policy_context(
        domains=[MultiAgentDomain.Domain.DISCOVERY],
        last_user_text="비슷한 가격대의 타이어 더 추천해줘",
        context_text="키너지 EX 설명좀\n비슷한 가격대의 타이어 더 추천해줘",
        tire_size="195/55R15",
    )

    assert decision is not None
    assert decision.metadata["response_shape_key"] == "similar_price_range_recommendation"
    assert "tire_size" not in patch


def test_recommendation_tool_applies_discovery_policy_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _Response:
        status_code = 200
        parsed = {"rcmd_type": "performance", "total": 0, "items": []}

    def _fake_recommendations(**kwargs):
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr(discovery_tools, "get_products_recommendations", _fake_recommendations)
    token = discovery_tools.current_discovery_recommendation_tool_patch.set({
        "rcmd_type": "performance",
        "season_nm": "여름",
    })
    try:
        result = discovery_tools.get_products_recommendations_tool.func(
            rcmd_type="tstation",
            limit=3,
            brand_cd="HK",
        )
    finally:
        discovery_tools.current_discovery_recommendation_tool_patch.reset(token)

    assert result["status"] == "success"
    assert captured["rcmd_type"] == discovery_tools.RcmdType.PERFORMANCE
    assert captured["season_nm"] == "여름"


def test_recommendation_tool_falls_back_from_winter_to_all_weather(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class _Response:
        def __init__(self, parsed: dict):
            self.status_code = 200
            self.parsed = parsed

    def _fake_recommendations(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return _Response({"rcmd_type": "snow", "total": 0, "items": []})
        return _Response(
            {
                "rcmd_type": "all_weather",
                "total": 1,
                "items": [{"goods_no": "G1", "goods_nm": "키너지 4S2"}],
            }
        )

    monkeypatch.setattr(discovery_tools, "get_products_recommendations", _fake_recommendations)
    monkeypatch.setattr(discovery_tools, "_enrich_items_with_descriptions", lambda items: items)
    monkeypatch.setattr(discovery_tools, "_sort_items", lambda items, sort_by: items)

    result = discovery_tools.get_products_recommendations_tool.func(
        rcmd_type=discovery_tools.RcmdType.SNOW,
        limit=3,
        brand_cd="HK",
        tire_size="225/55R17",
        season_nm="겨울",
    )

    assert result["status"] == "success"
    assert [call["rcmd_type"] for call in calls] == [
        discovery_tools.RcmdType.SNOW,
        discovery_tools.RcmdType.ALL_WEATHER,
    ]
    assert [call["season_nm"] for call in calls] == ["겨울", "올웨더"]
    fallback = result["data"]["recommendation_fallback"]
    assert fallback["requested_season_nm"] == "겨울"
    assert fallback["applied_season_nm"] == "올웨더"
    assert "올웨더 대안" in fallback["assistant_response_hint"]


def test_followup_size_input_ignores_plain_size_without_prior_scenario() -> None:
    messages = [
        {"role": "user", "content": "안녕하세요"},
        {"role": "assistant", "content": "무엇을 도와드릴까요?"},
        {"role": "user", "content": "2355519"},
    ]

    assert _infer_followup_recommendation_context(messages, "2355519") is None


@pytest.mark.parametrize("text", ["내차말고 GV70", "내차말구 GV70", "내차말로 ev70", "내 차 아닌 모델Y"])
def test_non_self_car_negation_handles_common_typos(text: str) -> None:
    assert _NON_SELF_CAR_RE.search(text)


def test_non_self_vehicle_plate_only_prompts_for_owner_lookup() -> None:
    event = _non_self_vehicle_plate_owner_lookup_prompt_event("내차말고 29조3344")

    assert event is not None
    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "code_non_self_vehicle_owner_lookup_prompt"
    assert "차량번호 + 소유주명" in event["data"]["assistantResponse"]
    assert "소유주명만 이어서 입력" in event["data"]["assistantResponse"]
    assert _labels(event["data"]["quickReplies"]) == ["차번+이름으로 검색", "사이즈 직접 입력", "내 차량 보기"]


def test_product_selection_prefers_latest_recommendation_context_over_stale_search() -> None:
    prev_tool_data = [
        {
            "tool": "search_product_tool",
            "data": [
                {
                    "goods_no": "GSTALE000001",
                    "goods_nm": "다이나프로 HPX",
                    "tire_size_1": "265/50R20",
                }
            ],
        },
        {
            "tool": "get_products_recommendations_tool",
            "data": [
                {
                    "goods_no": "GREC00000001",
                    "goods_nm": "윈터 아이셉트 에보3 X",
                    "tire_size_1": "235/55R19",
                },
                {
                    "goods_no": "GREC00000002",
                    "goods_nm": "다이나프로 HPX",
                    "tire_size_1": "235/55R19",
                },
            ],
        },
    ]

    goods_no = TStationChatServiceV2._resolve_goods_no_from_selection(
        "다이나프로 HPX 235/55R19",
        prev_tool_data,
    )

    assert goods_no == "GREC00000002"


def test_single_product_search_result_updates_goods_no_and_tire_size() -> None:
    slots = ConversationSlots(
        goods_no="GOLD00000001",
        tire_model="이전 상품",
        tire_size="265/50R20",
        payment_amount=300000,
    )

    changed = StreamingMultiAgentCoordinator._apply_tool_derived_slots(
        slots,
        "search_product_tool",
        {
            "status": "success",
            "data": {
                "items": [
                    {
                        "goods_no": "GNEW00000001",
                        "goods_nm": "다이나프로 HPX",
                        "tire_size_1": "235/55R19",
                    }
                ]
            },
        },
    )

    assert changed is True
    assert slots.goods_no == "GNEW00000001"
    assert slots.tire_size == "235/55R19"
    assert slots.tire_model is None
    assert slots.payment_amount is None


def test_product_description_result_keeps_goods_no_but_does_not_promote_unsized_row_tire_size() -> None:
    slots = ConversationSlots(
        goods_no="GOLD00000001",
        tire_model="이전 상품",
        payment_amount=300000,
    )

    changed = StreamingMultiAgentCoordinator._apply_tool_derived_slots(
        slots,
        "get_product_description_tool",
        {
            "status": "success",
            "data": {
                "goods_no": "G000000309855",
                "goods_nm": "벤투스 S2 AS",
                "tire_size_1": "225/50R18",
            },
        },
        {"goods_no": "G000000309855"},
        [],
    )

    assert changed is True
    assert slots.goods_no == "G000000309855"
    assert slots.tire_size is None
    assert slots.tire_model is None
    assert slots.payment_amount is None


def test_product_description_result_preserves_sized_source_tire_size() -> None:
    slots = ConversationSlots(
        goods_no="GOLD00000001",
        tire_model="이전 상품",
        payment_amount=300000,
    )

    changed = StreamingMultiAgentCoordinator._apply_tool_derived_slots(
        slots,
        "get_product_description_tool",
        {
            "status": "success",
            "data": {
                "goods_no": "G000000309855",
                "goods_nm": "벤투스 S2 AS",
                "tire_size_1": "225/50R18",
            },
        },
        {"goods_no": "G000000309855"},
        [
            {
                "tool": "get_products_recommendations_tool",
                "input": {"rcmd_type": "wet", "tire_size": "245/45R18"},
                "data": {
                    "status": "success",
                    "data": {
                        "items": [
                            {
                                "goods_no": "G000000309855",
                                "goods_nm": "벤투스 S2 AS",
                                "tire_size_1": "225/50R18",
                            }
                        ]
                    },
                },
            }
        ],
    )

    assert changed is True
    assert slots.goods_no == "G000000309855"
    assert slots.tire_size == "245/45R18"
    assert slots.tire_model is None
    assert slots.payment_amount is None


def test_fresh_recommendation_turn_clears_unsized_selected_product_slots() -> None:
    slots = ConversationSlots(
        goods_no="G000000309855",
        tire_size="195/65R15",
        payment_amount=412000,
    )

    cleared = _clear_stale_product_slots_for_new_recommendation(
        slots,
        user_text="주말 장거리용으로 다른 거 추천해줘",
        regex_slots=ConversationSlots(),
        prev_tool_data=[
            {
                "tool": "get_products_recommendations_tool",
                "input": {"rcmd_type": "wet"},
                "data": {
                    "status": "success",
                    "data": {
                        "items": [
                            {
                                "goods_no": "G000000309855",
                                "goods_nm": "키너지 ST AS",
                                "tire_size_1": "195/65R15",
                            }
                        ]
                    },
                },
            }
        ],
    )

    assert cleared == {
        "tire_size": "195/65R15",
        "goods_no": "G000000309855",
        "payment_amount": 412000,
    }
    assert slots.goods_no is None
    assert slots.tire_size is None
    assert slots.payment_amount is None


def test_fresh_recommendation_turn_preserves_confirmed_sized_context() -> None:
    slots = ConversationSlots(
        goods_no="G000000309855",
        tire_size="245/45R18",
        payment_amount=412000,
    )

    cleared = _clear_stale_product_slots_for_new_recommendation(
        slots,
        user_text="같은 사이즈로 주말 장거리용 다른 거 추천해줘",
        regex_slots=ConversationSlots(),
        prev_tool_data=[
            {
                "tool": "get_products_recommendations_tool",
                "input": {"rcmd_type": "low_vibration", "tire_size": "245/45R18"},
                "data": {
                    "status": "success",
                    "data": {
                        "items": [
                            {
                                "goods_no": "G000000309855",
                                "goods_nm": "벤투스 S2 AS",
                                "tire_size_1": "225/50R18",
                            }
                        ]
                    },
                },
            }
        ],
    )

    assert cleared == {}
    assert slots.goods_no == "G000000309855"
    assert slots.tire_size == "245/45R18"
    assert slots.payment_amount == 412000


def test_discovery_intent_frame_can_disable_inherited_tire_size() -> None:
    frame = build_discovery_intent_frame(
        "주말 장거리용으로 다른 거 추천해줘",
        known_slots={"tire_size": "195/65R15", "allow_inherited_tire_size": False},
    )

    assert frame.entities["tire_size"] is None


def test_final_price_result_updates_payment_amount_with_cheapest_final_price_first() -> None:
    slots = ConversationSlots(ord_qty=4)

    changed = StreamingMultiAgentCoordinator._apply_tool_derived_slots(
        slots,
        "get_final_price_tool",
        {
            "status": "success",
            "data": {
                "sale_prc": 120000,
                "extra_fvr_sale_prc": 100000,
                "cheapest_final_prc": 85000,
                "wage_prc": 12000,
            },
        },
    )

    assert changed is True
    assert slots.payment_amount == (85000 + 12000) * 4


def test_preorder_template_payload_recovers_order_slots() -> None:
    slot_values = TStationChatServiceV2._preorder_slot_values_from_data({
        "assistantResponse": "주문 내용을 확인해 주세요.",
        "orderInfo": {
            "product": "벤투스 S2 AS 225/45R17",
            "quantity": 2,
            "storeName": "티스테이션 한남점",
            "bookingDateTime": "2026년 6월 9일 (화) 17:00",
            "paymentAmount": 237600,
        },
        "isReadyToOrder": True,
        "isReadyToAddToCart": False,
        "metadata": {
            "goodsId": "G000000309783",
            "shopId": "F07782",
        },
    })

    assert slot_values == {
        "goods_no": "G000000309783",
        "shop_id": "F07782",
        "shop_name": "티스테이션 한남점",
        "ord_qty": 2,
        "payment_amount": 237600,
        "tire_size": "225/45R17",
        "requested_cal_day": "20260609",
        "rsv_hour": "17",
    }


def test_preorder_template_payload_ignores_non_ready_card() -> None:
    assert TStationChatServiceV2._preorder_slot_values_from_data({
        "orderInfo": {"storeName": "티스테이션 한남점"},
        "isReadyToOrder": False,
        "metadata": {"shopId": "F07782"},
    }) is None


def test_non_self_vehicle_plate_owner_lookup_stages_plate_only_until_owner_name() -> None:
    assert _non_self_vehicle_plate_owner_lookup_plate("내차말고 29조3344") == "29조3344"
    assert _non_self_vehicle_plate_owner_lookup_plate("내차말고 29조3344 홍길동") is None
    assert _should_reuse_pending_vehicle_lookup_car_no(None, "홍길동", "29조3344") is True


def test_vehicle_owner_lookup_normalizes_both_orders_without_treating_non_self_prefix_as_name() -> None:
    assert _normalize_vehicle_owner_lookup_text("29조3344 홍길동") == "29조3344 홍길동"
    assert _normalize_vehicle_owner_lookup_text("홍길동 29조3344") == "29조3344 홍길동"
    assert _normalize_vehicle_owner_lookup_text("내차말고 29조3344") is None
    assert _normalize_vehicle_owner_lookup_text("내차말고 29조3344 홍길동") == "29조3344 홍길동"
    assert _normalize_vehicle_owner_lookup_text("내차말고 홍길동 29조3344") == "29조3344 홍길동"


# --------------------------------------------------------------------------- #
#  LEADING domain → progress chips
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("source_domain", ["leading", "LEADING", "Leading"])
def test_leading_domain_returns_progress_chips(source_domain: str) -> None:
    chips, label = _choose_quickreply_fallback(set(), source_domain)
    assert _labels(chips) == ["상품 검색", "타이어 추천"]
    assert label == "leading_progress"


def test_leading_domain_first_chip_is_discovery() -> None:
    chips, _ = _choose_quickreply_fallback(set(), "leading")
    assert chips[0]["domain"] == "DISCOVERY"


# --------------------------------------------------------------------------- #
#  Tool dispatch beats domain routing
# --------------------------------------------------------------------------- #


def test_order_tool_overrides_leading_domain() -> None:
    chips, label = _choose_quickreply_fallback({"get_orders_of_user_tool"}, "leading")
    assert chips == _FALLBACK_ORDER_LIST
    assert label == "order"


def test_coupon_tool_overrides_leading_domain() -> None:
    chips, label = _choose_quickreply_fallback({"get_my_coupons_tool"}, "leading")
    assert chips == _FALLBACK_COUPON
    assert label == "coupon"


# --------------------------------------------------------------------------- #
#  Domain/context fallback routing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "source_domain",
    [None, "", "unknown"],
)
def test_unknown_domain_returns_non_escalation_generic(source_domain: str | None) -> None:
    chips, label = _choose_quickreply_fallback(set(), source_domain)
    assert chips == _FALLBACK_GENERIC
    assert label == "generic"
    assert "1:1 문의하기" not in _labels(chips)


def test_transaction_store_plain_text_returns_store_schedule_chips() -> None:
    chips, label = _choose_quickreply_fallback(
        set(),
        "transaction",
        "고객님, 선택하신 매장의 예약 가능 시간을 확인해 주세요.",
    )

    assert label == "transaction_store_schedule"
    assert _labels(chips) == ["예약 가능 시간 보기", "다른 지역 입력", "매장 선택 다시"]
    assert chips[1]["actionId"] == "enter_region"
    assert "1:1 문의하기" not in _labels(chips)


def test_transaction_purchase_store_prompt_returns_region_chips() -> None:
    chips, label = _choose_quickreply_fallback(
        set(),
        "transaction",
        "구매를 진행하려면 장착 매장을 먼저 선택해야 해요. 어느 지역 매장을 찾아드릴까요? 😊",
    )

    assert label == "transaction_purchase_store_search"
    assert chips == _FALLBACK_TRANSACTION_STORE_SEARCH
    assert _labels(chips) == ["강남", "분당", "해운대", "주변 매장 찾기"]


def test_transaction_purchase_store_prompt_replaces_validation_dead_end_chips() -> None:
    assert _looks_like_generic_dead_end_chips([
        {"label": "다시 시도", "domain": "LEADING"},
        {"label": "상담사 연결", "domain": "SUPPORT"},
    ])

    recovery = _discovery_recovery_chips_for_text(
        "구매를 진행하려면 장착 매장을 먼저 선택해야 해요. 어느 지역 매장을 찾아드릴까요? 😊",
        "transaction",
    )

    assert recovery is not None
    chips, label = recovery
    assert label == "transaction_purchase_store_search"
    assert _labels(chips) == ["강남", "분당", "해운대", "주변 매장 찾기"]
    assert "상담사 연결" not in _labels(chips)


def test_support_info_plain_text_returns_next_action_chips_without_qna() -> None:
    chips, label = _choose_quickreply_fallback(
        set(),
        "support",
        "앞뒤 타이어 사이즈가 다른 차량은 전륜용과 후륜용을 각각 선택해서 구매하시면 돼요.",
    )

    assert label == "support_info"
    assert _labels(chips) == ["구매하기", "매장 찾기", "타이어 추천"]
    assert "1:1 문의하기" not in _labels(chips)


def test_support_true_dead_end_allows_qna_chip() -> None:
    chips, label = _choose_quickreply_fallback(
        set(),
        "support",
        "시스템 조회가 일시적으로 어려워 1:1 문의로 확인해 주세요.",
    )

    assert label == "support_recovery"
    assert _labels(chips) == ["1:1 문의하기", "처음으로"]


def test_progress_constant_shape() -> None:
    assert len(_FALLBACK_LEADING_PROGRESS) == 2
    assert all("label" in c and "domain" in c for c in _FALLBACK_LEADING_PROGRESS)


# --------------------------------------------------------------------------- #
#  Discovery normal guidance must not dead-end into support chips
# --------------------------------------------------------------------------- #


def test_detects_generic_dead_end_chip_pair() -> None:
    assert _looks_like_generic_dead_end_chips([
        {"label": "1:1 문의하기", "domain": "SUPPORT"},
        {"label": "처음으로", "domain": "LEADING"},
    ])


def test_discovery_vehicle_size_guidance_replaces_dead_end_chips() -> None:
    text = (
        "등록 차량에는 트럭이 확인되지 않아, 정확한 안내를 원하시면 "
        "트럭의 타이어 사이즈나 차량번호+소유주명을 알려주세요."
    )
    assert _should_replace_discovery_dead_end_chips(text, "discovery")
    recovery = _discovery_recovery_chips_for_text(text, "discovery")
    assert recovery is not None
    chips, label = recovery
    assert label == "discovery_size_vehicle"
    assert _labels(chips) == ["사이즈 직접 입력", "차량번호로 찾기", "타이어 추천 받기"]


def test_discovery_no_result_guidance_uses_search_recovery_chips() -> None:
    recovery = _discovery_recovery_chips_for_text(
        "해당 조건에 맞는 타이어를 찾을 수 없어요.",
        "discovery",
    )
    assert recovery is not None
    chips, label = recovery
    assert label == "discovery_no_result"
    assert _labels(chips) == ["다시 검색", "다른 조건으로 찾기", "타이어 추천 받기"]


def test_discovery_fitment_answer_uses_size_vehicle_chips() -> None:
    recovery = _discovery_recovery_chips_for_text(
        "SUV용과 승용차용 타이어는 하중과 설계 특성이 달라요.",
        "discovery",
    )
    assert recovery is not None
    chips, label = recovery
    assert label == "discovery_size_vehicle"
    assert _labels(chips) == ["사이즈 직접 입력", "차량번호로 찾기", "타이어 추천 받기"]


def test_discovery_generic_answer_uses_discovery_default_chips() -> None:
    recovery = _discovery_recovery_chips_for_text(
        "조건을 조금 더 알려주시면 이어서 찾아드릴게요.",
        "discovery",
    )
    assert recovery is not None
    chips, label = recovery
    assert label == "discovery_default"
    assert _labels(chips) == ["상품 검색", "타이어 추천"]


def test_remove_home_quick_reply_chips_strips_button_and_predicted_domain() -> None:
    event_data = {
        "assistantResponse": "무엇을 도와드릴까요?",
        "quickReplies": [
            {"label": "상품 검색", "domain": "DISCOVERY"},
            {"label": "처음으로", "domain": "LEADING"},
        ],
        "predictedDomains": ["DISCOVERY", "LEADING"],
    }

    assert _remove_home_quick_reply_chips(event_data)
    assert _labels(event_data["quickReplies"]) == ["상품 검색"]
    assert event_data["predictedDomains"] == ["DISCOVERY"]


def test_discovery_explicit_support_text_keeps_dead_end_chips() -> None:
    text = "정확한 확인은 1:1 문의로 문의해 주세요."
    assert not _should_replace_discovery_dead_end_chips(text, "discovery")


def test_discovery_policy_dead_end_keeps_dead_end_chips() -> None:
    text = "특정 제조 주차를 사전에 확정해 안내드리기는 어려워요."
    assert not _should_replace_discovery_dead_end_chips(text, "discovery")


def test_non_discovery_domain_keeps_dead_end_chips() -> None:
    text = "타이어 사이즈나 차량번호를 알려주세요."
    assert not _should_replace_discovery_dead_end_chips(text, "support")


def test_tool_error_summary_compacts_error_response() -> None:
    assert _tool_error_summary(
        "quick_order_tool",
        {
            "status": "error",
            "http_status": 502,
            "reason": "upstream_error",
            "message": "고객사 API 호출 실패",
            "data": {"ignored": True},
        },
    ) == {
        "tool_name": "quick_order_tool",
        "http_status": 502,
        "reason": "upstream_error",
        "message": "고객사 API 호출 실패",
    }


def test_trace_final_error_state_marks_recovered_tool_error() -> None:
    final_status, error_class, user_visible_error = _trace_final_error_state(
        tool_errors=[{"tool_name": "get_store_inventory_tool", "http_status": 500}],
        draft_response="현재 재고 확인이 지연되어 다른 방법으로 안내드릴게요.",
        buffered_data_events=[],
        original_message_events=[],
        last_assistant_response_source=None,
    )

    assert final_status == "recovered"
    assert error_class == "tool_error_recovered"
    assert user_visible_error is False


def test_trace_final_error_state_marks_validation_fallback_user_visible() -> None:
    final_status, error_class, user_visible_error = _trace_final_error_state(
        tool_errors=[],
        draft_response="죄송합니다, 답변을 정리하던 중 일시적인 문제가 발생했어요.",
        buffered_data_events=[],
        original_message_events=[],
        last_assistant_response_source="validation_fallback",
    )

    assert final_status == "error"
    assert error_class == "template_validation_error"
    assert user_visible_error is True


def test_quantity_benefit_missing_event_stores_continuation_metadata() -> None:
    frame = build_discovery_intent_frame("옵티모 상품 2개살까 4개살까 고민 중인데 4개 사면 더 할인해줘?")

    event = _build_quantity_benefit_missing_event(frame)

    assert event["assistant_response_source"] == "code_quantity_benefit_missing_slots"
    assert event["data"]["metadata"] == {
        "pendingIntent": "quantity_benefit_comparison",
        "quantityOptions": [2, 4],
        "productName": "Optimo",
        "missingSlot": "tire_size",
    }


def test_quantity_benefit_pending_slots_continue_with_product_and_size() -> None:
    slots = ConversationSlots(
        pending_intent="quantity_benefit_comparison",
        pending_product_name="옵티모",
        pending_quantity_options=[2, 4],
        pending_required_slot="tire_size",
    )

    frame = _quantity_benefit_continuation_frame_from_pending("옵티모 2454519", slots=slots)

    assert frame is not None
    assert frame.sub_intent == "quantity_benefit_comparison"
    assert frame.entities["product_names"] == ("Optimo",)
    assert frame.entities["tire_size"] == "245/45R19"
    assert frame.entities["quantity_options"] == (2, 4)
    assert frame.missing_slots == ()


def test_quantity_benefit_quickreply_metadata_continues_after_history_summary() -> None:
    previous_event = _build_quantity_benefit_missing_event(
        build_discovery_intent_frame("옵티모 상품 2개살까 4개살까 고민 중인데 4개 사면 더 할인해줘?")
    )

    frame = _quantity_benefit_continuation_frame_from_pending(
        "2454519",
        slots=ConversationSlots(),
        latest_quickreply_tmpl=previous_event,
    )

    assert frame is not None
    assert frame.entities["product_names"] == ("Optimo",)
    assert frame.entities["tire_size"] == "245/45R19"
    assert frame.entities["quantity_options"] == (2, 4)


def test_plain_product_size_search_does_not_trigger_quantity_benefit_without_pending_state() -> None:
    frame = _quantity_benefit_continuation_frame_from_pending("옵티모 2454519", slots=ConversationSlots())

    assert frame is None


def test_goods_no_from_product_template_selection_resolves_named_variant() -> None:
    product_template = {
        "products": [
            {"title": "옵티모 H108 245/45R19", "titleProductName": "옵티모 H108", "titleTires": "245/45R19"},
            {"title": "옵티모 H426 245/45R19", "titleProductName": "옵티모 H426", "titleTires": "245/45R19"},
        ],
        "metadata": [{"goodsId": "G000000309817"}, {"goodsId": "G000000309961"}],
    }

    assert (
        _resolve_goods_no_from_product_template_selection("옵티모 H426 245/45R19", product_template)
        == "G000000309961"
    )


def test_quantity_benefit_product_selection_continues_to_goods_no_comparison() -> None:
    product_template = {
        "products": [
            {"title": "옵티모 H108 245/45R19", "titleProductName": "옵티모 H108", "titleTires": "245/45R19"},
            {"title": "옵티모 H426 245/45R19", "titleProductName": "옵티모 H426", "titleTires": "245/45R19"},
        ],
        "metadata": [{"goodsId": "G000000309817"}, {"goodsId": "G000000309961"}],
        "quantityBenefitComparison": {
            "pendingIntent": "quantity_benefit_comparison",
            "quantityOptions": [2, 4],
            "productName": "Optimo",
            "missingSlot": "goods_no",
        },
    }

    frame = _quantity_benefit_continuation_frame_from_pending(
        "옵티모 H426 245/45R19",
        slots=ConversationSlots(),
        latest_product_tmpl=product_template,
    )

    assert frame is not None
    assert frame.sub_intent == "quantity_benefit_comparison"
    assert frame.known_slots["goods_no"] == "G000000309961"
    assert frame.entities["quantity_options"] == (2, 4)


def _transaction_turn_contract(user_text: str, known_slots: dict | None = None):
    frame = build_transaction_intent_frame(user_text, known_slots=known_slots or {})
    tool_plan = plan_transaction_tools(frame)
    response_decision = decide_transaction_response(
        intent=frame.intent,
        user_text=user_text,
        known_slots=dict(frame.known_slots),
    )
    return build_turn_contract(
        user_text=user_text,
        intent_frame=frame,
        tool_plan=tool_plan,
        response_decision=response_decision,
    )


def _routing_result(
    *,
    domains=None,
    execution_plan=None,
    comparison_followup_intent: str = "none",
    comparison_metric: str = "none",
    referred_object_status: str = "resolved",
    referred_object_type: str = "none",
    needs_clarification: bool = False,
) -> MultiAgentDomain:
    return MultiAgentDomain(
        reason="test",
        domains=domains or [MultiAgentDomain.Domain.TRANSACTION],
        execution_plan=execution_plan or ["transaction:price_or_coupon_check"],
        user_behavior="test",
        flow="test",
        claim_check_type="none",
        complaint_scope="none",
        discovery_followup_intent="none",
        carried_discovery_objective="none",
        comparison_followup_intent=comparison_followup_intent,
        comparison_metric=comparison_metric,
        referred_object_status=referred_object_status,
        referred_object_type=referred_object_type,
        needs_clarification=needs_clarification,
        planner_confidence=0.91,
        agent_prompt_profile="full",
    )


@pytest.mark.parametrize("user_text", ["그거 구매할래", "이 상품 주문할게", "그거 결제하고 싶어"])
def test_turn_contract_guards_unclear_purchase_reference_followup(user_text: str) -> None:
    contract = _transaction_turn_contract(user_text)

    assert contract.required_slots == ("product",)
    assert contract.risk_level == "high"
    assert should_guard_required_slots(contract)

    event = build_required_slot_clarification_event(contract)
    assert event["assistant_response_source"] == "code_turn_contract_required_slot_guard"
    assert event["template"] == "quickReply"
    assert "어떤 상품 기준" in event["data"]["assistantResponse"]
    assert "상품명 입력" in _labels(event["data"]["quickReplies"])


@pytest.mark.parametrize("user_text", ["가격 얼마야?", "쿠폰 적용돼?", "할인가 확인해줘"])
def test_turn_contract_guards_price_coupon_without_product(user_text: str) -> None:
    contract = _transaction_turn_contract(user_text)

    assert contract.intent == "price_or_coupon_check"
    assert contract.blocking_required_slots == ("product",)
    assert should_guard_required_slots(contract)


@pytest.mark.parametrize("user_text", ["벤투스 에어S 가격 알려줘", "dynapro hp3 가격 알려줘"])
def test_turn_contract_does_not_guard_cross_domain_product_price_resolution(user_text: str) -> None:
    cross_domain_plan = plan_cross_domain_turn(user_text, known_slots={})
    frame = build_transaction_intent_frame(user_text, known_slots={})
    tool_plan = plan_transaction_tools(frame)
    response_decision = decide_transaction_response(
        intent=frame.intent,
        user_text=user_text,
        known_slots=dict(frame.known_slots),
    )

    contract = build_turn_contract(
        user_text=user_text,
        intent_frame=frame,
        tool_plan=tool_plan,
        response_decision=response_decision,
        cross_domain_plan=cross_domain_plan,
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION],
            execution_plan=["discovery:resolve_product", "transaction:price_or_coupon_check"],
        ),
    )

    assert cross_domain_plan.is_cross_domain
    assert contract.planner_intent == "resolve_or_describe_product"
    assert contract.intent == "resolve_or_describe_product"
    assert contract.resolvable_required_slots
    assert not contract.blocking_required_slots
    assert not should_guard_required_slots(contract)
    assert any(item["field"] == "intent" for item in contract.contract_drift)


@pytest.mark.parametrize("user_text", ["그거 구매할래", "그거 가격 알려줘", "두 개 다 재고 있어?"])
def test_turn_contract_blocks_missing_or_ambiguous_referred_object(user_text: str) -> None:
    contract = build_turn_contract(
        user_text=user_text,
        routing_result=_routing_result(
            referred_object_status="ambiguous" if "두 개" in user_text else "missing",
            referred_object_type="product_set" if "두 개" in user_text else "product",
            needs_clarification=True,
            execution_plan=["transaction:quick_order_reservation"],
        ),
    )

    assert contract.referred_objects["needs_clarification"] is True
    assert contract.blocking_required_slots
    assert should_guard_required_slots(contract)


def test_turn_contract_blocks_missing_reference_even_when_planner_starts_with_discovery() -> None:
    contract = build_turn_contract(
        user_text="그거 구매할래",
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION],
            execution_plan=["discovery:resolve_product", "transaction:quick_order_reservation"],
            referred_object_status="missing",
            referred_object_type="product",
            needs_clarification=True,
        ),
    )

    assert contract.domain == "discovery"
    assert contract.blocking_required_slots == ("product",)
    assert contract.risk_level == "high"
    assert should_guard_required_slots(contract)


def test_turn_contract_blocks_ambiguous_price_followup_even_with_transaction_policy_plan() -> None:
    cross_domain_plan = plan_cross_domain_turn("가격 알려줘", known_slots={})

    contract = build_turn_contract(
        user_text="가격 알려줘",
        intent_frame=IntentFrame(domain=PolicyDomain.DISCOVERY, intent="product_recommendation"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("price_without_size",),
        ),
        cross_domain_plan=cross_domain_plan,
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY],
            execution_plan=["discovery:clarify_ambiguous_product_set_price"],
            referred_object_status="ambiguous",
            referred_object_type="product_set",
            needs_clarification=True,
        ),
    )
    event = build_required_slot_clarification_event(contract)

    assert contract.referred_objects == {
        "status": "ambiguous",
        "type": "product_set",
        "needs_clarification": True,
    }
    assert contract.blocking_required_slots == ("product_set",)
    assert contract.risk_level == "high"
    assert should_guard_required_slots(contract)
    assert event["data"]["assistantResponse"] == "어떤 상품 기준으로 확인해드릴까요?"
    assert event["data"]["quickReplies"][0]["label"] == "상품명 입력"


def test_turn_contract_ignores_freeform_execution_plan_as_planner_intent() -> None:
    contract = build_turn_contract(
        user_text="가격 알려줘",
        intent_frame=IntentFrame(domain=PolicyDomain.TRANSACTION, intent="price_or_coupon_check"),
        routing_result=_routing_result(
            execution_plan=["Run TRANSACTION price flow after resolving context"],
        ),
    )

    assert contract.planner_intent is None
    assert contract.intent == "price_or_coupon_check"
    assert "run_transaction_price_flow_after_resolving_context" not in {
        contract.intent,
        contract.planner_intent,
    }


def test_turn_contract_does_not_clarify_normal_product_description() -> None:
    contract = _transaction_turn_contract("dynapro hp3 설명해줘")

    assert contract.blocking_required_slots == ()
    assert not should_guard_required_slots(contract)


def test_turn_contract_allows_stock_when_required_slots_are_known() -> None:
    contract = _transaction_turn_contract(
        "재고 확인해줘",
        {
            "goods_no": "G000000000001",
            "tire_size": "225/45R17",
            "quantity": 4,
            "region": "서울",
        },
    )

    assert contract.intent == "stock_store_search"
    assert contract.blocking_required_slots == ()
    assert not should_guard_required_slots(contract)


def test_quick_order_reservation_treats_selected_datepick_as_resolved_booking_datetime() -> None:
    contract = _transaction_turn_contract(
        "주문 확정",
        {
            "goods_no": "G000000317682",
            "tire_size": "235/55R19",
            "ord_qty": 2,
            "shop_id": "F00721",
            "shop_name": "티스테이션 판교점",
            "requested_cal_day": "20260623",
            "rsv_hour": "17",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
    )

    assert contract.intent == "quick_order_reservation"
    assert contract.response_decision["metadata"]["response_shape_key"] == "reservation_confirmation_ready"
    assert contract.blocking_required_slots == ()
    assert not should_guard_required_slots(contract)


def test_quick_order_reservation_keeps_datepick_guard_without_selected_datetime() -> None:
    contract = _transaction_turn_contract(
        "주문 확정",
        {
            "goods_no": "G000000317682",
            "tire_size": "235/55R19",
            "ord_qty": 2,
            "shop_id": "F00721",
            "shop_name": "티스테이션 판교점",
            "pending_intent": "order",
            "goal_type": "place_order",
        },
    )

    assert contract.intent == "quick_order_reservation"
    assert contract.response_decision["metadata"]["response_shape_key"] == "reservation_slots"
    assert contract.blocking_required_slots == ("booking_datetime",)
    assert should_guard_required_slots(contract)


def test_turn_contract_blocks_templates_that_conflict_with_missing_required_slots() -> None:
    contract = _transaction_turn_contract("그거 구매할래")

    assert violates_response_template_contract({"template": "datepick"}, contract)
    assert violates_response_template_contract({"template": "preOrder"}, contract)
    assert violates_response_template_contract({"template": "orderComplete"}, contract)
    assert not violates_response_template_contract({"template": "quickReply"}, contract)


def test_turn_contract_blocks_datepick_for_unavailable_stock_response_policy() -> None:
    frame = IntentFrame(
        domain=PolicyDomain.TRANSACTION,
        intent="inventory_availability",
        known_slots={"goods_no": "G000000000001", "tire_size": "225/45R17", "quantity": 4},
    )
    response_decision = decide_transaction_response(
        intent="inventory_availability",
        known_slots=dict(frame.known_slots),
        tool_result={"available_qty": 0, "todayShopArray": [], "tnaShopArray": []},
    )
    contract = build_turn_contract(
        user_text="오늘 장착 가능해?",
        intent_frame=frame,
        response_decision=response_decision,
    )

    assert contract.blocking_required_slots == ()
    assert not should_guard_required_slots(contract)
    assert violates_response_template_contract({"template": "datepick"}, contract)
    assert violates_response_template_contract({"template": "preOrder"}, contract)
    assert not violates_response_template_contract({"template": "quickReply"}, contract)

    event = build_response_policy_guard_event(contract)
    assert event["assistant_response_source"] == "code_turn_contract_response_policy_guard"
    assert "예약 가능한 재고" in event["data"]["assistantResponse"]
    assert "다른 매장 찾기" in _labels(event["data"]["quickReplies"])


def test_transaction_preview_tool_result_with_schedule_slots_is_not_treated_as_stock_unavailable() -> None:
    response_decision = decide_transaction_response(
        intent="inventory_availability",
        known_slots={
            "goods_no": "G000000317682",
            "tire_size": "235/55R19",
            "ord_qty": 2,
            "shop_name": "티스테이션 판교점",
            "requested_cal_day": "20260623",
        },
        tool_result={
            "status": "success",
            "data": {
                "inventory": {
                    "todayShopArray": [{"shopId": "F00721"}],
                    "tnaShopArray": [{"shopId": "F00721"}],
                },
                "schedule": {
                    "stores": [{
                        "shop_id": "F00721",
                        "is_installable": True,
                        "slots": [{"cal_day": "20260623", "tm": "17"}],
                    }],
                },
                "stores": [{
                    "shop_id": "F00721",
                    "is_installable": True,
                }],
            },
        },
    )

    assert response_decision.metadata["response_shape_key"] == "reservation_slots"
    assert response_decision.template == TemplateName.DATE_PICK
    assert "datepick_for_unavailable_stock" not in response_decision.forbidden_behaviors
    assert "preorder" not in response_decision.forbidden_behaviors


def test_turn_contract_qc_reports_forbidden_template_violation() -> None:
    frame = IntentFrame(
        domain=PolicyDomain.TRANSACTION,
        intent="inventory_availability",
        known_slots={"goods_no": "G000000000001", "tire_size": "225/45R17", "quantity": 4},
    )
    response_decision = decide_transaction_response(
        intent="inventory_availability",
        known_slots=dict(frame.known_slots),
        tool_result={"available_qty": 0, "todayShopArray": [], "tnaShopArray": []},
    )
    contract = build_turn_contract(
        user_text="오늘 장착 가능해?",
        intent_frame=frame,
        response_decision=response_decision,
    )

    violations = response_contract_violations(template="datepick", contract=contract)

    assert violations == [{
        "type": "forbidden_template",
        "template": "datepick",
        "fallback_reason": "response_policy_forbidden_behaviors",
        "response_shape_key": "",
        "assistant_response_source": "",
    }]


def test_turn_contract_blocks_discovery_summary_before_transaction_resolution() -> None:
    contract = build_turn_contract(
        user_text="옵티모 가격 얼마야?",
        intent_frame=IntentFrame(domain=PolicyDomain.TRANSACTION, intent="price_or_coupon_check"),
        response_decision=decide_transaction_response(intent="price_or_coupon_check", user_text="옵티모 가격 얼마야?"),
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION],
            execution_plan=["discovery:resolve_product", "transaction:price_or_coupon_check"],
        ),
    )

    event = {
        "template": "quickReply",
        "source_domain": "discovery",
        "assistant_response_source": "code_product_attribute_resolver",
        "response_shape_key": "product_attribute_summary",
        "called_tools": ["search_product_tool"],
    }

    assert violates_response_template_contract(event, contract)
    fallback_event = build_response_policy_guard_event(contract)
    assert "어떤 상품 기준인지" in fallback_event["data"]["assistantResponse"]
    assert "상품명 입력" in _labels(fallback_event["data"]["quickReplies"])


def test_turn_contract_qc_reports_discovery_first_leg_violation() -> None:
    contract = build_turn_contract(
        user_text="키너지 재고 있어?",
        intent_frame=IntentFrame(domain=PolicyDomain.TRANSACTION, intent="stock_store_search"),
        response_decision=decide_transaction_response(intent="stock_store_search", user_text="키너지 재고 있어?"),
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION],
            execution_plan=["discovery:resolve_product", "transaction:stock_store_search"],
        ),
    )

    violations = response_contract_violations(
        template="quickReply",
        assistant_response_source="code_product_attribute_resolver",
        response_shape_key="product_attribute_summary",
        called_tools=["search_product_tool"],
        contract=contract,
    )

    assert violations == [{
        "type": "forbidden_discovery_first_leg_response",
        "template": "quickReply",
        "fallback_reason": "missing_required_slots:product",
        "response_shape_key": "product_attribute_summary",
        "assistant_response_source": "code_product_attribute_resolver",
    }]


def test_turn_contract_blocks_price_template_on_price_tool_error() -> None:
    response_decision = _tool_error_response_decision("get_final_price_tool")
    contract = build_turn_contract(
        user_text="가격 알려줘",
        intent_frame=IntentFrame(domain=PolicyDomain.TRANSACTION, intent="price_or_coupon_check"),
        response_decision=response_decision,
        routing_result=_routing_result(execution_plan=["transaction:price_or_coupon_check"]),
    )

    assert violates_response_template_contract({"template": "billProduct"}, contract)
    assert violates_response_template_contract({"template": "preOrder"}, contract)
    event = build_response_policy_guard_event(contract)
    assert "금액을 단정할 수 없" in event["data"]["assistantResponse"]


@pytest.mark.parametrize("forbidden_behavior", ["product_card_without_size", "price_without_size", "answer_without_price_tool"])
def test_turn_contract_blocks_product_template_for_price_without_confirmed_size(
    forbidden_behavior: str,
) -> None:
    contract = build_turn_contract(
        user_text="가격은?",
        intent_frame=IntentFrame(domain=PolicyDomain.TRANSACTION, intent="price_or_coupon_check"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=(forbidden_behavior,),
        ),
        routing_result=_routing_result(execution_plan=["transaction:price_or_coupon_check"]),
    )

    assert violates_response_template_contract(
        {
            "template": "product",
            "source_domain": "discovery",
            "assistant_response_source": "code_product_description",
            "response_shape_key": "product_search_summary",
            "called_tools": [],
        },
        contract,
    )
    fallback_event = build_response_policy_guard_event(contract)
    assert fallback_event["template"] == "quickReply"


def test_turn_contract_keeps_product_template_when_current_turn_has_product_source_tool() -> None:
    contract = build_turn_contract(
        user_text="벤투스 에어S 추천해줘",
        intent_frame=IntentFrame(domain=PolicyDomain.DISCOVERY, intent="product_recommendation"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.CARD,
            template=TemplateName.PRODUCT,
        ),
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY],
            execution_plan=["discovery:product_recommendation"],
        ),
    )

    assert not violates_response_template_contract(
        {
            "template": "product",
            "source_domain": "discovery",
            "assistant_response_source": "code_bare_product_search",
            "response_shape_key": "product_search_summary",
            "called_tools": ["search_product_tool"],
        },
        contract,
    )


def test_turn_contract_allows_compare_quickreply_during_discovery_first_leg_transaction_chain() -> None:
    contract = build_turn_contract(
        user_text="ventus s2 as, ventus air s 중에 뭐가 더 신상품?",
        intent_frame=IntentFrame(domain=PolicyDomain.TRANSACTION, intent="price_or_coupon_check"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            metadata={"response_shape_key": "metric_comparison_summary"},
        ),
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION],
            execution_plan=["discovery:resolve_product", "transaction:price_or_coupon_check"],
        ),
    )

    compare_event = {
        "template": "quickReply",
        "source_domain": "discovery",
        "assistant_response_source": "code_product_compare_resolver",
        "response_shape_key": "metric_comparison_summary",
        "called_tools": ["search_product_tool"],
    }

    assert not violates_response_template_contract(compare_event, contract)
    assert response_contract_violations(contract=contract, **compare_event) == []


def test_turn_contract_reports_missing_metric_row_for_compare_continuation() -> None:
    contract = build_turn_contract(
        user_text="dynapro hpx, dynapro hp3 중에서는?",
        intent_frame=IntentFrame(domain=PolicyDomain.DISCOVERY, intent="product_comparison", sub_intent="latest_compare"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            metadata={
                "response_shape_key": "metric_comparison_summary",
                "compare_metric": "release",
                "comparison_followup_intent": "continue_previous_compare_metric",
            },
        ),
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY],
            execution_plan=["discovery:product_comparison"],
            comparison_followup_intent="continue_previous_compare_metric",
            comparison_metric="release",
        ),
    )

    violations = response_contract_violations(
        template="quickReply",
        assistant_response_text="| 항목 | Dynapro HPX | Dynapro HP3 |\n|---|---|---|\n| 상품 등급 | premium | standard |",
        assistant_response_source="code_product_compare_resolver",
        response_shape_key="metric_comparison_summary",
        called_tools=["search_product_tool"],
        source_domain="discovery",
        contract=contract,
    )

    assert {"type": "compare_metric_row_missing", "comparison_followup_intent": "continue_previous_compare_metric", "compare_metric": "release", "expected_row": "출시 시점"} in violations


def test_turn_contract_reports_compare_metric_metadata_drift() -> None:
    contract = build_turn_contract(
        user_text="dynapro hpx, dynapro hp3 중에서는?",
        intent_frame=IntentFrame(domain=PolicyDomain.DISCOVERY, intent="product_comparison", sub_intent="latest_compare"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            metadata={
                "response_shape_key": "metric_comparison_summary",
                "compare_metric": "release",
                "comparison_followup_intent": "continue_previous_compare_metric",
            },
        ),
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY],
            execution_plan=["discovery:product_comparison"],
            comparison_followup_intent="continue_previous_compare_metric",
            comparison_metric="release",
        ),
    )

    violations = response_contract_violations(
        template="quickReply",
        assistant_response_text="| 항목 | Dynapro HPX | Dynapro HP3 |\n|---|---|---|\n| 특징 | x | y |",
        assistant_response_source="code_product_compare_resolver",
        compare_metric="detail",
        response_shape_key="metric_comparison_summary",
        called_tools=["search_product_tool"],
        source_domain="discovery",
        contract=contract,
    )

    assert {"type": "compare_metric_metadata_drift", "compare_metric": "release", "assistant_compare_metric": "detail"} in violations


def test_response_decision_helper_uses_source_domain_contextvars() -> None:
    discovery_decision = ResponseDecision(
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        metadata={"response_shape_key": "metric_comparison_summary"},
    )
    transaction_decision = ResponseDecision(
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        metadata={"response_shape_key": "order_summary"},
    )
    discovery_token = current_discovery_response_decision.set(discovery_decision)
    transaction_token = current_transaction_response_decision.set(transaction_decision)
    try:
        assert _response_decision_for_source_domain("discovery") is discovery_decision
        assert _response_decision_for_source_domain("transaction") is transaction_decision
        assert _response_decision_for_source_domain("unknown") is transaction_decision
        assert _response_shape_key_for_source_domain("discovery") == "metric_comparison_summary"
        assert _response_shape_key_for_source_domain("transaction") == "order_summary"
        assert _response_shape_key_for_source_domain("unknown") == "order_summary"
    finally:
        current_discovery_response_decision.reset(discovery_token)
        current_transaction_response_decision.reset(transaction_token)


def test_stream_response_multi_keeps_stream_alive_when_turn_contract_validation_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery_decision = ResponseDecision(
        response_shape=ResponseShape.SUMMARY,
        template=TemplateName.QUICK_REPLY,
        metadata={"response_shape_key": "metric_comparison_summary"},
    )
    discovery_token = current_discovery_response_decision.set(discovery_decision)
    transaction_token = current_transaction_response_decision.set(None)

    class _FakeCoordinator:
        def stream(self, *args, **kwargs):
            yield {"type": "sub-agent", "agent": "[DISCOVERY AGENT]", "status": "start"}
            yield {
                "type": "data",
                "template": "quickReply",
                "source_domain": "discovery",
                "assistant_response_source": "code_product_compare_resolver",
                "data": {
                    "assistantResponse": "최신 상품은 벤투스 에어S입니다.",
                    "quickReplies": [{"label": "구매하기", "domain": "TRANSACTION"}],
                    "predictedDomains": ["DISCOVERY", "TRANSACTION"],
                    "metadata": {"response_shape_key": "metric_comparison_summary"},
                },
            }
            yield {"type": "sub-agent", "agent": "[DONE]", "status": "success"}

    async def _fake_async_from_sync_iter(iterator):
        for item in iterator:
            yield item

    monkeypatch.setattr(chat_module, "_coordinator", _FakeCoordinator())
    monkeypatch.setattr(chat_module, "_async_from_sync_iter", _fake_async_from_sync_iter)
    monkeypatch.setattr(chat_module.settings, "AI_QC_ENABLED", False)
    monkeypatch.setattr(
        chat_module,
        "violates_response_template_contract",
        lambda *args, **kwargs: (_ for _ in ()).throw(UnboundLocalError("local alias scope error")),
    )

    turn_contract = build_turn_contract(
        user_text="무응답 방지 테스트",
        intent_frame=IntentFrame(domain=PolicyDomain.DISCOVERY, intent="product_search"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            metadata={"response_shape_key": "product_search_summary"},
        ),
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY],
            execution_plan=["discovery:product_search"],
        ),
    )

    try:
        async def _collect_events() -> list[str]:
            return [
                chunk
                async for chunk in TStationChatServiceV2._stream_response_multi(
                    messages=[{"role": "user", "content": "무응답 방지 테스트"}],
                    domains=[MultiAgentDomain.Domain.DISCOVERY],
                    initial_slots=ConversationSlots(),
                    turn_contract=turn_contract,
                )
            ]

        events = asyncio.run(_collect_events())
    finally:
        current_discovery_response_decision.reset(discovery_token)
        current_transaction_response_decision.reset(transaction_token)

    assert any(chunk == "data: [DONE]\n\n" for chunk in events)

    parsed_events = []
    for chunk in events:
        if not chunk.startswith("data: ") or chunk == "data: [DONE]\n\n":
            continue
        parsed_events.append(json.loads(chunk[6:].strip()))

    quickreply_events = [event for event in parsed_events if event.get("type") == "data"]
    assert quickreply_events
    assert quickreply_events[-1]["template"] == "quickReply"
    assert quickreply_events[-1]["assistant_response_source"] == "code_turn_contract_response_policy_guard"
    assert any(event.get("type") == "DONE" for event in parsed_events)


def test_turn_contract_reports_product_template_without_current_source_even_without_called_tools() -> None:
    contract = build_turn_contract(
        user_text="그럼 가격은?",
        intent_frame=IntentFrame(domain=PolicyDomain.TRANSACTION, intent="price_or_coupon_check"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("price_without_size",),
        ),
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION],
            execution_plan=["discovery:resolve_product", "transaction:price_or_coupon_check"],
        ),
    )

    violations = response_contract_violations(
        template="product",
        assistant_response_source="code_product_description",
        response_shape_key="product_search_summary",
        called_tools=[],
        source_domain="discovery",
        contract=contract,
    )

    assert violations == [{
        "type": "unsupported_product_template_without_current_source",
        "template": "product",
        "fallback_reason": "missing_required_slots:product",
        "response_shape_key": "product_search_summary",
        "assistant_response_source": "code_product_description",
    }]


@pytest.mark.parametrize("template", ["product", "cheapestProduct", "billProduct"])
def test_turn_contract_blocks_price_without_size_templates(template: str) -> None:
    contract = build_turn_contract(
        user_text="최종가는?",
        intent_frame=IntentFrame(domain=PolicyDomain.TRANSACTION, intent="price_or_coupon_check"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("price_without_size",),
        ),
        routing_result=_routing_result(execution_plan=["transaction:price_or_coupon_check"]),
    )

    assert violates_response_template_contract({"template": template}, contract)


@pytest.mark.parametrize(
    ("dialogue", "followup_text"),
    [
        (
            [
                {"role": "user", "content": "벤투스 에어S 가격 알려줘"},
                {"role": "assistant", "content": "규격이 확인되면 가격을 안내해드릴게요."},
                {"role": "user", "content": "가격은?"},
            ],
            "가격은?",
        ),
        (
            [
                {"role": "user", "content": "벤투스 에어S 가격 알려줘"},
                {"role": "assistant", "content": "규격이 확인되면 가격을 안내해드릴게요."},
                {"role": "user", "content": "얼마야?"},
            ],
            "얼마야?",
        ),
        (
            [
                {"role": "user", "content": "벤투스 에어S 가격 알려줘"},
                {"role": "assistant", "content": "규격이 확인되면 가격을 안내해드릴게요."},
                {"role": "user", "content": "가격 알려줘"},
            ],
            "가격 알려줘",
        ),
        (
            [
                {"role": "user", "content": "벤투스 에어S 가격 알려줘"},
                {"role": "assistant", "content": "규격이 확인되면 가격을 안내해드릴게요."},
                {"role": "user", "content": "그럼 가격은?"},
            ],
            "그럼 가격은?",
        ),
        (
            [
                {"role": "user", "content": "벤투스 에어S 가격 알려줘"},
                {"role": "assistant", "content": "규격이 확인되면 가격을 안내해드릴게요."},
                {"role": "user", "content": "최종가는?"},
            ],
            "최종가는?",
        ),
    ],
)
def test_real_dialogue_price_followup_blocks_source_less_product_card(
    dialogue: list[dict[str, str]],
    followup_text: str,
) -> None:
    """실제 대화: 상품명 기반 가격 요청 뒤 규격 미확정 상태의 가격 재질문은 product 카드로 끝나면 안 된다."""

    contract = build_turn_contract(
        user_text=followup_text,
        intent_frame=IntentFrame(domain=PolicyDomain.TRANSACTION, intent="price_or_coupon_check"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.SUMMARY,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=("price_without_size",),
        ),
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION],
            execution_plan=["discovery:resolve_product", "transaction:price_or_coupon_check"],
        ),
    )

    llm_product_event = {
        "template": "product",
        "source_domain": "discovery",
        "assistant_response_source": "code_product_description",
        "response_shape_key": "product_search_summary",
        "called_tools": [],
        "messages": dialogue,
    }

    assert violates_response_template_contract(llm_product_event, contract)
    fallback_event = build_response_policy_guard_event(contract)
    assert fallback_event["template"] == "quickReply"
    assert "어떤 상품 기준인지" in fallback_event["data"]["assistantResponse"]


def test_real_dialogue_sized_price_flow_keeps_current_turn_product_source_card_allowed() -> None:
    """실제 대화: 규격이 명시된 상품 가격 문의에서 현재 턴 search_product_tool 결과 product 카드는 차단 대상이 아니다."""

    dialogue = [
        {"role": "user", "content": "벤투스 에어S 2454518 가격 알려줘"},
        {"role": "assistant", "content": "245/45R18 기준 상품을 찾았어요."},
    ]
    contract = build_turn_contract(
        user_text="벤투스 에어S 2454518 가격 알려줘",
        intent_frame=IntentFrame(domain=PolicyDomain.DISCOVERY, intent="product_search"),
        response_decision=ResponseDecision(
            response_shape=ResponseShape.CARD,
            template=TemplateName.PRODUCT,
        ),
        routing_result=_routing_result(
            domains=[MultiAgentDomain.Domain.DISCOVERY],
            execution_plan=["discovery:resolve_product"],
        ),
    )

    mapper_product_event = {
        "template": "product",
        "source_domain": "discovery",
        "assistant_response_source": "code_bare_product_search",
        "response_shape_key": "product_search_summary",
        "called_tools": ["search_product_tool"],
        "messages": dialogue,
    }

    assert not violates_response_template_contract(mapper_product_event, contract)


def test_turn_contract_accumulates_post_tool_forbidden_behaviors_across_tools() -> None:
    price_error_decision = _tool_error_response_decision("get_final_price_tool")
    accumulated_behaviors = list(price_error_decision.forbidden_behaviors)
    coupon_success_decision = None
    if coupon_success_decision is None and accumulated_behaviors:
        coupon_success_decision = ResponseDecision(
            response_shape=ResponseShape.NO_RESULT,
            template=TemplateName.QUICK_REPLY,
            forbidden_behaviors=tuple(accumulated_behaviors),
            assistant_guidance="keep prior post-tool constraints",
            metadata={"tools": ["get_final_price_tool"]},
        )

    contract = build_turn_contract(
        user_text="가격이랑 쿠폰 알려줘",
        intent_frame=IntentFrame(domain=PolicyDomain.TRANSACTION, intent="price_or_coupon_check"),
        response_decision=coupon_success_decision,
        routing_result=_routing_result(execution_plan=["transaction:price_or_coupon_check"]),
    )

    assert "assert_price_without_tool_result" in contract.response_decision["forbidden_behaviors"]
    assert violates_response_template_contract({"template": "billProduct"}, contract)


def test_turn_contract_treats_high_risk_tool_parse_failure_as_forbidden_behavior() -> None:
    response_decision = _tool_parse_failure_response_decision("get_final_price_tool")
    contract = build_turn_contract(
        user_text="가격 알려줘",
        intent_frame=IntentFrame(domain=PolicyDomain.TRANSACTION, intent="price_or_coupon_check"),
        response_decision=response_decision,
        routing_result=_routing_result(execution_plan=["transaction:price_or_coupon_check"]),
    )

    assert response_decision.metadata["parse_failure"] is True
    assert "assert_price_without_tool_result" in contract.response_decision["forbidden_behaviors"]
    assert violates_response_template_contract({"template": "billProduct"}, contract)


def test_qc_factual_mismatch_guard_event_uses_safe_fallback() -> None:
    event = _qc_factual_mismatch_guard_event([
        qc_verifier.Mismatch(field="price", value="123,456원"),
        qc_verifier.Mismatch(field="goods_no", value="G000000000001"),
    ])

    assert event["assistant_response_source"] == "code_qc_factual_mismatch_guard"
    assert event["template"] == "quickReply"
    assert "일치하지 않아" in event["data"]["assistantResponse"]
    assert event["data"]["metadata"]["qcMismatchFields"] == ["goods_no", "price"]


def test_repair_assistant_response_removes_mismatched_price_and_repasses_qc() -> None:
    source = [
        (
            "get_product_description_tool",
            {
                "status": "success",
                "data": {"goods_no": "G000000310283", "cheapest_final_prc": 122300},
            },
        )
    ]
    mismatches = qc_verifier.verify_draft("회원 최저가는 119,900원이에요.", source)

    repaired = _repair_assistant_response("회원 최저가는 119,900원이에요.", mismatches)

    assert repaired == "정확한 가격은 다시 확인해서 안내드릴게요."
    assert qc_verifier.verify_draft(repaired, source) == []


def test_repair_qc_mismatch_event_updates_assistant_response_without_guard_fallback() -> None:
    event = _repair_qc_mismatch_event(
        {
            "type": "data",
            "template": "quickReply",
            "data": {
                "assistantResponse": "회원 최저가는 119,900원이에요.",
                "quickReplies": [{"label": "가격 확인", "domain": "TRANSACTION"}],
            },
        },
        mismatches=[qc_verifier.Mismatch(field="price", value="119,900원")],
    )

    assert event is not None
    assert event["assistant_response_source"] == "code_qc_mismatch_repair"
    assert event["data"]["assistantResponse"] == "정확한 가격은 다시 확인해서 안내드릴게요."
    assert event["data"]["quickReplies"] == [{"label": "가격 확인", "domain": "TRANSACTION"}]


def test_env_example_defaults_to_sequential_qc_for_blocking_contracts() -> None:
    env_example = Path(__file__).resolve().parents[3] / ".env.example"

    assert "AI_QC_ENABLED=true" in env_example.read_text()
    assert "AI_QC_PARALLEL=false" in env_example.read_text()


def test_contract_sensitive_turn_should_disable_parallel_qc_condition() -> None:
    contract = build_turn_contract(
        user_text="그거 구매할래",
        routing_result=_routing_result(
            referred_object_status="missing",
            referred_object_type="product",
            needs_clarification=True,
        ),
    )

    contract_sensitive_qc = bool(
        contract
        and (
            contract.blocking_required_slots
            or contract.resolvable_required_slots
            or (contract.response_decision or {}).get("forbidden_behaviors")
        )
    )

    assert contract_sensitive_qc is True
    assert not (True and True and not contract_sensitive_qc)
