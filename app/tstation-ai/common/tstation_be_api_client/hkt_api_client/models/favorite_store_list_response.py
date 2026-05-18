from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.favorite_store_item import FavoriteStoreItem


T = TypeVar("T", bound="FavoriteStoreListResponse")


@_attrs_define
class FavoriteStoreListResponse:
    """
    Attributes:
        stores (list[FavoriteStoreItem] | Unset): 회원이 단골 등록한 매장 목록. MYSHOP_INFO_STS_CD='100' 만 포함. 매장명 가나다 순.
    """

    stores: list[FavoriteStoreItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        stores: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.stores, Unset):
            stores = []
            for stores_item_data in self.stores:
                stores_item = stores_item_data.to_dict()
                stores.append(stores_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if stores is not UNSET:
            field_dict["stores"] = stores

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.favorite_store_item import FavoriteStoreItem

        d = dict(src_dict)
        _stores = d.pop("stores", UNSET)
        stores: list[FavoriteStoreItem] | Unset = UNSET
        if _stores is not UNSET:
            stores = []
            for stores_item_data in _stores:
                stores_item = FavoriteStoreItem.from_dict(stores_item_data)

                stores.append(stores_item)

        favorite_store_list_response = cls(
            stores=stores,
        )

        favorite_store_list_response.additional_properties = d
        return favorite_store_list_response

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
