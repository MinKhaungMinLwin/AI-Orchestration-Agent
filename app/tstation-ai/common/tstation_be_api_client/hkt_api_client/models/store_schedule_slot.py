from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="StoreScheduleSlot")


@_attrs_define
class StoreScheduleSlot:
    """
    Attributes:
        cal_day (str): 예약 가능 날짜 (YYYYMMDD)
        tm (str): 예약 가능 시간 (HHMM, 예: '0900', '1030')
    """

    cal_day: str
    tm: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cal_day = self.cal_day

        tm = self.tm

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "cal_day": cal_day,
                "tm": tm,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        cal_day = d.pop("cal_day")

        tm = d.pop("tm")

        store_schedule_slot = cls(
            cal_day=cal_day,
            tm=tm,
        )

        store_schedule_slot.additional_properties = d
        return store_schedule_slot

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
