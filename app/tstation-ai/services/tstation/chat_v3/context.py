"""Build the LLM message list: history + user context + current time.

Port of V2's `_build_messages_with_user_info` — pure formatting, no regex.
"""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from common.curr_time import get_current_time
from common.jwt_utils import get_user_info_from_token
from config.prompts import load_client_injection
from schemas.tstation.chat import TStationChatRequest

_SAFE_USER_FIELDS = {"mbr_nm", "location", "user_id"}


def _has_valid_location(location: dict | None) -> bool:
    if not isinstance(location, dict):
        return False
    return isinstance(location.get("xpos"), (int, float)) and isinstance(location.get("ypos"), (int, float))


def merged_user_info(request: TStationChatRequest) -> dict | None:
    """JWT user info merged with UI-provided info (UI overrides)."""
    user_info = None
    if request.access_token:
        user_info = get_user_info_from_token(request.access_token)
    if request.user_info:
        user_info = {**(user_info or {}), **request.user_info}
    if user_info and not _has_valid_location(user_info.get("location")):
        user_info = {k: v for k, v in user_info.items() if k != "location"}
    return user_info


def _user_context_block(user_info: dict) -> str | None:
    lines = []
    for key, value in user_info.items():
        if key not in _SAFE_USER_FIELDS:
            continue
        if key == "location" and isinstance(value, dict):
            lines.append(f"xpos: {value.get('xpos')}, ypos: {value.get('ypos')}")
        elif key == "user_id":
            lines.append(f"mbr_no: {value}")
        else:
            lines.append(f"{key}: {value}")
    if not lines:
        return None
    return (
        "## USER CONTEXT INFORMATION (Always Available)\n"
        + "\n".join(lines)
        + "\n\n## INSTRUCTIONS:\n"
        "🔹 Always prioritize data provided directly by the user\n"
        "🔹 If no direct data is provided, reference the personal data above\n"
        "🔹 NEVER expose internal identifiers in responses\n"
    )


def build_messages(request: TStationChatRequest, *, system_prompt: str, extra_context: list[str] | None = None) -> list[BaseMessage]:
    """History → LangChain messages, with user context injected before the last user turn."""
    system_parts = [system_prompt]
    client_injection = load_client_injection()
    if client_injection:
        system_parts.append(f"## CLIENT INSTRUCTIONS\n{client_injection}")
    user_info = merged_user_info(request)
    if user_info:
        context_block = _user_context_block(user_info)
        if context_block:
            system_parts.append(context_block)
    system_parts.extend(extra_context or [])
    system_parts.append(f"[current_time: {get_current_time()}]")

    messages: list[BaseMessage] = [SystemMessage(content="\n\n".join(system_parts))]
    for msg in request.messages:
        content = str(msg.get("content") or "")
        role = msg.get("role")
        if role == "assistant":
            messages.append(AIMessage(content=content))
        elif role == "system":
            messages.append(SystemMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


def last_user_text(request: TStationChatRequest) -> str:
    for msg in reversed(request.messages):
        if msg.get("role") == "user":
            return str(msg.get("content") or "")
    return ""
