"""pytest config — make app/tstation-ai/ importable so tests can do
``from services.tstation.qc_verifier import ...`` without setting PYTHONPATH.
"""
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent.parent  # app/tstation-ai/
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))
