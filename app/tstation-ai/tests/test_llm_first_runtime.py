from __future__ import annotations

import asyncio
import datetime
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
from services.tstation.llm_first.planner import LeadingAgentPlanner, extract_known_inputs  # noqa: E402
from services.tstation.llm_first.qc import verify_response  # noqa: E402
from services.tstation.llm_first.runtime import LLMFirstRuntime  # noqa: E402
from services.tstation.llm_first import schedule_validation as schedule_validation_module  # noqa: E402
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
                    "llm_first_benefit_event_deal_list",
                    "llm_first_event_applicable_products",
                    "llm_first_benefit_applicable_products",
                    "llm_first_order_complete",
                    "llm_first_cart_complete",
                    "llm_first_unsupported_region",
                }:
                    return data["assistantResponse"]
        return "확인한 결과를 안내드립니다."


class StructuredFakeLLM:
    def __init__(self, decision):
        self.decision = decision

    async def ainvoke(self, messages, config=None):
        return self.decision


class FakeLLM:
    def __init__(self, decision: PlannerDecision):
        self.decision = decision

    def with_structured_output(self, schema, strict=True):
        assert strict is True
        if schema is StructuredPlannerDecision:
            return StructuredFakeLLM(self.decision)
        raise AssertionError(f"unexpected schema: {schema}")


class CapturingStructuredPlannerLLM:
    def __init__(self, decision: PlannerDecision):
        self.decision = decision
        self.messages = None
        self.config = None

    async def ainvoke(self, messages, config=None):
        self.messages = messages
        self.config = config
        return self.decision


