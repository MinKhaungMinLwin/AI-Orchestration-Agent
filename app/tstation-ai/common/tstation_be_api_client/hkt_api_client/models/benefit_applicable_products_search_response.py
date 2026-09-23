from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.benefit_applicable_products_match import BenefitApplicableProductsMatch


T = TypeVar("T", bound="BenefitApplicableProductsSearchResponse")


@_attrs_define
class BenefitApplicableProductsSearchResponse:
    """
    Attributes:
        query (str): 검색어
        total_matches (int): 검색어에 매칭되고 적용 상품/매장이 있는 혜택 수
        total_products (int): 전체 대표 상품 수
        total_stores (int | Unset): 전체 매장 수 Default: 0.
        matches (list[BenefitApplicableProductsMatch] | Unset): 쿠폰/이벤트/기획전 통합 적용 상품 검색 결과
    """

    query: str
    total_matches: int
    total_products: int
    total_stores: int | Unset = 0
    matches: list[BenefitApplicableProductsMatch] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        query = self.query

        total_matches = self.total_matches

        total_products = self.total_products

        total_stores = self.total_stores

        matches: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.matches, Unset):
            matches = []
            for matches_item_data in self.matches:
                matches_item = matches_item_data.to_dict()
                matches.append(matches_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "query": query,
                "total_matches": total_matches,
                "total_products": total_products,
            }
        )
        if total_stores is not UNSET:
            field_dict["total_stores"] = total_stores
        if matches is not UNSET:
            field_dict["matches"] = matches

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.benefit_applicable_products_match import BenefitApplicableProductsMatch

        d = dict(src_dict)
        query = d.pop("query")

        total_matches = d.pop("total_matches")

        total_products = d.pop("total_products")

        total_stores = d.pop("total_stores", UNSET)

        _matches = d.pop("matches", UNSET)
        matches: list[BenefitApplicableProductsMatch] | Unset = UNSET
        if _matches is not UNSET:
            matches = []
            for matches_item_data in _matches:
                matches_item = BenefitApplicableProductsMatch.from_dict(matches_item_data)

                matches.append(matches_item)

        benefit_applicable_products_search_response = cls(
            query=query,
            total_matches=total_matches,
            total_products=total_products,
            total_stores=total_stores,
            matches=matches,
        )

        benefit_applicable_products_search_response.additional_properties = d
        return benefit_applicable_products_search_response

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
