"""Reference-only recent interaction context for router classification.

This module summarizes the previous assistant/template turn so the router can
interpret short follow-up messages. The summary is intentionally non-executable:
it is evidence for language understanding only, not a source of tool authority.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping


RECENT_INTERACTION_CONTEXT_MARKER = "ROUTER RECENT INTERACTION SUMMARY:"


def build_recent_interaction_summary(
    *,
    latest_quickreply_tmpl: Mapping[str, Any] | None = None,
    recent_template_msgs: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    template_data = _latest_template_data(latest_quickreply_tmpl, recent_template_msgs)
    if not isinstance(template_data, Mapping):
        return {}
    data = template_data.get("data") if isinstance(template_data.get("data"), Mapping) else template_data
    if not isinstance(data, Mapping):
        return {}

    source = str(template_data.get("assistant_response_source") or data.get("assistant_response_source") or "").strip()
    assistant_response = str(data.get("assistantResponse") or "").strip()
    metadata = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}
    response_shape_key = str(metadata.get("response_shape_key") or "").strip()

    summary: dict[str, Any] = {
        "reference_only": True,
        "do_not_execute_from_context": True,
        "last_answer_shape": str(template_data.get("template") or data.get("template") or "").strip(),
        "last_response_source": source,
        "last_response_shape_key": response_shape_key,
    }
    summary.update(_infer_task_summary(source=source, response_shape_key=response_shape_key, assistant_response=assistant_response))
    if assistant_response:
        summary["last_answer_excerpt"] = _compact_text(assistant_response, limit=220)
    return _drop_empty(summary)


def recent_interaction_router_message(summary: Mapping[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(summary, Mapping) or not summary:
        return None
    return {
        "role": "assistant",
        "content": RECENT_INTERACTION_CONTEXT_MARKER
        + "\n"
        + json.dumps(dict(summary), ensure_ascii=False, separators=(",", ":")),
    }


def insert_recent_interaction_router_message(
    messages: list[dict[str, Any]],
    summary: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    router_message = recent_interaction_router_message(summary)
    if router_message is None:
        return messages
    copied = [dict(message) for message in messages]
    for index in range(len(copied) - 1, -1, -1):
        if copied[index].get("role") == "user":
            copied.insert(index, router_message)
            return copied
    copied.append(router_message)
    return copied


def parse_recent_interaction_router_message(content: str) -> dict[str, Any]:
    if RECENT_INTERACTION_CONTEXT_MARKER not in str(content or ""):
        return {}
    raw = str(content or "").split(RECENT_INTERACTION_CONTEXT_MARKER, 1)[1].strip()
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, Mapping):
        return {}
    parsed_dict = dict(parsed)
    parsed_dict["reference_only"] = True
    parsed_dict["do_not_execute_from_context"] = True
    return _drop_empty(parsed_dict)


def _latest_template_data(
    latest_quickreply_tmpl: Mapping[str, Any] | None,
    recent_template_msgs: list[Mapping[str, Any]] | None,
) -> Mapping[str, Any] | None:
    if isinstance(latest_quickreply_tmpl, Mapping):
        return latest_quickreply_tmpl
    for message in recent_template_msgs or []:
        template_data = message.get("template_data") if isinstance(message, Mapping) else None
        if isinstance(template_data, Mapping):
            return template_data
    return None


def _infer_task_summary(*, source: str, response_shape_key: str, assistant_response: str) -> dict[str, Any]:
    text = assistant_response or ""
    source_key = source or response_shape_key
    if source_key in {
        "code_coupon_resolver",
        "code_coupon_applicability",
        "code_product_coupon_eligibility",
        "coupon_applicable_products_by_owned_coupon",
    } or "적용 가능 상품" in text or "적용 상품" in text:
        subject = _quoted_subject(text)
        return {
            "last_task": "applicable_products_lookup",
            "last_domain": "transaction",
            "last_subject": subject,
            "last_subject_type": "coupon_or_benefit" if subject else "",
            "last_result_type": "applicable_products",
            "last_user_goal": "특정 쿠폰/기획전/이벤트의 적용 가능 상품 조회",
        }
    if source_key in {"code_event_applicable_products", "event_applicable_products_lookup"}:
        return {
            "last_task": "applicable_products_lookup",
            "last_domain": "discovery",
            "last_subject_type": "event_or_deal",
            "last_result_type": "applicable_products",
            "last_user_goal": "특정 이벤트/기획전의 적용 가능 상품 조회",
        }
    if source_key in {"code_product_applicable_events", "product_event_lookup"}:
        return {
            "last_task": "applicable_events_lookup",
            "last_domain": "discovery",
            "last_subject_type": "product",
            "last_result_type": "applicable_events",
            "last_user_goal": "특정 상품에 적용 가능한 이벤트/기획전 조회",
        }
    return {
        "last_task": response_shape_key or source or "",
        "last_result_type": response_shape_key or "",
    }


def _quoted_subject(text: str) -> str:
    match = re.search(r"[‘']([^’']{2,80})[’']", text or "")
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    match = re.search(r"^([^\n]{2,80}?)(?:\s*적용\s*가능\s*상품|에\s*적용\s*가능)", text or "")
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip(" :-")
    return ""


def _compact_text(text: str, *, limit: int) -> str:
    compacted = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 16].rstrip() + " ... [truncated]"


def _drop_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _drop_empty(item)) not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _drop_empty(item)) not in (None, "", [], {})]
    return value
