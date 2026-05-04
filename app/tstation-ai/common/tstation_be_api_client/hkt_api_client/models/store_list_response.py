from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.store_list_item import StoreListItem


T = TypeVar("T", bound="StoreListResponse")


@_attrs_define
class StoreListResponse:
    """
    Attributes:
        stores (list[StoreListItem]):
    """

    stores: list[StoreListItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        stores = []
        for stores_item_data in self.stores:
            stores_item = stores_item_data.to_dict()
            stores.append(stores_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "stores": stores,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.store_list_item import StoreListItem

        d = dict(src_dict)
        stores = []
        _stores = d.pop("stores")
        for stores_item_data in _stores:
            stores_item = StoreListItem.from_dict(stores_item_data)

            stores.append(stores_item)

        store_list_response = cls(
            stores=stores,
        )

        store_list_response.additional_properties = d
        return store_list_response

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
