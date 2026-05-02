import json
import logging
import os
import time

import httpx

from common import percentile
from judges import call_faithfulness_llm

logger = logging.getLogger(__name__)


def get_jwt_token() -> str:
    return os.environ.get("EVAL_JWT_TOKEN", "")


def _compute_timing(
    total_s: float,
    tool_events: list[dict],
    tool_start_times: dict[str, list[float]],
    thinking_end_s: float | None,
    first_token_s: float | None,
) -> dict:
    """Compute per-segment timing from raw SSE event timestamps.

    Segments:
      thinking_s    — stream start → first tool_start OR "답변 중..."
                      (LLM initial decision latency)
      tool_calls    — per-tool: start (tool_start event) → end (tool result event)
      tool_total_s  — wall time across all tool calls (first start → last end)
      post_tool_s   — last tool result → first token
                      (LLM re-reasoning after seeing tool output)
      ttft_s        — stream start → first token (Time To First Token)
      generation_s  — first token → stream end (response streaming time)
      total_s       — full end-to-end latency
    """
    # Per-tool breakdown: match tool_start events to tool results in order
    pending = {k: list(v) for k, v in tool_start_times.items()}
    tool_calls: list[dict] = []
    for te in tool_events:
        name = te["tool_name"]
        starts = pending.get(name, [])
        start_s = starts.pop(0) if starts else None
        end_s = te["received_at_s"]
        tool_calls.append({
            "tool": name,
            "start_s": start_s,
            "end_s": end_s,
            "duration_s": round(end_s - start_s, 3) if start_s is not None else None,
        })

    # Tool wall time: from earliest tool_start to latest tool result
    valid_starts = [tc["start_s"] for tc in tool_calls if tc["start_s"] is not None]
    all_ends = [tc["end_s"] for tc in tool_calls]
    tool_total_s: float | None = None
    if valid_starts and all_ends:
        tool_total_s = round(max(all_ends) - min(valid_starts), 3)

    # Post-tool LLM: last tool result → first token
    last_tool_end = max(all_ends) if all_ends else None
    post_tool_s: float | None = None
    if last_tool_end is not None and first_token_s is not None:
        post_tool_s = round(first_token_s - last_tool_end, 3)

    # TTFT and generation
    generation_s: float | None = round(total_s - first_token_s, 3) if first_token_s is not None else None

    # Thinking: stream start (≈0) → first tool_start OR first token
    thinking_s: float | None
    if thinking_end_s is not None:
        thinking_s = round(thinking_end_s, 3)
    elif first_token_s is not None:
        thinking_s = round(first_token_s, 3)
    else:
        thinking_s = None

    return {
        "total_s": total_s,
        "ttft_s": first_token_s,
        "thinking_s": thinking_s,
        "tool_calls": tool_calls,
        "tool_total_s": tool_total_s,
        "post_tool_s": post_tool_s,
        "generation_s": generation_s,
    }


def call_chat(api_url: str, jwt_token: str, user_message: str, session_id: str, timeout: int = 120) -> dict:
    url = f"{api_url.rstrip('/')}/tstation/messages/chat"
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}
    payload = {"content": user_message, "session_id": session_id, "stream": True}

    start = time.time()
    template_events: list[dict] = []
    tool_events: list[dict] = []
    agent_flow_events: list[dict] = []

    # Timing accumulators
    first_token_s: float | None = None
    thinking_end_s: float | None = None   # time of first tool_start OR "답변 중..."
    tool_start_times: dict[str, list[float]] = {}  # tool_name → [start_s, ...]

    with httpx.stream("POST", url, json=payload, headers=headers, timeout=timeout, verify=False) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            line = line.strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            event = json.loads(data_str)
            t = round(time.time() - start, 3)

            etype = event.get("type")

            if etype == "data" and event.get("template"):
                template_events.append(event)

            elif etype == "tool":
                tool_name = event.get("tool") or event.get("tool_name") or event.get("name")
                tool_events.append({
                    "tool_name": tool_name,
                    "tool_input": event.get("input") or event.get("args") or event.get("tool_input"),
                    "tool_output": event.get("output") or event.get("result") or event.get("tool_output"),
                    "received_at_s": t,
                })

            elif etype == "agent_flow":
                agent_flow_events.append({
                    "agent": event.get("agent"),
                    "agent_class": event.get("agent_class"),
                    "status": event.get("status"),
                    "received_at_s": t,
                })

            elif etype == "status":
                status_val = event.get("status", "")
                if status_val == "tool_start":
                    tool_name = event.get("tool", "")
                    tool_start_times.setdefault(tool_name, []).append(t)
                    if thinking_end_s is None:
                        thinking_end_s = t
                elif status_val == "답변 중...":
                    if thinking_end_s is None:
                        thinking_end_s = t

            elif etype == "token":
                if first_token_s is None:
                    first_token_s = t

    total_s = round(time.time() - start, 3)
    timing = _compute_timing(total_s, tool_events, tool_start_times, thinking_end_s, first_token_s)

    return {
        "tool_evidence": tool_events,
        "template_events": template_events,
        "agent_flow_events": agent_flow_events,
        "latency_s": total_s,
        "timing": timing,
    }


