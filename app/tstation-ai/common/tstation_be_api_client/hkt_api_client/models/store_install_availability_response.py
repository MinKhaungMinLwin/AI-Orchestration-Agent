from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.store_install_availability_item import StoreInstallAvailabilityItem


T = TypeVar("T", bound="StoreInstallAvailabilityResponse")


@_attrs_define
class StoreInstallAvailabilityResponse:
    """
    Attributes:
        qty (int): 요청 수량
        items (list[StoreInstallAvailabilityItem]):
        goods_no (None | str | Unset): 요청 상품 번호
        rsv_sale_yn (None | str | Unset): 예약 판매 여부
    """

    qty: int
    items: list[StoreInstallAvailabilityItem]
    goods_no: None | str | Unset = UNSET
    rsv_sale_yn: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        qty = self.qty

        items = []
        for items_item_data in self.items:
            items_item = items_item_data.to_dict()
            items.append(items_item)

        goods_no: None | str | Unset
        if isinstance(self.goods_no, Unset):
            goods_no = UNSET
        else:
            goods_no = self.goods_no

        rsv_sale_yn: None | str | Unset
        if isinstance(self.rsv_sale_yn, Unset):
            rsv_sale_yn = UNSET
        else:
            rsv_sale_yn = self.rsv_sale_yn

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "qty": qty,
                "items": items,
            }
        )
        if goods_no is not UNSET:
            field_dict["goods_no"] = goods_no
        if rsv_sale_yn is not UNSET:
            field_dict["rsv_sale_yn"] = rsv_sale_yn

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.store_install_availability_item import StoreInstallAvailabilityItem

        d = dict(src_dict)
        qty = d.pop("qty")

        items = []
        _items = d.pop("items")
        for items_item_data in _items:
            items_item = StoreInstallAvailabilityItem.from_dict(items_item_data)

            items.append(items_item)

        def _parse_goods_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        goods_no = _parse_goods_no(d.pop("goods_no", UNSET))

        def _parse_rsv_sale_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rsv_sale_yn = _parse_rsv_sale_yn(d.pop("rsv_sale_yn", UNSET))

        store_install_availability_response = cls(
            qty=qty,
            items=items,
            goods_no=goods_no,
            rsv_sale_yn=rsv_sale_yn,
        )

        store_install_availability_response.additional_properties = d
        return store_install_availability_response

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
