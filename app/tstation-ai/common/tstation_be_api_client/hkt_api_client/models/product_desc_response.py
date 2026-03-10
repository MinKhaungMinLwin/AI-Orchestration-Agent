from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.product_image import ProductImage


T = TypeVar("T", bound="ProductDescResponse")


@_attrs_define
class ProductDescResponse:
    """
    Attributes:
        goods_no (str): 상품 번호
        ptrn_cd (None | str | Unset): 패턴 번호
        pc_prod_remark_desc (None | str | Unset): 특장점 (PC_PROD_REMARK_DESC)
        pc_prod_tech_desc (None | str | Unset): 기술력 (PC_PROD_TECH_DESC)
        slogan (None | str | Unset): 슬로건 (SLOGAN)
        images (list[ProductImage] | Unset): 상품 이미지 목록
    """

    goods_no: str
    ptrn_cd: None | str | Unset = UNSET
    pc_prod_remark_desc: None | str | Unset = UNSET
    pc_prod_tech_desc: None | str | Unset = UNSET
    slogan: None | str | Unset = UNSET
    images: list[ProductImage] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_no = self.goods_no

        ptrn_cd: None | str | Unset
        if isinstance(self.ptrn_cd, Unset):
            ptrn_cd = UNSET
        else:
            ptrn_cd = self.ptrn_cd

        pc_prod_remark_desc: None | str | Unset
        if isinstance(self.pc_prod_remark_desc, Unset):
            pc_prod_remark_desc = UNSET
        else:
            pc_prod_remark_desc = self.pc_prod_remark_desc

        pc_prod_tech_desc: None | str | Unset
        if isinstance(self.pc_prod_tech_desc, Unset):
            pc_prod_tech_desc = UNSET
        else:
            pc_prod_tech_desc = self.pc_prod_tech_desc

        slogan: None | str | Unset
        if isinstance(self.slogan, Unset):
            slogan = UNSET
        else:
            slogan = self.slogan

        images: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.images, Unset):
            images = []
            for images_item_data in self.images:
                images_item = images_item_data.to_dict()
                images.append(images_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goods_no": goods_no,
            }
        )
        if ptrn_cd is not UNSET:
            field_dict["ptrn_cd"] = ptrn_cd
        if pc_prod_remark_desc is not UNSET:
            field_dict["pc_prod_remark_desc"] = pc_prod_remark_desc
        if pc_prod_tech_desc is not UNSET:
            field_dict["pc_prod_tech_desc"] = pc_prod_tech_desc
        if slogan is not UNSET:
            field_dict["slogan"] = slogan
        if images is not UNSET:
            field_dict["images"] = images

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.product_image import ProductImage

        d = dict(src_dict)
        goods_no = d.pop("goods_no")

        def _parse_ptrn_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ptrn_cd = _parse_ptrn_cd(d.pop("ptrn_cd", UNSET))

        def _parse_pc_prod_remark_desc(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pc_prod_remark_desc = _parse_pc_prod_remark_desc(d.pop("pc_prod_remark_desc", UNSET))

        def _parse_pc_prod_tech_desc(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pc_prod_tech_desc = _parse_pc_prod_tech_desc(d.pop("pc_prod_tech_desc", UNSET))

        def _parse_slogan(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        slogan = _parse_slogan(d.pop("slogan", UNSET))

        _images = d.pop("images", UNSET)
        images: list[ProductImage] | Unset = UNSET
        if _images is not UNSET:
            images = []
            for images_item_data in _images:
                images_item = ProductImage.from_dict(images_item_data)

                images.append(images_item)

        product_desc_response = cls(
            goods_no=goods_no,
            ptrn_cd=ptrn_cd,
            pc_prod_remark_desc=pc_prod_remark_desc,
            pc_prod_tech_desc=pc_prod_tech_desc,
            slogan=slogan,
            images=images,
        )

        product_desc_response.additional_properties = d
        return product_desc_response

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