def score_faithfulness(
    user_message: str,
    tool_evidence: list[dict],
    template_events: list[dict],
    judge_api_url: str,
    judge_api_key: str,
) -> dict:
    tool_evidence_for_judge = [
        {k: v for k, v in e.items() if k != "received_at_s"} for e in tool_evidence
    ]
    scored = call_faithfulness_llm(
        judge_api_url=judge_api_url,
        judge_api_key=judge_api_key,
        user_message=user_message,
        tool_evidence=json.dumps(tool_evidence_for_judge, ensure_ascii=False),
        response=json.dumps(template_events, ensure_ascii=False),
    )
    faith_bin = 1 if float(scored["faithfulness"]) > 0.5 else 0
    return {**scored, "faithfulness_bin": faith_bin, "verdict": "PASS" if faith_bin else "FAIL"}


def summarize_records(results: list[dict]) -> dict:
    latencies = [r["latency_s"] for r in results if isinstance(r.get("latency_s"), (int, float))]
    scored = [r for r in results if r.get("faithfulness_eval")]
    faith_scores = [float(r["faithfulness_eval"]["faithfulness"]) for r in scored]
    pass_count = sum(1 for r in scored if r["faithfulness_eval"]["verdict"] == "PASS")

    template_scored = [r for r in results if r.get("template_eval")]
    template_verdicts = [r["template_eval"]["verdict"] for r in template_scored]
    t_pass = template_verdicts.count("PASS")
    t_fallback = template_verdicts.count("FALLBACK")
    t_fail = template_verdicts.count("FAIL")
    t_total = len(template_scored)

    grounding_scored = [r for r in results if r.get("grounding_eval")]
    grounding_verdicts = [r["grounding_eval"]["verdict"] for r in grounding_scored]
    g_pass = grounding_verdicts.count("PASS")
    g_fail = grounding_verdicts.count("FAIL")
    g_skip = grounding_verdicts.count("SKIP")
    g_checkable = g_pass + g_fail

    # Timing averages — only include records that have timing data
    def _avg(vals: list[float]) -> float | None:
        return round(sum(vals) / len(vals), 3) if vals else None

    timings = [r["timing"] for r in results if r.get("timing")]

    ttfts = [t["ttft_s"] for t in timings if t.get("ttft_s") is not None]
    thinkings = [t["thinking_s"] for t in timings if t.get("thinking_s") is not None]
    tool_totals = [t["tool_total_s"] for t in timings if t.get("tool_total_s") is not None]
    post_tools = [t["post_tool_s"] for t in timings if t.get("post_tool_s") is not None]
    generations = [t["generation_s"] for t in timings if t.get("generation_s") is not None]

    return {
        "total_count": len(results),
        "scored_count": len(scored),
        "avg_latency_s": _avg(latencies),
        "latency_p50_s": percentile(latencies, 50),
        "latency_p90_s": percentile(latencies, 90),
        "latency_p95_s": percentile(latencies, 95),
        "latency_p99_s": percentile(latencies, 99),
        "avg_faithfulness": _avg(faith_scores),
        "pass_rate_pct": round(100 * pass_count / len(scored), 1) if scored else 0.0,
        # Template correctness
        "template_scored_count": t_total,
        "template_pass_rate_pct": round(100 * t_pass / t_total, 1) if t_total else 0.0,
        "template_fallback_rate_pct": round(100 * t_fallback / t_total, 1) if t_total else 0.0,
        "template_fail_rate_pct": round(100 * t_fail / t_total, 1) if t_total else 0.0,
        # Tool grounding (deterministic hallucination check)
        "grounding_checkable_count": g_checkable,
        "grounding_pass_rate_pct": round(100 * g_pass / g_checkable, 1) if g_checkable else None,
        "grounding_fail_count": g_fail,
        "grounding_skip_count": g_skip,
        # Timing breakdown averages
        "avg_ttft_s": _avg(ttfts),
        "avg_thinking_s": _avg(thinkings),
        "avg_tool_total_s": _avg(tool_totals),
        "avg_post_tool_s": _avg(post_tools),
        "avg_generation_s": _avg(generations),
    }
