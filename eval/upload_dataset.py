"""
Upload test cases to a Langfuse dataset.

Run once before langfuse_eval.py. Safe to re-run — existing items are skipped.

Usage:
    python eval/upload_dataset.py
    python eval/upload_dataset.py --dataset tstation-eval --file eval/test_cases_tool_only.json
    python eval/upload_dataset.py --dry-run
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

_eval_dir = Path(__file__).parent
if str(_eval_dir) not in sys.path:
    sys.path.insert(0, str(_eval_dir))

from common import EVAL_DIR, load_dotenv
from logging_utils import configure_logging

logger = logging.getLogger(__name__)

DEFAULT_DATASET_NAME = "tstation-eval"
DEFAULT_FILE = EVAL_DIR / "test_cases_tool_only.json"


def upload_dataset(dataset_name: str, test_cases_file: Path, dry_run: bool = False, limit: int = 0) -> None:
    from langfuse import Langfuse

    lf = Langfuse(
        host=os.environ.get("LANGFUSE_HOST", "http://localhost:3002"),
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    )

    test_cases: list[dict] = json.loads(test_cases_file.read_text(encoding="utf-8"))
    if limit > 0:
        test_cases = test_cases[:limit]
    logger.info("Loaded %d test cases from %s", len(test_cases), test_cases_file.name)

    valid = [(tc["tc_id"] or tc.get("id", ""), tc.get("user_message", ""), tc) for tc in test_cases]
    valid = [(tc_id, msg, tc) for tc_id, msg, tc in valid if tc_id and msg]

    if dry_run:
        for tc_id, msg, tc in valid:
            n_turns = len(tc.get("messages") or [])
            turns_str = f" [{n_turns} turns]" if n_turns > 1 else ""
            logger.info("[DRY RUN] %s%s — %s", tc_id, turns_str, msg[:70])
        logger.info("Would create %d item(s) in dataset '%s'", len(valid), dataset_name)
        return

    lf.create_dataset(
        name=dataset_name,
        description="T-Station AI eval — test cases for discovery and transaction agents (single-turn and multi-turn)",
    )
    existing_ids = {str(item.id) for item in lf.get_dataset(dataset_name).items}
    logger.info("Dataset '%s': %d existing items", dataset_name, len(existing_ids))

    created = skipped = 0
    for tc_id, user_message, tc in valid:
        if tc_id in existing_ids:
            skipped += 1
            continue
        input_data: dict = {"user_message": user_message}
        messages = tc.get("messages")
        if messages and len(messages) > 1:
            input_data["messages"] = messages

        lf.create_dataset_item(
            dataset_name=dataset_name,
            id=tc_id,
            input=input_data,
            metadata={
                "tc_id": tc_id,
                "description": tc.get("description", ""),
                "category": tc.get("category", ""),
                "agent": tc.get("agent", ""),
                "agent_flow": tc.get("agent_flow", ""),
            },
        )
        logger.info("Created item: %s", tc_id)
        created += 1

    lf.flush()
    logger.info(
        "Created %d item(s) in dataset '%s'%s",
        created, dataset_name,
        f", skipped {skipped} existing" if skipped else "",
    )


def main() -> None:
    configure_logging()
    load_dotenv()

    parser = argparse.ArgumentParser(description="Upload test cases to a Langfuse dataset")
    parser.add_argument("--dataset", default=DEFAULT_DATASET_NAME, help=f"Dataset name (default: {DEFAULT_DATASET_NAME})")
    parser.add_argument("--file", default=str(DEFAULT_FILE), help=f"Test cases JSON file (default: {DEFAULT_FILE.name})")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making API calls")
    parser.add_argument("--limit", type=int, default=0, help="Max items to upload (0 = all)")
    args = parser.parse_args()

    upload_dataset(
        dataset_name=args.dataset,
        test_cases_file=Path(args.file),
        dry_run=args.dry_run,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
