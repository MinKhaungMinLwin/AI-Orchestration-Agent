"""Native tool-calling loop: the LLM decides which tools to call.

No dispatch rules — tools for the routed domain are bound to the model
and it chooses. Streams answer tokens and tool progress as SSE strings;
final state is available on the instance after the stream ends.
"""

import json
import logging
from collections.abc import Callable

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from pydantic import ValidationError

from services.tstation.chat_v3 import sse
from services.tstation.chat_v3.llm import get_composer_llm, get_fallback_llm, get_tool_selector_llm
from services.tstation.policies.inventory_response_policy import redact_inventory_output_for_model

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4
_TOOL_OUTPUT_PREVIEW_CHARS = 4000
_RECOMMENDATION_TOOL = "get_products_recommendations_tool"
_RECOMMENDATION_LLM_FIELDS = (
    "goods_no",
    "goods_nm",
    "tire_size_1",
    "sale_prc",
    "extra_fvr_sale_prc",
    "extra_fvr_sale_per",
    "cheapest_final_prc",
    "cheapest_total_discount",
    "season_nm",
    # 차종 분류명 (전기차 / SUV / 승용 / 화물·승합). Without it the model cannot tell an
    # EV-only or van-only tire from a passenger one, and recommends iON for a petrol car.
    "car_knd_nm",
    "goods_pfm_nm",
    "goods_dtl_pfm_nm",
    "t_wgt_spd",
    "label_pnwave_nm",
    "label_pndb",
    "t_rls_yearmon",
)


