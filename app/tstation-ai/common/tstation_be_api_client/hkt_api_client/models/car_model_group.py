from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CarModelGroup")


@_attrs_define
class CarModelGroup:
    """
    Attributes:
        car_model_det (str): 차량 상세 모델명 (예: '더 뉴 K7(VG)')
        trim_count (int): 해당 그룹 내 트림 수
        year_from (int | None | Unset): 최소 연식
        year_to (int | None | Unset): 최대 연식
    """

    car_model_det: str
    trim_count: int
    year_from: int | None | Unset = UNSET
    year_to: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        car_model_det = self.car_model_det

        trim_count = self.trim_count

        year_from: int | None | Unset
        if isinstance(self.year_from, Unset):
            year_from = UNSET
        else:
            year_from = self.year_from

        year_to: int | None | Unset
        if isinstance(self.year_to, Unset):
            year_to = UNSET
        else:
            year_to = self.year_to

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "car_model_det": car_model_det,
                "trim_count": trim_count,
            }
        )
        if year_from is not UNSET:
            field_dict["year_from"] = year_from
        if year_to is not UNSET:
            field_dict["year_to"] = year_to

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        car_model_det = d.pop("car_model_det")

        trim_count = d.pop("trim_count")

        def _parse_year_from(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        year_from = _parse_year_from(d.pop("year_from", UNSET))

        def _parse_year_to(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        year_to = _parse_year_to(d.pop("year_to", UNSET))

        car_model_group = cls(
            car_model_det=car_model_det,
            trim_count=trim_count,
            year_from=year_from,
            year_to=year_to,
        )

        car_model_group.additional_properties = d
        return car_model_group

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
