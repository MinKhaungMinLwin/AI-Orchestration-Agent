from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="OrderDeliveryResponse")


@_attrs_define
class OrderDeliveryResponse:
    """
    Attributes:
        ord_prgs_stat_cd (None | str | Unset): 주문 진행 상태 코드
        dlv_prgs_stat_cd (None | str | Unset): 배송 진행 상태 코드
        inv_no (None | str | Unset): 운송장 번호
        hdc_cd (None | str | Unset): 택배사 코드
        dlv_fcst_dtime (None | str | Unset): 도착 예정 일시
    """

    ord_prgs_stat_cd: None | str | Unset = UNSET
    dlv_prgs_stat_cd: None | str | Unset = UNSET
    inv_no: None | str | Unset = UNSET
    hdc_cd: None | str | Unset = UNSET
    dlv_fcst_dtime: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ord_prgs_stat_cd: None | str | Unset
        if isinstance(self.ord_prgs_stat_cd, Unset):
            ord_prgs_stat_cd = UNSET
        else:
            ord_prgs_stat_cd = self.ord_prgs_stat_cd

        dlv_prgs_stat_cd: None | str | Unset
        if isinstance(self.dlv_prgs_stat_cd, Unset):
            dlv_prgs_stat_cd = UNSET
        else:
            dlv_prgs_stat_cd = self.dlv_prgs_stat_cd

        inv_no: None | str | Unset
        if isinstance(self.inv_no, Unset):
            inv_no = UNSET
        else:
            inv_no = self.inv_no

        hdc_cd: None | str | Unset
        if isinstance(self.hdc_cd, Unset):
            hdc_cd = UNSET
        else:
            hdc_cd = self.hdc_cd

        dlv_fcst_dtime: None | str | Unset
        if isinstance(self.dlv_fcst_dtime, Unset):
            dlv_fcst_dtime = UNSET
        else:
            dlv_fcst_dtime = self.dlv_fcst_dtime

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if ord_prgs_stat_cd is not UNSET:
            field_dict["ord_prgs_stat_cd"] = ord_prgs_stat_cd
        if dlv_prgs_stat_cd is not UNSET:
            field_dict["dlv_prgs_stat_cd"] = dlv_prgs_stat_cd
        if inv_no is not UNSET:
            field_dict["inv_no"] = inv_no
        if hdc_cd is not UNSET:
            field_dict["hdc_cd"] = hdc_cd
        if dlv_fcst_dtime is not UNSET:
            field_dict["dlv_fcst_dtime"] = dlv_fcst_dtime

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_ord_prgs_stat_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ord_prgs_stat_cd = _parse_ord_prgs_stat_cd(d.pop("ord_prgs_stat_cd", UNSET))

        def _parse_dlv_prgs_stat_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dlv_prgs_stat_cd = _parse_dlv_prgs_stat_cd(d.pop("dlv_prgs_stat_cd", UNSET))

        def _parse_inv_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        inv_no = _parse_inv_no(d.pop("inv_no", UNSET))

        def _parse_hdc_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        hdc_cd = _parse_hdc_cd(d.pop("hdc_cd", UNSET))

        def _parse_dlv_fcst_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dlv_fcst_dtime = _parse_dlv_fcst_dtime(d.pop("dlv_fcst_dtime", UNSET))

        order_delivery_response = cls(
            ord_prgs_stat_cd=ord_prgs_stat_cd,
            dlv_prgs_stat_cd=dlv_prgs_stat_cd,
            inv_no=inv_no,
            hdc_cd=hdc_cd,
            dlv_fcst_dtime=dlv_fcst_dtime,
        )

        order_delivery_response.additional_properties = d
        return order_delivery_response

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
