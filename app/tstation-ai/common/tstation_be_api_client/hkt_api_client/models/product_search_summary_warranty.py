from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.product_search_summary_warranty_item import ProductSearchSummaryWarrantyItem


T = TypeVar("T", bound="ProductSearchSummaryWarranty")


@_attrs_define
class ProductSearchSummaryWarranty:
    """
    Attributes:
        free_guarantee_yn (None | str | Unset): 무상교환보증 여부 Y/N (FREE_GUARANTEE_YN)
        t_rlx_isn_yn (None | str | Unset): 안심보험 여부 Y/N (T_RLX_ISN_YN)
        warranties (list[ProductSearchSummaryWarrantyItem] | Unset): ET_DGTL_WRT_APLY_INFO 기준 WRT_TGT_YN='Y' 인 적용 가능 워런티
            목록
    """

    free_guarantee_yn: None | str | Unset = UNSET
    t_rlx_isn_yn: None | str | Unset = UNSET
    warranties: list[ProductSearchSummaryWarrantyItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        free_guarantee_yn: None | str | Unset
        if isinstance(self.free_guarantee_yn, Unset):
            free_guarantee_yn = UNSET
        else:
            free_guarantee_yn = self.free_guarantee_yn

        t_rlx_isn_yn: None | str | Unset
        if isinstance(self.t_rlx_isn_yn, Unset):
            t_rlx_isn_yn = UNSET
        else:
            t_rlx_isn_yn = self.t_rlx_isn_yn

        warranties: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.warranties, Unset):
            warranties = []
            for warranties_item_data in self.warranties:
                warranties_item = warranties_item_data.to_dict()
                warranties.append(warranties_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if free_guarantee_yn is not UNSET:
            field_dict["free_guarantee_yn"] = free_guarantee_yn
        if t_rlx_isn_yn is not UNSET:
            field_dict["t_rlx_isn_yn"] = t_rlx_isn_yn
        if warranties is not UNSET:
            field_dict["warranties"] = warranties

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.product_search_summary_warranty_item import ProductSearchSummaryWarrantyItem

        d = dict(src_dict)

        def _parse_free_guarantee_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        free_guarantee_yn = _parse_free_guarantee_yn(d.pop("free_guarantee_yn", UNSET))

        def _parse_t_rlx_isn_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_rlx_isn_yn = _parse_t_rlx_isn_yn(d.pop("t_rlx_isn_yn", UNSET))

        _warranties = d.pop("warranties", UNSET)
        warranties: list[ProductSearchSummaryWarrantyItem] | Unset = UNSET
        if _warranties is not UNSET:
            warranties = []
            for warranties_item_data in _warranties:
                warranties_item = ProductSearchSummaryWarrantyItem.from_dict(warranties_item_data)

                warranties.append(warranties_item)

        product_search_summary_warranty = cls(
            free_guarantee_yn=free_guarantee_yn,
            t_rlx_isn_yn=t_rlx_isn_yn,
            warranties=warranties,
        )

        product_search_summary_warranty.additional_properties = d
        return product_search_summary_warranty

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
