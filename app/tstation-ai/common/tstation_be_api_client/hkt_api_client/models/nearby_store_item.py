from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="NearbyStoreItem")


@_attrs_define
class NearbyStoreItem:
    """
    Attributes:
        shop_id (str): 매장 ID
        distance_km (float): 거리 (km)
    """

    shop_id: str
    distance_km: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        shop_id = self.shop_id

        distance_km = self.distance_km

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "shop_id": shop_id,
                "distance_km": distance_km,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        shop_id = d.pop("shop_id")

        distance_km = d.pop("distance_km")

        nearby_store_item = cls(
            shop_id=shop_id,
            distance_km=distance_km,
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
