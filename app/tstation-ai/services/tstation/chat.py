import json
import logging
import re
from typing import Iterator, Optional
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
    QC_LLM,
)
from common.jwt_utils import get_user_info_from_token
from common.curr_time import get_current_time
from services.tstation.common.pii_guardrail import check_pii, GUARDRAIL_RESPONSE

from services.tstation.agents.g_qc_agent.agent import invoke_qc
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
      (Transaction Agent will handle: price lookup, quantity check, store selection, cart/order)
    - Discovery Agent says "다른 사이즈로 검색" → CONTINUE → DISCOVERY
    - Agent asks user to input tire size manually → STOP (wait for user input)
    - Transaction Agent asks user to select quantity → STOP (wait for user input)
    - Transaction Agent asks user to choose store vs cart → STOP (wait for user input)

⚠️ PRE-ORDER PREVIEW FLOW RULES:
    - Transaction Agent shows pre-order preview (Flow 5.5) → STOP (wait for user confirmation)
    - User confirms order ("바로 주문", "주문할게") → CONTINUE → TRANSACTION (quick_order_tool)
    - User selects from recommendActions → STOP (wait for user input, Transaction handles update)
    - User says "장바구니로" / "나중에" → STOP (Transaction handles save_to_cart_tool)
    - User says "예약 날짜 없이 진행" → STOP (Transaction handles isReadyToAddToCart flow)
    - Pre-order preview with missing bookingDateTime → recommendActions shown → STOP

    KEY PRINCIPLE: If agent says it will search but has no tools to search → HANDOVER NEEDED.

    ⚠️ CRITICAL RULE — DISCOVERY → TRANSACTION DETECTION:
        If the Discovery Agent response contains goods_no (e.g., G000000XXXXXX)
        and mentions any of: "가격을 확인", "주문 진행", "연결합니다",
        "매장", "재고", "장착", "배송",
        you MUST return next_action=CONTINUE and next_domain="transaction".

        This applies to ALL of:
        - Price queries: Discovery found goods_no → Transaction gets price
        - Order queries: Discovery found goods_no → Transaction handles order
        - Store queries: Discovery found goods_no → Transaction finds stores / checks inventory
        - Installation queries: Discovery found goods_no → Transaction checks today install / T-NA delivery

        Do NOT return STOP when Discovery has found goods_no and the original
        user request includes price/order/store/inventory/installation intent.
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
- DISCOVERY: Product search by name, recommendations, vehicle-tire compatibility check, features, product video reviews, YouTube video search
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

8.1. "Dynapro HPX 가격 얼마야?"
     "How much is Dynapro HPX?"
     → DISCOVERY → TRANSACTION
     (Product Name Search with JWT tire size → Price)
     ⚠️ goods_no NOT known → DISCOVERY first, NOT TRANSACTION alone

8.2. "벤투스 S2 가격"
     "Ventus S2 price"
     → DISCOVERY → TRANSACTION
     (Product Name Search → Price)

8.3. "스콜피온제로 2755519 재고있어?"
     "Is Scorpion Zero 275/55R19 in stock?"
     → DISCOVERY → TRANSACTION
     (Product Name + Size Search → goods_no Resolution → Logistics Inventory Check)
     ⚠️ goods_no NOT known → DISCOVERY first, NOT TRANSACTION alone

8.4. "벤투스 S2 재고 확인해줘"
     "Check Ventus S2 stock"
     → DISCOVERY → TRANSACTION
     (Product Name Search → goods_no Resolution → Logistics Inventory Check)

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
    (Product Name+Size Search → goods_no Resolution → Quantity Confirm → Store or Cart)

22. "키네르기 EX 205/55R16 2개 사고 싶어"
    "I want to buy 2 Kinergy EX 205/55R16"
    → DISCOVERY → TRANSACTION
    (Product Name+Size Search → goods_no Resolution → Quantity Confirm → Store or Cart)

23. "Ventus S1 evo3 245/45R18 주문"
    "Order Ventus S1 evo3 245/45R18"
    → DISCOVERY → TRANSACTION
    (Product Name+Size Search → Quantity Confirm → Store or Cart)

24. "장바구니에 담아줘"
    "Save to cart"
    → TRANSACTION
    (Cart Save - goods_no and qty must be in context)

