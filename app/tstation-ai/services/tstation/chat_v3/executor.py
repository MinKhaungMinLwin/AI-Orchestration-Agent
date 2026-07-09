"""Native tool-calling loop: the LLM decides which tools to call.

No dispatch rules — tools for the routed domain are bound to the model
and it chooses. Streams answer tokens and tool progress as SSE strings;
final state is available on the instance after the stream ends.
"""

import json
import logging
from collections.abc import Callable

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from services.tstation.chat_v3 import sse
from services.tstation.chat_v3.llm import get_chat_llm
from services.tstation.policies.inventory_response_policy import redact_inventory_output_for_model
from services.tstation.policies.vehicle_category_catalog import match_vehicle_model_category

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4
_TOOL_OUTPUT_PREVIEW_CHARS = 4000
_CAR_MODEL_GROUP_TOOL = "search_car_model_groups_tool"
_RECOMMENDATION_TOOL = "get_products_recommendations_tool"


def _tool_output_text(output: object) -> str:
    if isinstance(output, str):
        return output
    try:
        return json.dumps(output, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(output)


def _normalize_tool_call(call: dict) -> dict:
    """Map removed V3 discovery tools to the current executable recommendation path."""
    name = call.get("name") or ""
    if name != _CAR_MODEL_GROUP_TOOL:
        return call

    raw_args = call.get("args")
    args = raw_args if isinstance(raw_args, dict) else {}
    keyword = str(
        args.get("keyword")
        or args.get("car_model")
        or args.get("vehicle_query")
        or args.get("query")
        or ""
    ).strip()

    recommendation_args: dict[str, object] = {"rcmd_type": "tstation", "limit": 3}
    match = match_vehicle_model_category(keyword)
    if match is not None:
        recommendation_args["vehicle_type"] = match.category

    normalized = dict(call)
    normalized["name"] = _RECOMMENDATION_TOOL
    normalized["args"] = recommendation_args
    logger.info(
        "[CHAT_V3] rewrote removed tool %s to %s args=%s",
        _CAR_MODEL_GROUP_TOOL,
        _RECOMMENDATION_TOOL,
        recommendation_args,
    )
    return normalized


def _model_visible_tool_output(name: str, output_text: str) -> str:
    return redact_inventory_output_for_model(name, output_text)


class ToolLoopExecutor:
    """One conversation turn: LLM ↔ tools until the model answers in text."""

    def __init__(
        self,
        messages: list[BaseMessage],
        tools: list,
        display_names: dict[str, str],
        *,
        stream_tokens: bool = True,
        trace_config: dict | None = None,
        tool_call_normalizer: Callable[[dict], dict] | None = None,
    ):
        self._messages = list(messages)
        self._tools = {t.name: t for t in tools}
        self._display_names = display_names
        self._stream_tokens = stream_tokens
        self._trace_config = trace_config
        self._tool_call_normalizer = tool_call_normalizer
        self.final_text: str = ""
        self.tool_calls: list[dict] = []

    async def stream(self):
        llm = get_chat_llm()
        if self._tools:
            llm = llm.bind_tools(list(self._tools.values()))

        for _ in range(MAX_TOOL_ROUNDS + 1):
            accumulated = None
            round_text = ""
            async for chunk in llm.astream(self._messages, config=self._trace_config):
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
        async for chunk in get_chat_llm().astream(self._messages, config=self._trace_config):
            text = sse.chunk_text(chunk.content)
            if text:
                final_text += text
                if self._stream_tokens:
                    yield sse.token(text)
        self.final_text = final_text

    async def _run_tool(self, call: dict):
        call = _normalize_tool_call(call)
        if self._tool_call_normalizer is not None:
            call = self._tool_call_normalizer(call)
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
                output = await tool.ainvoke(args, config=self._trace_config)
                output_text = _tool_output_text(output)
            except Exception as exc:
                logger.exception("[CHAT_V3] tool %s failed", name)
                output_text = f"Tool error: {exc}"
        self.tool_calls.append({"name": name, "args": args, "output": output_text})
        model_visible_output = _model_visible_tool_output(name, output_text)
        yield sse.tool_result(name, args, model_visible_output[:_TOOL_OUTPUT_PREVIEW_CHARS])
        yield sse.agent_flow(display, "error" if output_text.startswith("Tool error") else "success")
        self._messages.append(
            ToolMessage(content=model_visible_output[:_TOOL_OUTPUT_PREVIEW_CHARS], tool_call_id=call_id)
        )
