import logging
import random
from concurrent.futures import ThreadPoolExecutor

from config.env import settings

logger = logging.getLogger(__name__)

# Bounded worker pool — eval is fire-and-forget per request and must not back up
# the API workers. If the queue saturates, submit() will still return immediately
# (the executor queues internally); we cap parallelism to avoid stampeding the
# LLM gateway.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="geval")

_SCORED_DOMAINS = {"leading", "discovery", "transaction", "support"}


def submit_geval(
    *,
    domain: str | None,
    user_query: str,
    draft_response: str,
    source_data: str,
    trace_id: str | None,
    session_id: str | None = None,
) -> None:
    """Enqueue a G-Eval scoring run for the given turn. Returns immediately.

    Silent no-op when disabled, sampled out, missing trace_id, or domain not in
    the scored set. All exceptions inside the worker are swallowed and logged.
    """
    if not settings.AI_GEVAL_ENABLED:
        return
    if not trace_id:
        logger.debug("[GEVAL] Skipping — no trace_id")
        return
    if domain not in _SCORED_DOMAINS:
        logger.debug(f"[GEVAL] Skipping — domain={domain!r} not in scored set")
        return
    if not draft_response or not draft_response.strip():
        return
    if random.random() > settings.AI_GEVAL_SAMPLE_RATE:
        return

    _executor.submit(
        _run_safe,
        domain=domain,
        user_query=user_query,
        draft_response=draft_response,
        source_data=source_data,
        trace_id=trace_id,
        session_id=session_id,
    )


def _run_safe(**kwargs) -> None:
    try:
        _run(**kwargs)
    except Exception as exc:
        logger.exception(f"[GEVAL] Scoring failed: {exc}")


def _run(
    *,
    domain: str,
    user_query: str,
    draft_response: str,
    source_data: str,
    trace_id: str,
    session_id: str | None,
) -> None:
    # Imports deferred so a misconfigured eval path can't break startup.
    from config.tracing import tracer
    from services.tstation.agents.h_eval_agent.agent import score_faithfulness
    from services.tstation.agents.router import EVAL_LLM

    result = score_faithfulness(
        EVAL_LLM,
        user_query=user_query,
        response=draft_response,
        source_data=source_data,
    )
    logger.info(
        f"[GEVAL] domain={domain} trace_id={trace_id} faithfulness={result.score} "
        f"reasoning={result.reasoning[:160]!r}"
    )

    tracer.create_score(
        trace_id=trace_id,
        name="geval.faithfulness",
        value=float(result.score),
        comment=result.reasoning,
        data_type="NUMERIC",
    )
    tracer.create_score(
        trace_id=trace_id,
        name="geval.domain",
        value=str(domain),
        data_type="CATEGORICAL",
    )
