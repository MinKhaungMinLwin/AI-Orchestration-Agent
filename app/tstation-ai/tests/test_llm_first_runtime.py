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

import pytest  # noqa: E402

from schemas.tstation.chat import TStationChatRequest  # noqa: E402
from services.tstation.llm_first.composer import Composer  # noqa: E402
from services.tstation.llm_first.executor import AFExecutor  # noqa: E402
from services.tstation.llm_first.models import AgentFlow, ConversationState, FactBundle, PlannerDecision, ProductState, SelectedAF, StructuredPlannerDecision, ToolCallRecord  # noqa: E402
from services.tstation.llm_first.planner import LeadingAgentPlanner  # noqa: E402
from services.tstation.llm_first.qc import verify_response  # noqa: E402
from services.tstation.llm_first.runtime import LLMFirstRuntime  # noqa: E402
from services.tstation.llm_first.state import LLMFirstStateStore, apply_state_rules  # noqa: E402
from services.tstation.llm_first.tools import invoke_tool  # noqa: E402
from services.tstation.agents.templates.schemas import DatepickDataEvent, ListCarDataEvent, LocationDataEvent, PreOrderDataEvent, ProductDataEvent, VoucherDataEvent  # noqa: E402


class MemoryStateStore:
    def __init__(self):
        self.state = ConversationState()

    def load(self, session_id: str) -> ConversationState:
        return self.state

    def save(self, session_id: str, state: ConversationState) -> None:
        self.state = state


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.setex_calls = []

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value
        self.setex_calls.append((key, ttl, value))


class StaticComposer:
    async def compose(self, *, user_text, bundle, **kwargs):
        if bundle.missing_inputs:
            return "필요한 정보를 알려주세요."
        if bundle.templates:
            data = bundle.templates[-1].get("data")
            if isinstance(data, dict) and isinstance(data.get("metadata"), dict):
                if data["metadata"].get("source") in {
                    "llm_first_escalation_confirmation",
                    "llm_first_product_comparison",
                    "llm_first_favorite_store_empty",
                }:
                    return data["assistantResponse"]
        return "확인한 결과를 안내드립니다."


class StructuredFakeLLM:
    def __init__(self, decision: PlannerDecision):
        self.decision = decision

    async def ainvoke(self, messages, config=None):
        return self.decision


class FakeLLM:
    def __init__(self, decision: PlannerDecision):
        self.decision = decision

    def with_structured_output(self, schema, strict=True):
        assert schema is StructuredPlannerDecision
        assert strict is True
        return StructuredFakeLLM(self.decision)


class ComposerResult:
    def __init__(self, content: str):
        self.content = content


class CapturingComposerLLM:
    def __init__(self, content: str):
        self.content = content
        self.messages = None
        self.config = None

    async def ainvoke(self, messages, config=None):
        self.messages = messages
        self.config = config
        return ComposerResult(self.content)


class StaticPlanner:
    def __init__(self, decision: PlannerDecision):
        self.decision = decision

    async def plan(self, *, user_text, state, **kwargs):
        return self.decision


