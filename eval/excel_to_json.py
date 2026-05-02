#!/usr/bin/env python3
"""
Convert 'eval/2026 AI 서비스_TC_v0.1.xlsx' to eval/test_cases_from_excel.json
for use with the faithfulness benchmark runner.

Usage:
    uv run --with openpyxl python eval/excel_to_json.py
    uv run --with openpyxl python eval/excel_to_json.py --input "eval/2026 AI 서비스_TC_v0.1.xlsx" --output eval/test_cases_from_excel.json

Output schema (matches benchmark_runner.py expectations):
    [
      {
        "id":          "tc-001",           # lowercase TC-ID, used as unique key
        "tc_id":       "TC-001",           # original TC-ID from Excel
        "category":    "product_recommendation",  # derived from Agent Flow
        "part":        "Part 1",           # section from Excel TOC
        "agent_flow":  "Product Recommendation AF",  # raw Agent Flow cell
        "user_message": "...",             # 질문 샘플 (quotes stripped)
        "description": "...",             # 테스트 시나리오
        "expected":    "...",             # 기대 결과
        "messages":    ["..."],           # list of turns (multi-turn for Part 6)
      },
      ...
    ]
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Ensure stdout handles Unicode on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Column indices (0-based, row values_only)
# ---------------------------------------------------------------------------
COL_TC_ID = 1           # B
COL_DESCRIPTION = 2     # C  테스트 시나리오
COL_AGENT_FLOW = 3      # D  Agent Flow
COL_USER_MESSAGE = 4    # E  질문 샘플
COL_EXPECTED = 5        # F  기대 결과

DATA_START_ROW = 12  # 1-based first data row (row 11 = header "TC-ID", ...)

# Part boundaries derived from TOC (TC-ID numbers, inclusive)
PART_RANGES = [
    (1,   45,  "Part 1", "메인 홈 및 상품 추천"),
    (46,  96,  "Part 2", "매장 선택 및 예약 서비스"),
    (97,  133, "Part 3", "혜택 적용 및 주문/결제"),
    (134, 178, "Part 4", "주문 내역 및 사후 관리"),
    (179, 228, "Part 5", "AI 가드레일 및 보안/윤리"),
    (229, 233, "Part 6", "챗봇 대화 기반 주문서 생성"),
]

# Agent Flow → category slug mapping
# Keys must be lowercase-stripped versions of the exact Excel cell values.
AGENT_FLOW_CATEGORY: dict[str, str] = {
    "product compatibility af":    "product_compatibility",
    "product description af":      "product_description",
    "product recommendation af":   "product_recommendation",
    "inventory af":                "inventory",
    "price af":                    "price_coupon",
    "faq af":                      "faq",
    "store af":                    "store",
    "store reservation af":        "store_reservation",
    "order / delivery af":         "order_delivery",
    "order af":                    "order_delivery",
    "fallback/escalation af":      "guardrail_escalation",
    "quick shopping af":           "quick_shopping",
}


def _get_part(tc_num: int) -> tuple[str, str]:
    """Return (part_label, part_description) for a TC number."""
    for lo, hi, label, desc in PART_RANGES:
        if lo <= tc_num <= hi:
            return label, desc
    return "Unknown", ""


def _agent_flow_to_category(agent_flow: str | None) -> str:
    """Map raw Agent Flow string to a category slug."""
    if not agent_flow:
        return "unknown"
    key = agent_flow.strip().lower()
    return AGENT_FLOW_CATEGORY.get(key, re.sub(r"\s+af$", "", key).replace(" ", "_"))


def _strip_quotes(text: str) -> str:
    """Remove surrounding Korean/ASCII quotation marks from a question sample."""
    text = text.strip()
    # Remove leading/trailing " " ' '
    text = re.sub(r'^["""\'\']+', "", text)
    text = re.sub(r'["""\'\']+$', "", text)
    return text.strip()


