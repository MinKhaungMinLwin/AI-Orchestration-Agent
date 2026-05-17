from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.cheapest_by_coupon_item import CheapestByCouponItem


T = TypeVar("T", bound="CheapestByCouponResponse")


@_attrs_define
class CheapestByCouponResponse:
    """
    Attributes:
        quantity (int): 수량
        items (list[CheapestByCouponItem]): 상품별 최저가 시뮬레이션 결과
    """

    quantity: int
    items: list[CheapestByCouponItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        quantity = self.quantity

        items = []
        for items_item_data in self.items:
            items_item = items_item_data.to_dict()
            items.append(items_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "quantity": quantity,
                "items": items,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.cheapest_by_coupon_item import CheapestByCouponItem

        d = dict(src_dict)
        quantity = d.pop("quantity")

        items = []
        _items = d.pop("items")
        for items_item_data in _items:
            items_item = CheapestByCouponItem.from_dict(items_item_data)

            items.append(items_item)

        cheapest_by_coupon_response = cls(
            quantity=quantity,
            items=items,
        )

        cheapest_by_coupon_response.additional_properties = d
        return cheapest_by_coupon_response

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
