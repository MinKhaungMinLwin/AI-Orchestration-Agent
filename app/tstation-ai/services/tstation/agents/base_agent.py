from abc import ABC, abstractmethod
from typing import TypeVar, Generic

from langchain.messages import AIMessageChunk, AIMessage, ToolMessage
from langchain.agents import create_agent


T = TypeVar("T")


class BaseAgent(ABC):
    """Base agent class with streaming support for agent name and AF (Agent Function) mapping."""

    TOOL_TO_AF_MAP: dict[str, str] = {}

    def __init__(self, model, tools: list | None = None, system_prompt: str = "", name: str = ""):
        self.name = name
        self.agent = create_agent(
            model=model,
            tools=tools,
            debug=True,
            system_prompt=system_prompt,
            name=name,
        )

    def invoke(self, messages: list[dict]) -> str:
        result = self.agent.invoke({"messages": messages})
        return result["messages"][-1].content

    def stream(self, messages: list[dict]):
        """
        Supported Stream modes:
        - agent_flow: Agent name or AF when active (for UI display)
        - tokens: AI response tokens
        - message: Agent messages with agent name
        - tool: Tool execution results with tool name and AF
        """
        # Yield agent start event
        yield {"type": "agent_flow", "agent": f"[{self.name}]"}

        for mode, chunk in self.agent.stream(
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
                        yield {
                            "type": "message",
                            "content": message.content,
                            "node": node,
                            "agent": self.name,
                        }
                    elif isinstance(message, ToolMessage):
                        af = self.TOOL_TO_AF_MAP.get(message.name, "Unknown")
                        # Yield AF when tool is called
                        yield {"type": "agent_flow", "agent": f"[{af} AF]"}
                        yield {
                            "type": "tool",
                            "content": message.content,
                            "node": node,
                            "tool": message.name,
                        }
