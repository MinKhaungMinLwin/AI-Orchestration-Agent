"""SSE event builders — the only place V3 formats stream events.

Event contract mirrors V2 so the FE and the API layer
(`stream_chat_response`) keep working unchanged.
"""

import json

AGENT_NAME = "[V3 CHAT]"


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def token(content: str) -> str:
    return sse({"type": "token", "content": content})


def message(content: str, agent: str = AGENT_NAME) -> str:
    return sse({"type": "message", "content": content, "agent": agent})


def status(text: str) -> str:
    return sse({"type": "status", "status": text})


def tool_start(tool_name: str, display_name: str) -> str:
    return sse({"type": "status", "status": "tool_start", "tool": tool_name, "display_name": display_name})


def tool_result(tool_name: str, tool_input: dict, output: str) -> str:
    return sse({"type": "tool", "tool": tool_name, "input": tool_input, "output": output, "node": AGENT_NAME})


def agent_flow(agent: str, flow_status: str) -> str:
    return sse({"type": "agent_flow", "agent": agent, "status": flow_status})


def data_event(template: str, data: dict, **extra) -> str:
    return sse({"type": "data", "template": template, "data": data, **extra})


def done() -> list[str]:
    """Terminal event sequence closing every V3 stream."""
    return [sse({"type": "DONE"}), "data: [DONE]\n\n"]


def chunk_text(content: str | list) -> str:
    """Normalize an LLM chunk's content (string or content-block list) to text."""
    if isinstance(content, str):
        return content
    return "".join(
        part.get("text", "") if isinstance(part, dict) else str(part)
        for part in content
    )
