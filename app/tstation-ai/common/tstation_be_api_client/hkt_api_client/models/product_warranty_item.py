from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ProductWarrantyItem")


@_attrs_define
class ProductWarrantyItem:
    """상품에 적용 가능한 워런티 1건.

    WRT_TP_CD='20' (안심) + PLPR_YN='Y' 인 패턴은 응답에서 '안심서비스' / '안심플러스'
    2건으로 분리되어 노출된다 (사용자가 두 옵션 모두 적용 가능함을 명확히 인지하도록).

        Attributes:
            wrt_tp_cd (str): 워런티 타입 코드 (ET_DGTL_WRT_APLY_INFO.WRT_TP_CD). '10'=품질보증 / '20'=안심서비스(PLPR_YN='Y' 이면 안심플러스 행도 추가)
                / '30'=30일 해피보증 / '40'=코드절상 무상교환
            wrt_nm (str): 워런티 한글명 (사용자 노출용). '품질보증' / '안심서비스' / '안심플러스' / '30일 해피보증' / '코드절상 무상교환'
            is_plus (bool | Unset): 안심플러스 분리 행 여부 (WRT_TP_CD='20' + PLPR_YN='Y' 일 때만 추가되는 행이 True) Default: False.
    """

    wrt_tp_cd: str
    wrt_nm: str
    is_plus: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        wrt_tp_cd = self.wrt_tp_cd

        wrt_nm = self.wrt_nm

        is_plus = self.is_plus

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "wrt_tp_cd": wrt_tp_cd,
                "wrt_nm": wrt_nm,
            }
        )
        if is_plus is not UNSET:
            field_dict["is_plus"] = is_plus

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        wrt_tp_cd = d.pop("wrt_tp_cd")

        wrt_nm = d.pop("wrt_nm")

        is_plus = d.pop("is_plus", UNSET)

        product_warranty_item = cls(
            wrt_tp_cd=wrt_tp_cd,
            wrt_nm=wrt_nm,
            is_plus=is_plus,
        )

        product_warranty_item.additional_properties = d
        return product_warranty_item

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