def _parse_multi_turn(question_cell: str) -> list[str]:
    """
    Parse multi-turn messages from Part 6 cells.

    Cells look like:
        1. "message one"\n2. (AI responds)\n3. "message two"\n...

    We extract only the numbered user turns (lines starting with a digit + dot).
    Lines that are parenthetical descriptions of AI responses are skipped.
    """
    messages: list[str] = []
    # Split on newlines
    lines = question_cell.replace("\r\n", "\n").split("\n")
    for line in lines:
        line = line.strip()
        # Match lines like: 1. "...", 2. "...", etc.
        m = re.match(r"^\d+\.\s+(.+)$", line)
        if not m:
            continue
        content = m.group(1).strip()
        # Skip parenthetical AI-response descriptions: (AI responds ...) or (...)
        if content.startswith("(") and content.endswith(")"):
            continue
        messages.append(_strip_quotes(content))
    return messages if messages else [_strip_quotes(question_cell)]


def convert(input_path: Path, output_path: Path) -> list[dict]:
    try:
        import openpyxl
    except ImportError:
        print("ERROR: openpyxl not installed. Run: pip install openpyxl", file=sys.stderr)
        sys.exit(1)

    wb = openpyxl.load_workbook(str(input_path))
    sheet_name = "(공통)테스트 시나리오"
    if sheet_name not in wb.sheetnames:
        print(f"ERROR: Sheet '{sheet_name}' not found. Available: {wb.sheetnames}", file=sys.stderr)
        sys.exit(1)

    ws = wb[sheet_name]
    test_cases: list[dict] = []
    skipped = 0

    for row in ws.iter_rows(min_row=DATA_START_ROW, max_row=ws.max_row, values_only=True):
        tc_id_raw = row[COL_TC_ID]

        # Skip rows without a valid TC-ID
        if not tc_id_raw or not str(tc_id_raw).strip().upper().startswith("TC-"):
            skipped += 1
            continue

        tc_id = str(tc_id_raw).strip()  # e.g. "TC-001"

        # Extract TC number for part lookup
        tc_id_match = re.match(r"TC-(\d+)", tc_id, re.IGNORECASE)
        tc_num = int(tc_id_match.group(1)) if tc_id_match else 0

        description = str(row[COL_DESCRIPTION]).strip() if row[COL_DESCRIPTION] else ""
        agent_flow = str(row[COL_AGENT_FLOW]).strip() if row[COL_AGENT_FLOW] else ""
        user_message_raw = str(row[COL_USER_MESSAGE]).strip() if row[COL_USER_MESSAGE] else ""
        expected = str(row[COL_EXPECTED]).strip() if row[COL_EXPECTED] else ""

        if not user_message_raw:
            skipped += 1
            continue

        part, part_description = _get_part(tc_num)
        category = _agent_flow_to_category(agent_flow)

        # Part 6 (TC-229~233) are multi-turn scenarios
        is_multi_turn = part == "Part 6"

        if is_multi_turn:
            messages = _parse_multi_turn(user_message_raw)
            user_message = messages[-1] if messages else _strip_quotes(user_message_raw)
        else:
            messages = [_strip_quotes(user_message_raw)]
            user_message = messages[0]

        tc = {
            "id": tc_id.lower().replace("-", "_"),   # "tc_001" — unique key for resume logic
            "tc_id": tc_id,                           # "TC-001"
            "part": part,                             # "Part 1"
            "part_description": part_description,
            "category": category,                     # "product_recommendation"
            "agent_flow": agent_flow,                 # "Product Recommendation AF"
            "user_message": user_message,             # last / only user turn
            "messages": messages,                     # all user turns (multi-turn support)
            "description": description,               # 테스트 시나리오
            "expected": expected,                     # 기대 결과
        }
        test_cases.append(tc)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(test_cases, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Converted {len(test_cases)} test cases -> {output_path}")
    print(f"  Skipped {skipped} empty/non-TC rows")

    # Print summary by part
    from collections import Counter
    part_counts = Counter(tc["part"] for tc in test_cases)
    cat_counts = Counter(tc["category"] for tc in test_cases)
    print("\nBy part:")
    for part, count in sorted(part_counts.items()):
        print(f"  {part}: {count} cases")
    print("\nBy category:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count} cases")

    return test_cases


def main() -> None:
    default_input = Path(__file__).parent / "2026 AI 서비스_TC_v0.1.xlsx"
    default_output = Path(__file__).parent / "test_cases_from_excel.json"

    parser = argparse.ArgumentParser(
        description="Convert T-Station AI test case Excel to JSON for benchmark runner"
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=default_input,
        help=f"Path to Excel file (default: {default_input})",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=default_output,
        help=f"Path to output JSON file (default: {default_output})",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    convert(args.input, args.output)


if __name__ == "__main__":
    main()
