from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.my_coupon_item import MyCouponItem


T = TypeVar("T", bound="MyCouponResponse")


@_attrs_define
class MyCouponResponse:
    """
    Attributes:
        coupons (list[MyCouponItem]):
    """

    coupons: list[MyCouponItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        coupons = []
        for coupons_item_data in self.coupons:
            coupons_item = coupons_item_data.to_dict()
            coupons.append(coupons_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "coupons": coupons,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.my_coupon_item import MyCouponItem

        d = dict(src_dict)
        coupons = []
        _coupons = d.pop("coupons")
        for coupons_item_data in _coupons:
            coupons_item = MyCouponItem.from_dict(coupons_item_data)

            coupons.append(coupons_item)

        my_coupon_response = cls(
            coupons=coupons,
        )

        my_coupon_response.additional_properties = d
        return my_coupon_response

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
