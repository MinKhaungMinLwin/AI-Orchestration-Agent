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

import asyncio  # noqa: E402
import json  # noqa: E402

from langchain_core.messages import AIMessageChunk  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from services.tstation.chat_v3 import executor as executor_module  # noqa: E402
from services.tstation.chat_v3 import llm as llm_module  # noqa: E402
from services.tstation.chat_v3.executor import (  # noqa: E402
    ToolLoopExecutor,
    _model_visible_tool_output,
    _normalize_business_failure,
    _output_flow_status,
)
from services.tstation.chat_v3.memory import context_items_from_tool_calls, tool_context_block  # noqa: E402
from services.tstation.chat_v3.tools.discovery import DISCOVERY_TOOLS  # noqa: E402
from services.tstation.chat_v3.tools import tools_for_domain  # noqa: E402
from services.tstation.agents.b_discovery_agent import tools as discovery_tools  # noqa: E402


def test_v3_model_tier_uses_specific_setting_and_legacy_fallback(monkeypatch) -> None:
    monkeypatch.setattr(llm_module.settings, "AI_MODEL", "legacy-main")
    monkeypatch.setattr(llm_module.settings, "AI_MODEL_TOOL_SELECTOR", "gpt-5.6-luna")

    assert llm_module._configured_model("AI_MODEL_TOOL_SELECTOR") == "gpt-5.6-luna"

    monkeypatch.setattr(llm_module.settings, "AI_MODEL_TOOL_SELECTOR", "")

    assert llm_module._configured_model("AI_MODEL_TOOL_SELECTOR") == "legacy-main"


def test_executor_contract_rejects_missing_required_tool_argument() -> None:
    class SearchArgs(BaseModel):
        query: str

    class FakeSearchTool:
        name = "search_product_tool"

        @staticmethod
        def get_input_schema():
            return SearchArgs

    executor = ToolLoopExecutor([], [FakeSearchTool()], {})

    denial = executor._tool_call_denial({"name": "search_product_tool", "args": {}, "id": "missing-query"})

    assert denial == "invalid_tool_arguments:search_product_tool:query"


def test_v3_discovery_exposes_the_two_step_car_model_size_lookup() -> None:
    """A named car model must be resolvable to its real tire_size_fr/re.

    These two tools are the only path to that: search_car_model_groups_tool yields a
    car_model_det, get_car_trims_tool turns it into per-trim front/rear sizes. With step 1
    unbound the chain was dead, so the model guessed the size (215/55R17 for a BMW 520d).
    """
    tool_names = {tool.name for tool in DISCOVERY_TOOLS}

    assert "search_car_model_groups_tool" in tool_names
    assert "get_car_trims_tool" in tool_names
    assert "get_products_recommendations_tool" in tool_names


def test_v3_transaction_tools_can_resolve_product_goods_no() -> None:
    tool_names = {tool.name for tool in tools_for_domain("TRANSACTION")}

    assert "search_product_tool" in tool_names


def test_inventory_tool_output_is_redacted_only_for_model_visible_observation() -> None:
    output = '{"status":"success","data":{"todayShopArray":[{"shopId":"F00071","stock_qty":8}]}}'

    visible = _model_visible_tool_output("get_store_inventory_tool", output)

    assert output != visible
    assert "status" not in visible
    assert "8" not in visible
    assert "available_quantity_redacted" in visible


def test_discovery_success_response_removes_origin_from_all_nested_data() -> None:
    response = discovery_tools._success_response(
        200,
        {
            "goods_nm": "벤투스 에어 S",
            "orpl_nm": "한국",
            "variants": [
                {
                    "goods_no": "G1",
                    "ORPL_NM": "한국",
                    "season_nm": "사계절",
                    "cheapest_final_prc": 210_000,
                    "cheapest_total_discount": 10_000,
                    "cheapest_applied_coupons": [{"cpn_nm": "보유 쿠폰"}],
                }
            ],
        },
    )

    serialized = json.dumps(response, ensure_ascii=False)

    assert "orpl_nm" not in serialized.lower()
    assert "cheapest_" not in serialized
    assert response["data"]["goods_nm"] == "벤투스 에어 S"
    assert response["data"]["variants"] == [{"goods_no": "G1", "season_nm": "사계절"}]


