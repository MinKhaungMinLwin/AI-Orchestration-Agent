"""API client for session management with new chat API."""
import os
import uuid
from typing import Dict, List

import requests
import streamlit as st

BASE_URL = "http://tstation-ai:8000"


def _get_or_create_session_id(session_id: str | None, access_token: str) -> str:
    """Get session_id or create new one if None."""
    if session_id:
        return session_id
    # Generate new UUID for new conversation
    return str(uuid.uuid4())


def get_sessions(access_token: str) -> List[Dict]:
    """
    Get list of user's sessions.
    GET /tstation/messages/sessions
    """
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(
            f"{BASE_URL}/tstation/messages/sessions",
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("sessions", [])
    except Exception as e:
        st.error(f"Error getting sessions: {e}")
        return []


def get_history(session_id: str | None, access_token: str) -> List[Dict]:
    """
    Get chat history for a session.
    GET /tstation/messages/history/{session_id}
    """
    session_id = _get_or_create_session_id(session_id, access_token)
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(
            f"{BASE_URL}/tstation/messages/history/{session_id}",
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("messages", [])
    except Exception as e:
        st.error(f"Error getting history: {e}")
        return []


def delete_session(session_id: str, access_token: str) -> bool:
    """
    Delete a session and all its messages.
    DELETE /tstation/messages/{session_id}
    """
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.delete(
            f"{BASE_URL}/tstation/messages/{session_id}",
            headers=headers,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        st.error(f"Error deleting session: {e}")
        return False


def get_user_info(access_token: str) -> Dict:
    """
    Get user info from JWT token.
    GET /tstation/messages/user-info
    """
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(
            f"{BASE_URL}/tstation/messages/user-info",
            headers=headers,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error getting user info: {e}")
        return {}