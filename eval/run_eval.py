"""
LLM-as-Judge Evaluation Script for tstation-ai model experiments.

Usage:
    # Step 1: Run baseline (gpt-5.4-reasoning)
    python eval/run_eval.py --run baseline --api-url http://localhost:8000 --api-key YOUR_KEY

    # Step 2: Change AI_MODEL_REASONING in .env to experiment model, restart server, then:
    python eval/run_eval.py --run experiment --api-url http://localhost:8000 --api-key YOUR_KEY

    # Step 3: Judge and compare (judge-api-url = AI Gateway base URL, e.g. http://localhost:4000/v1)
    python eval/run_eval.py --judge --judge-api-url http://localhost:4000/v1 --judge-api-key YOUR_KEY

Scores:
    - faithfulness (0.0-1.0 float, binarized >0.5): does the response stay true to tool data? no hallucination?
    - correctness (0.0-1.0 float, binarized >0.5): is the response correct compared to baseline?
"""

import argparse
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx

# ── Load .env file if present (for model auto-detection in docker containers) ──
def _load_dotenv():
    """Load env vars exclusively from docker/.env."""
    candidate = Path(__file__).parent.parent / "docker" / ".env"
    if candidate.exists():
        with open(candidate) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())

_load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
EVAL_DIR = Path(__file__).parent
TEST_CASES_FILE = EVAL_DIR / "test_cases.json"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ── Chat API call ──────────────────────────────────────────────────────────────
def call_chat(
    api_url: str,
    api_key: str,
    user_message: str,
    session_id: str,
    timeout: int = 120,
) -> dict:
    """Call the chat API using streaming and collect type=data SSE events (structured template output).

    type=message events (streaming tokens) are ignored — the canonical output is
    the type=data event emitted at the end of each agent turn, which contains the
    full FE-ready payload (products, stores, quickReplies, etc.).
    """
    url = f"{api_url.rstrip('/')}/tstation/messages/chat"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }
    payload = {
        "content": user_message,
        "session_id": session_id,
        "stream": True,
    }

    start = time.time()
    template_data_list: list[dict] = []
    with httpx.stream("POST", url, json=payload, headers=headers, timeout=timeout) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            line = line.strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]  # Remove "data: " prefix
            if data_str == "[DONE]":
                break
            event = json.loads(data_str)
            # Collect structured template_data (product cards, quickReply, etc.)
            if event.get("type") == "data" and event.get("template"):
                template_data_list.append(event)
    latency = time.time() - start
    return {
        "success": True,
        "template_data": template_data_list,
        "latency_s": round(latency, 3),
    }


# ── Run baseline or experiment ─────────────────────────────────────────────────
def run_responses(api_url: str, api_key: str, run_name: str, model: str = "", limit: int | None = None) -> None:
    """Call chat API for all test cases and save results."""
    test_cases = json.loads(TEST_CASES_FILE.read_text(encoding="utf-8"))
    if limit:
        test_cases = test_cases[:limit]
    output_file = RESULTS_DIR / f"{run_name}.json"

    results = []
    # Load existing results to support resume
    if output_file.exists():
        existing = json.loads(output_file.read_text(encoding="utf-8"))
        done_ids = {r["id"] for r in existing}
        results = existing
        print(f"\n[{run_name.upper()}] Resuming — {len(done_ids)} already done, {len(test_cases) - len(done_ids)} remaining")
    else:
        done_ids = set()
        print(f"\n[{run_name.upper()}] Running {len(test_cases)} test cases against {api_url}")
        if model:
            print(f"             model: {model}")

    for tc in test_cases:
        if tc["id"] in done_ids:
            print(f"  [{tc['id']}] skip (already done)")
            continue
        session_id = f"eval_{run_name}_{tc['id']}_{uuid.uuid4().hex[:6]}"
        print(f"  [{tc['id']}] {tc['user_message'][:50]}... ", end="", flush=True)

        result = call_chat(api_url, api_key, tc["user_message"], session_id)
        td = result.get("template_data", [])
        record = {
            "id": tc["id"],
            "model": model,
            "user_message": tc["user_message"],
            "description": tc.get("description", ""),
            "template_data": td,
            "latency_s": result["latency_s"],
        }
        results.append(record)
        # Write after each case for real-time persistence
        output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        has_data = "✓ data" if td else "✗ no data"
        print(f"✓ latency={result['latency_s']}s  {has_data}")

    # ── Latency summary ─────────────────────────────────────────────────────────
    lats = sorted(r["latency_s"] for r in results if isinstance(r.get("latency_s"), (int, float)))

    def _pct(vals: list[float], p: int) -> float:
        if not vals:
            return 0.0
        idx = int(len(vals) * p / 100)
        return round(vals[min(idx, len(vals) - 1)], 3)

    has_data_count = sum(1 for r in results if r.get("template_data"))
    print(f"\n── {run_name.upper()} SUMMARY ({'n=' + str(len(lats))} cases) ──")
    print(f"  Latency      avg={round(sum(lats)/len(lats),3) if lats else '-'}s  p50={_pct(lats,50)}s  p90={_pct(lats,90)}s  p95={_pct(lats,95)}s")
    print(f"  Structured   {has_data_count}/{len(results)} cases returned template_data")
    print(f"\nSaved to {output_file}")


