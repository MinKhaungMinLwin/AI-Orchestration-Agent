"""
Faithfulness eval — experiment and judge steps, both backed by Langfuse.

Step 1 — experiment: call chatbot, upload trace input/output, link to dataset run.
Step 2 — judge:      read traces from Langfuse, score faithfulness, upload scores.

Usage:
    # Chạy cả 2 bước (JUDGE_MODEL lấy từ .env)
    python eval/langfuse_eval.py --run-name gpt-5.5-r1

    # Override judge model từ CLI
    python eval/langfuse_eval.py --run-name gpt-5.5-r1 --judge-model gpt-5.5-reasoning-xhigh

    # Chỉ chạy experiment (gọi chatbot, lưu trace)
    python eval/langfuse_eval.py --run-name gpt-5.5-r1 --step experiment

    # Chỉ chạy judge (chấm điểm)
    python eval/langfuse_eval.py --run-name gpt-5.5-r1 --step judge

    # Giới hạn số item, tăng concurrency
    python eval/langfuse_eval.py --run-name gpt-5.5-r1 --concurrency 5 --limit 10
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

_eval_dir = Path(__file__).parent
if str(_eval_dir) not in sys.path:
    sys.path.insert(0, str(_eval_dir))

from common import EVAL_DIR, load_dotenv
from logging_utils import configure_logging
from experiment import run_experiment
from judge import run_judge

logger = logging.getLogger(__name__)

DEFAULT_DATASET_NAME = "tstation-eval"
DEFAULT_FILE = EVAL_DIR / "test_cases_tool_only.json"


def _make_langfuse():
    from langfuse import Langfuse
    return Langfuse(
        host=os.environ.get("LANGFUSE_HOST", "http://localhost:3002"),
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    )


def main() -> None:
    configure_logging()
    load_dotenv()

    _https_port = os.environ.get("HTTPS_PORT", "8001")
    _default_api_url = f"https://localhost:{_https_port}/api"

    parser = argparse.ArgumentParser(description="Faithfulness eval — experiment and judge steps")
    parser.add_argument("--judge-model", default=None, help="Judge model — overrides JUDGE_MODEL env var")
    parser.add_argument("--run-name", required=True, help="Langfuse dataset run name (e.g. gpt-5.5-r1)")
    parser.add_argument(
        "--step",
        choices=["experiment", "judge", "all"],
        default="all",
        help="Which step to run: experiment (call chatbot), judge (score), all (default)",
    )
    parser.add_argument("--dataset", default=DEFAULT_DATASET_NAME, help=f"Langfuse dataset name (default: {DEFAULT_DATASET_NAME})")
    parser.add_argument("--file", default=str(DEFAULT_FILE), help=f"Test cases JSON for ground-truth agent metadata (default: {DEFAULT_FILE.name})")
    parser.add_argument("--api-url", default=os.environ.get("EVAL_API_URL", _default_api_url))
    parser.add_argument("--judge-api-url", default=os.environ.get("JUDGE_API_URL", "http://localhost:4000/v1"))
    parser.add_argument("--judge-api-key", default=os.environ.get("AI_GATEWAY_API_KEY", os.environ.get("OPENAI_API_KEY", "")))
    parser.add_argument("--limit", type=int, default=0, help="Max items to run in experiment step (0 = all)")
    parser.add_argument("--concurrency", type=int, default=1, help="Parallel workers (default: 1)")
    parser.add_argument("--judge-runs", type=int, default=3, help="Judge runs per item, final score = mean (default: 3)")
    args = parser.parse_args()
    if args.judge_model:
        os.environ["JUDGE_MODEL"] = args.judge_model

    chatbot_model = os.environ.get("AI_MODEL_REASONING") or os.environ.get("AI_MODEL", "(unknown)")
    qc_model = os.environ.get("AI_QC_MODEL") or os.environ.get("AI_MODEL_QC_AGENT", "(unknown)")
    logger.info("=" * 60)
    logger.info("EVAL CONFIG   run=%s | step=%s", args.run_name, args.step)
    logger.info("  experiment  api=%s", args.api_url)
    logger.info("  experiment  chatbot=%s  qc=%s", chatbot_model, qc_model)
    logger.info("  judge       model=%s  runs=%d", os.environ.get("JUDGE_MODEL", "(not set)"), args.judge_runs)
    logger.info("  dataset=%-20s concurrency=%d  limit=%s", args.dataset, args.concurrency, args.limit or "all")
    logger.info("=" * 60)

    lf = _make_langfuse()

    if args.step in ("experiment", "all"):
        run_experiment(
            api_url=args.api_url,
            run_name=args.run_name,
            dataset_name=args.dataset,
            tc_file=Path(args.file),
            limit=args.limit,
            concurrency=args.concurrency,
            lf=lf,
        )

    if args.step == "all":
        logger.info("Waiting 10s for Langfuse to index traces (use --step experiment/judge separately for large datasets)...")
        time.sleep(10)

    if args.step in ("judge", "all"):
        run_judge(
            run_name=args.run_name,
            dataset_name=args.dataset,
            judge_runs=args.judge_runs,
            judge_api_url=args.judge_api_url,
            judge_api_key=args.judge_api_key,
            concurrency=args.concurrency,
            lf=lf,
        )


if __name__ == "__main__":
    main()
