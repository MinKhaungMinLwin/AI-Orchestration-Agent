from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.best_seller_search_response_result_scope import BestSellerSearchResponseResultScope
from ..models.best_seller_search_response_status import BestSellerSearchResponseStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.best_seller_fallback_option import BestSellerFallbackOption
    from ..models.best_seller_item import BestSellerItem
    from ..models.best_seller_search_period import BestSellerSearchPeriod
    from ..models.vehicle_resolution import VehicleResolution


T = TypeVar("T", bound="BestSellerSearchResponse")


@_attrs_define
class BestSellerSearchResponse:
    """
    Attributes:
        total (int): 반환된 상품 수
        period (BestSellerSearchPeriod):
        result_scope (BestSellerSearchResponseResultScope): 집계 범위
        status (BestSellerSearchResponseStatus): 최종 결과 상태
        items (list[BestSellerItem] | Unset): 베스트셀러 상품 목록
        vehicle_query (None | str | Unset): 원본 차량 검색어
        vehicle_resolution (None | Unset | VehicleResolution): 차량 해석 결과
        fallback_options (list[BestSellerFallbackOption] | Unset): 차량 해석 실패 또는 주문 데이터 없음 시 대체 안내 옵션
    """

    total: int
    period: BestSellerSearchPeriod
    result_scope: BestSellerSearchResponseResultScope
    status: BestSellerSearchResponseStatus
    items: list[BestSellerItem] | Unset = UNSET
    vehicle_query: None | str | Unset = UNSET
    vehicle_resolution: None | Unset | VehicleResolution = UNSET
    fallback_options: list[BestSellerFallbackOption] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.vehicle_resolution import VehicleResolution

        total = self.total

        period = self.period.to_dict()

        result_scope = self.result_scope.value

        status = self.status.value

        items: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.items, Unset):
            items = []
            for items_item_data in self.items:
                items_item = items_item_data.to_dict()
                items.append(items_item)

        vehicle_query: None | str | Unset
        if isinstance(self.vehicle_query, Unset):
            vehicle_query = UNSET
        else:
            vehicle_query = self.vehicle_query

        vehicle_resolution: dict[str, Any] | None | Unset
        if isinstance(self.vehicle_resolution, Unset):
            vehicle_resolution = UNSET
        elif isinstance(self.vehicle_resolution, VehicleResolution):
            vehicle_resolution = self.vehicle_resolution.to_dict()
        else:
            vehicle_resolution = self.vehicle_resolution

        fallback_options: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.fallback_options, Unset):
            fallback_options = []
            for fallback_options_item_data in self.fallback_options:
                fallback_options_item = fallback_options_item_data.to_dict()
                fallback_options.append(fallback_options_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total": total,
                "period": period,
                "result_scope": result_scope,
                "status": status,
            }
        )
        if items is not UNSET:
            field_dict["items"] = items
        if vehicle_query is not UNSET:
            field_dict["vehicle_query"] = vehicle_query
        if vehicle_resolution is not UNSET:
            field_dict["vehicle_resolution"] = vehicle_resolution
        if fallback_options is not UNSET:
            field_dict["fallback_options"] = fallback_options

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.best_seller_fallback_option import BestSellerFallbackOption
        from ..models.best_seller_item import BestSellerItem
        from ..models.best_seller_search_period import BestSellerSearchPeriod
        from ..models.vehicle_resolution import VehicleResolution

        d = dict(src_dict)
        total = d.pop("total")

        period = BestSellerSearchPeriod.from_dict(d.pop("period"))

        result_scope = BestSellerSearchResponseResultScope(d.pop("result_scope"))

        status = BestSellerSearchResponseStatus(d.pop("status"))

        _items = d.pop("items", UNSET)
        items: list[BestSellerItem] | Unset = UNSET
        if _items is not UNSET:
            items = []
            for items_item_data in _items:
                items_item = BestSellerItem.from_dict(items_item_data)

                items.append(items_item)

        def _parse_vehicle_query(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        vehicle_query = _parse_vehicle_query(d.pop("vehicle_query", UNSET))

        def _parse_vehicle_resolution(data: object) -> None | Unset | VehicleResolution:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                vehicle_resolution_type_0 = VehicleResolution.from_dict(data)

                return vehicle_resolution_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | VehicleResolution, data)

        vehicle_resolution = _parse_vehicle_resolution(d.pop("vehicle_resolution", UNSET))

        _fallback_options = d.pop("fallback_options", UNSET)
        fallback_options: list[BestSellerFallbackOption] | Unset = UNSET
        if _fallback_options is not UNSET:
            fallback_options = []
            for fallback_options_item_data in _fallback_options:
                fallback_options_item = BestSellerFallbackOption.from_dict(fallback_options_item_data)

                fallback_options.append(fallback_options_item)

        best_seller_search_response = cls(
            total=total,
            period=period,
            result_scope=result_scope,
            status=status,
            items=items,
            vehicle_query=vehicle_query,
            vehicle_resolution=vehicle_resolution,
            fallback_options=fallback_options,
        )

        best_seller_search_response.additional_properties = d
        return best_seller_search_response

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
