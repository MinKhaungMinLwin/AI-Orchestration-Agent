from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="MessageResponse")


@_attrs_define
class MessageResponse:
    """
    Attributes:
        msg_id (str): 메시지 고유 ID (UUID)
        session_id (str): 채팅 세션 ID
        role (str): 메시지 역할 (user / assistant)
        content (str): 메시지 내용
        status (str): 처리 상태 (received / completed / failed)
        created_at (str): 생성 일시 (YYYY-MM-DD HH24:MI:SS)
    """

    msg_id: str
    session_id: str
    role: str
    content: str
    status: str
    created_at: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        msg_id = self.msg_id

        session_id = self.session_id

        role = self.role

        content = self.content

        status = self.status

        created_at = self.created_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "msg_id": msg_id,
                "session_id": session_id,
                "role": role,
                "content": content,
                "status": status,
                "created_at": created_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        msg_id = d.pop("msg_id")

        session_id = d.pop("session_id")

        role = d.pop("role")

        content = d.pop("content")

        status = d.pop("status")

        created_at = d.pop("created_at")

        message_response = cls(
            msg_id=msg_id,
            session_id=session_id,
            role=role,
            content=content,
            status=status,
            created_at=created_at,
        )

        message_response.additional_properties = d
        return message_response

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
