from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="EventApplicableProductItem")


@_attrs_define
class EventApplicableProductItem:
    """
    Attributes:
        aply_tp_cd (str): 적용 유형 코드 (50=상품, 80=패턴)
        goods_no (str): 상품 번호
        goods_nm (None | str | Unset): 상품명
        ptrn_cd (None | str | Unset): 패턴 코드
        tire_size_1 (None | str | Unset): 타이어 사이즈 (TIRE_SIZE_1, 예: '245/45R18')
        tire_size_2 (None | str | Unset): 타이어 사이즈 후륜 (TIRE_SIZE_2, 전후륜 다른 차량용)
        sale_prc (int | None | Unset): 기본 판매가 (PR_ITEM_PRC_INFO.SALE_PRC)
        extra_fvr_sale_prc (int | None | Unset): 최대 혜택 판매가. 회원 유형에 따라 PR_GOODS_DSCNT_PRC_INFO(일반) 또는
            PR_GOODS_ENTR_DSCNT_PRC_INFO(PARTNER)에서 join
        extra_fvr_sale_per (float | None | Unset): 최대 혜택 할인율 (%)
        smrt_pay_yn (None | str | Unset): 스마트페이 가능 여부 Y/N (활성 PR_ITEM_PRC_INFO.SMRT_PAY_PRC > 0 기준)
        image_url (None | str | Unset): 대표 이미지 URL (PR_PTRN_IMG_INFO IMG_SCT_CD='80' + IMAGE_BASE_URL)
        label_pnwave (None | str | Unset): EU 소음 라벨 등급 코드 (LABEL_PNWAVE). 값: 'AA'(최저소음) / 'A'(저소음) / 그 외
        label_pnwave_nm (None | str | Unset): EU 소음 라벨 등급명 (DECODE(LABEL_PNWAVE)): '최저소음' / '저소음' / ''
        label_pndb (None | str | Unset): EU 소음 데시벨 라벨 값 (LABEL_PNDB)
        prc_grd_nm (None | str | Unset): 가격 등급명 (PR_GOODS_BASE.PRC_GRD_NM). 응답값: '프리미엄' (DB 원본 '프리미엄+' 도 응답 단계에서 '프리미엄'
            으로 정규화) / '스탠다드' / '이코노미'
        goods_pfm_nm (None | str | Unset): 퍼포먼스 분류명 (PR_GOODS_BASE.GOODS_PFM_NM). 예:
            'COMFORT'(정숙/승차감)/'SPORT'(고속/제동성)/'RUNFLAT'(런플랫)
        t_oe_maker_1 (None | str | Unset): OE 메이커 코드/명 (PR_GOODS_BASE.T_OE_MAKER_1)
        oe_badge_yn (None | str | Unset): OE 뱃지 노출 여부. T_OE_MAKER_1 값이 있으면 Y, 없으면 N
        rating_avg (float | None | Unset): 패턴 평균 평점 (PR_GDAS_INFO.GDAS_SCR_VAL 평균, 0.0~5.0)
        review_count (int | None | Unset): 패턴 활성 리뷰 수
    """

    aply_tp_cd: str
    goods_no: str
    goods_nm: None | str | Unset = UNSET
    ptrn_cd: None | str | Unset = UNSET
    tire_size_1: None | str | Unset = UNSET
    tire_size_2: None | str | Unset = UNSET
    sale_prc: int | None | Unset = UNSET
    extra_fvr_sale_prc: int | None | Unset = UNSET
    extra_fvr_sale_per: float | None | Unset = UNSET
    smrt_pay_yn: None | str | Unset = UNSET
    image_url: None | str | Unset = UNSET
    label_pnwave: None | str | Unset = UNSET
    label_pnwave_nm: None | str | Unset = UNSET
    label_pndb: None | str | Unset = UNSET
    prc_grd_nm: None | str | Unset = UNSET
    goods_pfm_nm: None | str | Unset = UNSET
    t_oe_maker_1: None | str | Unset = UNSET
    oe_badge_yn: None | str | Unset = UNSET
    rating_avg: float | None | Unset = UNSET
    review_count: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        aply_tp_cd = self.aply_tp_cd

        goods_no = self.goods_no

        goods_nm: None | str | Unset
        if isinstance(self.goods_nm, Unset):
            goods_nm = UNSET
        else:
            goods_nm = self.goods_nm

        ptrn_cd: None | str | Unset
        if isinstance(self.ptrn_cd, Unset):
            ptrn_cd = UNSET
        else:
            ptrn_cd = self.ptrn_cd

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

        sale_prc: int | None | Unset
        if isinstance(self.sale_prc, Unset):
            sale_prc = UNSET
        else:
            sale_prc = self.sale_prc

        extra_fvr_sale_prc: int | None | Unset
        if isinstance(self.extra_fvr_sale_prc, Unset):
            extra_fvr_sale_prc = UNSET
        else:
            extra_fvr_sale_prc = self.extra_fvr_sale_prc

        extra_fvr_sale_per: float | None | Unset
        if isinstance(self.extra_fvr_sale_per, Unset):
            extra_fvr_sale_per = UNSET
        else:
            extra_fvr_sale_per = self.extra_fvr_sale_per

        smrt_pay_yn: None | str | Unset
        if isinstance(self.smrt_pay_yn, Unset):
            smrt_pay_yn = UNSET
        else:
            smrt_pay_yn = self.smrt_pay_yn

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

        t_oe_maker_1: None | str | Unset
        if isinstance(self.t_oe_maker_1, Unset):
            t_oe_maker_1 = UNSET
        else:
            t_oe_maker_1 = self.t_oe_maker_1

        oe_badge_yn: None | str | Unset
        if isinstance(self.oe_badge_yn, Unset):
            oe_badge_yn = UNSET
        else:
            oe_badge_yn = self.oe_badge_yn

        rating_avg: float | None | Unset
        if isinstance(self.rating_avg, Unset):
            rating_avg = UNSET
        else:
            rating_avg = self.rating_avg

        review_count: int | None | Unset
        if isinstance(self.review_count, Unset):
            review_count = UNSET
        else:
            review_count = self.review_count

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "aply_tp_cd": aply_tp_cd,
                "goods_no": goods_no,
            }
        )
        if goods_nm is not UNSET:
            field_dict["goods_nm"] = goods_nm
        if ptrn_cd is not UNSET:
            field_dict["ptrn_cd"] = ptrn_cd
        if tire_size_1 is not UNSET:
            field_dict["tire_size_1"] = tire_size_1
        if tire_size_2 is not UNSET:
            field_dict["tire_size_2"] = tire_size_2
        if sale_prc is not UNSET:
            field_dict["sale_prc"] = sale_prc
        if extra_fvr_sale_prc is not UNSET:
            field_dict["extra_fvr_sale_prc"] = extra_fvr_sale_prc
        if extra_fvr_sale_per is not UNSET:
            field_dict["extra_fvr_sale_per"] = extra_fvr_sale_per
        if smrt_pay_yn is not UNSET:
            field_dict["smrt_pay_yn"] = smrt_pay_yn
        if image_url is not UNSET:
            field_dict["image_url"] = image_url
        if label_pnwave is not UNSET:
            field_dict["label_pnwave"] = label_pnwave
        if label_pnwave_nm is not UNSET:
            field_dict["label_pnwave_nm"] = label_pnwave_nm
        if label_pndb is not UNSET:
            field_dict["label_pndb"] = label_pndb
        if prc_grd_nm is not UNSET:
            field_dict["prc_grd_nm"] = prc_grd_nm
        if goods_pfm_nm is not UNSET:
            field_dict["goods_pfm_nm"] = goods_pfm_nm
        if t_oe_maker_1 is not UNSET:
            field_dict["t_oe_maker_1"] = t_oe_maker_1
        if oe_badge_yn is not UNSET:
            field_dict["oe_badge_yn"] = oe_badge_yn
        if rating_avg is not UNSET:
            field_dict["rating_avg"] = rating_avg
        if review_count is not UNSET:
            field_dict["review_count"] = review_count

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        aply_tp_cd = d.pop("aply_tp_cd")

        goods_no = d.pop("goods_no")

        def _parse_goods_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        goods_nm = _parse_goods_nm(d.pop("goods_nm", UNSET))

        def _parse_ptrn_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ptrn_cd = _parse_ptrn_cd(d.pop("ptrn_cd", UNSET))

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

        def _parse_sale_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        sale_prc = _parse_sale_prc(d.pop("sale_prc", UNSET))

        def _parse_extra_fvr_sale_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        extra_fvr_sale_prc = _parse_extra_fvr_sale_prc(d.pop("extra_fvr_sale_prc", UNSET))

        def _parse_extra_fvr_sale_per(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        extra_fvr_sale_per = _parse_extra_fvr_sale_per(d.pop("extra_fvr_sale_per", UNSET))

        def _parse_smrt_pay_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        smrt_pay_yn = _parse_smrt_pay_yn(d.pop("smrt_pay_yn", UNSET))

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

        def _parse_t_oe_maker_1(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_oe_maker_1 = _parse_t_oe_maker_1(d.pop("t_oe_maker_1", UNSET))

        def _parse_oe_badge_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        oe_badge_yn = _parse_oe_badge_yn(d.pop("oe_badge_yn", UNSET))

        def _parse_rating_avg(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        rating_avg = _parse_rating_avg(d.pop("rating_avg", UNSET))

        def _parse_review_count(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        review_count = _parse_review_count(d.pop("review_count", UNSET))

        event_applicable_product_item = cls(
            aply_tp_cd=aply_tp_cd,
            goods_no=goods_no,
            goods_nm=goods_nm,
            ptrn_cd=ptrn_cd,
            tire_size_1=tire_size_1,
            tire_size_2=tire_size_2,
            sale_prc=sale_prc,
            extra_fvr_sale_prc=extra_fvr_sale_prc,
            extra_fvr_sale_per=extra_fvr_sale_per,
            smrt_pay_yn=smrt_pay_yn,
            image_url=image_url,
            label_pnwave=label_pnwave,
            label_pnwave_nm=label_pnwave_nm,
            label_pndb=label_pndb,
            prc_grd_nm=prc_grd_nm,
            goods_pfm_nm=goods_pfm_nm,
            t_oe_maker_1=t_oe_maker_1,
            oe_badge_yn=oe_badge_yn,
            rating_avg=rating_avg,
            review_count=review_count,
        )

        event_applicable_product_item.additional_properties = d
        return event_applicable_product_item

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
