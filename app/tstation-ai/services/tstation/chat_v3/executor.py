"""Native tool-calling loop: the LLM decides which tools to call.

No dispatch rules — tools for the routed domain are bound to the model
and it chooses. Streams answer tokens and tool progress as SSE strings;
final state is available on the instance after the stream ends.
"""

import json
import logging

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from services.tstation.chat_v3 import sse
from services.tstation.chat_v3.llm import get_chat_llm

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4
_TOOL_OUTPUT_PREVIEW_CHARS = 4000


def _tool_output_text(output: object) -> str:
    if isinstance(output, str):
        return output
    try:
        return json.dumps(output, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(output)


class ToolLoopExecutor:
    """One conversation turn: LLM ↔ tools until the model answers in text."""

    def __init__(
        self,
        messages: list[BaseMessage],
        tools: list,
        display_names: dict[str, str],
        *,
        stream_tokens: bool = True,
    ):
        self._messages = list(messages)
        self._tools = {t.name: t for t in tools}
        self._display_names = display_names
        self._stream_tokens = stream_tokens
        self.final_text: str = ""
        self.tool_calls: list[dict] = []

    async def stream(self):
        llm = get_chat_llm()
        if self._tools:
            llm = llm.bind_tools(list(self._tools.values()))

        for _ in range(MAX_TOOL_ROUNDS + 1):
            accumulated = None
            round_text = ""
            async for chunk in llm.astream(self._messages):
                accumulated = chunk if accumulated is None else accumulated + chunk
                text = sse.chunk_text(chunk.content)
                if text:
                    round_text += text
                    if self._stream_tokens:
                        yield sse.token(text)

            ai_message = accumulated if isinstance(accumulated, AIMessage) else AIMessage(content=round_text)
            tool_calls = getattr(ai_message, "tool_calls", None) or []
            if not tool_calls:
                self.final_text = round_text
                return

            self._messages.append(ai_message)
            for call in tool_calls:
                async for event in self._run_tool(call):
                    yield event

        # Tool budget exhausted — force a final text answer without tools.
        final_text = ""
        async for chunk in get_chat_llm().astream(self._messages):
            text = sse.chunk_text(chunk.content)
            if text:
                final_text += text
                if self._stream_tokens:
                    yield sse.token(text)
        self.final_text = final_text

    async def _run_tool(self, call: dict):
        name = call.get("name") or ""
        args = call.get("args") or {}
        call_id = call.get("id") or name
        tool = self._tools.get(name)
        display = self._display_names.get(name, name)
        yield sse.tool_start(name, display)
        if tool is None:
            output_text = f"Unknown tool: {name}"
        else:
            try:
                output = await tool.ainvoke(args)
                output_text = _tool_output_text(output)
            except Exception as exc:
                logger.exception("[CHAT_V3] tool %s failed", name)
                output_text = f"Tool error: {exc}"
        self.tool_calls.append({"name": name, "args": args, "output": output_text})
        yield sse.tool_result(name, args, output_text[:_TOOL_OUTPUT_PREVIEW_CHARS])
        yield sse.agent_flow(display, "error" if output_text.startswith("Tool error") else "success")
        self._messages.append(ToolMessage(content=output_text[:_TOOL_OUTPUT_PREVIEW_CHARS], tool_call_id=call_id))
