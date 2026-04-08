from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="NearbyStoreRequest")


@_attrs_define
class NearbyStoreRequest:
    """
    Attributes:
        user_xpos (float): 고객 현재 X 좌표
        user_ypos (float): 고객 현재 Y 좌표
        radius_km (float | Unset): 검색 반경 (km), 기본값 20km Default: 20.0.
        svc_codes (list[str] | None | Unset): 서비스 구분 코드 목록 (ET_SHOP_ITEM_SVC_INFO.SHOP_ITEM_SVC_SCT_CD). 입력된 코드 중 하나라도
            보유한 매장을 반환합니다. 예: ["101", "102"] → 타이어(오프라인) 또는 경정비 서비스 보유 매장
        all_my_t_only (bool | Unset): True 이면 all my T 매장만 조회 (SMART_CARE_SHOP_YN = 'Y') Default: False.
    """

    user_xpos: float
    user_ypos: float
    radius_km: float | Unset = 20.0
    svc_codes: list[str] | None | Unset = UNSET
    all_my_t_only: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        user_xpos = self.user_xpos

        user_ypos = self.user_ypos

        radius_km = self.radius_km

        svc_codes: list[str] | None | Unset
        if isinstance(self.svc_codes, Unset):
            svc_codes = UNSET
        elif isinstance(self.svc_codes, list):
            svc_codes = self.svc_codes

        else:
            svc_codes = self.svc_codes

        all_my_t_only = self.all_my_t_only

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "user_xpos": user_xpos,
                "user_ypos": user_ypos,
            }
        )
        if radius_km is not UNSET:
            field_dict["radius_km"] = radius_km
        if svc_codes is not UNSET:
            field_dict["svc_codes"] = svc_codes
        if all_my_t_only is not UNSET:
            field_dict["all_my_t_only"] = all_my_t_only

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        user_xpos = d.pop("user_xpos")

        user_ypos = d.pop("user_ypos")

        radius_km = d.pop("radius_km", UNSET)

        def _parse_svc_codes(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                svc_codes_type_0 = cast(list[str], data)

                return svc_codes_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        svc_codes = _parse_svc_codes(d.pop("svc_codes", UNSET))

        all_my_t_only = d.pop("all_my_t_only", UNSET)

        nearby_store_request = cls(
            user_xpos=user_xpos,
            user_ypos=user_ypos,
            radius_km=radius_km,
            svc_codes=svc_codes,
            all_my_t_only=all_my_t_only,
        )

        nearby_store_request.additional_properties = d
        return nearby_store_request

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
