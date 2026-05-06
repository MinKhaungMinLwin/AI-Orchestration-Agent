import json
import logging
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

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


def _experiment_one(*, item, idx: int, total: int, api_url: str, jwt_token: str, eval_run_id: str, run_name: str, tc_meta: dict, lf) -> tuple[float, str]:
    meta = item.metadata or {}
    tc_id = meta.get("tc_id", str(item.id))
    # JSON file is ground truth for agent; Langfuse metadata can be stale
    agent = tc_meta.get(tc_id, {}).get("agent") or meta.get("agent", "unknown")

    input_ = item.input or {}
    user_message = input_.get("user_message", "")
    messages: list[str] = input_.get("messages") or ([user_message] if user_message else [])

    if not messages:
        raise ValueError(f"{tc_id} has no messages")

    tracing_id = uuid.uuid4().hex
    session_id = uuid.uuid4().hex
    n_turns = len(messages)

    logger.info("[EXP] [%d/%d] %s [%s] — calling chatbot (%d turn%s)...", idx, total, tc_id, agent, n_turns, "s" if n_turns > 1 else "")

    all_tool_evidence: list[dict] = []
    last_template_events: list[dict] = []
    turn_latencies: list[float] = []

    for turn_idx, msg in enumerate(messages, 1):
        # Multi-turn: each turn gets a unique tracing_id so the server processes it as a
        # fresh request. The aggregated eval trace (tracing_id) is created separately below.
        turn_tracing_id = uuid.uuid4().hex if n_turns > 1 else tracing_id
        result = call_chat(
            api_url,
            jwt_token=jwt_token,
            user_message=msg,
            session_id=session_id,
            tracing_id=turn_tracing_id,
        )
        all_tool_evidence.extend(result["tool_evidence"])
        last_template_events = result["template_events"]
        turn_latencies.append(result["total_s"])
        if n_turns > 1:
            logger.info("[EXP] [%d/%d] %s  turn %d/%d — %.1fs", idx, total, tc_id, turn_idx, n_turns, result["total_s"])

    trace_input: dict = {"user_message": user_message}
    if n_turns > 1:
        trace_input["messages"] = messages

    lf.api.ingestion.batch(batch=[
        IngestionEvent_TraceCreate(
            id=uuid.uuid4().hex,
            timestamp=datetime.now(timezone.utc).isoformat(),
            body=TraceBody(
                id=tracing_id,
                input=trace_input,
                output={"tool_evidence": all_tool_evidence, "template_events": last_template_events},
                tags=[agent],
            ),
        )
    ])

    lf.api.dataset_run_items.create(request=CreateDatasetRunItemRequest(
        run_name=run_name,
        dataset_item_id=str(item.id),
        trace_id=tracing_id,
    ))

    last_turn_s = turn_latencies[-1]

    lf.create_score(trace_id=tracing_id, name="latency", value=round(last_turn_s, 3), data_type="NUMERIC")
    if n_turns > 1:
        for i, t in enumerate(turn_latencies, 1):
            lf.create_score(trace_id=tracing_id, name=f"latency.turn_{i}", value=round(t, 3), data_type="NUMERIC")

    if n_turns > 1:
        logger.info("[EXP] [%d/%d] %s [%s] — done (last=%.1fs  total=%.1fs)", idx, total, tc_id, agent, last_turn_s, sum(turn_latencies))
    else:
        logger.info("[EXP] [%d/%d] %s [%s] — done (%.1fs)", idx, total, tc_id, agent, last_turn_s)
    return last_turn_s, agent


def run_experiment(*, api_url: str, run_name: str, dataset_name: str, tc_file: Path, limit: int = 0, concurrency: int = 1, turns: str = "all", lf) -> None:
    tc_meta = {tc["tc_id"]: tc for tc in json.loads(tc_file.read_text(encoding="utf-8")) if tc.get("tc_id")}
    logger.info("[EXP] Loaded %d test cases from %s (ground truth for agent)", len(tc_meta), tc_file.name)

    dataset = lf.get_dataset(dataset_name)
    items = list(reversed(dataset.items))
    items = items[:limit] if limit > 0 else items

    if turns != "all":
        before = len(items)
        items = [
            item for item in items
            if (len((item.input or {}).get("messages", [])) > 1) == (turns == "multi")
        ]
        logger.info("[EXP] Filtered to %s-turn: %d → %d items", turns, before, len(items))

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
                            eval_run_id=eval_run_id, run_name=run_name, tc_meta=tc_meta, lf=lf): item
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
