from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="RcmdGoodsItem")


@_attrs_define
class RcmdGoodsItem:
    """
    Attributes:
        goods_no (str): 상품 번호
        goods_nm (None | str | Unset): 상품명
        extra_fvr_sale_prc (int | None | Unset): 최대 혜택 판매가
        extra_fvr_sale_per (float | None | Unset): 최대 혜택 할인율 (%)
        tot_scr (int | None | Unset): 추천 점수 (TOT_SCR (FST_DISP_YN = ‘Y’ 이면 TOT_SCR * 10), 티스테이션 추천 전용)
        t_comfort (float | None | Unset): 승차감 (T_COMFORT)
        t_silence (float | None | Unset): 정숙성 (T_SILENCE)
        t_life_span (float | None | Unset): 수명 (T_LIFE_SPAN)
        t_fuel_eff_convert (float | None | Unset): 연비 (T_FUEL_EFF_CONVERT)
    """

    goods_no: str
    goods_nm: None | str | Unset = UNSET
    extra_fvr_sale_prc: int | None | Unset = UNSET
    extra_fvr_sale_per: float | None | Unset = UNSET
    tot_scr: int | None | Unset = UNSET
    t_comfort: float | None | Unset = UNSET
    t_silence: float | None | Unset = UNSET
    t_life_span: float | None | Unset = UNSET
    t_fuel_eff_convert: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_no = self.goods_no

        goods_nm: None | str | Unset
        if isinstance(self.goods_nm, Unset):
            goods_nm = UNSET
        else:
            goods_nm = self.goods_nm

        extra_fvr_sale_prc: int | None | Unset
        if isinstance(self.extra_fvr_sale_prc, Unset):
            extra_fvr_sale_prc = UNSET
        else:
            extra_fvr_sale_prc = self.extra_fvr_sale_prc

        extra_fvr_sale_per: float | None | Unset
        if isinstance(self.extra_fvr_sale_per, Unset):
            extra_fvr_sale_per = UNSET
        else:
            extra_fvr_sale_per = self.extra_fvr_sale_per

        tot_scr: int | None | Unset
        if isinstance(self.tot_scr, Unset):
            tot_scr = UNSET
        else:
            tot_scr = self.tot_scr

        t_comfort: float | None | Unset
        if isinstance(self.t_comfort, Unset):
            t_comfort = UNSET
        else:
            t_comfort = self.t_comfort

        t_silence: float | None | Unset
        if isinstance(self.t_silence, Unset):
            t_silence = UNSET
        else:
            t_silence = self.t_silence

        t_life_span: float | None | Unset
        if isinstance(self.t_life_span, Unset):
            t_life_span = UNSET
        else:
            t_life_span = self.t_life_span

        t_fuel_eff_convert: float | None | Unset
        if isinstance(self.t_fuel_eff_convert, Unset):
            t_fuel_eff_convert = UNSET
        else:
            t_fuel_eff_convert = self.t_fuel_eff_convert

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goods_no": goods_no,
            }
        )
        if goods_nm is not UNSET:
            field_dict["goods_nm"] = goods_nm
        if extra_fvr_sale_prc is not UNSET:
            field_dict["extra_fvr_sale_prc"] = extra_fvr_sale_prc
        if extra_fvr_sale_per is not UNSET:
            field_dict["extra_fvr_sale_per"] = extra_fvr_sale_per
        if tot_scr is not UNSET:
            field_dict["tot_scr"] = tot_scr
        if t_comfort is not UNSET:
            field_dict["t_comfort"] = t_comfort
        if t_silence is not UNSET:
            field_dict["t_silence"] = t_silence
        if t_life_span is not UNSET:
            field_dict["t_life_span"] = t_life_span
        if t_fuel_eff_convert is not UNSET:
            field_dict["t_fuel_eff_convert"] = t_fuel_eff_convert

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        goods_no = d.pop("goods_no")

        def _parse_goods_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        goods_nm = _parse_goods_nm(d.pop("goods_nm", UNSET))

        def _parse_extra_fvr_sale_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        extra_fvr_sale_prc = _parse_extra_fvr_sale_prc(d.pop("extra_fvr_sale_prc", UNSET))

        def _parse_extra_fvr_sale_per(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        extra_fvr_sale_per = _parse_extra_fvr_sale_per(d.pop("extra_fvr_sale_per", UNSET))

        def _parse_tot_scr(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        tot_scr = _parse_tot_scr(d.pop("tot_scr", UNSET))

        def _parse_t_comfort(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_comfort = _parse_t_comfort(d.pop("t_comfort", UNSET))

        def _parse_t_silence(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_silence = _parse_t_silence(d.pop("t_silence", UNSET))

        def _parse_t_life_span(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_life_span = _parse_t_life_span(d.pop("t_life_span", UNSET))

        def _parse_t_fuel_eff_convert(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_fuel_eff_convert = _parse_t_fuel_eff_convert(d.pop("t_fuel_eff_convert", UNSET))

        rcmd_goods_item = cls(
            goods_no=goods_no,
            goods_nm=goods_nm,
            extra_fvr_sale_prc=extra_fvr_sale_prc,
            extra_fvr_sale_per=extra_fvr_sale_per,
            tot_scr=tot_scr,
            t_comfort=t_comfort,
            t_silence=t_silence,
            t_life_span=t_life_span,
            t_fuel_eff_convert=t_fuel_eff_convert,
        )

        rcmd_goods_item.additional_properties = d
        return rcmd_goods_item

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
