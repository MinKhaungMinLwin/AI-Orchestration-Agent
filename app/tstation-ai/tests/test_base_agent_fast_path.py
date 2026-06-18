import json

from langchain_core.messages import AIMessage, ToolMessage

from services.tstation.agents.base_agent import (
    BaseAgent,
    _AssistantResponseStreamer,
    _build_product_warranty_quickreply_event,
    _is_explicit_vehicle_list_request,
    _normalize_qty_quick_replies,
    _owner_lookup_vehicle_recommendation_args,
    _resolve_registered_vehicle_match,
    _should_skip_support_search_product_fast_path,
    _should_defer_listcar_for_possessive_model_mismatch,
    _vehicle_owner_lookup_args_after_registered_mismatch,
)
from services.tstation.policies.response_decision import ResponseDecision, ResponseShape, TemplateName
from services.tstation.template_mapper import current_transaction_response_decision, current_user_text


def test_fast_path_allows_product_search_product_template():
    code_event = {
        "type": "data",
        "template": "product",
        "data": {"assistantResponse": "상품을 확인했어요."},
    }

    assert BaseAgent._is_fast_path_code_event("search_product_tool", code_event)


def test_support_agent_skips_search_product_fast_path() -> None:
    assert _should_skip_support_search_product_fast_path("Support Agent", "search_product_tool") is True
    assert _should_skip_support_search_product_fast_path("Discovery Agent", "search_product_tool") is False
    assert _should_skip_support_search_product_fast_path("Support Agent", "get_product_warranties_tool") is False


def test_product_warranty_tool_result_builds_support_quickreply() -> None:
    event = _build_product_warranty_quickreply_event(
        {
            "status": "success",
            "data": {
                "goods_no": "G000000309780",
                "ptrn_cd": "H462",
                "warranties": [
                    {"wrt_tp_cd": "10", "wrt_nm": "품질보증", "is_plus": False},
                    {"wrt_tp_cd": "20", "wrt_nm": "안심서비스", "is_plus": False},
                    {"wrt_tp_cd": "40", "wrt_nm": "코드절상 무상교환", "is_plus": False},
                ],
            },
        },
        [
            {
                "tool": "search_product_tool",
                "data": {
                    "status": "success",
                    "data": {
                        "items": [
                            {"goods_no": "G000000309780", "goods_nm": "벤투스 S2 AS"},
                        ],
                    },
                },
                "args": {"keyword": "벤투스 S2 AS"},
            },
        ],
    )

    assert event is not None
    assert event["template"] == "quickReply"
    data = event["data"]
    assert "벤투스 S2 AS에 적용 가능한 워런티" in data["assistantResponse"]
    assert "- 품질보증" in data["assistantResponse"]
    assert "- 안심서비스" in data["assistantResponse"]
    assert "- 코드절상 무상교환" in data["assistantResponse"]
    assert "사이즈가 아직 확인되지 않아" not in data["assistantResponse"]
    assert [chip["label"] for chip in data["quickReplies"]][:1] == ["나의 워런티 확인"]
    assert data["predictedDomains"] == ["SUPPORT"]


def test_fast_path_allows_transaction_preview_terminal_templates():
    for template in ("location", "datepick", "quickReply"):
        code_event = {
            "type": "data",
            "template": template,
            "data": {"assistantResponse": "장착 가능 정보를 확인했어요."},
        }

        assert BaseAgent._is_fast_path_code_event("transaction_store_preview_tool", code_event)


def test_fast_path_blocks_non_terminal_or_unlisted_tool():
    assert BaseAgent._is_fast_path_code_event(
        "get_store_inventory_tool",
        {"type": "data", "template": "location", "data": {}},
    )
    assert not BaseAgent._is_fast_path_code_event(
        "get_store_schedule_tool",
        {"type": "data", "template": "location", "data": {}},
    )


