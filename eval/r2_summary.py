"""r2 benchmark summary — single entry point for all r2 analysis.

Usage:
    python eval/r2_summary.py                  # full report
    python eval/r2_summary.py --consistency    # consistency table only
    python eval/r2_summary.py --clean          # clean metrics only (outliers removed)
"""
import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_eval_dir = Path(__file__).parent
_results_dir = _eval_dir / "results"

if str(_eval_dir) not in sys.path:
    sys.path.insert(0, str(_eval_dir))

from common import percentile, sanitize_name

MODELS = [
    "gpt-5.1-reasoning",
    "o1-mini",
    "gpt-5.0-reasoning-high",
    "gpt-5.5-reasoning",
    "gpt-5.0-reasoning-minimal",
    "o4-mini-medium",
    "o1-medium",
    "o4-mini-low",
    "gpt-5.2-reasoning-low",
    "gpt-5.2",
]


def load_records(tag: str | None = None) -> dict[str, list[dict]]:
    """Load r2 (or baseline) records for all models."""
    out: dict[str, list[dict]] = {}
    for m in MODELS:
        safe = sanitize_name(m)
        suffix = f"_{tag}" if tag else ""
        f = _results_dir / f"benchmark_{safe}{suffix}.json"
        if f.exists():
            out[m] = json.loads(f.read_text(encoding="utf-8"))
    return out


def compute_threshold(model_records: dict[str, list[dict]]) -> tuple[float, float, float]:
    """Return (mean, std, threshold=mean+2std) across all records."""
    all_lats = [
        r["timing"]["total_s"]
        for recs in model_records.values()
        for r in recs
        if isinstance((r.get("timing") or {}).get("total_s"), (int, float))
    ]
    mean = sum(all_lats) / len(all_lats)
    std = (sum((x - mean) ** 2 for x in all_lats) / len(all_lats)) ** 0.5
    return mean, std, mean + 2 * std


def find_outlier_tcs(model_records: dict[str, list[dict]], threshold: float) -> set[str]:
    return {
        r.get("tc_id", "?")
        for recs in model_records.values()
        for r in recs
        if isinstance((r.get("timing") or {}).get("total_s"), (int, float))
        and r["timing"]["total_s"] > threshold
    }


def model_stats(records: list[dict]) -> dict:
    lats = sorted([r["timing"]["total_s"] for r in records if isinstance((r.get("timing") or {}).get("total_s"), (int, float))])
    faiths = [float(r["faithfulness_eval"]["faithfulness"]) for r in records if r.get("faithfulness_eval", {}).get("faithfulness") is not None]
    passes = sum(1 for r in records if r.get("faithfulness_eval", {}).get("verdict") == "PASS")
    n = len(records)
    return {
        "n": n,
        "pass_pct": round(passes / n * 100, 1) if n else 0,
        "faith": round(sum(faiths) / len(faiths), 3) if faiths else 0,
        "avg": round(sum(lats) / len(lats), 2) if lats else 0,
        "p50": percentile(lats, 50),
        "p90": percentile(lats, 90),
        "p95": percentile(lats, 95),
        "p99": percentile(lats, 99),
    }


def print_stats_table(title: str, rows: list[dict], ranked_by: str = "pass_pct") -> None:
    sorted_rows = sorted(rows, key=lambda x: (-x["stats"][ranked_by], -x["stats"]["faith"]))
    print(f"\n{'='*115}")
    print(f"  {title}")
    print(f"{'='*115}")
    print(f"  {'#':<2}  {'Model':<30}  {'N':>3}  {'Pass%':>6}  {'Faith':>6}  {'Avg':>7}  {'p50':>7}  {'p90':>7}  {'p95':>7}  {'p99':>7}")
    print(f"  {'-'*109}")
    for i, row in enumerate(sorted_rows, 1):
        s = row["stats"]
        print(
            f"  {i:<2}  {row['model']:<30}  {s['n']:>3}  {s['pass_pct']:>5.1f}%"
            f"  {s['faith']:>6.3f}  {s['avg']:>6.2f}s  {s['p50']:>6.2f}s"
            f"  {s['p90']:>6.2f}s  {s['p95']:>6.2f}s  {s['p99']:>6.2f}s"
        )


def print_outlier_section(model_records: dict, threshold: float, outlier_tcs: set[str]) -> None:
    print(f"\n{'='*115}")
    print(f"  OUTLIER ANALYSIS  (threshold: >{threshold:.2f}s = mean+2std)")
    print(f"{'='*115}")

    tc_count: dict[str, tuple[float, str]] = {}
    for m, records in model_records.items():
        outliers = [r for r in records if isinstance((r.get("timing") or {}).get("total_s"), (int, float)) and r["timing"]["total_s"] > threshold]
        if outliers:
            print(f"\n  {m}  ({len(outliers)} outlier(s))")
            for r in sorted(outliers, key=lambda x: x["timing"]["total_s"], reverse=True):
                tc = r.get("tc_id", "?")
                lat = r["timing"]["total_s"]
                desc = r.get("description", "")[:48]
                tc_count.setdefault(tc, (lat, desc))
                tc_count[tc] = (max(tc_count[tc][0], lat), desc)
                print(f"    {tc:<10}  {lat:>6.2f}s  {desc}")

    print(f"\n  Outlier TCs removed globally ({len(outlier_tcs)}): {sorted(outlier_tcs)}")

    cross_model: dict[str, int] = {}
    for m, records in model_records.items():
        for r in records:
            t = (r.get("timing") or {}).get("total_s")
            if isinstance(t, (int, float)) and t > threshold:
                tc = r.get("tc_id", "?")
                cross_model[tc] = cross_model.get(tc, 0) + 1

    multi = [(tc, cnt) for tc, cnt in cross_model.items() if cnt >= 2]
    if multi:
        print(f"\n  Cross-model outliers (appear in 2+ models):")
        for tc, cnt in sorted(multi, key=lambda x: -x[1]):
            desc = tc_count.get(tc, (0, ""))[1]
            print(f"    {tc:<10}  {cnt}/10 models  {desc}")


