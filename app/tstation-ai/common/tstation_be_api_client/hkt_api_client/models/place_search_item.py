from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PlaceSearchItem")


@_attrs_define
class PlaceSearchItem:
    """
    Attributes:
        title (str): 장소명
        x (str): X 좌표 (경도)
        y (str): Y 좌표 (위도)
        road_addr (None | str | Unset): 도로명 주소
    """

    title: str
    x: str
    y: str
    road_addr: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        title = self.title

        x = self.x

        y = self.y

        road_addr: None | str | Unset
        if isinstance(self.road_addr, Unset):
            road_addr = UNSET
        else:
            road_addr = self.road_addr

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "title": title,
                "x": x,
                "y": y,
            }
        )
        if road_addr is not UNSET:
            field_dict["road_addr"] = road_addr

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        title = d.pop("title")

        x = d.pop("x")

        y = d.pop("y")

        def _parse_road_addr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        road_addr = _parse_road_addr(d.pop("road_addr", UNSET))

        place_search_item = cls(
            title=title,
            x=x,
            y=y,
            road_addr=road_addr,
        )

        place_search_item.additional_properties = d
        return place_search_item

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
