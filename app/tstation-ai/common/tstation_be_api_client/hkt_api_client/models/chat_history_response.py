from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.message_response import MessageResponse


T = TypeVar("T", bound="ChatHistoryResponse")


@_attrs_define
class ChatHistoryResponse:
    """
    Attributes:
        session_id (str): 채팅 세션 ID
        total (int): 메시지 수
        messages (list[MessageResponse] | Unset): 메시지 목록 (CREATED_AT 오름차순)
    """

    session_id: str
    total: int
    messages: list[MessageResponse] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        session_id = self.session_id

        total = self.total

        messages: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.messages, Unset):
            messages = []
            for messages_item_data in self.messages:
                messages_item = messages_item_data.to_dict()
                messages.append(messages_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "session_id": session_id,
                "total": total,
            }
        )
        if messages is not UNSET:
            field_dict["messages"] = messages

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.message_response import MessageResponse

        d = dict(src_dict)
        session_id = d.pop("session_id")

        total = d.pop("total")

        _messages = d.pop("messages", UNSET)
        messages: list[MessageResponse] | Unset = UNSET
        if _messages is not UNSET:
            messages = []
            for messages_item_data in _messages:
                messages_item = MessageResponse.from_dict(messages_item_data)

                messages.append(messages_item)

        chat_history_response = cls(
            session_id=session_id,
            total=total,
            messages=messages,
        )

        chat_history_response.additional_properties = d
        return chat_history_response

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
