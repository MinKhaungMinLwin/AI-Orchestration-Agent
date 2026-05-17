from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.applied_coupon_item import AppliedCouponItem


T = TypeVar("T", bound="CheapestByCouponItem")


@_attrs_define
class CheapestByCouponItem:
    """
    Attributes:
        goods_no (str): 상품 번호
        sale_prc (int): 판매가 (단가)
        total_discount (int): 총 할인 (단가, sale_prc - final_prc)
        final_prc (int): 최종 혜택가 (단가)
        goods_nm (None | str | Unset): 상품명
        applied_coupons (list[AppliedCouponItem] | Unset): 단계별로 적용된 쿠폰 리스트 (AI 가 텍스트 답변에 인용)
    """

    goods_no: str
    sale_prc: int
    total_discount: int
    final_prc: int
    goods_nm: None | str | Unset = UNSET
    applied_coupons: list[AppliedCouponItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_no = self.goods_no

        sale_prc = self.sale_prc

        total_discount = self.total_discount

        final_prc = self.final_prc

        goods_nm: None | str | Unset
        if isinstance(self.goods_nm, Unset):
            goods_nm = UNSET
        else:
            goods_nm = self.goods_nm

        applied_coupons: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.applied_coupons, Unset):
            applied_coupons = []
            for applied_coupons_item_data in self.applied_coupons:
                applied_coupons_item = applied_coupons_item_data.to_dict()
                applied_coupons.append(applied_coupons_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goods_no": goods_no,
                "sale_prc": sale_prc,
                "total_discount": total_discount,
                "final_prc": final_prc,
            }
        )
        if goods_nm is not UNSET:
            field_dict["goods_nm"] = goods_nm
        if applied_coupons is not UNSET:
            field_dict["applied_coupons"] = applied_coupons

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.applied_coupon_item import AppliedCouponItem

        d = dict(src_dict)
        goods_no = d.pop("goods_no")

        sale_prc = d.pop("sale_prc")

        total_discount = d.pop("total_discount")

        final_prc = d.pop("final_prc")

        def _parse_goods_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        goods_nm = _parse_goods_nm(d.pop("goods_nm", UNSET))

        _applied_coupons = d.pop("applied_coupons", UNSET)
        applied_coupons: list[AppliedCouponItem] | Unset = UNSET
        if _applied_coupons is not UNSET:
            applied_coupons = []
            for applied_coupons_item_data in _applied_coupons:
                applied_coupons_item = AppliedCouponItem.from_dict(applied_coupons_item_data)

                applied_coupons.append(applied_coupons_item)

        cheapest_by_coupon_item = cls(
            goods_no=goods_no,
            sale_prc=sale_prc,
            total_discount=total_discount,
            final_prc=final_prc,
            goods_nm=goods_nm,
            applied_coupons=applied_coupons,
        )

        cheapest_by_coupon_item.additional_properties = d
        return cheapest_by_coupon_item

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
