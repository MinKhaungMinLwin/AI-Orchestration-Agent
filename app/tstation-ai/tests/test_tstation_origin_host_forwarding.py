from types import SimpleNamespace

from api.tstation.chat_message import _normalize_tstation_origin_host
from services.tstation.common.tstation_be_client import _InstrumentedBackendClient, set_tstation_origin_host


class _FakeSharedClient:
    def __init__(self):
        self.last_request = None

    def request(self, **kwargs):
        self.last_request = kwargs
        return SimpleNamespace(status_code=200)


def test_chat_origin_host_normalizer_allows_tstation_domains_only() -> None:
    assert _normalize_tstation_origin_host("https://wwwqa.tstation.com/product") == "wwwqa.tstation.com"
    assert _normalize_tstation_origin_host("https://mqa.tstation.com") == "mqa.tstation.com"
    assert _normalize_tstation_origin_host("mbiz.tstation.com:443") == "mbiz.tstation.com"
    assert _normalize_tstation_origin_host("https://bizqa.tstation.com/order") == "bizqa.tstation.com"
    assert _normalize_tstation_origin_host("https://www.tstation.com") == "www.tstation.com"
    assert _normalize_tstation_origin_host("https://m.tstation.com/product") == "m.tstation.com"
    assert _normalize_tstation_origin_host("https://biz.tstation.com/order") == "biz.tstation.com"
    assert _normalize_tstation_origin_host("https://evil.example.com") is None


def test_backend_client_forwards_origin_host_header() -> None:
    set_tstation_origin_host("mqa.tstation.com")
    shared_client = _FakeSharedClient()
    client = _InstrumentedBackendClient(shared_client, token="token-value")

    response = client.request("POST", "http://backend/api/quick-order/order/setOrderFormAI.do", json={})

    assert response.status_code == 200
    assert shared_client.last_request["headers"]["Authorization"] == "Bearer token-value"
    assert shared_client.last_request["headers"]["X-TStation-Origin-Host"] == "mqa.tstation.com"
