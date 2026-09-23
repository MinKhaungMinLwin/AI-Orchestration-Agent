from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="BestSellerSearchRequest")


@_attrs_define
class BestSellerSearchRequest:
    """
    Attributes:
        vehicle_query (None | str | Unset): 자연어 차량 검색어 (예: '그랜저', '벤츠 e300')
        limit (int | Unset): 반환할 상품 수 (1-50, 기본 5) Default: 5.
        months (int | None | Unset): 명시적 기간이 없을 때 최근 N개월
        from_date (datetime.date | None | Unset): 조회 시작일 (YYYY-MM-DD, 있으면 to_date와 함께 우선 사용)
        to_date (datetime.date | None | Unset): 조회 종료일 (YYYY-MM-DD, 있으면 from_date와 함께 우선 사용)
    """

    vehicle_query: None | str | Unset = UNSET
    limit: int | Unset = 5
    months: int | None | Unset = UNSET
    from_date: datetime.date | None | Unset = UNSET
    to_date: datetime.date | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        vehicle_query: None | str | Unset
        if isinstance(self.vehicle_query, Unset):
            vehicle_query = UNSET
        else:
            vehicle_query = self.vehicle_query

        limit = self.limit

        months: int | None | Unset
        if isinstance(self.months, Unset):
            months = UNSET
        else:
            months = self.months

        from_date: None | str | Unset
        if isinstance(self.from_date, Unset):
            from_date = UNSET
        elif isinstance(self.from_date, datetime.date):
            from_date = self.from_date.isoformat()
        else:
            from_date = self.from_date

        to_date: None | str | Unset
        if isinstance(self.to_date, Unset):
            to_date = UNSET
        elif isinstance(self.to_date, datetime.date):
            to_date = self.to_date.isoformat()
        else:
            to_date = self.to_date

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if vehicle_query is not UNSET:
            field_dict["vehicle_query"] = vehicle_query
        if limit is not UNSET:
            field_dict["limit"] = limit
        if months is not UNSET:
            field_dict["months"] = months
        if from_date is not UNSET:
            field_dict["from_date"] = from_date
        if to_date is not UNSET:
            field_dict["to_date"] = to_date

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_vehicle_query(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        vehicle_query = _parse_vehicle_query(d.pop("vehicle_query", UNSET))

        limit = d.pop("limit", UNSET)

        def _parse_months(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        months = _parse_months(d.pop("months", UNSET))

        def _parse_from_date(data: object) -> datetime.date | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                from_date_type_0 = isoparse(data).date()

                return from_date_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.date | None | Unset, data)

        from_date = _parse_from_date(d.pop("from_date", UNSET))

        def _parse_to_date(data: object) -> datetime.date | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                to_date_type_0 = isoparse(data).date()

                return to_date_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.date | None | Unset, data)

        to_date = _parse_to_date(d.pop("to_date", UNSET))

        best_seller_search_request = cls(
            vehicle_query=vehicle_query,
            limit=limit,
            months=months,
            from_date=from_date,
            to_date=to_date,
        )

        best_seller_search_request.additional_properties = d
        return best_seller_search_request

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
