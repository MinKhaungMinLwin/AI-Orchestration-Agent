from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.schedule_mode import ScheduleMode
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.store_schedule_slot import StoreScheduleSlot


T = TypeVar("T", bound="StoreScheduleResponse")


@_attrs_define
class StoreScheduleResponse:
    """
    Attributes:
        shop_id (str): 매장 ID
        mode (ScheduleMode): 매장 스케줄 조회 모드.

            재고 상태 조합에 따라 backend 가 적용할 cal_day range 가 달라진다.

            | mode                          | 매핑                              | range                      |
            |-------------------------------|-----------------------------------|----------------------------|
            | today_only                    | Flow 3.5 1순위 (todayShopArray O) | 오늘서비스 only            |
            | tna_only                      | Flow 3.5 2순위 (tnaShopArray O)   | T바로배송 only             |
            | logistics_only                | 매장재고 X + 물류재고 O           | 일반배송 only              |
            | in_store_only                 | 매장재고 O + 물류재고 X           | 오늘 ∪ T바로              |
            | in_store_logistics_combined   | 매장재고 O + 물류재고 O           | 오늘 ∪ T바로 ∪ 일반배송  |
            | general                       | 타이어 미특정 단순 매장 방문       | SYSDATE ~ SYSDATE+30       |
        shop_nm (None | str | Unset): 매장명
        is_installable (bool | Unset): 쇼핑 장착 가능 매장 여부 (SMART_CARE_SHOP_YN IN ('Y','E')) Default: False.
        is_tna_delivery (bool | Unset): T바로배송 가능 매장 여부 (SMART_CARE_SHOP_YN = 'Y') Default: False.
        slots (list[StoreScheduleSlot] | Unset): 예약 가능 시간 슬롯 (cal_day, tm 오름차순). 빈 리스트면 해당 모드 range 내 가용 슬롯 없음.
    """

    shop_id: str
    mode: ScheduleMode
    shop_nm: None | str | Unset = UNSET
    is_installable: bool | Unset = False
    is_tna_delivery: bool | Unset = False
    slots: list[StoreScheduleSlot] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        shop_id = self.shop_id

        mode = self.mode.value

        shop_nm: None | str | Unset
        if isinstance(self.shop_nm, Unset):
            shop_nm = UNSET
        else:
            shop_nm = self.shop_nm

        is_installable = self.is_installable

        is_tna_delivery = self.is_tna_delivery

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
                "mode": mode,
            }
        )
        if shop_nm is not UNSET:
            field_dict["shop_nm"] = shop_nm
        if is_installable is not UNSET:
            field_dict["is_installable"] = is_installable
        if is_tna_delivery is not UNSET:
            field_dict["is_tna_delivery"] = is_tna_delivery
        if slots is not UNSET:
            field_dict["slots"] = slots

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.store_schedule_slot import StoreScheduleSlot

        d = dict(src_dict)
        shop_id = d.pop("shop_id")

        mode = ScheduleMode(d.pop("mode"))

        def _parse_shop_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_nm = _parse_shop_nm(d.pop("shop_nm", UNSET))

        is_installable = d.pop("is_installable", UNSET)

        is_tna_delivery = d.pop("is_tna_delivery", UNSET)

        _slots = d.pop("slots", UNSET)
        slots: list[StoreScheduleSlot] | Unset = UNSET
        if _slots is not UNSET:
            slots = []
            for slots_item_data in _slots:
                slots_item = StoreScheduleSlot.from_dict(slots_item_data)

                slots.append(slots_item)

        store_schedule_response = cls(
            shop_id=shop_id,
            mode=mode,
            shop_nm=shop_nm,
            is_installable=is_installable,
            is_tna_delivery=is_tna_delivery,
            slots=slots,
        )

        store_schedule_response.additional_properties = d
        return store_schedule_response

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
