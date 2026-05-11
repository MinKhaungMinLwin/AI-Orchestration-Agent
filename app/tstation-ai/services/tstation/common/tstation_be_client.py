"""
T-Station BE API Client with shared connection pooling and backend latency tracing.
"""

import logging
import threading
import time
from typing import Any

import httpx

from common.tstation_be_api_client.hkt_api_client.client import AuthenticatedClient
from config.env import settings

logger = logging.getLogger(__name__)

_BE_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
_BE_HTTP_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=30.0)


class _InstrumentedBackendClient:
    """Per-token request adapter backed by a shared httpx.Client connection pool."""

    def __init__(self, shared_client: httpx.Client, token: str, prefix: str = "Bearer") -> None:
        self._shared_client = shared_client
        self._token = token
        self._prefix = prefix

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if self._token and "Authorization" not in headers:
            headers["Authorization"] = f"{self._prefix} {self._token}" if self._prefix else self._token

        start = time.perf_counter()
        status_code: int | str = "error"
        try:
            response = self._shared_client.request(method=method, url=url, headers=headers, **kwargs)
            status_code = response.status_code
            return response
        except httpx.TimeoutException:
            status_code = "timeout"
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "[TSTATION_BE] %s %s status=%s elapsed_ms=%.1f",
                method.upper(),
                url,
                status_code,
                elapsed_ms,
            )

    def close(self) -> None:
        """No-op: the singleton owns the shared connection pool lifecycle."""
        return None


class TstationBeClient:
    """
    Thread-safe client factory for tstation-be API with per-request access token.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_once()
        return cls._instance

    def _init_once(self) -> None:
        self._token_state = threading.local()
        self._shared_httpx_client = httpx.Client(
            base_url=settings.TSTATION_BE_API,
            timeout=_BE_HTTP_TIMEOUT,
            limits=_BE_HTTP_LIMITS,
        )

    def set_token(self, token: str | None) -> None:
        """Set access token for current thread."""
        self._token_state.token = token

    def get_client(self, token: str | None = None) -> AuthenticatedClient:
        """
        Get authenticated client with access token.

        Args:
            token: Explicit token. If None, uses token stored for current thread.

        Returns:
            AuthenticatedClient using the shared backend HTTP connection pool.
        """
        use_token = token if token is not None else getattr(self._token_state, "token", None)
        client = AuthenticatedClient(
            base_url=settings.TSTATION_BE_API,
            token=use_token or "",
            timeout=_BE_HTTP_TIMEOUT,
        )
        return client.set_httpx_client(_InstrumentedBackendClient(self._shared_httpx_client, use_token or ""))

    def close(self) -> None:
        """Close the shared backend HTTP connection pool."""
        self._shared_httpx_client.close()


# Singleton instance
_tstation_be_client = TstationBeClient()


def set_tstation_be_token(token: str | None) -> None:
    """Set access token for current request."""
    _tstation_be_client.set_token(token)


def get_tstation_be_client(token: str | None = None) -> AuthenticatedClient:
    """Get authenticated client with optional token."""
    return _tstation_be_client.get_client(token)


def close_tstation_be_client() -> None:
    """Close shared backend HTTP resources."""
    _tstation_be_client.close()
