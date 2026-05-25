#!/usr/bin/env python3
"""
FAQ Hybrid Search Benchmark — Legacy vs Hybrid (LLM-as-a-Judge).

Run both containers sequentially and compare answers with LLM-as-a-Judge.

Env vars:
  JWT_TOKEN             Bearer token for the chat API (required for collect)
  LANGFUSE_PUBLIC_KEY   Langfuse public key (required for collect)
  LANGFUSE_SECRET_KEY   Langfuse secret key (required for collect)
  LANGFUSE_EVAL_HOST    Langfuse host reachable from this machine (default: http://localhost:3005)
  AI_GATEWAY_API_KEY    AI gateway API key (required for judge; falls back to OPENAI_API_KEY)
  JUDGE_API_URL         OpenAI-compatible judge API URL (default: http://localhost:4000/v1)
  JUDGE_MODEL           Judge model name (default: gpt-4o-mini)

Usage:
  # Step 1: container with FAQ_SEARCH_MODE=legacy
  python eval/run_faq_benchmark.py collect --mode legacy

  # Step 2: restart container with FAQ_SEARCH_MODE=hybrid
  python eval/run_faq_benchmark.py collect --mode hybrid

  # Step 3: compare with LLM-as-a-Judge
  python eval/run_faq_benchmark.py judge

Requirements:
  pip install requests openai
"""

import argparse
import json
import os
import time
import uuid
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

BENCHMARK_FILE = Path(__file__).parent / "data" / "support_agent_benchmark.json"
RESULTS_DIR = Path(__file__).parent / "results"
CHAT_PATH = "/api/tstation/messages/chat"
DEFAULT_BENCHMARK_URL = "https://localhost:8001"
DEFAULT_JUDGE_MODEL = "gpt-4o-mini"
DEFAULT_LANGFUSE_HOST = "http://localhost:3005"
DEFAULT_JUDGE_API_URL = "http://localhost:4000/v1"
LANGFUSE_TRACE_DELAY_S = 2  # seconds to wait before querying Langfuse
REASONING_MODEL_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def _percentile(values: list[int | float], pct: float) -> float:
    """Return percentile with linear interpolation."""
    if not values:
        return 0.0
    sorted_values = sorted(float(v) for v in values)
    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (len(sorted_values) - 1) * pct / 100
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    weight = rank - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def _load_dotenv() -> None:
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


# ── Collect ────────────────────────────────────────────────────────────────────

def collect(mode: str, base_url: str, tc_ids: list[str] | None = None) -> None:
    token = os.environ["JWT_TOKEN"]
    benchmark = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
    if tc_ids:
        benchmark = [tc for tc in benchmark if tc["tc_id"] in tc_ids]
    RESULTS_DIR.mkdir(exist_ok=True)

    total = sum(len(tc["queries"]) for tc in benchmark)
    done = 0
    tc_results = []

    for tc in benchmark:
        query_results = []
        for query in tc["queries"]:
            done += 1
            print(f"[{done:02d}/{total}] {tc['tc_id']} | {query[:55]}...")

            result = _call_agent(base_url, token, query)
            result["query"] = query
            query_results.append(result)

            time.sleep(0.3)

        tc_results.append({
            "tc_id": tc["tc_id"],
            "title": tc["title"],
            "queries": query_results,
        })
        _save(mode, tc_results)  # save after each TC — crash-safe

    print(f"\nDone. Saved to {RESULTS_DIR / f'{mode}_results.json'}")
    _print_collect_summary(mode, tc_results)


