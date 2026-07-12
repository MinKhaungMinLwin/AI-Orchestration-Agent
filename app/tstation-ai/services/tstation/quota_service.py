"""
Per-user monthly token quota enforced via Redis.

Key  : quota:tokens:{user_id}:{YYYY-MM}
TTL  : auto-expires at end of month (KST UTC+9)
Score: posted to Langfuse trace as "monthly_tokens_used" after each turn,
       and "quota_blocked" when a request is denied.
"""
import calendar
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_KST = timedelta(hours=9)
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
        tracer.create_score(trace_id=trace_id, name=name, value=value, comment=comment)
    except Exception as exc:
        logger.debug("[QUOTA] Langfuse score failed (%s): %s", name, exc)


def record_monthly_tokens(user_id: str, tokens: int, trace_id: str, limit: int) -> int:
    """Add tokens to a user's monthly counter and mirror the new total to Langfuse.

    Shared by every caller that has a real per-turn token count to report —
    the crude text-length estimate (legacy/llm_first) and chat_v3's real
    usage_metadata sum both funnel through this one place.
    """
    new_total = add_monthly_tokens(user_id, tokens)
    logger.info("[QUOTA] %s: %d / %d tokens this month", user_id, new_total, limit)
    post_langfuse_score(
        trace_id, "monthly_tokens_used", float(new_total),
        f"{new_total:,} / {limit:,} tokens this month",
    )
    return new_total


def _post_reconciled_monthly_score(user_id: str, total: int, limit: int) -> None:
    """Post a corrected monthly_tokens_used score that shows under the user.

    Reconcile runs outside any chat turn, so there is no existing trace to hang
    the score on. The Scores tab derives its User column from the trace's
    user_id, so we create a minimal trace carrying this user_id (mirrors how
    service.py builds its parent span + score_trace) and score it. A flush is
    required because reconcile is typically invoked as a one-off command whose
    process exits immediately — without it the score never reaches Langfuse.

    Best-effort: any failure is logged and swallowed; the Redis fix already stuck.
    """
    try:
        import uuid

        from config.tracing import _tracing_enabled, tracer

        if not _tracing_enabled or not tracer:
            return
        trace_id = uuid.uuid4().hex
        span = tracer.start_span(name="quota_reconciliation", trace_context={"trace_id": trace_id})
        try:
            span.update_trace(user_id=user_id, name="quota_reconciliation")
        finally:
            span.end()
        post_langfuse_score(
            trace_id, "monthly_tokens_used", float(total),
            f"{total:,} / {limit:,} tokens this month (reconciled)",
        )
        tracer.flush()
    except Exception as exc:
        logger.debug("[QUOTA] reconciled score post failed for %s: %s", user_id, exc)


def reconcile_user_from_langfuse(user_id: str) -> int | None:
    """Overwrite the Redis counter with this user's real monthly token total from Langfuse.

    The live per-turn counter (crude estimate or in-process real-usage sum) can
    drift from reality — either by under-measuring, or by missing traffic that
    never passed through the quota-gated endpoint at all. This reads Langfuse's
    own observation-level totals (the same numbers shown in the Users tab),
    corrects Redis to match, and posts a corrected monthly_tokens_used score so
    the Scores tab reflects the real total immediately (over-limit users are then
    blocked and can't post a fresh score via a normal turn).

    Best-effort: returns None (and logs) on any failure, real usage is unaffected.
    """
    import json as _json

    try:
        from langfuse.api.client import FernLangfuse

        from config.env import settings

        client = FernLangfuse(
            # The SDK's own request paths already start with "api/public/..." relative
            # to base_url — do not append "/api/public" here or every call 404s on a
            # doubled path (.../api/public/api/public/metrics).
            base_url=settings.LANGFUSE_HOST.rstrip("/"),
            x_langfuse_public_key=settings.LANGFUSE_PUBLIC_KEY,
            username=settings.LANGFUSE_PUBLIC_KEY,
            password=settings.LANGFUSE_SECRET_KEY,
        )
        now = _now_kst()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        query = _json.dumps({
            "view": "observations",
            "metrics": [{"measure": "totalTokens", "aggregation": "sum"}],
            "filters": [{"column": "userId", "operator": "=", "value": user_id, "type": "string"}],
            "fromTimestamp": month_start.isoformat(),
            "toTimestamp": now.isoformat(),
        })
        response = client.metrics.metrics(query=query)
        rows = getattr(response, "data", None) or []
        real_total = int((rows[0] or {}).get("sum_totalTokens") or 0) if rows else 0
    except Exception as exc:
        logger.warning("[QUOTA] Langfuse reconciliation failed for %s: %s", user_id, exc)
        return None

    from config.env import settings

    from services.tstation.chat_history_service import get_redis_client
    redis = get_redis_client()
    redis.set(_quota_key(user_id), real_total, ex=_seconds_until_month_end())
    logger.info("[QUOTA] Reconciled %s from Langfuse: %d real tokens this month", user_id, real_total)
    _post_reconciled_monthly_score(user_id, real_total, settings.MONTHLY_TOKEN_LIMIT)
    return real_total
