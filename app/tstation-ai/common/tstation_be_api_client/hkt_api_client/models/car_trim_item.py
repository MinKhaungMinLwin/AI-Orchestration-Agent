from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CarTrimItem")


@_attrs_define
class CarTrimItem:
    """
    Attributes:
        car_lnc_cd (str): 차량 출시 코드
        car_nm (str): 차량명 (예: 'K7 2.4 GDI 프레스티지')
        car_year (int | None | Unset): 연식
        tire_size_fr (None | str | Unset): 전륜 타이어 사이즈 (예: 225/45R18)
        tire_size_re (None | str | Unset): 후륜 타이어 사이즈 (예: 225/45R18)
    """

    car_lnc_cd: str
    car_nm: str
    car_year: int | None | Unset = UNSET
    tire_size_fr: None | str | Unset = UNSET
    tire_size_re: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        car_lnc_cd = self.car_lnc_cd

        car_nm = self.car_nm

        car_year: int | None | Unset
        if isinstance(self.car_year, Unset):
            car_year = UNSET
        else:
            car_year = self.car_year

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
                "car_nm": car_nm,
            }
        )
        if car_year is not UNSET:
            field_dict["car_year"] = car_year
        if tire_size_fr is not UNSET:
            field_dict["tire_size_fr"] = tire_size_fr
        if tire_size_re is not UNSET:
            field_dict["tire_size_re"] = tire_size_re

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        car_lnc_cd = d.pop("car_lnc_cd")

        car_nm = d.pop("car_nm")

        def _parse_car_year(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        car_year = _parse_car_year(d.pop("car_year", UNSET))

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

        car_trim_item = cls(
            car_lnc_cd=car_lnc_cd,
            car_nm=car_nm,
            car_year=car_year,
            tire_size_fr=tire_size_fr,
            tire_size_re=tire_size_re,
        )

        car_trim_item.additional_properties = d
        return car_trim_item

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
