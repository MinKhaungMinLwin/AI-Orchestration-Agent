from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="DiscountPriceItem")


@_attrs_define
class DiscountPriceItem:
    """
    Attributes:
        goods_no (str): 상품 번호
        sale_prc (int): 정가 (단가)
        product_discount (int): 상품할인 (단가, SALE_PRC - MAX_FVR_SALE_PRC)
        coupon_discount (int): 쿠폰할인 (단가, 할인 - 상품할인)
        total_discount (int): 총 할인 (단가, SALE_PRC - EXTRA_FVR_SALE_PRC)
        final_unit_price (int): 최종 단가 (EXTRA_FVR_SALE_PRC)
        total_product_price (int): 총 상품가 (final_unit_price × quantity)
        total_wage (int): 총 공임비
        final_price (int): 최종 결제금액 (총 상품가 + 총 공임비)
        wage_prc (int | None | Unset): 공임비 (단가)
        wage_today_prc (int | None | Unset): 오늘의 공임비 (단가)
    """

    goods_no: str
    sale_prc: int
    product_discount: int
    coupon_discount: int
    total_discount: int
    final_unit_price: int
    total_product_price: int
    total_wage: int
    final_price: int
    wage_prc: int | None | Unset = UNSET
    wage_today_prc: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_no = self.goods_no

        sale_prc = self.sale_prc

        product_discount = self.product_discount

        coupon_discount = self.coupon_discount

        total_discount = self.total_discount

        final_unit_price = self.final_unit_price

        total_product_price = self.total_product_price

        total_wage = self.total_wage

        final_price = self.final_price

        wage_prc: int | None | Unset
        if isinstance(self.wage_prc, Unset):
            wage_prc = UNSET
        else:
            wage_prc = self.wage_prc

        wage_today_prc: int | None | Unset
        if isinstance(self.wage_today_prc, Unset):
            wage_today_prc = UNSET
        else:
            wage_today_prc = self.wage_today_prc

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goods_no": goods_no,
                "sale_prc": sale_prc,
                "product_discount": product_discount,
                "coupon_discount": coupon_discount,
                "total_discount": total_discount,
                "final_unit_price": final_unit_price,
                "total_product_price": total_product_price,
                "total_wage": total_wage,
                "final_price": final_price,
            }
        )
        if wage_prc is not UNSET:
            field_dict["wage_prc"] = wage_prc
        if wage_today_prc is not UNSET:
            field_dict["wage_today_prc"] = wage_today_prc

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        goods_no = d.pop("goods_no")

        sale_prc = d.pop("sale_prc")

        product_discount = d.pop("product_discount")

        coupon_discount = d.pop("coupon_discount")

        total_discount = d.pop("total_discount")

        final_unit_price = d.pop("final_unit_price")

        total_product_price = d.pop("total_product_price")

        total_wage = d.pop("total_wage")

        final_price = d.pop("final_price")

        def _parse_wage_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        wage_prc = _parse_wage_prc(d.pop("wage_prc", UNSET))

        def _parse_wage_today_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        wage_today_prc = _parse_wage_today_prc(d.pop("wage_today_prc", UNSET))

        discount_price_item = cls(
            goods_no=goods_no,
            sale_prc=sale_prc,
            product_discount=product_discount,
            coupon_discount=coupon_discount,
            total_discount=total_discount,
            final_unit_price=final_unit_price,
            total_product_price=total_product_price,
            total_wage=total_wage,
            final_price=final_price,
            wage_prc=wage_prc,
            wage_today_prc=wage_today_prc,
        )

        discount_price_item.additional_properties = d
        return discount_price_item

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
