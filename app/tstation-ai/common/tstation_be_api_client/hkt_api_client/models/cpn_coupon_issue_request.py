from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="CpnCouponIssueRequest")


@_attrs_define
class CpnCouponIssueRequest:
    """쿠폰번호 기반 발급 — 지정 쿠폰 단일 발급.

    Attributes:
        cpn_no (str): 쿠폰 번호
    """

    cpn_no: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cpn_no = self.cpn_no

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "cpn_no": cpn_no,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        cpn_no = d.pop("cpn_no")

        cpn_coupon_issue_request = cls(
            cpn_no=cpn_no,
        )

        cpn_coupon_issue_request.additional_properties = d
        return cpn_coupon_issue_request

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
