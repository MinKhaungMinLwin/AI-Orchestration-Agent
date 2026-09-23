from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ReservationListItem")


@_attrs_define
class ReservationListItem:
    """
    Attributes:
        shop_rsv_seq (str): 매장예약순번 (PK, ET_SHOP_RSV_INFO.SHOP_RSV_SEQ)
        shop_rsv_no (None | str | Unset): 매장예약번호 (SHOP_RSV_NO)
        ord_no (None | str | Unset): 주문번호 (SHOP_RSV_SCT_CD='200' 구매후방문예약에서 세팅)
        shop_rsv_sct_cd (None | str | Unset): 매장예약구분 코드 [SHOP001]. 100: 방문예약, 200: 구매후방문예약, 300: 오프라인예약
        shop_rsv_sct_label (None | str | Unset): 매장예약구분 한글 라벨
        shop_id (None | str | Unset): 매장 ID (SHOP_ID)
        shop_nm (None | str | Unset): 매장명 (VW_ET_SHOP_INFO.SHOP_NM JOIN)
        tel_no (None | str | Unset): 매장 전화번호 (VW_ET_SHOP_INFO.SHOP_TEL_NO JOIN)
        vst_rsv_dtime (None | str | Unset): 매장방문예약일시 (YYYY-MM-DD HH24:MI)
        rsv_req_desc (None | str | Unset): 예약요청설명 (RSV_REQ_DESC)
        shop_vst_rsv_sts_cd (None | str | Unset): 매장방문예약상태 코드 [SHOP002]
        shop_vst_rsv_sts_label (None | str | Unset): 예약 상태 그룹 라벨: 예약대기 / 예약완료 / 서비스완료 / 서비스취소
        sys_reg_dtime (None | str | Unset): 시스템 등록 일시 (YYYY-MM-DD HH24:MI)
    """

    shop_rsv_seq: str
    shop_rsv_no: None | str | Unset = UNSET
    ord_no: None | str | Unset = UNSET
    shop_rsv_sct_cd: None | str | Unset = UNSET
    shop_rsv_sct_label: None | str | Unset = UNSET
    shop_id: None | str | Unset = UNSET
    shop_nm: None | str | Unset = UNSET
    tel_no: None | str | Unset = UNSET
    vst_rsv_dtime: None | str | Unset = UNSET
    rsv_req_desc: None | str | Unset = UNSET
    shop_vst_rsv_sts_cd: None | str | Unset = UNSET
    shop_vst_rsv_sts_label: None | str | Unset = UNSET
    sys_reg_dtime: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        shop_rsv_seq = self.shop_rsv_seq

        shop_rsv_no: None | str | Unset
        if isinstance(self.shop_rsv_no, Unset):
            shop_rsv_no = UNSET
        else:
            shop_rsv_no = self.shop_rsv_no

        ord_no: None | str | Unset
        if isinstance(self.ord_no, Unset):
            ord_no = UNSET
        else:
            ord_no = self.ord_no

        shop_rsv_sct_cd: None | str | Unset
        if isinstance(self.shop_rsv_sct_cd, Unset):
            shop_rsv_sct_cd = UNSET
        else:
            shop_rsv_sct_cd = self.shop_rsv_sct_cd

        shop_rsv_sct_label: None | str | Unset
        if isinstance(self.shop_rsv_sct_label, Unset):
            shop_rsv_sct_label = UNSET
        else:
            shop_rsv_sct_label = self.shop_rsv_sct_label

        shop_id: None | str | Unset
        if isinstance(self.shop_id, Unset):
            shop_id = UNSET
        else:
            shop_id = self.shop_id

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

        vst_rsv_dtime: None | str | Unset
        if isinstance(self.vst_rsv_dtime, Unset):
            vst_rsv_dtime = UNSET
        else:
            vst_rsv_dtime = self.vst_rsv_dtime

        rsv_req_desc: None | str | Unset
        if isinstance(self.rsv_req_desc, Unset):
            rsv_req_desc = UNSET
        else:
            rsv_req_desc = self.rsv_req_desc

        shop_vst_rsv_sts_cd: None | str | Unset
        if isinstance(self.shop_vst_rsv_sts_cd, Unset):
            shop_vst_rsv_sts_cd = UNSET
        else:
            shop_vst_rsv_sts_cd = self.shop_vst_rsv_sts_cd

        shop_vst_rsv_sts_label: None | str | Unset
        if isinstance(self.shop_vst_rsv_sts_label, Unset):
            shop_vst_rsv_sts_label = UNSET
        else:
            shop_vst_rsv_sts_label = self.shop_vst_rsv_sts_label

        sys_reg_dtime: None | str | Unset
        if isinstance(self.sys_reg_dtime, Unset):
            sys_reg_dtime = UNSET
        else:
            sys_reg_dtime = self.sys_reg_dtime

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "shop_rsv_seq": shop_rsv_seq,
            }
        )
        if shop_rsv_no is not UNSET:
            field_dict["shop_rsv_no"] = shop_rsv_no
        if ord_no is not UNSET:
            field_dict["ord_no"] = ord_no
        if shop_rsv_sct_cd is not UNSET:
            field_dict["shop_rsv_sct_cd"] = shop_rsv_sct_cd
        if shop_rsv_sct_label is not UNSET:
            field_dict["shop_rsv_sct_label"] = shop_rsv_sct_label
        if shop_id is not UNSET:
            field_dict["shop_id"] = shop_id
        if shop_nm is not UNSET:
            field_dict["shop_nm"] = shop_nm
        if tel_no is not UNSET:
            field_dict["tel_no"] = tel_no
        if vst_rsv_dtime is not UNSET:
            field_dict["vst_rsv_dtime"] = vst_rsv_dtime
        if rsv_req_desc is not UNSET:
            field_dict["rsv_req_desc"] = rsv_req_desc
        if shop_vst_rsv_sts_cd is not UNSET:
            field_dict["shop_vst_rsv_sts_cd"] = shop_vst_rsv_sts_cd
        if shop_vst_rsv_sts_label is not UNSET:
            field_dict["shop_vst_rsv_sts_label"] = shop_vst_rsv_sts_label
        if sys_reg_dtime is not UNSET:
            field_dict["sys_reg_dtime"] = sys_reg_dtime

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        shop_rsv_seq = d.pop("shop_rsv_seq")

        def _parse_shop_rsv_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_rsv_no = _parse_shop_rsv_no(d.pop("shop_rsv_no", UNSET))

        def _parse_ord_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ord_no = _parse_ord_no(d.pop("ord_no", UNSET))

        def _parse_shop_rsv_sct_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_rsv_sct_cd = _parse_shop_rsv_sct_cd(d.pop("shop_rsv_sct_cd", UNSET))

        def _parse_shop_rsv_sct_label(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_rsv_sct_label = _parse_shop_rsv_sct_label(d.pop("shop_rsv_sct_label", UNSET))

        def _parse_shop_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_id = _parse_shop_id(d.pop("shop_id", UNSET))

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

        def _parse_vst_rsv_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        vst_rsv_dtime = _parse_vst_rsv_dtime(d.pop("vst_rsv_dtime", UNSET))

        def _parse_rsv_req_desc(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rsv_req_desc = _parse_rsv_req_desc(d.pop("rsv_req_desc", UNSET))

        def _parse_shop_vst_rsv_sts_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_vst_rsv_sts_cd = _parse_shop_vst_rsv_sts_cd(d.pop("shop_vst_rsv_sts_cd", UNSET))

        def _parse_shop_vst_rsv_sts_label(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_vst_rsv_sts_label = _parse_shop_vst_rsv_sts_label(d.pop("shop_vst_rsv_sts_label", UNSET))

        def _parse_sys_reg_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sys_reg_dtime = _parse_sys_reg_dtime(d.pop("sys_reg_dtime", UNSET))

        reservation_list_item = cls(
            shop_rsv_seq=shop_rsv_seq,
            shop_rsv_no=shop_rsv_no,
            ord_no=ord_no,
            shop_rsv_sct_cd=shop_rsv_sct_cd,
            shop_rsv_sct_label=shop_rsv_sct_label,
            shop_id=shop_id,
            shop_nm=shop_nm,
            tel_no=tel_no,
            vst_rsv_dtime=vst_rsv_dtime,
            rsv_req_desc=rsv_req_desc,
            shop_vst_rsv_sts_cd=shop_vst_rsv_sts_cd,
            shop_vst_rsv_sts_label=shop_vst_rsv_sts_label,
            sys_reg_dtime=sys_reg_dtime,
        )

        reservation_list_item.additional_properties = d
        return reservation_list_item

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
