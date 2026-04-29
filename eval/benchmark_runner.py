import json
import logging

from common import RESULTS_DIR, sanitize_name, resolve_test_cases_file
from response_runner import call_chat, score_faithfulness, summarize_records

logger = logging.getLogger(__name__)


def _run_single_model(
    model: str,
    api_url: str,
    api_key: str,
    judge_api_url: str,
    judge_api_key: str,
    test_cases: list[dict],
) -> dict:
    run_name = f"benchmark_{sanitize_name(model)}"
    output_file = RESULTS_DIR / f"{run_name}.json"

    if output_file.exists():
        records: list[dict] = json.loads(output_file.read_text(encoding="utf-8"))
        done_ids = {record.get("id") for record in records}
        remaining = [tc for tc in test_cases if tc["id"] not in done_ids]
        logger.info(
            "[BENCHMARK] [%s] resume done=%s remaining=%s api=%s",
            model,
            len(done_ids),
            len(remaining),
            api_url,
        )
    else:
        records = []
        remaining = list(test_cases)
        logger.info("[BENCHMARK] [%s] start cases=%s api=%s", model, len(test_cases), api_url)

    for tc in remaining:
        session_id = f"eval_{sanitize_name(model)}_{tc['id']}"
        messages = tc.get("messages") or [tc["user_message"]]
        total_latency_s = 0.0
        final_result = None

        try:
            for message in messages:
                result = call_chat(api_url, jwt_token=api_key, user_message=message, session_id=session_id)
                final_result = result
                total_latency_s += result["latency_s"]

            if final_result is None:
                raise ValueError(f"No final result collected for case {tc['id']}")

            faithfulness_eval = score_faithfulness(
                user_message=tc["user_message"],
                tool_evidence=final_result["tool_evidence"],
                final_response_structured=final_result["final_response_structured"],
                judge_api_url=judge_api_url,
                judge_api_key=judge_api_key,
            )
            record = {
                "id": tc["id"],
                "tc_id": tc.get("tc_id", ""),
                "model": model,
                "user_message": tc["user_message"],
                "messages": messages,
                "category": tc.get("category", ""),
                "description": tc.get("description", ""),
                "tool_evidence": final_result["tool_evidence"],
                "final_response_structured": final_result["final_response_structured"],
                "latency_s": round(total_latency_s, 3),
                "faithfulness_eval": faithfulness_eval,
            }
        except Exception as exc:
            record = {
                "id": tc["id"],
                "tc_id": tc.get("tc_id", ""),
                "model": model,
                "user_message": tc["user_message"],
                "messages": messages,
                "category": tc.get("category", ""),
                "description": tc.get("description", ""),
                "tool_evidence": [],
                "final_response_structured": None,
                "latency_s": round(total_latency_s, 3),
                "faithfulness_eval": {
                    "faithfulness": None,
                    "verdict": "SKIP",
                    "reason": f"Benchmark error: {exc}",
                    "faithfulness_bin": None,
                    "skip": True,
                    "skip_reason": f"Benchmark error: {exc}",
                },
            }

        records.append(record)
        output_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        feval = record["faithfulness_eval"]
        if feval["skip"]:
            logger.info("[BENCHMARK] [%s] [%s] skip reason=%s", model, tc["id"], feval["skip_reason"])
        else:
            logger.info(
                "[BENCHMARK] [%s] [%s] latency=%ss faith=%.2f->%s",
                model,
                tc["id"],
                record["latency_s"],
                float(feval["faithfulness"]),
                feval["faithfulness_bin"],
            )

    summary = summarize_records(records)
    model_output = {
        "model": model,
        "api_url": api_url,
        "result_file": str(output_file),
        "summary": summary,
    }
    logger.info(
        "[BENCHMARK] [%s] done avg_latency=%s avg_faithfulness=%s skipped=%s",
        model,
        summary["avg_latency_s"],
        summary["avg_faithfulness"],
        summary["skip_count"],
    )
    return model_output


def run_benchmark(
    model_endpoints: list[str],
    api_key: str,
    judge_api_url: str,
    judge_api_key: str,
    limit: int = 5,
    test_cases_file: str | None = None,
) -> None:
    """Run faithfulness benchmark for multiple models sequentially."""
    resolved_test_cases_file = resolve_test_cases_file(test_cases_file)
    test_cases = json.loads(resolved_test_cases_file.read_text(encoding="utf-8"))
    test_cases = test_cases[:limit] if limit else test_cases

    parsed_models: list[tuple[str, str]] = []
    for item in model_endpoints:
        model, sep, api_url = item.partition("=")
        if not sep or not model.strip() or not api_url.strip():
            raise ValueError(f"Invalid model endpoint mapping: {item}. Expected model=http://host:port")
        parsed_models.append((model.strip(), api_url.strip()))

    logger.info(
        "[BENCHMARK] models=%s cases=%s test_cases=%s mode=sequential",
        len(parsed_models),
        len(test_cases),
        resolved_test_cases_file,
    )

    summaries: list[dict] = []
    for model, api_url in parsed_models:
        try:
            summaries.append(
                _run_single_model(
                    model=model,
                    api_url=api_url,
                    api_key=api_key,
                    judge_api_url=judge_api_url,
                    judge_api_key=judge_api_key,
                    test_cases=test_cases,
                )
            )
        except Exception as exc:
            logger.exception("[BENCHMARK] [%s] failed: %s", model, exc)
            summaries.append(
                {
                    "model": model,
                    "api_url": api_url,
                    "result_file": None,
                    "summary": {
                        "total_count": len(test_cases),
                        "scored_count": 0,
                        "skip_count": len(test_cases),
                        "avg_latency_s": None,
                        "latency_p50_s": None,
                        "latency_p90_s": None,
                        "latency_p95_s": None,
                        "avg_faithfulness": None,
                        "pass_rate_pct": 0.0,
                        "error": str(exc),
                    },
                }
            )

    summaries.sort(key=lambda item: item["model"])
    summary_output = {
        "test_cases_file": str(resolved_test_cases_file),
        "limit": len(test_cases),
        "mode": "sequential",
        "models": summaries,
    }
    summary_file = RESULTS_DIR / "benchmark_summary.json"
    summary_file.write_text(json.dumps(summary_output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[BENCHMARK] saved_to=%s", summary_file)
