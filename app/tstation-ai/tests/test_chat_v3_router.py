from __future__ import annotations

import os
from datetime import date

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

from schemas.tstation.chat import TStationChatRequest  # noqa: E402
from services.tstation.chat_v3.router.route import _clear_in_range_reservation_date_guard  # noqa: E402
from services.tstation.chat_v3.router.schemas import Domain, GuardId, RouteDecision  # noqa: E402
from services.tstation.chat_v3.slots.schemas import SlotsPatch  # noqa: E402


def _request(**kwargs) -> TStationChatRequest:
    return TStationChatRequest(
        messages=[{"role": "user", "content": "2026년 07월 09일 15:00"}],
        stream=True,
        user_id="M200012931",
        session_id="session",
        **kwargs,
    )


def _reservation_guard_decision(requested_cal_day: str | None) -> RouteDecision:
    return RouteDecision(
        guard_id=GuardId.RESERVATION_DATE_RANGE,
        domain=Domain.TRANSACTION,
        intents=["reservation_schedule_selection"],
        slots_patch=SlotsPatch(requested_cal_day=requested_cal_day, rsv_hour="15"),
        needs_selection_card=False,
    )


def test_in_range_reservation_schedule_slot_clears_date_range_guard() -> None:
    decision = _reservation_guard_decision("20260709")

    result = _clear_in_range_reservation_date_guard(decision, _request(), today=date(2026, 7, 8))

    assert result.guard_id == GuardId.NONE
    assert result.slots_patch.requested_cal_day == "20260709"
    assert result.slots_patch.rsv_hour == "15"


def test_out_of_range_reservation_schedule_keeps_date_range_guard() -> None:
    decision = _reservation_guard_decision("20260808")

    result = _clear_in_range_reservation_date_guard(decision, _request(), today=date(2026, 7, 8))

    assert result.guard_id == GuardId.RESERVATION_DATE_RANGE


def test_past_reservation_schedule_keeps_date_range_guard() -> None:
    decision = _reservation_guard_decision("20260707")

    result = _clear_in_range_reservation_date_guard(decision, _request(), today=date(2026, 7, 8))

    assert result.guard_id == GuardId.RESERVATION_DATE_RANGE


def test_in_range_reservation_schedule_from_ui_action_clears_date_range_guard() -> None:
    decision = _reservation_guard_decision(None)
    request = _request(ui_action={"slots": {"requested_cal_day": "20260709", "rsv_hour": "15"}})

    result = _clear_in_range_reservation_date_guard(decision, request, today=date(2026, 7, 8))

    assert result.guard_id == GuardId.NONE