25. "{{goods_no}} 4개 주문할게"
    "Order 4 of {{goods_no}}" (e.g., "G012345678901")
    → TRANSACTION
    (goods_no known → Quantity confirmed → Store or Cart)

26. "벤투스 S2 AS 살 수 있는 매장 찾아줘"
    "Find stores where I can buy Ventus S2 AS"
    → DISCOVERY → TRANSACTION
    (Product Name Search → goods_no Resolution → Store Search / Store Inventory)

27. "Ventus S2 AS 4개 살건데 오늘 장착 가능한 매장 찾아줘"
    "I want to buy 4 Ventus S2 AS, find stores that can install today"
    → DISCOVERY → TRANSACTION
    (Product Name Search → goods_no Resolution → Store Inventory with today install filter)

28. "키네르기 EX T바로배송 되는 매장 알려줘"
    "Show stores with T-NA delivery for Kinergy EX"
    → DISCOVERY → TRANSACTION
    (Product Name Search → goods_no Resolution → Store Inventory with T-NA filter)

29. "벤투스 S2 AS 올마이티 매장에서 사고 싶어"
    "I want to buy Ventus S2 AS at an All My T store"
    → DISCOVERY → TRANSACTION
    (Product Name Search → goods_no Resolution → All My T Store Search)

30. "이벤트 알려줘" / "현재 진행중인 이벤트 뭐야?"
    "Tell me about current events"
    → DISCOVERY
    (get_events_tool → Display event list)

31. "기획전 정보" / "지금 어떤 기획전 하고 있어?"
    "What promotions are available?"
    → DISCOVERY
    (get_deals_tool → Display deal list)

32. "이벤트랑 기획전 다 알려줘"
    "Tell me about events AND promotions"
    → DISCOVERY
    (get_events_tool + get_deals_tool → Display both sections)

29. "벤투스 S1 리뷰 영상 있어?"
    "Do you have Ventus S1 review videos?"
    → DISCOVERY
    (search_youtube_video_tool → Display video list)

30. "타이어 소음 테스트 영상 보여줘"
    "Show me tire noise test videos"
    → DISCOVERY
    (search_youtube_video_tool → Display video list)

31. "iON 타이어 리뷰 영상"
    "iON tire review videos"
    → DISCOVERY
    (search_youtube_video_tool → Display video list)

32. "주문 확인해주세요" / "주문 정보 다시 보여줘"
    "Check my order" / "Show order info again"
    → TRANSACTION
    (Pre-order preview → Order confirmation → quick_order_tool)

33. "결제 금액 확인したい"
    "Check payment amount"
    → TRANSACTION
    (Pre-order preview → paymentAmount calculation)

34. "예약 날짜 선택해줘" / "날짜 추천받아서 예약할게"
    "Select booking date for me" / "Book based on recommended date"
    → TRANSACTION
    (Pre-order preview with recommendActions → User selects action → quick_order_tool)

35. "장바구니로 저장할게" / "나중에 주문할게"
    "Save to cart" / "Order later"
    → TRANSACTION
    (Pre-order preview isReadyToAddToCart=true → save_to_cart_tool)

36. "바로 주문할게" / "지금 주문할게"
    "Order now" / "I'll order now"
    → TRANSACTION
    (Pre-order preview isReadyToOrder=true → quick_order_tool)

37. "예약날짜 없이 주문 진행해줘" / "매장만 선택할게"
    "Proceed without booking date" / "Just select store"
    → TRANSACTION
    (Pre-order preview isReadyToOrder=false → isReadyToAddToCart=true → save_to_cart_tool)

38. "방문 방법 선택해줘" / "哪种访问方式好?"
    "Which visit method to choose?" / "Which visit method is better?"
    → TRANSACTION
    (Pre-order preview with recommendActions → visitMethod selection)

39. "G000000314254이랑 G000000312692 가격 비교해줘"
    "Compare prices between G000000314254 and G000000312692"
    → TRANSACTION
    (Multiple goods_no known → compare_discount_tool)

40. "벤투스 S2랑 키네르기 EX 가격 비교해줘"
    "Compare prices between Ventus S2 and Kinergy EX"
    → DISCOVERY → TRANSACTION
    (Product Name Search → goods_no Resolution → Discount Price Comparison)

41. "추천 타이어들 가격 비교해서 가장 싼 거 알려줘"
    "Compare the recommended tires and tell me which is cheapest"
    → DISCOVERY
    (Recommendation → compare_discount_tool → UI Template Agent)

