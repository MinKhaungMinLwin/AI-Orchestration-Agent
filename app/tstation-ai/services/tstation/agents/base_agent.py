from abc import ABC
from collections.abc import Callable
from typing import Any, TypeVar
import ast
import json
import logging
import re

from langchain.messages import AIMessageChunk, AIMessage, ToolMessage
from langchain.agents import create_agent
from pydantic import BaseModel, TypeAdapter, ValidationError

from config.tracing import trace_span as _trace_span, truncate_for_trace as _truncate
from services.tstation.tool_summaries import summarize_tool


logger = logging.getLogger(__name__)


def _emit_tool_summary_span(
    config: dict | None,
    *,
    tool_name: str,
    tool_input: dict,
    tool_result: Any,
    tool_status: str,
) -> None:
    """Open a short-lived child span carrying a one-line summary of a tool call.

    The span is named ``🔧 <tool>: <summary>`` so the Langfuse trace tree shows
    the result inline (e.g. ``🔧 search_product_tool: 3 hits → G123``) without
    needing to expand the raw JSON output captured by the LangChain auto-span.

    Silently no-ops when tracing is disabled or when the trace context is
    missing — never raises into the agent stream.
    """
    cfgable = (config or {}).get("configurable", {}) if isinstance(config, dict) else {}
    trace_id = cfgable.get("tstation_trace_id")
    parent_span_id = cfgable.get("tstation_parent_span_id")
    if not trace_id:
        return
    try:
        summary = summarize_tool(tool_name, tool_result)
    except Exception as exc:  # never let summary formatting break the agent loop
        logger.debug("[TRACE] tool summary failed for %s: %s", tool_name, exc)
        summary = f"status={tool_status}"
    span_name = f"🔧 {tool_name}: {summary}"
    with _trace_span(
        span_name,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        input=tool_input,
    ) as _ts:
        _ts.update(output=_truncate({"summary": summary, "status": tool_status}))

T = TypeVar("T")


# Keys stripped from the SSE `tool` event's `output` payload before it reaches
# the FE / dev tools. These are *internal-only* directives meant for the LLM's
# deterministic guard logic (e.g. `transaction_store_preview_tool` instructing
# the agent to STOP at the location card). The LLM still sees them in the
# original `ToolMessage` content held by LangGraph state; only the SSE-visible
# copy is sanitized so analysts / browser dev tools / log streams never expose
# the raw guard text.
_SSE_TOOL_OUTPUT_STRIPPED_KEYS: frozenset[str] = frozenset({"instruction_to_agent"})


def _strip_keys_in_place(node: Any, keys: frozenset[str]) -> None:
    if isinstance(node, dict):
        for k in list(node.keys()):
            if k in keys:
                del node[k]
            else:
                _strip_keys_in_place(node[k], keys)
    elif isinstance(node, list):
        for item in node:
            _strip_keys_in_place(item, keys)


def _sanitize_tool_output_for_sse(content: Any) -> Any:
    """Return a copy of the tool result with internal-only keys removed.

    Falls back to the original value on parse error so SSE delivery never
    breaks even if a tool emits malformed JSON.
    """
    if not isinstance(content, str):
        return content
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content
    _strip_keys_in_place(parsed, _SSE_TOOL_OUTPUT_STRIPPED_KEYS)
    try:
        return json.dumps(parsed, ensure_ascii=False)
    except (TypeError, ValueError):
        return content


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
# Matches trailing `quickReplies: [...]` that the model sometimes appends when it fails
# to emit a proper fenced JSON block (plain-text fallback path in stream()).
_INLINE_QUICK_REPLIES_RE = re.compile(r"\n\s*quickReplies:\s*(\[.*?\])\s*$", re.DOTALL | re.IGNORECASE)
_UNQUOTED_JSON_KEY_RE = re.compile(r"(?<=[{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")


