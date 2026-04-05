from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="OrderListItem")


@_attrs_define
class OrderListItem:
    """
    Attributes:
        ord_no (str): 주문 번호
        goods_nm (None | str | Unset): 상품명
        ord_qty (int | None | Unset): 주문 수량
        sys_reg_dtime (None | str | Unset): 시스템 등록 일시
    """

    ord_no: str
    goods_nm: None | str | Unset = UNSET
    ord_qty: int | None | Unset = UNSET
    sys_reg_dtime: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ord_no = self.ord_no

        goods_nm: None | str | Unset
        if isinstance(self.goods_nm, Unset):
            goods_nm = UNSET
        else:
            goods_nm = self.goods_nm

        ord_qty: int | None | Unset
        if isinstance(self.ord_qty, Unset):
            ord_qty = UNSET
        else:
            ord_qty = self.ord_qty

        sys_reg_dtime: None | str | Unset
        if isinstance(self.sys_reg_dtime, Unset):
            sys_reg_dtime = UNSET
        else:
            sys_reg_dtime = self.sys_reg_dtime

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ord_no": ord_no,
            }
        )
        if goods_nm is not UNSET:
            field_dict["goods_nm"] = goods_nm
        if ord_qty is not UNSET:
            field_dict["ord_qty"] = ord_qty
        if sys_reg_dtime is not UNSET:
            field_dict["sys_reg_dtime"] = sys_reg_dtime

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ord_no = d.pop("ord_no")

        def _parse_goods_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        goods_nm = _parse_goods_nm(d.pop("goods_nm", UNSET))

        def _parse_ord_qty(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ord_qty = _parse_ord_qty(d.pop("ord_qty", UNSET))

        def _parse_sys_reg_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sys_reg_dtime = _parse_sys_reg_dtime(d.pop("sys_reg_dtime", UNSET))

        order_list_item = cls(
            ord_no=ord_no,
            goods_nm=goods_nm,
            ord_qty=ord_qty,
            sys_reg_dtime=sys_reg_dtime,
        )

        order_list_item.additional_properties = d
        return order_list_item

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
