from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.deal_coupon_item import DealCouponItem


T = TypeVar("T", bound="DealWithCouponsItem")


@_attrs_define
class DealWithCouponsItem:
    """
    Attributes:
        deal_no (str): 기획전 번호
        deal_nm (None | str | Unset): 기획전명
        disp_strt_dtime (None | str | Unset): 전시 시작 일시
        disp_end_dtime (None | str | Unset): 전시 종료 일시
        coupons (list[DealCouponItem] | Unset): 해당 기획전에 매핑된 쿠폰 목록
    """

    deal_no: str
    deal_nm: None | str | Unset = UNSET
    disp_strt_dtime: None | str | Unset = UNSET
    disp_end_dtime: None | str | Unset = UNSET
    coupons: list[DealCouponItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        deal_no = self.deal_no

        deal_nm: None | str | Unset
        if isinstance(self.deal_nm, Unset):
            deal_nm = UNSET
        else:
            deal_nm = self.deal_nm

        disp_strt_dtime: None | str | Unset
        if isinstance(self.disp_strt_dtime, Unset):
            disp_strt_dtime = UNSET
        else:
            disp_strt_dtime = self.disp_strt_dtime

        disp_end_dtime: None | str | Unset
        if isinstance(self.disp_end_dtime, Unset):
            disp_end_dtime = UNSET
        else:
            disp_end_dtime = self.disp_end_dtime

        coupons: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.coupons, Unset):
            coupons = []
            for coupons_item_data in self.coupons:
                coupons_item = coupons_item_data.to_dict()
                coupons.append(coupons_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "deal_no": deal_no,
            }
        )
        if deal_nm is not UNSET:
            field_dict["deal_nm"] = deal_nm
        if disp_strt_dtime is not UNSET:
            field_dict["disp_strt_dtime"] = disp_strt_dtime
        if disp_end_dtime is not UNSET:
            field_dict["disp_end_dtime"] = disp_end_dtime
        if coupons is not UNSET:
            field_dict["coupons"] = coupons

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.deal_coupon_item import DealCouponItem

        d = dict(src_dict)
        deal_no = d.pop("deal_no")

        def _parse_deal_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        deal_nm = _parse_deal_nm(d.pop("deal_nm", UNSET))

        def _parse_disp_strt_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        disp_strt_dtime = _parse_disp_strt_dtime(d.pop("disp_strt_dtime", UNSET))

        def _parse_disp_end_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        disp_end_dtime = _parse_disp_end_dtime(d.pop("disp_end_dtime", UNSET))

        _coupons = d.pop("coupons", UNSET)
        coupons: list[DealCouponItem] | Unset = UNSET
        if _coupons is not UNSET:
            coupons = []
            for coupons_item_data in _coupons:
                coupons_item = DealCouponItem.from_dict(coupons_item_data)

                coupons.append(coupons_item)

        deal_with_coupons_item = cls(
            deal_no=deal_no,
            deal_nm=deal_nm,
            disp_strt_dtime=disp_strt_dtime,
            disp_end_dtime=disp_end_dtime,
            coupons=coupons,
        )

        deal_with_coupons_item.additional_properties = d
        return deal_with_coupons_item

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
