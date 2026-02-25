from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.tools import tool


PRODUCT_SEARCH_PROMPT = """
You are ProductSearchSubAgent for T-Station.

Responsibilities:
- Identify tire product from user query
- Extract brand, size, vehicle if present
- Return structured result

Do NOT answer conversationally.
"""


class ProductSearchSubAgent:
    def __init__(self, model: ChatOpenAI):
        self._agent = create_agent(
            model=model,
            tools=[],
            system_prompt=PRODUCT_SEARCH_PROMPT,
            name="product_search_agent"
        )

    def invoke(self, query: str):

        result = self._agent.invoke({
            "messages": [
                {"role": "user", "content": query}
            ]
        })
        return result["messages"][-1].content


# Tool factory
def create_product_search_tool(model: ChatOpenAI):
    subagent = ProductSearchSubAgent(model)

    @tool(
        "product_search",
        description="""
Resolve tire product from user query.

Use when:
- user mentions tire
- user mentions brand
- user mentions vehicle
- user mentions tire size
"""
    )
    def product_search_tool(query: str):

        return subagent.invoke(query)

    return product_search_tool
