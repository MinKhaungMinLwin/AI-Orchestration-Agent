"""
Batch eval runner — runs faithfulness benchmark for multiple models sequentially.

How it works:
  1. For each model in --models list:
     a. Update AI_MODEL in docker/.env
     b. Restart tstation-ai service via docker compose
     c. Wait for service to be healthy (via docker exec inside container)
     d. Run eval (calls run_eval.py logic directly)
  2. Print comparison summary at the end.

Architecture note:
  tstation-ai uses `expose: 8000` (not `ports`) so it is NOT accessible at
  localhost:8000 from the host.  The nginx proxy exposes:
    - HTTP  → https://localhost:${HTTPS_PORT}/api   (default HTTPS_PORT=8001)
  All eval API calls go through nginx with SSL verification disabled
  (self-signed cert).  Health checks run via `docker exec` inside the container.

Usage:
    # Run specific models
    python eval/run_eval_all.py \\
        --models gpt-5.5-reasoning-low gpt-5.5-reasoning-high o3-high \\
        --limit 14

    # Run all models defined in ALL_MODELS list below
    python eval/run_eval_all.py --all --limit 14

    # Dry run (no restart, assumes service already running with correct model)
    python eval/run_eval_all.py --models gpt-5.5-reasoning-low --limit 5 --no-restart

Requirements:
    - Docker must be running with the tstation-agent stack
    - docker/.env must exist with HTTPS_PORT set (default 8001)
    - EVAL_JWT_TOKEN must be set in docker/.env
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

_eval_dir = Path(__file__).parent
_root_dir = _eval_dir.parent
_docker_env_path = _root_dir / "docker" / ".env"
_docker_compose_path = _root_dir / "docker" / "docker-compose.yml"

if str(_eval_dir) not in sys.path:
    sys.path.insert(0, str(_eval_dir))

from benchmark_runner import run_benchmark
from common import RESULTS_DIR
from logging_utils import configure_logging

logger = logging.getLogger(__name__)


def _load_env_into_os() -> None:
    """Load docker/.env into os.environ (setdefault — won't override existing vars)."""
    if _docker_env_path.exists():
        with open(_docker_env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


_load_env_into_os()

# All available models in conf-gateway.yaml (newest → oldest)
# Edit this list to control which models are included in --all
ALL_MODELS = [
    # GPT-5.5 (23/04/2026)
    "gpt-5.5-reasoning-xhigh",
    "gpt-5.5-reasoning-high",
    "gpt-5.5-reasoning",
    "gpt-5.5-reasoning-low",
    "gpt-5.5-reasoning-none",
    "gpt-5.5",
    # GPT-5.4 (05/03/2026)
    "gpt-5.4-reasoning-high",
    "gpt-5.4-reasoning",
    "gpt-5.4-reasoning-low",
    "gpt-5.4-reasoning-minimal",
    "gpt-5.4",
    # GPT-5.2 (11/12/2025)
    "gpt-5.2-reasoning-high",
    "gpt-5.2-reasoning",
    "gpt-5.2-reasoning-low",
    "gpt-5.2-reasoning-minimal",
    "gpt-5.2",
    # GPT-5.1 (11/2025)
    "gpt-5.1-reasoning-high",
    "gpt-5.1-reasoning",
    "gpt-5.1-reasoning-low",
    "gpt-5.1-reasoning-minimal",
    "gpt-5.1",
    # GPT-5.0 (08/2025)
    "gpt-5.0-reasoning-high",
    "gpt-5.0-reasoning",
    "gpt-5.0-reasoning-low",
    "gpt-5.0-reasoning-minimal",
    "gpt-5.0",
    # o4-mini (04/2025)
    "o4-mini-high",
    "o4-mini-medium",
    "o4-mini-low",
    # o3 (04/2025)
    "o3-high",
    "o3-medium",
    "o3-low",
    # GPT-4.1 (14/04/2025)
    "gpt-4.1",
    "gpt-4.1-mini",
    # GPT-4.5 (02/2025)
    "gpt-4.5",
    # o3-mini (31/01/2025)
    "o3-mini-high",
    "o3-mini-medium",
    "o3-mini-low",
    # o1 (12/2024)
    "o1-high",
    "o1-medium",
    "o1-low",
    # o1-preview / o1-mini (09/2024)
    "o1-preview",
    "o1-mini",
    # GPT-4o mini (07/2024)
    "gpt-4o-mini",
    # GPT-4o (05/2024)
    "gpt-4o",
]


def _load_dotenv() -> dict[str, str]:
    """Load docker/.env into a dict."""
    env: dict[str, str] = {}
    if _docker_env_path.exists():
        with open(_docker_env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    return env


def _set_ai_model(model: str) -> None:
    """Update AI_MODEL= line in docker/.env."""
    if not _docker_env_path.exists():
        raise FileNotFoundError(f"docker/.env not found at {_docker_env_path}")

    content = _docker_env_path.read_text(encoding="utf-8")
    new_content = re.sub(
        r"^(AI_MODEL\s*=\s*).*$",
        f"AI_MODEL={model}",
        content,
        flags=re.MULTILINE,
    )
    if new_content == content and f"AI_MODEL={model}" not in content:
        # Line doesn't exist, append it
        new_content = content.rstrip() + f"\nAI_MODEL={model}\n"

    _docker_env_path.write_text(new_content, encoding="utf-8")
    logger.info("[BATCH] Set AI_MODEL=%s in docker/.env", model)


def _restart_service(service_name: str = "tstation-ai") -> None:
    """Restart docker compose service."""
    cmd = [
        "docker", "compose",
        "-f", str(_docker_compose_path),
        "restart", service_name,
    ]
    logger.info("[BATCH] Restarting service: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_root_dir))
    if result.returncode != 0:
        logger.error("[BATCH] Restart failed: %s", result.stderr)
        raise RuntimeError(f"docker compose restart failed: {result.stderr}")
    logger.info("[BATCH] Service restarted")


def _get_container_name(service_name: str = "tstation-ai") -> str:
    """Resolve the running container name for a docker compose service."""
    cmd = [
        "docker", "compose",
        "-f", str(_docker_compose_path),
        "ps", "--format", "{{.Name}}", service_name,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_root_dir))
    name = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    return name or f"docker-{service_name}-1"  # fallback to default compose naming


def _wait_for_health(service_name: str = "tstation-ai", timeout: int = 60, interval: int = 3) -> None:
    """Poll /health inside the container via docker exec (avoids host-port exposure issue)."""
    container = _get_container_name(service_name)
    deadline = time.time() + timeout
    logger.info("[BATCH] Waiting for container %s to be healthy ...", container)
    while time.time() < deadline:
        result = subprocess.run(
            ["docker", "exec", container, "curl", "-fs", "http://localhost:8000/health"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info("[BATCH] Service is healthy")
            return
        time.sleep(interval)
    raise TimeoutError(f"Service not healthy after {timeout}s (container: {container})")


def _print_comparison(models: list[str]) -> None:
    """Print a comparison table of all completed model results."""
    rows = []
    for model in models:
        from common import sanitize_name
        result_file = RESULTS_DIR / f"benchmark_{sanitize_name(model)}.json"
        if not result_file.exists():
            continue
        records = json.loads(result_file.read_text(encoding="utf-8"))
        if not records:
            continue
        faithfulness_scores = [
            float(r["faithfulness_eval"]["faithfulness"])
            for r in records
            if r.get("faithfulness_eval", {}).get("faithfulness") is not None
        ]
        latencies = [r["latency_s"] for r in records if r.get("latency_s")]
        pass_count = sum(1 for r in records if r.get("faithfulness_eval", {}).get("verdict") == "PASS")
        avg_faith = sum(faithfulness_scores) / len(faithfulness_scores) if faithfulness_scores else 0
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        rows.append({
            "model": model,
            "cases": len(records),
            "pass": pass_count,
            "pass_rate": f"{pass_count/len(records)*100:.0f}%" if records else "—",
            "avg_faith": f"{avg_faith:.2f}",
            "avg_lat": f"{avg_lat:.1f}s",
        })

    if not rows:
        return

    print("\n" + "=" * 70)
    print("BENCHMARK COMPARISON SUMMARY")
    print("=" * 70)
    print(f"{'Model':<35} {'Cases':>5} {'PASS':>5} {'Rate':>6} {'Faith':>6} {'Latency':>8}")
    print("-" * 70)
    for r in rows:
        print(f"{r['model']:<35} {r['cases']:>5} {r['pass']:>5} {r['pass_rate']:>6} {r['avg_faith']:>6} {r['avg_lat']:>8}")
    print("=" * 70)


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="Batch faithfulness benchmark — runs eval for multiple models sequentially",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--models",
        nargs="+",
        metavar="MODEL",
        help="Model aliases to test (e.g. gpt-5.5-reasoning-low o3-high)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all models defined in ALL_MODELS list",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=14,
        help="Max test cases per model (0 = all, default: 14)",
    )
    # Derive default HTTPS port from docker/.env (HTTPS_PORT=8001)
    _env_vars = _load_dotenv()
    _https_port = _env_vars.get("HTTPS_PORT", "8001")
    _default_api_url = f"https://localhost:{_https_port}/api"

    parser.add_argument(
        "--api-url",
        default=os.environ.get("EVAL_API_URL", _default_api_url),
        help=f"tstation-ai service URL via nginx (default: {_default_api_url})",
    )
    parser.add_argument(
        "--judge-api-url",
        default=os.environ.get("JUDGE_API_URL", "http://localhost:4000/v1"),
        help="OpenAI-compatible base URL for judge LLM (default: http://localhost:4000/v1 — ai-gateway exposed port)",
    )
    parser.add_argument(
        "--judge-api-key",
        default=os.environ.get("JUDGE_API_KEY", os.environ.get("AI_GATEWAY_API_KEY", os.environ.get("OPENAI_API_KEY", ""))),
        help="API key for judge LLM (reads JUDGE_API_KEY, AI_GATEWAY_API_KEY, or OPENAI_API_KEY from env; prefers AI_GATEWAY_API_KEY since judge calls local gateway)",
    )
    parser.add_argument(
        "--test-cases-file",
        default=None,
        help="Path to test cases JSON file",
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
    parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Skip docker compose restart (assume service already running with correct model)",
    )
    parser.add_argument(
        "--service-name",
        default="tstation-ai",
        help="Docker compose service name to restart (default: tstation-ai)",
    )
    parser.add_argument(
        "--health-timeout",
        type=int,
        default=60,
        help="Seconds to wait for service health after restart (default: 60)",
    )

    args = parser.parse_args()

    if args.all:
        models = ALL_MODELS
    elif args.models:
        models = args.models
    else:
        parser.error("Provide --models MODEL [MODEL ...] or --all")

    logger.info("[BATCH] Starting batch eval: %d models, limit=%d", len(models), args.limit)

    completed = []
    failed = []

    for i, model in enumerate(models, 1):
        logger.info("[BATCH] ── Model %d/%d: %s ──", i, len(models), model)

        try:
            if not args.no_restart:
                _set_ai_model(model)
                _restart_service(args.service_name)
                _wait_for_health(args.service_name, timeout=args.health_timeout)
            else:
                logger.info("[BATCH] --no-restart: skipping service restart")

            agents = None if args.agents == ["all"] else args.agents
            run_benchmark(
                model_endpoints=[f"{model}={args.api_url}"],
                judge_api_url=args.judge_api_url,
                judge_api_key=args.judge_api_key,
                limit=args.limit,
                test_cases_file=args.test_cases_file,
                agents=agents,
            )
            completed.append(model)
            logger.info("[BATCH] [OK] Done: %s", model)

        except Exception as exc:
            logger.error("[BATCH] [FAIL] %s -- %s", model, exc)
            failed.append((model, str(exc)))

    _print_comparison(completed)

    if failed:
        print(f"\nFailed models ({len(failed)}):")
        for model, err in failed:
            print(f"  {model}: {err}")

    logger.info("[BATCH] Finished: %d completed, %d failed", len(completed), len(failed))


if __name__ == "__main__":
    main()
