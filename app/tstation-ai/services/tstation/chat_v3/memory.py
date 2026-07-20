"""Cross-turn tool-context memory — reuses V2's Redis store.

Tool results from this turn are persisted (`chat:tool_ctx:{session}`, 2h TTL,
deduped server-side) and injected into the next turn's system context so
follow-ups like "2번째 상품으로 할게" keep their grounding data.
"""

import json
import logging

from services.tstation.chat_history_service import get_chat_history_service

logger = logging.getLogger(__name__)

_MAX_INJECT_ITEMS = 3
_MAX_INJECT_CHARS = 4000
_MAX_ITEM_OUTPUT_CHARS = 2000


async def load_tool_context(session_id: str) -> list[dict]:
    try:
        service = get_chat_history_service()
        return await service.get_tool_context_async(session_id)
    except Exception:
        logger.exception("[CHAT_V3] failed to load tool context for %s", session_id)
        return []


def tool_context_block(items: list[dict]) -> str | None:
    """Previous-turn tool results as a system-context block (most recent first)."""
    if not items:
        return None
    lines = [
        "## PREVIOUS TOOL RESULTS (data already fetched in earlier turns — reuse instead of re-calling "
        "when the user refers back to it; re-call the tool when freshness matters, e.g. stock/price)"
    ]
    used = 0
    for item in items[:_MAX_INJECT_ITEMS]:
        entry = json.dumps(
            {"tool": item.get("tool", ""), "input": item.get("input", {}), "data": item.get("data")},
            ensure_ascii=False,
            default=str,
        )
        if used + len(entry) > _MAX_INJECT_CHARS:
            lines.append("… (일부 생략)")
            break
        lines.append(entry)
        used += len(entry)
    return "\n".join(lines) if len(lines) > 1 else None


def context_items_from_tool_calls(tool_calls: list[dict]) -> list[dict]:
    """Executor tool calls → storable context items ({tool, input, data})."""
    items = []
    for call in tool_calls:
        output = str(call.get("output") or "")
        if not call.get("name") or output.startswith("Tool error"):
            continue
        try:
            data = json.loads(output[:_MAX_ITEM_OUTPUT_CHARS * 4])
        except (ValueError, TypeError):
            data = output[:_MAX_ITEM_OUTPUT_CHARS]
        items.append({"tool": call["name"], "input": call.get("args") or {}, "data": data})
    return items


async def persist_turn_context(
    session_id: str,
    *,
    tool_calls: list[dict],
    quick_reply_domains: list[str],
    predicted_domains: list[str],
    user_id: str | None,
) -> None:
    """End-of-turn write: tool context + next-turn routing hints (V2-compatible)."""
    try:
        service = get_chat_history_service()
        await service.finalize_chat_context_async(
            session_id=session_id,
            tool_data=context_items_from_tool_calls(tool_calls),
            quick_reply_domains=quick_reply_domains,
            predicted_domains=predicted_domains,
            user_id=user_id,
        )
    except Exception:
        logger.exception("[CHAT_V3] failed to persist turn context for %s", session_id)
