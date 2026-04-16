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
        rsv_sale_yn (None | str | Unset): 예약 판매 여부 (PR_GOODS_BASE.RSV_SALE_YN). Y=예약판매 가능
    """

    logistics_qty: int | None | Unset = UNSET
    rsv_sale_yn: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        logistics_qty: int | None | Unset
        if isinstance(self.logistics_qty, Unset):
            logistics_qty = UNSET
        else:
            logistics_qty = self.logistics_qty

        rsv_sale_yn: None | str | Unset
        if isinstance(self.rsv_sale_yn, Unset):
            rsv_sale_yn = UNSET
        else:
            rsv_sale_yn = self.rsv_sale_yn

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if logistics_qty is not UNSET:
            field_dict["logistics_qty"] = logistics_qty
        if rsv_sale_yn is not UNSET:
            field_dict["rsv_sale_yn"] = rsv_sale_yn

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

        def _parse_rsv_sale_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rsv_sale_yn = _parse_rsv_sale_yn(d.pop("rsv_sale_yn", UNSET))

        logistics_response = cls(
            logistics_qty=logistics_qty,
            rsv_sale_yn=rsv_sale_yn,
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
