from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.review_item import ReviewItem
    from ..models.review_rating import ReviewRating


T = TypeVar("T", bound="ReviewData")


@_attrs_define
class ReviewData:
    """
    Attributes:
        goods_no (str): 상품 번호
        rating (ReviewRating | Unset):
        reviews (list[ReviewItem] | Unset): 리뷰 목록
    """

    goods_no: str
    rating: ReviewRating | Unset = UNSET
    reviews: list[ReviewItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_no = self.goods_no

        rating: dict[str, Any] | Unset = UNSET
        if not isinstance(self.rating, Unset):
            rating = self.rating.to_dict()

        reviews: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.reviews, Unset):
            reviews = []
            for reviews_item_data in self.reviews:
                reviews_item = reviews_item_data.to_dict()
                reviews.append(reviews_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goods_no": goods_no,
            }
        )
        if rating is not UNSET:
            field_dict["rating"] = rating
        if reviews is not UNSET:
            field_dict["reviews"] = reviews

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.review_item import ReviewItem
        from ..models.review_rating import ReviewRating

        d = dict(src_dict)
        goods_no = d.pop("goods_no")

        _rating = d.pop("rating", UNSET)
        rating: ReviewRating | Unset
        if isinstance(_rating, Unset):
            rating = UNSET
        else:
            rating = ReviewRating.from_dict(_rating)

        _reviews = d.pop("reviews", UNSET)
        reviews: list[ReviewItem] | Unset = UNSET
        if _reviews is not UNSET:
            reviews = []
            for reviews_item_data in _reviews:
                reviews_item = ReviewItem.from_dict(reviews_item_data)

                reviews.append(reviews_item)

        review_data = cls(
            goods_no=goods_no,
            rating=rating,
            reviews=reviews,
        )

        review_data.additional_properties = d
        return review_data

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
