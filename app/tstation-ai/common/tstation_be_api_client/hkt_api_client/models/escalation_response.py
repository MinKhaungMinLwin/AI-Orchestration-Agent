from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="EscalationResponse")


@_attrs_define
class EscalationResponse:
    """
    Attributes:
        channel (str): 상담 채널 (chat | call | email)
        branch (str): 분기 유형 (with_summary | direct | policy)
        has_summary (bool): 요약 내용 포함 여부
        redirect_url (str): 상담 페이지 URL (요약은 summary 쿼리 파라미터로 전달)
    """

    channel: str
    branch: str
    has_summary: bool
    redirect_url: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        channel = self.channel

        branch = self.branch

        has_summary = self.has_summary

        redirect_url = self.redirect_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "channel": channel,
                "branch": branch,
                "has_summary": has_summary,
                "redirect_url": redirect_url,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        channel = d.pop("channel")

        branch = d.pop("branch")

        has_summary = d.pop("has_summary")

        redirect_url = d.pop("redirect_url")

        escalation_response = cls(
            channel=channel,
            branch=branch,
            has_summary=has_summary,
            redirect_url=redirect_url,
        )

        escalation_response.additional_properties = d
        return escalation_response

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
