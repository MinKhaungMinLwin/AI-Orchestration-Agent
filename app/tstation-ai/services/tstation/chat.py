import json
import logging
import re
from typing import ClassVar, Iterator, Optional
from textwrap import dedent

from pydantic import BaseModel, Field
from enum import Enum

from services.tstation.common.tstation_be_client import set_tstation_be_token
from config.env import settings
from fastapi.responses import StreamingResponse
from schemas.tstation.chat import TStationChatRequest, TStationChatResponse
from services.tstation.agents.router import (
    AgentDomain,
    leading_agent,
    discovery_subagent,
    transaction_subagent,
    support_subagent,
)
from common.jwt_utils import get_user_info_from_token
from common.curr_time import get_current_time
from services.tstation.common.pii_guardrail import check_pii, GUARDRAIL_RESPONSE

from services.tstation.agents.g_qc_agent.source_filter import filter_source_data, filter_for_context

logger = logging.getLogger(__name__)


class NextAction(str, Enum):
    STOP = "stop"
    CONTINUE = "continue"


class AgentDecision(BaseModel):
    next_action: NextAction = Field(description="STOP or CONTINUE")
    next_domain: str = Field(description="Next domain if CONTINUE ('null' if STOP)")
    reason: str = Field(description="Reason for decision, using english")


def prompt_router() -> str:
    return dedent(f"""
    Current Time: {get_current_time()}

    You are a domain classifier and decision engine for T-Station AI.

    MODE 1 - Initial Classification: Classify user message into ONE domain.
    MODE 2 - Next Action Decision: After agent completes, decide STOP or CONTINUE.

    DOMAINS:
    - LEADING: Greeting, unclear intent
    - DISCOVERY: Product search, recommendations, vehicle compatibility
    - TRANSACTION: Price, stock, store inventory, store search, purchase, checkout, order tracking, reservation
    - SUPPORT: Warranty, returns, FAQ, human agent

    DECISION RULES:

    DEFAULT: STOP after every agent turn.
    Each agent does its ONE job, returns the result, and waits for the user's next explicit action.
    The user drives every step — agents never auto-chain into the next domain.

    ONLY CONTINUE when the agent was routed to the WRONG domain and cannot complete the task:
    - Transaction Agent has no product search tools → needs goods_no → CONTINUE → DISCOVERY
    - Discovery Agent has no price/order/store tools → CONTINUE → TRANSACTION
    - Discovery Agent says "다른 사이즈로 검색" (internal retry) → CONTINUE → DISCOVERY

    STOP in ALL other cases:
    - Agent completed its task (showed products, stores, prices, schedule, etc.) → STOP
    - Agent is showing a list waiting for user selection (cars, tires, stores) → STOP
    - Agent asks user for any input → STOP
    - Pre-order preview shown → STOP
    - Any confirmation step → STOP

    KEY PRINCIPLE: One agent, one turn, one job. User explicitly triggers the next step.
    """)


def decide_next_action(
    original_messages: list[dict],
    previous_agent_response: str,
    previous_domain: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    trace_id: str | None = None,
) -> AgentDecision:
    from langchain_litellm import ChatLiteLLM
    from langchain_core.messages import SystemMessage, HumanMessage
    from config.tracing import build_trace_config

    llm = ChatLiteLLM(
        api_base=settings.AI_GATEWAY_BASE_URL,
        api_key=settings.AI_GATEWAY_API_KEY,
        model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL}",
    )

    structured_model = llm.with_structured_output(AgentDecision)

    user_message = ""
    for msg in reversed(original_messages):
        if msg.get("role") == "user":
            user_message = msg.get("content", "")
            break

    system_msg = SystemMessage(content=prompt_router())
    human_msg = HumanMessage(
        content=dedent(f"""
        Original User Request: {user_message}

        Previous Agent Domain: {previous_domain}

        Previous Agent Response:
        {previous_agent_response}

        Please decide the next action.
    """)
    )

    trace_config = build_trace_config(
        run_name="decide_next_action",
        session_id=session_id,
        user_id=user_id,
        trace_id=trace_id,
        tags=["router", "decide_next_action"],
    )

    try:
        result: AgentDecision = structured_model.invoke([system_msg, human_msg], config=trace_config)
        return result
    except Exception as e:
        logger.warning(f"[DECISION] LLM decision failed: {e}")
        # Fallback: stop if cannot decide
        return AgentDecision(
            next_action=NextAction.STOP,
            next_domain=None,
            reason=f"Decision failed: {str(e)[:100]}",
        )


class MultiAgentDomain(BaseModel):
    """Router result that supports multiple domains (multi-intent)."""

    class Domain(str, Enum):
        LEADING = "leading"
        DISCOVERY = "discovery"
        TRANSACTION = "transaction"
        SUPPORT = "support"

    reason: str = Field(description="Reason for the classification, using english")
    domains: list[Domain] = Field(description="List of domains detected in the request, ordered by priority")
    user_behavior: str = Field(
        description=(
            "What the user is currently doing in this conversation turn, inferred from full history. "
            "Examples: 'selecting car from list shown in previous turn', "
            "'providing car number to resolve vehicle', "
            "'confirming product selection', 'responding to recommendation', "
            "'fresh start — first message'. "
            "Always provide a value."
        ),
    )
    next_action: str = Field(
        description=(
            "The specific action the target agent should perform immediately based on conversation state. "
            "Be concrete — reference tool name and key param if possible. "
            "Examples: 'match car_no 123가4566 from previous car list → extract tire_size_fr → call get_products_recommendations_tool', "
            "'user already has goods_no from context → call get_final_price_tool directly', "
            "'call get_my_cars_tool with mbr_no from user context'. "
            "Use 'proceed normally' if action is obvious from the user message alone."
        ),
    )
    flow: str = Field(
        description=(
            "One-line summary of the conversation journey so far. "
            "Examples: 'user requested tires → agent showed 2 cars → user is selecting car', "
            "'user asked price → discovery found goods_no → transaction showing price', "
            "'fresh start — no prior context'. "
            "Keep under 120 chars."
        ),
    )

    def get_agents(self):
        """Return list of agents based on detected domains."""
        agent_map = {
            self.Domain.DISCOVERY: discovery_subagent,
            self.Domain.TRANSACTION: transaction_subagent,
            self.Domain.SUPPORT: support_subagent,
            self.Domain.LEADING: leading_agent,
        }
        return [agent_map[d] for d in self.domains if d in agent_map]


