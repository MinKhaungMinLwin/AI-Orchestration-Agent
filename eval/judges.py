import json
import os

import httpx


# ---------------------------------------------------------------------------
# Template correctness — rule-based, no LLM needed
# ---------------------------------------------------------------------------

# Templates that indicate the bot asked for clarification instead of completing the task
CLARIFICATION_TEMPLATES: frozenset[str] = frozenset({"quickReply", "listCar"})

# Maps test-case agent_flow value → acceptable template types (first = preferred)
AGENT_FLOW_TEMPLATE_MAP: dict[str, list[str]] = {
    "Product Compatibility AF":   ["product"],
    "Product Description AF":     ["quickReply", "product"],
    "Product Recommendation AF":  ["product", "cheapestProduct"],
    "Inventory AF":               ["location"],
    "Store AF":                   ["location"],
    "Price AF":                   ["voucher", "cheapestProduct", "product"],
    "FAQ AF":                     ["quickReply", "qnaComplete"],
    "Fallback/Escalation AF":     ["quickReply", "qnaComplete"],
    "Order / Delivery AF":        ["quickReply", "qnaComplete"],
}


def check_template_correctness(tc_agent_flow: str, template_events: list[dict]) -> dict:
    """Rule-based check: did the bot emit the expected FE template type?

    Verdicts:
      PASS      — at least one expected template was emitted
      FALLBACK  — only clarification templates (quickReply/listCar) emitted when a richer one was expected
      FAIL      — a wrong structured template was emitted
      NO_OUTPUT — no template events captured at all
      UNKNOWN   — agent_flow not in AGENT_FLOW_TEMPLATE_MAP
    """
    actual = [e["template"] for e in template_events if e.get("template")]
    expected = AGENT_FLOW_TEMPLATE_MAP.get(tc_agent_flow)

    if expected is None:
        return {
            "verdict": "UNKNOWN",
            "expected": [],
            "actual": actual,
            "reason": f"No template mapping for agent_flow '{tc_agent_flow}'",
        }

    if not actual:
        return {
            "verdict": "NO_OUTPUT",
            "expected": expected,
            "actual": [],
            "reason": "No template events captured",
        }

    matched = [t for t in actual if t in expected]
    if matched:
        return {
            "verdict": "PASS",
            "expected": expected,
            "actual": actual,
            "reason": f"Expected template '{matched[0]}' emitted",
        }

    if all(t in CLARIFICATION_TEMPLATES for t in actual):
        return {
            "verdict": "FALLBACK",
            "expected": expected,
            "actual": actual,
            "reason": f"Bot returned '{actual[0]}' (clarification) instead of completing with {expected}",
        }

    return {
        "verdict": "FAIL",
        "expected": expected,
        "actual": actual,
        "reason": f"Unexpected template '{actual[0]}'; expected one of {expected}",
    }


# ---------------------------------------------------------------------------
# Tool grounding — rule-based, deterministic, no LLM needed
# ---------------------------------------------------------------------------

# Templates that carry no factual DB claims — grounding check not applicable
GROUNDING_EXEMPT: frozenset[str] = frozenset({"quickReply", "qnaComplete", "previewYoutube"})

# Maps template type → tool name substrings (ANY match = grounded)
# Order matters: more specific patterns first
TEMPLATE_TOOL_PATTERNS: dict[str, list[str]] = {
    "listCar":         ["get_my_cars_tool"],
    "product":         ["search_product", "get_goods", "get_product"],
    "cheapestProduct": ["search_product", "get_goods", "get_cheapest", "get_final_price"],
    "location":        ["search_store", "get_store", "get_nearby", "get_shop"],
    "voucher":         ["get_final_price", "get_voucher", "get_coupon"],
    "preOrder":        ["pre_order", "create_order", "reserve"],
    "orderComplete":   ["complete_order", "create_order", "finalize"],
    "datepick":        ["get_date", "get_booking", "get_slot", "get_schedule"],
}


