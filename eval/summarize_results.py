#!/usr/bin/env python3
"""
Aggregate all benchmark_*.json result files into a single summary.

Usage:
    python eval/summarize_results.py
    python eval/summarize_results.py --results-dir eval/results
    python eval/summarize_results.py --output eval/results/full_summary.json

    # v1 baseline: all models ranked by Pass% with latency percentiles
    python eval/summarize_results.py --v1

    # Cross-model comparison: group TCs by verdict consistency
    python eval/summarize_results.py --compare
    python eval/summarize_results.py --compare --models gpt-4.1 gpt-4.1-mini gpt-5.1

    # Latency breakdown: LLM% vs Tool% per model with percentiles
    python eval/summarize_results.py --latency
    python eval/summarize_results.py --latency --models gpt-5.2-reasoning o1-low

Output:
    eval/results/full_summary.json  — machine-readable full summary
    Prints a ranked table to stdout (sorted by avg_faithfulness desc)
"""

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_eval_dir = Path(__file__).parent
if str(_eval_dir) not in sys.path:
    sys.path.insert(0, str(_eval_dir))

from common import RESULTS_DIR, percentile as _percentile
from response_runner import summarize_records as _summarize_records

# Files excluded from summary/compare/consistency — reference-only files, not model results.
_SUMMARY_EXCLUDED: frozenset[str] = frozenset({
    "benchmark_summary.json",
    "full_summary.json",
    "benchmark_baseline.json",   # FALLBACK/FAIL reference baseline — not a model comparison result
})


def aggregate(results_dir: Path) -> list[dict]:
    """Load all benchmark_*.json files (excluding reference/summary files) and aggregate."""
    files = sorted(
        f for f in results_dir.glob("benchmark_*.json")
        if f.name not in _SUMMARY_EXCLUDED
    )
    if not files:
        print(f"No benchmark_*.json files found in {results_dir}", file=sys.stderr)
        return []

    rows = []
    for path in files:
        try:
            records: list[dict] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] Could not read {path.name}: {exc}", file=sys.stderr)
            continue

        if not records:
            continue

        model = records[0].get("model", path.stem.removeprefix("benchmark_"))
        summary = _summarize_records(records)
        rows.append({
            "model": model,
            "summary": summary,
        })

    # Sort by avg_faithfulness descending (None last)
    rows.sort(key=lambda x: (x["summary"]["avg_faithfulness"] is None, -(x["summary"]["avg_faithfulness"] or 0)))
    return rows


def _print_table(rows: list[dict]) -> None:
    """Print a ranked comparison table to stdout."""
    if not rows:
        return

    col_model = max(len(r["model"]) for r in rows)
    col_model = max(col_model, 5)

    header = (
        f"{'#':>3}  "
        f"{'Model':<{col_model}}  "
        f"{'Cases':>5}  "
        f"{'Pass%':>6}  "
        f"{'Faith':>6}  "
        f"{'AvgLat':>7}  "
        f"{'P90Lat':>7}  "
        f"{'Routing':>8}  "
        f"{'Think':>7}  "
        f"{'Tools':>7}  "
        f"{'Resp':>7}"
    )
    sep = "-" * len(header)
    print()
    print("=== Benchmark Results (ranked by faithfulness) ===")
    print(sep)
    print(header)
    print(sep)

    for rank, row in enumerate(rows, 1):
        s = row["summary"]
        faith = f"{s['avg_faithfulness']:.4f}" if s["avg_faithfulness"] is not None else "  N/A "
        pass_pct = f"{s['pass_rate_pct']:5.1f}%" if s["pass_rate_pct"] is not None else "  N/A "
        avg_lat = f"{s['avg_latency_s']:6.2f}s" if s["avg_latency_s"] is not None else "   N/A "
        p90_lat = f"{s['latency_p90_s']:6.2f}s" if s["latency_p90_s"] is not None else "   N/A "
        routing = f"{s['avg_routing_s']:6.2f}s" if s.get("avg_routing_s") is not None else "   N/A "
        thinking = f"{s['avg_thinking_s']:5.2f}s" if s.get("avg_thinking_s") is not None else "  N/A "
        tools = f"{s['avg_tool_total_s']:5.2f}s" if s.get("avg_tool_total_s") is not None else "  N/A "
        resp = f"{s['avg_response_s']:5.2f}s" if s.get("avg_response_s") is not None else "  N/A "

        print(
            f"{rank:>3}  "
            f"{row['model']:<{col_model}}  "
            f"{s['total_count']:>5}  "
            f"{pass_pct:>6}  "
            f"{faith:>6}  "
            f"{avg_lat:>7}  "
            f"{p90_lat:>7}  "
            f"{routing:>8}  "
            f"{thinking:>7}  "
            f"{tools:>7}  "
            f"{resp:>7}"
        )

    print(sep)
    print(f"Total models: {len(rows)}")
    print()