def prompt_router_multi() -> str:
    """Classification prompt that detects multi-intent with flow sequences and conversation context."""
    return f"""
Current Time: {get_current_time()}

You are a domain classifier for T-Station AI (Hankook Tire).
Read the FULL conversation history to classify the current user message.

Produce 4 outputs:
1. domains — ONE OR MORE domains based on detected intents (ordered by priority)
2. reason — why you chose these domains
3. user_behavior — what the user is currently doing based on the full conversation (e.g. "selecting car from list shown in previous turn", "providing tire size", "confirming product")
4. next_action — the concrete action the agent should take immediately (e.g. "match car_no 123가4566 from car list → extract tire_size_fr → call get_products_recommendations_tool")
5. flow — one-line summary of the journey so far (e.g. "user requested tires → agent showed 2 cars → user selecting")

IMPORTANT: user_behavior and next_action must reflect the FULL conversation context, not just the current message.
If the user is responding to a previous agent question (e.g. selecting a car, confirming a product, providing a car number),
identify WHAT they are responding to and set next_action accordingly.

Also identify the FLOW SEQUENCE (ordered list of domains) for the request.

DOMAINS:
- TRANSACTION: Price, stock (logistics/store), inventory, store availability, store search by location/name, purchase, checkout, order tracking, reservation
- SUPPORT: FAQ, warranty, returns, policies, maintenance, human agent
- DISCOVERY: Product search by name, recommendations, vehicle-tire compatibility check, features, product video reviews, YouTube video search
- LEADING: Greeting, unclear intent

====================================================
DOMAIN ROUTING EXAMPLES
====================================================

DISCOVERY — product search, recommendation, compatibility (no goods_no yet):
1. "i want to buy tires for 29조3344" → DISCOVERY (lookup car → recommend tires → STOP, wait for user)
2. "쏘나타에 맞는 타이어 추천해줘" → DISCOVERY
3. "벤투스 S2 가격" / "Dynapro HPX 얼마야?" → DISCOVERY (resolve goods_no first → STOP)
4. "벤투스 S2 재고 확인해줘" → DISCOVERY (resolve goods_no → STOP)
5. "벤투스 S2 AS 살 수 있는 매장" → DISCOVERY (resolve goods_no → STOP)
6. "이벤트 알려줘" / "기획전 정보" → DISCOVERY
7. "타이어 리뷰 영상 보여줘" → DISCOVERY
8. "추천 타이어들 가격 비교해줘" → DISCOVERY (compare_discount_tool is in Discovery)

TRANSACTION — price/stock/store/order with goods_no already known in context:
1. "{{goods_no}} 가격 얼마야?" → TRANSACTION
2. "주문할게" / "바로 주문할게" → TRANSACTION
3. "장바구니에 담아줘" → TRANSACTION
4. "강남 매장 찾아줘" / "근처 매장" → TRANSACTION
5. "한남점 예약 가능한 날짜 알려줘" → TRANSACTION
6. "주문 내역 확인해줘" → TRANSACTION
7. "티스테이션 한남점 선택할게" → TRANSACTION (store selection continuation)

SUPPORT — policy, warranty, human agent:
1. "보증 정책 알려줘" / "반품 가능해?" → SUPPORT
2. "1:1 문의 작성해줘" / "상담원 연결" → SUPPORT

LEADING — greeting, unclear intent:
1. "안녕하세요" / "뭘 도와줄 수 있어?" → LEADING

====================================================
DECISION RULES
====================================================

CORE RULE: Classify into EXACTLY ONE domain per turn.
Each domain does its ONE job and stops. User drives every next step.

DISCOVERY when:
- Product search by name/keyword (goods_no not yet known)
- Tire recommendation (vehicle-specific or general)
- Compatibility check
- Product specs/features/tech
- Price/stock/store queries where goods_no is NOT yet known → DISCOVERY resolves goods_no first, then STOP
- Event/deal/video content

TRANSACTION when:
- goods_no is already known in conversation context (G + 12 digits)
- Store search by location/name
- Store schedule / reservation slots
- Order creation, cart save, order tracking
- Pre-order confirmation flow

⚠️ "buy/order/purchase" with product NAME (not goods_no) → DISCOVERY first to find goods_no, then STOP and wait for user.
⚠️ "buy/order/purchase" with goods_no already in context → TRANSACTION directly.

SUPPORT when: warranty, returns, policy, human agent, 1:1 inquiry
LEADING when: greeting, unclear intent

====================================================
CONTINUATION DETECTION
====================================================

If the previous agent showed a list and asked user to SELECT (cars, tires, stores, dates):
→ User's short reply (number, name, tire size, store name) is a CONTINUATION of the SAME domain.
→ Classify into that SAME domain — do NOT chain to another domain.

Examples:
- Previous: Discovery showed car list → User: "제타" → DISCOVERY (same domain continues)
- Previous: Discovery showed tires → User: "벤투스 S2 AS" → DISCOVERY (same domain continues)
- Previous: Transaction showed stores → User: "한남점" → TRANSACTION (same domain continues)
- Previous: Transaction showed schedule → User: "내일 10시" → TRANSACTION (same domain continues)

Korean vehicle numbers follow patterns: {{vehicle_number}} (e.g., "12가3456", "123가1234")
"""


