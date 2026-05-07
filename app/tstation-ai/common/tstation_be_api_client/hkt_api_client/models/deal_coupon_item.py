from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="DealCouponItem")


@_attrs_define
class DealCouponItem:
    """
    Attributes:
        cpn_no (str): 쿠폰 번호
        cpn_knd_cd (None | str | Unset): 쿠폰 종류 코드 (예: C301=기획전쿠폰)
        cpn_prgs_stat_cd (None | str | Unset): 쿠폰 진행 상태 코드 (40=활성)
    """

    cpn_no: str
    cpn_knd_cd: None | str | Unset = UNSET
    cpn_prgs_stat_cd: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cpn_no = self.cpn_no

        cpn_knd_cd: None | str | Unset
        if isinstance(self.cpn_knd_cd, Unset):
            cpn_knd_cd = UNSET
        else:
            cpn_knd_cd = self.cpn_knd_cd

        cpn_prgs_stat_cd: None | str | Unset
        if isinstance(self.cpn_prgs_stat_cd, Unset):
            cpn_prgs_stat_cd = UNSET
        else:
            cpn_prgs_stat_cd = self.cpn_prgs_stat_cd

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "cpn_no": cpn_no,
            }
        )
        if cpn_knd_cd is not UNSET:
            field_dict["cpn_knd_cd"] = cpn_knd_cd
        if cpn_prgs_stat_cd is not UNSET:
            field_dict["cpn_prgs_stat_cd"] = cpn_prgs_stat_cd

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        cpn_no = d.pop("cpn_no")

        def _parse_cpn_knd_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cpn_knd_cd = _parse_cpn_knd_cd(d.pop("cpn_knd_cd", UNSET))

        def _parse_cpn_prgs_stat_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cpn_prgs_stat_cd = _parse_cpn_prgs_stat_cd(d.pop("cpn_prgs_stat_cd", UNSET))

        deal_coupon_item = cls(
            cpn_no=cpn_no,
            cpn_knd_cd=cpn_knd_cd,
            cpn_prgs_stat_cd=cpn_prgs_stat_cd,
        )

        deal_coupon_item.additional_properties = d
        return deal_coupon_item

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
