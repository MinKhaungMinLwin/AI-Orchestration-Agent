from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ReviewItem")


@_attrs_define
class ReviewItem:
    """
    Attributes:
        goods_no (None | str | Unset): 상품 번호
        gdas_score (float | None | Unset): 상품평 점수 (GDAS_SCR_VAL)
        gdas_cont (None | str | Unset): 상품평 내용 (GDAS_CONT)
        reg_dtime (None | str | Unset): 등록 일시 (SYS_REG_DTIME)
    """

    goods_no: None | str | Unset = UNSET
    gdas_score: float | None | Unset = UNSET
    gdas_cont: None | str | Unset = UNSET
    reg_dtime: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_no: None | str | Unset
        if isinstance(self.goods_no, Unset):
            goods_no = UNSET
        else:
            goods_no = self.goods_no

        gdas_score: float | None | Unset
        if isinstance(self.gdas_score, Unset):
            gdas_score = UNSET
        else:
            gdas_score = self.gdas_score

        gdas_cont: None | str | Unset
        if isinstance(self.gdas_cont, Unset):
            gdas_cont = UNSET
        else:
            gdas_cont = self.gdas_cont

        reg_dtime: None | str | Unset
        if isinstance(self.reg_dtime, Unset):
            reg_dtime = UNSET
        else:
            reg_dtime = self.reg_dtime

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if goods_no is not UNSET:
            field_dict["goods_no"] = goods_no
        if gdas_score is not UNSET:
            field_dict["gdas_score"] = gdas_score
        if gdas_cont is not UNSET:
            field_dict["gdas_cont"] = gdas_cont
        if reg_dtime is not UNSET:
            field_dict["reg_dtime"] = reg_dtime

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_goods_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        goods_no = _parse_goods_no(d.pop("goods_no", UNSET))

        def _parse_gdas_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        gdas_score = _parse_gdas_score(d.pop("gdas_score", UNSET))

        def _parse_gdas_cont(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        gdas_cont = _parse_gdas_cont(d.pop("gdas_cont", UNSET))

        def _parse_reg_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        reg_dtime = _parse_reg_dtime(d.pop("reg_dtime", UNSET))

        review_item = cls(
            goods_no=goods_no,
            gdas_score=gdas_score,
            gdas_cont=gdas_cont,
            reg_dtime=reg_dtime,
        )

        review_item.additional_properties = d
        return review_item

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
