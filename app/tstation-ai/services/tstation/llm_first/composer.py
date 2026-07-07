from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from config.tracing import build_trace_config
from services.tstation.llm_first.models import FactBundle

logger = logging.getLogger(__name__)

_GENERAL_TIRE_TERM_EXPLANATIONS: tuple[tuple[str, str], ...] = (
    (
        "3pmsf",
        "3PMSF는 Three-Peak Mountain Snowflake 마크로, 눈길 성능 기준을 충족한 겨울용/올웨더 타이어에 "
        "붙는 표시예요. 보통 M+S보다 눈길 성능 기준이 더 엄격한 편으로 이해하시면 됩니다.",
    ),
)


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

    if any(call.tool_name == "search_faq_hybrid_tool" for call in bundle.tool_calls):
        return "관련 FAQ 근거를 확인했습니다. 세부 내용은 안내된 정책 기준으로 확인해 주세요."

    return "요청하신 내용을 확인했습니다."


def _general_tire_term_explanation(user_text: str) -> str | None:
    normalized = user_text.casefold()
    for term, explanation in _GENERAL_TIRE_TERM_EXPLANATIONS:
        if term in normalized:
            return explanation
    return None


def _fixed_template_response(bundle: FactBundle) -> str | None:
    if not bundle.templates:
        return None
    data = bundle.templates[-1].get("data")
    if not isinstance(data, dict):
        return None
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return None
    if metadata.get("source") != "llm_first_escalation_confirmation":
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
        if direct_explanation := _general_tire_term_explanation(user_text):
            return direct_explanation

        fallback = fallback_compose(user_text, bundle)
        if fixed_response := _fixed_template_response(bundle):
            return fixed_response
        if self.llm is None or bundle.missing_inputs:
            return fallback

        prompt = (
            "You are the QC/Composer for a T-Station LLM-first runtime. "
            "Answer in Korean. Use only the provided tool facts. "
            "Do not claim price, stock, schedule, order, reservation, cart, coupon issue, or QnA completion "
            "unless a matching tool fact proves it. "
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
