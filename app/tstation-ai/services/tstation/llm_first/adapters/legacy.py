from __future__ import annotations

from typing import Any


def transaction_tool(name: str) -> Any:
    from services.tstation.agents.c_transaction_agent import tools

    return getattr(tools, name)


def discovery_tool(name: str) -> Any:
    from services.tstation.agents.b_discovery_agent import tools

    return getattr(tools, name)


def support_tool(name: str) -> Any:
    from services.tstation.agents.e_support_agent import tools

    return getattr(tools, name)


def normalize_vehicle_type_from_car_type(value: Any, *, fallback_text: str | None = None) -> str | None:
    from services.tstation.policies.ui_action_policy import normalize_vehicle_type_from_car_type as _normalize

    return _normalize(value, fallback_text=fallback_text)


def match_vehicle_model_category(text: str) -> Any:
    from services.tstation.policies.vehicle_category_catalog import match_vehicle_model_category as _match

    return _match(text)


def build_template_from_tool_data(tool_data_list: list[dict[str, Any]], assistant_text: str) -> dict[str, Any] | None:
    from services.tstation.template_mapper import try_build_template

    return try_build_template(tool_data_list, assistant_text)


def latest_template_data(session_id: str, template: str) -> dict[str, Any] | None:
    from services.tstation.chat_history_service import get_chat_history_service

    data = get_chat_history_service().get_latest_template_data(session_id, template)
    return data if isinstance(data, dict) else None


def redis_client() -> Any:
    from services.tstation.chat_history_service import get_redis_client

    return get_redis_client()


def chat_history_ttl_seconds() -> int:
    from services.tstation.chat_history_service import CHAT_HISTORY_TTL_SECONDS

    return int(CHAT_HISTORY_TTL_SECONDS)
