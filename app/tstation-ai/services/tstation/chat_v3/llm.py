"""LLM instances for chat V3 — lazy singletons per model tier."""

from langchain_litellm import ChatLiteLLM

from config.env import settings

_instances: dict[str, ChatLiteLLM] = {}


def _make(model_setting: str, *, streaming: bool, timeout: int = 120) -> ChatLiteLLM:
    return ChatLiteLLM(
        api_base=settings.AI_GATEWAY_BASE_URL,
        api_key=settings.AI_GATEWAY_API_KEY,
        model=f"{settings.AI_DEFAULT_PROVIDER}/{model_setting}",
        streaming=streaming,
        request_timeout=timeout,
    )


def get_chat_llm() -> ChatLiteLLM:
    """Main conversation model (AI_MODEL) — streams the user-facing answer."""
    if "chat" not in _instances:
        _instances["chat"] = _make(settings.AI_MODEL, streaming=True)
    return _instances["chat"]


def get_router_llm() -> ChatLiteLLM:
    """Small fast model (AI_MODEL_MINI) — routing / structured decisions."""
    if "router" not in _instances:
        _instances["router"] = _make(settings.AI_MODEL_MINI, streaming=False, timeout=30)
    return _instances["router"]
