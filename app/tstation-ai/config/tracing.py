import contextlib
import logging
from contextvars import ContextVar
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
    # Langfuse is observability-only; keep chat startup clean when it is unavailable.
    logger.info(
        "Langfuse unavailable during startup; tracing callbacks disabled: %s",
        exc,
    )


def truncate_for_trace(value: Any, max_chars: int = MAX_TRACE_OUTPUT_CHARS) -> Any:
    """Recursively clip large str/dict/list values before sending to Langfuse."""
    if isinstance(value, str):
        if len(value) > max_chars:
            suffix = f"... ({len(value)} chars total)"
            return value[:max_chars - len(suffix)] + suffix
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


# Per-request trace name stored in a ContextVar so callbacks can read it
# without threading the value through every function signature.
_trace_name_var: ContextVar[str | None] = ContextVar("_trace_name", default=None)


def set_trace_name(name: str | None) -> None:
    """Set the desired Langfuse trace name for the current request context."""
    _trace_name_var.set(name)


def _redact_system_entries(value: Any, placeholder: str) -> Any:
    from langchain_core.messages import BaseMessage, SystemMessage

    if isinstance(value, BaseMessage):
        return SystemMessage(content=placeholder) if value.type == "system" else value
    if isinstance(value, dict):
        if str(value.get("role") or value.get("type") or "").lower() == "system":
            return {**value, "content": placeholder}
        return {key: _redact_system_entries(val, placeholder) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        if len(value) == 2 and isinstance(value[0], str) and value[0].lower() == "system":
            return (value[0], placeholder) if isinstance(value, tuple) else [value[0], placeholder]
        redacted_items = [_redact_system_entries(item, placeholder) for item in value]
        return tuple(redacted_items) if isinstance(value, tuple) else redacted_items
    return value


class FilteredCallbackHandler(CallbackHandler):
    """LangChain callback handler that:
    - Replaces system prompts with ``[prompt:<name>]`` to keep generation spans small.
    - Sets the Langfuse trace name to the user's message (read from ContextVar)
      on the root chain span, overriding the default LangChain class name.
    """

    def __init__(self, prompt_name: str | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("update_trace", False)
        super().__init__(**kwargs)
        self._prompt_name = prompt_name or "agent"

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: Any,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> Any:
        filtered_inputs = _redact_system_entries(inputs, f"[prompt:{self._prompt_name}]")
        result = super().on_chain_start(
            serialized, filtered_inputs, run_id=run_id, parent_run_id=parent_run_id, **kwargs
        )
        # For the root chain of each callback handler (parent_run_id is None from
        # LangChain's perspective), override the trace name with the user message.
        if parent_run_id is None:
            trace_name = _trace_name_var.get()
            if trace_name:
                obs = getattr(self, "runs", {}).get(run_id)
                if obs is not None:
                    try:
                        obs.update_trace(name=trace_name)
                    except Exception:
                        pass
        return result

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: Any,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> Any:
        placeholder = f"[prompt:{self._prompt_name}]"
        filtered_outputs = _redact_system_entries(outputs, placeholder)
        if kwargs.get("inputs") is not None:
            kwargs["inputs"] = _redact_system_entries(kwargs["inputs"], placeholder)
        return super().on_chain_end(
            filtered_outputs, run_id=run_id, parent_run_id=parent_run_id, **kwargs
        )

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
        metadata["user"] = user_id  # LiteLLM proxy uses this for per-user spend tracking
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
    # Stash trace_id and parent_span_id under `configurable` so downstream
    # code (e.g. BaseAgent.stream) can open manual child spans without
    # threading the ids through every signature.
    if trace_id:
        config.setdefault("configurable", {})["tstation_trace_id"] = trace_id
        if parent_span_id:
            config["configurable"]["tstation_parent_span_id"] = parent_span_id
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


def safe_trace_update(observation: Any, *, trace: bool = False, **kwargs: Any) -> None:
    """Best-effort Langfuse observation/trace update.

    Observability must never block or fail a chat response, so callers can use
    this wrapper for non-critical metadata updates.
    """
    if observation is None:
        return
    try:
        if trace:
            observation.update_trace(**kwargs)
        else:
            observation.update(**kwargs)
    except Exception as exc:
        logger.debug("[TRACE] update failed: %s", exc)
