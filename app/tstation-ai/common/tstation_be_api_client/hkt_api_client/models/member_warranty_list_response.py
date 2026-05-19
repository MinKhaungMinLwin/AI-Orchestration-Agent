from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.member_warranty_item import MemberWarrantyItem


T = TypeVar("T", bound="MemberWarrantyListResponse")


@_attrs_define
class MemberWarrantyListResponse:
    """
    Attributes:
        warranties (list[MemberWarrantyItem] | Unset): 회원 보유 워런티 목록. WRT_REG_DATE 내림차순. WRT_PRGS_STAT_CD IN ('200',
            '300', '400') 만 포함.
    """

    warranties: list[MemberWarrantyItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        warranties: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.warranties, Unset):
            warranties = []
            for warranties_item_data in self.warranties:
                warranties_item = warranties_item_data.to_dict()
                warranties.append(warranties_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if warranties is not UNSET:
            field_dict["warranties"] = warranties

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.member_warranty_item import MemberWarrantyItem

        d = dict(src_dict)
        _warranties = d.pop("warranties", UNSET)
        warranties: list[MemberWarrantyItem] | Unset = UNSET
        if _warranties is not UNSET:
            warranties = []
            for warranties_item_data in _warranties:
                warranties_item = MemberWarrantyItem.from_dict(warranties_item_data)

                warranties.append(warranties_item)

        member_warranty_list_response = cls(
            warranties=warranties,
        )

        member_warranty_list_response.additional_properties = d
        return member_warranty_list_response

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