def test_code_template_events_do_not_duplicate_streamed_assistant_response():
    agent = object.__new__(BaseAgent)
    agent.name = "[TEST AGENT]"
    streamer = _AssistantResponseStreamer()
    streamed = streamer.feed('{"assistantResponse":"이미 보낸 답변"')
    assert streamed == "이미 보낸 답변"

    events = agent._code_template_events(
        {
            "type": "data",
            "template": "quickReply",
            "data": {"assistantResponse": "이미 보낸 답변"},
        },
        streamer,
        answering_emitted=True,
    )

    assert {"type": "token", "content": "이미 보낸 답변"} not in events
    assert events[-2]["template_source"] == "code_mapper"


def test_transaction_policy_blocks_heavy_tool_when_required_slot_missing():
    token = current_transaction_response_decision.set(
        ResponseDecision(
            response_shape=ResponseShape.CLARIFY,
            template=TemplateName.QUICK_REPLY,
            required_slots=("tire_size",),
            forbidden_behaviors=("order_summary_with_null_required_fields",),
            assistant_guidance="사이즈를 먼저 확인한다.",
        )
    )
    try:
        event = BaseAgent._transaction_policy_blocked_event("transaction_store_preview_tool")
    finally:
        current_transaction_response_decision.reset(token)

    assert event is not None
    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "transaction_policy_guard"
    assert event["data"]["requiredSlots"] == ["tire_size"]
    assert "사이즈 직접 입력" in {reply["label"] for reply in event["data"]["quickReplies"]}


def test_transaction_policy_blocks_store_list_tool_when_required_slot_missing():
    token = current_transaction_response_decision.set(
        ResponseDecision(
            response_shape=ResponseShape.CLARIFY,
            template=TemplateName.QUICK_REPLY,
            required_slots=("quantity",),
            forbidden_behaviors=("empty_location_card",),
            assistant_guidance="수량을 먼저 확인한다.",
        )
    )
    try:
        event = BaseAgent._transaction_policy_blocked_event("get_store_list_tool")
    finally:
        current_transaction_response_decision.reset(token)

    assert event is not None
    assert event["template"] == "quickReply"
    assert event["assistant_response_source"] == "transaction_policy_guard"
    assert event["data"]["requiredSlots"] == ["quantity"]
    assert [reply["label"] for reply in event["data"]["quickReplies"]] == ["1개", "2개", "3개", "4개"]


def test_transaction_policy_does_not_block_when_previous_tool_facts_have_goods_no():
    token = current_transaction_response_decision.set(
        ResponseDecision(
            response_shape=ResponseShape.CLARIFY,
            template=TemplateName.QUICK_REPLY,
            required_slots=("product",),
            forbidden_behaviors=("empty_location_card",),
            assistant_guidance="상품을 먼저 확인한다.",
        )
    )
    messages = [
        {
            "role": "assistant",
            "content": (
                '[Previous agent tool facts]\n'
                '[{"tool":"search_product_tool","data":{"status":"success","data":{"items":'
                '[{"goods_no":"G000000309783","goods_nm":"벤투스 S2 AS"}]}}}]'
            ),
        }
    ]
    try:
        event = BaseAgent._transaction_policy_blocked_event("get_store_list_tool", messages)
    finally:
        current_transaction_response_decision.reset(token)

    assert event is None


def test_qty_quickreply_normalizer_preserves_staggered_max_two_chips():
    payload = {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": (
                "앞바퀴 225/50R18 기준으로 몇 개 구매하실까요? "
                "이 차량은 앞/뒤 규격이 달라 현재 규격은 최대 2개까지 선택할 수 있어요."
            ),
            "quickReplies": [
                {"label": "1개", "domain": "TRANSACTION"},
                {"label": "2개", "domain": "TRANSACTION"},
            ],
        },
    }

    _normalize_qty_quick_replies(payload)

    assert [reply["label"] for reply in payload["data"]["quickReplies"]] == ["1개", "2개"]


def test_qty_quickreply_normalizer_rewrites_staggered_max_two_prompt_to_two_chips():
    payload = {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": (
                "앞바퀴 225/50R18 기준으로 몇 개 구매하실까요? "
                "이 차량은 앞/뒤 규격이 달라 현재 규격은 최대 2개까지 선택할 수 있어요."
            ),
            "quickReplies": [
                {"label": "1개", "domain": "TRANSACTION"},
                {"label": "2개", "domain": "TRANSACTION"},
                {"label": "3개", "domain": "TRANSACTION"},
                {"label": "4개", "domain": "TRANSACTION"},
            ],
        },
    }

    _normalize_qty_quick_replies(payload)

    assert [reply["label"] for reply in payload["data"]["quickReplies"]] == ["1개", "2개"]


