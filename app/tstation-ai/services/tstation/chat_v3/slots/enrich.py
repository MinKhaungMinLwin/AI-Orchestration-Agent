"""Slot enrichment — backfill the product display label when only goods_no is known."""

import asyncio
import logging

from schemas.tstation.slots import ConversationSlots
from services.tstation.agents.b_discovery_agent.tools import get_product_description_tool
from services.tstation.policies.discovery_intent_policy import normalize_tire_size

logger = logging.getLogger(__name__)


async def backfill_product_label(slots: ConversationSlots) -> ConversationSlots:
    goods_no = str(slots.goods_no or "").strip()
    if goods_no and str(slots.car_no or "").strip() == goods_no:
        slots = slots.model_copy(update={"car_no": None})
    if not goods_no or slots.tire_model or slots.pending_product_name:
        return slots
    try:
        result = await asyncio.to_thread(get_product_description_tool.invoke, {"goods_no": goods_no})
    except Exception:
        logger.exception("[CHAT_V3] product label backfill failed for goods_no=%s", goods_no)
        return slots
    detail = result.get("data") if isinstance(result, dict) and isinstance(result.get("data"), dict) else {}
    goods_nm = str(detail.get("goods_nm") or "").strip()
    if not goods_nm or str(detail.get("goods_no") or "").strip() != goods_no:
        logger.warning(
            "[CHAT_V3] product label backfill got no goods_nm for goods_no=%s (result=%s)",
            goods_no,
            {k: result.get(k) for k in ("status", "http_status", "reason", "message")}
            if isinstance(result, dict)
            else type(result).__name__,
        )
        return slots
    updates: dict = {"tire_model": goods_nm, "pending_product_name": goods_nm}
    tire_size = normalize_tire_size(str(detail.get("tire_size_1") or ""))
    if tire_size and not slots.tire_size:
        updates["tire_size"] = tire_size
    logger.info("[CHAT_V3] product label backfilled for goods_no=%s: %s", goods_no, goods_nm)
    return slots.model_copy(update=updates)
