from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="CarModelSearchItem")


@_attrs_define
class CarModelSearchItem:
    """
    Attributes:
        car_lnc_cd (str): 차량 출시 코드
        car_nm (str): 차량명
    """

    car_lnc_cd: str
    car_nm: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        car_lnc_cd = self.car_lnc_cd

        car_nm = self.car_nm

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "car_lnc_cd": car_lnc_cd,
                "car_nm": car_nm,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        car_lnc_cd = d.pop("car_lnc_cd")

        car_nm = d.pop("car_nm")

        car_model_search_item = cls(
            car_lnc_cd=car_lnc_cd,
            car_nm=car_nm,
        )

        car_model_search_item.additional_properties = d
        return car_model_search_item

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
