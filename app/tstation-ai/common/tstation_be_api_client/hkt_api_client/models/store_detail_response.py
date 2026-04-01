from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="StoreDetailResponse")


@_attrs_define
class StoreDetailResponse:
    """
    Attributes:
        shop_nm (None | str | Unset): 매장명
        tel_no (None | str | Unset): 전화번호
        holiday (None | str | Unset): 휴무일
        shop_biz_strt_time (None | str | Unset): 영업 시작 시간
        shop_biz_end_time (None | str | Unset): 영업 종료 시간
        shop_biz_strt_wday (None | str | Unset): 영업 시작 요일 (예: 월요일)
        shop_biz_end_wday (None | str | Unset): 영업 종료 요일 (예: 금요일)
        shop_sat_strt_time (None | str | Unset): 토요일 영업 시작 시간
        shop_sat_end_time (None | str | Unset): 토요일 영업 종료 시간
        available_slots (list[str] | Unset): 예약 가능 시간 슬롯 목록 (예: ['09','10','11'])
    """

    shop_nm: None | str | Unset = UNSET
    tel_no: None | str | Unset = UNSET
    holiday: None | str | Unset = UNSET
    shop_biz_strt_time: None | str | Unset = UNSET
    shop_biz_end_time: None | str | Unset = UNSET
    shop_biz_strt_wday: None | str | Unset = UNSET
    shop_biz_end_wday: None | str | Unset = UNSET
    shop_sat_strt_time: None | str | Unset = UNSET
    shop_sat_end_time: None | str | Unset = UNSET
    available_slots: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
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

        holiday: None | str | Unset
        if isinstance(self.holiday, Unset):
            holiday = UNSET
        else:
            holiday = self.holiday

        shop_biz_strt_time: None | str | Unset
        if isinstance(self.shop_biz_strt_time, Unset):
            shop_biz_strt_time = UNSET
        else:
            shop_biz_strt_time = self.shop_biz_strt_time

        shop_biz_end_time: None | str | Unset
        if isinstance(self.shop_biz_end_time, Unset):
            shop_biz_end_time = UNSET
        else:
            shop_biz_end_time = self.shop_biz_end_time

        shop_biz_strt_wday: None | str | Unset
        if isinstance(self.shop_biz_strt_wday, Unset):
            shop_biz_strt_wday = UNSET
        else:
            shop_biz_strt_wday = self.shop_biz_strt_wday

        shop_biz_end_wday: None | str | Unset
        if isinstance(self.shop_biz_end_wday, Unset):
            shop_biz_end_wday = UNSET
        else:
            shop_biz_end_wday = self.shop_biz_end_wday

        shop_sat_strt_time: None | str | Unset
        if isinstance(self.shop_sat_strt_time, Unset):
            shop_sat_strt_time = UNSET
        else:
            shop_sat_strt_time = self.shop_sat_strt_time

        shop_sat_end_time: None | str | Unset
        if isinstance(self.shop_sat_end_time, Unset):
            shop_sat_end_time = UNSET
        else:
            shop_sat_end_time = self.shop_sat_end_time

        available_slots: list[str] | Unset = UNSET
        if not isinstance(self.available_slots, Unset):
            available_slots = self.available_slots

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if shop_nm is not UNSET:
            field_dict["shop_nm"] = shop_nm
        if tel_no is not UNSET:
            field_dict["tel_no"] = tel_no
        if holiday is not UNSET:
            field_dict["holiday"] = holiday
        if shop_biz_strt_time is not UNSET:
            field_dict["shop_biz_strt_time"] = shop_biz_strt_time
        if shop_biz_end_time is not UNSET:
            field_dict["shop_biz_end_time"] = shop_biz_end_time
        if shop_biz_strt_wday is not UNSET:
            field_dict["shop_biz_strt_wday"] = shop_biz_strt_wday
        if shop_biz_end_wday is not UNSET:
            field_dict["shop_biz_end_wday"] = shop_biz_end_wday
        if shop_sat_strt_time is not UNSET:
            field_dict["shop_sat_strt_time"] = shop_sat_strt_time
        if shop_sat_end_time is not UNSET:
            field_dict["shop_sat_end_time"] = shop_sat_end_time
        if available_slots is not UNSET:
            field_dict["available_slots"] = available_slots

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

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

        def _parse_holiday(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        holiday = _parse_holiday(d.pop("holiday", UNSET))

        def _parse_shop_biz_strt_time(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_biz_strt_time = _parse_shop_biz_strt_time(d.pop("shop_biz_strt_time", UNSET))

        def _parse_shop_biz_end_time(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_biz_end_time = _parse_shop_biz_end_time(d.pop("shop_biz_end_time", UNSET))

        def _parse_shop_biz_strt_wday(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_biz_strt_wday = _parse_shop_biz_strt_wday(d.pop("shop_biz_strt_wday", UNSET))

        def _parse_shop_biz_end_wday(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_biz_end_wday = _parse_shop_biz_end_wday(d.pop("shop_biz_end_wday", UNSET))

        def _parse_shop_sat_strt_time(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_sat_strt_time = _parse_shop_sat_strt_time(d.pop("shop_sat_strt_time", UNSET))

        def _parse_shop_sat_end_time(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_sat_end_time = _parse_shop_sat_end_time(d.pop("shop_sat_end_time", UNSET))

        available_slots = cast(list[str], d.pop("available_slots", UNSET))

        store_detail_response = cls(
            shop_nm=shop_nm,
            tel_no=tel_no,
            holiday=holiday,
            shop_biz_strt_time=shop_biz_strt_time,
            shop_biz_end_time=shop_biz_end_time,
            shop_biz_strt_wday=shop_biz_strt_wday,
            shop_biz_end_wday=shop_biz_end_wday,
            shop_sat_strt_time=shop_sat_strt_time,
            shop_sat_end_time=shop_sat_end_time,
            available_slots=available_slots,
        )

        store_detail_response.additional_properties = d
        return store_detail_response

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
