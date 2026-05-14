"""
Tool Result Cache — Redis-based caching for expensive backend tool calls.

Usage:
    @tool_cache(ttl=300)
    def my_tool_function(arg1, arg2):
        ...

The cache key is derived from the function name + all positional/keyword arguments.
Cache is stored in Redis with the configured TTL (seconds).
"""
import hashlib
import json
import logging
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)

_TOOL_CACHE_PREFIX = "tool_cache"


def _make_cache_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """Build a stable Redis key from function name + arguments."""
    payload = json.dumps({"fn": func_name, "args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    digest = hashlib.md5(payload.encode()).hexdigest()
    return f"{_TOOL_CACHE_PREFIX}:{func_name}:{digest}"


def _is_cacheable_result(result: Any) -> bool:
    """Cache only successful tool responses so transient BE errors are retried."""
    return not (isinstance(result, dict) and result.get("status") == "error")


def tool_cache(ttl: int = 300) -> Callable:
    """Decorator to cache tool function results in Redis.

    Args:
        ttl: Cache time-to-live in seconds. Default 300 (5 minutes).
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            from services.tstation.chat_history_service import get_redis_client
            try:
                redis_client = get_redis_client()
                cache_key = _make_cache_key(func.__name__, args, kwargs)

                cached = redis_client.get(cache_key)
                if cached is not None:
                    logger.debug("[TOOL_CACHE] HIT %s key=%s", func.__name__, cache_key[-8:])
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"[TOOL_CACHE] Redis read failed for {func.__name__}, falling back to direct call: {e}")
                return func(*args, **kwargs)

            result = func(*args, **kwargs)
            if not _is_cacheable_result(result):
                logger.debug("[TOOL_CACHE] SKIP %s key=%s reason=error_response", func.__name__, cache_key[-8:])
                return result

            try:
                redis_client.setex(cache_key, ttl, json.dumps(result, default=str))
                logger.debug("[TOOL_CACHE] SET %s key=%s ttl=%ss", func.__name__, cache_key[-8:], ttl)
            except Exception as e:
                logger.warning(f"[TOOL_CACHE] Redis write failed for {func.__name__}: {e}")
            return result

        return wrapper
    return decorator
