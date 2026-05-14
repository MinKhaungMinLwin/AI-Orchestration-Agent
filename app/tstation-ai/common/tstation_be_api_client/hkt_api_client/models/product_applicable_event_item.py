from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ProductApplicableEventItem")


@_attrs_define
class ProductApplicableEventItem:
    """
    Attributes:
        evt_no (str): 이벤트 번호
        cust_fvr_aply_sct_cd (str): 혜택 적용 구분 코드 (10=적용)
        cust_fvr_aply_tp_cd (str): 혜택 적용 유형 코드 (50=상품 매핑, 80=패턴 매핑)
        aply_key (str): 해당 이벤트에 매핑된 키 (50일 경우 GOODS_NO, 80일 경우 PTRN_CD)
        evt_nm (None | str | Unset): 이벤트명 (lang_cd 기준)
        evt_strt_dtime (None | str | Unset): 이벤트 시작 일시 (YYYY-MM-DD HH24:MI:SS)
        evt_end_dtime (None | str | Unset): 이벤트 종료 일시 (YYYY-MM-DD HH24:MI:SS)
        evt_prgs_stat_cd (None | str | Unset): 이벤트 진행 상태 코드 (10=진행 중)
        disp_yn (None | str | Unset): 전시 여부 (Y/N)
    """

    evt_no: str
    cust_fvr_aply_sct_cd: str
    cust_fvr_aply_tp_cd: str
    aply_key: str
    evt_nm: None | str | Unset = UNSET
    evt_strt_dtime: None | str | Unset = UNSET
    evt_end_dtime: None | str | Unset = UNSET
    evt_prgs_stat_cd: None | str | Unset = UNSET
    disp_yn: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        evt_no = self.evt_no

        cust_fvr_aply_sct_cd = self.cust_fvr_aply_sct_cd

        cust_fvr_aply_tp_cd = self.cust_fvr_aply_tp_cd

        aply_key = self.aply_key

        evt_nm: None | str | Unset
        if isinstance(self.evt_nm, Unset):
            evt_nm = UNSET
        else:
            evt_nm = self.evt_nm

        evt_strt_dtime: None | str | Unset
        if isinstance(self.evt_strt_dtime, Unset):
            evt_strt_dtime = UNSET
        else:
            evt_strt_dtime = self.evt_strt_dtime

        evt_end_dtime: None | str | Unset
        if isinstance(self.evt_end_dtime, Unset):
            evt_end_dtime = UNSET
        else:
            evt_end_dtime = self.evt_end_dtime

        evt_prgs_stat_cd: None | str | Unset
        if isinstance(self.evt_prgs_stat_cd, Unset):
            evt_prgs_stat_cd = UNSET
        else:
            evt_prgs_stat_cd = self.evt_prgs_stat_cd

        disp_yn: None | str | Unset
        if isinstance(self.disp_yn, Unset):
            disp_yn = UNSET
        else:
            disp_yn = self.disp_yn

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "evt_no": evt_no,
                "cust_fvr_aply_sct_cd": cust_fvr_aply_sct_cd,
                "cust_fvr_aply_tp_cd": cust_fvr_aply_tp_cd,
                "aply_key": aply_key,
            }
        )
        if evt_nm is not UNSET:
            field_dict["evt_nm"] = evt_nm
        if evt_strt_dtime is not UNSET:
            field_dict["evt_strt_dtime"] = evt_strt_dtime
        if evt_end_dtime is not UNSET:
            field_dict["evt_end_dtime"] = evt_end_dtime
        if evt_prgs_stat_cd is not UNSET:
            field_dict["evt_prgs_stat_cd"] = evt_prgs_stat_cd
        if disp_yn is not UNSET:
            field_dict["disp_yn"] = disp_yn

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        evt_no = d.pop("evt_no")

        cust_fvr_aply_sct_cd = d.pop("cust_fvr_aply_sct_cd")

        cust_fvr_aply_tp_cd = d.pop("cust_fvr_aply_tp_cd")

        aply_key = d.pop("aply_key")

        def _parse_evt_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        evt_nm = _parse_evt_nm(d.pop("evt_nm", UNSET))

        def _parse_evt_strt_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        evt_strt_dtime = _parse_evt_strt_dtime(d.pop("evt_strt_dtime", UNSET))

        def _parse_evt_end_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        evt_end_dtime = _parse_evt_end_dtime(d.pop("evt_end_dtime", UNSET))

        def _parse_evt_prgs_stat_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        evt_prgs_stat_cd = _parse_evt_prgs_stat_cd(d.pop("evt_prgs_stat_cd", UNSET))

        def _parse_disp_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        disp_yn = _parse_disp_yn(d.pop("disp_yn", UNSET))

        product_applicable_event_item = cls(
            evt_no=evt_no,
            cust_fvr_aply_sct_cd=cust_fvr_aply_sct_cd,
            cust_fvr_aply_tp_cd=cust_fvr_aply_tp_cd,
            aply_key=aply_key,
            evt_nm=evt_nm,
            evt_strt_dtime=evt_strt_dtime,
            evt_end_dtime=evt_end_dtime,
            evt_prgs_stat_cd=evt_prgs_stat_cd,
            disp_yn=disp_yn,
        )

        product_applicable_event_item.additional_properties = d
        return product_applicable_event_item

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