class StreamingMultiAgentCoordinator:
    """Orchestrates multiple agents with streaming support."""

    def __init__(self):
        self.agent_map = {
            MultiAgentDomain.Domain.DISCOVERY: discovery_subagent,
            MultiAgentDomain.Domain.TRANSACTION: transaction_subagent,
            MultiAgentDomain.Domain.SUPPORT: support_subagent,
            MultiAgentDomain.Domain.LEADING: leading_agent,
        }

    def classify_multi_intent(
        self,
        messages: list,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
    ) -> tuple[list[MultiAgentDomain.Domain], MultiAgentDomain | None]:
        """Classify user message into one or more domains.

        Returns:
            (domains, routing_result) — domains for backward compat, full result for context injection.
        """
        from langchain_litellm import ChatLiteLLM
        from langchain_core.messages import SystemMessage
        from config.tracing import build_trace_config

        llm = ChatLiteLLM(
            api_base=settings.AI_GATEWAY_BASE_URL,
            api_key=settings.AI_GATEWAY_API_KEY,
            model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL}",
        )

        structured_model = llm.with_structured_output(
            MultiAgentDomain,
            strict=True,
        )

        try:
            system_msg = SystemMessage(content=prompt_router_multi())
            all_messages = [system_msg] + list(messages)

            trace_config = build_trace_config(
                run_name="classify_multi_intent",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                tags=["router", "classify_multi_intent"],
            )
            result: MultiAgentDomain = structured_model.invoke(all_messages, config=trace_config)
            logger.info(
                f"[MULTI-DOMAIN] Classification result: domain={result.domains}, behavior={result.user_behavior!r}, next={result.next_action!r}, flow={result.flow!r}"
            )
            domains = result.domains if result.domains else [MultiAgentDomain.Domain.LEADING]
            return domains, result

        except Exception as e:
            logger.exception(f"[MULTI-DOMAIN] Classification failed: {e}")
            return [MultiAgentDomain.Domain.LEADING], None

    @staticmethod
    def _inject_conversation_context(messages: list[dict], routing: MultiAgentDomain | None) -> list[dict]:
        """Inject conversation context (user_behavior, next_action, flow) above the Korean instruction
        in the last user message.

        The current last user message already has the format:
            # Respond in Korean language
            <original user text>

        After injection:
            ## CONVERSATION CONTEXT
            - User behavior: ...
            - Next action: ...
            - Flow so far: ...

            # Respond in Korean language
            <original user text>
        """
        if routing is None:
            return messages

        # Only inject if at least one field is non-empty
        context_parts = []
        if routing.user_behavior:
            context_parts.append(f"- User behavior: {routing.user_behavior}")
        if routing.next_action:
            context_parts.append(f"- Next action: {routing.next_action}")
        if routing.flow:
            context_parts.append(f"- Flow so far: {routing.flow}")

        if not context_parts:
            return messages

        context_block = "## CONVERSATION CONTEXT\n" + "\n".join(context_parts) + "\n"

        # Find last user message and prepend the context block above "# Respond in Korean language"
        messages = [dict(m) for m in messages]
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                content = messages[i]["content"]
                if content.startswith("# Respond in Korean language"):
                    messages[i]["content"] = context_block + "\n" + content
                else:
                    messages[i]["content"] = context_block + "\n# Respond in Korean language\n" + content
                break

        return messages

    def _build_context_message(
        self,
        domain: MultiAgentDomain.Domain,
        accumulated_context: dict,
    ) -> dict | None:
        """Build context message from previous agent results."""
        if not accumulated_context:
            return None

        parts = []
        for dom, content in accumulated_context.items():
            if content:
                parts.append(f"- {dom}: {content[:5000]}")  # Truncate to avoid bloat

        if not parts:
            return None

        return {"role": "assistant", "content": f"[Context from previous steps]\n" + "\n".join(parts)}

    # Tool → pending_intent that the tool FULFILLS (clears from slots on successful run).
    # When one of these tools returns a successful result, the matching pending_intent
    # is considered satisfied and cleared, so later turns don't re-route on a stale intent.
    _TOOL_TO_FULFILL: ClassVar[dict[str, str]] = {
        "get_final_price_tool": "price",
        "get_logistics_inventory_tool": "stock",
        "get_store_inventory_tool": "stock",
        "quick_order_tool": "order",
        "save_to_cart_tool": "order",
    }

    @staticmethod
    def _save_tool_derived_slots(session_id: str, tool_name: str, parsed_data: dict, tool_input: dict | None = None):
        """Persist goods_no, shop_id, and tire_size from successful tool results/inputs to slots.

        Also clears `pending_intent` when the tool that ran fulfills that intent
        (see `_TOOL_TO_FULFILL`).
        """
        from schemas.tstation.slots import ConversationSlots
        from services.tstation.chat_history_service import get_chat_history_service

        # Fulfillment: if this tool satisfies a pending intent AND succeeded, clear it.
        # Tools return {"status": "success"|"error", ...}; only "success" counts as fulfillment
        # so a failed price/stock/order lookup still leaves the intent for retry.
        # Done BEFORE other slot updates so the cleared state is the one we save.
        fulfilled_intent = StreamingMultiAgentCoordinator._TOOL_TO_FULFILL.get(tool_name)
        tool_succeeded = isinstance(parsed_data, dict) and parsed_data.get("status") == "success"
        if fulfilled_intent and tool_succeeded:
            try:
                svc = get_chat_history_service()
                current_slots = svc.get_slots(session_id)
                if current_slots.pending_intent == fulfilled_intent:
                    new_slots = current_slots.model_copy()
                    new_slots.pending_intent = None
                    svc.save_slots(session_id, new_slots)
                    logger.info(
                        f"[SLOTS] Cleared pending_intent={fulfilled_intent!r} "
                        f"after {tool_name} completed successfully"
                    )
            except Exception as e:
                logger.warning(f"[SLOTS] Failed to clear pending_intent: {e}")

        # Map tool names to the slot fields they can provide (from output)
        tool_slot_extractors = {
            "search_product_tool": ["goods_no"],
            "get_store_list_tool": ["shop_id"],
            "get_nearby_stores_tool": ["shop_id"],
            "get_store_inventory_tool": ["shop_id"],
        }

        # When user searches for a different car model, reset tire_size and goods_no
        # so the previous vehicle's tire_size doesn't persist
        if tool_name == "search_car_model_tool":
            try:
                svc = get_chat_history_service()
                current_slots = svc.get_slots(session_id)
                if current_slots.tire_size is not None or current_slots.goods_no is not None:
                    new_slots = current_slots.model_copy()
                    new_slots.tire_size = None
                    new_slots.goods_no = None
                    svc.save_slots(session_id, new_slots)
                    logger.info("[SLOTS] Reset tire_size and goods_no due to search_car_model_tool call")
            except Exception as e:
                logger.warning(f"[SLOTS] Failed to reset slots on car model search: {e}")

        # Extract tire_size from tool INPUT when recommendation tool is called
        # This captures the confirmed tire_size that the LLM used for recommendations
        if tool_name == "get_products_recommendations_tool" and tool_input:
            input_tire_size = tool_input.get("tire_size")
            if input_tire_size:
                try:
                    svc = get_chat_history_service()
                    current_slots = svc.get_slots(session_id)
                    new_slots = ConversationSlots(tire_size=input_tire_size)
                    updated = current_slots.merge(new_slots)
                    svc.save_slots(session_id, updated)
                    logger.info(f"[SLOTS] tire_size saved from {tool_name} input: {input_tire_size}")
                except Exception as e:
                    logger.warning(f"[SLOTS] Failed to save tire_size from tool input: {e}")

        fields = tool_slot_extractors.get(tool_name)
        if not fields:
            return

        # Extract values from tool result data
        tool_slots = {}
        data = parsed_data.get("data", parsed_data)

        # Handle list results (e.g., search results) — only auto-fill if exactly 1 item
        if isinstance(data, dict) and "items" in data:
            items = data["items"]
            if isinstance(items, list) and len(items) == 1:
                data = items[0]
            else:
                return  # Multiple or no results — don't auto-fill
        elif isinstance(data, dict) and "stores" in data:
            stores = data["stores"]
            if isinstance(stores, list) and len(stores) == 1:
                data = stores[0]
            else:
                return

        for field in fields:
            val = data.get(field) if isinstance(data, dict) else None
            if val:
                tool_slots[field] = val

        if not tool_slots:
            return

        try:
            svc = get_chat_history_service()
            current_slots = svc.get_slots(session_id)
            new_slots = ConversationSlots(**tool_slots)
            updated = current_slots.merge(new_slots)
            svc.save_slots(session_id, updated)
            logger.info(f"[SLOTS] Tool-derived slots saved from {tool_name}: {tool_slots}")
        except Exception as e:
            logger.warning(f"[SLOTS] Failed to save tool-derived slots: {e}")

    def stream(
        self,
        messages: list[dict],
        domains: list[MultiAgentDomain.Domain] | None = None,
        slot_context: str | None = None,
        session_id: str | None = None,
        tool_context: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        skip_decision: bool = False,
    ) -> Iterator[dict]:
        """
        Chain multiple agents and stream their outputs.

        Args:
            messages: Original user messages
            domains: Pre-classified domains (optional, will classify if not provided)
            slot_context: Formatted slot context string to inject into agent messages
            session_id: Session ID for persisting tool-derived slots (goods_no, shop_id)
            tool_context: Formatted tool results from previous turn for context preservation
            user_id: User ID for Langfuse tracing
            trace_id: Trace ID to group all LLM calls of this request under one trace
            skip_decision: When True AND domains has >= 2 entries, skip the
                `decide_next_action` LLM call between the first and second agent
                (the chain is pre-committed by the caller — e.g., P0 code gate).

        Yields:
            Stream events from all agents in sequence
        """
        from config.tracing import build_trace_config

        # Classify if domains not provided
        # Save original messages before CONVERSATION CONTEXT injection for UI Template Agent
        original_messages = list(messages)
        if domains is None:
            domains, routing_result = self.classify_multi_intent(
                messages,
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
            )
            messages = StreamingMultiAgentCoordinator._inject_conversation_context(messages, routing_result)

        if not domains:
            domains = [MultiAgentDomain.Domain.LEADING]

        logger.info(f"[COORDINATOR] Streaming for domains: {[d.value for d in domains]}")

        accumulated_context = {}
        accumulated_tool_data = []  # Collect tool outputs for UI Template Agent
        domain_data_event_emitted = False  # Domain agent emitted a `data` event itself

        is_first_agent = True

        for domain in domains:
            agent = self.agent_map.get(domain)
            if not agent:
                logger.warning(f"[COORDINATOR] No agent found for domain: {domain}")
                continue

            # Build enriched messages with context from previous agents
            # Order: slot_context | messages (with user_context inside) | current_user_msg LAST | accumulated_context LAST
            enriched_messages = []

            # 1. slot_context FIRST
            if slot_context:
                enriched_messages.append(
                    {
                        "role": "assistant",
                        "content": slot_context,
                    }
                )

            # 1.5. tool_context from previous turn (structured tool results)
            if tool_context:
                enriched_messages.append(
                    {
                        "role": "assistant",
                        "content": tool_context,
                    }
                )

            # 2. Original messages (already contains user_context from _build_messages_with_user_info)
            #    These messages have current_user_msg at the LAST position
            enriched_messages.extend(list(messages))

            # 3. Append accumulated_context AFTER current_user_msg (for handover agents)
            if accumulated_context:
                for prev_domain, content in accumulated_context.items():
                    if content and content.strip():
                        enriched_messages.append({"role": "assistant", "content": str(content)})
                        enriched_messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Based on the previous agent's findings above, produce a SINGLE unified response for the user. "
                                    "Include key findings from the previous agent (e.g., compatibility results, product info) and "
                                    "seamlessly add your own results (e.g., pricing, inventory, store info). "
                                    "Do NOT repeat introductory greetings or offer intermediate choices that are already resolved. "
                                    "The response must read as ONE coherent answer, not two separate answers concatenated together."
                                ),
                            }
                        )
                        logger.info(f"[COORDINATOR] Passing context to {domain.value}")
                        break  # Only take first previous agent

            # 4. Append accumulated_tool_data LAST (for UI Template Agent)
            if accumulated_tool_data:
                # Extract ord_qty from user messages when chaining to Transaction Agent
                if domain == MultiAgentDomain.Domain.TRANSACTION:
                    has_ord_qty = any(
                        isinstance(item.get("data"), dict) and "ord_qty" in item.get("data", {})
                        for item in accumulated_tool_data
                    )
                    if not has_ord_qty:
                        user_text = " ".join(msg.get("content", "") for msg in messages if msg.get("role") == "user")
                        qty_match = re.search(r"(\d+)\s*개", user_text)
                        if qty_match:
                            ord_qty = int(qty_match.group(1))
                            accumulated_tool_data.append({"tool": "user_intent", "data": {"ord_qty": ord_qty}})
                            logger.info(f"[COORDINATOR] Extracted ord_qty={ord_qty} from user message")

                tool_summary = json.dumps(accumulated_tool_data, ensure_ascii=False, indent=2)
                enriched_messages.append(
                    {"role": "assistant", "content": f"[Previous agent tool results]\n{tool_summary}"}
                )
                logger.info(f"[COORDINATOR] Passing {len(accumulated_tool_data)} tool results to {domain.value}")

            domain_key = domain.value
            logger.info(
                f"[COORDINATOR_MESSAGE] Domain: {domain_key}, enriched_messages: {json.dumps(enriched_messages, ensure_ascii=False, indent=2)}"
            )

            # Yield agent start event
            yield {
                "type": "sub-agent",
                "agent": f"[{domain_key.upper()} AGENT]",
                "status": "start",
            }

            # Stream from agent and yield events immediately
            full_response = ""
            last_agent_called_tools = False
            agent_trace_config = build_trace_config(
                run_name=f"{domain_key}_agent",
                session_id=session_id,
                user_id=user_id,
                trace_id=trace_id,
                tags=[domain_key, "agent"],
            )
            for event in agent.stream(enriched_messages, config=agent_trace_config):
                # Tag with source domain for UI
                event["source_domain"] = domain_key
                yield event

                # Track direct data events emitted by the domain agent (JSON output).
                # When present, skip the UI Template stage below.
                if event.get("type") == "data":
                    domain_data_event_emitted = True

                # Capture message content for context passing
                if event.get("type") == "message":
                    content = event.get("content", "")
                    if content:
                        accumulated_context[domain_key] = content
                        full_response = content
                        logger.info(f"[COORDINATOR] Captured message for {domain_key}: {content}...")

                # Capture tool outputs for UI Template Agent
                if event.get("type") == "tool":
                    last_agent_called_tools = True
                    tool_output = event.get("output", "")
                    if tool_output:
                        try:
                            parsed = json.loads(tool_output) if isinstance(tool_output, str) else tool_output
                            accumulated_tool_data.append({"tool": event.get("tool", ""), "data": parsed})

                            # Persist tool-derived goods_no, shop_id, and tire_size to slots
                            if session_id and isinstance(parsed, dict):
                                self._save_tool_derived_slots(
                                    session_id, event.get("tool", ""), parsed, event.get("input", {})
                                )

                        except (json.JSONDecodeError, TypeError):
                            accumulated_tool_data.append({"tool": event.get("tool", ""), "data": tool_output})

            # Yield agent completion event
            yield {
                "type": "sub-agent",
                "agent": f"[{domain_key.upper()} AGENT]",
                "status": "done",
            }

            # LLM Decision: After first agent, use LLM to decide next action
            # Support domain rarely chains to other agents — skip LLM decision to save ~300ms
            if is_first_agent:
                is_first_agent = False
                if domain == MultiAgentDomain.Domain.SUPPORT:
                    logger.info("[COORDINATOR] Support domain — skipping LLM decision, stopping chain")
                    break

                # Caller pre-committed the chain (e.g., P0 auto-chain code gate) —
                # skip the decide_next_action LLM call (saves ~300ms) and proceed
                # directly to the next domain in `domains`.
                #
                # BUT: only proceed if Discovery actually resolved a single goods_no.
                # `_save_tool_derived_slots` (search_product_tool extractor) only
                # writes goods_no to slots when the tool returns exactly 1 item;
                # 0/multiple-result cases leave goods_no=None and Discovery is
                # already in clarification/selection mode. Chaining Transaction on
                # top would produce a contradictory "상품 검색이 필요합니다" fallback.
                if skip_decision and len(domains) >= 2:
                    goods_no_resolved = False
                    if session_id:
                        try:
                            from services.tstation.chat_history_service import get_chat_history_service

                            post_slots = get_chat_history_service().get_slots(session_id)
                            goods_no_resolved = post_slots.goods_no is not None
                        except Exception as e:
                            logger.warning(
                                f"[COORDINATOR] Failed to verify goods_no post-Discovery: {e}"
                            )
                    if not goods_no_resolved:
                        logger.info(
                            "[COORDINATOR] skip_decision=True but Discovery did not resolve "
                            "goods_no (0 or multiple results) — stopping chain"
                        )
                        break
                    logger.info(
                        "[COORDINATOR] skip_decision=True — proceeding to next domain "
                        f"({domains[1].value}) without LLM decision"
                    )
                    continue

                decision = decide_next_action(
                    original_messages=messages,
                    previous_agent_response=full_response,
                    previous_domain=domain_key,
                    session_id=session_id,
                    user_id=user_id,
                    trace_id=trace_id,
                )
                logger.info(f"[COORDINATOR] LLM Decision: {decision.next_action} - {decision.reason}")

                if decision.next_action == NextAction.STOP or not decision.next_domain:
                    logger.info("[COORDINATOR] Stopping multi-agent chain")
                    break

                # Map next_domain string to enum
                next_domain_map = {
                    "discovery": MultiAgentDomain.Domain.DISCOVERY,
                    "transaction": MultiAgentDomain.Domain.TRANSACTION,
                    "support": MultiAgentDomain.Domain.SUPPORT,
                }
                next_domain = next_domain_map.get(decision.next_domain.lower())
                if next_domain:
                    domains = [next_domain] + [d for d in domains if d != next_domain]

        # Legacy UI Template Agent path is disabled.
        # Domain agents should emit `data` events directly. If a migrated agent misses a
        # structured payload, fall back to a minimal quickReply built from the last
        # assistant response instead of calling the UI Template Agent.
        _has_qna = any(item.get("tool") == "transfer_to_qna_tool" for item in accumulated_tool_data)
        _has_non_support_data = any(
            item.get("tool") not in ("get_faq_tool", "search_faq_rag_tool", "transfer_to_qna_tool")
            for item in accumulated_tool_data
        )
        _has_agent_response = bool(accumulated_context)
        _no_tools_called = not accumulated_tool_data
        _has_relevant_tool_data = accumulated_tool_data and (_has_qna or _has_non_support_data)
        assistant_text = next((c for c in reversed(list(accumulated_context.values())) if c and c.strip()), "")
        if domain_data_event_emitted:
            logger.info("[COORDINATOR] Domain agent emitted data event — skipping UI Template Agent")
        elif _has_agent_response and (_no_tools_called or _has_relevant_tool_data):
            trigger_reason = f"{len(accumulated_tool_data)} tool outputs"
            logger.warning(
                "[COORDINATOR] UI Template Agent disabled — generating fallback quickReply (%s)",
                trigger_reason,
            )
            yield {
                "type": "data",
                "template": "quickReply",
                "data": {
                    "assistantResponse": assistant_text,
                    "quickReplies": [],
                },
                "source_domain": domain_key if "domain_key" in locals() else "ui_template",
            }

        # Final done event
        yield {"type": "sub-agent", "agent": "[DONE]", "status": "success"}


