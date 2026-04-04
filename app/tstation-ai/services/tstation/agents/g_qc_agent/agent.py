from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import logging

logger = logging.getLogger(__name__)

QC_SYSTEM_PROMPT = """You are the strictly deterministic Quality Control (QC) and Fact-Checking Agent for T-Station AI.
Your job is to receive a 'Draft Response' written by another AI agent and verify it against the 'RAW SOURCE DATA' (which contains JSON outputs from backend APIs).

CORE FACT-CHECKING RULES:
1. STRICT VALIDATION: Every price, product name, product ID (goods_no), store ID (shop_id/shopSeq), store name, and specification mentioned in the Draft Response MUST perfectly match the Source Data.
2. NO HALLUCINATION: If the Draft Response contains a specific factual claim (like a price, discount %, or stock status) that is NOT present in the Source Data, you must remove it or correct it.
3. PRESERVE FORMATTING & URLS: You MUST preserve the exact Markdown formatting of the Draft Response. Do not break tables, bullet points, or bold text. 
   - CRITICAL: If there is a URL (e.g., a checkout link), ensure the query parameters (like goods_no, shopSeq, ord_qty) match the Source Data, but DO NOT break the URL structure.
4. PRESERVE TONE & LANGUAGE: Keep the friendly, professional commerce tone of the Draft. Respond in the exact same language as the Draft Response (usually Korean).
5. CLEANUP: Remove any internal backend jargon (e.g., 'Tool names', 'AFs', 'JSON', 'database') that might have accidentally leaked into the draft.

INSTRUCTIONS:
- If the Draft Response is already factually correct and safe, simply output it exactly as is (or with minor language cleanup).
- If it is factually incorrect, rewrite the incorrect parts using ONLY the facts from the Source Data, while keeping the rest of the message intact.
- If the Source Data is empty or says "No tool data retrieved", the draft MUST NOT claim to know specific prices, stock, or store details.

Output ONLY the final, safe message to be shown to the user. Do not add introductory conversational filler like "Here is the corrected response:".
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