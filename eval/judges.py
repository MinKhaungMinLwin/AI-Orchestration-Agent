import json
import os
import time

import httpx


FAITHFULNESS_SYSTEM_PROMPT = """You are an expert evaluator for T-Station AI, a Korean automotive chatbot (Hankook Tire).
Your job is to evaluate whether a single response is faithful to the live TOOL EVIDENCE.

You are given:
- the user question
- TOOL EVIDENCE captured from live tool events
- final structured output

Treat TOOL EVIDENCE as the source of truth for factual claims whenever available.
If the response says something not supported by tool evidence, lower faithfulness.
Do not use any fallback source. Judge only from TOOL EVIDENCE and the final structured output.

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

Scoring criteria (float 0.0 to 1.0):
- faithfulness: Does the output avoid hallucination against the TOOL EVIDENCE? Are product names, prices, store names, dates, coupons, and order facts supported by the evidence?
  1.0 = completely faithful to evidence | 0.0 = major hallucinations or wrong facts

Return ONLY valid JSON (no markdown, no explanation outside JSON):
{"faithfulness": <float 0.0-1.0>, "verdict": "PASS" or "FAIL", "reason": "<1 sentence in English explaining why the response is faithful or not faithful to the evidence>"}

PASS if faithfulness > 0.5. Otherwise FAIL."""

FAITHFULNESS_USER_TEMPLATE = """User question: {user_message}

TOOL EVIDENCE (source of truth when available):
{tool_evidence}

Final structured output:
{response}

Score the response for faithfulness only."""


def _extract_response_text(resp_json: dict) -> str:
    """Extract response text across common OpenAI-compatible response shapes."""
    choice = (resp_json.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("text"), str):
                text_parts.append(item["text"])
                continue
            if item.get("type") == "output_text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
        return "".join(text_parts).strip()

    for key in ("reasoning_content", "reasoning"):
        extra = message.get(key)
        if isinstance(extra, str) and extra.strip():
            return extra.strip()
        if isinstance(extra, list):
            text_parts = []
            for item in extra:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
            if text_parts:
                return "".join(text_parts).strip()

    if isinstance(choice.get("text"), str):
        return choice["text"].strip()

    return ""


def _normalize_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) > 1:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def _parse_json_text(text: str) -> dict:
    text = _normalize_json_text(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def call_faithfulness_llm(
    judge_api_url: str,
    judge_api_key: str,
    user_message: str,
    tool_evidence: str,
    response: str,
) -> dict:
    """Call judge LLM for faithfulness-only scoring."""
    url = f"{judge_api_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {judge_api_key}",
        "Content-Type": "application/json",
    }
    judge_model = os.environ.get("JUDGE_MODEL", "gpt-5.4-reasoning")
    payload = {
        "model": judge_model,
        "messages": [
            {"role": "system", "content": FAITHFULNESS_SYSTEM_PROMPT},
            {"role": "user", "content": FAITHFULNESS_USER_TEMPLATE.format(
                user_message=user_message,
                tool_evidence=tool_evidence,
                response=response,
            )},
        ],
        "temperature": 0.0,
        "max_tokens": 512,
    }

    last_error = ""
    last_response = ""

    for _ in range(3):
        resp = httpx.post(url, json=payload, headers=headers, timeout=90)
        resp.raise_for_status()
        resp_json = resp.json()
        content = _extract_response_text(resp_json)

        if content:
            try:
                return _parse_json_text(content)
            except json.JSONDecodeError as exc:
                last_error = f"JSON decode failed: {exc}"
                last_response = content[:2000]
        else:
            last_error = "Empty response content"
            last_response = json.dumps(resp_json, ensure_ascii=False)[:2000]

        time.sleep(2)

    raise ValueError(f"Judge returned unusable response after retries. {last_error}. Raw={last_response}")
