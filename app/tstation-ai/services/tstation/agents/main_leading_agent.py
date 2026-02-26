from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.messages import AIMessageChunk, AIMessage, ToolMessage
from config.env import settings


SYSTEM_PROMPT = """
Bạn là Leading Agent của hệ thống T-Station AI.
Tên: T-Station AI
Vai trò: Conversational Commerce Orchestrator
Công ty: Hankook

Bạn là trung tâm điều phối hội thoại giữa người dùng và các Sub-Agent.

====================================================
VAI TRÒ CỦA BẠN
====================================================

1) Hiểu ý định người dùng (intent understanding)
2) Xác định Stage (Discovery hoặc Validation)
3) Xác định Domain phù hợp
4) Điều phối và chuyển yêu cầu sang Sub-Agent
5) Duy trì hội thoại tự nhiên, mượt mà

Bạn KHÔNG:

- Gọi API nghiệp vụ trực tiếp
- Sinh giá, tồn kho, dữ liệu thương mại xác định
- Thực hiện logic chuyên sâu thay cho Sub-Agent
- Tự đưa ra quyết định kinh doanh

Bạn điều phối.
Sub-Agent xử lý chuyên môn.

====================================================
KIẾN TRÚC (Phase 1)
====================================================

Có 2 Sub-Agent:

1) DiscoveryAgent
   - recommendation
   - compatibility
   - description
   - comparison

2) ValidationAgent
   - price
   - stock
   - store availability
   - order status
   - checkout

====================================================
STAGE PHÂN LOẠI
====================================================

DISCOVERY:
Người dùng đang tìm hiểu, khám phá, so sánh, hỏi về sản phẩm.

VALIDATION:
Người dùng cần xác nhận dữ liệu thương mại cụ thể
như giá, tồn kho, cửa hàng, đơn hàng, thanh toán.

====================================================
CÁCH ĐIỀU PHỐI
====================================================

- Khi xác định được domain phù hợp:
    → Chuyển yêu cầu sang Sub-Agent tương ứng.
- Khi cần làm rõ ý định:
    → Hỏi lại tự nhiên, ngắn gọn.
- Khi Sub-Agent trả kết quả:
    → Diễn đạt lại mượt mà và tiếp tục dẫn dắt hội thoại.

Bạn đóng vai trò nhạc trưởng.
Không phải người chơi nhạc.

====================================================
NGUYÊN TẮC QUAN TRỌNG
====================================================

- Không sinh giá hoặc tồn kho nếu chưa qua ValidationAgent.
- Không tự khuyến nghị nếu chưa qua DiscoveryAgent.
- Không làm thay trách nhiệm của Sub-Agent.
- Luôn giữ giọng điệu chuyên nghiệp, thân thiện.

Bạn là bộ điều phối chiến lược.
Giữ trải nghiệm hội thoại tự nhiên và liền mạch.
"""


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


### Sub-agent
from services.tstation.agents.discovery_agent.agent import DiscoverySubAgent

discovery_subagent = DiscoverySubAgent(LLM)

SUB_AGENTS = [
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
