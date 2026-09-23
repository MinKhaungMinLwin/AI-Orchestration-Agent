from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.schedule_mode import ScheduleMode
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.store_schedule_slot import StoreScheduleSlot


T = TypeVar("T", bound="StoreInstallAvailabilityItem")


@_attrs_define
class StoreInstallAvailabilityItem:
    """
    Attributes:
        shop_id (str): 매장 ID
        status (str): available / no_inventory / no_slots / not_found
        shop_nm (None | str | Unset): 매장명
        mode (None | ScheduleMode | Unset): BE가 재고 상태로 결정한 스케줄 조회 모드
        has_today_stock (bool | Unset): 오늘서비스 재고 가능 매장 여부 Default: False.
        has_tna_stock (bool | Unset): T바로배송 재고 가능 매장 여부 Default: False.
        has_logistics_stock (bool | Unset): 물류 재고 가능 여부 Default: False.
        is_installable (bool | Unset): 쇼핑 장착 가능 매장 여부 (SMART_CARE_SHOP_YN IN ('Y','E')) Default: False.
        is_tna_delivery (bool | Unset): T바로배송 가능 매장 여부 (SMART_CARE_SHOP_YN = 'Y') Default: False.
        first_available_slot (None | StoreScheduleSlot | Unset): 가장 빠른 예약 가능 슬롯
        slots (list[StoreScheduleSlot] | Unset): mode 범위 내 예약 가능 슬롯 목록
    """

    shop_id: str
    status: str
    shop_nm: None | str | Unset = UNSET
    mode: None | ScheduleMode | Unset = UNSET
    has_today_stock: bool | Unset = False
    has_tna_stock: bool | Unset = False
    has_logistics_stock: bool | Unset = False
    is_installable: bool | Unset = False
    is_tna_delivery: bool | Unset = False
    first_available_slot: None | StoreScheduleSlot | Unset = UNSET
    slots: list[StoreScheduleSlot] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.store_schedule_slot import StoreScheduleSlot

        shop_id = self.shop_id

        status = self.status

        shop_nm: None | str | Unset
        if isinstance(self.shop_nm, Unset):
            shop_nm = UNSET
        else:
            shop_nm = self.shop_nm

        mode: None | str | Unset
        if isinstance(self.mode, Unset):
            mode = UNSET
        elif isinstance(self.mode, ScheduleMode):
            mode = self.mode.value
        else:
            mode = self.mode

        has_today_stock = self.has_today_stock

        has_tna_stock = self.has_tna_stock

        has_logistics_stock = self.has_logistics_stock

        is_installable = self.is_installable

        is_tna_delivery = self.is_tna_delivery

        first_available_slot: dict[str, Any] | None | Unset
        if isinstance(self.first_available_slot, Unset):
            first_available_slot = UNSET
        elif isinstance(self.first_available_slot, StoreScheduleSlot):
            first_available_slot = self.first_available_slot.to_dict()
        else:
            first_available_slot = self.first_available_slot

        slots: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.slots, Unset):
            slots = []
            for slots_item_data in self.slots:
                slots_item = slots_item_data.to_dict()
                slots.append(slots_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "shop_id": shop_id,
                "status": status,
            }
        )
        if shop_nm is not UNSET:
            field_dict["shop_nm"] = shop_nm
        if mode is not UNSET:
            field_dict["mode"] = mode
        if has_today_stock is not UNSET:
            field_dict["has_today_stock"] = has_today_stock
        if has_tna_stock is not UNSET:
            field_dict["has_tna_stock"] = has_tna_stock
        if has_logistics_stock is not UNSET:
            field_dict["has_logistics_stock"] = has_logistics_stock
        if is_installable is not UNSET:
            field_dict["is_installable"] = is_installable
        if is_tna_delivery is not UNSET:
            field_dict["is_tna_delivery"] = is_tna_delivery
        if first_available_slot is not UNSET:
            field_dict["first_available_slot"] = first_available_slot
        if slots is not UNSET:
            field_dict["slots"] = slots

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.store_schedule_slot import StoreScheduleSlot

        d = dict(src_dict)
        shop_id = d.pop("shop_id")

        status = d.pop("status")

        def _parse_shop_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_nm = _parse_shop_nm(d.pop("shop_nm", UNSET))

        def _parse_mode(data: object) -> None | ScheduleMode | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                mode_type_0 = ScheduleMode(data)

                return mode_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ScheduleMode | Unset, data)

        mode = _parse_mode(d.pop("mode", UNSET))

        has_today_stock = d.pop("has_today_stock", UNSET)

        has_tna_stock = d.pop("has_tna_stock", UNSET)

        has_logistics_stock = d.pop("has_logistics_stock", UNSET)

        is_installable = d.pop("is_installable", UNSET)

        is_tna_delivery = d.pop("is_tna_delivery", UNSET)

        def _parse_first_available_slot(data: object) -> None | StoreScheduleSlot | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                first_available_slot_type_0 = StoreScheduleSlot.from_dict(data)

                return first_available_slot_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | StoreScheduleSlot | Unset, data)

        first_available_slot = _parse_first_available_slot(d.pop("first_available_slot", UNSET))

        _slots = d.pop("slots", UNSET)
        slots: list[StoreScheduleSlot] | Unset = UNSET
        if _slots is not UNSET:
            slots = []
            for slots_item_data in _slots:
                slots_item = StoreScheduleSlot.from_dict(slots_item_data)

                slots.append(slots_item)

        store_install_availability_item = cls(
            shop_id=shop_id,
            status=status,
            shop_nm=shop_nm,
            mode=mode,
            has_today_stock=has_today_stock,
            has_tna_stock=has_tna_stock,
            has_logistics_stock=has_logistics_stock,
            is_installable=is_installable,
            is_tna_delivery=is_tna_delivery,
            first_available_slot=first_available_slot,
            slots=slots,
        )

        store_install_availability_item.additional_properties = d
        return store_install_availability_item

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