class CapturingPlannerLLM:
    def __init__(self, decision: PlannerDecision):
        self.structured = CapturingStructuredPlannerLLM(decision)

    def with_structured_output(self, schema, strict=True):
        assert strict is True
        if schema is StructuredPlannerDecision:
            return self.structured
        raise AssertionError(f"unexpected schema: {schema}")


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
    async def _call(self, bundle, af, tool_name, args, *, allow_side_effect=False):
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
        elif tool_name == "get_benefit_event_deal_list_tool":
            result = {
                "status": "success",
                "data": {
                    "events": {
                        "items": [
                            {
                                "evt_nm": "한국타이어 페스타",
                                "evt_strt_dtime": "2026-06-01 00:00:00",
                                "evt_end_dtime": "2026-06-30 23:59:59",
                                "evt_url_addr": "https://wwwqa.tstation.com/promotion/event/festa",
                            }
                        ]
                    },
                    "deals": {
                        "items": [
                            {
                                "deal_nm": "여름맞이 기획전",
                                "deal_strt_dtime": "2026-06-01 00:00:00",
                                "deal_end_dtime": "2026-07-15 23:59:59",
                                "dtl_conts_url_addr": "https://wwwqa.tstation.com/promotion/deal/summer",
                            }
                        ]
                    },
                },
            }
        elif tool_name == "get_event_applicable_products_tool":
            result = {
                "status": "success",
                "data": {
                    "events": [
                        {
                            "evt_nm": "한국타이어 페스타",
                            "items": [
                                {"goods_nm": "키너지 EX"},
                                {"goods_nm": "벤투스 S2 AS"},
                            ],
                        }
                    ]
                },
            }
        elif tool_name == "search_benefit_applicable_products_tool":
            result = {
                "status": "success",
                "data": {
                    "query": args.get("query"),
                    "matches": [
                        {
                            "source_type": "event",
                            "source_name": "한국타이어 페스타",
                            "products": [
                                {"goods_nm": "키너지 EX"},
                                {"goods_nm": "벤투스 S2 AS"},
                            ],
                            "stores": [
                                {"shop_nm": "티스테이션 판교점"},
                            ],
                        }
                    ],
                },
            }
        elif tool_name == "search_stores_tool":
            if args.get("place_query") in {"우즈벡", "사우디", "평양"}:
                result = {
                    "status": "success",
                    "data": {
                        "stores": [],
                        "search": {
                            "source": "place_fallback_blocked",
                            "reason": "not_domestic_search_area",
                        },
                    },
                }
            else:
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
        elif tool_name == "search_stores_complex_tool":
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
                    ],
                    "search": {
                        "source": "complex",
                        "filters": {
                            "cal_days": args.get("cal_days"),
                            "open_only": args.get("open_only"),
                            "time_after_hour": args.get("time_after_hour"),
                        },
                    },
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
            if args.get("region_code") in {"우즈벡", "사우디", "평양"}:
                result = {
                    "status": "success",
                    "data": {
                        "stores": [],
                        "search": {
                            "source": "place_fallback_blocked",
                            "reason": "not_domestic_search_area",
                        },
                    },
                }
            else:
                result = {
                    "status": "success",
                    "data": {
                        "schedule": {
                            "tier": "in_store_only",
                            "stores": [
                                {
                                    "shop_id": "S002",
                                    "shop_nm": "티스테이션 분당점",
                                    "mode": "in_store_only",
                                    "slots": [
                                        {"cal_day": "20260707", "tm": "1000"},
                                        {"cal_day": "20260707", "tm": "1100"},
                                    ],
                                }
                            ],
                        },
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
            if args.get("mode") == "in_store_only":
                result = {
                    "status": "success",
                    "data": {
                        "shop_id": args["shop_id"],
                        "shop_nm": "티스테이션 분당점",
                        "mode": "in_store_only",
                        "slots": [
                            {"cal_day": "20260707", "tm": "1000"},
                            {"cal_day": "20260707", "tm": "1100"},
                            {"cal_day": "20260707", "tm": "1200"},
                            {"cal_day": "20260708", "tm": "0900"},
                        ],
                    },
                }
            else:
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
        elif tool_name == "quick_order_tool":
            if not allow_side_effect:
                result = None
                bundle.tool_calls.append(ToolCallRecord(
                    af=af,
                    tool_name=tool_name,
                    args=args,
                    blocked=True,
                    reason=f"side-effect tool blocked in LLM-first MVP: {tool_name}",
                ))
                return result
            result = {
                "status": "success",
                "http_status": 200,
                "data": {
                    "result": True,
                    "message": "",
                    "drtPurYn": "Y",
                    "data": {
                        "cartNoArrStr": "15722",
                        "goodsInfoArrStr": f"{args['goods_no']}|{args['ord_qty']}|Y",
                    },
                },
            }
        elif tool_name == "save_to_cart_tool":
            if not allow_side_effect:
                result = None
                bundle.tool_calls.append(ToolCallRecord(
                    af=af,
                    tool_name=tool_name,
                    args=args,
                    blocked=True,
                    reason=f"side-effect tool blocked in LLM-first MVP: {tool_name}",
                ))
                return result
            result = {
                "status": "success",
                "http_status": 200,
                "data": {
                    "result": True,
                    "message": "",
                    "drtPurYn": "N",
                    "data": {
                        "cartNoArrStr": "15766",
                        "goodsInfoArrStr": f"{args['goods_no']}|{args['ord_qty']}|Y",
                    },
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
                        },
                        {
                            "car_no": "34나5678",
                            "car_maker": "제네시스",
                            "car_nm": "GV70",
                            "car_model_det": "GV70 2.5T",
                            "car_lnc_cd": "CAR003",
                            "tire_size_fr": "235/55R19",
                            "tire_size_re": "235/55R19",
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


class AlternativeFakeExecutor(FakeExecutor):
    async def _call(self, bundle, af, tool_name, args, *, allow_side_effect=False):
        if tool_name == "get_products_recommendations_tool":
            result = {
                "status": "success",
                "data": {
                    "items": [
                        {
                            "goods_no": "G000000000003",
                            "goods_nm": "아이온 에보",
                            "tire_size_1": "235/55R19",
                            "brand_nm": "한국타이어",
                            "sale_prc": 250000,
                            "extra_fvr_sale_prc": 210000,
                        },
                        {
                            "goods_no": "G000000000005",
                            "goods_nm": "다이나프로 HPX",
                            "tire_size_1": "235/55R19",
                            "brand_nm": "한국타이어",
                            "sale_prc": 230000,
                            "extra_fvr_sale_prc": 190000,
                        },
                    ]
                },
            }
            bundle.tool_calls.append(ToolCallRecord(af=af, tool_name=tool_name, args=args, result=result))
            bundle.facts[tool_name] = result
            return result
        if tool_name == "transaction_store_preview_tool":
            result = {
                "status": "success",
                "data": {
                    "stores": [
                        {
                            "shop_id": "S001",
                            "shop_nm": "티스테이션 판교점",
                            "address": "경기 성남시 분당구 판교로",
                        },
                        {
                            "shop_id": "S002",
                            "shop_nm": "티스테이션 분당점",
                            "address": "경기 성남시 분당구",
                        },
                    ]
                },
            }
            bundle.tool_calls.append(ToolCallRecord(af=af, tool_name=tool_name, args=args, result=result))
            bundle.facts[tool_name] = result
            return result
        return await super()._call(bundle, af, tool_name, args, allow_side_effect=allow_side_effect)


class EmptyFavoriteStoreExecutor(FakeExecutor):
    async def _call(self, bundle, af, tool_name, args, *, allow_side_effect=False):
        if tool_name != "get_favorite_stores_tool":
            return await super()._call(bundle, af, tool_name, args, allow_side_effect=allow_side_effect)
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
        "vehicle_recommendation",
        "vehicle_type",
        "recommendation_type",
        "recommendation_source",
        "benefit_lookup",
        "benefit_query",
        "evt_no_list",
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


def test_planner_prompt_routes_unsupported_oe_part_number_queries_to_faq() -> None:
    llm = CapturingPlannerLLM(PlannerDecision(
        selected_afs=[
            SelectedAF(
                af=AgentFlow.FAQ,
                reason="unsupported oe part number lookup should be answered as faq limitation",
                known_inputs={},
                missing_inputs=[],
            )
        ],
        conversation_goal="answer_unsupported_oe_lookup",
    ))
    planner = LeadingAgentPlanner(llm)

    decision = asyncio.run(planner.plan(
        user_text="벤츠 E클래스 W212 순정 출고 타이어(OE) 품번이 뭐야?",
        state=ConversationState(),
    ))

    assert decision.selected_afs[0].af == AgentFlow.FAQ
    assert llm.structured.messages is not None
    system_prompt = llm.structured.messages[0].content
    assert "select FAQAF instead of ProductDescriptionAF" in system_prompt
    assert "OE/factory tire part number" in system_prompt


def test_planner_purchase_pivot_classifier_routes_reservation_window_question_to_faq() -> None:
    state = ConversationState()
    state.commerce_state.product.goods_no = "G000000317682"
    state.commerce_state.product.product_name = "다이나프로 HPX 235/55R19"
    state.commerce_state.product.tire_size = "235/55R19"
    state.commerce_state.quantity = 4
    state.commerce_state.store.shop_id = "F00721"
    state.commerce_state.store.shop_name = "티스테이션 판교점"
    llm = CapturingPlannerLLM(PlannerDecision(
        selected_afs=[
            SelectedAF(
                af=AgentFlow.FAQ,
                reason="general reservation-window policy question during active purchase",
                known_inputs={},
                missing_inputs=[],
            )
        ],
        resume_previous_flow=False,
    ))
    planner = LeadingAgentPlanner(llm)

    decision = asyncio.run(planner.plan(
        user_text="아니 이 매장을 말하는게 아니고 예약 가능 최대 몇 주 까지 늦게 예약할 수 있어?",
        state=state,
    ))

    assert decision.selected_afs[0].af == AgentFlow.FAQ
    assert decision.resume_previous_flow is False
    assert llm.structured.messages is not None
    assert "If the user asks a separate question while purchase is waiting" in llm.structured.messages[0].content


def test_planner_purchase_pivot_classifier_routes_price_question_to_price_af() -> None:
    state = ConversationState()
    state.commerce_state.product.goods_no = "G000000317682"
    state.commerce_state.product.product_name = "다이나프로 HPX 235/55R19"
    state.commerce_state.product.tire_size = "235/55R19"
    llm = CapturingPlannerLLM(PlannerDecision(
        selected_afs=[
            SelectedAF(
                af=AgentFlow.PRICE,
                reason="price question should pivot away from purchase slot filling",
                known_inputs={},
                missing_inputs=[],
            )
        ],
        resume_previous_flow=False,
    ))
    planner = LeadingAgentPlanner(llm)

    decision = asyncio.run(planner.plan(
        user_text="쿠폰 적용하면 얼마야?",
        state=state,
    ))

    assert decision.selected_afs[0].af == AgentFlow.PRICE
    assert decision.resume_previous_flow is False
    assert llm.structured.messages is not None
    assert "product_applicable_benefits" in llm.structured.messages[0].content


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
    assert product["description"] == "정숙/승차감 중심 성향이에요. 평점 4.5점, 리뷰 12건이에요."
    assert product_events[0]["data"]["isBookingFlow"] is True
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
    assert "4.5점 / 리뷰 12건 / 대표 리뷰: 승차감이 부드럽고 일상 주행에서 소음이 적다는 의견이 많아요." in events[0]["data"]["assistantResponse"]
    assert "4점 / 리뷰 8건 / 대표 리뷰: 가격 부담이 낮고 기본 주행 성능이 무난하다는 평가가 있어요." in events[0]["data"]["assistantResponse"]
    assert [call["tool_name"] for call in metadata["tool_calls"]] == [
        "search_product_summary_tool",
        "search_product_summary_tool",
    ]
    assert metadata["missing_inputs"] == []


def test_product_comparison_persists_followup_context_in_state() -> None:
    state_store = MemoryStateStore()
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
        state_store=state_store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "키너지 ex랑 옵티모랑 비교해줘"}],
        stream=False,
        user_id="u1",
        session_id="product-comparison-followup",
    )

    asyncio.run(runtime.run(request))

    assert "키너지 EX" in state_store.state.conversation_summary
    assert "옵티모" in state_store.state.conversation_summary
    assert state_store.state.last_facts["followup_type"] == "product_comparison"
    assert state_store.state.last_facts["product_names"] == ["키너지 EX", "옵티모"]
    assert state_store.state.last_facts["compare_metric"] == "detail"


def test_product_template_persists_followup_context_in_state() -> None:
    state_store = MemoryStateStore()
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_RECOMMENDATION,
                    reason="recommend tires",
                    known_inputs={"recommendation_type": "tstation", "tire_size": "245/45R19"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=state_store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "245/45R19 추천해줘"}],
        stream=False,
        user_id="u1",
        session_id="product-followup",
    )

    asyncio.run(runtime.run(request))

    assert state_store.state.last_facts["followup_type"] == "product_list"
    assert state_store.state.last_facts["product_names"] == ["벤투스 S2 AS"]
    assert state_store.state.last_facts["goods_no"] == "G000000000001"
    assert "벤투스 S2 AS" in state_store.state.conversation_summary


