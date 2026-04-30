"""
Faithfulness benchmark entrypoint for tstation-ai.
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
        "--api-key",
        "--jwt-token",
        dest="api_key",
        default=os.environ.get("EVAL_API_KEY", ""),
        help="JWT Bearer token for chat API",
    )
    parser.add_argument(
        "--judge-api-url",
        default=os.environ.get("AI_GATEWAY_BASE_URL", "http://ai-gateway:8000/v1"),
        help="OpenAI-compatible base URL for judge LLM",
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
        required=True,
        help="Model to API mapping in the form model=http://host:port",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max number of test cases to run per model (default: 5)",
    )
    parser.add_argument(
        "--test-cases-file",
        default=None,
        help="Path to test cases JSON file (default: eval/test_cases_from_excel.json)",
    )

    args = parser.parse_args()

    run_benchmark(
        model_endpoints=args.model_endpoints,
        api_key=args.api_key,
        judge_api_url=args.judge_api_url,
        judge_api_key=args.judge_api_key,
        limit=args.limit,
        test_cases_file=args.test_cases_file,
    )


if __name__ == "__main__":
    main()
