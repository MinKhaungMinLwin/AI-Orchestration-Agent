from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.coupon_result_item import CouponResultItem


T = TypeVar("T", bound="CouponIssueResponse")


@_attrs_define
class CouponIssueResponse:
    """쿠폰 발급 응답.

    - goods 모드: ``max_cpn`` (상품쿠폰) + ``extra_cpn`` (결제쿠폰)
    - cpn 모드: ``single_cpn``

        Attributes:
            code (str): API 전체 실행결과 코드 (100/400/700/800/900)
            message (None | str | Unset): 실패 시 메시지
            max_cpn (CouponResultItem | None | Unset): goods 모드: 상품쿠폰 결과
            extra_cpn (CouponResultItem | None | Unset): goods 모드: 결제쿠폰 결과
            single_cpn (CouponResultItem | None | Unset): cpn 모드: 단일 쿠폰 결과
    """

    code: str
    message: None | str | Unset = UNSET
    max_cpn: CouponResultItem | None | Unset = UNSET
    extra_cpn: CouponResultItem | None | Unset = UNSET
    single_cpn: CouponResultItem | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.coupon_result_item import CouponResultItem

        code = self.code

        message: None | str | Unset
        if isinstance(self.message, Unset):
            message = UNSET
        else:
            message = self.message

        max_cpn: dict[str, Any] | None | Unset
        if isinstance(self.max_cpn, Unset):
            max_cpn = UNSET
        elif isinstance(self.max_cpn, CouponResultItem):
            max_cpn = self.max_cpn.to_dict()
        else:
            max_cpn = self.max_cpn

        extra_cpn: dict[str, Any] | None | Unset
        if isinstance(self.extra_cpn, Unset):
            extra_cpn = UNSET
        elif isinstance(self.extra_cpn, CouponResultItem):
            extra_cpn = self.extra_cpn.to_dict()
        else:
            extra_cpn = self.extra_cpn

        single_cpn: dict[str, Any] | None | Unset
        if isinstance(self.single_cpn, Unset):
            single_cpn = UNSET
        elif isinstance(self.single_cpn, CouponResultItem):
            single_cpn = self.single_cpn.to_dict()
        else:
            single_cpn = self.single_cpn

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
            }
        )
        if message is not UNSET:
            field_dict["message"] = message
        if max_cpn is not UNSET:
            field_dict["max_cpn"] = max_cpn
        if extra_cpn is not UNSET:
            field_dict["extra_cpn"] = extra_cpn
        if single_cpn is not UNSET:
            field_dict["single_cpn"] = single_cpn

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.coupon_result_item import CouponResultItem

        d = dict(src_dict)
        code = d.pop("code")

        def _parse_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message = _parse_message(d.pop("message", UNSET))

        def _parse_max_cpn(data: object) -> CouponResultItem | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                max_cpn_type_0 = CouponResultItem.from_dict(data)

                return max_cpn_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CouponResultItem | None | Unset, data)

        max_cpn = _parse_max_cpn(d.pop("max_cpn", UNSET))

        def _parse_extra_cpn(data: object) -> CouponResultItem | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                extra_cpn_type_0 = CouponResultItem.from_dict(data)

                return extra_cpn_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CouponResultItem | None | Unset, data)

        extra_cpn = _parse_extra_cpn(d.pop("extra_cpn", UNSET))

        def _parse_single_cpn(data: object) -> CouponResultItem | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                single_cpn_type_0 = CouponResultItem.from_dict(data)

                return single_cpn_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CouponResultItem | None | Unset, data)

        single_cpn = _parse_single_cpn(d.pop("single_cpn", UNSET))

        coupon_issue_response = cls(
            code=code,
            message=message,
            max_cpn=max_cpn,
            extra_cpn=extra_cpn,
            single_cpn=single_cpn,
        )

        coupon_issue_response.additional_properties = d
        return coupon_issue_response

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
