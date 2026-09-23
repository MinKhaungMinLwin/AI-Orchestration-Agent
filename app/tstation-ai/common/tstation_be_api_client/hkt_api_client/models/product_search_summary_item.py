from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.product_search_summary_warranty import ProductSearchSummaryWarranty
    from ..models.review_item import ReviewItem


T = TypeVar("T", bound="ProductSearchSummaryItem")


@_attrs_define
class ProductSearchSummaryItem:
    """
    Attributes:
        ptrn_cd (str): 상품 패턴 코드. 상품군 식별자이며 특정 사이즈 SKU(goods_no)가 아님
        goods_nm (str): 상품명
        big_goods_nm (None | str | Unset): 대상품명 (BIG_GOODS_NM)
        ptrn_d_nm (None | str | Unset): 직관적 명칭 (PTRN_D_NM)
        available_sizes (list[str] | Unset): 해당 상품군에서 판매 가능한 타이어 규격 목록
        goods_no_count (int | Unset): 해당 상품군에 포함된 활성 SKU 수 Default: 0.
        score (int | Unset): 검색 관련도 점수 Default: 0.
        match_type (str | Unset): 매칭 유형 (exact/prefix/partial/alias) Default: 'none'.
        image_url (None | str | Unset): 대표 이미지 URL
        rating_avg (float | Unset): 패턴 기준 리뷰 평균 별점 Default: 0.0.
        review_count (int | Unset): 패턴 기준 리뷰 수 Default: 0.
        min_sale_prc (int | None | Unset): 활성 SKU 중 최저 판매가
        max_sale_prc (int | None | Unset): 활성 SKU 중 최고 판매가
        min_extra_fvr_sale_prc (int | None | Unset): 활성 SKU 중 최저 최대혜택가
        max_extra_fvr_sale_prc (int | None | Unset): 활성 SKU 중 최고 최대혜택가
        max_extra_fvr_sale_per (float | None | Unset): 활성 SKU 중 최대 혜택 할인율
        smrt_pay_yn (None | str | Unset): 스마트페이 가능 SKU 포함 여부 Y/N
        prc_grd_nm (None | str | Unset): 가격 등급명
        goods_pfm_nm (None | str | Unset): 퍼포먼스 분류명
        goods_dtl_pfm_nm (None | str | Unset): 세부 퍼포먼스 분류명
        sound_absorber_yn (None | str | Unset): 흡음재 적용 여부 Y/N
        three_pmsf_yn (None | str | Unset): 3PMSF/삼봉마크 인증 여부 Y/N
        season_nm (None | str | Unset): 계절 속성
        car_knd_nm (None | str | Unset): 차종 속성
        brand_nm (None | str | Unset): 브랜드명
        certify_brand_nm (None | str | Unset): 공식인증 브랜드명
        orpl_nm (None | str | Unset): 원산지명
        t_rls_yearmon (None | str | Unset): 출시년월
        rr (None | str | Unset): 회전저항 등급
        wet (None | str | Unset): 젖은노면 제동 등급
        label_pnwave (None | str | Unset): EU 소음 라벨 등급 코드
        label_pnwave_nm (None | str | Unset): EU 소음 라벨 등급명
        label_pndb (None | str | Unset): EU 소음 데시벨 라벨 값
        slogan (None | str | Unset): 슬로건
        pc_prod_remark_desc (None | str | Unset): 특장점
        pc_prod_tech_desc (None | str | Unset): 기술력
        reviews (list[ReviewItem] | Unset): 패턴 기준 평점 높은 대표 리뷰 최대 5개
        warranty (ProductSearchSummaryWarranty | Unset):
    """

    ptrn_cd: str
    goods_nm: str
    big_goods_nm: None | str | Unset = UNSET
    ptrn_d_nm: None | str | Unset = UNSET
    available_sizes: list[str] | Unset = UNSET
    goods_no_count: int | Unset = 0
    score: int | Unset = 0
    match_type: str | Unset = "none"
    image_url: None | str | Unset = UNSET
    rating_avg: float | Unset = 0.0
    review_count: int | Unset = 0
    min_sale_prc: int | None | Unset = UNSET
    max_sale_prc: int | None | Unset = UNSET
    min_extra_fvr_sale_prc: int | None | Unset = UNSET
    max_extra_fvr_sale_prc: int | None | Unset = UNSET
    max_extra_fvr_sale_per: float | None | Unset = UNSET
    smrt_pay_yn: None | str | Unset = UNSET
    prc_grd_nm: None | str | Unset = UNSET
    goods_pfm_nm: None | str | Unset = UNSET
    goods_dtl_pfm_nm: None | str | Unset = UNSET
    sound_absorber_yn: None | str | Unset = UNSET
    three_pmsf_yn: None | str | Unset = UNSET
    season_nm: None | str | Unset = UNSET
    car_knd_nm: None | str | Unset = UNSET
    brand_nm: None | str | Unset = UNSET
    certify_brand_nm: None | str | Unset = UNSET
    orpl_nm: None | str | Unset = UNSET
    t_rls_yearmon: None | str | Unset = UNSET
    rr: None | str | Unset = UNSET
    wet: None | str | Unset = UNSET
    label_pnwave: None | str | Unset = UNSET
    label_pnwave_nm: None | str | Unset = UNSET
    label_pndb: None | str | Unset = UNSET
    slogan: None | str | Unset = UNSET
    pc_prod_remark_desc: None | str | Unset = UNSET
    pc_prod_tech_desc: None | str | Unset = UNSET
    reviews: list[ReviewItem] | Unset = UNSET
    warranty: ProductSearchSummaryWarranty | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ptrn_cd = self.ptrn_cd

        goods_nm = self.goods_nm

        big_goods_nm: None | str | Unset
        if isinstance(self.big_goods_nm, Unset):
            big_goods_nm = UNSET
        else:
            big_goods_nm = self.big_goods_nm

        ptrn_d_nm: None | str | Unset
        if isinstance(self.ptrn_d_nm, Unset):
            ptrn_d_nm = UNSET
        else:
            ptrn_d_nm = self.ptrn_d_nm

        available_sizes: list[str] | Unset = UNSET
        if not isinstance(self.available_sizes, Unset):
            available_sizes = self.available_sizes

        goods_no_count = self.goods_no_count

        score = self.score

        match_type = self.match_type

        image_url: None | str | Unset
        if isinstance(self.image_url, Unset):
            image_url = UNSET
        else:
            image_url = self.image_url

        rating_avg = self.rating_avg

        review_count = self.review_count

        min_sale_prc: int | None | Unset
        if isinstance(self.min_sale_prc, Unset):
            min_sale_prc = UNSET
        else:
            min_sale_prc = self.min_sale_prc

        max_sale_prc: int | None | Unset
        if isinstance(self.max_sale_prc, Unset):
            max_sale_prc = UNSET
        else:
            max_sale_prc = self.max_sale_prc

        min_extra_fvr_sale_prc: int | None | Unset
        if isinstance(self.min_extra_fvr_sale_prc, Unset):
            min_extra_fvr_sale_prc = UNSET
        else:
            min_extra_fvr_sale_prc = self.min_extra_fvr_sale_prc

        max_extra_fvr_sale_prc: int | None | Unset
        if isinstance(self.max_extra_fvr_sale_prc, Unset):
            max_extra_fvr_sale_prc = UNSET
        else:
            max_extra_fvr_sale_prc = self.max_extra_fvr_sale_prc

        max_extra_fvr_sale_per: float | None | Unset
        if isinstance(self.max_extra_fvr_sale_per, Unset):
            max_extra_fvr_sale_per = UNSET
        else:
            max_extra_fvr_sale_per = self.max_extra_fvr_sale_per

        smrt_pay_yn: None | str | Unset
        if isinstance(self.smrt_pay_yn, Unset):
            smrt_pay_yn = UNSET
        else:
            smrt_pay_yn = self.smrt_pay_yn

        prc_grd_nm: None | str | Unset
        if isinstance(self.prc_grd_nm, Unset):
            prc_grd_nm = UNSET
        else:
            prc_grd_nm = self.prc_grd_nm

        goods_pfm_nm: None | str | Unset
        if isinstance(self.goods_pfm_nm, Unset):
            goods_pfm_nm = UNSET
        else:
            goods_pfm_nm = self.goods_pfm_nm

        goods_dtl_pfm_nm: None | str | Unset
        if isinstance(self.goods_dtl_pfm_nm, Unset):
            goods_dtl_pfm_nm = UNSET
        else:
            goods_dtl_pfm_nm = self.goods_dtl_pfm_nm

        sound_absorber_yn: None | str | Unset
        if isinstance(self.sound_absorber_yn, Unset):
            sound_absorber_yn = UNSET
        else:
            sound_absorber_yn = self.sound_absorber_yn

        three_pmsf_yn: None | str | Unset
        if isinstance(self.three_pmsf_yn, Unset):
            three_pmsf_yn = UNSET
        else:
            three_pmsf_yn = self.three_pmsf_yn

        season_nm: None | str | Unset
        if isinstance(self.season_nm, Unset):
            season_nm = UNSET
        else:
            season_nm = self.season_nm

        car_knd_nm: None | str | Unset
        if isinstance(self.car_knd_nm, Unset):
            car_knd_nm = UNSET
        else:
            car_knd_nm = self.car_knd_nm

        brand_nm: None | str | Unset
        if isinstance(self.brand_nm, Unset):
            brand_nm = UNSET
        else:
            brand_nm = self.brand_nm

        certify_brand_nm: None | str | Unset
        if isinstance(self.certify_brand_nm, Unset):
            certify_brand_nm = UNSET
        else:
            certify_brand_nm = self.certify_brand_nm

        orpl_nm: None | str | Unset
        if isinstance(self.orpl_nm, Unset):
            orpl_nm = UNSET
        else:
            orpl_nm = self.orpl_nm

        t_rls_yearmon: None | str | Unset
        if isinstance(self.t_rls_yearmon, Unset):
            t_rls_yearmon = UNSET
        else:
            t_rls_yearmon = self.t_rls_yearmon

        rr: None | str | Unset
        if isinstance(self.rr, Unset):
            rr = UNSET
        else:
            rr = self.rr

        wet: None | str | Unset
        if isinstance(self.wet, Unset):
            wet = UNSET
        else:
            wet = self.wet

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

        slogan: None | str | Unset
        if isinstance(self.slogan, Unset):
            slogan = UNSET
        else:
            slogan = self.slogan

        pc_prod_remark_desc: None | str | Unset
        if isinstance(self.pc_prod_remark_desc, Unset):
            pc_prod_remark_desc = UNSET
        else:
            pc_prod_remark_desc = self.pc_prod_remark_desc

        pc_prod_tech_desc: None | str | Unset
        if isinstance(self.pc_prod_tech_desc, Unset):
            pc_prod_tech_desc = UNSET
        else:
            pc_prod_tech_desc = self.pc_prod_tech_desc

        reviews: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.reviews, Unset):
            reviews = []
            for reviews_item_data in self.reviews:
                reviews_item = reviews_item_data.to_dict()
                reviews.append(reviews_item)

        warranty: dict[str, Any] | Unset = UNSET
        if not isinstance(self.warranty, Unset):
            warranty = self.warranty.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ptrn_cd": ptrn_cd,
                "goods_nm": goods_nm,
            }
        )
        if big_goods_nm is not UNSET:
            field_dict["big_goods_nm"] = big_goods_nm
        if ptrn_d_nm is not UNSET:
            field_dict["ptrn_d_nm"] = ptrn_d_nm
        if available_sizes is not UNSET:
            field_dict["available_sizes"] = available_sizes
        if goods_no_count is not UNSET:
            field_dict["goods_no_count"] = goods_no_count
        if score is not UNSET:
            field_dict["score"] = score
        if match_type is not UNSET:
            field_dict["match_type"] = match_type
        if image_url is not UNSET:
            field_dict["image_url"] = image_url
        if rating_avg is not UNSET:
            field_dict["rating_avg"] = rating_avg
        if review_count is not UNSET:
            field_dict["review_count"] = review_count
        if min_sale_prc is not UNSET:
            field_dict["min_sale_prc"] = min_sale_prc
        if max_sale_prc is not UNSET:
            field_dict["max_sale_prc"] = max_sale_prc
        if min_extra_fvr_sale_prc is not UNSET:
            field_dict["min_extra_fvr_sale_prc"] = min_extra_fvr_sale_prc
        if max_extra_fvr_sale_prc is not UNSET:
            field_dict["max_extra_fvr_sale_prc"] = max_extra_fvr_sale_prc
        if max_extra_fvr_sale_per is not UNSET:
            field_dict["max_extra_fvr_sale_per"] = max_extra_fvr_sale_per
        if smrt_pay_yn is not UNSET:
            field_dict["smrt_pay_yn"] = smrt_pay_yn
        if prc_grd_nm is not UNSET:
            field_dict["prc_grd_nm"] = prc_grd_nm
        if goods_pfm_nm is not UNSET:
            field_dict["goods_pfm_nm"] = goods_pfm_nm
        if goods_dtl_pfm_nm is not UNSET:
            field_dict["goods_dtl_pfm_nm"] = goods_dtl_pfm_nm
        if sound_absorber_yn is not UNSET:
            field_dict["sound_absorber_yn"] = sound_absorber_yn
        if three_pmsf_yn is not UNSET:
            field_dict["three_pmsf_yn"] = three_pmsf_yn
        if season_nm is not UNSET:
            field_dict["season_nm"] = season_nm
        if car_knd_nm is not UNSET:
            field_dict["car_knd_nm"] = car_knd_nm
        if brand_nm is not UNSET:
            field_dict["brand_nm"] = brand_nm
        if certify_brand_nm is not UNSET:
            field_dict["certify_brand_nm"] = certify_brand_nm
        if orpl_nm is not UNSET:
            field_dict["orpl_nm"] = orpl_nm
        if t_rls_yearmon is not UNSET:
            field_dict["t_rls_yearmon"] = t_rls_yearmon
        if rr is not UNSET:
            field_dict["rr"] = rr
        if wet is not UNSET:
            field_dict["wet"] = wet
        if label_pnwave is not UNSET:
            field_dict["label_pnwave"] = label_pnwave
        if label_pnwave_nm is not UNSET:
            field_dict["label_pnwave_nm"] = label_pnwave_nm
        if label_pndb is not UNSET:
            field_dict["label_pndb"] = label_pndb
        if slogan is not UNSET:
            field_dict["slogan"] = slogan
        if pc_prod_remark_desc is not UNSET:
            field_dict["pc_prod_remark_desc"] = pc_prod_remark_desc
        if pc_prod_tech_desc is not UNSET:
            field_dict["pc_prod_tech_desc"] = pc_prod_tech_desc
        if reviews is not UNSET:
            field_dict["reviews"] = reviews
        if warranty is not UNSET:
            field_dict["warranty"] = warranty

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.product_search_summary_warranty import ProductSearchSummaryWarranty
        from ..models.review_item import ReviewItem

        d = dict(src_dict)
        ptrn_cd = d.pop("ptrn_cd")

        goods_nm = d.pop("goods_nm")

        def _parse_big_goods_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        big_goods_nm = _parse_big_goods_nm(d.pop("big_goods_nm", UNSET))

        def _parse_ptrn_d_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ptrn_d_nm = _parse_ptrn_d_nm(d.pop("ptrn_d_nm", UNSET))

        available_sizes = cast(list[str], d.pop("available_sizes", UNSET))

        goods_no_count = d.pop("goods_no_count", UNSET)

        score = d.pop("score", UNSET)

        match_type = d.pop("match_type", UNSET)

        def _parse_image_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        image_url = _parse_image_url(d.pop("image_url", UNSET))

        rating_avg = d.pop("rating_avg", UNSET)

        review_count = d.pop("review_count", UNSET)

        def _parse_min_sale_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        min_sale_prc = _parse_min_sale_prc(d.pop("min_sale_prc", UNSET))

        def _parse_max_sale_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_sale_prc = _parse_max_sale_prc(d.pop("max_sale_prc", UNSET))

        def _parse_min_extra_fvr_sale_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        min_extra_fvr_sale_prc = _parse_min_extra_fvr_sale_prc(d.pop("min_extra_fvr_sale_prc", UNSET))

        def _parse_max_extra_fvr_sale_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        max_extra_fvr_sale_prc = _parse_max_extra_fvr_sale_prc(d.pop("max_extra_fvr_sale_prc", UNSET))

        def _parse_max_extra_fvr_sale_per(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        max_extra_fvr_sale_per = _parse_max_extra_fvr_sale_per(d.pop("max_extra_fvr_sale_per", UNSET))

        def _parse_smrt_pay_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        smrt_pay_yn = _parse_smrt_pay_yn(d.pop("smrt_pay_yn", UNSET))

        def _parse_prc_grd_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        prc_grd_nm = _parse_prc_grd_nm(d.pop("prc_grd_nm", UNSET))

        def _parse_goods_pfm_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        goods_pfm_nm = _parse_goods_pfm_nm(d.pop("goods_pfm_nm", UNSET))

        def _parse_goods_dtl_pfm_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        goods_dtl_pfm_nm = _parse_goods_dtl_pfm_nm(d.pop("goods_dtl_pfm_nm", UNSET))

        def _parse_sound_absorber_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sound_absorber_yn = _parse_sound_absorber_yn(d.pop("sound_absorber_yn", UNSET))

        def _parse_three_pmsf_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        three_pmsf_yn = _parse_three_pmsf_yn(d.pop("three_pmsf_yn", UNSET))

        def _parse_season_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        season_nm = _parse_season_nm(d.pop("season_nm", UNSET))

        def _parse_car_knd_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_knd_nm = _parse_car_knd_nm(d.pop("car_knd_nm", UNSET))

        def _parse_brand_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        brand_nm = _parse_brand_nm(d.pop("brand_nm", UNSET))

        def _parse_certify_brand_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        certify_brand_nm = _parse_certify_brand_nm(d.pop("certify_brand_nm", UNSET))

        def _parse_orpl_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        orpl_nm = _parse_orpl_nm(d.pop("orpl_nm", UNSET))

        def _parse_t_rls_yearmon(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_rls_yearmon = _parse_t_rls_yearmon(d.pop("t_rls_yearmon", UNSET))

        def _parse_rr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rr = _parse_rr(d.pop("rr", UNSET))

        def _parse_wet(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        wet = _parse_wet(d.pop("wet", UNSET))

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

        def _parse_slogan(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        slogan = _parse_slogan(d.pop("slogan", UNSET))

        def _parse_pc_prod_remark_desc(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pc_prod_remark_desc = _parse_pc_prod_remark_desc(d.pop("pc_prod_remark_desc", UNSET))

        def _parse_pc_prod_tech_desc(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pc_prod_tech_desc = _parse_pc_prod_tech_desc(d.pop("pc_prod_tech_desc", UNSET))

        _reviews = d.pop("reviews", UNSET)
        reviews: list[ReviewItem] | Unset = UNSET
        if _reviews is not UNSET:
            reviews = []
            for reviews_item_data in _reviews:
                reviews_item = ReviewItem.from_dict(reviews_item_data)

                reviews.append(reviews_item)

        _warranty = d.pop("warranty", UNSET)
        warranty: ProductSearchSummaryWarranty | Unset
        if isinstance(_warranty, Unset):
            warranty = UNSET
        else:
            warranty = ProductSearchSummaryWarranty.from_dict(_warranty)

        product_search_summary_item = cls(
            ptrn_cd=ptrn_cd,
            goods_nm=goods_nm,
            big_goods_nm=big_goods_nm,
            ptrn_d_nm=ptrn_d_nm,
            available_sizes=available_sizes,
            goods_no_count=goods_no_count,
            score=score,
            match_type=match_type,
            image_url=image_url,
            rating_avg=rating_avg,
            review_count=review_count,
            min_sale_prc=min_sale_prc,
            max_sale_prc=max_sale_prc,
            min_extra_fvr_sale_prc=min_extra_fvr_sale_prc,
            max_extra_fvr_sale_prc=max_extra_fvr_sale_prc,
            max_extra_fvr_sale_per=max_extra_fvr_sale_per,
            smrt_pay_yn=smrt_pay_yn,
            prc_grd_nm=prc_grd_nm,
            goods_pfm_nm=goods_pfm_nm,
            goods_dtl_pfm_nm=goods_dtl_pfm_nm,
            sound_absorber_yn=sound_absorber_yn,
            three_pmsf_yn=three_pmsf_yn,
            season_nm=season_nm,
            car_knd_nm=car_knd_nm,
            brand_nm=brand_nm,
            certify_brand_nm=certify_brand_nm,
            orpl_nm=orpl_nm,
            t_rls_yearmon=t_rls_yearmon,
            rr=rr,
            wet=wet,
            label_pnwave=label_pnwave,
            label_pnwave_nm=label_pnwave_nm,
            label_pndb=label_pndb,
            slogan=slogan,
            pc_prod_remark_desc=pc_prod_remark_desc,
            pc_prod_tech_desc=pc_prod_tech_desc,
            reviews=reviews,
            warranty=warranty,
        )

        product_search_summary_item.additional_properties = d
        return product_search_summary_item

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
