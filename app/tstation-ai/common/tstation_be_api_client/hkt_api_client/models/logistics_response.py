from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="LogisticsResponse")


@_attrs_define
class LogisticsResponse:
    """
    Attributes:
        logistics_qty (int | None | Unset): 물류 재고 수량 (FN_GET_GOODS_STOCK_QTY)
    """

    logistics_qty: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        logistics_qty: int | None | Unset
        if isinstance(self.logistics_qty, Unset):
            logistics_qty = UNSET
        else:
            logistics_qty = self.logistics_qty

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if logistics_qty is not UNSET:
            field_dict["logistics_qty"] = logistics_qty

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_logistics_qty(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        logistics_qty = _parse_logistics_qty(d.pop("logistics_qty", UNSET))

        logistics_response = cls(
            logistics_qty=logistics_qty,
        )

        logistics_response.additional_properties = d
        return logistics_response

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