def test_extract_known_inputs_uses_last_facts_fallback() -> None:
    state = ConversationState()
    state.last_facts = {
        "product_names": ["키너지 EX", "옵티모"],
        "compare_metric": "detail",
        "shop_id": "S001",
        "store_name": "티스테이션 판교점",
        "car_model": "GV70",
    }

    known = extract_known_inputs("가격은?", state)

    assert known["product_names"] == ["키너지 EX", "옵티모"]
    assert known["compare_metric"] == "detail"
    assert known["shop_id"] == "S001"
    assert known["store_name"] == "티스테이션 판교점"
    assert known["car_model"] == "GV70"


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


def test_recommendation_af_with_product_names_still_emits_product_cards() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_RECOMMENDATION,
                    reason="recommend among named products",
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
        messages=[{"role": "user", "content": "키너지 ex랑 옵티모 추천해줘"}],
        stream=False,
        user_id="u1",
        session_id="product-recommendation-with-product-names",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "product"
    assert metadata["tool_calls"][0]["tool_name"] == "get_products_recommendations_tool"
    assert events[0]["data"]["metadata"][0]["goodsId"] == "G000000000001"


def test_description_af_recommendation_request_reroutes_to_product_cards() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_DESCRIPTION,
                    reason="planner misclassified recommendation as description",
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
        messages=[{"role": "user", "content": "키너지 ex랑 옵티모 추천해줘"}],
        stream=False,
        user_id="u1",
        session_id="product-description-reroutes-recommendation",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "product"
    assert metadata["tool_calls"][0]["tool_name"] == "get_products_recommendations_tool"
    assert all(
        not (
            isinstance(event.get("data"), dict)
            and isinstance(event["data"].get("metadata"), dict)
            and event["data"]["metadata"].get("response_shape_key") == "metric_comparison_summary"
        )
        for event in events
    )


def test_alternative_tire_request_excludes_current_product() -> None:
    state_store = MemoryStateStore()
    state_store.state.commerce_state.product.goods_no = "G000000000003"
    state_store.state.commerce_state.product.product_name = "아이온 에보"
    state_store.state.commerce_state.product.tire_size = "235/55R19"
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(selected_afs=[])),
        executor=AlternativeFakeExecutor(),
        composer=StaticComposer(),
        state_store=state_store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "다른 타이어 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="alternative-tire",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert metadata["planner"]["conversation_goal"] == "show_alternative_products"
    assert events[0]["template"] == "product"
    assert [product["titleProductName"] for product in events[0]["data"]["products"]] == ["다이나프로 HPX"]
    assert events[0]["data"]["metadata"] == [{"goodsId": "G000000000005"}]