42. "둘 중 어느 게 더 싸?", "Which one is cheaper?"
    "Which one is cheaper?" (when multiple products in context)
    → DISCOVERY
    (Discovery Agent has compare_discount_tool)

43. "이 제품들 할인 가격 비교해줘"
    "Compare discount prices for these products"
    → DISCOVERY
    (Discovery Agent has compare_discount_tool)

====================================================
PRE-ORDER PREVIEW FLOW RULES
====================================================

After user selects store path (Step 5A) or cart path (Step 5B), BEFORE calling API:
→ Transaction Agent displays pre-order preview (markdown table)
→ User reviews: carInfo, product, quantity, storeName, bookingDateTime, visitMethod, paymentAmount
→ isReadyToOrder: user confirms all info → quick_order_tool
→ isReadyToAddToCart: missing critical info → save_to_cart_tool
→ recommendActions: prompts for missing info with suggested Korean phrases

Flow detection:
- User confirms order → TRANSACTION (quick_order_tool)
- User selects from recommendActions → TRANSACTION (update orderInfo → re-show preview)
- User says "장바구니로" / "나중에" → TRANSACTION (save_to_cart_tool)
- User changes mind mid-flow → same agent handles path switch

====================================================
DECISION RULES
====================================================

TRANSACTION if user wants:
- "How much", "price", "cost", "discount" for product with KNOWN goods_no (e.g., "{{goods_no}} 가격" - format: G + 12 digits)
- **Price comparison** between multiple products ("비교", "둘 중 어느 게 더 싸", "which is cheaper", "가격 비교")
- "In stock?", "available?" for specific product at specific store
- Check logistics stock (warehouse availability)
- Find stores by LOCATION (e.g., "stores near Gangnam", "stores in Seoul")
- Find stores by NAME (e.g., "find Hankook store")
- Check store inventory (which stores have this tire)
- "Buy", "purchase", "order", "checkout" with goods_no known
- Track existing order (provide order number)
- "장바구니에 담아줘", "장바구니 저장" (save to cart)
- Select quantity, select store for order
- Book store visit/reservation with specific date/time
- **Pre-order confirmation** ("주문 확인", "바로 주문", "예약 날짜 선택")
- **Cart save** ("장바구니로 저장", "나중에 주문할게")
- **Visit method selection** ("방문 방법", "어떻게 가지러 오지")
- **Express store visit intent** (e.g., "방문할게", "visiting", "찜아갈게", "I'll visit [store]")
Examples: "{{goods_no}} 가격 얼마야?", "Is {{goods_no}} in stock?", "Show me stores near Gangnam", "{{goods_no}} 4개 주문할게", "장바구니에 담아줘", "Book installation at 2pm", "Track my order 12345", "주문 확인해주세요", "바로 주문할게", "장바구니로 저장할게", "I'll visit [store name]", "방문할게요", "[매장명] 방문"

DISCOVERY if user wants:
- Search products by NAME/KEYWORD (e.g., "search for Ventus", "show me Hankook tires")
- Recommend tires (vehicle-specific or general)
- Check if specific tire FITS specific vehicle ("does 205/55R16 fit my BMW?")
- Product specifications, features, technology
- **Price for product by NAME (goods_no NOT known)** → DISCOVERY to find goods_no
- View user's registered vehicles (list my cars, my vehicle list)
- **Event/Deal information** ("이벤트 알려줘", "기획전 정보", "현재 진행중인 이벤트")
Examples: "Find tires called Ventus", "What tires fit my car {{vehicle_number}}?", "Will these tires fit my vehicle?", "Dynapro HPX 가격 얼마야?", "벤투스 S2 가격", "List my cars", "Show my registered vehicles", "이벤트 알려줘", "기획전 정보"

⚠️ CRITICAL DISTINCTION for price queries:
- "{{goods_no}} 가격" (e.g., "G012345678901") → goods_no KNOWN → TRANSACTION only
- "Dynapro HPX 가격" → goods_no NOT known → DISCOVERY, TRANSACTION
- "벤투스 S2 가격 얼마야?" → goods_no NOT known → DISCOVERY, TRANSACTION

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

