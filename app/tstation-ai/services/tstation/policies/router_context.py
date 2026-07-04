"""Compact context builder for the router LLM.

The router needs current-turn intent evidence, not full tool/template payloads.
This module keeps the router input bounded while leaving domain-agent prompts
unchanged.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from services.tstation.policies.conversation_context_policy import (
    RECENT_INTERACTION_CONTEXT_MARKER,
    parse_recent_interaction_router_message,
)


_CURRENT_TIME_RE = re.compile(r"\n+\[current_time:[^\]]+\]\s*$")
_PREVIOUS_SELECTION_MARKER = "[이전 선택된 상품 데이터]"
_BASE64ISH_RE = re.compile(r"\b[A-Za-z0-9+/]{120,}={0,2}\b")


@dataclass(frozen=True)
class RouterCompactResult:
    messages: list[dict[str, Any]]
    metadata: dict[str, Any]


def compact_router_messages(
    messages: list[dict[str, Any]],
    *,
    max_recent_messages: int = 4,
    max_candidates: int = 5,
) -> RouterCompactResult:
    """Return bounded router input plus observability metadata."""

    original = [dict(message) for message in messages]
    current_user = _current_user_message(original)
    slot_fill_context = _router_slot_fill_context(original)
    recent_interaction_summary = _recent_interaction_summary(original)
    recent_messages = _recent_dialogue_summaries(
        original,
        current_user_content=str(current_user.get("content") or ""),
        limit=max_recent_messages,
        max_candidates=max_candidates,
    )
    compact_context = {
        "current_user_text": _clean_user_text(str(current_user.get("content") or "")),
        "active_flow": _compact_active_flow(slot_fill_context),
        "confirmed_slots": _compact_confirmed_slots(slot_fill_context),
        "missing_slots": _compact_missing_slots(slot_fill_context),
        "recent_candidates": _compact_recent_candidates(slot_fill_context, max_candidates=max_candidates),
        "recent_interaction_summary": recent_interaction_summary,
        "recent_dialogue": recent_messages,
    }
    compact_context = _drop_empty(compact_context)

    compacted: list[dict[str, Any]] = []
    if slot_fill_context:
        compacted.append({
            "role": "system",
            "content": "ROUTER SLOT-FILL CONTEXT:\n"
            + json.dumps(_compact_slot_fill_context(slot_fill_context, max_candidates), ensure_ascii=False),
        })
    if compact_context:
        compacted.append({
            "role": "assistant",
            "content": "ROUTER COMPACT CONTEXT:\n"
            + json.dumps(compact_context, ensure_ascii=False, separators=(",", ":")),
        })
    if current_user:
        compacted.append({
            "role": "user",
            "content": _clean_user_text(str(current_user.get("content") or "")),
        })

    if not compacted:
        compacted = original[-1:]

    before_chars = _messages_chars(original)
    after_chars = _messages_chars(compacted)
    return RouterCompactResult(
        messages=compacted,
        metadata={
            "router_compacted": True,
            "router_input_chars_before": before_chars,
            "router_input_chars_after": after_chars,
            "router_message_count_before": len(original),
            "router_message_count_after": len(compacted),
        },
    )


def _messages_chars(messages: list[dict[str, Any]]) -> int:
    return sum(len(str(message.get("content") or "")) for message in messages)


def _current_user_message(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for message in reversed(messages):
        if message.get("role") == "user" and not _is_user_context_message(message):
            return dict(message)
    return dict(messages[-1]) if messages else {}


def _is_user_context_message(message: Mapping[str, Any]) -> bool:
    return str(message.get("content") or "").startswith("## USER CONTEXT INFORMATION")


def _clean_user_text(text: str) -> str:
    text = text.replace("# Respond in Korean language", "").strip()
    text = _CURRENT_TIME_RE.sub("", text).strip()
    return _sanitize_long_payload(text, limit=1200)


def _sanitize_long_payload(text: str, *, limit: int = 600) -> str:
    if _PREVIOUS_SELECTION_MARKER in text:
        text = text.split(_PREVIOUS_SELECTION_MARKER, 1)[0].strip()
    text = _BASE64ISH_RE.sub("[omitted-base64]", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        return text[: limit - 20].rstrip() + " ... [truncated]"
    return text


def _router_slot_fill_context(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for message in reversed(messages):
        content = str(message.get("content") or "")
        marker = "ROUTER SLOT-FILL CONTEXT:"
        if marker not in content:
            continue
        raw = content.split(marker, 1)[1].strip()
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _recent_interaction_summary(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for message in reversed(messages):
        content = str(message.get("content") or "")
        if RECENT_INTERACTION_CONTEXT_MARKER not in content:
            continue
        return parse_recent_interaction_router_message(content)
    return {}


def _compact_slot_fill_context(context: Mapping[str, Any], max_candidates: int) -> dict[str, Any]:
    keys = (
        "current_flow",
        "known_slots",
        "missing_slots",
        "last_requested_slot",
        "last_candidates",
        "active_flow_context",
    )
    compact = {key: context.get(key) for key in keys if context.get(key) not in (None, "", [], {})}
    if isinstance(compact.get("last_candidates"), list):
        compact["last_candidates"] = compact["last_candidates"][:max_candidates]
    return _drop_empty(compact)


def _compact_active_flow(context: Mapping[str, Any]) -> dict[str, Any]:
    active = context.get("active_flow_context")
    if isinstance(active, Mapping):
        allowed = (
            "flow_type",
            "flow_step",
            "current_step",
            "status",
            "target_action",
            "next_tool",
            "missing_slots",
        )
        return _drop_empty({key: active.get(key) for key in allowed})
    return {}


def _compact_confirmed_slots(context: Mapping[str, Any]) -> dict[str, Any]:
    slots = context.get("known_slots")
    if not isinstance(slots, Mapping):
        return {}
    allowed = (
        "goods_no",
        "product_name",
        "tire_size",
        "ord_qty",
        "quantity",
        "shop_id",
        "shop_name",
        "store_name",
        "region",
        "car_model",
        "car_no",
        "vehicle_type",
        "pending_intent",
        "goal_type",
    )
    return _drop_empty({key: slots.get(key) for key in allowed})


def _compact_missing_slots(context: Mapping[str, Any]) -> list[str]:
    value = context.get("missing_slots")
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    return []


def _compact_recent_candidates(context: Mapping[str, Any], *, max_candidates: int) -> list[dict[str, Any]]:
    candidates = context.get("last_candidates")
    if not isinstance(candidates, list):
        return []
    compacted: list[dict[str, Any]] = []
    for item in candidates[:max_candidates]:
        if not isinstance(item, Mapping):
            continue
        compacted.append(_drop_empty({
            "label": item.get("label") or item.get("name") or item.get("title"),
            "type": item.get("type"),
            "index": item.get("index"),
            "action_type": item.get("action_type") or item.get("actionType"),
        }))
    return compacted


def _recent_dialogue_summaries(
    messages: list[dict[str, Any]],
    *,
    current_user_content: str,
    limit: int,
    max_candidates: int,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for message in reversed(messages):
        if len(summaries) >= limit:
            break
        role = str(message.get("role") or "")
        if role not in {"user", "assistant"} or _is_user_context_message(message):
            continue
        content = str(message.get("content") or "")
        if RECENT_INTERACTION_CONTEXT_MARKER in content:
            continue
        if role == "user" and content == current_user_content:
            continue
        summary: dict[str, Any] = {"role": role}
        template_summary = _template_summary(message.get("template_data"), max_candidates=max_candidates)
        if template_summary:
            summary["template"] = template_summary
        if content:
            summary["text"] = _sanitize_long_payload(content, limit=260)
        summary = _drop_empty(summary)
        if len(summary) > 1:
            summaries.append(summary)
    return list(reversed(summaries))


def _template_summary(template_data: Any, *, max_candidates: int) -> dict[str, Any]:
    if not isinstance(template_data, Mapping):
        return {}
    data = template_data.get("data") if isinstance(template_data.get("data"), Mapping) else template_data
    if not isinstance(data, Mapping):
        return {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}
    summary = {
        "template": template_data.get("template") or data.get("template"),
        "source_domain": template_data.get("source_domain"),
        "assistant_response_source": template_data.get("assistant_response_source"),
        "response_shape_key": metadata.get("response_shape_key") if isinstance(metadata, Mapping) else None,
        "candidates": _template_candidates(data, max_candidates=max_candidates),
    }
    return _drop_empty(summary)


def _template_candidates(data: Mapping[str, Any], *, max_candidates: int) -> list[dict[str, Any]]:
    for key in ("products", "stores", "listCar", "vouchers", "quickReplies"):
        value = data.get(key)
        if not isinstance(value, list):
            continue
        candidates: list[dict[str, Any]] = []
        for item in value[:max_candidates]:
            if not isinstance(item, Mapping):
                continue
            candidates.append(_drop_empty({
                "label": (
                    item.get("label")
                    or item.get("name")
                    or item.get("title")
                    or item.get("productName")
                    or item.get("shopName")
                    or item.get("couponName")
                    or item.get("carName")
                ),
                "type": key,
            }))
        return candidates
    return []


def _drop_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _drop_empty(item)) not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _drop_empty(item)) not in (None, "", [], {})]
    if isinstance(value, bytes):
        try:
            return base64.b64encode(value[:32]).decode("ascii")
        except Exception:
            return ""
    return value
