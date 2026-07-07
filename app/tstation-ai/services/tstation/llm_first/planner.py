from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from config.tracing import build_trace_config
from services.tstation.llm_first.models import AgentFlow, ConversationState, PlannerDecision, StructuredPlannerDecision

logger = logging.getLogger(__name__)

_GOODS_NO_RE = re.compile(r"\bG\d{12}\b", re.IGNORECASE)
_TIRE_SIZE_RE = re.compile(r"\b(\d{3})\s*/?\s*(\d{2})\s*[Rr]?\s*(\d{2})\b")
_QTY_RE = re.compile(r"(\d{1,2})\s*(?:개|본|짝)")


def normalize_tire_size(text: str) -> str | None:
    match = _TIRE_SIZE_RE.search(text)
    if not match:
        return None
    width, ratio, inch = match.groups()
    return f"{width}/{ratio}R{inch}"


def extract_known_inputs(user_text: str, state: ConversationState) -> dict[str, Any]:
    text = user_text.strip()
    known: dict[str, Any] = {}
    last_facts = state.last_facts if isinstance(state.last_facts, dict) else {}
    if goods := _GOODS_NO_RE.search(text):
        known["goods_no"] = goods.group(0).upper()
    elif state.commerce_state.product.goods_no:
        known["goods_no"] = state.commerce_state.product.goods_no
    elif last_facts.get("goods_no"):
        known["goods_no"] = last_facts["goods_no"]

    tire_size = normalize_tire_size(text) or state.commerce_state.product.tire_size or last_facts.get("tire_size")
    if tire_size:
        known["tire_size"] = tire_size

    if qty := _QTY_RE.search(text):
        known["ord_qty"] = int(qty.group(1))
    elif state.commerce_state.quantity:
        known["ord_qty"] = state.commerce_state.quantity
    elif last_facts.get("ord_qty"):
        known["ord_qty"] = last_facts["ord_qty"]

    if state.commerce_state.product.product_name:
        known["product_name"] = state.commerce_state.product.product_name
    elif last_facts.get("product_name"):
        known["product_name"] = last_facts["product_name"]
    product_names = last_facts.get("product_names")
    if isinstance(product_names, list):
        normalized_names = [str(name).strip() for name in product_names if str(name).strip()]
        if normalized_names:
            known["product_names"] = normalized_names[:5]
    if last_facts.get("compare_metric"):
        known["compare_metric"] = last_facts["compare_metric"]
    if state.commerce_state.store.shop_id:
        known["shop_id"] = state.commerce_state.store.shop_id
    elif last_facts.get("shop_id"):
        known["shop_id"] = last_facts["shop_id"]
    if state.commerce_state.store.shop_name:
        known["store_name"] = state.commerce_state.store.shop_name
    elif last_facts.get("store_name"):
        known["store_name"] = last_facts["store_name"]
    if state.commerce_state.store.region:
        known["region"] = state.commerce_state.store.region
    elif last_facts.get("region"):
        known["region"] = last_facts["region"]
    if last_facts.get("date"):
        known["date"] = last_facts["date"]
    if last_facts.get("time"):
        known["time"] = last_facts["time"]
    if last_facts.get("car_no"):
        known["car_no"] = last_facts["car_no"]
    if last_facts.get("car_model"):
        known["car_model"] = last_facts["car_model"]

    return known


def _clarification_plan() -> PlannerDecision:
    return PlannerDecision(
        selected_afs=[],
        conversation_goal="clarify_user_request",
        answer_mode="clarification",
        requires_user_confirmation=False,
        resume_previous_flow=False,
    )


