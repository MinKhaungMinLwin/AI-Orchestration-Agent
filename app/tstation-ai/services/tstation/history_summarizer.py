"""Rolling conversation summarizer — compresses old turns to reduce LLM input tokens."""
import logging

logger = logging.getLogger(__name__)

# Trigger every 4 turns (8 messages: 4 user + 4 assistant).
SUMMARIZE_EVERY_N = 8

# Keep the last 3 turns (6 messages) verbatim; summarise everything older.
KEEP_RECENT_MESSAGES = 6

_SUMMARIZE_PROMPT = """\
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

_UPDATE_PROMPT = """\
You are updating a running summary of a customer service conversation for a tire advisor AI.

Information already tracked separately — DO NOT repeat:
{slots_info}

Incorporate the new messages into the existing summary. Remove details that are
outdated or superseded. Keep everything the advisor still needs.
Write in Korean.

[EXISTING SUMMARY]
{existing_summary}

[NEW MESSAGES]
{messages_text}"""


def _format_messages(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        role = "고객" if m.get("role") == "user" else "상담사"
        content = m.get("content", "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _format_slots(slots) -> str:
    if slots is None:
        return "(없음)"
    data = slots.model_dump() if hasattr(slots, "model_dump") else {}
    filled = {k: v for k, v in data.items() if v is not None}
    if not filled:
        return "(없음)"
    return ", ".join(f"{k}={v}" for k, v in filled.items())


async def maybe_summarize(session_id: str) -> None:
    """Fire-and-forget: run summarization if due; swallows all exceptions."""
    try:
        from services.tstation.chat_history_service import get_chat_history_service

        service = get_chat_history_service()
        count = service.get_message_count(session_id)

        if count < SUMMARIZE_EVERY_N or count % SUMMARIZE_EVERY_N != 0:
            return

        existing = service.get_summary(session_id)
        covered = existing["covered_count"] if existing else 0
        target_covered = count - KEEP_RECENT_MESSAGES

        if target_covered <= covered:
            return  # already up to date for this batch

        await _do_summarize(session_id, service, count)
    except Exception:
        logger.exception(
            f"[SUMMARY] Background summarization failed for session {session_id}"
        )


async def _do_summarize(session_id: str, service, total_count: int) -> None:
    from langchain_core.messages import HumanMessage
    from services.tstation.agents.router import DECISION_LLM

    all_messages = service.get_history(session_id)
    slots = service.get_slots(session_id)
    existing = service.get_summary(session_id)

    # Only summarise messages not yet covered by the existing summary.
    # covered_count tells us how many messages were already processed last time,
    # so we start from there — avoids re-sending already-summarised turns.
    covered = existing["covered_count"] if existing else 0
    to_summarize = all_messages[covered : total_count - KEEP_RECENT_MESSAGES]
    if not to_summarize:
        return

    slots_info = _format_slots(slots)
    messages_text = _format_messages(to_summarize)

    if existing:
        prompt = _UPDATE_PROMPT.format(
            slots_info=slots_info,
            existing_summary=existing["content"],
            messages_text=messages_text,
        )
    else:
        prompt = _SUMMARIZE_PROMPT.format(
            slots_info=slots_info,
            messages_text=messages_text,
        )

    result = await DECISION_LLM.ainvoke([HumanMessage(content=prompt)])
    summary_text = result.content.strip() if hasattr(result, "content") else str(result).strip()

    if summary_text:
        covered_count = total_count - KEEP_RECENT_MESSAGES
        service.save_summary(session_id, summary_text, covered_count)
        logger.info(
            f"[SUMMARY] Updated for session {session_id} "
            f"(covered_count={covered_count}, turns_summarised={covered_count // 2})"
        )
