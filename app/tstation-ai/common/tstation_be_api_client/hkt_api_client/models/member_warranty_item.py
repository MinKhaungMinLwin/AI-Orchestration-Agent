from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MemberWarrantyItem")


@_attrs_define
class MemberWarrantyItem:
    """회원이 보유한 워런티 1건 (ET_DGTL_WRT_REG_INFO).

    Attributes:
        wrt_tp_cd (str): 워런티 타입 코드. '10'=품질보증 / '20'=안심서비스 / '30'=30일 해피보증 / '40'=코드절상 무상교환
        wrt_nm (str): 워런티 한글명 (사용자 노출용). 회원 보유 응답에서는 WRT_TP_CD='20' 은 '안심서비스' 로 단일 표기 (가입 레코드 단위는 안심/안심플러스 구분 컬럼 부재 가정).
        wrt_prgs_stat_cd (str): 워런티 진행상태 코드 (WRT_PRGS_STAT_CD). '200'=가입완료 / '300'=기간만료 / '400'=보상완료. '100' (가입대기) 는 응답
            단계에서 제외된다.
        wrt_prgs_stat_nm (str): 진행상태 한글명
        wrt_reg_date (None | str | Unset): 워런티 가입일자 (YYYY-MM-DD)
        wrt_exp_date (None | str | Unset): 워런티 만료일자 (YYYY-MM-DD)
    """

    wrt_tp_cd: str
    wrt_nm: str
    wrt_prgs_stat_cd: str
    wrt_prgs_stat_nm: str
    wrt_reg_date: None | str | Unset = UNSET
    wrt_exp_date: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        wrt_tp_cd = self.wrt_tp_cd

        wrt_nm = self.wrt_nm

        wrt_prgs_stat_cd = self.wrt_prgs_stat_cd

        wrt_prgs_stat_nm = self.wrt_prgs_stat_nm

        wrt_reg_date: None | str | Unset
        if isinstance(self.wrt_reg_date, Unset):
            wrt_reg_date = UNSET
        else:
            wrt_reg_date = self.wrt_reg_date

        wrt_exp_date: None | str | Unset
        if isinstance(self.wrt_exp_date, Unset):
            wrt_exp_date = UNSET
        else:
            wrt_exp_date = self.wrt_exp_date

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "wrt_tp_cd": wrt_tp_cd,
                "wrt_nm": wrt_nm,
                "wrt_prgs_stat_cd": wrt_prgs_stat_cd,
                "wrt_prgs_stat_nm": wrt_prgs_stat_nm,
            }
        )
        if wrt_reg_date is not UNSET:
            field_dict["wrt_reg_date"] = wrt_reg_date
        if wrt_exp_date is not UNSET:
            field_dict["wrt_exp_date"] = wrt_exp_date

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        wrt_tp_cd = d.pop("wrt_tp_cd")

        wrt_nm = d.pop("wrt_nm")

        wrt_prgs_stat_cd = d.pop("wrt_prgs_stat_cd")

        wrt_prgs_stat_nm = d.pop("wrt_prgs_stat_nm")

        def _parse_wrt_reg_date(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        wrt_reg_date = _parse_wrt_reg_date(d.pop("wrt_reg_date", UNSET))

        def _parse_wrt_exp_date(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        wrt_exp_date = _parse_wrt_exp_date(d.pop("wrt_exp_date", UNSET))

        member_warranty_item = cls(
            wrt_tp_cd=wrt_tp_cd,
            wrt_nm=wrt_nm,
            wrt_prgs_stat_cd=wrt_prgs_stat_cd,
            wrt_prgs_stat_nm=wrt_prgs_stat_nm,
            wrt_reg_date=wrt_reg_date,
            wrt_exp_date=wrt_exp_date,
        )

        member_warranty_item.additional_properties = d
        return member_warranty_item

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
