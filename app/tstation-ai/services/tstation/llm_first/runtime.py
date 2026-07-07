from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi.responses import StreamingResponse
from langchain_litellm import ChatLiteLLM

from config.env import settings
from config.tracing import set_trace_name
from schemas.tstation.chat import TStationChatRequest, TStationChatResponse
from services.tstation.llm_first.composer import Composer
from services.tstation.llm_first.executor import AFExecutor
from services.tstation.llm_first.planner import LeadingAgentPlanner
from services.tstation.llm_first.qc import verify_response
from services.tstation.llm_first.state import LLMFirstStateStore, apply_state_rules

logger = logging.getLogger(__name__)


def _make_llm(model_setting: str, *, streaming: bool = False, timeout: int = 60) -> ChatLiteLLM:
    return ChatLiteLLM(
        api_base=settings.AI_GATEWAY_BASE_URL,
        api_key=settings.AI_GATEWAY_API_KEY,
        model=f"{settings.AI_DEFAULT_PROVIDER}/{model_setting}",
        streaming=streaming,
        request_timeout=timeout,
    )


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def _last_user_text(request: TStationChatRequest) -> str:
    for message in reversed(request.messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _request_slot_patch(request: TStationChatRequest) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for source in (request.slots, request.ui_action, request.chip_context):
        if isinstance(source, dict):
            patch.update(source)
            nested_slots = source.get("slots")
            if isinstance(nested_slots, dict):
                patch.update(nested_slots)
            metadata = source.get("metadata")
            if isinstance(metadata, dict):
                patch.update(metadata)
    return patch


def _apply_request_patch(state: Any, request: TStationChatRequest) -> Any:
    patch = _request_slot_patch(request)
    if not patch:
        return state
    product_patch = {
        "goods_no": patch.get("goods_no") or patch.get("goodsNo") or patch.get("goodsId"),
        "product_name": patch.get("product_name") or patch.get("productName") or patch.get("product"),
        "tire_size": patch.get("tire_size") or patch.get("tireSize"),
    }
    raw_qty = patch.get("ord_qty") or patch.get("ordQty") or patch.get("quantity")
    quantity = None
    try:
        quantity = int(raw_qty) if raw_qty not in (None, "") else None
    except (TypeError, ValueError):
        quantity = None
    store_patch = {
        "shop_id": patch.get("shop_id") or patch.get("shopId"),
        "shop_name": patch.get("shop_name") or patch.get("shopName") or patch.get("storeName"),
        "region": patch.get("region") or patch.get("region_code") or patch.get("regionCode"),
    }
    schedule_patch = {
        "date": patch.get("requested_cal_day") or patch.get("requestedCalDay") or patch.get("date"),
        "time": patch.get("rsv_hour") or patch.get("rsvHour") or patch.get("time"),
    }
    raw_price = patch.get("final_price") or patch.get("paymentAmount") or patch.get("payment_amount")
    price = None
    try:
        price = int(raw_price) if raw_price not in (None, "") else None
    except (TypeError, ValueError):
        price = None
    return apply_state_rules(
        state,
        product_patch={k: v for k, v in product_patch.items() if v not in (None, "")},
        quantity=quantity,
        store_patch={k: v for k, v in store_patch.items() if v not in (None, "")},
        schedule_patch={k: v for k, v in schedule_patch.items() if v not in (None, "")},
        price_patch={"final_price": price, "source": "request_slots"} if price is not None else None,
    )


class LLMFirstRuntime:
    def __init__(
        self,
        *,
        planner: LeadingAgentPlanner | None = None,
        executor: AFExecutor | None = None,
        composer: Composer | None = None,
        state_store: LLMFirstStateStore | None = None,
    ):
        self.planner = planner or LeadingAgentPlanner(_make_llm(settings.AI_MODEL_QC_AGENT))
        self.executor = executor or AFExecutor()
        self.composer = composer or Composer(_make_llm(settings.AI_MODEL, streaming=False, timeout=120))
        self.state_store = state_store or LLMFirstStateStore()

    async def run(self, request: TStationChatRequest) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        user_text = _last_user_text(request)
        set_trace_name(user_text[:60] if user_text else "llm_first_chat")
        state = _apply_request_patch(self.state_store.load(request.session_id), request)
        planner = await self.planner.plan(
            user_text=user_text,
            state=state,
            session_id=request.session_id,
            user_id=request.user_id,
            trace_id=request.tracing_id,
        )
        bundle = await self.executor.execute(user_text=user_text, state=state, planner=planner)
        text = await self.composer.compose(
            user_text=user_text,
            bundle=bundle,
            session_id=request.session_id,
            user_id=request.user_id,
            trace_id=request.tracing_id,
        )
        qc_status, qc_event = verify_response(text, bundle)
        events = list(bundle.templates)
        if qc_event is not None:
            events = [qc_event]
            text = str(qc_event.get("data", {}).get("assistantResponse") or text)
        self.state_store.save(request.session_id, bundle.state)
        metadata = {
            "runtime": "llm_first",
            "planner": planner.model_dump(mode="json"),
            "qc_status": qc_status,
            "tool_calls": [
                call.model_dump(mode="json", exclude={"result"})
                for call in bundle.tool_calls
            ],
            "missing_inputs": bundle.missing_inputs,
        }
        return text, events, metadata

    async def stream(self, request: TStationChatRequest) -> AsyncIterator[str]:
        yield _sse({"type": "agent_flow", "agent": "[LLM-FIRST LEADING AGENT]", "status": "start"})
        try:
            text, events, metadata = await self.run(request)
            yield _sse({"type": "agent_flow", "agent": "[LLM-FIRST LEADING AGENT]", "status": "done", "metadata": metadata})
            for event in events:
                yield _sse(event)
            if text:
                yield _sse({"type": "token", "content": text})
                yield _sse({"type": "message", "content": text, "agent": "[LLM-FIRST COMPOSER]"})
            yield _sse({"type": "DONE"})
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.exception("[LLM_FIRST_RUNTIME] stream failed")
            message = "요청을 처리하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            yield _sse({
                "type": "data",
                "template": "quickReply",
                "data": {
                    "assistantResponse": message,
                    "quickReplies": [{"label": "다시 시도", "domain": "LEADING"}],
                    "metadata": {"source": "llm_first_runtime_error", "error": str(exc)},
                },
            })
            yield _sse({"type": "token", "content": message})
            yield _sse({"type": "message", "content": message, "agent": "[LLM-FIRST COMPOSER]"})
            yield "data: [DONE]\n\n"


async def chat(request: TStationChatRequest):
    runtime = LLMFirstRuntime()
    if request.stream:
        return StreamingResponse(
            runtime.stream(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    text, _, _ = await runtime.run(request)
    return TStationChatResponse(content=text)


def enabled() -> bool:
    return bool(getattr(settings, "AI_LLM_FIRST_RUNTIME_ENABLED", False))
