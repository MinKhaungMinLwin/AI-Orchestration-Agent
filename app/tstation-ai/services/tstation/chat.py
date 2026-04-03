import json
import logging
from typing import Iterator
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
    ui_template_subagent,
)
from common.jwt_utils import get_user_info_from_token
from common.curr_time import get_current_time

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

    STOP when:
    - Single-domain request completed
    - Response is greeting, farewell, or acknowledgment
    - Agent asks user for more information (e.g., user needs to provide input)

    CONTINUE when:
    - User asked multi-domain question (e.g., "recommend AND tell price")
    - Example flows:
      * DISCOVERY → TRANSACTION: recommendation + price
      * DISCOVERY → TRANSACTION: recommendation + purchase
      * TRANSACTION: price + buy/reserve (single agent handles all)
    - Agent needs another agent's tools to complete the request

    ⚠️ CRITICAL HANDOVER RULES:
    - Transaction Agent says "검색", "확인하기 위해", "상품 번호를 확인" → CONTINUE → DISCOVERY
      (Agent needs Discovery tools: search_product, get_user_vehicles, check_compatibility)
    - Discovery Agent completed product search with goods_no → CONTINUE → TRANSACTION
    - Discovery Agent says "다른 사이즈로 검색" → CONTINUE → DISCOVERY
    - Agent asks user to input tire size manually → STOP (wait for user input)

    KEY PRINCIPLE: If agent says it will search but has no tools to search → HANDOVER NEEDED.

    ⚠️ CRITICAL RULE — [ORDER_READY] DETECTION:
        If the previous agent response contains the text "[ORDER_READY]",
        you MUST return next_action=CONTINUE and next_domain="transaction".
        This block means the Discovery Agent has resolved the goods_no and
        the Transaction Agent must create the order draft immediately.
        Do NOT return STOP when [ORDER_READY] is present, even if the agent
        also asked a confirmation question.
    """)


def decide_next_action(
    original_messages: list[dict],
    previous_agent_response: str,
    previous_domain: str,
) -> AgentDecision:
    from langchain_litellm import ChatLiteLLM
    from langchain_core.messages import SystemMessage, HumanMessage

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
    human_msg = HumanMessage(content=dedent(f"""
        Original User Request: {user_message}

        Previous Agent Domain: {previous_domain}

        Previous Agent Response:
        {previous_agent_response}

        Please decide the next action.
    """))

    try:
        result: AgentDecision = structured_model.invoke([system_msg, human_msg])
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
    domains: list[Domain] = Field(
        description="List of domains detected in the request, ordered by priority"
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
    """Classification prompt that detects multi-intent with flow sequences."""
    return f"""
Current Time: {get_current_time()}

You are a domain classifier for T-Station AI (Hankook Tire).
Classify user message into ONE OR MORE domains based on detected intents.
Also identify the FLOW SEQUENCE (ordered list of domains) for the request.

DOMAINS:
- TRANSACTION: Price, stock (logistics/store), inventory, store availability, store search by location/name, purchase, checkout, order tracking, reservation
- SUPPORT: FAQ, warranty, returns, policies, maintenance, human agent
- DISCOVERY: Product search by name, recommendations, vehicle-tire compatibility check, features
- LEADING: Greeting, unclear intent

====================================================
FLOW SEQUENCES (Tool/Agent Chains)
====================================================

Map user queries to the correct flow sequence:

EXAMPLE QUERIES → FLOW:

1. "쏘나타에 맞는 타이어 추천하고 가격 알려줘"
   "Recommend tires for Sonata and tell me the price"
   → DISCOVERY → TRANSACTION
   (Compatibility → Recommendation → Price)

2. "추천 타이어 중 재고 있는 매장 알려줘"
   "Show stores that have recommended tires in stock"
   → DISCOVERY → TRANSACTION
   (Recommendation → Store Inventory)

3. "벤투스 S1 evo3 가격이랑 강남점 재고 알려줘"
   "Tell me Ventus S1 evo3 price and Gangnam stock"
   → TRANSACTION
   (Price + Inventory - single agent handles all)

