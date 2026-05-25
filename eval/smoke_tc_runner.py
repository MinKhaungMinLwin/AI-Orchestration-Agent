"""Run lightweight SSE smoke checks for T-Station review test cases.

This runner intentionally avoids LLM judging. It collects the raw SSE evidence
needed for manual triage: agents, tools, templates, assistant messages, latency,
and simple machine-detectable warnings.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx


EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_PATH = EVAL_DIR / "test_cases_from_excel.json"
DEFAULT_OVERLAY_PATH = EVAL_DIR / "current_review_tc_notes.md"
DEFAULT_REPORT_DIR = EVAL_DIR / "smoke_reports"


@dataclass
class SmokeCase:
    tc_id: str
    category: str
    agent_flow: str
    description: str
    expected: str
    messages: list[str]
    source: str
    focus: str = ""


@dataclass
class SmokeResult:
    tc_id: str
    source: str
    status: str
    category: str
    agent_flow: str
    messages: list[str]
    focus: str
    latency_total_s: float | None = None
    latency_first_event_s: float | None = None
    agents: list[str] = field(default_factory=list)
    agent_flows: list[str] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    templates: list[dict[str, Any]] = field(default_factory=list)
    assistant_messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    session_id: str | None = None


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def load_overlay(path: Path) -> dict[str, dict[str, str]]:
    overlay: dict[str, dict[str, str]] = {}
    if not path.exists():
        return overlay

    for line in path.read_text(encoding="utf-8").splitlines():
        cells = _split_markdown_row(line)
        if len(cells) < 4 or not re.fullmatch(r"TC-\d+", cells[0]):
            continue
        overlay[cells[0]] = {
            "agent_flow": cells[1],
            "review_question": cells[2],
            "focus": cells[3],
        }
    return overlay


def load_cases(cases_path: Path, overlay_path: Path, *, source: str) -> list[SmokeCase]:
    raw_cases = json.loads(cases_path.read_text(encoding="utf-8"))
    overlay = load_overlay(overlay_path)
    cases: list[SmokeCase] = []

    for raw in raw_cases:
        tc_id = raw.get("tc_id") or raw.get("id")
        if not tc_id:
            continue
        overlay_item = overlay.get(tc_id)
        if source == "overlay" and not overlay_item:
            continue

        if overlay_item:
            messages = [overlay_item["review_question"]]
            case_source = "overlay"
            focus = overlay_item["focus"]
            agent_flow = overlay_item.get("agent_flow") or raw.get("agent_flow", "")
        else:
            messages = list(raw.get("messages") or [raw.get("user_message", "")])
            case_source = "base"
            focus = ""
            agent_flow = raw.get("agent_flow", "")

        messages = [msg for msg in messages if msg]
        if not messages:
            continue

        cases.append(
            SmokeCase(
                tc_id=tc_id,
                category=raw.get("category", ""),
                agent_flow=agent_flow,
                description=raw.get("description", ""),
                expected=raw.get("expected", ""),
                messages=messages,
                source=case_source,
                focus=focus,
            )
        )
    return cases


def _extract_tool(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": event.get("tool"),
        "source_domain": event.get("source_domain"),
        "input": event.get("input"),
        "output_preview": _preview(event.get("output"), limit=800),
    }


def _extract_template(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data") or {}
    template = event.get("template")
    return {
        "template": template,
        "source_domain": event.get("source_domain"),
        "assistant_response": _preview(data.get("assistantResponse"), limit=500),
        "item_count": _template_item_count(template, data),
    }


def _template_item_count(template: str | None, data: dict[str, Any]) -> int | None:
    if template == "product":
        return _first_list_count(data, "products", "items")
    if template == "location":
        return _first_list_count(data, "locations", "stores", "items")
    if template == "voucher":
        return _first_list_count(data, "coupons", "vouchers", "items")
    if template == "listCar":
        return _first_list_count(data, "cars", "vehicles", "items")
    if template == "datepick":
        return len(data.get("schedules") or data.get("dates") or [])
    quick_replies = data.get("quickReplies")
    if template == "quickReply" and isinstance(quick_replies, list):
        return len(quick_replies)
    return None


def _first_list_count(data: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return len(value)
    return None


def _preview(value: Any, *, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    value = value.replace("\n", "\\n")
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def call_chat(
    *,
    api_url: str,
    jwt_token: str,
    content: str,
    session_id: str,
    timeout_s: float,
    location: dict[str, float],
) -> tuple[list[dict[str, Any]], float, float | None, bool]:
    url = f"{api_url.rstrip('/')}/tstation/messages/chat"
    payload = {
        "content": content,
        "session_id": session_id,
        "stream": True,
        "user_info": {"location": location},
    }
    start = time.monotonic()
    first_event_s: float | None = None
    done = False
    events: list[dict[str, Any]] = []

    with httpx.stream(
        "POST",
        url,
        json=payload,
        headers={"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"},
        timeout=timeout_s,
        verify=False,
    ) as response:
        response.raise_for_status()
        for raw_line in response.iter_lines():
            line = raw_line.strip()
            if not line or not line.startswith("data: "):
                continue
            if first_event_s is None:
                first_event_s = round(time.monotonic() - start, 3)
            data_str = line[6:]
            if data_str == "[DONE]":
                done = True
                break
            event = json.loads(data_str)
            events.append(event)
            if event.get("type") == "DONE":
                done = True
                break

    return events, round(time.monotonic() - start, 3), first_event_s, done


def call_chat_over_ssh(
    *,
    ssh_host: str,
    ssh_key: str | None,
    api_url: str,
    jwt_token: str,
    content: str,
    session_id: str,
    timeout_s: float,
    location: dict[str, float],
) -> tuple[list[dict[str, Any]], float, float | None, bool]:
    url = f"{api_url.rstrip('/')}/tstation/messages/chat"
    payload = json.dumps(
        {
            "content": content,
            "session_id": session_id,
            "stream": True,
            "user_info": {"location": location},
        },
        ensure_ascii=False,
    )
    remote_cmd = " ".join(
        [
            "curl",
            "-skN",
            "-X",
            "POST",
            shlex.quote(url),
            "-H",
            shlex.quote(f"Authorization: Bearer {jwt_token}"),
            "-H",
            shlex.quote("Accept: text/event-stream"),
            "-H",
            shlex.quote("Content-Type: application/json"),
            "--data-binary",
            "@-",
        ]
    )
    cmd = ["ssh", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=2"]
    if ssh_key:
        cmd.extend(["-i", ssh_key])
    cmd.extend([ssh_host, remote_cmd])

    start = time.monotonic()
    first_event_s: float | None = None
    done = False
    events: list[dict[str, Any]] = []
    process = subprocess.Popen(  # noqa: S603 - command is built from explicit CLI args for test runner use.
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(payload)
    process.stdin.close()

    try:
        deadline = start + timeout_s
        for raw_line in process.stdout:
            if time.monotonic() > deadline:
                process.kill()
                raise TimeoutError(f"SSH curl timed out after {timeout_s}s")
            line = raw_line.strip()
            if not line or not line.startswith("data: "):
                continue
            if first_event_s is None:
                first_event_s = round(time.monotonic() - start, 3)
            data_str = line[6:]
            if data_str == "[DONE]":
                done = True
                break
            event = json.loads(data_str)
            events.append(event)
            if event.get("type") == "DONE":
                done = True
                break
        stderr = process.stderr.read() if process.stderr is not None else ""
        return_code = process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()

    if return_code != 0:
        raise RuntimeError(f"ssh curl failed with code {return_code}: {stderr.strip()}")
    return events, round(time.monotonic() - start, 3), first_event_s, done


def run_case(
    case: SmokeCase,
    *,
    api_url: str,
    jwt_token: str,
    session_prefix: str,
    timeout_s: float,
    location: dict[str, float],
    ssh_host: str | None = None,
    ssh_key: str | None = None,
) -> SmokeResult:
    session_id = f"{session_prefix}-{case.tc_id.lower()}-{uuid4().hex[:8]}"
    result = SmokeResult(
        tc_id=case.tc_id,
        source=case.source,
        status="PASS",
        category=case.category,
        agent_flow=case.agent_flow,
        messages=case.messages,
        focus=case.focus,
        session_id=session_id,
    )

    all_events: list[dict[str, Any]] = []
    total_s = 0.0
    first_event_s: float | None = None
    try:
        for message in case.messages:
            if ssh_host:
                events, turn_total_s, turn_first_event_s, done = call_chat_over_ssh(
                    ssh_host=ssh_host,
                    ssh_key=ssh_key,
                    api_url=api_url,
                    jwt_token=jwt_token,
                    content=message,
                    session_id=session_id,
                    timeout_s=timeout_s,
                    location=location,
                )
            else:
                events, turn_total_s, turn_first_event_s, done = call_chat(
                    api_url=api_url,
                    jwt_token=jwt_token,
                    content=message,
                    session_id=session_id,
                    timeout_s=timeout_s,
                    location=location,
                )
            total_s += turn_total_s
            if first_event_s is None:
                first_event_s = turn_first_event_s
            if not done:
                result.warnings.append("sse_done_missing")
            all_events.extend(events)
    except Exception as exc:  # noqa: BLE001 - smoke runner should preserve any failure.
        result.status = "FAIL"
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    result.latency_total_s = round(total_s, 3)
    result.latency_first_event_s = first_event_s
    _summarize_events(result, all_events)
    _apply_smoke_warnings(result)
    if result.status != "FAIL" and result.warnings:
        result.status = "PARTIAL"
    return result


def _summarize_events(result: SmokeResult, events: list[dict[str, Any]]) -> None:
    for event in events:
        etype = event.get("type")
        if etype == "sub-agent":
            agent = event.get("agent")
            if agent and agent not in result.agents:
                result.agents.append(agent)
        elif etype == "agent_flow":
            agent_flow = event.get("agent")
            if agent_flow:
                result.agent_flows.append(agent_flow)
        elif etype == "tool":
            result.tools.append(_extract_tool(event))
        elif etype == "data":
            result.templates.append(_extract_template(event))
        elif etype == "message":
            content = event.get("content")
            if content:
                result.assistant_messages.append(content)


def _apply_smoke_warnings(result: SmokeResult) -> None:
    if not result.assistant_messages and not result.templates:
        result.warnings.append("no_visible_response")
    if result.latency_total_s is not None and result.latency_total_s > 30:
        result.warnings.append("latency_total_over_30s")
    if result.latency_first_event_s is not None and result.latency_first_event_s > 5:
        result.warnings.append("first_event_over_5s")

    assistant_blob = "\n".join(result.assistant_messages)
    if "죄송" in assistant_blob or "오류" in assistant_blob or "문제가 발생" in assistant_blob:
        result.warnings.append("error_like_assistant_text")
    if "1:1 문의하기" in assistant_blob and "처음으로" in assistant_blob and not result.tools:
        result.warnings.append("generic_fallback_without_tool")

    for template in result.templates:
        if template["template"] in {"product", "location", "voucher", "listCar"} and template.get("item_count") == 0:
            result.warnings.append(f"empty_{template['template']}_template")


def write_reports(results: list[SmokeResult], report_dir: Path, run_id: str) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = report_dir / f"{run_id}.jsonl"
    md_path = report_dir / f"{run_id}.md"

    with jsonl_path.open("w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")

    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    lines = [
        f"# Smoke Report {run_id}",
        "",
        f"- total: {len(results)}",
        f"- PASS: {counts.get('PASS', 0)}",
        f"- PARTIAL: {counts.get('PARTIAL', 0)}",
        f"- FAIL: {counts.get('FAIL', 0)}",
        "",
        "| TC | Status | Latency | First Event | Tools | Templates | Warnings |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for result in results:
        tools = ", ".join(tool.get("tool") or "" for tool in result.tools) or "-"
        templates = ", ".join(template.get("template") or "" for template in result.templates) or "-"
        warnings = ", ".join(result.warnings) or (result.error or "-")
        lines.append(
            "| {tc} | {status} | {latency} | {first} | {tools} | {templates} | {warnings} |".format(
                tc=result.tc_id,
                status=result.status,
                latency=result.latency_total_s if result.latency_total_s is not None else "-",
                first=result.latency_first_event_s if result.latency_first_event_s is not None else "-",
                tools=tools.replace("|", "\\|"),
                templates=templates.replace("|", "\\|"),
                warnings=warnings.replace("|", "\\|"),
            )
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return jsonl_path, md_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["overlay", "all"], default="overlay")
    parser.add_argument("--cases-path", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--overlay-path", type=Path, default=DEFAULT_OVERLAY_PATH)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--api-url", default=os.environ.get("SMOKE_API_URL", "https://localhost/api"))
    parser.add_argument("--ssh-host", default=os.environ.get("SMOKE_SSH_HOST"))
    parser.add_argument("--ssh-key", default=os.environ.get("SMOKE_SSH_KEY"))
    parser.add_argument("--jwt-token", default=os.environ.get("JWT_TOKEN") or os.environ.get("EVAL_JWT_TOKEN", ""))
    parser.add_argument("--session-prefix", default="codex-smoke-alltc")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--tc", action="append", default=[], help="Run only the given TC id. Can be repeated.")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--xpos", type=float, default=127.0276)
    parser.add_argument("--ypos", type=float, default=37.4979)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    cases = load_cases(args.cases_path, args.overlay_path, source=args.source)
    if args.tc:
        wanted = {tc.upper() for tc in args.tc}
        cases = [case for case in cases if case.tc_id.upper() in wanted]
    if args.offset:
        cases = cases[args.offset :]
    if args.limit:
        cases = cases[: args.limit]

    if args.dry_run:
        for case in cases:
            print(f"{case.tc_id}\t{case.source}\t{case.messages[0]}")
        print(f"total={len(cases)}")
        return 0

    if not args.jwt_token:
        print("JWT token is required. Set JWT_TOKEN/EVAL_JWT_TOKEN or pass --jwt-token.", file=sys.stderr)
        return 2

    run_id = datetime.now().strftime("smoke_%Y%m%d_%H%M%S")
    results: list[SmokeResult] = []
    location = {"xpos": args.xpos, "ypos": args.ypos}
    for idx, case in enumerate(cases, start=1):
        print(f"[{idx}/{len(cases)}] {case.tc_id} {case.messages[0][:80]}", flush=True)
        result = run_case(
            case,
            api_url=args.api_url,
            jwt_token=args.jwt_token,
            session_prefix=args.session_prefix,
            timeout_s=args.timeout,
            location=location,
            ssh_host=args.ssh_host,
            ssh_key=args.ssh_key,
        )
        print(
            f"  -> {result.status} total={result.latency_total_s} first={result.latency_first_event_s} "
            f"tools={[tool.get('tool') for tool in result.tools]} "
            f"templates={[template.get('template') for template in result.templates]} "
            f"warnings={result.warnings or result.error}",
            flush=True,
        )
        results.append(result)

    jsonl_path, md_path = write_reports(results, args.report_dir, run_id)
    print(f"jsonl={jsonl_path}")
    print(f"markdown={md_path}")
    return 1 if any(result.status == "FAIL" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
