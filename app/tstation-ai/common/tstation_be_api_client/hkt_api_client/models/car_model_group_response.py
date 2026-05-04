from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.car_model_group import CarModelGroup


T = TypeVar("T", bound="CarModelGroupResponse")


@_attrs_define
class CarModelGroupResponse:
    """
    Attributes:
        keyword (str): 검색한 차량 모델명 키워드
        items (list[CarModelGroup]):
    """

    keyword: str
    items: list[CarModelGroup]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        keyword = self.keyword

        items = []
        for items_item_data in self.items:
            items_item = items_item_data.to_dict()
            items.append(items_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "keyword": keyword,
                "items": items,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.car_model_group import CarModelGroup

        d = dict(src_dict)
        keyword = d.pop("keyword")

        items = []
        _items = d.pop("items")
        for items_item_data in _items:
            items_item = CarModelGroup.from_dict(items_item_data)

            items.append(items_item)

        car_model_group_response = cls(
            keyword=keyword,
            items=items,
        )

        car_model_group_response.additional_properties = d
        return car_model_group_response

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