class FakeExecutor(AFExecutor):
    async def _call(self, bundle, af, tool_name, args):
        if tool_name == "get_products_recommendations_tool":
            result = {
                "status": "success",
                "data": {
                    "items": [
                        {
                            "goods_no": "G000000000001",
                            "goods_nm": "벤투스 S2 AS",
                            "tire_size_1": "245/45R19",
                            "brand_nm": "한국 타이어",
                            "prc_grd_nm": "프리미엄+",
                            "goods_pfm_nm": "COMFORT",
                            "sound_absorber_yn": "Y",
                            "oe_badge_yn": "N",
                            "t_oe_maker_1": "현대",
                            "smrt_pay_yn": "Y",
                            "sale_prc": 260000,
                            "extra_fvr_sale_prc": 200000,
                            "rate": 4.5,
                            "total_qty": 12,
                        }
                    ]
                },
            }
        elif tool_name == "get_best_selling_products_tool":
            result = {
                "status": "success",
                "data": {
                    "items": [
                        {
                            "goods_no": "G000000000004",
                            "goods_nm": "키너지 EX",
                            "tire_size_1": "205/55R16",
                            "brand_nm": "한국타이어",
                            "sale_prc": 130000,
                            "extra_fvr_sale_prc": 110000,
                            "rate": 4.7,
                            "total_qty": 20,
                        }
                    ]
                },
            }
        elif tool_name == "get_final_price_tool":
            result = {
                "status": "success",
                "data": {
                    "goods_no": args["goods_no"],
                    "sale_prc": 300000,
                    "cheapest_final_prc": 240000,
                },
            }
        elif tool_name == "search_product_tool":
            result = {
                "status": "success",
                "data": {
                    "items": [
                        {
                            "goods_no": "G000000000002",
                            "goods_nm": "벤투스 S2 AS",
                        }
                    ]
                },
            }
        elif tool_name == "search_product_summary_tool":
            keyword = args.get("keyword")
            result = {
                "status": "success",
                "data": {
                    "items": [
                        {
                            "goods_nm": keyword,
                            "ptrn_d_nm": keyword,
                            "prc_grd_nm": "스탠다드" if keyword == "옵티모" else "프리미엄",
                            "goods_pfm_nm": "COMFORT",
                            "goods_dtl_pfm_nm": "컴포트",
                            "season_nm": "사계절",
                            "car_knd_nm": "승용차",
                            "rating_avg": 4.5 if keyword == "키너지 EX" else 4.0,
                            "review_count": 12 if keyword == "키너지 EX" else 8,
                            "reviews": [
                                {
                                    "gdas_cont": (
                                        "승차감이 부드럽고 일상 주행에서 소음이 적다는 의견이 많아요."
                                        if keyword == "키너지 EX"
                                        else "가격 부담이 낮고 기본 주행 성능이 무난하다는 평가가 있어요."
                                    )
                                }
                            ],
                            "available_sizes": ["205/55R16", "215/55R17"],
                        }
                    ]
                },
            }
        elif tool_name == "search_stores_tool":
            result = {
                "status": "success",
                "data": {
                    "stores": [
                        {
                            "shop_id": "S001",
                            "shop_nm": "티스테이션 판교점",
                            "road_addr_base": "경기 성남시 분당구 판교로",
                            "road_addr_dtl": "123",
                            "tel_no": "031-000-0000",
                            "shop_biz_strt_time": "09:00",
                            "shop_biz_end_time": "18:00",
                            "rating_idx": 4.8,
                            "review_count": 27,
                            "is_all_my_t": True,
                            "is_installable": True,
                            "svc_codes": ["116"],
                        }
                    ]
                },
            }
        elif tool_name == "get_favorite_stores_tool":
            result = {
                "status": "success",
                "data": {
                    "stores": [
                        {
                            "shop_id": "S003",
                            "shop_nm": "티스테이션 단골점",
                            "road_addr_base": "서울특별시 강남구",
                            "road_addr_dtl": "1층",
                            "tel_no": "02-000-0000",
                            "is_all_my_t": True,
                            "is_installable": True,
                            "favored_at": "2026-07-01 10:00:00",
                        }
                    ]
                },
            }
        elif tool_name == "transaction_store_preview_tool":
            result = {
                "status": "success",
                "data": {
                    "stores": [
                        {
                            "shop_id": "S002",
                            "shop_nm": "티스테이션 분당점",
                            "address": "경기 성남시 분당구",
                            "todayInstall": True,
                        }
                    ]
                },
            }
        elif tool_name == "get_store_schedule_tool":
            result = {
                "status": "success",
                "data": [
                    {
                        "date": "20260707",
                        "available": True,
                        "availableTimes": [10, 11, 12, 13],
                    }
                ],
            }
        elif tool_name == "get_my_coupons_tool":
            result = {
                "status": "success",
                "data": {
                    "coupons": [
                        {
                            "cpn_no": "C001",
                            "cpn_nm": "타이어 할인 쿠폰",
                            "rt_amt_val": "10%",
                            "use_end_dtime": "2026-12-31 23:59:59",
                        }
                    ]
                },
            }
        elif tool_name == "get_my_reservations_tool":
            result = {
                "status": "success",
                "data": {
                    "reservations": [
                        {
                            "shop_rsv_no": "R001",
                            "shop_nm": "티스테이션 판교점",
                            "vst_rsv_dtime": "2026-07-07 10:00",
                            "shop_vst_rsv_sts_label": "예약완료",
                        }
                    ]
                },
            }
        elif tool_name == "get_orders_of_user_tool":
            result = {
                "status": "success",
                "data": {
                    "orders": [
                        {
                            "ord_no": "O001",
                            "goods_nm": "벤투스 S2 AS",
                            "ord_qty": 4,
                            "sys_reg_dtime": "2026-07-07 09:00:00",
                        }
                    ]
                },
            }
        elif tool_name == "get_maintenance_history_tool":
            result = {
                "status": "success",
                "data": {
                    "items": [
                        {
                            "car_svc_dt": "2026-07-01",
                            "shop_nm": "티스테이션 판교점",
                            "car_svc_info": "타이어 교체",
                            "car_svc_qty": "4",
                        }
                    ]
                },
            }
        elif tool_name == "get_my_warranties_tool":
            result = {
                "status": "success",
                "data": {
                    "warranties": [
                        {
                            "wrt_nm": "안심서비스",
                            "goods_nm": "벤투스 S2 AS",
                            "shop_nm": "티스테이션 판교점",
                            "reg_dtime": "2026-07-01",
                            "expr_dtime": "2027-07-01",
                        }
                    ]
                },
            }
        elif tool_name == "get_my_cars_tool":
            result = {
                "status": "success",
                "data": {
                    "items": [
                        {
                            "car_no": "12가3456",
                            "car_maker": "현대",
                            "car_nm": "쏘나타",
                            "car_model_det": "쏘나타 DN8",
                            "car_lnc_cd": "CAR001",
                            "tire_size_fr": "205/65R16",
                            "tire_size_re": "205/65R16",
                        }
                    ]
                },
            }
        elif tool_name == "get_user_vehicles_tool":
            result = {
                "status": "success",
                "data": {
                    "car_no": args["car_no"],
                    "car_maker": "기아",
                    "car_nm": "K5",
                    "car_model_det": "K5 DL3",
                    "car_lnc_cd": "CAR002",
                    "tire_size_fr": "215/55R17",
                    "tire_size_re": "215/55R17",
                },
            }
        elif tool_name == "search_car_model_groups_tool":
            result = {
                "status": "success",
                "data": {
                    "items": [
                        {
                            "car_model_det": "그랜저 GN7",
                            "year_from": "2022",
                            "year_to": "2026",
                        }
                    ]
                },
            }
        elif tool_name in {"transfer_to_qna_tool", "escalate_tool"}:
            result = None
            bundle.tool_calls.append(ToolCallRecord(
                af=af,
                tool_name=tool_name,
                args=args,
                blocked=True,
                reason=f"side-effect tool blocked in LLM-first MVP: {tool_name}",
            ))
            return result
        else:
            result = {"status": "success", "data": []}
        bundle.tool_calls.append(ToolCallRecord(af=af, tool_name=tool_name, args=args, result=result))
        bundle.facts[tool_name] = result
        return result


