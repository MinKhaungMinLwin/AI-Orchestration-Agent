"""
Classifier feedback logging — captures P0 redirect events to Langfuse.

Each P0 redirect in chat.py is a labeled classifier failure:
  code knows classifier said X, but correct answer is Y.

Logging these to Langfuse creates a dataset for:
  1. Tracking P0 redirect rate over time (measure impact of prompt changes)
  2. Identifying the most common failing user_behavior patterns
  3. Finding few-shot examples to add to prompt_router_multi()

Usage in Langfuse dashboard:
  - Filter traces by score name "classifier.redirect"
  - Each score's comment is a JSON object with rule, classifier output, and context
  - Group by "rule" to see P0c vs P0b vs auto-chain breakdown
  - Filter by rule → read user_behavior column → identify prompt improvement patterns

Score schema:
  name  : "classifier.redirect"
  value : 1.0  (binary — redirect happened)
  comment: JSON {
    rule            : "P0c" | "P0b" | "P0_auto_chain" | "post_classification"
    classifier_domains : ["discovery"]          ← what LLM said
    corrected_domains  : ["transaction"]        ← what code corrected to
    user_text          : first 120 chars of user message
    user_behavior      : classifier's free-text behavior field ← key for prompt improvement
    slots              : {goods_no, pending_intent, tire_size, tire_model}
  }
"""

import json
import logging

logger = logging.getLogger(__name__)

SCORE_NAME = "classifier.redirect"


def log_classifier_redirect(
    *,
    trace_id: str | None,
    rule: str,
    classifier_domains: list[str],
    corrected_domains: list[str],
    user_text: str,
    user_behavior: str,
    slots: dict,
) -> None:
    """Log a P0 redirect event to Langfuse as a scored observation.

    Non-blocking — all exceptions are swallowed so this never affects
    the main request path.

    Args:
        trace_id:            Langfuse trace ID for this request.
        rule:                Which P0 gate fired.
                             One of: "P0c", "P0b", "P0_auto_chain", "post_classification"
        classifier_domains:  Domain list the LLM returned (wrong).
        corrected_domains:   Domain list after code correction (correct).
        user_text:           Raw last user message (truncated to 120 chars).
        user_behavior:       The classifier's `user_behavior` field — this is the
                             primary field to analyze when improving the prompt.
                             When a redirect fires with a specific user_behavior,
                             that pair (user_text, user_behavior) → corrected_domains
                             is a ready-made few-shot example.
        slots:               Relevant slot values at redirect time for context.
    """
    # Late import to avoid circular dependency at module load time.
    from config.tracing import tracer, _tracing_enabled

    if not trace_id or not _tracing_enabled:
        return

    try:
        comment = json.dumps(
            {
                "rule": rule,
                "classifier_domains": classifier_domains,
                "corrected_domains": corrected_domains,
                "user_text": user_text[:120],
                "user_behavior": user_behavior[:120] if user_behavior else "",
                "slots": slots,
            },
            ensure_ascii=False,
        )
        tracer.create_score(
            trace_id=trace_id,
            name=SCORE_NAME,
            value=1.0,
            comment=comment,
        )
        logger.debug(
            "[CLASSIFIER_FEEDBACK] Logged %s redirect → corrected=%s",
            rule,
            corrected_domains,
        )
    except Exception as exc:
        logger.debug("[CLASSIFIER_FEEDBACK] Failed to log redirect: %s", exc)
