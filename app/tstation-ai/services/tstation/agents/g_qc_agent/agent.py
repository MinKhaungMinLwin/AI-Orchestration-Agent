from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import logging

logger = logging.getLogger(__name__)

QC_SYSTEM_PROMPT = """You are a fast QC (Quality Control) agent for T-Station AI.
Compare the Draft Response against the SOURCE DATA and decide:

If the draft is factually correct → respond with exactly: PASS
If the draft has errors → respond with ONLY the corrected full response.

CHECK THESE ONLY:
- prices, discount %, product names, goods_no, shop_id, store names, tire sizes, stock status
- vehicle list completeness: if Source Data contains multiple vehicles, draft MUST show ALL of them. Never omit any vehicle.
- tire_size consistency: the tire_size mentioned in the draft MUST match the tire_size in the Tool Input. If Tool Input shows tire_size="235/55R19" but draft says "225/40R18", that is an error — fix it to match the Input.
- These MUST match the Source Data exactly.
- If Source Data is empty/"No tool data retrieved", draft must NOT claim specific prices/stock/stores.
- If Source Data is empty AND draft has no useful content, replace draft with a helpful Korean message guiding the user to ask a different question. Example: "죄송합니다. 해당 요청을 처리할 수 없습니다. 타이어 추천, 가격 조회, 매장 검색 등 다른 질문을 해주세요."

RULES FOR CORRECTIONS:
- Fix ONLY incorrect facts. Keep everything else identical.
- Preserve Markdown formatting, tables, URLs, tone, and language (Korean).
- Remove leaked backend jargon (tool names, AFs, JSON, database).
- NEVER output "No tool data retrieved" as a user-facing response.

RESPOND WITH EITHER:
1. PASS (if correct)
2. The corrected response only (if errors found)
"""

def get_qc_chain(llm):
    prompt = ChatPromptTemplate.from_messages([
        ("system", QC_SYSTEM_PROMPT),
        ("user", "User Query:\n{user_query}\n\nRAW SOURCE DATA (Ground Truth):\n{source_data}\n\nDraft Response:\n{draft_response}")
    ])
    return prompt | llm | StrOutputParser()

def invoke_qc(llm, user_query: str, draft_response: str, source_data: str) -> str:
    logger.info("[QC_AGENT] Invoking QC check...")
    chain = get_qc_chain(llm)
    return chain.invoke({
        "user_query": user_query, 
        "draft_response": draft_response, 
        "source_data": source_data
    })

def stream_qc(llm, user_query: str, draft_response: str, source_data: str):
    logger.info("[QC_AGENT] Streaming QC check...")
    chain = get_qc_chain(llm)
    return chain.stream({
        "user_query": user_query, 
        "draft_response": draft_response, 
        "source_data": source_data
    })