class EmptyFavoriteStoreExecutor(FakeExecutor):
    async def _call(self, bundle, af, tool_name, args):
        if tool_name != "get_favorite_stores_tool":
            return await super()._call(bundle, af, tool_name, args)
        result = {"status": "success", "data": {"stores": []}}
        bundle.tool_calls.append(ToolCallRecord(af=af, tool_name=tool_name, args=args, result=result))
        bundle.facts[tool_name] = result
        return result


def test_structured_planner_schema_requires_all_strict_fields() -> None:
    schema = StructuredPlannerDecision.model_json_schema()
    assert set(schema["required"]) == {
        "selected_afs",
        "conversation_goal",
        "answer_mode",
        "requires_user_confirmation",
        "resume_previous_flow",
    }
    selected_af_ref = schema["properties"]["selected_afs"]["items"]["$ref"].removeprefix("#/$defs/")
    selected_af_schema = schema["$defs"][selected_af_ref]
    assert set(selected_af_schema["required"]) == {
        "af",
        "reason",
        "required_inputs",
        "known_inputs",
        "missing_inputs",
    }
    known_inputs_ref = selected_af_schema["properties"]["known_inputs"]["$ref"].removeprefix("#/$defs/")
    known_inputs_schema = schema["$defs"][known_inputs_ref]
    assert known_inputs_schema["additionalProperties"] is False
    assert set(known_inputs_schema["required"]) == {
        "goods_no",
        "tire_size",
        "ord_qty",
        "product_name",
        "product_names",
        "compare_metric",
        "shop_id",
        "store_name",
        "region",
        "store_attribute",
        "store_lookup",
        "date",
        "time",
        "mbr_no",
        "car_no",
        "owner_nm",
        "car_model",
        "car_lnc_cd",
        "vehicle_type",
        "recommendation_type",
        "recommendation_source",
        "season_nm",
        "sort_by",
        "min_price",
        "max_price",
        "limit",
        "vehicle_query",
        "months",
        "from_date",
        "to_date",
        "escalation_target",
        "account_lookup",
    }


def test_planner_selects_recommendation_for_tire_size() -> None:
    planner = LeadingAgentPlanner(FakeLLM(PlannerDecision(
        selected_afs=[
            SelectedAF(
                af=AgentFlow.PRODUCT_RECOMMENDATION,
                reason="user asks for tire recommendation",
                required_inputs=["tire_size"],
                known_inputs={},
                missing_inputs=[],
            )
        ],
        conversation_goal="recommend_tires",
    )))
    decision = asyncio.run(planner.plan(user_text="245/45R19 타이어 추천해줘", state=ConversationState()))
    assert [item.af for item in decision.selected_afs] == [AgentFlow.PRODUCT_RECOMMENDATION]
    assert decision.selected_afs[0].known_inputs["tire_size"] == "245/45R19"


def test_planner_without_llm_does_not_route_by_regex() -> None:
    decision = asyncio.run(
        LeadingAgentPlanner().plan(user_text="245/45R19 타이어 추천해줘", state=ConversationState())
    )

    assert decision.selected_afs == []
    assert decision.answer_mode == "clarification"


def test_composer_prompt_allows_general_tire_knowledge_without_faq_evidence() -> None:
    llm = CapturingComposerLLM(
        "3PMSF는 Three-Peak Mountain Snowflake 마크로, 눈길 성능 기준을 충족한 타이어 표시예요."
    )
    composer = Composer(llm)
    bundle = FactBundle(
        planner=PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.FAQ,
                    reason="general tire term question",
                    known_inputs={},
                )
            ]
        ),
    )
    bundle.tool_calls.append(ToolCallRecord(
        af=AgentFlow.FAQ,
        tool_name="search_faq_hybrid_tool",
        args={"query": "3PMSF 설명해줘", "top_k": 5},
        result={"status": "success", "data": {"items": []}},
    ))

    text = asyncio.run(composer.compose(user_text="3PMSF 설명해줘", bundle=bundle))

    assert llm.messages is not None
    system_prompt = llm.messages[0].content
    assert "you may answer from general tire knowledge instead of refusing".lower() in system_prompt.lower()
    assert "Treat T-Station/company policy" in system_prompt
    assert "Three-Peak Mountain Snowflake" in text


def test_state_dependency_invalidation_on_product_change() -> None:
    state = ConversationState()
    state.commerce_state.product = ProductState(goods_no="G000000000001", product_name="old")
    state.commerce_state.quantity = 4
    state.commerce_state.store.shop_id = "S1"
    state.commerce_state.schedule.date = "20260707"
    state.commerce_state.price.final_price = 100

    updated = apply_state_rules(state, product_patch={"goods_no": "G000000000002", "product_name": "new"})

    assert updated.commerce_state.product.goods_no == "G000000000002"
    assert updated.commerce_state.quantity is None
    assert updated.commerce_state.store.shop_id is None
    assert updated.commerce_state.schedule.date is None
    assert updated.commerce_state.price.final_price is None


