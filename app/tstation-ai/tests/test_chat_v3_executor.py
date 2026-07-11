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

import asyncio  # noqa: E402
import json  # noqa: E402

from services.tstation.chat_v3.executor import (  # noqa: E402
    ToolLoopExecutor,
    _model_visible_tool_output,
    _normalize_business_failure,
    _normalize_tool_call,
    _output_flow_status,
)
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


def test_inventory_tool_output_is_redacted_only_for_model_visible_observation() -> None:
    output = '{"status":"success","data":{"todayShopArray":[{"shopId":"F00071","stock_qty":8}]}}'

    visible = _model_visible_tool_output("get_store_inventory_tool", output)

    assert output != visible
    assert "status" not in visible
    assert "8" not in visible
    assert "available_quantity_redacted" in visible


def test_cart_result_false_is_normalized_to_error() -> None:
    output = json.dumps(
        {"status": "success", "http_status": 200, "data": {"result": False, "message": "이미 장바구니에 담겨있는 상품입니다."}},
        ensure_ascii=False,
    )

    normalized = _normalize_business_failure("save_to_cart_tool", output)
    parsed = json.loads(normalized)

    assert parsed["status"] == "error"
    assert parsed["error"] == "cart_add_failed"
    assert parsed["data"]["message"] == "이미 장바구니에 담겨있는 상품입니다."
    assert _output_flow_status(normalized) == "error"


def test_cart_result_true_stays_success() -> None:
    output = json.dumps({"status": "success", "http_status": 200, "data": {"result": True}})

    assert _normalize_business_failure("save_to_cart_tool", output) == output
    assert _output_flow_status(output) == "success"


def test_business_failure_normalization_only_applies_to_cart_tool() -> None:
    output = json.dumps({"status": "success", "data": {"result": False}})

    assert _normalize_business_failure("get_final_price_tool", output) == output


def test_executor_records_cart_result_false_as_error() -> None:
    asyncio.run(_assert_executor_records_cart_result_false_as_error())


async def _assert_executor_records_cart_result_false_as_error() -> None:
    class FakeCartTool:
        name = "save_to_cart_tool"

        async def ainvoke(self, args, config=None):
            return {"status": "success", "http_status": 200, "data": {"result": False, "message": "이미 장바구니에 담겨있는 상품입니다."}}

    executor = ToolLoopExecutor([], [FakeCartTool()], {})
    events = []
    async for event in executor._run_tool({"name": "save_to_cart_tool", "args": {"goods_no": "G1", "ord_qty": 2}, "id": "c1"}):
        events.append(event)

    recorded = json.loads(executor.tool_calls[0]["output"])
    assert recorded["status"] == "error"
    assert any('"agent_flow"' in event and '"error"' in event for event in events)
