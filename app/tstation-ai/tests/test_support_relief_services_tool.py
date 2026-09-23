from __future__ import annotations

from services.tstation.agents.e_support_agent import tools


class _ParsedReliefServices:
    def to_dict(self) -> dict:
        return {
            "relief_services": [
                {
                    "ord_no": "O001",
                    "join_dtime": "2026-07-01 09:00:00",
                    "equp_conf_dtime": "2026-07-02T10:30:00",
                    "relief_svc_dtime": "2026-08-10 11:12:13",
                    "relief_end_dtime": "2026-08-12 23:59:59",
                    "relief_state_nm": "가입완료",
                }
            ]
        }


class _Response:
    status_code = 200
    parsed = _ParsedReliefServices()


def test_get_my_relief_services_tool_returns_date_only_fields(monkeypatch) -> None:
    def fake_get_my_relief_services(*, client):
        return _Response()

    monkeypatch.setattr(tools, "get_my_relief_services", fake_get_my_relief_services)
    monkeypatch.setattr(tools, "get_client", lambda: object())

    result = tools.get_my_relief_services_tool.func()

    item = result["data"]["relief_services"][0]
    assert item["join_dtime"] == "2026-07-01"
    assert item["equp_conf_dtime"] == "2026-07-02"
    assert item["relief_svc_dtime"] == "2026-08-10"
    assert item["relief_end_dtime"] == "2026-08-12"