class LeadingAgentPlanner:
    def __init__(self, llm: Any | None = None):
        self.llm = llm
        self._structured_llm = (
            llm.with_structured_output(StructuredPlannerDecision, strict=True) if llm is not None else None
        )

    async def plan(
        self,
        *,
        user_text: str,
        state: ConversationState,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> PlannerDecision:
        if self._structured_llm is None:
            return _clarification_plan()

        known_inputs = extract_known_inputs(user_text, state)
        prompt = (
            "You are the LLM-first Leading Agent for T-Station. "
            "Select one or more MVP Agent Flows for the current user turn. "
            "Use current-turn intent first. Do not force stale purchase context unless the user explicitly resumes. "
            "Return missing_inputs for each selected flow. Include product_name, product_names, compare_metric, "
            "benefit_lookup, benefit_query, evt_no_list, region, store_name, store_lookup, ord_qty, goods_no, "
            "shop_id, tire_size, schedule date/time, car_no, owner_nm, car_model, car_lnc_cd, "
            "vehicle_recommendation, store_attribute in known_inputs "
            "when the user or state provides them. "
            "For purchase/order intent, use QuickShoppingAF and keep the flow continuous across turns: "
            "collect product or tire_size, ord_qty, store/region, and schedule date/time in order. "
            "If the current state has an active purchase and the user provides a missing purchase value "
            "such as quantity, store, region, date, or time, treat that as resuming the purchase flow and select QuickShoppingAF. "
            "If product and quantity are known but only a region/store name is known, QuickShoppingAF should show installable store candidates. "
            "If product, quantity, and shop_id are known but schedule is missing, QuickShoppingAF should show schedule choices. "
            "If product, quantity, shop_id, and schedule are known, QuickShoppingAF should prepare an order draft, not complete the order. "
            "For store lookup with an extra condition such as female staff, waiting room, night service, equipment, "
            "or other store attributes, still select StoreAF and set known_inputs.store_attribute to the requested condition. "
            "The executor will search stores first, then answer only from verified store data or say the attribute is not confirmed. "
            "For explicit favorite/regular store requests such as '내 단골매장', '단골 가게', '자주 가는 매장', "
            "'마이샵', or '단골점', select StoreAF and set known_inputs.store_lookup=favorite_stores. "
            "Do not ask for location and do not treat it as a generic store search. "
            "For product-to-product comparisons such as 'A랑 B 비교해줘', select ProductDescriptionAF, "
            "set known_inputs.product_names to the compared product/model names, and set compare_metric to detail by default "
            "or mileage/noise/fuel_efficiency/wet/release/grade/car_type when the user names a comparison axis. "
            "Do not use ProductRecommendationAF for a comparison between named products. "
            "If no concrete tire size is needed, use summary-level product comparison; do not ask for size first. "
            "For event/promotion/deal/benefit questions, select ProductDescriptionAF and set benefit_lookup: "
            "event_deal_list for generic current events/promotions/deals/benefits list; "
            "event_applicable_products when the user asks which products apply to a named event/deal/promotion, "
            "with benefit_query set to the event/deal/promotion name, or evt_no_list when event numbers are provided; "
            "product_applicable_benefits when the user asks which event/deal/coupon/benefit applies to a product, "
            "with benefit_query set to the product name. "
            "For authenticated account lookups, set known_inputs.account_lookup to one of: "
            "coupons for owned coupon list, reservations for reservation history, orders for order history, "
            "maintenance_history for service/maintenance history, warranties for owned warranty/assurance service. "
            "For unsupported fact lookups that are not searchable in current tools, such as asking a vehicle's "
            "OE/factory tire part number or exact original-equipment part code, select FAQAF instead of ProductDescriptionAF. "
            "In those cases, treat the turn as an informational limitation answer: explain that the exact OE part number "
            "cannot be confirmed from current data and do not ask the user to pick a product first. "
            "For tire recommendations, use ProductRecommendationAF and classify like legacy Discovery Flow A. "
            "For registered my-car recommendations such as '내차에 맞는 타이어 추천' or '내 차량 기반 추천', "
            "select ProductCompatibilityAF first, set vehicle_recommendation=true, and rely on runtime mbr_no to fetch saved cars. "
            "If the user names one of their cars such as '내차 중에 제타/GV70/쏘나타', still select ProductCompatibilityAF, "
            "set vehicle_recommendation=true and car_model to that named car; executor will fetch saved cars and auto-select only a unique match. "
            "Do not jump straight to generic ProductRecommendationAF without a selected registered car for my-car wording. "
            "Use A2 size-tied when tire_size is present, "
            "A3 general/scenario-only when no vehicle or size is present. A3 must still recommend immediately without asking for size. "
            "Set known_inputs.recommendation_type default tstation, or map scenarios: value, discount, wet, snow, "
            "high_speed, performance, low_vibration, commute, long_distance, urban, family, ev, heavy_load, "
            "weekend, safe_kids, all_weather, warranty, summer, sound_absorber. "
            "Set vehicle_type separately for EV/SUV/passenger/truck_van, season_nm for 사계절/올웨더/여름/겨울, "
            "and limit when the user asks for a count. "
            "For best-selling/popular tire searches, use ProductRecommendationAF with recommendation_source=best_seller, "
            "vehicle_query for car-model-specific best sellers, months/from_date/to_date when the period is specified, "
            "and limit when requested. "
            "For vehicle compatibility, select ProductCompatibilityAF and set car_no+owner_nm, car_model, "
            "or rely on runtime mbr_no for the user's registered cars. "
            "Explicit registered-vehicle list requests such as '내차목록', '내 차량', '보유차량', "
            "or '등록차량 보여줘' are ProductCompatibilityAF requests to fetch the user's saved cars, "
            "not FallbackEscalationAF. "
            "For explicit 1:1 inquiry or human handoff requests, select FallbackEscalationAF and set "
            "known_inputs.escalation_target to qna or human. "
            "Allowed MVP flows: StoreAF, PriceAF, InventoryAF, QuickShoppingAF, "
            "ProductRecommendationAF, ProductDescriptionAF, FAQAF, OrderDeliveryAF, "
            "ProductCompatibilityAF, FallbackEscalationAF. "
            "Side effects require confirmation and are blocked in MVP."
        )
        state_json = state.model_dump_json(exclude_none=True)
        human = (
            f"Current user text:\n{user_text}\n\n"
            f"Current state:\n{state_json}\n\n"
            f"Known scalar inputs extracted from explicit values/state:\n{known_inputs}"
        )
        try:
            trace_config = build_trace_config(
                run_name="llm_first_planner",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                tags=["llm_first", "planner"],
                prompt_name="llm_first_planner",
                extra_metadata={"runtime": "llm_first"},
            )
            decision = await self._structured_llm.ainvoke(
                [SystemMessage(content=prompt), HumanMessage(content=human)],
                config=trace_config,
            )
            decision_payload = decision.model_dump()
            for item in decision_payload.get("selected_afs", []):
                item["known_inputs"] = {
                    key: value for key, value in item.get("known_inputs", {}).items() if value is not None
                }
            decision = PlannerDecision.model_validate(decision_payload)
        except Exception:
            logger.warning("[LLM_FIRST_PLANNER] structured planner failed; asking clarification", exc_info=True)
            return _clarification_plan()

        allowed = {
            AgentFlow.STORE,
            AgentFlow.PRICE,
            AgentFlow.INVENTORY,
            AgentFlow.QUICK_SHOPPING,
            AgentFlow.PRODUCT_RECOMMENDATION,
            AgentFlow.PRODUCT_DESCRIPTION,
            AgentFlow.FAQ,
            AgentFlow.ORDER_DELIVERY,
            AgentFlow.PRODUCT_COMPATIBILITY,
            AgentFlow.FALLBACK_ESCALATION,
        }
        filtered = [item for item in decision.selected_afs if item.af in allowed]
        if not filtered:
            return _clarification_plan()
        for item in filtered:
            item.known_inputs = {**known_inputs, **item.known_inputs}
        decision.selected_afs = filtered
        return decision
