"""V3 Chat service — pure LLM chat.

The conversation is sent straight to the LLM and the answer is streamed
back unchanged: no routing rules, no tools, no regex guards, no QC.
Enabled via ``AI_CHAT_V3_PURE_LLM_ENABLED`` (V2 stays the default).
"""

import json
import logging
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_litellm import ChatLiteLLM

from config.env import settings
from schemas.tstation.chat import TStationChatRequest, TStationChatResponse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "당신은 한국타이어 T-Station의 친절한 AI 상담사입니다. 사용자와 자연스럽게 한국어로 대화하세요."

ERROR_RESPONSE = "요청을 처리하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."

_llm: ChatLiteLLM | None = None


def _get_llm() -> ChatLiteLLM:
    global _llm
    if _llm is None:
        _llm = ChatLiteLLM(
            api_base=settings.AI_GATEWAY_BASE_URL,
            api_key=settings.AI_GATEWAY_API_KEY,
            model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL}",
            streaming=True,
            request_timeout=120,
        )
    return _llm


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _llm_messages(request: TStationChatRequest) -> list[BaseMessage]:
    messages: list[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
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


def _chunk_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    return "".join(
        part.get("text", "") if isinstance(part, dict) else str(part)
        for part in content
    )


class TStationChatServiceV3:
    """V3 chat service: the LLM alone produces the answer."""

    @staticmethod
    async def chat(request: TStationChatRequest):
        logger.info("[CHAT_V3] Pure-LLM chat for session=%s", request.session_id)
        if request.stream:
            return StreamingResponse(
                TStationChatServiceV3._stream(request),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        result = await _get_llm().ainvoke(_llm_messages(request))
        return TStationChatResponse(content=_chunk_text(result.content))

    @staticmethod
    async def _stream(request: TStationChatRequest) -> AsyncIterator[str]:
        full_content = ""
        try:
            async for chunk in _get_llm().astream(_llm_messages(request)):
                text = _chunk_text(chunk.content)
                if text:
                    full_content += text
                    yield _sse({"type": "token", "content": text})
        except Exception:
            logger.exception("[CHAT_V3] stream failed")
            full_content = ERROR_RESPONSE
            yield _sse({"type": "token", "content": ERROR_RESPONSE})
        yield _sse({"type": "message", "content": full_content, "agent": "[V3 PURE LLM]"})
        yield _sse({
            "type": "data",
            "template": "quickReply",
            "data": {
                "assistantResponse": full_content,
                "quickReplies": [],
                "predictedDomains": [],
            },
        })
        yield _sse({"type": "DONE"})
        yield "data: [DONE]\n\n"


def enabled() -> bool:
    return bool(getattr(settings, "AI_CHAT_V3_PURE_LLM_ENABLED", True))