4. "내 차에 맞는 타이어 추천하고 바로 주문할게"
   "Recommend tires for my car and I'll order immediately"
   → DISCOVERY → TRANSACTION
   (Compatibility → Recommendation → Purchase)

5. "타이어 추천하고 할인 가격 알려줘"
   "Recommend tires and tell me discounted price"
   → DISCOVERY → TRANSACTION
   (Recommendation → Price)

6. "추천 타이어 중 재고 있는 것만 보여줘"
   "Show only recommended tires that are in stock"
   → DISCOVERY → TRANSACTION
   (Recommendation → Inventory)

7. "추천 타이어 가격 비교해줘"
   "Compare the prices of recommended tires"
   → DISCOVERY → TRANSACTION
   (Recommendation → Price)

8. "벤투스 S1 evo3 설명하고 가격 알려줘"
   "Explain Ventus S1 evo3 and tell me the price"
   → DISCOVERY → TRANSACTION
   (Description → Price)

9. "추천 타이어 중 강남점 재고 알려줘"
   "Show Gangnam store stock for recommended tires"
   → DISCOVERY → TRANSACTION
   (Recommendation → Store Inventory)

10. "쏘나타 타이어 추천하고 장착 예약할게"
    "Recommend tires for Sonata and make installation reservation"
    → DISCOVERY → TRANSACTION
    (Compatibility → Recommendation → Reservation)

11. "강남점 재고 있는 타이어 가격 알려줘"
    "Tell me the price of tires in stock at Gangnam store"
    → TRANSACTION
    (Store Inventory + Price - single agent)

12. "추천 타이어 리뷰랑 가격 알려줘"
    "Show reviews and prices of recommended tires"
    → DISCOVERY → TRANSACTION
    (Recommendation → Description → Price)

13. "인기 타이어 가격이랑 재고 알려줘"
    "Tell me the price and stock of popular tires"
    → DISCOVERY → TRANSACTION
    (Recommendation → Price + Inventory)

14. "내 차 타이어 추천하고 장착 예약하고 싶어요"
    "Recommend tires for my car and make installation reservation"
    → DISCOVERY → TRANSACTION
    (Compatibility → Recommendation → Reservation)

15. "재고 있는 타이어 추천해주세요"
    "Recommend tires that are in stock"
    → DISCOVERY → TRANSACTION
    (Recommendation → Filter by Inventory)

16. "타이어 추천하고 가까운 매장 알려줘"
    "Recommend tires and show nearby stores"
    → DISCOVERY → TRANSACTION
    (Recommendation → Store)

17. "재고 있는 매장 알려주고 예약할게"
    "Show stores with stock and make a reservation"
    → TRANSACTION
    (Store Search → Inventory → Reservation - single agent)

18. "벤투스 타이어 가격이랑 장착 예약"
    "Ventus tire price and installation reservation"
    → TRANSACTION
    (Price + Reservation - single agent)

19. "추천 타이어 중 할인 상품 알려줘"
    "Show discounted products among recommended tires"
    → DISCOVERY → TRANSACTION
    (Recommendation → Price)

20. "타이어 추천하고 비교해줘"
    "Recommend tires and compare them"
    → DISCOVERY
    (Recommendation → Description)

21. "벤투스 S2 225/45R17 4개 주문할게"
    "Order 4 Ventus S2 225/45R17"
    → DISCOVERY → TRANSACTION
    (Product Name+Size Search → goods_no Resolution → Order Draft)

22. "키네르기 EX 205/55R16 2개 사고 싶어"
    "I want to buy 2 Kinergy EX 205/55R16"
    → DISCOVERY → TRANSACTION
    (Product Name+Size Search → goods_no Resolution → Order Draft)

23. "Ventus S1 evo3 245/45R18 주문"
    "Order Ventus S1 evo3 245/45R18"
    → DISCOVERY → TRANSACTION
    (Product Name+Size Search → Order)

====================================================
DECISION RULES
====================================================

