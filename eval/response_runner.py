import json
import logging
import os
import time

import httpx

from common import SCORED_AGENTS, percentile
from judges import call_faithfulness_llm

logger = logging.getLogger(__name__)


def get_jwt_token() -> str:
    return os.environ.get("EVAL_JWT_TOKEN", "")


def _compute_timing(
    total_s: float,
    tool_events: list[dict],
    tool_start_times: dict[str, list[float]],
    sub_agent_start_s: float | None,
    thinking_end_s: float | None,
    data_event_s: float | None,
) -> dict:
    """Compute per-segment timing from SSE event arrival timestamps.

    All segments are measured directly from SSE events emitted by production code:

      total_s      — request start → [DONE] marker
      routing_s    — request start → "sub-agent start" event
                     (coordinator routing: auth + slot loading + agent dispatch)
      thinking_s   — "sub-agent start" → first "tool_start" status event
                     (LLM initial decision: which tool to call)
      tool_calls   — per tool: "tool_start" status → "tool" result event
      tool_total_s — earliest tool_start → latest tool result (wall time)
      response_s   — last tool result → "data" template event
                     (post-tool LLM reasoning + template generation)
    """
    # Per-tool breakdown: match tool_start status events to tool result events in order
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

    # Tool wall time: earliest tool_start → latest tool result
    valid_starts = [tc["start_s"] for tc in tool_calls if tc["start_s"] is not None]
    all_ends = [tc["end_s"] for tc in tool_calls]
    tool_total_s: float | None = None
    last_tool_end: float | None = None
    if valid_starts and all_ends:
        tool_total_s = round(max(all_ends) - min(valid_starts), 3)
        last_tool_end = max(all_ends)

    # routing_s: 0 → sub-agent start (coordinator setup + dispatch overhead)
    routing_s: float | None = round(sub_agent_start_s, 3) if sub_agent_start_s is not None else None

    # thinking_s: sub-agent start → first tool_start (pure LLM decision time)
    # Falls back to 0 as reference if no sub-agent event was received
    thinking_s: float | None = None
    if thinking_end_s is not None:
        ref = sub_agent_start_s or 0.0
        thinking_s = round(thinking_end_s - ref, 3)

    # response_s: last tool result → data template event (post-tool LLM reasoning)
    # Only present when tools were called and a data template was returned
    response_s: float | None = None
    if data_event_s is not None and last_tool_end is not None:
        response_s = round(data_event_s - last_tool_end, 3)

    return {
        "total_s": total_s,
        "routing_s": routing_s,
        "thinking_s": thinking_s,
        "tool_calls": tool_calls,
        "tool_total_s": tool_total_s,
        "response_s": response_s,
    }


def call_chat(api_url: str, jwt_token: str, user_message: str, session_id: str, timeout: int = 120) -> dict:
    url = f"{api_url.rstrip('/')}/tstation/messages/chat"
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}
    payload = {"content": user_message, "session_id": session_id, "stream": True}

    start = time.time()
    template_events: list[dict] = []
    tool_events: list[dict] = []  # includes received_at_s internally for timing

    # Timing accumulators — all measured from SSE event arrival times
    sub_agent_start_s: float | None = None  # "sub-agent start" → agent dispatch complete
    thinking_end_s: float | None = None     # first "tool_start" status OR "답변 중..."
    data_event_s: float | None = None       # first "data" template event
    tool_start_times: dict[str, list[float]] = {}  # tool_name → [start_s, ...]
    actual_agent: str | None = None         # agent_class from first agent_flow event

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
                if data_event_s is None:
                    data_event_s = t

            elif etype == "tool":
                # Production always sends: "tool" (name), "input" (args), "output" (result), "source_domain"
                tool_events.append({
                    "tool_name": event["tool"],
                    "tool_input": event.get("input"),
                    "tool_output": event.get("output"),
                    "source_domain": event.get("source_domain"),
                    "received_at_s": t,  # kept internally for timing, stripped before output
                })

            elif etype == "agent_flow":
                if actual_agent is None and event.get("agent_class"):
                    # Normalize "Discovery Agent" → "discovery_agent" to match SCORED_AGENTS / AF_TO_AGENT
                    actual_agent = event["agent_class"].lower().replace(" ", "_")

            elif etype == "sub-agent":
                if event.get("status") == "start" and sub_agent_start_s is None:
                    sub_agent_start_s = t

            elif etype == "status":
                status_val = event.get("status", "")
                if status_val == "tool_start":
                    tool_name = event.get("tool", "")
                    tool_start_times.setdefault(tool_name, []).append(t)
                    if thinking_end_s is None:
                        thinking_end_s = t
                elif status_val == "답변 중...":  # Korean server status: "Answering..."
                    if thinking_end_s is None:
                        thinking_end_s = t

    total_s = round(time.time() - start, 3)
    timing = _compute_timing(total_s, tool_events, tool_start_times, sub_agent_start_s, thinking_end_s, data_event_s)

    # Strip internal timing field before returning
    tool_evidence = [{k: v for k, v in e.items() if k != "received_at_s"} for e in tool_events]

    return {
        "tool_evidence": tool_evidence,
        "template_events": template_events,
        "timing": timing,
        "actual_agent": actual_agent or "",
    }


def score_faithfulness(
    user_message: str,
    tool_evidence: list[dict],
    template_events: list[dict],
    judge_api_url: str,
    judge_api_key: str,
) -> dict:
    scored = call_faithfulness_llm(
        judge_api_url=judge_api_url,
        judge_api_key=judge_api_key,
        user_message=user_message,
        tool_evidence=json.dumps(tool_evidence, ensure_ascii=False),
        response=json.dumps(template_events, ensure_ascii=False),
    )
    verdict = "PASS" if float(scored["faithfulness"]) > 0.5 else "FAIL"
    return {**scored, "verdict": verdict}


