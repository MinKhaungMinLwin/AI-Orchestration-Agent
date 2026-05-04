import json
import logging
import uuid

from common import AF_TO_AGENT, RESULTS_DIR, SCORED_AGENTS, resolve_test_cases_file, sanitize_name
from judges import check_template_correctness, check_tool_grounding
from response_runner import call_chat, get_jwt_token, score_faithfulness, summarize_records

logger = logging.getLogger(__name__)


def _tc_matches_agents(tc: dict, agents: list[str]) -> bool:
    """Return True if this test case belongs to one of the target agents.

    Supports both excel format (agent_flow → AF_TO_AGENT lookup) and
    manual format (agent field = "discovery" / "transaction" / ...).
    """
    if AF_TO_AGENT.get(tc.get("agent_flow", "")) in agents:
        return True
    return (tc.get("agent", "") + "_agent") in agents


def _run_single_model(model: str, api_url: str, judge_api_url: str, judge_api_key: str, test_cases: list[dict], tag: str = "") -> None:
    suffix = f"_{tag}" if tag else ""
    output_file = RESULTS_DIR / f"benchmark_{sanitize_name(model)}{suffix}.json"
    jwt_token = get_jwt_token()
    run_id = uuid.uuid4().hex[:8]  # unique per run → fresh Redis session, no leftover context

    if output_file.exists():
        records: list[dict] = json.loads(output_file.read_text(encoding="utf-8"))
        done_ids = {r.get("tc_id") for r in records}
        remaining = [tc for tc in test_cases if tc["tc_id"] not in done_ids]
        logger.info(
            "[BENCHMARK] [%s] RESUME  tag=%s | already done=%d | remaining=%d | api=%s | run_id=%s",
            model, tag or "baseline", len(done_ids), len(remaining), api_url, run_id,
        )
    else:
        records, remaining = [], list(test_cases)
        logger.info(
            "[BENCHMARK] [%s] START   tag=%s | total=%d TCs | api=%s | run_id=%s",
            model, tag or "baseline", len(test_cases), api_url, run_id,
        )

    total = len(records) + len(remaining)
    for idx, tc in enumerate(remaining, start=len(records) + 1):
        session_id = f"eval_{run_id}_{sanitize_name(model)}_{tc['tc_id']}"
        user_message = tc["user_message"]

        logger.info("[BENCHMARK] [%s] [%d/%d] %s — calling chatbot...", model, idx, total, tc["tc_id"])
        result = call_chat(api_url, jwt_token=jwt_token, user_message=user_message, session_id=session_id)

        logger.info("[BENCHMARK] [%s] [%d/%d] %s — scoring faithfulness...", model, idx, total, tc["tc_id"])
        faith_eval = score_faithfulness(
            user_message=user_message,
            tool_evidence=result["tool_evidence"],
            template_events=result["template_events"],
            judge_api_url=judge_api_url,
            judge_api_key=judge_api_key,
        )
        template_eval = check_template_correctness(
            tc_agent_flow=tc.get("agent_flow", ""),
            template_events=result["template_events"],
        )
        grounding_eval = check_tool_grounding(
            template_events=result["template_events"],
            tool_evidence=result["tool_evidence"],
        )
        actual_agent = result["actual_agent"]
        record = {
            "tc_id": tc["tc_id"],
            "category": tc.get("category", ""),
            "description": tc.get("description", ""),
            "model": model,
            "run_tag": tag,
            "actual_agent": actual_agent,
            "user_message": user_message,
            "tool_evidence": result["tool_evidence"],
            "template_events": result["template_events"],
            "timing": result["timing"],
            "faithfulness_eval": faith_eval,
            "template_eval": template_eval,
            "grounding_eval": grounding_eval,
        }
        records.append(record)
        output_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

        scored = not actual_agent or actual_agent in SCORED_AGENTS
        agent_label = (actual_agent or "?") + ("" if scored else " [EXCL]")
        logger.info(
            "[BENCHMARK] [%s] [%d/%d] %s ✓  agent=%-28s  total=%5.1fs  faith=%.2f %-4s  template=%-8s  grounding=%s",
            model, idx, total, tc["tc_id"],
            agent_label,
            result["timing"]["total_s"],
            float(faith_eval["faithfulness"]), faith_eval["verdict"],
            template_eval["verdict"], grounding_eval["verdict"],
        )

    summary = summarize_records(records)
    logger.info(
        "[BENCHMARK] [%s] DONE    pass=%d/%d (%.0f%%)  avg_faith=%.3f  avg_latency=%.1fs",
        model, summary["pass_count"], summary["scored_count"],
        summary["pass_rate_pct"] or 0, summary["avg_faithfulness"] or 0, summary["avg_latency_s"] or 0,
    )


def _scored_verdicts_from_records(records: list[dict], eval_key: str) -> dict[str, str]:
    """Extract {tc_id: verdict} for scored agents only from a list of records."""
    return {
        r["tc_id"]: (r.get(eval_key) or {}).get("verdict", "")
        for r in records
        if not r.get("actual_agent") or r["actual_agent"].lower().replace(" ", "_") in SCORED_AGENTS
    }


def _load_baseline_records() -> list[dict] | None:
    """Return records from benchmark_baseline.json if it exists, else None."""
    path = RESULTS_DIR / "benchmark_baseline.json"
    if not path.exists():
        return None
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
        return records if records else None
    except Exception:
        return None


