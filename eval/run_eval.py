"""
Faithfulness benchmark entrypoint for tstation-ai.

Single-model run:
    python eval/run_eval.py --model-endpoint gpt-5.5-reasoning-low=http://localhost:8000 --limit 14

Multi-model batch run (requires Docker):
    python eval/run_eval_all.py --models gpt-5.5-reasoning-low gpt-5.5-reasoning-high --limit 14
"""

import argparse
import os
import sys
from pathlib import Path

_eval_dir = Path(__file__).parent
if str(_eval_dir) not in sys.path:
    sys.path.insert(0, str(_eval_dir))

from benchmark_runner import run_benchmark
from logging_utils import configure_logging


def _load_dotenv() -> None:
    """Load env vars from docker/.env if present."""
    candidate = _eval_dir.parent / "docker" / ".env"
    if candidate.exists():
        with open(candidate, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Faithfulness benchmark for tstation-ai")
    parser.add_argument(
        "--judge-api-url",
        default=os.environ.get("JUDGE_API_URL", "http://localhost:4000/v1"),
        help="OpenAI-compatible base URL for judge LLM (default: http://localhost:4000/v1 — ai-gateway exposed port)",
    )
    parser.add_argument(
        "--judge-api-key",
        default=os.environ.get("AI_GATEWAY_API_KEY", ""),
        help="API key for judge LLM",
    )
    parser.add_argument(
        "--model-endpoint",
        action="append",
        dest="model_endpoints",
        default=None,
        help=(
            "Model to API mapping in the form model=http://host:port. "
            "Can be repeated for multiple models. "
            "If omitted, reads EVAL_MODEL_NAME and EVAL_API_URL from env."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max number of test cases to run per model (0 = all, default: 5)",
    )
    parser.add_argument(
        "--test-cases-file",
        default=None,
        help="Path to test cases JSON file (default: eval/test_cases_from_excel.json)",
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        default=["discovery_agent", "transaction_agent"],
        metavar="AGENT",
        help="Only run cases handled by these agents (default: discovery_agent transaction_agent). "
             "Choices: discovery_agent transaction_agent support_agent leading_agent. "
             "Pass --agents all to disable filtering.",
    )

    args = parser.parse_args()

    model_endpoints = args.model_endpoints
    if not model_endpoints:
        # Use AI_MODEL as the label (the main model being benchmarked).
        # Fall back to EVAL_MODEL_NAME if set explicitly.
        model_name = (
            os.environ.get("EVAL_MODEL_NAME", "").strip()
            or os.environ.get("AI_MODEL", "").strip()
        )
        api_url = os.environ.get("EVAL_API_URL", "http://tstation-ai:8000").strip()
        if not model_name:
            parser.error(
                "Provide --model-endpoint or set AI_MODEL (or EVAL_MODEL_NAME) in env."
            )
        model_endpoints = [f"{model_name}={api_url}"]

    agents = None if args.agents == ["all"] else args.agents
    run_benchmark(
        model_endpoints=model_endpoints,
        judge_api_url=args.judge_api_url,
        judge_api_key=args.judge_api_key,
        limit=args.limit,
        test_cases_file=args.test_cases_file,
        agents=agents,
    )


if __name__ == "__main__":
    main()
