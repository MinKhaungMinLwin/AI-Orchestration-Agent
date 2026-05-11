from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="EventApplicableProductItem")


@_attrs_define
class EventApplicableProductItem:
    """
    Attributes:
        aply_tp_cd (str): 적용 유형 코드 (50=상품, 80=패턴)
        goods_no (str): 상품 번호
        goods_nm (None | str | Unset): 상품명
        ptrn_cd (None | str | Unset): 패턴 코드
        tire_size_1 (None | str | Unset): 타이어 사이즈 (TIRE_SIZE_1, 예: '245/45R18')
        tire_size_2 (None | str | Unset): 타이어 사이즈 후륜 (TIRE_SIZE_2, 전후륜 다른 차량용)
    """

    aply_tp_cd: str
    goods_no: str
    goods_nm: None | str | Unset = UNSET
    ptrn_cd: None | str | Unset = UNSET
    tire_size_1: None | str | Unset = UNSET
    tire_size_2: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        aply_tp_cd = self.aply_tp_cd

        goods_no = self.goods_no

        goods_nm: None | str | Unset
        if isinstance(self.goods_nm, Unset):
            goods_nm = UNSET
        else:
            goods_nm = self.goods_nm

        ptrn_cd: None | str | Unset
        if isinstance(self.ptrn_cd, Unset):
            ptrn_cd = UNSET
        else:
            ptrn_cd = self.ptrn_cd

        tire_size_1: None | str | Unset
        if isinstance(self.tire_size_1, Unset):
            tire_size_1 = UNSET
        else:
            tire_size_1 = self.tire_size_1

        tire_size_2: None | str | Unset
        if isinstance(self.tire_size_2, Unset):
            tire_size_2 = UNSET
        else:
            tire_size_2 = self.tire_size_2

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "aply_tp_cd": aply_tp_cd,
                "goods_no": goods_no,
            }
        )
        if goods_nm is not UNSET:
            field_dict["goods_nm"] = goods_nm
        if ptrn_cd is not UNSET:
            field_dict["ptrn_cd"] = ptrn_cd
        if tire_size_1 is not UNSET:
            field_dict["tire_size_1"] = tire_size_1
        if tire_size_2 is not UNSET:
            field_dict["tire_size_2"] = tire_size_2

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        aply_tp_cd = d.pop("aply_tp_cd")

        goods_no = d.pop("goods_no")

        def _parse_goods_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        goods_nm = _parse_goods_nm(d.pop("goods_nm", UNSET))

        def _parse_ptrn_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ptrn_cd = _parse_ptrn_cd(d.pop("ptrn_cd", UNSET))

        def _parse_tire_size_1(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tire_size_1 = _parse_tire_size_1(d.pop("tire_size_1", UNSET))

        def _parse_tire_size_2(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tire_size_2 = _parse_tire_size_2(d.pop("tire_size_2", UNSET))

        event_applicable_product_item = cls(
            aply_tp_cd=aply_tp_cd,
            goods_no=goods_no,
            goods_nm=goods_nm,
            ptrn_cd=ptrn_cd,
            tire_size_1=tire_size_1,
            tire_size_2=tire_size_2,
        )

        event_applicable_product_item.additional_properties = d
        return event_applicable_product_item

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
