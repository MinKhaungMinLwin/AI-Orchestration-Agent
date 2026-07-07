"""Rich FE templates: product cards, store lists, car picker, cheapest price.

The mini model maps raw tool output into the Pydantic template models from
`agents/templates/schemas.py` (single source of truth) — same approach V2
uses via RESPONSE_FORMAT, but as one dedicated call. Any failure returns
None and the turn falls back to the plain quickReply event.
"""

import json
import logging

from pydantic import BaseModel

from services.tstation.agents.templates.schemas import (
    CheapestProductTemplate,
    ListCarTemplate,
    LocationTemplate,
    ProductTemplate,
)
from services.tstation.chat_v3.llm import get_router_llm
from services.tstation.chat_v3.prompts.templates import TEMPLATE_BUILDER_PROMPT

logger = logging.getLogger(__name__)

_MAX_TOOL_OUTPUT_CHARS = 12000

# Which template a tool's output can feed — data availability, not routing.
_TOOL_TEMPLATES: dict[str, tuple[str, type[BaseModel]]] = {
    "search_product_tool": ("product", ProductTemplate),
    "search_product_summary_tool": ("product", ProductTemplate),
    "get_products_recommendations_tool": ("product", ProductTemplate),
    "get_best_selling_products_tool": ("product", ProductTemplate),
    "get_newest_products_tool": ("product", ProductTemplate),
    "search_benefit_applicable_products_tool": ("product", ProductTemplate),
    "get_event_applicable_products_tool": ("product", ProductTemplate),
    "get_coupon_applicable_products_tool": ("product", ProductTemplate),
    "search_stores_tool": ("location", LocationTemplate),
    "search_stores_complex_tool": ("location", LocationTemplate),
    "get_nearby_stores_tool": ("location", LocationTemplate),
    "get_store_list_tool": ("location", LocationTemplate),
    "get_stores_with_time_filter_tool": ("location", LocationTemplate),
    "get_user_vehicles_tool": ("listCar", ListCarTemplate),
    "get_my_cars_tool": ("listCar", ListCarTemplate),
    "get_cheapest_price_tool": ("cheapestProduct", CheapestProductTemplate),
}


def _has_rows(output: str) -> bool:
    """True when the tool output parses to non-empty JSON data."""
    try:
        parsed = json.loads(output)
    except (TypeError, ValueError):
        return bool(output and len(output) > 50)
    if isinstance(parsed, dict):
        return any(bool(v) for v in parsed.values())
    return bool(parsed)


def _pick_source(tool_calls: list[dict]) -> tuple[str, type[BaseModel], dict] | None:
    """Most recent tool call whose output can feed a rich template."""
    for call in reversed(tool_calls):
        entry = _TOOL_TEMPLATES.get(call.get("name") or "")
        output = str(call.get("output") or "")
        if entry and not output.startswith("Tool error") and _has_rows(output):
            return entry[0], entry[1], call
    return None


async def build_rich_data_event(answer: str, tool_calls: list[dict]) -> dict | None:
    """Return a validated FE data event dict, or None to fall back to quickReply."""
    source = _pick_source(tool_calls)
    if source is None:
        return None
    template_name, template_model, call = source
    try:
        llm = get_router_llm().with_structured_output(template_model, method="function_calling")
        payload = await llm.ainvoke(
            [
                ("system", TEMPLATE_BUILDER_PROMPT),
                (
                    "user",
                    f"## 도구: {call['name']}\n## 도구 결과\n{str(call['output'])[:_MAX_TOOL_OUTPUT_CHARS]}\n\n"
                    f"## 챗봇 답변\n{answer[:2000]}",
                ),
            ]
        )
        if not getattr(payload, "assistantResponse", ""):
            payload.assistantResponse = answer
        return {
            "type": "data",
            "template": template_name,
            "data": payload.model_dump(mode="json", exclude_none=True),
            "source_tool": call["name"],
        }
    except Exception:
        logger.exception("[CHAT_V3] rich template build failed (%s) — falling back to quickReply", template_name)
        return None
