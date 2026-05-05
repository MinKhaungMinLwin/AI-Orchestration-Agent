import json
import os

import httpx

_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")

FAITHFULNESS_SYSTEM_PROMPT = """You are an expert evaluator for T-Station AI, a Korean automotive chatbot (Hankook Tire).
Evaluate whether the bot's response is faithful to the live TOOL EVIDENCE.

You are given the user question, TOOL EVIDENCE from live tool events, and the final structured output.
Treat TOOL EVIDENCE as the source of truth. Lower faithfulness for any claim not supported by it.
For multi-turn conversations, TOOL EVIDENCE aggregates calls from all turns — evaluate the final output against the full evidence set.

Templates and key fields:
- quickReply: data.assistantResponse, data.quickReplies[]
- product: data.assistantResponse, data.products[{title,price,rate,tires}], data.metadata[{goodsId}]
- location: data.assistantResponse, data.stores[{nameAddress,detailAddress,distance,todayInstall}], data.metadata[{shopId}]
- datepick: data.assistantResponse, data.dates[{date,available}]
- voucher: data.assistantResponse, data.vouchers[{nameVoucher,discount,dateVoucher}]
- preOrder: data.assistantResponse, data.orderInfo{product,quantity,storeName,bookingDateTime,paymentAmount}, data.recommendActions
- orderComplete: data.assistantResponse, data.isSuccess, data.orderInfo
- listCar: data.assistantResponse, data.listCar[{licensePlate,info}]
- cheapestProduct: data.assistantResponse, data.cheapestProduct[{title,finalPrice,totalDiscount}]
- previewYoutube: data.assistantResponse, data.items[{title,youtubeUrl}]
- qnaComplete: data.assistantResponse, data.title, data.summary

Return ONLY valid JSON:
{"faithfulness": <float 0.0-1.0>, "reason": "<1 sentence>"}"""

ANSWER_RELEVANCE_SYSTEM_PROMPT = """You are an expert evaluator for T-Station AI, a Korean automotive chatbot (Hankook Tire).
Evaluate whether the bot's response actually answers the user's question.

Do NOT evaluate factual accuracy — only whether the response addresses what the user asked.
- 1.0 = directly and completely answers the question
- 0.5 = partially answers or addresses a related but not exact intent
- 0.0 = completely off-topic or ignores the question

Return ONLY valid JSON:
{"answer_relevance": <float 0.0-1.0>, "reason": "<1 sentence>"}"""

TEMPLATE_CORRECTNESS_SYSTEM_PROMPT = """You are an expert evaluator for T-Station AI, a Korean automotive chatbot (Hankook Tire).
Evaluate whether the bot used the correct UI template for the user's intent.

Templates and when to use them:
- quickReply: general FAQ, greetings, complaints, or when no specific data is needed
- product: tire/product search results with prices and ratings
- location: nearby stores with address and install availability
- datepick: available appointment dates for installation
- voucher: discount coupons or promotions
- preOrder: order confirmation before finalizing (product, store, datetime, price)
- orderComplete: completed booking confirmation
- listCar: user's registered vehicles
- cheapestProduct: cheapest product option
- previewYoutube: YouTube video recommendations
- qnaComplete: directing user to 1:1 inquiry / customer service page

- 1.0 = perfect template choice for the intent
- 0.5 = acceptable but not ideal
- 0.0 = completely wrong template for the intent

Return ONLY valid JSON:
{"template_correctness": <float 0.0-1.0>, "reason": "<1 sentence>"}"""

TOOL_APPROPRIATENESS_SYSTEM_PROMPT = """You are an expert evaluator for T-Station AI, a Korean automotive chatbot (Hankook Tire).
Evaluate whether the bot called the right tools for the user's request.

Consider:
1. Were the correct tools called for the user's intent?
2. Were unnecessary or wrong tools called?
3. Were required tools skipped (e.g., product search missing for a product query)?
If no tools were needed (e.g., greeting/complaint), score 1.0.
For multi-turn conversations, tool calls span all turns — evaluate overall tool usage for the complete conversation goal.

- 1.0 = exactly the right tools with sensible parameters
- 0.5 = mostly correct but missing a tool or one unnecessary call
- 0.0 = wrong tools called or required tools completely missed

Return ONLY valid JSON:
{"tool_appropriateness": <float 0.0-1.0>, "reason": "<1 sentence>"}"""


