from __future__ import annotations

from fastapi import Request
import pytest

from api.tstation import chat_message as chat_message_module
from schemas.tstation.chat_message import AppendMessageRequest, ChatMessageResponse


def _request() -> Request:
    return Request(
        scope={
            "type": "http",
            "method": "POST",
            "path": "/api/tstation/messages/append",
            "headers": [],
        }
    )


def test_append_request_to_chat_body_uses_template_structured_fields() -> None:
    request = AppendMessageRequest(
        session_id="s1",
        content="다이나프로 HPX 255/55R18",
        role="user",
        template_data={
            "chip_context": {"cta_action": "select_product"},
            "ui_action": {
                "action_type": "select_product",
                "slots": {"goods_no": "G000000317729"},
            },
            "slots": {"goods_no": "G000000317729"},
        },
    )

    assert chat_message_module._append_should_route_to_chat(request) is True

    chat_body = chat_message_module._append_request_to_chat_body(request)

    assert chat_body.content == "다이나프로 HPX 255/55R18"
    assert chat_body.ui_action["action_type"] == "select_product"
    assert chat_body.slots == {"goods_no": "G000000317729"}
    assert chat_body.chip_context.model_dump()["cta_action"] == "select_product"


@pytest.mark.asyncio
async def test_append_message_routes_structured_user_selection_to_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(chat_message_module, "get_chat_history_service", lambda: object())
    monkeypatch.setattr(chat_message_module, "_ensure_session_owner", lambda *args, **kwargs: None)

    async def fake_chat(chat_body, http_request, user):
        seen["chat_body"] = chat_body
        seen["http_request"] = http_request
        seen["user"] = user
        return ChatMessageResponse(
            session_id="s1",
            message_id="m1",
            role="user",
            content=chat_body.content,
            created_at="2026-07-07T00:00:00",
        )

    monkeypatch.setattr(chat_message_module, "chat", fake_chat)

    response = await chat_message_module.append_message(
        AppendMessageRequest(
            session_id="s1",
            content="다이나프로 HPX 255/55R18",
            role="user",
            ui_action={"action_type": "select_product", "slots": {"goods_no": "G000000317729"}},
            slots={"goods_no": "G000000317729"},
        ),
        _request(),
        {"user_id": "u1", "token": "tok"},
    )

    assert response.message_id == "m1"
    assert seen["chat_body"].ui_action["action_type"] == "select_product"
    assert seen["chat_body"].slots["goods_no"] == "G000000317729"


@pytest.mark.asyncio
async def test_append_message_keeps_plain_append_path(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyService:
        def save_message(self, **kwargs):
            return "saved-message"

    monkeypatch.setattr(chat_message_module, "get_chat_history_service", lambda: DummyService())
    monkeypatch.setattr(chat_message_module, "_ensure_session_owner", lambda *args, **kwargs: None)

    response = await chat_message_module.append_message(
        AppendMessageRequest(
            session_id="s1",
            content="컴포트",
            role="user",
            template_data={"label": "컴포트"},
        ),
        _request(),
        {"user_id": "u1", "token": "tok"},
    )

    assert response.success is True
    assert response.msg_id == "saved-message"
