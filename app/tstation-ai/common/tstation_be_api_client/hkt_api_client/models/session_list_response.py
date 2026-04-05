from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.session_info import SessionInfo


T = TypeVar("T", bound="SessionListResponse")


@_attrs_define
class SessionListResponse:
    """
    Attributes:
        user_id (str): 회원번호
        total_sessions (int): 전체 세션 수
        sessions (list[SessionInfo] | Unset): 세션 목록 (last_message_at 내림차순)
    """

    user_id: str
    total_sessions: int
    sessions: list[SessionInfo] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        user_id = self.user_id

        total_sessions = self.total_sessions

        sessions: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.sessions, Unset):
            sessions = []
            for sessions_item_data in self.sessions:
                sessions_item = sessions_item_data.to_dict()
                sessions.append(sessions_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "user_id": user_id,
                "total_sessions": total_sessions,
            }
        )
        if sessions is not UNSET:
            field_dict["sessions"] = sessions

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.session_info import SessionInfo

        d = dict(src_dict)
        user_id = d.pop("user_id")

        total_sessions = d.pop("total_sessions")

        _sessions = d.pop("sessions", UNSET)
        sessions: list[SessionInfo] | Unset = UNSET
        if _sessions is not UNSET:
            sessions = []
            for sessions_item_data in _sessions:
                sessions_item = SessionInfo.from_dict(sessions_item_data)

                sessions.append(sessions_item)

        session_list_response = cls(
            user_id=user_id,
            total_sessions=total_sessions,
            sessions=sessions,
        )

        session_list_response.additional_properties = d
        return session_list_response

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