def print_consistency_section(baseline: dict[str, list[dict]], r2: dict[str, list[dict]]) -> None:
    print(f"\n{'='*115}")
    print(f"  CONSISTENCY  (baseline vs r2, per TC verdict PASS/FAIL)")
    print(f"{'='*115}")
    print(f"\n  {'Model':<30}  {'Consist%':>9}  {'StablePASS':>10}  {'StableFAIL':>10}  {'Flipped':>8}  Systemic FAILs")
    print(f"  {'-'*109}")

    overall_stable = overall_total = 0
    details: list[dict] = []

    for m in MODELS:
        if m not in baseline or m not in r2:
            continue
        run1 = {r["tc_id"]: r for r in baseline[m]}
        run2 = {r["tc_id"]: r for r in r2[m]}
        common = sorted(set(run1) & set(run2))

        stable_pass = stable_fail = flipped = 0
        systemic: list[str] = []
        flip_details: list[dict] = []

        for tc in common:
            v1 = (run1[tc].get("faithfulness_eval") or {}).get("verdict", "?")
            v2 = (run2[tc].get("faithfulness_eval") or {}).get("verdict", "?")
            f1 = (run1[tc].get("faithfulness_eval") or {}).get("faithfulness")
            f2 = (run2[tc].get("faithfulness_eval") or {}).get("faithfulness")
            desc = run1[tc].get("description", "")[:42]
            if v1 == v2 == "PASS":
                stable_pass += 1
            elif v1 == v2 == "FAIL":
                stable_fail += 1
                systemic.append(tc)
            else:
                flipped += 1
                flip_details.append({"tc": tc, "v1": v1, "f1": f1, "v2": v2, "f2": f2, "desc": desc})

        total = len(common)
        stable = stable_pass + stable_fail
        rate = 100 * stable / total if total else 0
        overall_stable += stable
        overall_total += total

        sys_str = ", ".join(systemic) if systemic else "—"
        print(f"  {m:<30}  {rate:>8.0f}%  {stable_pass:>10}  {stable_fail:>10}  {flipped:>8}  {sys_str}")
        details.append({"model": m, "flips": flip_details})

    if overall_total:
        rate = 100 * overall_stable / overall_total
        print(f"  {'-'*109}")
        print(f"  {'OVERALL':<30}  {rate:>8.0f}%  ({overall_stable}/{overall_total} TCs across {len(details)} models)")

    # Print flipped TCs per model
    print()
    for d in details:
        if not d["flips"]:
            continue
        print(f"  Flipped TCs — {d['model']}:")
        for e in d["flips"]:
            f1s = f"{e['f1']:.2f}" if e["f1"] is not None else " N/A"
            f2s = f"{e['f2']:.2f}" if e["f2"] is not None else " N/A"
            print(f"    {e['tc']:<10}  {e['v1']}({f1s}) → {e['v2']}({f2s})  {e['desc']}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="r2 benchmark full analysis")
    parser.add_argument("--consistency", action="store_true", help="Show consistency section only")
    parser.add_argument("--clean", action="store_true", help="Show clean metrics only (outliers removed)")
    args = parser.parse_args()

    r2_records = load_records(tag="r2")
    if not r2_records:
        print("No r2 result files found.", file=sys.stderr)
        sys.exit(1)

    baseline_records = load_records(tag=None)

    mean, std, threshold = compute_threshold(r2_records)
    outlier_tcs = find_outlier_tcs(r2_records, threshold)

    if args.consistency:
        print_consistency_section(baseline_records, r2_records)
        return

    # --- Raw metrics ---
    if not args.clean:
        raw_rows = [{"model": m, "stats": model_stats(recs)} for m, recs in r2_records.items()]
        print_stats_table(f"r2 RAW METRICS  ({next(iter(r2_records.values()), [None]).__len__()} TCs per model, outliers included)", raw_rows)

        print_outlier_section(r2_records, threshold, outlier_tcs)

    # --- Clean metrics ---
    clean_rows = []
    for m, recs in r2_records.items():
        clean = [r for r in recs if r.get("tc_id") not in outlier_tcs]
        clean_rows.append({"model": m, "stats": model_stats(clean)})

    n_clean = len(next(iter(clean_rows), {}).get("stats", {}).get("n", 0) and [])
    sample_n = clean_rows[0]["stats"]["n"] if clean_rows else 0
    print_stats_table(
        f"r2 CLEAN METRICS  ({sample_n} TCs per model, {len(outlier_tcs)} outlier TCs removed globally)",
        clean_rows,
    )

    # --- Consistency ---
    if baseline_records:
        print_consistency_section(baseline_records, r2_records)

    print()


if __name__ == "__main__":
    main()
