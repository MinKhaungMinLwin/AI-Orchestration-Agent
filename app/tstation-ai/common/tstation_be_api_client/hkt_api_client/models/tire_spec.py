from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="TireSpec")


@_attrs_define
class TireSpec:
    """
    Attributes:
        tire_width (int | None | Unset): 단면폭 (TIRE_WIDTH)
        tire_series (int | None | Unset): 편평비 (TIRE_SERIES)
        inch (int | None | Unset): 인치 (INCH)
    """

    tire_width: int | None | Unset = UNSET
    tire_series: int | None | Unset = UNSET
    inch: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tire_width: int | None | Unset
        if isinstance(self.tire_width, Unset):
            tire_width = UNSET
        else:
            tire_width = self.tire_width

        tire_series: int | None | Unset
        if isinstance(self.tire_series, Unset):
            tire_series = UNSET
        else:
            tire_series = self.tire_series

        inch: int | None | Unset
        if isinstance(self.inch, Unset):
            inch = UNSET
        else:
            inch = self.inch

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if tire_width is not UNSET:
            field_dict["tire_width"] = tire_width
        if tire_series is not UNSET:
            field_dict["tire_series"] = tire_series
        if inch is not UNSET:
            field_dict["inch"] = inch

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_tire_width(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        tire_width = _parse_tire_width(d.pop("tire_width", UNSET))

        def _parse_tire_series(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        tire_series = _parse_tire_series(d.pop("tire_series", UNSET))

        def _parse_inch(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        inch = _parse_inch(d.pop("inch", UNSET))

        tire_spec = cls(
            tire_width=tire_width,
            tire_series=tire_series,
            inch=inch,
        )

        tire_spec.additional_properties = d
        return tire_spec

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