def test_alternative_store_request_excludes_current_store() -> None:
    state_store = MemoryStateStore()
    state_store.state.commerce_state.product.goods_no = "G000000000003"
    state_store.state.commerce_state.product.product_name = "아이온 에보"
    state_store.state.commerce_state.quantity = 4
    state_store.state.commerce_state.store.shop_id = "S001"
    state_store.state.commerce_state.store.shop_name = "티스테이션 판교점"
    state_store.state.commerce_state.store.region = "판교"
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(selected_afs=[])),
        executor=AlternativeFakeExecutor(),
        composer=StaticComposer(),
        state_store=state_store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "다른 매장 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="alternative-store",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert metadata["planner"]["conversation_goal"] == "show_alternative_stores"
    assert metadata["tool_calls"][0]["tool_name"] == "transaction_store_preview_tool"
    assert metadata["tool_calls"][0]["args"]["region_code"] == "판교"
    assert events[0]["template"] == "location"
    assert [store["nameAddress"] for store in events[0]["data"]["stores"]] == ["티스테이션 분당점"]
    assert events[0]["data"]["metadata"] == [
        {
            "shopId": "S002",
            "shopName": "티스테이션 분당점",
            "ctaAction": "select_store",
            "cta_action": "select_store",
            "fillsSlot": "shop_id",
            "fills_slot": "shop_id",
        }
    ]


def test_benefit_event_deal_list_uses_benefit_list_tool() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_DESCRIPTION,
                    reason="current event and deal list",
                    known_inputs={"benefit_lookup": "event_deal_list"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "지금 이벤트랑 기획전 뭐 있어?"}],
        stream=False,
        user_id="u1",
        session_id="benefit-list",
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "quickReply"
    assert text == events[0]["data"]["assistantResponse"]
    assert events[0]["data"]["metadata"]["response_shape_key"] == "benefit_event_list_lookup"
    assert "한국타이어 페스타" in events[0]["data"]["assistantResponse"]
    assert "여름맞이 기획전" in events[0]["data"]["assistantResponse"]
    assert metadata["tool_calls"][0]["tool_name"] == "get_benefit_event_deal_list_tool"
    assert metadata["tool_calls"][0]["args"] == {"lang_cd": "ko"}


def test_event_applicable_products_with_event_number_uses_event_products_tool() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_DESCRIPTION,
                    reason="event applicable products by event id",
                    known_inputs={
                        "benefit_lookup": "event_applicable_products",
                        "evt_no_list": ["E000001234"],
                    },
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "E000001234 이벤트 적용 상품 알려줘"}],
        stream=False,
        user_id="u1",
        session_id="event-products",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "quickReply"
    assert events[0]["data"]["metadata"]["response_shape_key"] == "event_applicable_products_lookup"
    assert "현재 이벤트/기획전/프로모션 적용 상품이에요." in events[0]["data"]["assistantResponse"]
    assert "키너지 EX" in events[0]["data"]["assistantResponse"]
    assert metadata["tool_calls"][0]["tool_name"] == "get_event_applicable_products_tool"
    assert metadata["tool_calls"][0]["args"] == {"evt_no_list": ["E000001234"]}


def test_named_benefit_or_product_benefit_lookup_uses_benefit_applicable_products_tool() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_DESCRIPTION,
                    reason="named benefit applicable products",
                    known_inputs={
                        "benefit_lookup": "product_applicable_benefits",
                        "benefit_query": "키너지 EX",
                    },
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "키너지 EX에 적용되는 이벤트 기획전 쿠폰 알려줘"}],
        stream=False,
        user_id="u1",
        session_id="product-benefits",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "quickReply"
    assert events[0]["data"]["metadata"]["response_shape_key"] == "benefit_applicable_products_lookup"
    assert "'키너지 EX'에 매칭되는 적용 상품/매장이에요." in events[0]["data"]["assistantResponse"]
    assert "한국타이어 페스타" in events[0]["data"]["assistantResponse"]
    assert "티스테이션 판교점" in events[0]["data"]["assistantResponse"]
    assert metadata["tool_calls"][0]["tool_name"] == "search_benefit_applicable_products_tool"
    assert metadata["tool_calls"][0]["args"] == {"query": "키너지 EX", "lang_cd": "ko"}


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


