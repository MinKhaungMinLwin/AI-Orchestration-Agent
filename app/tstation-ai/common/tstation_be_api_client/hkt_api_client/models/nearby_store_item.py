from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="NearbyStoreItem")


@_attrs_define
class NearbyStoreItem:
    """
    Attributes:
        shop_id (str): 매장 ID
        distance_km (float): 거리 (km)
        shop_nm (None | str | Unset): 매장명
        addr_base (None | str | Unset): 일반 주소
        addr_dtl (None | str | Unset): 일반 주소 상세
        road_addr_base (None | str | Unset): 도로명 주소
        road_addr_dtl (None | str | Unset): 도로명 주소 상세
        is_all_my_t (bool | Unset): all my T 매장 여부 (SMART_CARE_SHOP_YN = 'Y') Default: False.
    """

    shop_id: str
    distance_km: float
    shop_nm: None | str | Unset = UNSET
    addr_base: None | str | Unset = UNSET
    addr_dtl: None | str | Unset = UNSET
    road_addr_base: None | str | Unset = UNSET
    road_addr_dtl: None | str | Unset = UNSET
    is_all_my_t: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        shop_id = self.shop_id

        distance_km = self.distance_km

        shop_nm: None | str | Unset
        if isinstance(self.shop_nm, Unset):
            shop_nm = UNSET
        else:
            shop_nm = self.shop_nm

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

        is_all_my_t = self.is_all_my_t

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "shop_id": shop_id,
                "distance_km": distance_km,
            }
        )
        if shop_nm is not UNSET:
            field_dict["shop_nm"] = shop_nm
        if addr_base is not UNSET:
            field_dict["addr_base"] = addr_base
        if addr_dtl is not UNSET:
            field_dict["addr_dtl"] = addr_dtl
        if road_addr_base is not UNSET:
            field_dict["road_addr_base"] = road_addr_base
        if road_addr_dtl is not UNSET:
            field_dict["road_addr_dtl"] = road_addr_dtl
        if is_all_my_t is not UNSET:
            field_dict["is_all_my_t"] = is_all_my_t

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        shop_id = d.pop("shop_id")

        distance_km = d.pop("distance_km")

        def _parse_shop_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_nm = _parse_shop_nm(d.pop("shop_nm", UNSET))

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

        is_all_my_t = d.pop("is_all_my_t", UNSET)

        nearby_store_item = cls(
            shop_id=shop_id,
            distance_km=distance_km,
            shop_nm=shop_nm,
            addr_base=addr_base,
            addr_dtl=addr_dtl,
            road_addr_base=road_addr_base,
            road_addr_dtl=road_addr_dtl,
            is_all_my_t=is_all_my_t,
        )

        nearby_store_item.additional_properties = d
        return nearby_store_item

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
