"""Load/merge/save conversation slots — reuses V2's Redis storage.

`ConversationSlots.merge` owns dependency resets; this module only
validates the LLM patch and talks to `ChatHistoryService`.
"""

import asyncio
import json
import logging
from typing import Any

from pydantic import ValidationError

from schemas.tstation.slots import ConversationSlots
from services.tstation.chat_history_service import get_chat_history_service
from services.tstation.chat_v3.slots.schemas import SlotsPatch
from services.tstation.policies.discovery_intent_policy import normalize_tire_size
from services.tstation.policies.product_name_normalization import normalize_product_slot_values

logger = logging.getLogger(__name__)


def _compact_identity(value: Any) -> str:
    return str(value or "").casefold().replace(" ", "")


def _same_product_identity(existing: ConversationSlots, values: dict) -> bool:
    old_name = _compact_identity(existing.pending_product_name or existing.tire_model)
    new_name = _compact_identity(values.get("pending_product_name") or values.get("tire_model"))
    if not old_name or not new_name or old_name not in new_name:
        return False
    new_size = str(values.get("tire_size") or existing.tire_size or "").strip()
    return not existing.tire_size or new_size == existing.tire_size


def _restore_confirmed_product(existing: ConversationSlots, merged: ConversationSlots, values: dict) -> ConversationSlots:
    if not existing.goods_no or merged.goods_no or values.get("goods_no"):
        return merged
    if not any(key in values for key in ("pending_product_name", "tire_model", "tire_size")):
        return merged
    if not _same_product_identity(existing, values):
        return merged
    restored = merged.model_copy()
    restored.goods_no = existing.goods_no
    return restored


async def load_slots(session_id: str) -> ConversationSlots:
    service = get_chat_history_service()
    try:
        return await asyncio.to_thread(service.get_slots, session_id)
    except Exception:
        logger.exception("[CHAT_V3] failed to load slots for %s", session_id)
        return ConversationSlots()


def _normalize_patch_tire_size(values: dict) -> dict:
    """tire_size only ever stores a normalized size (e.g. '255/35R19') — never
    free text such as a combined product-name + size string from the router LLM."""
    raw = values.get("tire_size")
    if raw in (None, ""):
        return values
    normalized = normalize_tire_size(str(raw))
    if normalized:
        return {**values, "tire_size": normalized}
    logger.info("[CHAT_V3] dropped unnormalizable tire_size from router patch: %r", raw)
    return {k: v for k, v in values.items() if k != "tire_size"}


def apply_patch(existing: ConversationSlots, patch: SlotsPatch | None) -> ConversationSlots:
    if patch is None:
        return existing
    values = _normalize_patch_tire_size(normalize_product_slot_values(patch.non_empty()))
    while values:
        try:
            merged = existing.merge(ConversationSlots.model_validate(values))
            return _restore_confirmed_product(existing, merged, values)
        except ValidationError as exc:
            # Drop fields the LLM filled with out-of-vocabulary values and retry.
            bad_fields = {str(err["loc"][0]) for err in exc.errors() if err.get("loc")}
            if not bad_fields:
                break
            logger.info("[CHAT_V3] dropped invalid slot fields: %s", sorted(bad_fields))
            values = {k: v for k, v in values.items() if k not in bad_fields}
    return existing


async def save_slots(session_id: str, slots: ConversationSlots, user_id: str | None = None) -> None:
    service = get_chat_history_service()
    try:
        await service.save_slots_async(session_id, slots, user_id=user_id)
    except Exception:
        logger.exception("[CHAT_V3] failed to save slots for %s", session_id)


def slots_context_block(slots: ConversationSlots) -> str | None:
    """Known conversation state, injected into the system prompt."""
    values = {k: v for k, v in slots.model_dump(mode="json").items() if v is not None}
    if not values:
        return None
    if (
        slots.tire_size
        and slots.tire_size_front
        and slots.tire_size_rear
        and slots.tire_size_front != slots.tire_size_rear
        and slots.tire_size in {slots.tire_size_front, slots.tire_size_rear}
    ):
        values["staggered_tire_purchase_guidance"] = (
            "전/후륜 규격이 다른 차량은 도구로 확인되지 않은 상태에서 두 규격을 한 번에 구매 가능하다고 "
            "단정하지 말고, 현재 채팅 흐름은 선택한 규격 하나씩 상품 추천/구매를 진행한다고 안내하세요."
        )
    return "## CONVERSATION SLOTS (known context from earlier turns)\n" + json.dumps(
        values, ensure_ascii=False, separators=(",", ":")
    )
