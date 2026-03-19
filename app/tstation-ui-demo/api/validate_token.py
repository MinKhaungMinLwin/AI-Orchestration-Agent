"""Validate token API call."""
import requests
import os


def validate_token(access_token: str) -> dict:
    """
    Validate access token by calling the AI service API.

    Returns:
        dict with status and valid flag
    """
    base_url = "http://tstation-ai:8000/api"
    try:
        response = requests.post(
            f"{base_url}/tstation/validate-token",
            json={"access_token": access_token},
            timeout=10
        )
        return response.json()
    except Exception as e:
        return {"status": "error", "valid": False, "reason": str(e)}