def _get_all_fail_tc_ids() -> set[str]:
    """Return TC ids that have faithfulness FAIL in ALL existing baseline result files (scored agents only).

    If benchmark_baseline.json exists, it is used as the sole reference — no intersection
    across partial model files needed. Otherwise falls back to intersection across all files.
    """
    baseline = _load_baseline_records()
    if baseline is not None:
        verdicts = _scored_verdicts_from_records(baseline, "faithfulness_eval")
        return {tc_id for tc_id, v in verdicts.items() if v == "FAIL"}

    files = [f for f in RESULTS_DIR.glob("benchmark_*.json")
             if f.name not in ("benchmark_summary.json", "full_summary.json", "benchmark_baseline.json")]
    if not files:
        return set()
    model_verdicts: list[dict[str, str]] = []
    for path in files:
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
            if not records or records[0].get("run_tag"):
                continue
            model_verdicts.append(_scored_verdicts_from_records(records, "faithfulness_eval"))
        except Exception:
            continue
    if not model_verdicts:
        return set()
    common_tcs = set(model_verdicts[0]).intersection(*[set(m) for m in model_verdicts[1:]])
    return {tc_id for tc_id in common_tcs if all(m.get(tc_id) == "FAIL" for m in model_verdicts)}


def _get_all_fallback_tc_ids() -> set[str]:
    """Return TC ids where template_eval is FALLBACK in ALL existing baseline result files.

    If benchmark_baseline.json exists, it is used as the sole reference — partial model
    result files do not distort the intersection. Otherwise falls back to intersection.
    """
    baseline = _load_baseline_records()
    if baseline is not None:
        verdicts = _scored_verdicts_from_records(baseline, "template_eval")
        return {tc_id for tc_id, v in verdicts.items() if v == "FALLBACK"}

    files = [f for f in RESULTS_DIR.glob("benchmark_*.json")
             if f.name not in ("benchmark_summary.json", "full_summary.json", "benchmark_baseline.json")]
    if not files:
        return set()
    model_verdicts: list[dict[str, str]] = []
    for path in files:
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
            if not records or records[0].get("run_tag"):
                continue
            model_verdicts.append(_scored_verdicts_from_records(records, "template_eval"))
        except Exception:
            continue
    if not model_verdicts:
        return set()
    common_tcs = set(model_verdicts[0]).intersection(*[set(m) for m in model_verdicts[1:]])
    return {tc_id for tc_id in common_tcs if all(m.get(tc_id) == "FALLBACK" for m in model_verdicts)}


def run_benchmark(
    model_endpoints: list[str],
    judge_api_url: str,
    judge_api_key: str,
    limit: int = 5,
    test_cases_file: str | None = None,
    agents: list[str] | None = None,
    skip_all_fail: bool = False,
    skip_all_fallback: bool = False,
    tag: str = "",
) -> None:
    """Run faithfulness benchmark for multiple models sequentially."""
    resolved = resolve_test_cases_file(test_cases_file)
    test_cases = json.loads(resolved.read_text(encoding="utf-8"))

    # Normalize: support both excel format (tc_id/agent_flow) and manual format (id/agent)
    for tc in test_cases:
        if "tc_id" not in tc:
            tc["tc_id"] = tc.get("id", "")

    # Drop multi-turn cases (eval is single-turn only)
    before = len(test_cases)
    test_cases = [tc for tc in test_cases if len(tc.get("messages") or [tc.get("user_message", "")]) == 1]
    if len(test_cases) < before:
        logger.info("[BENCHMARK] dropped %d multi-turn cases → %d remaining", before - len(test_cases), len(test_cases))

    if agents:
        test_cases = [tc for tc in test_cases if _tc_matches_agents(tc, agents)]
        logger.info("[BENCHMARK] agent filter=%s → %d cases", agents, len(test_cases))

    if skip_all_fail:
        all_fail_ids = _get_all_fail_tc_ids()
        if all_fail_ids:
            test_cases = [tc for tc in test_cases if tc["tc_id"] not in all_fail_ids]
            logger.info("[BENCHMARK] skip-all-fail: removed %d TCs %s → %d remaining", len(all_fail_ids), sorted(all_fail_ids), len(test_cases))

    if skip_all_fallback:
        all_fallback_ids = _get_all_fallback_tc_ids()
        if all_fallback_ids:
            test_cases = [tc for tc in test_cases if tc["tc_id"] not in all_fallback_ids]
            logger.info("[BENCHMARK] skip-all-fallback: removed %d TCs %s → %d remaining", len(all_fallback_ids), sorted(all_fallback_ids), len(test_cases))
        else:
            logger.info("[BENCHMARK] skip-all-fallback: no all-FALLBACK TCs found yet (need baseline run first)")

    if limit > 0:
        test_cases = test_cases[:limit]

    parsed_models: list[tuple[str, str]] = []
    for item in model_endpoints:
        model, sep, api_url = item.partition("=")
        if not sep or not model.strip() or not api_url.strip():
            raise ValueError(f"Invalid model endpoint: {item!r}. Expected model=http://host:port")
        parsed_models.append((model.strip(), api_url.strip()))

    logger.info("[BENCHMARK] ── Starting: %d model(s), %d TCs, file=%s ──", len(parsed_models), len(test_cases), resolved.name)

    for model, api_url in parsed_models:
        _run_single_model(model, api_url, judge_api_url, judge_api_key, test_cases, tag)

    logger.info("[BENCHMARK] ── All done — run `python eval/summarize_results.py` to generate summary ──")