def test_state_dependency_invalidation_on_tire_size_change_clears_product() -> None:
    state = ConversationState()
    state.commerce_state.product = ProductState(
        goods_no="G000000000001",
        product_name="벤투스 S2 AS",
        tire_size="245/45R19",
    )
    state.commerce_state.quantity = 4
    state.commerce_state.store.shop_id = "S1"
    state.commerce_state.schedule.date = "20260707"
    state.commerce_state.price.final_price = 100

    updated = apply_state_rules(state, product_patch={"tire_size": "225/45R17"})

    assert updated.commerce_state.product.tire_size == "225/45R17"
    assert updated.commerce_state.product.goods_no is None
    assert updated.commerce_state.product.product_name is None
    assert updated.commerce_state.quantity is None
    assert updated.commerce_state.store.shop_id is None
    assert updated.commerce_state.schedule.date is None
    assert updated.commerce_state.price.final_price is None


def test_redis_state_store_round_trip() -> None:
    redis = FakeRedis()
    store = LLMFirstStateStore(redis_client=redis)
    state = ConversationState()
    state.commerce_state.product.goods_no = "G000000000001"
    state.commerce_state.quantity = 4

    store.save("session-1", state)
    loaded = store.load("session-1")

    assert loaded.commerce_state.product.goods_no == "G000000000001"
    assert loaded.commerce_state.quantity == 4
    assert redis.setex_calls[0][0] == "chat:llm_first_state:session-1"
    assert redis.setex_calls[0][1] > 0


def test_side_effect_tool_is_blocked() -> None:
    with pytest.raises(PermissionError):
        invoke_tool("quick_order_tool", {})


def test_tool_registry_blocks_wrong_af() -> None:
    with pytest.raises(PermissionError):
        invoke_tool("get_final_price_tool", {"goods_no": "G000000000001"}, af=AgentFlow.STORE)


def test_tool_registry_validates_required_args() -> None:
    with pytest.raises(ValueError):
        invoke_tool("get_final_price_tool", {}, af=AgentFlow.PRICE)


def test_runtime_recommendation_stream_emits_product_and_done() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_RECOMMENDATION,
                    reason="user asks for tire recommendation",
                    known_inputs={"tire_size": "245/45R19"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "245/45R19 타이어 추천해줘"}],
        stream=True,
        user_id="u1",
        session_id="s1",
    )

    async def _collect() -> list[str]:
        return [chunk async for chunk in runtime.stream(request)]

    chunks = asyncio.run(_collect())
    body = "".join(chunks)
    product_events = []
    token_events = []
    for line in body.splitlines():
        if not line.startswith("data: {"):
            continue
        event = json.loads(line.removeprefix("data: "))
        if event.get("template") == "product":
            product_events.append(event)
        if event.get("type") == "token":
            token_events.append(event)

    assert '"template": "product"' in body
    ProductDataEvent.model_validate(product_events[0])
    product = product_events[0]["data"]["products"][0]
    assert product["title"] == "벤투스 S2 AS 245/45R19"
    assert product["tires"] == ""
    assert product["titleTires"] == "245/45R19"
    assert product["brandName"] == "한국타이어"
    assert product["oeBadgeYn"] == "N"
    assert product["oeMaker"] == "현대"
    assert product["smrtPayYn"] == "Y"
    assert product["price"] == 200000
    assert product["originalPrice"] == 260000
    assert product["discountAmount"] == 60000
    assert product["discountRate"] == 23.1
    assert product["rate"] == 4.5
    assert product["totalQuantity"] == 12
    assert product["tags"] == [
        {"text": "프리미엄", "primary": True},
        {"text": "정숙/승차감", "primary": False},
        {"text": "흡음재", "primary": False},
    ]
    assert product_events[0]["data"]["isBookingFlow"] is False
    assert product_events[0]["data"]["metadata"][0]["goodsId"] == "G000000000001"
    assert token_events[0]["content"] == "확인한 결과를 안내드립니다."
    assert "data: [DONE]" in body


def test_product_comparison_uses_quickreply_summary_not_product_cards() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_DESCRIPTION,
                    reason="compare named tire products",
                    known_inputs={
                        "product_names": ["키너지 EX", "옵티모"],
                        "compare_metric": "detail",
                    },
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "키너지 ex랑 옵티모랑 비교해줘"}],
        stream=False,
        user_id="u1",
        session_id="product-comparison",
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert text == events[0]["data"]["assistantResponse"]
    assert events[0]["template"] == "quickReply"
    assert events[0]["data"]["quickReplies"] == []
    assert events[0]["data"]["predictedDomains"] == ["DISCOVERY"]
    assert events[0]["data"]["metadata"]["response_shape_key"] == "metric_comparison_summary"
    assert events[0]["data"]["metadata"]["productNames"] == ["키너지 EX", "옵티모"]
    assert "상품 정보를 상품별 표로 비교해드릴게요." in events[0]["data"]["assistantResponse"]
    assert "**키너지 EX**" in events[0]["data"]["assistantResponse"]
    assert "**옵티모**" in events[0]["data"]["assistantResponse"]
    assert "4.5점\n리뷰 12건\n대표 리뷰: 승차감이 부드럽고 일상 주행에서 소음이 적다는 의견이 많아요." in events[0]["data"]["assistantResponse"]
    assert "4점\n리뷰 8건\n대표 리뷰: 가격 부담이 낮고 기본 주행 성능이 무난하다는 평가가 있어요." in events[0]["data"]["assistantResponse"]
    assert [call["tool_name"] for call in metadata["tool_calls"]] == [
        "search_product_summary_tool",
        "search_product_summary_tool",
    ]
    assert metadata["missing_inputs"] == []


