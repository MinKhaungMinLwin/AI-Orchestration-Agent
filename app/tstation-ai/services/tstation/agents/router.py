from enum import Enum
from textwrap import dedent

from config.env import settings
from common.curr_time import get_current_time

from pydantic import BaseModel, Field


from langchain_litellm import ChatLiteLLM

# Default LLM (AI_MODEL) — used by Discovery and Support agents.
LLM = ChatLiteLLM(
    api_base=settings.AI_GATEWAY_BASE_URL,
    api_key=settings.AI_GATEWAY_API_KEY,
    model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL}",
    streaming=True,
)

# Per-agent overrides
LEADING_LLM = ChatLiteLLM(
    api_base=settings.AI_GATEWAY_BASE_URL,
    api_key=settings.AI_GATEWAY_API_KEY,
    model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL_LEADING_AGENT}",
    streaming=True,
)

TRANSACTION_LLM = ChatLiteLLM(
    api_base=settings.AI_GATEWAY_BASE_URL,
    api_key=settings.AI_GATEWAY_API_KEY,
    model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL_TRANSACTION_AGENT}",
    streaming=True,
)

# Lightweight LLM for routing/decision tasks (AI_MODEL_QC_AGENT, e.g. gpt-4o-mini).
# Use for short structured outputs where reasoning depth is not needed.
DECISION_LLM = ChatLiteLLM(
    api_base=settings.AI_GATEWAY_BASE_URL,
    api_key=settings.AI_GATEWAY_API_KEY,
    model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL_QC_AGENT}",
)

### Multi-Agent Router
# Leading Agent
from services.tstation.agents.a_leading_agent.agent import LeadingAgent

leading_agent = LeadingAgent(LEADING_LLM)
# Discovery Agent
from services.tstation.agents.b_discovery_agent.agent import DiscoverySubAgent

discovery_subagent = DiscoverySubAgent(LLM)
# Transaction Agent (merged PRICING + ORDER)
from services.tstation.agents.c_transaction_agent.agent import TransactionSubAgent

transaction_subagent = TransactionSubAgent(TRANSACTION_LLM)

# Support Agent
from services.tstation.agents.e_support_agent.agent import SupportSubAgent

support_subagent = SupportSubAgent(LLM)

# Template rendering is handled by the code-based template_mapper (Path A) or
# directly by domain agents emitting structured `data` events (Path B). The
# legacy UI Template Agent has been removed in refactor/af-labels-and-template-cleanup.
# QC Agent stays out of the runtime path.


