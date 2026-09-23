from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PriceResponse")


@_attrs_define
class PriceResponse:
    """
    Attributes:
        sale_prc (int | None | Unset): 기본 판매가
        extra_fvr_sale_prc (int | None | Unset): 최대 혜택 판매가 (쿠폰 등 적용)
        extra_fvr_sale_per (float | None | Unset): 최대 혜택 할인율 (%)
        wage_prc (int | None | Unset): 공임비
        wage_today_prc (int | None | Unset): 오늘의 공임비
        smrt_pay_yn (None | str | Unset): 스마트페이 가능 여부 Y/N (활성 PR_ITEM_PRC_INFO.SMRT_PAY_PRC > 0 기준)
        smrt_pay_prc (int | None | Unset): 스마트페이 월 납부액 계산 기준 금액 (PR_ITEM_PRC_INFO.SMRT_PAY_PRC)
    """

    sale_prc: int | None | Unset = UNSET
    extra_fvr_sale_prc: int | None | Unset = UNSET
    extra_fvr_sale_per: float | None | Unset = UNSET
    wage_prc: int | None | Unset = UNSET
    wage_today_prc: int | None | Unset = UNSET
    smrt_pay_yn: None | str | Unset = UNSET
    smrt_pay_prc: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        sale_prc: int | None | Unset
        if isinstance(self.sale_prc, Unset):
            sale_prc = UNSET
        else:
            sale_prc = self.sale_prc

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

        wage_prc: int | None | Unset
        if isinstance(self.wage_prc, Unset):
            wage_prc = UNSET
        else:
            wage_prc = self.wage_prc

        wage_today_prc: int | None | Unset
        if isinstance(self.wage_today_prc, Unset):
            wage_today_prc = UNSET
        else:
            wage_today_prc = self.wage_today_prc

        smrt_pay_yn: None | str | Unset
        if isinstance(self.smrt_pay_yn, Unset):
            smrt_pay_yn = UNSET
        else:
            smrt_pay_yn = self.smrt_pay_yn

        smrt_pay_prc: int | None | Unset
        if isinstance(self.smrt_pay_prc, Unset):
            smrt_pay_prc = UNSET
        else:
            smrt_pay_prc = self.smrt_pay_prc

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if sale_prc is not UNSET:
            field_dict["sale_prc"] = sale_prc
        if extra_fvr_sale_prc is not UNSET:
            field_dict["extra_fvr_sale_prc"] = extra_fvr_sale_prc
        if extra_fvr_sale_per is not UNSET:
            field_dict["extra_fvr_sale_per"] = extra_fvr_sale_per
        if wage_prc is not UNSET:
            field_dict["wage_prc"] = wage_prc
        if wage_today_prc is not UNSET:
            field_dict["wage_today_prc"] = wage_today_prc
        if smrt_pay_yn is not UNSET:
            field_dict["smrt_pay_yn"] = smrt_pay_yn
        if smrt_pay_prc is not UNSET:
            field_dict["smrt_pay_prc"] = smrt_pay_prc

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_sale_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        sale_prc = _parse_sale_prc(d.pop("sale_prc", UNSET))

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

        def _parse_wage_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        wage_prc = _parse_wage_prc(d.pop("wage_prc", UNSET))

        def _parse_wage_today_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        wage_today_prc = _parse_wage_today_prc(d.pop("wage_today_prc", UNSET))

        def _parse_smrt_pay_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        smrt_pay_yn = _parse_smrt_pay_yn(d.pop("smrt_pay_yn", UNSET))

        def _parse_smrt_pay_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        smrt_pay_prc = _parse_smrt_pay_prc(d.pop("smrt_pay_prc", UNSET))

        price_response = cls(
            sale_prc=sale_prc,
            extra_fvr_sale_prc=extra_fvr_sale_prc,
            extra_fvr_sale_per=extra_fvr_sale_per,
            wage_prc=wage_prc,
            wage_today_prc=wage_today_prc,
            smrt_pay_yn=smrt_pay_yn,
            smrt_pay_prc=smrt_pay_prc,
        )

        price_response.additional_properties = d
        return price_response

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
