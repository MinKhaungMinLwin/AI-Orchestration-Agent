from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MyCouponItem")


@_attrs_define
class MyCouponItem:
    """
    Attributes:
        cpn_issu_no (str): 쿠폰 발급 번호
        mbr_no (str): 회원 번호
        cpn_no (str): 쿠폰 번호
        cpn_nm (None | str | Unset): 쿠폰명
        cpn_d_nm (None | str | Unset): 쿠폰 상세명
        disp_nm (None | str | Unset): 전시명
        issu_dtime (None | str | Unset): 발급 일시
        use_strt_dtime (None | str | Unset): 사용 시작 일시
        use_end_dtime (None | str | Unset): 사용 종료 일시
        mbr_use_yn (None | str | Unset): 회원 사용 여부
        cpn_dscn_tp_cd (None | str | Unset): 쿠폰 할인 유형 코드
        rt_amt_val (float | None | Unset): 정률/정액 값
        min_pur_amt (int | None | Unset): 최소 구매 금액
        max_dscnt_amt (int | None | Unset): 최대 할인 금액
        cpn_onoff_cd (None | str | Unset): 쿠폰 온/오프라인 코드
        coupon_channel_type (None | str | Unset): 정규화된 쿠폰 사용처: online, offline, onoff, store_only, partner_only
        has_store_mapping (bool | Unset): 매장 적용 대상 매핑(TGT_SCT_CD='90') 보유 여부 Default: False.
        has_partner_mapping (bool | Unset): 제휴사 적용 대상 매핑(TGT_SCT_CD='100') 보유 여부 Default: False.
    """

    cpn_issu_no: str
    mbr_no: str
    cpn_no: str
    cpn_nm: None | str | Unset = UNSET
    cpn_d_nm: None | str | Unset = UNSET
    disp_nm: None | str | Unset = UNSET
    issu_dtime: None | str | Unset = UNSET
    use_strt_dtime: None | str | Unset = UNSET
    use_end_dtime: None | str | Unset = UNSET
    mbr_use_yn: None | str | Unset = UNSET
    cpn_dscn_tp_cd: None | str | Unset = UNSET
    rt_amt_val: float | None | Unset = UNSET
    min_pur_amt: int | None | Unset = UNSET
    max_dscnt_amt: int | None | Unset = UNSET
    cpn_onoff_cd: None | str | Unset = UNSET
    coupon_channel_type: None | str | Unset = UNSET
    has_store_mapping: bool | Unset = False
    has_partner_mapping: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cpn_issu_no = self.cpn_issu_no

        mbr_no = self.mbr_no

        cpn_no = self.cpn_no

        cpn_nm: None | str | Unset
        if isinstance(self.cpn_nm, Unset):
            cpn_nm = UNSET
        else:
            cpn_nm = self.cpn_nm

        cpn_d_nm: None | str | Unset
        if isinstance(self.cpn_d_nm, Unset):
            cpn_d_nm = UNSET
        else:
            cpn_d_nm = self.cpn_d_nm

        disp_nm: None | str | Unset
        if isinstance(self.disp_nm, Unset):
            disp_nm = UNSET
        else:
            disp_nm = self.disp_nm

        issu_dtime: None | str | Unset
        if isinstance(self.issu_dtime, Unset):
            issu_dtime = UNSET
        else:
            issu_dtime = self.issu_dtime

        use_strt_dtime: None | str | Unset
        if isinstance(self.use_strt_dtime, Unset):
            use_strt_dtime = UNSET
        else:
            use_strt_dtime = self.use_strt_dtime

        use_end_dtime: None | str | Unset
        if isinstance(self.use_end_dtime, Unset):
            use_end_dtime = UNSET
        else:
            use_end_dtime = self.use_end_dtime

        mbr_use_yn: None | str | Unset
        if isinstance(self.mbr_use_yn, Unset):
            mbr_use_yn = UNSET
        else:
            mbr_use_yn = self.mbr_use_yn

        cpn_dscn_tp_cd: None | str | Unset
        if isinstance(self.cpn_dscn_tp_cd, Unset):
            cpn_dscn_tp_cd = UNSET
        else:
            cpn_dscn_tp_cd = self.cpn_dscn_tp_cd

        rt_amt_val: float | None | Unset
        if isinstance(self.rt_amt_val, Unset):
            rt_amt_val = UNSET
        else:
            rt_amt_val = self.rt_amt_val

        min_pur_amt: int | None | Unset
        if isinstance(self.min_pur_amt, Unset):
            min_pur_amt = UNSET
        else:
            min_pur_amt = self.min_pur_amt

        max_dscnt_amt: int | None | Unset
        if isinstance(self.max_dscnt_amt, Unset):
            max_dscnt_amt = UNSET
        else:
            max_dscnt_amt = self.max_dscnt_amt

        cpn_onoff_cd: None | str | Unset
        if isinstance(self.cpn_onoff_cd, Unset):
            cpn_onoff_cd = UNSET
        else:
            cpn_onoff_cd = self.cpn_onoff_cd

        coupon_channel_type: None | str | Unset
        if isinstance(self.coupon_channel_type, Unset):
            coupon_channel_type = UNSET
        else:
            coupon_channel_type = self.coupon_channel_type

        has_store_mapping = self.has_store_mapping

        has_partner_mapping = self.has_partner_mapping

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "cpn_issu_no": cpn_issu_no,
                "mbr_no": mbr_no,
                "cpn_no": cpn_no,
            }
        )
        if cpn_nm is not UNSET:
            field_dict["cpn_nm"] = cpn_nm
        if cpn_d_nm is not UNSET:
            field_dict["cpn_d_nm"] = cpn_d_nm
        if disp_nm is not UNSET:
            field_dict["disp_nm"] = disp_nm
        if issu_dtime is not UNSET:
            field_dict["issu_dtime"] = issu_dtime
        if use_strt_dtime is not UNSET:
            field_dict["use_strt_dtime"] = use_strt_dtime
        if use_end_dtime is not UNSET:
            field_dict["use_end_dtime"] = use_end_dtime
        if mbr_use_yn is not UNSET:
            field_dict["mbr_use_yn"] = mbr_use_yn
        if cpn_dscn_tp_cd is not UNSET:
            field_dict["cpn_dscn_tp_cd"] = cpn_dscn_tp_cd
        if rt_amt_val is not UNSET:
            field_dict["rt_amt_val"] = rt_amt_val
        if min_pur_amt is not UNSET:
            field_dict["min_pur_amt"] = min_pur_amt
        if max_dscnt_amt is not UNSET:
            field_dict["max_dscnt_amt"] = max_dscnt_amt
        if cpn_onoff_cd is not UNSET:
            field_dict["cpn_onoff_cd"] = cpn_onoff_cd
        if coupon_channel_type is not UNSET:
            field_dict["coupon_channel_type"] = coupon_channel_type
        if has_store_mapping is not UNSET:
            field_dict["has_store_mapping"] = has_store_mapping
        if has_partner_mapping is not UNSET:
            field_dict["has_partner_mapping"] = has_partner_mapping

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        cpn_issu_no = d.pop("cpn_issu_no")

        mbr_no = d.pop("mbr_no")

        cpn_no = d.pop("cpn_no")

        def _parse_cpn_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cpn_nm = _parse_cpn_nm(d.pop("cpn_nm", UNSET))

        def _parse_cpn_d_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cpn_d_nm = _parse_cpn_d_nm(d.pop("cpn_d_nm", UNSET))

        def _parse_disp_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        disp_nm = _parse_disp_nm(d.pop("disp_nm", UNSET))

        def _parse_issu_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        issu_dtime = _parse_issu_dtime(d.pop("issu_dtime", UNSET))

        def _parse_use_strt_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        use_strt_dtime = _parse_use_strt_dtime(d.pop("use_strt_dtime", UNSET))

        def _parse_use_end_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        use_end_dtime = _parse_use_end_dtime(d.pop("use_end_dtime", UNSET))

        def _parse_mbr_use_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mbr_use_yn = _parse_mbr_use_yn(d.pop("mbr_use_yn", UNSET))

        def _parse_cpn_dscn_tp_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cpn_dscn_tp_cd = _parse_cpn_dscn_tp_cd(d.pop("cpn_dscn_tp_cd", UNSET))

        def _parse_rt_amt_val(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        rt_amt_val = _parse_rt_amt_val(d.pop("rt_amt_val", UNSET))

        def _parse_min_pur_amt(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        min_pur_amt = _parse_min_pur_amt(d.pop("min_pur_amt", UNSET))

        def _parse_max_dscnt_amt(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_dscnt_amt = _parse_max_dscnt_amt(d.pop("max_dscnt_amt", UNSET))

        def _parse_cpn_onoff_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cpn_onoff_cd = _parse_cpn_onoff_cd(d.pop("cpn_onoff_cd", UNSET))

        def _parse_coupon_channel_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        coupon_channel_type = _parse_coupon_channel_type(d.pop("coupon_channel_type", UNSET))

        has_store_mapping = d.pop("has_store_mapping", UNSET)

        has_partner_mapping = d.pop("has_partner_mapping", UNSET)

        my_coupon_item = cls(
            cpn_issu_no=cpn_issu_no,
            mbr_no=mbr_no,
            cpn_no=cpn_no,
            cpn_nm=cpn_nm,
            cpn_d_nm=cpn_d_nm,
            disp_nm=disp_nm,
            issu_dtime=issu_dtime,
            use_strt_dtime=use_strt_dtime,
            use_end_dtime=use_end_dtime,
            mbr_use_yn=mbr_use_yn,
            cpn_dscn_tp_cd=cpn_dscn_tp_cd,
            rt_amt_val=rt_amt_val,
            min_pur_amt=min_pur_amt,
            max_dscnt_amt=max_dscnt_amt,
            cpn_onoff_cd=cpn_onoff_cd,
            coupon_channel_type=coupon_channel_type,
            has_store_mapping=has_store_mapping,
            has_partner_mapping=has_partner_mapping,
        )

        my_coupon_item.additional_properties = d
        return my_coupon_item

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