def test_named_vehicle_recommendation_infers_vehicle_type_from_model() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_RECOMMENDATION,
                    reason="named vehicle recommendation",
                    known_inputs={
                        "car_model": "팰리세이드",
                        "recommendation_type": "family",
                    },
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "팰리세이드에 맞는 패밀리 타이어 추천"}],
        stream=False,
        user_id="u1",
        session_id="named-vehicle-recommendation",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "product"
    assert metadata["tool_calls"][0]["args"] == {
        "rcmd_type": "family",
        "limit": 3,
        "vehicle_type": "suv",
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


def test_side_question_with_stale_purchase_slots_uses_current_turn_intent() -> None:
    store = MemoryStateStore()
    store.state = ConversationState()
    store.state.commerce_state.product.goods_no = "G000000000003"
    store.state.commerce_state.product.product_name = "아이온 에보"
    store.state.commerce_state.quantity = 4
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
        session_id="side-price-stale-slots",
        slots={
            "goodsNo": "G000000000003",
            "productName": "아이온 에보",
            "ordQty": 4,
            "shopId": "S001",
            "shopName": "티스테이션 판교점",
            "requestedCalDay": "20260707",
            "rsvHour": "10",
        },
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events == []
    assert metadata["planner"]["selected_afs"][0]["af"] == "PriceAF"
    assert [call["tool_name"] for call in metadata["tool_calls"]] == ["get_final_price_tool"]
    assert store.state.commerce_state.store.shop_id is None
    assert store.state.commerce_state.schedule.date is None
    assert store.state.commerce_state.schedule.time is None


def test_schedule_stage_side_question_with_stale_ui_slots_uses_current_turn_intent() -> None:
    store = MemoryStateStore()
    store.state = ConversationState()
    store.state.commerce_state.product.goods_no = "G000000000003"
    store.state.commerce_state.product.product_name = "아이온 에보"
    store.state.commerce_state.quantity = 4
    store.state.commerce_state.store.shop_id = "S001"
    store.state.commerce_state.store.shop_name = "티스테이션 판교점"
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRICE,
                    reason="side question during schedule selection",
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
        session_id="schedule-side-price-stale-ui-slots",
        ui_action={
            "slots": {
                "requestedCalDay": "20260707",
                "rsvHour": "10",
            },
        },
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events == []
    assert metadata["planner"]["selected_afs"][0]["af"] == "PriceAF"
    assert [call["tool_name"] for call in metadata["tool_calls"]] == ["get_final_price_tool"]
    assert store.state.commerce_state.schedule.date is None
    assert store.state.commerce_state.schedule.time is None


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
    assert store.state.commerce_state.schedule.date == "2026년 07월 07일"
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


def test_store_flow_uses_gangnam_station_place_query_override() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(af=AgentFlow.STORE, reason="store lookup", known_inputs={"region": "강남"})
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "강남 매장 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="store-gangnam-override",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "location"
    assert metadata["tool_calls"][0]["tool_name"] == "search_stores_tool"
    assert metadata["tool_calls"][0]["args"] == {"limit": 10, "place_query": "강남역"}


def test_store_flow_uses_current_location_when_region_missing() -> None:
    state_store = MemoryStateStore()
    state_store.state.commerce_state.store.region = "이전지역"
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(af=AgentFlow.STORE, reason="store lookup near current location", known_inputs={})
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=state_store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "근처 매장 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="store-current-location",
        user_info={"location": {"xpos": 127.123, "ypos": 37.456}},
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "location"
    assert metadata["tool_calls"][0]["tool_name"] == "search_stores_tool"
    assert metadata["tool_calls"][0]["args"] == {"limit": 10, "xpos": 127.123, "ypos": 37.456}


def test_store_flow_without_location_or_region_requests_location_input() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(af=AgentFlow.STORE, reason="store lookup needs location", known_inputs={})
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "매장 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="store-missing-location",
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert text == "필요한 정보를 알려주세요."
    assert events == []
    assert metadata["missing_inputs"] == ["region_or_store"]
    assert metadata["tool_calls"] == []


def test_store_flow_blocks_unsupported_foreign_region_gate_result() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(af=AgentFlow.STORE, reason="store lookup outside service area", known_inputs={"region": "우즈벡"})
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "우즈벡 매장 찾아줘"}],
        stream=False,
        user_id="u1",
        session_id="store-unsupported-region",
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "quickReply"
    assert events[0]["data"]["metadata"]["source"] == "llm_first_unsupported_region"
    assert "국내 지역명" in text
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


def test_store_attribute_search_uses_ev_specialty_filter() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.STORE,
                    reason="store lookup with ev specialty filter",
                    known_inputs={"region": "서울", "store_attribute": "전기차 특화매장"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "서울 전기차 특화매장 찾아줘"}],
        stream=False,
        user_id="u1",
        session_id="store-attribute-ev-specialty",
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "location"
    assert events[0]["data"]["assistantResponse"] == "전기차 특화매장 조건에 맞는 매장 후보를 확인해 주세요."
    assert "포함되어 있지 않아요" not in events[0]["data"]["assistantResponse"]
    assert text == "확인한 결과를 안내드립니다."
    assert metadata["tool_calls"][0]["tool_name"] == "search_stores_tool"
    assert metadata["tool_calls"][0]["args"] == {
        "limit": 10,
        "place_query": "서울",
        "ev_specialty_only": True,
    }


