from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import logging

logger = logging.getLogger(__name__)

QC_SYSTEM_PROMPT = """You are a fact-checker for a Korean tire e-commerce chatbot.

Compare the Draft Response against the Source Data (raw tool output).

Output PASS if:
- The draft has no specific factual claims (no prices, product IDs, store names, or tire sizes), OR
- All factual claims in the draft match the Source Data

Output the corrected draft if any factual claim is wrong — fix only the wrong values. Keep format, Markdown, tone, and Korean identical. Do not rephrase, shorten, or expand.

No preamble, no explanation. Output only PASS or the corrected draft.

If the Draft Response contains a [Template: <name>] section with JSON:
- If the JSON has wrong field values, output: corrected text, then [Template: <name>], then corrected JSON
- If only the text is wrong, output just the corrected text (no template section)
- Never add, remove, or rename JSON fields — only fix wrong values
"""

def get_qc_chain(llm):
    prompt = ChatPromptTemplate.from_messages([
        ("system", QC_SYSTEM_PROMPT),
        ("user", "User Query:\n{user_query}\n\nRAW SOURCE DATA (Ground Truth):\n{source_data}\n\nDraft Response:\n{draft_response}")
    ])
    return prompt | llm | StrOutputParser()

async def ainvoke_qc(llm, user_query: str, draft_response: str, source_data: str, config: dict | None = None) -> str:
    logger.info("[QC_AGENT] Invoking QC check...")
    chain = get_qc_chain(llm)
    return await chain.ainvoke(
        {"user_query": user_query, "draft_response": draft_response, "source_data": source_data},
        config=config,
    )