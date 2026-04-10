from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="StoreListItem")


@_attrs_define
class StoreListItem:
    """
    Attributes:
        shop_id (str): 매장 ID
        shop_nm (None | str | Unset): 매장명
        is_all_my_t (bool | Unset): all my T 매장 여부 (SMART_CARE_SHOP_YN = 'Y') Default: False.
        is_installable (bool | Unset): 쇼핑 장착 가능 매장 여부 (SMART_CARE_SHOP_YN IN ('Y','E')) Default: False.
        addr_base (None | str | Unset): 일반주소
        addr_dtl (None | str | Unset): 일반주소
        road_addr_base (None | str | Unset): 도로명주소
        road_addr_dtl (None | str | Unset): 도로명주소 상세
        shop_biz_strt_time (None | str | Unset): 영업 시작 시간
        shop_biz_end_time (None | str | Unset): 영업 종료 시간
        shop_biz_strt_wday (None | str | Unset): 영업 시작 요일 (예: 월요일)
        shop_biz_end_wday (None | str | Unset): 영업 종료 요일 (예: 금요일)
        shop_sat_strt_time (None | str | Unset): 토요일 영업 시작 시간
        shop_sat_end_time (None | str | Unset): 토요일 영업 종료 시간
        distance_km (float | None | Unset): 좌표 기준 거리 (km), 좌표 검색 시에만 반환
    """

    shop_id: str
    shop_nm: None | str | Unset = UNSET
    is_all_my_t: bool | Unset = False
    is_installable: bool | Unset = False
    addr_base: None | str | Unset = UNSET
    addr_dtl: None | str | Unset = UNSET
    road_addr_base: None | str | Unset = UNSET
    road_addr_dtl: None | str | Unset = UNSET
    shop_biz_strt_time: None | str | Unset = UNSET
    shop_biz_end_time: None | str | Unset = UNSET
    shop_biz_strt_wday: None | str | Unset = UNSET
    shop_biz_end_wday: None | str | Unset = UNSET
    shop_sat_strt_time: None | str | Unset = UNSET
    shop_sat_end_time: None | str | Unset = UNSET
    distance_km: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        shop_id = self.shop_id

        shop_nm: None | str | Unset
        if isinstance(self.shop_nm, Unset):
            shop_nm = UNSET
        else:
            shop_nm = self.shop_nm

        is_all_my_t = self.is_all_my_t

        is_installable = self.is_installable

        addr_base: None | str | Unset
        if isinstance(self.addr_base, Unset):
            addr_base = UNSET
        else:
            addr_base = self.addr_base

        addr_dtl: None | str | Unset
        if isinstance(self.addr_dtl, Unset):
            addr_dtl = UNSET
        else:
            addr_dtl = self.addr_dtl

        road_addr_base: None | str | Unset
        if isinstance(self.road_addr_base, Unset):
            road_addr_base = UNSET
        else:
            road_addr_base = self.road_addr_base

        road_addr_dtl: None | str | Unset
        if isinstance(self.road_addr_dtl, Unset):
            road_addr_dtl = UNSET
        else:
            road_addr_dtl = self.road_addr_dtl

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

        distance_km: float | None | Unset
        if isinstance(self.distance_km, Unset):
            distance_km = UNSET
        else:
            distance_km = self.distance_km

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "shop_id": shop_id,
            }
        )
        if shop_nm is not UNSET:
            field_dict["shop_nm"] = shop_nm
        if is_all_my_t is not UNSET:
            field_dict["is_all_my_t"] = is_all_my_t
        if is_installable is not UNSET:
            field_dict["is_installable"] = is_installable
        if addr_base is not UNSET:
            field_dict["addr_base"] = addr_base
        if addr_dtl is not UNSET:
            field_dict["addr_dtl"] = addr_dtl
        if road_addr_base is not UNSET:
            field_dict["road_addr_base"] = road_addr_base
        if road_addr_dtl is not UNSET:
            field_dict["road_addr_dtl"] = road_addr_dtl
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
        if distance_km is not UNSET:
            field_dict["distance_km"] = distance_km

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        shop_id = d.pop("shop_id")

        def _parse_shop_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_nm = _parse_shop_nm(d.pop("shop_nm", UNSET))

        is_all_my_t = d.pop("is_all_my_t", UNSET)

        is_installable = d.pop("is_installable", UNSET)

        def _parse_addr_base(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        addr_base = _parse_addr_base(d.pop("addr_base", UNSET))

        def _parse_addr_dtl(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        addr_dtl = _parse_addr_dtl(d.pop("addr_dtl", UNSET))

        def _parse_road_addr_base(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        road_addr_base = _parse_road_addr_base(d.pop("road_addr_base", UNSET))

        def _parse_road_addr_dtl(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        road_addr_dtl = _parse_road_addr_dtl(d.pop("road_addr_dtl", UNSET))

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

        def _parse_distance_km(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        distance_km = _parse_distance_km(d.pop("distance_km", UNSET))

        store_list_item = cls(
            shop_id=shop_id,
            shop_nm=shop_nm,
            is_all_my_t=is_all_my_t,
            is_installable=is_installable,
            addr_base=addr_base,
            addr_dtl=addr_dtl,
            road_addr_base=road_addr_base,
            road_addr_dtl=road_addr_dtl,
            shop_biz_strt_time=shop_biz_strt_time,
            shop_biz_end_time=shop_biz_end_time,
            shop_biz_strt_wday=shop_biz_strt_wday,
            shop_biz_end_wday=shop_biz_end_wday,
            shop_sat_strt_time=shop_sat_strt_time,
            shop_sat_end_time=shop_sat_end_time,
            distance_km=distance_km,
        )

        store_list_item.additional_properties = d
        return store_list_item

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
