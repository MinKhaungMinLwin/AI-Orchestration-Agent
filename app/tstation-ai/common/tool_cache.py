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


def tool_cache(ttl: int = 300) -> Callable:
    """Decorator to cache tool function results in Redis.

    Args:
        ttl: Cache time-to-live in seconds. Default 300 (5 minutes).
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            from services.tstation.chat_history_service import get_redis_client
            redis_client = get_redis_client()
            cache_key = _make_cache_key(func.__name__, args, kwargs)

            cached = redis_client.get(cache_key)
            if cached is not None:
                logger.debug(f"[TOOL_CACHE] HIT {func.__name__} key={cache_key[-8:]}")
                return json.loads(cached)

            result = func(*args, **kwargs)
            redis_client.setex(cache_key, ttl, json.dumps(result, default=str))
            logger.debug(f"[TOOL_CACHE] SET {func.__name__} key={cache_key[-8:]} ttl={ttl}s")
            return result

        return wrapper
    return decorator