def test_transaction_policy_does_not_block_when_no_required_slots():
    token = current_transaction_response_decision.set(
        ResponseDecision(
            response_shape=ResponseShape.DATE_PICK,
            template=TemplateName.DATE_PICK,
            required_slots=(),
            assistant_guidance="예약 슬롯을 제시한다.",
        )
    )
    try:
        event = BaseAgent._transaction_policy_blocked_event("transaction_store_preview_tool")
    finally:
        current_transaction_response_decision.reset(token)

    assert event is None


def test_code_template_events_replace_internal_policy_text():
    agent = BaseAgent.__new__(BaseAgent)
    agent.name = "test_agent"
    code_event = {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "상품명 검색 결과 기준으로 답하고 이전 추천 결과로 대체하지 않는다.",
            "quickReplies": [],
        },
    }

    events = agent._code_template_events(code_event, response_streamer=None, answering_emitted=False)

    message_event = next(event for event in events if event["type"] == "message")
    assert "상품명 검색 결과 기준으로 답하고" not in message_event["content"]
    assert "검색된 상품 정보를 기준으로 안내드릴게요" in message_event["content"]
    assert code_event["data"]["assistantResponse"] == message_event["content"]


def test_stream_processes_all_tool_messages_in_single_update_chunk():
    class _StubGraph:
        def stream(self, *_args, **_kwargs):
            yield (
                "updates",
                {
                    "model": {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "name": "get_products_recommendations_tool",
                                        "args": {"rcmd_type": "tstation", "brand_cd": "MC", "limit": 1},
                                        "id": "call_mc",
                                        "type": "tool_call",
                                    },
                                    {
                                        "name": "get_products_recommendations_tool",
                                        "args": {"rcmd_type": "tstation", "brand_cd": "CT", "limit": 1},
                                        "id": "call_ct",
                                        "type": "tool_call",
                                    },
                                ],
                            )
                        ]
                    }
                },
            )
            yield (
                "updates",
                {
                    "tools": {
                        "messages": [
                            ToolMessage(
                                content=json.dumps(
                                    {
                                        "status": "success",
                                        "data": {"items": [{"goods_no": "GMC", "goods_nm": "미쉐린 상품"}]},
                                    },
                                    ensure_ascii=False,
                                ),
                                name="get_products_recommendations_tool",
                                tool_call_id="call_mc",
                            ),
                            ToolMessage(
                                content=json.dumps(
                                    {
                                        "status": "success",
                                        "data": {"items": [{"goods_no": "GCT", "goods_nm": "콘티넨탈 상품"}]},
                                    },
                                    ensure_ascii=False,
                                ),
                                name="get_products_recommendations_tool",
                                tool_call_id="call_ct",
                            ),
                        ]
                    }
                },
            )

    agent = BaseAgent.__new__(BaseAgent)
    agent.name = "test_agent"
    agent._agent = _StubGraph()
    agent._tools = []
    agent._system_prompt = ""
    agent._system_prompt_chars = 0
    agent.OUTPUT_TEMPLATE = None

    events = list(agent.stream([{"role": "user", "content": "테스트"}], config={}))

    tool_events = [event for event in events if event.get("type") == "tool"]
    assert len(tool_events) == 2
    assert tool_events[0]["input"]["brand_cd"] == "MC"
    assert tool_events[1]["input"]["brand_cd"] == "CT"


