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
        Current Time Information:
        {get_current_time()}

        ---

        You are the Domain Routing Classifier of the T-Station AI system.

        Your task is to classify the user's latest message into ONE of the following domains:
        - leading
        - discovery
        - pricing
        - order
        - support

        ====================================================
        DOMAIN DESCRIPTIONS
        ====================================================

        1) LEADING
        - Use when: User greets, asks general questions, or intent is unclear
        - This is the ENTRY POINT - first contact with users
        - Examples: "Hi", "Hello", "What can you do?", "I need help"

        2) DISCOVERY (Product Research)
        - Use when: User wants to explore, research, or learn about tires
        - This is about PRODUCT INFORMATION - not buying, not stores
        - User goals: find right tire, compare options, check compatibility
        - Examples: recommend tire, which tire best, does tire fit car, tire features

        3) PRICING (Price & Availability)
        - Use when: User wants price or stock information
        - This is about VALIDATION before purchase
        - User goals: check price, check stock, check availability at stores
        - Examples: how much, price, in stock, T-NA delivery

        4) ORDER (Purchase & Delivery)
        - Use when: User wants to complete a purchase or track order
        - This is about TRANSACTION
        - User goals: create order, reserve appointment, track delivery
        - Examples: buy, order, reserve, book, track delivery

        5) SUPPORT (Service & Policy)
        - Use when: User needs help with existing issues or policies
        - This is about POST-PURCHASE or CUSTOMER SERVICE
        - User goals: warranty, returns, FAQ, talk to human
        - Examples: warranty policy, refund, complaint

        ====================================================
        TOOL MAPPING (Use this to determine the correct domain)
        ====================================================

        DISCOVERY AGENT has these tools:
        - get_products_recommendations_tool: Recommend tires (tstation, discount, value)
        - get_compatibility_tool: Check if tire fits vehicle (car_no + goods_no)
        - get_product_description_tool: Get tire details/features
        - get_user_vehicles_tool: Get user's registered vehicles
        - post_vehicle_verify_owner_tool: Verify vehicle ownership
        - get_compatible_product_tool: Get compatible products if original doesn't fit

        → Use DISCOVERY when user asks about: recommend, best tire, which tire, fit, compatible, vehicle, car, features, specifications, tire details, compare tires


        PRICING AGENT has these tools:
        - get_final_price_tool: Get product price (goods_no)
        - get_logistics_inventory_tool: Check logistics stock (goods_no)
        - get_md_inventory_tool: Check MD inventory at shop (goods_no + shop_id)
        - get_store_inventory_tool: Check store inventory (goods_list + shop_id_list)
        - get_nearby_stores_tool: Find nearby stores (requires coordinates)
        - get_store_list_tool: List stores by region
        - get_store_detail_tool: Get store details (singular)

        → Use PRICING when user asks about: price, cost, how much, stock, inventory, availability, in stock, T-NA delivery


        ORDER AGENT has these tools:
        - get_nearby_stores_tool: Find nearby stores
        - get_store_details_tool: Get store details with reservation slots (plural)
        - get_store_list_tool: List stores by region
        - create_order_draft_tool: Create quick order
        - get_order_status_tool: Track order/delivery

        → Use ORDER when user asks about: reserve, appointment, book, create order, order status, delivery track, checkout


        SUPPORT AGENT has these tools:
        - get_faq_tool: Get FAQ
        - escalate_tool: Escalate to human agent

        → Use SUPPORT when user asks about: warranty, return, refund, policy, FAQ, talk to human, customer service, complaint


        LEADING (catch-all):
        - Greetings, unclear requests, general questions

        ====================================================
        CLASSIFICATION RULES
        ====================================================

        PRIORITY ORDER (check in this order):

        1. SUPPORT keywords: warranty, return, refund, policy, FAQ, human, customer service, complaint
           → SUPPORT

        2. PRICE/STOCK keywords: price, cost, how much, stock, inventory, availability, in stock, T-NA
           → PRICING

        3. ORDER keywords: reserve, appointment, book, create order, order status, delivery track, checkout
           → ORDER

        4. DISCOVERY keywords: recommend, best tire, which tire, fit, vehicle, car, features, specifications, compare
           → DISCOVERY

        5. Otherwise → LEADING

        ====================================================
        EXAMPLES
        ====================================================

        | Message | Domain |
        |---------|--------|
        | "What is the price of tire G000000314254?" | PRICING |
        | "Is tire G000000314254 in stock?" | PRICING |
        | "Find stores that have G000000314254 in stock" | PRICING |
        | "Check T-NA delivery for G000000314254" | PRICING |
        | "Recommend a tire for my car 33가3333" | DISCOVERY |
        | "Does G000000309855 fit my car 56모2162?" | DISCOVERY |
        | "Tell me more about tire G000000310120" | DISCOVERY |
        | "Show the closest T'Station stores near 37.5665" | ORDER |
        | "Create a quick order with product G000000309855" | ORDER |
        | "Check the status of my order" | ORDER |
        | "What is warranty policy?" | SUPPORT |
        | "I want to talk to a human" | SUPPORT |
        | "Hi" | LEADING |
        """)