def test_product_item_whitelist_does_not_restore_origin() -> None:
    slim = discovery_tools._slim_product_item(
        {"goods_no": "G1", "goods_nm": "벤투스 S2 AS", "orpl_nm": "한국", "season_nm": "사계절"}
    )

    assert slim == {"goods_no": "G1", "goods_nm": "벤투스 S2 AS", "season_nm": "사계절"}


def test_price_filter_uses_general_benefit_price_before_personalized_price() -> None:
    item = {
        "sale_prc": 300_000,
        "extra_fvr_sale_prc": 220_000,
        "cheapest_final_prc": 280_000,
    }

    assert discovery_tools._price_filter_basis(item) == 220_000


def test_tool_memory_removes_personalized_prices_for_new_and_legacy_context() -> None:
    tool_calls = [
        {
            "name": "get_final_price_tool",
            "args": {"goods_no": "G1"},
            "output": json.dumps(
                {
                    "data": {
                        "extra_fvr_sale_prc": 220_000,
                        "cheapest_final_prc": 280_000,
                        "cheapest_applied_coupons": [{"cpn_nm": "보유 쿠폰"}],
                    }
                }
            ),
        }
    ]

    items = context_items_from_tool_calls(tool_calls)
    new_context = json.dumps(items, ensure_ascii=False)
    legacy_context = tool_context_block(
        [
            {
                "tool": "get_final_price_tool",
                "input": {"goods_no": "G1"},
                "data": {
                    "extra_fvr_sale_prc": 220_000,
                    "cheapest_final_prc": 280_000,
                },
            }
        ]
    )

    assert "extra_fvr_sale_prc" in new_context
    assert "cheapest_" not in new_context
    assert legacy_context is not None
    assert "extra_fvr_sale_prc" in legacy_context
    assert "cheapest_" not in legacy_context


def test_recommendation_output_uses_general_benefit_price_contract_before_truncation() -> None:
    items = []
    for index in range(3):
        items.append(
            {
                "goods_no": f"G{index}",
                "goods_nm": f"상품 {index}",
                "tire_size_1": "255/35R19",
                "sale_prc": 369_600 + index,
                "extra_fvr_sale_prc": 277_400 + index,
                "cheapest_final_prc": 351_100 + index,
                "cheapest_total_discount": 18_500,
                "cheapest_applied_coupons": [
                    {"stage": "payment", "cpn_nm": "마케팅동의 5% 결제쿠폰", "discount_amt": 18_500}
                ],
                "pc_prod_remark_desc": "<html>" + ("상세설명" * 3000) + "</html>",
                "pc_prod_tech_desc": "기술설명" * 3000,
            }
        )
    output = json.dumps({"status": "success", "data": {"total": 3, "items": items}}, ensure_ascii=False)

    visible = _model_visible_tool_output("get_products_recommendations_tool", output)
    parsed = json.loads(visible)

    assert len(visible) < 4000
    assert [item["extra_fvr_sale_prc"] for item in parsed["data"]["items"]] == [277400, 277401, 277402]
    assert all("cheapest_final_prc" not in item for item in parsed["data"]["items"])
    assert all("cheapest_applied_coupons" not in item for item in parsed["data"]["items"])
    assert parsed["data"]["price_contract"] == {
        "sale_prc": "기본가",
        "extra_fvr_sale_prc": "혜택가",
        "instruction": "상품 가격은 혜택가를 우선하고, 없으면 기본가를 표시",
    }
    assert "pc_prod_remark_desc" not in visible
    assert "pc_prod_tech_desc" not in visible


def test_recommendation_output_keeps_car_knd_nm_so_ev_only_tires_are_visible() -> None:
    """Without 차종 분류명 the model cannot tell an EV-only tire from a passenger one, and has
    recommended iON (전기차 전용) for a petrol Carnival."""
    output = json.dumps(
        {
            "status": "success",
            "data": {"total": 1, "items": [{"goods_no": "G1", "goods_nm": "아이온", "car_knd_nm": "전기차"}]},
        },
        ensure_ascii=False,
    )

    visible = _model_visible_tool_output("get_products_recommendations_tool", output)

    assert json.loads(visible)["data"]["items"][0]["car_knd_nm"] == "전기차"