def _call_agent(base_url: str, token: str, query: str) -> dict:
    import requests

    tracing_id = uuid.uuid4().hex
    url = base_url.rstrip("/") + CHAT_PATH
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = {
        "content": query,
        "session_id": f"bench-{uuid.uuid4().hex[:12]}",
        "stream": True,
        "tracing_id": tracing_id,
    }

    answer = ""
    t0 = time.perf_counter()

    with requests.post(url, json=payload, headers=headers, stream=True, timeout=60, verify=False) as resp:
        resp.raise_for_status()
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if not line.startswith("data: "):
                continue
            data_str = line[6:].strip()
            if not data_str or data_str == "[DONE]":
                continue
            event = json.loads(data_str)
            if event.get("type") == "message" and event.get("content"):
                answer = event["content"]

    latency_ms = round((time.perf_counter() - t0) * 1000)
    usage = _fetch_langfuse_usage(tracing_id)
    return {
        "status": "ok",
        "answer": answer,
        "latency_ms": latency_ms,
        "tracing_id": tracing_id,
        **usage,
    }


def _fetch_langfuse_usage(tracing_id: str) -> dict:
    import requests

    host = os.environ.get("LANGFUSE_EVAL_HOST", DEFAULT_LANGFUSE_HOST)
    public_key = os.environ["LANGFUSE_PUBLIC_KEY"]
    secret_key = os.environ["LANGFUSE_SECRET_KEY"]

    time.sleep(LANGFUSE_TRACE_DELAY_S)  # wait for Langfuse to ingest the trace

    url = f"{host}/api/public/traces/{tracing_id}"
    try:
        resp = requests.get(url, auth=(public_key, secret_key), timeout=10)
        resp.raise_for_status()
        trace_json = resp.json()

        all_usage = _extract_usage(trace_json, scope="all")
        support_usage = _extract_usage(trace_json, scope="support")
        if all_usage["total_tokens"] or support_usage["total_tokens"]:
            return _format_usage_result(all_usage, support_usage)

        # Langfuse often stores token usage on generation observations, not on
        # the trace summary. Fall back to summing observations for this trace.
        obs_url = f"{host}/api/public/observations"
        obs_resp = requests.get(
            obs_url,
            params={"traceId": tracing_id, "limit": 100},
            auth=(public_key, secret_key),
            timeout=10,
        )
        obs_resp.raise_for_status()
        observations_json = obs_resp.json()
        all_usage = _extract_usage(observations_json, scope="all")
        support_usage = _extract_usage(observations_json, scope="support")
        return _format_usage_result(all_usage, support_usage)
    except Exception as exc:
        print(f"  [warn] Langfuse usage unavailable for {tracing_id}: {exc}")
        return _format_usage_result(
            {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "token_scope": "all"},
            {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "token_scope": "support"},
        )


def _format_usage_result(all_usage: dict, support_usage: dict) -> dict:
    """Flatten token usage while retaining both all-trace and support-only breakdowns."""
    return {
        # Backward-compatible default: support agent only.
        "input_tokens": support_usage.get("input_tokens", 0),
        "output_tokens": support_usage.get("output_tokens", 0),
        "total_tokens": support_usage.get("total_tokens", 0),
        "token_scope": "support_agent",
        "support_input_tokens": support_usage.get("input_tokens", 0),
        "support_output_tokens": support_usage.get("output_tokens", 0),
        "support_total_tokens": support_usage.get("total_tokens", 0),
        "trace_input_tokens": all_usage.get("input_tokens", 0),
        "trace_output_tokens": all_usage.get("output_tokens", 0),
        "trace_total_tokens": all_usage.get("total_tokens", 0),
    }


