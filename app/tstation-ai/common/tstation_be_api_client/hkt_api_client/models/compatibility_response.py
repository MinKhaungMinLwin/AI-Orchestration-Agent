from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.tire_spec import TireSpec


T = TypeVar("T", bound="CompatibilityResponse")


@_attrs_define
class CompatibilityResponse:
    """
    Attributes:
        car_no (str): 차량 번호
        goods_no (str): 상품 번호
        is_compatible_fr (bool): 전륜 호환 여부
        is_compatible_re (bool): 후륜 호환 여부
        is_compatible (bool): 전체 호환 여부 (전/후 모두 호환 시 true)
        tire_size_fr (None | str | Unset): 차량 전륜 타이어 사이즈 (예: 205/55R16)
        tire_size_re (None | str | Unset): 차량 후륜 타이어 사이즈 (예: 225/45R17)
        goods_spec (TireSpec | Unset):
    """

    car_no: str
    goods_no: str
    is_compatible_fr: bool
    is_compatible_re: bool
    is_compatible: bool
    tire_size_fr: None | str | Unset = UNSET
    tire_size_re: None | str | Unset = UNSET
    goods_spec: TireSpec | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        car_no = self.car_no

        goods_no = self.goods_no

        is_compatible_fr = self.is_compatible_fr

        is_compatible_re = self.is_compatible_re

        is_compatible = self.is_compatible

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

        goods_spec: dict[str, Any] | Unset = UNSET
        if not isinstance(self.goods_spec, Unset):
            goods_spec = self.goods_spec.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "car_no": car_no,
                "goods_no": goods_no,
                "is_compatible_fr": is_compatible_fr,
                "is_compatible_re": is_compatible_re,
                "is_compatible": is_compatible,
            }
        )
        if tire_size_fr is not UNSET:
            field_dict["tire_size_fr"] = tire_size_fr
        if tire_size_re is not UNSET:
            field_dict["tire_size_re"] = tire_size_re
        if goods_spec is not UNSET:
            field_dict["goods_spec"] = goods_spec

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.tire_spec import TireSpec

        d = dict(src_dict)
        car_no = d.pop("car_no")

        goods_no = d.pop("goods_no")

        is_compatible_fr = d.pop("is_compatible_fr")

        is_compatible_re = d.pop("is_compatible_re")

        is_compatible = d.pop("is_compatible")

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

        _goods_spec = d.pop("goods_spec", UNSET)
        goods_spec: TireSpec | Unset
        if isinstance(_goods_spec, Unset):
            goods_spec = UNSET
        else:
            goods_spec = TireSpec.from_dict(_goods_spec)

        compatibility_response = cls(
            car_no=car_no,
            goods_no=goods_no,
            is_compatible_fr=is_compatible_fr,
            is_compatible_re=is_compatible_re,
            is_compatible=is_compatible,
            tire_size_fr=tire_size_fr,
            tire_size_re=tire_size_re,
            goods_spec=goods_spec,
        )

        compatibility_response.additional_properties = d
        return compatibility_response

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
