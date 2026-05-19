from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.car_maintenance_dday import CarMaintenanceDday


T = TypeVar("T", bound="MaintenanceDdayResponse")


@_attrs_define
class MaintenanceDdayResponse:
    """
    Attributes:
        cars (list[CarMaintenanceDday] | Unset): 회원의 등록차량별 정비 D-day 매트릭스
    """

    cars: list[CarMaintenanceDday] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cars: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.cars, Unset):
            cars = []
            for cars_item_data in self.cars:
                cars_item = cars_item_data.to_dict()
                cars.append(cars_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if cars is not UNSET:
            field_dict["cars"] = cars

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.car_maintenance_dday import CarMaintenanceDday

        d = dict(src_dict)
        _cars = d.pop("cars", UNSET)
        cars: list[CarMaintenanceDday] | Unset = UNSET
        if _cars is not UNSET:
            cars = []
            for cars_item_data in _cars:
                cars_item = CarMaintenanceDday.from_dict(cars_item_data)

                cars.append(cars_item)

        maintenance_dday_response = cls(
            cars=cars,
        )

        maintenance_dday_response.additional_properties = d
        return maintenance_dday_response

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