def test_recommendation_output_keeps_the_relaxed_vehicle_type_warning() -> None:
    """The tool drops the vehicle_type filter when it would return nothing and says so in
    recommendation_fallback — the model must see that, or it presents van tires as a fit."""
    fallback = {
        "requested_vehicle_type": "truck_van",
        "applied_vehicle_type": None,
        "assistant_response_hint": "요청하신 차량 타입 전용 상품이 확인되지 않아 차량 타입 필터 없이 추천했습니다.",
    }
    output = json.dumps(
        {
            "status": "success",
            "data": {"total": 1, "items": [{"goods_no": "G1"}], "recommendation_fallback": fallback},
        },
        ensure_ascii=False,
    )

    visible = _model_visible_tool_output("get_products_recommendations_tool", output)

    assert json.loads(visible)["data"]["recommendation_fallback"] == fallback


def test_final_price_output_hides_personalized_price_fields_from_model() -> None:
    output = json.dumps(
        {
            "status": "success",
            "data": {
                "sale_prc": 200_000,
                "extra_fvr_sale_prc": 179_700,
                "cheapest_final_prc": 195_000,
                "cheapest_total_discount": 5_000,
                "cheapest_applied_coupons": [{"cpn_nm": "보유 쿠폰"}],
                "cheapest_goods_no": "G1",
            },
        },
        ensure_ascii=False,
    )

    visible = _model_visible_tool_output("get_final_price_tool", output)

    assert "extra_fvr_sale_prc" in visible
    assert "cheapest_" not in visible


def test_cart_result_false_is_normalized_to_error() -> None:
    output = json.dumps(
        {"status": "success", "http_status": 200, "data": {"result": False, "message": "이미 장바구니에 담겨있는 상품입니다."}},
        ensure_ascii=False,
    )

    normalized = _normalize_business_failure("save_to_cart_tool", output)
    parsed = json.loads(normalized)

    assert parsed["status"] == "error"
    assert parsed["error"] == "cart_add_failed"
    assert parsed["data"]["message"] == "이미 장바구니에 담겨있는 상품입니다."
    assert _output_flow_status(normalized) == "error"


def test_cart_result_true_stays_success() -> None:
    output = json.dumps({"status": "success", "http_status": 200, "data": {"result": True}})

    assert _normalize_business_failure("save_to_cart_tool", output) == output
    assert _output_flow_status(output) == "success"


def test_business_failure_normalization_only_applies_to_cart_tool() -> None:
    output = json.dumps({"status": "success", "data": {"result": False}})

    assert _normalize_business_failure("get_final_price_tool", output) == output


def test_executor_records_cart_result_false_as_error() -> None:
    asyncio.run(_assert_executor_records_cart_result_false_as_error())


def test_executor_stops_between_vehicle_lookup_and_next_tool(monkeypatch) -> None:
    asyncio.run(_assert_executor_stops_between_vehicle_lookup_and_next_tool(monkeypatch))


async def _assert_executor_stops_between_vehicle_lookup_and_next_tool(monkeypatch) -> None:
    executed = []

    class FakeLLM:
        def bind_tools(self, tools):
            return self

        async def astream(self, messages, config=None):
            yield AIMessageChunk(
                content="",
                tool_calls=[
                    {"name": "get_my_cars_tool", "args": {}, "id": "cars"},
                    {"name": "get_products_recommendations_tool", "args": {}, "id": "recommend"},
                ],
            )

    class FakeTool:
        def __init__(self, name):
            self.name = name

        async def ainvoke(self, args, config=None):
            executed.append(self.name)
            return {"status": "success", "data": {}}

    monkeypatch.setattr(executor_module, "get_tool_selector_llm", lambda: FakeLLM())
    executor = ToolLoopExecutor(
        [],
        [FakeTool("get_my_cars_tool"), FakeTool("get_products_recommendations_tool")],
        {},
        stop_after_tool=lambda calls: len(calls) == 1,
    )

    events = [event async for event in executor.stream()]

    assert events
    assert executed == ["get_my_cars_tool"]
    assert [call["name"] for call in executor.tool_calls] == ["get_my_cars_tool"]
    assert executor.stopped_after_tool is True


