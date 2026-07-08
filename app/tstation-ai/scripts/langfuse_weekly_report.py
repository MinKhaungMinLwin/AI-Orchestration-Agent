#!/usr/bin/env python3
"""Generate a weekly customer-monitoring report from Langfuse.

Usage:
    python app/tstation-ai/scripts/langfuse_weekly_report.py --days 7
    python app/tstation-ai/scripts/langfuse_weekly_report.py --from 2026-07-01 --to 2026-07-08 --csv report.csv

Required environment:
    LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class MonitoringTrace:
    trace_id: str
    timestamp: str
    session_id: str
    user_id: str
    input_text: str
    final_status: str
    error_reason: str
    primary_domain: str
    primary_af: str
    final_template: str
    latency_ms: int | None
    message_id: str
    route_intents: list[str]
    tool_path: list[str]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Langfuse customer_monitoring weekly report.")
    parser.add_argument("--days", type=int, default=7, help="Lookback days when --from/--to are not provided.")
    parser.add_argument("--from", dest="date_from", help="Start date, YYYY-MM-DD.")
    parser.add_argument("--to", dest="date_to", help="End date, YYYY-MM-DD. Exclusive end boundary.")
    parser.add_argument("--limit", type=int, default=100, help="Langfuse page size.")
    parser.add_argument("--max-pages", type=int, default=50, help="Safety cap for pagination.")
    parser.add_argument("--csv", dest="csv_path", help="Optional CSV output path.")
    return parser.parse_args()


def _date_range(args: argparse.Namespace) -> tuple[datetime, datetime]:
    if args.date_from or args.date_to:
        if not args.date_from or not args.date_to:
            raise SystemExit("--from and --to must be provided together.")
        return (
            datetime.fromisoformat(args.date_from).replace(tzinfo=UTC),
            datetime.fromisoformat(args.date_to).replace(tzinfo=UTC),
        )
    end = datetime.now(UTC)
    return end - timedelta(days=args.days), end


def _auth_header() -> str:
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        raise SystemExit("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required.")
    token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    return f"Basic {token}"


def _get_json(path: str, params: dict[str, Any]) -> dict[str, Any]:
    host = os.environ.get("LANGFUSE_HOST")
    if not host:
        raise SystemExit("LANGFUSE_HOST is required.")
    url = f"{host.rstrip('/')}{path}?{urlencode(params)}"
    request = Request(url, headers={"Authorization": _auth_header()})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return []


def _collect_traces(start: datetime, end: datetime, *, limit: int, max_pages: int) -> list[MonitoringTrace]:
    traces: list[MonitoringTrace] = []
    for page in range(1, max_pages + 1):
        payload = _get_json(
            "/api/public/traces",
            {
                "name": "customer_monitoring",
                "fromTimestamp": start.isoformat().replace("+00:00", "Z"),
                "toTimestamp": end.isoformat().replace("+00:00", "Z"),
                "page": page,
                "limit": limit,
            },
        )
        rows = payload.get("data") or []
        for row in rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            output = row.get("output") if isinstance(row.get("output"), dict) else {}
            traces.append(
                MonitoringTrace(
                    trace_id=str(row.get("id") or ""),
                    timestamp=str(row.get("timestamp") or ""),
                    session_id=str(row.get("sessionId") or metadata.get("session_id") or ""),
                    user_id=str(row.get("userId") or metadata.get("user_id") or ""),
                    input_text=str(row.get("input") or ""),
                    final_status=str(metadata.get("final_status") or output.get("final_status") or ""),
                    error_reason=str(metadata.get("error_reason") or output.get("error_reason") or ""),
                    primary_domain=str(metadata.get("primary_domain") or output.get("primary_domain") or ""),
                    primary_af=str(metadata.get("primary_af") or output.get("primary_af") or ""),
                    final_template=str(metadata.get("final_template") or output.get("final_template") or ""),
                    latency_ms=metadata.get("latency_ms") if isinstance(metadata.get("latency_ms"), int) else None,
                    message_id=str(metadata.get("message_id") or ""),
                    route_intents=_as_list(metadata.get("route_intents")),
                    tool_path=_as_list(metadata.get("tool_path")),
                )
            )
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        if page >= int(meta.get("totalPages") or page) or not rows:
            break
    return traces


def _percent(part: int, total: int) -> str:
    return "0.0%" if total == 0 else f"{part / total * 100:.1f}%"


def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return ordered[index]


def _write_csv(path: str, traces: list[MonitoringTrace]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "timestamp",
                "trace_id",
                "session_id",
                "message_id",
                "user_id",
                "final_status",
                "error_reason",
                "primary_domain",
                "primary_af",
                "final_template",
                "latency_ms",
                "route_intents",
                "tool_path",
                "input_text",
            ],
        )
        writer.writeheader()
        for trace in traces:
            writer.writerow(
                {
                    "timestamp": trace.timestamp,
                    "trace_id": trace.trace_id,
                    "session_id": trace.session_id,
                    "message_id": trace.message_id,
                    "user_id": trace.user_id,
                    "final_status": trace.final_status,
                    "error_reason": trace.error_reason,
                    "primary_domain": trace.primary_domain,
                    "primary_af": trace.primary_af,
                    "final_template": trace.final_template,
                    "latency_ms": trace.latency_ms,
                    "route_intents": ",".join(trace.route_intents),
                    "tool_path": ",".join(trace.tool_path),
                    "input_text": trace.input_text,
                }
            )


def _print_report(traces: list[MonitoringTrace], start: datetime, end: datetime) -> None:
    total = len(traces)
    status_counts = Counter(trace.final_status or "unknown" for trace in traces)
    af_counts = Counter(trace.primary_af or "unknown" for trace in traces)
    error_counts = Counter(trace.error_reason or "none" for trace in traces)
    tool_counts = Counter(tool for trace in traces for tool in trace.tool_path)
    latencies = [trace.latency_ms for trace in traces if isinstance(trace.latency_ms, int)]
    avg_latency = int(sum(latencies) / len(latencies)) if latencies else None
    p95_latency = _p95(latencies)

    print("# T-Station AI Weekly Monitoring Report\n")
    print(f"- Period: {start.date()} ~ {end.date()} UTC")
    print(f"- Total customer_monitoring traces: {total}")
    print(f"- Success rate: {_percent(status_counts.get('success', 0), total)}")
    print(f"- Average latency: {avg_latency if avg_latency is not None else '-'} ms")
    print(f"- P95 latency: {p95_latency if p95_latency is not None else '-'} ms\n")

    print("## Status")
    for status, count in status_counts.most_common():
        print(f"- {status}: {count} ({_percent(count, total)})")

    print("\n## AF")
    for af, count in af_counts.most_common():
        print(f"- {af}: {count}")

    print("\n## Error Reason")
    for reason, count in error_counts.most_common():
        print(f"- {reason}: {count}")

    print("\n## Top Tools")
    for tool, count in tool_counts.most_common(10):
        print(f"- {tool}: {count}")

    risky = [trace for trace in traces if trace.final_status in {"error", "fallback", "partial_success"}]
    print("\n## Review Targets")
    for trace in risky[:20]:
        print(
            f"- {trace.timestamp} | {trace.final_status} | {trace.error_reason} | "
            f"{trace.primary_af} | session={trace.session_id} | trace={trace.trace_id}"
        )


def main() -> int:
    args = _parse_args()
    start, end = _date_range(args)
    traces = _collect_traces(start, end, limit=args.limit, max_pages=args.max_pages)
    _print_report(traces, start, end)
    if args.csv_path:
        _write_csv(args.csv_path, traces)
        print(f"\nCSV written: {args.csv_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
