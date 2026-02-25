from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.messages import AIMessageChunk, AIMessage, ToolMessage
from config.env import settings
from langchain.tools import tool


SYSTEM_PROMPT = """
You are the Leading Agent of T-Station AI system.
Name: LeadingAgent
Company: T-Station AI

Your responsibilities:

- Understand user intent
- Manage conversation goal
- Decide which Agent Flow should handle next
- Provide helpful conversational response

Available Agent Flows:

Store_AF
Price_AF
Inventory_AF
Order_AF
QuickShopping_AF
ProductCompatibility_AF
ProductRecommendation_AF
ProductDescription_AF
FAQ_AF
Fallback_AF

Rules:

- Price, Inventory, Order → must use DB/API (do not hallucinate)
- Recommendation, Description → allowed to generate content

You are the main coordinator agent.
"""


LLM = ChatOpenAI(
    base_url="https://api.upstage.ai/v1",
    api_key=settings.UPSTAGE_API_KEY,
    model="solar-pro3",
    temperature=0.7,
    streaming=True,
)

### Sub-agent
from services.tstation.agents.product_search_agent import create_product_search_tool


SUB_AGENTS = [
    create_product_search_tool(LLM),
    ### Add more sub-agents here
]

class LeadingAgent:
    def __init__(self):
        self.agent = create_agent(
            model=LLM,
            tools=SUB_AGENTS,
            system_prompt=SYSTEM_PROMPT
        )


    def invoke(self, messages: list[dict]) -> str:
        result = self.agent.invoke({
            "messages": messages
        })
        return result["messages"][-1].content


    def stream(self, messages: list[dict]):
        """
        Supported Stream modes:
        - tokens
        - agent updates
        - tool calls
        """

        for mode, chunk in self.agent.stream(
                {"messages": messages},
                stream_mode=["messages", "updates"],
        ):

            # TOKEN STREAM
            if mode == "messages":
                token, metadata = chunk
                if isinstance(token, AIMessageChunk):
                    text = token.text
                    if text:
                        yield {
                            "type": "token",
                            "content": text,
                        }

            # AGENT UPDATES
            elif mode == "updates":
                for node, update in chunk.items():
                    message = update["messages"][-1]
                    if isinstance(message, AIMessage):
                        yield {
                            "type": "message",
                            "content": message.content,
                            "node": node,
                        }

                    elif isinstance(message, ToolMessage):
                        yield {
                            "type": "tool",
                            "content": message.content,
                            "node": node,
                        }