def test_executor_retries_rejected_tool_selection_once_with_fallback(monkeypatch) -> None:
    asyncio.run(_assert_executor_retries_rejected_tool_selection_once_with_fallback(monkeypatch))


async def _assert_executor_retries_rejected_tool_selection_once_with_fallback(monkeypatch) -> None:
    invoked = []

    class FakeLLM:
        def __init__(self, chunk):
            self.chunk = chunk

        def bind_tools(self, tools):
            return self

        async def astream(self, messages, config=None):
            yield self.chunk

    class FakeTool:
        def __init__(self, name):
            self.name = name

        async def ainvoke(self, args, config=None):
            invoked.append((self.name, args))
            return {"status": "success", "data": {"items": []}}

    selector = FakeLLM(
        AIMessageChunk(
            content="",
            tool_calls=[{"name": "save_to_cart_tool", "args": {"goods_no": "G1"}, "id": "bad"}],
        )
    )
    fallback = FakeLLM(
        AIMessageChunk(
            content="",
            tool_calls=[{"name": "search_product_tool", "args": {"query": "벤투스"}, "id": "good"}],
        )
    )
    composer = FakeLLM(AIMessageChunk(content="검색 결과를 확인했어요."))
    monkeypatch.setattr(executor_module, "get_tool_selector_llm", lambda: selector)
    monkeypatch.setattr(executor_module, "get_fallback_llm", lambda: fallback)
    monkeypatch.setattr(executor_module, "get_composer_llm", lambda: composer)

    executor = ToolLoopExecutor(
        [],
        [FakeTool("save_to_cart_tool"), FakeTool("search_product_tool")],
        {},
        tool_call_guard=lambda call: "cart_write_not_confirmed" if call.get("name") == "save_to_cart_tool" else None,
    )
    events = [event async for event in executor.stream()]

    assert events
    assert invoked == [("search_product_tool", {"query": "벤투스"})]
    assert executor.final_text == "검색 결과를 확인했어요."
    assert executor.selector_fallback_used is True
    assert executor.selector_fallback_reason == "policy_guard:cart_write_not_confirmed"
    assert [call["name"] for call in executor.tool_calls] == ["search_product_tool"]


def test_executor_recomposes_with_fallback_model(monkeypatch) -> None:
    asyncio.run(_assert_executor_recomposes_with_fallback_model(monkeypatch))


async def _assert_executor_recomposes_with_fallback_model(monkeypatch) -> None:
    class FakeFallbackLLM:
        async def astream(self, messages, config=None):
            assert "failed deterministic grounding checks" in messages[-1].content
            yield AIMessageChunk(content="도구 결과에 맞춰 수정한 답변")

    monkeypatch.setattr(executor_module, "get_fallback_llm", lambda: FakeFallbackLLM())
    executor = ToolLoopExecutor([], [], {})

    answer = await executor.recompose_with_fallback("qc_det_failed:price=100")

    assert answer == "도구 결과에 맞춰 수정한 답변"
    assert executor.composer_fallback_used is True


async def _assert_executor_records_cart_result_false_as_error() -> None:
    class FakeCartTool:
        name = "save_to_cart_tool"

        async def ainvoke(self, args, config=None):
            return {"status": "success", "http_status": 200, "data": {"result": False, "message": "이미 장바구니에 담겨있는 상품입니다."}}

    executor = ToolLoopExecutor([], [FakeCartTool()], {})
    events = []
    async for event in executor._run_tool({"name": "save_to_cart_tool", "args": {"goods_no": "G1", "ord_qty": 2}, "id": "c1"}):
        events.append(event)

    recorded = json.loads(executor.tool_calls[0]["output"])
    assert recorded["status"] == "error"
    assert any('"agent_flow"' in event and '"error"' in event for event in events)
