"""
Fetch eval results from Langfuse and export to CSV.

Usage:
    python eval/fetch_results.py --run-name gpt-5.5-r1
    python eval/fetch_results.py --run-name gpt-5.5-r1 --output results.csv
    python eval/fetch_results.py --run-name gpt-5.5-r1 --concurrency 5
"""

import argparse
import csv
import json
import logging
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_eval_dir = Path(__file__).parent
if str(_eval_dir) not in sys.path:
    sys.path.insert(0, str(_eval_dir))

from common import EVAL_DIR, load_dotenv
from logging_utils import configure_logging

logger = logging.getLogger(__name__)

DEFAULT_DATASET_NAME = "tstation-eval"
DEFAULT_FILE = EVAL_DIR / "test_cases_tool_only.json"
SUMMARY_METRICS = ["faith", "relevance", "template", "tools"]
META_FIELDS = [
    "tc_id", "agent", "is_multi_turn", "n_turns",
    "user_message", "tool_names", "templates_used",
]


def _load_tc_meta(file: Path) -> dict[str, dict]:
    """Load test cases JSON → dict keyed by tc_id (ground truth for metadata)."""
    cases = json.loads(file.read_text(encoding="utf-8"))
    return {tc["tc_id"]: tc for tc in cases if tc.get("tc_id")}


def _normalize_scores(scores_raw: list) -> dict:
    """Convert all scores to seconds. Fields ending in _ms are divided by 1000 and renamed."""
    result: dict = {}
    for s in scores_raw:
        name: str = s.name
        value: float = s.value
        if name.endswith("_ms"):
            name = name[:-3] + "_s"
            value = round(value / 1000, 3)
        result[name] = value
    return result


def _obs_duration_s(obs) -> float | None:
    """Return span duration in seconds, or None if timestamps are missing."""
    if not obs.start_time or not obs.end_time:
        return None
    return round((obs.end_time - obs.start_time).total_seconds(), 3)


# Span names whose GENERATION children should be excluded from "agent" LLM analysis
_EXCLUDE_SPAN_NAMES = {"classify_multi_intent", "classify_multi_intent_slim", "qc_agent"}


def _extract_span_timings(trace_id: str, lf) -> dict:
    """Fetch Langfuse observations and decompose latency into tools / llm_think / llm_gen.

    Uses temporal ordering instead of parent-child hierarchy because LangGraph nests
    spans multiple levels deep (discovery_agent → agent_node → ChatLiteLLM), so
    direct-children lookup would miss grandchildren.

    Also reads durations from the manual business spans added to the tracing layer:
      "classify"   → latency.classify_s
      "agent:*"    → latency.agents_s  (sum of all matching spans)
      "qc"         → latency.qc_s
    These replace the old create_score() submissions for the same fields. Old traces
    that still carry the score values are overwritten by these when both are present
    (span_timings is applied after scores in _fetch_row_full).
    """
    page = lf.api.observations.get_many(trace_id=trace_id, limit=100)
    obs_list = page.data or []
    if not obs_list:
        return {}

    # Collect IDs of classify / qc spans and their direct children so we can
    # exclude their GENERATION spans from the agent-level think/gen analysis.
    children: dict[str | None, list] = defaultdict(list)
    for obs in obs_list:
        children[obs.parent_observation_id].append(obs)

    excluded_ids: set[str] = set()
    for obs in obs_list:
        if (obs.name or "") in _EXCLUDE_SPAN_NAMES:
            excluded_ids.add(obs.id)
            for child in children.get(obs.id, []):
                excluded_ids.add(child.id)

    # Partition observations
    gen_obs = [o for o in obs_list if (o.type or "").upper() == "GENERATION" and o.start_time and o.end_time]
    tool_obs = [
        o for o in obs_list
        if o.id not in excluded_ids
        and (o.name == "tools" or (o.name or "").endswith("_tool"))
        and o.start_time and o.end_time
    ]
    agent_gen_obs = [o for o in gen_obs if o.id not in excluded_ids]

    result: dict = {}

    llm_total_s = sum(d for o in gen_obs if (d := _obs_duration_s(o)))
    tools_total_s = sum(d for o in tool_obs if (d := _obs_duration_s(o)))

    if llm_total_s:
        result["span.llm_s"] = round(llm_total_s, 3)
    if tools_total_s:
        result["span.tools_s"] = round(tools_total_s, 3)

    if tool_obs and agent_gen_obs:
        first_tool_start = min(o.start_time for o in tool_obs)
        last_tool_end = max((o.end_time for o in tool_obs if o.end_time), default=None)

        pre_gens = [o for o in agent_gen_obs if o.end_time <= first_tool_start]
        post_gens = [o for o in agent_gen_obs if last_tool_end and o.start_time >= last_tool_end]

        think_s = sum(d for o in pre_gens if (d := _obs_duration_s(o)))
        gen_s = sum(d for o in post_gens if (d := _obs_duration_s(o)))
        if think_s:
            result["span.llm_think_s"] = round(think_s, 3)
        if gen_s:
            result["span.llm_gen_s"] = round(gen_s, 3)
    elif agent_gen_obs:
        # No tools called — all agent LLM time is direct response generation
        gen_s = sum(d for o in agent_gen_obs if (d := _obs_duration_s(o)))
        if gen_s:
            result["span.llm_gen_s"] = round(gen_s, 3)

    # --- Business-span durations (replace old create_score submissions) ---
    for obs in obs_list:
        name = obs.name or ""
        dur = _obs_duration_s(obs)
        if dur is None:
            continue
        if name == "classify":
            result["latency.classify_s"] = dur
        elif name == "qc":
            result["latency.qc_s"] = dur
        elif name.startswith("agent:"):
            result["latency.agents_s"] = round(
                result.get("latency.agents_s", 0.0) + dur, 3
            )

    # Derive stream_total from agents + qc when both are available
    if "latency.agents_s" in result and "latency.qc_s" in result:
        result["latency.stream_total_s"] = round(
            result["latency.agents_s"] + result["latency.qc_s"], 3
        )
    elif "latency.agents_s" in result:
        result["latency.stream_total_s"] = result["latency.agents_s"]

    return result


