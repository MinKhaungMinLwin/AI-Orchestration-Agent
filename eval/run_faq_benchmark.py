#!/usr/bin/env python3
"""
FAQ Hybrid Search Benchmark — Legacy vs Hybrid (LLM-as-a-Judge).

Chạy tuần tự 2 container (legacy, hybrid), so sánh kết quả bằng LLM-as-a-Judge.

Usage:
  # Bước 1: Container FAQ_SEARCH_MODE=legacy
  python eval/run_faq_benchmark.py collect --mode legacy --token <JWT>

  # Bước 2: Container FAQ_SEARCH_MODE=hybrid
  python eval/run_faq_benchmark.py collect --mode hybrid --token <JWT>

  # Bước 3: So sánh bằng LLM-as-a-Judge
  python eval/run_faq_benchmark.py judge --openai-key <OPENAI_API_KEY>

Requirements:
  pip install requests openai
"""

import argparse
import json
import time
import uuid
from pathlib import Path

BENCHMARK_FILE = Path(__file__).parent / "data" / "support_agent_benchmark.json"
RESULTS_DIR = Path(__file__).parent / "results"
CHAT_PATH = "/tstation/messages/chat"
DEFAULT_URL = "http://localhost:8001"
DEFAULT_JUDGE_MODEL = "gpt-4o-mini"


# ── Collect ────────────────────────────────────────────────────────────────────

def collect(mode: str, base_url: str, token: str) -> None:
    """Gọi API cho từng query, ghi kết quả ra results/{mode}_results.json."""
    benchmark = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
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
        _save(mode, tc_results)  # 중간 저장 — crash-safe

    print(f"\n✅ Done. Saved to {RESULTS_DIR / f'{mode}_results.json'}")
    _print_collect_summary(mode, tc_results)


def _call_agent(base_url: str, token: str, query: str) -> dict:
    """SSE 스트리밍으로 agent 호출, 답변과 latency 반환."""
    import requests

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
    }

    tokens: list[str] = []
    t0 = time.perf_counter()

    try:
        with requests.post(url, json=payload, headers=headers, stream=True, timeout=60) as resp:
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
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "token":
                    tokens.append(event.get("content", ""))

        latency_ms = round((time.perf_counter() - t0) * 1000)
        answer = "".join(tokens)
        return {
            "status": "ok",
            "answer": answer,
            "latency_ms": latency_ms,
            "output_chars": len(answer),
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000)
        print(f"  ⚠ ERROR: {exc}")
        return {"status": "error", "error": str(exc), "latency_ms": latency_ms}


def _save(mode: str, data: list) -> None:
    path = RESULTS_DIR / f"{mode}_results.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_collect_summary(mode: str, tc_results: list) -> None:
    all_q = [q for tc in tc_results for q in tc["queries"]]
    ok = [q for q in all_q if q.get("status") == "ok"]
    latencies = [q["latency_ms"] for q in ok]
    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"\n{mode.upper()} summary:")
        print(f"  Queries : {len(ok)}/{len(all_q)} ok")
        print(f"  Latency : avg {avg:.0f}ms  |  min {min(latencies)}ms  |  max {max(latencies)}ms")


# ── Judge ──────────────────────────────────────────────────────────────────────

JUDGE_PROMPT = """\
당신은 AI 고객 서비스 응답 평가자입니다. 두 답변을 비교해 주세요.

[사용자 질문]
{query}

[응답 A — Legacy]
{legacy}

[응답 B — Hybrid]
{hybrid}

두 답변이 사용자의 질문 의도에 대해 같은 방향으로 답하고 있는지 판단하세요.
100% 동일할 필요는 없으며, 핵심 정보와 intent가 일치하면 MATCH입니다.

판단 기준:
- MATCH   : 두 답변이 같은 intent로 답변함 (표현이 달라도 무방)
- MISMATCH: 한쪽이 다른 정보를 전달하거나 질문 의도에 벗어난 답변을 함

반드시 아래 형식으로만 답변하세요:
VERDICT: <MATCH|MISMATCH>
REASON: <한 문장, 한국어>"""