def test_registered_vehicle_recommendation_resolves_explicit_plate():
    tool_result = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "205소4214",
                    "car_lnc_cd": "W049847",
                    "car_nm": "GV70 2.5T 가솔린 AWD A/T",
                    "car_model_det": "GV70 (1세대) (2021 - 2024)",
                    "tire_size_fr": "2355519",
                },
                {
                    "car_no": "33가3333",
                    "car_lnc_cd": "W063313",
                    "car_nm": "더 뉴 A-class(W177) F/L A 220 Hatchback A/T",
                    "tire_size_fr": "205/55R17",
                },
            ]
        },
    }

    row = _resolve_registered_vehicle_match(
        "get_my_cars_tool",
        tool_result,
        [{"role": "user", "content": "내 차 번호 205소 4214 알지? 맞는 타이어 보여줘."}],
    )

    assert row is not None
    assert row["car_no"] == "205소4214"
    assert row["car_lnc_cd"] == "W049847"
    assert row["tire_size_fr"] == "2355519"


def test_vehicle_size_retry_is_explicit_vehicle_list_request():
    assert _is_explicit_vehicle_list_request([
        {"role": "user", "content": "내차 사이즈로 다시"},
    ])
    assert _is_explicit_vehicle_list_request([
        {"role": "user", "content": "내 차 규격으로 다시"},
    ])


def test_registered_vehicle_recommendation_resolves_possessive_model_only():
    tool_result = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "205소4214",
                    "car_lnc_cd": "W049847",
                    "car_nm": "GV70 2.5T 가솔린 AWD A/T",
                    "car_model_det": "GV70 (1세대) (2021 - 2024)",
                    "tire_size_fr": "2355519",
                }
            ]
        },
    }

    row = _resolve_registered_vehicle_match(
        "get_my_cars_tool",
        tool_result,
        [{"role": "user", "content": "내 GV70에 맞는 타이어 추천해줘"}],
    )

    assert row is not None
    assert row["tire_size_fr"] == "2355519"


def test_registered_vehicle_recommendation_resolves_possessive_korean_model_alias():
    tool_result = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "29조3344",
                    "car_lnc_cd": "W036270",
                    "car_nm": "뉴 제타(6세대) 2.0 TDI A/T",
                    "car_model_det": "제타(6세대) (2011 - 2016)",
                    "tire_size_fr": "2254517",
                }
            ]
        },
    }

    row = _resolve_registered_vehicle_match(
        "get_my_cars_tool",
        tool_result,
        [{"role": "user", "content": "내 제타에 맞는 타이어 추천"}],
    )

    assert row is not None
    assert row["tire_size_fr"] == "2254517"
    assert row["car_lnc_cd"] == "W036270"


def test_registered_vehicle_recommendation_does_not_resolve_generic_model_mention():
    tool_result = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "205소4214",
                    "car_lnc_cd": "W049847",
                    "car_nm": "GV70 2.5T 가솔린 AWD A/T",
                    "car_model_det": "GV70 (1세대) (2021 - 2024)",
                    "tire_size_fr": "2355519",
                }
            ]
        },
    }

    row = _resolve_registered_vehicle_match(
        "get_my_cars_tool",
        tool_result,
        [{"role": "user", "content": "GV70에 맞는 타이어 추천해줘"}],
    )

    assert row is None


def test_possessive_model_mismatch_defers_listcar_fast_path():
    tool_result = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "29조3344",
                    "car_lnc_cd": "W036270",
                    "car_nm": "뉴 제타(6세대) 2.0 TDI A/T",
                    "car_model_det": "제타(6세대) (2011 - 2016)",
                    "tire_size_fr": "2254517",
                }
            ]
        },
    }

    should_defer = _should_defer_listcar_for_possessive_model_mismatch(
        "get_my_cars_tool",
        tool_result,
        [{"role": "user", "content": "내 차 다마스인데 하중 버틸 수 있어?"}],
    )

    assert should_defer is True


def test_possessive_model_match_keeps_registered_vehicle_flow():
    tool_result = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "29조3344",
                    "car_lnc_cd": "W036270",
                    "car_nm": "뉴 제타(6세대) 2.0 TDI A/T",
                    "car_model_det": "제타(6세대) (2011 - 2016)",
                    "tire_size_fr": "2254517",
                }
            ]
        },
    }

    should_defer = _should_defer_listcar_for_possessive_model_mismatch(
        "get_my_cars_tool",
        tool_result,
        [{"role": "user", "content": "내 차 제타에 맞는 타이어 추천"}],
    )

    assert should_defer is False


