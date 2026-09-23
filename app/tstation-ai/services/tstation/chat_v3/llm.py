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
    """Backward-compatible alias for the V3 composer model."""
    return get_composer_llm()


def _configured_model(setting_name: str) -> str:
    return str(getattr(settings, setting_name, "") or settings.AI_MODEL).strip()


def get_tool_selector_llm() -> ChatLiteLLM:
    """Fast model for the first tool-selection decision."""
    if "tool_selector" not in _instances:
        _instances["tool_selector"] = _make(
            _configured_model("AI_MODEL_TOOL_SELECTOR"),
            streaming=True,
            timeout=30,
        )
    return _instances["tool_selector"]


def get_composer_llm() -> ChatLiteLLM:
    """Fast model for grounded user-facing answers after tool execution."""
    if "composer" not in _instances:
        _instances["composer"] = _make(_configured_model("AI_MODEL_COMPOSER"), streaming=True)
    return _instances["composer"]


def get_fallback_llm() -> ChatLiteLLM:
    """Stronger one-shot fallback for rejected tool calls or failed grounded answers."""
    if "fallback" not in _instances:
        _instances["fallback"] = _make(_configured_model("AI_MODEL_FALLBACK"), streaming=True)
    return _instances["fallback"]


def get_router_llm() -> ChatLiteLLM:
    """Small fast model (AI_MODEL_MINI) — routing / structured decisions."""
    if "router" not in _instances:
        _instances["router"] = _make(settings.AI_MODEL_MINI, streaming=False, timeout=30)
    return _instances["router"]
