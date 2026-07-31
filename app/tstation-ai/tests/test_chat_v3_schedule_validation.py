import json
import os

from schemas.tstation.chat import TStationChatRequest
from schemas.tstation.slots import ConversationSlots


for key in (
    "PROJECT_NAME",
    "ROOT_PATH",
    "API_SECRET_KEY",
    "TSTATION_BE_API",
    "TSTATION_BE_MCP",
    "AI_DEFAULT_PROVIDER",
    "AI_GATEWAY_BASE_URL",
    "AI_GATEWAY_API_KEY",
    "AI_MODEL",
    "AI_MODEL_REASONING",
    "AI_MODEL_MINI",
    "AI_MODEL_LEADING_AGENT",
    "AI_MODEL_QC_AGENT",
    "AI_MODEL_TRANSACTION_AGENT",
    "UPSTAGE_API_KEY",
    "OPENAI_API_KEY",
    "REDIS_CONVERSATION_MANAGEMENT_PASSWORD",
    "REDIS_CONVERSATION_MANAGEMENT_URL",
    "REDIS_QUEUE_URL",
    "REDIS_PASSWORD",
    "REDIS_URL",
    "RABBITMQ_NODENAME",
    "RABBITMQ_USERNAME",
    "RABBITMQ_PASSWORD",
    "RABBITMQ_URL",
    "RABBITMQ_URL_MANAGEMENT",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_DEFAULT_REGION",
    "S3_BUCKET_NAME",
    "GF_SECURITY_ADMIN_USER",
    "GF_SECURITY_ADMIN_PASSWORD",
    "LOKI_URL",
    "PROMETHEUS_URL",
    "LANGFUSE_HOST",
    "LANGFUSE_PROJECT_NAME",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_PUBLIC_KEY",
):
    os.environ.setdefault(key, "test")
os.environ["REDIS_CONVERSATION_MANAGEMENT_URL"] = "redis://localhost:6379/0"
os.environ["REDIS_QUEUE_URL"] = "redis://localhost:6379/1"
os.environ["REDIS_URL"] = "redis://localhost:6379/2"

from services.tstation.chat_v3 import schedule_validation  # noqa: E402
from services.tstation.chat_v3.router.schemas import Domain, RouteDecision  # noqa: E402
from services.tstation.chat_v3.slots.schemas import SlotsPatch  # noqa: E402


def _slots() -> ConversationSlots:
    return ConversationSlots(
        goods_no="G0001",
        tire_size="245/40R18",
        ord_qty=2,
        shop_id="F00721",
        shop_name="티스테이션 판교점",
        requested_cal_day="20260731",
        rsv_hour="14",
        pending_intent="order",
        goal_type="place_order",
    )


def _request(*, ui_action: dict | None = None) -> TStationChatRequest:
    return TStationChatRequest(
        messages=[{"role": "user", "content": "오늘 2시"}],
        user_id="u",
        session_id="s",
        ui_action=ui_action,
    )


def test_manual_schedule_completion_requires_validation_even_when_router_intent_is_wrong():
    decision = RouteDecision(
        domain=Domain.TRANSACTION,
        intents=["reservation_status_lookup"],
        slots_patch=SlotsPatch(requested_cal_day="20260731", rsv_hour="14"),
    )

    assert schedule_validation.needs_preorder_schedule_validation(_request(), decision, _slots()) is True


def test_matching_availability_slot_is_positive_evidence():
    output = {
        "status": "success",
        "data": {
            "items": [
                {
                    "shop_id": "F00721",
                    "status": "available",
                    "slots": [{"cal_day": "20260731", "tm": "1400"}],
                }
            ]
        },
    }
    evidence = schedule_validation.current_turn_evidence(
        [{"name": schedule_validation.AVAILABILITY_TOOL, "output": json.dumps(output)}],
        _slots(),
    )

    assert evidence.checked is True
    assert evidence.available is True
    assert evidence.reason == "matching_slot"


def test_no_inventory_is_checked_but_not_available():
    output = {
        "status": "success",
        "data": {
            "items": [
                {
                    "shop_id": "F00721",
                    "status": "no_inventory",
                    "has_today_stock": False,
                    "has_tna_stock": False,
                    "has_logistics_stock": False,
                    "slots": [],
                }
            ],
            "schedule": {"tier": "none", "stores": []},
        },
    }
    evidence = schedule_validation.current_turn_evidence(
        [{"name": schedule_validation.AVAILABILITY_TOOL, "output": json.dumps(output)}],
        _slots(),
    )

    assert evidence.checked is True
    assert evidence.available is False
    assert evidence.reason == "no_inventory"


def test_different_hour_does_not_validate_preorder():
    output = {
        "status": "success",
        "data": {
            "items": [
                {
                    "shop_id": "F00721",
                    "status": "available",
                    "slots": [{"cal_day": "20260731", "tm": "1500"}],
                }
            ]
        },
    }
    evidence = schedule_validation.current_turn_evidence(
        [{"name": schedule_validation.AVAILABILITY_TOOL, "output": output}],
        _slots(),
    )

    assert evidence.checked is True
    assert evidence.available is False
    assert evidence.reason == "slot_unavailable"


def test_datepick_ui_selection_can_reuse_matching_context_evidence():
    request = _request(
        ui_action={
            "action_type": "select_schedule",
            "slots": {"requested_cal_day": "20260731", "rsv_hour": "14"},
        }
    )
    context_items = [
        {
            "tool": schedule_validation.AVAILABILITY_TOOL,
            "data": {
                "status": "success",
                "data": {
                    "items": [
                        {
                            "shop_id": "F00721",
                            "status": "available",
                            "slots": [{"cal_day": "20260731", "tm": "14"}],
                        }
                    ]
                },
            },
        }
    ]

    evidence = schedule_validation.context_evidence(context_items, _slots())

    assert schedule_validation.is_schedule_ui_selection(request) is True
    assert evidence.available is True
