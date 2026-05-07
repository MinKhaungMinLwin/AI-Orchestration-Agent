from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.best_seller_item import BestSellerItem


T = TypeVar("T", bound="BestSellerResponse")


@_attrs_define
class BestSellerResponse:
    """
    Attributes:
        period (str): 조회 기간 (day | week | month | 3months)
        total (int): 반환된 상품 수
        items (list[BestSellerItem]):
    """

    period: str
    total: int
    items: list[BestSellerItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        period = self.period

        total = self.total

        items = []
        for items_item_data in self.items:
            items_item = items_item_data.to_dict()
            items.append(items_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "period": period,
                "total": total,
                "items": items,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.best_seller_item import BestSellerItem

        d = dict(src_dict)
        period = d.pop("period")

        total = d.pop("total")

        items = []
        _items = d.pop("items")
        for items_item_data in _items:
            items_item = BestSellerItem.from_dict(items_item_data)

            items.append(items_item)

        best_seller_response = cls(
            period=period,
            total=total,
            items=items,
        )

        best_seller_response.additional_properties = d
        return best_seller_response

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
