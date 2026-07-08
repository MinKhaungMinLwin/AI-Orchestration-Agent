from __future__ import annotations

import os

_TEST_ENV_DEFAULTS = {
    "PROJECT_NAME": "test",
    "ROOT_PATH": "",
    "API_SECRET_KEY": "secret",
    "TSTATION_BE_API": "http://localhost",
    "TSTATION_BE_MCP": "http://localhost",
    "AI_DEFAULT_PROVIDER": "openai",
    "AI_GATEWAY_BASE_URL": "http://localhost/v1",
    "AI_GATEWAY_API_KEY": "test",
    "AI_MODEL": "gpt-test",
    "AI_MODEL_REASONING": "gpt-test",
    "AI_MODEL_MINI": "gpt-test",
    "AI_MODEL_LEADING_AGENT": "gpt-test",
    "AI_MODEL_QC_AGENT": "gpt-test",
    "AI_MODEL_TRANSACTION_AGENT": "gpt-test",
    "UPSTAGE_API_KEY": "test",
    "OPENAI_API_KEY": "test",
    "REDIS_CONVERSATION_MANAGEMENT_PASSWORD": "",
    "REDIS_CONVERSATION_MANAGEMENT_URL": "redis://localhost:6379/0",
    "REDIS_QUEUE_URL": "redis://localhost:6379/1",
    "REDIS_PASSWORD": "",
    "REDIS_URL": "redis://localhost:6379/0",
    "RABBITMQ_NODENAME": "rabbit@test",
    "RABBITMQ_USERNAME": "guest",
    "RABBITMQ_PASSWORD": "guest",
    "RABBITMQ_URL": "amqp://guest:guest@localhost:5672/",
    "RABBITMQ_URL_MANAGEMENT": "http://localhost:15672",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
    "AWS_DEFAULT_REGION": "ap-northeast-2",
    "S3_BUCKET_NAME": "test",
    "GF_SECURITY_ADMIN_USER": "admin",
    "GF_SECURITY_ADMIN_PASSWORD": "admin",
    "LOKI_URL": "http://localhost",
    "PROMETHEUS_URL": "http://localhost",
    "LANGFUSE_HOST": "http://localhost",
    "LANGFUSE_PROJECT_NAME": "test",
    "LANGFUSE_SECRET_KEY": "test",
    "LANGFUSE_PUBLIC_KEY": "test",
}

for key, value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(key, value)

from services.tstation.chat_v3.executor import _normalize_tool_call  # noqa: E402
from services.tstation.chat_v3.tools.discovery import DISCOVERY_TOOLS  # noqa: E402
from services.tstation.chat_v3.tools import tools_for_domain  # noqa: E402


def test_v3_discovery_tools_do_not_expose_car_model_group_lookup() -> None:
    tool_names = {tool.name for tool in DISCOVERY_TOOLS}

    assert "search_car_model_groups_tool" not in tool_names
    assert "get_products_recommendations_tool" in tool_names


def test_v3_transaction_tools_can_resolve_product_goods_no() -> None:
    tool_names = {tool.name for tool in tools_for_domain("TRANSACTION")}

    assert "search_product_tool" in tool_names


def test_removed_car_model_group_call_rewrites_to_recommendation_vehicle_type() -> None:
    normalized = _normalize_tool_call(
        {"name": "search_car_model_groups_tool", "args": {"keyword": "그랜저"}, "id": "call-1"}
    )

    assert normalized["name"] == "get_products_recommendations_tool"
    assert normalized["args"] == {"rcmd_type": "tstation", "limit": 3, "vehicle_type": "passenger"}
    assert normalized["id"] == "call-1"


def test_removed_car_model_group_call_rewrites_suv_alias() -> None:
    normalized = _normalize_tool_call({"name": "search_car_model_groups_tool", "args": {"keyword": "G바겐"}})

    assert normalized["name"] == "get_products_recommendations_tool"
    assert normalized["args"]["vehicle_type"] == "suv"


def test_non_removed_tool_call_is_preserved() -> None:
    call = {"name": "search_product_tool", "args": {"keyword": "벤투스"}}

    assert _normalize_tool_call(call) is call
