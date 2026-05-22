from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.maintenance_history_item import MaintenanceHistoryItem


T = TypeVar("T", bound="MaintenanceHistoryResponse")


@_attrs_define
class MaintenanceHistoryResponse:
    """
    Attributes:
        items (list[MaintenanceHistoryItem] | Unset): 최근 정비이력 목록 (정비/장착일 내림차순)
    """

    items: list[MaintenanceHistoryItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        items: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.items, Unset):
            items = []
            for items_item_data in self.items:
                items_item = items_item_data.to_dict()
                items.append(items_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if items is not UNSET:
            field_dict["items"] = items

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.maintenance_history_item import MaintenanceHistoryItem

        d = dict(src_dict)
        _items = d.pop("items", UNSET)
        items: list[MaintenanceHistoryItem] | Unset = UNSET
        if _items is not UNSET:
            items = []
            for items_item_data in _items:
                items_item = MaintenanceHistoryItem.from_dict(items_item_data)

                items.append(items_item)

        maintenance_history_response = cls(
            items=items,
        )

        maintenance_history_response.additional_properties = d
        return maintenance_history_response

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
