from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.shop_id_item import ShopIdItem


T = TypeVar("T", bound="StoreInventoryResponse")


@_attrs_define
class StoreInventoryResponse:
    """
    Attributes:
        today_shop_array (list[ShopIdItem] | Unset): 오늘 장착 가능 매장 목록
        tna_shop_array (list[ShopIdItem] | Unset): T바로배송 가능 매장 목록
    """

    today_shop_array: list[ShopIdItem] | Unset = UNSET
    tna_shop_array: list[ShopIdItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        today_shop_array: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.today_shop_array, Unset):
            today_shop_array = []
            for today_shop_array_item_data in self.today_shop_array:
                today_shop_array_item = today_shop_array_item_data.to_dict()
                today_shop_array.append(today_shop_array_item)

        tna_shop_array: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.tna_shop_array, Unset):
            tna_shop_array = []
            for tna_shop_array_item_data in self.tna_shop_array:
                tna_shop_array_item = tna_shop_array_item_data.to_dict()
                tna_shop_array.append(tna_shop_array_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if today_shop_array is not UNSET:
            field_dict["todayShopArray"] = today_shop_array
        if tna_shop_array is not UNSET:
            field_dict["tnaShopArray"] = tna_shop_array

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.shop_id_item import ShopIdItem

        d = dict(src_dict)
        _today_shop_array = d.pop("todayShopArray", UNSET)
        today_shop_array: list[ShopIdItem] | Unset = UNSET
        if _today_shop_array is not UNSET:
            today_shop_array = []
            for today_shop_array_item_data in _today_shop_array:
                today_shop_array_item = ShopIdItem.from_dict(today_shop_array_item_data)

                today_shop_array.append(today_shop_array_item)

        _tna_shop_array = d.pop("tnaShopArray", UNSET)
        tna_shop_array: list[ShopIdItem] | Unset = UNSET
        if _tna_shop_array is not UNSET:
            tna_shop_array = []
            for tna_shop_array_item_data in _tna_shop_array:
                tna_shop_array_item = ShopIdItem.from_dict(tna_shop_array_item_data)

                tna_shop_array.append(tna_shop_array_item)

        store_inventory_response = cls(
            today_shop_array=today_shop_array,
            tna_shop_array=tna_shop_array,
        )

        store_inventory_response.additional_properties = d
        return store_inventory_response

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
