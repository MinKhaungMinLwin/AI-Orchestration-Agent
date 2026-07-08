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

from services.tstation.agents.templates.schemas import DatepickTemplate, LocationTemplate, ProductTemplate  # noqa: E402
from schemas.tstation.chat import TStationChatRequest  # noqa: E402
from schemas.tstation.slots import ConversationSlots  # noqa: E402
from services.tstation.chat_v3 import service  # noqa: E402
from services.tstation.chat_v3 import templates  # noqa: E402
from services.tstation.chat_v3.router.schemas import Domain, RouteDecision  # noqa: E402


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


class _FakeToolLoopExecutor:
    def __init__(self, *args, **kwargs):
        self.final_text = "Ready to confirm this order."
        self.tool_calls = [
            {
                "name": "get_cheapest_price_tool",
                "args": {},
                "output": json.dumps({"status": "success", "data": {"cheapest_final_prc": 77050}}),
            }
        ]

    async def stream(self):
        if False:
            yield None


class _FakeDatepickStructuredLLM:
    async def ainvoke(self, messages):
        return DatepickTemplate(
            assistantResponse="예약 가능한 날짜를 확인해 주세요.",
            dates=[
                {"date": "20260710", "available": True, "availableTimes": [10, 11], "index": 0},
                {"date": "이미 포맷됨", "available": False, "availableTimes": [], "index": 1},
            ],
            selectedDate=0,
            metadata={"shopId": "F00721"},
        )


class _FakeDatepickRouterLLM:
    def with_structured_output(self, model, method):
        return _FakeDatepickStructuredLLM()


class _FakeProductStructuredLLM:
    async def ainvoke(self, messages):
        return ProductTemplate(
            assistantResponse="추천 상품입니다.",
            products=[
                {
                    "imageUrl": "",
                    "title": "벤투스 S2 AS 245/45R19",
                    "tires": "",
                    "titleProductName": "벤투스 S2 AS",
                    "titleTires": "245/45R19",
                    "brandName": "HANKOOK",
                    "oeBadgeYn": "",
                    "price": 180000,
                    "originalPrice": 200000,
                    "discountRate": 10,
                    "discountAmount": 20000,
                    "rate": 4.5,
                    "totalQuantity": 7,
                    "tags": [
                        {"text": "프리미엄+", "primary": True},
                        {"text": "사계절", "primary": False},
                        {"text": "조용함", "primary": False},
                    ],
                }
            ],
            metadata=[{"goodsId": "G0001"}],
        )


class _FakeProductRouterLLM:
    def with_structured_output(self, model, method):
        return _FakeProductStructuredLLM()


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


def test_datepick_template_normalizes_raw_yyyymmdd_date(monkeypatch):
    monkeypatch.setattr(templates, "get_router_llm", lambda: _FakeDatepickRouterLLM())

    event = asyncio.run(
        templates.build_rich_data_event(
            "예약 가능한 날짜를 확인해 주세요.",
            [{"name": "get_store_schedule_tool", "args": {"shop_id": "F00721"}, "output": json.dumps({"data": {"stores": []}}, ensure_ascii=False)}],
        )
    )

    assert event is not None
    assert event["template"] == "datepick"
    assert event["data"]["dates"][0]["date"] == "2026년 07월 10일"
    assert event["data"]["dates"][1]["date"] == "이미 포맷됨"


def test_product_template_normalizes_tags_from_tool_output(monkeypatch):
    monkeypatch.setattr(templates, "get_router_llm", lambda: _FakeProductRouterLLM())
    tool_output = {
        "status": "success",
        "items": [
            {
                "goods_no": "G0001",
                "goods_nm": "벤투스 S2 AS",
                "tire_size_1": "245/45R19",
                "brand_nm": "HANKOOK",
                "prc_grd_nm": "프리미엄+",
                "goods_pfm_nm": "COMFORT",
                "goods_dtl_pfm_nm": "흡음재 적용",
                "sound_absorber_yn": "Y",
                "three_pmsf_yn": "Y",
                "oe_badge_yn": "Y",
                "extra_fvr_sale_prc": 180000,
                "sale_prc": 200000,
                "rating_avg": 4.5,
                "total_qty": 7,
            }
        ],
    }

    event = asyncio.run(
        templates.build_rich_data_event(
            "추천 상품입니다.",
            [{"name": "search_product_tool", "args": {}, "output": json.dumps(tool_output, ensure_ascii=False)}],
        )
    )

    assert event is not None
    assert event["template"] == "product"
    product = event["data"]["products"][0]
    assert product["tags"] == [
        {"text": "프리미엄", "primary": True},
        {"text": "정숙/승차감", "primary": False},
        {"text": "흡음재", "primary": False},
        {"text": "3PMS", "primary": False},
    ]
    assert product["oeBadgeYn"] == "Y"


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


