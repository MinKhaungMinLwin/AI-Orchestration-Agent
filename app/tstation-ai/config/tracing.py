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
_tracing_enabled = False

try:
    tracer.auth_check()
    _tracing_enabled = True
    logger.info(
        "Enabled tracing with project '%s', environment '%s'",
        settings.LANGFUSE_PROJECT_NAME,
        settings.ENV,
    )
except Exception as exc:
    # Langfuse should never block API startup in container environments.
    logger.warning(
        "Langfuse unavailable during startup; continuing without tracing callbacks: %s",
        exc,
    )

# Stateless handler — per-run context is supplied via RunnableConfig metadata.
langfuse_handler = CallbackHandler() if _tracing_enabled else None


def build_trace_config(
    *,
    run_name: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
    tags: list[str] | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a RunnableConfig dict wiring the Langfuse callback + trace metadata.

    Pass the return value as `config=...` to any LangChain `invoke`/`stream` call.
    In Langfuse v3, pass parent_span_id to nest this call under an existing span,
    making all sub-calls children of the `chat` root span.
    """
    metadata: dict[str, Any] = {}
    if session_id:
        metadata["langfuse_session_id"] = session_id
    if user_id:
        metadata["langfuse_user_id"] = user_id
    all_tags = [settings.ENV.value if hasattr(settings.ENV, "value") else str(settings.ENV)]
    if tags:
        all_tags.extend(tags)
    metadata["langfuse_tags"] = all_tags
    if extra_metadata:
        metadata.update(extra_metadata)

    config: dict[str, Any] = {"metadata": metadata}
    if _tracing_enabled:
        if trace_id:
            tc: dict[str, str] = {"trace_id": trace_id}
            if parent_span_id:
                tc["parent_span_id"] = parent_span_id
            config["callbacks"] = [CallbackHandler(trace_context=tc)]
        elif langfuse_handler is not None:
            config["callbacks"] = [langfuse_handler]
    if run_name:
        config["run_name"] = run_name
    return config