def consistency(results_dir: Path, tag: str, models: list[str] | None = None) -> None:
    """Compare baseline run vs tagged re-run for each model, TC by TC.

    For each TC, checks whether the faithfulness verdict (PASS/FAIL) is the same
    across both runs. A flipped verdict signals instability: either the model gave
    a different answer, or the judge scored inconsistently.
    """
    all_files = sorted(
        f for f in results_dir.glob("benchmark_*.json")
        if f.name not in _SUMMARY_EXCLUDED
        and not f.name.startswith("benchmark_summary_")
    )

    baseline: dict[str, dict[str, dict]] = {}
    rerun: dict[str, dict[str, dict]] = {}

    for path in all_files:
        try:
            records: list[dict] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] {path.name}: {exc}", file=sys.stderr)
            continue
        if not records:
            continue
        model = records[0].get("model", "")
        if models and model not in models:
            continue
        record_tag = records[0].get("run_tag", "")
        if record_tag == tag:
            rerun[model] = {r["tc_id"]: r for r in records}
        elif not record_tag:
            baseline[model] = {r["tc_id"]: r for r in records}

    models_with_both = sorted(m for m in baseline if m in rerun)
    if not models_with_both:
        print(f"[ERROR] No models found with both a baseline and a '{tag}' run.", file=sys.stderr)
        print(f"  Baseline models : {sorted(baseline)}", file=sys.stderr)
        print(f"  '{tag}' run models: {sorted(rerun)}", file=sys.stderr)
        return

    overall_consistent = overall_total = 0

    for model in models_with_both:
        run1 = baseline[model]
        run2 = rerun[model]
        common_tcs = sorted(set(run1) & set(run2))

        consistent_pass: list[dict] = []
        consistent_fail: list[dict] = []
        flipped: list[dict] = []

        for tc_id in common_tcs:
            fe1 = run1[tc_id].get("faithfulness_eval") or {}
            fe2 = run2[tc_id].get("faithfulness_eval") or {}
            v1, v2 = fe1.get("verdict", "?"), fe2.get("verdict", "?")
            f1 = fe1.get("faithfulness")
            f2 = fe2.get("faithfulness")
            desc = run1[tc_id].get("description", "")[:42]
            entry = {"tc_id": tc_id, "v1": v1, "v2": v2, "f1": f1, "f2": f2, "desc": desc}
            if v1 == v2 == "PASS":
                consistent_pass.append(entry)
            elif v1 == v2 == "FAIL":
                consistent_fail.append(entry)
            else:
                flipped.append(entry)

        total = len(common_tcs)
        stable = len(consistent_pass) + len(consistent_fail)
        rate = 100 * stable / total if total else 0
        overall_consistent += stable
        overall_total += total

        sep = "-" * 70
        print(f"\n{'=' * 70}")
        print(f"  {model}  —  consistency {rate:.0f}%  ({stable}/{total} TCs stable)")
        print(f"{'=' * 70}")
        print(f"  Stable PASS : {len(consistent_pass):>3}  |  Stable FAIL : {len(consistent_fail):>3}  |  Flipped : {len(flipped):>3}")

        if flipped:
            print(f"\n  {'TC-ID':<10}  {'Baseline':^14}  {'Re-run':^14}  Description")
            print(f"  {sep}")
            for e in flipped:
                f1_s = f"{e['f1']:.2f}" if e["f1"] is not None else " N/A"
                f2_s = f"{e["f2"]:.2f}" if e["f2"] is not None else " N/A"
                col1 = f"{e['v1']}({f1_s})"
                col2 = f"{e['v2']}({f2_s})"
                print(f"  {e['tc_id']:<10}  {col1:^14}  {col2:^14}  {e['desc']}")

        if consistent_fail:
            fail_ids = [e["tc_id"] for e in consistent_fail]
            print(f"\n  Stable FAILs (both runs fail — systemic): {fail_ids}")

    if overall_total:
        overall_rate = 100 * overall_consistent / overall_total
        print(f"\n{'=' * 70}")
        print(f"  OVERALL  consistency {overall_rate:.0f}%  ({overall_consistent}/{overall_total} TCs across {len(models_with_both)} models)")
        print(f"{'=' * 70}")


