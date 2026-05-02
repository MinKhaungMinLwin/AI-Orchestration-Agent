#!/usr/bin/env python3
"""
Aggregate all benchmark_*.json result files into a single summary.

Usage:
    python eval/summarize_results.py
    python eval/summarize_results.py --results-dir eval/results
    python eval/summarize_results.py --output eval/results/full_summary.json

Output:
    eval/results/full_summary.json  — machine-readable full summary
    Prints a ranked table to stdout (sorted by avg_faithfulness desc)
"""

import argparse
import json
import sys
from pathlib import Path

_eval_dir = Path(__file__).parent
if str(_eval_dir) not in sys.path:
    sys.path.insert(0, str(_eval_dir))

from common import RESULTS_DIR, percentile


def _summarize_records(records: list[dict]) -> dict:
    """Re-compute summary stats from raw records (same logic as response_runner.summarize_records)."""
    latencies = [r["latency_s"] for r in records if isinstance(r.get("latency_s"), (int, float))]
    faith_scores: list[float] = []
    pass_count = 0
    error_count = 0

    for r in records:
        fe = r.get("faithfulness_eval") or {}
        raw = fe.get("faithfulness")
        verdict = fe.get("verdict", "")
        error = fe.get("error")

        if error:
            error_count += 1
            continue

        try:
            score = float(raw)
            faith_scores.append(score)
            if verdict == "PASS":
                pass_count += 1
        except (TypeError, ValueError):
            error_count += 1

    total = len(records)
    scored = len(faith_scores)

    return {
        "total_count": total,
        "scored_count": scored,
        "error_count": error_count,
        "avg_latency_s": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "latency_p50_s": percentile(latencies, 50),
        "latency_p90_s": percentile(latencies, 90),
        "latency_p95_s": percentile(latencies, 95),
        "latency_p99_s": percentile(latencies, 99),
        "avg_faithfulness": round(sum(faith_scores) / scored, 4) if scored else None,
        "pass_count": pass_count,
        "pass_rate_pct": round(pass_count / scored * 100, 1) if scored else None,
    }


def aggregate(results_dir: Path) -> list[dict]:
    """Load all benchmark_*.json files (excluding benchmark_summary.json) and aggregate."""
    files = sorted(
        f for f in results_dir.glob("benchmark_*.json")
        if f.name != "benchmark_summary.json" and f.name != "full_summary.json"
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
            "result_file": str(path),
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
        f"{'Scored':>6}  "
        f"{'Errors':>6}  "
        f"{'Pass%':>6}  "
        f"{'Faith':>6}  "
        f"{'AvgLat':>7}  "
        f"{'P90Lat':>7}"
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
        errors = s.get("error_count", 0)

        print(
            f"{rank:>3}  "
            f"{row['model']:<{col_model}}  "
            f"{s['total_count']:>5}  "
            f"{s['scored_count']:>6}  "
            f"{errors:>6}  "
            f"{pass_pct:>6}  "
            f"{faith:>6}  "
            f"{avg_lat:>7}  "
            f"{p90_lat:>7}"
        )

    print(sep)
    print(f"Total models: {len(rows)}")
    print()


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
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    output_path = Path(args.output) if args.output else results_dir / "full_summary.json"

    rows = aggregate(results_dir)
    if not rows:
        sys.exit(1)

    _print_table(rows)

    out = {
        "results_dir": str(results_dir),
        "total_models": len(rows),
        "models": rows,
    }
    output_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