# ── LLM-as-Judge ───────────────────────────────────────────────────────────────
JUDGE_SYSTEM_PROMPT = """You are an expert evaluator for T-Station AI, a Korean automotive chatbot (Hankook Tire).
Your job is to compare an EXPERIMENT structured output against a BASELINE structured output and score the experiment.

Each output is a JSON array of SSE type=data events:
[{"type": "data", "template": "<template_name>", "data": { ... }}]

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
- faithfulness: Does the experiment avoid hallucination? Are product names, prices, store names, dates accurate?
  1.0 = completely faithful | 0.0 = major hallucinations or wrong facts
- correctness: Does the experiment convey the same correct information as baseline? Same template type? Same key data?
  1.0 = equivalent quality to baseline | 0.0 = completely wrong or missing key info

Return ONLY valid JSON (no markdown, no explanation outside JSON):
{"faithfulness": <float 0.0-1.0>, "correctness": <float 0.0-1.0>, "verdict": "PASS" or "FAIL", "reason": "<2-3 sentences in English: what was correct, what was wrong/hallucinated, what specific data differed>", "insight": "<1 sentence in English: key quality tradeoff for this case>"}

PASS if both faithfulness > 0.5 AND correctness > 0.5. Otherwise FAIL.
If both outputs are empty arrays [], score faithfulness=1.0 correctness=1.0 PASS (both failed equally).
"""

JUDGE_USER_TEMPLATE = """User question: {user_message}

BASELINE output (reference):
{baseline_response}

EXPERIMENT output (to evaluate):
{experiment_response}

Score the EXPERIMENT output."""


def call_judge_llm(
    judge_api_url: str,
    judge_api_key: str,
    user_message: str,
    baseline_response: str,
    experiment_response: str,
) -> dict:
    """Use OpenAI-compatible API directly to judge responses."""
    url = f"{judge_api_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {judge_api_key}",
        "Content-Type": "application/json",
    }
    judge_model = os.environ.get("JUDGE_MODEL", "gpt-5.4-reasoning")
    payload = {
        "model": judge_model,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": JUDGE_USER_TEMPLATE.format(
                    user_message=user_message,
                    baseline_response=baseline_response,
                    experiment_response=experiment_response,
                ),
            },
        ],
        "temperature": 0.0,
        "max_tokens": 512,
    }
    for attempt in range(3):
        resp = httpx.post(url, json=payload, headers=headers, timeout=90)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        # Strip markdown fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip().rstrip("```").strip()
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass
        time.sleep(2)
    # fallback if all attempts fail
    return {"faithfulness": 0.0, "correctness": 0.0, "verdict": "FAIL", "reason": "Judge returned empty/unparseable response.", "insight": "Could not evaluate this case."}