def _extract_usage(payload: object, scope: str = "all") -> dict:
    """Extract token usage from common Langfuse trace/observation response shapes."""
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "token_scope": scope}

    def read_num(obj: dict, *keys: str) -> int:
        for key in keys:
            value = obj.get(key)
            if isinstance(value, (int, float)):
                return int(value)
        return 0

    def add_usage(obj: dict) -> None:
        usage_sources = []
        for key in ("usage", "usageDetails", "usage_details"):
            value = obj.get(key)
            if isinstance(value, dict) and (
                read_num(value, "input", "prompt", "inputTokens", "promptTokens", "input_tokens", "prompt_tokens")
                or read_num(value, "output", "completion", "outputTokens", "completionTokens", "output_tokens", "completion_tokens")
                or read_num(value, "total", "totalTokens", "total_tokens")
            ):
                usage_sources.append(value)
                break
        if not usage_sources:
            # Some SDK/API shapes put token fields directly on the observation.
            usage_sources.append(obj)

        for usage in usage_sources:
            input_tokens = read_num(
                usage,
                "input",
                "prompt",
                "inputTokens",
                "promptTokens",
                "input_tokens",
                "prompt_tokens",
            )
            output_tokens = read_num(
                usage,
                "output",
                "completion",
                "outputTokens",
                "completionTokens",
                "output_tokens",
                "completion_tokens",
            )
            total_tokens = read_num(
                usage,
                "total",
                "totalTokens",
                "total_tokens",
            )
            if not total_tokens and (input_tokens or output_tokens):
                total_tokens = input_tokens + output_tokens

            totals["input_tokens"] += input_tokens
            totals["output_tokens"] += output_tokens
            totals["total_tokens"] += total_tokens

    def observation_id(obj: dict) -> str | None:
        value = obj.get("id") or obj.get("observationId") or obj.get("observation_id")
        return str(value) if value else None

    def parent_observation_id(obj: dict) -> str | None:
        value = obj.get("parentObservationId") or obj.get("parent_observation_id")
        return str(value) if value else None

    def observation_name(obj: dict) -> str:
        return str(obj.get("name") or "")

    def collect_observations(obj: object) -> list[dict]:
        if isinstance(obj, dict):
            observations = obj.get("observations")
            if isinstance(observations, list):
                return [item for item in observations if isinstance(item, dict)]
            data = obj.get("data")
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
            return []
        if isinstance(obj, list):
            return [item for item in obj if isinstance(item, dict)]
        return []

    def support_observations(observations: list[dict]) -> list[dict]:
        by_parent: dict[str, list[dict]] = {}
        roots: list[str] = []
        for obs in observations:
            oid = observation_id(obs)
            if not oid:
                continue
            name = observation_name(obs).lower()
            if name == "agent:support" or "support_agent" in name:
                roots.append(oid)
            parent = parent_observation_id(obs)
            if parent:
                by_parent.setdefault(parent, []).append(obs)

        support_ids: set[str] = set()
        stack = roots[:]
        while stack:
            oid = stack.pop()
            if oid in support_ids:
                continue
            support_ids.add(oid)
            for child in by_parent.get(oid, []):
                child_id = observation_id(child)
                if child_id:
                    stack.append(child_id)

        return [obs for obs in observations if observation_id(obs) in support_ids]

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            add_usage(obj)
            for key, value in obj.items():
                if key in {"usage", "usageDetails", "usage_details"}:
                    continue
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    if scope == "support":
        observations = support_observations(collect_observations(payload))
        walk(observations)
    else:
        walk(payload)
    return totals


def _save(mode: str, data: list) -> None:
    path = RESULTS_DIR / f"{mode}_results.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_collect_summary(mode: str, tc_results: list) -> None:
    all_q = [q for tc in tc_results for q in tc["queries"]]
    latencies = [q["latency_ms"] for q in all_q]
    input_tokens = [q.get("input_tokens", 0) for q in all_q]
    output_tokens = [q.get("output_tokens", 0) for q in all_q]
    trace_input_tokens = [q.get("trace_input_tokens", 0) for q in all_q]
    trace_output_tokens = [q.get("trace_output_tokens", 0) for q in all_q]

    print(f"\n{mode.upper()} summary:")
    print(f"  Queries      : {len(all_q)}")
    if latencies:
        avg = sum(latencies) / len(latencies)
        print(
            "  Latency      : "
            f"avg {avg:.0f}ms  |  "
            f"p50 {_percentile(latencies, 50):.0f}ms  |  "
            f"p95 {_percentile(latencies, 95):.0f}ms  |  "
            f"p99 {_percentile(latencies, 99):.0f}ms  |  "
            f"min {min(latencies)}ms  |  max {max(latencies)}ms"
        )
    if any(input_tokens):
        print(f"  Support tokens: input avg {sum(input_tokens)/len(input_tokens):.0f}  |  output avg {sum(output_tokens)/len(output_tokens):.0f}")
    if any(trace_input_tokens):
        print(f"  Trace tokens  : input avg {sum(trace_input_tokens)/len(trace_input_tokens):.0f}  |  output avg {sum(trace_output_tokens)/len(trace_output_tokens):.0f}")


