from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="EventItem")


@_attrs_define
class EventItem:
    """
    Attributes:
        evt_no (str): 이벤트 번호
        evt_clss_cd (str): 이벤트 분류 코드
        evt_nm (None | str | Unset): 이벤트명
        evt_strt_dtime (None | str | Unset): 이벤트 시작 일시
        evt_end_dtime (None | str | Unset): 이벤트 종료 일시
        evt_prgs_stat_cd (None | str | Unset): 이벤트 진행 상태 코드
        evt_url_addr (None | str | Unset): 이벤트 URL 주소
        bnr_img_url_addr (None | str | Unset): 배너 이미지 URL 주소
        dtl_conts_url_addr (None | str | Unset): 상세 컨텐츠 URL 주소
        frdm_cmps_url_addr (None | str | Unset): 자유 구성 URL 주소
        evt_badge_nm (None | str | Unset): 이벤트 뱃지 이름
        new_evt_yn (None | str | Unset): 신규 이벤트 여부
        dtl_evt_cont (None | str | Unset): 상세 이벤트 내용
    """

    evt_no: str
    evt_clss_cd: str
    evt_nm: None | str | Unset = UNSET
    evt_strt_dtime: None | str | Unset = UNSET
    evt_end_dtime: None | str | Unset = UNSET
    evt_prgs_stat_cd: None | str | Unset = UNSET
    evt_url_addr: None | str | Unset = UNSET
    bnr_img_url_addr: None | str | Unset = UNSET
    dtl_conts_url_addr: None | str | Unset = UNSET
    frdm_cmps_url_addr: None | str | Unset = UNSET
    evt_badge_nm: None | str | Unset = UNSET
    new_evt_yn: None | str | Unset = UNSET
    dtl_evt_cont: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        evt_no = self.evt_no

        evt_clss_cd = self.evt_clss_cd

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

        evt_url_addr: None | str | Unset
        if isinstance(self.evt_url_addr, Unset):
            evt_url_addr = UNSET
        else:
            evt_url_addr = self.evt_url_addr

        bnr_img_url_addr: None | str | Unset
        if isinstance(self.bnr_img_url_addr, Unset):
            bnr_img_url_addr = UNSET
        else:
            bnr_img_url_addr = self.bnr_img_url_addr

        dtl_conts_url_addr: None | str | Unset
        if isinstance(self.dtl_conts_url_addr, Unset):
            dtl_conts_url_addr = UNSET
        else:
            dtl_conts_url_addr = self.dtl_conts_url_addr

        frdm_cmps_url_addr: None | str | Unset
        if isinstance(self.frdm_cmps_url_addr, Unset):
            frdm_cmps_url_addr = UNSET
        else:
            frdm_cmps_url_addr = self.frdm_cmps_url_addr

        evt_badge_nm: None | str | Unset
        if isinstance(self.evt_badge_nm, Unset):
            evt_badge_nm = UNSET
        else:
            evt_badge_nm = self.evt_badge_nm

        new_evt_yn: None | str | Unset
        if isinstance(self.new_evt_yn, Unset):
            new_evt_yn = UNSET
        else:
            new_evt_yn = self.new_evt_yn

        dtl_evt_cont: None | str | Unset
        if isinstance(self.dtl_evt_cont, Unset):
            dtl_evt_cont = UNSET
        else:
            dtl_evt_cont = self.dtl_evt_cont

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "evt_no": evt_no,
                "evt_clss_cd": evt_clss_cd,
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
        if evt_url_addr is not UNSET:
            field_dict["evt_url_addr"] = evt_url_addr
        if bnr_img_url_addr is not UNSET:
            field_dict["bnr_img_url_addr"] = bnr_img_url_addr
        if dtl_conts_url_addr is not UNSET:
            field_dict["dtl_conts_url_addr"] = dtl_conts_url_addr
        if frdm_cmps_url_addr is not UNSET:
            field_dict["frdm_cmps_url_addr"] = frdm_cmps_url_addr
        if evt_badge_nm is not UNSET:
            field_dict["evt_badge_nm"] = evt_badge_nm
        if new_evt_yn is not UNSET:
            field_dict["new_evt_yn"] = new_evt_yn
        if dtl_evt_cont is not UNSET:
            field_dict["dtl_evt_cont"] = dtl_evt_cont

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        evt_no = d.pop("evt_no")

        evt_clss_cd = d.pop("evt_clss_cd")

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

        def _parse_evt_url_addr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        evt_url_addr = _parse_evt_url_addr(d.pop("evt_url_addr", UNSET))

        def _parse_bnr_img_url_addr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        bnr_img_url_addr = _parse_bnr_img_url_addr(d.pop("bnr_img_url_addr", UNSET))

        def _parse_dtl_conts_url_addr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dtl_conts_url_addr = _parse_dtl_conts_url_addr(d.pop("dtl_conts_url_addr", UNSET))

        def _parse_frdm_cmps_url_addr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        frdm_cmps_url_addr = _parse_frdm_cmps_url_addr(d.pop("frdm_cmps_url_addr", UNSET))

        def _parse_evt_badge_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        evt_badge_nm = _parse_evt_badge_nm(d.pop("evt_badge_nm", UNSET))

        def _parse_new_evt_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        new_evt_yn = _parse_new_evt_yn(d.pop("new_evt_yn", UNSET))

        def _parse_dtl_evt_cont(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dtl_evt_cont = _parse_dtl_evt_cont(d.pop("dtl_evt_cont", UNSET))

        event_item = cls(
            evt_no=evt_no,
            evt_clss_cd=evt_clss_cd,
            evt_nm=evt_nm,
            evt_strt_dtime=evt_strt_dtime,
            evt_end_dtime=evt_end_dtime,
            evt_prgs_stat_cd=evt_prgs_stat_cd,
            evt_url_addr=evt_url_addr,
            bnr_img_url_addr=bnr_img_url_addr,
            dtl_conts_url_addr=dtl_conts_url_addr,
            frdm_cmps_url_addr=frdm_cmps_url_addr,
            evt_badge_nm=evt_badge_nm,
            new_evt_yn=new_evt_yn,
            dtl_evt_cont=dtl_evt_cont,
        )

        event_item.additional_properties = d
        return event_item

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