def test_product_comparison_guard_handles_recommendation_af_with_product_names() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_RECOMMENDATION,
                    reason="planner selected recommendation but supplied compared products",
                    known_inputs={
                        "product_names": ["키너지 EX", "옵티모"],
                        "compare_metric": "detail",
                        "tire_size": "235/55R19",
                    },
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "키너지 ex랑 옵티모랑 비교해줘"}],
        stream=False,
        user_id="u1",
        session_id="product-comparison-guard",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "quickReply"
    assert metadata["tool_calls"][0]["tool_name"] == "search_product_summary_tool"
    assert all(event["template"] != "product" for event in events)


def test_general_tire_recommendation_does_not_require_size() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_RECOMMENDATION,
                    reason="general tire recommendation",
                    known_inputs={"recommendation_type": "tstation"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "타이어 추천해줘"}],
        stream=False,
        user_id="u1",
        session_id="general-recommendation",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "product"
    assert metadata["missing_inputs"] == []
    assert metadata["tool_calls"][0]["tool_name"] == "get_products_recommendations_tool"
    assert metadata["tool_calls"][0]["args"] == {"rcmd_type": "tstation", "limit": 3}


def test_sized_tire_recommendation_passes_tire_size() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_RECOMMENDATION,
                    reason="size-tied tire recommendation",
                    known_inputs={"tire_size": "225/45R17", "recommendation_type": "value", "limit": 4},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "225/45R17 가성비 타이어 4개 추천"}],
        stream=False,
        user_id="u1",
        session_id="sized-recommendation",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "product"
    assert metadata["tool_calls"][0]["args"] == {
        "rcmd_type": "value",
        "limit": 4,
        "tire_size": "225/45R17",
    }


def test_vehicle_type_recommendation_passes_vehicle_type_without_size() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_RECOMMENDATION,
                    reason="car-type tire recommendation",
                    known_inputs={
                        "recommendation_type": "low_vibration",
                        "vehicle_type": "ev",
                        "season_nm": "사계절",
                    },
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "전기차 사계절 저소음 타이어 추천"}],
        stream=False,
        user_id="u1",
        session_id="vehicle-type-recommendation",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "product"
    assert metadata["tool_calls"][0]["args"] == {
        "rcmd_type": "low_vibration",
        "limit": 3,
        "vehicle_type": "ev",
        "season_nm": "사계절",
    }


def test_best_seller_search_uses_best_selling_tool() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_RECOMMENDATION,
                    reason="best-selling tire search",
                    known_inputs={
                        "recommendation_source": "best_seller",
                        "vehicle_query": "그랜저",
                        "months": 3,
                        "limit": 5,
                    },
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "최근 3개월 그랜저 베스트셀러 타이어"}],
        stream=False,
        user_id="u1",
        session_id="best-seller",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "product"
    assert metadata["tool_calls"][0]["tool_name"] == "get_best_selling_products_tool"
    assert metadata["tool_calls"][0]["args"] == {
        "limit": 5,
        "vehicle_query": "그랜저",
        "months": 3,
    }


def test_price_flow_uses_search_then_final_price() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRICE,
                    reason="user asks for price",
                    known_inputs={"product_name": "벤투스 S2"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "벤투스 S2 가격 알려줘"}],
        stream=False,
        user_id="u1",
        session_id="s2",
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert text == "확인한 결과를 안내드립니다."
    tool_names = [call["tool_name"] for call in metadata["tool_calls"]]
    assert "search_product_tool" in tool_names
    assert "get_final_price_tool" in tool_names
    assert not events


def test_price_side_question_does_not_force_preorder() -> None:
    store = MemoryStateStore()
    store.state = ConversationState()
    store.state.commerce_state.product.goods_no = "G000000000003"
    store.state.commerce_state.product.product_name = "아이온 에보"
    store.state.commerce_state.quantity = 4
    store.state.commerce_state.store.shop_id = "S001"
    store.state.commerce_state.schedule.date = "20260707"
    store.state.commerce_state.schedule.time = "10"
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRICE,
                    reason="side question about applied discount",
                    known_inputs={"goods_no": "G000000000003"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "적용된 할인이 뭐야?"}],
        stream=False,
        user_id="u1",
        session_id="side-price",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events == []
    assert [call["tool_name"] for call in metadata["tool_calls"]] == ["get_final_price_tool"]


def test_runtime_applies_request_slot_patch_to_state() -> None:
    store = MemoryStateStore()
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.QUICK_SHOPPING,
                    reason="explicit order draft continuation",
                    known_inputs={},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "주문 진행해줘"}],
        stream=False,
        user_id="u1",
        session_id="s3",
        slots={
            "goodsNo": "G000000000003",
            "productName": "아이온 에보",
            "ordQty": 4,
            "shopId": "S001",
            "shopName": "티스테이션 판교점",
            "requestedCalDay": "20260707",
            "rsvHour": "10",
            "paymentAmount": 500000,
        },
    )

    asyncio.run(runtime.run(request))

    assert store.state.commerce_state.product.goods_no == "G000000000003"
    assert store.state.commerce_state.quantity == 4
    assert store.state.commerce_state.store.shop_id == "S001"
    assert store.state.commerce_state.schedule.date == "20260707"
    assert store.state.commerce_state.price.final_price == 500000


