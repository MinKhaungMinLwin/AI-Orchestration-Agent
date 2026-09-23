from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AppliedCouponItem")


@_attrs_define
class AppliedCouponItem:
    """
    Attributes:
        stage (str): 적용 단계: product|payment|plus
        cpn_no (str): 쿠폰 번호
        discount_amt (int): 해당 단계 할인 금액 (단가 기준)
        cpn_nm (None | str | Unset): 쿠폰명
        dup_use_yn (None | str | Unset): CC_CPN_BASE.CPN_DUP_USE_YN (product 단계만 의미). N이면 결제쿠폰 단계 스킵.
    """

    stage: str
    cpn_no: str
    discount_amt: int
    cpn_nm: None | str | Unset = UNSET
    dup_use_yn: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        stage = self.stage

        cpn_no = self.cpn_no

        discount_amt = self.discount_amt

        cpn_nm: None | str | Unset
        if isinstance(self.cpn_nm, Unset):
            cpn_nm = UNSET
        else:
            cpn_nm = self.cpn_nm

        dup_use_yn: None | str | Unset
        if isinstance(self.dup_use_yn, Unset):
            dup_use_yn = UNSET
        else:
            dup_use_yn = self.dup_use_yn

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "stage": stage,
                "cpn_no": cpn_no,
                "discount_amt": discount_amt,
            }
        )
        if cpn_nm is not UNSET:
            field_dict["cpn_nm"] = cpn_nm
        if dup_use_yn is not UNSET:
            field_dict["dup_use_yn"] = dup_use_yn

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        stage = d.pop("stage")

        cpn_no = d.pop("cpn_no")

        discount_amt = d.pop("discount_amt")

        def _parse_cpn_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cpn_nm = _parse_cpn_nm(d.pop("cpn_nm", UNSET))

        def _parse_dup_use_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dup_use_yn = _parse_dup_use_yn(d.pop("dup_use_yn", UNSET))

        applied_coupon_item = cls(
            stage=stage,
            cpn_no=cpn_no,
            discount_amt=discount_amt,
            cpn_nm=cpn_nm,
            dup_use_yn=dup_use_yn,
        )

        applied_coupon_item.additional_properties = d
        return applied_coupon_item

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
