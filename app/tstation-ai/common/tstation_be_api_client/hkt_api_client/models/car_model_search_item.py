from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CarModelSearchItem")


@_attrs_define
class CarModelSearchItem:
    """
    Attributes:
        car_lnc_cd (str): 차량 출시 코드
        car_nm (str): 차량명
        car_model_det (None | str | Unset): 차량 상세 모델명
    """

    car_lnc_cd: str
    car_nm: str
    car_model_det: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        car_lnc_cd = self.car_lnc_cd

        car_nm = self.car_nm

        car_model_det: None | str | Unset
        if isinstance(self.car_model_det, Unset):
            car_model_det = UNSET
        else:
            car_model_det = self.car_model_det

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "car_lnc_cd": car_lnc_cd,
                "car_nm": car_nm,
            }
        )
        if car_model_det is not UNSET:
            field_dict["car_model_det"] = car_model_det

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        car_lnc_cd = d.pop("car_lnc_cd")

        car_nm = d.pop("car_nm")

        def _parse_car_model_det(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_model_det = _parse_car_model_det(d.pop("car_model_det", UNSET))

        car_model_search_item = cls(
            car_lnc_cd=car_lnc_cd,
            car_nm=car_nm,
            car_model_det=car_model_det,
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
