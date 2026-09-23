from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.coupon_applicable_product_item import CouponApplicableProductItem


T = TypeVar("T", bound="DealApplicableProductsGroup")


@_attrs_define
class DealApplicableProductsGroup:
    """
    Attributes:
        deal_no (str): 기획전 번호
        total (int): 해당 기획전에 매핑된 쿠폰을 통해 적용 가능한 상품 수
        items (list[CouponApplicableProductItem] | Unset): 해당 기획전에 적용 가능한 패턴 대표 상품 목록
    """

    deal_no: str
    total: int
    items: list[CouponApplicableProductItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        deal_no = self.deal_no

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
                "deal_no": deal_no,
                "total": total,
            }
        )
        if items is not UNSET:
            field_dict["items"] = items

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.coupon_applicable_product_item import CouponApplicableProductItem

        d = dict(src_dict)
        deal_no = d.pop("deal_no")

        total = d.pop("total")

        _items = d.pop("items", UNSET)
        items: list[CouponApplicableProductItem] | Unset = UNSET
        if _items is not UNSET:
            items = []
            for items_item_data in _items:
                items_item = CouponApplicableProductItem.from_dict(items_item_data)

                items.append(items_item)

        deal_applicable_products_group = cls(
            deal_no=deal_no,
            total=total,
            items=items,
        )

        deal_applicable_products_group.additional_properties = d
        return deal_applicable_products_group

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