def run_judge(judge_api_url: str, judge_api_key: str, baseline: str = "baseline", experiment: str = "experiment") -> None:
    """Compare baseline vs experiment using LLM-as-judge. Supports checkpoint/resume."""
    baseline_file = RESULTS_DIR / f"{baseline}.json"
    experiment_file = RESULTS_DIR / f"{experiment}.json"
    checkpoint_file = RESULTS_DIR / f"judgment_{baseline}_vs_{experiment}_checkpoint.json"

    if not baseline_file.exists():
        print(f"ERROR: {baseline_file} not found. Run 'responses --run-name {baseline}' first.")
        return
    if not experiment_file.exists():
        print(f"ERROR: {experiment_file} not found. Run 'responses --run-name {experiment}' first.")
        return

    baseline_map = {r["id"]: r for r in json.loads(baseline_file.read_text(encoding="utf-8"))}
    experiment_results = json.loads(experiment_file.read_text(encoding="utf-8"))

    # ── Resume from checkpoint ─────────────────────────────────────────────────
    judgments: list[dict] = []
    done_ids: set[str] = set()
    if checkpoint_file.exists():
        judgments = json.loads(checkpoint_file.read_text(encoding="utf-8"))
        done_ids = {j["id"] for j in judgments}
        print(f"\n[JUDGE] Resuming checkpoint — {len(done_ids)} already judged, {len(experiment_results) - len(done_ids)} remaining")
    else:
        print(f"\n[JUDGE] Evaluating {len(experiment_results)} cases using LLM-as-judge...")

    print(f"        Judge model: {os.environ.get('JUDGE_MODEL', 'openai/gpt-5.4-reasoning')}")

    faith_scores: list[float] = [float(j["judgment"].get("faithfulness", 0.0)) for j in judgments]
    correct_scores: list[float] = [float(j["judgment"].get("correctness", 0.0)) for j in judgments]
    pass_count = sum(1 for j in judgments if j["judgment"].get("verdict") == "PASS")
    total = len(judgments)

    for exp in experiment_results:
        case_id = exp["id"]
        if case_id in done_ids:
            print(f"  [{case_id}] skip (checkpoint)")
            continue
        base = baseline_map.get(case_id)
        if not base:
            print(f"  [{case_id}] SKIP — no baseline found")
            continue

        print(f"  [{case_id}] judging... ", end="", flush=True)
        baseline_td = json.dumps(base.get("template_data", []), ensure_ascii=False)
        experiment_td = json.dumps(exp.get("template_data", []), ensure_ascii=False)
        judgment = call_judge_llm(
            judge_api_url=judge_api_url,
            judge_api_key=judge_api_key,
            user_message=exp["user_message"],
            baseline_response=baseline_td,
            experiment_response=experiment_td,
        )

        f_raw = float(judgment.get("faithfulness", 0.0))
        c_raw = float(judgment.get("correctness", 0.0))
        f_bin = 1 if f_raw > 0.5 else 0
        c_bin = 1 if c_raw > 0.5 else 0
        verdict = "PASS" if f_bin == 1 and c_bin == 1 else "FAIL"
        judgment["faithfulness_bin"] = f_bin
        judgment["correctness_bin"] = c_bin
        judgment["verdict"] = verdict

        lat_diff_pct = None
        if base.get("latency_s") and exp.get("latency_s"):
            lat_diff_pct = round(100 * (exp["latency_s"] - base["latency_s"]) / base["latency_s"], 1)
        wc_diff_pct = None
        if base.get("word_count") and exp.get("word_count"):
            wc_diff_pct = round(100 * (exp["word_count"] - base["word_count"]) / base["word_count"], 1)

        record = {
            "id": exp["id"],
            "model_experiment": exp.get("model", ""),
            "model_baseline": base.get("model", ""),
            "user_message": exp["user_message"],
            "description": exp.get("description", ""),
            "latency_experiment_s": exp.get("latency_s"),
            "latency_baseline_s": base.get("latency_s"),
            "latency_diff_pct": lat_diff_pct,
            "word_count_experiment": exp.get("word_count"),
            "word_count_baseline": base.get("word_count"),
            "word_count_diff_pct": wc_diff_pct,
            "judgment": judgment,
        }
        judgments.append(record)
        done_ids.add(case_id)
        total += 1
        faith_scores.append(f_raw)
        correct_scores.append(c_raw)
        if verdict == "PASS":
            pass_count += 1
        lat_saved = round(base.get("latency_s", 0) - exp.get("latency_s", 0), 2) if base.get("latency_s") and exp.get("latency_s") else None
        lat_info = f"  latency_saved={lat_saved}s" if lat_saved is not None else ""
        print(f"{verdict} (faith={f_raw:.2f}→{f_bin}, correct={c_raw:.2f}→{c_bin}){lat_info}")
        if judgment.get("reason"):
            print(f"    reason : {judgment['reason']}")
        if judgment.get("insight"):
            print(f"    insight: {judgment['insight']}")

        # Write checkpoint after each case
        checkpoint_file.write_text(json.dumps(judgments, ensure_ascii=False, indent=2), encoding="utf-8")

    # Build summary block
    avg_faith = round(sum(faith_scores) / len(faith_scores), 3) if faith_scores else 0.0
    avg_correct = round(sum(correct_scores) / len(correct_scores), 3) if correct_scores else 0.0

    def _pct(vals: list[float], p: int) -> float:
        if not vals:
            return 0.0
        s = sorted(vals)
        idx = int(len(s) * p / 100)
        return round(s[min(idx, len(s) - 1)], 3)

    exp_lats = sorted(j["latency_experiment_s"] for j in judgments if isinstance(j.get("latency_experiment_s"), (int, float)))
    base_lats = sorted(j["latency_baseline_s"] for j in judgments if isinstance(j.get("latency_baseline_s"), (int, float)))
    exp_words = [j["word_count_experiment"] for j in judgments if isinstance(j.get("word_count_experiment"), int)]
    base_words = [j["word_count_baseline"] for j in judgments if isinstance(j.get("word_count_baseline"), int)]

    _ea = round(sum(exp_lats)/len(exp_lats), 3) if exp_lats else None
    _ba = round(sum(base_lats)/len(base_lats), 3) if base_lats else None
    _lat_diff_pct = round(100 * (_ea - _ba) / _ba, 1) if _ea is not None and _ba else None
    _ew = round(sum(exp_words)/len(exp_words), 1) if exp_words else None
    _bw = round(sum(base_words)/len(base_words), 1) if base_words else None
    _wc_diff_pct = round(100 * (_ew - _bw) / _bw, 1) if _ew is not None and _bw else None

    summary = {
        "total_cases": total,
        "pass_count": pass_count,
        "fail_count": total - pass_count,
        "pass_rate_pct": round(100 * pass_count / total, 1) if total else 0.0,
        "avg_faithfulness": avg_faith,
        "avg_correctness": avg_correct,
        "latency_experiment_avg_s": _ea,
        "latency_baseline_avg_s": _ba,
        "latency_diff_pct": _lat_diff_pct,
        "latency_experiment_p50": _pct(exp_lats, 50) if exp_lats else None,
        "latency_experiment_p90": _pct(exp_lats, 90) if exp_lats else None,
        "latency_baseline_p50": _pct(base_lats, 50) if base_lats else None,
        "latency_baseline_p90": _pct(base_lats, 90) if base_lats else None,
        "word_count_experiment_avg": _ew,
        "word_count_baseline_avg": _bw,
        "word_count_diff_pct": _wc_diff_pct,
    }

    # Save final judgment file and remove checkpoint
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    judgment_file = RESULTS_DIR / f"judgment_{baseline}_vs_{experiment}_{timestamp}.json"
    output = {"cases": judgments, "summary": summary}
    judgment_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    if checkpoint_file.exists():
        checkpoint_file.unlink()

    # Print summary table
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"{'ID':<20} {'Faith':>6} {'Correct':>8} {'Verdict':<8} {'Exp(s)':>6} {'Base(s)':>7}")
    print("-" * 60)

    for j in judgments:
        jdg = j.get("judgment", {})
        f_bin = jdg.get("faithfulness_bin", "-")
        c_bin = jdg.get("correctness_bin", "-")
        verdict = jdg.get("verdict", "-")
        exp_lat = j.get("latency_experiment_s", "-")
        base_lat = j.get("latency_baseline_s", "-")
        print(f"{j['id']:<20} {f_bin!s:>6} {c_bin!s:>8} {verdict:<8} {exp_lat!s:>6} {base_lat!s:>7}")

    print("-" * 60)
    print(f"\nOverall: {pass_count}/{total} PASS ({100*pass_count//total if total else 0}%)")
    print(f"         avg_faithfulness={avg_faith:.3f}  avg_correctness={avg_correct:.3f}")

    if exp_lats and base_lats:
        print(f"\n── LATENCY COMPARISON ──")
        print(f"  {'':12} {'avg':>6} {'p50':>6} {'p90':>6} {'p95':>6} {'p99':>6}")
        print(f"  {'experiment':<12} {_ea:>6} {_pct(exp_lats,50):>6} {_pct(exp_lats,90):>6} {_pct(exp_lats,95):>6} {_pct(exp_lats,99):>6}")
        print(f"  {'baseline':<12} {_ba:>6} {_pct(base_lats,50):>6} {_pct(base_lats,90):>6} {_pct(base_lats,95):>6} {_pct(base_lats,99):>6}")
    if exp_words:
        print(f"\n── WORD COUNT ──")
        print(f"  experiment: avg={_ew}  min={min(exp_words)}  max={max(exp_words)}")
        if base_words:
            print(f"  baseline:   avg={_bw}  min={min(base_words)}  max={max(base_words)}")

    # ── INSIGHTS ──────────────────────────────────────────────────────────────
    lat_savings = [
        j["latency_baseline_s"] - j["latency_experiment_s"]
        for j in judgments
        if isinstance(j.get("latency_experiment_s"), (int, float)) and isinstance(j.get("latency_baseline_s"), (int, float))
    ]
    insights_list = [j["judgment"].get("insight", "") for j in judgments if j["judgment"].get("insight")]
    fail_reasons = [
        f"  [{j['id']}] {j['judgment'].get('reason', '')}"
        for j in judgments if j["judgment"].get("verdict") == "FAIL"
    ]

    print(f"\n{'='*60}")
    print("INSIGHTS")
    print(f"{'='*60}")
    if lat_savings:
        avg_saved = round(sum(lat_savings) / len(lat_savings), 2)
        total_saved = round(sum(lat_savings), 2)
        pct_faster = round(100 * avg_saved / (_ba if _ba else 1), 1) if exp_lats and base_lats else 0
        print(f"  ⚡ Latency: experiment is ~{pct_faster}% faster on average")
        print(f"     avg saved per request: {avg_saved}s  |  total saved across {len(lat_savings)} cases: {total_saved}s")
    if pass_count == total:
        print(f"  ✅ All {total} cases PASS — experiment quality matches baseline")
    elif pass_count == 0:
        print(f"  ❌ All {total} cases FAIL — experiment quality significantly below baseline")
    else:
        print(f"  ⚠️  {total - pass_count}/{total} cases FAIL — quality degradation in some cases")
    if fail_reasons:
        print(f"\n  Failure reasons:")
        for r in fail_reasons:
            print(r)
    if insights_list:
        print(f"\n  Per-case insights:")
        for i, (j, ins) in enumerate(zip(judgments, [j["judgment"].get("insight","") for j in judgments])):
            if ins:
                verdict_icon = "✅" if j["judgment"].get("verdict") == "PASS" else "❌"
                print(f"  {verdict_icon} [{j['id']}] {ins}")

    print(f"\nFull results saved to {judgment_file}")


