from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.maintenance_dday_item import MaintenanceDdayItem


T = TypeVar("T", bound="CarMaintenanceDday")


@_attrs_define
class CarMaintenanceDday:
    """
    Attributes:
        mbr_car_reg_seq (str): 회원 차량 등록 시퀀스
        car_nm (None | str | Unset): 차량명 (제조사 + 모델, 예: '현대 그랜저')
        items (list[MaintenanceDdayItem] | Unset): 해당 차량의 7개 정비 항목 매트릭스
    """

    mbr_car_reg_seq: str
    car_nm: None | str | Unset = UNSET
    items: list[MaintenanceDdayItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        mbr_car_reg_seq = self.mbr_car_reg_seq

        car_nm: None | str | Unset
        if isinstance(self.car_nm, Unset):
            car_nm = UNSET
        else:
            car_nm = self.car_nm

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
                "mbr_car_reg_seq": mbr_car_reg_seq,
            }
        )
        if car_nm is not UNSET:
            field_dict["car_nm"] = car_nm
        if items is not UNSET:
            field_dict["items"] = items

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.maintenance_dday_item import MaintenanceDdayItem

        d = dict(src_dict)
        mbr_car_reg_seq = d.pop("mbr_car_reg_seq")

        def _parse_car_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_nm = _parse_car_nm(d.pop("car_nm", UNSET))

        _items = d.pop("items", UNSET)
        items: list[MaintenanceDdayItem] | Unset = UNSET
        if _items is not UNSET:
            items = []
            for items_item_data in _items:
                items_item = MaintenanceDdayItem.from_dict(items_item_data)

                items.append(items_item)

        car_maintenance_dday = cls(
            mbr_car_reg_seq=mbr_car_reg_seq,
            car_nm=car_nm,
            items=items,
        )

        car_maintenance_dday.additional_properties = d
        return car_maintenance_dday

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
