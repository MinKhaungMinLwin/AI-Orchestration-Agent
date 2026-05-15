from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.coupon_applicable_products_group import CouponApplicableProductsGroup
    from ..models.deal_applicable_products_group import DealApplicableProductsGroup


T = TypeVar("T", bound="CouponDealApplicableProductsResponse")


@_attrs_define
class CouponDealApplicableProductsResponse:
    """
    Attributes:
        total_coupons (int): 요청 cpn_no 중 매핑된 상품이 1개 이상인 쿠폰 수
        total_deals (int): 요청 deal_no 중 매핑된 상품이 1개 이상인 기획전 수
        total_products (int): coupons + deals 그룹 전체의 상품 row 합 (그룹 간 중복 별도 카운트)
        coupons (list[CouponApplicableProductsGroup] | Unset): cpn_no 별 적용 가능 상품 그룹 목록
        deals (list[DealApplicableProductsGroup] | Unset): deal_no 별 적용 가능 상품 그룹 목록 (deal → cpn → goods join)
    """

    total_coupons: int
    total_deals: int
    total_products: int
    coupons: list[CouponApplicableProductsGroup] | Unset = UNSET
    deals: list[DealApplicableProductsGroup] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total_coupons = self.total_coupons

        total_deals = self.total_deals

        total_products = self.total_products

        coupons: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.coupons, Unset):
            coupons = []
            for coupons_item_data in self.coupons:
                coupons_item = coupons_item_data.to_dict()
                coupons.append(coupons_item)

        deals: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.deals, Unset):
            deals = []
            for deals_item_data in self.deals:
                deals_item = deals_item_data.to_dict()
                deals.append(deals_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total_coupons": total_coupons,
                "total_deals": total_deals,
                "total_products": total_products,
            }
        )
        if coupons is not UNSET:
            field_dict["coupons"] = coupons
        if deals is not UNSET:
            field_dict["deals"] = deals

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.coupon_applicable_products_group import CouponApplicableProductsGroup
        from ..models.deal_applicable_products_group import DealApplicableProductsGroup

        d = dict(src_dict)
        total_coupons = d.pop("total_coupons")

        total_deals = d.pop("total_deals")

        total_products = d.pop("total_products")

        _coupons = d.pop("coupons", UNSET)
        coupons: list[CouponApplicableProductsGroup] | Unset = UNSET
        if _coupons is not UNSET:
            coupons = []
            for coupons_item_data in _coupons:
                coupons_item = CouponApplicableProductsGroup.from_dict(coupons_item_data)

                coupons.append(coupons_item)

        _deals = d.pop("deals", UNSET)
        deals: list[DealApplicableProductsGroup] | Unset = UNSET
        if _deals is not UNSET:
            deals = []
            for deals_item_data in _deals:
                deals_item = DealApplicableProductsGroup.from_dict(deals_item_data)

                deals.append(deals_item)

        coupon_deal_applicable_products_response = cls(
            total_coupons=total_coupons,
            total_deals=total_deals,
            total_products=total_products,
            coupons=coupons,
            deals=deals,
        )

        coupon_deal_applicable_products_response.additional_properties = d
        return coupon_deal_applicable_products_response

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
