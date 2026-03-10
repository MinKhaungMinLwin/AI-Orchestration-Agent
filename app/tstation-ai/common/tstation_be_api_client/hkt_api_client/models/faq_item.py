from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="FaqItem")


@_attrs_define
class FaqItem:
    """
    Attributes:
        lrcl_cd (None | str | Unset): 대분류 코드 (LRCL_CD)
        mdcl_cd (None | str | Unset): 중분류 코드 (MDCL_CD)
        cust_quest (None | str | Unset): 질문 (CUST_QUEST)
        pc_ans_cont (None | str | Unset): 답변 (PC_ANS_CONT)
    """

    lrcl_cd: None | str | Unset = UNSET
    mdcl_cd: None | str | Unset = UNSET
    cust_quest: None | str | Unset = UNSET
    pc_ans_cont: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        lrcl_cd: None | str | Unset
        if isinstance(self.lrcl_cd, Unset):
            lrcl_cd = UNSET
        else:
            lrcl_cd = self.lrcl_cd

        mdcl_cd: None | str | Unset
        if isinstance(self.mdcl_cd, Unset):
            mdcl_cd = UNSET
        else:
            mdcl_cd = self.mdcl_cd

        cust_quest: None | str | Unset
        if isinstance(self.cust_quest, Unset):
            cust_quest = UNSET
        else:
            cust_quest = self.cust_quest

        pc_ans_cont: None | str | Unset
        if isinstance(self.pc_ans_cont, Unset):
            pc_ans_cont = UNSET
        else:
            pc_ans_cont = self.pc_ans_cont

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if lrcl_cd is not UNSET:
            field_dict["lrcl_cd"] = lrcl_cd
        if mdcl_cd is not UNSET:
            field_dict["mdcl_cd"] = mdcl_cd
        if cust_quest is not UNSET:
            field_dict["cust_quest"] = cust_quest
        if pc_ans_cont is not UNSET:
            field_dict["pc_ans_cont"] = pc_ans_cont

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_lrcl_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        lrcl_cd = _parse_lrcl_cd(d.pop("lrcl_cd", UNSET))

        def _parse_mdcl_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mdcl_cd = _parse_mdcl_cd(d.pop("mdcl_cd", UNSET))

        def _parse_cust_quest(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        cust_quest = _parse_cust_quest(d.pop("cust_quest", UNSET))

        def _parse_pc_ans_cont(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pc_ans_cont = _parse_pc_ans_cont(d.pop("pc_ans_cont", UNSET))

        faq_item = cls(
            lrcl_cd=lrcl_cd,
            mdcl_cd=mdcl_cd,
            cust_quest=cust_quest,
            pc_ans_cont=pc_ans_cont,
        )

        faq_item.additional_properties = d
        return faq_item

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