# ── Judge ──────────────────────────────────────────────────────────────────────

# Korean prompt
JUDGE_PROMPT_KO = """\
당신은 T-Station(타이어/자동차 서비스) AI 챗봇의 응답 품질 평가자입니다.
두 챗봇 응답이 사용자 질문의 의도에 동일하게 답하고 있는지 판단하세요.

[사용자 질문]
{query}

[응답 A — Legacy]
{legacy}

[응답 B — Hybrid]
{hybrid}

판단 기준:
MATCH — 두 응답이 사용자 질문의 핵심 의도에 같은 방향으로 답함
  - 표현·문장 구조가 달라도 무방
  - B가 A보다 더 자세하더라도 핵심 정보가 일치하면 MATCH
  - 정책·금액·조건·기간 등 핵심 사실이 동일하게 안내되면 MATCH

MISMATCH — 두 응답이 서로 다른 정보를 전달하거나 한쪽이 질문 의도를 벗어남
  - 한쪽은 올바른 정책을 안내하고 다른 쪽은 무관한 서비스를 안내
  - 핵심 사실(금액·기간·조건 등)이 서로 다르게 안내됨
  - 한쪽이 질문과 무관한 내용으로만 답변

반드시 아래 형식으로만 답변하세요:
VERDICT: <MATCH|MISMATCH>
REASON: <한 문장>"""

# English prompt
JUDGE_PROMPT_EN = """\
You are a quality evaluator for T-Station (tire/car service) AI chatbot responses.
Determine whether both responses address the user's question with the same intent.

[User question]
{query}

[Response A — Legacy]
{legacy}

[Response B — Hybrid]
{hybrid}

Criteria:
MATCH — both responses answer the core intent of the question in the same direction
  - wording or sentence structure may differ
  - B being more detailed than A is still MATCH if the core information is consistent
  - same policy, price, condition, or time period guidance → MATCH

MISMATCH — the responses convey different information, or one misses the user's intent
  - one correctly explains a policy while the other describes an unrelated service
  - key facts (price, duration, conditions) are stated differently
  - one response answers something unrelated to the question

Reply in this exact format:
VERDICT: <MATCH|MISMATCH>
REASON: <one sentence in Korean>"""

JUDGE_PROMPTS = {"ko": JUDGE_PROMPT_KO, "en": JUDGE_PROMPT_EN}


