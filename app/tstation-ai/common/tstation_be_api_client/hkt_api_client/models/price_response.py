from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.applied_coupon_item import AppliedCouponItem


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
        cheapest_final_prc (int | None | Unset): 회원 보유 쿠폰 3-stage 그리디 적용 후 최저가. 결제 단계의 paymentAmount 기준값. 회원 미보유 /
            PL/SQL 함수 미배포 등으로 계산 실패 시 null — 호출자는 extra_fvr_sale_prc 로 fallback.
        cheapest_total_discount (int | None | Unset): cheapest 시뮬레이션 총 할인 (sale_prc - cheapest_final_prc)
        cheapest_applied_coupons (list[AppliedCouponItem] | None | Unset): cheapest 시뮬레이션 단계별 적용 쿠폰 목록
    """

    sale_prc: int | None | Unset = UNSET
    extra_fvr_sale_prc: int | None | Unset = UNSET
    extra_fvr_sale_per: float | None | Unset = UNSET
    wage_prc: int | None | Unset = UNSET
    wage_today_prc: int | None | Unset = UNSET
    smrt_pay_yn: None | str | Unset = UNSET
    cheapest_final_prc: int | None | Unset = UNSET
    cheapest_total_discount: int | None | Unset = UNSET
    cheapest_applied_coupons: list[AppliedCouponItem] | None | Unset = UNSET
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

        cheapest_final_prc: int | None | Unset
        if isinstance(self.cheapest_final_prc, Unset):
            cheapest_final_prc = UNSET
        else:
            cheapest_final_prc = self.cheapest_final_prc

        cheapest_total_discount: int | None | Unset
        if isinstance(self.cheapest_total_discount, Unset):
            cheapest_total_discount = UNSET
        else:
            cheapest_total_discount = self.cheapest_total_discount

        cheapest_applied_coupons: list[dict[str, Any]] | None | Unset
        if isinstance(self.cheapest_applied_coupons, Unset):
            cheapest_applied_coupons = UNSET
        elif isinstance(self.cheapest_applied_coupons, list):
            cheapest_applied_coupons = []
            for cheapest_applied_coupons_type_0_item_data in self.cheapest_applied_coupons:
                cheapest_applied_coupons_type_0_item = cheapest_applied_coupons_type_0_item_data.to_dict()
                cheapest_applied_coupons.append(cheapest_applied_coupons_type_0_item)

        else:
            cheapest_applied_coupons = self.cheapest_applied_coupons

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
        if cheapest_final_prc is not UNSET:
            field_dict["cheapest_final_prc"] = cheapest_final_prc
        if cheapest_total_discount is not UNSET:
            field_dict["cheapest_total_discount"] = cheapest_total_discount
        if cheapest_applied_coupons is not UNSET:
            field_dict["cheapest_applied_coupons"] = cheapest_applied_coupons

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.applied_coupon_item import AppliedCouponItem

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

        def _parse_cheapest_final_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cheapest_final_prc = _parse_cheapest_final_prc(d.pop("cheapest_final_prc", UNSET))

        def _parse_cheapest_total_discount(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cheapest_total_discount = _parse_cheapest_total_discount(d.pop("cheapest_total_discount", UNSET))

        def _parse_cheapest_applied_coupons(data: object) -> list[AppliedCouponItem] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                cheapest_applied_coupons_type_0 = []
                _cheapest_applied_coupons_type_0 = data
                for cheapest_applied_coupons_type_0_item_data in _cheapest_applied_coupons_type_0:
                    cheapest_applied_coupons_type_0_item = AppliedCouponItem.from_dict(
                        cheapest_applied_coupons_type_0_item_data
                    )

                    cheapest_applied_coupons_type_0.append(cheapest_applied_coupons_type_0_item)

                return cheapest_applied_coupons_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[AppliedCouponItem] | None | Unset, data)

        cheapest_applied_coupons = _parse_cheapest_applied_coupons(d.pop("cheapest_applied_coupons", UNSET))

        price_response = cls(
            sale_prc=sale_prc,
            extra_fvr_sale_prc=extra_fvr_sale_prc,
            extra_fvr_sale_per=extra_fvr_sale_per,
            wage_prc=wage_prc,
            wage_today_prc=wage_today_prc,
            smrt_pay_yn=smrt_pay_yn,
            cheapest_final_prc=cheapest_final_prc,
            cheapest_total_discount=cheapest_total_discount,
            cheapest_applied_coupons=cheapest_applied_coupons,
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