def test_store_flow_emits_location_template() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(af=AgentFlow.STORE, reason="store lookup", known_inputs={"region": "판교"})
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "판교 근처 매장 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="s4",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "location"
    LocationDataEvent.model_validate(events[0])
    store = events[0]["data"]["stores"][0]
    assert store["nameAddress"] == "티스테이션 판교점"
    assert store["detailAddress"] == "경기 성남시 분당구 판교로 123"
    assert store["isAllMyT"] is True
    assert store["todayInstall"] is False
    assert store["tnaDelivery"] is False
    assert "전화: 031-000-0000" in store["description"]
    assert "평점: 4.8" in store["description"]
    assert "리뷰 27건" in store["description"]
    assert "서비스: 올마이티 | 온라인 장착 가능 | 얼라인먼트" in store["description"]
    assert metadata["tool_calls"][0]["tool_name"] == "search_stores_tool"


def test_store_attribute_searches_stores_and_marks_attribute_unconfirmed() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.STORE,
                    reason="store lookup with unverifiable staff condition",
                    known_inputs={"region": "서울", "store_attribute": "여자 직원 근무 여부"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "서울에 여자직원 있는 매장 있어?"}],
        stream=False,
        user_id="u1",
        session_id="store-attribute-guard",
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "location"
    assert "여자 직원 근무 여부" in events[0]["data"]["assistantResponse"]
    assert "포함되어 있지 않아요" in events[0]["data"]["assistantResponse"]
    assert text == "확인한 결과를 안내드립니다."
    assert metadata["tool_calls"][0]["tool_name"] == "search_stores_tool"


def test_favorite_store_lookup_uses_favorite_store_tool_and_location_template() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.STORE,
                    reason="favorite store lookup",
                    known_inputs={"store_lookup": "favorite_stores"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "내 단골매장 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="favorite-store",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "location"
    LocationDataEvent.model_validate(events[0])
    assert events[0]["data"]["assistantResponse"] == "단골매장이에요. 원하시는 매장을 선택해 주세요."
    assert events[0]["data"]["stores"][0]["nameAddress"] == "티스테이션 단골점"
    assert events[0]["data"]["isBookingFlow"] is False
    assert metadata["tool_calls"][0]["tool_name"] == "get_favorite_stores_tool"
    assert metadata["tool_calls"][0]["args"] == {}


def test_empty_favorite_store_lookup_emits_quickreply_without_generic_store_search() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.STORE,
                    reason="favorite store lookup",
                    known_inputs={"store_lookup": "favorite_stores"},
                )
            ]
        )),
        executor=EmptyFavoriteStoreExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "내 단골매장 어디야?"}],
        stream=False,
        user_id="u1",
        session_id="favorite-store-empty",
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "quickReply"
    assert events[0]["data"]["assistantResponse"] == "등록된 단골매장이 없어요. 매장 검색으로 안내해 드릴까요?"
    assert text == events[0]["data"]["assistantResponse"]
    assert [reply["label"] for reply in events[0]["data"]["quickReplies"]] == ["매장 검색", "아니요"]
    assert [call["tool_name"] for call in metadata["tool_calls"]] == ["get_favorite_stores_tool"]
    assert metadata["missing_inputs"] == []


def test_store_flow_with_active_product_and_quantity_is_booking_flow() -> None:
    store = MemoryStateStore()
    store.state.commerce_state.product.goods_no = "G000000000002"
    store.state.commerce_state.quantity = 4
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(af=AgentFlow.STORE, reason="store lookup", known_inputs={"region": "판교"})
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "판교 매장 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="booking-store-list",
    )

    _, events, _ = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "location"
    LocationDataEvent.model_validate(events[0])
    assert events[0]["data"]["isBookingFlow"] is True


def test_inventory_flow_requires_qty_before_tool_call() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.INVENTORY,
                    reason="inventory check",
                    known_inputs={"goods_no": "G000000000002", "region": "판교"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "판교 재고 확인해줘"}],
        stream=False,
        user_id="u1",
        session_id="s5",
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert text == "필요한 정보를 알려주세요."
    assert events == []
    assert metadata["missing_inputs"] == ["ord_qty"]
    assert metadata["tool_calls"] == []


def test_inventory_flow_with_required_inputs_emits_booking_location() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.INVENTORY,
                    reason="inventory check",
                    known_inputs={"goods_no": "G000000000002", "ord_qty": 4, "region": "판교"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "판교 장착 가능 매장 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="s6",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "location"
    LocationDataEvent.model_validate(events[0])
    assert events[0]["data"]["isBookingFlow"] is True
    assert metadata["tool_calls"][0]["tool_name"] == "transaction_store_preview_tool"


def test_quick_shopping_with_store_but_no_schedule_emits_datepick() -> None:
    store = MemoryStateStore()
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(af=AgentFlow.QUICK_SHOPPING, reason="order draft", known_inputs={})
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "주문 진행해줘"}],
        stream=False,
        user_id="u1",
        session_id="s7",
        slots={
            "goodsNo": "G000000000003",
            "productName": "아이온 에보",
            "ordQty": 4,
            "shopId": "S001",
            "shopName": "티스테이션 판교점",
        },
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "datepick"
    DatepickDataEvent.model_validate(events[0])
    assert events[0]["data"]["dates"][0]["availableTimes"] == [10, 11, 13]
    assert metadata["missing_inputs"] == ["schedule"]
    assert metadata["tool_calls"][0]["tool_name"] == "get_store_schedule_tool"


