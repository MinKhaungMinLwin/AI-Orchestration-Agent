import json
import logging
import time

import httpx

from common import percentile
from judges import call_faithfulness_llm

logger = logging.getLogger(__name__)


def _extract_tool_result(event: dict) -> dict:
    """Keep only the minimal tool evidence needed for faithfulness evaluation."""
    return {
        "tool_name": event.get("tool_name") or event.get("name") or event.get("tool"),
        "tool_input": event.get("input") or event.get("args") or event.get("tool_input"),
        "tool_output": event.get("output") or event.get("result") or event.get("tool_output"),
    }


def _has_tool_error(tool_evidence: list[dict]) -> bool:
    """Return True if any tool call returned an error status."""
    for ev in tool_evidence:
        output = ev.get("tool_output")
        if not output:
            continue
        parsed = json.loads(output) if isinstance(output, str) else output
        if parsed.get("status") == "error":
            return True
    return False


def _extract_final_structured_response(template_events: list[dict], plain_text: str = "") -> dict | None:
    """Return the final structured response from the last data event."""
    if template_events:
        final_event = template_events[-1]
        return {
            "template": final_event.get("template"),
            "data": final_event.get("data"),
        }
    if plain_text:
        return {"template": "text", "data": {"assistantResponse": plain_text}}
    return None


def call_chat(
    api_url: str,
    jwt_token: str,
    user_message: str,
    session_id: str,
    timeout: int = 120,
) -> dict:
    """Call the chat API using streaming and collect minimal faithfulness artifacts."""
    url = f"{api_url.rstrip('/')}/tstation/messages/chat"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "content": user_message,
        "session_id": session_id,
        "stream": True,
    }

    start = time.time()
    template_data_list: list[dict] = []
    tool_events: list[dict] = []
    plain_text_chunks: list[str] = []
    with httpx.stream("POST", url, json=payload, headers=headers, timeout=timeout) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            line = line.strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            event = json.loads(data_str)
            event_type = event.get("type")
            if event_type == "data" and event.get("template"):
                template_data_list.append(event)
            elif event_type == "tool":
                tool_events.append(_extract_tool_result(event))
            elif event_type == "message" and event.get("content"):
                plain_text_chunks.append(event["content"])
    latency = time.time() - start
    plain_text = "".join(plain_text_chunks).strip()
    final_structured_response = _extract_final_structured_response(template_data_list, plain_text)
    if not tool_events:
        logger.warning("No tool events captured - case may be a plain-text/quickReply response")
    return {
        "tool_evidence": tool_events,
        "final_response_structured": final_structured_response,
        "latency_s": round(latency, 3),
    }


def score_faithfulness(
    user_message: str,
    tool_evidence: list[dict],
    final_response_structured: dict | None,
    judge_api_url: str,
    judge_api_key: str,
) -> dict:
    """Score one response for faithfulness or mark it skipped with a clear reason."""
    if not tool_evidence:
        return {
            "faithfulness": None,
            "verdict": "SKIP",
            "reason": "No tool evidence - faithfulness not applicable.",
            "faithfulness_bin": None,
            "skip": True,
            "skip_reason": "No tool evidence - faithfulness not applicable.",
        }

    if _has_tool_error(tool_evidence):
        return {
            "faithfulness": None,
            "verdict": "SKIP",
            "reason": "Tool error in evidence - faithfulness not applicable.",
            "faithfulness_bin": None,
            "skip": True,
            "skip_reason": "Tool error in evidence - faithfulness not applicable.",
        }

    if final_response_structured is None:
        return {
            "faithfulness": None,
            "verdict": "SKIP",
            "reason": "Missing final structured response - faithfulness not applicable.",
            "faithfulness_bin": None,
            "skip": True,
            "skip_reason": "Missing final structured response - faithfulness not applicable.",
        }

    scored = call_faithfulness_llm(
        judge_api_url=judge_api_url,
        judge_api_key=judge_api_key,
        user_message=user_message,
        tool_evidence=json.dumps(tool_evidence, ensure_ascii=False),
        response=json.dumps(final_response_structured, ensure_ascii=False),
    )
    faithfulness_raw = float(scored["faithfulness"])
    faithfulness_bin = 1 if faithfulness_raw > 0.5 else 0
    scored["faithfulness_bin"] = faithfulness_bin
    scored["verdict"] = "PASS" if faithfulness_bin == 1 else "FAIL"
    scored["skip"] = False
    scored["skip_reason"] = None
    return scored


def summarize_records(results: list[dict]) -> dict:
    latencies = [r["latency_s"] for r in results if isinstance(r.get("latency_s"), (int, float))]
    scored = [r for r in results if r.get("faithfulness_eval", {}).get("skip") is False]
    skip_count = sum(1 for r in results if r.get("faithfulness_eval", {}).get("skip") is True)
    faith_scores = [float(r["faithfulness_eval"]["faithfulness"]) for r in scored]
    pass_count = sum(1 for r in scored if r["faithfulness_eval"]["verdict"] == "PASS")
    avg_latency = round(sum(latencies) / len(latencies), 3) if latencies else None
    avg_faithfulness = round(sum(faith_scores) / len(faith_scores), 3) if faith_scores else None
    return {
        "total_count": len(results),
        "scored_count": len(scored),
        "skip_count": skip_count,
        "avg_latency_s": avg_latency,
        "latency_p50_s": percentile(latencies, 50),
        "latency_p90_s": percentile(latencies, 90),
        "latency_p95_s": percentile(latencies, 95),
        "avg_faithfulness": avg_faithfulness,
        "pass_rate_pct": round(100 * pass_count / len(scored), 1) if scored else 0.0,
    }
