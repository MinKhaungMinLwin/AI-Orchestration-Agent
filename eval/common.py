import os
import re
from pathlib import Path


EVAL_DIR = Path(__file__).parent
DEFAULT_BENCHMARK_TEST_CASES_FILE = EVAL_DIR / "test_cases_from_excel.json"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

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


def percentile(values: list[float], p: int) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    idx = int(len(sorted_values) * p / 100)
    return round(sorted_values[min(idx, len(sorted_values) - 1)], 3)