def test_store_schedule_search_uses_complex_tool_for_specific_date_and_normalizes_gyeonggi() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.STORE,
                    reason="specific-date store schedule search",
                    known_inputs={"region": "경기권", "date": "2026-07-12"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "경기권에서 2026-07-12 장착 가능한 매장 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="store-schedule-complex-date",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "location"
    LocationDataEvent.model_validate(events[0])
    assert metadata["tool_calls"][0]["tool_name"] == "search_stores_complex_tool"
    assert metadata["tool_calls"][0]["args"] == {
        "limit": 10,
        "cal_days": ["20260712"],
        "open_only": True,
        "place_query": "경기도",
    }


def test_store_schedule_search_uses_complex_tool_for_weekend() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.STORE,
                    reason="weekend store schedule search",
                    known_inputs={"region": "경기지역"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "경기지역 이번주말 장착 가능한 매장 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="store-schedule-complex-weekend",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "location"
    LocationDataEvent.model_validate(events[0])
    assert metadata["tool_calls"][0]["tool_name"] == "search_stores_complex_tool"
    assert metadata["tool_calls"][0]["args"] == {
        "limit": 10,
        "cal_days": ["20260711", "20260712"],
        "open_only": True,
        "place_query": "경기도",
    }


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


def test_location_template_persists_followup_context_in_state() -> None:
    state_store = MemoryStateStore()
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
        state_store=state_store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "내 단골매장 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="favorite-store-followup",
    )

    asyncio.run(runtime.run(request))

    assert state_store.state.last_facts["followup_type"] == "store_list"
    assert state_store.state.last_facts["store_names"] == ["티스테이션 단골점"]
    assert state_store.state.last_facts["shop_ids"] == ["S003"]
    assert "티스테이션 단골점" in state_store.state.conversation_summary


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
    assert events[0]["template"] == "quickReply"
    assert events[0]["data"]["assistantResponse"] == "수량 정보를 알려주시면 이어서 확인해 드릴게요."
    assert [reply["label"] for reply in events[0]["data"]["quickReplies"]] == ["1개", "2개", "3개", "4개"]
    assert all(reply["domain"] == "TRANSACTION" for reply in events[0]["data"]["quickReplies"])
    assert events[0]["data"]["metadata"]["fillsSlot"] == "ord_qty"
    assert metadata["missing_inputs"] == ["ord_qty"]
    assert metadata["tool_calls"] == []


def test_quick_shopping_missing_quantity_emits_quantity_quickreply() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.QUICK_SHOPPING,
                    reason="purchase flow needs quantity",
                    known_inputs={"goods_no": "G000000000003"},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "이 상품 구매할래"}],
        stream=False,
        user_id="u1",
        session_id="quick-shopping-quantity-missing",
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert text == "필요한 정보를 알려주세요."
    assert events[0]["template"] == "quickReply"
    assert [reply["label"] for reply in events[0]["data"]["quickReplies"]] == ["1개", "2개", "3개", "4개"]
    assert metadata["missing_inputs"] == ["quantity"]
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
    assert events[0]["data"]["metadata"][0]["sourceTool"] == "transaction_store_preview_tool"
    assert events[0]["data"]["metadata"][0]["scheduleMode"] == "in_store_only"
    assert events[0]["data"]["metadata"][0]["scheduleTier"] == "in_store_only"
    assert events[0]["data"]["metadata"][0]["ctaAction"] == "select_store"


def test_inventory_flow_uses_current_location_when_region_missing() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.INVENTORY,
                    reason="inventory check near current location",
                    known_inputs={"goods_no": "G000000000002", "ord_qty": 4},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "근처 장착 가능 매장 보여줘"}],
        stream=False,
        user_id="u1",
        session_id="inventory-current-location",
        user_info={"location": {"xpos": 127.123, "ypos": 37.456}},
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "location"
    assert metadata["tool_calls"][0]["tool_name"] == "transaction_store_preview_tool"
    assert metadata["tool_calls"][0]["args"] == {
        "goods_no": "G000000000002",
        "ord_qty": 4,
        "region_code": None,
        "store_nm": None,
        "user_xpos": 127.123,
        "user_ypos": 37.456,
    }


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
    assert events[0]["data"]["dates"][0]["date"] == "2026년 07월 07일"
    assert events[0]["data"]["dates"][0]["availableTimes"] == [10, 11, 13]
    assert metadata["missing_inputs"] == ["schedule"]
    assert metadata["tool_calls"][0]["tool_name"] == "get_store_schedule_tool"


def test_datepick_template_persists_followup_context_in_state() -> None:
    state_store = MemoryStateStore()
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(af=AgentFlow.QUICK_SHOPPING, reason="order draft", known_inputs={})
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=state_store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "주문 진행해줘"}],
        stream=False,
        user_id="u1",
        session_id="datepick-followup",
        slots={
            "goodsNo": "G000000000003",
            "productName": "아이온 에보",
            "ordQty": 4,
            "shopId": "S001",
            "shopName": "티스테이션 판교점",
        },
    )

    asyncio.run(runtime.run(request))

    assert state_store.state.last_facts["followup_type"] == "schedule_options"
    assert state_store.state.last_facts["date_candidates"][0] == "2026년 07월 07일"
    assert state_store.state.last_facts["first_available_times"] == [10, 11, 13]
    assert state_store.state.last_facts["shop_id"] == "S001"


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


def test_quick_shopping_blocks_unsupported_region_gate_result() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.QUICK_SHOPPING,
                    reason="continue order with unsupported region",
                    known_inputs={
                        "goods_no": "G000000000003",
                        "product_name": "아이온 에보",
                        "ord_qty": 4,
                        "region": "사우디",
                    },
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "사우디에서 장착할래"}],
        stream=False,
        user_id="u1",
        session_id="purchase-unsupported-region",
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "quickReply"
    assert events[0]["data"]["metadata"]["source"] == "llm_first_unsupported_region"
    assert "국내 지역명" in text
    assert metadata["missing_inputs"] == []
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


def test_shop_id_only_ui_action_in_active_purchase_flow_emits_datepick_with_schedule_mode() -> None:
    store = MemoryStateStore()
    store.state.commerce_state.product.goods_no = "G000000000003"
    store.state.commerce_state.product.product_name = "아이온 에보"
    store.state.commerce_state.quantity = 4
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
        session_id="store-selection-shopid-only",
        ui_action={
            "slots": {
                "shopId": "S002",
                "shopName": "티스테이션 분당점",
                "scheduleMode": "in_store_only",
                "sourceTool": "transaction_store_preview_tool",
            },
        },
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "datepick"
    DatepickDataEvent.model_validate(events[0])
    assert events[0]["data"]["dates"][0]["date"] == "2026년 07월 07일"
    assert events[0]["data"]["dates"][0]["availableTimes"] == [10, 11]
    assert events[0]["data"]["dates"][1]["date"] == "2026년 07월 08일"
    assert metadata["planner"]["selected_afs"][0]["af"] == "QuickShoppingAF"
    assert metadata["tool_calls"][0]["tool_name"] == "get_store_schedule_tool"
    assert metadata["tool_calls"][0]["args"] == {"shop_id": "S002", "mode": "in_store_only"}
    assert store.state.commerce_state.store.shop_id == "S002"