import re

_FALLBACK_RESPONSE = (
    "죄송합니다, 해당 내용은 제가 안내해 드리기 어려운 부분이에요.\n\n"
    "타이어 추천, 가격 조회, 매장 검색 등 타이어 관련 문의사항이 있으시면 편하게 말씀해 주세요."
)

_INTERNAL_JARGON_PATTERN = re.compile(
    r"No tool data retrieved|tool data|source data",
    re.IGNORECASE,
)


def _sanitize_response(text: str) -> str:
    """Replace internal jargon with user-friendly fallback if response has no useful content."""
    stripped = text.strip()
    if not stripped:
        return _FALLBACK_RESPONSE
    if _INTERNAL_JARGON_PATTERN.search(stripped) and len(stripped) < 100:
        return _FALLBACK_RESPONSE
    return text


_FACTUAL_CLAIM_PATTERN = re.compile(
    r"\d{1,3}(?:,\d{3})*\s*원"  # 가격 (e.g. 150,000원)
    r"|G\d{9,}"  # goods_no (e.g. GXXXXXXXXXXXX)
    r"|shop(?:Seq|_id|Id)"  # 매장 ID
    r"|재고|할인|%\s*할인"  # 재고/할인
    r"|\d{3}/\d{2,3}[a-zA-Z]+\d{2}"  # 타이어 사이즈 (e.g. 225/40R18, 245/40ZR19)
    r"|티스테이션\s*\S*점"  # 매장명 (e.g. 티스테이션 양평점, 티스테이션판교점)
    r"|F\d{5}\b",  # shop_id (e.g. F01234)
    re.IGNORECASE,
)


def _has_factual_claims(text: str) -> bool:
    """Check if draft contains factual commerce claims that need QC verification."""
    return bool(_FACTUAL_CLAIM_PATTERN.search(text))


# Singleton coordinator instance
_coordinator = StreamingMultiAgentCoordinator()


def _enrich_messages_with_template_data(messages: list[dict], session_id: str) -> list[dict]:
    """Append template_data from Redis to assistant messages."""
    if not session_id:
        return messages

    try:
        from services.tstation.chat_history_service import get_chat_history_service

        redis_messages = get_chat_history_service().get_history(session_id)

        # content -> template_data map
        template_map = {
            msg["content"]: msg["template_data"]
            for msg in redis_messages
            if msg.get("role") == "assistant" and msg.get("template_data") and msg.get("content")
        }

        if not template_map:
            return messages

        # Append template_data to matching assistant messages
        for msg in messages:
            if msg.get("role") == "assistant" and msg["content"] in template_map:
                template_str = json.dumps(template_map[msg["content"]], ensure_ascii=False)
                msg["content"] += f"\n\n[이전 선택된 상품 데이터]\n{template_str}"

        return messages

    except Exception as e:
        logger.warning(f"[TEMPLATE_DATA] Failed: {e}")
        return messages


