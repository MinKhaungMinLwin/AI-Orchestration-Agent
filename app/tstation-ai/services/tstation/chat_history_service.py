"""
Chat History Service - Redis-based conversation management.

Stores messages as JSON in sorted sets (chat:tmpl:{session_id}).
Session management per user_id from JWT token.
Slot persistence per session for conversation context tracking.
"""
import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from schemas.tstation.slots import ConversationSlots

import redis

from common.jwt_utils import decode_jwt, get_user_info_from_token
from config.env import settings

logger = logging.getLogger(__name__)

# Redis client for conversation management
_redis_client: Optional[redis.Redis] = None


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


# Key prefixes
SESSION_SET_KEY = "chat:user:{user_id}:sessions"
MESSAGES_KEY = "chat:messages:{session_id}"
META_KEY = "chat:meta:{session_id}"
# Custom messages with template_data (sorted set)
TEMPLATE_MESSAGES_KEY = "chat:tmpl:{session_id}"


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


class ChatHistoryService:
    """Service for managing chat history via Redis."""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client or get_redis_client()

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

        logger.info(f"[CHAT_HISTORY] Created session {session_id} for user {user_id}")
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
            logger.info(f"[CHAT_HISTORY] Creating session {session_id} for user {user_id}")
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
            return session_id

        # Session belongs to different user - create new
        logger.warning(f"[CHAT_HISTORY] Session {session_id} not found for user {user_id}")
        return self.create_session_id(user_id)

    def save_message(self, session_id: str, role: str, content: str, template_data: Optional[dict] = None) -> str:
        """Save message to Redis as JSON in sorted set.

        Args:
            session_id: Session ID
            role: "user" or "assistant"
            content: Message content
            template_data: Optional UI template data (default None)
        """
        msg_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        msg_json = json.dumps({
            "msg_id": msg_id,
            "role": role,
            "content": content,
            "template_data": template_data,
            "created_at": now,
        })
        # Score = timestamp for ordering
        score = datetime.now().timestamp()
        self.redis.zadd(_get_template_messages_key(session_id), {msg_json: score})

        # Update metadata
        meta_key = _get_meta_key(session_id)
        self.redis.hset(meta_key, mapping={
            "updated_at": now,
            "last_message": content[:100],
        })

        logger.info(f"[CHAT_HISTORY] Saved {role} message to session {session_id}" +
                  (f" with template_data" if template_data is not None else ""))
        return msg_id

    def get_history(self, session_id: str) -> List[dict]:
        """Get all messages for a session from sorted set."""
        messages = []

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
                    "content": data.get("content", ""),
                    "status": "completed",
                    "template_data": data.get("template_data"),
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

    def list_sessions(self, user_id: str) -> List[dict]:
        """List all sessions for a user."""
        session_set_key = _get_session_set_key(user_id)
        session_ids = self.redis.smembers(session_set_key)

        sessions = []
        for session_id in session_ids:
            meta_key = _get_meta_key(session_id)
            meta = self.redis.hgetall(meta_key)

            if meta:
                sessions.append({
                    "session_id": session_id,
                    "last_message": meta.get("last_message", ""),
                    "updated_at": meta.get("updated_at", ""),
                })
            else:
                # Orphaned session, remove from set
                self.redis.srem(session_set_key, session_id)

        # Sort by updated_at descending
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

        # Delete all keys
        messages_key = _get_messages_key(session_id)
        self.redis.delete(messages_key, meta_key, tmpl_key)

        # Remove from user's session set
        if user_id:
            session_set_key = _get_session_set_key(user_id)
            self.redis.srem(session_set_key, session_id)

        logger.info(f"[CHAT_HISTORY] Deleted session {session_id}, {messages_deleted} messages")
        return messages_deleted

    def session_exists(self, session_id: str, user_id: str) -> bool:
        """Check if session exists and belongs to user."""
        meta_key = _get_meta_key(session_id)
        session_user_id = self.redis.hget(meta_key, "user_id")
        return session_user_id == user_id

    def save_slots(self, session_id: str, slots: ConversationSlots) -> None:
        """Save conversation slots to session metadata."""
        meta_key = _get_meta_key(session_id)
        self.redis.hset(meta_key, "slots", slots.model_dump_json())
        logger.info(f"[CHAT_HISTORY] Saved slots for session {session_id}: {slots.model_dump()}")

    def get_slots(self, session_id: str) -> ConversationSlots:
        """Load conversation slots from session metadata."""
        meta_key = _get_meta_key(session_id)
        raw = self.redis.hget(meta_key, "slots")
        if raw:
            return ConversationSlots.model_validate_json(raw)
        return ConversationSlots()


# Singleton instance
_chat_history_service: Optional[ChatHistoryService] = None


def get_chat_history_service() -> ChatHistoryService:
    """Get singleton ChatHistoryService instance."""
    global _chat_history_service
    if _chat_history_service is None:
        _chat_history_service = ChatHistoryService()
    return _chat_history_service
