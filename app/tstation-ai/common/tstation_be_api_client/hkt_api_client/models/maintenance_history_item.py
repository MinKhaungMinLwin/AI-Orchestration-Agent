from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MaintenanceHistoryItem")


@_attrs_define
class MaintenanceHistoryItem:
    """
    Attributes:
        svc_tp (str): 이력 유형: 오프라인 / 온라인/장착
        car_svc_hist_seq (None | str | Unset): 정비이력 시퀀스 또는 예약 시퀀스
        mbr_car_reg_seq (None | str | Unset): 회원 차량 등록/통합 시퀀스
        car_no (None | str | Unset): 차량번호
        car_svc_dt (None | str | Unset): 정비/장착일 (YYYY-MM-DD)
        car_svc_info (None | str | Unset): 정비/장착 내용
        car_svc_qty (None | str | Unset): 수량
        car_svc_prc (None | str | Unset): 단가
        tot_ord_amt (None | str | Unset): 총 주문 금액
        tot_dscnt_amt (None | str | Unset): 총 할인 금액
        item_cd (None | str | Unset): 상품/정비 항목 코드
        item_nm (None | str | Unset): 상품/정비 항목명
        ord_no (None | str | Unset): 온라인 주문번호
        rpr_psc_cd (None | str | Unset): 정비/주문 진행 상태 코드
        shop_nm (None | str | Unset): 매장명
    """

    svc_tp: str
    car_svc_hist_seq: None | str | Unset = UNSET
    mbr_car_reg_seq: None | str | Unset = UNSET
    car_no: None | str | Unset = UNSET
    car_svc_dt: None | str | Unset = UNSET
    car_svc_info: None | str | Unset = UNSET
    car_svc_qty: None | str | Unset = UNSET
    car_svc_prc: None | str | Unset = UNSET
    tot_ord_amt: None | str | Unset = UNSET
    tot_dscnt_amt: None | str | Unset = UNSET
    item_cd: None | str | Unset = UNSET
    item_nm: None | str | Unset = UNSET
    ord_no: None | str | Unset = UNSET
    rpr_psc_cd: None | str | Unset = UNSET
    shop_nm: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        svc_tp = self.svc_tp

        car_svc_hist_seq: None | str | Unset
        if isinstance(self.car_svc_hist_seq, Unset):
            car_svc_hist_seq = UNSET
        else:
            car_svc_hist_seq = self.car_svc_hist_seq

        mbr_car_reg_seq: None | str | Unset
        if isinstance(self.mbr_car_reg_seq, Unset):
            mbr_car_reg_seq = UNSET
        else:
            mbr_car_reg_seq = self.mbr_car_reg_seq

        car_no: None | str | Unset
        if isinstance(self.car_no, Unset):
            car_no = UNSET
        else:
            car_no = self.car_no

        car_svc_dt: None | str | Unset
        if isinstance(self.car_svc_dt, Unset):
            car_svc_dt = UNSET
        else:
            car_svc_dt = self.car_svc_dt

        car_svc_info: None | str | Unset
        if isinstance(self.car_svc_info, Unset):
            car_svc_info = UNSET
        else:
            car_svc_info = self.car_svc_info

        car_svc_qty: None | str | Unset
        if isinstance(self.car_svc_qty, Unset):
            car_svc_qty = UNSET
        else:
            car_svc_qty = self.car_svc_qty

        car_svc_prc: None | str | Unset
        if isinstance(self.car_svc_prc, Unset):
            car_svc_prc = UNSET
        else:
            car_svc_prc = self.car_svc_prc

        tot_ord_amt: None | str | Unset
        if isinstance(self.tot_ord_amt, Unset):
            tot_ord_amt = UNSET
        else:
            tot_ord_amt = self.tot_ord_amt

        tot_dscnt_amt: None | str | Unset
        if isinstance(self.tot_dscnt_amt, Unset):
            tot_dscnt_amt = UNSET
        else:
            tot_dscnt_amt = self.tot_dscnt_amt

        item_cd: None | str | Unset
        if isinstance(self.item_cd, Unset):
            item_cd = UNSET
        else:
            item_cd = self.item_cd

        item_nm: None | str | Unset
        if isinstance(self.item_nm, Unset):
            item_nm = UNSET
        else:
            item_nm = self.item_nm

        ord_no: None | str | Unset
        if isinstance(self.ord_no, Unset):
            ord_no = UNSET
        else:
            ord_no = self.ord_no

        rpr_psc_cd: None | str | Unset
        if isinstance(self.rpr_psc_cd, Unset):
            rpr_psc_cd = UNSET
        else:
            rpr_psc_cd = self.rpr_psc_cd

        shop_nm: None | str | Unset
        if isinstance(self.shop_nm, Unset):
            shop_nm = UNSET
        else:
            shop_nm = self.shop_nm

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "svc_tp": svc_tp,
            }
        )
        if car_svc_hist_seq is not UNSET:
            field_dict["car_svc_hist_seq"] = car_svc_hist_seq
        if mbr_car_reg_seq is not UNSET:
            field_dict["mbr_car_reg_seq"] = mbr_car_reg_seq
        if car_no is not UNSET:
            field_dict["car_no"] = car_no
        if car_svc_dt is not UNSET:
            field_dict["car_svc_dt"] = car_svc_dt
        if car_svc_info is not UNSET:
            field_dict["car_svc_info"] = car_svc_info
        if car_svc_qty is not UNSET:
            field_dict["car_svc_qty"] = car_svc_qty
        if car_svc_prc is not UNSET:
            field_dict["car_svc_prc"] = car_svc_prc
        if tot_ord_amt is not UNSET:
            field_dict["tot_ord_amt"] = tot_ord_amt
        if tot_dscnt_amt is not UNSET:
            field_dict["tot_dscnt_amt"] = tot_dscnt_amt
        if item_cd is not UNSET:
            field_dict["item_cd"] = item_cd
        if item_nm is not UNSET:
            field_dict["item_nm"] = item_nm
        if ord_no is not UNSET:
            field_dict["ord_no"] = ord_no
        if rpr_psc_cd is not UNSET:
            field_dict["rpr_psc_cd"] = rpr_psc_cd
        if shop_nm is not UNSET:
            field_dict["shop_nm"] = shop_nm

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        svc_tp = d.pop("svc_tp")

        def _parse_car_svc_hist_seq(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_svc_hist_seq = _parse_car_svc_hist_seq(d.pop("car_svc_hist_seq", UNSET))

        def _parse_mbr_car_reg_seq(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mbr_car_reg_seq = _parse_mbr_car_reg_seq(d.pop("mbr_car_reg_seq", UNSET))

        def _parse_car_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_no = _parse_car_no(d.pop("car_no", UNSET))

        def _parse_car_svc_dt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_svc_dt = _parse_car_svc_dt(d.pop("car_svc_dt", UNSET))

        def _parse_car_svc_info(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_svc_info = _parse_car_svc_info(d.pop("car_svc_info", UNSET))

        def _parse_car_svc_qty(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_svc_qty = _parse_car_svc_qty(d.pop("car_svc_qty", UNSET))

        def _parse_car_svc_prc(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_svc_prc = _parse_car_svc_prc(d.pop("car_svc_prc", UNSET))

        def _parse_tot_ord_amt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tot_ord_amt = _parse_tot_ord_amt(d.pop("tot_ord_amt", UNSET))

        def _parse_tot_dscnt_amt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tot_dscnt_amt = _parse_tot_dscnt_amt(d.pop("tot_dscnt_amt", UNSET))

        def _parse_item_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        item_cd = _parse_item_cd(d.pop("item_cd", UNSET))

        def _parse_item_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        item_nm = _parse_item_nm(d.pop("item_nm", UNSET))

        def _parse_ord_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ord_no = _parse_ord_no(d.pop("ord_no", UNSET))

        def _parse_rpr_psc_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rpr_psc_cd = _parse_rpr_psc_cd(d.pop("rpr_psc_cd", UNSET))

        def _parse_shop_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_nm = _parse_shop_nm(d.pop("shop_nm", UNSET))

        maintenance_history_item = cls(
            svc_tp=svc_tp,
            car_svc_hist_seq=car_svc_hist_seq,
            mbr_car_reg_seq=mbr_car_reg_seq,
            car_no=car_no,
            car_svc_dt=car_svc_dt,
            car_svc_info=car_svc_info,
            car_svc_qty=car_svc_qty,
            car_svc_prc=car_svc_prc,
            tot_ord_amt=tot_ord_amt,
            tot_dscnt_amt=tot_dscnt_amt,
            item_cd=item_cd,
            item_nm=item_nm,
            ord_no=ord_no,
            rpr_psc_cd=rpr_psc_cd,
            shop_nm=shop_nm,
        )

        maintenance_history_item.additional_properties = d
        return maintenance_history_item

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