class TStationChatServiceV2:
    """V2 Chat service with multi-agent streaming support."""

    @staticmethod
    def _build_messages_with_user_info(request: TStationChatRequest) -> list[dict]:
        """Build messages with user info injected before current user message."""
        messages = [dict(msg) for msg in request.messages]

        # Remove duplicate "hi" from frontend
        if len(messages) >= 2 and messages[-2].get("role") == "user" and messages[-2].get("content") == "hi":
            messages.pop(-2)

        # Merge user info: JWT + UI (UI overrides)
        user_info = None
        if request.access_token:
            user_info = get_user_info_from_token(request.access_token)
        if request.user_info:
            user_info = {**(user_info or {}), **request.user_info}

        # Build USER CONTEXT message if user_info available
        user_context_msg = None
        if user_info:
            safe_fields = {"mbr_nm", "location", "user_id"}
            lines = []
            for k, v in user_info.items():
                if k not in safe_fields:
                    continue
                if k == "location" and isinstance(v, dict):
                    lines.append(f"xpos: {v.get('xpos')}, ypos: {v.get('ypos')}")
                elif k == "user_id":
                    lines.append(f"mbr_no: {v}")
                else:
                    lines.append(f"{k}: {v}")

            if lines:
                user_context_msg = {
                    "role": "user",
                    "content": (
                        "## USER CONTEXT INFORMATION (Always Available)\n"
                        f"{chr(10).join(lines)}\n\n"
                        "## INSTRUCTIONS FOR AGENTS:\n"
                        "🔹 Always prioritize data provided directly by the user\n"
                        "🔹 If no direct data is provided, reference the personal data below\n"
                        "🔹 NEVER expose internal identifiers in responses\n"
                    ),
                }

        # Find last user message index and insert user_context before it
        last_user_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                last_user_idx = i
                break

        if last_user_idx == -1:
            return messages

        # Insert user_context before last user message
        if user_context_msg:
            messages.insert(last_user_idx, user_context_msg)
            last_user_idx += 1

        # Add Korean prefix + current time to the current user message (now at last_user_idx)
        messages[last_user_idx]["content"] = (
            f"# Respond in Korean language\n{messages[last_user_idx]['content']}"
            f"\n\n[current_time: {get_current_time()}]"
        )

        return messages

    @staticmethod
    def _format_tool_context(tool_data: list[dict]) -> str:
        """Format accumulated structured tool results as a system prompt for conversation context.

        Results are ordered most-recent-first. Each entry shows the tool label,
        query conditions, and the structured data rows.
        """
        tool_labels = {
            "get_products_recommendations_tool": "타이어 추천 결과",
            "search_product_tool": "상품 검색 결과",
            "get_nearby_stores_tool": "근처 매장 목록",
            "get_store_list_tool": "매장 검색 결과",
            "get_store_inventory_tool": "매장 재고 현황",
            "get_orders_of_user_tool": "주문 내역",
            "check_compatibility_tool": "호환 사이즈 조회",
            "get_final_price_tool": "가격 조회",
            "compare_discount_tool": "할인 가격 비교",
            "get_product_description_tool": "상품 상세",
        }

        lines = [
            "[대화 중 조회한 데이터 — 고객이 이 내용을 참조할 수 있습니다]",
            "아래는 이번 대화에서 tool로 조회한 실제 결과입니다 (최신순).",
            "고객이 '18인치', '아까 19인치', '첫번째', '가장 저렴한 것' 등으로 참조하면",
            "아래 데이터에서 해당 조건에 정확히 매칭되는 항목을 찾아 응답하세요.",
            "절대로 아래 데이터에 없는 상품/매장/가격을 만들어내지 마세요.",
            "",
        ]

        for idx, item in enumerate(tool_data):
            tool_name = item.get("tool", "")
            label = tool_labels.get(tool_name, tool_name)
            tool_input = item.get("input", {})
            data = item.get("data")

            # Mark recency
            recency = "최신" if idx == 0 else f"{idx + 1}번째 전"
            header = f"• [{recency}] {label}"
            if tool_input:
                input_str = ", ".join(f"{k}={v}" for k, v in tool_input.items())
                header += f" (조회 조건: {input_str})"
            lines.append(header)

            if isinstance(data, list):
                for i, row in enumerate(data, 1):
                    if isinstance(row, dict):
                        if row.get("_truncated"):
                            lines.append(f"  ... {row['_truncated']}")
                        else:
                            row_str = " | ".join(f"{k}: {v}" for k, v in row.items())
                            lines.append(f"  {i}. {row_str}")
                    else:
                        lines.append(f"  {i}. {row}")
            elif isinstance(data, dict):
                row_str = " | ".join(f"{k}: {v}" for k, v in data.items())
                lines.append(f"  {row_str}")

            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _resolve_goods_no_from_selection(user_text: str, prev_tool_data: list[dict]) -> str | None:
        """Match a user's list-selection reply against the prior search_product_tool
        result and return the goods_no of the matched item.

        When a previous turn returned multiple products and the user responds with
        an ordinal ("3.", "3번") or a name + size ("Ventus S2 AS 225/45R18"), this
        lets the coordinator capture goods_no before any agent runs — so that the
        subsequent Discovery→Transaction handoff is not blocked by the "goods_no
        missing in slots" safety check (Discovery may skip calling the search tool
        when it can resolve the pick from conversation history alone).

        Matching strategy (first hit wins):
          1. Ordinal at the start of the message → items[idx-1]
          2. Single item with matching tire_size
          3. Multiple items with matching tire_size → pick the one whose goods_nm
             has the highest token overlap (≥2 tokens required to avoid false hits)

        Only the most recent search_product_tool entry is inspected.
        Returns None when no confident match is found.

        Expected tool_context entry shape (produced by filter_for_context in
        g_qc_agent/source_filter.py, which is what gets persisted to Redis):
            {"tool": "search_product_tool",
             "data": [{"goods_no": "...", "goods_nm": "...", "tire_size_1": "..."}],
             "input": {...}}
        Note: `data` is a LIST directly, and the size field is `tire_size_1`
        (filter whitelist is {"goods_no", "goods_nm", "tire_size_1", ...}).
        """
        if not user_text or not prev_tool_data:
            return None

        items: list[dict] = []
        for entry in prev_tool_data:
            if entry.get("tool") != "search_product_tool":
                continue
            data = entry.get("data")
            # Primary shape: filter_for_context stores data as a list directly
            if isinstance(data, list):
                items = [it for it in data if isinstance(it, dict) and not it.get("_truncated")]
                break
            # Defensive fallback: {"items": [...]} shape (raw tool output)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                items = [it for it in data["items"] if isinstance(it, dict)]
                break
        if not items:
            return None

        text = user_text.strip()

        ordinal_match = re.match(r"^\s*(\d+)\s*[\.\)번:]", text)
        if ordinal_match:
            idx = int(ordinal_match.group(1)) - 1
            if 0 <= idx < len(items):
                goods_no = items[idx].get("goods_no")
                if goods_no:
                    return goods_no

        size_match = re.search(r"\d{3}/\d{2}R\d{2}", text)
        if size_match:
            target_size = size_match.group(0)
            # filter_for_context keeps `tire_size_1`; include legacy aliases
            # for safety if another path ever stores the raw field name.
            same_size = [
                item for item in items
                if (
                    item.get("tire_size_1")
                    or item.get("tire_size")
                    or item.get("tireSize")
                    or ""
                ) == target_size
            ]

            if len(same_size) == 1:
                goods_no = same_size[0].get("goods_no")
                if goods_no:
                    return goods_no

            if len(same_size) >= 2:
                tokens = [
                    t.lower() for t in re.findall(r"[A-Za-z가-힣]+", text)
                    if len(t) >= 2
                ]
                best_item: dict | None = None
                best_score = 0
                for item in same_size:
                    goods_nm = (item.get("goods_nm") or "").lower()
                    score = sum(1 for tok in tokens if tok in goods_nm)
                    if score > best_score:
                        best_score = score
                        best_item = item
                if best_item is not None and best_score >= 2:
                    goods_no = best_item.get("goods_no")
                    if goods_no:
                        return goods_no

        return None

    @staticmethod
    def _resolve_shop_id_from_selection(user_text: str, prev_tool_data: list[dict]) -> str | None:
        """Match a user's list-selection reply against the prior
        get_nearby_stores_tool / get_store_list_tool result and return the
        shop_id of the matched store.

        Mirrors _resolve_goods_no_from_selection for stores. When a store list
        had more than 1 store, `_save_tool_derived_slots` skips shop_id
        auto-save (can't guess which one). This resolver fills that gap by
        matching the user's selection reply to the prior list.

        Matching strategy (first hit wins):
          1. Ordinal at the start ("1.", "5번", "3)") → items[idx-1]
          2. Token-overlap against shop_nm — only resolves when exactly ONE
             store has the top score (≥1 token match), to avoid ambiguous
             resolution when multiple stores share a substring like "한남점".

        Expected tool_context entry shape (from filter_for_context):
            {"tool": "get_nearby_stores_tool" | "get_store_list_tool",
             "data": [{"shop_id": "F07782", "shop_nm": "티스테이션 한남점",
                       "distance_km": 4.59, "addr_base": "..."}],
             "input": {...}}
        """
        if not user_text or not prev_tool_data:
            return None

        STORE_TOOLS = {"get_nearby_stores_tool", "get_store_list_tool"}
        items: list[dict] = []
        for entry in prev_tool_data:
            if entry.get("tool") not in STORE_TOOLS:
                continue
            data = entry.get("data")
            # Primary shape: filter_for_context stores data as a list directly
            if isinstance(data, list):
                items = [it for it in data if isinstance(it, dict) and not it.get("_truncated")]
                break
            # Defensive fallback: {"stores": [...]} shape (raw tool output)
            if isinstance(data, dict) and isinstance(data.get("stores"), list):
                items = [it for it in data["stores"] if isinstance(it, dict)]
                break
        if not items:
            return None

        text = user_text.strip()

        ordinal_match = re.match(r"^\s*(\d+)\s*[\.\)번:]", text)
        if ordinal_match:
            idx = int(ordinal_match.group(1)) - 1
            if 0 <= idx < len(items):
                shop_id = items[idx].get("shop_id")
                if shop_id:
                    return shop_id

        # Token-overlap match against shop_nm. Require a unique top-scoring
        # store to avoid auto-resolving ambiguous replies like a bare "한남점"
        # that could match several brands at the same address area.
        tokens = [
            t for t in re.findall(r"[A-Za-z가-힣]+", text)
            if len(t) >= 2
        ]
        if tokens:
            scored: list[tuple[int, dict]] = []
            for item in items:
                shop_nm = item.get("shop_nm") or ""
                score = sum(1 for tok in tokens if tok in shop_nm)
                if score > 0:
                    scored.append((score, item))
            if scored:
                max_score = max(s for s, _ in scored)
                top = [item for s, item in scored if s == max_score]
                if len(top) == 1:
                    shop_id = top[0].get("shop_id")
                    if shop_id:
                        return shop_id

        return None

    @staticmethod
    def _resolve_shop_id_from_history_template(user_text: str, history: list[dict]) -> str | None:
        """Match a user's list-selection reply against the metadata of the most
        recent assistant message that rendered a `location` template.

        Used as a fallback when prev_tool_data lookup fails (e.g., tool entry
        was evicted, or filter_for_context never persisted it). The template
        metadata is the authoritative source of "what stores were actually
        shown to the user", so matching against it is more robust than against
        raw tool output.

        Expected history msg shape (from chat_history_service.get_history):
            {"role": "assistant", "content": "...",
             "template_data": {"type": "data", "template": "location",
                               "data": {"stores": [{"nameAddress": "티스테이션 한남점", ...}],
                                        "metadata": [{"shopId": "F07782"}]}}}

        Matching strategy:
          1. Ordinal at the start ("1.", "5번", "3)") → metadata[idx-1].shopId
          2. Token-overlap against stores[].nameAddress — only resolves when
             exactly ONE store has the top score
        """
        if not user_text or not history:
            return None

        text = user_text.strip()

        # Find the most recent assistant message with a `location` template.
        # Stop at the first such message; do not fall through to older lists,
        # because the user's selection refers to the latest one shown.
        target_template: dict | None = None
        for msg in reversed(history):
            if msg.get("role") != "assistant":
                continue
            td = msg.get("template_data")
            if not isinstance(td, dict):
                continue
            if td.get("template") != "location":
                continue
            inner = td.get("data")
            if isinstance(inner, dict):
                target_template = inner
            break

        if not target_template:
            return None

        stores = target_template.get("stores") or []
        metadata = target_template.get("metadata") or []
        if not isinstance(stores, list) or not isinstance(metadata, list):
            return None
        if not stores or len(stores) != len(metadata):
            return None

        ordinal_match = re.match(r"^\s*(\d+)\s*[\.\)번:]", text)
        if ordinal_match:
            idx = int(ordinal_match.group(1)) - 1
            if 0 <= idx < len(metadata):
                meta = metadata[idx]
                if isinstance(meta, dict):
                    shop_id = meta.get("shopId")
                    if shop_id:
                        return shop_id

        tokens = [
            t for t in re.findall(r"[A-Za-z가-힣]+", text)
            if len(t) >= 2
        ]
        if tokens:
            scored: list[tuple[int, dict]] = []
            for store, meta in zip(stores, metadata):
                if not isinstance(store, dict) or not isinstance(meta, dict):
                    continue
                name = (
                    store.get("nameAddress")
                    or store.get("name")
                    or store.get("title")
                    or ""
                )
                score = sum(1 for tok in tokens if tok in name)
                if score > 0:
                    scored.append((score, meta))
            if scored:
                max_score = max(s for s, _ in scored)
                top = [meta for s, meta in scored if s == max_score]
                if len(top) == 1:
                    shop_id = top[0].get("shopId")
                    if shop_id:
                        return shop_id

        return None

    @staticmethod
    def chat(request: TStationChatRequest):
        """
        T-Station AI Chat V2 - Multi-Agent Streaming
        """
        logger.debug(f"[CHAT_V2] Received request: {request}")

        set_tstation_be_token(request.access_token)

        # PII Guardrail: check the latest user message before any agent processing
        last_user_msg = next(
            (m.get("content", "") for m in reversed(request.messages) if m.get("role") == "user"),
            "",
        )
        pii_detected = check_pii(last_user_msg)
        if pii_detected:
            logger.warning(f"[CHAT_V2] PII guardrail blocked: {pii_detected}")
            if request.stream:
                return StreamingResponse(
                    TStationChatServiceV2._stream_guardrail_response(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            return TStationChatResponse(content=GUARDRAIL_RESPONSE)

        # Step 1: Enrich messages with template_data from Redis history
        enriched_messages = _enrich_messages_with_template_data(
            [dict(msg) for msg in request.messages],
            request.session_id,
        )
        # Step 2: Build messages with user info
        request_with_enriched = TStationChatRequest(
            messages=enriched_messages,
            session_id=request.session_id,
            user_id=request.user_id,
            access_token=request.access_token,
            stream=request.stream,
            user_info=request.user_info,
        )
        messages = TStationChatServiceV2._build_messages_with_user_info(request_with_enriched)
        logger.debug(f"[CHAT_V2] Messages: {json.dumps(messages, ensure_ascii=False, indent=2)}")

        # Slot processing: load → extract → classify (with LLM slots) → merge → save → inject
        # Wrapped in try/except so slot failures never block the main chat flow
        from schemas.tstation.slots import ConversationSlots
        from services.tstation.chat_history_service import get_chat_history_service

        domains = None
        slot_context = None
        tool_context = None

        # Defaults hoisted above the try block so the P0 auto-chain gate below
        # can safely inspect them even if slot processing raises.
        last_user_text = ""
        regex_slots = ConversationSlots()
        merged_slots = ConversationSlots()
        goods_no_resolved_this_turn = False

        try:
            chat_history_svc = get_chat_history_service()

            # 1) Load existing slots from Redis
            existing_slots = chat_history_svc.get_slots(request.session_id)
            logger.info(f"[SLOTS] Loaded existing slots: {existing_slots.model_dump()}")

            # 2) Extract regex-based slots from the LATEST user message only
            for msg in reversed(request.messages):
                if msg.get("role") == "user":
                    last_user_text = msg.get("content", "")
                    break
            regex_slots = ConversationSlots.extract_from_user_text(last_user_text)

            # 3) Merge: existing → regex (full merge with dependency reset)
            merged_slots = existing_slots.merge(regex_slots)
            logger.info(f"[SLOTS] Merged slots: {merged_slots.model_dump()}")

            # 3.5) If the user explicitly asked for a recommendation in THIS turn
            # AND did not also include a fresh transactional keyword, clear any
            # stale transactional pending_intent from earlier turns.
            # A mixed turn like "추천해준 것 중 이거 가격 얼마야?" must NOT be cleared —
            # the fresh "price" extracted this turn wins over the old intent.
            # merge() only applies non-None values so we can't express "clear" via
            # regex_slots alone — it has to happen here after the merge.
            user_asked_for_recommend = ConversationSlots.has_recommend_intent(last_user_text)
            turn_has_new_transactional = regex_slots.pending_intent is not None
            if (
                merged_slots.pending_intent is not None
                and user_asked_for_recommend
                and not turn_has_new_transactional
            ):
                logger.info(
                    f"[SLOTS] Clearing stale pending_intent={merged_slots.pending_intent!r} "
                    f"— user switched back to recommendation"
                )
                merged_slots.pending_intent = None

            # 3.7) Load accumulated tool context (needed both for goods_no list-pick
            # resolution below AND for prompt injection in step 6). Loading before
            # save_slots lets resolved goods_no be persisted in step 4.
            prev_tool_data = chat_history_svc.get_tool_context(request.session_id)

            # 3.8) Resolve goods_no from the user's list-selection reply matched against
            # the most recent search_product_tool result. Without this, Discovery may
            # hand off ("상품 확인했어요. 바로 재고 확인으로 이어갑니다") without
            # actually calling a tool in the current turn — leaving goods_no=None in
            # slots and causing the coordinator's P0 safety check to stop the chain
            # before Transaction runs.
            if merged_slots.goods_no is None and prev_tool_data:
                resolved_goods_no = TStationChatServiceV2._resolve_goods_no_from_selection(
                    last_user_text, prev_tool_data
                )
                if resolved_goods_no:
                    merged_slots.goods_no = resolved_goods_no
                    goods_no_resolved_this_turn = True
                    logger.info(
                        f"[SLOTS] Resolved goods_no={resolved_goods_no!r} from user's "
                        f"list-selection against prior search_product_tool result"
                    )

            # 3.9) Resolve shop_id from the user's list-selection reply matched against
            # the most recent get_nearby_stores_tool / get_store_list_tool result.
            # `_save_tool_derived_slots` only auto-saves shop_id when the tool returned
            # exactly 1 store — multi-result lists (nearby stores within radius, region
            # searches) leave shop_id=None. When the user then picks a store from that
            # list, STEP 5A Step 4 needs shop_id to call get_store_schedule_tool; without
            # this resolver the LLM tends to re-run get_store_list_tool and stall at the
            # location template instead of progressing to datepick.
            if merged_slots.shop_id is None and prev_tool_data:
                resolved_shop_id = TStationChatServiceV2._resolve_shop_id_from_selection(
                    last_user_text, prev_tool_data
                )
                if resolved_shop_id:
                    merged_slots.shop_id = resolved_shop_id
                    logger.info(
                        f"[SLOTS] Resolved shop_id={resolved_shop_id!r} from user's "
                        f"list-selection against prior store-list tool result"
                    )
                else:
                    # Diagnostic: log why prev_tool_data path didn't match.
                    store_tool_entries = [
                        e.get("tool") for e in prev_tool_data
                        if e.get("tool") in ("get_nearby_stores_tool", "get_store_list_tool")
                    ]
                    logger.info(
                        f"[SLOTS] shop_id resolver (tool path) no-match: "
                        f"user_text={last_user_text[:60]!r}, "
                        f"store_tool_entries={store_tool_entries}"
                    )

            # 3.91) Fallback: resolve shop_id from the metadata of the most recent
            # assistant message that rendered a `location` template. This covers
            # cases where prev_tool_data is missing or stale (e.g., the prior
            # multi-store turn hit silent template-validation failure but the
            # template_data was still persisted by chat_message.stream_chat_response).
            # template_data shape (from chat_message.py):
            #   {"type": "data", "template": "location",
            #    "data": {"stores": [...], "metadata": [{"shopId": "F00098"}, ...]}}
            if merged_slots.shop_id is None:
                try:
                    history = chat_history_svc.get_history(request.session_id)
                    resolved_shop_id = TStationChatServiceV2._resolve_shop_id_from_history_template(
                        last_user_text, history
                    )
                    if resolved_shop_id:
                        merged_slots.shop_id = resolved_shop_id
                        logger.info(
                            f"[SLOTS] Resolved shop_id={resolved_shop_id!r} from user's "
                            f"list-selection against last `location` template metadata"
                        )
                except Exception as e:
                    logger.warning(f"[SLOTS] history shop_id fallback failed: {e}")

            # 4) Save merged slots to Redis
            chat_history_svc.save_slots(request.session_id, merged_slots)

            # 5) Build slot context string for agent injection
            slot_context = merged_slots.to_prompt_context() if merged_slots.has_any() else None

            # 6) Format tool context for prompt injection
            if prev_tool_data:
                tool_context = TStationChatServiceV2._format_tool_context(prev_tool_data)
                # Cap tool context to avoid consuming too much of the context window
                if len(tool_context) > 8000:
                    tool_context = tool_context[:8000] + "\n... (일부 생략)"
                logger.info(f"[TOOL_CTX] Loaded {len(prev_tool_data)} tool results ({len(tool_context)} chars)")

        except Exception as e:
            logger.exception(f"[SLOTS] Slot processing failed, continuing without slots: {e}")
            slot_context = None

        # Domain classification (separate from slot processing — must not fail)
        # Also injects conversation context (user_behavior, next_action, flow) into messages
        domains, routing_result = _coordinator.classify_multi_intent(
            messages,
            session_id=request.session_id,
            user_id=request.user_id,
            trace_id=request.tracing_id,
        )
        messages = StreamingMultiAgentCoordinator._inject_conversation_context(messages, routing_result)

        # Post-classification redirect: when the user's current-turn reply was a
        # list-selection that just resolved goods_no (via step 3.8) and a
        # transactional intent is still pending, the classifier may still pick
        # [DISCOVERY] alone because the CONTINUATION DETECTION rule treats
        # list-selection replies as same-domain continuation. But at this point
        # Discovery has nothing useful to do — it would only emit a handoff line
        # ("상품 확인했어요. 바로 재고 조회로 이어갑니다") and then decide_next_action
        # often returns STOP, stranding the user without the actual transactional
        # answer. Force-route directly to [TRANSACTION] for this narrow case.
        #
        # Guard: only when goods_no was resolved THIS turn from a list-selection,
        # so later "다른 사이즈 보기" / "이 타이어 맞아?" type turns (goods_no carried
        # but not freshly picked) still go through Discovery normally.
        if (
            len(domains) == 1
            and domains[0] == MultiAgentDomain.Domain.DISCOVERY
            and goods_no_resolved_this_turn
            and merged_slots.pending_intent is not None
        ):
            logger.info(
                f"[COORDINATOR] Post-classification redirect: goods_no={merged_slots.goods_no!r} "
                f"resolved from list-selection + pending_intent={merged_slots.pending_intent!r} "
                f"→ [DISCOVERY] → [TRANSACTION]"
            )
            domains = [MultiAgentDomain.Domain.TRANSACTION]

        # P0 auto-chain code gate: when a transactional intent (price/stock/order)
        # is outstanding — either expressed THIS turn or inherited from a prior turn
        # whose tool has not yet fulfilled it — and some product is identifiable
        # (current turn text OR inherited from prior turns), but no goods_no is yet
        # confirmed, override the classifier's single-domain [DISCOVERY] pick to
        # [DISCOVERY, TRANSACTION]. Discovery resolves goods_no via search_product_tool,
        # then Transaction proceeds (price/inventory/order) in the same user turn —
        # removing the redundant "네" confirmation step.
        #
        # Guard conditions (ALL must hold):
        #   1. Classifier chose exactly [DISCOVERY] — no override of TX/SUPPORT/LEADING.
        #   2. `merged_slots.pending_intent` is set — fresh this turn OR inherited
        #      from an earlier turn whose tool has not yet fulfilled the intent.
        #      Example: user asks "재고 있어?" in turn 1, search returns multiple
        #      results, user picks a specific size in turn 2 — the stock intent is
        #      still pending and should chain to Transaction once goods_no resolves.
        #      Short replies like "네" do NOT trigger because condition #4 requires
        #      a real product hint (tire_size / tire_model / brand keyword), which
        #      a bare "네" never satisfies.
        #   3. `merged_slots.goods_no is None` — goods_no-known turns stay TX-only.
        #   4. Product hint present via ONE of:
        #        a. `merged_slots.tire_size` — current turn OR inherited from a prior
        #           turn (intentional: user says "225/45R18" then later "가격 얼마?"
        #           should continue the same product context, not re-ask).
        #        b. `merged_slots.tire_model` — typically confirmed in prior turns via
        #           LLM slot extraction; inheriting it is by design.
        #        c. Brand/model keyword in CURRENT turn text (벤투스/Dynapro/...).
        #      Pure no-product queries with no prior context ("가격 얼마에요?" on a
        #      fresh session) stay Discovery-only so Discovery can ask which model.
        #
        # Safety: even when the gate fires, the coordinator verifies goods_no was
        # actually resolved after Discovery before running Transaction (search with
        # 0/multiple results → chain stops). See StreamingMultiAgentCoordinator.stream().
        skip_decision = False
        if (
            len(domains) == 1
            and domains[0] == MultiAgentDomain.Domain.DISCOVERY
            and merged_slots.pending_intent is not None
            and merged_slots.goods_no is None
            and (
                merged_slots.tire_size is not None
                or merged_slots.tire_model is not None
                or ConversationSlots.has_product_keyword(last_user_text)
            )
        ):
            domains = [MultiAgentDomain.Domain.DISCOVERY, MultiAgentDomain.Domain.TRANSACTION]
            skip_decision = True
            logger.info(
                f"[COORDINATOR] P0 auto-chain gate triggered: "
                f"pending_intent={merged_slots.pending_intent!r} "
                f"(fresh_this_turn={regex_slots.pending_intent!r}), goods_no=None, "
                f"tire_size={merged_slots.tire_size!r}, tire_model={merged_slots.tire_model!r}, "
                f"session_id={request.session_id} → domains=[DISCOVERY, TRANSACTION]"
            )

        # STREAM MODE
        if request.stream:
            return StreamingResponse(
                TStationChatServiceV2._stream_response_multi(
                    messages,
                    domains,
                    slot_context,
                    request.session_id,
                    tool_context,
                    user_id=request.user_id,
                    trace_id=request.tracing_id,
                    skip_decision=skip_decision,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # NON STREAM MODE
        try:
            final_content = ""
            last_message_content = ""

            for event_str in TStationChatServiceV2._stream_response_multi(
                messages,
                domains,
                slot_context,
                request.session_id,
                tool_context,
                user_id=request.user_id,
                trace_id=request.tracing_id,
                skip_decision=skip_decision,
            ):
                if event_str.startswith("data: "):
                    json_str = event_str[6:].strip()
                    if json_str and json_str != "[DONE]":
                        event = json.loads(json_str)

                        if event.get("type") == "token":
                            final_content += event.get("content", "")
                        elif event.get("type") == "message":
                            last_message_content = event.get("content", "")

            # FIX: Always prefer the final message event, because it contains the QC-corrected text!
            if last_message_content:
                final_content = last_message_content

            return TStationChatResponse(content=final_content)

        except ValueError as e:
            logger.warning(f"User Error: {e}")
            raise ValueError(e)
        except Exception as e:
            logger.exception(f"Server Error: {e}")
            raise Exception("Internal Server Error")

    @staticmethod
    def _stream_guardrail_response():
        """Stream a guardrail rejection response without invoking any agent."""
        yield f"data: {json.dumps({'type': 'token', 'content': GUARDRAIL_RESPONSE}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'sub-agent', 'agent': '[DONE]', 'status': 'success'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'DONE'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    @staticmethod
    def _stream_response_multi(
        messages: list[dict],
        domains: list[MultiAgentDomain.Domain] | None = None,
        slot_context: str | None = None,
        session_id: str | None = None,
        tool_context: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        skip_decision: bool = False,
    ):
        """Stream response from multi-agent coordinator with Strict QC Layer."""

        draft_response = ""
        source_data_chunks = []
        tool_context_items = []  # Structured tool results for context preservation
        original_message_events = []  # Hold message events to sync history
        coordinator_done_event = None  # Hold the premature [DONE] event
        agent_count = 0  # Track how many agents have started

        user_query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_query = msg.get("content", "")
                break

        # 1. Iterate through the main coordinator stream
        yield f"data: {json.dumps({'type': 'agent_flow', 'agent': '[응답 생성 중]', 'status': 'processing'}, ensure_ascii=False)}\n\n"
        # Track whether a code-mapper-eligible tool was called — if so, suppress token streaming
        # to avoid the "long text flashes then gets replaced by card" UX issue.
        from services.tstation.template_mapper import _TOOL_TEMPLATE_MAP

        _suppress_tokens = False

        for event in _coordinator.stream(
            messages,
            domains=domains,
            slot_context=slot_context,
            session_id=session_id,
            tool_context=tool_context,
            user_id=user_id,
            trace_id=trace_id,
            skip_decision=skip_decision,
        ):
            event_type = event.get("type")

            # --- INTERCEPT TOKENS (Draft Response & TTFT Fix) ---
            if event_type == "token":
                if event.get("content"):
                    draft_response += event["content"]
                # Suppress tokens if a code-mapper tool was called (card will replace text)
                if not _suppress_tokens:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                continue

            # --- INTERCEPT MESSAGES (History Sync ONLY) ---
            if event_type == "message":
                original_message_events.append(event)
                continue

            # --- COLLECT SOURCE DATA (Tools Only = True Ground Truth) ---
            if event_type == "tool":
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                tool_name = event.get("tool", "Unknown")
                # Suppress tokens when a "list display" tool is called (card will replace text).
                # Exclude car lookup tools — agent may need to show selection text first.
                _SUPPRESS_ON_TOOLS = {
                    "search_product_tool",
                    "get_products_recommendations_tool",
                    "get_available_coupons_tool",
                    "get_my_coupons_tool",
                    "compare_discount_tool",
                    "search_youtube_video_tool",
                }
                if tool_name in _SUPPRESS_ON_TOOLS:
                    _suppress_tokens = True
                input_data = event.get("input", {})
                output_data = event.get("out`put", "")
                source_parts = []
                if input_data:
                    source_parts.append(f"Input: {json.dumps(input_data, ensure_ascii=False)}")
                if output_data:
                    filtered = filter_source_data(tool_name, output_data)
                    source_parts.append(f"Output: {filtered}")
                if source_parts:
                    source_data_chunks.append(f"Tool [{tool_name}]:\n" + "\n".join(source_parts))

                # Collect structured tool results for context preservation
                if output_data:
                    ctx_item = filter_for_context(tool_name, output_data, input_data)
                    if ctx_item:
                        tool_context_items.append(ctx_item)

                continue

            # --- INTERCEPT EARLY DONE EVENT ---
            if event_type == "sub-agent" and event.get("agent") == "[DONE]":
                coordinator_done_event = event
                continue

            # --- INTERCEPT DATA EVENTS (UI Template Agent) ---
            if event_type == "data":
                event_data = event.get("data", {})
                if isinstance(event_data, dict) and event_data.get("assistantResponse"):
                    assistant_response = event_data["assistantResponse"]
                    source_domain = str(event.get("source_domain", "ui_template")).upper()
                    assistant_msg_event = {
                        "type": "message",
                        "content": assistant_response,
                        "agent": f"[{source_domain} AGENT]",
                    }
                    original_message_events.append(assistant_msg_event)
                    logger.info(
                        f"[COORDINATOR] Captured assistantResponse from data event ({source_domain}): {assistant_response[:50]}..."
                    )
                # Pass through data event to frontend
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                continue

            # --- RESET DRAFT when a new sub-agent starts (multi-agent chaining) ---
            # The second agent receives the first agent's context and produces a unified response,
            # so we only need the last agent's output for QC.
            if (
                event_type == "sub-agent"
                and event.get("status") == "start"
                and event.get("agent", "") != "[UI TEMPLATE AGENT]"
            ):
                agent_count += 1
                if agent_count > 1 and draft_response.strip():
                    logger.info(
                        f"[QC_LAYER] Resetting draft_response for agent #{agent_count} — last agent should produce unified response"
                    )
                    draft_response = ""
                    original_message_events = []

            # Pass all other events (UI templates, agent flows) through
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # 2. QC AGENT DISABLED
        # Keep the final assistant message as-is (after local sanitization) without
        # invoking the strict QC agent.
        if draft_response.strip():
            draft_response = _sanitize_response(draft_response)
            if original_message_events:
                final_msg_event = original_message_events[-1]
                final_msg_event["content"] = draft_response
                yield f"data: {json.dumps(final_msg_event, ensure_ascii=False)}\n\n"
        else:
            # FALLBACK HISTORY SYNC: If no text was generated, only yield message events
            # if they actually contain text. We DO NOT want to save empty assistant
            # messages to Redis, as it pollutes the LLM's future context window.
            for msg_event in original_message_events:
                if msg_event.get("content", "").strip():  # <-- ONLY yield if it has text
                    yield f"data: {json.dumps(msg_event, ensure_ascii=False)}\n\n"

        # 4. PERSIST TOOL CONTEXT for next turn (only overwrite when new tool results exist)
        if session_id and tool_context_items:
            try:
                from services.tstation.chat_history_service import get_chat_history_service

                get_chat_history_service().save_tool_context(session_id, tool_context_items)
            except Exception as e:
                logger.warning(f"[TOOL_CTX] Failed to save tool context: {e}")

        # 5. FINALIZE THE STREAM
        if coordinator_done_event:
            yield f"data: {json.dumps(coordinator_done_event, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'DONE'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
