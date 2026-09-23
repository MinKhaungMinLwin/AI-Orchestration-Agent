from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CouponStackingPair")


@_attrs_define
class CouponStackingPair:
    """두 쿠폰의 중복 적용 판정 결과 1건.

    Attributes:
        cpn_no_a (str): 쿠폰 A.
        cpn_no_b (str): 쿠폰 B.
        reason (str): 사용자 응답에 사용할 한 줄 사유. 예: '두 쿠폰 모두 중복 사용 가능' / '결제쿠폰의 중복 사용 가능 여부가 N' / '서비스쿠폰은 항상 중복 가능' / '정책상 안내가
            어려운 조합입니다.'
        can_stack (bool | None | Unset): 중복 적용 판정. True=동시 적용 가능 / False=동시 적용 불가 / null=DBA 가이드 명시 없는 조합 (안내 불가, 1:1 문의
            fallback).
    """

    cpn_no_a: str
    cpn_no_b: str
    reason: str
    can_stack: bool | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cpn_no_a = self.cpn_no_a

        cpn_no_b = self.cpn_no_b

        reason = self.reason

        can_stack: bool | None | Unset
        if isinstance(self.can_stack, Unset):
            can_stack = UNSET
        else:
            can_stack = self.can_stack

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "cpn_no_a": cpn_no_a,
                "cpn_no_b": cpn_no_b,
                "reason": reason,
            }
        )
        if can_stack is not UNSET:
            field_dict["can_stack"] = can_stack

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        cpn_no_a = d.pop("cpn_no_a")

        cpn_no_b = d.pop("cpn_no_b")

        reason = d.pop("reason")

        def _parse_can_stack(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        can_stack = _parse_can_stack(d.pop("can_stack", UNSET))

        coupon_stacking_pair = cls(
            cpn_no_a=cpn_no_a,
            cpn_no_b=cpn_no_b,
            reason=reason,
            can_stack=can_stack,
        )

        coupon_stacking_pair.additional_properties = d
        return coupon_stacking_pair

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
