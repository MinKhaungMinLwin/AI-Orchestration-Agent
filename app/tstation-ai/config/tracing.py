import logging
from typing import Any

from config.env import Environment, settings
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

logger = logging.getLogger(__name__)

# Config
tracer = Langfuse(
    host=settings.LANGFUSE_HOST,
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    # Environment
    environment=settings.ENV,
    # Debug
    debug=True if settings.ENV == Environment.LOCAL else False,
)
tracer.auth_check()
# Stateless handler — per-run context is supplied via RunnableConfig metadata.
langfuse_handler = CallbackHandler()

logger.info(f"Enabled tracing with project '{settings.LANGFUSE_PROJECT_NAME}', environment '{settings.ENV}'")


def build_trace_config(
    *,
    run_name: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    trace_id: str | None = None,
    tags: list[str] | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a RunnableConfig dict wiring the Langfuse callback + trace metadata.

    Pass the return value as `config=...` to any LangChain `invoke`/`stream` call.
    """
    metadata: dict[str, Any] = {}
    if session_id:
        metadata["langfuse_session_id"] = session_id
    if user_id:
        metadata["langfuse_user_id"] = user_id
    if trace_id:
        metadata["langfuse_trace_id"] = trace_id
    all_tags = [settings.ENV.value if hasattr(settings.ENV, "value") else str(settings.ENV)]
    if tags:
        all_tags.extend(tags)
    metadata["langfuse_tags"] = all_tags
    if extra_metadata:
        metadata.update(extra_metadata)

    config: dict[str, Any] = {
        "callbacks": [langfuse_handler],
        "metadata": metadata,
    }
    if run_name:
        config["run_name"] = run_name
    return config