# Validation 실패 시 사용자에게 빈 화면(silent dead-end) 대신 보여줄 안내.
# OUTPUT_TEMPLATE을 emit하려다 schema 검증이 깨진 경우, FE는 stream 종료
# 토큰(\n\n)만 받아 "응답 없음"으로 보였다. quickReply로 fallback하면
# 최소한 사용자가 다음 행동을 선택할 수 있다.
_VALIDATION_FALLBACK_MESSAGE = (
    "죄송합니다, 답변을 정리하던 중 일시적인 문제가 발생했어요.\n\n"
    "잠시 후 다시 시도해 주시거나 아래 버튼으로 다른 도움을 받아보세요."
)
_VALIDATION_FALLBACK_QUICK_REPLIES = [
    {"label": "다시 시도", "domain": "LEADING"},
    {"label": "상담사 연결", "domain": "SUPPORT"},
    {"label": "처음으로", "domain": "LEADING"},
]


def _build_validated_quickreply_data(assistant_response: str, chips: list[dict]) -> dict:
    """Build a quickReply `data` payload through QuickReplyTemplate validation.

    Fallback emit paths (validation failure, prose mode, validation_fallback) bypass
    pydantic instantiation and yield dicts directly, which means QuickReplyTemplate
    validators (qty enforcement, satisfaction-chip enforcement) never fire. This
    helper runs the payload through QuickReplyTemplate so the same deterministic
    guards apply on the fallback paths.

    Returns the validated `data` dict (assistantResponse + quickReplies). Schema
    failures fall back to the raw input so we never harden an emit path into a
    crash — but validators that mutate (e.g., satisfaction auto-fix) take effect.
    """
    from services.tstation.agents.templates.schemas import QuickReplyChip, QuickReplyTemplate

    try:
        chip_objs = [QuickReplyChip(**c) if isinstance(c, dict) else c for c in chips]
        tpl = QuickReplyTemplate(assistantResponse=assistant_response, quickReplies=chip_objs)
        return tpl.model_dump()
    except ValidationError as exc:
        logger.warning(
            "[_build_validated_quickreply_data] schema validation failed, falling back to raw: %s",
            exc.errors(include_url=False),
        )
        return {"assistantResponse": assistant_response, "quickReplies": chips}

# 주문 수량을 묻는 quickReply 는 항상 1/2/3/4 4개 chip 을 노출해야 한다.
# LLM 이 가끔 일부 chip 을 누락 (예: ["4개","2개"]) 하거나 중복 (["2개","2개"]) 시켜
# UX 가 깨지므로 결정적 후처리로 정규화한다.
_CANONICAL_QTY_CHIPS = ("1개", "2개", "3개", "4개")
_QTY_CHIP_LABEL_RE = re.compile(r"^\s*\d+\s*개\s*$")
_QTY_PROMPT_RE = re.compile(
    r"주문\s*수량"
    r"|몇\s*개\s*(?:주문|구매|확인|예약|받|살|쓸|장바구니|결제|보내|들여|선택)"
    r"|수량(?:을\s*(?:알려|선택|입력|말씀)|이\s*어떻|은\s*\d+\s*개)"
    r"|수량\s*[:：]"
)


def _normalize_qty_quick_replies(payload: dict) -> None:
    """주문 수량 질문 시 chip 을 결정적으로 ["1개","2개","3개","4개"] 로 강제.

    Trigger 조건 (모두 만족):
    - template == "quickReply"
    - assistantResponse 가 qty-asking 패턴 (`_QTY_PROMPT_RE`) 매칭
    - 기존 chip 이 모두 "N개" 모양 (혼합/비 qty chip 이면 보호하기 위해 skip)
    """
    if payload.get("template") != "quickReply":
        return
    data = payload.get("data")
    if not isinstance(data, dict):
        return
    assistant_response = data.get("assistantResponse") or ""
    if not _QTY_PROMPT_RE.search(assistant_response):
        return
    chips = data.get("quickReplies")
    chip_list = chips if isinstance(chips, list) else []
    labels = [c.get("label") if isinstance(c, dict) else c for c in chip_list]
    qty_shaped = [
        isinstance(label, str) and bool(_QTY_CHIP_LABEL_RE.match(label))
        for label in labels
    ]
    # 빈 배열이거나 chip 이 모두 qty 모양일 때만 정규화 — 다른 라벨이 섞이면 보존.
    if labels and not all(qty_shaped):
        return
    if tuple(labels) == _CANONICAL_QTY_CHIPS:
        return  # 이미 정상
    domains = {
        c.get("domain")
        for c in chip_list
        if isinstance(c, dict) and c.get("domain")
    }
    domain = next(iter(domains)) if len(domains) == 1 else "TRANSACTION"
    data["quickReplies"] = [
        {"label": label, "domain": domain} for label in _CANONICAL_QTY_CHIPS
    ]
    logger.info(
        "[base_agent] Normalized qty quickReply chips: was %s, now %s",
        labels,
        list(_CANONICAL_QTY_CHIPS),
    )


