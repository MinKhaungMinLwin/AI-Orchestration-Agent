from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CardInstallmentItem")


@_attrs_define
class CardInstallmentItem:
    """카드사 + 결제유형 + 기준금액 단위의 무이자 할부 가능 정보 1건.

    같은 카드사라도 결제유형(일반/스마트페이) 또는 기준금액별로 행이 분리될 수 있다.
    AI prompt 는 payment_type 을 사용자에게 노출하지 않는다 (실제 결제는 챗봇 밖에서 진행).

        Attributes:
            iscm_cd (str): 카드사 코드 (OP_NINT_INST_BASE.ISCM_CD, 공통코드 그룹 'PAY014').
            payment_type (str): 결제유형. '스마트페이' (NINT_SMARTPAY_YN='Y') 또는 '일반' (그 외). AI 응답에서 사용자에게 노출 금지 — trace/QC 용 식별자.
            iscm_nm (None | str | Unset): 카드사 한글명 (FN_GET_COMMON_NAME_AI('ko','CODE',ISCM_CD,'PAY014') 결과). 공통코드 매핑 부재 시
                null.
            tgt_amt (int | None | Unset): 기준금액 (이 금액 이상부터 해당 개월 무이자 적용). NULL 가능.
            months (list[int] | Unset): 무이자 가능한 할부 개월수 목록. NINT_N_MM_YN='Y' 인 N 값만 오름차순으로 포함 (N ∈
                {2,3,4,5,6,7,8,9,10,11,12,24}).
    """

    iscm_cd: str
    payment_type: str
    iscm_nm: None | str | Unset = UNSET
    tgt_amt: int | None | Unset = UNSET
    months: list[int] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        iscm_cd = self.iscm_cd

        payment_type = self.payment_type

        iscm_nm: None | str | Unset
        if isinstance(self.iscm_nm, Unset):
            iscm_nm = UNSET
        else:
            iscm_nm = self.iscm_nm

        tgt_amt: int | None | Unset
        if isinstance(self.tgt_amt, Unset):
            tgt_amt = UNSET
        else:
            tgt_amt = self.tgt_amt

        months: list[int] | Unset = UNSET
        if not isinstance(self.months, Unset):
            months = self.months

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "iscm_cd": iscm_cd,
                "payment_type": payment_type,
            }
        )
        if iscm_nm is not UNSET:
            field_dict["iscm_nm"] = iscm_nm
        if tgt_amt is not UNSET:
            field_dict["tgt_amt"] = tgt_amt
        if months is not UNSET:
            field_dict["months"] = months

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        iscm_cd = d.pop("iscm_cd")

        payment_type = d.pop("payment_type")

        def _parse_iscm_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        iscm_nm = _parse_iscm_nm(d.pop("iscm_nm", UNSET))

        def _parse_tgt_amt(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        tgt_amt = _parse_tgt_amt(d.pop("tgt_amt", UNSET))

        months = cast(list[int], d.pop("months", UNSET))

        card_installment_item = cls(
            iscm_cd=iscm_cd,
            payment_type=payment_type,
            iscm_nm=iscm_nm,
            tgt_amt=tgt_amt,
            months=months,
        )

        card_installment_item.additional_properties = d
        return card_installment_item

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
