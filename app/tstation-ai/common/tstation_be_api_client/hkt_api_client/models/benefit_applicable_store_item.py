from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="BenefitApplicableStoreItem")


@_attrs_define
class BenefitApplicableStoreItem:
    """
    Attributes:
        shop_id (None | str | Unset): 매장 ID
        shop_nm (None | str | Unset): 매장명
    """

    shop_id: None | str | Unset = UNSET
    shop_nm: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        shop_id: None | str | Unset
        if isinstance(self.shop_id, Unset):
            shop_id = UNSET
        else:
            shop_id = self.shop_id

        shop_nm: None | str | Unset
        if isinstance(self.shop_nm, Unset):
            shop_nm = UNSET
        else:
            shop_nm = self.shop_nm

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if shop_id is not UNSET:
            field_dict["shop_id"] = shop_id
        if shop_nm is not UNSET:
            field_dict["shop_nm"] = shop_nm

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_shop_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_id = _parse_shop_id(d.pop("shop_id", UNSET))

        def _parse_shop_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_nm = _parse_shop_nm(d.pop("shop_nm", UNSET))

        benefit_applicable_store_item = cls(
            shop_id=shop_id,
            shop_nm=shop_nm,
        )

        benefit_applicable_store_item.additional_properties = d
        return benefit_applicable_store_item

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