def check_tool_grounding(template_events: list[dict], tool_evidence: list[dict]) -> dict:
    """Verify that every structured template is backed by an actual tool call.

    For each template emitted:
      PASS — a matching tool was found in tool_evidence
      FAIL — structured data template emitted with no matching tool call (hallucination)
      SKIP — template carries no factual DB claims (quickReply, qnaComplete, etc.)

    Overall verdict:
      PASS — all checkable templates are grounded
      FAIL — at least one structured template is ungrounded
      SKIP — no checkable templates (only exempt templates or no output)
    """
    called_tools = {e["tool_name"] for e in tool_evidence if e.get("tool_name")}

    details: list[dict] = []
    has_checkable = False
    overall_fail = False

    for evt in template_events:
        template = evt.get("template", "")

        if not template or template in GROUNDING_EXEMPT:
            details.append({"template": template, "verdict": "SKIP", "reason": "No factual data claims"})
            continue

        patterns = TEMPLATE_TOOL_PATTERNS.get(template)
        if patterns is None:
            details.append({"template": template, "verdict": "SKIP", "reason": f"No grounding rule defined for '{template}'"})
            continue

        has_checkable = True
        grounded_by = next((t for t in called_tools if any(p in t for p in patterns)), None)

        if grounded_by:
            details.append({"template": template, "verdict": "PASS", "grounded_by": grounded_by})
        else:
            details.append({
                "template": template,
                "verdict": "FAIL",
                "reason": f"'{template}' emitted without required tool (expected one matching: {patterns})",
            })
            overall_fail = True

    if not has_checkable:
        overall_verdict = "SKIP"
        overall_reason = "Only exempt templates emitted — no factual data to ground"
    elif overall_fail:
        overall_verdict = "FAIL"
        overall_reason = "Structured template emitted without a supporting tool call"
    else:
        overall_verdict = "PASS"
        overall_reason = "All structured templates are backed by tool evidence"

    return {
        "verdict": overall_verdict,
        "reason": overall_reason,
        "details": details,
        "called_tools": sorted(called_tools),
    }


# ---------------------------------------------------------------------------
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


def _extract_text(resp_json: dict) -> str:
    choice = (resp_json.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "".join(parts).strip()

    for key in ("reasoning_content", "reasoning"):
        extra = message.get(key)
        if isinstance(extra, str) and extra.strip():
            return extra.strip()
        if isinstance(extra, list):
            parts = [i if isinstance(i, str) else i.get("text", "") for i in extra if isinstance(i, (str, dict))]
            if any(parts):
                return "".join(parts).strip()

    return choice.get("text", "").strip() if isinstance(choice.get("text"), str) else ""


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    text = text.removesuffix("```").strip()
    s, e = text.find("{"), text.rfind("}")
    return json.loads(text[s : e + 1])


def call_faithfulness_llm(
    judge_api_url: str,
    judge_api_key: str,
    user_message: str,
    tool_evidence: str,
    response: str,
) -> dict:
    url = f"{judge_api_url.rstrip('/')}/chat/completions"
    judge_model = os.environ.get("JUDGE_MODEL", "gpt-5.5-reasoning-xhigh")
    payload = {
        "model": judge_model,
        "messages": [
            {"role": "system", "content": FAITHFULNESS_SYSTEM_PROMPT},
            {"role": "user", "content": FAITHFULNESS_USER_TEMPLATE.format(
                user_message=user_message, tool_evidence=tool_evidence, response=response,
            )},
        ],
        "max_tokens": 16384,
    }
    # reasoning models (o1/o3/o4/gpt-5.x) don't support temperature
    _is_reasoning = any(judge_model.startswith(p) for p in ("o1", "o3", "o4", "gpt-5"))
    if not _is_reasoning:
        payload["temperature"] = 0.0
    resp = httpx.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {judge_api_key}", "Content-Type": "application/json"},
        timeout=90,
    )
    resp.raise_for_status()
    resp_json = resp.json()
    content = _extract_text(resp_json)
    if not content:
        raise ValueError(f"Judge returned empty response. Raw={json.dumps(resp_json, ensure_ascii=False)[:2000]}")
    return _parse_json(content)