def latency_breakdown(results_dir: Path, models: list[str] | None = None) -> None:
    """Print LLM vs Tool latency breakdown per model with avg, p50, p90, p95, p99."""
    files = sorted(
        f for f in results_dir.glob("benchmark_*.json")
        if f.name not in _SUMMARY_EXCLUDED
    )

    rows: list[dict] = []
    all_totals: list[float] = []

    for path in files:
        try:
            records: list[dict] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] {path.name}: {exc}", file=sys.stderr)
            continue
        if not records:
            continue
        model = records[0].get("model", path.stem.removeprefix("benchmark_"))
        if models and model not in models:
            continue

        totals, llms, tools = [], [], []
        for r in records:
            t = r.get("timing") or {}
            if not isinstance(t.get("total_s"), (int, float)):
                continue
            total    = t["total_s"]
            routing  = t.get("routing_s") or 0.0
            thinking = t.get("thinking_s") or 0.0
            tool     = t.get("tool_total_s") or 0.0
            response = t.get("response_s") or 0.0
            totals.append(total)
            llms.append(routing + thinking + response)
            tools.append(tool)

        if not totals:
            continue
        all_totals.extend(totals)

        avg_total = sum(totals) / len(totals)
        avg_llm   = sum(llms) / len(llms)
        avg_tool  = sum(tools) / len(tools)
        rows.append({
            "model":      model,
            "n":          len(totals),
            "avg_total":  round(avg_total, 2),
            "avg_llm":    round(avg_llm, 2),
            "avg_tool":   round(avg_tool, 2),
            "llm_pct":    round(avg_llm / avg_total * 100, 1) if avg_total else 0,
            "tool_pct":   round(avg_tool / avg_total * 100, 1) if avg_total else 0,
            "p50":        _percentile(totals, 50),
            "p90":        _percentile(totals, 90),
            "p95":        _percentile(totals, 95),
            "p99":        _percentile(totals, 99),
            "p90_llm":    _percentile(llms, 90),
            "p90_tool":   _percentile(tools, 90),
        })

    if not rows:
        print("No data found.", file=sys.stderr)
        return

    rows.sort(key=lambda x: x["avg_total"])

    # Global line
    if all_totals and not models:
        all_llm  = sum(r["avg_llm"]  * r["n"] for r in rows) / sum(r["n"] for r in rows)
        all_tool = sum(r["avg_tool"] * r["n"] for r in rows) / sum(r["n"] for r in rows)
        avg_glob = sum(all_totals) / len(all_totals)
        print(f"\n{'='*90}")
        print(f"  GLOBAL  ({len(all_totals)} records, {len(rows)} models)")
        print(f"  Avg total = {avg_glob:.2f}s  |  LLM = {all_llm:.2f}s ({all_llm/avg_glob*100:.1f}%)"
              f"  |  Tool = {all_tool:.2f}s ({all_tool/avg_glob*100:.1f}%)"
              f"  |  Overhead = {avg_glob-all_llm-all_tool:.2f}s ({(avg_glob-all_llm-all_tool)/avg_glob*100:.1f}%)")
        print(f"{'='*90}")

    col = max(len(r["model"]) for r in rows)
    header = (
        f"\n  {'Model':<{col}}  {'N':>4}  {'LLM%':>5}  {'Tool%':>5}"
        f"  {'Avg':>6}  {'p50':>6}  {'p90':>6}  {'p95':>6}  {'p99':>7}"
        f"  {'LLMp90':>7}  {'Toolp90':>8}"
    )
    sep = "-" * len(header)
    print(header)
    print(sep)

    for r in rows:
        print(
            f"  {r['model']:<{col}}  {r['n']:>4}  {r['llm_pct']:>5.1f}%  {r['tool_pct']:>5.1f}%"
            f"  {r['avg_total']:>6.2f}s  {r['p50']:>6.2f}s  {r['p90']:>6.2f}s"
            f"  {r['p95']:>6.2f}s  {r['p99']:>7.2f}s"
            f"  {r['p90_llm']:>7.2f}s  {r['p90_tool']:>8.2f}s"
        )

    print(sep)
    print()


