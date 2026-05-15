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
        query_no (str): 입력 조회 번호 (주문번호 O..., 배송번호 D...)
        ord_no (None | str | Unset): 주문 번호
        dlv_no (None | str | Unset): 배송 번호
        ord_prgs_stat_cd (None | str | Unset): 주문 진행 상태 코드
        ord_prgs_stat_nm (None | str | Unset): 주문 진행 상태명
        dlv_prgs_stat_cd (None | str | Unset): 배송 진행 상태 코드
        dlv_prgs_stat_nm (None | str | Unset): 배송 진행 상태명
        inv_no (None | str | Unset): 운송장 번호
        hdc_cd (None | str | Unset): 택배사 코드
        dlv_fcst_dtime (None | str | Unset): 도착 예정 일시
        shop_nm (None | str | Unset): 매장명 (방문 예약 매장)
        tel_no (None | str | Unset): 매장 전화번호
        rsv_dtime (None | str | Unset): 매장 방문 예약 일시 (YYYY-MM-DD HH:MI)
    """

    query_no: str
    ord_no: None | str | Unset = UNSET
    dlv_no: None | str | Unset = UNSET
    ord_prgs_stat_cd: None | str | Unset = UNSET
    ord_prgs_stat_nm: None | str | Unset = UNSET
    dlv_prgs_stat_cd: None | str | Unset = UNSET
    dlv_prgs_stat_nm: None | str | Unset = UNSET
    inv_no: None | str | Unset = UNSET
    hdc_cd: None | str | Unset = UNSET
    dlv_fcst_dtime: None | str | Unset = UNSET
    shop_nm: None | str | Unset = UNSET
    tel_no: None | str | Unset = UNSET
    rsv_dtime: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        query_no = self.query_no

        ord_no: None | str | Unset
        if isinstance(self.ord_no, Unset):
            ord_no = UNSET
        else:
            ord_no = self.ord_no

        dlv_no: None | str | Unset
        if isinstance(self.dlv_no, Unset):
            dlv_no = UNSET
        else:
            dlv_no = self.dlv_no

        ord_prgs_stat_cd: None | str | Unset
        if isinstance(self.ord_prgs_stat_cd, Unset):
            ord_prgs_stat_cd = UNSET
        else:
            ord_prgs_stat_cd = self.ord_prgs_stat_cd

        ord_prgs_stat_nm: None | str | Unset
        if isinstance(self.ord_prgs_stat_nm, Unset):
            ord_prgs_stat_nm = UNSET
        else:
            ord_prgs_stat_nm = self.ord_prgs_stat_nm

        dlv_prgs_stat_cd: None | str | Unset
        if isinstance(self.dlv_prgs_stat_cd, Unset):
            dlv_prgs_stat_cd = UNSET
        else:
            dlv_prgs_stat_cd = self.dlv_prgs_stat_cd

        dlv_prgs_stat_nm: None | str | Unset
        if isinstance(self.dlv_prgs_stat_nm, Unset):
            dlv_prgs_stat_nm = UNSET
        else:
            dlv_prgs_stat_nm = self.dlv_prgs_stat_nm

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

        shop_nm: None | str | Unset
        if isinstance(self.shop_nm, Unset):
            shop_nm = UNSET
        else:
            shop_nm = self.shop_nm

        tel_no: None | str | Unset
        if isinstance(self.tel_no, Unset):
            tel_no = UNSET
        else:
            tel_no = self.tel_no

        rsv_dtime: None | str | Unset
        if isinstance(self.rsv_dtime, Unset):
            rsv_dtime = UNSET
        else:
            rsv_dtime = self.rsv_dtime

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "query_no": query_no,
            }
        )
        if ord_no is not UNSET:
            field_dict["ord_no"] = ord_no
        if dlv_no is not UNSET:
            field_dict["dlv_no"] = dlv_no
        if ord_prgs_stat_cd is not UNSET:
            field_dict["ord_prgs_stat_cd"] = ord_prgs_stat_cd
        if ord_prgs_stat_nm is not UNSET:
            field_dict["ord_prgs_stat_nm"] = ord_prgs_stat_nm
        if dlv_prgs_stat_cd is not UNSET:
            field_dict["dlv_prgs_stat_cd"] = dlv_prgs_stat_cd
        if dlv_prgs_stat_nm is not UNSET:
            field_dict["dlv_prgs_stat_nm"] = dlv_prgs_stat_nm
        if inv_no is not UNSET:
            field_dict["inv_no"] = inv_no
        if hdc_cd is not UNSET:
            field_dict["hdc_cd"] = hdc_cd
        if dlv_fcst_dtime is not UNSET:
            field_dict["dlv_fcst_dtime"] = dlv_fcst_dtime
        if shop_nm is not UNSET:
            field_dict["shop_nm"] = shop_nm
        if tel_no is not UNSET:
            field_dict["tel_no"] = tel_no
        if rsv_dtime is not UNSET:
            field_dict["rsv_dtime"] = rsv_dtime

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        query_no = d.pop("query_no")

        def _parse_ord_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ord_no = _parse_ord_no(d.pop("ord_no", UNSET))

        def _parse_dlv_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dlv_no = _parse_dlv_no(d.pop("dlv_no", UNSET))

        def _parse_ord_prgs_stat_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ord_prgs_stat_cd = _parse_ord_prgs_stat_cd(d.pop("ord_prgs_stat_cd", UNSET))

        def _parse_ord_prgs_stat_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ord_prgs_stat_nm = _parse_ord_prgs_stat_nm(d.pop("ord_prgs_stat_nm", UNSET))

        def _parse_dlv_prgs_stat_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dlv_prgs_stat_cd = _parse_dlv_prgs_stat_cd(d.pop("dlv_prgs_stat_cd", UNSET))

        def _parse_dlv_prgs_stat_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dlv_prgs_stat_nm = _parse_dlv_prgs_stat_nm(d.pop("dlv_prgs_stat_nm", UNSET))

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

        def _parse_shop_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_nm = _parse_shop_nm(d.pop("shop_nm", UNSET))

        def _parse_tel_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tel_no = _parse_tel_no(d.pop("tel_no", UNSET))

        def _parse_rsv_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rsv_dtime = _parse_rsv_dtime(d.pop("rsv_dtime", UNSET))

        order_delivery_response = cls(
            query_no=query_no,
            ord_no=ord_no,
            dlv_no=dlv_no,
            ord_prgs_stat_cd=ord_prgs_stat_cd,
            ord_prgs_stat_nm=ord_prgs_stat_nm,
            dlv_prgs_stat_cd=dlv_prgs_stat_cd,
            dlv_prgs_stat_nm=dlv_prgs_stat_nm,
            inv_no=inv_no,
            hdc_cd=hdc_cd,
            dlv_fcst_dtime=dlv_fcst_dtime,
            shop_nm=shop_nm,
            tel_no=tel_no,
            rsv_dtime=rsv_dtime,
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