def test_compact_answer_spacing_reduces_blank_lines_to_single_newline():
    answer = templates.compact_answer_spacing(
        "좋아요 😊 T’Bot과 함께 타이어 쇼핑을 도와드릴게요.\n\n"
        "원하시는 방식으로 시작할 수 있어요.\n\n"
        "1. **내 차에 맞는 타이어 추천**\n"
        "   - 등록된 차량 기준으로 찾아드릴 수 있어요.  \n"
        "   \n"
        "원하시면 바로 추천해드릴게요."
    )

    assert "\n\n" not in answer
    assert answer == (
        "좋아요 😊 T’Bot과 함께 타이어 쇼핑을 도와드릴게요.\n"
        "원하시는 방식으로 시작할 수 있어요.\n"
        "1. **내 차에 맞는 타이어 추천**\n"
        "   - 등록된 차량 기준으로 찾아드릴 수 있어요.\n"
        "원하시면 바로 추천해드릴게요."
    )


def test_quantity_question_uses_fixed_quantity_quick_replies():
    chips = templates.quantity_quick_replies(
        "구매 진행을 위해 수량과 장착 매장을 선택해야 해요.\n"
        "보통 타이어는 4개 기준으로 주문하시는데, **4개로 진행할까요?**"
    )

    assert chips == [
        {"label": "1개", "domain": "TRANSACTION"},
        {"label": "2개", "domain": "TRANSACTION"},
        {"label": "3개", "domain": "TRANSACTION"},
        {"label": "4개", "domain": "TRANSACTION"},
    ]


def test_preorder_fallback_builds_ready_order_card_from_slots():
    slots = ConversationSlots(
        goods_no="G000000309783",
        tire_model="벤투스 S2 AS",
        tire_size="245/45R19",
        ord_qty=2,
        shop_id="F00721",
        shop_name="티스테이션 한남점",
        requested_cal_day="20260708",
        rsv_hour="14",
        payment_amount=308200,
        pending_intent="order",
        goal_type="place_order",
    )
    decision = RouteDecision(
        domain=Domain.TRANSACTION,
        intents=["place_order"],
        slots_patch={"rsv_hour": "14"},
    )

    event = templates.build_preorder_fallback(
        "아래 내용으로 구매 진행해도 될까요?",
        slots,
        decision,
    )

    assert event is not None
    assert event["template"] == "preOrder"
    assert event["data"]["isReadyToOrder"] is True
    assert event["data"]["metadata"]["goodsId"] == "G000000309783"
    assert event["data"]["orderInfo"]["storeName"] == "티스테이션 한남점"
    assert event["data"]["orderInfo"]["bookingDateTime"] == "2026년 07월 08일 14:00"


async def _collect_turn_events(request: TStationChatRequest) -> list[str]:
    events = []
    async for event in service._run_turn(request, {}):  # noqa: SLF001
        events.append(event)
    return events


def _parse_sse_event(event: str) -> dict:
    payload = event.removeprefix("data: ").strip()
    return json.loads(payload) if payload.startswith("{") else {}


def test_ready_preorder_takes_priority_over_generic_price_template(monkeypatch):
    async def fake_route_request(*args, **kwargs):
        return RouteDecision(
            domain=Domain.TRANSACTION,
            intents=["place_order"],
            slots_patch={"rsv_hour": "14"},
        )

    async def fake_load_slots(session_id):
        return ConversationSlots(
            goods_no="G000000309783",
            tire_model="Ventus S2 AS",
            tire_size="245/45R19",
            ord_qty=2,
            shop_id="F00721",
            shop_name="T-Station Hannam",
            requested_cal_day="20260708",
            rsv_hour="14",
            payment_amount=154100,
            pending_intent="order",
            goal_type="place_order",
        )

    async def fake_verify_answer(answer, *args, **kwargs):
        return answer

    async def fake_build_rich_data_event(*args, **kwargs):
        raise AssertionError("generic rich template should not run when preOrder is ready")

    async def fake_noop(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "route_request", fake_route_request)
    monkeypatch.setattr(service, "load_slots", fake_load_slots)
    monkeypatch.setattr(service, "ToolLoopExecutor", _FakeToolLoopExecutor)
    monkeypatch.setattr(service.qc, "verify_answer", fake_verify_answer)
    monkeypatch.setattr(service.templates, "build_rich_data_event", fake_build_rich_data_event)
    monkeypatch.setattr(service, "save_slots", fake_noop)
    monkeypatch.setattr(service.memory, "persist_turn_context", fake_noop)
    monkeypatch.setattr(service.memory, "load_tool_context_block", fake_noop)
    monkeypatch.setattr(service, "_tokens_enabled", lambda: False)
    monkeypatch.setattr(service, "_flush_trace", lambda: None)

    request = TStationChatRequest(
        messages=[{"role": "user", "content": "order"}],
        user_id="test-user",
        session_id="test-ready-preorder-priority",
    )

    events = asyncio.run(_collect_turn_events(request))
    data_events = [_parse_sse_event(event) for event in events if event.startswith("data: {")]
    templates_seen = [event.get("template") for event in data_events if event.get("type") == "data"]

    assert "preOrder" in templates_seen
    assert "cheapestProduct" not in templates_seen


