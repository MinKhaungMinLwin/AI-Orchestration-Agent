"""Chat V3 — LLM-first chat service, zero regex.

Every decision (safety, policy guards, intent routing, slot extraction,
tool selection) is made by an LLM call — no rule tables, no keyword
matching. See docs/chat-v3/TODO.md for the architecture.
"""

from services.tstation.chat_v3.service import TStationChatServiceV3, chat, enabled

__all__ = ["TStationChatServiceV3", "chat", "enabled"]
