from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MaintenanceDdayItem")


@_attrs_define
class MaintenanceDdayItem:
    """
    Attributes:
        kind_cd (str): 항목 코드 (001~007)
        kind_nm (str): 사용자 친화 항목명 (NOTI_KND_LABEL 매핑 결과)
        dday (int): 만기까지 잔여 일수. 음수면 만기 경과 (D+).
        status (str): expired (D+, 만기 경과) / upcoming (D-30 이내) / future (그 외)
        source (str): noti_record (ST_NOTI_DDAY_INFO 실데이터) / car_reg_fallback (차량등록일 + NOTI_MSG_TRNS_STD 개월 계산)
        exp_dt (None | str | Unset): 만기일 (YYYY-MM-DD)
    """

    kind_cd: str
    kind_nm: str
    dday: int
    status: str
    source: str
    exp_dt: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        kind_cd = self.kind_cd

        kind_nm = self.kind_nm

        dday = self.dday

        status = self.status

        source = self.source

        exp_dt: None | str | Unset
        if isinstance(self.exp_dt, Unset):
            exp_dt = UNSET
        else:
            exp_dt = self.exp_dt

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind_cd": kind_cd,
                "kind_nm": kind_nm,
                "dday": dday,
                "status": status,
                "source": source,
            }
        )
        if exp_dt is not UNSET:
            field_dict["exp_dt"] = exp_dt

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        kind_cd = d.pop("kind_cd")

        kind_nm = d.pop("kind_nm")

        dday = d.pop("dday")

        status = d.pop("status")

        source = d.pop("source")

        def _parse_exp_dt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        exp_dt = _parse_exp_dt(d.pop("exp_dt", UNSET))

        maintenance_dday_item = cls(
            kind_cd=kind_cd,
            kind_nm=kind_nm,
            dday=dday,
            status=status,
            source=source,
            exp_dt=exp_dt,
        )

        maintenance_dday_item.additional_properties = d
        return maintenance_dday_item

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