def _fetch_row_full(*, run_item, lf_item_meta: dict, tc_meta: dict, lf) -> dict | None:
    trace_id = run_item.trace_id
    if not trace_id:
        return None

    trace = lf.api.trace.get(trace_id)
    lf_meta = lf_item_meta.get(str(run_item.dataset_item_id), {})

    # Ground truth: JSON file > Langfuse metadata
    tc_id = lf_meta.get("tc_id") or str(run_item.dataset_item_id)
    tc = tc_meta.get(tc_id, {})

    input_ = trace.input or {}
    output_ = trace.output or {}
    messages = input_.get("messages", [])
    scores = _normalize_scores(trace.scores or [])

    tool_evidence: list[dict] = output_.get("tool_evidence", [])
    template_events: list[dict] = output_.get("template_events", [])
    tool_names = ",".join(dict.fromkeys(t.get("tool_name", "") for t in tool_evidence if t.get("tool_name")))
    templates_used = ",".join(dict.fromkeys(e.get("template", "") for e in template_events if e.get("template")))

    span_timings = _extract_span_timings(trace_id, lf)

    row: dict = {
        "tc_id": tc_id,
        "agent": tc.get("agent") or _infer_agent(scores) or (trace.tags or ["unknown"])[0],
        "is_multi_turn": len(messages) > 1,
        "n_turns": len(messages) if messages else 1,
        "user_message": tc.get("user_message") or input_.get("user_message", ""),
        "tool_names": tool_names,
        "templates_used": templates_used,
    }
    row.update(scores)
    row.update(span_timings)
    return row


def _infer_agent(scores: dict) -> str | None:
    for domain in ("discovery", "transaction", "support"):
        if scores.get(f"latency.{domain}") is not None:
            return domain
    return None


