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
        road_addr_base (None | str | Unset): 도로명주소
        shop_biz_strt_time (None | str | Unset): 영업 시작 시간
        shop_biz_end_time (None | str | Unset): 영업 종료 시간
    """

    shop_id: str
    shop_nm: None | str | Unset = UNSET
    road_addr_base: None | str | Unset = UNSET
    shop_biz_strt_time: None | str | Unset = UNSET
    shop_biz_end_time: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        shop_id = self.shop_id

        shop_nm: None | str | Unset
        if isinstance(self.shop_nm, Unset):
            shop_nm = UNSET
        else:
            shop_nm = self.shop_nm

        road_addr_base: None | str | Unset
        if isinstance(self.road_addr_base, Unset):
            road_addr_base = UNSET
        else:
            road_addr_base = self.road_addr_base

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

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "shop_id": shop_id,
            }
        )
        if shop_nm is not UNSET:
            field_dict["shop_nm"] = shop_nm
        if road_addr_base is not UNSET:
            field_dict["road_addr_base"] = road_addr_base
        if shop_biz_strt_time is not UNSET:
            field_dict["shop_biz_strt_time"] = shop_biz_strt_time
        if shop_biz_end_time is not UNSET:
            field_dict["shop_biz_end_time"] = shop_biz_end_time

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

        def _parse_road_addr_base(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        road_addr_base = _parse_road_addr_base(d.pop("road_addr_base", UNSET))

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

        store_list_item = cls(
            shop_id=shop_id,
            shop_nm=shop_nm,
            road_addr_base=road_addr_base,
            shop_biz_strt_time=shop_biz_strt_time,
            shop_biz_end_time=shop_biz_end_time,
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
