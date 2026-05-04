import os
import re
from pathlib import Path


EVAL_DIR = Path(__file__).parent
DEFAULT_BENCHMARK_TEST_CASES_FILE = EVAL_DIR / "test_cases_from_excel.json"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Agents whose outputs count toward all eval metrics.
# Records from other agents (leading_agent, support_agent, etc.) are excluded from scoring.
SCORED_AGENTS: frozenset[str] = frozenset({"discovery_agent", "transaction_agent"})

# Maps agent_flow label (from test case spec) to the backend agent that handles it.
AF_TO_AGENT: dict[str, str] = {
    "Product Compatibility AF":  "discovery_agent",
    "Product Description AF":    "discovery_agent",
    "Product Recommendation AF": "discovery_agent",
    "Vehicle & Compatibility AF": "discovery_agent",
    "Inventory AF":              "transaction_agent",
    "Price AF":                  "transaction_agent",
    "Store AF":                  "transaction_agent",
    "Order / Delivery AF":       "transaction_agent",
    "Quick shopping AF":         "transaction_agent",
    "FAQ AF":                    "support_agent",
    "Fallback/Escalation AF":    "leading_agent",
}


def resolve_test_cases_file(test_cases_file: str | None = None) -> Path:
    """Resolve benchmark test case file path relative to eval dir by default."""
    raw_path = test_cases_file or os.environ.get("EVAL_TEST_CASES_FILE", "")
    if not raw_path:
        return DEFAULT_BENCHMARK_TEST_CASES_FILE
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = EVAL_DIR / candidate
    return candidate


def sanitize_name(value: str) -> str:
    """Create a filesystem-safe identifier while keeping names readable."""
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return sanitized.strip("-._") or "run"


def percentile(values: list[float], p: float) -> float | None:
    """Return the p-th percentile of values using linear interpolation."""
    if not values:
        return None
    s = sorted(values)
    i = (p / 100) * (len(s) - 1)
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (i - lo), 3)
