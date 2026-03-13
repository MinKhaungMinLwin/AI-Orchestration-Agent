from enum import Enum
from textwrap import dedent

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.messages import AIMessageChunk, AIMessage, ToolMessage
from config.env import settings

from enum import Enum
from pydantic import BaseModel, Field


from langchain_litellm import ChatLiteLLM

LLM = ChatLiteLLM(
    openai_api_key=settings.OPENAI_API_KEY,
    # model="gpt-5.2",
    model="bedrock/arn:aws:bedrock:ap-northeast-2:763865062538:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0",
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

    reason: str = Field(default="", description="Reason for the classification")
    confidence: float = Field(default=0.0, description="Confidence of the classification")
    domain: Domain = Field(default=Domain.LEADING, description="Domain of the conversation")

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
    def prompt():
        return dedent("""
        You are the Domain Routing Classifier of the T-Station AI system.
        
        Your task is to classify the user's latest message into ONE of the following domains:
        - leading
        - discovery
        - order
        - pricing
        - support
        
        ====================================================
        DOMAIN DEFINITIONS
        ====================================================
        
        1) leading
        Use when:
        - The user greets the system.
        - The intent is unclear or incomplete.
        - The user asks general system questions.
        - The conversation needs high-level direction.
        
        Examples:
        - "Hi"
        - "I need help"
        - "What can you do?"
        - Unclear request
        
        ----------------------------------------------------
        
        2) discovery
        Use when the user is exploring, researching, or validating products.
        This is about PRODUCT INFORMATION - not about buying or stores.

        This includes:
        - Tire recommendations based on vehicle or driving needs
        - Asking which tire is best for their car
        - Asking about tire features, specifications, or descriptions
        - Comparing products
        - Checking if a tire fits their vehicle (vehicle number like 33가3333, 12가3456)
        - Compatibility check between vehicle and tire

        Examples:
        - "Recommend a tire for my car 33가3333"
        - "Recommend a tire for my Hyundai Sonata"
        - "Which tire is best for quiet driving?"
        - "Tell me more about HKKR001"
        - "Does HKKR001 fit my car 12가3456?"
        - "Does G000000309855 fit my car 56모2162?"
        - "What are the features of tire G000000310121?"

        IMPORTANT:
        - Keywords like "car", "vehicle", "recommend", "fit", "best" → DISCOVERY
        - This is NOT about price, stock, stores, or orders

        ----------------------------------------------------

        3) pricing
        Use when the user asks about pricing, stock, or inventory.

        This includes:
        - Asking for price
        - Asking for stock
        - Checking inventory
        - Checking store inventory availability
        - T-NA delivery availability

        Examples:
        - "What is the price of tire G000000314254?"
        - "How much is G000000314254?"
        - "Is tire G000000314254 in stock?"
        - "Check stock for product G000000314254"
        - "Find stores that have G000000314254 in stock"
        - "What stores can install G000000314254 today?"
        - "Check T-NA delivery availability"

        ----------------------------------------------------

        4) order
        Use when the user wants to create orders, track orders, or find stores.

        This includes:
        - Finding nearby stores
        - Store details and reservation
        - Quick order creation
        - Order status tracking
        - Delivery tracking

        Examples:
        - "Show the closest T'Station stores near 37.5665, 126.9780"
        - "Find stores near 37.4979, 127.0276"
        - "List T'Station stores in Seoul"
        - "Show details of store B03788"
        - "Create a quick order with product G000000309855"
        - "Check the status of my order"
        - "Show my order and delivery status"

        ----------------------------------------------------
        
        5) support
        Use when the user asks about policies, service issues, post-purchase support,
        OR when they want to speak with a human agent / customer service.
        This is also the FALLBACK route for ESCALATION from any domain.

        Includes:
        - Warranty
        - Refund policy
        - Installation policy
        - Complaint
        - Account problems
        - Human agent request / Escalation request
        - User says "I want to talk to a person"
        - User says "connect me to customer service"
        - User says "I need help from a human"
        - User is frustrated or having difficulties
        - When any other domain agent cannot resolve the issue

        Examples:
        - "What is the warranty policy?"
        - "How long does installation take?"
        - "I need help with my previous purchase"
        - "I want to talk to a customer service representative"
        - "Connect me to a human agent"
        - "This is not helpful, let me speak to someone"
        - "I need to escalate this issue"
        
        ====================================================
        STRICT CLASSIFICATION RULES (MUST FOLLOW EXACTLY)
        ====================================================

        Step 1: Check for PRICE/STOCK first - if ANY of these keywords appear → PRICING
        - price, cost, how much, amount, fee
        - stock, inventory, availability, in stock
        - Example: "What is the price of X?" → PRICING

        Step 2: If not Step 1, check for ORDER keywords
        - store, nearby, location, address
        - order, buy, purchase, delivery, track, shipping
        → ORDER

        Step 3: If not Step 1 or 2, check for DISCOVERY keywords
        - vehicle number (33가3333, 12가3456, etc.)
        - recommend, suggestion, best, which tire, what tire
        - fit, compatible, vehicle, car for, car number
        - product features, specifications
        → DISCOVERY

        Step 4: If not Step 1-3, check for SUPPORT
        - warranty, return, refund, policy, FAQ
        - human agent, talk to person, customer service
        → SUPPORT

        Step 5: Otherwise → LEADING

        IMPORTANT: When "price" or "stock" appears, ALWAYS choose PRICING
        regardless of other keywords (even "tire", "product", "recommend")
        """)
