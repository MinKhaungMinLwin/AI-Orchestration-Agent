"""
T-Station BE API Client with thread-local token support.
"""

import threading

from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from config.env import settings


class TstationBeClient:
    """
    Thread-safe client for tstation-be API with per-request access token.
    """
    _instance = None
    _lock = threading.Lock()
    _current_token = None

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def set_token(self, token: str | None) -> None:
        """Set access token for current thread."""
        self._current_token = token

    def get_client(self, token: str | None = None) -> AuthenticatedClient:
        """
        Get authenticated client with access token.

        Args:
            token: Explicit token. If None, uses stored token.

        Returns:
            AuthenticatedClient with Bearer token.
        """
        use_token = token if token is not None else self._current_token
        return AuthenticatedClient(
            base_url=settings.TSTATION_BE_API,
            token=use_token or "",
        )


# Singleton instance
_tstation_be_client = TstationBeClient()


def set_tstation_be_token(token: str | None) -> None:
    """Set access token for current request."""
    _tstation_be_client.set_token(token)


def get_tstation_be_client(token: str | None = None) -> AuthenticatedClient:
    """Get authenticated client with optional token."""
    return _tstation_be_client.get_client(token)
