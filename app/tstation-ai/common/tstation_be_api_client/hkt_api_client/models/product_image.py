from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ProductImage")


@_attrs_define
class ProductImage:
    """
    Attributes:
        img_path_nm (None | str | Unset): 이미지 경로 (IMG_PATH_NM)
        thnl_path_nm (None | str | Unset): 썸네일 경로 (THNL_PATH_NM)
    """

    img_path_nm: None | str | Unset = UNSET
    thnl_path_nm: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        img_path_nm: None | str | Unset
        if isinstance(self.img_path_nm, Unset):
            img_path_nm = UNSET
        else:
            img_path_nm = self.img_path_nm

        thnl_path_nm: None | str | Unset
        if isinstance(self.thnl_path_nm, Unset):
            thnl_path_nm = UNSET
        else:
            thnl_path_nm = self.thnl_path_nm

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if img_path_nm is not UNSET:
            field_dict["img_path_nm"] = img_path_nm
        if thnl_path_nm is not UNSET:
            field_dict["thnl_path_nm"] = thnl_path_nm

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_img_path_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        img_path_nm = _parse_img_path_nm(d.pop("img_path_nm", UNSET))

        def _parse_thnl_path_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        thnl_path_nm = _parse_thnl_path_nm(d.pop("thnl_path_nm", UNSET))

        product_image = cls(
            img_path_nm=img_path_nm,
            thnl_path_nm=thnl_path_nm,
        )

        product_image.additional_properties = d
        return product_image

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