def _is_scored_agent(record: dict) -> bool:
    """Return True if this record should count toward eval metrics.

    Records from agents outside SCORED_AGENTS (e.g. leading_agent, support_agent)
    are excluded. Records without actual_agent are included by default.
    Normalizes "Discovery Agent" → "discovery_agent" for backward compat.
    """
    actual = record.get("actual_agent") or ""
    if not actual:
        return True
    return actual.lower().replace(" ", "_") in SCORED_AGENTS


def summarize_records(results: list[dict]) -> dict:
    included = [r for r in results if _is_scored_agent(r)]
    excluded_count = len(results) - len(included)

    latencies = [r["timing"]["total_s"] for r in included if isinstance((r.get("timing") or {}).get("total_s"), (int, float))]
    scored = [r for r in included if r.get("faithfulness_eval")]
    faith_scores = [float(r["faithfulness_eval"]["faithfulness"]) for r in scored]
    pass_count = sum(1 for r in scored if r["faithfulness_eval"]["verdict"] == "PASS")

    template_scored = [r for r in included if r.get("template_eval")]
    template_verdicts = [r["template_eval"]["verdict"] for r in template_scored]
    t_pass = template_verdicts.count("PASS")
    t_fallback = template_verdicts.count("FALLBACK")
    t_fail = template_verdicts.count("FAIL")
    t_total = len(template_scored)

    grounding_scored = [r for r in included if r.get("grounding_eval")]
    grounding_verdicts = [r["grounding_eval"]["verdict"] for r in grounding_scored]
    g_pass = grounding_verdicts.count("PASS")
    g_fail = grounding_verdicts.count("FAIL")
    g_skip = grounding_verdicts.count("SKIP")
    g_checkable = g_pass + g_fail

    # Timing averages — only include records that have timing data
    def _avg(vals: list[float]) -> float | None:
        return round(sum(vals) / len(vals), 3) if vals else None

    timings = [r["timing"] for r in included if r.get("timing")]

    routings = [t["routing_s"] for t in timings if t.get("routing_s") is not None]
    thinkings = [t["thinking_s"] for t in timings if t.get("thinking_s") is not None]
    tool_totals = [t["tool_total_s"] for t in timings if t.get("tool_total_s") is not None]
    responses = [t["response_s"] for t in timings if t.get("response_s") is not None]

    # faithfulness_bin: binary score — 1 per PASS, 0 per FAIL, averaged (= pass_rate as 0–1)
    faith_bin_scores = [1.0 if r["faithfulness_eval"]["verdict"] == "PASS" else 0.0 for r in scored]

    # LLM vs Tool latency split (per record: LLM = routing + thinking + response)
    llm_times = [
        (t.get("routing_s") or 0.0) + (t.get("thinking_s") or 0.0) + (t.get("response_s") or 0.0)
        for t in timings
    ]
    tool_times = [t.get("tool_total_s") or 0.0 for t in timings]
    avg_llm = _avg(llm_times)
    avg_tool = _avg(tool_times)
    avg_total_for_pct = _avg([t["total_s"] for t in timings if isinstance(t.get("total_s"), (int, float))])

    return {
        "total_count": len(results),
        "included_count": len(included),
        "excluded_count": excluded_count,
        "scored_count": len(scored),
        "pass_count": pass_count,
        "fail_count": len(scored) - pass_count,
        "avg_latency_s": _avg(latencies),
        "latency_p50_s": percentile(latencies, 50),
        "latency_p90_s": percentile(latencies, 90),
        "latency_p95_s": percentile(latencies, 95),
        "latency_p99_s": percentile(latencies, 99),
        "avg_faithfulness": _avg(faith_scores),
        "faithfulness_p50": percentile(faith_scores, 50),
        "faithfulness_p90": percentile(faith_scores, 90),
        "faithfulness_p95": percentile(faith_scores, 95),
        "faithfulness_p99": percentile(faith_scores, 99),
        "avg_faithfulness_bin": _avg(faith_bin_scores),
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
        # Timing segments — each measured directly from SSE events
        "avg_routing_s": _avg(routings),
        "routing_p50_s": percentile(routings, 50),
        "routing_p90_s": percentile(routings, 90),
        "routing_p95_s": percentile(routings, 95),
        "routing_p99_s": percentile(routings, 99),
        "avg_thinking_s": _avg(thinkings),
        "thinking_p50_s": percentile(thinkings, 50),
        "thinking_p90_s": percentile(thinkings, 90),
        "thinking_p95_s": percentile(thinkings, 95),
        "thinking_p99_s": percentile(thinkings, 99),
        "avg_tool_total_s": _avg(tool_totals),
        "tool_total_p50_s": percentile(tool_totals, 50),
        "tool_total_p90_s": percentile(tool_totals, 90),
        "tool_total_p95_s": percentile(tool_totals, 95),
        "tool_total_p99_s": percentile(tool_totals, 99),
        "avg_response_s": _avg(responses),
        "response_p50_s": percentile(responses, 50),
        "response_p90_s": percentile(responses, 90),
        "response_p95_s": percentile(responses, 95),
        "response_p99_s": percentile(responses, 99),
        # LLM vs Tool latency split
        "avg_llm_s": avg_llm,
        "avg_tool_s": avg_tool,
        "llm_pct": round(avg_llm / avg_total_for_pct * 100, 1) if avg_llm and avg_total_for_pct else None,
        "tool_pct": round(avg_tool / avg_total_for_pct * 100, 1) if avg_tool is not None and avg_total_for_pct else None,
    }
