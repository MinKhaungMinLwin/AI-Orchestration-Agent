from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="QuickOrderRequest")


@_attrs_define
class QuickOrderRequest:
    """
    Attributes:
        goods_no (str): 상품 번호
        ord_qty (int): 주문 수량
        mbr_no (None | str | Unset): 회원 번호 (MBR_NO 또는 CAR_NO? 중 하나 필수)
    """

    goods_no: str
    ord_qty: int
    mbr_no: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_no = self.goods_no

        ord_qty = self.ord_qty

        mbr_no: None | str | Unset
        if isinstance(self.mbr_no, Unset):
            mbr_no = UNSET
        else:
            mbr_no = self.mbr_no

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goods_no": goods_no,
                "ord_qty": ord_qty,
            }
        )
        if mbr_no is not UNSET:
            field_dict["mbr_no"] = mbr_no

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        goods_no = d.pop("goods_no")

        ord_qty = d.pop("ord_qty")

        def _parse_mbr_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mbr_no = _parse_mbr_no(d.pop("mbr_no", UNSET))

        quick_order_request = cls(
            goods_no=goods_no,
            ord_qty=ord_qty,
            mbr_no=mbr_no,
        )

        quick_order_request.additional_properties = d
        return quick_order_request

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
