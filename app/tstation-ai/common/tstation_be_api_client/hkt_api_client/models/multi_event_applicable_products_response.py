from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.event_applicable_products_group import EventApplicableProductsGroup


T = TypeVar("T", bound="MultiEventApplicableProductsResponse")


@_attrs_define
class MultiEventApplicableProductsResponse:
    """
    Attributes:
        total_events (int): 요청 이벤트 중 매핑된 상품이 1개 이상인 이벤트 수
        total_products (int): 모든 이벤트의 총 상품 row 수 (이벤트 간 중복 별도 카운트)
        events (list[EventApplicableProductsGroup] | Unset): 이벤트별 적용 가능 상품 그룹 목록
    """

    total_events: int
    total_products: int
    events: list[EventApplicableProductsGroup] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total_events = self.total_events

        total_products = self.total_products

        events: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.events, Unset):
            events = []
            for events_item_data in self.events:
                events_item = events_item_data.to_dict()
                events.append(events_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total_events": total_events,
                "total_products": total_products,
            }
        )
        if events is not UNSET:
            field_dict["events"] = events

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.event_applicable_products_group import EventApplicableProductsGroup

        d = dict(src_dict)
        total_events = d.pop("total_events")

        total_products = d.pop("total_products")

        _events = d.pop("events", UNSET)
        events: list[EventApplicableProductsGroup] | Unset = UNSET
        if _events is not UNSET:
            events = []
            for events_item_data in _events:
                events_item = EventApplicableProductsGroup.from_dict(events_item_data)

                events.append(events_item)

        multi_event_applicable_products_response = cls(
            total_events=total_events,
            total_products=total_products,
            events=events,
        )

        multi_event_applicable_products_response.additional_properties = d
        return multi_event_applicable_products_response

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
