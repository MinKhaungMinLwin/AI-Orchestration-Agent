"""
Per-user monthly token quota enforced via Redis.

Key  : quota:tokens:{user_id}:{YYYY-MM}
TTL  : auto-expires at end of month (KST UTC+7)
Score: posted to Langfuse trace as "monthly_tokens_used" after each turn,
       and "quota_blocked" when a request is denied.
"""
import calendar
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_KST = timedelta(hours=7)
_QUOTA_KEY = "quota:tokens:{user_id}:{ym}"


def _now_kst() -> datetime:
    return datetime.now(timezone.utc) + _KST


def _quota_key(user_id: str) -> str:
    return _QUOTA_KEY.format(user_id=user_id, ym=_now_kst().strftime("%Y-%m"))


def _seconds_until_month_end() -> int:
    now = _now_kst()
    days = calendar.monthrange(now.year, now.month)[1]
    end = now.replace(day=days, hour=23, minute=59, second=59, microsecond=0) + timedelta(seconds=1)
    return max(3600, int((end - now).total_seconds()))


def get_monthly_tokens(user_id: str) -> int:
    from services.tstation.chat_history_service import get_redis_client
    val = get_redis_client().get(_quota_key(user_id))
    return int(val) if val else 0


def add_monthly_tokens(user_id: str, tokens: int) -> int:
    from services.tstation.chat_history_service import get_redis_client
    redis = get_redis_client()
    key = _quota_key(user_id)
    new_total = redis.incrby(key, tokens)
    redis.expire(key, _seconds_until_month_end())
    return new_total


def is_quota_exceeded(user_id: str, limit: int) -> bool:
    return get_monthly_tokens(user_id) >= limit


def estimate_tokens(text: str) -> int:
    """~3 UTF-8 bytes per token — covers Korean mixed with English/numbers."""
    return max(1, len(text.encode("utf-8")) // 3)


def post_langfuse_score(trace_id: str, name: str, value: float, comment: str) -> None:
    """Post a numeric score to a Langfuse trace. Failures are logged and ignored."""
    try:
        from config.tracing import tracer, _tracing_enabled
        if not _tracing_enabled or not tracer:
            return
        tracer.score(trace_id=trace_id, name=name, value=value, comment=comment)
    except Exception as exc:
        logger.debug("[QUOTA] Langfuse score failed (%s): %s", name, exc)
