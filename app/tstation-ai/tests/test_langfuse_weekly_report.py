from __future__ import annotations

import csv
from datetime import UTC, datetime

from scripts import langfuse_weekly_report as report


def test_collect_and_write_csv_includes_assistant_response(monkeypatch, tmp_path) -> None:
    payload = {
        "data": [
            {
                "id": "trace-1",
                "timestamp": "2026-07-13T06:11:04.226Z",
                "sessionId": "session-1",
                "userId": "member-1",
                "input": "내 근처 매장 찾아줘",
                "output": "가까운 매장을 안내드릴게요.",
                "metadata": {
                    "message_id": "message-1",
                    "assistant_response": "가까운 매장을 안내드릴게요.",
                    "final_status": "success",
                    "error_reason": "none",
                    "primary_domain": "TRANSACTION",
                    "primary_af": "Store AF",
                    "final_template": "quickReply",
                    "latency_ms": 12644,
                    "route_intents": ["store_finder"],
                    "tool_path": ["search_stores_tool"],
                },
            }
        ],
        "meta": {"totalPages": 1},
    }
    monkeypatch.setattr(report, "_get_json", lambda *_args, **_kwargs: payload)

    traces = report._collect_traces(
        datetime(2026, 7, 13, tzinfo=UTC),
        datetime(2026, 7, 14, tzinfo=UTC),
        limit=100,
        max_pages=1,
    )
    csv_path = tmp_path / "report.csv"
    report._write_csv(str(csv_path), traces)

    with csv_path.open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    assert rows[0]["input_text"] == "내 근처 매장 찾아줘"
    assert rows[0]["assistant_response"] == "가까운 매장을 안내드릴게요."


def test_collect_uses_string_output_when_assistant_metadata_is_missing(monkeypatch) -> None:
    payload = {
        "data": [
            {
                "id": "trace-1",
                "input": "질문",
                "output": "최종 답변",
                "metadata": {"final_status": "success"},
            }
        ],
        "meta": {"totalPages": 1},
    }
    monkeypatch.setattr(report, "_get_json", lambda *_args, **_kwargs: payload)

    traces = report._collect_traces(
        datetime(2026, 7, 13, tzinfo=UTC),
        datetime(2026, 7, 14, tzinfo=UTC),
        limit=100,
        max_pages=1,
    )

    assert traces[0].assistant_response == "최종 답변"
