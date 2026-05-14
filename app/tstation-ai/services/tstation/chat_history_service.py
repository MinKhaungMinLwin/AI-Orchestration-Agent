"""
Chat History Service - Redis-based conversation management.

Stores messages as JSON in sorted sets (chat:tmpl:{session_id}).
Session management per user_id from JWT token.
Slot persistence per session for conversation context tracking.

Retention: sliding TTL of CHAT_HISTORY_TTL_SECONDS (1 week). Each state-changing
operation refreshes TTL on the session's keys (tmpl, meta, user session set),
so active conversations stay alive while inactive sessions auto-expire after
1 week of no writes. Tool context has its own shorter TTL (see save_tool_context).
"""
import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from schemas.tstation.slots import ConversationSlots

import redis
import redis.asyncio as async_redis

from common.crypto import get_crypto_service
from common.jwt_utils import decode_jwt, get_user_info_from_token
from config.env import settings

logger = logging.getLogger(__name__)

# Redis client for conversation management
_redis_client: Optional[redis.Redis] = None
_async_redis_client: Optional[async_redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """Get Redis client for conversation management."""
    global _redis_client
    if _redis_client is None:
        redis_url = settings.REDIS_CONVERSATION_MANAGEMENT_URL

        # Parse URL: redis://:password@host:port/db
        _redis_client = redis.from_url(
            redis_url,
            socket_timeout=5,
            socket_connect_timeout=5,
            decode_responses=True,
        )
    return _redis_client


def get_async_redis_client() -> async_redis.Redis:
    """Get async Redis client for hot-path conversation operations."""
    global _async_redis_client
    if _async_redis_client is None:
        redis_url = settings.REDIS_CONVERSATION_MANAGEMENT_URL
        _async_redis_client = async_redis.from_url(
            redis_url,
            socket_timeout=5,
            socket_connect_timeout=5,
            decode_responses=True,
        )
    return _async_redis_client


# Key prefixes
SESSION_SET_KEY = "chat:user:{user_id}:sessions"
MESSAGES_KEY = "chat:messages:{session_id}"
META_KEY = "chat:meta:{session_id}"
# Custom messages with template_data (sorted set)
TEMPLATE_MESSAGES_KEY = "chat:tmpl:{session_id}"
# Rolling conversation summary (plain string, encrypted)
SUMMARY_KEY = "chat:summary:{session_id}"

# Maximum chat history retention (sliding TTL). Refreshed on every write so
# active sessions stay alive; inactive sessions auto-expire after this window.
CHAT_HISTORY_TTL_SECONDS = 7 * 24 * 60 * 60  # 1 week



def _get_session_set_key(user_id: str) -> str:
    """Get Redis key for user's session set."""
    return SESSION_SET_KEY.format(user_id=user_id)


def _get_messages_key(session_id: str) -> str:
    """Get Redis key for session messages."""
    return MESSAGES_KEY.format(session_id=session_id)


def _get_meta_key(session_id: str) -> str:
    """Get Redis key for session metadata."""
    return META_KEY.format(session_id=session_id)


def _get_template_messages_key(session_id: str) -> str:
    """Get Redis key for template messages (sorted set for messages with template_data)."""
    return TEMPLATE_MESSAGES_KEY.format(session_id=session_id)


def _get_summary_key(session_id: str) -> str:
    """Get Redis key for the rolling conversation summary."""
    return SUMMARY_KEY.format(session_id=session_id)


def _decode_template_data(value, crypto):
    """Decode stored template_data into a dict.

    Handles three storage shapes during the migration window:
    - None  -> None
    - dict  -> legacy plaintext, return as-is
    - str   -> encrypted (or legacy JSON string); decrypt then json.loads
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        plaintext = crypto.decrypt(value)
        try:
            return json.loads(plaintext)
        except (json.JSONDecodeError, TypeError):
            logger.warning("[CHAT_HISTORY] Failed to parse template_data after decrypt")
            return None
    return None


class ChatHistoryService:
    """Service for managing chat history via Redis."""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client or get_redis_client()
        self.async_redis = get_async_redis_client()

    def _refresh_session_ttl(self, session_id: str, user_id: Optional[str] = None) -> None:
        """Refresh sliding 1-week TTL on a session's Redis keys.

        Called after every write so that active sessions persist indefinitely
        while sessions idle for more than CHAT_HISTORY_TTL_SECONDS auto-expire.
        EXPIRE on a non-existent key is a safe no-op in Redis.
        """
        meta_key = _get_meta_key(session_id)
        if user_id is None:
            user_id = self.redis.hget(meta_key, "user_id")

        pipe = self.redis.pipeline()
        pipe.expire(_get_template_messages_key(session_id), CHAT_HISTORY_TTL_SECONDS)
        pipe.expire(meta_key, CHAT_HISTORY_TTL_SECONDS)
        if user_id:
            pipe.expire(_get_session_set_key(user_id), CHAT_HISTORY_TTL_SECONDS)
        pipe.execute()

    def decode_token(self, access_token: str) -> Optional[dict]:
        """Decode JWT token and return user info."""
        return get_user_info_from_token(access_token)

    def validate_token(self, access_token: str) -> tuple[bool, Optional[str]]:
        """Validate JWT token. Returns (is_valid, user_id)."""
        payload = decode_jwt(access_token)
        if payload and payload.get("user_id"):
            return True, payload.get("user_id")
        return False, None

    def get_user_info(self, access_token: str) -> Optional[dict]:
        """Extract user info from JWT token."""
        return get_user_info_from_token(access_token)

    def create_session_id(self, user_id: str) -> str:
        """Create new session ID and add to user's session set."""
        session_id = str(uuid.uuid4())

        # Add session_id to user's session set
        session_set_key = _get_session_set_key(user_id)
        self.redis.sadd(session_set_key, session_id)

        # Initialize metadata
        meta_key = _get_meta_key(session_id)
        self.redis.hset(meta_key, mapping={
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "last_message": "",
        })

        self._refresh_session_ttl(session_id, user_id=user_id)

        logger.debug(f"[CHAT_HISTORY] Created session {session_id} for user {user_id}")
        return session_id

    def get_or_create_session_id(self, session_id: str, user_id: str) -> str:
        """Get existing session_id or create new one with provided ID."""
        # Verify session exists and belongs to user
        meta_key = _get_meta_key(session_id)
        session_user_id = self.redis.hget(meta_key, "user_id")
        if session_user_id == user_id:
            return session_id

        # Session doesn't exist - create it with provided session_id
        if session_user_id is None:
            logger.debug(f"[CHAT_HISTORY] Creating session {session_id} for user {user_id}")
            # Add session_id to user's session set
            session_set_key = _get_session_set_key(user_id)
            self.redis.sadd(session_set_key, session_id)

            # Initialize metadata
            self.redis.hset(meta_key, mapping={
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "last_message": "",
            })
            self._refresh_session_ttl(session_id, user_id=user_id)
            return session_id

        # Session belongs to different user - create new
        logger.warning(f"[CHAT_HISTORY] Session {session_id} not found for user {user_id}")
        return self.create_session_id(user_id)

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        template_data: Optional[dict] = None,
        user_id: Optional[str] = None,
    ) -> str:
        """Save message to Redis as JSON in sorted set.

        Args:
            session_id: Session ID
            role: "user" or "assistant"
            content: Message content
            template_data: Optional UI template data (default None)
            user_id: Optional user ID — when provided, TTL refresh on the user
                session set is included in the same pipeline (saves 1 round-trip).
        """
        msg_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        crypto = get_crypto_service()
        encrypted_template = (
            crypto.encrypt(json.dumps(template_data, ensure_ascii=False))
            if template_data is not None
            else None
        )
        msg_json = json.dumps({
            "msg_id": msg_id,
            "role": role,
            "content": crypto.encrypt(content),
            "template_data": encrypted_template,
            "created_at": now,
        })
        score = datetime.now().timestamp()
        tmpl_key = _get_template_messages_key(session_id)
        meta_key = _get_meta_key(session_id)

        # Batch all writes + TTL refreshes into a single round-trip.
        pipe = self.redis.pipeline()
        pipe.zadd(tmpl_key, {msg_json: score})
        pipe.hset(meta_key, mapping={
            "updated_at": now,
            "last_message": crypto.encrypt(content[:100]) or "",
        })
        pipe.expire(tmpl_key, CHAT_HISTORY_TTL_SECONDS)
        pipe.expire(meta_key, CHAT_HISTORY_TTL_SECONDS)
        if user_id:
            pipe.expire(_get_session_set_key(user_id), CHAT_HISTORY_TTL_SECONDS)
        pipe.execute()

        logger.debug(
            "[CHAT_HISTORY] Saved %s message to session %s%s",
            role, session_id, " with template_data" if template_data is not None else "",
        )
        return msg_id

    def get_history(self, session_id: str) -> List[dict]:
        """Get all messages for a session from sorted set (decrypts content & template_data)."""
        messages = []
        crypto = get_crypto_service()

        # Get messages from custom template sorted set
        tmpl_key = _get_template_messages_key(session_id)
        tmpl_raw = self.redis.zrange(tmpl_key, 0, -1)
        for raw in tmpl_raw:
            try:
                data = json.loads(raw)
                messages.append({
                    "msg_id": data.get("msg_id", str(uuid.uuid4())),
                    "session_id": session_id,
                    "role": data.get("role", "assistant"),
                    "content": crypto.decrypt(data.get("content", "")) or "",
                    "status": "completed",
                    "template_data": _decode_template_data(data.get("template_data"), crypto),
                    "created_at": data.get("created_at", datetime.now().isoformat()),
                })
            except json.JSONDecodeError:
                logger.warning(f"[CHAT_HISTORY] Failed to parse message: {raw[:100]}")
                continue

        # Sort by created_at timestamp
        def get_timestamp(msg):
            try:
                return datetime.fromisoformat(msg["created_at"]).timestamp()
            except (ValueError, KeyError):
                return 0
        messages.sort(key=get_timestamp)

        return messages

    def get_history_range(self, session_id: str, start: int, end: int) -> List[dict]:
        """Get a specific range of messages from the sorted set to avoid full decryption."""
        messages = []
        crypto = get_crypto_service()

        tmpl_key = _get_template_messages_key(session_id)
        tmpl_raw = self.redis.zrange(tmpl_key, start, end)
        for raw in tmpl_raw:
            try:
                data = json.loads(raw)
                messages.append({
                    "msg_id": data.get("msg_id", str(uuid.uuid4())),
                    "session_id": session_id,
                    "role": data.get("role", "assistant"),
                    "content": crypto.decrypt(data.get("content", "")) or "",
                    "status": "completed",
                    "template_data": _decode_template_data(data.get("template_data"), crypto),
                    "created_at": data.get("created_at", datetime.now().isoformat()),
                })
            except json.JSONDecodeError:
                continue

        def get_timestamp(msg):
            try:
                return datetime.fromisoformat(msg["created_at"]).timestamp()
            except (ValueError, KeyError):
                return 0
        messages.sort(key=get_timestamp)
        return messages

    def acquire_summary_lock(self, session_id: str) -> bool:
        """Acquire a lock for summarization to prevent concurrent race conditions."""
        key = f"chat:summary_lock:{session_id}"
        return bool(self.redis.set(key, "1", nx=True, ex=30))

    def release_summary_lock(self, session_id: str) -> None:
        """Release the summarization lock."""
        key = f"chat:summary_lock:{session_id}"
        self.redis.delete(key)

    def list_sessions(self, user_id: str) -> List[dict]:
        """List all sessions for a user (decrypts last_message preview)."""
        session_set_key = _get_session_set_key(user_id)
        session_ids = list(self.redis.smembers(session_set_key))
        if not session_ids:
            return []

        crypto = get_crypto_service()
        pipe = self.redis.pipeline()
        for sid in session_ids:
            pipe.hgetall(_get_meta_key(sid))
        meta_results = pipe.execute()

        sessions = []
        orphaned = []
        for session_id, meta in zip(session_ids, meta_results):
            if meta:
                sessions.append({
                    "session_id": session_id,
                    "last_message": crypto.decrypt(meta.get("last_message", "")) or "",
                    "updated_at": meta.get("updated_at", ""),
                })
            else:
                orphaned.append(session_id)

        if orphaned:
            pipe = self.redis.pipeline()
            for sid in orphaned:
                pipe.srem(session_set_key, sid)
            pipe.execute()

        sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return sessions

    def delete_session(self, session_id: str) -> int:
        """Delete session and all its messages. Returns number of messages deleted."""
        meta_key = _get_meta_key(session_id)
        meta = self.redis.hgetall(meta_key)

        if not meta:
            logger.warning(f"[CHAT_HISTORY] Session {session_id} not found for deletion")
            return 0

        user_id = meta.get("user_id")

        # Get count from sorted set before delete
        tmpl_key = _get_template_messages_key(session_id)
        messages_deleted = self.redis.zcard(tmpl_key)

        # Delete all keys (including tool context and summary)
        messages_key = _get_messages_key(session_id)
        tool_ctx_key = f"chat:tool_ctx:{session_id}"
        summary_key = _get_summary_key(session_id)
        self.redis.delete(messages_key, meta_key, tmpl_key, tool_ctx_key, summary_key)

        # Remove from user's session set
        if user_id:
            session_set_key = _get_session_set_key(user_id)
            self.redis.srem(session_set_key, session_id)

        logger.debug(f"[CHAT_HISTORY] Deleted session {session_id}, {messages_deleted} messages")
        return messages_deleted

    def session_exists(self, session_id: str, user_id: str) -> bool:
        """Check if session exists and belongs to user."""
        meta_key = _get_meta_key(session_id)
        session_user_id = self.redis.hget(meta_key, "user_id")
        return session_user_id == user_id

    # Max accumulated tool results to keep (prevents unbounded growth)
    _MAX_TOOL_CONTEXT_ITEMS = 20

    def save_tool_context(self, session_id: str, tool_data: list[dict]) -> None:
        """Append structured tool results to accumulated context.

        New results are appended to the front (most recent first).
        Deduplicates by (tool, input) key — newer results replace older ones.
        Keeps at most _MAX_TOOL_CONTEXT_ITEMS entries.
        """
        key = f"chat:tool_ctx:{session_id}"

        # Load existing
        existing = self.get_tool_context(session_id)

        # Dedup by (tool, full_input): newer results replace older ones for the same query.
        # Uses _dedup_input (full params including PII) for accurate dedup,
        # while "input" (PII-filtered) is what gets injected into the prompt.
        def _dedup_key(item: dict) -> str:
            dedup_input = item.get("_dedup_input", item.get("input", {}))
            return json.dumps(
                {"tool": item.get("tool", ""), "input": dedup_input},
                sort_keys=True, ensure_ascii=False,
            )

        seen = set()
        merged = []
        # New items first (reversed so last tool call = most recent), then existing
        for item in list(reversed(tool_data)) + existing:
            dk = _dedup_key(item)
            if dk not in seen:
                seen.add(dk)
                merged.append(item)

        # Trim to max
        merged = merged[:self._MAX_TOOL_CONTEXT_ITEMS]

        crypto = get_crypto_service()
        plaintext_blob = json.dumps(merged, ensure_ascii=False)
        self.redis.set(key, crypto.encrypt(plaintext_blob))
        self.redis.expire(key, 7200)
        logger.debug(f"[TOOL_CTX] Saved {len(tool_data)} new + {len(existing)} existing "
                     f"= {len(merged)} total tool results for session {session_id}")

    def get_tool_context(self, session_id: str) -> list[dict]:
        """Load accumulated structured tool results (decrypts blob)."""
        key = f"chat:tool_ctx:{session_id}"
        raw = self.redis.get(key)
        if raw:
            crypto = get_crypto_service()
            plaintext = crypto.decrypt(raw)
            try:
                return json.loads(plaintext)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"[TOOL_CTX] Failed to parse tool context for session {session_id}")
        return []

    async def get_tool_context_async(self, session_id: str) -> list[dict]:
        """Load accumulated structured tool results without blocking async callers."""
        key = f"chat:tool_ctx:{session_id}"
        raw = await self.async_redis.get(key)
        if raw:
            crypto = get_crypto_service()
            plaintext = crypto.decrypt(raw)
            try:
                return json.loads(plaintext)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"[TOOL_CTX] Failed to parse tool context for session {session_id}")
        return []

    def get_message_count(self, session_id: str) -> int:
        """Return the total number of messages stored for this session."""
        return self.redis.zcard(_get_template_messages_key(session_id))

    def save_summary(self, session_id: str, content: str, covered_count: int) -> None:
        """Persist a rolling summary that covers the first *covered_count* messages."""
        crypto = get_crypto_service()
        payload = json.dumps(
            {"content": content, "covered_count": covered_count},
            ensure_ascii=False,
        )
        key = _get_summary_key(session_id)
        self.redis.set(key, crypto.encrypt(payload))
        self.redis.expire(key, CHAT_HISTORY_TTL_SECONDS)
        logger.debug(
            f"[SUMMARY] Saved summary for session {session_id} "
            f"(covered_count={covered_count})"
        )

    def get_summary(self, session_id: str) -> dict | None:
        """Load the rolling summary. Returns {content, covered_count} or None."""
        raw = self.redis.get(_get_summary_key(session_id))
        if not raw:
            return None
        crypto = get_crypto_service()
        plaintext = crypto.decrypt(raw)
        try:
            return json.loads(plaintext)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[SUMMARY] Failed to parse summary for session {session_id}")
            return None

    def get_history_for_llm(self, session_id: str) -> list[dict]:
        """Return [summary_msg] + last N messages when summary exists, else last 20 messages."""
        summary = self.get_summary(session_id)
        if summary is None:
            return self.get_history_range(session_id, -20, -1)

        crypto = get_crypto_service()
        tmpl_key = _get_template_messages_key(session_id)
        raw_items = self.redis.zrange(tmpl_key, summary["covered_count"], -1)
        recent = []
        for raw in raw_items:
            try:
                data = json.loads(raw)
                recent.append({
                    "msg_id": data.get("msg_id", str(uuid.uuid4())),
                    "session_id": session_id,
                    "role": data.get("role", "assistant"),
                    "content": crypto.decrypt(data.get("content", "")) or "",
                    "status": "completed",
                    "template_data": _decode_template_data(data.get("template_data"), crypto),
                    "created_at": data.get("created_at", datetime.now().isoformat()),
                })
            except json.JSONDecodeError:
                logger.warning(f"[SUMMARY] Failed to parse recent message: {raw[:100]}")
                continue

        summary_msg = {
            "msg_id": "summary",
            "session_id": session_id,
            "role": "assistant",
            "content": f"[이전 대화 요약]\n{summary['content']}",
            "status": "completed",
            "template_data": None,
            "created_at": recent[0]["created_at"] if recent else datetime.now().isoformat(),
        }
        return [summary_msg] + recent


    def get_recent_assistant_messages_with_template_data(
        self,
        session_id: str,
        limit: int,
    ) -> list[dict]:
        """Return the newest `limit` assistant messages that have template_data.

        Scans from the tail of the sorted set in small batches so sessions
        with many non-template messages do not force a full scan.
        """
        if limit <= 0:
            return []

        crypto = get_crypto_service()
        tmpl_key = _get_template_messages_key(session_id)
        result = []
        start = 0
        batch_size = max(limit * 4, 10)

        while len(result) < limit:
            raw_items = self.redis.zrevrange(tmpl_key, start, start + batch_size - 1)
            if not raw_items:
                break
            for raw in raw_items:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if data.get("role") != "assistant":
                    continue
                if not data.get("template_data"):
                    continue
                result.append({
                    "msg_id": data.get("msg_id", str(uuid.uuid4())),
                    "session_id": session_id,
                    "role": "assistant",
                    "content": crypto.decrypt(data.get("content", "")) or "",
                    "status": "completed",
                    "template_data": _decode_template_data(data.get("template_data"), crypto),
                    "created_at": data.get("created_at", datetime.now().isoformat()),
                })
                if len(result) >= limit:
                    break
            start += batch_size

        return result

    def get_latest_template_data(self, session_id: str, template_name: str) -> dict | None:
        """Return the data payload of the newest assistant message with the given template name."""
        if not template_name:
            return None
        for message in self.get_recent_assistant_messages_with_template_data(session_id, limit=10):
            td = message.get("template_data")
            if not isinstance(td, dict):
                continue
            if td.get("template") != template_name:
                continue
            data = td.get("data")
            if isinstance(data, dict):
                return data
        return None
    def save_slots(self, session_id: str, slots: ConversationSlots) -> None:
        """Save conversation slots to session metadata (encrypted)."""
        meta_key = _get_meta_key(session_id)
        crypto = get_crypto_service()
        encrypted = crypto.encrypt(slots.model_dump_json()) or ""
        self.redis.hset(meta_key, "slots", encrypted)
        self._refresh_session_ttl(session_id)
        logger.debug(f"[CHAT_HISTORY] Saved slots for session {session_id}: {slots.model_dump()}")

    async def save_slots_async(
        self, session_id: str, slots: ConversationSlots, user_id: Optional[str] = None
    ) -> None:
        """Save conversation slots without blocking the async chat request path."""
        meta_key = _get_meta_key(session_id)
        crypto = get_crypto_service()
        encrypted = crypto.encrypt(slots.model_dump_json()) or ""

        pipe = self.async_redis.pipeline()
        pipe.hset(meta_key, "slots", encrypted)
        pipe.expire(_get_template_messages_key(session_id), CHAT_HISTORY_TTL_SECONDS)
        pipe.expire(meta_key, CHAT_HISTORY_TTL_SECONDS)
        if user_id:
            pipe.expire(_get_session_set_key(user_id), CHAT_HISTORY_TTL_SECONDS)
        await pipe.execute()
        logger.debug(f"[CHAT_HISTORY] Saved slots for session {session_id}: {slots.model_dump()}")

    async def finalize_chat_context_async(
        self,
        session_id: str,
        tool_data: list[dict] | None = None,
        quick_reply_domains: list[str] | None = None,
        predicted_domains: list[str] | None = None,
        user_id: Optional[str] = None,
    ) -> None:
        """Persist end-of-stream context with async Redis and batched writes."""
        tool_data = tool_data or []
        quick_reply_domains = quick_reply_domains or []
        predicted_domains = predicted_domains or []
        if not (tool_data or quick_reply_domains or predicted_domains):
            return

        crypto = get_crypto_service()
        meta_key = _get_meta_key(session_id)
        pipe = self.async_redis.pipeline()

        if tool_data:
            existing = await self.get_tool_context_async(session_id)

            def _dedup_key(item: dict) -> str:
                dedup_input = item.get("_dedup_input", item.get("input", {}))
                return json.dumps(
                    {"tool": item.get("tool", ""), "input": dedup_input},
                    sort_keys=True, ensure_ascii=False,
                )

            seen = set()
            merged = []
            for item in list(reversed(tool_data)) + existing:
                dk = _dedup_key(item)
                if dk not in seen:
                    seen.add(dk)
                    merged.append(item)
            merged = merged[:self._MAX_TOOL_CONTEXT_ITEMS]
            tool_ctx_key = f"chat:tool_ctx:{session_id}"
            pipe.set(tool_ctx_key, crypto.encrypt(json.dumps(merged, ensure_ascii=False)))
            pipe.expire(tool_ctx_key, 7200)
            logger.debug(f"[TOOL_CTX] Saved {len(tool_data)} new + {len(existing)} existing "
                        f"= {len(merged)} total tool results for session {session_id}")

        if quick_reply_domains:
            pipe.hset(meta_key, "quick_reply_domains", crypto.encrypt(json.dumps(quick_reply_domains)) or "")
        if predicted_domains:
            pipe.hset(meta_key, "predicted_domains", crypto.encrypt(json.dumps(predicted_domains)) or "")

        pipe.expire(_get_template_messages_key(session_id), CHAT_HISTORY_TTL_SECONDS)
        pipe.expire(meta_key, CHAT_HISTORY_TTL_SECONDS)
        if user_id:
            pipe.expire(_get_session_set_key(user_id), CHAT_HISTORY_TTL_SECONDS)
        await pipe.execute()

        if quick_reply_domains:
            logger.debug(f"[CHAT_HISTORY] Saved quick_reply_domains for session {session_id}: {quick_reply_domains}")
        if predicted_domains:
            logger.debug(f"[CHAT_HISTORY] Saved predicted_domains for session {session_id}: {predicted_domains}")

    def save_quick_reply_domains(self, session_id: str, domains: list[str]) -> None:
        """Save next-turn chip routing hints."""
        crypto = get_crypto_service()
        self.redis.hset(_get_meta_key(session_id), "quick_reply_domains", crypto.encrypt(json.dumps(domains)) or "")
        self._refresh_session_ttl(session_id)
        logger.debug(f"[CHAT_HISTORY] Saved quick_reply_domains for session {session_id}: {domains}")

    def get_quick_reply_domains(self, session_id: str) -> list[str]:
        """Load next-turn chip routing hints."""
        raw = self.redis.hget(_get_meta_key(session_id), "quick_reply_domains")
        data = json.loads(get_crypto_service().decrypt(raw)) if raw else []
        return [item for item in data if isinstance(item, str)] if isinstance(data, list) else []

    def save_predicted_domains(self, session_id: str, domains: list[str]) -> None:
        """Save model-predicted next-turn hints."""
        crypto = get_crypto_service()
        self.redis.hset(_get_meta_key(session_id), "predicted_domains", crypto.encrypt(json.dumps(domains)) or "")
        self._refresh_session_ttl(session_id)
        logger.debug(f"[CHAT_HISTORY] Saved predicted_domains for session {session_id}: {domains}")

    def get_predicted_domains(self, session_id: str) -> list[str]:
        """Load model-predicted next-turn hints."""
        raw = self.redis.hget(_get_meta_key(session_id), "predicted_domains")
        data = json.loads(get_crypto_service().decrypt(raw)) if raw else []
        return [item for item in data if isinstance(item, str)] if isinstance(data, list) else []

    def get_slots(self, session_id: str) -> ConversationSlots:
        """Load conversation slots from session metadata (decrypts)."""
        meta_key = _get_meta_key(session_id)
        raw = self.redis.hget(meta_key, "slots")
        if raw:
            crypto = get_crypto_service()
            plaintext = crypto.decrypt(raw)
            try:
                return ConversationSlots.model_validate_json(plaintext)
            except (ValueError, TypeError) as exc:
                logger.warning(f"[CHAT_HISTORY] Failed to parse slots for session {session_id}: {exc}")
        return ConversationSlots()

    async def get_chat_context_pipeline_async(
        self, session_id: str, limit: int
    ) -> tuple[list[dict], ConversationSlots, list[dict], dict | None, dict | None, list[str], list[str]]:
        """Fetch hot-path chat context in one Redis pipeline."""
        tmpl_key = _get_template_messages_key(session_id)
        meta_key = _get_meta_key(session_id)
        tool_ctx_key = f"chat:tool_ctx:{session_id}"

        pipe = self.async_redis.pipeline()
        batch_size = max(limit * 4, 40)
        pipe.zrevrange(tmpl_key, 0, batch_size - 1)
        pipe.hget(meta_key, "slots")
        pipe.get(tool_ctx_key)
        pipe.hget(meta_key, "quick_reply_domains")
        pipe.hget(meta_key, "predicted_domains")

        raw_items, raw_slots, raw_tool_ctx, raw_quick_reply_domains, raw_predicted_domains = await pipe.execute()

        crypto = get_crypto_service()
        recent_template_msgs = []
        latest_listcar_tmpl = None
        latest_location_tmpl = None

        # Parse template messages
        for raw in raw_items:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data.get("role") != "assistant":
                continue
            td_raw = data.get("template_data")
            if not td_raw:
                continue

            td_decoded = _decode_template_data(td_raw, crypto)

            if td_decoded:
                inner = td_decoded.get("data")
                if isinstance(inner, dict):
                    tmpl_name = td_decoded.get("template")
                    if latest_listcar_tmpl is None and tmpl_name == "listCar":
                        latest_listcar_tmpl = inner
                    if latest_location_tmpl is None and tmpl_name == "location":
                        latest_location_tmpl = inner

            if len(recent_template_msgs) < limit:
                recent_template_msgs.append({
                    "msg_id": data.get("msg_id", str(uuid.uuid4())),
                    "session_id": session_id,
                    "role": "assistant",
                    "content": crypto.decrypt(data.get("content", "")) or "",
                    "status": "completed",
                    "template_data": td_decoded,
                    "created_at": data.get("created_at", datetime.now().isoformat()),
                })

        # Parse slots
        slots = ConversationSlots()
        if raw_slots:
            try:
                slots = ConversationSlots.model_validate_json(crypto.decrypt(raw_slots))
            except (ValueError, TypeError):
                pass

        # Parse tool context
        tool_ctx = []
        if raw_tool_ctx:
            try:
                tool_ctx = json.loads(crypto.decrypt(raw_tool_ctx))
            except (json.JSONDecodeError, TypeError):
                pass

        quick_reply_domains = []
        if raw_quick_reply_domains:
            try:
                parsed = json.loads(crypto.decrypt(raw_quick_reply_domains))
                if isinstance(parsed, list):
                    quick_reply_domains = [item for item in parsed if isinstance(item, str)]
            except (json.JSONDecodeError, TypeError):
                pass

        predicted_domains = []
        if raw_predicted_domains:
            try:
                parsed = json.loads(crypto.decrypt(raw_predicted_domains))
                if isinstance(parsed, list):
                    predicted_domains = [item for item in parsed if isinstance(item, str)]
            except (json.JSONDecodeError, TypeError):
                pass

        return recent_template_msgs, slots, tool_ctx, latest_listcar_tmpl, latest_location_tmpl, quick_reply_domains, predicted_domains


# Singleton instance
_chat_history_service: Optional[ChatHistoryService] = None


def get_chat_history_service() -> ChatHistoryService:
    """Get singleton ChatHistoryService instance."""
    global _chat_history_service
    if _chat_history_service is None:
        _chat_history_service = ChatHistoryService()
    return _chat_history_service
