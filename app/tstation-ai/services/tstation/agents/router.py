from enum import Enum
from textwrap import dedent

from config.env import settings
from common.curr_time import get_current_time

from pydantic import BaseModel, Field


from langchain_litellm import ChatLiteLLM

LLM = ChatLiteLLM(
    # openai_api_key=settings.OPENAI_API_KEY,
    # model="gpt-5.4",
    # model="bedrock/arn:aws:bedrock:ap-northeast-2:763865062538:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0",
    api_base=settings.AI_GATEWAY_BASE_URL,
    api_key=settings.AI_GATEWAY_API_KEY,
    model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL}",
    streaming=True,
)

### Multi-Agent Router
# Leading Agent
from services.tstation.agents.a_leading_agent.agent import LeadingAgent
leading_agent = LeadingAgent(LLM)
# Discovery Agent
from services.tstation.agents.b_discovery_agent.agent import DiscoverySubAgent
# Discovery Agent
discovery_subagent = DiscoverySubAgent(LLM)
# Pricing Agent
from services.tstation.agents.c_pricing_agent.agent import PricingSubAgent
pricing_subagent = PricingSubAgent(LLM)

# Order Agent
from services.tstation.agents.d_order_agent.agent import OrderSubAgent

order_subagent = OrderSubAgent(LLM)

# Support Agent
from services.tstation.agents.e_support_agent.agent import SupportSubAgent
support_subagent = SupportSubAgent(LLM)

## Router
class AgentDomain(BaseModel):
    class Domain(str, Enum):
        LEADING = "leading"
        DISCOVERY = "discovery"
        PRICING = "pricing"
        ORDER = "order"
        SUPPORT = "support"

    reason: str = Field(description="Reason for the classification")
    confidence: float = Field(description="Confidence of the classification")
    domain: Domain = Field(description="Domain of the conversation")

    _registry: dict[Domain, object] = {}

    def get_agent(self):
        if self.domain == self.Domain.DISCOVERY:
            return discovery_subagent

        elif self.domain == self.Domain.PRICING:
            return pricing_subagent

        elif self.domain == self.Domain.ORDER:
            return order_subagent

        elif self.domain == self.Domain.SUPPORT:
            return support_subagent

        else:
            return leading_agent

    @staticmethod
    def prompt_router():
        return dedent(f"""
        Current Time: {get_current_time()}

        You are a domain classifier for T-Station AI (Hankook Tire).
        Classify user message into ONE domain.

        DOMAINS:
        - ORDER: Purchase, reservation, store visit/booking, order tracking, store search by location/name
        - PRICING: Price, stock (logistics/store), inventory, store availability for specific product
        - SUPPORT: FAQ, warranty, returns, policies, maintenance, human agent
        - DISCOVERY: Product search by name, recommendations, vehicle-tire compatibility check, features
        - LEADING: Greeting, unclear intent

        DECISION RULES:

        ORDER if user wants:
        - "Buy", "purchase", "order", "checkout"
        - Track existing order (provide order number)
        - Book store visit/reservation with specific date/time
        - Find stores by LOCATION (e.g., "stores near Gangnam", "stores in Seoul")
        - Find stores by NAME (e.g., "find Hankook store")
        Examples: "I want to buy tires", "Book installation at 2pm", "Track my order 12345", "Show me stores near Gangnam"

        PRICING if user wants:
        - "How much", "price", "cost", "discount" for SPECIFIC product (goods_no known)
        - "In stock?", "available?" for specific product at specific store
        - Check logistics stock (warehouse availability)
        Examples: "How much is Ventus S1 evo3?", "Is G000000314254 in stock?"

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

        KEY PRINCIPLES:
        - "stores near [location]" → ORDER
        - "price of [specific product]" → PRICING
        - "search tires named [X]" → DISCOVERY
        - "does [tire] fit [car]?" → DISCOVERY (compatibility check)
        - "buy tires" → ORDER
        - "recommend tires" → DISCOVERY
        - "warranty, return, maintenance" → SUPPORT

        Korean vehicle numbers follow patterns: 12가3456, 123가1234
        """)
