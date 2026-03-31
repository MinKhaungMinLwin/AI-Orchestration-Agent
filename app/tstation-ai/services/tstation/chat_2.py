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
    - Agent asks user for more information
    - Response is greeting, farewell, or acknowledgment

    CONTINUE (next_domain: "X") when:
    - User asked multi-domain question (e.g., "recommend AND tell price")
    - Example flows:
      * DISCOVERY → TRANSACTION: recommendation + price
      * DISCOVERY → TRANSACTION: recommendation + purchase
      * TRANSACTION: price + buy/reserve (single agent handles all)
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
- Just greeting ("hello", "hi", "xin chào", "안녕하세요")
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
- "price of [specific product]" → TRANSACTION (if goods_no known)
- "How much is [product name ONLY]?" → DISCOVERY → TRANSACTION (unknown goods_no, need tire size first)
- "search tires named [X]" → DISCOVERY
- "does [tire] fit [car]?" → DISCOVERY (compatibility check)
- "buy tires" → TRANSACTION
- "recommend tires" → DISCOVERY
- "warranty, return, maintenance" → SUPPORT
- When multiple intents present, return ALL relevant domains in flow order

Korean vehicle numbers follow patterns: 12가3456, 123가1234

————————————————————————————————————————————
⚠️ SPECIAL CASE: PRODUCT LINE WITH MULTIPLE SIZES
————————————————————————————————————————————

CRITICAL DISTINCTION:
• "Dynapro HPX" is a PRODUCT LINE (NOT a single SKU)
• One product line = 20–50 different tire sizes
• Each size = separate goods_no (e.g., G000000314254, G000000314255, etc.)

When user asks "How much is Dynapro HPX?" with ONLY product name:
→ Must route DISCOVERY → TRANSACTION
→ DISCOVERY engine presents TWO methods for tire size selection:

**METHOD 1: Use Registered Vehicle (Auto-confirmation)**
If user has registered vehicle:
  1. Check: User has registered vehicle in context?
  2. If YES → Extract tire_size automatically from vehicle registration
  3. Confirm with user (simple & direct):
     예: "당신의 등록된 차량은 [245/45R18] 사이즈를 사용하시네요.
          다이나프로 HPX의 이 사이즈 가격을 확인해드릴까요?
          [YES, 확인] [아니면 다른 사이즈 보기]"
     영: "Your registered vehicle uses [245/45R18].
          Would you like the price for Dynapro HPX in that size?
          [YES] [Or browse other sizes]"
  4. User confirms YES:
     - Call search_product_tool("Dynapro HPX", limit=10)
     - Filter results to get goods_no for that tire_size
     - Extract and pass goods_no to TRANSACTION agent
  5. User wants other size:
     - Go to METHOD 2 (show size table)

**METHOD 2: Browse & Select from Size Table**
If user has no registered vehicle OR wants different size:
  1. Introduce method:
     예: "다이나프로 HPX는 여러 사이즈가 있어요.
          아래 표에서 원하는 사이즈를 선택하면 가격을 알려드리겠습니다."
     영: "Dynapro HPX comes in multiple sizes.
          Select the size you'd like from the table below."
  2. Call search_product_tool("Dynapro HPX", limit=30) to fetch all sizes
  3. Display TABLE (hide goods_no, but store it in data):
     
     | No | Tire Size  | Stock          | ... |
     |----|------------|----------------|-----|
     | 1  | 245/45R18  | ✓ In Stock      |
     | 2  | 235/55R19  | ✓ In Stock      |
     | 3  | 255/50R16  | △ Limited Stock |
     | 4  | 235/60R16  | ✓ In Stock      |

  4. Ask user to select:
     예: "원하는 사이즈를 선택해주세요. (예: '245/45R18' 또는 번호 '1')"
     영: "Which size would you like? (e.g., '245/45R18' or '1')"
  5. User selects → Extract corresponding goods_no
  6. Pass goods_no to TRANSACTION agent for price query

**Decision Logic:**
```
User: "Dynapro HPX 가격?"
  → Check: registered vehicle exists?
     YES → Present METHOD 1 (with METHOD 2 as fallback)
     NO → Present METHOD 2 directly
  → User selects size → Extract goods_no → TRANSACTION for price
```

**Output to TRANSACTION Agent:**
Always format: "Product (tire_size) - goods_no"
Example: "Selected: Dynapro HPX (245/45R18) - G000000314254"

This ensures Transaction Agent can extract correct goods_no for price query.

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

        # Final done event
        yield {"type": "sub-agent", "agent": "[DONE]", "status": "success"}


# Singleton coordinator instance
_coordinator = StreamingMultiAgentCoordinator()


class TStationChatServiceV2:
    """V2 Chat service with multi-agent streaming support."""

    @staticmethod
    def _build_messages_with_user_info(request: TStationChatRequest) -> list[dict]:
        """Build messages with user info injected conditionally when user references personal context."""
        messages = list(request.messages)

        user_info = None
        if request.access_token:
            user_info = get_user_info_from_token(request.access_token)

        if not user_info:
            messages[-1]["content"] = (
                f"# Response user in Korean language\n"
                f"{messages[-1]["content"]}"
            )
            return messages

        user_info_str = "\n".join([f"# {k}: {v}" for k, v in user_info.items()])

        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                original_content = messages[i].get("content", "")

                messages.insert(i, {
                    "role": "user",
                    "content": (
                        f"# My information:\n{user_info_str}\n"
                        f"# Only use this info when user asks about personal context "
                        f"(my car, my order, my profile, etc.)"
                    ),
                })
                messages[i + 1]["content"] = (
                    f"# Response user in Korean language\n"
                    f"User question: {original_content}"
                )
                break

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
