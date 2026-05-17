from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.coupon_applicable_store_item import CouponApplicableStoreItem


T = TypeVar("T", bound="CouponApplicableStoresGroup")


@_attrs_define
class CouponApplicableStoresGroup:
    """
    Attributes:
        cpn_no (str): 쿠폰 번호
        total (int): 해당 쿠폰에 매핑된 적용 가능 매장 수
        items (list[CouponApplicableStoreItem] | Unset): 해당 쿠폰에 적용 가능한 매장 목록 (TGT_SCT_CD='90' 매핑)
    """

    cpn_no: str
    total: int
    items: list[CouponApplicableStoreItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cpn_no = self.cpn_no

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
                "cpn_no": cpn_no,
                "total": total,
            }
        )
        if items is not UNSET:
            field_dict["items"] = items

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.coupon_applicable_store_item import CouponApplicableStoreItem

        d = dict(src_dict)
        cpn_no = d.pop("cpn_no")

        total = d.pop("total")

        _items = d.pop("items", UNSET)
        items: list[CouponApplicableStoreItem] | Unset = UNSET
        if _items is not UNSET:
            items = []
            for items_item_data in _items:
                items_item = CouponApplicableStoreItem.from_dict(items_item_data)

                items.append(items_item)

        coupon_applicable_stores_group = cls(
            cpn_no=cpn_no,
            total=total,
            items=items,
        )

        coupon_applicable_stores_group.additional_properties = d
        return coupon_applicable_stores_group

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
