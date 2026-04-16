from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CarTireSizeResponse")


@_attrs_define
class CarTireSizeResponse:
    """
    Attributes:
        car_lnc_cd (str): 차량 출시 코드
        tire_size_fr (None | str | Unset): 전륜 타이어 사이즈 (예: 225/45R18)
        tire_size_re (None | str | Unset): 후륜 타이어 사이즈 (예: 225/45R18)
    """

    car_lnc_cd: str
    tire_size_fr: None | str | Unset = UNSET
    tire_size_re: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        car_lnc_cd = self.car_lnc_cd

        tire_size_fr: None | str | Unset
        if isinstance(self.tire_size_fr, Unset):
            tire_size_fr = UNSET
        else:
            tire_size_fr = self.tire_size_fr

        tire_size_re: None | str | Unset
        if isinstance(self.tire_size_re, Unset):
            tire_size_re = UNSET
        else:
            tire_size_re = self.tire_size_re

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "car_lnc_cd": car_lnc_cd,
            }
        )
        if tire_size_fr is not UNSET:
            field_dict["tire_size_fr"] = tire_size_fr
        if tire_size_re is not UNSET:
            field_dict["tire_size_re"] = tire_size_re

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        car_lnc_cd = d.pop("car_lnc_cd")

        def _parse_tire_size_fr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tire_size_fr = _parse_tire_size_fr(d.pop("tire_size_fr", UNSET))

        def _parse_tire_size_re(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tire_size_re = _parse_tire_size_re(d.pop("tire_size_re", UNSET))

        car_tire_size_response = cls(
            car_lnc_cd=car_lnc_cd,
            tire_size_fr=tire_size_fr,
            tire_size_re=tire_size_re,
        )

        car_tire_size_response.additional_properties = d
        return car_tire_size_response

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