def _load_all_records(results_dir: Path) -> dict[str, dict[str, dict]]:
    """Load all benchmark files. Returns {model: {tc_id: record}}."""
    model_records: dict[str, dict[str, dict]] = {}
    files = sorted(
        f for f in results_dir.glob("benchmark_*.json")
        if f.name not in _SUMMARY_EXCLUDED
    )
    for path in files:
        try:
            records: list[dict] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] Could not read {path.name}: {exc}", file=sys.stderr)
            continue
        if not records:
            continue
        model = records[0].get("model", path.stem.removeprefix("benchmark_"))
        model_records[model] = {r["tc_id"]: r for r in records}
    return model_records


def compare(results_dir: Path, models: list[str] | None = None) -> None:
    """Cross-model comparison: group TCs by faithfulness verdict consistency."""
    all_records = _load_all_records(results_dir)

    if models:
        all_records = {m: v for m, v in all_records.items() if m in models}

    if len(all_records) < 2:
        print("Need at least 2 models to compare.", file=sys.stderr)
        return

    model_list = sorted(all_records.keys())

    # TCs present in ALL selected models
    tc_sets = [set(recs.keys()) for recs in all_records.values()]
    common_tcs = sorted(tc_sets[0].intersection(*tc_sets[1:]))
    print(f"\nModels: {', '.join(model_list)}")
    print(f"Common TCs: {len(common_tcs)}")

    # Build per-TC verdict matrix
    consistent_pass: list[dict] = []
    consistent_fail: list[dict] = []
    divergent: list[dict] = []

    for tc_id in common_tcs:
        row: dict = {"tc_id": tc_id}
        verdicts: list[str] = []
        for model in model_list:
            rec = all_records[model][tc_id]
            fe = rec.get("faithfulness_eval") or {}
            verdict = fe.get("verdict", "?")
            score = fe.get("faithfulness")
            ge = rec.get("grounding_eval") or {}
            grnd = ge.get("verdict", "SKIP")
            row[model] = {"verdict": verdict, "score": score, "grounding": grnd}
            verdicts.append(verdict)
        row["description"] = all_records[model_list[0]][tc_id].get("description", "")
        row["category"] = all_records[model_list[0]][tc_id].get("category", "")

        unique = set(verdicts)
        if unique == {"PASS"}:
            consistent_pass.append(row)
        elif unique == {"FAIL"}:
            consistent_fail.append(row)
        else:
            divergent.append(row)

    # Helper: abbreviated model labels
    abbrev = {m: m.replace("gpt-", "").replace("-reasoning", "-r")[:14] for m in model_list}
    col_w = 14
    header_models = "  ".join(f"{abbrev[m]:<{col_w}}" for m in model_list)
    sep = "-" * (8 + 2 + (col_w + 2) * len(model_list) + 44)

    def _print_row(row: dict) -> None:
        cols = "  ".join(
            f"{'P' if row[m]['verdict']=='PASS' else 'F'} {(row[m]['score'] or 0):.2f} "
            f"{'GF' if row[m]['grounding']=='FAIL' else 'G-' if row[m]['grounding']=='SKIP' else 'GP':<3}"
            for m in model_list
        )
        desc = row["description"][:42]
        print(f"{row['tc_id']:<8}  {cols}  {desc}")

    model_header = "  ".join(f"{abbrev[m]:<{col_w}}" for m in model_list)
    col_header = "  ".join(f"{'V  Score  Grnd':<{col_w}}" for _ in model_list)

    def _print_section(title: str, rows: list[dict]) -> None:
        print(f"\n{'='*80}")
        print(f"  {title}")
        print(f"{'='*80}")
        print(f"{'':8}  {model_header}")
        print(f"{'TC-ID':<8}  {col_header}  Description")
        print(sep)
        for row in rows:
            _print_row(row)

    _print_section(
        f"CONSISTENT - ALL PASS  ({len(consistent_pass)} TCs)  <- all models agree: correct",
        consistent_pass,
    )
    _print_section(
        f"CONSISTENT - ALL FAIL  ({len(consistent_fail)} TCs)  <- all models agree: wrong (systemic issue)",
        consistent_fail,
    )
    _print_section(
        f"DIVERGENT  ({len(divergent)} TCs)  <- models disagree -> key analysis target",
        divergent,
    )

    # Summary
    print(f"\n{'-'*50}")
    print(f"  All PASS   : {len(consistent_pass):>3} TCs  ({len(consistent_pass)/len(common_tcs)*100:.0f}%)")
    print(f"  All FAIL   : {len(consistent_fail):>3} TCs  ({len(consistent_fail)/len(common_tcs)*100:.0f}%)")
    print(f"  Divergent  : {len(divergent):>3} TCs  ({len(divergent)/len(common_tcs)*100:.0f}%)")
    print(f"  Total      : {len(common_tcs):>3} TCs")
    print("-" * 50)


