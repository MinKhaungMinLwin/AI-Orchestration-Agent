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

from services.tstation.agents.e_support_agent.tools import get_static_faq_policy_tool  # noqa: E402
from services.tstation.chat_v3.router.schemas import Domain, GuardId, RouteDecision  # noqa: E402
from services.tstation.chat_v3.service import _static_faq_policy_context  # noqa: E402
from services.tstation.chat_v3.tools.support import SUPPORT_TOOLS  # noqa: E402
from services.tstation.common.cta_urls import CTAUrls  # noqa: E402
from services.tstation.policies.static_faq_policy import STATIC_FAQ_POLICY_DATABASE, get_static_faq_policy  # noqa: E402


def test_static_faq_policy_database_contains_moved_router_policy_keys() -> None:
    assert set(STATIC_FAQ_POLICY_DATABASE) == {
        "vehicle_type_compatibility",
        "pickup_status",
        "pickup_info",
        "direct_home_delivery",
        "shipping_fee_region",
        "online_store_price_policy",
        "regional_price_policy",
        "past_event_page",
        "maintenance_history_access_policy",
        "maintenance_reminding_alarm",
        "my_goods_review_lookup",
        "store_service_review_write",
        "keep_service_history_lookup",
        "tire_check_result_lookup",
    }
    assert "집으로 배송받아 직접 장착하는 방식은 지원하지 않아요" in (
        get_static_faq_policy("direct_home_delivery") or {}
    ).get("answer", "")


def test_static_faq_policy_tool_returns_official_answer_by_key() -> None:
    result = get_static_faq_policy_tool.invoke({"policy_key": "shipping_fee_region"})

    assert result["status"] == "success"
    assert result["data"]["policy_key"] == "shipping_fee_region"
    assert "상품 1개당 배송비 1만 원" in result["data"]["answer"]
    assert result["data"]["quick_replies"]


def test_static_faq_policy_buttons_use_legacy_cta_urls() -> None:
    expectations = {
        "past_event_page": CTAUrls.PROMOTION_PAST_EVENT_LIST,
        "maintenance_history_access_policy": CTAUrls.STORE_SERVICE_HISTORY,
        "maintenance_reminding_alarm": CTAUrls.REMINDING_ALARM,
        "my_goods_review_lookup": CTAUrls.GOODS_REVIEW,
        "store_service_review_write": CTAUrls.STORE_SERVICE_HISTORY,
        "keep_service_history_lookup": CTAUrls.KEEP_SERVICE_HIST,
        "tire_check_result_lookup": CTAUrls.TIRE_CHECK_RESULT_LIST,
    }

    for policy_key, expected_url in expectations.items():
        policy = get_static_faq_policy(policy_key)
        assert policy is not None
        urls = {chip.get("url") for chip in policy["quick_replies"]}
        assert expected_url in urls


def test_static_faq_policy_tool_is_registered_for_v3_support() -> None:
    assert "get_static_faq_policy_tool" in {tool.name for tool in SUPPORT_TOOLS}


def test_static_faq_policy_context_forces_key_lookup() -> None:
    decision = RouteDecision(
        guard_id=GuardId.NONE,
        domain=Domain.SUPPORT,
        intents=["direct_home_delivery", "delivery_policy"],
        needs_selection_card=False,
    )

    context = _static_faq_policy_context(decision)

    assert context is not None
    assert "policy_key=direct_home_delivery" in context
    assert "get_static_faq_policy_tool" in context
