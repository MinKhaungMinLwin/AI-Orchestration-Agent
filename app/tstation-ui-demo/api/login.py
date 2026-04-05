"""Login service for tstation.com to get access token."""

import requests
from typing import Optional


class TstationLoginService:
    """Service to handle login to tstation.com and get access token."""

    def __init__(self, base_url: str = "https://wwwqa.tstation.com"):
        self.base_url = base_url
        self.session = requests.Session()

    def get_access_token(self) -> Optional[str]:
        """
        Get access token from tstation.com.
        Requires user to be logged in first (cookies/session).

        Returns:
            Access token string if successful, None otherwise.
        """
        try:
            response = self.session.get(
                f"{self.base_url}/member/chatbotTokenJson.do",
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            if data.get("result") is True:
                return data.get("accessToken")
            return None
        except Exception:
            return None

    def is_logged_in(self) -> bool:
        """Check if session is logged in by trying to get access token."""
        token = self.get_access_token()
        return token is not None


def get_tstation_login_service() -> TstationLoginService:
    """Get a TstationLoginService instance."""
    return TstationLoginService()
