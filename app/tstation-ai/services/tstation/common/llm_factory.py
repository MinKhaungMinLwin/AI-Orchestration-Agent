from langchain_litellm import ChatLiteLLM

from config.env import settings


def build_chat_llm(
    *,
    model_name: str,
    streaming: bool = False,
    temperature: float | None = None,
) -> ChatLiteLLM:
    params = {
        "model": f"{settings.AI_DEFAULT_PROVIDER}/{model_name}",
        "streaming": streaming,
    }

    if settings.AI_USE_GATEWAY:
        params["api_base"] = settings.AI_GATEWAY_BASE_URL
        params["api_key"] = settings.AI_GATEWAY_API_KEY
    else:
        if settings.AI_DEFAULT_PROVIDER != "openai":
            raise ValueError(
                "AI_USE_GATEWAY=false currently supports AI_DEFAULT_PROVIDER=openai only."
            )
        params["api_key"] = settings.OPENAI_API_KEY

    if temperature is not None:
        params["temperature"] = temperature

    return ChatLiteLLM(**params)