def v1_summary(results_dir: Path) -> None:
    """Print clean v1 metrics for all baseline models (non-r2 files only).

    v1 already had 15 outlier TCs removed before the benchmark run,
    so no additional filtering is needed here.
    """
    files = sorted(
        f for f in results_dir.glob("benchmark_*.json")
        if f.name not in _SUMMARY_EXCLUDED and "_r2" not in f.name
    )
    if not files:
        print("No v1 baseline files found.", file=sys.stderr)
        return

    rows = []
    for path in files:
        try:
            records: list[dict] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] {path.name}: {exc}", file=sys.stderr)
            continue
        if not records:
            continue
        model = records[0].get("model", path.stem.removeprefix("benchmark_"))
        s = _summarize_records(records)
        rows.append({"model": model, "summary": s})

    rows.sort(key=lambda x: (-(x["summary"]["pass_rate_pct"] or 0), -(x["summary"]["avg_faithfulness"] or 0)))

    def fmt(v: float | None) -> str:
        return f"{v:>6.2f}s" if v is not None else "   N/A"

    print(f"v1 clean — {len(rows)} baseline models (15 outlier TCs removed before benchmark run)")
    print()
    print(f"{'#':>2}  {'Model':<30}  {'Incl':>5}  {'Pass%':>6}  {'Faith':>6}  {'Avg':>7}  {'p50':>7}  {'p90':>7}  {'p95':>7}  {'p99':>7}")
    print("-" * 102)
    for i, r in enumerate(rows, 1):
        s = r["summary"]
        print(
            f"{i:>2}  {r['model']:<30}  {s['included_count']:>5}"
            f"  {s['pass_rate_pct']:>5.1f}%  {s['avg_faithfulness']:>6.3f}"
            f"  {fmt(s['avg_latency_s'])}  {fmt(s.get('latency_p50_s'))}"
            f"  {fmt(s.get('latency_p90_s'))}  {fmt(s.get('latency_p95_s'))}  {fmt(s.get('latency_p99_s'))}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate all benchmark result files into a summary")
    parser.add_argument(
        "--results-dir",
        default=str(RESULTS_DIR),
        help=f"Directory containing benchmark_*.json files (default: {RESULTS_DIR})",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file path (default: <results-dir>/full_summary.json)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Cross-model comparison: group TCs by faithfulness verdict consistency",
    )
    parser.add_argument(
        "--consistency",
        action="store_true",
        help="Compare baseline run vs tagged re-run to check verdict stability per TC",
    )
    parser.add_argument(
        "--tag",
        default="r2",
        metavar="TAG",
        help="Tag of the re-run to compare against baseline (default: r2). Used with --consistency.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        metavar="MODEL",
        help="Filter models (e.g. gpt-4.1 gpt-4.1-mini). Works with --compare, --consistency, --latency.",
    )
    parser.add_argument(
        "--latency",
        action="store_true",
        help="Print LLM vs Tool latency breakdown per model with avg, p50, p90, p95, p99.",
    )
    parser.add_argument(
        "--v1",
        action="store_true",
        help="Print clean v1 baseline metrics for all models (non-r2 files, outliers pre-removed).",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)

    if args.v1:
        v1_summary(results_dir)
        return

    if args.consistency:
        consistency(results_dir, tag=args.tag, models=args.models)
        return

    if args.compare:
        compare(results_dir, models=args.models)
        return

    if args.latency:
        latency_breakdown(results_dir, models=args.models)
        return

    output_path = Path(args.output) if args.output else results_dir / "full_summary.json"

    rows = aggregate(results_dir)
    if not rows:
        sys.exit(1)

    _print_table(rows)

    out = {
        "total_models": len(rows),
        "models": rows,
    }
    output_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
