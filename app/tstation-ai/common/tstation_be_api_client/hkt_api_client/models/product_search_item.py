from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ProductSearchItem")


@_attrs_define
class ProductSearchItem:
    """
    Attributes:
        goods_no (str): 상품 번호
        goods_nm (str): 상품명
        tire_size_1 (None | str | Unset): 타이어 사이즈 (TIRE_SIZE_1)
        tire_size_2 (None | str | Unset): 타이어 사이즈 (TIRE_SIZE_2)
        score (int | Unset): 검색 관련도 점수 Default: 0.
        match_type (str | Unset): 매칭 유형 (exact/prefix/partial/alias) Default: 'none'.
        image_url (None | str | Unset): 대표 이미지 URL (PR_PTRN_IMG_INFO IMG_SCT_CD='80' + IMAGE_BASE_URL)
        label_pnwave (None | str | Unset): EU 소음 라벨 등급 코드 (LABEL_PNWAVE). 값: 'AA'(최저소음) / 'A'(저소음) / 그 외
        label_pnwave_nm (None | str | Unset): EU 소음 라벨 등급명 (DECODE(LABEL_PNWAVE)): '최저소음' / '저소음' / ''
        label_pndb (None | str | Unset): EU 소음 데시벨 라벨 값 (LABEL_PNDB, VARCHAR2)
    """

    goods_no: str
    goods_nm: str
    tire_size_1: None | str | Unset = UNSET
    tire_size_2: None | str | Unset = UNSET
    score: int | Unset = 0
    match_type: str | Unset = "none"
    image_url: None | str | Unset = UNSET
    label_pnwave: None | str | Unset = UNSET
    label_pnwave_nm: None | str | Unset = UNSET
    label_pndb: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_no = self.goods_no

        goods_nm = self.goods_nm

        tire_size_1: None | str | Unset
        if isinstance(self.tire_size_1, Unset):
            tire_size_1 = UNSET
        else:
            tire_size_1 = self.tire_size_1

        tire_size_2: None | str | Unset
        if isinstance(self.tire_size_2, Unset):
            tire_size_2 = UNSET
        else:
            tire_size_2 = self.tire_size_2

        score = self.score

        match_type = self.match_type

        image_url: None | str | Unset
        if isinstance(self.image_url, Unset):
            image_url = UNSET
        else:
            image_url = self.image_url

        label_pnwave: None | str | Unset
        if isinstance(self.label_pnwave, Unset):
            label_pnwave = UNSET
        else:
            label_pnwave = self.label_pnwave

        label_pnwave_nm: None | str | Unset
        if isinstance(self.label_pnwave_nm, Unset):
            label_pnwave_nm = UNSET
        else:
            label_pnwave_nm = self.label_pnwave_nm

        label_pndb: None | str | Unset
        if isinstance(self.label_pndb, Unset):
            label_pndb = UNSET
        else:
            label_pndb = self.label_pndb

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goods_no": goods_no,
                "goods_nm": goods_nm,
            }
        )
        if tire_size_1 is not UNSET:
            field_dict["tire_size_1"] = tire_size_1
        if tire_size_2 is not UNSET:
            field_dict["tire_size_2"] = tire_size_2
        if score is not UNSET:
            field_dict["score"] = score
        if match_type is not UNSET:
            field_dict["match_type"] = match_type
        if image_url is not UNSET:
            field_dict["image_url"] = image_url
        if label_pnwave is not UNSET:
            field_dict["label_pnwave"] = label_pnwave
        if label_pnwave_nm is not UNSET:
            field_dict["label_pnwave_nm"] = label_pnwave_nm
        if label_pndb is not UNSET:
            field_dict["label_pndb"] = label_pndb

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        goods_no = d.pop("goods_no")

        goods_nm = d.pop("goods_nm")

        def _parse_tire_size_1(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tire_size_1 = _parse_tire_size_1(d.pop("tire_size_1", UNSET))

        def _parse_tire_size_2(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tire_size_2 = _parse_tire_size_2(d.pop("tire_size_2", UNSET))

        score = d.pop("score", UNSET)

        match_type = d.pop("match_type", UNSET)

        def _parse_image_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        image_url = _parse_image_url(d.pop("image_url", UNSET))

        def _parse_label_pnwave(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        label_pnwave = _parse_label_pnwave(d.pop("label_pnwave", UNSET))

        def _parse_label_pnwave_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        label_pnwave_nm = _parse_label_pnwave_nm(d.pop("label_pnwave_nm", UNSET))

        def _parse_label_pndb(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        label_pndb = _parse_label_pndb(d.pop("label_pndb", UNSET))

        product_search_item = cls(
            goods_no=goods_no,
            goods_nm=goods_nm,
            tire_size_1=tire_size_1,
            tire_size_2=tire_size_2,
            score=score,
            match_type=match_type,
            image_url=image_url,
            label_pnwave=label_pnwave,
            label_pnwave_nm=label_pnwave_nm,
            label_pndb=label_pndb,
        )

        product_search_item.additional_properties = d
        return product_search_item

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