def _tool_output_text(output: object) -> str:
    if isinstance(output, str):
        return output
    try:
        return json.dumps(output, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(output)


def _model_visible_tool_output(name: str, output_text: str) -> str:
    if name == _RECOMMENDATION_TOOL:
        return _compact_recommendation_output(output_text)
    return redact_inventory_output_for_model(name, output_text)


def _compact_recommendation_output(output_text: str) -> str:
    """Keep every product's price contract while dropping verbose catalogue HTML."""
    try:
        parsed = json.loads(output_text)
    except (TypeError, ValueError):
        return output_text
    if not isinstance(parsed, dict):
        return output_text
    data = parsed.get("data")
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return output_text

    compact_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        compact = {key: item[key] for key in _RECOMMENDATION_LLM_FIELDS if item.get(key) is not None}
        coupons = item.get("cheapest_applied_coupons")
        if isinstance(coupons, list):
            compact["cheapest_applied_coupons"] = [
                {
                    key: coupon[key]
                    for key in ("stage", "cpn_nm", "discount_amt")
                    if isinstance(coupon, dict) and coupon.get(key) is not None
                }
                for coupon in coupons
                if isinstance(coupon, dict)
            ]
        compact_items.append(compact)

    compact_data: dict[str, object] = {
        "total": data.get("total"),
        "items": compact_items,
        "price_contract": {
            "sale_prc": "기본가",
            "extra_fvr_sale_prc": "일반 혜택가",
            "cheapest_final_prc": "보유쿠폰 적용 혜택가",
            "instruction": "각 상품에서 존재하는 세 가격을 서로 대체하지 말고 라벨별로 모두 표시",
            "coupon_price_notice": "보유 쿠폰 기준 가격이며, 상품 상세 페이지에서 미 다운로드 쿠폰 적용 시 추가 할인 받으실 수 있습니다.",
        },
    }
    # The tool silently drops the vehicle_type filter when it would return nothing, and says so
    # in this block (it even carries the sentence for the assistant). Dropping it here is how a
    # van-only or EV-only tire reaches a customer presented as a fit for their car.
    if isinstance(data.get("recommendation_fallback"), dict):
        compact_data["recommendation_fallback"] = data["recommendation_fallback"]

    return json.dumps(
        {"status": parsed.get("status"), "data": compact_data},
        ensure_ascii=False,
        separators=(",", ":"),
    )


# The cart API returning HTTP success with data.result=false
# is a FAILED add-to-cart and must never be surfaced as a success.
_BUSINESS_RESULT_TOOLS = {"save_to_cart_tool"}


def _normalize_business_failure(name: str, output_text: str) -> str:
    if name not in _BUSINESS_RESULT_TOOLS:
        return output_text
    try:
        parsed = json.loads(output_text)
    except (TypeError, ValueError):
        return output_text
    if not isinstance(parsed, dict) or parsed.get("status") != "success":
        return output_text
    data = parsed.get("data")
    if not isinstance(data, dict) or bool(data.get("result")):
        return output_text
    parsed["status"] = "error"
    parsed["error"] = "cart_add_failed"
    return json.dumps(parsed, ensure_ascii=False)


def _output_flow_status(output_text: str) -> str:
    if output_text.startswith("Tool error"):
        return "error"
    try:
        parsed = json.loads(output_text)
    except (TypeError, ValueError):
        return "success"
    if isinstance(parsed, dict) and parsed.get("status") == "error":
        return "error"
    return "success"


class ToolLoopExecutor:
    """One conversation turn: LLM ↔ tools until the model answers in text."""

    def __init__(
        self,
        messages: list[BaseMessage],
        tools: list,
        display_names: dict[str, str],
        *,
        stream_tokens: bool = True,
        trace_config: dict | None = None,
        tool_call_normalizer: Callable[[dict], dict] | None = None,
        tool_call_guard: Callable[[dict], str | None] | None = None,
        stop_after_tool: Callable[[list[dict]], bool] | None = None,
    ):
        self._messages = list(messages)
        self._tools = {t.name: t for t in tools}
        self._display_names = display_names
        self._stream_tokens = stream_tokens
        self._trace_config = trace_config
        self._tool_call_normalizer = tool_call_normalizer
        self._tool_call_guard = tool_call_guard
        self._stop_after_tool = stop_after_tool
        self.final_text: str = ""
        self.tool_calls: list[dict] = []
        self.stopped_after_tool = False
        self.selector_fallback_used = False
        self.selector_fallback_reason = ""
        self.composer_fallback_used = False

    async def stream(self):
        has_tool_result = False
        fallback_instruction = ""
        force_answer_without_tools = False

        for _ in range(MAX_TOOL_ROUNDS + 1):
            input_messages = self._messages
            if fallback_instruction:
                llm = get_fallback_llm()
                input_messages = [
                    *self._messages,
                    SystemMessage(content=fallback_instruction),
                ]
                fallback_instruction = ""
            elif has_tool_result or not self._tools:
                llm = get_composer_llm()
            else:
                llm = get_tool_selector_llm()
            if self._tools and not force_answer_without_tools:
                llm = llm.bind_tools(list(self._tools.values()))

            accumulated = None
            round_text = ""
            async for chunk in llm.astream(input_messages, config=self._trace_config):
                accumulated = chunk if accumulated is None else accumulated + chunk
                text = sse.chunk_text(chunk.content)
                if text:
                    round_text += text
                    if self._stream_tokens:
                        yield sse.token(text)

            ai_message = accumulated if isinstance(accumulated, AIMessage) else AIMessage(content=round_text)
            tool_calls = getattr(ai_message, "tool_calls", None) or []
            if not tool_calls:
                self.final_text = round_text
                return

            prepared_calls = [self._normalize_tool_call(call) for call in tool_calls]
            denials = [(call, denial) for call in prepared_calls if (denial := self._tool_call_denial(call))]
            if denials and not self.selector_fallback_used:
                self.selector_fallback_used = True
                self.selector_fallback_reason = denials[0][1]
                rejected = ", ".join(str(call.get("name") or "unknown") for call, _ in denials)
                fallback_instruction = (
                    "The fast model proposed a tool call rejected by the runtime contract. "
                    f"Rejected tools: {rejected}. Reason: {self.selector_fallback_reason}. "
                    "Re-select only from the bound tools with valid required arguments. "
                    "Do not repeat the rejected call unless you have corrected it."
                )
                logger.info(
                    "[CHAT_V3] tool selection rejected; retrying once with fallback model: tools=%s reason=%s",
                    rejected,
                    self.selector_fallback_reason,
                )
                continue

            self._messages.append(ai_message)
            if denials:
                denial_by_id = {str(call.get("id") or call.get("name") or ""): denial for call, denial in denials}
                for call in prepared_calls:
                    key = str(call.get("id") or call.get("name") or "")
                    denial = denial_by_id.get(key) or "batch_rejected_due_to_contract_failure"
                    async for event in self._record_blocked_call(call, denial):
                        yield event
                has_tool_result = True
                force_answer_without_tools = True
                continue

            for call in prepared_calls:
                async for event in self._run_tool(call):
                    yield event
                if self._stop_after_tool is not None and self._stop_after_tool(self.tool_calls):
                    self.stopped_after_tool = True
                    return
            has_tool_result = True

        # Tool budget exhausted — force a final text answer without tools.
        final_text = ""
        async for chunk in get_composer_llm().astream(self._messages, config=self._trace_config):
            text = sse.chunk_text(chunk.content)
            if text:
                final_text += text
                if self._stream_tokens:
                    yield sse.token(text)
        self.final_text = final_text

    async def recompose_with_fallback(self, reason: str, trace_config: dict | None = None) -> str:
        """Rewrite a grounded answer once when deterministic QC rejects the fast composer."""
        instruction = SystemMessage(
            content=(
                "The fast composer answer failed deterministic grounding checks. "
                f"Failure: {reason}. Rewrite the user-facing answer using only the tool results already present. "
                "Keep product identifiers, prices, store names, inventory, and dates exactly consistent with those results."
            )
        )
        text = ""
        try:
            async for chunk in get_fallback_llm().astream(
                [*self._messages, instruction],
                config=trace_config or self._trace_config,
            ):
                text += sse.chunk_text(chunk.content)
        except Exception:
            logger.exception("[CHAT_V3] composer fallback failed; keeping the original answer")
            return ""
        self.composer_fallback_used = True
        return text.strip()

    def _normalize_tool_call(self, call: dict) -> dict:
        return self._tool_call_normalizer(call) if self._tool_call_normalizer is not None else call

    def _tool_call_denial(self, call: dict) -> str | None:
        name = str(call.get("name") or "")
        tool = self._tools.get(name)
        if tool is None:
            return f"tool_not_allowed:{name or 'missing_name'}"
        if self._tool_call_guard is not None:
            denial = self._tool_call_guard(call)
            if denial:
                return f"policy_guard:{denial}"
        get_input_schema = getattr(tool, "get_input_schema", None)
        if callable(get_input_schema):
            try:
                get_input_schema().model_validate(call.get("args") or {})
            except ValidationError as exc:
                fields = ",".join(str(item.get("loc", ["args"])[-1]) for item in exc.errors()[:3])
                return f"invalid_tool_arguments:{name}:{fields or 'args'}"
        return None

    async def _record_blocked_call(self, call: dict, denial: str):
        name = str(call.get("name") or "")
        args = call.get("args") or {}
        call_id = call.get("id") or name or "blocked_tool"
        display = self._display_names.get(name, name)
        output_text = f"Tool error: blocked_by_contract — {denial}"
        logger.info("[CHAT_V3] tool %s blocked by contract: %s", name, denial)
        self.tool_calls.append({"name": name, "args": args, "output": output_text})
        yield sse.agent_flow(display, "error")
        self._messages.append(ToolMessage(content=output_text, tool_call_id=call_id))

    async def _run_tool(self, call: dict):
        if self._tool_call_normalizer is not None:
            call = self._tool_call_normalizer(call)
        name = call.get("name") or ""
        args = call.get("args") or {}
        call_id = call.get("id") or name
        tool = self._tools.get(name)
        display = self._display_names.get(name, name)
        if self._tool_call_guard is not None:
            denial = self._tool_call_guard(call)
            if denial:
                output_text = f"Tool error: blocked_by_policy — {denial}"
                logger.info("[CHAT_V3] tool %s blocked by policy: %s", name, denial)
                self.tool_calls.append({"name": name, "args": args, "output": output_text})
                yield sse.agent_flow(display, "error")
                self._messages.append(ToolMessage(content=output_text, tool_call_id=call_id))
                return
        yield sse.tool_start(name, display)
        if tool is None:
            output_text = f"Unknown tool: {name}"
        else:
            try:
                output = await tool.ainvoke(args, config=self._trace_config)
                output_text = _normalize_business_failure(name, _tool_output_text(output))
            except Exception as exc:
                logger.exception("[CHAT_V3] tool %s failed", name)
                output_text = f"Tool error: {exc}"
        self.tool_calls.append({"name": name, "args": args, "output": output_text})
        model_visible_output = _model_visible_tool_output(name, output_text)
        yield sse.tool_result(name, args, model_visible_output[:_TOOL_OUTPUT_PREVIEW_CHARS])
        yield sse.agent_flow(display, _output_flow_status(output_text))
        self._messages.append(
            ToolMessage(content=model_visible_output[:_TOOL_OUTPUT_PREVIEW_CHARS], tool_call_id=call_id)
        )
