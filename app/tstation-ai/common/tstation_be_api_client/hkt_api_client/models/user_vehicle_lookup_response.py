from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="UserVehicleLookupResponse")


@_attrs_define
class UserVehicleLookupResponse:
    """
    Attributes:
        car_model (None | str | Unset): 차량 모델
        car_model_det (None | str | Unset): 차량 상세 모델명
        car_nm (None | str | Unset): 차량명
        car_maker (None | str | Unset): 차량 제조사
        car_type (None | str | Unset): 차량 타입 정규화값 (sedan/suv/ev/sports/truck_van)
        tire_size_fr (None | str | Unset): 전륜 타이어 사이즈
        tire_size_re (None | str | Unset): 후륜 타이어 사이즈
        valid_sizes (list[str] | Unset): 유효한 타이어 사이즈 후보 목록 (중복 제거, DB 조회 순서 유지)
    """

    car_model: None | str | Unset = UNSET
    car_model_det: None | str | Unset = UNSET
    car_nm: None | str | Unset = UNSET
    car_maker: None | str | Unset = UNSET
    car_type: None | str | Unset = UNSET
    tire_size_fr: None | str | Unset = UNSET
    tire_size_re: None | str | Unset = UNSET
    valid_sizes: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        car_model: None | str | Unset
        if isinstance(self.car_model, Unset):
            car_model = UNSET
        else:
            car_model = self.car_model

        car_model_det: None | str | Unset
        if isinstance(self.car_model_det, Unset):
            car_model_det = UNSET
        else:
            car_model_det = self.car_model_det

        car_nm: None | str | Unset
        if isinstance(self.car_nm, Unset):
            car_nm = UNSET
        else:
            car_nm = self.car_nm

        car_maker: None | str | Unset
        if isinstance(self.car_maker, Unset):
            car_maker = UNSET
        else:
            car_maker = self.car_maker

        car_type: None | str | Unset
        if isinstance(self.car_type, Unset):
            car_type = UNSET
        else:
            car_type = self.car_type

        tire_size_fr: None | str | Unset
        if isinstance(self.tire_size_fr, Unset):
            tire_size_fr = UNSET
        else:
            tire_size_fr = self.tire_size_fr

        tire_size_re: None | str | Unset
        if isinstance(self.tire_size_re, Unset):
            tire_size_re = UNSET
        else:
            tire_size_re = self.tire_size_re

        valid_sizes: list[str] | Unset = UNSET
        if not isinstance(self.valid_sizes, Unset):
            valid_sizes = self.valid_sizes

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if car_model is not UNSET:
            field_dict["car_model"] = car_model
        if car_model_det is not UNSET:
            field_dict["car_model_det"] = car_model_det
        if car_nm is not UNSET:
            field_dict["car_nm"] = car_nm
        if car_maker is not UNSET:
            field_dict["car_maker"] = car_maker
        if car_type is not UNSET:
            field_dict["car_type"] = car_type
        if tire_size_fr is not UNSET:
            field_dict["tire_size_fr"] = tire_size_fr
        if tire_size_re is not UNSET:
            field_dict["tire_size_re"] = tire_size_re
        if valid_sizes is not UNSET:
            field_dict["valid_sizes"] = valid_sizes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_car_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_model = _parse_car_model(d.pop("car_model", UNSET))

        def _parse_car_model_det(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_model_det = _parse_car_model_det(d.pop("car_model_det", UNSET))

        def _parse_car_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_nm = _parse_car_nm(d.pop("car_nm", UNSET))

        def _parse_car_maker(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_maker = _parse_car_maker(d.pop("car_maker", UNSET))

        def _parse_car_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_type = _parse_car_type(d.pop("car_type", UNSET))

        def _parse_tire_size_fr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tire_size_fr = _parse_tire_size_fr(d.pop("tire_size_fr", UNSET))

        def _parse_tire_size_re(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tire_size_re = _parse_tire_size_re(d.pop("tire_size_re", UNSET))

        valid_sizes = cast(list[str], d.pop("valid_sizes", UNSET))

        user_vehicle_lookup_response = cls(
            car_model=car_model,
            car_model_det=car_model_det,
            car_nm=car_nm,
            car_maker=car_maker,
            car_type=car_type,
            tire_size_fr=tire_size_fr,
            tire_size_re=tire_size_re,
            valid_sizes=valid_sizes,
        )

        user_vehicle_lookup_response.additional_properties = d
        return user_vehicle_lookup_response

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
