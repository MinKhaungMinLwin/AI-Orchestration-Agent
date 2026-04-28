from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CouponResultItem")


@_attrs_define
class CouponResultItem:
    """단일 쿠폰 발급 결과.

    Attributes:
        code (str): 발급 결과 코드 (100: 성공, 900: 실패)
        cpn_no (None | str | Unset): 쿠폰 번호
        message (None | str | Unset): 실패 시 메시지
        cpn_issu_no (None | str | Unset): 발급 성공 시 쿠폰 발급 번호
    """

    code: str
    cpn_no: None | str | Unset = UNSET
    message: None | str | Unset = UNSET
    cpn_issu_no: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        cpn_no: None | str | Unset
        if isinstance(self.cpn_no, Unset):
            cpn_no = UNSET
        else:
            cpn_no = self.cpn_no

        message: None | str | Unset
        if isinstance(self.message, Unset):
            message = UNSET
        else:
            message = self.message

        cpn_issu_no: None | str | Unset
        if isinstance(self.cpn_issu_no, Unset):
            cpn_issu_no = UNSET
        else:
            cpn_issu_no = self.cpn_issu_no

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
            }
        )
        if cpn_no is not UNSET:
            field_dict["cpn_no"] = cpn_no
        if message is not UNSET:
            field_dict["message"] = message
        if cpn_issu_no is not UNSET:
            field_dict["cpn_issu_no"] = cpn_issu_no

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        code = d.pop("code")

        def _parse_cpn_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cpn_no = _parse_cpn_no(d.pop("cpn_no", UNSET))

        def _parse_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message = _parse_message(d.pop("message", UNSET))

        def _parse_cpn_issu_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cpn_issu_no = _parse_cpn_issu_no(d.pop("cpn_issu_no", UNSET))

        coupon_result_item = cls(
            code=code,
            cpn_no=cpn_no,
            message=message,
            cpn_issu_no=cpn_issu_no,
        )

        coupon_result_item.additional_properties = d
        return coupon_result_item

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