def test_registered_vehicle_recommendation_uses_current_user_text_only():
    tool_result = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "205소4214",
                    "car_lnc_cd": "W049847",
                    "car_nm": "GV70 2.5T 가솔린 AWD A/T",
                    "tire_size_fr": "2355519",
                },
                {
                    "car_no": "33가3333",
                    "car_lnc_cd": "W063313",
                    "car_nm": "A 220 Hatchback A/T",
                    "tire_size_fr": "205/55R17",
                },
            ]
        },
    }
    token = current_user_text.set("내 차 번호 205소4214 알지?\n33가3333에 맞는 타이어 보여줘")
    try:
        row = _resolve_registered_vehicle_match(
            "get_my_cars_tool",
            tool_result,
            [{"role": "user", "content": "33가3333에 맞는 타이어 보여줘"}],
        )
    finally:
        current_user_text.reset(token)

    assert row is not None
    assert row["tire_size_fr"] == "205/55R17"


def test_explicit_vehicle_list_request_detected() -> None:
    assert _is_explicit_vehicle_list_request([{"role": "user", "content": "내차목록"}]) is True
    assert _is_explicit_vehicle_list_request([{"role": "user", "content": "보유차량 확인"}]) is True
    assert _is_explicit_vehicle_list_request([{"role": "user", "content": "235가3456 겨울용 타이어 추천"}]) is False


def test_owner_lookup_args_when_plate_not_in_registered_cars() -> None:
    tool_result = {
        "status": "success",
        "data": {"items": [{"car_no": "29조3344", "tire_size_fr": "2254517"}]},
    }

    args = _vehicle_owner_lookup_args_after_registered_mismatch(
        "get_my_cars_tool",
        tool_result,
        [{"role": "user", "content": "26저7922 황지훈"}],
    )

    assert args == {"car_no": "26저7922", "owner_nm": "황지훈"}


def test_owner_lookup_args_skips_registered_plate_match() -> None:
    tool_result = {
        "status": "success",
        "data": {"items": [{"car_no": "26저7922", "tire_size_fr": "2254517"}]},
    }

    args = _vehicle_owner_lookup_args_after_registered_mismatch(
        "get_my_cars_tool",
        tool_result,
        [{"role": "user", "content": "26저7922 황지훈"}],
    )

    assert args is None


def test_owner_lookup_vehicle_recommendation_uses_car_code_directly() -> None:
    owner_result = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "26저7922",
                    "car_lnc_cd": "W011338",
                    "tire_size_fr": "225/55R17",
                }
            ]
        },
    }

    args = _owner_lookup_vehicle_recommendation_args(
        owner_result,
        [{"role": "user", "content": "26저7922 황지훈"}],
    )

    assert args == {
        "rcmd_type": "tstation",
        "limit": 3,
        "brand_cd": "HK",
        "car_lnc_cd": "W011338",
    }


def test_owner_lookup_vehicle_recommendation_maps_all_season_to_four_season_filter() -> None:
    owner_result = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "26저7922",
                    "car_lnc_cd": "W011338",
                    "tire_size_fr": "225/55R17",
                }
            ]
        },
    }

    args = _owner_lookup_vehicle_recommendation_args(
        owner_result,
        [{"role": "user", "content": "26저7922 황지훈 올시즌 타이어 추천"}],
    )

    assert args is not None
    assert args["rcmd_type"] == "all_weather"
    assert args["season_nm"] == "사계절"


def test_owner_lookup_vehicle_recommendation_maps_all_weather_separately() -> None:
    owner_result = {
        "status": "success",
        "data": {
            "items": [
                {
                    "car_no": "26저7922",
                    "car_lnc_cd": "W011338",
                    "tire_size_fr": "225/55R17",
                }
            ]
        },
    }

    args = _owner_lookup_vehicle_recommendation_args(
        owner_result,
        [{"role": "user", "content": "26저7922 황지훈 올웨더 타이어 추천"}],
    )

    assert args is not None
    assert args["rcmd_type"] == "all_weather"
    assert args["season_nm"] == "올웨더"