def test_schedule_selection_in_active_purchase_flow_emits_preorder_without_planner_choice(monkeypatch) -> None:
    monkeypatch.setattr(
        schedule_validation_module,
        "_kst_now",
        lambda: datetime.datetime(2026, 7, 7, 9, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=9))),
    )
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
    assert events[0]["data"]["orderInfo"]["bookingDateTime"] == "2026년 07월 07일 10:00"
    assert metadata["planner"]["selected_afs"][0]["af"] == "QuickShoppingAF"
    assert metadata["planner"]["resume_previous_flow"] is True
    assert metadata["tool_calls"][0]["tool_name"] == "get_final_price_tool"
    assert store.state.commerce_state.schedule.date == "2026년 07월 07일"
    assert store.state.commerce_state.schedule.time == "10"


def test_schedule_selection_preorder_formats_hour_with_minutes(monkeypatch) -> None:
    monkeypatch.setattr(
        schedule_validation_module,
        "_kst_now",
        lambda: datetime.datetime(2026, 7, 7, 9, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=9))),
    )
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
        messages=[{"role": "user", "content": "7월 15일 15시"}],
        stream=False,
        user_id="u1",
        session_id="schedule-selection-preorder-hour-format",
        ui_action={
            "action_type": "select_schedule",
            "slots": {
                "requestedCalDay": "20260715",
                "rsvHour": "15",
            },
        },
    )

    _, events, _ = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "preOrder"
    assert events[0]["data"]["orderInfo"]["bookingDateTime"] == "2026년 07월 15일 15:00"
    assert events[0]["data"]["metadata"]["rsvHour"] == "15"


def test_schedule_selection_in_active_purchase_flow_allows_same_day_time(monkeypatch) -> None:
    monkeypatch.setattr(
        schedule_validation_module,
        "_kst_now",
        lambda: datetime.datetime(2026, 7, 7, 16, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=9))),
    )
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
        messages=[{"role": "user", "content": "2026년 07월 07일 16:00"}],
        stream=False,
        user_id="u1",
        session_id="schedule-selection-same-day-time",
        ui_action={
            "action_type": "select_schedule",
            "slots": {
                "requestedCalDay": "20260707",
                "rsvHour": "16",
            },
        },
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "preOrder"
    assert text == "확인한 결과를 안내드립니다."
    assert metadata["tool_calls"][0]["tool_name"] == "get_final_price_tool"
    assert store.state.commerce_state.schedule.date == "2026년 07월 07일"
    assert store.state.commerce_state.schedule.time == "16"


def test_schedule_selection_in_active_purchase_flow_blocks_past_date(monkeypatch) -> None:
    monkeypatch.setattr(
        schedule_validation_module,
        "_kst_now",
        lambda: datetime.datetime(2026, 7, 7, 16, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=9))),
    )
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
        messages=[{"role": "user", "content": "2026년 07월 06일 17:00"}],
        stream=False,
        user_id="u1",
        session_id="schedule-selection-past-date",
        ui_action={
            "action_type": "select_schedule",
            "slots": {
                "requestedCalDay": "20260706",
                "rsvHour": "17",
            },
        },
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "quickReply"
    assert events[0]["data"]["metadata"]["source"] == "llm_first_schedule_selection_past_datetime"
    assert text == "지난 날짜의 예약 가능 여부는 조회가 불가능합니다. 오늘 날짜 2026-07-07 이후로 다시 선택해 주세요."
    assert metadata["tool_calls"] == []
    assert store.state.commerce_state.schedule.date is None
    assert store.state.commerce_state.schedule.time is None


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
    assert events[0]["data"]["orderInfo"]["bookingDateTime"] == "2026년 07월 07일 10:00"
    assert all(call["tool_name"] not in {"quick_order_tool", "save_to_cart_tool"} for call in metadata["tool_calls"])


def test_confirmed_preorder_ui_action_executes_quick_order_tool() -> None:
    store = MemoryStateStore()
    store.state.commerce_state.product.goods_no = "G000000000003"
    store.state.commerce_state.product.product_name = "아이온 에보"
    store.state.commerce_state.quantity = 4
    store.state.commerce_state.store.shop_id = "S001"
    store.state.commerce_state.store.shop_name = "티스테이션 판교점"
    store.state.commerce_state.schedule.date = "2026년 07월 07일"
    store.state.commerce_state.schedule.time = "10"
    store.state.commerce_state.price.final_price = 500000
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(selected_afs=[])),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "주문하기"}],
        stream=False,
        user_id="u1",
        session_id="confirmed-order",
        ui_action={
            "action": "quick_order_execute",
            "template": "preOrder",
            "slots": {
                "goodsId": "G000000000003",
                "ordQty": 4,
                "shopId": "S001",
                "requestedCalDay": "20260707",
                "rsvHour": "10",
            },
        },
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "orderComplete"
    assert events[0]["data"]["autoMoveOrderPage"] is True
    assert events[0]["data"]["metadata"]["source"] == "llm_first_order_complete"
    assert "주문서가 준비되었습니다" in text
    quick_order_calls = [call for call in metadata["tool_calls"] if call["tool_name"] == "quick_order_tool"]
    assert len(quick_order_calls) == 1
    assert quick_order_calls[0]["args"] == {
        "goods_no": "G000000000003",
        "ord_qty": 4,
        "shop_id": "S001",
        "rsv_date": "20260707",
        "rsv_hour": "10",
    }