# ── CLI ────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-as-Judge evaluation for tstation-ai")
    subparsers = parser.add_subparsers(dest="command")

    # --- responses subcommand ---
    resp_parser = subparsers.add_parser("responses", help="Collect responses from chat API")
    resp_parser.add_argument("--api-url", default=os.environ.get("EVAL_API_URL", "http://localhost:8000"), help="Chat API base URL")
    resp_parser.add_argument("--api-key", default=os.environ.get("EVAL_API_KEY", ""), help="Chat API key (JWT token)")
    resp_parser.add_argument("--run-name", default="baseline", help="Name for this run (e.g. baseline, exp_gpt54)")
    resp_parser.add_argument("--model", default=os.environ.get("AI_MODEL_REASONING", os.environ.get("AI_MODEL", "")), help="Model name label to embed in results. Defaults to AI_MODEL_REASONING env var.")
    resp_parser.add_argument("--limit", type=int, default=None, help="Max number of test cases to run (default: all)")

    # --- judge subcommand ---
    judge_parser = subparsers.add_parser("judge", help="Run LLM-as-Judge comparison")
    judge_parser.add_argument(
        "--judge-api-url",
        default=os.environ.get("AI_GATEWAY_BASE_URL", "http://localhost:4000/v1"),
        help="OpenAI-compatible base URL for judge LLM",
    )
    judge_parser.add_argument("--judge-api-key", default=os.environ.get("AI_GATEWAY_API_KEY", ""), help="API key for judge LLM (default: AI_GATEWAY_API_KEY env var)")
    judge_parser.add_argument("--baseline", default="baseline", help="Baseline run name (default: baseline)")
    judge_parser.add_argument("--experiment", default="experiment", help="Experiment run name (default: experiment)")

    args = parser.parse_args()

    if args.command == "responses":
        run_responses(api_url=args.api_url, api_key=args.api_key, run_name=args.run_name, model=args.model, limit=args.limit)
    elif args.command == "judge":
        run_judge(
            judge_api_url=args.judge_api_url,
            judge_api_key=args.judge_api_key,
            baseline=args.baseline,
            experiment=args.experiment,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
