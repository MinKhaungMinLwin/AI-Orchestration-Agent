from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.vehicle_resolution_resolution_status import VehicleResolutionResolutionStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="VehicleResolution")


@_attrs_define
class VehicleResolution:
    """
    Attributes:
        resolution_status (VehicleResolutionResolutionStatus): 차량 해석 상태
        maker (None | str | Unset): 해석된 제조사 코드/명
        model (None | str | Unset): 해석된 대표 모델명
        option_keyword (None | str | Unset): 해석된 옵션/엔진 키워드
        candidate_count (int | Unset): 차량 후보 수 Default: 0.
    """

    resolution_status: VehicleResolutionResolutionStatus
    maker: None | str | Unset = UNSET
    model: None | str | Unset = UNSET
    option_keyword: None | str | Unset = UNSET
    candidate_count: int | Unset = 0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        resolution_status = self.resolution_status.value

        maker: None | str | Unset
        if isinstance(self.maker, Unset):
            maker = UNSET
        else:
            maker = self.maker

        model: None | str | Unset
        if isinstance(self.model, Unset):
            model = UNSET
        else:
            model = self.model

        option_keyword: None | str | Unset
        if isinstance(self.option_keyword, Unset):
            option_keyword = UNSET
        else:
            option_keyword = self.option_keyword

        candidate_count = self.candidate_count

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "resolution_status": resolution_status,
            }
        )
        if maker is not UNSET:
            field_dict["maker"] = maker
        if model is not UNSET:
            field_dict["model"] = model
        if option_keyword is not UNSET:
            field_dict["option_keyword"] = option_keyword
        if candidate_count is not UNSET:
            field_dict["candidate_count"] = candidate_count

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        resolution_status = VehicleResolutionResolutionStatus(d.pop("resolution_status"))

        def _parse_maker(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        maker = _parse_maker(d.pop("maker", UNSET))

        def _parse_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        model = _parse_model(d.pop("model", UNSET))

        def _parse_option_keyword(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        option_keyword = _parse_option_keyword(d.pop("option_keyword", UNSET))

        candidate_count = d.pop("candidate_count", UNSET)

        vehicle_resolution = cls(
            resolution_status=resolution_status,
            maker=maker,
            model=model,
            option_keyword=option_keyword,
            candidate_count=candidate_count,
        )

        vehicle_resolution.additional_properties = d
        return vehicle_resolution

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
