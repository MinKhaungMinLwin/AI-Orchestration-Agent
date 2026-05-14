import logging
import time
from config.tracing import tracer, _tracing_enabled

logger = logging.getLogger(__name__)

CLIENT_PROMPT_PREFIX = "inject/"
_NAMES_CACHE_TTL = 60  # seconds

_cached_names: list[str] = []
_cached_names_at: float = 0.0


def _load_inject_prompt_names() -> list[str]:
    """List all prompts with 'inject/' prefix, cached for 60s."""
    global _cached_names, _cached_names_at
    now = time.monotonic()
    if now - _cached_names_at < _NAMES_CACHE_TTL:
        return _cached_names
    try:
        result = tracer.api.prompts.list()
        names = [p.name for p in result.data if p.name.startswith(CLIENT_PROMPT_PREFIX)]
        _cached_names = names
        _cached_names_at = now
        logger.debug("[CLIENT_PROMPT] Found %d inject prompt(s): %s", len(names), names)
        return names
    except Exception as exc:
        logger.warning("[CLIENT_PROMPT] Failed to list prompts: %s", exc)
        return _cached_names


def load_client_injection() -> str:
    """Load all Langfuse prompts with 'inject/' prefix and concatenate.

    Hankook creates prompts named 'inject/anything' to activate injection.
    Prompt list and content are both cached 60s; changes propagate within ~60s.
    Returns empty string if no prompts configured or Langfuse is unavailable.
    """
    if not _tracing_enabled:
        logger.debug("[CLIENT_PROMPT] Tracing disabled, skipping client prompt load.")
        return ""
    names = _load_inject_prompt_names()
    if not names:
        return ""
    texts: list[str] = []
    for name in names:
        try:
            prompt = tracer.get_prompt(name, cache_ttl_seconds=60)
            text = prompt.prompt.strip()
            if text:
                texts.append(text)
                logger.info("[CLIENT_PROMPT] Loaded '%s' (version=%s, chars=%d).", name, prompt.version, len(text))
        except Exception as exc:
            logger.warning("[CLIENT_PROMPT] Failed to load prompt '%s': %s", name, exc)
    combined = "\n\n".join(texts)
    if combined:
        logger.info("[CLIENT_PROMPT] Injecting %d prompt(s) (total chars=%d).", len(texts), len(combined))
    return combined
