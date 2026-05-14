from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.deal_with_coupons_item import DealWithCouponsItem


T = TypeVar("T", bound="ProductDealsResponse")


@_attrs_define
class ProductDealsResponse:
    """
    Attributes:
        goods_no (str): 상품 번호
        total (int): 반환된 기획전 수
        items (list[DealWithCouponsItem] | Unset): 상품에 적용 가능한 진행 중 기획전 목록
    """

    goods_no: str
    total: int
    items: list[DealWithCouponsItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_no = self.goods_no

        total = self.total

        items: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.items, Unset):
            items = []
            for items_item_data in self.items:
                items_item = items_item_data.to_dict()
                items.append(items_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goods_no": goods_no,
                "total": total,
            }
        )
        if items is not UNSET:
            field_dict["items"] = items

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.deal_with_coupons_item import DealWithCouponsItem

        d = dict(src_dict)
        goods_no = d.pop("goods_no")

        total = d.pop("total")

        _items = d.pop("items", UNSET)
        items: list[DealWithCouponsItem] | Unset = UNSET
        if _items is not UNSET:
            items = []
            for items_item_data in _items:
                items_item = DealWithCouponsItem.from_dict(items_item_data)

                items.append(items_item)

        product_deals_response = cls(
            goods_no=goods_no,
            total=total,
            items=items,
        )

        product_deals_response.additional_properties = d
        return product_deals_response

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
