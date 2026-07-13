"""Store ordering when the user explicitly asks for a sort_by.

An explicit sort_by is the customer's ordering. The BE already returns the rows in
that order (rating: SHOP_EVAL_CVRT_IDX DESC NULLS LAST), so the tool layer must not
re-rank all_my_t stores to the front — that silently breaks the requested order.
The all_my_t priority still applies to the default/distance modes.
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

from services.tstation.agents.c_transaction_agent import tools  # noqa: E402


def _store(shop_id: str, *, all_my_t: bool = False, installable: bool = True, distance: float | None = None) -> dict:
    return {
        "shop_id": shop_id,
        "is_all_my_t": all_my_t,
        "is_installable": installable,
        "distance_km": distance,
    }


def _ids(stores: list[dict]) -> list[str]:
    return [store["shop_id"] for store in stores]


def test_rating_sort_keeps_backend_order_instead_of_promoting_all_my_t():
    # BE order = rating desc. "A" is a plain store rated above the all_my_t store "B";
    # promoting B would show a lower-rated store first in a rating-sorted list.
    stores = [_store("A"), _store("B", all_my_t=True), _store("C")]

    assert _ids(tools._sort_store_candidates(stores, "rating")) == ["A", "B", "C"]


def test_review_count_sort_keeps_backend_order_too():
    stores = [_store("A"), _store("B", all_my_t=True)]

    assert _ids(tools._sort_store_candidates(stores, "review_count")) == ["A", "B"]


def test_default_sort_still_prioritizes_all_my_t_then_installable_then_distance():
    # Purchase/booking flows are unchanged: all_my_t first, then installable, then nearest.
    stores = [
        _store("far", distance=9.0),
        _store("near", distance=1.0),
        _store("allmyt", all_my_t=True, distance=8.0),
        _store("not_installable", installable=False, distance=0.5),
    ]

    assert _ids(tools._sort_store_candidates(stores, None)) == ["allmyt", "near", "far", "not_installable"]


def test_distance_sort_still_prioritizes_all_my_t():
    stores = [_store("near", distance=1.0), _store("allmyt", all_my_t=True, distance=8.0)]

    assert _ids(tools._sort_store_candidates(stores, "distance")) == ["allmyt", "near"]


def test_rating_sort_does_not_mutate_the_input_list():
    stores = [_store("A"), _store("B", all_my_t=True)]

    result = tools._sort_store_candidates(stores, "rating")
    result.reverse()

    assert _ids(stores) == ["A", "B"]