def judge(judge_lang: str) -> None:
    from openai import OpenAI

    assert judge_lang in JUDGE_PROMPTS, f"--lang must be 'ko' or 'en', got '{judge_lang}'"
    judge_api_url = os.environ.get("JUDGE_API_URL", DEFAULT_JUDGE_API_URL)
    judge_api_key = os.environ.get("AI_GATEWAY_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not judge_api_key:
        raise RuntimeError("Missing AI_GATEWAY_API_KEY or OPENAI_API_KEY for judge")
    judge_model = os.environ.get("JUDGE_MODEL", DEFAULT_JUDGE_MODEL)
    judge_prompt = JUDGE_PROMPTS[judge_lang]

    legacy_path = RESULTS_DIR / "legacy_results.json"
    hybrid_path = RESULTS_DIR / "hybrid_results.json"

    assert legacy_path.exists(), f"Missing {legacy_path.name} — run collect first"
    assert hybrid_path.exists(), f"Missing {hybrid_path.name} — run collect first"

    legacy_data = json.loads(legacy_path.read_text(encoding="utf-8"))
    hybrid_data = json.loads(hybrid_path.read_text(encoding="utf-8"))

    legacy_map: dict[str, dict] = {
        r["query"]: r
        for tc in legacy_data
        for r in tc["queries"]
    }

    client = OpenAI(api_key=judge_api_key, base_url=judge_api_url)
    print(f"Judge model: {judge_model}  |  api: {judge_api_url}  |  prompt lang: {judge_lang}")

    judgments: list[dict] = []
    total = sum(len(tc["queries"]) for tc in hybrid_data)
    done = 0

    for tc in hybrid_data:
        for r in tc["queries"]:
            done += 1
            query = r["query"]
            print(f"[{done:02d}/{total}] {query[:55]}...")

            legacy_r = legacy_map.get(query, {})
            legacy_ans = legacy_r.get("answer", "")
            hybrid_ans = r.get("answer", "")

            if not legacy_ans or not hybrid_ans:
                verdict = "ERROR"
                reason = f"empty answer (legacy={bool(legacy_ans)}, hybrid={bool(hybrid_ans)})"
            else:
                verdict, reason = _llm_judge(client, judge_model, judge_prompt, query, legacy_ans, hybrid_ans)

            judgments.append({
                "tc_id": tc["tc_id"],
                "title": tc["title"],
                "query": query,
                "judge_model": judge_model,
                "judge_api_url": judge_api_url,
                "judge_prompt_lang": judge_lang,
                "verdict": verdict,
                "reason": reason,
                "legacy_latency_ms": legacy_r.get("latency_ms"),
                "hybrid_latency_ms": r.get("latency_ms"),
                "legacy_input_tokens": legacy_r.get("input_tokens"),
                "legacy_output_tokens": legacy_r.get("output_tokens"),
                "legacy_token_scope": legacy_r.get("token_scope", "support"),
                "legacy_support_input_tokens": legacy_r.get("support_input_tokens", legacy_r.get("input_tokens")),
                "legacy_support_output_tokens": legacy_r.get("support_output_tokens", legacy_r.get("output_tokens")),
                "legacy_trace_input_tokens": legacy_r.get("trace_input_tokens"),
                "legacy_trace_output_tokens": legacy_r.get("trace_output_tokens"),
                "hybrid_input_tokens": r.get("input_tokens"),
                "hybrid_output_tokens": r.get("output_tokens"),
                "hybrid_token_scope": r.get("token_scope", "support"),
                "hybrid_support_input_tokens": r.get("support_input_tokens", r.get("input_tokens")),
                "hybrid_support_output_tokens": r.get("support_output_tokens", r.get("output_tokens")),
                "hybrid_trace_input_tokens": r.get("trace_input_tokens"),
                "hybrid_trace_output_tokens": r.get("trace_output_tokens"),
            })

    out_path = RESULTS_DIR / f"judgment_results_{judge_lang}.json"
    out_path.write_text(json.dumps(judgments, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = _build_judge_summary(
        judgments,
        judge_model=judge_model,
        judge_api_url=judge_api_url,
        judge_lang=judge_lang,
    )
    summary_path = RESULTS_DIR / f"judgment_summary_{judge_lang}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    _print_judge_summary(summary, judgments)
    print(f"\nSaved to {out_path}")
    print(f"Summary saved to {summary_path}")


def _llm_judge(client, judge_model: str, judge_prompt: str, query: str, legacy_ans: str, hybrid_ans: str) -> tuple[str, str]:
    prompt = judge_prompt.format(
        query=query,
        legacy=legacy_ans[:1500],
        hybrid=hybrid_ans[:1500],
    )
    kwargs = {
        "model": judge_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 512,
    }
    if not judge_model.startswith(REASONING_MODEL_PREFIXES):
        kwargs["temperature"] = 0
    resp = client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content.strip()
    verdict, reason = "MATCH", text

    for line in text.splitlines():
        if line.startswith("VERDICT:"):
            v = line.split(":", 1)[1].strip()
            if v in ("MATCH", "MISMATCH"):
                verdict = v
        elif line.startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()

    return verdict, reason


def _avg(values: list[int | float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _build_judge_summary(judgments: list[dict], *, judge_model: str, judge_api_url: str, judge_lang: str) -> dict:
    total = len(judgments)
    verdicts = [j["verdict"] for j in judgments]

    match = verdicts.count("MATCH")
    mismatch = verdicts.count("MISMATCH")
    error = verdicts.count("ERROR")

    summary: dict = {
        "judge": {
            "model": judge_model,
            "api_url": judge_api_url,
            "prompt_lang": judge_lang,
        },
        "total": total,
        "verdicts": {
            "MATCH": match,
            "MISMATCH": mismatch,
            "ERROR": error,
            "match_rate": round(match / total, 4) if total else 0.0,
            "mismatch_rate": round(mismatch / total, 4) if total else 0.0,
        },
    }

    valid_lat = [j for j in judgments if j["legacy_latency_ms"] and j["hybrid_latency_ms"]]
    if valid_lat:
        legacy_latencies = [j["legacy_latency_ms"] for j in valid_lat]
        hybrid_latencies = [j["hybrid_latency_ms"] for j in valid_lat]
        avg_l = _avg(legacy_latencies)
        avg_h = _avg(hybrid_latencies)
        summary["latency_ms"] = {
            "legacy": {
                "avg": round(avg_l),
                "p50": round(_percentile(legacy_latencies, 50)),
                "p95": round(_percentile(legacy_latencies, 95)),
                "p99": round(_percentile(legacy_latencies, 99)),
                "min": min(legacy_latencies),
                "max": max(legacy_latencies),
            },
            "hybrid": {
                "avg": round(avg_h),
                "p50": round(_percentile(hybrid_latencies, 50)),
                "p95": round(_percentile(hybrid_latencies, 95)),
                "p99": round(_percentile(hybrid_latencies, 99)),
                "min": min(hybrid_latencies),
                "max": max(hybrid_latencies),
            },
            "hybrid_minus_legacy_avg": round(avg_h - avg_l),
        }

    _add_token_summary(
        summary,
        judgments,
        key="support_agent",
        legacy_input_key="legacy_support_input_tokens",
        legacy_output_key="legacy_support_output_tokens",
        hybrid_input_key="hybrid_support_input_tokens",
        hybrid_output_key="hybrid_support_output_tokens",
    )
    _add_token_summary(
        summary,
        judgments,
        key="all_trace",
        legacy_input_key="legacy_trace_input_tokens",
        legacy_output_key="legacy_trace_output_tokens",
        hybrid_input_key="hybrid_trace_input_tokens",
        hybrid_output_key="hybrid_trace_output_tokens",
    )

    mismatch_cases = [j for j in judgments if j["verdict"] == "MISMATCH"]
    if mismatch_cases:
        summary["mismatch_cases"] = [
            {
                "tc_id": j["tc_id"],
                "query": j["query"],
                "reason": j["reason"],
            }
            for j in mismatch_cases
        ]

    return summary


def _add_token_summary(
    summary: dict,
    judgments: list[dict],
    *,
    key: str,
    legacy_input_key: str,
    legacy_output_key: str,
    hybrid_input_key: str,
    hybrid_output_key: str,
) -> None:
    valid = [j for j in judgments if j.get(legacy_input_key) is not None and j.get(hybrid_input_key) is not None]
    if not valid:
        return

    avg_li = _avg([j.get(legacy_input_key, 0) or 0 for j in valid])
    avg_hi = _avg([j.get(hybrid_input_key, 0) or 0 for j in valid])
    avg_lo = _avg([j.get(legacy_output_key, 0) or 0 for j in valid])
    avg_ho = _avg([j.get(hybrid_output_key, 0) or 0 for j in valid])
    summary.setdefault("tokens_avg", {})[key] = {
        "legacy": {
            "input": round(avg_li),
            "output": round(avg_lo),
        },
        "hybrid": {
            "input": round(avg_hi),
            "output": round(avg_ho),
        },
        "hybrid_minus_legacy": {
            "input": round(avg_hi - avg_li),
            "output": round(avg_ho - avg_lo),
        },
    }


def _print_judge_summary(summary: dict, judgments: list[dict]) -> None:
    total = summary["total"]
    match = summary["verdicts"]["MATCH"]
    mismatch = summary["verdicts"]["MISMATCH"]
    error = summary["verdicts"]["ERROR"]
    judge = summary["judge"]

    print("\n" + "=" * 50)
    print("BENCHMARK SUMMARY — Legacy vs Hybrid")
    print("=" * 50)
    print(f"Judge  : {judge['model']}  |  api={judge['api_url']}  |  lang={judge['prompt_lang']}")
    print(f"Total   : {total}")
    print(f"MATCH   : {match:2d}  ({match / total * 100:.0f}%)")
    print(f"MISMATCH: {mismatch:2d}  ({mismatch / total * 100:.0f}%)")
    if error:
        print(f"ERROR   : {error:2d}")

    if latency := summary.get("latency_ms"):
        diff = latency["hybrid_minus_legacy_avg"]
        sign = "+" if diff > 0 else ""
        print("\nAvg latency")
        print(
            f"  Legacy : avg {latency['legacy']['avg']:.0f}ms  |  "
            f"p50 {latency['legacy']['p50']:.0f}ms  |  "
            f"p95 {latency['legacy']['p95']:.0f}ms  |  "
            f"p99 {latency['legacy']['p99']:.0f}ms"
        )
        print(
            f"  Hybrid : avg {latency['hybrid']['avg']:.0f}ms  ({sign}{diff:.0f}ms)  |  "
            f"p50 {latency['hybrid']['p50']:.0f}ms  |  "
            f"p95 {latency['hybrid']['p95']:.0f}ms  |  "
            f"p99 {latency['hybrid']['p99']:.0f}ms"
        )

    if tokens_by_scope := summary.get("tokens_avg"):
        print("\nAvg token usage")
        for label, tokens in (("Support agent", tokens_by_scope.get("support_agent")), ("All trace", tokens_by_scope.get("all_trace"))):
            if not tokens:
                continue
            print(f"  {label}:")
            print(f"    Legacy : input {tokens['legacy']['input']:.0f}  |  output {tokens['legacy']['output']:.0f}")
            print(f"    Hybrid : input {tokens['hybrid']['input']:.0f}  |  output {tokens['hybrid']['output']:.0f}")

    mismatch_cases = [j for j in judgments if j["verdict"] == "MISMATCH"]
    if mismatch_cases:
        print(f"\nMISMATCH cases ({len(mismatch_cases)}) — review needed:")
        for j in mismatch_cases:
            print(f"  [{j['tc_id']}] {j['query'][:50]}")
            print(f"         -> {j['reason']}")

    print("=" * 50)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="FAQ benchmark: legacy vs hybrid")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_collect = sub.add_parser("collect", help="Run queries against one container")
    p_collect.add_argument("--mode", choices=["legacy", "hybrid"], required=True)
    p_collect.add_argument("--url", default=DEFAULT_BENCHMARK_URL, help=f"Base URL (default: {DEFAULT_BENCHMARK_URL})")
    p_collect.add_argument("--tc-ids", nargs="+", metavar="TC_ID", help="Run only specific TC IDs, e.g. --tc-ids TC-011 TC-023")

    p_judge = sub.add_parser("judge", help="Compare results with LLM-as-a-Judge")
    p_judge.add_argument("--lang", choices=["ko", "en"], default="ko", help="Prompt language (default: ko)")

    args = parser.parse_args()

    if args.cmd == "collect":
        collect(args.mode, args.url, args.tc_ids)
    elif args.cmd == "judge":
        judge(args.lang)


if __name__ == "__main__":
    main()
