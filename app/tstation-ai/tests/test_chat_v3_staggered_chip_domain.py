"""The domain a canned chip carries decides the NEXT turn's routed domain.

Session 44553d91: the staggered quantity chips were labelled TRANSACTION, so
clicking "2개" routed the follow-up turn to TRANSACTION, which binds no
recommendation tool — the model fell back to search_product_tool and ended up
asking the customer to pick the sorting criteria instead of recommending.

Run from repo root:

    cd app/tstation-ai && ../../.venv/bin/python -m pytest tests/test_chat_v3_staggered_chip_domain.py -q
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

from schemas.tstation.slots import ConversationSlots  # noqa: E402
from schemas.tstation.chat import TStationChatRequest  # noqa: E402
from services.tstation.chat_v3.service import (  # noqa: E402
    _staggered_tire_quantity_choice_event,
    _staggered_tire_size_choice_event,
)
from services.tstation.chat_v3.slots.derive import apply_fe_slots  # noqa: E402
from services.tstation.chat_v3.templates import _QUANTITY_QUICK_REPLIES  # noqa: E402
from services.tstation.chat_v3.tools import tools_for_domains  # noqa: E402

RECOMMEND_TOOL = "get_products_recommendations_tool"


def _staggered_slots(**overrides) -> ConversationSlots:
    values = {"tire_size_front": "245/45R19", "tire_size_rear": "245/55R20"}
    values.update(overrides)
    return ConversationSlots(**values)


def _tap(chip: dict) -> TStationChatRequest:
    """The request the FE sends back when the customer taps `chip`."""
    slots = (chip.get("metadata") or {}).get("slots") or {}
    return TStationChatRequest(
        user_id="probe",
        session_id="staggered-chip-test",
        messages=[{"role": "user", "content": str(chip.get("label"))}],
        chip_context={"domain": chip.get("domain"), "slots": slots, "metadata": {"slots": slots}},
        ui_action={
            "action_type": "select_ui_action",
            "cta_action": "select_ui_action",
            "label": chip.get("label"),
            "metadata": {"slots": slots},
            "slots": slots,
        },
    )


def test_quantity_chips_stay_in_discovery_so_recommendation_tools_bind() -> None:
    event = _staggered_tire_quantity_choice_event(_staggered_slots(tire_size="245/45R19"))

    assert event is not None
    assert {chip["domain"] for chip in event["data"]["quickReplies"]} == {"DISCOVERY"}
    assert event["source_domain"] == "DISCOVERY"
    assert "DISCOVERY" in event["data"]["predictedDomains"]

    bound = {tool.name for tool in tools_for_domains(event["data"]["predictedDomains"])}
    assert RECOMMEND_TOOL in bound


def test_size_chips_and_quantity_chips_agree_on_domain() -> None:
    size_event = _staggered_tire_size_choice_event(_staggered_slots())
    qty_event = _staggered_tire_quantity_choice_event(_staggered_slots(tire_size="245/45R19"))

    assert size_event is not None and qty_event is not None
    size_domains = {chip["domain"] for chip in size_event["data"]["quickReplies"]}
    qty_domains = {chip["domain"] for chip in qty_event["data"]["quickReplies"]}
    assert size_domains == qty_domains


def test_transaction_alone_would_not_bind_the_recommendation_tool() -> None:
    # The regression this guards against: the old TRANSACTION label was not a
    # cosmetic mislabel, it removed the tool the flow depends on.
    bound = {tool.name for tool in tools_for_domains(["TRANSACTION"])}

    assert RECOMMEND_TOOL not in bound


def test_tapping_a_quantity_chip_keeps_the_size_the_customer_just_chose() -> None:
    # _clear_unconfirmed_staggered_size drops tire_size whenever an FE payload does not
    # mention it, so a quantity-only chip wiped the selection and the next turn asked for
    # the size again — the flow could never get past the quantity step.
    slots = _staggered_slots(tire_size="245/45R19")
    event = _staggered_tire_quantity_choice_event(slots)
    assert event is not None
    two = next(chip for chip in event["data"]["quickReplies"] if chip["label"] == "2개")

    after_tap = apply_fe_slots(slots, _tap(two))

    assert after_tap.tire_size == "245/45R19"
    assert after_tap.ord_qty == 2
    # …and therefore the size question does not fire again.
    assert _staggered_tire_size_choice_event(after_tap) is None


def test_a_quantity_only_payload_would_still_wipe_the_size() -> None:
    # Proves the test above detects the real defect rather than passing vacuously:
    # this is exactly the payload the chips used to carry.
    slots = _staggered_slots(tire_size="245/45R19")
    quantity_only = {"label": "2개", "domain": "DISCOVERY", "metadata": {"slots": {"ord_qty": 2}}}

    after_tap = apply_fe_slots(slots, _tap(quantity_only))

    assert after_tap.tire_size is None
    assert _staggered_tire_size_choice_event(after_tap) is not None


def test_order_flow_quantity_chips_remain_transaction() -> None:
    # Mirror case: the generic quantity chips fire only once a product is chosen
    # (_is_quantity_required_flow requires goods_no + an order/cart intent), so
    # they must keep routing to TRANSACTION.
    assert {chip["domain"] for chip in _QUANTITY_QUICK_REPLIES} == {"TRANSACTION"}
