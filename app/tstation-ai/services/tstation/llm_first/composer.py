from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from config.tracing import build_trace_config
from services.tstation.llm_first.models import FactBundle

logger = logging.getLogger(__name__)


def _compact_facts(bundle: FactBundle) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for call in bundle.tool_calls:
        if call.blocked:
            continue
        value = call.result
        if isinstance(value, dict):
            data = value.get("data", value)
            facts[call.tool_name] = data
        else:
            facts[call.tool_name] = value
    return facts


def fallback_compose(user_text: str, bundle: FactBundle) -> str:
    if bundle.missing_inputs:
        labels = {
            "product": "상품",
            "product_selection": "어떤 상품인지",
            "goods_no": "상품",
            "quantity": "수량",
            "ord_qty": "수량",
            "region_or_store": "지역 또는 매장",
            "store_or_region": "매장 또는 지역",
            "store": "매장",
            "schedule": "장착 일정",
            "tire_size_or_vehicle": "타이어 사이즈 또는 차량 정보",
            "benefit_query": "혜택/이벤트/기획전 이름",
        }
        missing = [labels.get(item, item) for item in dict.fromkeys(bundle.missing_inputs)]
        return f"{', '.join(missing)} 정보를 알려주시면 이어서 확인해 드릴게요."

    if bundle.templates:
        return str(bundle.templates[-1].get("data", {}).get("assistantResponse") or "확인한 결과를 정리해 드릴게요.")

    if any(call.tool_name == "get_final_price_tool" for call in bundle.tool_calls):
        price = bundle.state.commerce_state.price.final_price
        if price:
            return f"확인된 최종 기준 가격은 {price:,}원입니다. 실제 적용 금액은 보유 쿠폰과 주문 조건에 따라 달라질 수 있어요."
        return "가격 도구 결과에서 확정 가격을 찾지 못했습니다. 확인 가능한 상품을 다시 선택해 주세요."

    return "요청하신 내용을 확인했습니다."


def _fixed_template_response(bundle: FactBundle) -> str | None:
    if not bundle.templates:
        return None
    data = bundle.templates[-1].get("data")
    if not isinstance(data, dict):
        return None
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return None
    if metadata.get("source") not in {
        "llm_first_escalation_confirmation",
        "llm_first_product_comparison",
        "llm_first_favorite_store_empty",
        "llm_first_benefit_event_deal_list",
        "llm_first_event_applicable_products",
        "llm_first_benefit_applicable_products",
        "llm_first_order_complete",
        "llm_first_cart_complete",
        "llm_first_unsupported_region",
        "llm_first_escalation_complete",
        "llm_first_escalation_declined",
        "llm_first_qna_complete",
    }:
        return None
    text = str(data.get("assistantResponse") or "").strip()
    return text or None


class Composer:
    def __init__(self, llm: Any | None = None):
        self.llm = llm

    async def compose(
        self,
        *,
        user_text: str,
        bundle: FactBundle,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> str:
        fallback = fallback_compose(user_text, bundle)
        if fixed_response := _fixed_template_response(bundle):
            return fixed_response
        if self.llm is None or bundle.missing_inputs:
            return fallback

        prompt = (
            "You are the QC/Composer for a T-Station LLM-first runtime. "
            "Answer in Korean. "
            "Do not claim price, stock, schedule, order, reservation, cart, coupon issue, or QnA completion "
            "unless a matching tool fact proves it. "
            "Treat T-Station/company policy, coupons, warranties/coverage, store service availability, and "
            "any transactional status as tool-grounded only. "
            "If FAQ/search facts are missing or weak but the user is asking a general tire concept question "
            "(for example tire markings, standards, sidewall terminology, seasonal category meaning, or other "
            "generic tire knowledge), you may answer from general tire knowledge instead of refusing. "
            "Do not present general knowledge as T-Station policy or product-specific fact. "
            "Do not say an order or reservation was completed. Keep the answer concise."
        )
        payload = {
            "user_text": user_text,
            "selected_afs": [item.model_dump(mode="json") for item in bundle.planner.selected_afs],
            "facts": _compact_facts(bundle),
            "commerce_state": bundle.state.commerce_state.model_dump(exclude_none=True),
            "templates": bundle.templates,
        }
        try:
            trace_config = build_trace_config(
                run_name="llm_first_composer",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                tags=["llm_first", "composer"],
                prompt_name="llm_first_composer",
                extra_metadata={"runtime": "llm_first"},
            )
            result = await self.llm.ainvoke([
                SystemMessage(content=prompt),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False, default=str)),
            ], config=trace_config)
        except Exception:
            logger.warning("[LLM_FIRST_COMPOSER] composer failed; using fallback", exc_info=True)
            return fallback
        content = getattr(result, "content", result)
        return str(content or fallback).strip() or fallback
