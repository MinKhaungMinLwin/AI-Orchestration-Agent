from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.member_relief_service_item import MemberReliefServiceItem


T = TypeVar("T", bound="MemberReliefServiceListResponse")


@_attrs_define
class MemberReliefServiceListResponse:
    """
    Attributes:
        relief_services (list[MemberReliefServiceItem] | Unset): 회원 안심서비스 가입/보상 이력. JOIN_DTIME 내림차순.
    """

    relief_services: list[MemberReliefServiceItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        relief_services: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.relief_services, Unset):
            relief_services = []
            for relief_services_item_data in self.relief_services:
                relief_services_item = relief_services_item_data.to_dict()
                relief_services.append(relief_services_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if relief_services is not UNSET:
            field_dict["relief_services"] = relief_services

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.member_relief_service_item import MemberReliefServiceItem

        d = dict(src_dict)
        _relief_services = d.pop("relief_services", UNSET)
        relief_services: list[MemberReliefServiceItem] | Unset = UNSET
        if _relief_services is not UNSET:
            relief_services = []
            for relief_services_item_data in _relief_services:
                relief_services_item = MemberReliefServiceItem.from_dict(relief_services_item_data)

                relief_services.append(relief_services_item)

        member_relief_service_list_response = cls(
            relief_services=relief_services,
        )

        member_relief_service_list_response.additional_properties = d
        return member_relief_service_list_response

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
