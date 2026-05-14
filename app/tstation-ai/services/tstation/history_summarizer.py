"""Rolling conversation summarizer — compresses old turns to reduce LLM input tokens."""
import logging

logger = logging.getLogger(__name__)

# Create the first summary after 3 turns (6 messages: 3 user + 3 assistant).
MIN_MESSAGES_FOR_SUMMARY = 6

# After the first summary, update it every 2 more turns (4 messages).
SUMMARY_UPDATE_INTERVAL = 4

# Keep the last 2 turns (4 messages) verbatim; summarise everything older.
RECENT_MESSAGES_TO_KEEP = 4

_SUMMARY_PROMPT = """\
You are summarizing a customer service conversation for a tire advisor AI.
The summary replaces older messages so the advisor can continue helping the customer.

Information already tracked separately — DO NOT repeat in the summary:
{slots_info}

Summarize the conversation below. Preserve everything the advisor still needs:
- Customer's vehicle and driving context
- Stated preferences or constraints
- Products or stores viewed or discussed
- Decisions and selections already made
- Any implicit context the advisor should keep in mind

Write in Korean. Let the content determine the length.

[CONVERSATION]
{messages_text}"""

_SUMMARY_UPDATE_PROMPT = """\
You are updating a running summary of a customer service conversation for a tire advisor AI.

Information already tracked separately — DO NOT repeat:
{slots_info}

Incorporate the new messages into the existing summary. Remove details that are
outdated or superseded. Keep everything the advisor still needs.
Write in Korean.

[EXISTING SUMMARY]
{summary}

[NEW MESSAGES]
{messages_text}"""


def _format_messages(messages: list[dict]) -> str:
    lines = []
    for message in messages:
        speaker = "고객" if message.get("role") == "user" else "상담사"
        content = message.get("content", "").strip()
        if content:
            lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def _format_slots(slots) -> str:
    if slots is None:
        return "(없음)"
    slot_values = slots.model_dump() if hasattr(slots, "model_dump") else {}
    populated_slots = {key: value for key, value in slot_values.items() if value is not None}
    if not populated_slots:
        return "(없음)"
    return ", ".join(f"{key}={value}" for key, value in populated_slots.items())


async def refresh_summary(session_id: str) -> None:
    """Run background summary maintenance when enough new history has accumulated."""
    from services.tstation.chat_history_service import get_chat_history_service

    history_service = get_chat_history_service()
    
    # Optimize Concurrency: Prevent race condition via Redis lock
    if not history_service.acquire_summary_lock(session_id):
        logger.info(f"[SUMMARY] Task skipped, another summarization is in progress for {session_id}")
        return

    try:
        message_count = history_service.get_message_count(session_id)

        if message_count < MIN_MESSAGES_FOR_SUMMARY:
            return

        summary = history_service.get_summary(session_id)
        covered_count = summary["covered_count"] if summary else 0
        target_covered = message_count - RECENT_MESSAGES_TO_KEEP

        if target_covered <= covered_count:
            return

        if summary and target_covered - covered_count < SUMMARY_UPDATE_INTERVAL:
            return

        await _update_summary(session_id, history_service, message_count, summary, covered_count, target_covered)
    except Exception:
        logger.exception(
            f"[SUMMARY] Background summarization failed for session {session_id}"
        )
    finally:
        history_service.release_summary_lock(session_id)


async def _update_summary(session_id: str, history_service, message_count: int, summary: dict | None, covered_count: int, target_covered: int) -> None:
    from langchain_core.messages import HumanMessage
    from services.tstation.agents.router import DECISION_LLM

    # Optimize Redis Fetch: Get only the range we actually need, skip fully decrypting history
    messages_to_summarize = history_service.get_history_range(session_id, covered_count, target_covered - 1)
    if not messages_to_summarize:
        return

    slots = history_service.get_slots(session_id)

    slots_info = _format_slots(slots)
    messages_text = _format_messages(messages_to_summarize)

    if summary:
        prompt = _SUMMARY_UPDATE_PROMPT.format(
            slots_info=slots_info,
            summary=summary["content"],
            messages_text=messages_text,
        )
    else:
        prompt = _SUMMARY_PROMPT.format(
            slots_info=slots_info,
            messages_text=messages_text,
        )

    result = await DECISION_LLM.ainvoke([HumanMessage(content=prompt)])
    summary_text = result.content.strip() if hasattr(result, "content") else str(result).strip()

    if summary_text:
        new_covered_count = target_covered
        history_service.save_summary(session_id, summary_text, new_covered_count)
        logger.info(
            f"[SUMMARY] Updated for session {session_id} "
            f"(covered_count={new_covered_count}, turns_summarised={new_covered_count // 2})"
        )