def test_quick_shopping_with_region_but_no_store_emits_booking_location() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.QUICK_SHOPPING,
                    reason="continue order with region",
                    known_inputs={
                        "goods_no": "G000000000003",
                        "product_name": "아이온 에보",
                        "ord_qty": 4,
                        "region": "판교",
                    },
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "판교에서 장착할래"}],
        stream=False,
        user_id="u1",
        session_id="purchase-region-store",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "location"
    LocationDataEvent.model_validate(events[0])
    assert events[0]["data"]["isBookingFlow"] is True
    assert metadata["missing_inputs"] == ["store"]
    assert metadata["tool_calls"][0]["tool_name"] == "transaction_store_preview_tool"


def test_store_selection_in_active_purchase_flow_emits_datepick_without_planner_choice() -> None:
    store = MemoryStateStore()
    store.state.commerce_state.product.goods_no = "G000000000003"
    store.state.commerce_state.product.product_name = "아이온 에보"
    store.state.commerce_state.quantity = 4
    store.state.commerce_state.store.region = "판교"
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(selected_afs=[])),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "이 매장 선택"}],
        stream=False,
        user_id="u1",
        session_id="store-selection-datepick",
        ui_action={
            "action_type": "select_store",
            "fills_slot": "shop_id",
            "slots": {
                "shop_id": "S001",
                "shop_name": "티스테이션 판교점",
            },
        },
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "datepick"
    DatepickDataEvent.model_validate(events[0])
    assert metadata["planner"]["selected_afs"][0]["af"] == "QuickShoppingAF"
    assert metadata["tool_calls"][0]["tool_name"] == "get_store_schedule_tool"
    assert store.state.commerce_state.store.shop_id == "S001"


def test_schedule_selection_in_active_purchase_flow_emits_preorder_without_planner_choice() -> None:
    store = MemoryStateStore()
    store.state.commerce_state.product.goods_no = "G000000000003"
    store.state.commerce_state.product.product_name = "아이온 에보"
    store.state.commerce_state.quantity = 4
    store.state.commerce_state.store.shop_id = "S001"
    store.state.commerce_state.store.shop_name = "티스테이션 판교점"
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(selected_afs=[])),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "7월 7일 10시"}],
        stream=False,
        user_id="u1",
        session_id="schedule-selection-preorder",
        ui_action={
            "action_type": "select_schedule",
            "slots": {
                "requestedCalDay": "20260707",
                "rsvHour": "10",
            },
        },
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "preOrder"
    PreOrderDataEvent.model_validate(events[0])
    assert events[0]["data"]["isReadyToOrder"] is True
    assert metadata["planner"]["selected_afs"][0]["af"] == "QuickShoppingAF"
    assert metadata["planner"]["resume_previous_flow"] is True
    assert metadata["tool_calls"][0]["tool_name"] == "get_final_price_tool"
    assert store.state.commerce_state.schedule.date == "20260707"
    assert store.state.commerce_state.schedule.time == "10"


def test_quick_shopping_complete_inputs_emits_preorder_without_side_effect() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(af=AgentFlow.QUICK_SHOPPING, reason="order draft", known_inputs={})
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "주문 진행해줘"}],
        stream=False,
        user_id="u1",
        session_id="s8",
        slots={
            "goodsNo": "G000000000003",
            "productName": "아이온 에보",
            "ordQty": 4,
            "shopId": "S001",
            "shopName": "티스테이션 판교점",
            "requestedCalDay": "20260707",
            "rsvHour": "10",
            "paymentAmount": 500000,
        },
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "preOrder"
    PreOrderDataEvent.model_validate(events[0])
    assert events[0]["data"]["isReadyToOrder"] is True
    assert all(call["tool_name"] not in {"quick_order_tool", "save_to_cart_tool"} for call in metadata["tool_calls"])


def test_coupon_list_uses_coupon_tool_and_voucher_template() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRICE,
                    reason="owned coupon lookup",
                    known_inputs={"account_lookup": "coupons"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "쿠폰 목록"}],
        stream=False,
        user_id="u1",
        session_id="coupon-list",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "voucher"
    VoucherDataEvent.model_validate(events[0])
    assert events[0]["data"]["vouchers"][0]["nameVoucher"] == "타이어 할인 쿠폰"
    assert metadata["planner"]["selected_afs"][0]["known_inputs"]["account_lookup"] == "coupons"
    assert metadata["tool_calls"][0]["tool_name"] == "get_my_coupons_tool"


def test_reservation_history_uses_reservation_tool_not_faq() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.ORDER_DELIVERY,
                    reason="reservation history lookup",
                    known_inputs={"account_lookup": "reservations"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "내 예약 내역 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="reservation-history",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events == []
    assert metadata["planner"]["selected_afs"][0]["af"] == "OrderDeliveryAF"
    assert metadata["tool_calls"][0]["tool_name"] == "get_my_reservations_tool"


def test_text_only_stream_emits_quickreply_data_for_fe_rendering() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.ORDER_DELIVERY,
                    reason="reservation history lookup",
                    known_inputs={"account_lookup": "reservations"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "내 예약 내역 보여줘"}],
        stream=True,
        user_id="u1",
        session_id="reservation-history-stream",
    )

    async def _collect() -> list[str]:
        return [chunk async for chunk in runtime.stream(request)]

    chunks = asyncio.run(_collect())
    body = "".join(chunks)
    data_events = []
    message_events = []
    for line in body.splitlines():
        if not line.startswith("data: {"):
            continue
        event = json.loads(line.removeprefix("data: "))
        if event.get("template") == "quickReply":
            data_events.append(event)
        if event.get("type") == "message":
            message_events.append(event)

    assert data_events[0]["data"]["assistantResponse"] == "확인한 결과를 안내드립니다."
    assert data_events[0]["data"]["metadata"]["source"] == "llm_first_text_response"
    assert message_events[0]["content"] == "확인한 결과를 안내드립니다."


