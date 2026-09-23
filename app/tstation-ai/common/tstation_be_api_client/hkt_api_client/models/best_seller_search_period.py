from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.best_seller_search_period_mode import BestSellerSearchPeriodMode

T = TypeVar("T", bound="BestSellerSearchPeriod")


@_attrs_define
class BestSellerSearchPeriod:
    """
    Attributes:
        mode (BestSellerSearchPeriodMode): 기간 계산 방식
        months (int): 적용된 개월 수
        from_date (str): 집계 시작일 (inclusive)
        to_date (str): 집계 종료일 (inclusive 표기)
    """

    mode: BestSellerSearchPeriodMode
    months: int
    from_date: str
    to_date: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        mode = self.mode.value

        months = self.months

        from_date = self.from_date

        to_date = self.to_date

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "mode": mode,
                "months": months,
                "from_date": from_date,
                "to_date": to_date,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        mode = BestSellerSearchPeriodMode(d.pop("mode"))

        months = d.pop("months")

        from_date = d.pop("from_date")

        to_date = d.pop("to_date")

        best_seller_search_period = cls(
            mode=mode,
            months=months,
            from_date=from_date,
            to_date=to_date,
        )

        best_seller_search_period.additional_properties = d
        return best_seller_search_period

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
