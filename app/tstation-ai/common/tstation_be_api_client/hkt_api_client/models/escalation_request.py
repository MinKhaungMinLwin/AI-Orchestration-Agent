from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="EscalationRequest")


@_attrs_define
class EscalationRequest:
    """
    Attributes:
        mbr_no (None | str | Unset): 회원 번호 (상담 페이지 전달용)
        inq_type_cd (None | str | Unset): 문의 유형 코드 (정책 기반 채널 분기에 사용)
        msg_count (int | Unset): 현재까지의 대화 메시지 수 Default: 0.
        summary (None | str | Unset): AI가 생성한 대화 요약 (대화량 충분 시 전달)
    """

    mbr_no: None | str | Unset = UNSET
    inq_type_cd: None | str | Unset = UNSET
    msg_count: int | Unset = 0
    summary: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        mbr_no: None | str | Unset
        if isinstance(self.mbr_no, Unset):
            mbr_no = UNSET
        else:
            mbr_no = self.mbr_no

        inq_type_cd: None | str | Unset
        if isinstance(self.inq_type_cd, Unset):
            inq_type_cd = UNSET
        else:
            inq_type_cd = self.inq_type_cd

        msg_count = self.msg_count

        summary: None | str | Unset
        if isinstance(self.summary, Unset):
            summary = UNSET
        else:
            summary = self.summary

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if mbr_no is not UNSET:
            field_dict["mbr_no"] = mbr_no
        if inq_type_cd is not UNSET:
            field_dict["inq_type_cd"] = inq_type_cd
        if msg_count is not UNSET:
            field_dict["msg_count"] = msg_count
        if summary is not UNSET:
            field_dict["summary"] = summary

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_mbr_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mbr_no = _parse_mbr_no(d.pop("mbr_no", UNSET))

        def _parse_inq_type_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        inq_type_cd = _parse_inq_type_cd(d.pop("inq_type_cd", UNSET))

        msg_count = d.pop("msg_count", UNSET)

        def _parse_summary(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        summary = _parse_summary(d.pop("summary", UNSET))

        escalation_request = cls(
            mbr_no=mbr_no,
            inq_type_cd=inq_type_cd,
            msg_count=msg_count,
            summary=summary,
        )

        escalation_request.additional_properties = d
        return escalation_request

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
