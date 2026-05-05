import logging
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from langfuse.api import IngestionEvent_TraceCreate, TraceBody
from langfuse.api.resources.dataset_run_items.types.create_dataset_run_item_request import CreateDatasetRunItemRequest

from response_runner import call_chat, get_jwt_token

logger = logging.getLogger(__name__)


def _existing_run_item_ids(lf, dataset_name: str, run_name: str) -> set[str]:
    """Return dataset_item_ids already linked to this run (empty set if run doesn't exist yet)."""
    all_runs = lf.api.datasets.get_runs(dataset_name=dataset_name)
    if run_name not in {r.name for r in (all_runs.data or [])}:
        return set()
    run = lf.api.datasets.get_run(dataset_name=dataset_name, run_name=run_name)
    return {str(ri.dataset_item_id) for ri in (run.dataset_run_items or [])}


def _latency_stats(latencies: list[float]) -> str:
    if not latencies:
        return "no data"
    s = sorted(latencies)
    n = len(s)

    def p(pct: int) -> float:
        return s[min(int(n * pct / 100), n - 1)]

    avg = sum(s) / n
    return f"avg={avg:.1f}s  p50={p(50):.1f}s  p90={p(90):.1f}s  p95={p(95):.1f}s  p99={p(99):.1f}s"


def _experiment_one(*, item, idx: int, total: int, api_url: str, jwt_token: str, eval_run_id: str, run_name: str, lf) -> tuple[float, str]:
    meta = item.metadata or {}
    tc_id = meta.get("tc_id", str(item.id))
    agent = meta.get("agent", "unknown")
    user_message = (item.input or {}).get("user_message", "")

    if not user_message:
        raise ValueError(f"{tc_id} has no user_message")

    tracing_id = uuid.uuid4().hex
    logger.info("[EXP] [%d/%d] %s [%s] — calling chatbot...", idx, total, tc_id, agent)

    result = call_chat(
        api_url,
        jwt_token=jwt_token,
        user_message=user_message,
        session_id=f"eval_{eval_run_id}_{tc_id}",
        tracing_id=tracing_id,
    )

    lf.api.ingestion.batch(batch=[
        IngestionEvent_TraceCreate(
            id=uuid.uuid4().hex,
            timestamp=datetime.now(timezone.utc).isoformat(),
            body=TraceBody(
                id=tracing_id,
                input={"user_message": user_message},
                output={"tool_evidence": result["tool_evidence"], "template_events": result["template_events"]},
                tags=[agent],
            ),
        )
    ])

    lf.api.dataset_run_items.create(request=CreateDatasetRunItemRequest(
        run_name=run_name,
        dataset_item_id=str(item.id),
        trace_id=tracing_id,
    ))

    lf.create_score(trace_id=tracing_id, name="latency", value=result["total_s"], data_type="NUMERIC")
    lf.create_score(trace_id=tracing_id, name=f"latency.{agent}", value=result["total_s"], data_type="NUMERIC")

    logger.info("[EXP] [%d/%d] %s [%s] — done (%.1fs)", idx, total, tc_id, agent, result["total_s"])
    return result["total_s"], agent


def run_experiment(*, api_url: str, run_name: str, dataset_name: str, limit: int = 0, concurrency: int = 1, lf) -> None:
    dataset = lf.get_dataset(dataset_name)
    items = dataset.items[:limit] if limit > 0 else dataset.items

    existing_ids = _existing_run_item_ids(lf, dataset_name, run_name)
    if existing_ids:
        logger.info("[EXP] Skipping %d already-run items in run '%s'", len(existing_ids), run_name)
    items = [item for item in items if str(item.id) not in existing_ids]

    jwt_token = get_jwt_token()
    eval_run_id = uuid.uuid4().hex[:8]
    total_items = len(items)

    if total_items == 0:
        logger.info("[EXP] Nothing to run — all items already completed for run '%s'", run_name)
        return

    logger.info(
        "[EXP] START  run=%s | dataset=%s | items=%d | concurrency=%d | run_id=%s",
        run_name, dataset_name, total_items, concurrency, eval_run_id,
    )

    per_agent: defaultdict[str, list[float]] = defaultdict(list)
    errors = 0

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(_experiment_one, item=item, idx=idx, total=total_items,
                            api_url=api_url, jwt_token=jwt_token,
                            eval_run_id=eval_run_id, run_name=run_name, lf=lf): item
            for idx, item in enumerate(items, 1)
        }
        for future in as_completed(futures):
            if future.exception():
                logger.error("[EXP] item failed: %s", future.exception())
                errors += 1
            else:
                latency, agent = future.result()
                per_agent[agent].append(latency)

    lf.flush()

    total_done = sum(len(v) for v in per_agent.values())
    logger.info("[EXP] DONE   done=%d errors=%d", total_done, errors)
    for agent, latencies in sorted(per_agent.items()):
        logger.info("  %-12s (%2d): %s", agent, len(latencies), _latency_stats(latencies))