TRANSACTION if user wants:
- "How much", "price", "cost", "discount" for SPECIFIC product (goods_no known)
- "In stock?", "available?" for specific product at specific store
- Check logistics stock (warehouse availability)
- Find stores by LOCATION (e.g., "stores near Gangnam", "stores in Seoul")
- Find stores by NAME (e.g., "find Hankook store")
- Check store inventory (which stores have this tire)
- "Buy", "purchase", "order", "checkout"
- Track existing order (provide order number)
- Create order draft
- Book store visit/reservation with specific date/time
Examples: "How much is Ventus S1 evo3?", "Is G000000314254 in stock?", "Show me stores near Gangnam", "I want to buy tires", "Book installation at 2pm", "Track my order 12345"

DISCOVERY if user wants:
- Search products by NAME/KEYWORD (e.g., "search for Ventus", "show me Hankook tires")
- Recommend tires (vehicle-specific or general)
- Check if specific tire FITS specific vehicle ("does 205/55R16 fit my BMW?")
- Product specifications, features, technology
Examples: "Find tires called Ventus", "What tires fit my car 12가3456?", "Will these tires fit my vehicle?"

SUPPORT if user wants:
- Tire replacement guidance (when to replace, air pressure, maintenance)
- Policy questions (warranty terms, return conditions, refund process)
- General guidance without purchase intent
- Request for human agent / 1:1 inquiry
- Write/save 1:1 inquiry with AI-summarized content
- "1:1 문의 작성", "상담원 연결", "이 문제를 1:1로 저장하고 싶어요"
Examples: "When should I replace tires?", "What's the warranty policy?", "Can I return this?", "1:1 문의 작성해주세요", "상담원 연결해주세요"

LEADING if:
- Just greeting ("hello", "hi", "안녕하세요")
- No clear goal or action requested
- General capability questions ("what can you do")
Examples: "Hi", "What can you help me with?", "Hello"

====================================================
MULTI-INTENT DETECTION
====================================================

If user request contains multiple intents, detect ALL relevant domains.
The "domains" list should be ordered by the FLOW SEQUENCE.

Examples:
- "Explain Ventus S1 evo3 and tell me the price" → DISCOVERY, TRANSACTION
- "Find tires for my BMW and check if in stock at nearby store" → DISCOVERY, TRANSACTION
- "Recommend tires and their warranty" → DISCOVERY, SUPPORT
- "How much is this tire? Also, what's the warranty?" → TRANSACTION, SUPPORT

KEY PRINCIPLES:
- "stores near [location]" → TRANSACTION
- "find stores" → TRANSACTION
- "price of [specific product]" → TRANSACTION
- "search tires named [X]" → DISCOVERY
- "does [tire] fit [car]?" → DISCOVERY (compatibility check)
- "buy tires" → TRANSACTION
- "recommend tires" → DISCOVERY
- "warranty, return, maintenance" → SUPPORT
- When multiple intents present, return ALL relevant domains in flow order

