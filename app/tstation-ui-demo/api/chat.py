"""API client for communicating with the backend using new chat API."""
import json
import uuid
from typing import Generator, Union

import requests
import streamlit as st

BASE_URL = "http://tstation-ai:8000/api"


def get_examples(language: str) -> dict:
    """Fetch example questions from the API."""
    try:
        response = requests.get(
            f"{BASE_URL}/tstation/chat/example_questions/{language}",
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.sidebar.error(f"Error when get example questions: {e}")
        return {}


def _get_or_create_session_id(session_id: str | None) -> str:
    """Get session_id or create new one if None."""
    if session_id:
        return session_id
    return str(uuid.uuid4())


def send_chat_message(
    content: str,
    session_id: str | None,
    stream: bool = False,
    access_token: str | None = None,
    user_info: dict | None = None,
    chip_context: dict | None = None,
    ui_action: dict | None = None,
) -> Union[str, Generator[dict, None, None]]:
    """
    Send chat message using new API (content only, no messages array).

    Args:
        content: User message content only
        session_id: Session identifier (optional, creates new if None)
        stream: If True, returns streaming generator; if False, returns complete response
        access_token: JWT access token (passed in Authorization header)
        user_info: Additional user info from UI (e.g., location)
        chip_context: Quick-reply chip routing metadata when the user tapped a chip
        ui_action: Normalized UI action payload when the user tapped a chip

    Returns:
        str: Complete response when stream=False
        Generator[str, None, None]: Streaming generator when stream=True
    """
    if not access_token:
        return "Access token is required."

    # Get or create session_id
    session_id = _get_or_create_session_id(session_id)

    payload = {
        "content": content,
        "session_id": session_id,
        "stream": stream,
    }
    if user_info:
        payload["user_info"] = user_info
    if chip_context:
        payload["chip_context"] = chip_context
    if ui_action:
        payload["ui_action"] = ui_action

    if stream:
        return _handle_stream_response(payload, session_id, access_token)
    else:
        return _handle_regular_response(payload, access_token)


def _handle_regular_response(payload: dict, access_token: str) -> str:
    """Handle non-streaming response"""
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.post(
            f"{BASE_URL}/tstation/messages/chat",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        return data.get("content", "Don't get the answer.")
    except Exception as e:
        return f"Error when call to API: {e}"


def _handle_stream_response(payload: dict, session_id: str, access_token: str) -> Generator[dict, None, None]:
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
        response = requests.post(
            f"{BASE_URL}/tstation/messages/chat",
            json=payload,
            stream=True,
            headers=headers,
        )

        response.raise_for_status()
        response.encoding = "utf-8"

        yield from _iter_sse_events(response)

    except Exception as e:
        yield {"type": "error", "content": str(e)}


def send_quick_order_action(
    session_id: str,
    payload: dict,
    access_token: str | None = None,
) -> Generator[dict, None, None]:
    """Execute the structured preOrder action endpoint and stream its SSE events."""
    if not access_token:
        yield {"type": "error", "content": "Access token is required."}
        return

    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
        response = requests.post(
            f"{BASE_URL}/tstation/messages/actions/quick-order",
            json={
                "session_id": session_id,
                "action": "quick_order_execute",
                "payload": payload,
                "stream": True,
            },
            stream=True,
            headers=headers,
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        yield from _iter_sse_events(response)
    except Exception as e:
        yield {"type": "error", "content": str(e)}


def _iter_sse_events(response) -> Generator[dict, None, None]:
    buffer = ""
    first_chunk = True

    for chunk in response.iter_content(chunk_size=1, decode_unicode=True):
        if not chunk:
            continue

        buffer += chunk

        # process full SSE event
        while "\n\n" in buffer:
            event, buffer = buffer.split("\n\n", 1)

            if not event.startswith("data: "):
                continue

            data_content = event[6:]

            if data_content.strip() == "[DONE]":
                return

            try:
                data = json.loads(data_content)
            except json.JSONDecodeError:
                continue

            # First chunk contains session info - just yield it
            if first_chunk and data.get("stream_started"):
                first_chunk = False
                yield {"type": "session_info", "session_id": data.get("session_id")}
                continue

            yield data
