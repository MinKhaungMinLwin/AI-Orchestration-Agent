from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.coupon_stacking_info import CouponStackingInfo
    from ..models.coupon_stacking_pair import CouponStackingPair


T = TypeVar("T", bound="CouponStackingCheckResponse")


@_attrs_define
class CouponStackingCheckResponse:
    """
    Attributes:
        coupons (list[CouponStackingInfo] | Unset): 요청한 cpn_no 순서대로 정렬된 쿠폰 정보. 마스터 미발견은 found=false.
        pairs (list[CouponStackingPair] | Unset): 입력 cpn_no 들의 모든 2-조합 (N개 입력 → C(N,2) 개). 입력 순서 기준 (a 가 먼저, b 가 나중).
            cpn_no 가 1개면 빈 배열.
    """

    coupons: list[CouponStackingInfo] | Unset = UNSET
    pairs: list[CouponStackingPair] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        coupons: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.coupons, Unset):
            coupons = []
            for coupons_item_data in self.coupons:
                coupons_item = coupons_item_data.to_dict()
                coupons.append(coupons_item)

        pairs: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.pairs, Unset):
            pairs = []
            for pairs_item_data in self.pairs:
                pairs_item = pairs_item_data.to_dict()
                pairs.append(pairs_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if coupons is not UNSET:
            field_dict["coupons"] = coupons
        if pairs is not UNSET:
            field_dict["pairs"] = pairs

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.coupon_stacking_info import CouponStackingInfo
        from ..models.coupon_stacking_pair import CouponStackingPair

        d = dict(src_dict)
        _coupons = d.pop("coupons", UNSET)
        coupons: list[CouponStackingInfo] | Unset = UNSET
        if _coupons is not UNSET:
            coupons = []
            for coupons_item_data in _coupons:
                coupons_item = CouponStackingInfo.from_dict(coupons_item_data)

                coupons.append(coupons_item)

        _pairs = d.pop("pairs", UNSET)
        pairs: list[CouponStackingPair] | Unset = UNSET
        if _pairs is not UNSET:
            pairs = []
            for pairs_item_data in _pairs:
                pairs_item = CouponStackingPair.from_dict(pairs_item_data)

                pairs.append(pairs_item)

        coupon_stacking_check_response = cls(
            coupons=coupons,
            pairs=pairs,
        )

        coupon_stacking_check_response.additional_properties = d
        return coupon_stacking_check_response

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