## Router
class AgentDomain(BaseModel):
    class Domain(str, Enum):
        LEADING = "leading"
        DISCOVERY = "discovery"
        TRANSACTION = "transaction"
        SUPPORT = "support"

    reason: str = Field(description="Reason for the classification")
    confidence: float = Field(description="Confidence of the classification")
    domain: Domain = Field(description="Domain of the conversation")

    _registry: dict[Domain, object] = {}

    def get_agent(self):
        if self.domain == self.Domain.DISCOVERY:
            return discovery_subagent

        elif self.domain == self.Domain.TRANSACTION:
            return transaction_subagent

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
        - TRANSACTION: Price, stock (logistics/store), inventory, store search by location/name, store availability, purchase, store visit reservation (specific date/time slot booking at a store), order tracking, create order draft, coupon inquiry
        - SUPPORT: FAQ, warranty, returns, policies, general maintenance information, **per-vehicle maintenance D-day / 정비 시기·주기 / 교체 시기 / 점검 알림 만기 / all my T 점검 만기** (data-backed schedule inquiry for the user's registered car), human agent
        - DISCOVERY: Product search by name, recommendations, vehicle-tire compatibility check, features, **registered vehicle list (listCar) inquiry**
        - LEADING: Greeting, unclear intent

        DECISION RULES:

        TRANSACTION if user wants:
        - "How much", "price", "cost", "discount" for product with KNOWN goods_no (e.g., "{{goods_no}} 가격" - format: G + 12 digits)
        - "In stock?", "available?" for specific product at specific store
        - Check logistics stock (warehouse availability)
        - Find stores by LOCATION (e.g., "stores near Gangnam", "stores in Seoul")
        - Find stores by NAME (e.g., "find Hankook store")
        - Find "All My T" stores (e.g., "all my T", "All My T", "올마이티", "allMyT")
        - Check store inventory (which stores have this tire)
        - "Buy", "purchase", "order", "checkout" WITH goods_no already known
        - Track existing order (provide order number)
        - "장바구니에 담아줘", "장바구니 저장" (cart save)
        - Book store visit/reservation with specific date/time
        - Select quantity for order (e.g., "4개 주문", "2개")
        - Select store for order
        - Coupon inquiry ("쿠폰 조회", "내 쿠폰", "쿠폰함")
        Examples:
        - "{{goods_no}} 가격 얼마야?" (e.g., "G012345678901" - goods_no KNOWN → TRANSACTION)
        - "Is {{goods_no}} in stock?" (e.g., "G012345678901")
        - "Show me stores near Gangnam"
        - "Show me nearby All My T stores"
        - "All My T 매장 찾아줘"
        - "올마이티 매장 검색"
        - "{{goods_no}} 4개 주문할게" (e.g., "G012345678901" - goods_no KNOWN → TRANSACTION)
        - "Book installation at 2pm"
        - "Track my order 12345"
        - "장바구니에 담아줘"
        - "쿠폰 조회해줘"
        - "내 쿠폰 보여줘"

        DISCOVERY if user wants:
        - Search products by NAME/KEYWORD (e.g., "search for Ventus", "show me Hankook tires")
        - Recommend tires (vehicle-specific or general)
        - Check if specific tire FITS specific vehicle ("does 205/55R16 fit my BMW?")
        - Product specifications, features, technology
        - Search car model by name to get trims/tire size (e.g., "K7 타이어", "소나타 연식별 사이즈")
        - **Price for product by NAME (goods_no NOT known)** → DISCOVERY first to find goods_no
        Examples: "Find tires called Ventus", "What tires fit my car {{vehicle_number}}?", "Will these tires fit my vehicle?", "Dynapro HPX 가격 얼마야?", "벤투스 S2 가격"

        ⚠️ CRITICAL DISTINCTION for price queries:
        - "{{goods_no}} 가격" (e.g., "G012345678901") → goods_no KNOWN → TRANSACTION only
        - "Dynapro HPX 가격" → goods_no NOT known, product NAME only → DISCOVERY (to find goods_no first)
        - "벤투스 S2 가격 얼마야?" → goods_no NOT known → DISCOVERY

        SUPPORT if user wants:
        - Tire replacement guidance (when to replace, air pressure, maintenance)
        - Policy questions (warranty terms, return conditions, refund process)
        - General guidance without purchase intent
        - **Per-vehicle maintenance schedule / D-day inquiry** — "내 차 정비 일정", "엔진오일 언제 갈아야", "배터리 교체 시기", "타이어 교체 시기", "all my T 점검 만기 언제", "내 차 5대무상 점검 만기", "와이퍼 언제 갈아", "정비 D-day", "점검 만기일" (registered-car-based D-day matrix for the 7 items: 얼라인먼트/all my T 무상점검/엔진오일/실내필터/와이퍼/타이어/배터리). ⚠️ NOT to be confused with "store visit reservation booking" (=TRANSACTION).
        - Request for human agent / 1:1 inquiry
        - Write/save 1:1 inquiry with AI-summarized content
        - "1:1 문의 작성", "상담원 연결", "이 문제를 1:1로 저장하고 싶어요"
        - **Customer complaints, frustration, anger** (e.g., "뭐 이런 서비스가", "제대로 해", "상담 이딴식으로", "엉망이야", aggressive/angry tone)
        Examples: "When should I replace tires?", "What's the warranty policy?", "Can I return this?", "1:1 문의 작성해주세요", "상담원 연결해주세요", "너 상담 왜 이렇게 못해?", "짜증나", "다른 상담원 연결해줘", "내 차 정비 일정 알려줘", "엔진오일 언제 갈아야 해?", "all my T 점검 언제까지야?"

        LEADING if:
        - Just greeting ("hello", "hi", "안녕하세요")
        - No clear goal or action requested
        - General capability questions ("what can you do")
        Examples: "Hi", "What can you help me with?", "Hello"

        KEY PRINCIPLES:
        - "stores near [location]" → TRANSACTION
        - "store near me" + "All My T" → TRANSACTION
        - "find All My T stores" → TRANSACTION
        - "price of [specific product]" → TRANSACTION
        - "search tires named [X]" → DISCOVERY
        - "does [tire] fit [car]?" → DISCOVERY (compatibility check)
        - "buy tires" → TRANSACTION
        - "recommend tires" → DISCOVERY
        - "warranty, return, maintenance FAQ" → SUPPORT
        - "내 차 정비 일정 / 정비 D-day / 교체 시기 / 점검 만기" → SUPPORT (data-backed, registered vehicle 7-item D-day matrix)
        - "방문 예약 시간 알려줘 / 매장 예약 조회" → TRANSACTION (store visit slot booking)
        - "find stores" → TRANSACTION

        Korean vehicle numbers follow patterns: {{vehicle_number}} (e.g., "12가3456", "123가1234")
        """)
