"""Per-turn execution contract for policy shadow logging and narrow guards."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from services.tstation.common.cta_urls import CTAUrls
from services.tstation.policies.cross_domain_policy import CrossDomainPlan
from services.tstation.policies.discovery_intent_policy import (
    extract_best_seller_vehicle_query,
    has_registered_vehicle_ownership_signal,
    is_best_seller_request,
)
from services.tstation.policies.flow_controller import build_purchase_flow_fallback_event
from services.tstation.policies.intent_frame import IntentFrame
from services.tstation.policies.price_basis_policy import has_price_basis
from services.tstation.policies.preorder_event_builder import build_preorder_event
from services.tstation.policies.resolved_context import build_resolved_turn_context
from services.tstation.policies.response_decision import ResponseDecision, ToolPlan
from services.tstation.policies.router_evidence import merge_router_evidence_known_slots
from services.tstation.policies.support_response_policy import (
    _is_tire_manufacture_date_question,
    build_general_cancel_fee_policy_event,
)
from services.tstation.policies.transaction_intent_policy import build_transaction_intent_frame


_HIGH_RISK_INTENTS = frozenset({
    "price_or_coupon_check",
    "price_coupon_summary",
    "product_coupon_eligibility",
    "product_coupon_discount_amount",
    "coupon_discount_amount",
    "coupon_applicable_products",
    "coupon_pattern_applicability",
    "stock_store_search",
    "store_schedule",
    "open_store_search",
    "quick_order_reservation",
    "quick_order_execute",
    "inventory_availability",
    "recent_product_set_size_availability",
})
_HIGH_RISK_DOMAINS = frozenset({"transaction"})
_HARD_REQUIRED_SLOT_GUARD_INTENTS = frozenset({
    "quick_order_execute",
})
_REQUIRED_SLOT_BLOCK_TEMPLATES = frozenset({
    "datepick",
    "preOrder",
    "orderComplete",
    "billProduct",
    "billService",
})
_STORE_ONLY_FLOW_BLOCK_TEMPLATES = frozenset({"datepick", "preOrder", "orderComplete"})
_FORBIDDEN_BEHAVIOR_TEMPLATE_BLOCKS = {
    "datepick_for_unavailable_stock": frozenset({"datepick", "preOrder"}),
    "datepick_for_pure_inventory_flow": frozenset({"datepick", "preOrder"}),
    "preorder_for_pure_inventory_flow": frozenset({"preOrder", "orderComplete"}),
    "preorder": frozenset({"preOrder", "orderComplete"}),
    "preorder_with_null_required_fields": frozenset({"preOrder", "orderComplete"}),
    "order_summary_with_null_required_fields": frozenset({"preOrder", "orderComplete"}),
    "product_card_without_size": frozenset({"product"}),
    "price_without_size": frozenset({"product", "cheapestProduct", "billProduct"}),
    "answer_without_price_tool": frozenset({"product", "cheapestProduct", "billProduct"}),
    "assert_price_without_tool_result": frozenset({"preOrder", "billProduct", "cheapestProduct"}),
    "assert_coupon_without_tool_result": frozenset({"voucher", "preOrder", "billProduct"}),
    "order_complete_on_tool_error": frozenset({"orderComplete"}),
    "datepick_on_tool_error": frozenset({"datepick", "preOrder"}),
    "assert_success_without_tool_result": frozenset({"datepick", "preOrder", "orderComplete", "billProduct"}),
    "datepick_for_store_visit_advisory": frozenset({"datepick", "preOrder"}),
    "force_store_schedule_for_visit_advisory": frozenset({"datepick", "preOrder"}),
    "datepick_for_store_search_flow": _STORE_ONLY_FLOW_BLOCK_TEMPLATES,
    "schedule_tool_for_store_service_search": _STORE_ONLY_FLOW_BLOCK_TEMPLATES,
    "datepick_for_unknown_store_service": _STORE_ONLY_FLOW_BLOCK_TEMPLATES,
    "schedule_tool_for_unknown_store_service": _STORE_ONLY_FLOW_BLOCK_TEMPLATES,
    "schedule_tool_for_vehicle_experience_store_search": _STORE_ONLY_FLOW_BLOCK_TEMPLATES,
    "quick_order_for_vehicle_experience_store_search": frozenset({"preOrder", "orderComplete"}),
    "preorder_for_vehicle_experience_store_search": frozenset({"preOrder", "orderComplete"}),
}
_DISCOVERY_FIRST_LEG_BLOCK_RESPONSE_SHAPES = frozenset({
    "product_attribute_summary",
    "product_search_summary",
    "technology_explanation_then_unsized_recommendation_summary",
    "safe_service_explanation_then_unsized_recommendation_summary",
    "unsized_recommendation_summary",
    "neutral_product_description",
    "discovery_summary",
})
_DISCOVERY_FIRST_LEG_BLOCK_SOURCES = frozenset({
    "code_product_attribute_resolver",
    "code_product_description",
    "discovery_policy",
})
_DISCOVERY_PRODUCT_SOURCE_TOOLS = frozenset({
    "search_product_tool",
    "get_products_recommendations_tool",
    "get_best_selling_products_tool",
    "get_newest_products_tool",
})
_PENDING_CHECK_FOLLOWUP_PLANNER_INTENTS = frozenset({
    "coupon_applicability_check",
})


def _latest_router_evidence_intent(known_slots: Mapping[str, Any]) -> str:
    availability_context = (
        known_slots.get("availability_context") if isinstance(known_slots.get("availability_context"), Mapping) else {}
    )
    latest_router_evidence = (
        availability_context.get("latest_router_evidence")
        if isinstance(availability_context.get("latest_router_evidence"), Mapping)
        else {}
    )
    return str(latest_router_evidence.get("intent") or "").strip()
_COMPARISON_RESOLVER_TOOLS = _DISCOVERY_PRODUCT_SOURCE_TOOLS | frozenset({"get_product_description_tool"})
_HIGH_RISK_TRANSACTION_TOOLS = frozenset({
    "get_final_price_tool",
    "compare_discount_tool",
    "transaction_store_preview_tool",
    "get_store_schedule_tool",
    "quick_order_tool",
    "add_to_cart_tool",
    "get_my_coupons_tool",
    "get_available_coupons_tool",
    "get_my_reservations_tool",
    "get_orders_of_user_tool",
    "get_order_status_tool",
})
_STORE_SERVICE_SEARCH_TOOLS = frozenset({
    "search_stores_tool",
    "search_stores_complex_tool",
    "get_store_list_tool",
    "get_nearby_stores_tool",
})
_DISCOVERY_EVENT_CONTENT_TOOLS = frozenset({
    "search_product_tool",
    "get_product_applicable_events_tool",
    "get_product_promotions_tool",
    "get_benefit_event_deal_list_tool",
    "get_events_tool",
    "get_deals_tool",
})
_DISCOVERY_EVENT_CONTENT_FORBIDDEN_TOOLS = frozenset({
    "quick_order_tool",
    "transaction_store_preview_tool",
    "get_store_schedule_tool",
    "get_multi_store_schedule_tool",
})
_WARNING_CONTRACT_VIOLATION_TYPES = frozenset({
    "unexpected_tool_for_contract",
    "requested_product_attribute_contract_drift",
    "compare_metric_metadata_drift",
    "compare_metric_contract_drift",
    "compare_metric_row_missing",
    "forbidden_discovery_first_leg_response",
    "recommendation_approximation_disclosure_missing",
})
_PRICE_OR_COUPON_RE = re.compile(r"가격|얼마|할인가|쿠폰|할인|혜택", re.IGNORECASE)
_COUPON_ANCHOR_RE = re.compile(r"쿠폰", re.IGNORECASE)
_REFERENCE_PURCHASE_RE = re.compile(r"(?:그거|그\s*상품|이거|이\s*상품).{0,20}(구매|주문|결제|살래|살게|사고)", re.IGNORECASE)
_PURCHASE_PRODUCT_RESOLUTION_INTENTS = frozenset({
    "product_search",
    "resolve_product_for_purchase_size_selection",
})
_DISCOVERY_NO_RESULT_RE = re.compile(r"찾을\s*수\s*없|확인되지\s*않|검색되지\s*않|없어요", re.IGNORECASE)
_ORDER_PROGRESS_ONLY_RE = re.compile(
    r"(주문|구매|결제).{0,20}(진행|이어|도와|확정\s*단계|단계로)|"
    r"(진행|이어).{0,20}(주문|구매|결제)",
    re.IGNORECASE,
)
_RESERVATION_STORE_CLAIM_RE = re.compile(
    r"예약(?:하신|한)?\s*(?:매장|지점|곳)|예약\s*매장|예약\s*지점",
    re.IGNORECASE,
)
_RESERVATION_STATUS_CLAIM_RE = re.compile(
    r"예약\s*(?:내역|상태|확인|조회|정보)|예약(?:하신|한|된)?\s*(?:건|내용)|"
    r"예약(?:이|은|는)?.{0,12}(?:있|없|확인|잡혀|되어|돼|됐)|예약\s*확인으로",
    re.IGNORECASE,
)
_REFERENCE_SIGNAL_RE = re.compile(
    r"그거|이거|요거|저거|"
    r"그\s*상품|이\s*상품|해당\s*상품|"
    r"그\s*매장|이\s*매장|해당\s*매장|거기|여기|저기|"
    r"첫\s*번째|1\s*번|두\s*번째|2\s*번|"
    r"방금\s*거|아까\s*거|최근\s*거|해당\s*건",
    re.IGNORECASE,
)
_LEGAL_ACTION_FORBIDDEN_BEHAVIORS = frozenset({
    "provide_legal_action_steps",
    "explain_lawsuit_or_complaint_method",
    "give_legal_advice",
})
_LEGAL_ACTION_PROCEDURE_RE = re.compile(
    r"(?:고소장|소장|내용\s*증명|내용증명|분쟁\s*조정|분쟁조정|소송|고소|신고|법적\s*(?:절차|조치|대응))"
    r".{0,50}(?:작성|제출|접수|발송|보내|신청|관할|경찰서|법원|소비자원|기관|서류|증거|요건|단계|절차)|"
    r"(?:작성|제출|접수|발송|보내|신청|관할|경찰서|법원|소비자원|기관|서류|증거|요건|단계|절차)"
    r".{0,50}(?:고소장|소장|내용\s*증명|내용증명|분쟁\s*조정|분쟁조정|소송|고소|신고|법적\s*(?:절차|조치|대응))",
    re.IGNORECASE,
)
_LEGAL_ACTION_DENIAL_RE = re.compile(
    r"법적\s*(?:절차|조치|대응).{0,24}(?:안내|도움|제공).{0,16}(?:어렵|불가|드릴\s*수\s*없)|"
    r"(?:안내|도움|제공).{0,16}(?:어렵|불가|드릴\s*수\s*없).{0,24}법적\s*(?:절차|조치|대응)",
    re.IGNORECASE,
)
_BEST_SELLER_SIZE_CLARIFICATION_RE = re.compile(
    r"(정확한\s*사이즈|사이즈\s*(?:정보|직접\s*입력)|연식/트림에\s*따라|연식/트림|차량번호|내\s*차량)",
    re.IGNORECASE,
)


def _prefer_router_product_keyword_for_purchase_resolution(
    *,
    known_slots: dict[str, Any],
    tool_args_patch: Mapping[str, Any],
    intent: str,
    action_mode: str,
) -> None:
    keyword = str(tool_args_patch.get("keyword") or "").strip()
    if not keyword:
        return
    pending_intent = str(known_slots.get("pending_intent") or "").strip()
    goal_type = str(known_slots.get("goal_type") or "").strip()
    router_action = str(known_slots.get("router_primary_action") or "").strip()
    if not (
        intent in _PURCHASE_PRODUCT_RESOLUTION_INTENTS
        or action_mode == "purchase_continuation"
        or pending_intent == "order"
        or goal_type == "place_order"
        or router_action == "buy"
    ):
        return
    known_slots["pending_product_name"] = keyword
    known_slots["tire_model"] = keyword
    slot_sources = known_slots.get("slot_sources")
    if not isinstance(slot_sources, dict):
        slot_sources = {}
    else:
        slot_sources = dict(slot_sources)
    slot_sources["pending_product_name"] = "router_evidence"
    slot_sources["tire_model"] = "router_evidence"
    known_slots["slot_sources"] = slot_sources
_OE_PART_NUMBER_REQUEST_RE = re.compile(
    r"(?:\bOE\b|순정|출고\s*타이어|출고용|출고때|출고 시).{0,40}(?:품번|부품\s*번호|파트\s*넘버|part\s*number)|"
    r"(?:품번|부품\s*번호|파트\s*넘버|part\s*number).{0,40}(?:\bOE\b|순정|출고\s*타이어|출고용|출고때|출고 시)",
    re.IGNORECASE,
)
_BEST_SELLER_DISALLOWED_CTA_LABELS = frozenset({
    "사이즈 직접 입력",
    "내 차량 보기",
    "내 차로 찾기",
    "내 차량으로 확인",
    "차량번호로 확인",
})
_REFERENCE_GUARD_EXEMPT_INTENTS = frozenset({
    "best_seller_search",
    "favorite_store_lookup",
    "oe_part_number_unavailable",
    "oe_re_concept_explanation",
    "product_recommendation",
    "tire_recommendation",
    "service_duration_advisory",
    "maintenance_addon_with_tire_service",
    "store_service_availability",
    "general_cancel_fee_policy",
    "general_card_cancel_timing_policy",
    "coupon_usage_policy",
    "coupon_registration_policy",
    "maintenance_history_access_policy",
    "order_document_guidance",
    "delivery_delay_reservation_schedule_policy",
    "legal_action_guidance_denied",
    "human_escalation",
    "support_faq",
    "store_service_advisory",
    "store_visit_advisory",
})
_SUPPORT_ANSWER_ACTION_MODES = frozenset({"support_policy_answer", "info_only"})
_REFERENCE_GUARD_EXEMPT_DISCOVERY_PLAN_TOKENS = frozenset({
    "general_recommendation",
    "condition_recommendation",
    "similar_price_recommendation",
    "vehicle_based_recommendation_refinement",
    "vehicle_resolved_recommendation",
    "best_seller_search",
    "get_best_selling_tires_for_vehicle",
    "get_best_selling_product_for_vehicle",
    "get_best_selling_products_for_vehicle",
    "get_best_selling_products_for_vehicle_timeframe",
    "get_best_selling_tire_by_model_and_size",
    "best_seller_list_by_vehicle_and_size_and_period",
    "query_order_data_for_vehicle_with_period",
    "vehicle_best_seller_search",
    "oe_part_number_unavailable",
})
ROUTER_WINS_INFORMATIONAL_INTENTS = frozenset({
    "card_installment_lookup",
    "product_detail_lookup",
    "product_description",
    "product_comparison",
    "product_size_list_lookup",
    "competitor_counterpart_guidance",
    "compatibility_advisory",
    "delivery_delay_reservation_schedule_policy",
    "coupon_usage_policy",
    "coupon_registration_policy",
    "coupon_stacking_policy",
    "signup_first_purchase_benefit_policy",
    "signup_coupon_guidance",
    "partner_member_coupon_policy",
    "general_cancel_fee_policy",
    "general_card_cancel_timing_policy",
    "reservation_policy_guidance",
    "installation_work_policy",
    "external_tire_install_policy",
    "promotion_gift_policy",
    "tire_condition_photo_policy",
    "tire_manufacture_date_policy",
    "tire_quality_warranty_policy",
    "assurance_service_policy",
    "maintenance_history_access_policy",
    "order_document_guidance",
    "payment_error_troubleshooting",
    "shipping_fee_policy",
    "online_store_price_policy",
    "regional_price_policy",
    "legal_action_guidance_denied",
    "human_escalation",
    "tstation_service_complaint",
    "support_faq",
    "policy_notice_or_escalation",
    "owned_warranty_lookup",
})
ROUTER_WINS_EXECUTION_BOUNDARY_INTENTS = frozenset({
    "stock_store_search",
    "store_search",
    "store_schedule",
    "open_store_search",
    "store_service_search",
    "store_recommendation_by_vehicle_experience",
})
_SUPPORT_FAQ_POLICY_TOOL_INTENTS = frozenset({
    "card_installment_lookup",
    "general_cancel_fee_policy",
    "general_card_cancel_timing_policy",
    "payment_error_troubleshooting",
    "compatibility_advisory",
    "tire_manufacture_date_policy",
    "tire_quality_warranty_policy",
    "reservation_window_policy",
    "external_tire_install_policy",
    "tire_condition_photo_policy",
})
_OWNED_WARRANTY_LOOKUP_INTENTS = frozenset({
    "owned_warranty_lookup",
    "my_warranty_lookup",
    "verify_safe_service_subscription",
    "safe_service_subscription_lookup",
})
_SUPPORT_SAFE_AGENT_TOOLS = (
    "get_faq_tool",
    "search_faq_rag_tool",
    "search_faq_hybrid_tool",
    "get_card_installments_tool",
    "get_product_warranties_tool",
    "get_my_warranties_tool",
    "get_maintenance_dday_tool",
    "check_coupon_stacking_tool",
)
_SUPPORT_POLICY_PURCHASE_FORBIDDEN_TOOLS = frozenset({
    "quick_order_tool",
    "save_to_cart_tool",
    "add_to_cart_tool",
    "transaction_store_preview_tool",
    "get_store_schedule_tool",
    "get_multi_store_schedule_tool",
    "get_store_inventory_tool",
    "get_logistics_inventory_tool",
    "get_final_price_tool",
    "compare_discount_tool",
    "search_product_tool",
})
_CARD_INSTALLMENT_LOOKUP_RE = re.compile(
    r"무이자|할부|몇\s*개?월|[0-9]{1,2}\s*개?월|개월수|카드사별|현대카드|신한카드|삼성카드|국민카드|"
    r"롯데카드|하나카드|농협카드|우리카드|비씨카드|BC카드|스마트\s*페이|smart\s*pay|smartpay",
    re.IGNORECASE,
)
_PAYMENT_TROUBLESHOOTING_RE = re.compile(
    r"결제\s*(?:오류|에러|실패|안\s*돼|안\s*되|안\s*열|진행\s*불가)|"
    r"결제.{0,16}(?:창|화면).{0,16}(?:안\s*열|안\s*떠|멈|하얗|오류|에러|먹통)|"
    r"(?:창|화면).{0,16}(?:멈|하얗|먹통).{0,16}결제|"
    r"승인\s*실패|본인\s*인증.{0,8}(?:실패|안\s*돼|안\s*되)|장착일\s*선택란",
    re.IGNORECASE,
)
_PAYMENT_METHOD_OR_COUPON_POLICY_RE = re.compile(
    r"쿠폰|포인트|제휴\s*혜택|제휴카드|카드사\s*혜택|카드\s*혜택|복원|원복|다시\s*돌아",
    re.IGNORECASE,
)
_COMPARISON_ROUTER_WINS_FOLLOWUP_INTENTS = frozenset({
    "generic_compare",
    "new_compare_metric",
    "continue_previous_compare_metric",
})
_COMPARISON_ROUTER_WINS_RESPONSE_SHAPES = frozenset({
    "metric_comparison_summary",
    "grade_comparison_summary",
})
_ROUTER_WINS_EXECUTION_EXCLUDED_INTENTS = frozenset({
    "quick_order_reservation",
    "quick_order_execute",
    "cart_add",
    "cart_continuation",
    "stock_store_search",
    "store_schedule",
    "selected_store_schedule",
    "reservation_store_info_lookup",
    "reservation_status_lookup",
    "reservation_change_request",
    "order_cancel_status_lookup",
    "owned_order_cancel_fee_inquiry",
    "owned_coupon_lookup",
    "maintenance_history_lookup",
})
_ROUTER_WINS_TRANSACTION_FORBIDDEN_TOOLS = frozenset({
    "quick_order_tool",
    "save_to_cart_tool",
    "transaction_store_preview_tool",
    "get_store_schedule_tool",
    "get_multi_store_schedule_tool",
    "get_store_inventory_tool",
    "get_logistics_inventory_tool",
    "get_final_price_tool",
    "compare_discount_tool",
    "get_orders_of_user_tool",
    "get_order_status_tool",
    "get_my_reservations_tool",
    "get_my_coupons_tool",
    "get_available_coupons_tool",
    "get_coupon_applicable_products_tool",
    "issue_coupon_tool",
})
_ROUTER_WINS_ORDER_EXECUTION_FORBIDDEN_TOOLS = frozenset({
    "quick_order_tool",
    "save_to_cart_tool",
    "add_to_cart_tool",
    "get_final_price_tool",
    "compare_discount_tool",
    "get_orders_of_user_tool",
    "get_order_status_tool",
    "get_my_reservations_tool",
    "get_my_coupons_tool",
    "get_available_coupons_tool",
    "get_coupon_applicable_products_tool",
    "issue_coupon_tool",
})


@dataclass(frozen=True)
class TurnContract:
    """Stable policy snapshot for one user turn."""

    domain: str
    intent: str
    sub_intent: str | None = None
    known_slots: Mapping[str, Any] = field(default_factory=dict)
    required_slots: tuple[str, ...] = ()
    blocking_required_slots: tuple[str, ...] = ()
    resolvable_required_slots: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    preferred_tool: str | None = None
    tool_args_patch: Mapping[str, Any] = field(default_factory=dict)
    response_decision: Mapping[str, Any] | None = None
    risk_level: str = "low"
    fallback_reason: str | None = None
    planner_intent: str | None = None
    planner_domains: tuple[str, ...] = ()
    execution_plan: tuple[str, ...] = ()
    referred_objects: Mapping[str, Any] = field(default_factory=dict)
    planner_confidence: float | None = None
    has_reference_signal: bool = False
    planner_source: str | None = None
    override_applied: bool = False
    override_reason: str | None = None
    original_router_domains: tuple[str, ...] = ()
    original_router_execution_plan: tuple[str, ...] = ()
    override_blocked: bool = False
    blocked_override_reason: str | None = None
    contract_drift: tuple[Mapping[str, Any], ...] = ()
    resolved_context: Mapping[str, Any] = field(default_factory=dict)
    action_mode: str = "unspecified"
    context_state: str = "dormant"
    resume_source: str = "none"
    router_waited: bool = False
    router_source: str | None = None
    contract_source: str | None = None
    speculative_used_for_contract: bool = False
    current_turn_intent: str | None = None
    previous_pending_intent: str | None = None
    previous_goal_type: str | None = None
    resume_anchor_detected: bool = False
    dormant_context_reason: str | None = None
    blocking_required_slots_source: str | None = None
    flow_id: str | None = None
    flow_step: str | None = None
    router_wins_applied: bool = False
    code_frame_intent: str | None = None
    drift_resolution: str | None = None
    stale_context_used_for: str | None = None
    response_policy_source: str | None = None
    contract_seed: Mapping[str, Any] = field(default_factory=dict)
    context_evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "intent": self.intent,
            "sub_intent": self.sub_intent,
            "known_slots": dict(self.known_slots),
            "required_slots": list(self.required_slots),
            "blocking_required_slots": list(self.blocking_required_slots),
            "resolvable_required_slots": list(self.resolvable_required_slots),
            "allowed_tools": list(self.allowed_tools),
            "forbidden_tools": list(self.forbidden_tools),
            "blocked_tools": list(self.forbidden_tools),
            "preferred_tool": self.preferred_tool,
            "tool_args_patch": dict(self.tool_args_patch),
            "response_decision": dict(self.response_decision or {}),
            "risk_level": self.risk_level,
            "fallback_reason": self.fallback_reason,
            "planner_intent": self.planner_intent,
            "planner_domains": list(self.planner_domains),
            "execution_plan": list(self.execution_plan),
            "referred_objects": dict(self.referred_objects),
            "planner_confidence": self.planner_confidence,
            "has_reference_signal": self.has_reference_signal,
            "planner_source": self.planner_source,
            "override_applied": self.override_applied,
            "override_reason": self.override_reason,
            "original_router_domains": list(self.original_router_domains),
            "original_router_execution_plan": list(self.original_router_execution_plan),
            "override_blocked": self.override_blocked,
            "blocked_override_reason": self.blocked_override_reason,
            "contract_drift": [dict(item) for item in self.contract_drift],
            "resolved_context": dict(self.resolved_context),
            "action_mode": self.action_mode,
            "context_state": self.context_state,
            "resume_source": self.resume_source,
            "router_waited": self.router_waited,
            "router_source": self.router_source,
            "contract_source": self.contract_source,
            "speculative_used_for_contract": self.speculative_used_for_contract,
            "current_turn_intent": self.current_turn_intent,
            "previous_pending_intent": self.previous_pending_intent,
            "previous_goal_type": self.previous_goal_type,
            "resume_anchor_detected": self.resume_anchor_detected,
            "dormant_context_reason": self.dormant_context_reason,
            "blocking_required_slots_source": self.blocking_required_slots_source,
            "flow_id": self.flow_id,
            "flow_step": self.flow_step,
            "router_wins_applied": self.router_wins_applied,
            "code_frame_intent": self.code_frame_intent,
            "drift_resolution": self.drift_resolution,
            "stale_context_used_for": self.stale_context_used_for,
            "response_policy_source": self.response_policy_source,
            "contract_seed": dict(self.contract_seed),
            "context_evidence": dict(self.context_evidence),
        }


_GUARD_EVENT_STALE_CONTEXT_KEYS = frozenset({
    "template_data",
    "templateData",
    "ui_action",
    "uiAction",
    "pending_intent",
    "pendingIntent",
    "goal_type",
    "goalType",
})

def _guard_event_contract_snapshot(contract: TurnContract) -> dict[str, Any]:
    snapshot = contract.to_dict()
    for key in ("known_slots", "resolved_context", "contract_seed", "context_evidence"):
        value = snapshot.get(key)
        if isinstance(value, Mapping):
            snapshot[key] = _strip_guard_event_stale_context(value)
    return snapshot

def _strip_guard_event_stale_context(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _strip_guard_event_stale_context(item)
            for key, item in value.items()
            if str(key) not in _GUARD_EVENT_STALE_CONTEXT_KEYS
        }
    if isinstance(value, list):
        return [_strip_guard_event_stale_context(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_strip_guard_event_stale_context(item) for item in value)
    return value

def _router_wins_information_interrupts_slot_fill(
    *,
    router_wins_intent: str | None,
    context_state: str,
    resume_source: str,
) -> bool:
    intent = str(router_wins_intent or "").strip()
    if not intent:
        return False
    if str(context_state or "").strip() != "resumed":
        return False
    if not str(resume_source or "").strip().startswith("expected_slot_fill:"):
        return False
    return intent in ROUTER_WINS_INFORMATIONAL_INTENTS or intent.endswith("_policy") or intent.endswith("_guidance")

def _drop_interrupted_slot_fill_values(
    values: Mapping[str, Any],
    *,
    resume_source: str,
) -> dict[str, Any]:
    sanitized = dict(values)
    expected_slot = str(resume_source or "").partition(":")[2]
    if expected_slot == "region":
        for key in ("region", "place_query"):
            sanitized.pop(key, None)
    if expected_slot == "store":
        for key in ("store_name", "shop_name"):
            sanitized.pop(key, None)
    if expected_slot == "schedule":
        for key in ("requested_cal_day", "rsv_hour", "booking_datetime"):
            sanitized.pop(key, None)
    return sanitized

def build_turn_contract(
    *,
    user_text: str = "",
    intent_frame: IntentFrame | None = None,
    tool_plan: ToolPlan | None = None,
    response_decision: ResponseDecision | None = None,
    cross_domain_plan: CrossDomainPlan | None = None,
    routing_result: Any | None = None,
    merged_slots: Any | None = None,
    action_mode: str = "unspecified",
    context_state: str = "dormant",
    resume_source: str = "none",
    router_waited: bool = False,
    router_source: str = "unknown",
    contract_source: str | None = None,
    speculative_used_for_contract: bool = False,
    previous_pending_intent: str | None = None,
    previous_goal_type: str | None = None,
    resume_anchor_detected: bool = False,
    dormant_context_reason: str | None = None,
    contract_seed: Mapping[str, Any] | None = None,
    context_evidence: Mapping[str, Any] | None = None,
) -> TurnContract:
    """Combine policy objects into a single contract without changing execution."""

    planner_domains = _planner_domains(routing_result, cross_domain_plan)
    execution_plan = _execution_plan(routing_result, cross_domain_plan)
    planner_intent = _planner_best_seller_intent(
        _planner_intent(routing_result, cross_domain_plan),
        user_text=user_text,
    )
    if planner_intent == "unknown":
        planner_intent = None
    policy_intent = str(getattr(routing_result, "policy_intent", "") or "")
    if planner_intent == "payment_error_troubleshooting" and _is_payment_error_policy_overmatch(user_text):
        planner_intent = None
    if _should_normalize_dot_manufacture_date_policy(
        user_text=user_text,
        policy_intent=policy_intent,
        planner_intent=planner_intent,
    ):
        policy_intent = "tire_manufacture_date_policy"
        if planner_intent == "tire_quality_warranty_policy":
            planner_intent = "tire_manufacture_date_policy"
    router_wins_intent = _router_wins_current_turn_intent(
        user_text=user_text,
        planner_intent=planner_intent,
        policy_intent=policy_intent,
        routing_result=routing_result,
        intent_frame=intent_frame,
        response_decision=response_decision,
        action_mode=action_mode,
    )
    if router_wins_intent in {"signup_first_purchase_benefit_policy", "signup_coupon_guidance"} and _ASSURANCE_SERVICE_POLICY_ANCHOR_RE.search(
        user_text or ""
    ):
        router_wins_intent = "assurance_service_policy"
    code_domain = _domain_value(intent_frame.domain) if intent_frame is not None else _domain_from_routing(routing_result)
    code_intent = intent_frame.intent if intent_frame is not None else _intent_from_cross_domain(cross_domain_plan)
    transaction_boundary_frame = _transaction_policy_boundary_frame(user_text=user_text, merged_slots=merged_slots)
    if transaction_boundary_frame is not None and _should_apply_transaction_policy_boundary(
        planner_intent=planner_intent,
        policy_intent=policy_intent,
        code_intent=code_intent,
        code_domain=code_domain,
    ):
        code_domain = _domain_value(transaction_boundary_frame.domain)
        code_intent = transaction_boundary_frame.intent
        if planner_intent in {None, "product_recommendation", "sized_product_recommendation"}:
            planner_intent = transaction_boundary_frame.intent
        if policy_intent in {"product_recommendation", "sized_product_recommendation"}:
            policy_intent = transaction_boundary_frame.intent
    keep_registered_vehicle_contract = _should_keep_registered_vehicle_information_contract(
        user_text=user_text,
        intent_frame=intent_frame,
        code_intent=code_intent,
    )
    if keep_registered_vehicle_contract and policy_intent == "coupon_registration_policy":
        policy_intent = "none"
    if keep_registered_vehicle_contract and planner_intent == "coupon_registration_policy":
        planner_intent = None
    if keep_registered_vehicle_contract and router_wins_intent == "coupon_registration_policy":
        router_wins_intent = None
    if _should_normalize_dot_manufacture_date_policy(
        user_text=user_text,
        policy_intent=policy_intent,
        planner_intent=planner_intent,
        code_intent=code_intent,
    ):
        policy_intent = "tire_manufacture_date_policy"
        if planner_intent == "tire_quality_warranty_policy":
            planner_intent = "tire_manufacture_date_policy"
        if code_intent == "tire_quality_warranty_policy":
            code_intent = "tire_manufacture_date_policy"
    if _should_force_card_installment_lookup_intent(
        user_text=user_text,
        planner_intent=planner_intent,
        policy_intent=policy_intent,
        code_intent=code_intent,
        domain=code_domain,
        planner_domains=planner_domains,
    ):
        code_domain = "support"
        code_intent = "card_installment_lookup"
        router_wins_intent = "card_installment_lookup"
    domain = planner_domains[0] if planner_domains else code_domain
    intent = planner_intent or code_intent
    if keep_registered_vehicle_contract:
        domain = code_domain
        intent = code_intent
    elif router_wins_intent:
        domain = _router_wins_domain(router_wins_intent, planner_domains)
        intent = router_wins_intent
    elif _should_lock_code_intent_contract(code_intent):
        domain = code_domain
        intent = code_intent
    sub_intent = intent_frame.sub_intent if intent_frame is not None else None
    best_seller_anchor = is_best_seller_request(user_text, include_demographic_preference=False)
    known_slots = _compact_slots({
        **(dict(intent_frame.known_slots) if intent_frame is not None else {}),
        **(dict(transaction_boundary_frame.known_slots) if transaction_boundary_frame is not None else {}),
        **_slots_from_model(merged_slots),
    })
    availability_context = (
        known_slots.get("availability_context") if isinstance(known_slots.get("availability_context"), Mapping) else {}
    )
    latest_router_evidence = (
        availability_context.get("latest_router_evidence")
        if isinstance(availability_context.get("latest_router_evidence"), Mapping)
        else {}
    )
    known_slots = merge_router_evidence_known_slots(
        known_slots,
        latest_router_evidence,
        preserve_existing=False,
    )
    known_slots = _normalize_quantity_slots(known_slots)
    if intent_frame is not None:
        requested_product_attribute = str(intent_frame.entities.get("requested_product_attribute") or "")
        compare_metric = str(intent_frame.entities.get("compare_metric") or "")
        comparison_followup_intent = str(intent_frame.entities.get("comparison_followup_intent") or "")
        oe_replacement_type = str(intent_frame.entities.get("oe_replacement_type") or "")
        stock_check_mode = str(intent_frame.entities.get("stock_check_mode") or "")
        discovery_followup_action = str(intent_frame.entities.get("discovery_followup_action") or "")
        recommendation_scenario = str(intent_frame.entities.get("recommendation_scenario") or "")
        recommendation_context = intent_frame.entities.get("recommendation_context")
        if requested_product_attribute:
            known_slots["requested_product_attribute"] = requested_product_attribute
        if compare_metric:
            known_slots["compare_metric"] = compare_metric
        if comparison_followup_intent:
            known_slots["comparison_followup_intent"] = comparison_followup_intent
        if oe_replacement_type:
            known_slots["oe_replacement_type"] = oe_replacement_type
        if stock_check_mode:
            known_slots["stock_check_mode"] = stock_check_mode
        if discovery_followup_action:
            known_slots["discovery_followup_action"] = discovery_followup_action
        if recommendation_scenario:
            for key in (
                "recommendation_scenario",
                "applied_rcmd_type",
                "applied_vehicle_type",
                "applied_season_nm",
                "approximation_basis",
            ):
                value = intent_frame.entities.get(key)
                if value not in (None, ""):
                    known_slots[key] = value
            if intent_frame.entities.get("approximation") is True:
                known_slots["approximation"] = True
        normalized_recommendation_context = _recommendation_context_dict(recommendation_context)
        if normalized_recommendation_context:
            known_slots["recommendation_context"] = normalized_recommendation_context
            scenario = str(
                normalized_recommendation_context.get("recommendation_scenario")
                or normalized_recommendation_context.get("scenario")
                or ""
            ).strip()
            if scenario and not known_slots.get("recommendation_scenario"):
                known_slots["recommendation_scenario"] = scenario
    tool_plan_metadata = tool_plan.metadata if tool_plan is not None else {}
    if isinstance(tool_plan_metadata, Mapping):
        expected_tool_args = tool_plan_metadata.get("recommendation_expected_tool_args")
        if isinstance(expected_tool_args, Mapping):
            known_slots["recommendation_expected_tool_args"] = {
                key: value for key, value in expected_tool_args.items() if value not in (None, "")
            }
        schedule_mode = str(tool_plan_metadata.get("schedule_mode") or "").strip()
        stock_check_mode = str(tool_plan_metadata.get("stock_check_mode") or "").strip()
        if schedule_mode and not known_slots.get("schedule_mode"):
            known_slots["schedule_mode"] = schedule_mode
        if stock_check_mode and not known_slots.get("stock_check_mode"):
            known_slots["stock_check_mode"] = stock_check_mode
    if policy_intent and policy_intent != "none":
        known_slots["policy_intent"] = policy_intent
    routing_pending_check_topic = str(getattr(routing_result, "pending_check_topic", "") or "").strip()
    if (
        planner_intent
        and planner_intent not in _PENDING_CHECK_FOLLOWUP_PLANNER_INTENTS
        and routing_pending_check_topic in {"", "none"}
        and str(known_slots.get("pending_check_topic") or "").strip()
    ):
        known_slots.pop("pending_check_topic", None)
        known_slots.pop("pending_check_object_type", None)
        known_slots.pop("pending_check_object_value", None)
        known_slots.pop("pending_check_turns_remaining", None)
    if routing_pending_check_topic and routing_pending_check_topic != "none" and not known_slots.get("pending_check_topic"):
        known_slots["pending_check_topic"] = routing_pending_check_topic
    routing_pending_check_object_type = str(getattr(routing_result, "pending_check_object_type", "") or "").strip()
    if (
        routing_pending_check_object_type
        and routing_pending_check_object_type != "none"
        and not known_slots.get("pending_check_object_type")
    ):
        known_slots["pending_check_object_type"] = routing_pending_check_object_type
    routing_pending_check_object_value = str(getattr(routing_result, "pending_check_object_value", "") or "").strip()
    if routing_pending_check_object_value and not known_slots.get("pending_check_object_value"):
        known_slots["pending_check_object_value"] = routing_pending_check_object_value
    latest_router_intent = _latest_router_evidence_intent(known_slots)
    if planner_intent == "owned_coupon_lookup" or code_intent == "owned_coupon_lookup":
        domain = "transaction"
        intent = "owned_coupon_lookup"
    if latest_router_intent == "product_coupon_eligibility" and intent in {"coupon_usage", "price_or_coupon_check"}:
        domain = "transaction"
        intent = "product_coupon_eligibility"
        if not known_slots.get("product_name"):
            fallback_product_name = (
                known_slots.get("tire_model")
                or known_slots.get("pending_product_name")
                or known_slots.get("pattern_name")
            )
            if fallback_product_name not in (None, "", [], {}):
                known_slots["product_name"] = fallback_product_name
        if (
            not known_slots.get("product_name")
            and str(known_slots.get("pending_check_object_type") or "").strip() == "product_name"
            and known_slots.get("pending_check_object_value")
        ):
            known_slots["product_name"] = known_slots.get("pending_check_object_value")
    response_metadata = response_decision.metadata if response_decision is not None else {}
    response_shape_key = str(response_metadata.get("response_shape_key") or "").strip() if isinstance(response_metadata, Mapping) else ""
    if domain == "support" and intent == "support_faq" and response_shape_key in _SUPPORT_FAQ_POLICY_TOOL_INTENTS:
        intent = response_shape_key
        policy_intent = response_shape_key
        known_slots["policy_intent"] = response_shape_key
    if isinstance(response_metadata, Mapping):
        requested_product_attribute = str(response_metadata.get("requested_product_attribute") or "")
        compare_metric = str(response_metadata.get("compare_metric") or "")
        comparison_followup_intent = str(response_metadata.get("comparison_followup_intent") or "")
        oe_replacement_type = str(response_metadata.get("oe_replacement_type") or "")
        stock_check_mode = str(response_metadata.get("stock_check_mode") or "")
        schedule_mode = str(response_metadata.get("schedule_mode") or "").strip()
        if requested_product_attribute and not known_slots.get("requested_product_attribute"):
            known_slots["requested_product_attribute"] = requested_product_attribute
        if compare_metric and not known_slots.get("compare_metric"):
            known_slots["compare_metric"] = compare_metric
        if comparison_followup_intent and not known_slots.get("comparison_followup_intent"):
            known_slots["comparison_followup_intent"] = comparison_followup_intent
        if oe_replacement_type and not known_slots.get("oe_replacement_type"):
            known_slots["oe_replacement_type"] = oe_replacement_type
        if stock_check_mode and not known_slots.get("stock_check_mode"):
            known_slots["stock_check_mode"] = stock_check_mode
        if schedule_mode and not known_slots.get("schedule_mode"):
            known_slots["schedule_mode"] = schedule_mode
    flow_id = None
    flow_step = None
    if isinstance(tool_plan_metadata, Mapping):
        flow_id = str(tool_plan_metadata.get("flow_id") or "").strip() or None
        flow_step = str(tool_plan_metadata.get("flow_step") or "").strip() or None
    if isinstance(response_metadata, Mapping):
        flow_id = flow_id or (str(response_metadata.get("flow_id") or "").strip() or None)
        flow_step = flow_step or (str(response_metadata.get("flow_step") or "").strip() or None)

    has_reference_signal = _has_reference_signal(user_text)
    if intent == "transaction_fallback" and _is_recoverable_today_install_stock_contract(known_slots):
        intent = "stock_store_search"
    if code_intent == "service_duration_advisory":
        domain = "transaction"
        intent = "service_duration_advisory"
    if code_intent == "maintenance_addon_with_tire_service":
        domain = "transaction"
        intent = "maintenance_addon_with_tire_service"
    if code_intent == "store_service_availability":
        domain = "support"
        intent = "store_service_availability"
    if code_intent == "reservation_store_info_lookup":
        domain = "transaction"
        intent = "reservation_store_info_lookup"
    if code_intent == "reservation_status_lookup":
        domain = "transaction"
        intent = "reservation_status_lookup"
    if code_intent == "reservation_change_request":
        domain = "transaction"
        intent = "reservation_change_request"
    if code_intent == "order_arrival_status_lookup":
        domain = "transaction"
        intent = "order_arrival_status_lookup"
    if code_intent == "maintenance_history_lookup" or planner_intent == "maintenance_history_lookup":
        domain = "transaction"
        intent = "maintenance_history_lookup"
    if code_intent == "maintenance_history_access_policy" or planner_intent == "maintenance_history_access_policy":
        domain = "support"
        intent = "maintenance_history_access_policy"
    if code_intent == "order_document_guidance" or planner_intent == "order_document_guidance":
        domain = "support"
        intent = "order_document_guidance"
    if code_intent == "delivery_delay_reservation_schedule_policy" or planner_intent == "delivery_delay_reservation_schedule_policy":
        domain = "support"
        intent = "delivery_delay_reservation_schedule_policy"
    if code_intent == "card_installment_lookup" or planner_intent == "card_installment_lookup":
        domain = "support"
        intent = "card_installment_lookup"
    if code_intent == "general_card_cancel_timing_policy" or planner_intent == "general_card_cancel_timing_policy":
        domain = "support"
        intent = "general_card_cancel_timing_policy"
    if code_intent == "coupon_usage_policy" or planner_intent == "coupon_usage_policy":
        domain = "support"
        intent = "coupon_usage_policy"
    if code_intent == "coupon_stacking_policy" or planner_intent in {"coupon_stacking_policy", "stacking"}:
        domain = "support"
        intent = "coupon_stacking_policy"
    if code_intent == "coupon_registration_policy" or planner_intent == "coupon_registration_policy":
        domain = "support"
        intent = "coupon_registration_policy"
    if planner_intent == "order_cart_status_check":
        domain = "transaction"
        intent = "order_history_lookup"
        known_slots["owned_record_target"] = "order"
    if planner_intent == "coupon_applicability_check" or intent == "coupon_applicability_check":
        domain = "transaction"
        intent = "product_coupon_eligibility"
        if (
            not known_slots.get("product_name")
            and str(known_slots.get("pending_check_object_type") or "").strip() == "product_name"
            and known_slots.get("pending_check_object_value")
        ):
            known_slots["product_name"] = known_slots.get("pending_check_object_value")
    if _is_discovery_event_content_contract(routing_result, planner_intent, code_intent):
        discovery_event_content_intents = {
            "benefit_event_list_lookup",
            "benefit_deal_list",
            "product_event_lookup",
            "product_promotion_lookup",
            "product_coupon_lookup",
            "product_deal_lookup",
        }
        domain = "discovery"
        intent = (
            planner_intent if planner_intent in discovery_event_content_intents
            else code_intent if code_intent in discovery_event_content_intents
            else "product_event_lookup"
        )
        known_slots["goal_type"] = intent
    if planner_intent == "quick_order_execute" and _has_quick_order_execute_slots(known_slots):
        intent = "quick_order_execute"
    if code_intent == "order_cancel_status_lookup":
        intent = "order_cancel_status_lookup"
    if router_wins_intent:
        domain = _router_wins_domain(router_wins_intent, planner_domains)
        intent = router_wins_intent
    intent = _current_turn_stock_owner_intent(intent, known_slots)
    if intent == "stock_store_search":
        domain = "transaction"
    action_required_slots = tool_plan.required_slots if tool_plan is not None else ()
    preferred_tool = str(tool_plan.preferred_tool or "").strip() if tool_plan is not None else ""
    tool_args_patch = {
        str(key): value
        for key, value in dict(tool_plan.tool_args_patch if tool_plan is not None else {}).items()
        if value not in (None, "", [], {})
    }
    if _router_wins_information_interrupts_slot_fill(
        router_wins_intent=router_wins_intent,
        context_state=context_state,
        resume_source=resume_source,
    ):
        known_slots = _drop_interrupted_slot_fill_values(known_slots, resume_source=resume_source)
        tool_args_patch = _drop_interrupted_slot_fill_values(tool_args_patch, resume_source=resume_source)
        action_mode = "support_policy_answer"
        context_state = "dormant"
        resume_source = "none"
        dormant_context_reason = dormant_context_reason or "support_turn"
    _prefer_router_product_keyword_for_purchase_resolution(
        known_slots=known_slots,
        tool_args_patch=tool_args_patch,
        intent=intent,
        action_mode=action_mode,
    )
    fallback_required_slots = (
        intent_frame.missing_slots
        if tool_plan is None and intent_frame is not None
        else ()
    )
    cross_domain_required_slots = (
        _required_slots_from_cross_domain(cross_domain_plan)
        if tool_plan is None
        else ()
    )
    required_slots = _merge_tuple(
        action_required_slots,
        fallback_required_slots,
        cross_domain_required_slots,
    )
    required_slots = _merge_tuple(
        required_slots,
        _derived_required_slots(
            user_text,
            code_intent,
            known_slots,
            cross_domain_plan=cross_domain_plan,
        ),
    )
    router_wins_preempted_required_slots = bool(router_wins_intent and required_slots)
    if router_wins_intent:
        required_slots = ()
    required_slots = _strip_downstream_transaction_required_slots_for_discovery_resolution(
        required_slots,
        intent=intent,
        known_slots=known_slots,
        cross_domain_plan=cross_domain_plan,
    )
    selected_store_schedule_continuation = _selected_store_schedule_continuation_matches(
        intent=intent,
        known_slots=known_slots,
        resume_source=resume_source,
    )
    if selected_store_schedule_continuation:
        required_slots = tuple(
            slot for slot in required_slots
            if slot not in {"requested_cal_day", "rsv_hour", "booking_datetime"}
        )
    required_slots = _filter_satisfied_required_slots(required_slots, known_slots)
    resolvable_required_slots = _resolvable_required_slots(required_slots, cross_domain_plan, known_slots)
    blocking_required_slots = _blocking_required_slots(
        user_text,
        required_slots,
        resolvable_required_slots,
        intent=intent,
        routing_result=routing_result,
    )
    blocking_required_slots_source = _blocking_required_slots_source(
        user_text=user_text,
        intent=intent,
        routing_result=routing_result,
        blocking_required_slots=blocking_required_slots,
    )
    allowed_tools = tuple(tool_plan.allowed_tools) if tool_plan is not None else ()
    allowed_tools = _augment_allowed_tools_for_discovery_resolution(
        allowed_tools,
        intent=intent,
        known_slots=known_slots,
        cross_domain_plan=cross_domain_plan,
    )
    forbidden_tools = tuple(tool_plan.forbidden_tools) if tool_plan is not None else ()
    if router_wins_intent:
        router_allowed_tools, router_forbidden_tools = _router_wins_tool_boundary(router_wins_intent)
        allowed_tools = router_allowed_tools
        forbidden_tools = _merge_tuple(
            tuple(tool for tool in forbidden_tools if tool not in router_allowed_tools),
            router_forbidden_tools,
        )
    if planner_intent == "quick_order_execute" and _has_quick_order_execute_slots(known_slots):
        allowed_tools = _merge_tuple(allowed_tools, ("quick_order_tool",))
        forbidden_tools = tuple(tool for tool in forbidden_tools if tool != "quick_order_tool")
    if selected_store_schedule_continuation:
        allowed_tools = ("get_store_schedule_tool",)
        forbidden_tools = _merge_tuple(
            tuple(tool for tool in forbidden_tools if tool != "get_store_schedule_tool"),
            (
                "transaction_store_preview_tool",
                "get_store_inventory_tool",
                "get_logistics_inventory_tool",
                "get_store_list_tool",
                "get_nearby_stores_tool",
                "search_stores_tool",
                "get_multi_store_schedule_tool",
                "quick_order_tool",
            ),
        )
    if intent == "stock_store_search" and str(known_slots.get("stock_check_mode") or "") == "inventory_only":
        allowed_tools = _merge_tuple(
            allowed_tools,
            (
                "search_product_tool",
                "get_store_list_tool",
                "search_stores_tool",
                "get_store_inventory_tool",
                "get_logistics_inventory_tool",
            ),
        )
        forbidden_tools = _merge_tuple(forbidden_tools, tuple(_INVENTORY_ONLY_STOCK_ACTION_TOOLS))
    if _is_owned_record_lookup_intent(intent):
        record_allowed_tools, record_forbidden_tools, record_preferred_tool = _owned_record_lookup_tool_boundary(intent)
        allowed_tools = record_allowed_tools
        forbidden_tools = _merge_tuple(
            tuple(tool for tool in forbidden_tools if tool not in record_allowed_tools),
            record_forbidden_tools,
        )
        preferred_tool = record_preferred_tool
        tool_args_patch = {}
        required_slots = ()
        resolvable_required_slots = ()
        blocking_required_slots = ()
        blocking_required_slots_source = f"{intent}_contract"
        if action_mode == "unspecified":
            action_mode = "owned_record_lookup"
    payment_error_overmatched_installment = (
        policy_intent == "payment_error_troubleshooting" and _CARD_INSTALLMENT_LOOKUP_RE.search(user_text or "") is not None
    )
    payment_error_without_troubleshooting_anchor = (
        policy_intent == "payment_error_troubleshooting" and _is_payment_error_policy_overmatch(user_text)
    )
    support_policy_intent = policy_intent
    if support_policy_intent in {"signup_first_purchase_benefit_policy", "signup_coupon_guidance"} and _ASSURANCE_SERVICE_POLICY_ANCHOR_RE.search(
        user_text or ""
    ):
        support_policy_intent = "assurance_service_policy"
    if (
        domain == "support"
        and support_policy_intent
        and support_policy_intent != "none"
        and not payment_error_overmatched_installment
        and not payment_error_without_troubleshooting_anchor
    ):
        intent = support_policy_intent
        if support_policy_intent in _SUPPORT_FAQ_POLICY_TOOL_INTENTS:
            allowed_tools = _merge_tuple(
                allowed_tools,
                _SUPPORT_SAFE_AGENT_TOOLS,
            )
            forbidden_tools = _merge_tuple(
                forbidden_tools,
                ("search_product_tool", "get_final_price_tool", "transfer_to_qna_tool"),
            )
    if router_wins_intent:
        domain = _router_wins_domain(router_wins_intent, planner_domains)
        intent = router_wins_intent
        router_allowed_tools, router_forbidden_tools = _router_wins_tool_boundary(router_wins_intent)
        allowed_tools = router_allowed_tools
        forbidden_tools = _merge_tuple(
            tuple(tool for tool in forbidden_tools if tool not in router_allowed_tools),
            router_forbidden_tools,
        )
    if intent == "legal_action_guidance_denied":
        allowed_tools = _merge_tuple(allowed_tools, ("transfer_to_qna_tool",))
        allowed_tools = tuple(
            tool for tool in allowed_tools if tool not in {"get_faq_tool", "search_faq_hybrid_tool", "search_faq_rag_tool"}
        )
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "get_faq_tool",
                "search_faq_hybrid_tool",
                "search_faq_rag_tool",
                "search_product_tool",
                "get_final_price_tool",
            ),
        )
    if intent == "benefit_event_list_lookup":
        allowed_tools = ("get_benefit_event_deal_list_tool",)
        forbidden_tools = _merge_tuple(
            tuple(tool for tool in forbidden_tools if tool != "get_benefit_event_deal_list_tool"),
            (
                "get_events_tool",
                "get_deals_tool",
                "get_product_promotions_tool",
                "get_product_applicable_events_tool",
                "search_product_tool",
            ),
        )
        preferred_tool = "get_benefit_event_deal_list_tool"
        tool_args_patch = {"lang_cd": "ko"}
    if intent in {
        "product_event_lookup",
        "product_promotion_lookup",
        "product_coupon_lookup",
        "product_deal_lookup",
    }:
        allowed_tools = _merge_tuple(allowed_tools, tuple(_DISCOVERY_EVENT_CONTENT_TOOLS))
        forbidden_tools = _merge_tuple(forbidden_tools, tuple(_DISCOVERY_EVENT_CONTENT_FORBIDDEN_TOOLS))
    if intent == "maintenance_history_lookup":
        allowed_tools = _merge_tuple(allowed_tools, ("get_maintenance_history_tool",))
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            ("get_products_recommendations_tool", "search_product_tool", "get_orders_of_user_tool"),
        )
    if intent == "maintenance_history_access_policy":
        allowed_tools = ()
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "get_maintenance_history_tool",
                "get_orders_of_user_tool",
                "get_products_recommendations_tool",
                "search_product_tool",
            ),
        )
    if intent == "signup_first_purchase_benefit_policy":
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "issue_coupon_tool",
                "get_my_coupons_tool",
                "get_coupon_applicable_products_tool",
                "transfer_to_qna_tool",
            ),
        )
    if intent == "signup_coupon_guidance":
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "issue_coupon_tool",
                "get_my_coupons_tool",
                "get_coupon_applicable_products_tool",
                "transfer_to_qna_tool",
            ),
        )
    if intent == "product_coupon_eligibility":
        allowed_tools = _merge_tuple(
            allowed_tools,
            ("get_my_coupons_tool", "get_product_promotions_tool", "get_coupon_applicable_products_tool"),
        )
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            ("issue_coupon_tool", "search_product_tool", "get_product_description_tool", "get_final_price_tool"),
        )
        if not preferred_tool or preferred_tool in forbidden_tools:
            preferred_tool = "get_my_coupons_tool"
            tool_args_patch = {}
    if intent == "owned_coupon_lookup":
        allowed_tools = _merge_tuple(
            allowed_tools,
            ("get_my_coupons_tool",),
        )
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "issue_coupon_tool",
                "search_product_tool",
                "get_product_description_tool",
                "get_coupon_applicable_products_tool",
                "get_final_price_tool",
            ),
        )
        if not preferred_tool or preferred_tool in forbidden_tools:
            preferred_tool = "get_my_coupons_tool"
            tool_args_patch = {}
        required_slots = ()
        resolvable_required_slots = ()
        blocking_required_slots = ()
        blocking_required_slots_source = "owned_coupon_lookup_contract"
    if intent == "partner_member_coupon_policy":
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "issue_coupon_tool",
                "get_my_coupons_tool",
                "get_coupon_applicable_products_tool",
            ),
        )
    if intent == "coupon_usage_policy":
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "issue_coupon_tool",
                "get_my_coupons_tool",
                "get_coupon_applicable_products_tool",
                "get_final_price_tool",
            ),
        )
    if intent == "card_installment_lookup":
        allowed_tools = ("get_card_installments_tool",)
        forbidden_tools = _merge_tuple(
            tuple(tool for tool in forbidden_tools if tool != "get_card_installments_tool"),
            (
                "search_faq_hybrid_tool",
                "search_faq_rag_tool",
                "get_faq_tool",
                "transfer_to_qna_tool",
                "search_product_tool",
                "get_final_price_tool",
            ),
        )
        preferred_tool = "get_card_installments_tool"
        required_slots = ()
        resolvable_required_slots = ()
        blocking_required_slots = ()
        blocking_required_slots_source = "card_installment_lookup_contract"
    if intent == "coupon_stacking_policy":
        allowed_tools = _merge_tuple(
            allowed_tools,
            ("get_my_coupons_tool", "check_coupon_stacking_tool"),
        )
        forbidden_tools = _merge_tuple(
            tuple(tool for tool in forbidden_tools if tool not in {"get_my_coupons_tool", "check_coupon_stacking_tool"}),
            (
                "issue_coupon_tool",
                "search_product_tool",
                "get_product_description_tool",
                "get_coupon_applicable_products_tool",
                "get_final_price_tool",
                "search_faq_hybrid_tool",
            ),
        )
        if not preferred_tool or preferred_tool in forbidden_tools:
            preferred_tool = "get_my_coupons_tool"
            tool_args_patch = {}
        required_slots = ()
        resolvable_required_slots = ()
        blocking_required_slots = ()
        blocking_required_slots_source = "coupon_stacking_policy_contract"
        response_decision_payload = {
            "response_shape": "clarify",
            "template": "quickReply",
            "required_slots": [],
            "forbidden_behaviors": [
                "generic_faq_answer",
                "infer_stacking_without_tool",
                "start_product_coupon_applicability_lookup",
            ],
            "assistant_guidance": (
                "쿠폰 중복 사용 가능 여부는 일반 FAQ로 답하지 말고, 보유 쿠폰 목록에서 사용자가 말한 쿠폰을 "
                "특정한 뒤 check_coupon_stacking_tool 판정값으로만 안내한다. 쿠폰이 특정되지 않으면 비교할 쿠폰을 되묻는다."
            ),
            "metadata": {"response_shape_key": "coupon_stacking_policy"},
        }
    if intent == "coupon_registration_policy":
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "issue_coupon_tool",
                "get_my_coupons_tool",
                "get_coupon_applicable_products_tool",
                "get_final_price_tool",
            ),
        )
    if planner_intent == "best_seller_search" or (
        best_seller_anchor
        and (
            str(sub_intent or "") == "best_seller_search"
            or code_intent == "best_seller_search"
        )
    ):
        domain = "discovery"
        intent = "best_seller_search"
        allowed_tools = _merge_tuple(allowed_tools, ("get_best_selling_products_tool",))
    if intent == "order_document_guidance":
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "transfer_to_qna_tool",
                "get_orders_of_user_tool",
                "get_order_status_tool",
                "quick_order_tool",
            ),
        )
    if intent == "delivery_delay_reservation_schedule_policy":
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "get_my_reservations_tool",
                "get_orders_of_user_tool",
                "get_order_status_tool",
                "get_store_schedule_tool",
                "transaction_store_preview_tool",
            ),
        )
    if intent == "reservation_window_policy":
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "get_my_reservations_tool",
                "get_orders_of_user_tool",
                "get_order_status_tool",
                "get_store_schedule_tool",
                "get_multi_store_schedule_tool",
                "transaction_store_preview_tool",
                "search_stores_tool",
                "get_store_list_tool",
                "quick_order_tool",
            ),
        )
    if intent == "external_tire_install_policy":
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "get_my_reservations_tool",
                "get_orders_of_user_tool",
                "get_order_status_tool",
                "get_store_schedule_tool",
                "get_multi_store_schedule_tool",
                "transaction_store_preview_tool",
                "search_stores_tool",
                "get_store_list_tool",
                "quick_order_tool",
            ),
        )
    if intent == "general_card_cancel_timing_policy":
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "get_orders_of_user_tool",
                "get_order_status_tool",
                "get_my_reservations_tool",
                "quick_order_tool",
            ),
        )
    if intent == "reservation_policy_guidance":
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            (
                "get_orders_of_user_tool",
                "get_order_status_tool",
                "get_my_reservations_tool",
                "quick_order_tool",
            ),
        )

    drift = _contract_drift(
        code_domain=code_domain,
        code_intent=code_intent,
        planner_domain=domain,
        planner_intent=planner_intent,
    )
    risk_level = _risk_level(
        domain=domain,
        intent=intent,
        required_slots=blocking_required_slots,
        tool_plan=tool_plan,
    )
    if blocking_required_slots and _is_blocking_reference(
        routing_result,
        user_text=user_text,
        intent=intent,
    ):
        risk_level = "high"
    fallback_reason = _fallback_reason(
        intent=intent,
        required_slots=blocking_required_slots,
        response_decision=response_decision,
        cross_domain_plan=cross_domain_plan,
    )
    resolved_context = build_resolved_turn_context(
        user_text=user_text,
        slots=known_slots,
    ).to_dict()

    response_decision_payload = response_decision.to_dict() if response_decision is not None else None
    if selected_store_schedule_continuation and _selected_store_schedule_response_decision_mismatch(
        response_decision_payload
    ):
        response_decision_payload = _selected_store_schedule_response_decision_payload(known_slots)
    if intent == "legal_action_guidance_denied" and response_decision_payload is None:
        response_decision_payload = {
            "response_shape": "action_confirm",
            "template": "quickReply",
            "required_slots": [],
            "forbidden_behaviors": [
                "provide_legal_action_steps",
                "explain_lawsuit_or_complaint_method",
                "give_legal_advice",
            ],
            "assistant_guidance": (
                "법적 절차, 기관, 서류, 단계, 요건은 안내하지 않고 1:1 문의 또는 고객센터 불편 접수만 안내한다."
            ),
            "metadata": {"response_shape_key": "legal_action_guidance_denied"},
        }
    if intent == "human_escalation" and response_decision_payload is None:
        response_decision_payload = {
            "response_shape": "action_confirm",
            "template": "qnaComplete",
            "required_slots": [],
            "forbidden_behaviors": [
                "overpromise_live_agent",
                "hide_official_contact",
            ],
            "assistant_guidance": "사용자가 명시적으로 1:1 문의/상담원 연결을 요청했으므로 transfer_to_qna_tool로 문의 접수 링크를 생성한다.",
            "metadata": {"response_shape_key": "human_escalation"},
        }
    if intent == "order_document_guidance" and response_decision_payload is None:
        response_decision_payload = {
            "response_shape": "summary",
            "template": "quickReply",
            "required_slots": [],
            "forbidden_behaviors": [
                "direct_email_document_send",
                "direct_qna_complete_first",
                "skip_order_history_guidance",
            ],
            "assistant_guidance": (
                "거래명세서/증빙 서류 문의는 이메일 직접 발송 불가를 먼저 설명하고 주문 내역 확인 경로를 우선 제시한다. "
                "1:1 문의는 보조 CTA로만 둔다."
            ),
            "metadata": {"response_shape_key": "order_document_guidance"},
        }
    if intent == "delivery_delay_reservation_schedule_policy" and response_decision_payload is None:
        response_decision_payload = {
            "response_shape": "summary",
            "template": "quickReply",
            "required_slots": [],
            "forbidden_behaviors": [
                "start_owned_reservation_lookup",
                "normalize_as_store_schedule_lookup",
                "claim_personal_reservation_changed",
            ],
            "assistant_guidance": (
                "배송 지연으로 예약 일정이 자동 변경되는지 묻는 질문은 일반 정책 안내로 답한다. "
                "배송 지연으로 예약 일정이 자동 변경되지는 않으며, 상품이 예약 일정에 맞춰 도착하지 않으면 "
                "매장 해피콜 등으로 안내받을 수 있다고 설명한다."
            ),
            "metadata": {"response_shape_key": "delivery_delay_reservation_schedule_policy"},
        }
    if intent in {"coupon_usage_policy", "coupon_registration_policy"} and response_decision_payload is None:
        response_decision_payload = {
            "response_shape": "summary",
            "template": "quickReply",
            "required_slots": [],
            "forbidden_behaviors": [
                "route_to_partner_coupon_policy",
                "start_owned_coupon_lookup",
                "require_product_clarification",
            ],
            "assistant_guidance": (
                "쿠폰 일반 정책 문의는 FAQ hybrid 검색을 먼저 수행하고 사용처/등록 경로를 quickReply로 요약한다. "
                "보유 쿠폰 조회나 상품별 적용 조회로 바로 전환하지 않는다."
            ),
            "metadata": {"response_shape_key": intent},
        }
    if intent in {
        "tire_manufacture_date_policy",
        "tire_quality_warranty_policy",
        "assurance_service_policy",
        "reservation_policy_guidance",
        "installation_work_policy",
        "promotion_gift_policy",
        "tire_condition_photo_policy",
        "coupon_usage_policy",
        "coupon_registration_policy",
    } and response_decision_payload is None:
        response_decision_payload = {
            "response_shape": "summary",
            "template": "quickReply",
            "required_slots": [],
            "forbidden_behaviors": [
                "transfer_to_qna_direct_first",
                "skip_policy_guidance",
            ],
            "assistant_guidance": "FAQ hybrid 검색을 먼저 수행하고 정책/조건을 quickReply로 요약한 뒤 필요 시에만 1:1 문의로 이어진다.",
            "metadata": {"response_shape_key": intent},
        }
    if planner_intent == "best_seller_search" or (
        best_seller_anchor
        and (
            str(sub_intent or "") == "best_seller_search"
            or code_intent == "best_seller_search"
        )
    ):
        domain = "discovery"
        intent = "best_seller_search"
        allowed_tools = _merge_tuple(allowed_tools, ("get_best_selling_products_tool",))
        forbidden_tools = _merge_tuple(forbidden_tools, ("get_products_recommendations_tool",))
        if _router_wins_response_decision_mismatch("best_seller_search", response_decision_payload):
            response_decision_payload = _best_seller_response_decision_payload()
    router_wins_suppressed_required_slots = bool(
        router_wins_intent
        and (router_wins_preempted_required_slots or required_slots or resolvable_required_slots or blocking_required_slots)
    )
    final_support_policy_intent = str(known_slots.get("policy_intent") or "").strip()
    if domain == "support" and intent == "support_faq" and final_support_policy_intent in _SUPPORT_FAQ_POLICY_TOOL_INTENTS:
        intent = final_support_policy_intent
        allowed_tools = _merge_tuple(allowed_tools, _SUPPORT_SAFE_AGENT_TOOLS)
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            ("search_product_tool", "get_final_price_tool", "transfer_to_qna_tool"),
        )
    if intent in {"general_cancel_fee_policy", "owned_order_cancel_fee_inquiry"} and not allowed_tools:
        allowed_tools = ("search_faq_hybrid_tool",)
        forbidden_tools = _merge_tuple(
            forbidden_tools,
            tuple(tool for tool in _ROUTER_WINS_TRANSACTION_FORBIDDEN_TOOLS if tool != "search_faq_hybrid_tool"),
        )
    if intent in {"general_cancel_fee_policy", "owned_order_cancel_fee_inquiry"}:
        required_slots = ()
        resolvable_required_slots = ()
        blocking_required_slots = ()
        blocking_required_slots_source = "transaction_policy_boundary"
        if _response_shape_key(response_decision_payload) not in {
            "general_cancel_fee_policy",
            "general_cancel_fee_policy_summary",
            "owned_order_cancel_fee_inquiry",
            "owned_order_cancel_fee_inquiry_summary",
        }:
            response_decision_payload = _router_wins_response_decision(intent)
    support_answer_contract = _support_answer_contract_owns_response(
        domain=domain,
        intent=intent,
        action_mode=action_mode,
    )
    if support_answer_contract:
        required_slots = ()
        resolvable_required_slots = ()
        blocking_required_slots = ()
        blocking_required_slots_source = "support_answer_contract"
        forbidden_tools = _merge_tuple(forbidden_tools, tuple(_SUPPORT_POLICY_PURCHASE_FORBIDDEN_TOOLS))
        if action_mode == "unspecified":
            action_mode = "support_policy_answer"
    if router_wins_intent:
        required_slots = ()
        resolvable_required_slots = ()
        blocking_required_slots = ()
        blocking_required_slots_source = "router_wins_information_contract" if router_wins_suppressed_required_slots else "none"
        if _router_wins_response_decision_mismatch(router_wins_intent, response_decision_payload):
            response_decision_payload = _router_wins_response_decision(router_wins_intent)

    allowed_tools = tuple(tool for tool in allowed_tools if tool not in forbidden_tools)

    preferred_allowed = bool(
        preferred_tool
        and (not allowed_tools or preferred_tool in allowed_tools)
        and preferred_tool not in forbidden_tools
    )
    if not preferred_allowed:
        original_preferred_tool = preferred_tool
        preferred_tool = (
            _default_preferred_tool_for_boundary(
                intent=intent,
                allowed_tools=allowed_tools,
                forbidden_tools=forbidden_tools,
            ) or ""
            if router_wins_intent or len(allowed_tools) == 1 or intent in _SUPPORT_FAQ_POLICY_TOOL_INTENTS
            else ""
        )
        if preferred_tool != original_preferred_tool:
            tool_args_patch = {}

    return TurnContract(
        domain=domain,
        intent=intent,
        sub_intent=sub_intent,
        known_slots=known_slots,
        required_slots=required_slots,
        blocking_required_slots=blocking_required_slots,
        resolvable_required_slots=resolvable_required_slots,
        allowed_tools=allowed_tools,
        forbidden_tools=forbidden_tools,
        preferred_tool=preferred_tool or None,
        tool_args_patch=tool_args_patch,
        response_decision=response_decision_payload,
        risk_level=risk_level,
        fallback_reason=fallback_reason,
        planner_intent=planner_intent,
        planner_domains=planner_domains,
        execution_plan=execution_plan,
        referred_objects=_referred_objects(routing_result),
        planner_confidence=_planner_confidence(routing_result),
        has_reference_signal=has_reference_signal,
        planner_source=_planner_source(routing_result, cross_domain_plan),
        override_applied=bool(getattr(routing_result, "override_applied", False)),
        override_reason=str(getattr(routing_result, "override_reason", "") or "") or None,
        original_router_domains=tuple(
            _domain_value(domain)
            for domain in tuple(getattr(routing_result, "original_router_domains", ()) or ())
        ),
        original_router_execution_plan=tuple(
            str(item) for item in tuple(getattr(routing_result, "original_router_execution_plan", ()) or ())
        ),
        override_blocked=bool(getattr(routing_result, "override_blocked", False)),
        blocked_override_reason=str(getattr(routing_result, "blocked_override_reason", "") or "") or None,
        contract_drift=drift,
        resolved_context=resolved_context,
        action_mode=action_mode,
        context_state=context_state,
        resume_source=resume_source,
        router_waited=router_waited,
        router_source=router_source,
        contract_source=contract_source or _planner_source(routing_result, cross_domain_plan),
        speculative_used_for_contract=speculative_used_for_contract,
        current_turn_intent=intent,
        previous_pending_intent=previous_pending_intent,
        previous_goal_type=previous_goal_type,
        resume_anchor_detected=resume_anchor_detected,
        dormant_context_reason=dormant_context_reason,
        blocking_required_slots_source=blocking_required_slots_source,
        flow_id=flow_id,
        flow_step=flow_step,
        router_wins_applied=bool(router_wins_intent),
        code_frame_intent=str(code_intent or "") or None,
        drift_resolution=(
            f"router_intent:{router_wins_intent}_kept_over_code_frame:{code_intent}"
            if router_wins_intent and code_intent and code_intent != router_wins_intent
            else "router_intent_kept"
            if router_wins_intent
            else None
        ),
        stale_context_used_for=_stale_context_usage(router_wins_intent=router_wins_intent, context_state=context_state),
        response_policy_source="router_intent" if router_wins_intent else _response_policy_source(response_decision_payload),
        contract_seed=dict(contract_seed or {}),
        context_evidence=dict(context_evidence or {}),
    )


def should_guard_required_slots(contract: TurnContract | None) -> bool:
    """Return true only when missing slots create an immediate safety risk.

    TurnContract is a final safety verifier, not the primary slot-collection
    engine. Most intent-dependent missing slots should be handled by the domain
    policy/resolver layer so normal tool execution can still resolve them.
    """

    if contract is None or not contract.blocking_required_slots:
        return False
    if _has_blocking_reference(contract):
        return True
    if contract.risk_level != "high":
        return False
    if contract.has_reference_signal and any(
        slot in {"product", "product_set", "store", "order", "coupon", "reference"}
        for slot in contract.blocking_required_slots
    ):
        return True
    if contract.domain not in _HIGH_RISK_DOMAINS:
        return False
    return str(contract.intent or "") in _HARD_REQUIRED_SLOT_GUARD_INTENTS


def align_tool_plan_to_turn_contract(tool_plan: ToolPlan | None, contract: TurnContract | None) -> ToolPlan | None:
    """Keep router-wins execution ContextVar plans inside the final contract boundary."""

    if tool_plan is None or contract is None or not contract.router_wins_applied:
        return tool_plan
    if not _should_align_router_wins_tool_plan(contract):
        return tool_plan
    allowed_tools = tuple(contract.allowed_tools or ())
    forbidden_tools = tuple(contract.forbidden_tools or ())
    preferred_tool = str(tool_plan.preferred_tool or "")
    preferred_allowed = bool(
        preferred_tool
        and (not allowed_tools or preferred_tool in allowed_tools)
        and preferred_tool not in forbidden_tools
    )
    aligned_preferred_tool = preferred_tool if preferred_allowed else _router_wins_default_preferred_tool(contract)
    metadata = {
        **dict(tool_plan.metadata or {}),
        "tool_plan_aligned_to_turn_contract": True,
        "turn_contract_intent": contract.intent,
        "router_wins_applied": True,
    }
    return ToolPlan(
        allowed_tools=allowed_tools,
        preferred_tool=aligned_preferred_tool,
        tool_args_patch=dict(tool_plan.tool_args_patch or {}),
        forbidden_tools=forbidden_tools,
        required_slots=tuple(contract.required_slots or ()),
        metadata=metadata,
    )


def _should_align_router_wins_tool_plan(contract: TurnContract) -> bool:
    intent = str(contract.intent or "")
    return intent in ROUTER_WINS_EXECUTION_BOUNDARY_INTENTS or intent in _SUPPORT_FAQ_POLICY_TOOL_INTENTS


def _router_wins_default_preferred_tool(contract: TurnContract) -> str | None:
    if str(contract.intent or "") == "store_search":
        quantity = contract.known_slots.get("ord_qty") or contract.known_slots.get("quantity")
        has_purchase_slots = bool(
            contract.known_slots.get("goods_no")
            and quantity not in (None, "", 0, "0")
            and (
                contract.known_slots.get("region")
                or contract.known_slots.get("place_query")
                or contract.known_slots.get("place")
            )
        )
        if has_purchase_slots and "transaction_store_preview_tool" in tuple(contract.allowed_tools or ()):
            return "transaction_store_preview_tool"
    return _default_preferred_tool_for_boundary(
        intent=str(contract.intent or ""),
        allowed_tools=tuple(contract.allowed_tools or ()),
        forbidden_tools=tuple(contract.forbidden_tools or ()),
    )


def _default_preferred_tool_for_boundary(
    *,
    intent: str,
    allowed_tools: tuple[str, ...],
    forbidden_tools: tuple[str, ...],
) -> str | None:
    intent = str(intent or "")
    preferred_by_intent = {
        "stock_store_search": "transaction_store_preview_tool",
        "store_search": "get_store_list_tool",
        "store_schedule": "get_store_schedule_tool",
        "open_store_search": "search_stores_complex_tool",
        "store_service_search": "search_stores_tool",
        "store_recommendation_by_vehicle_experience": "search_stores_complex_tool",
    }
    preferred = preferred_by_intent.get(intent)
    if preferred and preferred in allowed_tools and preferred not in forbidden_tools:
        return preferred
    if intent == "card_installment_lookup" and "get_card_installments_tool" in allowed_tools:
        return "get_card_installments_tool"
    if intent in _SUPPORT_FAQ_POLICY_TOOL_INTENTS and "search_faq_hybrid_tool" in allowed_tools:
        return "search_faq_hybrid_tool"
    return next((tool for tool in allowed_tools if tool not in forbidden_tools), None)


def _support_answer_contract_owns_response(*, domain: str, intent: str, action_mode: str) -> bool:
    if str(domain or "") != "support":
        return False
    normalized_intent = str(intent or "").strip()
    normalized_mode = str(action_mode or "").strip()
    if normalized_mode in _SUPPORT_ANSWER_ACTION_MODES:
        return True
    if normalized_intent in {
        "card_installment_lookup",
        "human_escalation",
        "legal_action_guidance_denied",
        "support_faq",
        "tstation_service_complaint",
        "owned_warranty_lookup",
    }:
        return True
    if normalized_intent.endswith("_policy") or normalized_intent.endswith("_guidance"):
        return True
    return False


def _support_guard_message_and_chips(
    *,
    intent: str,
    response_shape_key: str,
) -> tuple[str, list[dict[str, str]]]:
    quick_replies = [
        {"label": "1:1 문의하기", "domain": "SUPPORT"},
        {"label": "처음으로", "domain": "LEADING"},
    ]
    if intent == "legal_action_guidance_denied":
        return (
            "법적 절차나 방법은 안내하기 어렵고, 1:1 문의나 고객센터로 불편을 접수해 주세요.",
            quick_replies,
        )
    if intent == "human_escalation":
        return (
            "1:1 문의로 접수해 드릴 수 있어요. 문의할 내용을 남겨 주세요.",
            quick_replies,
        )
    if intent == "tstation_service_complaint" or response_shape_key == "support_complaint_guidance":
        return (
            "이용 중 불편을 겪으셨다면 죄송합니다. 정확한 확인을 위해 1:1 문의로 상세 내용을 남겨 주시면 "
            "확인후 빠르게 도와드릴게요.",
            quick_replies,
        )
    return (
        "현재 문의 기준으로 안내드릴게요. 필요하면 1:1 문의로 이어서 도와드릴게요.",
        quick_replies,
    )


def build_required_slot_clarification_event(contract: TurnContract) -> dict[str, Any]:
    """Build the quickReply used when a high-risk turn lacks required slots."""

    message = _clarification_text(contract.blocking_required_slots)
    quick_replies = _clarification_chips(contract.blocking_required_slots)
    return _annotate_contract_guard_event({
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_turn_contract_required_slot_guard",
        "data": {
            "assistantResponse": message,
            "quickReplies": quick_replies,
            "predictedDomains": ["TRANSACTION", "DISCOVERY"],
            "metadata": {
                "turnContract": _guard_event_contract_snapshot(contract),
                "requiredSlots": list(contract.blocking_required_slots),
            },
        },
    }, contract, reason="required_slot_guard")


def _annotate_contract_guard_event(
    event: dict[str, Any],
    contract: TurnContract,
    *,
    reason: str,
) -> dict[str, Any]:
    template = str(event.get("template") or "")
    source = str(event.get("assistant_response_source") or "code_turn_contract_guard")
    event["contract_intent"] = str(contract.intent or "")
    event["contract_gate_result"] = "blocked"
    event["contract_gate_reason"] = reason
    event["emitted_template"] = template
    event["direct_source"] = source
    event_data = event.get("data")
    if isinstance(event_data, dict):
        metadata = event_data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            event_data["metadata"] = metadata
        metadata["contract_intent"] = str(contract.intent or "")
        metadata["contract_gate_result"] = "blocked"
        metadata["contract_gate_reason"] = reason
        metadata["emitted_template"] = template
        metadata["direct_source"] = source
    return event


def _build_owned_record_lookup_guard_event(contract: TurnContract) -> dict[str, Any] | None:
    intent = str(contract.intent or "")
    if not _is_owned_record_lookup_intent(intent):
        return None
    response_shape_key = intent
    response_decision = contract.response_decision or {}
    if isinstance(response_decision, Mapping):
        metadata = response_decision.get("metadata")
        if isinstance(metadata, Mapping):
            response_shape_key = str(metadata.get("response_shape_key") or response_shape_key)
    if intent in {"reservation_status_lookup", "reservation_store_info_lookup"}:
        message = "예약 내역을 기준으로 다시 확인해 드릴게요."
        quick_replies = [
            {"label": "내 예약 조회", "domain": "TRANSACTION"},
            {"label": "주문 내역 보기", "url": CTAUrls.ORDER_HISTORY, "domain": "TRANSACTION"},
        ]
    elif intent in {"order_cancel_status_lookup", "order_arrival_status_lookup"}:
        message = "주문 내역을 기준으로 다시 확인해 드릴게요."
        quick_replies = [
            {"label": "주문 내역 보기", "url": CTAUrls.ORDER_HISTORY, "domain": "TRANSACTION"},
            {"label": "내 예약 조회", "domain": "TRANSACTION"},
        ]
    else:
        message = "보유 내역을 기준으로 다시 확인해 드릴게요."
        quick_replies = [
            {"label": "내역 다시 조회", "domain": "TRANSACTION"},
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ]
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_turn_contract_owned_record_guard",
        "data": {
            "assistantResponse": message,
            "quickReplies": quick_replies,
            "predictedDomains": ["TRANSACTION"],
            "metadata": {
                "turnContract": _guard_event_contract_snapshot(contract),
                "responseShapeKey": response_shape_key,
                "response_shape_key": response_shape_key,
                "assistant_response_source": "code_turn_contract_owned_record_guard",
                "contract_intent": intent,
            },
        },
    }

def build_response_policy_guard_event(contract: TurnContract) -> dict[str, Any]:
    """Build a safe fallback when a template violates response policy, not slots."""

    response_decision = contract.response_decision or {}
    forbidden = response_decision.get("forbidden_behaviors") if isinstance(response_decision, Mapping) else ()
    forbidden_set = {str(item) for item in forbidden} if isinstance(forbidden, list | tuple) else set()
    if str(contract.domain or "") == "transaction" and str(contract.intent or "") == "general_cancel_fee_policy":
        user_query = str(contract.known_slots.get("region") or contract.known_slots.get("user_query") or "")
        event = build_general_cancel_fee_policy_event(user_query)
        event["assistant_response_source"] = "code_turn_contract_general_cancel_fee_policy_guard"
        data = event.get("data")
        if isinstance(data, dict):
            metadata = data.get("metadata")
            if isinstance(metadata, dict):
                metadata["assistant_response_source"] = "code_turn_contract_general_cancel_fee_policy_guard"
        return _annotate_contract_guard_event(event, contract, reason="response_policy_guard")
    if _support_answer_contract_owns_response(
        domain=str(contract.domain or ""),
        intent=str(contract.intent or ""),
        action_mode=str(contract.action_mode or ""),
    ):
        intent = str(contract.intent or "")
        response_shape_key = ""
        if isinstance(response_decision, Mapping):
            metadata = response_decision.get("metadata")
            if isinstance(metadata, Mapping):
                response_shape_key = str(metadata.get("response_shape_key") or "")
        message, quick_replies = _support_guard_message_and_chips(
            intent=intent,
            response_shape_key=response_shape_key,
        )
        return _annotate_contract_guard_event({
            "type": "data",
            "template": "quickReply",
            "source_domain": "support",
            "assistant_response_source": "code_turn_contract_support_response_guard",
            "data": {
                "assistantResponse": message,
                "quickReplies": quick_replies,
                "predictedDomains": ["SUPPORT"],
                "metadata": {
                    "turnContract": _guard_event_contract_snapshot(contract),
                    "forbiddenBehaviors": sorted(forbidden_set),
                    "responseShapeKey": response_shape_key or intent,
                    "response_shape_key": response_shape_key or intent,
                    "assistant_response_source": "code_turn_contract_support_response_guard",
                    "contract_intent": intent,
                },
            },
        }, contract, reason="response_policy_guard")
    owned_record_event = _build_owned_record_lookup_guard_event(contract)
    if owned_record_event is not None:
        return _annotate_contract_guard_event(owned_record_event, contract, reason="response_policy_guard")
    purchase_flow_event = build_purchase_flow_fallback_event(
        intent=str(contract.intent or ""),
        known_slots=contract.known_slots,
    )
    if purchase_flow_event is not None:
        return _annotate_contract_guard_event(purchase_flow_event, contract, reason="response_policy_guard")
    preorder_event = build_preorder_event(contract, contract.known_slots)
    if preorder_event is not None:
        return _annotate_contract_guard_event(preorder_event, contract, reason="response_policy_guard")
    unknown_store_service_event = _build_unknown_store_service_guard_event(contract)
    if unknown_store_service_event is not None:
        return _annotate_contract_guard_event(unknown_store_service_event, contract, reason="response_policy_guard")
    tool_error_behaviors = {
        "assert_price_without_tool_result",
        "assert_coupon_without_tool_result",
        "order_complete_on_tool_error",
        "datepick_on_tool_error",
    }
    if not (forbidden_set & tool_error_behaviors):
        missing_slot_event = _build_missing_slot_action_prompt_event(contract)
        if missing_slot_event is not None:
            return _annotate_contract_guard_event(missing_slot_event, contract, reason="response_policy_guard")

    if _is_discovery_first_leg_transaction_contract(contract):
        intent = str(contract.intent or "")
        known_slots = contract.known_slots or {}
        pending_intent = str(known_slots.get("pending_intent") or "").strip()
        goal_type = str(known_slots.get("goal_type") or "").strip()
        has_transaction_action = contract.action_mode in {
            "unspecified",
            "purchase_continuation",
            "stock_check",
            "reservation_lookup",
            "booking_continuation",
        }
        if not has_transaction_action:
            message = "요청하신 내용을 기준으로 다시 확인해 주세요."
            quick_replies = [
                {"label": "상품 다시 찾기", "domain": "DISCOVERY"},
                {"label": "처음부터 다시", "domain": "LEADING"},
            ]
        elif pending_intent == "order" or goal_type == "place_order":
            if not (known_slots.get("goods_no") or known_slots.get("tire_size")):
                message = "구매를 진행하려면 먼저 타이어 규격을 확인해야 해요. 장착할 규격을 선택해 주세요."
                quick_replies = [
                    {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
                    {"label": "구매 진행", "domain": "TRANSACTION"},
                    {"label": "상품 다시 찾기", "domain": "DISCOVERY"},
                ]
            elif not (known_slots.get("ord_qty") or known_slots.get("quantity")):
                message = "구매를 진행하려면 수량이 필요해요. 구매할 타이어 수량을 알려주세요."
                quick_replies = _quantity_selection_quick_replies()
            elif not (
                known_slots.get("shop_id")
                or known_slots.get("shop_name")
                or known_slots.get("store_name")
                or known_slots.get("store_nm")
            ):
                message = "구매를 진행하려면 장착 매장이 필요해요. 구매할 매장을 선택해 주세요."
                quick_replies = [
                    {"label": "매장 찾기", "domain": "TRANSACTION"},
                    {"label": "내 주변 매장", "domain": "TRANSACTION"},
                    {"label": "상품 다시 찾기", "domain": "DISCOVERY"},
                ]
            else:
                message = "해당 매장의 예약 가능 시간을 확인하지 못했어요. 다른 날짜나 매장을 확인해드릴게요."
                quick_replies = [
                    {"label": "다른 날짜 확인", "domain": "TRANSACTION"},
                    {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
                    {"label": "상품 다시 찾기", "domain": "DISCOVERY"},
                ]
        elif pending_intent == "stock" or goal_type == "store_with_stock":
            message = "재고를 확인하려면 먼저 타이어 규격을 확인해야 해요. 장착할 규격을 선택해 주세요."
            quick_replies = [
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
                {"label": "재고 확인", "domain": "TRANSACTION"},
                {"label": "상품 다시 찾기", "domain": "DISCOVERY"},
            ]
        elif pending_intent == "price" or goal_type in {
            "price_inquiry",
            "coupon_discount_amount",
            "product_coupon_discount_amount",
        }:
            message = "가격을 확인하려면 먼저 타이어 규격을 확인해야 해요. 확인할 규격을 선택해 주세요."
            quick_replies = [
                {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
                {"label": "가격 확인", "domain": "TRANSACTION"},
                {"label": "상품 다시 찾기", "domain": "DISCOVERY"},
            ]
        elif intent == "stock_store_search":
            message = "재고를 확인하려면 어떤 상품 기준인지 먼저 정해야 해요. 확인할 상품명을 알려주시거나 상품을 선택해 주세요."
            quick_replies = [
                {"label": "상품명 입력", "domain": "DISCOVERY"},
                {"label": "재고 확인", "domain": "TRANSACTION"},
                {"label": "상품 추천", "domain": "DISCOVERY"},
            ]
        elif intent == "quick_order_reservation":
            message = "구매를 이어가려면 어떤 상품인지 먼저 정해야 해요. 확인할 상품명을 알려주시거나 상품을 선택해 주세요."
            quick_replies = [
                {"label": "상품명 입력", "domain": "DISCOVERY"},
                {"label": "구매 진행", "domain": "TRANSACTION"},
                {"label": "상품 추천", "domain": "DISCOVERY"},
            ]
        elif intent == "quick_order_execute":
            message = "주문을 이어가려면 상품, 매장, 예약 정보가 모두 확인되어야 해요. 필요한 정보를 다시 확인해 주세요."
            quick_replies = [
                {"label": "상품 다시 선택", "domain": "DISCOVERY"},
                {"label": "매장 다시 선택", "domain": "TRANSACTION"},
                {"label": "예약 시간 다시 선택", "domain": "TRANSACTION"},
            ]
        else:
            message = "가격을 확인하려면 어떤 상품 기준인지 먼저 정해야 해요. 확인할 상품명을 알려주시거나 상품을 선택해 주세요."
            quick_replies = [
                {"label": "상품명 입력", "domain": "DISCOVERY"},
                {"label": "가격 확인", "domain": "TRANSACTION"},
                {"label": "상품 추천", "domain": "DISCOVERY"},
            ]
    elif (
        "datepick_for_unavailable_stock" in forbidden_set
        or "datepick_for_pure_inventory_flow" in forbidden_set
        or "preorder_for_pure_inventory_flow" in forbidden_set
    ):
        message = "요청하신 조건으로 바로 예약 가능한 재고를 확인하지 못했어요. 다른 매장이나 조건으로 다시 확인해드릴게요."
        quick_replies = [
            {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
            {"label": "다른 날짜 확인", "domain": "TRANSACTION"},
            {"label": "다른 상품 추천", "domain": "DISCOVERY"},
        ]
    elif "assert_price_without_tool_result" in forbidden_set:
        message = "가격 정보를 확인하지 못해 금액을 단정할 수 없어요. 상품 조건을 다시 확인한 뒤 조회해드릴게요."
        quick_replies = [
            {"label": "가격 다시 확인", "domain": "TRANSACTION"},
            {"label": "상품 다시 선택", "domain": "DISCOVERY"},
        ]
    elif "assert_coupon_without_tool_result" in forbidden_set:
        message = "쿠폰 정보를 확인하지 못해 적용 여부를 단정할 수 없어요. 보유 쿠폰이나 적용 대상을 다시 확인해드릴게요."
        quick_replies = [
            {"label": "내 쿠폰 확인", "domain": "TRANSACTION"},
            {"label": "적용 상품 확인", "domain": "TRANSACTION"},
        ]
    elif "order_complete_on_tool_error" in forbidden_set:
        message = "주문서 생성 결과를 확인하지 못했어요. 주문 완료로 안내하지 않고 다시 확인해드릴게요."
        quick_replies = [
            {"label": "주문 다시 확인", "domain": "TRANSACTION"},
            {"label": "장바구니 확인", "domain": "TRANSACTION"},
        ]
    elif "datepick_on_tool_error" in forbidden_set:
        message = "예약 가능 시간을 확인하지 못했어요. 매장이나 날짜 조건을 다시 확인해드릴게요."
        quick_replies = [
            {"label": "다른 날짜 확인", "domain": "TRANSACTION"},
            {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
        ]
    else:
        missing_slots = _missing_slots_for_action_prompt(contract) or ("product",)
        missing_summary = _missing_slot_summary_text(missing_slots)
        message = (
            "현재 확인된 정보만으로 바로 진행하기 어려워요. "
            f"부족한 정보는 {missing_summary}입니다. 필요한 정보를 먼저 확인한 뒤 이어서 도와드릴게요."
        )
        quick_replies = _clarification_chips(missing_slots)

    return _annotate_contract_guard_event({
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_turn_contract_response_policy_guard",
        "data": {
            "assistantResponse": message,
            "quickReplies": quick_replies,
            "predictedDomains": ["TRANSACTION", "DISCOVERY"],
            "metadata": {
                "turnContract": _guard_event_contract_snapshot(contract),
                "forbiddenBehaviors": sorted(forbidden_set),
                "missingSlots": list(_missing_slots_for_action_prompt(contract)),
            },
        },
    }, contract, reason="response_policy_guard")


def _build_unknown_store_service_guard_event(contract: TurnContract) -> dict[str, Any] | None:
    if str(contract.intent or "") != "unsupported_or_unmapped_store_service_policy":
        return None
    known_slots = contract.known_slots or {}
    service_name = str(known_slots.get("service_name") or "해당 서비스").strip()
    store_name = str(known_slots.get("store_name") or known_slots.get("shop_name") or "").strip()
    region = str(known_slots.get("region") or known_slots.get("place_query") or "").strip()
    if store_name:
        assistant_response = (
            "현재 챗봇에서는 해당 서비스의 매장별 예약 가능 여부를 바로 확인할 수 없어요.\n\n"
            f"{store_name}에서 {service_name} 운영 여부는 매장별 기준이 달라서 방문 예정 매장에 직접 문의해 주세요."
        )
        quick_replies = [
            {"label": "매장 전화번호 확인", "domain": "TRANSACTION"},
            {"label": "매장 상세보기", "domain": "TRANSACTION"},
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ]
    elif region:
        assistant_response = (
            "현재 챗봇에서는 해당 서비스의 매장별 예약 가능 여부를 바로 확인할 수 없어요.\n\n"
            f"{region} 기준으로 방문 예정 매장명을 알려주시면 기본 매장 정보와 함께 안내해드릴게요."
        )
        quick_replies = [
            {"label": "매장명 입력", "domain": "TRANSACTION"},
            {"label": "매장 찾기", "domain": "TRANSACTION"},
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ]
    else:
        assistant_response = (
            "현재 챗봇에서는 해당 서비스의 매장별 예약 가능 여부를 바로 확인할 수 없어요.\n\n"
            "세차나 튜닝처럼 매장별 운영 서비스는 지역이나 방문 예정 매장을 알려주시면 확인 방법을 안내해드릴게요."
        )
        quick_replies = [
            {"label": "매장명 입력", "domain": "TRANSACTION"},
            {"label": "지역 입력", "domain": "TRANSACTION"},
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ]
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_unknown_store_service_policy",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": quick_replies,
            "predictedDomains": ["TRANSACTION", "SUPPORT"],
            "metadata": {
                "response_shape_key": "unsupported_or_unmapped_store_service_policy",
                "assistant_response_source": "code_unknown_store_service_policy",
                "contract_intent": "unsupported_or_unmapped_store_service_policy",
                "service_name": service_name,
                "store_name": store_name,
                "region": region,
            },
        },
    }


def _build_missing_slot_action_prompt_event(contract: TurnContract) -> dict[str, Any] | None:
    if contract.action_mode not in {
        "unspecified",
        "purchase_continuation",
        "stock_check",
        "reservation_lookup",
        "booking_continuation",
    }:
        return None
    missing_slots = _missing_slots_for_action_prompt(contract)
    if not missing_slots:
        return None
    resolved_slots = _resolved_context_slots(contract)
    is_order = _is_order_missing_slot_context(contract)

    if _has_missing_slot(missing_slots, "store", "location") and _has_product_size_quantity(resolved_slots):
        event = _build_missing_store_action_prompt_event(contract, resolved_slots, is_order=is_order)
    elif _has_missing_slot(missing_slots, "ord_qty", "quantity") and _has_product_and_size(resolved_slots):
        event = _build_missing_quantity_action_prompt_event(contract, resolved_slots, is_order=is_order)
    elif _has_missing_slot(missing_slots, "tire_size", "size") and _has_product_context(resolved_slots):
        event = _build_missing_tire_size_action_prompt_event(contract, resolved_slots, is_order=is_order)
    elif _has_missing_slot(missing_slots, "goods_no", "product", "product_name"):
        event = _build_missing_product_action_prompt_event(contract, resolved_slots, is_order=is_order)
    elif _has_missing_slot(missing_slots, "store", "location"):
        event = _build_missing_store_action_prompt_event(contract, resolved_slots, is_order=is_order)
    elif _has_missing_slot(missing_slots, "ord_qty", "quantity"):
        event = _build_missing_quantity_action_prompt_event(contract, resolved_slots, is_order=is_order)
    elif _has_missing_slot(missing_slots, "tire_size", "size"):
        event = _build_missing_tire_size_action_prompt_event(contract, resolved_slots, is_order=is_order)
    else:
        return None
    return event


def _missing_slots_for_action_prompt(contract: TurnContract) -> tuple[str, ...]:
    response_decision = contract.response_decision or {}
    metadata = response_decision.get("metadata") if isinstance(response_decision, Mapping) else None
    metadata_missing = metadata.get("missing_slots") if isinstance(metadata, Mapping) else ()
    response_required = response_decision.get("required_slots") if isinstance(response_decision, Mapping) else ()
    return _dedupe_slots(
        contract.blocking_required_slots,
        metadata_missing if isinstance(metadata_missing, list | tuple) else (),
        response_required if isinstance(response_required, list | tuple) else (),
        contract.required_slots,
    )


def _dedupe_slots(*slot_groups: Any) -> tuple[str, ...]:
    slots: list[str] = []
    for group in slot_groups:
        if isinstance(group, str):
            candidates = (group,)
        elif isinstance(group, list | tuple):
            candidates = group
        else:
            continue
        for slot in candidates:
            normalized = _canonical_missing_slot(str(slot or "").strip())
            if normalized and normalized not in slots:
                slots.append(normalized)
    return tuple(slots)


def _canonical_missing_slot(slot: str) -> str:
    if slot in {"location", "shop", "shop_id", "shop_name", "store_name", "store_nm"}:
        return "store"
    if slot in {"quantity"}:
        return "ord_qty"
    if slot in {"size"}:
        return "tire_size"
    if slot in {"goods_no", "product_name", "goods", "item"}:
        return "product"
    return slot


def _has_missing_slot(slots: tuple[str, ...], *candidates: str) -> bool:
    canonical = {_canonical_missing_slot(candidate) for candidate in candidates}
    return any(slot in canonical for slot in slots)


def _is_order_missing_slot_context(contract: TurnContract) -> bool:
    known_slots = contract.known_slots or {}
    return (
        contract.action_mode in {"purchase_continuation", "unspecified"}
        and (
            str(contract.intent or "") in {"quick_order_reservation", "quick_order_execute"}
            or str(known_slots.get("pending_intent") or "").strip() == "order"
            or str(known_slots.get("goal_type") or "").strip() == "place_order"
        )
    )


def _resolved_context_slots(contract: TurnContract) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    resolved_context = contract.resolved_context or {}
    for group in ("product", "size", "quantity", "store", "booking"):
        values = resolved_context.get(group)
        if not isinstance(values, Mapping):
            continue
        for key, payload in values.items():
            if not isinstance(payload, Mapping):
                continue
            value = payload.get("value")
            if value not in (None, "", [], {}):
                slots[str(key)] = value
    if not slots:
        return dict(contract.known_slots or {})
    for key in ("pending_intent", "goal_type"):
        value = (contract.known_slots or {}).get(key)
        if value not in (None, ""):
            slots[key] = value
    return slots


def _has_product_context(known_slots: Mapping[str, Any]) -> bool:
    return bool(
        known_slots.get("goods_no")
        or _product_name(known_slots)
    )


def _has_product_and_size(known_slots: Mapping[str, Any]) -> bool:
    return _has_product_context(known_slots) and bool(known_slots.get("tire_size"))


def _has_product_size_quantity(known_slots: Mapping[str, Any]) -> bool:
    return _has_product_and_size(known_slots) and bool(known_slots.get("ord_qty") or known_slots.get("quantity"))


def _quantity_selection_quick_replies() -> list[dict[str, str]]:
    return [
        {"label": "1개", "domain": "TRANSACTION"},
        {"label": "2개", "domain": "TRANSACTION"},
        {"label": "3개", "domain": "TRANSACTION"},
        {"label": "4개", "domain": "TRANSACTION"},
    ]


def _build_missing_store_action_prompt_event(
    contract: TurnContract,
    known_slots: Mapping[str, Any],
    *,
    is_order: bool,
) -> dict[str, Any]:
    product_label = _order_product_label(known_slots)
    quantity = _slot_text(known_slots, "ord_qty", "quantity")
    if is_order and product_label and quantity:
        message = f"{product_label} {quantity}개 구매를 진행하려면 장착 매장이 필요해요. 어느 지역이나 매장에서 확인할까요?"
    elif is_order and product_label:
        message = f"{product_label} 구매를 진행하려면 장착 매장이 필요해요. 어느 지역이나 매장에서 확인할까요?"
    elif not is_order and product_label:
        message = f"{product_label} 기준으로 확인하려면 지역이나 매장이 필요해요. 어느 지역이나 매장에서 확인할까요?"
    elif not is_order:
        message = "확인하려면 지역이나 매장이 필요해요. 어느 지역이나 매장에서 확인할까요?"
    else:
        message = "구매를 진행하려면 장착 매장이 필요해요. 어느 지역이나 매장에서 확인할까요?"
    return _missing_slot_quickreply_event(
        contract,
        message=message,
        quick_replies=[
            {"label": "내 주변 매장 찾기", "domain": "TRANSACTION"},
            {"label": "단골매장 보기", "domain": "TRANSACTION"},
            {"label": "지역/매장 입력", "domain": "TRANSACTION"},
        ],
        missing_slot="store",
    )


def _build_missing_quantity_action_prompt_event(
    contract: TurnContract,
    known_slots: Mapping[str, Any],
    *,
    is_order: bool,
) -> dict[str, Any]:
    product_label = _order_product_label(known_slots)
    if is_order and product_label:
        message = f"{product_label} 구매를 진행하려면 수량이 필요해요. 구매할 타이어 수량을 알려주세요."
    elif not is_order and product_label:
        message = f"{product_label} 기준으로 확인하려면 수량이 필요해요. 확인할 타이어 수량을 알려주세요."
    elif not is_order:
        message = "확인하려면 수량이 필요해요. 확인할 타이어 수량을 알려주세요."
    else:
        message = "구매를 진행하려면 수량이 필요해요. 구매할 타이어 수량을 알려주세요."
    return _missing_slot_quickreply_event(
        contract,
        message=message,
        quick_replies=_quantity_selection_quick_replies(),
        missing_slot="quantity",
    )


def _build_missing_tire_size_action_prompt_event(
    contract: TurnContract,
    known_slots: Mapping[str, Any],
    *,
    is_order: bool,
) -> dict[str, Any]:
    product_name = _product_name(known_slots)
    if is_order and product_name:
        message = f"{product_name} 구매를 진행하려면 타이어 사이즈가 필요해요. 장착할 규격을 선택하거나 입력해 주세요."
    elif not is_order and product_name:
        message = f"{product_name} 기준으로 확인하려면 타이어 사이즈가 필요해요. 확인할 규격을 선택하거나 입력해 주세요."
    elif not is_order:
        message = "확인하려면 타이어 규격이 필요해요. 확인할 규격을 선택하거나 입력해 주세요."
    else:
        message = "구매를 진행하려면 먼저 타이어 규격을 확인해야 해요. 장착할 규격을 선택하거나 입력해 주세요."
    return _missing_slot_quickreply_event(
        contract,
        message=message,
        quick_replies=[
            {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
            {"label": "내 차량 보기", "domain": "DISCOVERY"},
            {"label": "상품 다시 찾기", "domain": "DISCOVERY"},
        ],
        missing_slot="tire_size",
    )


def _build_missing_product_action_prompt_event(
    contract: TurnContract,
    known_slots: Mapping[str, Any],
    *,
    is_order: bool,
) -> dict[str, Any]:
    if is_order:
        message = "구매를 이어가려면 어떤 상품인지 먼저 정해야 해요. 확인할 상품명을 알려주시거나 상품을 선택해 주세요."
    else:
        message = "진행하려면 어떤 상품 기준인지 먼저 정해야 해요. 확인할 상품명을 알려주시거나 상품을 선택해 주세요."
    return _missing_slot_quickreply_event(
        contract,
        message=message,
        quick_replies=[
            {"label": "상품명 입력", "domain": "DISCOVERY"},
            {"label": "상품 추천", "domain": "DISCOVERY"},
            {"label": "처음부터 다시", "domain": "LEADING"},
        ],
        missing_slot="product",
    )


def _missing_slot_quickreply_event(
    contract: TurnContract,
    *,
    message: str,
    quick_replies: list[dict[str, str]],
    missing_slot: str,
) -> dict[str, Any]:
    pending_order_context = _pending_order_context_from_slots(_resolved_context_slots(contract))
    enriched_quick_replies: list[dict[str, Any]] = []
    for chip in quick_replies:
        enriched = dict(chip)
        if missing_slot == "store":
            label = str(enriched.get("label") or "").strip()
            if "지역" in label:
                enriched["actionId"] = "enter_region"
                enriched["cta_action"] = "select_purchase_region"
            elif "매장" in label:
                enriched["cta_action"] = "show_purchase_region_stores"
            enriched["ctaContext"] = dict(pending_order_context)
        enriched_quick_replies.append(enriched)
    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_turn_contract_missing_slot_prompt",
        "data": {
            "assistantResponse": message,
            "quickReplies": enriched_quick_replies,
            "predictedDomains": ["TRANSACTION", "DISCOVERY"],
            "metadata": {
                "turnContract": _guard_event_contract_snapshot(contract),
                "missingSlot": missing_slot,
                "missingSlots": list(_missing_slots_for_action_prompt(contract)),
                "pendingOrderContext": pending_order_context,
            },
        },
    }


def _pending_order_context_from_slots(known_slots: Mapping[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for source_key, target_key in (
        ("goods_no", "goods_no"),
        ("goods_no", "goodsNo"),
        ("product_name", "product_name"),
        ("tire_model", "product_name"),
        ("pending_product_name", "product_name"),
        ("tire_size", "tire_size"),
        ("tire_size", "tireSize"),
        ("ord_qty", "ord_qty"),
        ("ord_qty", "ordQty"),
        ("quantity", "ord_qty"),
        ("stock_check_mode", "stock_check_mode"),
        ("stock_check_mode", "stockCheckMode"),
        ("pending_intent", "pending_intent"),
        ("pending_intent", "pendingIntent"),
        ("goal_type", "goal_type"),
        ("goal_type", "goalType"),
        ("pending_step", "pending_step"),
        ("pending_step", "pendingStep"),
        ("awaiting_store_region", "awaiting_store_region"),
        ("awaiting_store_region", "awaitingStoreRegion"),
    ):
        value = known_slots.get(source_key)
        if value not in (None, "") and target_key not in context:
            context[target_key] = value
    context.setdefault("pending_intent", "order")
    context.setdefault("goal_type", "place_order")
    return context


def _order_product_label(known_slots: Mapping[str, Any]) -> str:
    product_name = _product_name(known_slots)
    tire_size = _slot_text(known_slots, "tire_size")
    if product_name and tire_size:
        return f"{product_name} {tire_size}"
    return product_name or tire_size


def _product_name(known_slots: Mapping[str, Any]) -> str:
    return _slot_text(
        known_slots,
        "product_name",
        "tire_model",
        "pending_product_name",
        "goods_nm",
        "goods_name",
    )


def _slot_text(known_slots: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = known_slots.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def violates_response_template_contract(event: Mapping[str, Any], contract: TurnContract | None) -> bool:
    """Return true only for hard template violations that must be replaced before emit."""

    if contract is None:
        return False
    template = str(event.get("template") or "")
    if should_guard_required_slots(contract) and template in _REQUIRED_SLOT_BLOCK_TEMPLATES:
        return True
    if _action_mode_contract_violation(event=event, contract=contract) is not None:
        return True
    if _order_complete_template_missing_execution_tool(event=event, contract=contract):
        return True
    if _flow_step_template_violation(template=template, contract=contract):
        return True
    if _is_discovery_product_template_compatible(event, contract):
        return False
    if _is_unsupported_discovery_product_template_without_current_source(event, contract):
        return True
    response_decision = contract.response_decision or {}
    forbidden_behaviors = response_decision.get("forbidden_behaviors") if isinstance(response_decision, Mapping) else ()
    if not isinstance(forbidden_behaviors, list | tuple):
        return False
    return any(
        template in _FORBIDDEN_BEHAVIOR_TEMPLATE_BLOCKS.get(str(behavior), ())
        for behavior in _effective_forbidden_behaviors(event, contract, forbidden_behaviors)
    )


def _order_complete_template_missing_execution_tool(*, event: Mapping[str, Any], contract: TurnContract) -> bool:
    if str(event.get("template") or "") != "orderComplete":
        return False
    is_execute_contract = str(contract.intent or "") == "quick_order_execute"
    is_execute_planner_drift = (
        str(contract.planner_intent or "") == "quick_order_execute"
        and str(contract.intent or "") == "quick_order_reservation"
        and _has_quick_order_execute_slots(contract.known_slots)
    )
    if not (is_execute_contract or is_execute_planner_drift):
        return False
    called_tools = {str(tool) for tool in tuple(event.get("called_tools") or ()) if str(tool).strip()}
    return "quick_order_tool" not in called_tools

def _flow_step_template_violation(*, template: str, contract: TurnContract) -> bool:
    if not template:
        return False
    intent = str(contract.intent or "")
    flow_step = str(contract.flow_step or "")
    if intent in {"quick_order_reservation", "quick_order_reservation_continue"}:
        if flow_step in {"ask_size", "ask_quantity", "ask_store"}:
            return template in {"location", "datepick", "preOrder", "orderComplete"}
        if flow_step in {"show_store_candidates", "resolve_store"}:
            return template in {"datepick", "preOrder", "orderComplete"}
        if flow_step in {"show_schedule", "resolve_schedule"}:
            return template in {"preOrder", "orderComplete"}
        if flow_step == "resolve_price":
            return template in {"preOrder", "orderComplete"}
        if flow_step == "build_preorder":
            return template in {"datepick", "orderComplete"}
    if intent == "quick_order_execute" and flow_step == "execute_order":
        return template in {"datepick", "preOrder"}
    if intent in {
        "reservation_window_policy",
        "delivery_delay_reservation_schedule_policy",
        "general_cancel_fee_policy",
    }:
        return template in {"location", "datepick", "preOrder", "orderComplete"}
    return False


def _discovery_product_payload_has_items(event: Mapping[str, Any]) -> bool:
    data = event.get("data")
    if not isinstance(data, Mapping):
        return False
    products = data.get("products")
    if not isinstance(products, list):
        return False
    return any(isinstance(product, Mapping) for product in products)


def _is_discovery_product_template_compatible(
    event: Mapping[str, Any],
    contract: TurnContract | None,
) -> bool:
    if contract is None:
        return False
    if str(contract.domain or "").lower() != "discovery":
        return False
    if str(event.get("template") or "") != "product":
        return False
    if str(event.get("source_domain") or "").lower() != "discovery":
        return False
    called_tools = {str(tool) for tool in tuple(event.get("called_tools") or ()) if str(tool).strip()}
    if not called_tools or not (called_tools & _DISCOVERY_PRODUCT_SOURCE_TOOLS):
        return False
    forbidden_tools = {str(tool) for tool in tuple(contract.forbidden_tools or ()) if str(tool).strip()}
    if called_tools & forbidden_tools:
        return False
    if not _discovery_product_payload_has_items(event):
        return False
    return True


def _effective_forbidden_behaviors(
    event: Mapping[str, Any],
    contract: TurnContract,
    forbidden_behaviors: list[Any] | tuple[Any, ...],
) -> tuple[str, ...]:
    behaviors = tuple(str(behavior) for behavior in forbidden_behaviors)
    if _is_sized_discovery_product_source_event(event):
        behaviors = tuple(
            behavior
            for behavior in behaviors
            if behavior not in {"product_card_without_size", "price_without_size"}
        )
    if _is_logistics_schedule_datepick_event(event):
        return tuple(
            behavior
            for behavior in behaviors
            if behavior not in {"datepick_for_unavailable_stock", "datepick_for_pure_inventory_flow"}
        )
    if _is_selected_store_schedule_continuation_contract(contract):
        return tuple(
            behavior
            for behavior in behaviors
            if behavior not in {"datepick_before_store_selection", "preorder"}
        )
    if not _is_purchase_bound_preview_event(event, contract):
        return behaviors
    return tuple(
        behavior
        for behavior in behaviors
        if behavior not in {"datepick_for_pure_inventory_flow", "preorder_for_pure_inventory_flow"}
    )


def _is_sized_discovery_product_source_event(event: Mapping[str, Any]) -> bool:
    if str(event.get("template") or "") != "product":
        return False
    if str(event.get("source_domain") or "").lower() != "discovery":
        return False
    called_tools = {str(tool) for tool in tuple(event.get("called_tools") or ()) if str(tool).strip()}
    if not called_tools & _DISCOVERY_PRODUCT_SOURCE_TOOLS:
        return False
    data = event.get("data")
    if not isinstance(data, Mapping):
        return False
    products = data.get("products")
    if not isinstance(products, list):
        return False
    for product in products:
        if not isinstance(product, Mapping):
            continue
        tire_size = (
            product.get("titleTires")
            or product.get("tireSize")
            or product.get("tire_size")
            or product.get("tire_size_1")
        )
        if str(tire_size or "").strip():
            return True
    return False


def _is_logistics_schedule_datepick_event(event: Mapping[str, Any]) -> bool:
    if str(event.get("template") or "") != "datepick":
        return False
    called_tools = {
        str(tool)
        for tool in tuple(event.get("called_tools") or ())
        if str(tool).strip()
    }
    if "get_store_schedule_tool" not in called_tools:
        return False
    data = event.get("data")
    metadata = data.get("metadata") if isinstance(data, Mapping) else None
    if not isinstance(metadata, Mapping):
        return False
    schedule_mode = str(
        metadata.get("scheduleMode")
        or metadata.get("schedule_mode")
        or metadata.get("inventoryMode")
        or metadata.get("inventory_mode")
        or ""
    ).strip().lower()
    dates = data.get("dates") if isinstance(data, Mapping) else None
    return schedule_mode == "logistics_only" and (dates is None or (isinstance(dates, list) and bool(dates)))


def _is_purchase_bound_preview_event(event: Mapping[str, Any], contract: TurnContract | None) -> bool:
    if contract is None:
        return False
    template = str(event.get("template") or "")
    if template not in {"datepick", "preOrder"}:
        return False
    known_slots = contract.known_slots or {}
    pending_intent = str(known_slots.get("pending_intent") or "").strip()
    goal_type = str(known_slots.get("goal_type") or "").strip()
    intent = str(contract.intent or "")
    if pending_intent != "order" and goal_type != "place_order" and intent not in {
        "quick_order_reservation",
        "quick_order_execute",
    }:
        return False
    if not known_slots.get("goods_no"):
        return False
    if not (known_slots.get("ord_qty") or known_slots.get("quantity")):
        return False
    if not (
        known_slots.get("shop_id")
        or known_slots.get("shop_name")
        or known_slots.get("store_name")
        or known_slots.get("store_nm")
    ):
        return False
    called_tools = {
        str(tool)
        for tool in tuple(event.get("called_tools") or ())
        if str(tool).strip()
    }
    data = event.get("data")
    metadata = data.get("metadata") if isinstance(data, Mapping) else None
    source_tool = str(metadata.get("sourceTool") or metadata.get("source_tool") or "") if isinstance(metadata, Mapping) else ""
    return "transaction_store_preview_tool" in called_tools or source_tool == "transaction_store_preview_tool"


def _selected_store_schedule_continuation_matches(
    *,
    intent: str,
    known_slots: Mapping[str, Any],
    resume_source: str,
) -> bool:
    normalized_intent = str(intent or "").strip()
    if normalized_intent not in {"stock_store_search", "stock_store_search_slot_fill_store"}:
        pending_intent = str(known_slots.get("pending_intent") or "").strip()
        goal_type = str(known_slots.get("goal_type") or "").strip()
        if normalized_intent != "unknown" or (pending_intent != "stock" and goal_type != "store_with_stock"):
            return False
    if str(resume_source or "") not in {
        "expected_slot_fill:store",
        "router_slot_fill:store",
        "validated_ui_action_slot_fill",
        "location_selection:stock_store_search",
    }:
        return False
    schedule_mode = str(
        known_slots.get("schedule_mode")
        or known_slots.get("inventory_mode")
        or ""
    ).strip()
    return bool(
        known_slots.get("shop_id")
        and schedule_mode
        and known_slots.get("goods_no")
        and known_slots.get("tire_size")
        and (known_slots.get("ord_qty") or known_slots.get("quantity"))
        and str(known_slots.get("source_tool") or "") == "transaction_store_preview_tool"
    )


def _selected_store_schedule_response_decision_mismatch(response_decision: Mapping[str, Any] | None) -> bool:
    if not isinstance(response_decision, Mapping):
        return True
    metadata = response_decision.get("metadata")
    response_shape_key = str(metadata.get("response_shape_key") or "") if isinstance(metadata, Mapping) else ""
    return str(response_decision.get("template") or "") != "datepick" or response_shape_key != "reservation_slots"


def _selected_store_schedule_response_decision_payload(known_slots: Mapping[str, Any]) -> dict[str, Any]:
    schedule_mode = str(
        known_slots.get("schedule_mode")
        or known_slots.get("inventory_mode")
        or ""
    ).strip()
    return {
        "response_shape": "date_pick",
        "template": "datepick",
        "required_slots": [],
        "forbidden_behaviors": [
            "hide_available_stock",
            "empty_select_only_response",
            "preorder",
        ],
        "assistant_guidance": "선택한 매장 후보의 예약 가능 일정을 바로 datepick으로 이어간다.",
        "metadata": {
            "response_shape_key": "reservation_slots",
            "stock_check_mode": "preview",
            "schedule_mode": schedule_mode,
        },
    }


def _is_selected_store_schedule_continuation_contract(contract: TurnContract | None) -> bool:
    if contract is None:
        return False
    return _selected_store_schedule_continuation_matches(
        intent=str(contract.intent or ""),
        known_slots=contract.known_slots or {},
        resume_source=str(contract.resume_source or ""),
    )


_PURCHASE_OR_BOOKING_PROMPT_RE = re.compile(
    r"구매를\s*(?:진행|이어)|주문을\s*(?:진행|이어)|예약(?:\s*가능(?:\s*시간)?|\s*일정을?\s*(?:진행|확인|선택)|\s*을\s*진행)|"
    r"장착\s*매장|장착할\s*규격|수량이\s*필요",
    re.IGNORECASE,
)
_ACTION_TEMPLATE_MODES = {
    "datepick": {"purchase_continuation", "booking_continuation", "reservation_lookup", "stock_check"},
    "preOrder": {"purchase_continuation"},
    "orderComplete": {"purchase_continuation"},
    "cartComplete": {"purchase_continuation"},
}
_LOCATION_BOOKING_FLOW_MODES = {"purchase_continuation", "stock_check", "booking_continuation", "reservation_lookup"}
_ACTION_TOOL_MODES = {
    "quick_order_tool": {"purchase_continuation"},
    "add_to_cart_tool": {"purchase_continuation"},
    "transaction_store_preview_tool": {"purchase_continuation", "stock_check", "booking_continuation"},
    "get_store_schedule_tool": {"purchase_continuation", "stock_check", "booking_continuation", "reservation_lookup"},
    "get_multi_store_schedule_tool": {"purchase_continuation", "stock_check", "booking_continuation", "reservation_lookup"},
}


_INVENTORY_ONLY_STOCK_ACTION_TOOLS = frozenset({
    "transaction_store_preview_tool",
    "get_store_schedule_tool",
    "get_multi_store_schedule_tool",
    "quick_order_tool",
})
_OWNED_RECORD_LOOKUP_FORBIDDEN_TOOLS = frozenset({
    "quick_order_tool",
    "save_to_cart_tool",
    "add_to_cart_tool",
    "transaction_store_preview_tool",
    "get_store_schedule_tool",
    "get_multi_store_schedule_tool",
    "get_store_inventory_tool",
    "get_logistics_inventory_tool",
    "get_final_price_tool",
    "compare_discount_tool",
    "search_product_tool",
})

def _is_inventory_only_stock_contract(contract: TurnContract) -> bool:
    return str(contract.known_slots.get("stock_check_mode") or "") == "inventory_only"

def _is_owned_record_lookup_intent(intent: str) -> bool:
    return intent in {
        "reservation_status_lookup",
        "reservation_store_info_lookup",
        "order_cancel_status_lookup",
        "order_arrival_status_lookup",
        "maintenance_history_lookup",
    }

def _owned_record_lookup_tool_boundary(intent: str) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    if intent in {"reservation_status_lookup", "reservation_store_info_lookup"}:
        return (
            ("get_my_reservations_tool", "get_orders_of_user_tool", "get_order_status_tool"),
            tuple(_OWNED_RECORD_LOOKUP_FORBIDDEN_TOOLS),
            "get_my_reservations_tool",
        )
    if intent in {"order_cancel_status_lookup", "order_arrival_status_lookup"}:
        return (
            ("get_orders_of_user_tool", "get_order_status_tool"),
            tuple(_OWNED_RECORD_LOOKUP_FORBIDDEN_TOOLS - {"get_orders_of_user_tool", "get_order_status_tool"}),
            "get_orders_of_user_tool",
        )
    if intent == "maintenance_history_lookup":
        return (
            ("get_maintenance_history_tool",),
            tuple(_OWNED_RECORD_LOOKUP_FORBIDDEN_TOOLS | {"get_orders_of_user_tool", "get_order_status_tool"}),
            "get_maintenance_history_tool",
        )
    return (), (), ""

def _current_turn_stock_owner_intent(intent: str, known_slots: Mapping[str, Any]) -> str:
    stock_check_mode = str(known_slots.get("stock_check_mode") or "")
    if stock_check_mode and intent in {"resolve_or_describe_product", "transaction_fallback"}:
        return "stock_store_search"
    return intent

def _action_mode_contract_violation(
    *,
    event: Mapping[str, Any],
    contract: TurnContract,
) -> dict[str, Any] | None:
    action_mode = str(contract.action_mode or "info_only")
    if action_mode == "unspecified":
        return None

    template = str(event.get("template") or "")
    if action_mode == "stock_check" and _is_inventory_only_stock_contract(contract):
        if template in {"datepick", "preOrder", "orderComplete"}:
            return {
                "type": "inventory_only_stock_action_template_violation",
                "action_mode": action_mode,
                "stock_check_mode": "inventory_only",
                "template": template,
            }
        data = event.get("data")
        if template == "location" and isinstance(data, Mapping) and bool(data.get("isBookingFlow")):
            return {
                "type": "inventory_only_stock_booking_location_violation",
                "action_mode": action_mode,
                "stock_check_mode": "inventory_only",
                "template": template,
                "field": "isBookingFlow",
            }
        called_tools = {str(tool or "") for tool in event.get("called_tools") or ()}
        blocked_tools = sorted(called_tools & _INVENTORY_ONLY_STOCK_ACTION_TOOLS)
        if blocked_tools:
            return {
                "type": "inventory_only_stock_action_tool_violation",
                "action_mode": action_mode,
                "stock_check_mode": "inventory_only",
                "called_tools": blocked_tools,
            }

    allowed_modes = _ACTION_TEMPLATE_MODES.get(template)
    if allowed_modes is not None and action_mode not in allowed_modes:
        return {
            "type": "action_mode_template_violation",
            "action_mode": action_mode,
            "context_state": contract.context_state,
            "resume_source": contract.resume_source,
            "template": template,
        }
    data = event.get("data")
    response_shape_key = str(
        event.get("response_shape_key")
        or (
            data.get("metadata", {}).get("response_shape_key")
            if isinstance(data, Mapping) and isinstance(data.get("metadata"), Mapping)
            else ""
        )
        or ((contract.response_decision or {}).get("metadata") or {}).get("response_shape_key")
        or ""
    )
    if response_shape_key == "missing_stock_search_slots" and template == "quickReply":
        return None
    if (
        template == "location"
        and isinstance(data, Mapping)
        and bool(data.get("isBookingFlow"))
        and action_mode not in _LOCATION_BOOKING_FLOW_MODES
    ):
        return {
            "type": "action_mode_template_violation",
            "action_mode": action_mode,
            "context_state": contract.context_state,
            "resume_source": contract.resume_source,
            "template": template,
            "field": "isBookingFlow",
        }

    called_tools = {str(tool or "") for tool in event.get("called_tools") or ()}
    for tool_name, tool_modes in _ACTION_TOOL_MODES.items():
        if tool_name in called_tools and action_mode not in tool_modes:
            return {
                "type": "action_mode_tool_violation",
                "action_mode": action_mode,
                "context_state": contract.context_state,
                "resume_source": contract.resume_source,
                "tool": tool_name,
            }

    assistant_text = str(event.get("assistant_response_text") or "")
    if response_shape_key == "support_complaint_guidance":
        return None
    if (
        action_mode
        in {"support_policy_answer", "product_description", "product_comparison", "owned_record_lookup", "store_search", "info_only"}
        and _PURCHASE_OR_BOOKING_PROMPT_RE.search(assistant_text)
        and response_shape_key != "missing_stock_search_slots"
        and str(contract.intent or "") != "reservation_policy_guidance"
        and str(contract.sub_intent or "") != "reservation_window_policy"
    ):
        return {
            "type": "action_mode_prompt_violation",
            "action_mode": action_mode,
            "context_state": contract.context_state,
            "resume_source": contract.resume_source,
            "template": template,
        }
    return None


def response_contract_violations(
    *,
    template: str | None,
    user_text: str | None = None,
    assistant_response_text: str | None = None,
    assistant_response_source: str | None = None,
    compare_metric: str | None = None,
    response_shape_key: str | None = None,
    called_tools: list[str] | tuple[str, ...] | None = None,
    tool_inputs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None = None,
    structured_sources: list[tuple[str, Mapping[str, Any]]] | tuple[tuple[str, Mapping[str, Any]], ...] | None = None,
    event_data: Mapping[str, Any] | None = None,
    source_domain: str | None = None,
    contract: TurnContract | None,
) -> list[dict[str, Any]]:
    """Return deterministic contract violations for QC logging."""

    if contract is None:
        return []
    violations: list[dict[str, Any]] = []
    event = {
        "template": template or "",
        "assistant_response_source": assistant_response_source or "",
        "assistant_response_text": assistant_response_text or "",
        "response_shape_key": response_shape_key or "",
        "called_tools": list(called_tools or ()),
        "source_domain": source_domain or ("discovery" if contract.domain == "discovery" else contract.domain),
    }
    if event_data is not None:
        event["data"] = event_data
    known_slots = contract.known_slots or {}
    schedule_mode = str(
        known_slots.get("mode")
        or known_slots.get("scheduleMode")
        or known_slots.get("schedule_mode")
        or known_slots.get("inventoryMode")
        or known_slots.get("inventory_mode")
        or ""
    ).strip()
    if schedule_mode:
        event["data"] = {"metadata": {"scheduleMode": schedule_mode}}
    if should_guard_required_slots(contract) and template != "quickReply":
        violations.append({
            "type": "required_slots_not_clarified",
            "required_slots": list(contract.blocking_required_slots),
            "template": template,
        })
    action_mode_violation = _action_mode_contract_violation(event=event, contract=contract)
    if action_mode_violation is not None:
        violations.append(action_mode_violation)
    unsupported_product_template = _is_unsupported_discovery_product_template_without_current_source(event, contract)
    if unsupported_product_template:
        violations.append({
            "type": "unsupported_product_template_without_current_source",
            "template": template,
            "fallback_reason": contract.fallback_reason,
            "response_shape_key": str(event.get("response_shape_key") or ""),
            "assistant_response_source": str(event.get("assistant_response_source") or ""),
        })
    truncated_policy_response = _truncated_policy_response_violation(event=event, contract=contract)
    if truncated_policy_response is not None:
        violations.append(truncated_policy_response)
    discovery_first_leg_violation = _is_discovery_first_leg_transaction_violation(event, contract)
    if discovery_first_leg_violation:
        violations.append({
            "type": "forbidden_discovery_first_leg_response",
            "template": template,
            "fallback_reason": contract.fallback_reason,
            "response_shape_key": str(event.get("response_shape_key") or ""),
            "assistant_response_source": str(event.get("assistant_response_source") or ""),
        })
    if violates_response_template_contract(event, contract) and not unsupported_product_template:
        violations.append({
            "type": "forbidden_template",
            "template": template,
            "fallback_reason": contract.fallback_reason,
            "response_shape_key": str(event.get("response_shape_key") or ""),
            "assistant_response_source": str(event.get("assistant_response_source") or ""),
        })
    compare_metadata_violation = _comparison_metric_metadata_violation(
        compare_metric=compare_metric,
        assistant_response_source=assistant_response_source,
        contract=contract,
    )
    if compare_metadata_violation is not None:
        violations.append(compare_metadata_violation)
    product_attribute_violation = _product_attribute_contract_violation(
        assistant_response_source=assistant_response_source,
        response_shape_key=response_shape_key,
        contract=contract,
    )
    if product_attribute_violation is not None:
        violations.append(product_attribute_violation)
    tool_contract_violation = _tool_contract_violation(
        called_tools=called_tools,
        contract=contract,
    )
    if tool_contract_violation is not None:
        violations.append(tool_contract_violation)
    store_service_search_violation = _store_service_search_contract_violation(
        tool_inputs=tool_inputs,
        contract=contract,
    )
    if store_service_search_violation is not None:
        violations.append(store_service_search_violation)
    selected_store_schedule_violation = _selected_store_schedule_contract_violation(
        tool_inputs=tool_inputs,
        contract=contract,
    )
    if selected_store_schedule_violation is not None:
        violations.append(selected_store_schedule_violation)
    compare_violation = _comparison_contract_violation(
        assistant_response_text=assistant_response_text,
        assistant_response_source=assistant_response_source,
        response_shape_key=response_shape_key,
        contract=contract,
    )
    if compare_violation is not None:
        violations.append(compare_violation)
    stock_violation = _stock_contract_violation(
        template=template,
        assistant_response_source=assistant_response_source,
        response_shape_key=response_shape_key,
        called_tools=called_tools,
        contract=contract,
    )
    if stock_violation is not None:
        violations.append(stock_violation)
    quick_order_violation = _quick_order_execute_contract_violation(
        template=template,
        assistant_response_text=assistant_response_text,
        assistant_response_source=assistant_response_source,
        response_shape_key=response_shape_key,
        called_tools=called_tools,
        tool_inputs=tool_inputs,
        structured_sources=structured_sources,
        contract=contract,
    )
    if quick_order_violation is not None:
        violations.append(quick_order_violation)
    quick_order_reservation_violation = _quick_order_reservation_contract_violation(
        template=template,
        assistant_response_text=assistant_response_text,
        assistant_response_source=assistant_response_source,
        response_shape_key=response_shape_key,
        called_tools=called_tools,
        contract=contract,
    )
    if quick_order_reservation_violation is not None:
        violations.append(quick_order_reservation_violation)
    reservation_store_violation = _reservation_store_info_contract_violation(
        assistant_response_text=assistant_response_text,
        response_shape_key=response_shape_key,
        called_tools=called_tools,
        contract=contract,
    )
    if reservation_store_violation is not None:
        violations.append(reservation_store_violation)
    reservation_status_violation = _reservation_status_contract_violation(
        assistant_response_text=assistant_response_text,
        response_shape_key=response_shape_key,
        called_tools=called_tools,
        contract=contract,
    )
    if reservation_status_violation is not None:
        violations.append(reservation_status_violation)
    order_cancel_status_violation = _order_cancel_status_contract_violation(
        assistant_response_text=assistant_response_text,
        response_shape_key=response_shape_key,
        called_tools=called_tools,
        contract=contract,
    )
    if order_cancel_status_violation is not None:
        violations.append(order_cancel_status_violation)
    general_card_cancel_timing_violation = _general_card_cancel_timing_policy_contract_violation(
        assistant_response_text=assistant_response_text,
        response_shape_key=response_shape_key,
        called_tools=called_tools,
        contract=contract,
    )
    if general_card_cancel_timing_violation is not None:
        violations.append(general_card_cancel_timing_violation)
    order_cancel_fee_violation = _order_cancel_fee_inquiry_contract_violation(
        assistant_response_text=assistant_response_text,
        response_shape_key=response_shape_key,
        called_tools=called_tools,
        contract=contract,
    )
    if order_cancel_fee_violation is not None:
        violations.append(order_cancel_fee_violation)
    payment_error_violation = _payment_error_troubleshooting_contract_violation(
        template=template,
        called_tools=called_tools,
        event_data=event_data,
        contract=contract,
    )
    if payment_error_violation is not None:
        violations.append(payment_error_violation)
    order_document_violation = _order_document_guidance_contract_violation(
        template=template,
        called_tools=called_tools,
        event_data=event_data,
        contract=contract,
    )
    if order_document_violation is not None:
        violations.append(order_document_violation)
    signup_benefit_violation = _signup_first_purchase_benefit_contract_violation(
        user_text=user_text,
        assistant_response_text=assistant_response_text,
        called_tools=called_tools,
        contract=contract,
    )
    if signup_benefit_violation is not None:
        violations.append(signup_benefit_violation)
    signup_coupon_violation = _signup_coupon_guidance_contract_violation(
        user_text=user_text,
        assistant_response_text=assistant_response_text,
        called_tools=called_tools,
        contract=contract,
    )
    if signup_coupon_violation is not None:
        violations.append(signup_coupon_violation)
    promotion_gift_violation = _promotion_gift_policy_contract_violation(
        assistant_response_text=assistant_response_text,
        response_shape_key=response_shape_key,
        called_tools=called_tools,
        contract=contract,
    )
    if promotion_gift_violation is not None:
        violations.append(promotion_gift_violation)
    assurance_service_violation = _assurance_service_policy_contract_violation(
        assistant_response_text=assistant_response_text,
        contract=contract,
    )
    if assurance_service_violation is not None:
        violations.append(assurance_service_violation)
    tire_condition_photo_violation = _tire_condition_photo_policy_contract_violation(
        user_text=user_text,
        assistant_response_text=assistant_response_text,
        contract=contract,
    )
    if tire_condition_photo_violation is not None:
        violations.append(tire_condition_photo_violation)
    tire_quality_warranty_violation = _tire_quality_warranty_policy_contract_violation(
        assistant_response_text=assistant_response_text,
        event_data=event_data,
        contract=contract,
    )
    if tire_quality_warranty_violation is not None:
        violations.append(tire_quality_warranty_violation)
    best_seller_violation = _best_seller_search_contract_violation(
        assistant_response_text=assistant_response_text,
        called_tools=called_tools,
        event_data=event_data,
        contract=contract,
    )
    if best_seller_violation is not None:
        violations.append(best_seller_violation)
    faq_first_support_violation = _faq_first_support_policy_contract_violation(
        user_text=user_text,
        assistant_response_text=assistant_response_text,
        called_tools=called_tools,
        structured_sources=structured_sources,
        contract=contract,
    )
    if faq_first_support_violation is not None:
        violations.append(faq_first_support_violation)
    legal_action_violation = _legal_action_guidance_contract_violation(
        assistant_response_text=assistant_response_text,
        event_data=event_data,
        contract=contract,
    )
    if legal_action_violation is not None:
        violations.append(legal_action_violation)
    recommendation_disclosure_violation = _recommendation_approximation_disclosure_violation(
        assistant_response_text=assistant_response_text,
        contract=contract,
    )
    if recommendation_disclosure_violation is not None:
        violations.append(recommendation_disclosure_violation)
    recommendation_tool_drift = _recommendation_tool_input_drift_violation(
        tool_inputs=tool_inputs,
        contract=contract,
    )
    if recommendation_tool_drift is not None:
        violations.append(recommendation_tool_drift)
    return [_with_contract_violation_severity(violation) for violation in violations]


def _best_seller_search_contract_violation(
    *,
    assistant_response_text: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    event_data: Mapping[str, Any] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(contract.intent or "") != "best_seller_search":
        return None
    tools = [str(tool) for tool in tuple(called_tools or ()) if str(tool).strip()]
    if "get_products_recommendations_tool" in tools:
        return {
            "type": "best_seller_search_used_recommendation_tool",
            "called_tools": tools,
        }
    assistant_text = str(assistant_response_text or "").strip()
    if assistant_text and _BEST_SELLER_SIZE_CLARIFICATION_RE.search(assistant_text):
        return {
            "type": "best_seller_search_drifted_to_size_clarification",
            "assistant_response_text": assistant_text[:200],
        }
    quick_replies = event_data.get("quickReplies") if isinstance(event_data, Mapping) else None
    if isinstance(quick_replies, list):
        labels = {
            str(item.get("label") or "").strip()
            for item in quick_replies
            if isinstance(item, Mapping) and str(item.get("label") or "").strip()
        }
        blocked = sorted(labels & _BEST_SELLER_DISALLOWED_CTA_LABELS)
        if blocked:
            return {
                "type": "best_seller_search_disallowed_clarification_cta",
                "quick_replies": blocked,
            }
    return None


def _payment_error_troubleshooting_contract_violation(
    *,
    template: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    event_data: Mapping[str, Any] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or contract.intent != "payment_error_troubleshooting":
        return None
    tools = list(called_tools or ())
    has_faq = "search_faq_hybrid_tool" in tools
    has_qna = "transfer_to_qna_tool" in tools
    if has_qna and not has_faq:
        return {
            "type": "payment_error_troubleshooting_without_faq_search",
            "called_tools": tools,
        }
    if not has_faq:
        return None
    if template == "qnaComplete":
        return {
            "type": "payment_error_troubleshooting_qna_without_solution",
            "template": template,
            "called_tools": tools,
        }
    quick_replies = []
    assistant_text = ""
    if isinstance(event_data, Mapping):
        assistant_text = str(event_data.get("assistantResponse") or "").strip()
        raw_replies = event_data.get("quickReplies")
        if isinstance(raw_replies, list):
            quick_replies = [item for item in raw_replies if isinstance(item, Mapping)]
    if (
        quick_replies
        and len(assistant_text) < 30
        and all(str(item.get("label") or "").strip() in {"1:1 문의하기", "1:1 문의"} for item in quick_replies)
    ):
        return {
            "type": "payment_error_troubleshooting_qna_only_quickreply",
            "template": template,
            "called_tools": tools,
        }
    return None


def _legal_action_guidance_contract_violation(
    *,
    assistant_response_text: str | None,
    event_data: Mapping[str, Any] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None:
        return None
    response_decision = contract.response_decision or {}
    forbidden_behaviors = response_decision.get("forbidden_behaviors") if isinstance(response_decision, Mapping) else ()
    if not isinstance(forbidden_behaviors, list | tuple):
        return None
    forbidden_set = {str(item) for item in forbidden_behaviors}
    if not (forbidden_set & _LEGAL_ACTION_FORBIDDEN_BEHAVIORS):
        return None
    assistant_text = str(assistant_response_text or "").strip()
    if not assistant_text and isinstance(event_data, Mapping):
        assistant_text = str(event_data.get("assistantResponse") or "").strip()
    if not assistant_text:
        return None
    if _LEGAL_ACTION_DENIAL_RE.search(assistant_text):
        return None
    if not _LEGAL_ACTION_PROCEDURE_RE.search(assistant_text):
        return None
    return {
        "type": "legal_action_guidance_forbidden",
        "assistant_response_text": assistant_text[:160],
        "forbidden_behaviors": sorted(forbidden_set & _LEGAL_ACTION_FORBIDDEN_BEHAVIORS),
    }


def _order_document_guidance_contract_violation(
    *,
    template: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    event_data: Mapping[str, Any] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or contract.intent != "order_document_guidance":
        return None
    tools = list(called_tools or ())
    if "transfer_to_qna_tool" in tools or template == "qnaComplete":
        return {
            "type": "order_document_guidance_qna_direct",
            "template": template,
            "called_tools": tools,
        }
    assistant_text = ""
    quick_replies: list[Mapping[str, Any]] = []
    if isinstance(event_data, Mapping):
        assistant_text = str(event_data.get("assistantResponse") or "").strip()
        raw_replies = event_data.get("quickReplies")
        if isinstance(raw_replies, list):
            quick_replies = [item for item in raw_replies if isinstance(item, Mapping)]
    if assistant_text and "이메일" not in assistant_text:
        return {
            "type": "order_document_guidance_missing_email_notice",
            "assistant_response_text": assistant_text[:160],
        }
    has_order_history_cta = any(
        "주문" in str(item.get("label") or "")
        and "order-history" in str(item.get("url") or "")
        for item in quick_replies
    )
    if quick_replies and not has_order_history_cta:
        return {
            "type": "order_document_guidance_missing_order_history_cta",
            "quick_replies": [dict(item) for item in quick_replies[:3]],
        }
    return None


def _recommendation_metadata(contract: TurnContract | None) -> dict[str, Any]:
    if contract is None:
        return {}
    data: dict[str, Any] = {}
    context = _recommendation_context_dict(contract.known_slots.get("recommendation_context"))
    data.update(context)
    for key in (
        "recommendation_scenario",
        "applied_rcmd_type",
        "applied_vehicle_type",
        "applied_season_nm",
        "approximation",
        "approximation_basis",
        "recommendation_expected_tool_args",
    ):
        if contract.known_slots.get(key) not in (None, ""):
            data[key] = contract.known_slots[key]
    response_decision = contract.response_decision or {}
    response_metadata = response_decision.get("metadata") if isinstance(response_decision, Mapping) else {}
    if isinstance(response_metadata, Mapping):
        for key, value in response_metadata.items():
            if key.startswith("recommendation_") or key in {
                "applied_rcmd_type",
                "applied_vehicle_type",
                "applied_season_nm",
                "approximation",
                "approximation_basis",
            }:
                data[key] = value
    return data


_RECOMMENDATION_APPROXIMATION_DISCLOSURE_RE = re.compile(
    r"근사|전용(?:\s*필터)?(?:가|는)?\s*아니|하중\s*안정|SUV\s*/?\s*하중|기준으로\s*추천",
    re.IGNORECASE,
)
_OFFROAD_EXACT_CLAIM_RE = re.compile(r"오프로드\s*전용", re.IGNORECASE)
_OFFROAD_NEGATED_EXACT_CLAIM_RE = re.compile(
    r"오프로드\s*전용(?:\s*필터)?(?:이|가|은|는)?\s*(?:아니라|아니고|아님|아닙니다|아닌)",
    re.IGNORECASE,
)
_SENTENCE_WITH_OFFROAD_EXACT_CLAIM_RE = re.compile(
    r"[^.!?\n。！？]*오프로드\s*전용[^.!?\n。！？]*(?:[.!?。！？]+|$)",
    re.IGNORECASE,
)


def _has_unsupported_offroad_exact_claim(text: str) -> bool:
    return any(
        _OFFROAD_EXACT_CLAIM_RE.search(sentence)
        and not _OFFROAD_NEGATED_EXACT_CLAIM_RE.search(sentence)
        for sentence in (
            match.group(0)
            for match in _SENTENCE_WITH_OFFROAD_EXACT_CLAIM_RE.finditer(str(text or ""))
        )
    )


def _recommendation_approximation_disclosure_violation(
    *,
    assistant_response_text: str | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    metadata = _recommendation_metadata(contract)
    if metadata.get("approximation") is not True:
        return None
    text = str(assistant_response_text or "")
    if _has_unsupported_offroad_exact_claim(text):
        return {
            "type": "claim_unsupported_scenario_as_exact",
            "recommendation_scenario": metadata.get("recommendation_scenario") or metadata.get("scenario"),
            "approximation_basis": metadata.get("approximation_basis"),
        }
    if _RECOMMENDATION_APPROXIMATION_DISCLOSURE_RE.search(text):
        return None
    return {
        "type": "recommendation_approximation_disclosure_missing",
        "recommendation_scenario": metadata.get("recommendation_scenario") or metadata.get("scenario"),
        "approximation_basis": metadata.get("approximation_basis"),
    }


def _tool_input_for(tool_inputs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None, tool_name: str) -> dict[str, Any]:
    for item in reversed(tuple(tool_inputs or ())):
        if not isinstance(item, Mapping):
            continue
        if str(item.get("tool") or item.get("name") or "") != tool_name:
            continue
        args = item.get("effective_args")
        if args is None:
            args = item.get("effective_input")
        if args is None:
            args = item.get("args")
        if args is None:
            args = item.get("input")
        if isinstance(args, Mapping):
            return {key: value for key, value in args.items() if value not in (None, "")}
    return {}


def _normalized_tool_arg(value: Any) -> str:
    text = str(value or "").strip()
    if "." in text and text.lower().startswith("rcmdtype."):
        text = text.split(".", 1)[1]
    return text.lower()


def _recommendation_tool_input_drift_violation(
    *,
    tool_inputs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    metadata = _recommendation_metadata(contract)
    actual_args = _tool_input_for(tool_inputs, "get_products_recommendations_tool")
    if not actual_args:
        return None
    expected = metadata.get("recommendation_expected_tool_args")
    if not isinstance(expected, Mapping):
        expected = metadata.get("expected_tool_args")
    if not isinstance(expected, Mapping):
        context = _recommendation_context_dict(metadata)
        patch = context.get("tool_args_patch")
        expected = patch if isinstance(patch, Mapping) else {}
    expected_args = {key: value for key, value in dict(expected).items() if value not in (None, "")}
    actual_uses_vehicle_fitment = bool(actual_args.get("car_lnc_cd") and not actual_args.get("tire_size"))
    if (
        contract is not None
        and contract.known_slots.get("tire_size")
        and "tire_size" not in expected_args
        and not actual_uses_vehicle_fitment
    ):
        expected_args["tire_size"] = contract.known_slots.get("tire_size")
    if actual_uses_vehicle_fitment:
        expected_args.pop("tire_size", None)
    expected_args = {
        key: expected_args[key]
        for key in ("rcmd_type", "vehicle_type", "season_nm", "tire_size")
        if expected_args.get(key) not in (None, "")
    }
    if not expected_args:
        return None
    drift = {
        key: {"expected": expected_value, "actual": actual_args.get(key)}
        for key, expected_value in expected_args.items()
        if _normalized_tool_arg(actual_args.get(key)) != _normalized_tool_arg(expected_value)
    }
    if not drift:
        return None
    return {
        "type": "recommendation_tool_input_drift",
        "drift": drift,
    }


def _with_contract_violation_severity(violation: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(violation)
    if normalized.get("severity") in {"error", "warning"}:
        return normalized
    violation_type = str(normalized.get("type") or "")
    normalized["severity"] = "warning" if violation_type in _WARNING_CONTRACT_VIOLATION_TYPES else "error"
    return normalized


def hard_contract_violations(violations: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    return [violation for violation in violations if str(violation.get("severity") or "error") == "error"]


def warning_contract_violations(violations: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    return [violation for violation in violations if str(violation.get("severity") or "error") == "warning"]


def _comparison_metric_metadata_violation(
    *,
    compare_metric: str | None,
    assistant_response_source: str | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(assistant_response_source or "") != "code_product_compare_resolver":
        return None
    response_metadata = contract.response_decision or {}
    response_metadata = response_metadata.get("metadata") if isinstance(response_metadata, Mapping) else {}
    if not isinstance(response_metadata, Mapping):
        return None
    expected_metric = str(response_metadata.get("compare_metric") or contract.known_slots.get("compare_metric") or "")
    actual_metric = str(compare_metric or "").strip()
    if not expected_metric or not actual_metric or expected_metric == actual_metric:
        return None
    return {
        "type": "compare_metric_metadata_drift",
        "compare_metric": expected_metric,
        "assistant_compare_metric": actual_metric,
    }


def _product_attribute_contract_violation(
    *,
    assistant_response_source: str | None,
    response_shape_key: str | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None:
        return None
    response_metadata = contract.response_decision or {}
    response_metadata = response_metadata.get("metadata") if isinstance(response_metadata, Mapping) else {}
    if not isinstance(response_metadata, Mapping):
        return None
    requested_product_attribute = str(
        response_metadata.get("requested_product_attribute") or contract.known_slots.get("requested_product_attribute") or ""
    )
    if not requested_product_attribute:
        return None
    if str(response_shape_key or "") == "product_attribute_summary":
        return None
    return {
        "type": "requested_product_attribute_contract_drift",
        "requested_product_attribute": requested_product_attribute,
        "response_shape_key": str(response_shape_key or ""),
        "assistant_response_source": str(assistant_response_source or ""),
        "expected_response_shape_key": "product_attribute_summary",
    }


def _tool_contract_violation(
    *,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or not called_tools:
        return None
    called_tool_set = {str(tool) for tool in tuple(called_tools or ()) if str(tool).strip()}
    if (
        called_tool_set
        and called_tool_set <= _DISCOVERY_PRODUCT_SOURCE_TOOLS
        and _is_discovery_first_leg_transaction_contract(contract)
    ):
        return None
    if called_tool_set and called_tool_set <= _COMPARISON_RESOLVER_TOOLS and _is_comparison_contract(contract):
        return None
    forbidden = [
        str(tool)
        for tool in called_tools
        if str(tool) and str(tool) in contract.forbidden_tools
    ]
    if forbidden:
        severity = (
            "error"
            if contract.domain in {"transaction", "support"}
            or any(tool in _HIGH_RISK_TRANSACTION_TOOLS for tool in forbidden)
            else "warning"
        )
        return {
            "type": "forbidden_tool_for_contract",
            "called_tools": forbidden,
            "forbidden_tools": list(contract.forbidden_tools),
            "severity": severity,
        }
    unexpected = [
        str(tool)
        for tool in called_tools
        if str(tool) and str(tool) not in contract.allowed_tools
    ]
    if not unexpected:
        return None
    return {
        "type": "unexpected_tool_for_contract",
        "called_tools": unexpected,
        "allowed_tools": list(contract.allowed_tools),
    }


def _selected_store_schedule_contract_violation(
    *,
    tool_inputs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or not _is_selected_store_schedule_continuation_contract(contract) or not tool_inputs:
        return None
    known_slots = contract.known_slots or {}
    expected_shop_id = str(known_slots.get("shop_id") or "").strip()
    expected_mode = str(
        known_slots.get("schedule_mode")
        or known_slots.get("inventory_mode")
        or ""
    ).strip()
    for tool_input in tool_inputs:
        tool_name = str(tool_input.get("tool") or "")
        if tool_name != "get_store_schedule_tool":
            continue
        args = tool_input.get("args") if isinstance(tool_input.get("args"), Mapping) else tool_input.get("input")
        if not isinstance(args, Mapping):
            continue
        actual_shop_id = str(args.get("shop_id") or "").strip()
        actual_mode = str(args.get("mode") or "").strip()
        if actual_shop_id != expected_shop_id:
            return {
                "type": "selected_store_schedule_shop_mismatch",
                "expected_shop_id": expected_shop_id,
                "actual_shop_id": actual_shop_id,
                "severity": "error",
            }
        if actual_mode != expected_mode:
            return {
                "type": "selected_store_schedule_mode_mismatch",
                "expected_mode": expected_mode,
                "actual_mode": actual_mode,
                "severity": "error",
            }
    return None


def _normalize_service_code_values(value: Any) -> set[str]:
    if value in (None, "", [], (), {}):
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item or "").strip()}
    return {str(value).strip()} if str(value).strip() else set()


def _store_search_location_values_match(*, expected: str, actual: str, region: str = "") -> bool:
    expected_value = str(expected or "").strip()
    actual_value = str(actual or "").strip()
    region_value = str(region or "").strip()
    if not expected_value or not actual_value:
        return True
    if expected_value == actual_value:
        return True
    if region_value and actual_value == region_value:
        return expected_value == region_value or region_value in expected_value
    return len(actual_value) >= 2 and actual_value in expected_value


def _store_service_search_contract_violation(
    *,
    tool_inputs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or contract.intent != "store_service_search" or not tool_inputs:
        return None
    known_slots = contract.known_slots or {}
    expected_region = _slot_text(known_slots, "region")
    expected_place_query = _slot_text(known_slots, "place_query")
    expected_service_codes = _normalize_service_code_values(
        known_slots.get("service_codes") or known_slots.get("service_code")
    )
    for tool_input in tool_inputs:
        tool_name = str(tool_input.get("tool") or "")
        if tool_name not in _STORE_SERVICE_SEARCH_TOOLS:
            continue
        args = tool_input.get("args") if isinstance(tool_input.get("args"), Mapping) else tool_input.get("input")
        if not isinstance(args, Mapping):
            continue
        actual_region = str(args.get("region_code") or args.get("region") or "").strip()
        actual_place_query = str(args.get("place_query") or "").strip()
        actual_service_codes = _normalize_service_code_values(
            args.get("svc_codes") or args.get("service_codes") or args.get("service_code") or args.get("svc_code")
        )
        if expected_region and actual_region and expected_region != actual_region:
            return {
                "type": "store_service_search_region_contract_drift",
                "known_region": expected_region,
                "tool_region": actual_region,
                "tool": tool_name,
            }
        if expected_place_query and actual_place_query and not _store_search_location_values_match(
            expected=expected_place_query,
            actual=actual_place_query,
            region=expected_region,
        ):
            return {
                "type": "store_service_search_place_query_contract_drift",
                "known_place_query": expected_place_query,
                "tool_place_query": actual_place_query,
                "tool": tool_name,
            }
        if expected_service_codes and actual_service_codes and expected_service_codes.isdisjoint(actual_service_codes):
            return {
                "type": "store_service_search_service_code_contract_drift",
                "known_service_codes": sorted(expected_service_codes),
                "tool_service_codes": sorted(actual_service_codes),
                "tool": tool_name,
            }
    return None


def _signup_first_purchase_benefit_contract_violation(
    *,
    user_text: str | None,
    assistant_response_text: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or contract.intent != "signup_first_purchase_benefit_policy":
        return None
    if _ASSURANCE_SERVICE_POLICY_ANCHOR_RE.search(str(user_text or "")):
        return None
    tools = list(called_tools or ())
    if "transfer_to_qna_tool" in tools:
        return {
            "type": "signup_first_purchase_benefit_qna_direct",
            "called_tools": tools,
        }
    assistant_text = str(assistant_response_text or "").strip()
    if "첫구매" in assistant_text and "핵심 조건" not in assistant_text and "바로 안내되지는" not in assistant_text:
        return {
            "type": "signup_first_purchase_benefit_asserted_first_purchase_only",
            "assistant_response_text": assistant_text,
        }
    if "마케팅 수신 동의" not in assistant_text or "5% 할인 쿠폰" not in assistant_text:
        return {
            "type": "signup_first_purchase_benefit_missing_membership_marketing_policy",
            "assistant_response_text": assistant_text,
            "severity": "warning",
        }
    if re.search(r"(자동|바로|즉시).{0,12}(발급|지급)|이미.{0,8}(발급|지급)", assistant_text):
        return {
            "type": "signup_first_purchase_benefit_asserted_unverified_coupon_issue",
            "assistant_response_text": assistant_text,
        }
    return None


def _signup_coupon_guidance_contract_violation(
    *,
    user_text: str | None,
    assistant_response_text: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or contract.intent != "signup_coupon_guidance":
        return None
    if _ASSURANCE_SERVICE_POLICY_ANCHOR_RE.search(str(user_text or "")):
        return None
    tools = list(called_tools or ())
    if "transfer_to_qna_tool" in tools:
        return {
            "type": "signup_coupon_guidance_qna_direct",
            "called_tools": tools,
        }
    assistant_text = str(assistant_response_text or "").strip()
    if "첫구매 고객에게만" in assistant_text or "첫구매 전용" in assistant_text:
        return {
            "type": "signup_coupon_guidance_asserted_first_purchase_only",
            "assistant_response_text": assistant_text,
        }
    if "마케팅 수신 동의" not in assistant_text or "5% 할인 쿠폰" not in assistant_text:
        return {
            "type": "signup_coupon_guidance_missing_membership_marketing_policy",
            "assistant_response_text": assistant_text,
            "severity": "warning",
        }
    if re.search(r"이미.{0,8}(발급|지급)|발급됐", assistant_text):
        return {
            "type": "signup_coupon_guidance_asserted_already_issued",
            "assistant_response_text": assistant_text,
        }
    return None


def _promotion_gift_policy_contract_violation(
    *,
    assistant_response_text: str | None,
    response_shape_key: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(contract.intent or "") != "promotion_gift_policy":
        return None
    tools = {str(tool) for tool in tuple(called_tools or ()) if str(tool).strip()}
    blocked_tools = sorted(
        tools
        & {
            "search_product_tool",
            "get_final_price_tool",
            "get_orders_of_user_tool",
            "get_order_status_tool",
            "get_product_applicable_events_tool",
            "get_product_promotions_tool",
        }
    )
    if blocked_tools:
        return {
            "type": "promotion_gift_policy_used_forbidden_lookup",
            "called_tools": blocked_tools,
            "response_shape_key": str(response_shape_key or ""),
        }
    assistant_text = str(assistant_response_text or "").strip()
    normalized_text = re.sub(r"\s+", "", assistant_text)
    has_partial_cancel = any(token in normalized_text for token in ("부분취소", "일부취소", "취소"))
    has_threshold_miss = any(token in normalized_text for token in ("기준수량", "기준미달", "수량미달", "조건미달"))
    has_return_or_deduction = any(token in normalized_text for token in ("사은품반납", "반납", "차감", "상당금액"))
    has_refund = "환불" in normalized_text
    has_final_condition = any(
        token in normalized_text for token in ("이벤트상세조건", "상세조건", "주문취소처리기준", "취소처리기준")
    )
    if not (has_partial_cancel and has_threshold_miss and has_return_or_deduction and has_refund and has_final_condition):
        return {
            "type": "promotion_gift_policy_missing_partial_cancel_guidance",
            "assistant_response_text": assistant_text,
            "response_shape_key": str(response_shape_key or ""),
            "severity": "warning",
        }
    return None


def _assurance_service_policy_contract_violation(
    *,
    assistant_response_text: str | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(contract.intent or "") != "assurance_service_policy":
        return None
    assistant_text = str(assistant_response_text or "").strip()
    normalized_text = re.sub(r"\s+", "", assistant_text)
    has_time_condition = any(token in normalized_text for token in ("1년이내", "12개월이내"))
    has_mileage_condition = any(token in normalized_text for token in ("16,000km이내", "16000km이내", "16000km", "16,000km"))
    if not (has_time_condition and has_mileage_condition):
        return {
            "type": "assurance_service_policy_missing_core_conditions",
            "assistant_response_text": assistant_text,
            "severity": "warning",
        }
    if re.search(r"(무조건|항상|자동|반드시).{0,12}보상|보상.{0,8}(확정|됩니다)", assistant_text, re.IGNORECASE):
        return {
            "type": "assurance_service_policy_overstated_compensation",
            "assistant_response_text": assistant_text,
        }
    return None


_FAQ_FIRST_SUPPORT_POLICY_INTENTS = {
    "tire_manufacture_date_policy",
    "tire_quality_warranty_policy",
    "assurance_service_policy",
    "reservation_window_policy",
    "reservation_policy_guidance",
    "installation_work_policy",
    "external_tire_install_policy",
    "promotion_gift_policy",
}

_FAQ_SOURCE_TOOLS = frozenset({"get_faq_tool", "search_faq_rag_tool", "search_faq_hybrid_tool"})
_USER_UPLOAD_REQUEST_RE = re.compile(
    r"사진\s*(?:보낼|올릴|업로드|첨부)|이미지\s*(?:보낼|올릴|업로드|첨부)|"
    r"파일\s*(?:보낼|올릴|업로드|첨부)|첨부\s*(?:할게|했어|하면|해도|해서)|"
    r"(?:사진|이미지|파일).{0,8}(?:봐줘|봐\s*줄|확인해\s*줘)",
    re.IGNORECASE,
)
_NON_UPLOAD_IMAGE_LOOKUP_RE = re.compile(
    r"(?:매장|지점|상품|타이어).{0,10}(?:사진|이미지).{0,8}(?:보여|조회|찾아)|"
    r"(?:사진|이미지).{0,8}(?:보여줘|조회해줘|찾아줘)",
    re.IGNORECASE,
)
_FAQ_FIRST_SUPPORT_POLICY_UNSUPPORTED_ASSERTION_RE = {
    "tire_manufacture_date_policy": re.compile(
        r"(무조건|항상|바로|즉시|확정|반드시).{0,18}(교환|환불|새\s*걸|불량)|"
        r"(교환|환불).{0,8}(확정|됩니다)|"
        r"새\s*걸로\s*바꿔\s*(?:드릴게요|드립니다|드려요|줄게요|줍니다)",
        re.IGNORECASE,
    ),
    "tire_quality_warranty_policy": re.compile(
        r"(무조건|항상|바로|즉시|확정|반드시).{0,18}(무상|무료|교체|A/S|AS)|"
        r"무상.{0,8}(확정|됩니다)|무료\s*교체\s*(?:됩니다|해\s*드)",
        re.IGNORECASE,
    ),
    "assurance_service_policy": re.compile(
        r"(무조건|항상|바로|즉시|확정|반드시|자동).{0,18}(보상|가입)|보상.{0,8}(확정|됩니다)",
        re.IGNORECASE,
    ),
    "tire_condition_photo_policy": re.compile(r"(더\s*타도\s*돼|주행\s*가능|안전합니다)", re.IGNORECASE),
}
_FAQ_POLICY_SOURCE_MIN_SCORE_BY_INTENT = {
    "tire_manufacture_date_policy": 0.2,
    "tire_quality_warranty_policy": 0.2,
    "reservation_no_show_fee_policy": 0.2,
    "promotion_gift_delivery_policy": 0.2,
}
_FAQ_POLICY_SOURCE_RELEVANCE_RE = {
    "tire_manufacture_date_policy": re.compile(
        r"제조\s*일자|제조일자|DOT|신품|유통|숙성|선입선출|6\s*~\s*12개월|6개월|12개월",
        re.IGNORECASE,
    ),
    "tire_quality_warranty_policy": re.compile(
        r"측면|사이드월|부풀|품질\s*보증|품질보증|무상\s*(?:A/?S|AS|as|교체|수리)|"
        r"제조상\s*과실|보증\s*(?:기준|기간|조건)|점검|잔여\s*홈|워런티",
        re.IGNORECASE,
    ),
}
_FAQ_POLICY_ALLOW_TOKENS = {
    "tire_manufacture_date_policy": ("제조일자", "DOT", "신품", "유통", "숙성", "선입선출", "6개월", "12개월"),
    "tire_quality_warranty_policy": ("측면", "사이드월", "부풀", "품질보증", "보증기간", "무상", "점검", "워런티"),
    "reservation_no_show_fee_policy": ("미방문", "예약시간", "못 갔", "취소", "수수료", "위약금", "환불"),
    "promotion_gift_delivery_policy": ("사은품", "지급", "배송", "수령", "언제"),
}
_FAQ_POLICY_DENY_TOKENS = {
    "tire_quality_warranty_policy": ("제조일자", "DOT", "선입선출", "1년 이내 생산", "최신 제조", "신품", "6개월", "12개월"),
    "reservation_no_show_fee_policy": ("예약 방법", "장착점 선택", "고객정보 입력"),
    "promotion_gift_delivery_policy": ("부분 취소", "반납", "차감"),
}
_TIRE_QUALITY_WARRANTY_MANUFACTURE_DRIFT_RE = re.compile(
    r"선입선출|1년\s*이내\s*생산|최신\s*제조|DOT|제조\s*일자|제조일자|신품|6\s*~\s*12개월|6개월|12개월|유통",
    re.IGNORECASE,
)
_ASSURANCE_SERVICE_POLICY_ANCHOR_RE = re.compile(
    r"안심\s*서비스|안심서비스|안심\s*플러스|안심플러스|디지털\s*워런티|종이\s*보증서|보증서|워런티",
    re.IGNORECASE,
)


def _walk_string_values(obj: Any) -> list[str]:
    values: list[str] = []
    if isinstance(obj, str):
        stripped = obj.strip()
        if stripped:
            values.append(stripped)
    elif isinstance(obj, Mapping):
        for value in obj.values():
            values.extend(_walk_string_values(value))
    elif isinstance(obj, list | tuple):
        for item in obj:
            values.extend(_walk_string_values(item))
    return values


def _faq_policy_candidate_score(candidate: Mapping[str, Any]) -> float | None:
    raw_score = candidate.get("score")
    if raw_score is None:
        return None
    try:
        return float(raw_score)
    except (TypeError, ValueError):
        return None


def _faq_policy_candidate_text(candidate: Mapping[str, Any]) -> str:
    parts = [
        str(candidate.get("question") or "").strip(),
        str(
            candidate.get("answer")
            or candidate.get("pc_ans_cont")
            or candidate.get("content")
            or candidate.get("body")
            or ""
        ).strip(),
    ]
    return "\n".join(part for part in parts if part)


def _faq_policy_candidates_from_output(output: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    data = output.get("data", output)
    candidates: list[Any] = []
    if isinstance(data, Mapping):
        for key in ("items", "faqs", "results"):
            value = data.get(key)
            if isinstance(value, list):
                candidates.extend(value)
        if not candidates:
            candidates.append(data)
    elif isinstance(data, list):
        candidates.extend(data)
    return [candidate for candidate in candidates if isinstance(candidate, Mapping)]


def _faq_policy_candidate_is_relevant(intent: str | None, candidate: Mapping[str, Any]) -> bool:
    if not intent:
        return True
    text = _faq_policy_candidate_text(candidate)
    if not text:
        return False
    score = _faq_policy_candidate_score(candidate)
    min_score = _FAQ_POLICY_SOURCE_MIN_SCORE_BY_INTENT.get(intent)
    if min_score is not None and score is not None and score < min_score:
        return False
    relevance_re = _FAQ_POLICY_SOURCE_RELEVANCE_RE.get(intent)
    if relevance_re is not None and not relevance_re.search(text):
        return False
    lowered_text = text.lower()
    allow_tokens = _FAQ_POLICY_ALLOW_TOKENS.get(intent, ())
    if allow_tokens and not any(token.lower() in lowered_text for token in allow_tokens):
        return False
    deny_tokens = _FAQ_POLICY_DENY_TOKENS.get(intent, ())
    if deny_tokens and any(token.lower() in lowered_text for token in deny_tokens):
        return False
    return True


def _faq_source_text(structured_sources: list[tuple[str, Mapping[str, Any]]] | tuple[tuple[str, Mapping[str, Any]], ...] | None) -> str:
    snippets: list[str] = []
    for tool_name, output in tuple(structured_sources or ()):
        if str(tool_name or "") not in _FAQ_SOURCE_TOOLS or not isinstance(output, Mapping):
            continue
        snippets.extend(_walk_string_values(output))
    return "\n".join(snippets)


def _faq_source_text_for_intent(
    intent: str | None,
    structured_sources: list[tuple[str, Mapping[str, Any]]] | tuple[tuple[str, Mapping[str, Any]], ...] | None,
) -> str:
    snippets: list[str] = []
    for tool_name, output in tuple(structured_sources or ()):
        if str(tool_name or "") not in _FAQ_SOURCE_TOOLS or not isinstance(output, Mapping):
            continue
        for candidate in _faq_policy_candidates_from_output(output):
            if _faq_policy_candidate_is_relevant(intent, candidate):
                snippets.append(_faq_policy_candidate_text(candidate))
    return "\n".join(snippet for snippet in snippets if snippet)


def _has_faq_source(
    structured_sources: list[tuple[str, Mapping[str, Any]]] | tuple[tuple[str, Mapping[str, Any]], ...] | None,
) -> bool:
    return bool(_faq_source_text(structured_sources))


def _faq_source_supports_assertion(intent: str, assistant_text: str, faq_text: str) -> bool:
    """Allow conditional policy wording when the same policy topic exists in FAQ source.

    This does not try to prove every Korean sentence. It only prevents broad keyword hard-blocking for
    source-backed conditional language such as "가능 여부 확인" while keeping absolute benefit/safety claims blocked.
    """
    if not faq_text.strip():
        return False
    if intent == "tire_condition_photo_policy":
        return False
    absolute_re = _FAQ_FIRST_SUPPORT_POLICY_UNSUPPORTED_ASSERTION_RE.get(intent)
    if absolute_re and absolute_re.search(assistant_text):
        return False
    topic_tokens = {
        "tire_manufacture_date_policy": ("제조", "제조일", "신품", "유통", "숙성", "6개월", "12개월"),
        "tire_quality_warranty_policy": ("품질", "보증", "무상", "A/S", "AS", "잔여", "마모"),
        "assurance_service_policy": ("안심", "워런티", "보상", "디지털", "가입"),
        "reservation_window_policy": ("예약", "30일", "1개월", "장착일", "사전 구매"),
        "reservation_policy_guidance": ("예약", "취소", "변경", "위약", "장착점"),
        "installation_work_policy": ("공임", "장착", "얼라인먼트", "폐타이어", "현장"),
        "external_tire_install_policy": ("외부", "반입", "공임", "장착", "온라인몰", "지정 장착점"),
        "promotion_gift_policy": ("사은품", "프로모션", "이벤트", "반납", "차감"),
    }.get(intent, ())
    if not topic_tokens:
        return True
    return any(token.lower() in faq_text.lower() for token in topic_tokens)


def _requires_upload_capability_notice(user_text: str | None) -> bool:
    text = str(user_text or "").strip()
    if not text:
        return False
    if _NON_UPLOAD_IMAGE_LOOKUP_RE.search(text):
        return False
    return bool(_USER_UPLOAD_REQUEST_RE.search(text))


def _tire_condition_photo_policy_contract_violation(
    *,
    user_text: str | None = None,
    assistant_response_text: str | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(contract.intent or "") != "tire_condition_photo_policy":
        return None
    assistant_text = str(assistant_response_text or "").strip()
    normalized_text = re.sub(r"\s+", "", assistant_text)
    if _requires_upload_capability_notice(user_text):
        has_upload_notice = any(token in normalized_text for token in ("업로드", "첨부", "파일"))
        if not has_upload_notice:
            return {
                "type": "upload_capability_notice_missing",
                "assistant_response_text": assistant_text[:160],
                "severity": "error",
            }
    if re.search(r"(더\s*타도\s*돼|주행\s*가능|안전합니다)", assistant_text, re.IGNORECASE):
        return {
            "type": "tire_condition_photo_policy_safety_assertion_without_verification",
            "assistant_response_text": assistant_text,
            "severity": "error",
        }
    has_photo_limit = any(token in normalized_text for token in ("사진만으로는", "사진만으로", "판단불가", "확정할수없"))
    has_qna_registration = "1:1문의" in normalized_text or "1대1문의" in normalized_text
    has_measurement_or_inspection = (
        "마모도측정서비스" in normalized_text
        or ("마모도" in normalized_text and "측정" in normalized_text)
        or "매장점검" in normalized_text
        or "전문점검" in normalized_text
    )
    if not (has_photo_limit and has_qna_registration and has_measurement_or_inspection):
        return {
            "type": "tire_condition_photo_policy_missing_required_guidance",
            "assistant_response_text": assistant_text,
        }
    return None


def _faq_first_support_policy_contract_violation(
    *,
    user_text: str | None = None,
    assistant_response_text: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    structured_sources: list[tuple[str, Mapping[str, Any]]] | tuple[tuple[str, Mapping[str, Any]], ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or contract.intent not in _FAQ_FIRST_SUPPORT_POLICY_INTENTS:
        return None
    tools = list(called_tools or ())
    has_faq = bool(set(tools) & _FAQ_SOURCE_TOOLS)
    has_qna = "transfer_to_qna_tool" in tools
    if has_qna and not has_faq:
        return {
            "type": f"{contract.intent}_qna_without_faq_search",
            "called_tools": tools,
        }
    assistant_text = str(assistant_response_text or "").strip()
    if assistant_text and not has_faq:
        return {
            "type": f"{contract.intent}_answer_without_faq_search",
            "assistant_response_text": assistant_text[:160],
            "called_tools": tools,
        }
    intent = str(contract.intent or "")
    if _requires_upload_capability_notice(user_text):
        upload_notice_present = (
            "업로드" in assistant_text
            or "첨부" in assistant_text
            or "파일" in assistant_text
        )
        if not upload_notice_present:
            return {
                "type": "upload_capability_notice_missing",
                "assistant_response_text": assistant_text[:160],
                "severity": "error",
            }
    assertion_re = _FAQ_FIRST_SUPPORT_POLICY_UNSUPPORTED_ASSERTION_RE.get(intent)
    if not assistant_text or not assertion_re or not assertion_re.search(assistant_text):
        return None
    faq_text = _faq_source_text_for_intent(intent, structured_sources) or _faq_source_text(structured_sources)
    if _faq_source_supports_assertion(intent, assistant_text, faq_text):
        return None
    violation_type = (
        f"{contract.intent}_safety_assertion_without_verification"
        if intent == "tire_condition_photo_policy"
        else f"{contract.intent}_assertion_not_supported_by_faq_source"
        if _has_faq_source(structured_sources)
        else f"{contract.intent}_asserted_without_verification"
    )
    return {
        "type": violation_type,
        "assistant_response_text": assistant_text,
    }


def _tire_quality_warranty_policy_contract_violation(
    *,
    assistant_response_text: str | None,
    event_data: Mapping[str, Any] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(contract.intent or "") != "tire_quality_warranty_policy":
        return None
    assistant_text = str(assistant_response_text or "").strip()
    if not assistant_text and isinstance(event_data, Mapping):
        assistant_text = str(event_data.get("assistantResponse") or "").strip()
    normalized_text = re.sub(r"\s+", "", assistant_text)
    if _TIRE_QUALITY_WARRANTY_MANUFACTURE_DRIFT_RE.search(assistant_text):
        return {
            "type": "tire_quality_warranty_policy_irrelevant_manufacture_date_guidance",
            "assistant_response_text": assistant_text[:160],
            "severity": "error",
        }
    has_damage_guidance = "부풀" in normalized_text or "사이드월" in normalized_text or "측면" in normalized_text
    has_inspection_guidance = "점검" in normalized_text or "상태확인" in normalized_text
    has_policy_guidance = (
        "구매" in normalized_text
        and "장착" in normalized_text
        and ("보증" in normalized_text or "워런티" in normalized_text)
    )
    if not (has_damage_guidance and has_inspection_guidance and has_policy_guidance):
        return {
            "type": "tire_quality_warranty_policy_missing_core_guidance",
            "assistant_response_text": assistant_text[:160],
            "severity": "warning",
        }
    quick_replies = event_data.get("quickReplies") if isinstance(event_data, Mapping) else None
    if isinstance(quick_replies, list):
        first = quick_replies[0] if quick_replies else None
        if not isinstance(first, Mapping) or str(first.get("url") or "") != CTAUrls.WARRANTY_MAIN:
            return {
                "type": "tire_quality_warranty_policy_missing_warranty_cta",
                "severity": "warning",
            }
    return None


def _is_comparison_contract(contract: TurnContract | None) -> bool:
    if contract is None:
        return False
    if str(contract.intent or "") == "product_comparison":
        return True
    response_decision = contract.response_decision or {}
    metadata = response_decision.get("metadata") if isinstance(response_decision, Mapping) else {}
    if not isinstance(metadata, Mapping):
        return False
    response_shape_key = str(metadata.get("response_shape_key") or "")
    return response_shape_key in {"metric_comparison_summary", "grade_comparison_summary"}


def _comparison_contract_violation(
    *,
    assistant_response_text: str | None,
    assistant_response_source: str | None,
    response_shape_key: str | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None:
        return None
    response_metadata = contract.response_decision or {}
    response_metadata = response_metadata.get("metadata") if isinstance(response_metadata, Mapping) else {}
    if not isinstance(response_metadata, Mapping):
        return None
    comparison_followup_intent = str(response_metadata.get("comparison_followup_intent") or "")
    compare_metric = str(response_metadata.get("compare_metric") or contract.known_slots.get("compare_metric") or "")
    if comparison_followup_intent != "continue_previous_compare_metric":
        return None
    if str(assistant_response_source or "") != "code_product_compare_resolver":
        return {
            "type": "compare_metric_contract_drift",
            "comparison_followup_intent": comparison_followup_intent,
            "compare_metric": compare_metric or "none",
            "assistant_response_source": str(assistant_response_source or ""),
        }
    expected_response_shape_key = (
        "grade_comparison_summary" if compare_metric in {"grade", "price_grade"} else "metric_comparison_summary"
    )
    if str(response_shape_key or "") != expected_response_shape_key:
        return {
            "type": "compare_metric_contract_drift",
            "comparison_followup_intent": comparison_followup_intent,
            "compare_metric": compare_metric or "none",
            "response_shape_key": str(response_shape_key or ""),
            "expected_response_shape_key": expected_response_shape_key,
        }
    expected_row = _comparison_metric_row_label(compare_metric)
    response_text = str(assistant_response_text or "")
    if expected_row and expected_row not in response_text:
        return {
            "type": "compare_metric_row_missing",
            "comparison_followup_intent": comparison_followup_intent,
            "compare_metric": compare_metric or "none",
            "expected_row": expected_row,
        }
    return None


def _reservation_store_info_contract_violation(
    *,
    assistant_response_text: str | None,
    response_shape_key: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(contract.intent or "") != "reservation_store_info_lookup":
        return None
    tools = {str(tool) for tool in tuple(called_tools or ()) if str(tool).strip()}
    source_tools = {"get_my_reservations_tool", "get_orders_of_user_tool", "get_order_status_tool"}
    if tools & source_tools:
        return None
    response_text = str(assistant_response_text or "")
    if str(response_shape_key or "") == "reservation_store_info_lookup" or _RESERVATION_STORE_CLAIM_RE.search(response_text):
        return {
            "type": "reservation_store_claim_without_reservation_source",
            "response_shape_key": str(response_shape_key or ""),
            "called_tools": sorted(tools),
        }
    return None


def _reservation_status_contract_violation(
    *,
    assistant_response_text: str | None,
    response_shape_key: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(contract.intent or "") != "reservation_status_lookup":
        return None
    tools = {str(tool) for tool in tuple(called_tools or ()) if str(tool).strip()}
    source_tools = {"get_my_reservations_tool", "get_orders_of_user_tool", "get_order_status_tool"}
    if tools & source_tools:
        return None
    response_text = str(assistant_response_text or "")
    if str(response_shape_key or "") == "reservation_status_lookup" or _RESERVATION_STATUS_CLAIM_RE.search(response_text):
        return {
            "type": "reservation_status_claim_without_reservation_source",
            "response_shape_key": str(response_shape_key or ""),
            "called_tools": sorted(tools),
        }
    return None


def _order_cancel_status_contract_violation(
    *,
    assistant_response_text: str | None,
    response_shape_key: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(contract.intent or "") != "order_cancel_status_lookup":
        return None
    response_text = str(assistant_response_text or "")
    if response_text.startswith("제가 직접 주문을 취소 처리할 수는 없어요"):
        return {
            "type": "order_cancel_status_normalized_as_cancel_request",
            "response_shape_key": str(response_shape_key or ""),
        }
    tools = {str(tool) for tool in tuple(called_tools or ()) if str(tool).strip()}
    if tools & {"get_order_status_tool", "get_orders_of_user_tool"}:
        return None
    if str(response_shape_key or "") == "order_cancel_status_summary":
        return {
            "type": "order_cancel_status_without_order_lookup",
            "response_shape_key": str(response_shape_key or ""),
            "called_tools": sorted(tools),
        }
    return None


def _general_card_cancel_timing_policy_contract_violation(
    *,
    assistant_response_text: str | None,
    response_shape_key: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(contract.intent or "") != "general_card_cancel_timing_policy":
        return None
    tools = {str(tool) for tool in tuple(called_tools or ()) if str(tool).strip()}
    blocked_tools = sorted(tools & {"get_orders_of_user_tool", "get_order_status_tool", "quick_order_tool"})
    if blocked_tools:
        return {
            "type": "general_card_cancel_timing_policy_used_order_lookup",
            "called_tools": blocked_tools,
            "response_shape_key": str(response_shape_key or ""),
        }
    response_text = str(assistant_response_text or "")
    if str(response_shape_key or "") == "order_cancel_status_summary" or "주문 상태를 확인해보니" in response_text:
        return {
            "type": "general_card_cancel_timing_policy_normalized_as_order_status_lookup",
            "response_shape_key": str(response_shape_key or ""),
        }
    return None


def _order_cancel_fee_inquiry_contract_violation(
    *,
    assistant_response_text: str | None,
    response_shape_key: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None:
        return None
    intent = str(contract.intent or "")
    response_text = str(assistant_response_text or "")
    tools = {str(tool) for tool in tuple(called_tools or ()) if str(tool).strip()}
    if intent == "owned_order_cancel_fee_inquiry":
        if response_text.startswith("제가 직접 주문을 취소 처리할 수는 없어요"):
            return {
                "type": "owned_order_cancel_fee_inquiry_normalized_as_cancel_request",
                "response_shape_key": str(response_shape_key or ""),
            }
        return None
    if intent != "general_cancel_fee_policy":
        return None
    owned_lookup_tools = {"get_my_reservations_tool", "get_orders_of_user_tool", "get_order_status_tool"}
    if tools & owned_lookup_tools:
        return {
            "type": "general_cancel_fee_policy_used_order_lookup",
            "response_shape_key": str(response_shape_key or ""),
            "called_tools": sorted(tools & owned_lookup_tools),
        }
    if response_text.startswith("제가 직접 주문을 취소 처리할 수는 없어요"):
        return {
            "type": "general_cancel_fee_policy_normalized_as_cancel_request",
            "response_shape_key": str(response_shape_key or ""),
        }
    if re.search(r"최근\s*(?:온라인\s*)?(?:주문|예약)|확인된\s*온라인\s*주문(?:/예약)?\s*1건", response_text):
        return {
            "type": "general_cancel_fee_policy_asserted_recent_order_state",
            "response_shape_key": str(response_shape_key or ""),
        }
    if (
        re.search(r"주문\s*상세|취소\s*가능", response_text)
        and not re.search(r"위약금|수수료|비용|배송비|택배비", response_text)
    ):
        return {
            "type": "general_cancel_fee_policy_missing_fee_explanation",
            "response_shape_key": str(response_shape_key or ""),
        }
    return None


def _stock_contract_violation(
    *,
    template: str | None,
    assistant_response_source: str | None,
    response_shape_key: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None or str(contract.intent or "") != "stock_store_search":
        return None
    stock_check_mode = str(contract.known_slots.get("stock_check_mode") or "")
    called_tools = tuple(str(tool) for tool in tuple(called_tools or ()) if str(tool).strip())
    event = {
        "template": str(template or ""),
        "called_tools": list(called_tools),
        "data": {"metadata": {"sourceTool": "transaction_store_preview_tool"}}
        if "transaction_store_preview_tool" in called_tools
        else {},
    }
    if stock_check_mode == "inventory_only" and _is_purchase_bound_preview_event(event, contract):
        return None
    if stock_check_mode == "inventory_only":
        if str(response_shape_key or "") == "transaction_fallback" and not called_tools:
            return {
                "type": "stock_contract_fell_back_without_resolution",
                "assistant_response_source": str(assistant_response_source or ""),
                "response_shape_key": str(response_shape_key or ""),
                "called_tools": [],
            }
        if not called_tools:
            return {
                "type": "inventory_tool_missing_for_stock_contract",
                "assistant_response_source": str(assistant_response_source or ""),
                "response_shape_key": str(response_shape_key or ""),
            }
        if any(tool == "transaction_store_preview_tool" for tool in called_tools):
            return {
                "type": "unexpected_preview_tool_for_inventory_only_stock",
                "called_tools": list(called_tools),
            }
        if str(template or "") == "datepick":
            return {
                "type": "forbidden_datepick_for_inventory_only_stock",
                "response_shape_key": str(response_shape_key or ""),
            }
    if (
        stock_check_mode == "preview"
        and str(template or "") == "datepick"
        and contract.known_slots.get("goods_no")
        and (contract.known_slots.get("ord_qty") or contract.known_slots.get("quantity"))
        and "get_store_schedule_tool" in called_tools
        and "transaction_store_preview_tool" not in called_tools
        and not _is_selected_store_schedule_continuation_contract(contract)
    ):
        return {
            "type": "datepick_without_product_conditioned_preview_tool",
            "called_tools": list(called_tools),
            "response_shape_key": str(response_shape_key or ""),
        }
    if str(response_shape_key or "") == "transaction_fallback":
        return {
            "type": "stock_contract_fell_back_without_resolution",
            "assistant_response_source": str(assistant_response_source or ""),
        }
    return None


def _quick_order_execute_contract_violation(
    *,
    template: str | None,
    assistant_response_text: str | None,
    assistant_response_source: str | None,
    response_shape_key: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    tool_inputs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None,
    structured_sources: list[tuple[str, Mapping[str, Any]]] | tuple[tuple[str, Mapping[str, Any]], ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None:
        return None
    is_execute_contract = str(contract.intent or "") == "quick_order_execute"
    is_execute_planner_drift = (
        str(contract.planner_intent or "") == "quick_order_execute"
        and str(contract.intent or "") == "quick_order_reservation"
        and _has_quick_order_execute_slots(contract.known_slots)
    )
    if not (is_execute_contract or is_execute_planner_drift):
        return None
    called_tools = tuple(str(tool) for tool in tuple(called_tools or ()) if str(tool).strip())
    if "quick_order_tool" not in called_tools:
        if str(template or "") == "orderComplete":
            return {
                "type": "order_complete_without_quick_order_tool",
                "assistant_response_source": str(assistant_response_source or ""),
                "response_shape_key": str(response_shape_key or ""),
            }
        return {
            "type": "quick_order_execute_without_tool",
            "assistant_response_source": str(assistant_response_source or ""),
            "response_shape_key": str(response_shape_key or ""),
            "template": str(template or ""),
            "assistant_response_text": str(assistant_response_text or "")[:160],
        }
    if str(template or "") == "orderComplete" and not _has_successful_quick_order_tool_result(
        tool_inputs=tool_inputs,
        structured_sources=structured_sources,
    ):
        return {
            "type": "order_complete_without_successful_quick_order_tool",
            "assistant_response_source": str(assistant_response_source or ""),
            "response_shape_key": str(response_shape_key or ""),
        }
    if str(response_shape_key or "") == "transaction_fallback":
        return {
            "type": "quick_order_execute_fell_back_without_resolution",
            "assistant_response_source": str(assistant_response_source or ""),
        }
    return None


def _has_successful_quick_order_tool_result(
    *,
    tool_inputs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None,
    structured_sources: list[tuple[str, Mapping[str, Any]]] | tuple[tuple[str, Mapping[str, Any]], ...] | None,
) -> bool:
    for tool_name, output in tuple(structured_sources or ()):
        if tool_name == "quick_order_tool" and _is_successful_tool_output(output):
            return True
    for tool_input in tuple(tool_inputs or ()):
        if str(tool_input.get("tool") or "") != "quick_order_tool":
            continue
        output = tool_input.get("data") or tool_input.get("output") or tool_input.get("result")
        if isinstance(output, Mapping) and _is_successful_tool_output(output):
            return True
    return False


def _is_successful_tool_output(output: Mapping[str, Any]) -> bool:
    return str(output.get("status") or "").lower() == "success"


def _quick_order_reservation_contract_violation(
    *,
    template: str | None,
    assistant_response_text: str | None,
    assistant_response_source: str | None,
    response_shape_key: str | None,
    called_tools: list[str] | tuple[str, ...] | None,
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None:
        return None
    if str(contract.intent or "") != "quick_order_reservation" and str(contract.known_slots.get("goal_type") or "") != "place_order":
        return None
    quantity = contract.known_slots.get("ord_qty") or contract.known_slots.get("quantity")
    try:
        has_quantity = int(quantity or 0) > 0
    except (TypeError, ValueError):
        has_quantity = bool(quantity)
    has_price = has_price_basis(contract.known_slots)
    if (
        template == "preOrder"
        and str(assistant_response_source or "") == "code_reservation_confirmation_ready"
        and str(response_shape_key or "") == "reservation_confirmation_ready"
        and not has_price
    ):
        return {
            "type": "preorder_without_price_basis",
            "assistant_response_source": str(assistant_response_source or ""),
            "response_shape_key": str(response_shape_key or ""),
        }
    is_ready_preorder_summary = bool(
        str(assistant_response_source or "") == "code_reservation_confirmation_ready"
        and str(response_shape_key or "") == "reservation_confirmation_ready"
        and str(contract.flow_step or "") == "build_preorder"
        and str(contract.action_mode or "") == "purchase_continuation"
        and contract.known_slots.get("goods_no")
        and (contract.known_slots.get("tire_size") or contract.known_slots.get("product_name") or contract.known_slots.get("tire_model"))
        and contract.known_slots.get("shop_id")
        and (contract.known_slots.get("shop_name") or contract.known_slots.get("store_name"))
        and contract.known_slots.get("requested_cal_day")
        and contract.known_slots.get("rsv_hour")
        and has_quantity
        and has_price
    )
    if template == "preOrder" and is_ready_preorder_summary:
        return None
    called_tools = tuple(str(tool) for tool in tuple(called_tools or ()) if str(tool).strip())
    if called_tools:
        return None
    response_text = str(assistant_response_text or "")
    if str(response_shape_key or "") == "transaction_fallback" or _ORDER_PROGRESS_ONLY_RE.search(response_text):
        return {
            "type": "quick_order_reservation_progress_without_tool",
            "assistant_response_source": str(assistant_response_source or ""),
            "response_shape_key": str(response_shape_key or ""),
            "assistant_response_text": response_text[:160],
        }
    return None


def _has_quick_order_execute_slots(slots: Mapping[str, Any] | None) -> bool:
    if not isinstance(slots, Mapping):
        return False
    quantity = slots.get("ord_qty") or slots.get("quantity")
    try:
        has_quantity = int(quantity or 0) > 0
    except (TypeError, ValueError):
        has_quantity = bool(quantity)
    return bool(
        slots.get("goods_no")
        and slots.get("shop_id")
        and slots.get("requested_cal_day")
        and slots.get("rsv_hour")
        and has_quantity
    )


def _comparison_metric_row_label(metric: str) -> str:
    return {
        "release": "출시 시점",
        "price": "최종 혜택가",
        "grade": "상품 등급",
        "price_grade": "상품 등급",
        "mileage": "마일리지/수명",
        "noise": "정숙성",
        "fuel_efficiency": "연비/회전저항",
        "wet": "빗길 성능",
        "car_type": "차종",
        "detail": "특징",
    }.get(str(metric or ""), "")


def _router_wins_information_intent(
    *,
    user_text: str = "",
    planner_intent: str | None,
    policy_intent: str,
    routing_result: Any | None,
    intent_frame: IntentFrame | None = None,
    response_decision: ResponseDecision | None = None,
    action_mode: str = "",
) -> str | None:
    comparison_intent = _comparison_router_wins_intent(
        routing_result=routing_result,
        intent_frame=intent_frame,
        response_decision=response_decision,
        action_mode=action_mode,
    )
    if comparison_intent:
        return comparison_intent
    candidates = (
        str(policy_intent or "").strip(),
        str(planner_intent or "").strip(),
        str(getattr(intent_frame, "intent", "") or "").strip(),
    )
    for candidate in candidates:
        if not candidate or candidate == "none" or candidate in _ROUTER_WINS_EXECUTION_EXCLUDED_INTENTS:
            continue
        if candidate in _OWNED_WARRANTY_LOOKUP_INTENTS:
            return "owned_warranty_lookup"
        if candidate == "payment_error_troubleshooting" and _is_payment_error_policy_overmatch(user_text):
            continue
        if candidate in ROUTER_WINS_INFORMATIONAL_INTENTS:
            return candidate
        if candidate.endswith("_policy") or candidate.endswith("_guidance"):
            return candidate
    complaint_scope = str(getattr(routing_result, "complaint_scope", "") or "").strip()
    if complaint_scope == "tstation_service_complaint":
        return "tstation_service_complaint"
    return None


def _router_wins_current_turn_intent(
    *,
    user_text: str = "",
    planner_intent: str | None,
    policy_intent: str,
    routing_result: Any | None,
    intent_frame: IntentFrame | None = None,
    response_decision: ResponseDecision | None = None,
    action_mode: str = "",
) -> str | None:
    informational_intent = _router_wins_information_intent(
        user_text=user_text,
        planner_intent=planner_intent,
        policy_intent=policy_intent,
        routing_result=routing_result,
        intent_frame=intent_frame,
        response_decision=response_decision,
        action_mode=action_mode,
    )
    if informational_intent:
        return informational_intent
    candidates = (
        str(policy_intent or "").strip(),
        str(planner_intent or "").strip(),
    )
    for candidate in candidates:
        if candidate in ROUTER_WINS_EXECUTION_BOUNDARY_INTENTS:
            return candidate
    return None


def _should_normalize_dot_manufacture_date_policy(
    *,
    user_text: str,
    policy_intent: str | None = None,
    planner_intent: str | None = None,
    code_intent: str | None = None,
) -> bool:
    candidates = {
        str(policy_intent or "").strip(),
        str(planner_intent or "").strip(),
        str(code_intent or "").strip(),
    }
    if "tire_quality_warranty_policy" not in candidates:
        return False
    return _is_tire_manufacture_date_question(user_text)


def _is_payment_error_policy_overmatch(user_text: str | None) -> bool:
    text = str(user_text or "")
    return (
        _CARD_INSTALLMENT_LOOKUP_RE.search(text) is not None
        or _PAYMENT_TROUBLESHOOTING_RE.search(text) is None
        or _PAYMENT_METHOD_OR_COUPON_POLICY_RE.search(text) is not None
    )


def _transaction_policy_boundary_frame(*, user_text: str, merged_slots: Any | None) -> IntentFrame | None:
    frame = build_transaction_intent_frame(user_text, known_slots=_slots_from_model(merged_slots))
    if frame.intent in {"general_cancel_fee_policy", "owned_order_cancel_fee_inquiry"}:
        return frame
    return None


def _should_apply_transaction_policy_boundary(
    *,
    planner_intent: str | None,
    policy_intent: str,
    code_intent: str | None,
    code_domain: str | None,
) -> bool:
    candidates = {
        str(planner_intent or "").strip(),
        str(policy_intent or "").strip(),
        str(code_intent or "").strip(),
    }
    if candidates & {"product_recommendation", "sized_product_recommendation"}:
        return True
    return str(code_domain or "").strip() in {"", "discovery"} and not any(candidates)


def _should_force_card_installment_lookup_intent(
    *,
    user_text: str,
    planner_intent: str | None,
    policy_intent: str | None,
    code_intent: str | None,
    domain: str | None,
    planner_domains: tuple[str, ...],
) -> bool:
    text = str(user_text or "")
    if _is_tire_manufacture_date_question(text, include_candidate_terms=True):
        return False
    if _CARD_INSTALLMENT_LOOKUP_RE.search(text) is None:
        return False
    if _PAYMENT_TROUBLESHOOTING_RE.search(text) is not None:
        return False
    candidates = {
        str(planner_intent or "").strip(),
        str(policy_intent or "").strip(),
        str(code_intent or "").strip(),
        str(domain or "").strip(),
        *(str(item or "").strip() for item in planner_domains),
    }
    if "card_installment_lookup" in candidates:
        return True
    return "support" in candidates or "payment_error_troubleshooting" in candidates


def _comparison_router_wins_intent(
    *,
    routing_result: Any | None,
    intent_frame: IntentFrame | None,
    response_decision: ResponseDecision | None,
    action_mode: str,
) -> str | None:
    frame_entities = intent_frame.entities if intent_frame is not None else {}
    response_metadata = response_decision.metadata if response_decision is not None else {}
    comparison_followup_intent = str(
        getattr(routing_result, "comparison_followup_intent", None)
        or frame_entities.get("comparison_followup_intent")
        or response_metadata.get("comparison_followup_intent")
        or ""
    ).strip()
    comparison_metric = str(
        getattr(routing_result, "comparison_metric", None)
        or frame_entities.get("compare_metric")
        or response_metadata.get("compare_metric")
        or ""
    ).strip()
    response_shape_key = str(response_metadata.get("response_shape_key") or "").strip()
    routed_action_mode = str(getattr(routing_result, "action_mode", "") or "").strip()
    current_action_mode = str(action_mode or "").strip()
    frame_intent = str(getattr(intent_frame, "intent", "") or "").strip()
    if (
        frame_entities.get("multi_product_description_request")
        and frame_intent in {"product_search", "product_description"}
        and comparison_followup_intent == "generic_compare"
        and comparison_metric in {"", "none", "detail"}
        and response_shape_key in {"", "neutral_product_description", "product_search_summary"}
    ):
        return None
    if comparison_followup_intent in _COMPARISON_ROUTER_WINS_FOLLOWUP_INTENTS:
        return "product_comparison"
    if comparison_metric and comparison_metric != "none":
        return "product_comparison"
    if current_action_mode == "product_comparison" or routed_action_mode == "product_comparison":
        return "product_comparison"
    if response_shape_key in _COMPARISON_ROUTER_WINS_RESPONSE_SHAPES:
        return "product_comparison"
    return None


def _router_wins_domain(intent: str, planner_domains: tuple[str, ...]) -> str:
    if intent in {
        "product_detail_lookup",
        "product_description",
        "product_comparison",
        "product_size_list_lookup",
        "competitor_counterpart_guidance",
    }:
        return "discovery"
    if intent in ROUTER_WINS_INFORMATIONAL_INTENTS or intent.endswith("_policy") or intent.endswith("_guidance"):
        return "support"
    if intent in _OWNED_WARRANTY_LOOKUP_INTENTS:
        return "support"
    if intent in ROUTER_WINS_EXECUTION_BOUNDARY_INTENTS:
        return "transaction"
    return planner_domains[0] if planner_domains else "support"


def _router_wins_tool_boundary(intent: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if intent == "stock_store_search":
        allowed_tools = (
            "transaction_store_preview_tool",
            "search_stores_tool",
            "search_stores_complex_tool",
            "get_store_list_tool",
            "get_nearby_stores_tool",
        )
        return (
            allowed_tools,
            tuple(
                tool
                for tool in _ROUTER_WINS_ORDER_EXECUTION_FORBIDDEN_TOOLS
                | {
                    "get_store_schedule_tool",
                    "get_multi_store_schedule_tool",
                }
                if tool not in allowed_tools
            ),
        )
    if intent == "store_search":
        allowed_tools = (
            "get_store_list_tool",
            "search_stores_tool",
            "search_stores_complex_tool",
            "get_nearby_stores_tool",
        )
        return (
            allowed_tools,
            tuple(
                tool
                for tool in _ROUTER_WINS_ORDER_EXECUTION_FORBIDDEN_TOOLS
                | {
                    "transaction_store_preview_tool",
                    "get_store_schedule_tool",
                    "get_multi_store_schedule_tool",
                    "get_store_inventory_tool",
                    "get_logistics_inventory_tool",
                }
                if tool not in allowed_tools
            ),
        )
    if intent == "store_schedule":
        return (
            ("get_store_schedule_tool",),
            tuple(
                tool
                for tool in _ROUTER_WINS_ORDER_EXECUTION_FORBIDDEN_TOOLS
                | _STORE_SERVICE_SEARCH_TOOLS
                | {
                    "transaction_store_preview_tool",
                    "get_store_inventory_tool",
                    "get_logistics_inventory_tool",
                    "get_multi_store_schedule_tool",
                }
                if tool != "get_store_schedule_tool"
            ),
        )
    if intent == "store_service_search":
        allowed_tools = tuple(_STORE_SERVICE_SEARCH_TOOLS)
        return (
            allowed_tools,
            tuple(
                tool
                for tool in _ROUTER_WINS_ORDER_EXECUTION_FORBIDDEN_TOOLS
                | {
                    "transaction_store_preview_tool",
                    "get_store_schedule_tool",
                    "get_multi_store_schedule_tool",
                    "get_store_inventory_tool",
                    "get_logistics_inventory_tool",
                }
                if tool not in allowed_tools
            ),
        )
    if intent == "store_recommendation_by_vehicle_experience":
        allowed_tools = (
            "search_stores_complex_tool",
            "search_stores_tool",
            "get_store_list_tool",
            "get_nearby_stores_tool",
        )
        return (
            allowed_tools,
            tuple(
                tool
                for tool in _ROUTER_WINS_ORDER_EXECUTION_FORBIDDEN_TOOLS
                | {
                    "transaction_store_preview_tool",
                    "get_store_schedule_tool",
                    "get_multi_store_schedule_tool",
                    "get_store_inventory_tool",
                    "get_logistics_inventory_tool",
                }
                if tool not in allowed_tools
            ),
        )
    if intent == "open_store_search":
        allowed_tools = (
            "search_stores_tool",
            "search_stores_complex_tool",
            "get_store_list_tool",
            "get_nearby_stores_tool",
        )
        return (
            allowed_tools,
            tuple(
                tool
                for tool in _ROUTER_WINS_ORDER_EXECUTION_FORBIDDEN_TOOLS
                | {
                    "get_store_schedule_tool",
                    "get_multi_store_schedule_tool",
                    "transaction_store_preview_tool",
                    "get_store_inventory_tool",
                    "get_logistics_inventory_tool",
                }
                if tool not in allowed_tools
            ),
        )
    if intent == "product_size_list_lookup":
        return (
            ("search_product_tool",),
            tuple(
                tool
                for tool in _ROUTER_WINS_TRANSACTION_FORBIDDEN_TOOLS
                | {"get_products_recommendations_tool", "get_product_description_tool"}
                if tool != "search_product_tool"
            ),
        )
    if intent in {"product_detail_lookup", "product_description"}:
        return (
            ("search_product_tool", "get_product_description_tool"),
            tuple(
                tool
                for tool in _ROUTER_WINS_TRANSACTION_FORBIDDEN_TOOLS | {"get_products_recommendations_tool"}
                if tool not in {"search_product_tool", "get_product_description_tool"}
            ),
        )
    if intent == "product_comparison":
        return (
            ("search_product_tool", "get_product_description_tool", "get_cheapest_price_tool"),
            tuple(
                tool
                for tool in _ROUTER_WINS_TRANSACTION_FORBIDDEN_TOOLS | {"get_products_recommendations_tool"}
                if tool not in {"search_product_tool", "get_product_description_tool", "get_cheapest_price_tool"}
            ),
        )
    if intent == "competitor_counterpart_guidance":
        return (
            (),
            tuple(
                tool
                for tool in _ROUTER_WINS_TRANSACTION_FORBIDDEN_TOOLS
                | {
                    "search_faq_hybrid_tool",
                    "search_faq_rag_tool",
                    "get_faq_tool",
                    "search_product_tool",
                    "get_product_description_tool",
                    "get_products_recommendations_tool",
                }
            ),
        )
    if intent == "human_escalation":
        return (
            ("transfer_to_qna_tool",),
            tuple(
                tool
                for tool in _ROUTER_WINS_TRANSACTION_FORBIDDEN_TOOLS
                | {"search_faq_hybrid_tool", "search_faq_rag_tool", "get_faq_tool"}
                if tool != "transfer_to_qna_tool"
            ),
        )
    if intent == "tstation_service_complaint":
        return (
            ("search_faq_hybrid_tool", "transfer_to_qna_tool"),
            tuple(
                tool
                for tool in _ROUTER_WINS_TRANSACTION_FORBIDDEN_TOOLS
                if tool not in {"search_faq_hybrid_tool", "transfer_to_qna_tool"}
            ),
        )
    if intent in _OWNED_WARRANTY_LOOKUP_INTENTS:
        return (
            ("get_my_warranties_tool",),
            tuple(
                tool
                for tool in _ROUTER_WINS_TRANSACTION_FORBIDDEN_TOOLS
                | {"search_faq_hybrid_tool", "transfer_to_qna_tool"}
                if tool != "get_my_warranties_tool"
            ),
        )
    if intent == "card_installment_lookup":
        allowed_tools = ("get_card_installments_tool",)
        return (
            allowed_tools,
            tuple(
                tool
                for tool in _ROUTER_WINS_TRANSACTION_FORBIDDEN_TOOLS
                | {"search_faq_hybrid_tool", "transfer_to_qna_tool"}
                if tool not in allowed_tools
            ),
        )
    if intent in _SUPPORT_FAQ_POLICY_TOOL_INTENTS:
        return (
            _SUPPORT_SAFE_AGENT_TOOLS,
            tuple(tool for tool in _ROUTER_WINS_TRANSACTION_FORBIDDEN_TOOLS if tool not in _SUPPORT_SAFE_AGENT_TOOLS),
        )
    if intent == "coupon_stacking_policy":
        allowed_tools = ("get_my_coupons_tool", "check_coupon_stacking_tool")
        return (
            allowed_tools,
            tuple(
                tool
                for tool in _ROUTER_WINS_TRANSACTION_FORBIDDEN_TOOLS
                | {
                    "issue_coupon_tool",
                    "search_product_tool",
                    "get_product_description_tool",
                    "get_coupon_applicable_products_tool",
                    "get_final_price_tool",
                    "search_faq_hybrid_tool",
                }
                if tool not in allowed_tools
            ),
        )
    return (
        ("search_faq_hybrid_tool",),
        tuple(tool for tool in _ROUTER_WINS_TRANSACTION_FORBIDDEN_TOOLS if tool != "search_faq_hybrid_tool"),
    )


def _router_wins_response_shape_key(intent: str) -> str:
    return {
        "product_detail_lookup": "neutral_product_description",
        "product_description": "neutral_product_description",
        "product_comparison": "metric_comparison_summary",
        "product_size_list_lookup": "product_size_list_lookup",
        "competitor_counterpart_guidance": "competitor_counterpart_guidance",
        "tstation_service_complaint": "support_complaint_guidance",
        "owned_warranty_lookup": "owned_warranty_lookup",
    }.get(intent, intent)


def _response_shape_key(response_decision_payload: Mapping[str, Any] | None) -> str:
    metadata = response_decision_payload.get("metadata") if isinstance(response_decision_payload, Mapping) else None
    if isinstance(metadata, Mapping):
        return str(metadata.get("response_shape_key") or "")
    return ""


def _router_wins_response_decision(intent: str) -> dict[str, Any]:
    response_shape_key = _router_wins_response_shape_key(intent)
    response_shape = "summary"
    template = "quickReply"
    forbidden_behaviors = [
        "resume_stale_transaction_flow",
        "start_owned_record_lookup",
        "normalize_as_purchase_or_schedule",
    ]
    if intent == "stock_store_search":
        response_shape = "location"
        template = "location"
        guidance = "현재 턴의 재고/장착 가능 매장 검색만 수행한다. 주문 확정, 장바구니, 예약 실행으로 조기 전환하지 않는다."
        forbidden_behaviors = [
            "resume_stale_transaction_flow",
            "start_quick_order_execution",
            "emit_preorder_without_user_confirmation",
            "emit_order_complete_without_quick_order_tool",
            "emit_datepick_before_store_selection",
        ]
    elif intent == "store_schedule":
        response_shape = "date_pick"
        template = "datepick"
        guidance = "현재 턴의 매장 예약 가능 시간 조회만 수행한다. 주문 확정이나 매장 목록 반복으로 전환하지 않는다."
        forbidden_behaviors = [
            "resume_stale_transaction_flow",
            "start_quick_order_execution",
            "loop_store_preview_instead_of_schedule",
            "emit_preorder_without_user_confirmation",
            "emit_order_complete_without_quick_order_tool",
        ]
    elif intent in {"store_search", "open_store_search", "store_service_search", "store_recommendation_by_vehicle_experience"}:
        response_shape = "location"
        template = "location"
        guidance = "현재 턴의 매장 검색 intent 기준으로 매장을 조회한다. 주문/가격/쿠폰/예약 실행 flow로 전환하지 않는다."
        forbidden_behaviors = [
            "resume_stale_transaction_flow",
            "datepick_for_store_search_flow",
            "start_quick_order_execution",
            "start_price_or_coupon_execution",
            "emit_preorder_without_user_confirmation",
            "emit_order_complete_without_quick_order_tool",
        ]
    elif intent in {"product_detail_lookup", "product_description"}:
        guidance = "현재 턴의 상품 설명 의도에 맞춰 상품 정보/특징을 요약한다. 추천/구매/매장 흐름으로 전환하지 않는다."
    elif intent == "product_comparison":
        guidance = "현재 턴의 비교 대상 상품만 구분해 비교한다. 같은 goods_no 두 번 비교하거나 이전 추천 정책으로 응답하지 않는다."
    elif intent == "product_size_list_lookup":
        guidance = "현재 턴의 사이즈 목록 조회 의도에 맞춰 search_product_tool 결과의 규격 목록을 안내한다."
    elif intent == "tstation_service_complaint":
        guidance = "T-Station 범위의 불편 사항으로 응답하고, 이전 구매/예약/매장 문맥이 실행 flow를 재개하지 않게 한다."
    elif intent == "human_escalation":
        response_shape = "action_confirm"
        template = "qnaComplete"
        guidance = "사용자가 명시적으로 1:1 문의/상담원 연결을 요청했으므로 transfer_to_qna_tool로 문의 접수 링크를 생성한다."
        forbidden_behaviors = [
            "overpromise_live_agent",
            "hide_official_contact",
        ]
    elif intent in _OWNED_WARRANTY_LOOKUP_INTENTS:
        guidance = (
            "사용자가 본인 안심서비스/워런티 가입 여부 확인을 요청한 턴은 get_my_warranties_tool로 보유 워런티를 조회한다. "
            "이전 불만/정책 문맥만으로 FAQ 안내나 1:1 문의로 전환하지 않는다."
        )
        forbidden_behaviors = [
            "answer_without_owned_warranty_lookup",
            "normalize_as_service_complaint",
            "transfer_to_qna_direct_first",
        ]
    elif intent == "card_installment_lookup":
        guidance = (
            "카드사별 무이자 할부 문의는 search_faq_hybrid_tool이 아니라 get_card_installments_tool로만 처리한다. "
            "카드사/개월수/스마트페이 여부에 맞춰 결과를 필터링하고, 일반 카드 무이자와 스마트페이 개월수는 합산하지 않는다."
        )
        forbidden_behaviors = [
            "route_to_payment_error_troubleshooting",
            "generic_faq_answer",
            "merge_general_and_smartpay_installments",
        ]
    elif intent == "coupon_stacking_policy":
        response_shape = "clarify"
        guidance = (
            "쿠폰 중복 사용 가능 여부는 일반 FAQ로 답하지 말고, 보유 쿠폰 목록에서 사용자가 말한 쿠폰을 "
            "특정한 뒤 check_coupon_stacking_tool 판정값으로만 안내한다. 쿠폰이 특정되지 않으면 비교할 쿠폰을 되묻는다."
        )
        forbidden_behaviors = [
            "generic_faq_answer",
            "infer_stacking_without_tool",
            "start_product_coupon_applicability_lookup",
        ]
    else:
        guidance = "현재 턴의 FAQ/정책 intent 기준으로 안내하고 개인 조회, 구매, 예약 실행 flow로 전환하지 않는다."
    return {
        "response_shape": response_shape,
        "template": template,
        "required_slots": [],
        "forbidden_behaviors": forbidden_behaviors,
        "assistant_guidance": guidance,
        "metadata": {"response_shape_key": response_shape_key},
    }


def _router_wins_response_decision_mismatch(intent: str, response_decision_payload: Mapping[str, Any] | None) -> bool:
    if response_decision_payload is None:
        return True
    response_shape_key = _response_shape_key(response_decision_payload)
    expected = _router_wins_response_shape_key(intent)
    if intent == "product_comparison":
        return response_shape_key not in {"metric_comparison_summary", "grade_comparison_summary", expected}
    if intent in {"product_detail_lookup", "product_description"}:
        return response_shape_key not in {"neutral_product_description", "product_description_answer", expected}
    return response_shape_key != expected


def _response_policy_source(response_decision_payload: Mapping[str, Any] | None) -> str:
    return "response_decision" if response_decision_payload is not None else "none"


def _best_seller_response_decision_payload() -> dict[str, Any]:
    return {
        "response_shape": "card",
        "template": "product",
        "required_slots": [],
        "forbidden_behaviors": [
            "use_generic_recommendation_engine",
            "expose_sales_count",
        ],
        "assistant_guidance": "요청 기간/차종 기준 베스트셀러 도구 결과를 product 카드로 안내하고 판매 수량은 노출하지 않는다.",
        "metadata": {"response_shape_key": "best_seller_product_cards"},
    }


def _stale_context_usage(*, router_wins_intent: str | None, context_state: str) -> str | None:
    if not router_wins_intent:
        return None
    if str(context_state or "") == "dormant":
        return "known_slots_only"
    return "current_intent_supporting_evidence"


def _domain_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "unknown")


def _domain_from_routing(routing_result: Any | None) -> str:
    domains = getattr(routing_result, "domains", None)
    if domains:
        return _domain_value(domains[0])
    return "unknown"


def _planner_domains(routing_result: Any | None, plan: CrossDomainPlan | None) -> tuple[str, ...]:
    domains = getattr(routing_result, "domains", None)
    if domains:
        return tuple(_domain_value(domain) for domain in domains)
    if plan is not None:
        return (_domain_value(plan.primary_domain),)
    return ()


def _is_discovery_first_leg_transaction_contract(contract: TurnContract | None) -> bool:
    if contract is None:
        return False
    if not contract.planner_domains or contract.planner_domains[0] != "discovery":
        return False
    if "transaction" in contract.planner_domains[1:]:
        return True
    return any(str(item).strip().startswith("transaction:") for item in contract.execution_plan)


def _is_discovery_first_leg_transaction_violation(
    event: Mapping[str, Any],
    contract: TurnContract | None,
) -> bool:
    if not _is_discovery_first_leg_transaction_contract(contract):
        return False
    if str(event.get("source_domain") or "").lower() != "discovery":
        return False
    if str(event.get("template") or "") != "quickReply":
        return False
    response_shape_key = str(event.get("response_shape_key") or "")
    assistant_response_source = str(event.get("assistant_response_source") or "")
    assistant_response_text = str(event.get("assistant_response_text") or "")
    if not assistant_response_text:
        data = event.get("data")
        if isinstance(data, Mapping):
            assistant_response_text = str(data.get("assistantResponse") or "")
    if assistant_response_source == "discovery_agent" and _DISCOVERY_NO_RESULT_RE.search(assistant_response_text):
        return False
    if (
        assistant_response_source == "code_product_compare_resolver"
        and response_shape_key in {"metric_comparison_summary", "grade_comparison_summary"}
    ):
        return False
    called_tools = tuple(str(tool) for tool in tuple(event.get("called_tools") or ()))
    if any(tool.startswith("get_final_price_tool") or tool.startswith("get_store") or tool.startswith("quick_order") for tool in called_tools):
        return False
    return (
        response_shape_key in _DISCOVERY_FIRST_LEG_BLOCK_RESPONSE_SHAPES
        or assistant_response_source in _DISCOVERY_FIRST_LEG_BLOCK_SOURCES
    )


def _is_unsupported_discovery_product_template_without_current_source(
    event: Mapping[str, Any],
    contract: TurnContract | None,
) -> bool:
    if contract is None:
        return False
    if str(event.get("template") or "") != "product":
        return False
    if str(event.get("source_domain") or "").lower() != "discovery":
        return False
    response_decision = contract.response_decision or {}
    forbidden_behaviors = response_decision.get("forbidden_behaviors") if isinstance(response_decision, Mapping) else ()
    if not isinstance(forbidden_behaviors, list | tuple) or not forbidden_behaviors:
        return False
    forbidden_set = {str(item) for item in forbidden_behaviors}
    if not any("product" in _FORBIDDEN_BEHAVIOR_TEMPLATE_BLOCKS.get(behavior, ()) for behavior in forbidden_set):
        return False
    called_tools = {str(tool) for tool in tuple(event.get("called_tools") or ()) if str(tool).strip()}
    if called_tools & _DISCOVERY_PRODUCT_SOURCE_TOOLS:
        return False
    return True


def _truncated_policy_response_violation(
    *,
    event: Mapping[str, Any],
    contract: TurnContract | None,
) -> dict[str, Any] | None:
    if contract is None:
        return None
    intent = str(contract.intent or "")
    if not (
        contract.domain == "support"
        or intent.endswith("_policy")
        or intent.endswith("_guidance")
        or intent in _FAQ_FIRST_SUPPORT_POLICY_INTENTS
    ):
        return None
    response_text = str(event.get("assistant_response_text") or "").strip()
    data = event.get("data")
    if not response_text and isinstance(data, Mapping):
        response_text = str(data.get("assistantResponse") or "").strip()
    if not response_text.endswith("..."):
        return None
    return {
        "type": "truncated_policy_response",
        "response_shape_key": str(event.get("response_shape_key") or ""),
        "assistant_response_source": str(event.get("assistant_response_source") or ""),
    }


def _execution_plan(routing_result: Any | None, plan: CrossDomainPlan | None) -> tuple[str, ...]:
    raw_plan = getattr(routing_result, "execution_plan", None)
    if raw_plan:
        return tuple(str(item) for item in raw_plan if str(item).strip())
    if plan is not None:
        return tuple(f"{task.domain.value}:{task.intent}" for task in plan.subtasks)
    return ()


def _planner_intent(routing_result: Any | None, plan: CrossDomainPlan | None) -> str | None:
    for item in _execution_plan(routing_result, plan):
        token = str(item).strip()
        if not token:
            continue
        if ":" in token:
            _, intent = token.split(":", 1)
            return _normalize_plan_intent(intent)
    return None


def _normalize_plan_intent(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    aliases = {
        "resolve_product": "resolve_or_describe_product",
        "continue_purchase": "quick_order_reservation",
        "quick_order_confirmed": "quick_order_execute",
        "product_compare_tool": "product_comparison",
        "metric_comparison_summary": "product_comparison",
        "grade_comparison_summary": "product_comparison",
        "transaction_price_stock": "price_or_coupon_check",
        "discovery_search": "resolve_or_describe_product",
        "promotion_lookup": "product_promotion_lookup",
        "promotions_lookup": "product_promotion_lookup",
        "product_promotion": "product_promotion_lookup",
        "product_promotions": "product_promotion_lookup",
        "product_coupon": "product_coupon_lookup",
        "product_coupons": "product_coupon_lookup",
        "coupon_lookup": "product_coupon_lookup",
        "deal_lookup": "product_deal_lookup",
        "product_deal": "product_deal_lookup",
        "event_lookup": "product_event_lookup",
        "product_event": "product_event_lookup",
        "discovery_event_content": "product_event_lookup",
        "get_best_selling_tires_for_vehicle": "best_seller_search",
        "get_best_selling_product_for_vehicle": "best_seller_search",
        "get_best_selling_products_for_vehicle_timeframe": "best_seller_search",
        "get_best_selling_products_for_vehicle": "best_seller_search",
        "best_seller_list_by_vehicle_and_size_and_period": "best_seller_search",
        "get_best_selling_tire_by_model_and_size": "best_seller_search",
        "get_best_selling_products_tool": "best_seller_search",
        "best_seller": "best_seller_search",
        "sales_rank": "best_seller_search",
        "query_order_data_for_vehicle_with_period": "best_seller_search",
        "verify_safe_service_subscription": "owned_warranty_lookup",
        "safe_service_subscription_lookup": "owned_warranty_lookup",
        "my_warranty_lookup": "owned_warranty_lookup",
        "best_seller_search_by_vehicle": "best_seller_search",
        "vehicle_best_seller_search": "best_seller_search",
        "order_data_for_vehicle": "best_seller_search",
        "connect_1to1_inquiry": "human_escalation",
        "1to1_inquiry_connect": "human_escalation",
        "connect_1_to_1_inquiry": "human_escalation",
        "one_to_one_inquiry_connect": "human_escalation",
        "one_to_one_inquiry": "human_escalation",
        "qna_request": "human_escalation",
        "qna_connect": "human_escalation",
        "connect_human_agent": "human_escalation",
    }
    return aliases.get(normalized, normalized or "unknown")


def _planner_best_seller_intent(value: str | None, *, user_text: str) -> str:
    normalized = _normalize_plan_intent(str(value or ""))
    if normalized in {"vehicle_tire_recommendation_prompt", "recommend_tire_for_vehicle"} and is_best_seller_request(
        user_text,
        include_demographic_preference=False,
    ):
        return "best_seller_search"
    return normalized


def _is_discovery_event_content_contract(
    routing_result: Any | None,
    planner_intent: str | None,
    code_intent: str | None,
) -> bool:
    event_intents = {
        "benefit_event_list_lookup",
        "benefit_deal_list",
        "product_event_lookup",
        "product_promotion_lookup",
        "product_coupon_lookup",
        "product_deal_lookup",
    }
    if planner_intent in event_intents or code_intent in event_intents:
        return True
    profile = str(getattr(getattr(routing_result, "agent_prompt_profile", None), "value", "") or "").lower()
    if profile == "discovery_event_content":
        return True
    plan_text = " ".join(str(item or "").lower() for item in (getattr(routing_result, "execution_plan", None) or ()))
    return any(
        token in plan_text
        for token in (
            "benefit_event_list_lookup",
            "benefit_deal_list",
            "product_event_lookup",
            "product_promotion_lookup",
            "product_coupon_lookup",
            "product_deal_lookup",
            "discovery_event_content",
        )
    )


def _planner_confidence(routing_result: Any | None) -> float | None:
    value = getattr(routing_result, "planner_confidence", None)
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return None


def _planner_source(routing_result: Any | None, plan: CrossDomainPlan | None) -> str:
    if routing_result is not None:
        return "router_llm"
    if plan is not None:
        return "cross_domain_policy"
    return "unknown"


def _referred_objects(routing_result: Any | None) -> dict[str, Any]:
    if routing_result is None:
        return {}
    return {
        "status": str(getattr(routing_result, "referred_object_status", "resolved") or "resolved"),
        "type": str(getattr(routing_result, "referred_object_type", "none") or "none"),
        "needs_clarification": bool(getattr(routing_result, "needs_clarification", False)),
    }


def _contract_drift(
    *,
    code_domain: str,
    code_intent: str,
    planner_domain: str,
    planner_intent: str | None,
) -> tuple[Mapping[str, Any], ...]:
    drift: list[Mapping[str, Any]] = []
    if planner_domain and planner_domain != "unknown" and code_domain != planner_domain:
        drift.append({
            "field": "domain",
            "planner": planner_domain,
            "code_frame": code_domain,
        })
    if planner_intent and planner_intent != "unknown" and code_intent != planner_intent:
        drift.append({
            "field": "intent",
            "planner": planner_intent,
            "code_frame": code_intent,
        })
    return tuple(drift)


def _intent_from_cross_domain(plan: CrossDomainPlan | None) -> str:
    if plan is None or not plan.subtasks:
        return "unknown"
    return plan.subtasks[0].intent


def _required_slots_from_cross_domain(plan: CrossDomainPlan | None) -> tuple[str, ...]:
    if plan is None:
        return ()
    slots: list[str] = []
    for task in plan.subtasks:
        slots.extend(task.required_slots)
    return tuple(slots)


def _resolvable_required_slots(
    required_slots: tuple[str, ...],
    plan: CrossDomainPlan | None,
    known_slots: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    if not required_slots:
        return ()
    resolvable: set[str] = set()
    if _has_discovery_product_resolution_task(plan):
        resolvable.update({"product", "goods_no"})
    if (
        isinstance(known_slots, Mapping)
        and str(known_slots.get("discovery_followup_action") or "")
        in {"vehicle_based_recommendation_refinement", "vehicle_resolved_recommendation"}
    ):
        resolvable.add("tire_size")
    return tuple(slot for slot in required_slots if slot in resolvable)


def _blocking_required_slots(
    user_text: str,
    required_slots: tuple[str, ...],
    resolvable_required_slots: tuple[str, ...],
    *,
    intent: str,
    routing_result: Any | None,
) -> tuple[str, ...]:
    blocking = [slot for slot in required_slots if slot not in set(resolvable_required_slots)]
    if _should_apply_reference_guard(
        user_text=user_text,
        intent=intent,
        routing_result=routing_result,
    ):
        referred = _referred_objects(routing_result)
        slot = _slot_for_referred_object_type(str(referred.get("type") or "none"))
        if slot not in blocking:
            blocking.append(slot)
    return tuple(blocking)


def _blocking_required_slots_source(
    *,
    user_text: str,
    intent: str,
    routing_result: Any | None,
    blocking_required_slots: tuple[str, ...],
) -> str:
    if not blocking_required_slots:
        return "none"
    if not _should_apply_reference_guard(
        user_text=user_text,
        intent=intent,
        routing_result=routing_result,
    ):
        return "current_intent"
    referred = _referred_objects(routing_result)
    referred_type = str(referred.get("type") or "reference")
    guard_slot = _slot_for_referred_object_type(referred_type)
    if guard_slot in blocking_required_slots:
        return f"current_intent+reference_guard:{referred_type}"
    return "current_intent"


def _is_blocking_reference(routing_result: Any | None, *, user_text: str = "", intent: str = "") -> bool:
    return _should_apply_reference_guard(
        user_text=user_text,
        intent=intent,
        routing_result=routing_result,
    )


def _has_blocking_reference(contract: TurnContract) -> bool:
    if _reference_guard_exempt_intent(contract.intent):
        return False
    referred_type = str(contract.referred_objects.get("type") or "none")
    if not (
        contract.referred_objects.get("needs_clarification")
        and contract.referred_objects.get("status") in {"missing", "ambiguous"}
    ):
        return False
    if referred_type == "none":
        return contract.has_reference_signal
    if referred_type == "store" and not contract.has_reference_signal:
        return False
    return True


def _reference_guard_exempt_routing_result(routing_result: Any | None) -> bool:
    if routing_result is None:
        return False
    domains = tuple(_domain_value(domain) for domain in (getattr(routing_result, "domains", None) or ()))
    if domains and domains != ("discovery",):
        return False
    plan_items = tuple(str(item or "").strip().lower() for item in (getattr(routing_result, "execution_plan", None) or ()))
    if any(
        any(token in item for token in _REFERENCE_GUARD_EXEMPT_DISCOVERY_PLAN_TOKENS)
        for item in plan_items
    ):
        return True
    profile = str(getattr(getattr(routing_result, "agent_prompt_profile", None), "value", "") or "").lower()
    return profile == "discovery_recommendation"


def _should_apply_reference_guard(
    *,
    user_text: str,
    intent: str,
    routing_result: Any | None,
) -> bool:
    if _OE_PART_NUMBER_REQUEST_RE.search(user_text or ""):
        return False
    if _reference_guard_exempt_intent(intent):
        return False
    if _reference_guard_exempt_routing_result(routing_result):
        return False
    referred = _referred_objects(routing_result)
    if not (
        referred.get("needs_clarification")
        and referred.get("status") in {"missing", "ambiguous"}
    ):
        return False
    referred_type = str(referred.get("type") or "none")
    if (
        referred_type in {"product", "product_set"}
        and is_best_seller_request(user_text, include_demographic_preference=False)
        and extract_best_seller_vehicle_query(user_text)
    ):
        return False
    has_reference_signal = _has_reference_signal(user_text)
    if referred_type == "none":
        return has_reference_signal
    if referred_type == "store" and not has_reference_signal:
        return False
    if has_reference_signal:
        return True
    return referred_type in {"product", "product_set", "order", "coupon"}


def _reference_guard_exempt_intent(intent: str) -> bool:
    normalized = str(intent or "").strip()
    if not normalized:
        return False
    if normalized in _REFERENCE_GUARD_EXEMPT_INTENTS:
        return True
    if normalized.endswith("_policy") or normalized.endswith("_guidance"):
        return True
    return False


def _should_lock_code_intent_contract(intent: str) -> bool:
    normalized = str(intent or "").strip()
    if not normalized:
        return False
    return _reference_guard_exempt_intent(normalized)


def _should_keep_registered_vehicle_information_contract(
    *,
    user_text: str,
    intent_frame: IntentFrame | None,
    code_intent: str,
) -> bool:
    if intent_frame is None:
        return False
    if _domain_value(intent_frame.domain) != "discovery":
        return False
    if str(code_intent or "").strip() != "product_description":
        return False
    if str(intent_frame.sub_intent or "").strip() != "vehicle_information":
        return False
    if _COUPON_ANCHOR_RE.search(user_text or ""):
        return False
    return has_registered_vehicle_ownership_signal(user_text)


def _slot_for_referred_object_type(object_type: str) -> str:
    return {
        "product": "product",
        "product_set": "product_set",
        "store": "store",
        "order": "order",
        "coupon": "coupon",
    }.get(object_type, "reference")


def _has_reference_signal(user_text: str) -> bool:
    return bool(_REFERENCE_SIGNAL_RE.search(str(user_text or "")))


def _slots_from_model(model: Any | None) -> dict[str, Any]:
    if model is None:
        return {}
    if hasattr(model, "model_dump"):
        return dict(model.model_dump())
    if isinstance(model, Mapping):
        return dict(model)
    return {
        name: getattr(model, name)
        for name in (
            "goods_no",
            "tire_model",
            "tire_size",
            "ord_qty",
            "shop_id",
            "shop_name",
            "region",
            "pending_intent",
            "goal_type",
        )
        if hasattr(model, name)
    }


def _recommendation_context_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_policy_dict"):
        try:
            return {key: item for key, item in value.to_policy_dict().items() if item not in (None, "")}
        except Exception:
            return {}
    if isinstance(value, Mapping):
        data = {key: item for key, item in value.items() if item not in (None, "")}
        if "recommendation_scenario" not in data and data.get("scenario"):
            data["recommendation_scenario"] = data.get("scenario")
        return data
    return {}


def _compact_slots(slots: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in slots.items() if value not in (None, "", [], {})}


def _normalize_quantity_slots(slots: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(slots)
    quantity = normalized.get("quantity") or normalized.get("ord_qty")
    if quantity in (None, "") and normalized.get("pending_intent") in {"stock", "order"}:
        quantity = normalized.get("limit")
    if quantity not in (None, ""):
        normalized["quantity"] = quantity
        normalized["ord_qty"] = quantity
    return normalized


def _has_quantity_slot(known_slots: Mapping[str, Any]) -> bool:
    return bool(known_slots.get("quantity") or known_slots.get("ord_qty"))


def _filter_satisfied_required_slots(
    required_slots: tuple[str, ...],
    known_slots: Mapping[str, Any],
) -> tuple[str, ...]:
    if not required_slots:
        return ()
    filtered: list[str] = []
    for slot in required_slots:
        if slot == "quantity" and _has_quantity_slot(known_slots):
            continue
        if slot == "goods_no" and known_slots.get("goods_no"):
            continue
        if slot == "product" and (
            known_slots.get("goods_no")
            or known_slots.get("product_name")
            or known_slots.get("tire_model")
            or known_slots.get("pattern_name")
        ):
            continue
        if slot == "tire_size" and known_slots.get("tire_size"):
            continue
        if slot in {"store", "location"} and (
            known_slots.get("shop_id")
            or known_slots.get("shop_name")
            or known_slots.get("store_name")
            or known_slots.get("region")
        ):
            continue
        filtered.append(slot)
    return tuple(filtered)


def _is_recoverable_today_install_stock_contract(known_slots: Mapping[str, Any]) -> bool:
    return bool(
        (known_slots.get("pending_intent") == "stock" or known_slots.get("goal_type") == "store_with_stock")
        and known_slots.get("availability_intent") == "today_install"
        and known_slots.get("goods_no")
        and known_slots.get("tire_size")
        and _has_quantity_slot(known_slots)
    )


def _merge_tuple(*values: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    for seq in values:
        for item in seq or ():
            if item and item not in merged:
                merged.append(item)
    return tuple(merged)


def _derived_required_slots(
    user_text: str,
    intent: str,
    known_slots: Mapping[str, Any],
    *,
    cross_domain_plan: CrossDomainPlan | None = None,
) -> tuple[str, ...]:
    has_product = bool(
        known_slots.get("goods_no")
        or known_slots.get("product_name")
        or known_slots.get("tire_model")
        or known_slots.get("pattern_name")
    )
    text = user_text or ""
    required: list[str] = []
    if (
        intent == "price_or_coupon_check"
        and _PRICE_OR_COUPON_RE.search(text)
        and not has_product
        and not _has_discovery_product_resolution_task(cross_domain_plan)
    ):
        required.append("product")
    if _REFERENCE_PURCHASE_RE.search(text) and not has_product:
        required.append("product")
    has_owned_order_reference = bool(
        known_slots.get("order_no")
        or known_slots.get("order_no_suffix")
        or known_slots.get("owned_anchor_target")
        or known_slots.get("order_cancel_status_lookup")
        or known_slots.get("reservation_store_reference")
    )
    if intent == "order_cancel_request" and _has_reference_signal(text) and not has_owned_order_reference:
        required.append("order")
    return tuple(required)


def _has_discovery_product_resolution_task(plan: CrossDomainPlan | None) -> bool:
    if plan is None:
        return False
    return any(task.intent == "resolve_or_describe_product" for task in plan.subtasks)


def _is_discovery_first_cross_domain_resolution_contract(
    *,
    intent: str,
    known_slots: Mapping[str, Any],
    cross_domain_plan: CrossDomainPlan | None,
) -> bool:
    if intent != "resolve_or_describe_product" or known_slots.get("goods_no"):
        return False
    if cross_domain_plan is None or not cross_domain_plan.is_cross_domain:
        return False
    subtasks = tuple(cross_domain_plan.subtasks or ())
    if len(subtasks) < 2:
        return False
    first_task = subtasks[0]
    first_domain = str(getattr(first_task.domain, "value", first_task.domain) or "")
    return first_domain == "discovery" and str(first_task.intent or "") == "resolve_or_describe_product" and any(
        str(getattr(task.domain, "value", task.domain) or "") == "transaction" for task in subtasks[1:]
    )


def _strip_downstream_transaction_required_slots_for_discovery_resolution(
    required_slots: tuple[str, ...],
    *,
    intent: str,
    known_slots: Mapping[str, Any],
    cross_domain_plan: CrossDomainPlan | None,
) -> tuple[str, ...]:
    if not _is_discovery_first_cross_domain_resolution_contract(
        intent=intent,
        known_slots=known_slots,
        cross_domain_plan=cross_domain_plan,
    ):
        return required_slots
    return tuple(slot for slot in required_slots if slot in {"product", "goods_no", "product_set", "tire_size"})


def _augment_allowed_tools_for_discovery_resolution(
    allowed_tools: tuple[str, ...],
    *,
    intent: str,
    known_slots: Mapping[str, Any],
    cross_domain_plan: CrossDomainPlan | None,
) -> tuple[str, ...]:
    if intent == "best_seller_search":
        return _merge_tuple(allowed_tools, ("get_best_selling_products_tool",))
    if not _is_discovery_first_cross_domain_resolution_contract(
        intent=intent,
        known_slots=known_slots,
        cross_domain_plan=cross_domain_plan,
    ):
        return allowed_tools
    return _merge_tuple(allowed_tools, ("search_product_tool",))


def _risk_level(
    *,
    domain: str,
    intent: str,
    required_slots: tuple[str, ...],
    tool_plan: ToolPlan | None,
) -> str:
    if required_slots and intent in _HIGH_RISK_INTENTS:
        return "high"
    if domain in _HIGH_RISK_DOMAINS and (intent in _HIGH_RISK_INTENTS or required_slots):
        return "high"
    if tool_plan is not None and tool_plan.forbidden_tools:
        return "medium"
    return "low"


def _fallback_reason(
    *,
    intent: str,
    required_slots: tuple[str, ...],
    response_decision: ResponseDecision | None,
    cross_domain_plan: CrossDomainPlan | None,
) -> str | None:
    if required_slots:
        return f"missing_required_slots:{','.join(required_slots)}"
    if response_decision is not None and response_decision.forbidden_behaviors:
        return "response_policy_forbidden_behaviors"
    if cross_domain_plan is not None and cross_domain_plan.is_cross_domain:
        return "cross_domain_plan"
    if intent in _HIGH_RISK_INTENTS:
        return "high_risk_intent"
    return None


def _clarification_text(required_slots: tuple[str, ...]) -> str:
    if "product" in required_slots or "goods_no" in required_slots or "product_set" in required_slots:
        return "어떤 상품 기준으로 확인해드릴까요?"
    if "order" in required_slots:
        return "어떤 주문이나 예약을 취소하시려는지 알려주세요."
    if "tire_size" in required_slots:
        return "확인할 타이어 사이즈를 알려주세요."
    if "quantity" in required_slots:
        return "몇 개 기준으로 확인해드릴까요?"
    if "store" in required_slots or "location" in required_slots or "region" in required_slots:
        return "어느 지역이나 매장 기준으로 확인해드릴까요?"
    return "확인에 필요한 정보를 조금만 더 알려주세요."


def _missing_slot_summary_text(required_slots: tuple[str, ...]) -> str:
    labels: list[str] = []
    label_by_slot = {
        "product": "상품",
        "goods_no": "상품",
        "product_name": "상품명",
        "product_set": "상품 선택",
        "order": "주문/예약",
        "tire_size": "타이어 규격",
        "size": "타이어 규격",
        "quantity": "수량",
        "ord_qty": "수량",
        "store": "매장",
        "location": "지역/매장",
        "region": "지역",
        "booking_datetime": "예약 날짜/시간",
        "schedule": "예약 날짜/시간",
    }
    for slot in required_slots:
        label = label_by_slot.get(str(slot), str(slot))
        if label and label not in labels:
            labels.append(label)
    return ", ".join(labels) if labels else "추가 확인 정보"


def _clarification_chips(required_slots: tuple[str, ...]) -> list[dict[str, str]]:
    chips: list[dict[str, str]] = []
    if "product" in required_slots or "goods_no" in required_slots or "product_set" in required_slots:
        chips.append({"label": "상품명 입력", "domain": "DISCOVERY"})
    if "order" in required_slots:
        chips.append({"label": "주문 내역 보기", "domain": "TRANSACTION"})
    if "tire_size" in required_slots:
        chips.append({"label": "사이즈 입력", "domain": "DISCOVERY"})
    if "quantity" in required_slots:
        chips.append({"label": "수량 선택", "domain": "TRANSACTION"})
    if "store" in required_slots or "location" in required_slots or "region" in required_slots:
        chips.append({"label": "지역/매장 입력", "domain": "TRANSACTION"})
    chips.extend([
        {"label": "상품 추천", "domain": "DISCOVERY"},
        {"label": "처음부터 다시", "domain": "LEADING"},
    ])
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for chip in chips:
        label = chip["label"]
        if label not in seen:
            deduped.append(chip)
            seen.add(label)
    return deduped[:4]
