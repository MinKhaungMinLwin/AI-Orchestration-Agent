from __future__ import annotations

import json
import logging
from typing import Any

from services.tstation.llm_first.adapters import legacy
from services.tstation.llm_first.models import ConversationState

logger = logging.getLogger(__name__)

_STATE_KEY = "chat:llm_first_state:{session_id}"


def _state_key(session_id: str) -> str:
    return _STATE_KEY.format(session_id=session_id)


class LLMFirstStateStore:
    def __init__(self, redis_client: Any | None = None):
        self.redis = redis_client or legacy.redis_client()

    def load(self, session_id: str) -> ConversationState:
        raw = self.redis.get(_state_key(session_id))
        if not raw:
            return ConversationState()
        try:
            return ConversationState.model_validate(json.loads(raw))
        except Exception:
            logger.warning("[LLM_FIRST_STATE] Invalid state for session=%s; resetting", session_id, exc_info=True)
            return ConversationState()

    def save(self, session_id: str, state: ConversationState) -> None:
        self.redis.setex(
            _state_key(session_id),
            legacy.chat_history_ttl_seconds(),
            state.model_dump_json(exclude_none=True),
        )


def apply_state_rules(
    state: ConversationState,
    *,
    product_patch: dict[str, Any] | None = None,
    quantity: int | None = None,
    store_patch: dict[str, Any] | None = None,
    schedule_patch: dict[str, Any] | None = None,
    price_patch: dict[str, Any] | None = None,
) -> ConversationState:
    """Apply FIX_LOG dependency invalidation rules to commerce state."""
    updated = state.model_copy(deep=True)
    commerce = updated.commerce_state

    if product_patch:
        before = commerce.product.model_dump()
        tire_size_before = commerce.product.tire_size
        for key, value in product_patch.items():
            if value not in (None, "") and hasattr(commerce.product, key):
                setattr(commerce.product, key, value)
        tire_size_changed = (
            "tire_size" in product_patch
            and product_patch.get("tire_size") not in (None, "")
            and commerce.product.tire_size != tire_size_before
        )
        if tire_size_changed and not (product_patch.get("goods_no") or product_patch.get("product_name")):
            commerce.product.goods_no = None
            commerce.product.product_name = None
        if commerce.product.model_dump() != before:
            commerce.quantity = None
            commerce.store = commerce.store.__class__()
            commerce.schedule = commerce.schedule.__class__()
            commerce.price = commerce.price.__class__()

    if quantity is not None and quantity > 0 and quantity != commerce.quantity:
        commerce.quantity = quantity
        commerce.store = commerce.store.__class__()
        commerce.schedule = commerce.schedule.__class__()
        commerce.price = commerce.price.__class__()

    if store_patch:
        before = commerce.store.model_dump()
        for key, value in store_patch.items():
            if value not in (None, "") and hasattr(commerce.store, key):
                setattr(commerce.store, key, value)
        if commerce.store.model_dump() != before:
            commerce.schedule = commerce.schedule.__class__()
            commerce.price = commerce.price.__class__()

    if schedule_patch:
        before = commerce.schedule.model_dump()
        for key, value in schedule_patch.items():
            if value not in (None, "") and hasattr(commerce.schedule, key):
                setattr(commerce.schedule, key, value)
        if commerce.schedule.model_dump() != before:
            commerce.price = commerce.price.__class__()

    if price_patch:
        for key, value in price_patch.items():
            if value not in (None, "") and hasattr(commerce.price, key):
                setattr(commerce.price, key, value)

    return updated
