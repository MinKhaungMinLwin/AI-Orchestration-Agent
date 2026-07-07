from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from config.tracing import build_trace_config
from services.tstation.llm_first.models import AgentFlow, ConversationState, PlannerDecision

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
    if goods := _GOODS_NO_RE.search(text):
        known["goods_no"] = goods.group(0).upper()
    elif state.commerce_state.product.goods_no:
        known["goods_no"] = state.commerce_state.product.goods_no

    tire_size = normalize_tire_size(text) or state.commerce_state.product.tire_size
    if tire_size:
        known["tire_size"] = tire_size

    if qty := _QTY_RE.search(text):
        known["ord_qty"] = int(qty.group(1))
    elif state.commerce_state.quantity:
        known["ord_qty"] = state.commerce_state.quantity

    if state.commerce_state.product.product_name:
        known["product_name"] = state.commerce_state.product.product_name
    if state.commerce_state.store.shop_id:
        known["shop_id"] = state.commerce_state.store.shop_id
    if state.commerce_state.store.shop_name:
        known["store_name"] = state.commerce_state.store.shop_name
    if state.commerce_state.store.region:
        known["region"] = state.commerce_state.store.region

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
        self._structured_llm = llm.with_structured_output(PlannerDecision, strict=True) if llm is not None else None

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
            "Return missing_inputs for each selected flow. Include product_name, region, store_name, ord_qty, "
            "goods_no, shop_id, tire_size, schedule date/time in known_inputs when the user or state provides them. "
            "Allowed MVP flows: StoreAF, PriceAF, InventoryAF, QuickShoppingAF, "
            "ProductRecommendationAF, ProductDescriptionAF, FAQAF. "
            "OrderDeliveryAF, ProductCompatibilityAF, and FallbackEscalationAF are deferred. "
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
        }
        filtered = [item for item in decision.selected_afs if item.af in allowed]
        if not filtered:
            return _clarification_plan()
        for item in filtered:
            item.known_inputs = {**known_inputs, **item.known_inputs}
        decision.selected_afs = filtered
        return decision
