from enum import Enum

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.messages import AIMessageChunk, AIMessage, ToolMessage
from config.env import settings

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


class AgentDomain(str, Enum):
    LEADING = "leading"
    DISCOVERY = "discovery"
    TRANSACTION = "transaction"
    SHOPPING = "shopping"
    SUPPORT = "support"
