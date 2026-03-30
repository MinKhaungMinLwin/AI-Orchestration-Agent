from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ReviewRating")


@_attrs_define
class ReviewRating:
    """
    Attributes:
        review_count (int | Unset): 리뷰 수 Default: 0.
        rating_avg (float | Unset): 평점 평균 Default: 0.0.
    """

    review_count: int | Unset = 0
    rating_avg: float | Unset = 0.0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        review_count = self.review_count

        rating_avg = self.rating_avg

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if review_count is not UNSET:
            field_dict["review_count"] = review_count
        if rating_avg is not UNSET:
            field_dict["rating_avg"] = rating_avg

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        review_count = d.pop("review_count", UNSET)

        rating_avg = d.pop("rating_avg", UNSET)

        review_rating = cls(
            review_count=review_count,
            rating_avg=rating_avg,
        )

        review_rating.additional_properties = d
        return review_rating

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
