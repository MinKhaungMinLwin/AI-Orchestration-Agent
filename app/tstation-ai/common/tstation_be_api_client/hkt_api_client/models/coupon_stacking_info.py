from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CouponStackingInfo")


@_attrs_define
class CouponStackingInfo:
    """단일 쿠폰의 중복 판정용 정보 1건 (CC_CPN_BASE 조회 결과).

    Attributes:
        cpn_no (str): 쿠폰 번호 (요청 echo).
        cpn_nm (None | str | Unset): 쿠폰명 (CC_CPN_BASE_ML.LANG_CD='ko'). 미발견 또는 명칭 부재 시 null.
        cpn_tp_cd (None | str | Unset): 쿠폰 유형 코드 (CC_CPN_BASE.CPN_TP_CD). '10'=상품쿠폰, '20'=결제쿠폰, '30'=서비스쿠폰, '40'=플러스쿠폰.
            AI 응답에서 사용자에게 노출 금지.
        cpn_tp_nm (None | str | Unset): 쿠폰 유형 한글명 (cpn_tp_cd 매핑 결과). '상품쿠폰' / '결제쿠폰' / '서비스쿠폰' / '플러스쿠폰' / null. 사용자 응답에
            사용 가능.
        cpn_dup_use_yn (None | str | Unset): 중복 사용 가능 여부 (CC_CPN_BASE.CPN_DUP_USE_YN, 'Y' 또는 'N'). DBA 가이드: CPN_TP_CD IN
            ('10','20') 조합에만 영향. AI 응답에서 사용자에게 코드값으로 노출 금지 (의미는 reason 으로 풀어 전달).
        found (bool | Unset): CC_CPN_BASE 에서 조회 성공 여부. False 면 입력 cpn_no 가 마스터에 없음 → 모든 pair 의 can_stack=None (판정 불가).
            Default: True.
    """

    cpn_no: str
    cpn_nm: None | str | Unset = UNSET
    cpn_tp_cd: None | str | Unset = UNSET
    cpn_tp_nm: None | str | Unset = UNSET
    cpn_dup_use_yn: None | str | Unset = UNSET
    found: bool | Unset = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cpn_no = self.cpn_no

        cpn_nm: None | str | Unset
        if isinstance(self.cpn_nm, Unset):
            cpn_nm = UNSET
        else:
            cpn_nm = self.cpn_nm

        cpn_tp_cd: None | str | Unset
        if isinstance(self.cpn_tp_cd, Unset):
            cpn_tp_cd = UNSET
        else:
            cpn_tp_cd = self.cpn_tp_cd

        cpn_tp_nm: None | str | Unset
        if isinstance(self.cpn_tp_nm, Unset):
            cpn_tp_nm = UNSET
        else:
            cpn_tp_nm = self.cpn_tp_nm

        cpn_dup_use_yn: None | str | Unset
        if isinstance(self.cpn_dup_use_yn, Unset):
            cpn_dup_use_yn = UNSET
        else:
            cpn_dup_use_yn = self.cpn_dup_use_yn

        found = self.found

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "cpn_no": cpn_no,
            }
        )
        if cpn_nm is not UNSET:
            field_dict["cpn_nm"] = cpn_nm
        if cpn_tp_cd is not UNSET:
            field_dict["cpn_tp_cd"] = cpn_tp_cd
        if cpn_tp_nm is not UNSET:
            field_dict["cpn_tp_nm"] = cpn_tp_nm
        if cpn_dup_use_yn is not UNSET:
            field_dict["cpn_dup_use_yn"] = cpn_dup_use_yn
        if found is not UNSET:
            field_dict["found"] = found

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        cpn_no = d.pop("cpn_no")

        def _parse_cpn_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cpn_nm = _parse_cpn_nm(d.pop("cpn_nm", UNSET))

        def _parse_cpn_tp_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cpn_tp_cd = _parse_cpn_tp_cd(d.pop("cpn_tp_cd", UNSET))

        def _parse_cpn_tp_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cpn_tp_nm = _parse_cpn_tp_nm(d.pop("cpn_tp_nm", UNSET))

        def _parse_cpn_dup_use_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cpn_dup_use_yn = _parse_cpn_dup_use_yn(d.pop("cpn_dup_use_yn", UNSET))

        found = d.pop("found", UNSET)

        coupon_stacking_info = cls(
            cpn_no=cpn_no,
            cpn_nm=cpn_nm,
            cpn_tp_cd=cpn_tp_cd,
            cpn_tp_nm=cpn_tp_nm,
            cpn_dup_use_yn=cpn_dup_use_yn,
            found=found,
        )

        coupon_stacking_info.additional_properties = d
        return coupon_stacking_info

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
