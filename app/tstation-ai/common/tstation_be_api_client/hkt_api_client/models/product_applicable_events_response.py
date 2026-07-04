from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.product_applicable_event_item import ProductApplicableEventItem


T = TypeVar("T", bound="ProductApplicableEventsResponse")


@_attrs_define
class ProductApplicableEventsResponse:
    """
    Attributes:
        ptrn_cd (str): 상품 패턴 코드
        total (int): 적용 가능한 진행 중 이벤트 수
        items (list[ProductApplicableEventItem] | Unset): 해당 상품 패턴에 적용 가능한 진행 중 이벤트 목록 (EVT_STRT_DTIME DESC)
    """

    ptrn_cd: str
    total: int
    items: list[ProductApplicableEventItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ptrn_cd = self.ptrn_cd

        total = self.total

        items: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.items, Unset):
            items = []
            for items_item_data in self.items:
                items_item = items_item_data.to_dict()
                items.append(items_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ptrn_cd": ptrn_cd,
                "total": total,
            }
        )
        if items is not UNSET:
            field_dict["items"] = items

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.product_applicable_event_item import ProductApplicableEventItem

        d = dict(src_dict)
        ptrn_cd = d.pop("ptrn_cd")

        total = d.pop("total")

        _items = d.pop("items", UNSET)
        items: list[ProductApplicableEventItem] | Unset = UNSET
        if _items is not UNSET:
            items = []
            for items_item_data in _items:
                items_item = ProductApplicableEventItem.from_dict(items_item_data)

                items.append(items_item)

        product_applicable_events_response = cls(
            ptrn_cd=ptrn_cd,
            total=total,
            items=items,
        )

        product_applicable_events_response.additional_properties = d
        return product_applicable_events_response

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