def judge(openai_key: str, judge_model: str) -> None:
    """두 결과 파일 로드 → LLM-as-a-Judge → judgment_results.json 저장."""
    from openai import OpenAI

    legacy_path = RESULTS_DIR / "legacy_results.json"
    hybrid_path = RESULTS_DIR / "hybrid_results.json"

    if not legacy_path.exists() or not hybrid_path.exists():
        missing = [p.name for p in [legacy_path, hybrid_path] if not p.exists()]
        print(f"ERROR: {', '.join(missing)} 없음. 먼저 collect를 실행하세요.")
        return

    legacy_data = json.loads(legacy_path.read_text(encoding="utf-8"))
    hybrid_data = json.loads(hybrid_path.read_text(encoding="utf-8"))

    legacy_map: dict[str, dict] = {
        r["query"]: r
        for tc in legacy_data
        for r in tc["queries"]
    }

    client = OpenAI(api_key=openai_key)
    print(f"Judge model: {judge_model}")
    judgments: list[dict] = []
    total = sum(len(tc["queries"]) for tc in hybrid_data)
    done = 0

    for tc in hybrid_data:
        for r in tc["queries"]:
            done += 1
            query = r["query"]
            print(f"[{done:02d}/{total}] judging: {query[:55]}...")

            legacy_r = legacy_map.get(query, {})
            legacy_ans = legacy_r.get("answer", "")
            hybrid_ans = r.get("answer", "")

            if not legacy_ans or not hybrid_ans:
                verdict = "ERROR"
                reason = f"answer 없음 (legacy={bool(legacy_ans)}, hybrid={bool(hybrid_ans)})"
            elif legacy_r.get("status") != "ok" or r.get("status") != "ok":
                verdict = "ERROR"
                reason = "collect 오류로 판단 불가"
            else:
                verdict, reason = _llm_judge(client, judge_model, query, legacy_ans, hybrid_ans)

            judgments.append({
                "tc_id": tc["tc_id"],
                "title": tc["title"],
                "query": query,
                "verdict": verdict,
                "reason": reason,
                "legacy_latency_ms": legacy_r.get("latency_ms"),
                "hybrid_latency_ms": r.get("latency_ms"),
                "legacy_chars": legacy_r.get("output_chars"),
                "hybrid_chars": r.get("output_chars"),
            })

    out_path = RESULTS_DIR / "judgment_results.json"
    out_path.write_text(json.dumps(judgments, ensure_ascii=False, indent=2), encoding="utf-8")

    _print_judge_summary(judgments)
    print(f"\n✅ Saved to {out_path}")


def _llm_judge(client, judge_model: str, query: str, legacy_ans: str, hybrid_ans: str) -> tuple[str, str]:
    prompt = JUDGE_PROMPT.format(
        query=query,
        legacy=legacy_ans[:1500],
        hybrid=hybrid_ans[:1500],
    )
    resp = client.chat.completions.create(
        model=judge_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=120,
        temperature=0,
    )
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


def _print_judge_summary(judgments: list[dict]) -> None:
    total = len(judgments)
    verdicts = [j["verdict"] for j in judgments]

    match = verdicts.count("MATCH")
    mismatch = verdicts.count("MISMATCH")
    error = verdicts.count("ERROR")

    print("\n" + "=" * 50)
    print("BENCHMARK SUMMARY — Legacy vs Hybrid")
    print("=" * 50)
    print(f"Total queries : {total}")
    print(f"MATCH         : {match:2d}  ({match / total * 100:.0f}%)")
    print(f"MISMATCH      : {mismatch:2d}  ({mismatch / total * 100:.0f}%)")
    if error:
        print(f"ERROR         : {error:2d}")

    valid = [j for j in judgments if j["legacy_latency_ms"] and j["hybrid_latency_ms"]]
    if valid:
        avg_l = sum(j["legacy_latency_ms"] for j in valid) / len(valid)
        avg_h = sum(j["hybrid_latency_ms"] for j in valid) / len(valid)
        diff = avg_h - avg_l
        sign = "+" if diff > 0 else ""
        print("\nAvg latency")
        print(f"  Legacy : {avg_l:.0f}ms")
        print(f"  Hybrid : {avg_h:.0f}ms  ({sign}{diff:.0f}ms)")

    mismatch_cases = [j for j in judgments if j["verdict"] == "MISMATCH"]
    if mismatch_cases:
        print(f"\n⚠ MISMATCH cases ({len(mismatch_cases)}) — cần review:")
        for j in mismatch_cases:
            print(f"  [{j['tc_id']}] {j['query'][:50]}")
            print(f"         → {j['reason']}")

    print("=" * 50)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FAQ benchmark: legacy vs hybrid")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_collect = sub.add_parser("collect", help="Run queries against one container")
    p_collect.add_argument("--mode", choices=["legacy", "hybrid"], required=True)
    p_collect.add_argument("--url", default=DEFAULT_URL, help=f"Base URL (default: {DEFAULT_URL})")
    p_collect.add_argument("--token", required=True, help="JWT Bearer token")

    p_judge = sub.add_parser("judge", help="Compare results with LLM-as-a-Judge")
    p_judge.add_argument("--openai-key", required=True, help="OpenAI API key")
    p_judge.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help=f"Judge model (default: {DEFAULT_JUDGE_MODEL})")

    args = parser.parse_args()

    if args.cmd == "collect":
        collect(args.mode, args.url, args.token)
    elif args.cmd == "judge":
        judge(args.openai_key, args.judge_model)


if __name__ == "__main__":
    main()
