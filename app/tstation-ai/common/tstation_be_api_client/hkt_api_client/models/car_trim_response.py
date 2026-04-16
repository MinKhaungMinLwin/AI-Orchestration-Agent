from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.car_trim_item import CarTrimItem


T = TypeVar("T", bound="CarTrimResponse")


@_attrs_define
class CarTrimResponse:
    """
    Attributes:
        car_model_det (str): 차량 상세 모델명
        items (list[CarTrimItem]):
    """

    car_model_det: str
    items: list[CarTrimItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        car_model_det = self.car_model_det

        items = []
        for items_item_data in self.items:
            items_item = items_item_data.to_dict()
            items.append(items_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "car_model_det": car_model_det,
                "items": items,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.car_trim_item import CarTrimItem

        d = dict(src_dict)
        car_model_det = d.pop("car_model_det")

        items = []
        _items = d.pop("items")
        for items_item_data in _items:
            items_item = CarTrimItem.from_dict(items_item_data)

            items.append(items_item)

        car_trim_response = cls(
            car_model_det=car_model_det,
            items=items,
        )

        car_trim_response.additional_properties = d
        return car_trim_response

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
