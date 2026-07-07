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
from services.tstation.llm_first.executor import AFExecutor  # noqa: E402
from services.tstation.llm_first.models import AgentFlow, ConversationState, PlannerDecision, ProductState, SelectedAF, StructuredPlannerDecision, ToolCallRecord  # noqa: E402
from services.tstation.llm_first.planner import LeadingAgentPlanner  # noqa: E402
from services.tstation.llm_first.qc import verify_response  # noqa: E402
from services.tstation.llm_first.runtime import LLMFirstRuntime  # noqa: E402
from services.tstation.llm_first.state import LLMFirstStateStore, apply_state_rules  # noqa: E402
from services.tstation.llm_first.tools import invoke_tool  # noqa: E402
from services.tstation.agents.templates.schemas import DatepickDataEvent, LocationDataEvent, PreOrderDataEvent, ProductDataEvent  # noqa: E402


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
                            "extra_fvr_sale_prc": 200000,
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
        elif tool_name == "search_stores_tool":
            result = {
                "status": "success",
                "data": {
                    "stores": [
                        {
                            "shop_id": "S001",
                            "shop_nm": "티스테이션 판교점",
                            "address": "경기 성남시 분당구 판교",
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
        else:
            result = {"status": "success", "data": []}
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
    assert product_events[0]["data"]["products"][0]["tires"] == "245/45R19"
    assert product_events[0]["data"]["products"][0]["rate"] == 0
    assert product_events[0]["data"]["metadata"][0]["goodsId"] == "G000000000001"
    assert token_events[0]["content"] == "확인한 결과를 안내드립니다."
    assert "data: [DONE]" in body


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
    assert events[0]["data"]["stores"][0]["nameAddress"] == "티스테이션 판교점"
    assert metadata["tool_calls"][0]["tool_name"] == "search_stores_tool"


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