def test_preorder_fallback_skips_irrelevant_followup_even_with_ready_slots():
    slots = ConversationSlots(
        goods_no="G000000309783",
        ord_qty=2,
        shop_id="F00721",
        requested_cal_day="20260708",
        rsv_hour="14",
        pending_intent="order",
        goal_type="place_order",
    )

    event = templates.build_preorder_fallback(
        "무이자 할부도 되나요?",
        slots,
        RouteDecision(domain=Domain.TRANSACTION, intents=["installment"]),
    )

    assert event is None


def test_transaction_preview_source_maps_to_location_not_preorder():
    source = templates._pick_source(  # noqa: SLF001
        [{"name": "transaction_store_preview_tool", "args": {}, "output": json.dumps({"data": {"stores": [{}]}})}]
    )

    assert source is not None
    assert source[0] == "location"


def test_save_to_cart_does_not_emit_order_complete_rich_template():
    source = templates._pick_source(  # noqa: SLF001
        [{"name": "save_to_cart_tool", "args": {}, "output": json.dumps({"status": "success", "data": {"result": True}})}]
    )

    assert source is None


def test_qna_complete_event_uses_redirect_link_without_exposing_url_in_answer():
    tool_output = {
        "status": "success",
        "response": "[open](https://csexample.com/cs/chat?summary=raw)",
        "redictLink": {
            "pc": "https://www.tstation.com/customer-service/qna.do?mode=write&payload=abc",
            "mobile": "https://m.tstation.com/customer-service/qna.do?mode=write&payload=abc",
        },
        "cnsl_clss_seq": "10019",
        "inq_tit_nm": "Need help",
        "ai_summary": "Need help with my order",
    }

    event = templates.build_qna_complete_event(
        "Please continue here.\n[open](https://csexample.com/cs/chat?summary=raw)",
        [{"name": "transfer_to_qna_tool", "args": {}, "output": json.dumps(tool_output)}],
    )

    assert event is not None
    assert event["template"] == "qnaComplete"
    assert event["source_tool"] == "transfer_to_qna_tool"
    assert event["data"]["redictLink"] == tool_output["redictLink"]
    assert event["data"]["cnslType"] == "\uae30\ud0c0"
    assert event["data"]["title"] == "Need help"
    assert event["data"]["summary"] == "Need help with my order"
    assert event["data"]["assistantResponse"] == "Please continue here."
    assert "http" not in event["data"]["assistantResponse"]


def test_qna_complete_event_maps_consultation_category_code_to_label():
    tool_output = {
        "status": "success",
        "redictLink": {
            "pc": "https://www.tstation.com/customer-service/qna.do?mode=write&payload=abc",
            "mobile": "https://m.tstation.com/customer-service/qna.do?mode=write&payload=abc",
        },
        "cnsl_clss_seq": "10002",
        "inq_tit_nm": "Product question",
        "ai_summary": "Product question summary",
    }

    event = templates.build_qna_complete_event(
        "Please submit the 1:1 inquiry.",
        [{"name": "transfer_to_qna_tool", "args": {}, "output": json.dumps(tool_output)}],
    )

    assert event is not None
    assert event["data"]["cnslType"] == "\uc0c1\ud488\ubb38\uc758"
    assert event["data"]["cnslType"] != "10002"


def test_v3_support_tools_use_qna_handoff_instead_of_legacy_escalation():
    from services.tstation.chat_v3.tools.support import SUPPORT_TOOLS

    tool_names = {tool.name for tool in SUPPORT_TOOLS}

    assert "transfer_to_qna_tool" in tool_names
    assert "escalate_tool" not in tool_names


def test_transfer_to_qna_tool_defaults_missing_consultation_category_to_etc(monkeypatch):
    from services.tstation.agents.e_support_agent import tools as support_tools

    captured = {}

    def fake_make_qna_payload_urls(cnsl_clss_seq=None, inq_tit_nm=None, ai_summary=None):
        captured["cnsl_clss_seq"] = cnsl_clss_seq
        captured["inq_tit_nm"] = inq_tit_nm
        captured["ai_summary"] = ai_summary
        return {
            "pc": "https://www.tstation.com/customer-service/qna.do?mode=write&payload=abc",
            "mobile": "https://m.tstation.com/customer-service/qna.do?mode=write&payload=abc",
        }

    monkeypatch.setattr(support_tools, "make_qna_payload_urls", fake_make_qna_payload_urls)

    result = support_tools.transfer_to_qna_tool.func(
        cnsl_clss_seq=None,
        inq_tit_nm="1:1 inquiry",
        ai_summary="Generic handoff request",
    )

    assert captured["cnsl_clss_seq"] == "10019"
    assert result["cnsl_clss_seq"] == "10019"

    result = support_tools.transfer_to_qna_tool.func(
        cnsl_clss_seq="99999",
        inq_tit_nm="1:1 inquiry",
        ai_summary="Generic handoff request",
    )

    assert captured["cnsl_clss_seq"] == "10019"
    assert result["cnsl_clss_seq"] == "10019"
