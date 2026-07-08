from __future__ import annotations

import asyncio
import json
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

from services.tstation.agents.templates.schemas import LocationTemplate  # noqa: E402
from services.tstation.chat_v3 import templates  # noqa: E402


class _FakeStructuredLLM:
    async def ainvoke(self, messages):
        return LocationTemplate(
            assistantResponse="경기권 보관서비스 매장입니다.",
            stores=[
                {
                    "nameAddress": "티스테이션 안양호계점 · 경기도 안양시 동안구",
                    "distance": "",
                    "detailAddress": "귀인로 76 (호계동)",
                    "isAllMyT": True,
                    "todayInstall": False,
                    "tnaDelivery": False,
                    "description": "전화: 031-458-2288",
                }
            ],
            metadata=[
                {
                    "shopId": "wrong",
                    "shopName": "티스테이션 안양호계점 · 경기도 안양시 동안구",
                    "isInstallable": True,
                }
            ],
        )


class _FakeRouterLLM:
    def with_structured_output(self, model, method):
        return _FakeStructuredLLM()


def test_location_template_normalizes_store_name_and_address_from_tool_output(monkeypatch):
    monkeypatch.setattr(templates, "get_router_llm", lambda: _FakeRouterLLM())
    tool_output = {
        "status": "success",
        "data": {
            "stores": [
                {
                    "shop_id": "C01410",
                    "shop_nm": "티스테이션 안양호계점",
                    "addr_base": "경기도 안양시 동안구",
                    "addr_dtl": "귀인로 76 (호계동)",
                }
            ]
        },
    }

    event = asyncio.run(
        templates.build_rich_data_event(
            "경기권 보관서비스 매장입니다.",
            [{"name": "get_store_list_tool", "args": {}, "output": json.dumps(tool_output, ensure_ascii=False)}],
        )
    )

    assert event is not None
    assert event["template"] == "location"
    store = event["data"]["stores"][0]
    meta = event["data"]["metadata"][0]
    assert store["nameAddress"] == "티스테이션 안양호계점"
    assert store["detailAddress"] == "경기도 안양시 동안구 귀인로 76 (호계동)"
    assert store["description"] == (
        "주소: 경기도 안양시 동안구 귀인로 76 (호계동)\n"
        "연락처: -\n"
        "평일: -\n"
        "토요일: -\n"
        "휴무일: -\n"
        "특징: -\n"
        "서비스: -"
    )
    assert meta["shopId"] == "C01410"
    assert meta["shopName"] == "티스테이션 안양호계점"


def test_location_answer_uses_fixed_store_info_labels():
    tool_output = {
        "status": "success",
        "data": {
            "stores": [
                {
                    "shop_id": "F07779",
                    "shop_nm": "티스테이션 방배점",
                    "is_all_my_t": True,
                    "is_installable": True,
                    "is_imported_car": True,
                    "is_ev_specialty": True,
                    "is_ev_charge_available": False,
                    "svc_codes": ["113", "119", "121", "124", "126"],
                    "addr_base": "서울특별시 서초구",
                    "addr_dtl": "효령로 225 (서초동)",
                    "tel_no": "02-3471-1918",
                    "shop_biz_strt_time": "09",
                    "shop_biz_end_time": "19",
                    "shop_biz_end_wday": "토요일",
                    "shop_sat_strt_time": "09:00",
                    "shop_sat_end_time": "16:00",
                }
            ]
        },
    }

    answer = templates.format_location_answer(
        "서초구에 **타이어 보관서비스 가능한 매장**은 1곳이 확인됩니다.",
        [{"name": "get_store_list_tool", "args": {}, "output": json.dumps(tool_output, ensure_ascii=False)}],
    )

    assert answer == (
        "서초구에 **타이어 보관서비스 가능한 매장**은 1곳이 확인됩니다.\n\n"
        "1. **티스테이션 방배점**\n"
        "   주소: 서울특별시 서초구 효령로 225 (서초동)\n"
        "   연락처: 02-3471-1918\n"
        "   평일: 09:00~19:00\n"
        "   토요일: 09:00~16:00\n"
        "   휴무일: 일요일\n"
        "   특징: all my T, 온라인 장착 가능, 수입차 특화점, 전기차 특화점\n"
        "   서비스: 타이어, 타이어 보관서비스, 경정비, 휠얼라이먼트, 무상점검"
    )
