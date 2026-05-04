from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.discount_price_item import DiscountPriceItem


T = TypeVar("T", bound="DiscountPriceResponse")


@_attrs_define
class DiscountPriceResponse:
    """
    Attributes:
        quantity (int): 수량
        items (list[DiscountPriceItem]): 상품별 가격 정보
        cheapest_goods_no (None | str | Unset): 최저가 상품 번호
    """

    quantity: int
    items: list[DiscountPriceItem]
    cheapest_goods_no: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        quantity = self.quantity

        items = []
        for items_item_data in self.items:
            items_item = items_item_data.to_dict()
            items.append(items_item)

        cheapest_goods_no: None | str | Unset
        if isinstance(self.cheapest_goods_no, Unset):
            cheapest_goods_no = UNSET
        else:
            cheapest_goods_no = self.cheapest_goods_no

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "quantity": quantity,
                "items": items,
            }
        )
        if cheapest_goods_no is not UNSET:
            field_dict["cheapest_goods_no"] = cheapest_goods_no

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.discount_price_item import DiscountPriceItem

        d = dict(src_dict)
        quantity = d.pop("quantity")

        items = []
        _items = d.pop("items")
        for items_item_data in _items:
            items_item = DiscountPriceItem.from_dict(items_item_data)

            items.append(items_item)

        def _parse_cheapest_goods_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cheapest_goods_no = _parse_cheapest_goods_no(d.pop("cheapest_goods_no", UNSET))

        discount_price_response = cls(
            quantity=quantity,
            items=items,
            cheapest_goods_no=cheapest_goods_no,
        )

        discount_price_response.additional_properties = d
        return discount_price_response

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