def _avg(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _latency_stats(vals: list[float]) -> str:
    if not vals:
        return "no data"
    s = sorted(vals)
    n = len(s)
    def p(pct: int) -> float:
        return s[min(int(n * pct / 100), n - 1)]
    return f"avg={_avg(s):.2f}s  p50={p(50):.2f}s  p90={p(90):.2f}s  p95={p(95):.2f}s  p99={p(99):.2f}s  n={n}"


_LATENCY_STEPS = [
    ("latency",               "total    "),
    ("latency.classify_s",    "classify "),
    ("latency.slots_s",       "slots    "),
    ("latency.agents_s",      "agents   "),
    ("span.tools_s",          "  tools  "),
    ("span.llm_think_s",      "  llm_think"),
    ("span.llm_gen_s",        "  llm_gen"),
    ("span.llm_s",            "  llm_all"),
    ("latency.qc_s",          "qc       "),
    ("latency.stream_total_s","stream   "),
]


def _print_summary(rows: list[dict], run_name: str) -> None:
    sep = "=" * 60
    logger.info(sep)
    logger.info("RESULTS   run=%s  n=%d items", run_name, len(rows))
    logger.info("")

    logger.info("Overall:")
    for field in SUMMARY_METRICS:
        vals = [r[field] for r in rows if r.get(field) is not None]
        if vals:
            logger.info("  %-10s avg=%.3f  min=%.3f  max=%.3f  n=%d", field, _avg(vals), min(vals), max(vals), len(vals))

    logger.info("")
    logger.info("By agent:")
    for agent in sorted({r["agent"] for r in rows}):
        ar = [r for r in rows if r["agent"] == agent]
        logger.info(
            "  %-14s n=%-3d  faith=%.3f  relevance=%.3f  template=%.3f  tools=%.3f  latency=%.1fs",
            agent, len(ar),
            _avg([r["faith"] for r in ar if r.get("faith") is not None]),
            _avg([r["relevance"] for r in ar if r.get("relevance") is not None]),
            _avg([r["template"] for r in ar if r.get("template") is not None]),
            _avg([r["tools"] for r in ar if r.get("tools") is not None]),
            _avg([r["latency"] for r in ar if r.get("latency") is not None]),
        )

    single = [r for r in rows if not r["is_multi_turn"]]
    multi = [r for r in rows if r["is_multi_turn"]]
    if multi:
        logger.info("")
        logger.info("Single-turn vs multi-turn:")
        for label, subset in [("single", single), ("multi", multi)]:
            if not subset:
                continue
            logger.info(
                "  %-8s n=%-3d  faith=%.3f  relevance=%.3f  latency=%.1fs",
                label, len(subset),
                _avg([r["faith"] for r in subset if r.get("faith") is not None]),
                _avg([r["relevance"] for r in subset if r.get("relevance") is not None]),
                _avg([r["latency"] for r in subset if r.get("latency") is not None]),
            )

    logger.info("")
    logger.info("Latency by step:")
    for field, label in _LATENCY_STEPS:
        vals = [r[field] for r in rows if r.get(field) is not None]
        if vals:
            logger.info("  %s  %s", label, _latency_stats(vals))

    scored = [r for r in rows if r.get("faith") is not None]
    if scored:
        logger.info("")
        logger.info("Lowest faith scores:")
        for r in sorted(scored, key=lambda x: x["faith"])[:5]:
            logger.info("  %-10s [%-12s] faith=%.3f  %s", r["tc_id"], r["agent"], r["faith"], r["user_message"][:60])

    logger.info(sep)


def fetch_results(*, dataset_name: str, run_name: str, output: Path, concurrency: int, tc_file: Path, lf) -> None:
    tc_meta = _load_tc_meta(tc_file)
    logger.info("Loaded %d test cases from %s", len(tc_meta), tc_file.name)

    dataset = lf.get_dataset(dataset_name)
    lf_item_meta = {str(item.id): item.metadata or {} for item in dataset.items}
    logger.info("Dataset '%s': %d items in Langfuse", dataset_name, len(lf_item_meta))

    run = lf.api.datasets.get_run(dataset_name=dataset_name, run_name=run_name)
    run_items = run.dataset_run_items or []
    total = len(run_items)
    logger.info("Run '%s': %d items", run_name, total)

    if not run_items:
        logger.warning("No items in run '%s'", run_name)
        return

    rows: list[dict] = []
    errors = 0

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(_fetch_row_full, run_item=item, lf_item_meta=lf_item_meta, tc_meta=tc_meta, lf=lf): item
            for item in run_items
        }
        for i, future in enumerate(as_completed(futures), 1):
            if future.exception():
                logger.error("[%d/%d] failed: %s", i, total, future.exception())
                errors += 1
            else:
                row = future.result()
                if row:
                    rows.append(row)

    if not rows:
        logger.warning("No rows to export")
        return

    rows.sort(key=lambda r: r["tc_id"])

    all_extra = {k for r in rows for k in r if k not in META_FIELDS}
    latency_cols = sorted(k for k in all_extra if k not in set(SUMMARY_METRICS))
    eval_cols = [k for k in SUMMARY_METRICS if k in all_extra]
    fieldnames = META_FIELDS + latency_cols + eval_cols

    with open(output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Exported %d rows → %s (errors=%d)", len(rows), output, errors)
    _print_summary(rows, run_name)


def main() -> None:
    configure_logging()
    load_dotenv()

    parser = argparse.ArgumentParser(description="Fetch eval results from Langfuse and export to CSV")
    parser.add_argument("--run-name", required=True, help="Langfuse dataset run name")
    parser.add_argument("--dataset", default=DEFAULT_DATASET_NAME)
    parser.add_argument("--file", default=str(DEFAULT_FILE), help=f"Test cases JSON for ground-truth metadata (default: {DEFAULT_FILE.name})")
    parser.add_argument("--output", default=None, help="CSV output path (default: eval/results_<run-name>.csv)")
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    output = Path(args.output) if args.output else EVAL_DIR / f"results_{args.run_name}.csv"

    from langfuse import Langfuse
    lf = Langfuse(
        host=os.environ.get("LANGFUSE_HOST", "http://localhost:3002"),
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    )

    fetch_results(
        dataset_name=args.dataset,
        run_name=args.run_name,
        output=output,
        concurrency=args.concurrency,
        tc_file=Path(args.file),
        lf=lf,
    )


if __name__ == "__main__":
    main()
