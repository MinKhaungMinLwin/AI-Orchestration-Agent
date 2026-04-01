from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="SessionInfo")


@_attrs_define
class SessionInfo:
    """
    Attributes:
        session_id (str): 채팅 세션 ID
        last_message_at (str): 마지막 메시지 일시 (YYYY-MM-DD HH24:MI:SS)
        msg_count (int): 세션 내 메시지 수
    """

    session_id: str
    last_message_at: str
    msg_count: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        session_id = self.session_id

        last_message_at = self.last_message_at

        msg_count = self.msg_count

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "session_id": session_id,
                "last_message_at": last_message_at,
                "msg_count": msg_count,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        session_id = d.pop("session_id")

        last_message_at = d.pop("last_message_at")

        msg_count = d.pop("msg_count")

        session_info = cls(
            session_id=session_id,
            last_message_at=last_message_at,
            msg_count=msg_count,
        )

        session_info.additional_properties = d
        return session_info

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
