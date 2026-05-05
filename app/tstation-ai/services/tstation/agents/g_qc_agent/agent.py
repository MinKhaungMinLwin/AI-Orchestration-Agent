from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import logging

logger = logging.getLogger(__name__)

QC_SYSTEM_PROMPT = """QC agent for T-Station AI. Compare the Draft Response against the SOURCE DATA.

Output PASS if factually correct. Output the corrected response only if errors found — no preamble, no explanation, no commentary (NEVER start with "수정합니다", "아래와 같이", "수정된 응답:" etc.). User sees your output directly.

CHECK ONLY:
- prices, discount %, product names, goods_no, shop_id, store names, tire sizes, stock status — must match Source Data exactly
- Vehicle list completeness: if Source Data contains multiple vehicles, draft MUST show ALL of them — never omit any
- tire_size in draft must match the tire_size in Tool Input exactly (e.g. Tool Input says "235/55R19" but draft says "225/40R18" → fix to match Tool Input)
- No 최신/신상/구형/이전 세대 claims unless Source Data contains launch_dt or goods_reg_dt; image URL upload paths are NOT launch dates — never infer launch year from them
- If Source Data is empty: draft must not claim specific prices, stock, or store info
- If Source Data is empty AND draft has no useful content: replace with natural Korean guiding user to ask something else

"Useful content" — do NOT replace: greetings, empathy, "no results" messages offering alternatives, any response with a next step. Only replace truly empty or jargon-only drafts.

CORRECTIONS:
- Fix only wrong facts. Keep Markdown, tables, URLs, tone, and Korean language identical.
- Remove backend jargon (tool names, AFs, JSON, DB, API, 시스템, 에러, 실패 etc.) — rephrase as natural conversational Korean.
"""

def get_qc_chain(llm):
    prompt = ChatPromptTemplate.from_messages([
        ("system", QC_SYSTEM_PROMPT),
        ("user", "User Query:\n{user_query}\n\nRAW SOURCE DATA (Ground Truth):\n{source_data}\n\nDraft Response:\n{draft_response}")
    ])
    return prompt | llm | StrOutputParser()

def invoke_qc(llm, user_query: str, draft_response: str, source_data: str, config: dict | None = None) -> str:
    logger.info("[QC_AGENT] Invoking QC check...")
    chain = get_qc_chain(llm)
    return chain.invoke({
        "user_query": user_query,
        "draft_response": draft_response,
        "source_data": source_data
        },
        config=config
    )

async def ainvoke_qc(llm, user_query: str, draft_response: str, source_data: str, config: dict | None = None) -> str:
    logger.info("[QC_AGENT] Invoking QC check (async)...")
    chain = get_qc_chain(llm)
    return await chain.ainvoke({
        "user_query": user_query,
        "draft_response": draft_response,
        "source_data": source_data
        },
        config=config
    )

def stream_qc(llm, user_query: str, draft_response: str, source_data: str):
    logger.info("[QC_AGENT] Streaming QC check...")
    chain = get_qc_chain(llm)
    return chain.stream({
        "user_query": user_query,
        "draft_response": draft_response,
        "source_data": source_data
    })