⚠️ CRITICAL — CONTINUATION DETECTION:
If the PREVIOUS assistant message asked the user to SELECT or CHOOSE (e.g., numbered list, "번호로 답해 주세요", "선택해 주세요"),
and the user replies with a short answer (number like "1", "2번", or a name like "제타", "i30"):
→ This is a CONTINUATION of the previous flow, NOT a new intent.
→ Look at the ORIGINAL user request in conversation history to determine the full intent.
→ If the original request included order/purchase intent (e.g., "주문할래", "사고 싶어"):
  → Classify as DISCOVERY, TRANSACTION (vehicle selection is part of order flow)
→ If the original request was recommendation only (e.g., "추천해줘"):
  → Classify as DISCOVERY only
→ If the previous assistant was in TRANSACTION (e.g., store selection):
  → Classify as TRANSACTION

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

    @staticmethod
    def _save_tool_derived_slots(session_id: str, tool_name: str, parsed_data: dict, tool_input: dict | None = None):
        """Persist goods_no, shop_id, and tire_size from successful tool results/inputs to slots."""
        from schemas.tstation.slots import ConversationSlots
        from services.tstation.chat_history_service import get_chat_history_service

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
    ) -> Iterator[dict]:
        """
        Chain multiple agents and stream their outputs.

        Args:
            messages: Original user messages
            domains: Pre-classified domains (optional, will classify if not provided)
            slot_context: Formatted slot context string to inject into agent messages
            session_id: Session ID for persisting tool-derived slots (goods_no, shop_id)
            tool_context: Formatted tool results from previous turn for context preservation

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
            # Order: slot_context | messages (with user_context inside) | current_user_msg LAST | accumulated_context LAST
            enriched_messages = []

            # 1. slot_context FIRST
            if slot_context:
                enriched_messages.append({
                    "role": "system",
                    "content": slot_context,
                })

            # 1.5. tool_context from previous turn (structured tool results)
            if tool_context:
                enriched_messages.append({
                    "role": "system",
                    "content": tool_context,
                })

            # 2. Original messages (already contains user_context from _build_messages_with_user_info)
            #    These messages have current_user_msg at the LAST position
            enriched_messages.extend(list(messages))

            # 3. Append accumulated_context AFTER current_user_msg (for handover agents)
            if accumulated_context:
                for prev_domain, content in accumulated_context.items():
                    if content and content.strip():
                        enriched_messages.append({
                            "role": "assistant",
                            "content": str(content)
                        })
                        enriched_messages.append({
                            "role": "user",
                            "content": (
                                "Based on the previous agent's findings above, produce a SINGLE unified response for the user. "
                                "Include key findings from the previous agent (e.g., compatibility results, product info) and "
                                "seamlessly add your own results (e.g., pricing, inventory, store info). "
                                "Do NOT repeat introductory greetings or offer intermediate choices that are already resolved. "
                                "The response must read as ONE coherent answer, not two separate answers concatenated together."
                            )
                        })
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
                        user_text = " ".join(
                            msg.get("content", "") for msg in messages if msg.get("role") == "user"
                        )
                        qty_match = re.search(r"(\d+)\s*개", user_text)
                        ord_qty = int(qty_match.group(1)) if qty_match else 2
                        accumulated_tool_data.append({
                            "tool": "user_intent",
                            "data": {"ord_qty": ord_qty}
                        })
                        if qty_match:
                            logger.info(f"[COORDINATOR] Extracted ord_qty={ord_qty} from user message")
                        else:
                            logger.info(f"[COORDINATOR] No qty found in user message, using default ord_qty={ord_qty}")

                tool_summary = json.dumps(accumulated_tool_data, ensure_ascii=False, indent=2)
                enriched_messages.append({
                    "role": "system",
                    "content": f"[Previous agent tool results]\n{tool_summary}"
                })
                logger.info(f"[COORDINATOR] Passing {len(accumulated_tool_data)} tool results to {domain.value}")

            domain_key = domain.value
            logger.info(f"[COORDINATOR_MESSAGE] Domain: {domain_key}, enriched_messages: {json.dumps(enriched_messages, ensure_ascii=False, indent=2)}")

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

                            # Persist tool-derived goods_no, shop_id, and tire_size to slots
                            if session_id and isinstance(parsed, dict):
                                self._save_tool_derived_slots(
                                    session_id, event.get("tool", ""), parsed, event.get("input", {})
                                )

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
            # Support domain rarely chains to other agents — skip LLM decision to save ~300ms
            if is_first_agent:
                is_first_agent = False
                if domain == MultiAgentDomain.Domain.SUPPORT:
                    logger.info("[COORDINATOR] Support domain — skipping LLM decision, stopping chain")
                    break

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
        # Only trigger when QnA tool was called OR non-support (FAQ) tools produced data
        _has_qna = any(item.get("tool") == "transfer_to_qna_tool" for item in accumulated_tool_data)
        _has_non_support_data = any(
            item.get("tool") not in ("get_faq_tool", "search_faq_rag_tool", "transfer_to_qna_tool")
            for item in accumulated_tool_data
        )
        if accumulated_tool_data and (_has_qna or _has_non_support_data):
            logger.info(f"[COORDINATOR] Running UI Template Agent with {len(accumulated_tool_data)} tool outputs")

            # Build context for UI Template Agent
            # Order: slot_context | messages (with user_context inside) | current_user_msg LAST | accumulated_context | accumulated_tool_data LAST
            ui_messages = []

            # 1. slot_context FIRST
            if slot_context:
                ui_messages.append({
                    "role": "system",
                    "content": slot_context,
                })

            # 2. Original messages (already contains user_context)
            ui_messages.extend(list(messages))

            # 3. Append accumulated context
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

            # 4. Append tool data summary LAST
            tool_summary = json.dumps(accumulated_tool_data, ensure_ascii=False, indent=2)
            ui_messages.append({
                "role": "assistant",
                "content": f"[Accumulated tool data for UI rendering]\n{tool_summary}"
            })
            ui_messages.append({
                "role": "user",
                "content": "Help me generate Template UI"
            })

            # Log UI Template Agent messages
            logger.info(f"[UI_TEMPLATE_MESSAGE] ui_messages: {json.dumps(ui_messages, ensure_ascii=False, indent=2)}")

            # Yield UI Template Agent start event
            yield {
                "type": "sub-agent",
                "agent": "[UI TEMPLATE AGENT]",
                "status": "start",
            }

            # Yield waiting event while UI Template Agent processes
            yield {
                "type": "waiting",
                "agent": "[UI TEMPLATE AGENT]",
            }

            # Stream from UI Template Agent (use stream_template to get data events)
            for event in ui_template_subagent.stream_template(ui_messages):
                event["source_domain"] = "ui_template"
                # FIX: Must yield as SSE formatted string
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # Yield UI Template Agent completion event
            yield {
                "type": "sub-agent",
                "agent": "[UI TEMPLATE AGENT]",
                "status": "done",
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
    r'\d{1,3}(?:,\d{3})*\s*원'      # 가격 (e.g. 150,000원)
    r'|G\d{9,}'                      # goods_no (e.g. G000000314254)
    r'|shop(?:Seq|_id|Id)'           # 매장 ID
    r'|재고|할인|%\s*할인'            # 재고/할인
    r'|\d{3}/\d{2,3}[a-zA-Z]+\d{2}'  # 타이어 사이즈 (e.g. 225/40R18, 245/40ZR19)
    r'|티스테이션\s*\S*점'             # 매장명 (e.g. 티스테이션 양평점, 티스테이션판교점)
    r'|F\d{5}\b',                     # shop_id (e.g. F01234)
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

        # Add Korean prefix to the current user message (now at last_user_idx)
        messages[last_user_idx]["content"] = (
            f"# Respond in Korean language\n{messages[last_user_idx]['content']}"
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

        try:
            chat_history_svc = get_chat_history_service()

            # 1) Load existing slots from Redis
            existing_slots = chat_history_svc.get_slots(request.session_id)
            logger.info(f"[SLOTS] Loaded existing slots: {existing_slots.model_dump()}")

            # 2) Extract regex-based slots from the LATEST user message only
            last_user_text = ""
            for msg in reversed(request.messages):
                if msg.get("role") == "user":
                    last_user_text = msg.get("content", "")
                    break
            regex_slots = ConversationSlots.extract_from_user_text(last_user_text)

            # 3) Merge: existing → regex (full merge with dependency reset)
            merged_slots = existing_slots.merge(regex_slots)
            logger.info(f"[SLOTS] Merged slots: {merged_slots.model_dump()}")

            # 4) Save merged slots to Redis
            chat_history_svc.save_slots(request.session_id, merged_slots)

            # 5) Build slot context string for agent injection
            slot_context = merged_slots.to_prompt_context() if merged_slots.has_any() else None

            # 6) Load accumulated tool context
            prev_tool_data = chat_history_svc.get_tool_context(request.session_id)
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
        domains = _coordinator.classify_multi_intent(messages)

        # STREAM MODE
        if request.stream:
            return StreamingResponse(
                TStationChatServiceV2._stream_response_multi(messages, domains, slot_context, request.session_id, tool_context),
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

            for event_str in TStationChatServiceV2._stream_response_multi(messages, domains, slot_context, request.session_id, tool_context):
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
    ):
        """Stream response from multi-agent coordinator with Strict QC Layer."""

        draft_response = ""
        source_data_chunks = []
        tool_context_items = []  # Structured tool results for context preservation
        original_message_events = [] # Hold message events to sync history
        coordinator_done_event = None # Hold the premature [DONE] event
        agent_count = 0  # Track how many agents have started

        user_query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_query = msg.get("content", "")
                break

        # 1. Iterate through the main coordinator stream
        yield f"data: {json.dumps({'type': 'agent_flow', 'agent': '[응답 생성 중]', 'status': 'processing'}, ensure_ascii=False)}\n\n"
        for event in _coordinator.stream(messages, domains=domains, slot_context=slot_context, session_id=session_id, tool_context=tool_context):
            event_type = event.get("type")
            
            # --- INTERCEPT TOKENS (Draft Response & TTFT Fix) ---
            if event_type == "token":
                if event.get("content"):
                    draft_response += event["content"]
                # FIX: Yield immediately so the UI isn't blocked!
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
                input_data = event.get("input", {})
                output_data = event.get("output", "")
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
                    assistant_msg_event = {
                        "type": "message",
                        "content": assistant_response,
                        "agent": "[UI TEMPLATE AGENT]",
                    }
                    original_message_events.append(assistant_msg_event)
                    logger.info(f"[COORDINATOR] Captured assistantResponse from UI Template: {assistant_response[:50]}...")
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
                    logger.info(f"[QC_LAYER] Resetting draft_response for agent #{agent_count} — last agent should produce unified response")
                    draft_response = ""
                    original_message_events = []

            # Pass all other events (UI templates, agent flows) through
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # 2. RUN THE STRICT QC AGENT
        # - Tool data exists AND draft has factual claims: verify against source data
        # - No tool data (no tools called): skip QC — nothing to fact-check
        # - No factual claims (greetings, FAQ): skip QC
        if draft_response.strip():
            source_data_str = "\n\n".join(source_data_chunks) if source_data_chunks else "No tool data retrieved."
            needs_qc = settings.AI_QC_ENABLED and bool(source_data_chunks) and _has_factual_claims(draft_response)

            if needs_qc:
                yield f"data: {json.dumps({'type': 'agent_flow', 'agent': '[QC AGENT]', 'status': 'processing'}, ensure_ascii=False)}\n\n"

                final_qc_text = ""
                try:
                    # FIX: Bulk invoke instead of streaming
                    qc_result = invoke_qc(QC_LLM, user_query, draft_response, source_data_str)

                    if qc_result.strip().upper() == "PASS":
                        final_qc_text = draft_response
                        logger.info("[QC_AGENT] PASS — draft is factually correct")
                    else:
                        final_qc_text = qc_result
                        logger.info("[QC_AGENT] Corrected draft response")

                except Exception as e:
                    logger.exception(f"[QC_AGENT] Failed: {e}")
                    final_qc_text = draft_response  # fallback

                # Sanitize: replace internal jargon with user-friendly fallback
                final_qc_text = _sanitize_response(final_qc_text)

                # 3. HISTORY & UI SYNC: Yield the final message event with QC'd content
                # The frontend MUST use this event to overwrite the fast-streamed draft
                if original_message_events:
                    final_msg_event = original_message_events[-1]
                    final_msg_event["content"] = final_qc_text
                    yield f"data: {json.dumps(final_msg_event, ensure_ascii=False)}\n\n"
            else:
                # No factual claims (greetings, FAQ): skip QC, pass draft directly
                draft_response = _sanitize_response(draft_response)
                yield f"data: {json.dumps({'type': 'token', 'content': draft_response}, ensure_ascii=False)}\n\n"
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