Korean vehicle numbers follow patterns: 12가3456, 123가1234
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

    def classify_multi_intent(self, messages: list) -> list[MultiAgentDomain.Domain]:
        """Classify user message into one or more domains."""
        from langchain_litellm import ChatLiteLLM
        from langchain_core.messages import SystemMessage

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

            result: MultiAgentDomain = structured_model.invoke(all_messages)
            logger.info(f"[MULTI-DOMAIN] Classification result: {result}")
            return result.domains if result.domains else [MultiAgentDomain.Domain.LEADING]

        except Exception as e:
            logger.exception(f"[MULTI-DOMAIN] Classification failed: {e}")
            return [MultiAgentDomain.Domain.LEADING]

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

        return {
            "role": "system",
            "content": f"[Context from previous steps]\n" + "\n".join(parts)
        }

    def stream(
        self,
        messages: list[dict],
        domains: list[MultiAgentDomain.Domain] | None = None,
    ) -> Iterator[dict]:
        """
        Chain multiple agents and stream their outputs.

        Args:
            messages: Original user messages
            domains: Pre-classified domains (optional, will classify if not provided)

        Yields:
            Stream events from all agents in sequence
        """
        # Classify if domains not provided
        if domains is None:
            domains = self.classify_multi_intent(messages)

        if not domains:
            domains = [MultiAgentDomain.Domain.LEADING]

        logger.info(f"[COORDINATOR] Streaming for domains: {[d.value for d in domains]}")

        accumulated_context = {}
        accumulated_tool_data = []  # Collect tool outputs for UI Template Agent

        is_first_agent = True

        for domain in domains:
            agent = self.agent_map.get(domain)
            if not agent:
                logger.warning(f"[COORDINATOR] No agent found for domain: {domain}")
                continue

            # Build enriched messages with context from previous agents
            enriched_messages = list(messages)

            # Append previous agent's assistant message if exists
            if accumulated_context:
                for prev_domain, content in accumulated_context.items():
                    if content and content.strip():
                        enriched_messages.append({
                            "role": "assistant",
                            "content": str(content)
                        })
                        enriched_messages.append({
                            "role": "user",
                            "content": "Continue with next step"
                        })
                        logger.info(f"[COORDINATOR] Passing context to {domain.value}")
                        break  # Only take first previous agent

            # Append accumulated tool data for next agent (so they can use results like goods_no)
            if accumulated_tool_data:
                tool_summary = json.dumps(accumulated_tool_data, ensure_ascii=False, indent=2)
                enriched_messages.append({
                    "role": "system",
                    "content": f"[Previous agent tool results]\n{tool_summary}"
                })
                logger.info(f"[COORDINATOR] Passing {len(accumulated_tool_data)} tool results to {domain.value}")

            domain_key = domain.value
            logger.info(f"[COORDINATOR_MESSAGE] Domain: {domain_key}, enriched_messages: {json.dumps(enriched_messages, ensure_ascii=False, indent=2)[:1000]}")

            # Yield agent start event
            yield {
                "type": "sub-agent",
                "agent": f"[{domain_key.upper()} AGENT]",
                "status": "start",
            }

            # Stream from agent and yield events immediately
            full_response = ""
            for event in agent.stream(enriched_messages):
                # Tag with source domain for UI
                event["source_domain"] = domain_key
                yield event

                # Capture message content for context passing
                if event.get("type") == "message":
                    content = event.get("content", "")
                    if content:
                        accumulated_context[domain_key] = content
                        full_response = content
                        logger.info(f"[COORDINATOR] Captured message for {domain_key}: {content}...")

                # Capture tool outputs for UI Template Agent
                if event.get("type") == "tool":
                    tool_output = event.get("output", "")
                    if tool_output:
                        try:
                            parsed = json.loads(tool_output) if isinstance(tool_output, str) else tool_output
                            accumulated_tool_data.append({
                                "tool": event.get("tool", ""),
                                "data": parsed
                            })
                        except (json.JSONDecodeError, TypeError):
                            accumulated_tool_data.append({
                                "tool": event.get("tool", ""),
                                "data": tool_output
                            })

            # Yield agent completion event
            yield {
                "type": "sub-agent",
                "agent": f"[{domain_key.upper()} AGENT]",
                "status": "done",
            }

            # LLM Decision: After first agent, use LLM to decide next action
            if is_first_agent:
                is_first_agent = False
                decision = decide_next_action(
                    original_messages=messages,
                    previous_agent_response=full_response,
                    previous_domain=domain_key,
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

        # Run UI Template Agent with accumulated data
        if accumulated_tool_data:
            logger.info(f"[COORDINATOR] Running UI Template Agent with {len(accumulated_tool_data)} tool outputs")

            # Build context for UI Template Agent
            ui_messages = list(messages)
            # Append accumulated context
            for prev_domain, content in accumulated_context.items():
                if content and content.strip():
                    ui_messages.append({
                        "role": "assistant",
                        "content": str(content)
                    })
                    ui_messages.append({
                        "role": "user",
                        "content": "Continue with next step"
                    })
                    break

            # Append tool data summary
            tool_summary = json.dumps(accumulated_tool_data, ensure_ascii=False, indent=2)
            ui_messages.append({
                "role": "system",
                "content": f"[Accumulated tool data for UI rendering]\n{tool_summary}"
            })
            ui_messages.append({
                "role": "user",
                "content": "Render this data as UI templates using the appropriate tools. Format each item as a UI template event."
            })

            # Yield UI Template Agent start event
            yield {
                "type": "sub-agent",
                "agent": "[UI TEMPLATE AGENT]",
                "status": "start",
            }

            # Stream from UI Template Agent (use stream_template to get data events)
            for event in ui_template_subagent.stream_template(ui_messages):
                event["source_domain"] = "ui_template"
                yield event

            # Yield UI Template Agent completion event
            yield {
                "type": "sub-agent",
                "agent": "[UI TEMPLATE AGENT]",
                "status": "done",
            }

        # Final done event
        yield {"type": "sub-agent", "agent": "[DONE]", "status": "success"}


# Singleton coordinator instance
_coordinator = StreamingMultiAgentCoordinator()


class TStationChatServiceV2:
    """V2 Chat service with multi-agent streaming support."""

    @staticmethod
    def _build_messages_with_user_info(request: TStationChatRequest) -> list[dict]:
        """Build messages with user info injected as system context for all agents."""
        import copy
        messages = copy.deepcopy(request.messages)

        user_info = None
        if request.access_token:
            user_info = get_user_info_from_token(request.access_token)

        # Merge user_info from UI (overrides JWT fields if overlap)
        if request.user_info:
            if user_info is None:
                user_info = {}
            user_info = {**user_info, **request.user_info}

        # get user info with mbr_nm
        # Always add language instruction to last user message
        if messages and messages[-1].get("role") == "user":
            # Remove duplicate "hi" message if exists (frontend sends both "hi" and "# Respond in Korean language\nhi")
            if len(messages) >= 2 and messages[-2].get("role") == "user" and messages[-2].get("content") == "hi":
                messages.pop(-2)

            messages[-1]["content"] = (
                f"# Respond in Korean language\n"
                f"{messages[-1]['content']}"
            )

        # If user info available, inject as system message at beginning
        if user_info:
            # Build user info context
            user_info_lines = []
            for k, v in user_info.items():
                user_info_lines.append(f"{k}: {v}")
            
            user_context = "\n".join(user_info_lines)

            user_context_message = {
                "role": "user",
                "content": (
                    f"## USER CONTEXT INFORMATION (Always Available)\n"
                    f"{user_context}\n\n"
                    f"## INSTRUCTIONS FOR AGENTS:\n"
                    f"🔹 Always prioritize data provided directly by the user\n"
                    f"🔹 If no direct data is provided, reference the personal data below\n"
                )
            }

            # Insert user context message after history, before current user message
            # Result: [history..., USER_CONTEXT, current with prefix]
            messages.insert(len(request.messages) - 1, user_context_message)

        return messages

    @staticmethod
    def chat(request: TStationChatRequest):
        """
        T-Station AI Chat V2 - Multi-Agent Streaming

        Workflow:
        1. Classify multi-intent (detect all relevant domains)
        2. Chain agents and stream their outputs
        """
        logger.debug(f"[CHAT_V2] Received request: {request}")

        set_tstation_be_token(request.access_token)

        messages = TStationChatServiceV2._build_messages_with_user_info(request)
        logger.debug(f"[CHAT_V2] Messages: {json.dumps(messages, ensure_ascii=False, indent=2)}")

        # STREAM MODE
        if request.stream:
            return StreamingResponse(
                TStationChatServiceV2._stream_response_multi(messages),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # NON STREAM MODE - invoke leading agent only
        try:
            content = leading_agent.invoke(messages)
            return TStationChatResponse(content=content)
        except ValueError as e:
            logger.warning(f"User Error: {e}")
            raise ValueError(e)
        except Exception as e:
            logger.exception(f"Server Error: {e}")
            raise Exception("Internal Server Error")

    @staticmethod
    def _stream_response_multi(messages: list[dict]):
        """Stream response from multi-agent coordinator."""
        for event in _coordinator.stream(messages):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
