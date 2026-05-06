import json
import logging
import os
import time

import httpx

from judges import call_answer_relevance_llm, call_faithfulness_llm, call_template_correctness_llm, call_tool_appropriateness_llm

logger = logging.getLogger(__name__)


def get_jwt_token() -> str:
    return os.environ.get("EVAL_JWT_TOKEN", "")


def call_chat(
    api_url: str,
    *,
    jwt_token: str,
    user_message: str,
    session_id: str,
    tracing_id: str | None = None,
    timeout: int = 300,
) -> dict:
    url = f"{api_url.rstrip('/')}/tstation/messages/chat"
    payload: dict = {"content": user_message, "session_id": session_id, "stream": True, "user_info": {"location": {"xpos": 127.0276, "ypos": 37.4979}}}
    if tracing_id:
        payload["tracing_id"] = tracing_id

    start = time.time()
    template_events: list[dict] = []
    tool_events: list[dict] = []

    with httpx.stream(
        "POST", url, json=payload,
        headers={"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"},
        timeout=timeout, verify=False,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            line = line.strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            event = json.loads(data_str)
            etype = event.get("type")
            if etype == "data" and event.get("template"):
                template_events.append(event)
            elif etype == "tool":
                tool_events.append({
                    "tool_name": event["tool"],
                    "tool_input": event.get("input"),
                    "tool_output": event.get("output"),
                    "source_domain": event.get("source_domain"),
                })

    return {
        "tool_evidence": tool_events,
        "template_events": template_events,
        "total_s": round(time.time() - start, 3),
    }


def score_faithfulness(*, user_message: str, messages: list[str] | None = None, tool_evidence: list[dict], template_events: list[dict], judge_api_url: str, judge_api_key: str) -> dict:
    return call_faithfulness_llm(
        judge_api_url=judge_api_url, judge_api_key=judge_api_key,
        user_message=user_message,
        messages=messages or [],
        tool_evidence=json.dumps(tool_evidence, ensure_ascii=False),
        response=json.dumps(template_events, ensure_ascii=False),
    )


def score_answer_relevance(*, user_message: str, messages: list[str] | None = None, template_events: list[dict], judge_api_url: str, judge_api_key: str) -> dict:
    return call_answer_relevance_llm(
        judge_api_url=judge_api_url, judge_api_key=judge_api_key,
        user_message=user_message,
        messages=messages or [],
        response=json.dumps(template_events, ensure_ascii=False),
    )


def score_template_correctness(*, user_message: str, messages: list[str] | None = None, template_events: list[dict], judge_api_url: str, judge_api_key: str) -> dict:
    return call_template_correctness_llm(
        judge_api_url=judge_api_url, judge_api_key=judge_api_key,
        user_message=user_message,
        messages=messages or [],
        response=json.dumps(template_events, ensure_ascii=False),
    )


def score_tool_appropriateness(*, user_message: str, messages: list[str] | None = None, tool_evidence: list[dict], judge_api_url: str, judge_api_key: str) -> dict:
    return call_tool_appropriateness_llm(
        judge_api_url=judge_api_url, judge_api_key=judge_api_key,
        user_message=user_message,
        messages=messages or [],
        tool_evidence=json.dumps(tool_evidence, ensure_ascii=False),
    )
