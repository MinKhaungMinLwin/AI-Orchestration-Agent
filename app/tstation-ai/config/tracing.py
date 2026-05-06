import contextlib
import logging
from typing import Any, Iterator

from config.env import Environment, settings
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

logger = logging.getLogger(__name__)

# Max payload size sent to Langfuse per field (chars / list items).
MAX_TRACE_INPUT_CHARS = 2000
MAX_TRACE_OUTPUT_CHARS = 2000
MAX_TRACE_LIST_ITEMS = 10

tracer = Langfuse(
    host=settings.LANGFUSE_HOST,
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    environment=settings.ENV,
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


def truncate_for_trace(value: Any, max_chars: int = MAX_TRACE_OUTPUT_CHARS) -> Any:
    """Recursively clip large str/dict/list values before sending to Langfuse."""
    if isinstance(value, str):
        if len(value) > max_chars:
            return value[:max_chars] + f"... ({len(value)} chars total)"
        return value
    if isinstance(value, dict):
        return {k: truncate_for_trace(v, max_chars) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = list(value)[:MAX_TRACE_LIST_ITEMS]
        truncated = [truncate_for_trace(v, max_chars) for v in items]
        if len(value) > MAX_TRACE_LIST_ITEMS:
            truncated.append(f"... ({len(value) - MAX_TRACE_LIST_ITEMS} more items)")
        return truncated
    return value


class FilteredCallbackHandler(CallbackHandler):
    """LangChain callback handler that replaces system prompts with ``[prompt:<name>]``
    before sending to Langfuse, so 800-line prompts don't appear in every generation span.
    """

    def __init__(self, prompt_name: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._prompt_name = prompt_name or "agent"

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list],
        **kwargs: Any,
    ) -> Any:
        from langchain_core.messages import SystemMessage
        filtered = [
            [
                SystemMessage(content=f"[prompt:{self._prompt_name}]")
                if getattr(msg, "type", None) == "system"
                else msg
                for msg in group
            ]
            for group in messages
        ]
        return super().on_chat_model_start(serialized, filtered, **kwargs)


# Stateless handler — per-run context is supplied via RunnableConfig metadata.
langfuse_handler = FilteredCallbackHandler() if _tracing_enabled else None


def build_trace_config(
    *,
    run_name: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
    tags: list[str] | None = None,
    extra_metadata: dict[str, Any] | None = None,
    prompt_name: str | None = None,
) -> dict[str, Any]:
    """Return a LangChain RunnableConfig wired with the Langfuse callback and trace metadata."""
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
            config["callbacks"] = [FilteredCallbackHandler(
                prompt_name=prompt_name,
                trace_context=tc,
            )]
        elif langfuse_handler is not None:
            config["callbacks"] = [langfuse_handler]
    if run_name:
        config["run_name"] = run_name
    return config


class _NullSpan:
    """No-op span used when tracing is disabled — mirrors the Langfuse v3 span API."""

    id: str | None = None

    def end(self, *args: Any, **kwargs: Any) -> None:
        return None

    def update(self, *args: Any, **kwargs: Any) -> None:
        return None

    def update_trace(self, *args: Any, **kwargs: Any) -> None:
        return None

    def event(self, *args: Any, **kwargs: Any) -> None:
        return None


_NULL_SPAN = _NullSpan()


@contextlib.contextmanager
def trace_span(
    name: str,
    *,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
    input: Any = None,
) -> Iterator[Any]:
    """Open a Langfuse child span, or yield a no-op _NullSpan when tracing is off."""
    if not _tracing_enabled or not trace_id:
        yield _NULL_SPAN
        return

    truncated_input = truncate_for_trace(input, MAX_TRACE_INPUT_CHARS) if input is not None else None
    trace_context: dict[str, str] = {"trace_id": trace_id}
    if parent_span_id:
        trace_context["parent_span_id"] = parent_span_id

    try:
        span = tracer.start_span(
            name=name,
            trace_context=trace_context,
            input=truncated_input,
        )
    except Exception as exc:
        logger.debug("[TRACE] Failed to start span '%s': %s", name, exc)
        yield _NULL_SPAN
        return

    try:
        yield span
    finally:
        try:
            span.end()
        except Exception as exc:
            logger.debug("[TRACE] Failed to end span '%s': %s", name, exc)
