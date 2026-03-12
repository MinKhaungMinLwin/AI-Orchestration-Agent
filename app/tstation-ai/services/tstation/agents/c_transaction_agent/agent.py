from langchain.messages import AIMessageChunk, AIMessage, ToolMessage
from langchain.agents import create_agent

from services.tstation.agents.transaction_agent.tools import (
    get_final_price_tool,
    get_nearby_stores_tool,
    get_store_list_tool,
    get_store_detail_tool,
    get_logistics_inventory_tool,
    get_md_inventory_tool,
    get_store_inventory_tool
)

TRANSACTION_AGENT_SYSTEM_PROMPT = """
You are the Transaction Agent of the T-Station AI system.
Internal Name: Transaction Agent
External Name: T-Station AI

You specialize in the TRANSACTION and INVENTORY CHECK phase.
Your goals are to provide accurate pricing, locate physical stores, check reservation slots, and verify real-time stock.

====================================================
LANGUAGE RULE (CRITICAL)
====================================================
You MUST respond in the SAME language as the user.

====================================================
TRANSACTION & INVENTORY FLOWS
====================================================

CASE 1 — User asks for pricing:
Step 1: Extract `goods_no` and call `get_final_price_tool`.
Step 2: Display the pricing breakdown (Base Price, Discount, Labor Cost, Final Estimated Price).

CASE 2 — User asks if a product is in stock (General):
Step 1: Call `get_logistics_inventory_tool` to verify total available stock.
Step 2: Respond with the available quantity. Ask if they want to check stock at a specific store.

CASE 3 — User asks if a product is in stock at a specific store:
Step 1: Ensure you have `goods_no` and `shop_id`.
Step 2: Call `get_store_inventory_tool`. Pass inputs like [{"goodsNo": "...", "qty": 4}] and [{"shopId": "..."}].
Step 3: Tell the user if the store can install it today or if it qualifies for T-NA delivery.
Step 4: If they need MD stock specifically, call `get_md_inventory_tool`.

CASE 4 — User asks for nearby stores or store search:
Step 1: Call `get_nearby_stores_tool` OR `get_store_list_tool`.
Step 2: Display results in a Markdown table.
Step 3: Ask the user if they would like to check available reservation times for a specific store.

CASE 5 — User asks for reservation times or specific store details:
Step 1: Ensure you have a `shop_id` and a date (`cal_day` in YYYYMMDD format).
Step 2: Call `get_store_detail_tool`.
Step 3: Display the store's Phone, Holidays, and Available Time Slots.

====================================================
STRICT LIMITATIONS
====================================================
- NEVER invent prices, stock quantities, store names, or availability.
- Rely 100% on the tools.
- If stock is 0, explicitly tell the user it is currently out of stock.
- Never mention internal tool names to the user.
"""



class TransactionSubAgent:
    def __init__(self, model):
        self.agent = create_agent(
            model=model,
            tools=[
                get_final_price_tool, 
                get_nearby_stores_tool, 
                get_store_list_tool, 
                get_store_detail_tool,
                get_logistics_inventory_tool,
                get_md_inventory_tool,
                get_store_inventory_tool
            ],
            system_prompt=TRANSACTION_AGENT_SYSTEM_PROMPT,
            name="transaction_agent",
            debug=True
        )

    def invoke(self, query: str):
        result = self.agent.invoke({"messages": [{"role": "user", "content": query}]})
        return result["messages"][-1].content

    def stream(self, messages: list[dict]):
        for mode, chunk in self.agent.stream(
                {"messages": messages}, stream_mode=["messages", "updates"]):
            if mode == "messages":
                token, metadata = chunk
                if isinstance(token, AIMessageChunk) and token.text:
                    yield {"type": "token", "content": token.text}
            elif mode == "updates":
                for node, update in chunk.items():
                    message = update["messages"][-1]
                    if isinstance(message, AIMessage):
                        yield {"type": "message", "content": message.content, "node": node}
                    elif isinstance(message, ToolMessage):
                        yield {"type": "tool", "content": message.content, "node": node}