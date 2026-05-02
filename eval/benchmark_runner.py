import json
import logging

from common import AF_TO_AGENT, RESULTS_DIR, resolve_test_cases_file, sanitize_name
from judges import check_template_correctness, check_tool_grounding
from response_runner import call_chat, get_jwt_token, score_faithfulness, summarize_records

logger = logging.getLogger(__name__)


def _run_single_model(model: str, api_url: str, judge_api_url: str, judge_api_key: str, test_cases: list[dict]) -> dict:
    output_file = RESULTS_DIR / f"benchmark_{sanitize_name(model)}.json"
    jwt_token = get_jwt_token()

    if output_file.exists():
        records: list[dict] = json.loads(output_file.read_text(encoding="utf-8"))
        done_ids = {r.get("id") for r in records}
        remaining = [tc for tc in test_cases if tc["id"] not in done_ids]
        logger.info("[BENCHMARK] [%s] resume done=%s remaining=%s api=%s", model, len(done_ids), len(remaining), api_url)
    else:
        records, remaining = [], list(test_cases)
        logger.info("[BENCHMARK] [%s] start cases=%s api=%s", model, len(test_cases), api_url)

    for tc in remaining:
        session_id = f"eval_{sanitize_name(model)}_{tc['id']}"
        messages = tc.get("messages") or [tc["user_message"]]
        assert messages, f"Test case {tc['id']} has no messages"

        total_latency = 0.0
        all_agent_flow_events: list[dict] = []
        all_tool_evidence: list[dict] = []
        final_result: dict = {}

        for msg in messages:
            final_result = call_chat(api_url, jwt_token=jwt_token, user_message=msg, session_id=session_id)
            total_latency += final_result["latency_s"]
            all_agent_flow_events.extend(final_result["agent_flow_events"])
            all_tool_evidence.extend(final_result["tool_evidence"])

        faith_eval = score_faithfulness(
            user_message=tc["user_message"],
            tool_evidence=all_tool_evidence,
            template_events=final_result["template_events"],
            judge_api_url=judge_api_url,
            judge_api_key=judge_api_key,
        )
        template_eval = check_template_correctness(
            tc_agent_flow=tc.get("agent_flow", ""),
            template_events=final_result["template_events"],
        )
        grounding_eval = check_tool_grounding(
            template_events=final_result["template_events"],
            tool_evidence=all_tool_evidence,
        )
        record = {
            **{k: tc.get(k, "") for k in ("id", "tc_id", "category", "description")},
            "model": model,
            "user_message": tc["user_message"],
            "messages": messages,
            "agent_flow_events": all_agent_flow_events,
            "tool_evidence": all_tool_evidence,
            "template_events": final_result["template_events"],
            "latency_s": round(total_latency, 3),
            "timing": final_result.get("timing"),
            "faithfulness_eval": faith_eval,
            "template_eval": template_eval,
            "grounding_eval": grounding_eval,
        }
        records.append(record)
        output_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        fe = faith_eval
        te = template_eval
        ge = grounding_eval
        logger.info(
            "[BENCHMARK] [%s] [%s] latency=%ss faith=%.2f->%s template=%s grounding=%s",
            model, tc["id"], record["latency_s"], float(fe["faithfulness"]), fe["faithfulness_bin"],
            te["verdict"], ge["verdict"],
        )

    summary = summarize_records(records)
    logger.info("[BENCHMARK] [%s] done avg_latency=%s avg_faithfulness=%s", model, summary["avg_latency_s"], summary["avg_faithfulness"])
    return {"model": model, "api_url": api_url, "result_file": str(output_file), "summary": summary}


def run_benchmark(
    model_endpoints: list[str],
    judge_api_url: str,
    judge_api_key: str,
    limit: int = 5,
    test_cases_file: str | None = None,
    agents: list[str] | None = None,
) -> None:
    """Run faithfulness benchmark for multiple models sequentially."""
    resolved = resolve_test_cases_file(test_cases_file)
    test_cases = json.loads(resolved.read_text(encoding="utf-8"))
    if agents:
        test_cases = [tc for tc in test_cases if AF_TO_AGENT.get(tc.get("agent_flow", "")) in agents]
        logger.info("[BENCHMARK] agent filter=%s → %s cases", agents, len(test_cases))
    if limit > 0:
        test_cases = test_cases[:limit]

    parsed_models: list[tuple[str, str]] = []
    for item in model_endpoints:
        model, sep, api_url = item.partition("=")
        if not sep or not model.strip() or not api_url.strip():
            raise ValueError(f"Invalid model endpoint: {item!r}. Expected model=http://host:port")
        parsed_models.append((model.strip(), api_url.strip()))

    logger.info("[BENCHMARK] models=%s cases=%s test_cases=%s", len(parsed_models), len(test_cases), resolved)

    summaries = [_run_single_model(model, api_url, judge_api_url, judge_api_key, test_cases) for model, api_url in parsed_models]
    summaries.sort(key=lambda x: x["model"])

    summary_file = RESULTS_DIR / "benchmark_summary.json"
    summary_file.write_text(
        json.dumps({"test_cases_file": str(resolved), "limit": len(test_cases), "models": summaries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("[BENCHMARK] saved_to=%s", summary_file)
