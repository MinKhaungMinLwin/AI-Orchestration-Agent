from enum import Enum
from textwrap import dedent

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.messages import AIMessageChunk, AIMessage, ToolMessage
from config.env import settings

from enum import Enum
from pydantic import BaseModel, Field


# LLM = ChatOpenAI(
#     base_url="https://api.upstage.ai/v1",
#     api_key=settings.UPSTAGE_API_KEY,
#     model="solar-pro3",
#     temperature=0.7,
#     streaming=True,
# )

from langchain_litellm import ChatLiteLLM

LLM = ChatLiteLLM(
    model="bedrock/arn:aws:bedrock:ap-northeast-2:763865062538:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0",
    # model = "bedrock/ap-northeast-1/arn:aws:bedrock:ap-northeast-1:763865062538:inference-profile/minimax.minimax-m2-1",
    temperature=0.7,
    streaming=True,
)

### Multi-Agent Router
# Leading Agent
from services.tstation.agents.a_leading_agent.agent import LeadingAgent
leading_agent = LeadingAgent(LLM)
# Discovery Agent
from services.tstation.agents.b_discovery_agent.agent import DiscoverySubAgent
discovery_subagent = DiscoverySubAgent(LLM)

# FAQ Agent
from services.tstation.agents.faq_agent.agent import FAQSubAgent
faq_subagent = FAQSubAgent(LLM)

## Router
class AgentDomain(BaseModel):
    class Domain(str, Enum):
        LEADING = "leading"
        DISCOVERY = "discovery"
        TRANSACTION = "transaction"
        SHOPPING = "shopping"
        SUPPORT = "support"

    reason: str = Field(default="", description="Reason for the classification")
    confidence: float = Field(default=0.0, description="Confidence of the classification")
    domain: Domain = Field(default=Domain.LEADING, description="Domain of the conversation")

    _registry: dict[Domain, object] = {}

    def get_agent(self):
        if self.domain == self.Domain.DISCOVERY:
            return discovery_subagent

        # elif self.domain == self.Domain.TRANSACTION:
        #     return transaction_agent
        #
        # elif self.domain == self.Domain.SHOPPING:
        #     return shopping_agent
        #
        elif self.domain == self.Domain.SUPPORT:
            return faq_subagent

        else:
            return leading_agent

    @staticmethod
    def prompt():
        return dedent("""
        You are the Domain Routing Classifier of the T-Station AI system.
        
        Your task is to classify the user's latest message into ONE of the following domains:
        - leading
        - discovery
        - shopping
        - transaction
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
        
        This includes:
        - Tire recommendations
        - Asking which tire is best
        - Asking about tire features or specifications
        - Comparing products
        - Asking if a product fits their car
        - Compatibility check between vehicle and tire
        - Recommendation + compatibility in same sentence
        
        Examples:
        - "Recommend a tire for my Hyundai Sonata"
        - "Which tire is best for quiet driving?"
        - "Tell me more about HKKR001"
        - "Does HKKR001 fit my car 12가3456?"
        - "Recommend a tire and check if it fits my vehicle"
        
        IMPORTANT:
        Compatibility validation (product ↔ vehicle fitment) belongs to DISCOVERY,
        NOT transaction.
        
        ----------------------------------------------------
        
        3) shopping
        Use when the user is preparing to buy but has not confirmed the purchase.
        
        Includes:
        - Asking for price
        - Asking for stock
        - Checking promotion or coupon
        - Checking store availability
        - Asking about installation schedule
        - Confirming availability before buying
        
        Examples:
        - "How much is HKIN001?"
        - "Is this tire in stock?"
        - "Do you have it in Gangnam store?"
        - "Can I install it tomorrow?"
        
        ----------------------------------------------------
        
        4) transaction
        Use when the user expresses clear purchase intent or manages an order.
        
        Includes:
        - "I want to buy HKIN001"
        - "Proceed with this tire"
        - "Place the order"
        - "Order if compatible"
        - Confirming purchase
        - Checking order status
        - Cancelling order
        - Delivery tracking
        
        IMPORTANT:
        If the user clearly wants to proceed with buying → transaction,
        even if compatibility is mentioned.
        
        Examples:
        - "I want to buy HKIN001"
        - "Order this if it fits"
        - "Where is my order?"
        - "Cancel my order"
        
        ----------------------------------------------------
        
        5) support
        Use when the user asks about policies, service issues, or post-purchase support.
        
        Includes:
        - Warranty
        - Refund policy
        - Installation policy
        - Complaint
        - Account problems
        - Human agent request
        
        Examples:
        - "What is the warranty policy?"
        - "How long does installation take?"
        - "I need help with my previous purchase"
        
        ====================================================
        PRIORITY RULES
        ====================================================
        
        If message includes strong purchase intent → transaction
        Else if price/stock/store inquiry → shopping
        Else if recommendation or compatibility → discovery
        Else if policy or complaint → support
        Else → leading
        
        If multiple intents exist:
        Classify based on the PRIMARY action the user wants to perform.
        """)
