from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.product_warranty_item import ProductWarrantyItem


T = TypeVar("T", bound="ProductWarrantiesResponse")


@_attrs_define
class ProductWarrantiesResponse:
    """
    Attributes:
        goods_no (str): 조회한 상품 번호
        ptrn_cd (None | str | Unset): 상품 패턴 코드 (PR_GOODS_BASE.PTRN_CD). 상품 없으면 null.
        warranties (list[ProductWarrantyItem] | Unset): WRT_TGT_YN='Y' 인 적용 가능 워런티 목록. WRT_TP_CD 오름차순.
    """

    goods_no: str
    ptrn_cd: None | str | Unset = UNSET
    warranties: list[ProductWarrantyItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_no = self.goods_no

        ptrn_cd: None | str | Unset
        if isinstance(self.ptrn_cd, Unset):
            ptrn_cd = UNSET
        else:
            ptrn_cd = self.ptrn_cd

        warranties: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.warranties, Unset):
            warranties = []
            for warranties_item_data in self.warranties:
                warranties_item = warranties_item_data.to_dict()
                warranties.append(warranties_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goods_no": goods_no,
            }
        )
        if ptrn_cd is not UNSET:
            field_dict["ptrn_cd"] = ptrn_cd
        if warranties is not UNSET:
            field_dict["warranties"] = warranties

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.product_warranty_item import ProductWarrantyItem

        d = dict(src_dict)
        goods_no = d.pop("goods_no")

        def _parse_ptrn_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ptrn_cd = _parse_ptrn_cd(d.pop("ptrn_cd", UNSET))

        _warranties = d.pop("warranties", UNSET)
        warranties: list[ProductWarrantyItem] | Unset = UNSET
        if _warranties is not UNSET:
            warranties = []
            for warranties_item_data in _warranties:
                warranties_item = ProductWarrantyItem.from_dict(warranties_item_data)

                warranties.append(warranties_item)

        product_warranties_response = cls(
            goods_no=goods_no,
            ptrn_cd=ptrn_cd,
            warranties=warranties,
        )

        product_warranties_response.additional_properties = d
        return product_warranties_response

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
