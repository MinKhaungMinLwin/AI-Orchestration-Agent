"""A narrowed tool profile must still leave the turn answerable.

Session d7d21b75: "다이나프로 hpx 2355519 1개 가격 얼마임?" routed to
tool_profile=transaction_price_stock, which bound get_final_price_tool but no tool that
can turn a product name into the goods_no that tool requires. The model called nothing
(tool_count=0) and told the customer it had no price data — recorded as final_status=success.

Run from repo root:

    cd app/tstation-ai && ../../.venv/bin/python -m pytest tests/test_chat_v3_tool_profiles.py -q
"""
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

from services.tstation.chat_v3.tools import PROFILE_TOOL_NAMES, tools_for_domains  # noqa: E402

# Tools that can turn a product name/size into a goods_no.
RESOLVER_TOOLS = frozenset({
    "search_product_tool",
    "search_product_summary_tool",
    "get_products_recommendations_tool",
})


def test_price_stock_profile_can_resolve_a_product() -> None:
    bound = {tool.name for tool in tools_for_domains(["TRANSACTION"], "transaction_price_stock")}

    assert bound & RESOLVER_TOOLS, "a price question naming a product has no reachable answer"
    assert "get_final_price_tool" in bound


# `transaction_order` has the same shape of gap — get_final_price_tool, save_to_cart_tool
# and quick_order_tool all need a goods_no it cannot look up — but no customer report
# points at it yet, and an order turn usually inherits goods_no from an earlier
# recommendation turn. Left alone deliberately; listed so it stays visible.
_KNOWN_GAPS = frozenset({"transaction_order"})


def test_every_pricing_profile_can_reach_a_product() -> None:
    # get_final_price_tool takes goods_no as a required argument, so any profile that
    # offers it must also offer a way to obtain one. This is the invariant the
    # d7d21b75 gap violated; a new profile should fail loudly rather than answer "no data".
    offenders = [
        profile
        for profile, names in PROFILE_TOOL_NAMES.items()
        if "get_final_price_tool" in names and not (names & RESOLVER_TOOLS)
    ]

    assert set(offenders) <= _KNOWN_GAPS, (
        f"profiles price a product they cannot look up: {sorted(set(offenders) - _KNOWN_GAPS)}"
    )


def test_price_stock_profile_is_still_narrower_than_full() -> None:
    # Mirror case: the profile exists to shrink the prompt. If every gap is patched by
    # widening, all profiles converge on `full` and the feature evaporates.
    narrowed = tools_for_domains(["TRANSACTION"], "transaction_price_stock")
    full = tools_for_domains(["TRANSACTION"], None)

    assert len(narrowed) < len(full) / 2
