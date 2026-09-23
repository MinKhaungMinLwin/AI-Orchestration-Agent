from __future__ import annotations

import os
import warnings
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]

FORBIDDEN_DIRECT_CONTEXT_READS = (
    "pending_order_context",
    "selected_order_context",
)

DISALLOWED_DIRECT_READ_FILES = (
    "app/tstation-ai/services/tstation/chat.py",
    "app/tstation-ai/services/tstation/policies/contract_required_tool_candidate.py",
    "app/tstation-ai/services/tstation/policies/preorder_event_builder.py",
    "app/tstation-ai/services/tstation/policies/slot_fill_controller.py",
    "app/tstation-ai/services/tstation/policies/transaction_intent_policy.py",
    "app/tstation-ai/services/tstation/policies/turn_contract.py",
    "app/tstation-ai/services/tstation/policies/ui_action_policy.py",
)

ALLOW_MARKER = "flowstate-boundary: allow"


def _direct_context_read_violations() -> list[str]:
    violations: list[str] = []
    for relative_path in DISALLOWED_DIRECT_READ_FILES:
        path = REPO_ROOT / relative_path
        if not path.exists():
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if ALLOW_MARKER in line:
                continue
            matched_tokens = [token for token in FORBIDDEN_DIRECT_CONTEXT_READS if token in line]
            if matched_tokens:
                token_list = ", ".join(matched_tokens)
                violations.append(f"{relative_path}:{line_no}: direct read token(s): {token_list}")
    return violations


def test_commerce_flow_context_reads_go_through_flow_state() -> None:
    """Warn when commerce state bypasses FlowState.

    During the migration this is advisory by default because legacy direct reads still exist.
    Set FLOWSTATE_BOUNDARY_STRICT=1 after the phase-1 refactor to fail on new violations.
    """

    violations = _direct_context_read_violations()
    if not violations:
        return

    message = (
        "Commerce flow context should be read through FlowState, not directly from "
        "pending_order_context/selected_order_context.\n"
        "Move legacy reads into flow_state.py or add a temporary inline "
        f"{ALLOW_MARKER!r} marker with a follow-up note.\n"
        + "\n".join(violations[:80])
    )
    if len(violations) > 80:
        message += f"\n... and {len(violations) - 80} more violation(s)"

    if os.environ.get("FLOWSTATE_BOUNDARY_STRICT") == "1":
        pytest.fail(message)

    warnings.warn(message, UserWarning, stacklevel=1)