def _extract_text(resp_json: dict) -> str:
    choice = (resp_json.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            item if isinstance(item, str) else item.get("text", "")
            for item in content
            if isinstance(item, (str, dict))
        ]
        if joined := "".join(p for p in parts if p).strip():
            return joined

    for key in ("reasoning_content", "reasoning"):
        extra = message.get(key)
        if isinstance(extra, str) and extra.strip():
            return extra.strip()
        if isinstance(extra, list):
            parts = [i if isinstance(i, str) else i.get("text", "") for i in extra if isinstance(i, (str, dict))]
            if joined := "".join(p for p in parts if p).strip():
                return joined

    return choice.get("text", "").strip() if isinstance(choice.get("text"), str) else ""


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    text = text.removesuffix("```").strip()
    s, e = text.find("{"), text.rfind("}")
    return json.loads(text[s: e + 1])


def _call_judge(*, judge_api_url: str, judge_api_key: str, system_prompt: str, user_content: str) -> dict:
    judge_model = os.environ.get("JUDGE_MODEL", "gpt-5.5-reasoning-xhigh")
    payload: dict = {
        "model": judge_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": 16384,
    }
    if not any(judge_model.startswith(p) for p in _REASONING_PREFIXES):
        payload["temperature"] = 0.0

    resp = httpx.post(
        f"{judge_api_url.rstrip('/')}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {judge_api_key}", "Content-Type": "application/json"},
        timeout=180,
    )
    resp.raise_for_status()
    content = _extract_text(resp.json())
    if not content:
        raise ValueError("Judge returned empty response")
    return _parse_json(content)


def call_faithfulness_llm(*, judge_api_url: str, judge_api_key: str, user_message: str, messages: list[str] | None = None, tool_evidence: str, response: str) -> dict:
    if messages and len(messages) > 1:
        conv = "\n".join(f"[Turn {i + 1}] {m}" for i, m in enumerate(messages))
        question_context = f"Full conversation ({len(messages)} turns):\n{conv}"
    else:
        question_context = f"User question: {user_message}"
    return _call_judge(
        judge_api_url=judge_api_url, judge_api_key=judge_api_key,
        system_prompt=FAITHFULNESS_SYSTEM_PROMPT,
        user_content=f"{question_context}\n\nTOOL EVIDENCE (source of truth):\n{tool_evidence}\n\nFinal structured output:\n{response}\n\nScore for faithfulness only.",
    )


def call_answer_relevance_llm(*, judge_api_url: str, judge_api_key: str, user_message: str, messages: list[str] | None = None, response: str) -> dict:
    if messages and len(messages) > 1:
        conv = "\n".join(f"[Turn {i + 1}] {m}" for i, m in enumerate(messages))
        user_content = f"Full conversation ({len(messages)} turns):\n{conv}\n\nFinal structured output (last turn):\n{response}\n\nScore whether the final output resolves the complete conversation goal."
    else:
        user_content = f"User question: {user_message}\n\nFinal structured output:\n{response}\n\nScore for answer relevance only."
    return _call_judge(
        judge_api_url=judge_api_url, judge_api_key=judge_api_key,
        system_prompt=ANSWER_RELEVANCE_SYSTEM_PROMPT,
        user_content=user_content,
    )


def call_template_correctness_llm(*, judge_api_url: str, judge_api_key: str, user_message: str, messages: list[str] | None = None, response: str) -> dict:
    if messages and len(messages) > 1:
        conv = "\n".join(f"[Turn {i + 1}] {m}" for i, m in enumerate(messages))
        user_content = f"Full conversation ({len(messages)} turns):\n{conv}\n\nFinal structured output (last turn):\n{response}\n\nScore whether the template type is appropriate for the final step of this conversation."
    else:
        user_content = f"User question: {user_message}\n\nFinal structured output:\n{response}\n\nScore whether the template type is appropriate for the user's intent."
    return _call_judge(
        judge_api_url=judge_api_url, judge_api_key=judge_api_key,
        system_prompt=TEMPLATE_CORRECTNESS_SYSTEM_PROMPT,
        user_content=user_content,
    )


def call_tool_appropriateness_llm(*, judge_api_url: str, judge_api_key: str, user_message: str, messages: list[str] | None = None, tool_evidence: str) -> dict:
    if messages and len(messages) > 1:
        conv = "\n".join(f"[Turn {i + 1}] {m}" for i, m in enumerate(messages))
        question_context = f"Full conversation ({len(messages)} turns):\n{conv}"
    else:
        question_context = f"User question: {user_message}"
    return _call_judge(
        judge_api_url=judge_api_url, judge_api_key=judge_api_key,
        system_prompt=TOOL_APPROPRIATENESS_SYSTEM_PROMPT,
        user_content=f"{question_context}\n\nTool calls made:\n{tool_evidence}\n\nScore whether the tool calls are appropriate for the user's request.",
    )
