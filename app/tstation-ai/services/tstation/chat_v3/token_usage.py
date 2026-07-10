"""Real per-turn LLM token usage, captured from actual model responses.

Every chat_v3 LLM call (router, tool loop, QC, template builder, quick
replies) shares one callback attached via trace_config. on_llm_end fires at
the raw ChatModel layer before any structured-output parsing strips the
message down, so this works for both plain and structured-output calls.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


def _extract_total(usage: dict[str, Any]) -> int:
    total = usage.get("total_tokens")
    if total is not None:
        try:
            return int(total)
        except (TypeError, ValueError):
            pass
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
    try:
        return int(input_tokens) + int(output_tokens)
    except (TypeError, ValueError):
        return 0


class TurnTokenUsage:
    """Accumulates real token usage across every LLM call made during one turn."""

    def __init__(self) -> None:
        self.total_tokens = 0

    def add(self, usage: dict[str, Any] | None) -> None:
        if usage:
            self.total_tokens += _extract_total(usage)

    def callback(self) -> BaseCallbackHandler:
        return _UsageCallbackHandler(self)


class _UsageCallbackHandler(BaseCallbackHandler):
    def __init__(self, tracker: TurnTokenUsage) -> None:
        self._tracker = tracker

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        for generation_list in getattr(response, "generations", None) or []:
            for generation in generation_list:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None) if message else None
                if not usage and getattr(response, "llm_output", None):
                    usage = response.llm_output.get("token_usage")
                self._tracker.add(usage)