def test_order_history_uses_order_tool_not_faq() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.ORDER_DELIVERY,
                    reason="order history lookup",
                    known_inputs={"account_lookup": "orders"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "내 주문내역 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="order-history",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events == []
    assert metadata["planner"]["selected_afs"][0]["af"] == "OrderDeliveryAF"
    assert metadata["planner"]["selected_afs"][0]["known_inputs"]["account_lookup"] == "orders"
    assert metadata["tool_calls"][0]["tool_name"] == "get_orders_of_user_tool"


def test_maintenance_history_uses_maintenance_tool_not_faq() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.ORDER_DELIVERY,
                    reason="maintenance history lookup",
                    known_inputs={"account_lookup": "maintenance_history"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "내 정비내역 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="maintenance-history",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events == []
    assert metadata["planner"]["selected_afs"][0]["af"] == "OrderDeliveryAF"
    assert metadata["planner"]["selected_afs"][0]["known_inputs"]["account_lookup"] == "maintenance_history"
    assert metadata["tool_calls"][0]["tool_name"] == "get_maintenance_history_tool"


def test_my_warranty_uses_warranty_tool_not_faq_search() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.FAQ,
                    reason="owned warranty lookup",
                    known_inputs={"account_lookup": "warranties"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "나의 워런티 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="my-warranty",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events == []
    assert metadata["planner"]["selected_afs"][0]["af"] == "FAQAF"
    assert metadata["planner"]["selected_afs"][0]["known_inputs"]["account_lookup"] == "warranties"
    assert metadata["tool_calls"][0]["tool_name"] == "get_my_warranties_tool"


def test_product_compatibility_uses_my_cars_tool_and_listcar_template() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_COMPATIBILITY,
                    reason="registered vehicle compatibility lookup",
                    known_inputs={},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "내 차에 맞는 타이어 보여줘"}],
        stream=False,
        user_id="M123",
        session_id="compat-my-cars",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "listCar"
    ListCarDataEvent.model_validate(events[0])
    assert events[0]["data"]["listCar"][0]["licensePlate"] == "12가3456"
    assert metadata["planner"]["selected_afs"][0]["af"] == "ProductCompatibilityAF"
    assert metadata["planner"]["selected_afs"][0]["known_inputs"]["mbr_no"] == "M123"
    assert metadata["tool_calls"][0]["tool_name"] == "get_my_cars_tool"


def test_product_compatibility_uses_owner_vehicle_lookup_when_plate_and_owner_known() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_COMPATIBILITY,
                    reason="vehicle lookup by plate and owner",
                    known_inputs={"car_no": "34나5678", "owner_nm": "홍길동"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "34나5678 홍길동 차량 타이어"}],
        stream=False,
        user_id="M123",
        session_id="compat-owner-vehicle",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "listCar"
    assert events[0]["data"]["metadata"][0]["tireSize"] == "215/55R17"
    assert metadata["tool_calls"][0]["tool_name"] == "get_user_vehicles_tool"
    assert metadata["tool_calls"][0]["args"] == {"car_no": "34나5678", "owner_nm": "홍길동"}


def test_product_compatibility_uses_car_model_group_search() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_COMPATIBILITY,
                    reason="car model lookup",
                    known_inputs={"car_model": "그랜저"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "그랜저 타이어 찾아줘"}],
        stream=False,
        user_id="M123",
        session_id="compat-car-model",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events == []
    assert metadata["tool_calls"][0]["tool_name"] == "search_car_model_groups_tool"
    assert metadata["tool_calls"][0]["args"] == {"keyword": "그랜저"}


def test_fallback_escalation_registers_side_effect_tool_as_blocked() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.FALLBACK_ESCALATION,
                    reason="explicit qna handoff",
                    known_inputs={"escalation_target": "qna"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "1:1 문의 연결해줘"}],
        stream=False,
        user_id="M123",
        session_id="fallback-escalation",
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "quickReply"
    assert events[0]["data"]["metadata"]["source"] == "llm_first_escalation_confirmation"
    assert "1:1 문의 작성 페이지로 이동할까요?" in events[0]["data"]["assistantResponse"]
    assert text == events[0]["data"]["assistantResponse"]
    assert metadata["planner"]["selected_afs"][0]["af"] == "FallbackEscalationAF"
    assert metadata["tool_calls"][0]["tool_name"] == "transfer_to_qna_tool"
    assert metadata["tool_calls"][0]["blocked"] is True
    assert metadata["missing_inputs"] == []


def test_qc_blocks_completion_claim_without_side_effect() -> None:
    decision = PlannerDecision(
        selected_afs=[SelectedAF(af=AgentFlow.QUICK_SHOPPING)],
    )
    from services.tstation.llm_first.models import FactBundle

    status, event = verify_response(
        "주문이 완료되었습니다.",
        FactBundle(planner=decision),
    )

    assert status == "completion_claim_blocked"
    assert event is not None
    assert event["template"] == "quickReply"
