from abc import ABC
from collections.abc import Callable
from typing import TypeVar
import json

from langchain.messages import AIMessageChunk, AIMessage, ToolMessage
from langchain.agents import create_agent


T = TypeVar("T")


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
    "compare_discount_tool": "할인 가격 비교 중...",
    "search_youtube_video_tool": "유튜브 영상 검색 중...",
    # Transaction
    "get_final_price_tool": "가격 정보 조회 중...",
    "get_available_coupons_tool": "사용 가능 쿠폰 조회 중...",
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
    # UI Template
    "quick_reply_tool": "응답 생성 중...",
    "list_car_tool": "차량 목록 준비 중...",
    "list_product_tool": "상품 목록 준비 중...",
    "list_voucher_tool": "쿠폰 목록 준비 중...",
    "list_location_tool": "매장 목록 준비 중...",
    "list_event_tool": "이벤트 목록 준비 중...",
    "list_preview_youtube_tool": "영상 목록 준비 중...",
    "available_dates_tool": "예약 날짜 준비 중...",
    "preorder_tool": "주문서 준비 중...",
    "qna_complete_tool": "문의 페이지 준비 중...",
    "order_complete_tool": "주문 완료 처리 중...",
    "cheapest_product_tool": "가격 비교 결과 준비 중...",
}


class BaseAgent(ABC):
    """Base agent class with streaming support for agent name and AF (Agent Function) mapping."""

    TOOL_TO_AF_MAP: dict[str, str] = {}
    TOOL_TO_TEMPLATE_MAP: dict[str, str] = {}

    def __init__(self, model, tools: list | None = None, system_prompt: str | Callable[[], str] = "", name: str = ""):
        self.name = name
        self._model = model
        self._tools = tools
        self._system_prompt = system_prompt

    def _build_agent(self):
        prompt = self._system_prompt() if callable(self._system_prompt) else self._system_prompt
        return create_agent(
            model=self._model,
            tools=self._tools,
            debug=True,
            system_prompt=prompt,
            name=self.name,
        )

    def invoke(self, messages: list[dict]) -> str:
        agent = self._build_agent()
        result = agent.invoke({"messages": messages})
        return result["messages"][-1].content

    def stream(self, messages: list[dict]):
        """
        Supported Stream modes:
        - status: Lifecycle markers — thinking (start), answering (before first token)
        - agent_flow: Agent name or AF when active (for UI display)
        - tokens: AI response tokens
        - message: Agent messages with agent name
        - tool_start: Emitted before a tool runs, with display_name for UI typing indicator
        - tool: Tool execution results with tool name, input, and output
        """
        agent = self._build_agent()
        tool_calls_map: dict[str, dict] = {}
        answering_emitted = False

        yield {"type": "status", "status": "생각 중..."}

        for mode, chunk in agent.stream(
            {"messages": messages},
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                token, _ = chunk
                if isinstance(token, AIMessageChunk) and token.text:
                    if not answering_emitted:
                        yield {"type": "status", "status": "답변 중..."}
                        answering_emitted = True
                    yield {"type": "token", "content": token.text}

            elif mode == "updates":
                for node, update in chunk.items():
                    message = update["messages"][-1]
                    if isinstance(message, AIMessage):
                        if hasattr(message, "tool_calls") and message.tool_calls:
                            for tc in message.tool_calls:
                                tool_calls_map[tc["id"]] = {"name": tc["name"], "args": tc.get("args", {})}
                                display_name = TOOL_DISPLAY_NAMES.get(tc["name"], "처리 중...")
                                yield {"type": "status", "status": "tool_start", "tool": tc["name"], "display_name": display_name}
                        yield {
                            "type": "message",
                            "content": message.content,
                            "node": node,
                            "agent": self.name,
                        }
                    elif isinstance(message, ToolMessage):
                        af = self.TOOL_TO_AF_MAP.get(message.name, "Unknown")
                        tool_status = "success"
                        try:
                            tool_result = json.loads(message.content) if isinstance(message.content, str) else message.content
                            if isinstance(tool_result, dict):
                                tool_status = tool_result.get("status", "success")
                        except (json.JSONDecodeError, TypeError):
                            pass
                        yield {"type": "agent_flow", "agent": f"[{af} AF]", "status": tool_status}
                        tool_input = tool_calls_map.get(message.tool_call_id, {})
                        yield {
                            "type": "tool",
                            "input": tool_input.get("args", {}),
                            "output": message.content,
                            "node": node,
                            "tool": message.name,
                        }

        yield {"type": "token", "content": "\n\n"}

    def stream_template(self, messages: list[dict]):
        """
        Stream that transforms tool calls into data template events.
        Yields ONLY data events (no token or agent_flow events).

        Use this when you want to format tool outputs as UI templates directly.
        """
        import json
        import logging
        logger = logging.getLogger(__name__)
        agent = self._build_agent()

        tool_called = False

        for mode, chunk in agent.stream(
            {"messages": messages},
            stream_mode=["messages", "updates"],
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
