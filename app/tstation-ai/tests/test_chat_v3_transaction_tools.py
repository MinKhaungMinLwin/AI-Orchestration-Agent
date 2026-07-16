import os

import pytest

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

from services.tstation.chat_v3.tools.transaction import TRANSACTION_READ_TOOLS  # noqa: E402
from services.tstation.agents.c_transaction_agent import tools as transaction_tools  # noqa: E402
from services.tstation.agents.c_transaction_agent.install_availability import (  # noqa: E402
    combine_install_availability,
)


def test_transaction_tools_use_unified_install_availability_lookup() -> None:
    names = {tool.name for tool in TRANSACTION_READ_TOOLS}
    availability_tool = next(tool for tool in TRANSACTION_READ_TOOLS if tool.name == "get_store_install_availability_tool")

    assert "get_store_install_availability_tool" in names
    assert "goods_items" in availability_tool.args
    assert "get_logistics_inventory_tool" not in names
    assert "get_store_inventory_tool" not in names
    assert "get_store_schedule_tool" not in names
    assert "get_multi_store_schedule_tool" not in names


def _availability_result(stores: list[tuple[str, list[str]]]) -> dict:
    return {
        "status": "success",
        "data": {
            "items": [{"shop_id": shop_id, "status": "available"} for shop_id, _ in stores],
            "schedule": {
                "stores": [
                    {
                        "shop_id": shop_id,
                        "shop_nm": shop_id,
                        "is_installable": True,
                        "slots": [{"cal_day": "20260717", "tm": tm} for tm in times],
                    }
                    for shop_id, times in stores
                ]
            },
        },
    }


def test_combined_install_availability_intersects_stores_and_exact_slots() -> None:
    payload = combine_install_availability(
        results=[
            _availability_result([("S1", ["09", "10"]), ("S2", ["09"])]),
            _availability_result([("S1", ["09", "11"]), ("S3", ["09"])]),
        ],
        candidate_shop_ids=["S1", "S2", "S3"],
        requested_cal_day=None,
    )

    assert payload["combined"] == {
        "all_products_available_together": True,
        "common_shop_ids": ["S1"],
        "first_available_slot": {"cal_day": "20260717", "tm": "09"},
    }
    assert payload["items"][0]["available_times_on_first_day"] == ["09"]


def test_install_availability_tool_uses_all_goods_items(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_lookup(**kwargs):
        calls.append(kwargs)
        return _availability_result([("S1", ["09"])])

    monkeypatch.setattr(transaction_tools, "_get_store_install_availability_result", fake_lookup)

    result = transaction_tools.get_store_install_availability_tool.invoke({
        "shop_id_list": ["S1"],
        "goods_items": [
            {"goods_no": "G-FRONT", "ord_qty": 2},
            {"goods_no": "G-REAR", "ord_qty": 1},
        ],
    })

    assert [call["goods_no"] for call in calls] == ["G-FRONT", "G-REAR"]
    assert [call["ord_qty"] for call in calls] == [2, 1]
    assert result["data"]["combined"]["common_shop_ids"] == ["S1"]
    assert result["data"]["combined"]["first_available_slot"] == {"cal_day": "20260717", "tm": "09"}
