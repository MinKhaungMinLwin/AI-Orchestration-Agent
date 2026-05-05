import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from response_runner import score_answer_relevance, score_faithfulness, score_template_correctness, score_tool_appropriateness

logger = logging.getLogger(__name__)

_METRICS: list[tuple[str, str, str]] = [
    ("faithfulness",        "faith",    "faith"),
    ("answer_relevance",    "relevance","relevance"),
    ("template_correctness","template", "template"),
    ("tool_appropriateness","tools",    "tools"),
]


def _score_runs(fn, runs: int, **kwargs) -> list[dict]:
    """Run a scoring function concurrently `runs` times, return successful results."""
    with ThreadPoolExecutor(max_workers=runs) as ex:
        futures = [ex.submit(fn, **kwargs) for _ in range(runs)]
    for f in futures:
        if f.exception():
            logger.warning("judge run failed: %s", f.exception())
    return [f.result() for f in futures if not f.exception()]


def _aggregate(runs: list[dict], score_key: str) -> tuple[float, str]:
    scores = [float(r[score_key]) for r in runs]
    avg = sum(scores) / len(scores)
    run_lines = "\n".join(f"[run {i + 1}] {r[score_key]:.3f} — {r.get('reason', '')}" for i, r in enumerate(runs))
    return avg, f"avg={avg:.3f} n={len(scores)}\n{run_lines}"


def _judge_one(*, run_item, idx: int, total: int, judge_runs: int, judge_api_url: str, judge_api_key: str, lf) -> dict:
    trace_id = run_item.trace_id
    if not trace_id:
        raise ValueError(f"run_item {idx} has no trace_id")

    trace = lf.api.trace.get(trace_id)
    input_ = trace.input or {}
    output_ = trace.output or {}
    agent = (trace.tags or ["unknown"])[0]
    user_message = input_.get("user_message", "")
    messages: list[str] = input_.get("messages", [])
    tool_evidence = output_.get("tool_evidence", [])
    template_events = output_.get("template_events", [])

    if not user_message:
        raise ValueError(f"trace {trace_id} has no user_message")

    existing_score_names = {s.name for s in (trace.scores or [])}
    if "faith" in existing_score_names:
        logger.info("[JUDGE] [%d/%d] %s [%s] — already scored, skipping", idx, total, trace_id, agent)
        return {}

    logger.info("[JUDGE] [%d/%d] %s [%s] — scoring (%d runs)...", idx, total, trace_id, agent, judge_runs)
    shared = dict(judge_api_url=judge_api_url, judge_api_key=judge_api_key)

    _metric_fns = {
        "faithfulness":         (score_faithfulness,         dict(user_message=user_message, messages=messages, tool_evidence=tool_evidence, template_events=template_events)),
        "answer_relevance":     (score_answer_relevance,     dict(user_message=user_message, messages=messages, template_events=template_events)),
        "template_correctness": (score_template_correctness, dict(user_message=user_message, messages=messages, template_events=template_events)),
        "tool_appropriateness": (score_tool_appropriateness, dict(user_message=user_message, messages=messages, tool_evidence=tool_evidence)),
    }
    with ThreadPoolExecutor(max_workers=len(_metric_fns)) as ex:
        metric_futures = {
            metric: ex.submit(_score_runs, fn, judge_runs, **kwargs, **shared)
            for metric, (fn, kwargs) in _metric_fns.items()
        }
    metric_runs = {metric: f.result() for metric, f in metric_futures.items()}

    results: dict[str, float] = {}
    for metric, log_label, score_name in _METRICS:
        runs = metric_runs[metric]
        if not runs:
            continue
        avg, comment = _aggregate(runs, metric)
        lf.create_score(trace_id=trace_id, name=score_name, value=round(avg, 4), data_type="NUMERIC", comment=comment)
        results[metric] = avg
        logger.info("[JUDGE] [%d/%d] %s  %s=%.3f", idx, total, trace_id, log_label, avg)

    return results


def run_judge(*, run_name: str, dataset_name: str, judge_runs: int = 3, judge_api_url: str, judge_api_key: str, concurrency: int = 1, lf) -> None:
    run = lf.api.datasets.get_run(dataset_name=dataset_name, run_name=run_name)
    run_items = run.dataset_run_items or []
    total_items = len(run_items)

    logger.info(
        "[JUDGE] START  run=%s | dataset=%s | items=%d | judge_runs=%d | concurrency=%d",
        run_name, dataset_name, total_items, judge_runs, concurrency,
    )

    totals: dict[str, list[float]] = {m: [0.0, 0] for m, _, _ in _METRICS}
    errors = skipped = 0

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(_judge_one, run_item=item, idx=idx, total=total_items,
                            judge_runs=judge_runs, judge_api_url=judge_api_url,
                            judge_api_key=judge_api_key, lf=lf): item
            for idx, item in enumerate(run_items, 1)
        }
        for future in as_completed(futures):
            if future.exception():
                logger.error("[JUDGE] item failed: %s", future.exception())
                errors += 1
                continue
            result = future.result()
            if not result:
                skipped += 1
                continue
            for metric, score in result.items():
                totals[metric][0] += score
                totals[metric][1] += 1

    lf.flush()

    scored = total_items - skipped - errors
    logger.info("[JUDGE] DONE   scored=%d skipped=%d errors=%d | Langfuse → Datasets → %s → %s",
                scored, skipped, errors, dataset_name, run_name)
    for metric, (total_score, count) in totals.items():
        avg = total_score / count if count else 0.0
        logger.info("  %-22s avg=%.3f  n=%d", metric, avg, count)