def test_confirmed_cart_ui_action_executes_save_to_cart_tool() -> None:
    store = MemoryStateStore()
    store.state.commerce_state.product.goods_no = "G000000000003"
    store.state.commerce_state.product.product_name = "아이온 에보"
    store.state.commerce_state.quantity = 2
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(selected_afs=[])),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "장바구니 담기"}],
        stream=False,
        user_id="u1",
        session_id="confirmed-cart",
        ui_action={
            "action": "save_to_cart",
            "slots": {
                "goodsId": "G000000000003",
                "ordQty": 2,
            },
        },
    )

    text, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "quickReply"
    assert events[0]["data"]["metadata"]["source"] == "llm_first_cart_complete"
    assert "장바구니에 담았어요" in text
    cart_calls = [call for call in metadata["tool_calls"] if call["tool_name"] == "save_to_cart_tool"]
    assert len(cart_calls) == 1
    assert cart_calls[0]["args"] == {
        "goods_no": "G000000000003",
        "ord_qty": 2,
    }


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


def test_listcar_template_persists_followup_context_in_state() -> None:
    state_store = MemoryStateStore()
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
        state_store=state_store,
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "내 차 보여줘"}],
        stream=False,
        user_id="M123",
        session_id="compat-followup",
    )

    asyncio.run(runtime.run(request))

    assert state_store.state.last_facts["followup_type"] == "vehicle_list"
    assert state_store.state.last_facts["car_numbers"][:2] == ["12가3456", "34나5678"]
    assert state_store.state.last_facts["car_no"] == "12가3456"
    assert state_store.state.last_facts["car_model"] == "쏘나타 DN8"


def test_vehicle_recommendation_first_shows_my_car_list() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_COMPATIBILITY,
                    reason="registered vehicle recommendation needs vehicle selection",
                    known_inputs={"vehicle_recommendation": True},
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "내차에 맞는 타이어 추천해줘"}],
        stream=False,
        user_id="M123",
        session_id="vehicle-recommend-list",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "listCar"
    assert events[0]["data"]["assistantResponse"] == "내 차에 맞는 타이어를 추천하려면 차량을 먼저 선택해 주세요."
    assert events[0]["data"]["metadata"][0]["sourceIntent"] == "vehicle_resolved_recommendation"
    assert events[0]["data"]["metadata"][0]["carLncCd"] == "CAR001"
    assert events[0]["data"]["metadata"][0]["tireSize"] == "205/65R16"
    assert [call["tool_name"] for call in metadata["tool_calls"]] == ["get_my_cars_tool"]


def test_named_registered_vehicle_recommendation_auto_selects_unique_car() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_COMPATIBILITY,
                    reason="named registered vehicle recommendation",
                    known_inputs={
                        "vehicle_recommendation": True,
                        "car_model": "쏘나타",
                        "recommendation_type": "tstation",
                    },
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "내차 중에 쏘나타에 맞는 타이어 추천해줘"}],
        stream=False,
        user_id="M123",
        session_id="vehicle-recommend-named",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "product"
    assert [call["tool_name"] for call in metadata["tool_calls"]] == [
        "get_my_cars_tool",
        "get_products_recommendations_tool",
    ]
    assert metadata["tool_calls"][1]["args"] == {
        "rcmd_type": "tstation",
        "limit": 3,
        "car_lnc_cd": "CAR001",
        "vehicle_type": "passenger",
    }


def test_named_registered_vehicle_recommendation_falls_back_to_model_vehicle_type() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(
            selected_afs=[
                SelectedAF(
                    af=AgentFlow.PRODUCT_COMPATIBILITY,
                    reason="named registered vehicle recommendation",
                    known_inputs={
                        "vehicle_recommendation": True,
                        "car_model": "포터",
                        "recommendation_type": "tstation",
                    },
                )
            ]
        )),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "내차 포터 타이어 추천해줘"}],
        stream=False,
        user_id="M123",
        session_id="vehicle-recommend-unmatched-named",
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "product"
    assert [call["tool_name"] for call in metadata["tool_calls"]] == [
        "get_my_cars_tool",
        "get_products_recommendations_tool",
    ]
    assert metadata["tool_calls"][1]["args"] == {
        "rcmd_type": "tstation",
        "limit": 3,
        "vehicle_type": "truck_van",
    }


def test_selected_registered_vehicle_continues_to_recommendation() -> None:
    runtime = LLMFirstRuntime(
        planner=StaticPlanner(PlannerDecision(selected_afs=[])),
        executor=FakeExecutor(),
        composer=StaticComposer(),
        state_store=MemoryStateStore(),
    )
    request = TStationChatRequest(
        messages=[{"role": "user", "content": "이 차량 선택"}],
        stream=False,
        user_id="M123",
        session_id="vehicle-selection-recommend",
        ui_action={
            "action_type": "select_vehicle_candidate",
            "slots": {
                "carLncCd": "CAR003",
                "tireSize": "235/55R19",
                "carType": "SUV",
                "sourceIntent": "vehicle_resolved_recommendation",
            },
        },
    )

    _, events, metadata = asyncio.run(runtime.run(request))

    assert events[0]["template"] == "product"
    assert metadata["planner"]["selected_afs"][0]["af"] == "ProductRecommendationAF"
    assert metadata["planner"]["resume_previous_flow"] is True
    assert metadata["tool_calls"][0]["tool_name"] == "get_products_recommendations_tool"
    assert metadata["tool_calls"][0]["args"] == {
        "rcmd_type": "tstation",
        "limit": 3,
        "tire_size": "235/55R19",
        "car_lnc_cd": "CAR003",
        "vehicle_type": "suv",
    }


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


def test_qc_fact_mismatch_is_metadata_only() -> None:
    decision = PlannerDecision(
        selected_afs=[SelectedAF(af=AgentFlow.PRICE)],
    )

    status, event = verify_response(
        "확인된 가격은 999,999원입니다.",
        FactBundle(
            planner=decision,
            tool_calls=[
                ToolCallRecord(
                    af=AgentFlow.PRICE,
                    tool_name="get_final_price_tool",
                    args={"goods_no": "G000000000001"},
                    result={"status": "success", "data": {"cheapest_final_prc": 123000}},
                )
            ],
        ),
    )

    assert status == "fact_mismatch"
    assert event is None
