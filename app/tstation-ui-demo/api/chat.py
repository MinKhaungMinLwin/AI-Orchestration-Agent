"""API client for communicating with the backend."""
import json
import os
from typing import Dict, Generator, List, Union

import requests
import streamlit as st

BASE_URL = "http://tstation-ai:8000/api"
API_KEY = os.getenv("API_SECRET_KEY", None)
HEADERS = {}
if API_KEY:
    HEADERS["Authorization"] = f"Bearer {API_KEY}"

def get_examples(language: str) -> dict:
    """Fetch example questions from the API."""
    try:
        response = requests.get(
            f"{BASE_URL}/tstation/chat/example_questions/{language}",
            headers=HEADERS,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.sidebar.error(f"Error when get example questions: {e}")
        return {}


def send_chat_message(messages: List[Dict[str, str]],
                      session_id: str,
                      user_id: str,
                      stream: bool = False) -> Union[str, Generator[str, None, None]]:
    """
    Send chat message to the API and return response.

    Args:
        messages: List of message dictionaries
        session_id: Session identifier
        user_id: User identifier
        stream: If True, returns streaming generator; if False, returns complete response

    Returns:
        str: Complete response when stream=False
        Generator[str, None, None]: Streaming generator when stream=True
    """
    payload = {
        "messages": messages,
        "session_id": session_id,
        "user_id": user_id,
        "stream": stream,

        # Tracing
        "metadata": {
            "position": "Streamlit Demo"
        },
    }

    if stream:
        return _handle_stream_response(payload)
    else:
        return _handle_regular_response(payload)


def _handle_regular_response(payload: dict) -> str:
    """Handle non-streaming response"""
    try:
        response = requests.post(
            f"{BASE_URL}/tstation/chat",
            headers=HEADERS,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        return data.get("content", "Don't get the answer.")
    except Exception as e:
        return f"Error when call to API: {e}"


def _handle_stream_response(payload: dict) -> Generator[str, None, None]:
    """Handle streaming response with SSE"""
    try:
        response = requests.post(
            f"{BASE_URL}/tstation/chat",
            json=payload,
            stream=True,
            headers={
                'Accept': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Authorization': f'Bearer {API_KEY}',
            }
        )
        response.raise_for_status()
        response.encoding = 'utf-8'

        # Process SSE stream
        for line in response.iter_lines(decode_unicode=True):
            if line:
                # SSE format: "data: {json_content}"
                if line.startswith("data: "):
                    data_content = line[6:]  # Remove "data: " prefix

                    # Check for end of stream
                    if data_content.strip() == "[DONE]":
                        break

                    try:
                        # Parse JSON chunk
                        chunk_data = json.loads(data_content)

                        # Extract content from chunk
                        if (chunk_data.get("choices") and
                                len(chunk_data["choices"]) > 0 and
                                chunk_data["choices"][0].get("delta") and
                                chunk_data["choices"][0]["delta"].get("content")):
                            content = chunk_data["choices"][0]["delta"]["content"]
                            if isinstance(content, bytes):
                                content = content.decode('utf-8')
                            yield content

                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue

    except Exception as e:
        yield f"Error when streaming API: {e}"
