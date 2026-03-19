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
    model="gpt-5.4",
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

        You are a domain classifier for T-Station AI. Classify user message into ONE domain:
        - leading: Entry point - greetings, unclear intent
        - discovery: Product research - recommendations, compatibility, features, vehicle
        - pricing: Price & stock - cost, availability, inventory
        - order: Transactions - purchase, reservation, order tracking
        - support: Service - FAQ, warranty, returns, policies, human agent

        CLASSIFY BY USER INTENT (not keywords):

        SUPPORT if user wants:
        - General tire guidance (replacement timing, maintenance, air pressure, driving conditions)
        - Policy/terms (warranty, return, refund)
        - Human assistance

        ORDER if user wants:
        - Make a purchase or reservation
        - Track existing order/delivery
        - Book installation appointment

        PRICING if user wants:
        - Know the price/cost
        - Check stock/availability
        - Compare costs

        DISCOVERY if user wants:
        - Product recommendations (for vehicle or general)
        - Check if product fits their vehicle
        - Learn about product features/specs

        LEADING if:
        - Just greeting
        - No clear intent
        - General "what can you do" questions

        Think about what the user WANTS TO ACHIEVE, not just what words they use.
        """)
