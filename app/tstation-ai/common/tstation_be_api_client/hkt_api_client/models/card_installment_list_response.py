from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.card_installment_item import CardInstallmentItem


T = TypeVar("T", bound="CardInstallmentListResponse")


@_attrs_define
class CardInstallmentListResponse:
    """
    Attributes:
        cards (list[CardInstallmentItem] | Unset): 진행중(SYSDATE BETWEEN APLY_STRT_DTIME AND APLY_END_DTIME) 인 무이자 할부 정보
            목록. ISCM_CD 오름차순 → TGT_AMT 오름차순.
    """

    cards: list[CardInstallmentItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cards: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.cards, Unset):
            cards = []
            for cards_item_data in self.cards:
                cards_item = cards_item_data.to_dict()
                cards.append(cards_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if cards is not UNSET:
            field_dict["cards"] = cards

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.card_installment_item import CardInstallmentItem

        d = dict(src_dict)
        _cards = d.pop("cards", UNSET)
        cards: list[CardInstallmentItem] | Unset = UNSET
        if _cards is not UNSET:
            cards = []
            for cards_item_data in _cards:
                cards_item = CardInstallmentItem.from_dict(cards_item_data)

                cards.append(cards_item)

        card_installment_list_response = cls(
            cards=cards,
        )

        card_installment_list_response.additional_properties = d
        return card_installment_list_response

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
