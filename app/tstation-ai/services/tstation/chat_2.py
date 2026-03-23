import json
import logging
from typing import Iterator

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
    pricing_subagent,
    order_subagent,
    support_subagent,
)
from common.jwt_utils import get_user_info_from_token
from common.curr_time import get_current_time

logger = logging.getLogger(__name__)


class MultiAgentDomain(BaseModel):
    """Router result that supports multiple domains (multi-intent)."""

    class Domain(str, Enum):
        LEADING = "leading"
        DISCOVERY = "discovery"
        PRICING = "pricing"
        ORDER = "order"
        SUPPORT = "support"

    reason: str = Field(description="Reason for the classification")
    domains: list[Domain] = Field(
        description="List of domains detected in the request, ordered by priority"
    )

    def get_agents(self):
        """Return list of agents based on detected domains."""
        agent_map = {
            self.Domain.DISCOVERY: discovery_subagent,
            self.Domain.PRICING: pricing_subagent,
            self.Domain.ORDER: order_subagent,
            self.Domain.SUPPORT: support_subagent,
            self.Domain.LEADING: leading_agent,
        }
        return [agent_map[d] for d in self.domains if d in agent_map]


def prompt_router_multi() -> str:
    """Classification prompt that detects multi-intent."""
    return f"""
Current Time: {get_current_time()}

You are a domain classifier for T-Station AI (Hankook Tire).
Classify user message into ONE OR MORE domains based on detected intents.

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

MULTI-INTENT DETECTION:
If user request contains multiple intents, detect ALL relevant domains.
Examples:
- "Explain Ventus S1 evo3 and tell me the price" → DISCOVERY + PRICING
- "Find tires for my BMW and check if in stock at nearby store" → DISCOVERY + PRICING + ORDER
- "Recommend tires and their warranty" → DISCOVERY + SUPPORT
- "How much is this tire? Also, what's the warranty?" → PRICING + SUPPORT

KEY PRINCIPLES:
- "stores near [location]" → ORDER
- "price of [specific product]" → PRICING
- "search tires named [X]" → DISCOVERY
- "does [tire] fit [car]?" → DISCOVERY (compatibility check)
- "buy tires" → ORDER
- "recommend tires" → DISCOVERY
- "warranty, return, maintenance" → SUPPORT
- When multiple intents present, return ALL relevant domains

Korean vehicle numbers follow patterns: 12가3456, 123가1234
"""


class StreamingMultiAgentCoordinator:
    """Orchestrates multiple agents with streaming support."""

    def __init__(self):
        self.agent_map = {
            MultiAgentDomain.Domain.DISCOVERY: discovery_subagent,
            MultiAgentDomain.Domain.PRICING: pricing_subagent,
            MultiAgentDomain.Domain.ORDER: order_subagent,
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
            model="gpt-5.4",
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
            for event in agent.stream(enriched_messages):
                # Tag with source domain for UI
                event["source_domain"] = domain_key
                yield event

                # Capture message content for context passing
                if event.get("type") == "message":
                    content = event.get("content", "")
                    if content:
                        accumulated_context[domain_key] = content
                        logger.info(f"[COORDINATOR] Captured message for {domain_key}: {content}...")

            # Yield agent completion event
            yield {
                "type": "sub-agent",
                "agent": f"[{domain_key.upper()} AGENT]",
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
        """Build messages with user info injected from JWT token."""
        messages = list(request.messages)

        user_info = None
        if request.access_token:
            user_info = get_user_info_from_token(request.access_token)

        if user_info:
            user_info_str = "\n".join([f"# {k}: {v}" for k, v in user_info.items()])
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    original_content = messages[i].get("content", "")
                    messages[i]["content"] = (
                        f"# Response user in Korean language\n"
                        f"# User information:\n"
                        f"{user_info_str}\n"
                        f"# User question:\n"
                        f"{original_content}"
                    )
                    break
            logger.info(f"[CHAT_V2] User info prepended to last user message")

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