class _AssistantResponseStreamer:
    """OUTPUT_TEMPLATE 응답에서 `assistantResponse` 값만 토큰 단위로 흘려보내는
    state machine. 이게 없으면 LeadingAgent처럼 fenced JSON을 출력하는 agent는
    JSON이 닫힐 때까지 모든 토큰을 버퍼링하므로, 사용자는 답이 다 만들어질 때까지
    스피너만 본다 (체감 latency의 핵심 원인).
    """

    _KEY = '"assistantResponse"'
    _ESCAPE_MAP = {'"': '"', "\\": "\\", "/": "/", "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}

    def __init__(self):
        self._buf = ""
        self._state = "SEARCHING"
        self._streamed_text = ""

    @property
    def streamed_any(self) -> bool:
        return bool(self._streamed_text)

    @property
    def streamed_text(self) -> str:
        return self._streamed_text

    @property
    def finished(self) -> bool:
        return self._state == "DONE"

    def feed(self, chunk: str) -> str:
        out: list[str] = []
        self._buf += chunk
        while True:
            if self._state == "SEARCHING":
                idx = self._buf.find(self._KEY)
                if idx < 0:
                    # key가 청크 경계에 걸칠 수 있으니 끝부분만 남긴다.
                    keep = len(self._KEY) - 1
                    if len(self._buf) > keep:
                        self._buf = self._buf[-keep:]
                    break
                self._buf = self._buf[idx + len(self._KEY):]
                self._state = "AWAIT_COLON"
            elif self._state == "AWAIT_COLON":
                idx = self._buf.find(":")
                if idx < 0:
                    break
                self._buf = self._buf[idx + 1:]
                self._state = "AWAIT_QUOTE"
            elif self._state == "AWAIT_QUOTE":
                idx = self._buf.find('"')
                if idx < 0:
                    break
                self._buf = self._buf[idx + 1:]
                self._state = "INSIDE"
            elif self._state == "INSIDE":
                emitted, consumed, finished = self._decode_inside(self._buf)
                if emitted:
                    out.append(emitted)
                self._buf = self._buf[consumed:]
                if finished:
                    self._state = "DONE"
                break
            else:
                self._buf = ""
                break
        result = "".join(out)
        if result:
            self._streamed_text += result
        return result

    @classmethod
    def _decode_inside(cls, s: str) -> tuple[str, int, bool]:
        out: list[str] = []
        i = 0
        n = len(s)
        while i < n:
            ch = s[i]
            if ch == '"':
                return ("".join(out), i + 1, True)
            if ch == "\\":
                if i + 1 >= n:
                    break
                esc = s[i + 1]
                if esc == "u":
                    if i + 6 > n:
                        break
                    try:
                        out.append(chr(int(s[i + 2:i + 6], 16)))
                    except ValueError:
                        out.append(s[i:i + 6])
                    i += 6
                    continue
                out.append(cls._ESCAPE_MAP.get(esc, esc))
                i += 2
                continue
            out.append(ch)
            i += 1
        return ("".join(out), i, False)


TOOL_DISPLAY_NAMES: dict[str, str] = {
    # Discovery
    "check_compatibility_tool": "차량-타이어 호환 확인 중...",
    "search_product_tool": "상품 검색 중...",
    "get_user_vehicles_tool": "차량 정보 조회 중...",
    "get_my_cars_tool": "내 차량 조회 중...",
    "search_car_model_tool": "차량 모델 검색 중...",
    "search_car_model_groups_tool": "차종 모델 검색 중...",
    "get_car_trims_tool": "차량 트림 조회 중...",
    "get_product_description_tool": "상품 상세 정보 조회 중...",
    "get_products_recommendations_tool": "상품 추천 조회 중...",
    "get_events_tool": "이벤트 목록 조회 중...",
    "get_deals_tool": "기획전 목록 조회 중...",
    "get_event_applicable_products_tool": "이벤트 적용 상품 조회 중...",
    "get_product_applicable_events_tool": "상품 적용 이벤트 조회 중...",
    "compare_discount_tool": "할인 가격 비교 중...",
    "search_youtube_video_tool": "유튜브 영상 검색 중...",
    # Transaction
    "get_final_price_tool": "가격 정보 조회 중...",
    "get_my_coupons_tool": "내 쿠폰 조회 중...",
    "get_logistics_inventory_tool": "재고 확인 중...",
    "get_store_inventory_tool": "매장 재고 확인 중...",
    "search_place_tool": "위치 검색 중...",
    "get_nearby_stores_tool": "주변 매장 검색 중...",
    "get_store_list_tool": "매장 목록 조회 중...",
    "get_store_detail_tool": "매장 상세 정보 조회 중...",
    "save_to_cart_tool": "장바구니에 담는 중...",
    "quick_order_tool": "주문서 작성 중...",
    "get_order_status_tool": "주문 현황 조회 중...",
    "get_orders_of_user_tool": "주문 내역 조회 중...",
    # Support
    "get_faq_tool": "자주 묻는 질문 검색 중...",
    "search_faq_rag_tool": "질문 검색 중...",
    "escalate_tool": "상담사 연결 중...",
    "transfer_to_qna_tool": "1:1 문의 페이지 준비 중...",
}


class BaseAgent(ABC):
    """Base agent class with streaming support for agent name and AF (Agent Function) mapping."""

    TOOL_TO_AF_MAP: dict[str, str] = {}
    TOOL_TO_TEMPLATE_MAP: dict[str, str] = {}
    OUTPUT_TEMPLATE: Any = None

    def __init__(self, model, tools: list | None = None, system_prompt: str | Callable[[], str] = "", name: str = ""):
        self.name = name
        self._model = model
        self._tools = tools
        self._system_prompt = system_prompt
        self._agent = self._build_agent()

    def _build_agent(self):
        prompt = self._system_prompt() if callable(self._system_prompt) else self._system_prompt
        self._system_prompt_chars = len(prompt or "")
        return create_agent(
            model=self._model,
            tools=self._tools,
            # Keep LangGraph debug stream off in runtime to avoid noisy
            # `[values]` / `[updates]` payload dumps in container logs.
            debug=False,
            system_prompt=prompt,
            name=self.name,
        )

    @property
    def system_prompt_chars(self) -> int:
        return getattr(self, "_system_prompt_chars", 0)

    def invoke(self, messages: list[dict], config: dict | None = None) -> str:
        agent = self._agent
        result = agent.invoke({"messages": messages}, config=config)
        return result["messages"][-1].content

    def stream(self, messages: list[dict], config: dict | None = None):
        """
        Supported Stream modes:
        - status: Lifecycle markers — thinking (start), answering (before first token)
        - agent_flow: Agent name or AF when active (for UI display)
        - tokens: AI response tokens
        - message: Agent messages with agent name
        - tool_start: Emitted before a tool runs, with display_name for UI typing indicator
        - tool: Tool execution results with tool name, input, and output
        - data: Final UI template payload from structured response
        """
        agent = self._agent
        tool_calls_map: dict[str, dict] = {}
        answering_emitted = False
        prompt_template = self.OUTPUT_TEMPLATE
        suppress_tokens = prompt_template is not None
        accumulated_text = ""
        accumulated_tool_data: list[dict] = []
        response_streamer = _AssistantResponseStreamer() if suppress_tokens else None

        yield {"type": "status", "status": "생각 중..."}

        speculative_guard = (config or {}).get("configurable", {}).get("speculative_tool_guard", {})
        confirm_event = speculative_guard.get("confirm_event")
        wait_for_confirmation = speculative_guard.get("wait_for_confirmation")
        mutating_tools = set(speculative_guard.get("mutating_tools") or [])

        for mode, chunk in agent.stream(
            {"messages": messages},
            stream_mode=["messages", "updates"],
            config=config,
        ):
            if mode == "messages":
                token, _ = chunk
                if isinstance(token, AIMessageChunk) and token.text:
                    if suppress_tokens:
                        accumulated_text += token.text
                        streamed = response_streamer.feed(token.text)
                        if streamed:
                            if not answering_emitted:
                                yield {"type": "status", "status": "답변 중..."}
                                answering_emitted = True
                            yield {"type": "token", "content": streamed}
                        continue
                    if not answering_emitted:
                        yield {"type": "status", "status": "답변 중..."}
                        answering_emitted = True
                    yield {"type": "token", "content": token.text}

            elif mode == "updates":
                for node, update in chunk.items():
                    if "messages" not in update:
                        continue
                    message = update["messages"][-1]
                    if isinstance(message, AIMessage):
                        if hasattr(message, "tool_calls") and message.tool_calls:
                            for tc in message.tool_calls:
                                tool_name = tc["name"]
                                tool_calls_map[tc["id"]] = {"name": tool_name, "args": tc.get("args", {})}
                                if confirm_event is not None and tool_name in mutating_tools and not confirm_event.is_set():
                                    logger.info("[%s] Waiting for speculative confirmation before %s", self.name, tool_name)
                                    if wait_for_confirmation is not None and not wait_for_confirmation():
                                        logger.info("[%s] Speculative route rejected before %s", self.name, tool_name)
                                        return
                                    if wait_for_confirmation is None:
                                        confirm_event.wait()
                                display_name = TOOL_DISPLAY_NAMES.get(tool_name, "답변 중...")
                                yield {
                                    "type": "status",
                                    "status": "tool_start",
                                    "tool": tool_name,
                                    "display_name": display_name,
                                }
                        if suppress_tokens:
                            continue
                        yield {
                            "type": "message",
                            "content": message.content,
                            "node": node,
                            "agent": self.name,
                        }
                    elif isinstance(message, ToolMessage):
                        af = self.TOOL_TO_AF_MAP.get(message.name, "Unknown")
                        tool_status = "success"
                        tool_result: Any = None
                        try:
                            tool_result = (
                                json.loads(message.content) if isinstance(message.content, str) else message.content
                            )
                            if isinstance(tool_result, dict):
                                tool_status = tool_result.get("status", "success")
                        except (json.JSONDecodeError, TypeError):
                            pass
                        tool_input = tool_calls_map.get(message.tool_call_id, {})
                        if tool_result is not None:
                            # Capture input args alongside the result so the
                            # template mapper can correlate same-turn tool calls
                            # by shop_id / cal_day (e.g., merge get_store_detail
                            # data into a get_store_list location card).
                            accumulated_tool_data.append({
                                "tool": message.name,
                                "data": tool_result,
                                "args": tool_input.get("args", {}),
                            })
                        # Manual Langfuse span with a one-line summary so the
                        # trace tree shows what the tool returned at a glance.
                        # Raw output is still captured by LangChain's auto-span;
                        # this layer is purely for analyst readability.
                        _emit_tool_summary_span(
                            config,
                            tool_name=message.name,
                            tool_input=tool_input.get("args", {}),
                            tool_result=tool_result,
                            tool_status=tool_status,
                        )
                        yield {"type": "agent_flow", "agent": f"[{af} AF]", "agent_class": self.name, "status": tool_status}
                        yield {
                            "type": "tool",
                            "input": tool_input.get("args", {}),
                            "output": _sanitize_tool_output_for_sse(message.content),
                            "node": node,
                            "tool": message.name,
                        }

        # Phase 2B: prefer code-based template mapping over LLM fenced JSON.
        # When a deterministically-mappable tool was used, build the data event
        # in code from accumulated_tool_data — saves the LLM from emitting the
        # full FE JSON payload (the dominant 2nd-call output token cost).
        code_event = self._try_code_template(accumulated_tool_data, response_streamer, accumulated_text)
        if code_event is not None:
            code_event["template_source"] = "code_mapper"
            assistant_response = self._get_assistant_response(code_event)
            already_streamed = response_streamer is not None and response_streamer.streamed_any
            if assistant_response:
                if not answering_emitted:
                    yield {"type": "status", "status": "답변 중..."}
                    answering_emitted = True
                if not already_streamed:
                    yield {"type": "token", "content": assistant_response}
                yield {
                    "type": "message",
                    "content": assistant_response,
                    "agent": self.name,
                }
            yield code_event
            yield {"type": "token", "content": "\n\n"}
            return

        if prompt_template is not None and accumulated_text:
            data_event = self._build_data_event_from_text(accumulated_text, prompt_template)
            already_streamed = response_streamer is not None and response_streamer.streamed_any
            if data_event is not None:
                # LLM 이 product 템플릿을 직접 emit 한 경우, tags 결정형 주입 +
                # 스키마 외 hallucinated 필드 (comfort 등) 제거. 다른 템플릿은 no-op.
                from services.tstation.template_mapper import inject_product_tags_and_sanitize
                inject_product_tags_and_sanitize(data_event, accumulated_tool_data)
                assistant_response = self._get_assistant_response(data_event)
                if assistant_response:
                    if not answering_emitted:
                        yield {"type": "status", "status": "답변 중..."}
                        answering_emitted = True
                    # 점진적 streaming으로 이미 prose를 보낸 경우 token 재전송은
                    # 화면에 응답이 두 번 쌓이게 만든다.
                    if not already_streamed:
                        yield {"type": "token", "content": assistant_response}
                    yield {
                        "type": "message",
                        "content": assistant_response,
                        "agent": self.name,
                    }
                yield data_event
            else:
                # If any tool returned a pre-built output_payload, use it directly
                # rather than falling through to generic fallback. This handles
                # reasoning models that consistently emit plain text instead of
                # the required fenced JSON block.
                _tool_payload_used = False
                for _td in reversed(accumulated_tool_data):
                    _tool_data = _td.get("data") or {}
                    _payload_str = (_tool_data.get("data") or {}).get("output_payload")
                    if _payload_str:
                        try:
                            _payload = json.loads(_payload_str)
                            if not answering_emitted:
                                yield {"type": "status", "status": "답변 중..."}
                                answering_emitted = True
                            yield _payload
                            _tool_payload_used = True
                        except Exception:
                            pass
                        break
                if not _tool_payload_used:
                    # _build_data_event_from_text가 이미 error 로그를 남겼다.
                    # 여기서는 빈 \n\n만 보내는 대신 사용자에게 fallback quickReply를
                    # 노출해 silent dead-end UX를 방지한다.
                    if not answering_emitted:
                        yield {"type": "status", "status": "답변 중..."}
                        answering_emitted = True
                    if already_streamed:
                        # prose는 이미 흘러갔으므로 fallback 메시지 중복 송출은 피하고
                        # 마무리용 quickReply chips만 추가한다.
                        yield {
                            "type": "data",
                            "template": "quickReply",
                            "data": _build_validated_quickreply_data(
                                response_streamer.streamed_text,
                                list(_VALIDATION_FALLBACK_QUICK_REPLIES),
                            ),
                            "nextAction": {"type": "stop", "domain": None},
                        }
                    else:
                        # Phase 2B: LLM may have emitted plain prose (PROSE MODE) when
                        # template_mapper couldn't build a card — e.g., zero-result
                        # search where the model honored the "prose mode" rule but
                        # the mapper found no items to render. Treat the raw text
                        # as the assistant's prose answer rather than showing the
                        # generic validation-failure apology.
                        prose_only = accumulated_text.strip()
                        if prose_only and self._extract_fenced_json(accumulated_text) is None:
                            # Model emitted plain text instead of fenced JSON. Strip any
                            # trailing `quickReplies: [...]` annotation and parse chips.
                            chips: list[dict] = []
                            m = _INLINE_QUICK_REPLIES_RE.search(prose_only)
                            if m:
                                prose_only = prose_only[:m.start()].strip()
                                try:
                                    raw = json.loads(m.group(1))
                                    chips = [
                                        {"label": c, "domain": None} if isinstance(c, str) else c
                                        for c in raw if c
                                    ]
                                except (json.JSONDecodeError, TypeError):
                                    pass
                            yield {"type": "token", "content": prose_only}
                            yield {
                                "type": "message",
                                "content": prose_only,
                                "agent": self.name,
                            }
                            yield {
                                "type": "data",
                                "template": "quickReply",
                                "data": _build_validated_quickreply_data(prose_only, chips),
                                "nextAction": {"type": "stop", "domain": None},
                            }
                        else:
                            yield from self._yield_validation_fallback()

        yield {"type": "token", "content": "\n\n"}

    def _yield_validation_fallback(self):
        """OUTPUT_TEMPLATE 검증 실패 시 사용자 가시 fallback 이벤트 시퀀스.

        성공 경로(token → message → data)와 같은 형태로 emit하여
        FE/coordinator가 일관되게 처리할 수 있게 한다.
        """
        message = _VALIDATION_FALLBACK_MESSAGE
        yield {"type": "token", "content": message}
        yield {
            "type": "message",
            "content": message,
            "agent": self.name,
        }
        yield {
            "type": "data",
            "template": "quickReply",
            "data": _build_validated_quickreply_data(
                message, list(_VALIDATION_FALLBACK_QUICK_REPLIES)
            ),
            "nextAction": {"type": "stop", "domain": None},
        }

    def _build_data_event(self, structured_response: BaseModel | dict | None) -> dict | None:
        """Convert structured response into the FE `data` event shape."""
        if structured_response is None:
            return None

        payload = (
            structured_response.model_dump() if isinstance(structured_response, BaseModel) else structured_response
        )
        if not isinstance(payload, dict):
            logger.warning("[%s] Structured response is not a dict — skipping data event", self.name)
            return None

        if payload.get("type") != "data":
            logger.warning("[%s] Structured response missing type='data' — skipping", self.name)
            return None

        if not isinstance(payload.get("template"), str):
            logger.warning("[%s] Structured response missing template — skipping", self.name)
            return None

        if not isinstance(payload.get("data"), dict):
            logger.warning("[%s] Structured response missing data object — skipping", self.name)
            return None

        _normalize_qty_quick_replies(payload)
        return payload

    @staticmethod
    def _get_assistant_response(data_event: dict) -> str:
        data = data_event.get("data", {})
        if not isinstance(data, dict):
            return ""
        assistant_response = data.get("assistantResponse")
        return assistant_response if isinstance(assistant_response, str) else ""

    def _build_data_event_from_text(self, text: str, template_cls: Any) -> dict | None:
        """Extract a fenced JSON object from `text`, validate it against `template_cls`,
        and return a `data` event ready to yield. Returns None on any failure.

        On failure, logs at error level so missed structured-output turns are observable
        (the coordinator will fall back to the legacy UI Template Agent path).
        """
        raw = self._extract_fenced_json(text)
        if raw is None:
            logger.error(
                "[%s] No fenced JSON block found in agent response — falling back to legacy UI path",
                self.name,
            )
            return None
        parsed = self._parse_agent_json(raw)
        if parsed is None:
            logger.error("[%s] Invalid JSON in agent response", self.name)
            return None
        try:
            validated = TypeAdapter(template_cls).validate_python(parsed)
        except ValidationError as exc:
            logger.error(
                "[%s] Output JSON failed schema validation (template=%s): %s",
                self.name,
                parsed.get("template") if isinstance(parsed, dict) else None,
                exc.errors(include_url=False),
            )
            return None
        return self._build_data_event(validated)

    @staticmethod
    def _parse_agent_json(raw: str) -> Any | None:
        """Parse LLM JSON, accepting common JSON-like slips without hiding real failures."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError as strict_exc:
            # Models sometimes emit JS/Python-ish dicts: {type: 'data'}.
            normalized = _UNQUOTED_JSON_KEY_RE.sub(r' "\1":', raw)
            try:
                return json.loads(normalized)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(normalized)
                except (SyntaxError, ValueError, TypeError) as loose_exc:
                    logger.debug("Agent JSON parse failed: strict=%s loose=%s", strict_exc, loose_exc)
                    return None
                return parsed

    @staticmethod
    def _extract_fenced_json(text: str) -> str | None:
        matches = _FENCED_JSON_RE.findall(text)
        return matches[-1] if matches else None

    @staticmethod
    def _try_code_template(
        accumulated_tool_data: list[dict],
        response_streamer: "_AssistantResponseStreamer | None",
        accumulated_text: str,
    ) -> dict | None:
        """Attempt deterministic FE-template construction from tool outputs.

        Returns a `data` event dict if any tool in accumulated_tool_data has a
        registered code mapper AND the mapper produced a valid event.
        Returns None to signal "fall through to fenced-JSON path".

        If the LLM emitted an explicit fenced JSON block, defer to it — the
        agent has chosen its own template (e.g. comparison intent → quickReply
        instead of the default cheapestProduct mapper).

        listCar exception: when get_my_cars_tool / get_user_vehicles_tool ran,
        always use the deterministic mapper even if the LLM emitted fenced JSON.
        The mapper enriches info with car_maker prefix and keeps info/description
        consistent; LLM-authored JSON drifts in format between turns.

        Store-detail exception: when get_store_detail_tool ran, the LLM's
        quickReply often slips into PROSE-MODE ("매장 상세정보를 확인했어요.")
        and the rich detail fields never reach the user — only QC catches it.
        _map_store_detail_info's own guards defer back to the LLM for Flow 5.1
        (date-specific datepick / no-slot apology).
        """
        if not accumulated_tool_data:
            return None
        _FORCE_CODE_MAPPER_TOOLS = (
            "get_my_cars_tool",
            "get_user_vehicles_tool",
            "get_store_detail_tool",
            "get_stores_with_time_filter_tool",
            # Product list tools — items 있으면 product 카드 강제. LLM 이
            # "비슷한 가격대 더 추천" 같은 follow-up 발화에서 fenced JSON 으로
            # quickReply 만 emit 하고 product 카드를 건너뛰는 회귀 차단.
            # items 0 (검색 0건) 케이스는 mapper 가 None 반환 → LLM prose fallback.
            "search_product_tool",
            "get_products_recommendations_tool",
            "get_newest_products_tool",
            "get_best_selling_products_tool",
        )
        has_force_code_mapper_tool = any(
            e.get("tool") in _FORCE_CODE_MAPPER_TOOLS for e in accumulated_tool_data
        )
        # Deterministic guard override: when a tool response carries
        # `instruction_to_agent` (e.g. transaction_store_preview_tool tier=none
        # region/multi-candidate case), the LLM's own template choice may slip
        # into a generic `quickReply` and bury the candidate list. Force the
        # code mapper so the structured card (`location`) reaches the FE.
        if not has_force_code_mapper_tool:
            for entry in accumulated_tool_data:
                output = entry.get("output")
                if isinstance(output, str) and '"instruction_to_agent"' in output:
                    has_force_code_mapper_tool = True
                    break
                if isinstance(output, dict):
                    data = output.get("data") if isinstance(output.get("data"), dict) else output
                    if isinstance(data, dict) and data.get("instruction_to_agent"):
                        has_force_code_mapper_tool = True
                        break
        if not has_force_code_mapper_tool and BaseAgent._extract_fenced_json(accumulated_text) is not None:
            return None
        from services.tstation.template_mapper import _MAPPERS, try_build_template
        if not any(e.get("tool") in _MAPPERS for e in accumulated_tool_data):
            return None
        prose = (
            response_streamer.streamed_text
            if response_streamer is not None and response_streamer.streamed_any
            else accumulated_text
        )
        return try_build_template(accumulated_tool_data, prose)

    def stream_template(self, messages: list[dict], config: dict | None = None):
        """
        Stream that transforms tool calls into data template events.
        Yields ONLY data events (no token or agent_flow events).

        Use this when you want to format tool outputs as UI templates directly.
        """
        import json
        import logging

        logger = logging.getLogger(__name__)
        agent = self._agent

        tool_called = False

        for mode, chunk in agent.stream(
            {"messages": messages},
            stream_mode=["messages", "updates"],
            config=config,
        ):
            if mode == "updates":
                for node, update in chunk.items():
                    message = update["messages"][-1]
                    if isinstance(message, ToolMessage):
                        tool_called = True
                        template_name = self.TOOL_TO_TEMPLATE_MAP.get(message.name)
                        if not template_name:
                            logger.warning(f"[UI_TEMPLATE] Tool {message.name} has no template mapping")
                            continue
                        # Parse tool output (message.content is JSON string)
                        try:
                            tool_output = json.loads(message.content)
                            tool_data = tool_output.get("data", {})
                        except (json.JSONDecodeError, TypeError):
                            logger.warning(f"[UI_TEMPLATE] Failed to parse tool output for {message.name}")
                            tool_data = {}

                        # Skip if tool_data is null or empty
                        if not tool_data:
                            logger.warning(f"[UI_TEMPLATE] Empty tool_data for {message.name}, skipping")
                            continue

                        # Yield data event with tool's actual output data
                        yield {
                            "type": "data",
                            "template": template_name,
                            "data": tool_data,
                        }

        if not tool_called:
            logger.warning("[UI_TEMPLATE] Agent generated no tool calls — templates not rendered")
