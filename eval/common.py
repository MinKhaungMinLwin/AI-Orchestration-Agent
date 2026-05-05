import os
from pathlib import Path

EVAL_DIR = Path(__file__).parent


def load_dotenv() -> None:
    """Load .env (root) into os.environ (setdefault — won't override existing vars)."""
    candidate = EVAL_DIR.parent / ".env"
    if not candidate.exists():
        return
    with open(candidate, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
