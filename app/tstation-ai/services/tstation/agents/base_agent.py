from abc import ABC
from collections.abc import Callable
from typing import TypeVar
import json

from langchain.messages import AIMessageChunk, AIMessage, ToolMessage
from langchain.agents import create_agent


T = TypeVar("T")


class BaseAgent(ABC):
    """Base agent class with streaming support for agent name and AF (Agent Function) mapping."""

    TOOL_TO_AF_MAP: dict[str, str] = {}
    TOOL_TO_TEMPLATE_MAP: dict[str, str] = {}

    def __init__(self, model, tools: list | None = None, system_prompt: str | Callable[[], str] = "", name: str = ""):
        self.name = name
        self._model = model
        self._tools = tools
        self._system_prompt = system_prompt

    def _build_agent(self):
        prompt = self._system_prompt() if callable(self._system_prompt) else self._system_prompt
        return create_agent(
            model=self._model,
            tools=self._tools,
            debug=True,
            system_prompt=prompt,
            name=self.name,
        )

    def invoke(self, messages: list[dict]) -> str:
        agent = self._build_agent()
        result = agent.invoke({"messages": messages})
        return result["messages"][-1].content

    def stream(self, messages: list[dict]):
        """
        Supported Stream modes:
        - agent_flow: Agent name or AF when active (for UI display)
        - tokens: AI response tokens
        - message: Agent messages with agent name
        - tool: Tool execution results with tool name, input, and output
        """
        agent = self._build_agent()
        # Track tool calls to capture input args
        tool_calls_map: dict[str, dict] = {}

        for mode, chunk in agent.stream(
            {"messages": messages},
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                token, _ = chunk
                if isinstance(token, AIMessageChunk) and token.text:
                    yield {"type": "token", "content": token.text}

            elif mode == "updates":
                for node, update in chunk.items():
                    message = update["messages"][-1]
                    if isinstance(message, AIMessage):
                        # Capture tool calls for input tracking
                        if hasattr(message, "tool_calls") and message.tool_calls:
                            for tc in message.tool_calls:
                                tool_calls_map[tc["id"]] = {"name": tc["name"], "args": tc.get("args", {})}
                        yield {
                            "type": "message",
                            "content": message.content,
                            "node": node,
                            "agent": self.name,
                        }
                    elif isinstance(message, ToolMessage):
                        af = self.TOOL_TO_AF_MAP.get(message.name, "Unknown")
                        # Extract status from tool result
                        tool_status = "success"
                        try:
                            tool_result = json.loads(message.content) if isinstance(message.content, str) else message.content
                            if isinstance(tool_result, dict):
                                tool_status = tool_result.get("status", "success")
                        except (json.JSONDecodeError, TypeError):
                            pass
                        # Yield AF with tool status
                        yield {"type": "agent_flow", "agent": f"[{af} AF]", "status": tool_status}
                        # Get tool input from captured tool_calls
                        tool_input = tool_calls_map.get(message.tool_call_id, {})
                        yield {
                            "type": "tool",
                            "input": tool_input.get("args", {}),
                            "output": message.content,
                            "node": node,
                            "tool": message.name,
                        }

        yield {"type": "token", "content": "\n\n"}

    def stream_template(self, messages: list[dict]):
        """
        Stream that transforms tool calls into data template events.
        Yields ONLY data events (no token or agent_flow events).

        Use this when you want to format tool outputs as UI templates directly.
        """
        import json
        import logging
        logger = logging.getLogger(__name__)
        agent = self._build_agent()

        tool_called = False

        for mode, chunk in agent.stream(
            {"messages": messages},
            stream_mode=["messages", "updates"],
        ):
            if mode == "updates":
                for node, update in chunk.items():
                    message = update["messages"][-1]
                    if isinstance(message, ToolMessage):
                        tool_called = True
                        template_name = self.TOOL_TO_TEMPLATE_MAP.get(message.name)
                        if not template_name:
                            logger.warning(f"[UI_TEMPLATE] Tool {message.name} has no template mapping")
                            continue
                        # Parse tool output (message.content is JSON string)
                        try:
                            tool_output = json.loads(message.content)
                            tool_data = tool_output.get("data", {})
                        except (json.JSONDecodeError, TypeError):
                            logger.warning(f"[UI_TEMPLATE] Failed to parse tool output for {message.name}")
                            tool_data = {}

                        # Skip if tool_data is null or empty
                        if not tool_data:
                            logger.warning(f"[UI_TEMPLATE] Empty tool_data for {message.name}, skipping")
                            continue

                        # Yield data event with tool's actual output data
                        yield {
                            "type": "data",
                            "template": template_name,
                            "data": tool_data,
                        }


        if not tool_called:
            logger.warning("[UI_TEMPLATE] Agent generated no tool calls — templates not rendered")
