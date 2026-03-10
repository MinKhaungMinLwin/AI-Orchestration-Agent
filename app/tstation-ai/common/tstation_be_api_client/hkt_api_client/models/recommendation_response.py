from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.rcmd_goods_item import RcmdGoodsItem


T = TypeVar("T", bound="RecommendationResponse")


@_attrs_define
class RecommendationResponse:
    """
    Attributes:
        rcmd_type (str): 추천 타입 (tstation | discount | value)
        total (int): 반환된 상품 수
        items (list[RcmdGoodsItem]):
    """

    rcmd_type: str
    total: int
    items: list[RcmdGoodsItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rcmd_type = self.rcmd_type

        total = self.total

        items = []
        for items_item_data in self.items:
            items_item = items_item_data.to_dict()
            items.append(items_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rcmd_type": rcmd_type,
                "total": total,
                "items": items,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.rcmd_goods_item import RcmdGoodsItem

        d = dict(src_dict)
        rcmd_type = d.pop("rcmd_type")

        total = d.pop("total")

        items = []
        _items = d.pop("items")
        for items_item_data in _items:
            items_item = RcmdGoodsItem.from_dict(items_item_data)

            items.append(items_item)

        recommendation_response = cls(
            rcmd_type=rcmd_type,
            total=total,
            items=items,
        )

        recommendation_response.additional_properties = d
        return recommendation_response

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
