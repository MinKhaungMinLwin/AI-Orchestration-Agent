from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="VerifyOwnerResponse")


@_attrs_define
class VerifyOwnerResponse:
    """
    Attributes:
        tire_size_fr (str | Unset): 차량 전륜 타이어 사이즈 (예: 205/55R16)
        tire_size_re (str | Unset): 차량 후륜 타이어 사이즈 (예: 225/45R17)
    """

    tire_size_fr: str | Unset = UNSET
    tire_size_re: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tire_size_fr = self.tire_size_fr

        tire_size_re = self.tire_size_re

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if tire_size_fr is not UNSET:
            field_dict["tire_size_fr"] = tire_size_fr
        if tire_size_re is not UNSET:
            field_dict["tire_size_re"] = tire_size_re

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tire_size_fr = d.pop("tire_size_fr", UNSET)

        tire_size_re = d.pop("tire_size_re", UNSET)

        verify_owner_response = cls(
            tire_size_fr=tire_size_fr,
            tire_size_re=tire_size_re,
        )

        verify_owner_response.additional_properties = d
        return verify_owner_response

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
